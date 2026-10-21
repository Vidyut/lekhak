"""Import a yWriter 7 project (.yw7) into a project. (2.3)

Flow of a yw7 import:

    read XML (utf-8, fallback utf-16) ─ PROJECT title
                                        │
        SCENES by ID (Unused/Notes/ToDo scenes skipped)  CHAPTERS in file order
                                        │  normal chapters only (Type 0, no Unused)
                                        │
        folder from the project title → chapter → scene, SceneContent
        (yWriter's inline HTML) stored as the scene's content.

A .yw7 is a single XML file — root tag YWRITER7 — with scene prose held
inline in <SceneContent> (yWriter 6+; only yWriter 5 kept side-car RTF
files). Chapter order comes from the CHAPTERS list and scene order from
each chapter's <Scenes>/<ScID> references, not from document order.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .project import Project

# yWriter (and Windows editors) may leave control characters the XML
# header does not sanction; ElementTree refuses them.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]")


@dataclass
class YwScene:
    """One scene of a parsed yWriter project."""

    id: str
    title: str
    content: str
    synopsis: str


@dataclass
class YwChapter:
    """One normal chapter with its scenes in yWriter's own order."""

    id: str
    title: str
    scenes: list[YwScene]


@dataclass
class YwProject:
    """The normal chapters of a yWriter project, ready to import."""

    title: str
    chapters: list[YwChapter]


def _text(element: ET.Element | None, tag: str) -> str:
    child = element.find(tag) if element is not None else None
    return (child.text or "").strip() if child is not None and child.text else ""


def parse_yw7(path: Path) -> YwProject:
    """Parse a .yw7 file into chapters and scenes.

    Notes, ToDo and unused chapters/scenes all carry an <Unused> marker
    (or a non-zero chapter Type) and are skipped, matching what yWriter
    itself leaves out of a compile. A normal chapter with no scenes
    still comes through — an empty chapter is structure, not noise.
    """
    path = Path(path)
    text: str | None = None
    for encoding in ("utf-8", "utf-16"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError(f"Cannot decode {path} as utf-8 or utf-16")
    root = ET.fromstring(_CONTROL_RE.sub("", text))

    scenes: dict[str, YwScene] = {}
    for element in root.iter("SCENE"):
        scene_id = _text(element, "ID")
        if not scene_id or element.find("Unused") is not None:
            continue
        scenes[scene_id] = YwScene(
            scene_id,
            _text(element, "Title") or "Untitled",
            (element.findtext("SceneContent") or ""),
            _text(element, "Desc"),
        )

    chapters: list[YwChapter] = []
    for element in root.iter("CHAPTER"):
        if element.find("Unused") is not None:
            continue
        # Type 0 is normal; 1 covers Notes and ToDo, told apart by
        # ChapterType (1 and 2), which we do not need to distinguish.
        if (_text(element, "Type") or "0") != "0":
            continue
        chapter_scenes: list[YwScene] = []
        references = element.find("Scenes")
        if references is not None:
            for reference in references.findall("ScID"):
                scene = scenes.get((reference.text or "").strip())
                if scene is not None:
                    chapter_scenes.append(scene)
        chapters.append(YwChapter(
            _text(element, "ID") or str(len(chapters)),
            _text(element, "Title") or "Untitled",
            chapter_scenes,
        ))

    title = _text(root.find("PROJECT"), "Title")
    return YwProject(title, chapters)


def import_yw7(project: Project, path: Path, *, title: str = "") -> str:
    """Import one yWriter project as a book; returns the folder id.

    The folder takes the yWriter project's own title (or the caller's),
    every normal chapter and scene lands under it, scene prose is stored
    as yWriter wrote it — its HTML is already the rich-text dialect Qt
    reads — and each Desc becomes the document's synopsis.
    """
    parsed = parse_yw7(path)
    folder_title = title.strip() or parsed.title or Path(path).stem
    folder = project.add_document(folder_title, None, "folder")
    for chapter in parsed.chapters:
        document = project.add_document(chapter.title, folder.id, "chapter")
        for scene in chapter.scenes:
            scene_document = project.add_document(
                scene.title, document.id, "scene")
            project.write_content(scene_document.id, scene.content)
            if scene.synopsis:
                project.set_metadata(scene_document.id,
                                     {"synopsis": scene.synopsis})
    return folder.id
