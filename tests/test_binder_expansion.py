"""The binder rests collapsed (bug report, 2026-10-22).

Opening every folder on load buried the structure under its contents. Only the
path to the current document opens; a sibling stays shut until asked.
"""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lekhak.app import MainWindow  # noqa: E402
from lekhak.project import Project  # noqa: E402

_application = QApplication.instance() or QApplication([])
_application.setOrganizationName("Lekhak")
_application.setApplicationName("Lekhak")
_settings_dir = tempfile.mkdtemp(prefix="lekhak-binder-settings-")
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)


def _find_item(tree, document_id):
    def walk(item):
        if item.data(0, Qt.UserRole) == document_id:
            return item
        for index in range(item.childCount()):
            found = walk(item.child(index))
            if found is not None:
                return found
        return None

    for index in range(tree.topLevelItemCount()):
        found = walk(tree.topLevelItem(index))
        if found is not None:
            return found
    return None


class BinderExpansionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temporary.name) / "Novel",
                                      "Novel")
        self.root = self.project.documents()[0]
        self.book = self.project.add_document("Book", self.root.id, "folder")
        self.chapter = self.project.add_document("One", self.book.id, "chapter")
        self.scene = self.project.add_document("Scene", self.chapter.id, "scene")
        self.other = self.project.add_document("Other Book", self.root.id,
                                               "folder")
        self.other_scene = self.project.add_document("Loose", self.other.id,
                                                     "scene")
        QSettings().remove("session/lastProject")
        self.window = MainWindow()
        self.window._switch_project(self.project)

    def tearDown(self):
        self.window.project = None
        self.project.close()
        self.temporary.cleanup()

    def _item(self, document_id):
        return _find_item(self.window.tree, document_id)

    def test_load_leaves_folders_collapsed(self):
        self.window._reload_tree()
        self.assertFalse(self._item(self.book.id).isExpanded())
        self.assertFalse(self._item(self.other.id).isExpanded())

    def test_the_path_to_the_selection_is_open(self):
        self.window.tree.setCurrentItem(self._item(self.scene.id))
        self.assertTrue(self._item(self.book.id).isExpanded())
        self.assertTrue(self._item(self.chapter.id).isExpanded())

    def test_a_sibling_folder_stays_shut(self):
        self.window.tree.setCurrentItem(self._item(self.scene.id))
        self.assertFalse(self._item(self.other.id).isExpanded())

    def test_selecting_in_the_other_book_moves_the_opening(self):
        self.window.tree.setCurrentItem(self._item(self.scene.id))
        self.window.tree.setCurrentItem(self._item(self.other_scene.id))
        self.assertTrue(self._item(self.other.id).isExpanded())


if __name__ == "__main__":
    unittest.main()
