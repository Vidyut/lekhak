"""2.3, next slice: plain markdown import with the writer's own divider
strings — splitter, placement, and the import dialog, offscreen.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from lekhak.app import ImportMarkdownDialog  # noqa: E402
from lekhak.importer import (  # noqa: E402
    import_markdown_file, split_markdown,
)
from lekhak.project import Project  # noqa: E402

_application = QApplication.instance() or QApplication([])
_application.setOrganizationName("Lekhak")
_application.setApplicationName("Lekhak")
_settings_dir = tempfile.mkdtemp(prefix="lekhak-md-settings-")
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)


class SplitMarkdownTests(unittest.TestCase):
    def test_defaults_split_chapters_and_scenes(self):
        chunks = split_markdown(
            "# The War\nWar prose.\n\n## First Light\nScene prose.")

        self.assertEqual(
            [(c.kind, c.title) for c in chunks],
            [("chapter", "The War"), ("scene", "First Light")])
        self.assertIn("War prose.", chunks[0].body)
        self.assertIn("Scene prose.", chunks[1].body)

    def test_prose_before_the_first_divider_becomes_the_opening_scene(self):
        chunks = split_markdown(
            "A cold open.\n\n# Chapter One\nBody.", opening_title="Book")

        self.assertEqual(chunks[0].kind, "scene")
        self.assertEqual(chunks[0].title, "Book")
        self.assertIn("A cold open.", chunks[0].body)
        self.assertEqual(chunks[1].title, "Chapter One")

    def test_empty_chapter_divider_leaves_only_scenes(self):
        chunks = split_markdown("## One\na\n\n## Two\nb",
                                chapter_divider="")

        self.assertEqual([c.kind for c in chunks], ["scene", "scene"])

    def test_both_dividers_empty_makes_one_opening_scene(self):
        chunks = split_markdown("Whole file prose.", chapter_divider="",
                                scene_divider="", opening_title="Solo")

        self.assertEqual(len(chunks), 1)
        self.assertEqual((chunks[0].kind, chunks[0].title),
                         ("scene", "Solo"))
        self.assertIn("Whole file prose.", chunks[0].body)

    def test_divider_must_be_followed_by_space_or_eol(self):
        # '##nope' is prose, and with the '#' / '##' defaults a level-3
        # heading is prose too — the writer's strings are exact.
        chunks = split_markdown("##nope\n\n### Deep\n\n# Real\nbody",
                                opening_title="Open")

        self.assertEqual([(c.kind, c.title) for c in chunks],
                         [("scene", "Open"), ("chapter", "Real")])
        self.assertIn("##nope", chunks[0].body)
        self.assertIn("### Deep", chunks[0].body)

    def test_scene_divider_wins_when_both_would_match(self):
        chunks = split_markdown("# Real Scene\nbody",
                                chapter_divider="#",
                                scene_divider="#")

        # Same string for both: the scene pass is tested first, so every
        # divider line becomes a scene, not a chapter.
        self.assertEqual(chunks[0].kind, "scene")
        self.assertEqual(chunks[0].title, "Real Scene")

    def test_untitled_divider_falls_back(self):
        chunks = split_markdown("#\nbody")

        self.assertEqual(chunks[0].title, "Untitled")

    def test_custom_divider_strings(self):
        chunks = split_markdown(
            "CHAPTER: One\nprose\nSCENE: Bit\nmore",
            chapter_divider="CHAPTER:", scene_divider="SCENE:")

        self.assertEqual([(c.kind, c.title) for c in chunks],
                         [("chapter", "One"), ("scene", "Bit")])


class ImportMarkdownFileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(
            Path(self.temporary.name) / "Novel", "Novel"
        )
        # Project.create already added a "Draft" folder; imports add
        # beside it, which the assertions tolerate.
        self.file = Path(self.temporary.name) / "solo.md"

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def _by_title(self, title, kind=None):
        return next(d for d in self.project.documents()
                    if d.title == title and (kind is None or d.kind == kind))

    def test_file_becomes_a_folder_with_chapters_and_scenes(self):
        self.file.write_text(
            "# The War\nWar prose.\n\n## First Light\nScene prose.",
            encoding="utf-8")

        folder_id = import_markdown_file(self.project, self.file)

        folder = self._by_title("solo")
        self.assertEqual(folder.id, folder_id)
        self.assertEqual(folder.kind, "folder")
        chapter = self._by_title("The War")
        scene = self._by_title("First Light")
        self.assertEqual(chapter.kind, "chapter")
        self.assertEqual(chapter.parent_id, folder_id)
        self.assertEqual(scene.kind, "scene")
        self.assertEqual(scene.parent_id, chapter.id)
        self.assertIn("<p>Scene prose.</p>",
                      self.project.read_content(scene.id))

    def test_scene_before_any_chapter_lands_under_the_book(self):
        self.file.write_text("## Cold open\nprose\n\n# Part\nbody",
                             encoding="utf-8")

        folder_id = import_markdown_file(self.project, self.file)

        scene = self._by_title("Cold open")
        self.assertEqual(scene.parent_id, folder_id)
        self.assertEqual(self._by_title("Part").parent_id, folder_id)

    def test_book_title_overrides_the_stem(self):
        self.file.write_text("# One\nbody", encoding="utf-8")

        folder_id = import_markdown_file(self.project, self.file,
                                         book_title="Renamed")

        self.assertEqual(self._by_title("Renamed").id, folder_id)

    def test_leading_prose_is_titled_after_the_book(self):
        self.file.write_text("A cold open.\n\n# One\nbody", encoding="utf-8")

        folder_id = import_markdown_file(self.project, self.file,
                                         book_title="Solo")

        opening = self._by_title("Solo", kind="scene")
        self.assertEqual(opening.kind, "scene")
        self.assertEqual(opening.parent_id, folder_id)
        self.assertIn("A cold open.",
                      self.project.read_content(opening.id))


class ImportMarkdownDialogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.file = Path(self.temporary.name) / "draft.md"
        self.file.write_text("# One\nbody", encoding="utf-8")
        self.dialog = ImportMarkdownDialog()

    def tearDown(self):
        self.dialog = None
        self.temporary.cleanup()

    def test_accept_without_a_file_refuses(self):
        with patch.object(QMessageBox, "warning") as warning:
            self.dialog.accept()

        warning.assert_called_once()
        self.assertNotEqual(self.dialog.result(), 1)  # not Accepted

    def test_path_defaults_the_title_to_the_stem(self):
        self.dialog.path_edit.setText(str(self.file))

        self.assertEqual(self.dialog.title_edit.text(), "draft")
        self.assertEqual(self.dialog.chosen_path(), self.file)

    def test_a_typed_title_survives_a_path_change(self):
        self.dialog.title_edit.setText("Renamed")
        self.dialog.path_edit.setText(str(self.file))
        self.dialog.path_edit.setText(str(self.file.with_name("other.md")))

        self.assertEqual(self.dialog.title_edit.text(), "Renamed")

    def test_missing_file_is_no_choice(self):
        self.dialog.path_edit.setText(
            str(Path(self.temporary.name) / "gone.md"))

        self.assertIsNone(self.dialog.chosen_path())


if __name__ == "__main__":
    unittest.main()
