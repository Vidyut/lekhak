"""The filesystem layout: writing a project out as a folder tree, and reading
it back (docs/STORAGE.md).

This is the storage migration's core, built *beside* the existing database
rather than replacing it — nothing in the running application calls this yet.
It exists so the tree can be written, read back, and compared before anything
real depends on it.

It works on plain :class:`Node` values, not on the database, so it can be
tested without a project and without Qt.

Frontmatter and manifests use a documented **subset of YAML** — keys, scalars,
simple lists, and one level of nesting by indentation. No anchors, aliases,
multi-document streams or tags; no dependency (docs/STORAGE.md).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Nothing on the three target filesystems will take these; Windows also
# reserves a handful of device names, and a file called NUL.txt is a headache.
ILLEGAL_EXTRA = set('<>:"/\\|?*')
RESERVED_NAMES = {"con", "prn", "aux", "nul",
                  *(f"com{n}" for n in range(1, 10)),
                  *(f"lpt{n}" for n in range(1, 10))}
MAX_LENGTH = 80

MACHINERY = ".lekhak"
PROJECT_MANIFEST = f"{MACHINERY}/project.yaml"
FOLDER_MANIFEST = f"{MACHINERY}/folder.yaml"
INDEX_NAME = "index.html"
DOCUMENT_SUFFIX = ".html"
FORMAT_VERSION = 1


# --- names -------------------------------------------------------------------

def slug(title: str) -> str:
    """The filename for a title: no spaces, nothing a filesystem refuses.

    Letters and digits survive in any script, and so do ``-`` and ``_``;
    spaces and everything else collapse to a single hyphen; the ends trim; the
    length caps; an empty title becomes ``Untitled``. Titles in the author's
    binder look like ``3 - Zayn meets Ari`` and ``1---AxAm's room``, which
    come out as ``3-Zayn-meets-Ari`` and ``1-AxAm-s-room``.
    """
    characters = []
    for character in unicodedata.normalize("NFC", title).strip():
        # Combining marks are not separators: Devanagari and European
        # diacritics would otherwise be hyphenated mid-word (अंत, café).
        if (character.isalnum() or character in "-_"
                or unicodedata.category(character).startswith("M")):
            characters.append(character)
        else:
            characters.append("-")
    name = "".join(characters)
    while "--" in name:
        name = name.replace("--", "-")
    name = name.strip("-._")[:MAX_LENGTH].rstrip("-._")
    if not name:
        name = "Untitled"
    if name.split(".")[0].casefold() in RESERVED_NAMES:
        name = f"_{name}"
    return name


def unique_name(name: str, taken: set[str]) -> str:
    """``Book``, then ``Book-2``, ``Book-3`` — compared case-insensitively,
    because macOS and Windows filesystems are (docs/STORAGE.md)."""
    if name.casefold() not in taken:
        return name
    number = 2
    while f"{name}-{number}".casefold() in taken:
        number += 1
    return f"{name}-{number}"


# --- the documented YAML subset ----------------------------------------------

def _scalar(value) -> str:
    """"A value, quoted only when it has to be."""
    text = "" if value is None else str(value)
    needs_quotes = (
        text == ""
        or text != text.strip()
        or ": " in text
        or text.startswith(("-", "#", '"', "'", "&", "*", "!", "|", ">", "%", "@", "`"))
        or text.casefold() in {"true", "false", "null", "~"}
    )
    if needs_quotes:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def _value(raw: str):
    """The value a scalar stands for: unquoted numbers and booleans become
    their Python types, everything else stays text."""
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if raw.lstrip("-").isdigit():
        return int(raw)
    if raw.casefold() in {"true", "false"}:
        return raw.casefold() == "true"
    if raw.casefold() in {"null", "~", ""}:
        return ""
    return raw


def dump_frontmatter(values: dict) -> str:
    """A ``---`` block: scalars, one level of nesting, lists of scalars."""
    lines = ["---"]
    for key, value in values.items():
        if isinstance(value, dict):
            lines.append(f"{key}:")
            for sub_key, sub_value in value.items():
                lines.append(f"  {sub_key}: {_scalar(sub_value)}")
        elif isinstance(value, (list, tuple)):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {_scalar(item)}")
        else:
            lines.append(f"{key}: {_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a file into (frontmatter, the rest).

    A file with no ``---`` block is all content, and its frontmatter is empty —
    a document edited by hand or written by another tool still loads.
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    after = text.find("\n", end + 1)
    rest = text[after + 1:] if after != -1 else ""
    values: dict = {}
    current = None
    for line in text[3:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - "):
            bucket = values.get(current)
            if not isinstance(bucket, list):
                bucket = []
                values[current] = bucket
            bucket.append(_value(line[4:]))
        elif line.startswith("  "):
            bucket = values.get(current)
            if not isinstance(bucket, dict):
                bucket = {}
                values[current] = bucket
            key, _, value = line.strip().partition(":")
            bucket[key.strip()] = _value(value)
        else:
            key, _, value = line.partition(":")
            current = key.strip()
            values[current] = _value(value) if value.strip() else None
    return values, rest


# --- the tree ----------------------------------------------------------------

@dataclass
class Node:
    """One binder item, as the filesystem will hold it."""

    id: str
    title: str
    kind: str = "document"          # physical: "folder" or "document"
    type: str = ""                  # the role, from Type metadata
    content: str = ""               # prose HTML, frontmatter excluded
    synopsis: str = ""
    word_target: int = 0
    metadata: dict = field(default_factory=dict)
    children: list["Node"] = field(default_factory=list)

    @property
    def is_container(self) -> bool:
        """A container is a directory, whatever its role: a filesystem item
        cannot be a file and a directory at once (docs/STORAGE.md)."""
        return self.kind == "folder" or bool(self.children)


def _document_text(node: Node) -> str:
    """Frontmatter plus prose — the file's whole content."""
    frontmatter = {
        "title": node.title,
        "id": node.id,
        "type": node.type,
        "synopsis": node.synopsis,
        "word_target": node.word_target,
    }
    if node.metadata:
        frontmatter["metadata"] = dict(node.metadata)
    return dump_frontmatter(frontmatter) + node.content


def write_tree(root: Path, nodes: list[Node], *, title: str = "",
               settings: dict | None = None) -> dict:
    """Write a whole project as a folder tree; returns what it wrote."""
    root = Path(root)
    (root / MACHINERY).mkdir(parents=True, exist_ok=True)
    (root / PROJECT_MANIFEST).write_text(
        dump_frontmatter({"title": title, "format": FORMAT_VERSION,
                          "settings": dict(settings or {})}),
        encoding="utf-8")
    stats = {"folders": 0, "documents": 0, "indexes": 0}
    _write_level(root, nodes, stats)
    return stats


def _write_level(parent: Path, nodes: list[Node], stats: dict) -> list[str]:
    """One folder's children, in the order given — names first, so a folder's
    manifest can record exactly what its siblings were called."""
    taken: set[str] = set()
    plan: list[tuple[Node, str]] = []
    for node in nodes:
        name = unique_name(slug(node.title), taken)
        taken.add(name.casefold())
        plan.append((node, name))

    written: list[str] = []
    for node, name in plan:
        if node.is_container:
            folder = parent / name
            folder.mkdir(parents=True, exist_ok=True)
            stats["folders"] += 1
            child_names = _write_level(folder, node.children, stats)
            if node.content.strip():
                (folder / INDEX_NAME).write_text(_document_text(node),
                                                 encoding="utf-8")
                stats["indexes"] += 1
            manifest = folder / FOLDER_MANIFEST
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                dump_frontmatter({"id": node.id, "title": node.title,
                                  "type": node.type,
                                  "children": child_names}),
                encoding="utf-8")
            written.append(name + "/")
        else:
            (parent / f"{name}{DOCUMENT_SUFFIX}").write_text(
                _document_text(node), encoding="utf-8")
            stats["documents"] += 1
            written.append(f"{name}{DOCUMENT_SUFFIX}")
    return written


def load_tree(root: Path) -> tuple[list[Node], dict]:
    """Read a folder tree back into nodes, and the project manifest with it."""
    root = Path(root)
    manifest = root / PROJECT_MANIFEST
    project = {}
    if manifest.exists():
        project, _rest = parse_frontmatter(manifest.read_text(encoding="utf-8"))
    return _load_level(root), project


def _load_level(folder: Path) -> list[Node]:
    """One folder: the manifest's order first, then anything new on disk
    (appended, in name order), because the manifest is the order and files may
    be added by other hands (docs/STORAGE.md)."""
    manifest = folder / FOLDER_MANIFEST
    order: list[str] = []
    if manifest.exists():
        values, _rest = parse_frontmatter(manifest.read_text(encoding="utf-8"))
        children = values.get("children")
        if isinstance(children, list):
            order = [str(name) for name in children]

    # index.html is the container's own prose, not one of its children.
    entries = {entry.name: entry for entry in folder.iterdir()
               if not entry.name.startswith(".") and entry.name != INDEX_NAME}
    names = [name for name in order if name in entries]
    names += sorted(name for name in entries if name not in names)

    nodes: list[Node] = []
    for name in names:
        entry = entries[name]
        if entry.is_dir():
            # The folder's own manifest carries its title, id and role; the
            # directory name is only ever a slug of the title.
            own = _manifest_values(entry)
            children = _load_level(entry)
            index = entry / INDEX_NAME
            index_values, content = ({}, "")
            if index.exists():
                index_values, content = parse_frontmatter(
                    index.read_text(encoding="utf-8"))
            nodes.append(Node(
                id=str(own.get("id") or index_values.get("id") or name),
                title=str(own.get("title") or index_values.get("title")
                          or name),
                kind="folder",
                type=str(own.get("type") or index_values.get("type") or ""),
                content=content,
                synopsis=str(index_values.get("synopsis") or ""),
                word_target=int(index_values.get("word_target") or 0),
                metadata=index_values.get("metadata") if isinstance(
                    index_values.get("metadata"), dict) else {},
                children=children,
            ))
        elif entry.suffix == DOCUMENT_SUFFIX:
            values, content = parse_frontmatter(entry.read_text(encoding="utf-8"))
            nodes.append(Node(
                id=str(values.get("id") or entry.stem),
                title=str(values.get("title") or entry.stem),
                kind="document",
                type=str(values.get("type") or ""),
                content=content,
                synopsis=str(values.get("synopsis") or ""),
                word_target=int(values.get("word_target") or 0),
                metadata=values.get("metadata") if isinstance(
                    values.get("metadata"), dict) else {},
            ))
    return nodes


def _manifest_values(folder: Path) -> dict:
    """A folder's own manifest: id, title, role, and the order it kept.

    It is inside the folder so that a copied folder is a valid project, and it
    holds the *title* because the directory name is only a slug of it.
    """
    manifest = folder / FOLDER_MANIFEST
    if not manifest.exists():
        return {}
    values, _rest = parse_frontmatter(manifest.read_text(encoding="utf-8"))
    return values if isinstance(values, dict) else {}
