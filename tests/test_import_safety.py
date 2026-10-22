"""Import safety: a second import must never overwrite or surprise.

The floor (docs/IMPORTS.md): imports never overwrite existing content, a
second copy of the same folder name lands numbered as a file manager would,
and identical content is reported before it is duplicated. The merge/skip
walkthrough comes later; these tests pin what ships now.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from lekhak.app import MainWindow  # noqa: E402
from lekhak.importer import import_markdown_file  # noqa: E402
from lekhak.project import Project  # noqa: E402

_application = QApplication.instance() or QApplication([])
_application.setOrganizationName("Lekhak")
_application.setApplicationName("Lekhak")
_settings_dir = tempfile.mkdtemp(prefix="lekhak-import-settings-")
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)


class UniqueTitleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temporary.name) / "Novel", "Novel")

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def test_numbering_follows_the_file_manager_convention(self):
        root = self.project.documents()[0]
        self.assertEqual(self.project.unique_title("Book", root.id), "Book")
        self.project.add_document("Book", root.id, "folder")
        self.assertEqual(self.project.unique_title("Book", root.id), "Book (2)")
        self.project.add_document("Book (2)", root.id, "folder")
        self.assertEqual(self.project.unique_title("Book", root.id), "Book (3)")

    def test_numbering_is_per_sibling_scope(self):
        root = self.project.documents()[0]
        other = self.project.add_document("Other", root.id, "folder")
        self.project.add_document("Book", root.id, "folder")
        self.assertEqual(self.project.unique_title("Book", other.id), "Book")

    def test_fingerprint_ignores_nothing_inside_a_folder(self):
        root = self.project.documents()[0]
        first = self.project.add_document("Book", root.id, "folder")
        twin = self.project.add_document("Book copy", root.id, "folder")
        for folder in (first, twin):
            chapter = self.project.add_document("Chapter", folder.id, "chapter")
            scene = self.project.add_document("Scene", chapter.id, "scene")
            self.project.write_content(scene.id, "<p>the same words</p>")
        self.assertEqual(self.project.subtree_fingerprint(first.id),
                         self.project.subtree_fingerprint(twin.id))

        scene = next(d for d in self.project.documents()
                     if d.title == "Scene" and d.parent_id != first.id)
        self.project.write_content(scene.id, "<p>different words</p>")
        self.assertNotEqual(self.project.subtree_fingerprint(first.id),
                            self.project.subtree_fingerprint(twin.id))


class ImporterNumberingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temporary.name) / "Novel", "Novel")
        self.source = Path(self.temporary.name) / "Story.md"
        self.source.write_text("Story body text.\n", encoding="utf-8")

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def test_a_second_import_of_the_same_name_is_numbered_not_stacked(self):
        first = import_markdown_file(self.project, self.source, book_title="Story")
        second = import_markdown_file(self.project, self.source, book_title="Story")

        titles = {d.id: d.title for d in self.project.documents()}
        self.assertEqual(titles[first], "Story")
        self.assertEqual(titles[second], "Story (2)")
        self.assertNotEqual(first, second)

    def test_documents_keep_their_titles(self):
        """Prose titles repeat legitimately; imports must not rename scenes."""
        folder = import_markdown_file(self.project, self.source, book_title="Story")
        chapters = [d for d in self.project.documents()
                    if d.parent_id == folder and d.kind == "scene"]
        self.assertTrue(chapters)
        self.assertIn(chapters[0].title, ("Story", "Story body text."))


class ImportConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temporary.name) / "Novel", "Novel")
        self.source = Path(self.temporary.name) / "Story.md"
        self.source.write_text("Story body text.\n", encoding="utf-8")
        self.other = Path(self.temporary.name) / "Story2.md"
        self.other.write_text("Something else entirely.\n", encoding="utf-8")
        QSettings().remove("session/lastProject")
        self.window = MainWindow()
        self.window._switch_project(self.project)
        import_markdown_file(self.project, self.source, book_title="Story")

    def tearDown(self):
        self.window.project = None
        self.project.close()
        self.temporary.cleanup()

    def _run(self, path, title="Story"):
        def run(project):
            return import_markdown_file(project, path, book_title=title)
        return run

    def test_identical_content_is_refused_by_default(self):
        with patch("lekhak.app.QMessageBox.warning",
                   return_value=QMessageBox.No) as warning:
            self.assertFalse(self.window._confirm_import(self._run(self.source)))
        self.assertIn("same content", warning.call_args[0][2])

    def test_identical_content_proceeds_when_the_writer_insists(self):
        with patch("lekhak.app.QMessageBox.warning", return_value=QMessageBox.Yes):
            self.assertTrue(self.window._confirm_import(self._run(self.source)))

    def test_different_content_under_the_same_name_is_announced_first(self):
        with patch("lekhak.app.QMessageBox.question",
                   return_value=QMessageBox.No) as question:
            self.assertFalse(self.window._confirm_import(self._run(self.other)))
        self.assertIn("different", question.call_args[0][2])

    def test_a_new_name_asks_nothing(self):
        with patch("lekhak.app.QMessageBox.question") as question, \
                patch("lekhak.app.QMessageBox.warning") as warning:
            self.assertTrue(self.window._confirm_import(
                self._run(self.other, title="Another")))
        question.assert_not_called()
        warning.assert_not_called()

    def test_the_project_is_untouched_when_the_import_is_refused(self):
        before = [(d.title, d.kind) for d in self.project.documents()]
        with patch("lekhak.app.QMessageBox.warning", return_value=QMessageBox.No):
            self.assertFalse(self.window._confirm_import(self._run(self.source)))
        self.assertEqual([(d.title, d.kind) for d in self.project.documents()],
                         before)


if __name__ == "__main__":
    unittest.main()
