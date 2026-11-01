"""Corkboard cards read as cards, and cannot vanish (docs/UI-NOTES.md 3).

The colours are derived and inverted, so the guarantee is measurable: the card
must be far in lightness from the chrome around it, and its text far from the
card, whatever palette the desktop hands us.
"""

import os
import re
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lekhak.app import MainWindow  # noqa: E402

_application = QApplication.instance() or QApplication([])
_application.setOrganizationName("Lekhak")
_application.setApplicationName("Lekhak")
_settings_dir = tempfile.mkdtemp(prefix="lekhak-corkboard-settings-")
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)


class CorkboardCardTests(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()
        self.sheet = self.window.corkboard.styleSheet()

    def tearDown(self):
        self.window.project = None

    def _colour(self, pattern):
        match = re.search(pattern, self.sheet)
        self.assertIsNotNone(match, "no colour matching %r in:\n%s" % (pattern, self.sheet))
        return QColor(match.group(1))

    def _chrome(self):
        return self._colour(r"QListWidget \{\s*background:\s*(#[0-9a-fA-F]{6})")

    def _card(self):
        return self._colour(r"QListWidget::item \{\s*background:\s*(#[0-9a-fA-F]{6})")

    def _ink(self):
        return self._colour(
            r"QListWidget::item \{\s*background:\s*#[0-9a-fA-F]{6};\s*"
            r"color:\s*(#[0-9a-fA-F]{6})")

    def test_cards_are_framed(self):
        self.assertIn("QListWidget::item", self.sheet)
        self.assertIn("border-radius", self.sheet)
        self.assertIn("padding", self.sheet)
        self.assertGreaterEqual(self.window.corkboard.spacing(), 4)

    def test_a_card_contrasts_with_its_surroundings(self):
        difference = abs(self._card().lightness() - self._chrome().lightness())
        self.assertGreater(difference, 100,
                           "a card that close in lightness to the chrome can vanish")

    def test_card_text_contrasts_with_the_card(self):
        difference = abs(self._ink().lightness() - self._card().lightness())
        self.assertGreater(difference, 100)

    def test_selection_is_visible(self):
        self.assertIn("QListWidget::item:selected", self.sheet)


if __name__ == "__main__":
    unittest.main()
