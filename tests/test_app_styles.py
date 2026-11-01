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
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lekhak.app import (  # noqa: E402
    NEW_STYLE_COMMAND, SEED_STYLES, UPDATE_STYLE_COMMAND, MainWindow,
    capture_paragraph_signature,
)
from lekhak.project import Project  # noqa: E402

# The style box's own capture commands trail the styles (2.4h).
STYLE_COMMAND_TEXTS = ("+ New style from paragraph…",
                       "Update style from paragraph…")

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

    def _box_names(self) -> list[str]:
        names = [self.window.style_box.itemText(index)
                 for index in range(self.window.style_box.count())]
        return [name for name in names if name]      # the separator's blank

    def test_style_box_lists_the_six_seeds_and_their_commands(self):
        # The styles, a separator, then the box's own capture commands
        # (2.4h) — making a style without hunting the menu.
        self.assertEqual(self._box_names(),
                         list(SEED_STYLES) + list(STYLE_COMMAND_TEXTS))

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
        self.assertIn("Epigraph", self._box_names())
        # A saved style keeps its own row, and the commands stay last.
        self.assertEqual(self._box_names()[-2:], list(STYLE_COMMAND_TEXTS))

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
        self.assertEqual(self._box_names(),
                         list(SEED_STYLES) + list(STYLE_COMMAND_TEXTS))

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

    # --- the box's own commands (2.4h) ------------------------------------

    def test_the_new_style_command_captures_and_persists(self):
        self.window.editor.setPlainText("shout")
        self._apply("Title")
        box = self.window.style_box

        with patch("lekhak.app.QInputDialog.getText",
                   return_value=("Shout", True)):
            box.activated.emit(box.findData(NEW_STYLE_COMMAND))

        self.assertIn("Shout", self._box_names())
        self.assertIn(
            "Shout", json.loads(self.project.get_setting("paragraph_styles")))
        # The box never sits on its own command: it returns to the style
        # the caret wears.
        self.assertEqual(box.currentData(), "Title")

    def test_a_cancelled_new_style_leaves_the_box_where_it_was(self):
        self.window.editor.setPlainText("shout")
        self._apply("Title")
        box = self.window.style_box

        with patch("lekhak.app.QInputDialog.getText",
                   return_value=("", False)):
            box.activated.emit(box.findData(NEW_STYLE_COMMAND))

        # Nothing was created, nothing was stored, and the box never
        # sat on its own command (2.4h).
        self.assertEqual(self.project.get_setting("paragraph_styles"), "")
        self.assertEqual(self.window._styles, SEED_STYLES)
        self.assertEqual(box.currentData(), "Title")

    def test_the_update_command_recaptures_the_shown_style(self):
        self._style_whole_editor(30.0, int(QFont.Bold))
        self.assertTrue(self.window.save_style_from_cursor("Shout"))
        # The paragraph changes after the style was captured.
        self._style_whole_editor(20.0, int(QFont.Normal))
        box = self.window.style_box
        # Picking the style is the box's memory of it, so the command
        # below re-captures the right one (2.4h).
        box.setCurrentIndex(box.findData("Shout"))

        box.activated.emit(box.findData(UPDATE_STYLE_COMMAND))

        self.assertEqual(self.window._styles["Shout"]["size"], 20.0)
        self.assertEqual(self.window._styles["Shout"]["weight"],
                         int(QFont.Normal))
        self.assertEqual(box.currentData(), "Shout")

    # --- the bar's alignment buttons (2.4h) -------------------------------

    def _alignment_action(self, label: str):
        return next(action for action
                    in self.window._alignment_actions.values()
                    if action.text() == label)

    def test_the_alignment_buttons_set_the_paragraph(self):
        self.window.editor.setPlainText("centre me")

        self._alignment_action("Centre").trigger()
        self.assertEqual(int(self.window.editor.alignment()),
                         int(Qt.AlignmentFlag.AlignCenter))

        self._alignment_action("Right").trigger()
        self.assertEqual(int(self.window.editor.alignment()),
                         int(Qt.AlignmentFlag.AlignRight))

    def test_the_alignment_buttons_show_the_paragraphs_own(self):
        self.window.editor.setPlainText("centre me")
        centre = self._alignment_action("Centre")
        left = self._alignment_action("Left")
        centre.trigger()

        # The clicked button checks; the others stand down — and the bar
        # answers a click even where a block-format change moves no caret.
        self.assertTrue(centre.isChecked())
        self.assertFalse(left.isChecked())
        self.assertTrue(self._alignment_action("Justify").isEnabled())

    def test_the_bar_says_which_paragraph_the_caret_is_in(self):
        self.window.editor.setHtml(
            '<p>plain</p><p style="text-align:center">centred</p>')
        centre = self._alignment_action("Centre")

        cursor = self.window.editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.window.editor.setTextCursor(cursor)

        self.assertTrue(centre.isChecked())


if __name__ == "__main__":
    unittest.main()
