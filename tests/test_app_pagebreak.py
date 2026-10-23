"""The Page start row is gone from the inspector — UI-NOTES 9.

The template owns page starts per kind (docs/TEMPLATES.md §2) and the
export's auto baseline — chapters open recto once a print trim is set —
needs no control of its own. What this file guards: the row does not
come back as a second place to say it, and a value stored by an older
project still loads and saves without the inspector reading or
clobbering it.

Same test contract as the other GUI suites: QSettings redirected into a
temp dir, windows never closed().
"""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from lekhak.app import MainWindow  # noqa: E402
from lekhak.project import Project  # noqa: E402

_application = QApplication.instance() or QApplication([])
_application.setOrganizationName("Lekhak")
_application.setApplicationName("Lekhak")
_settings_dir = tempfile.mkdtemp(prefix="lekhak-pagebreak-settings-")
# QSettings objects created from now on read/write under _settings_dir.
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)


class PageStartGoneTests(unittest.TestCase):
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

    def test_the_inspector_has_no_page_start_row(self):
        self.assertFalse(hasattr(self.window, "page_break_box"))
        labels = [label.text() for label in self.window.findChildren(QLabel)]
        self.assertNotIn("Page start", labels)

    def test_a_stored_page_break_survives_selection_and_save(self):
        """Export still honours old values; the inspector must neither
        read them nor write them away."""
        self.project.update_document(self.scene.id, page_break="right")
        self.window._select_document(self.scene.id)
        self.window.save_current()

        found = next(d for d in self.project.documents() if d.id == self.scene.id)
        self.assertEqual(found.page_break, "right")


if __name__ == "__main__":
    unittest.main()
