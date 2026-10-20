"""2.1 in the window: book settings in the inspector, the lifted
TEMPLATES area, multi-selection export scope — offscreen GUI.

Same contract as the other app suites: QSettings redirected into a temp
dir, windows never closed() (closeEvent would save into a possibly-
closed project and hang offscreen).
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from lekhak.app import (  # noqa: E402
    ExportOptionsDialog, MainWindow,
)
from lekhak.project import Project  # noqa: E402
from lekhak.templates import discover_template_sets  # noqa: E402

_application = QApplication.instance() or QApplication([])
_application.setOrganizationName("Lekhak")
_application.setApplicationName("Lekhak")
_settings_dir = tempfile.mkdtemp(prefix="lekhak-book-settings-settings-")
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)


def _within(item, document_id):
    if item.data(0, Qt.UserRole) == document_id:
        return item
    for index in range(item.childCount()):
        found = _within(item.child(index), document_id)
        if found:
            return found
    return None


def _find_item(widget, document_id):
    """Search a whole tree widget, or one item's subtree when handed an
    item — the binder keeps its current item selected, so tests clear
    both trees before building an export scope from scratch."""
    if hasattr(widget, "topLevelItemCount"):
        roots = [widget.topLevelItem(i)
                 for i in range(widget.topLevelItemCount())]
    else:
        roots = [widget]
    for root in roots:
        found = _within(root, document_id)
        if found:
            return found
    return None


def _clear_selection(*widgets):
    for widget in widgets:
        for item in widget.selectedItems():
            item.setSelected(False)


class BookSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(
            Path(self.temporary.name) / "Novel", "Novel"
        )
        draft = self.project.documents()[0]
        self.templates_root = self.project.add_document(
            "TEMPLATES", draft.id, "folder"
        )
        self.project.set_templates_root(self.templates_root.id, True)
        self.default_template = self.project.add_document(
            "default", self.templates_root.id, "folder"
        )
        generic_front = self.project.add_document(
            "Generic front", self.default_template.id, "chapter"
        )
        self.project.write_content(generic_front.id,
                                   "<p>Generic front text.</p>")

        self.book = self.project.add_document(
            "Marginally Human", draft.id, "folder"
        )
        self.chapter = self.project.add_document(
            "Chapter One", self.book.id, "chapter"
        )
        self.scene = self.project.add_document(
            "First Light", self.chapter.id, "scene"
        )
        self.project.write_content(self.chapter.id, "<p>Chapter opener.</p>")
        self.project.write_content(self.scene.id,
                                   "<p>First light prose.</p>")

        self.window = MainWindow()
        self.window._switch_project(self.project)

    def tearDown(self):
        # Never close() the window: closeEvent -> save_current on a closed
        # project raises into a modal QMessageBox and hangs offscreen.
        self.window.project = None
        self.project.close()
        self.temporary.cleanup()

    # --- inspector sections -------------------------------------------------

    def test_folder_shows_book_settings_and_hides_doc_slot(self):
        self.window._select_document(self.book.id)

        self.assertFalse(self.window.templates_root_box.isHidden())
        self.assertFalse(self.window.book_template_box.isHidden())
        self.assertFalse(self.window.book_cover_edit.isHidden())
        self.assertTrue(self.window.doc_template_box.isHidden())
        self.assertTrue(self.window.doc_template_label.isHidden())

    def test_prose_selection_shows_doc_template_slot(self):
        self.window._select_document(self.scene.id)

        self.assertFalse(self.window.doc_template_box.isHidden())
        self.assertTrue(self.window.templates_root_box.isHidden())
        self.assertTrue(self.window.book_template_box.isHidden())
        self.assertTrue(self.window.cover_label.isHidden())
        values = [
            self.window.doc_template_box.itemData(index)
            for index in range(self.window.doc_template_box.count())
        ]
        self.assertIn("", values)          # Default (the set's own slot)
        self.assertIn("bare", values)      # builtin: no chrome at all

    def test_picking_a_document_slot_persists(self):
        self.window._select_document(self.scene.id)
        box = self.window.doc_template_box

        box.setCurrentIndex(box.findData("bare"))

        document = next(
            d for d in self.project.documents() if d.id == self.scene.id
        )
        self.assertEqual(document.doc_template, "bare")

    def test_picking_a_book_template_persists(self):
        self.window._select_document(self.book.id)
        box = self.window.book_template_box
        # The folder combo offers every template folder (2.1).
        self.assertGreaterEqual(box.count(), 2)

        box.setCurrentIndex(box.findData(self.default_template.id))

        self.assertEqual(
            self.project.book_settings(self.book.id),
            {"template": self.default_template.id},
        )

    def test_cover_round_trips_and_clearing_removes_the_entry(self):
        self.window._select_document(self.book.id)
        self.window.book_cover_edit.setText("/tmp/fake-cover.png")
        self.window._book_settings_changed()
        self.assertEqual(
            self.project.book_settings(self.book.id),
            {"cover": "/tmp/fake-cover.png"},
        )

        # Repopulate through a selection round-trip: the line shows it.
        self.window._select_document(self.scene.id)
        self.window._select_document(self.book.id)
        self.assertEqual(self.window.book_cover_edit.text(),
                         "/tmp/fake-cover.png")

        self.window.book_cover_edit.setText("")
        self.window._book_settings_changed()
        self.assertEqual(self.project.book_settings(self.book.id), {})

    # --- the lifted TEMPLATES area ------------------------------------------

    def test_templates_flag_lifts_folder_below_the_manuscript(self):
        nested = self.project.add_document("Extras", self.book.id, "folder")
        self.window._reload_tree()

        self.window._select_document(nested.id)
        self.window.templates_root_box.setChecked(True)

        document = next(
            d for d in self.project.documents() if d.id == nested.id
        )
        self.assertTrue(document.is_templates_root)
        top_ids = [
            self.window.tree.topLevelItem(i).data(0, Qt.UserRole)
            for i in range(self.window.tree.topLevelItemCount())
        ]
        self.assertIn(nested.id, top_ids)
        self.assertGreater(top_ids.index(nested.id), 0)   # below the regulars
        book_item = _find_item(self.window.tree, self.book.id)
        self.assertIsNone(_find_item(book_item, nested.id))
        outliner_top = [
            self.window.outliner.topLevelItem(i).data(0, Qt.UserRole)
            for i in range(self.window.outliner.topLevelItemCount())
        ]
        self.assertIn(nested.id, outliner_top)

        self.window.templates_root_box.setChecked(False)
        top_ids = [
            self.window.tree.topLevelItem(i).data(0, Qt.UserRole)
            for i in range(self.window.tree.topLevelItemCount())
        ]
        self.assertNotIn(nested.id, top_ids)
        book_item = _find_item(self.window.tree, self.book.id)
        self.assertIsNotNone(_find_item(book_item, nested.id))

    def test_template_subtree_never_counts_in_project_total(self):
        self.window._refresh_outliner()
        with_templates = self.window._project_total
        self.assertGreater(with_templates, 0)

        # Every template-side id, walked up by parents (the compile rule).
        documents = self.project.documents()
        by_id = {d.id: d for d in documents}
        in_template = set()
        for document in documents:
            current = document
            while current is not None:
                if current.is_templates_root:
                    in_template.add(document.id)
                    break
                current = (by_id.get(current.parent_id)
                           if current.parent_id else None)
        expected = sum(
            d.word_count for d in documents if d.id not in in_template
        )
        template_words = sum(
            d.word_count for d in documents if d.id in in_template
        )
        self.assertGreater(template_words, 0)
        self.assertEqual(self.window._project_total, expected)
        self.assertLess(with_templates, sum(d.word_count for d in documents))

    # --- multi-selection and export scope -----------------------------------

    def test_outliner_multi_selection_survives_a_refresh(self):
        outliner = self.window.outliner
        _find_item(outliner, self.chapter.id).setSelected(True)
        _find_item(outliner, self.scene.id).setSelected(True)
        self.assertEqual(len(outliner.selectedItems()), 2)

        self.window.save_current()          # ends in _refresh_outliner()

        selected = {
            item.data(0, Qt.UserRole) for item in outliner.selectedItems()
        }
        self.assertEqual(selected, {self.chapter.id, self.scene.id})

    def test_export_scope_is_the_union_of_both_trees(self):
        _clear_selection(self.window.tree, self.window.outliner)
        _find_item(self.window.tree, self.scene.id).setSelected(True)
        _find_item(self.window.outliner, self.chapter.id).setSelected(True)

        self.assertEqual(
            self.window._gather_export_selection(),
            {self.scene.id, self.chapter.id},
        )
        self.assertTrue(
            self.window._export_summary({self.scene.id}).startswith(
                "Selection"
            )
        )
        self.assertTrue(
            self.window._export_summary(None).startswith("Whole project")
        )

        for widget in (self.window.tree, self.window.outliner):
            for item in widget.selectedItems():
                item.setSelected(False)
        self.assertIsNone(self.window._gather_export_selection())

    def test_export_dialog_shows_scope_and_no_checklist(self):
        sets = discover_template_sets(self.project.root)

        dialog = ExportOptionsDialog(
            "Selection — 1 item(s): First Light", sets, "default"
        )
        try:
            self.assertEqual(dialog.summary_label.text(),
                             "Selection — 1 item(s): First Light")
            self.assertFalse(hasattr(dialog, "documents"))  # checklist gone
            self.assertGreaterEqual(dialog.set_box.count(), 1)
        finally:
            dialog.deleteLater()

    def test_export_with_empty_selection_writes_the_whole_project(self):
        # The binder keeps its current item selected after a switch, so
        # "nothing selected" has to be built: deselect, then export.
        _clear_selection(self.window.tree, self.window.outliner)
        destination = Path(self.temporary.name) / "whole.txt"
        with patch.object(ExportOptionsDialog, "exec",
                          return_value=QDialog.Accepted), \
                patch("lekhak.app.QFileDialog.getSaveFileName",
                      return_value=(str(destination), "")):
            self.window.export("text")

        exported = destination.read_text(encoding="utf-8")
        self.assertIn("Chapter opener.", exported)
        self.assertIn("First light prose.", exported)
        # Template pages never export as manuscript, chrome or not.
        self.assertNotIn("Generic front text.", exported)

    def test_selection_export_through_the_window_keeps_book_scope(self):
        # Selecting the book folder: expansion pulls its chapters, and
        # the unmatched folder falls back to the default template (2.1).
        _clear_selection(self.window.tree, self.window.outliner)
        _find_item(self.window.tree, self.book.id).setSelected(True)
        destination = Path(self.temporary.name) / "book.txt"
        with patch.object(ExportOptionsDialog, "exec",
                          return_value=QDialog.Accepted), \
                patch("lekhak.app.QFileDialog.getSaveFileName",
                      return_value=(str(destination), "")):
            self.window.export("text")

        exported = destination.read_text(encoding="utf-8")
        self.assertIn("Chapter opener.", exported)
        self.assertIn("First light prose.", exported)
        self.assertIn("Generic front text.", exported)


if __name__ == "__main__":
    unittest.main()
