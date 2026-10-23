"""Preferences, category by category (docs/PREFERENCES.md; UI-NOTES 4).

The dialog is a category list beside stacked pages; the tests walk that
list, check every page is real, and drive the settings each category
actually persists — including the two the old wall of prose silently
ignored (autosave delay, reopen-on-start) and the AI prompt behind the
accordion.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from lekhak import ai  # noqa: E402
from lekhak.app import MainWindow, PreferencesDialog, load_paste_prefs  # noqa: E402
from lekhak.project import Project  # noqa: E402

_application = QApplication.instance() or QApplication([])
_application.setOrganizationName("Lekhak")
_application.setApplicationName("Lekhak")
_settings_dir = tempfile.mkdtemp(prefix="lekhak-prefs-settings-")
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)

_PASTE_OFF = {"fonts": False, "paragraphs": False,
              "inline": False, "alignment": False}

_EXPECTED_CATEGORIES = [
    "Appearance", "Editor", "Files & saving", "Pasting",
    "Links & export", "AI", "Read aloud", "Advanced",
]


class CategoryListTests(unittest.TestCase):
    def setUp(self):
        self.dialog = PreferencesDialog(11, dict(_PASTE_OFF))

    def tearDown(self):
        self.dialog.deleteLater()

    def test_every_category_shows_a_real_page(self):
        names = [self.dialog.categories.item(i).text()
                 for i in range(self.dialog.categories.count())]
        self.assertEqual(names, _EXPECTED_CATEGORIES)
        for row in range(self.dialog.categories.count()):
            item = self.dialog.categories.item(row)
            page = self.dialog.pages.widget(item.data(Qt.UserRole))
            self.assertIsNotNone(page, item.text())
            self.assertIsNotNone(page.layout(), item.text())

    def test_clicking_a_category_switches_the_page(self):
        for row in range(self.dialog.categories.count()):
            item = self.dialog.categories.item(row)
            self.dialog.categories.setCurrentItem(item)
            self.assertEqual(self.dialog.pages.currentIndex(),
                             item.data(Qt.UserRole), item.text())

    def test_the_filter_narrows_the_category_list(self):
        self.dialog.search_box.setText("AI")
        visible = [self.dialog.categories.item(i).text()
                   for i in range(self.dialog.categories.count())
                   if not self.dialog.categories.item(i).isHidden()]
        self.assertEqual(visible, ["AI"])
        self.dialog.search_box.setText("")
        self.assertFalse(any(
            self.dialog.categories.item(i).isHidden()
            for i in range(self.dialog.categories.count())))

    def test_the_font_slider_carries_a_live_sample(self):
        self.assertEqual(self.dialog.size_slider.minimum(), 8)
        self.assertEqual(self.dialog.size_slider.maximum(), 24)
        self.dialog.size_slider.setValue(18)
        self.assertEqual(self.dialog.size_label.text(), "18 pt")
        self.assertEqual(self.dialog.size_sample.font().pointSize(), 18)


class PreferencesApplyTests(unittest.TestCase):
    def setUp(self):
        QSettings().remove("session/lastProject")
        for key in ("editor/autosaveMs", "session/reopenLast",
                    "link_policy/default", "ai/prompt", "ui/fontSize",
                    "ui/spellSquiggles"):
            QSettings().remove(key)
        self.window = MainWindow()

    def tearDown(self):
        self.window.project = None
        self.window.deleteLater()
        # The link default is global; leave it as found for later suites.
        QSettings().remove("link_policy/default")

    def test_the_categories_persist_where_they_claim_to(self):
        QSettings().setValue("editor/autosaveMs", 1500)
        QSettings().setValue("session/reopenLast", True)
        QSettings().setValue("link_policy/default", "plain-text")
        QSettings().setValue("ai/prompt", "Old prompt.")
        created = []
        original_init = PreferencesDialog.__init__

        def spy(dialog, *args, **kwargs):
            created.append(dialog)
            original_init(dialog, *args, **kwargs)

        def accept_after_edits():
            # The dialog starts from what is stored; the writer then
            # edits the widgets. The apply path must persist what it
            # finds at accept, not what construction began with — which
            # is also what makes a dropped write observable here.
            dialog = created[0]
            dialog.autosave_spin.setValue(2400)
            dialog.reopen_last_box.setChecked(False)
            dialog.link_default_box.setCurrentIndex(
                dialog.link_default_box.findData("keep-as-note"))
            dialog.ai_prompt_edit.setPlainText("New contract.")
            return QDialog.Accepted

        with patch.object(PreferencesDialog, "__init__", spy), \
                patch.object(PreferencesDialog, "exec",
                             side_effect=accept_after_edits):
            self.window.preferences()

        self.assertEqual(int(QSettings().value("editor/autosaveMs")), 2400)
        self.assertFalse(
            bool(QSettings().value("session/reopenLast", True)))
        self.assertEqual(QSettings().value("link_policy/default"),
                         "keep-as-note")
        self.assertEqual(QSettings().value("ai/prompt"), "New contract.")
        # The autosave delay is live, not next-open: the running timer
        # picks the new interval up in the same call.
        self.assertEqual(self.window.save_timer.interval(), 2400)

    def test_the_shipped_proofreading_prompt_is_a_fallback(self):
        QSettings().remove("ai/prompt")
        self.assertEqual(ai.proofread_system(), ai.PROOFREAD_SYSTEM)
        QSettings().setValue("ai/prompt", "  Custom contract.  ")
        self.assertEqual(ai.proofread_system(), "Custom contract.")

    def test_the_dialog_edits_the_prompt_and_keeps_the_warning(self):
        dialog = PreferencesDialog(11, dict(_PASTE_OFF))
        try:
            self.assertTrue(dialog.ai_prompt_edit.isHidden())
            self.assertTrue(dialog.prompt_warning.isHidden())
            dialog.prompt_toggle.setChecked(True)
            self.assertFalse(dialog.ai_prompt_edit.isHidden())
            self.assertFalse(dialog.prompt_warning.isHidden())
            self.assertIn("Do not edit unless you know what you are doing",
                          dialog.prompt_warning.text())
        finally:
            dialog.deleteLater()


class ReopenGateTests(unittest.TestCase):
    def setUp(self):
        QSettings().remove("session/lastProject")
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(
            Path(self.temporary.name) / "Novel", "Novel")
        QSettings().setValue("session/lastProject", str(self.project.root))
        self.window = MainWindow()

    def tearDown(self):
        self.window.project = None
        self.window.deleteLater()
        QSettings().remove("session/lastProject")
        QSettings().remove("session/reopenLast")
        self.project.close()
        self.temporary.cleanup()

    def test_reopening_honours_the_switch(self):
        QSettings().setValue("session/reopenLast", False)
        self.window.reopen_last_project()
        self.assertIsNone(self.window.project)

        QSettings().setValue("session/reopenLast", True)
        self.window.reopen_last_project()
        self.assertIsNotNone(self.window.project)
        self.assertTrue(Path(self.window.project.root).name.startswith("Novel"))


if __name__ == "__main__":
    unittest.main()
