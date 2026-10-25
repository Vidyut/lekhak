"""Named template sets for manuscript export.

A template set is a directory of slot files, yw2html-style. Each slot is an
optional file; missing slots fall back to the built-in defaults. Placeholders
use ``${Name}`` and ``${Metadata.Key}`` syntax.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from html import escape
from pathlib import Path

# Slots, in the order a compile consults them. All are optional in a set.
SLOTS = (
    "project_header",
    "project_footer",
    "toc_page",
    "chapter",
    "chapter_end",
    "scene",
    "first_scene",
    "scene_end",
    "scene_divider",
)

PLACEHOLDER_RE = re.compile(r"\$\{([^{}]+)\}")

# 2.2 conditional blocks: $if(Key), $if(Key = Value), $if(Key != Value),
# $else, $endif — evaluated against the same values that fill ${...}.
# The $if(...) piece stops at the first ")", so a condition value
# containing ")" cannot be matched; conditionals live only in template
# slots, never in document prose.
CONDITIONAL_PIECE_RE = re.compile(
    r"(\$if\([^)]*\)|\$else(?![A-Za-z])|\$endif(?![A-Za-z]))")
CONDITIONAL_EXPR_RE = re.compile(r"^(.+?)\s*(!=|=)\s*(.*)$")

BUILTIN_HTML: dict[str, str] = {
    "project_header": "",
    "project_footer": "",
    "toc_page": '<nav class="toc"><h1>Contents</h1><ol>${Entries}</ol></nav>',
    "chapter": '<section class="chapter">\n<h1>${Title}</h1>\n${Content}\n</section>',
    "chapter_end": "",
    "scene": '<section class="scene">\n<h2>${Title}</h2>\n${Content}\n</section>',
    "first_scene": "",
    "scene_end": "",
    "scene_divider": '<hr class="scene-divider">',
}

BUILTIN_TEXT: dict[str, str] = {
    "project_header": "",
    "project_footer": "",
    "toc_page": "",
    "chapter": "${Title}\n\n${Content}",
    "chapter_end": "",
    "scene": "${Title}\n\n${Content}",
    "first_scene": "",
    "scene_end": "",
    "scene_divider": "\n* * *\n",
}

EXTENSIONS = {True: ".html", False: ".txt"}

# Document-level templates every set has (2.1): "bare" is the sidebar's
# "nothing, not even title" choice. Sets add their own as files under
# documents/<name>.html|.txt — a news-item preamble, and so on.
BUILTIN_DOCUMENT_TEMPLATES: dict[str, dict[bool, str]] = {
    "bare": {True: "${Content}", False: "${Content}"},
}

DOCUMENT_TEMPLATE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _-]*")

# Every value key the compile actually supplies (2.4 slot editor): mirrors
# Project._template_values plus the compile extras and the TOC's Entries.
# Metadata.<key> is open-ended and validated by prefix only. fill() is
# case-sensitive, so validation is too — ${title} renders empty and should
# be flagged, not silently accepted.
TEMPLATE_KEYS = (
    "Title", "Kind", "Synopsis", "WordCount", "Content",
    "ChapterNumber", "SceneNumber", "WordsTotal", "Entries", "Children",
)

# What the slot editor's completer offers, as the exact strings an
# activated item inserts (closing brace included; Metadata. stays open
# for the writer's own key).
TEMPLATE_COMPLETIONS = tuple(f"${{{key}}}" for key in TEMPLATE_KEYS) + (
    "${Metadata.", "$if(", "$else", "$endif",
)


def validate_slot(text: str, *, html: bool = True) -> list[str]:
    """Tier-1 checks for a hand-edited slot (2.4): unknown ${...} keys,
    unbalanced $if/$endif, an orphan $else, stray conditional markers.

    Advisory only — TemplateSet.fill already degrades a bad slot to
    something printable, so saving an issue stays allowed; this is the
    editor's tripwire, not a gate. The ``html`` argument is accepted for
    signature symmetry with the dialog's tier-2 Qt round-trip sniff,
    which lives in the GUI layer so this module stays Qt-free.
    """
    issues: list[str] = []
    for key in PLACEHOLDER_RE.findall(text):
        name = key.strip()
        if name.startswith("Metadata."):
            continue
        if name not in TEMPLATE_KEYS:
            issues.append(f"unknown placeholder ${{{name}}}")
    depth = 0
    for piece in CONDITIONAL_PIECE_RE.split(text):
        if piece.startswith("$if("):
            depth += 1
        elif piece == "$endif":
            depth -= 1
            if depth < 0:
                issues.append("$endif without a matching $if")
                depth = 0
        elif piece == "$else" and depth == 0:
            issues.append("$else without a matching $if")
    if depth > 0:
        issues.append(f"{depth} unclosed $if")
    leftover = CONDITIONAL_PIECE_RE.sub("", text)
    stray = sorted({marker for marker in ("$if", "$else", "$endif")
                    if marker in leftover})
    if stray:
        issues.append(
            "stray or malformed marker(s): " + ", ".join(stray)
            + " (missing parentheses?)")
    return issues


@dataclass(frozen=True)
class TemplateSet:
    """A resolved set of slot templates: user files over built-in defaults."""

    name: str
    directory: Path | None
    html_slots: dict[str, str]
    text_slots: dict[str, str]

    @classmethod
    def builtin(cls) -> "TemplateSet":
        return cls("default", None, dict(BUILTIN_HTML), dict(BUILTIN_TEXT))

    @classmethod
    def load(cls, name: str, directory: Path) -> "TemplateSet":
        """Load a set from a directory; missing slots keep built-in defaults."""
        html_slots, text_slots = dict(BUILTIN_HTML), dict(BUILTIN_TEXT)
        for slot in SLOTS:
            for mode, slots in ((True, html_slots), (False, text_slots)):
                path = Path(directory) / (slot + EXTENSIONS[mode])
                if path.is_file():
                    slots[slot] = path.read_text(encoding="utf-8")
        return cls(name, Path(directory), html_slots, text_slots)

    @property
    def editable(self) -> bool:
        return self.directory is not None

    def slot(self, name: str, *, html: bool = True) -> str:
        slots = self.html_slots if html else self.text_slots
        return slots.get(name, "")

    def render(self, name: str, values: dict[str, str], *, html: bool = True) -> str:
        """Fill one named slot of this set."""
        return self.fill(self.slot(name, html=html), values, html=html)

    @staticmethod
    def fill(template: str, values: dict[str, str], *,
             html: bool = True) -> str:
        """Fill an arbitrary template string. Scalar values are escaped in
        html mode; ``content``, ``children`` and ``entries`` are raw, as
        the caller has already decided. $if/$else/$endif blocks (2.2) are
        evaluated first and the dead branches removed."""
        template = TemplateSet.conditionals(template, values)
        raw_keys = {"content", "children", "entries"}

        def substitute(match: re.Match) -> str:
            key = match.group(1).strip()
            value = values.get(key, "")
            if html and key.lower() not in raw_keys:
                return escape(value)
            return value

        return PLACEHOLDER_RE.sub(substitute, template)

    @staticmethod
    def conditionals(template: str, values: dict[str, str]) -> str:
        """Evaluate $if/$else/$endif blocks (2.2); the result is the
        template with dead branches and every marker consumed.

        A condition is either a bare key — true when its value is
        non-empty — or `Key = Value` / `Key != Value`, compared
        case-insensitively against the raw (unescaped) value. Nesting
        works. An unmatched $if keeps its branch state to the end of the
        template; a stray $else/$endif is dropped. A hand-edited slot
        therefore degrades to something printable, never to leaked
        markers.
        """
        active = [True]
        else_taken: list[bool] = []
        result: list[str] = []
        for piece in CONDITIONAL_PIECE_RE.split(template):
            if piece.startswith("$if("):
                condition = TemplateSet._condition_holds(piece[4:-1], values)
                active.append(condition)
                else_taken.append(condition)
            elif piece == "$else":
                if else_taken:
                    active[-1] = not else_taken[-1]
                    else_taken[-1] = True
            elif piece == "$endif":
                if else_taken:
                    else_taken.pop()
                    active.pop()
            elif all(active):
                result.append(piece)
        return "".join(result)

    @staticmethod
    def _condition_holds(expr: str, values: dict[str, str]) -> bool:
        match = CONDITIONAL_EXPR_RE.match(expr.strip())
        if not match:
            return bool(values.get(expr.strip(), "").strip())
        key = match.group(1).strip()
        expected = match.group(3).strip()
        actual = values.get(key, "").strip()
        equal = actual.casefold() == expected.casefold()
        return equal if match.group(2) == "=" else not equal

    def document_slot(self, name: str, *, html: bool = True) -> str | None:
        """A document-level template (2.1): the file
        ``documents/<name>.html|.txt`` of this set, or the built-in
        ``bare``; None when this set has no such template, so the caller
        falls back to the ordinary chapter/scene slot."""
        if not name or not DOCUMENT_TEMPLATE_NAME_RE.fullmatch(name):
            return None
        if self.directory:
            path = self.directory / "documents" / (name + EXTENSIONS[html])
            if path.is_file():
                return path.read_text(encoding="utf-8")
        builtin = BUILTIN_DOCUMENT_TEMPLATES.get(name)
        return builtin[html] if builtin else None

    def document_template_names(self) -> list[str]:
        """Names the sidebar can offer: built-ins plus every template file
        in this set's documents/ directory."""
        names = set(BUILTIN_DOCUMENT_TEMPLATES)
        if self.directory:
            directory = self.directory / "documents"
            if directory.is_dir():
                for path in directory.iterdir():
                    if path.is_file() and path.suffix in tuple(EXTENSIONS.values()):
                        names.add(path.stem)
        return sorted(names)


def user_template_root() -> Path:
    from os import environ

    base = environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(base) / "lekhak" / "templates"


def project_template_root(project_root: Path) -> Path:
    return Path(project_root) / "templates"


def discover_template_sets(project_root: Path) -> list[TemplateSet]:
    """Built-in default plus every set directory under the user and project
    template roots. Project sets shadow user sets of the same name."""
    sets = [TemplateSet.builtin()]
    seen = {"default"}
    for root in (user_template_root(), project_template_root(project_root)):
        if not root.is_dir():
            continue
        for candidate in sorted(root.iterdir()):
            if candidate.is_dir() and candidate.name not in seen:
                sets.append(TemplateSet.load(candidate.name, candidate))
                seen.add(candidate.name)
    return sets


def create_template_set(name: str, project_root: Path) -> TemplateSet:
    """Copy the built-in defaults into a new editable set in the project."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]*", name):
        raise ValueError(f"Invalid template set name: {name!r}")
    directory = project_template_root(project_root) / name
    if directory.exists():
        raise FileExistsError(f"Template set already exists: {directory}")
    directory.mkdir(parents=True)
    for slot in SLOTS:
        (directory / (slot + ".html")).write_text(BUILTIN_HTML[slot], encoding="utf-8")
        (directory / (slot + ".txt")).write_text(BUILTIN_TEXT[slot], encoding="utf-8")
    return TemplateSet.load(name, directory)


def copy_template_set(source: TemplateSet, name: str, project_root: Path) -> TemplateSet:
    """Fork an existing set into a new editable one."""
    created = create_template_set(name, project_root)
    if source.directory:
        for path in source.directory.iterdir():
            if path.is_file():
                shutil.copy2(path, created.directory / path.name)
        return TemplateSet.load(name, created.directory)
    return created


SET_README = """This folder is one template set: the instructions for turning your project
into an exported book.

Each file here is a "slot" — chapter.html says what a chapter looks like,
scene.html what a scene looks like, title_page.html what the title page looks
like. Edit them to change your export; delete a file to fall back to the
built-in default for that slot.

Placeholders you can use inside a slot — ${Title}, ${Content}, ${Author},
${Date}, ${Metadata.AnyKey} — are filled in when you export.

You may add your own files here. A file whose name matches a slot name
(chapter, scene, title_page, toc_page, project_header, project_footer,
chapter_end, first_scene, scene_end, scene_divider) is that slot; anything
else is a document variant you can pick per document.

The .txt files are the same slots for plain-text export. Edit either; they do
not have to agree.

Nothing here is precious: make a copy (Templates area → Duplicate) before
changing anything you might want back.
"""


def materialise_builtin_set(project_root: Path, name: str = "Default") -> TemplateSet:
    """Write the built-in defaults out as an editable set inside the project.

    The defaults live in this module as strings, which suits the machine and is
    invisible to the writer. Materialising them is what puts a template in
    front of somebody: real files, in their project, beside their book — the
    "always contains at least one template" the author asked for. Called from
    Project.ensure_templates_area() and by the Templates area's copy action.
    """
    directory = project_template_root(project_root) / name
    if directory.is_dir():
        return TemplateSet.load(name, directory)
    created = create_template_set(name, project_root)
    documents = created.directory / "documents"
    documents.mkdir(parents=True, exist_ok=True)
    (documents / "bare.html").write_text(
        BUILTIN_DOCUMENT_TEMPLATES["bare"][True], encoding="utf-8")
    (created.directory / "README.txt").write_text(SET_README, encoding="utf-8")
    return created


def slot_file_path(directory: Path, name: str, *, document: bool,
                   html: bool) -> Path:
    """Where one slot of a set lives on disk (2.4): ``<set>/<slot>.html``
    or ``<set>/documents/<name>.html`` for document-level templates."""
    base = Path(directory) / "documents" if document else Path(directory)
    return base / (name + EXTENSIONS[html])


def write_slot(directory: Path, name: str, *, document: bool, html: bool,
               text: str) -> Path:
    """Atomic slot write (2.4): temp file + os.replace, the same contract
    document content uses — a crash mid-save never leaves a half-written
    template."""
    path = slot_file_path(directory, name, document=document, html=html)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return path
