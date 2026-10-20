"""Import a Scrivener multi-document markdown dump into a project. (2.3)

Flow of a dump import:

    read file ─ split on ===DOCUMENT=== ─ blank-line header fields ─ RawDocument list
                                                              │
                              book folders = parent titles that are not documents
                                                              │
                    import_book: folder → stack walk → add_document / write_content /
                    set_metadata / update_document(synopsis)

The dump format is flat: every block carries Title, Type, Parent (a
title, not an id), Position and a body after ===TEXT===. The blocks are
in depth-first binder order, which is what makes parent-by-title safe
even though titles repeat across books: walking the list with a stack of
open ancestors resolves each Parent to the nearest still-open ancestor
with that title — verified against the author's full corpus with zero
orphans before this code was written.

Only two kinds appear in the author's dumps (chapter, scene); anything
else lands as a scene, and folders are never in the dump at all — book
folders and intermediate containers are rebuilt here, not imported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .project import Project

# Every key the author's Scrivener compile emits. Continuation chunks in
# a multi-line field (a Synopsis written as story beats, for instance)
# are recognised by NOT being one of these keys, so the whitelist is
# load-bearing rather than documentation.
HEADER_KEYS = (
    "Type", "ID", "Hierarchy", "Position", "ParentPosition", "Parent",
    "Level1", "Level2", "Title", "PoV", "Location", "Date", "Quote",
    "Source", "Status", "Label", "Keywords", "Synopsis",
)

# Headers that describe the dump itself, not the document: used to build
# the tree, then dropped. Hierarchy is Scrivener's compile placeholder
# (always the same junk token in the author's dumps) and is dropped too.
STRUCTURAL_KEYS = {
    "Type", "ID", "Hierarchy", "Position", "ParentPosition", "Parent",
    "Level1", "Level2", "Title", "Synopsis",
}

# Scrivener writes these sentinels when a field was never filled in.
# Storing them would bury the real values under 300 "No Status" rows.
UNSET_VALUES = {"No Status", "No Label", "None", ""}

_FIELD_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9]*):[ \t]?(.*)$")


@dataclass
class RawDocument:
    """One ===DOCUMENT=== block, parsed but not yet placed."""

    title: str
    kind: str                       # "chapter", "scene" — the dump's Type
    parent: str                     # parent's Title as declared ("" = top)
    position: int                   # sibling order inside the parent
    synopsis: str
    body: str                       # markdown-ish prose after ===TEXT===
    metadata: dict[str, str] = field(default_factory=dict)


def parse_dump(path: Path) -> list[RawDocument]:
    """Parse a multi-document markdown dump into RawDocuments, in dump order.

    Dump order is depth-first binder order and is the contract every
    later step relies on — reordering the result would break parent
    resolution.
    """
    text = Path(path).read_text(encoding="utf-8")
    documents: list[RawDocument] = []
    for block in text.split("===DOCUMENT===")[1:]:
        if "===TEXT===" not in block:
            continue
        header_part, body = block.split("===TEXT===", 1)
        fields = _parse_header(header_part)
        documents.append(RawDocument(
            title=fields.get("Title", "").strip() or "Untitled",
            kind=fields.get("Type", "Scene").strip().lower(),
            parent=fields.get("Parent", "").strip(),
            position=_as_int(fields.get("Position", "0")),
            synopsis=fields.get("Synopsis", "").strip(),
            body=body.strip("\n"),
            metadata=_kept_metadata(fields),
        ))
    return documents


def _parse_header(header_part: str) -> dict[str, str]:
    """Blank-line-separated Key: value chunks → fields.

    A chunk whose first line is not a known key continues the previous
    field (multi-line Synopsis values arrive as bare continuation
    chunks), so an unknown chunk never invents a field.
    """
    fields: dict[str, str] = {}
    current: str | None = None
    for chunk in re.split(r"\n\s*\n", header_part):
        lines = [line for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue
        match = _FIELD_LINE.match(lines[0].strip())
        if match and match.group(1) in HEADER_KEYS:
            current = match.group(1)
            fields[current] = match.group(2).strip()
            continuation = [line.strip() for line in lines[1:]]
        else:
            continuation = [line.strip() for line in lines]
        if current is not None and continuation:
            joined = fields[current] + "\n" + "\n".join(continuation)
            fields[current] = joined
    return fields


def _kept_metadata(fields: dict[str, str]) -> dict[str, str]:
    """The document-metadata keys worth storing: everything non-structural
    that the writer actually filled in."""
    kept: dict[str, str] = {}
    for key, value in fields.items():
        if key in STRUCTURAL_KEYS:
            continue
        cleaned = value.strip()
        if cleaned in UNSET_VALUES:
            continue
        kept[key] = cleaned
    return kept


def _as_int(text: str) -> int:
    try:
        return int(text.strip())
    except (TypeError, ValueError):
        return 0


def dump_books(raw_documents: list[RawDocument]) -> list[str]:
    """The book folders a dump contains, in binder order.

    A book is a parent title that is not itself a document — the dump
    never includes folder blocks, so the books only exist as the parents
    their chapters hang off.
    """
    titles = {document.title for document in raw_documents}
    books: list[str] = []
    for document in raw_documents:
        if document.parent and document.parent not in titles:
            if document.parent not in books:
                books.append(document.parent)
    return books


def markdown_to_html(text: str) -> str:
    """Minimal markdown → the rich-text HTML Lekhak stores.

    Deliberately tiny: paragraphs split on blank lines, ``*em*`` and
    ``**strong**``, leading ``#`` heading lines (the dump's title-page
    blocks use them) rendered bold. Everything is escaped first and
    anything fancier stays visible as text — this is an import of prose,
    not a pandoc replacement; the writer polishes in the editor.
    """
    paragraphs: list[str] = []
    for chunk in re.split(r"\n\s*\n", text.strip()):
        lines = [line.rstrip() for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue
        joined = "\n".join(lines)
        heading = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", joined)
        if heading:
            paragraphs.append(f"<p><b>{_inline(heading.group(1))}</b></p>")
            continue
        escaped = _inline(joined).replace("\n", "<br>")
        paragraphs.append(f"<p>{escaped}</p>")
    return "\n".join(paragraphs)


def _inline(text: str) -> str:
    """Escape HTML, then turn the two markdown inline markers into tags."""
    escaped = (text.replace("&", "&amp;").replace("<", "&lt;")
               .replace(">", "&gt;"))
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<i>\1</i>", escaped)
    return escaped


def import_book(project: Project, raw_documents: list[RawDocument],
                book_title: str, parent_id: str | None = None) -> str:
    """Create one book from a parsed dump; returns the book folder's id.

    Walks the raw list in dump order with an ancestor stack, so scenes
    land under their own book's chapter even when another book has a
    chapter with the same title. Documents whose parent chain never
    reaches ``book_title`` belong to another book and are skipped.
    """
    folder = project.add_document(book_title, parent_id, "folder")
    stack: list[tuple[str, str]] = []          # (title, document_id)
    for raw in raw_documents:
        while stack and stack[-1][0] != raw.parent:
            stack.pop()
        if raw.parent == book_title:
            child_parent = folder.id
        elif stack:
            child_parent = stack[-1][1]
        else:
            stack = []      # not in this book; a later block may re-enter
            continue
        kind = raw.kind if raw.kind in ("chapter", "scene") else "scene"
        document = project.add_document(raw.title, child_parent, kind)
        if raw.synopsis:
            project.update_document(document.id, synopsis=raw.synopsis)
        if raw.metadata:
            project.set_metadata(document.id, raw.metadata)
        project.write_content(document.id, markdown_to_html(raw.body))
        stack.append((raw.title, document.id))
    return folder.id
