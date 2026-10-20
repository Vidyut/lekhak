"""2.3 Scrivener dump importer: the File-menu flows — offscreen GUI.

Dialogs are patched at the class level (getOpenFileName, getItem,
getExistingDirectory) so no modal ever runs; the window is never
close()'d, per the shared GUI-test contract.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lekhak.app import MainWindow  # noqa: E402
from lekhak.project import Project  # noqa: E402

_application = QApplication.instance() or QApplication([])
_application.setOrganizationName("Lekhak")
_application.setApplicationName("Lekhak")
_settings_dir = tempfile.mkdtemp(prefix="lekhak-import-settings-")
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)

MINI_DUMP = """\
===DOCUMENT===

Type: Chapter

ID: 1

Position: 1

ParentPosition: 0

Parent: Mini Book

Title: Start

PoV: Maya

Location: 

Date: 

Quote: 

Source: 

Status: No Status

Label: 

Keywords: 

Synopsis: 

===TEXT===

Words here that count.

===DOCUMENT===

Type: Scene

ID: 2

Position: 1

ParentPosition: 1

Parent: Start

Title: Beat

PoV: 

Location: 

Date: 

Quote: 

Source: 

Status: No Status

Label: 

Keywords: 

Synopsis: 

===TEXT===

More words.
"""


class ImportMenuTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.dump_path = Path(self.temporary.name) / "mini.md"
        self.dump_path.write_text(MINI_DUMP, encoding="utf-8")
        self.project = Project.create(Path(self.temporary.name) / "Novel", "Novel")
        self.window = MainWindow()
        self.window._switch_project(self.project)

    def tearDown(self):
        self.window.project = None
        self.project.close()
        self.temporary.cleanup()

    def _patch_dump_dialogs(self, book="Mini Book"):
        return (
            mock.patch("lekhak.app.QFileDialog.getOpenFileName",
                       return_value=(str(self.dump_path), "Scrivener dump (*.md)")),
            mock.patch("lekhak.app.QInputDialog.getItem",
                       return_value=(book, True)),
        )

    def test_import_into_open_project_adds_the_book_folder(self):
        open_dialog, pick_book = self._patch_dump_dialogs()

        with open_dialog, pick_book:
            self.window.import_scrivener_dump()

        folder = next(d for d in self.project.documents() if d.title == "Mini Book")
        self.assertEqual(folder.kind, "folder")
        self.assertEqual(self.window.current_id, folder.id)
        chapter = next(d for d in self.project.documents()
                       if d.parent_id == folder.id)
        self.assertEqual(chapter.title, "Start")
        self.assertEqual(chapter.kind, "chapter")

    def test_import_without_a_project_is_a_no_op(self):
        self.window.project = None
        open_dialog, _ = self._patch_dump_dialogs()

        with open_dialog as dialog:
            self.window.import_scrivener_dump()

        dialog.assert_not_called()

    def test_import_into_new_project_switches_to_it(self):
        open_dialog, pick_book = self._patch_dump_dialogs()
        destination = Path(self.temporary.name) / "fresh"

        with open_dialog, pick_book, mock.patch(
            "lekhak.app.QFileDialog.getExistingDirectory",
            return_value=str(destination),
        ):
            self.window.import_scrivener_dump_new_project()

        self.assertEqual(self.window.project.root, destination / "Mini Book.lekhak")
        folder = next(d for d in self.window.project.documents()
                      if d.title == "Mini Book")
        self.assertEqual(folder.kind, "folder")

    def test_cancelling_the_book_picker_imports_nothing(self):
        open_dialog, _ = self._patch_dump_dialogs()
        with open_dialog, mock.patch(
            "lekhak.app.QInputDialog.getItem", return_value=("", False)
        ):
            self.window.import_scrivener_dump()

        self.assertEqual(
            [d.title for d in self.project.documents() if d.title == "Mini Book"], []
        )


if __name__ == "__main__":
    unittest.main()
