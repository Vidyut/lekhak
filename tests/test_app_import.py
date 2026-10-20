"""2.3 Scrivener dump importer: the File-menu flows — offscreen GUI.

The menu imports the whole dump and splits it into books itself; only
the file picker (and the new-project title/location dialogs) are
patched, so no modal ever runs. The window is never close()'d, per the
shared GUI-test contract.
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

===DOCUMENT===

Type: Chapter

ID: 3

Position: 1

ParentPosition: 0

Parent: Second Book

Title: Other Start

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

Third document.
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

    def _patch_file_dialog(self):
        return mock.patch(
            "lekhak.app.QFileDialog.getOpenFileName",
            return_value=(str(self.dump_path), "Scrivener dump (*.md)"),
        )

    def test_import_splits_every_book_into_its_own_folder(self):
        with self._patch_file_dialog():
            self.window.import_scrivener_dump()

        folders = {d.title: d for d in self.project.documents() if d.kind == "folder"}
        self.assertIn("Mini Book", folders)
        self.assertIn("Second Book", folders)
        # First book's chapter lands under the first book, not the second
        chapters = [d for d in self.project.documents()
                    if d.parent_id == folders["Mini Book"].id]
        self.assertEqual([d.title for d in chapters], ["Start"])
        self.assertEqual(self.window.current_id, folders["Mini Book"].id)

    def test_import_without_a_project_is_a_no_op(self):
        self.window.project = None
        with self._patch_file_dialog() as dialog:
            self.window.import_scrivener_dump()

        dialog.assert_not_called()

    def test_import_into_new_project_uses_the_dump_name_by_default(self):
        with self._patch_file_dialog(), mock.patch(
            "lekhak.app.QFileDialog.getExistingDirectory",
            return_value=str(Path(self.temporary.name) / "fresh"),
        ), mock.patch(
            "lekhak.app.QInputDialog.getText", return_value=("mini", True)
        ):
            self.window.import_scrivener_dump_new_project()

        self.assertEqual(self.window.project.root,
                         Path(self.temporary.name) / "fresh" / "mini.lekhak")
        titles = {d.title for d in self.window.project.documents()
                  if d.kind == "folder" and d.title != "Draft"}
        self.assertEqual(titles, {"Mini Book", "Second Book"})

    def test_cancelling_the_file_picker_imports_nothing(self):
        with mock.patch("lekhak.app.QFileDialog.getOpenFileName",
                        return_value=("", "")):
            self.window.import_scrivener_dump()

        self.assertEqual(
            [d for d in self.project.documents()
             if d.kind == "folder" and d.title != "Draft"],
            []
        )


if __name__ == "__main__":
    unittest.main()
