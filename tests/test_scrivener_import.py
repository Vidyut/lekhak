"""2.3, final slice: Scrivener 3 (.scriv package) import — the RTF
converter and the binder walk, against synthetic packages.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lekhak.project import Project  # noqa: E402
from lekhak.scrivener import (  # noqa: E402
    import_scriv, parse_scriv, rtf_to_html,
)


class RtfToHtmlTests(unittest.TestCase):
    def test_paragraphs_and_plain_text(self):
        html = rtf_to_html(
            r"{\rtf1\ansi\uc1 First line\par Second line\par}")

        self.assertEqual(html, "<p>First line</p>\n<p>Second line</p>")

    def test_bold_and_italic_with_group_reset(self):
        # Each text run is wrapped on its own — adjacent same-style
        # runs are not merged — which Qt renders identically to the
        # nested form.
        html = rtf_to_html(
            r"{\rtf1\ansi plain {\b bold {\i both}} tail\par}")

        self.assertEqual(
            html,
            "<p>plain <b>bold </b><i><b>both</b></i> tail</p>")

    def test_toggle_off(self):
        html = rtf_to_html(r"{\rtf1\ansi\b bold\b0 plain\par}")

        self.assertEqual(html, "<p><b>bold</b>plain</p>")

    def test_hex_escapes_decode_as_cp1252(self):
        html = rtf_to_html(r"{\rtf1\ansi a\'93quoted\'94\par}")

        self.assertEqual(html, "<p>a“quoted”</p>")

    def test_unicode_escapes_and_fallback_skip(self):
        html = rtf_to_html(r"{\rtf1\ansi dash\u8212?next\par}")

        self.assertEqual(html, "<p>dash—next</p>")

    def test_named_characters(self):
        html = rtf_to_html(r"{\rtf1\ansi one\emdash two\par}")

        self.assertEqual(html, "<p>one—two</p>")

    def test_destination_groups_dropped_whole(self):
        html = rtf_to_html(
            r"{\rtf1\ansi{\fonttbl{\f0 Times;}}"
            r"{\colortbl;\red255\green0;}"
            r"{\*\generator Writer 2000;}"
            r"body\par}")

        self.assertEqual(html, "<p>body</p>")

    def test_line_break(self):
        html = rtf_to_html(r"{\rtf1\ansi one\line two\par}")

        self.assertEqual(html, "<p>one<br>two</p>")


def scrivx_xml() -> str:
    """Binder: DraftFolder (Manuscript) with a folder, two scenes and a
    synopsis; a ResearchFolder that must be skipped."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<ScrivenerProject Version="2.0">
  <Binder>
    <BinderItem UUID="draft-uuid" Type="DraftFolder">
      <Title>Manuscript</Title>
      <Children>
        <BinderItem UUID="folder-1" Type="Folder">
          <Title>Chapter Land</Title>
          <Children>
            <BinderItem UUID="scene-1" Type="Text">
              <Title>Cold Open</Title>
            </BinderItem>
            <BinderItem UUID="scene-2" Type="Text">
              <Title>Second</Title>
            </BinderItem>
          </Children>
        </BinderItem>
        <BinderItem UUID="scene-3" Type="Text">
          <Title>Loose Scene</Title>
        </BinderItem>
      </Children>
    </BinderItem>
    <BinderItem UUID="research-1" Type="ResearchFolder">
      <Title>Research</Title>
      <Children>
        <BinderItem UUID="research-2" Type="Text">
          <Title>Clippings</Title>
        </BinderItem>
      </Children>
    </BinderItem>
    <BinderItem UUID="trash-1" Type="TrashFolder">
      <Title>Trash</Title>
    </BinderItem>
  </Binder>
</ScrivenerProject>
'''


def write_package(root: Path, name: str = "Test.scriv") -> Path:
    package = root / name
    package.mkdir()
    (package / f"{name}.scrivx").write_text(scrivx_xml(), encoding="utf-8")
    data = package / "Files" / "Data"
    def put(uuid: str, rtf: str | None, synopsis: str | None = None) -> None:
        folder = data / uuid
        folder.mkdir(parents=True)
        if rtf is not None:
            (folder / "content.rtf").write_bytes(
                ("{\\rtf1\\ansi\\uc1 " + rtf + "}").encode("latin-1"))
        if synopsis is not None:
            (folder / "synopsis.txt").write_text(synopsis, encoding="utf-8")
    put("scene-1", r"Ice {\i everywhere}.\par And the sky.\par",
        "The ice cracks.")
    put("scene-2", r"The radio answers.\par")
    put("scene-3", None)
    put("research-2", r"Clipping text.\par")
    return package


class ParseScrivTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.package = write_package(Path(self.temporary.name))

    def tearDown(self):
        self.temporary.cleanup()

    def _find(self, item, title):
        if item.title == title:
            return item
        for child in item.children:
            found = self._find(child, title)
            if found is not None:
                return found
        return None

    def test_draft_only_research_and_trash_skipped(self):
        parsed = parse_scriv(self.package)

        self.assertEqual(parsed.title, "Manuscript")
        self.assertIsNone(self._find(parsed.draft, "Research"))
        self.assertIsNone(self._find(parsed.draft, "Clippings"))
        self.assertIsNone(self._find(parsed.draft, "Trash"))

    def test_folder_and_scene_mapping(self):
        parsed = parse_scriv(self.package)

        self.assertEqual(parsed.draft.kind, "folder")
        land = self._find(parsed.draft, "Chapter Land")
        self.assertEqual(land.kind, "folder")
        self.assertEqual(self._find(parsed.draft, "Cold Open").kind, "scene")
        self.assertEqual(self._find(parsed.draft, "Loose Scene").kind,
                         "scene")

    def test_content_and_synopsis_are_read(self):
        parsed = parse_scriv(self.package)

        cold = self._find(parsed.draft, "Cold Open")
        self.assertIn("<i>everywhere</i>", cold.content)
        self.assertIn("<p>And the sky.</p>", cold.content)
        self.assertEqual(cold.synopsis, "The ice cracks.")

    def test_missing_binder_raises(self):
        empty = Path(self.temporary.name) / "Empty.scriv"
        empty.mkdir()

        with self.assertRaises(ValueError):
            parse_scriv(empty)

    def test_a_plain_file_raises(self):
        plain = Path(self.temporary.name) / "file.scriv"
        plain.write_text("not a package", encoding="utf-8")

        with self.assertRaises(ValueError):
            parse_scriv(plain)


class ImportScrivTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.package = write_package(self.root)
        self.project = Project.create(self.root / "Novel", "Novel")

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def _by_title(self, title, kind=None):
        return next((d for d in self.project.documents()
                     if d.title == title
                     and (kind is None or d.kind == kind)), None)

    def test_structure_lands_under_the_root(self):
        root_id = import_scriv(self.project, self.package)

        root = self._by_title("Manuscript")
        self.assertEqual(root.id, root_id)
        land = self._by_title("Chapter Land")
        self.assertEqual(land.parent_id, root_id)
        cold = self._by_title("Cold Open", kind="scene")
        self.assertEqual(cold.parent_id, land.id)
        loose = self._by_title("Loose Scene", kind="scene")
        self.assertEqual(loose.parent_id, root_id)

    def test_content_and_synopsis_stored(self):
        import_scriv(self.project, self.package)

        cold = self._by_title("Cold Open", kind="scene")
        self.assertIn("everywhere", self.project.read_content(cold.id))
        entry = self.project.metadata_entries(cold.id).get("synopsis")
        self.assertEqual(entry[0], "The ice cracks.")

    def test_title_override(self):
        import_scriv(self.project, self.package, title="Renamed")

        self.assertIsNotNone(self._by_title("Renamed"))
        self.assertIsNone(self._by_title("Manuscript"))


if __name__ == "__main__":
    unittest.main()
