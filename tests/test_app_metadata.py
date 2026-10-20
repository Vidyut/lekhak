"""1.12 metadata panel: the inspector's inline rows — offscreen GUI.

Same test contract as the other GUI suites: QSettings redirected into a
temp dir, windows never closed() (closeEvent would save into a possibly-
closed project and hang offscreen).
"""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox  # noqa: E402

from lekhak.app import (  # noqa: E402
    PROJECT_METADATA_TARGET, MainWindow, MetadataDialog,
)
from lekhak.project import Project  # noqa: E402

_application = QApplication.instance() or QApplication([])
_application.setOrganizationName("Lekhak")
_application.setApplicationName("Lekhak")
_settings_dir = tempfile.mkdtemp(prefix="lekhak-metadata-settings-")
# QSettings objects created from now on read/write under _settings_dir.
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)


class MetadataPanelTests(unittest.TestCase):
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
        # Never close() the window: closeEvent -> save_current on a closed
        # project raises into a modal QMessageBox and hangs offscreen.
        self.window.project = None
        self.project.close()
        self.temporary.cleanup()

    def test_document_selection_shows_its_own_rows(self):
        self.project.set_metadata(self.scene.id, {"POV": "Maya"})

        self.window._select_document(self.scene.id)

        table = self.window.metadata_table
        self.assertEqual(self.window._metadata_target, self.scene.id)
        self.assertEqual(table.rowCount(), 1)
        self.assertEqual(table.item(0, 0).text(), "POV")
        self.assertEqual(table.item(0, 3).text(), "Maya")

    def test_folder_selection_shows_project_metadata(self):
        self.project.set_project_metadata({"Series": ("Strays", "text", [])})
        # Select away first: the panel refreshes on a selection CHANGE,
        # and the folder was already selected after the project switch.
        self.window._select_document(self.scene.id)

        self.window._select_document(self.folder.id)

        table = self.window.metadata_table
        self.assertEqual(self.window._metadata_target, PROJECT_METADATA_TARGET)
        self.assertEqual(table.rowCount(), 1)
        self.assertEqual(table.item(0, 0).text(), "Series")
        self.assertEqual(table.item(0, 3).text(), "Strays")

    def test_nothing_selected_targets_the_project(self):
        self.project.set_project_metadata({"Series": ("Strays", "text", [])})

        self.window.current_id = None
        self.window._populate_metadata_table()

        self.assertEqual(self.window._metadata_target, PROJECT_METADATA_TARGET)
        self.assertEqual(self.window.metadata_table.rowCount(), 1)

    def test_live_edit_persists_a_document_field(self):
        self.window._select_document(self.scene.id)

        self.window.metadata_table.add_field()
        self.window.metadata_table.item(0, 0).setText("POV")
        self.window.metadata_table.item(0, 3).setText("Maya")

        self.assertEqual(
            self.project.metadata_entries(self.scene.id)["POV"],
            ("Maya", "text", []),
        )

    def test_live_edit_persists_a_project_field(self):
        self.window._select_document(self.folder.id)

        self.window.metadata_table.add_field()
        self.window.metadata_table.item(0, 0).setText("Series")
        self.window.metadata_table.item(0, 3).setText("Strays")

        self.assertEqual(
            self.project.project_metadata()["Series"],
            ("Strays", "text", []),
        )

    def test_clearing_a_key_never_drops_the_field(self):
        # Mid-rename: the key commits empty first, the value still held.
        # A named-subset write at that instant would delete the field
        # from storage — the write waits for the row to name itself.
        self.project.set_metadata(self.scene.id, {"POV": "Maya"})
        self.window._select_document(self.scene.id)

        self.window.metadata_table.item(0, 0).setText("")

        self.assertEqual(
            self.project.metadata_entries(self.scene.id)["POV"],
            ("Maya", "text", []),
        )

        self.window.metadata_table.item(0, 0).setText("Hero")

        entries = self.project.metadata_entries(self.scene.id)
        self.assertNotIn("POV", entries)
        self.assertEqual(entries["Hero"], ("Maya", "text", []))

    def test_add_field_does_not_disturb_existing_rows(self):
        self.project.set_metadata(self.scene.id, {"POV": "Maya", "Location": "Delhi"})
        self.window._select_document(self.scene.id)

        self.window.metadata_table.add_field()

        self.assertEqual(
            set(self.project.metadata_entries(self.scene.id)),
            {"POV", "Location"},
        )

    def test_remove_selected_persists_the_deletion(self):
        self.project.set_metadata(self.scene.id, {"POV": "Maya"})
        self.window._select_document(self.scene.id)

        self.window.metadata_table.selectAll()
        self.window.metadata_table.remove_selected()

        self.assertEqual(self.project.metadata_entries(self.scene.id), {})

    def test_dropdown_value_widget_change_persists(self):
        self.project.set_metadata(
            self.scene.id, {"Status": "Draft"}, {"Status": "choice"},
            {"Status": ["Draft", "Final"]},
        )
        self.window._select_document(self.scene.id)

        value_widget = self.window.metadata_table.cellWidget(0, 3)
        self.assertIsInstance(value_widget, QComboBox)
        value_widget.setCurrentText("Final")

        self.assertEqual(
            self.project.metadata_entries(self.scene.id)["Status"][0], "Final"
        )

    def test_metadata_widgets_disabled_without_a_project(self):
        window = MainWindow()

        self.assertFalse(window.metadata_table.isEnabled())
        self.assertFalse(window.metadata_add_button.isEnabled())
        self.assertFalse(window.metadata_remove_button.isEnabled())
        window.project = None

    def test_dialog_edits_the_same_rows_through_the_shared_table(self):
        entries = {"POV": ("Maya", "text", []),
                   "Status": ("Draft", "choice", ["Draft", "Final"])}

        dialog = MetadataDialog(entries)

        self.assertEqual(dialog.values_types_options(), (
            {"POV": "Maya", "Status": "Draft"},
            {"POV": "text", "Status": "choice"},
            {"POV": [], "Status": ["Draft", "Final"]},
        ))
        dialog.table.add_field()
        self.assertEqual(dialog.table.rowCount(), 3)
        dialog.deleteLater()

    def test_edit_metadata_target_follows_the_selection(self):
        self.assertEqual(self.window._selection_metadata_target(),
                         PROJECT_METADATA_TARGET)          # Draft folder after switch
        self.window._select_document(self.scene.id)
        self.assertEqual(self.window._selection_metadata_target(), self.scene.id)
        self.window.current_id = None
        self.assertEqual(self.window._selection_metadata_target(),
                         PROJECT_METADATA_TARGET)          # outliner root
        bare = MainWindow()
        self.assertIsNone(bare._selection_metadata_target())
        bare.project = None

    def test_editor_tree_selecting_a_folder_switches_the_panel(self):
        self.project.set_metadata(self.scene.id, {"POV": "Maya"})
        self.project.set_project_metadata({"Series": ("Strays", "text", [])})
        self.window._select_document(self.scene.id)
        self.assertEqual(self.window.metadata_table.item(0, 0).text(), "POV")

        self.window._select_document(self.folder.id)

        self.assertEqual(self.window._metadata_target, PROJECT_METADATA_TARGET)
        self.assertEqual(self.window.metadata_table.item(0, 0).text(), "Series")


if __name__ == "__main__":
    unittest.main()
