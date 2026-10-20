"""Named template sets for manuscript export.

A template set is a directory of slot files, yw2html-style. Each slot is an
optional file; missing slots fall back to the built-in defaults. Placeholders
use ``${Name}`` and ``${Metadata.Key}`` syntax.
"""

from __future__ import annotations

import re
import shutil
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
        """Fill one slot. Scalar values are escaped in html mode; ``content``
        and ``entries`` are raw, as the caller has already decided."""
        raw_keys = {"content", "children", "entries"}
        template = self.slot(name, html=html)

        def substitute(match: re.Match) -> str:
            key = match.group(1).strip()
            value = values.get(key, "")
            if html and key.lower() not in raw_keys:
                return escape(value)
            return value

        return PLACEHOLDER_RE.sub(substitute, template)


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
