"""1.11 paragraph styles: seeds, capture, persistence — offscreen GUI.

QSettings is redirected into a temp dir (same contract as the resume and
paste tests) so the suite never touches the user's real Lekhak
configuration. Windows are never closed() — closeEvent would save into a
possibly-closed project and hang an offscreen run.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lekhak.app import (  # noqa: E402
    SEED_STYLES, MainWindow, capture_paragraph_signature,
)
from lekhak.project import Project  # noqa: E402

_application = QApplication.instance() or QApplication([])
_application.setOrganizationName("Lekhak")
_application.setApplicationName("Lekhak")
_settings_dir = tempfile.mkdtemp(prefix="lekhak-style-settings-")
# QSettings objects created from now on read/write under _settings_dir.
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)


class StyleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temporary.name) / "Novel", "Novel")
        self.window = MainWindow()
        self.window._switch_project(self.project)

    def tearDown(self):
        # Never close() the window: closeEvent -> save_current on a closed
        # project raises into a modal QMessageBox and hangs offscreen.
        self.window.project = None
        self.project.close()
        self.temporary.cleanup()

    def _apply(self, name: str) -> None:
        index = self.window.style_box.findData(name)
        self.assertGreaterEqual(index, 0, f"{name} missing from style box")
        self.window.apply_paragraph_style(index)

    def _style_whole_editor(self, size: float, weight: int) -> None:
        self.window.editor.setPlainText("loud words")
        cursor = self.window.editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        char_format = QTextCharFormat()
        char_format.setFontPointSize(size)
        char_format.setFontWeight(weight)
        cursor.mergeCharFormat(char_format)
        self.window.editor.setTextCursor(cursor)

    def test_style_box_lists_the_six_seeds(self):
        names = [self.window.style_box.itemText(index)
                 for index in range(self.window.style_box.count())]
        self.assertEqual(names, list(SEED_STYLES))

    def test_apply_seed_quote_formats_the_paragraph(self):
        self.window.editor.setPlainText("wise words")

        self._apply("Quote")

        captured = capture_paragraph_signature(self.window.editor.textCursor())
        self.assertTrue(captured["italic"])
        self.assertEqual(captured["left_margin"], 32.0)
        self.assertEqual(captured["right_margin"], 32.0)

    def test_apply_paragraph_after_quote_resets_the_margins(self):
        # The seeds carry complete margins precisely so style switching
        # cannot leak the previous style's spacing (the old parallel-array
        # version left Quote's 32 pt behind).
        self.window.editor.setPlainText("wise words")
        self._apply("Quote")

        self._apply("Paragraph")

        captured = capture_paragraph_signature(self.window.editor.textCursor())
        self.assertEqual(captured["left_margin"], 0.0)
        self.assertEqual(captured["right_margin"], 0.0)

    def test_create_style_persists_across_reload(self):
        self.window.editor.setPlainText("wise words")
        self._apply("Quote")

        self.assertTrue(self.window.save_style_from_cursor("Epigraph"))

        stored = json.loads(self.project.get_setting("paragraph_styles"))
        self.assertIn("Epigraph", stored)
        # A fresh load (as after reopening the project) brings it back.
        self.window._user_styles = {}
        self.window._load_styles()
        self.assertIn("Epigraph", self.window._styles)
        self.assertEqual(self.window.style_box.count(), len(SEED_STYLES) + 1)

    def test_create_refuses_taken_names_and_needs_a_project(self):
        self.window.editor.setPlainText("x")

        self.assertFalse(self.window.save_style_from_cursor("Quote"))
        self.assertTrue(self.window.save_style_from_cursor("Mine"))
        self.assertFalse(self.window.save_style_from_cursor("Mine"))
        self.assertFalse(self.window.save_style_from_cursor("   "))

        bare = MainWindow()
        self.assertFalse(bare.save_style_from_cursor("Theirs"))
        bare.project = None

    def test_update_overrides_a_seed_and_delete_brings_it_back(self):
        self._style_whole_editor(30.0, int(QFont.Bold))

        self.assertTrue(self.window.update_style_from_cursor("Quote"))

        self.assertEqual(self.window._styles["Quote"]["size"], 30.0)
        self.assertEqual(self.window._styles["Quote"]["weight"], int(QFont.Bold))

        self.assertTrue(self.window.remove_style("Quote"))

        self.assertNotIn("Quote", self.window._user_styles)
        self.assertEqual(self.window._styles["Quote"], SEED_STYLES["Quote"])

    def test_style_at_cursor_identifies_the_applied_style(self):
        self.window.editor.setPlainText("wise words")
        self._apply("Quote")
        self.assertEqual(self.window.style_at_cursor(), "Quote")

        self._apply("Paragraph")
        self.assertEqual(self.window.style_at_cursor(), "Paragraph")

    def test_captured_style_applies_its_alignment(self):
        self.window.editor.setHtml('<p style="text-align:center">c</p>')
        self.assertTrue(self.window.save_style_from_cursor("Centred"))

        self.window.editor.setPlainText("plain words")
        self._apply("Centred")

        captured = capture_paragraph_signature(self.window.editor.textCursor())
        self.assertEqual(captured["alignment"],
                         int(Qt.AlignmentFlag.AlignCenter))

    def test_junk_style_setting_falls_back_to_the_seeds(self):
        self.project.set_setting("paragraph_styles", "{not json")

        self.window._load_styles()

        self.assertEqual(self.window._styles, SEED_STYLES)
        self.assertEqual(self.window.style_box.count(), len(SEED_STYLES))

    def test_editor_menu_carries_the_style_commands(self):
        menu = self.window._build_editor_menu()
        texts = [action.text() for action in menu.actions()]

        self.assertIn("Create Style from Paragraph…", texts)
        self.assertIn("Update Style from Paragraph…", texts)
        self.assertIn("Delete Style…", texts)
        # Nothing saved yet: delete is present but inert.
        delete = next(action for action in menu.actions()
                      if action.text() == "Delete Style…")
        self.assertFalse(delete.isEnabled())
        menu.deleteLater()

    def test_editor_uses_a_custom_context_menu_policy(self):
        self.assertEqual(self.window.editor.contextMenuPolicy(),
                         Qt.ContextMenuPolicy.CustomContextMenu)


if __name__ == "__main__":
    unittest.main()
