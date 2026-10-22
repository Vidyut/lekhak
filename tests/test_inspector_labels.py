"""The inspector says what its controls are (docs/UI-NOTES.md §5)."""

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from lekhak.app import MainWindow  # noqa: E402

_application = QApplication.instance() or QApplication([])
_application.setOrganizationName("Lekhak")
_application.setApplicationName("Lekhak")
_settings_dir = tempfile.mkdtemp(prefix="lekhak-label-settings-")
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)


class InspectorLabelTests(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.project = None

    def test_the_control_says_word_count_goal(self):
        labels = [label.text() for label in self.window.findChildren(QLabel)]
        self.assertIn("Word count goal", labels)
        self.assertNotIn("Section target", labels)

    def test_the_zero_state_reads_no_goal(self):
        self.assertEqual(self.window.target.specialValueText(), "No goal")

    def test_it_explains_itself_on_hover(self):
        self.assertTrue(self.window.target.toolTip())
