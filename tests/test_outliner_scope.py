"""The outliner follows the selection (docs/UI-NOTES.md 2).

A folder shows its children, a document shows its siblings, nothing selected
shows the project — the corkboard's rule, applied to the tree view.
"""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lekhak.app import MainWindow  # noqa: E402
from lekhak.project import Project  # noqa: E402

_application = QApplication.instance() or QApplication([])
_application.setOrganizationName("Lekhak")
_application.setApplicationName("Lekhak")
_settings_dir = tempfile.mkdtemp(prefix="lekhak-outliner-settings-")
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)


class OutlinerScopeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temporary.name) / "Novel",
                                      "Novel")
        self.root = self.project.documents()[0]          # the seeded "Draft"
        self.book = self.project.add_document("Book", self.root.id, "folder")
        self.chapter = self.project.add_document("One", self.book.id, "chapter")
        self.scene = self.project.add_document("Scene", self.chapter.id, "scene")
        self.stray = self.project.add_document("Stray", self.root.id, "scene")
        QSettings().remove("session/lastProject")
        self.window = MainWindow()
        self.window._switch_project(self.project)

    def tearDown(self):
        self.window.project = None
        self.project.close()
        self.temporary.cleanup()

    def _titles(self):
        self.window._refresh_outliner()
        return [self.window.outliner.topLevelItem(index).text(0)
                for index in range(self.window.outliner.topLevelItemCount())]

    def test_a_selected_folder_shows_its_children(self):
        self.window.current_id = self.book.id
        self.assertEqual(self._titles(), ["One"])

    def test_a_selected_document_shows_its_siblings(self):
        self.window.current_id = self.stray.id
        self.assertEqual(self._titles(), ["Book", "Stray"])

    def test_the_root_folder_shows_its_children(self):
        self.window.current_id = self.root.id
        self.assertEqual(self._titles(), ["Book", "Stray"])

    def test_nothing_selected_shows_the_project(self):
        self.window.current_id = None
        self.assertEqual(self._titles(), ["Draft"])

    def test_the_scope_follows_a_binder_click_without_a_tab_switch(self):
        # The gap the first pass missed: while the Outliner tab is already
        # showing, moving the binder selection used to leave the old rows
        # up — only a tab change rebuilt them.
        self.window.views.setCurrentWidget(self.window.outliner)
        self.window._select_document(self.book.id)
        self.assertEqual(
            [self.window.outliner.topLevelItem(index).text(0)
             for index in range(self.window.outliner.topLevelItemCount())],
            ["One"])


if __name__ == "__main__":
    unittest.main()
