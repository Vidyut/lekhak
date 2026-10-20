"""2.4 follow-on: the template-slot editor.

Pure half — validate_slot, slot paths, atomic write, the Qt round-trip
sniff — plus the offscreen dialog: completer, validation labels, save
and revert, the built-in set staying view-only.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog  # noqa: E402

from lekhak.app import (  # noqa: E402
    TemplateSlotEditorDialog, _roundtrip_issues,
)
from lekhak.project import Project  # noqa: E402
from lekhak.templates import (  # noqa: E402
    BUILTIN_HTML, SLOTS, TEMPLATE_COMPLETIONS, create_template_set,
    slot_file_path, validate_slot, write_slot,
)

_application = QApplication.instance() or QApplication([])
_application.setOrganizationName("Lekhak")
_application.setApplicationName("Lekhak")
_settings_dir = tempfile.mkdtemp(prefix="lekhak-slot-settings-")
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)


class ValidateSlotTests(unittest.TestCase):
    def test_known_placeholders_are_clean(self):
        text = ("${Title}\n${Content}\n${ChapterNumber} ${SceneNumber} "
                "${WordsTotal} ${WordCount} ${Kind} ${Synopsis} "
                "${Entries} ${Children}")
        self.assertEqual(validate_slot(text), [])

    def test_unknown_placeholder_is_flagged(self):
        self.assertIn("unknown placeholder ${Bogus}",
                      validate_slot("Hello ${Bogus}"))

    def test_metadata_prefix_is_allowed(self):
        self.assertEqual(
            validate_slot("${Metadata.Author} ${Metadata.World}"), [])

    def test_keys_are_case_sensitive(self):
        # fill() looks values up exactly, so ${title} renders empty and
        # the editor must say so.
        self.assertIn("unknown placeholder ${title}",
                      validate_slot("${title}"))

    def test_conditionals_balance(self):
        self.assertEqual(
            validate_slot("$if(Key)yes$else$endif"), [])

        def has(needle, text):
            return any(needle in issue for issue in validate_slot(text))

        self.assertTrue(has("unclosed $if", "$if(Key)yes"))
        self.assertTrue(has("$endif without a matching $if", "yes$endif"))
        self.assertTrue(has("$else without a matching $if", "yes$else"))
        self.assertTrue(has("unclosed $if", "$if(A)$if(B)nested"))

    def test_stray_marker_without_parentheses_is_flagged(self):
        issues = validate_slot("$if Key)oops")
        self.assertTrue(any("stray or malformed" in issue
                            for issue in issues))

    def test_builtin_slots_validate_clean(self):
        for slot, text in BUILTIN_HTML.items():
            self.assertEqual(validate_slot(text), [], slot)


class SlotPathAndWriteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_slot_file_path_shapes(self):
        self.assertEqual(
            slot_file_path(self.directory, "chapter", document=False,
                           html=True),
            self.directory / "chapter.html")
        self.assertEqual(
            slot_file_path(self.directory, "bare", document=True,
                           html=False),
            self.directory / "documents" / "bare.txt")

    def test_write_slot_is_atomic_and_creates_documents_dir(self):
        path = write_slot(self.directory, "bare", document=True, html=True,
                          text="${Content}<!--custom-->")

        self.assertEqual(path, self.directory / "documents" / "bare.html")
        self.assertEqual(path.read_text(encoding="utf-8"),
                         "${Content}<!--custom-->")
        # No leftover temp files from the atomic write.
        self.assertEqual(
            [p.name for p in path.parent.iterdir() if p.name.startswith(".")],
            [])


class RoundtripSniffTests(unittest.TestCase):
    def test_wellformed_html_keeps_placeholders(self):
        self.assertEqual(
            _roundtrip_issues('<h1>${Title}</h1>\n${Content}'), [])

    def test_unterminated_comment_swallows_a_placeholder(self):
        issues = _roundtrip_issues("<p>before</p><!-- ${Title}")
        self.assertTrue(any("${Title}" in issue for issue in issues))


class TemplateSlotEditorDialogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(
            Path(self.temporary.name) / "Novel", "Novel"
        )
        self.created = create_template_set("Fancy", self.project.root)
        self.dialog = TemplateSlotEditorDialog(self.project)

    def tearDown(self):
        # Never close() a dialog that could touch settings; drop the
        # reference and the project, same contract as the app suites.
        self.dialog = None
        self.project.close()
        self.temporary.cleanup()

    def _select_label(self, label):
        index = self.dialog.slot_box.findText(label)
        self.assertNotEqual(index, -1, label)
        self.dialog.slot_box.setCurrentIndex(index)

    def _fancy_dir(self):
        return self.project.root / "templates" / "Fancy"

    def test_lists_slots_and_document_templates(self):
        labels = [self.dialog.slot_box.itemText(i)
                  for i in range(self.dialog.slot_box.count())]
        for slot in SLOTS:
            self.assertIn(slot + ".html", labels)
            self.assertIn(slot + ".txt", labels)
        self.assertIn("documents/bare.html", labels)

    def test_builtin_set_is_view_only(self):
        self.dialog.set_box.setCurrentIndex(0)  # "default"

        self.assertFalse(self.dialog.save_button.isEnabled())
        self.assertIn("fork", self.dialog.validation.text().casefold())

    def test_edit_and_save_writes_the_slot_file(self):
        self.dialog.set_box.setCurrentIndex(
            self.dialog.set_box.findText("Fancy"))
        self._select_label("chapter.html")
        self.dialog.editor.setPlainText("<section>${Title} — fancy</section>")

        self.dialog._save()

        written = self._fancy_dir() / "chapter.html"
        self.assertEqual(written.read_text(encoding="utf-8"),
                         "<section>${Title} — fancy</section>")
        self.assertTrue(self.dialog.validation.text().startswith("Saved."))

    def test_saving_a_document_template_creates_the_override(self):
        self.dialog.set_box.setCurrentIndex(
            self.dialog.set_box.findText("Fancy"))
        self._select_label("documents/bare.html")
        self.dialog.editor.setPlainText("${Content}<!--bare-->")

        self.dialog._save()

        written = self._fancy_dir() / "documents" / "bare.html"
        self.assertEqual(written.read_text(encoding="utf-8"),
                         "${Content}<!--bare-->")

    def test_revert_reloads_from_disk(self):
        self.dialog.set_box.setCurrentIndex(
            self.dialog.set_box.findText("Fancy"))
        self._select_label("scene.html")
        write_slot(self._fancy_dir(), "scene", document=False, html=True,
                   text="stored version")

        self.dialog.editor.setPlainText("unsaved scribble")
        self.dialog._slot_changed()

        self.assertEqual(self.dialog.editor.toPlainText(), "stored version")

    def test_validation_label_reports_issues(self):
        self.dialog.set_box.setCurrentIndex(
            self.dialog.set_box.findText("Fancy"))
        self._select_label("scene.html")

        self.dialog.editor.setPlainText("${Bogus} $else")

        text = self.dialog.validation.text()
        self.assertIn("unknown placeholder ${Bogus}", text)
        self.assertIn("$else without a matching $if", text)

    def test_completer_completes_a_placeholder_token(self):
        self.dialog.editor.setPlainText("${Tit")
        self.dialog.editor.moveCursor(QTextCursor.End)
        self.dialog._update_completer()

        self.assertEqual(self.dialog.completer.completionPrefix(), "${Tit")
        self.assertGreaterEqual(self.dialog.completer.completionCount(), 1)
        self.assertIn("${Title}", TEMPLATE_COMPLETIONS)

        self.dialog._insert_completion("${Title}")
        self.assertEqual(self.dialog.editor.toPlainText(), "${Title}")

    def test_new_set_forks_the_current_one(self):
        with patch.object(QInputDialog, "getText",
                          return_value=("Fancy2", True)):
            self.dialog._new_set()

        self.assertEqual(self.dialog.set_box.currentText(), "Fancy2")
        self.assertTrue((self.project.root / "templates" / "Fancy2"
                         / "chapter.html").is_file())
        self.assertTrue(self.dialog.save_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
