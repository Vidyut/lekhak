"""1.6 page starts: the inspector's Page start combo — offscreen.

Same test contract as the other GUI suites: QSettings redirected into a
temp dir, windows never closed().
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
_settings_dir = tempfile.mkdtemp(prefix="lekhak-pagebreak-settings-")
# QSettings objects created from now on read/write under _settings_dir.
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)


class PageStartTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temporary.name) / "Novel", "Novel")
        self.folder = self.project.documents()[0]          # Draft, kind "folder"
        self.scene = self.project.add_document(
            "Scene", parent_id=self.folder.id, kind="scene"
        )
        self.window = MainWindow()
        self.window._switch_project(self.project)

    def tearDown(self):
        self.window.project = None
        self.project.close()
        self.temporary.cleanup()

    def test_combo_lists_every_value_in_roadmap_order(self):
        values = [self.window.page_break_box.itemData(index)
                  for index in range(self.window.page_break_box.count())]
        self.assertEqual(values, ["auto", "flow", "page", "left", "right",
                                  "next-odd", "next-even"])

    def test_selection_loads_the_document_value(self):
        self.project.update_document(self.scene.id, page_break="right")
        self.window._select_document(self.scene.id)

        self.assertEqual(self.window.page_break_box.currentData(), "right")

    def test_changing_the_combo_saves_with_the_document(self):
        self.window._select_document(self.scene.id)
        index = self.window.page_break_box.findData("left")

        self.window.page_break_box.setCurrentIndex(index)
        self.window.save_current()

        found = next(d for d in self.project.documents() if d.id == self.scene.id)
        self.assertEqual(found.page_break, "left")

    def test_combo_disabled_without_a_project(self):
        window = MainWindow()

        self.assertFalse(window.page_break_box.isEnabled())
        window.project = None


if __name__ == "__main__":
    unittest.main()
