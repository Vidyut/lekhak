import tempfile
import unittest
import zipfile
from pathlib import Path

from lekhak.project import Project


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temporary.name) / "Novel", "Novel")

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def test_create_uses_transparent_layout(self):
        self.assertEqual(self.project.root.suffix, ".lekhak")
        self.assertTrue(self.project.db_path.exists())
        self.assertTrue(self.project.documents_dir.is_dir())
        self.assertEqual(self.project.get_setting("title"), "Novel")

    def test_content_round_trip_and_search(self):
        document = self.project.documents()[0]
        self.project.write_content(document.id, "<p>Hello <b>Linux</b> writer</p>")
        self.assertIn("Linux", self.project.read_content(document.id))
        self.assertEqual([d.id for d in self.project.search("linux")], [document.id])

    def test_hierarchy_and_export_order(self):
        root = self.project.documents()[0]
        chapter = self.project.add_document("Chapter One", root.id, "chapter")
        self.project.write_content(chapter.id, "<p>Opening</p>")
        scene = self.project.add_document("Scene A", chapter.id, "scene")
        self.project.write_content(scene.id, "<p>Chapter text</p>")
        destination = Path(self.temporary.name) / "book.txt"
        self.project.export_text(destination)
        exported = destination.read_text(encoding="utf-8")
        self.assertLess(exported.index("Opening"), exported.index("Chapter text"))

    def test_delete_removes_descendant_files(self):
        root = self.project.documents()[0]
        child = self.project.add_document("Child", root.id)
        self.project.delete_document(root.id)
        self.assertEqual(self.project.documents(), [])
        self.assertFalse(self.project.content_path(child.id).exists())

    def test_backup_is_recoverable(self):
        backup = self.project.backup()
        self.assertTrue((backup / "project.sqlite3").exists())
        self.assertTrue((backup / "documents").is_dir())

    def test_custom_backup_folder_is_remembered_and_used(self):
        custom_root = Path(self.temporary.name) / "External Backups"
        self.project.set_backup_folder(custom_root)
        backup = self.project.backup()
        self.assertEqual(backup.parent, custom_root / self.project.root.name)
        self.assertEqual(self.project.backup_directory(), backup.parent)
        self.assertTrue((backup / "project.sqlite3").exists())

    def test_snapshot_restore_preserves_both_versions(self):
        document = self.project.documents()[0]
        self.project.write_content(document.id, "<p>First version</p>")
        snapshot = self.project.create_snapshot(document.id, "First")
        self.project.write_content(document.id, "<p>Second version</p>")
        self.project.restore_snapshot(snapshot.id)
        self.assertIn("First version", self.project.read_content(document.id))
        self.assertEqual(len(self.project.snapshots(document.id)), 2)

    def test_word_target_is_persisted(self):
        document = self.project.documents()[0]
        self.project.update_document(document.id, word_target=2500)
        updated = self.project.documents()[0]
        self.assertEqual(updated.word_target, 2500)

    def test_chapter_and_scene_types(self):
        chapter = self.project.add_document("Chapter Two", kind="chapter")
        scene = self.project.add_document("A Meeting", chapter.id, "scene")
        by_id = {item.id: item for item in self.project.documents()}
        self.assertEqual(by_id[chapter.id].kind, "chapter")
        self.assertEqual(by_id[scene.id].kind, "scene")

    def test_epub_export_has_required_structure(self):
        root = self.project.documents()[0]
        scene = self.project.add_document("Scene One", root.id, "scene")
        self.project.write_content(scene.id, "<p>Once upon a time.</p>")
        destination = Path(self.temporary.name) / "book.epub"
        self.project.export_epub(destination)
        with zipfile.ZipFile(destination) as archive:
            self.assertEqual(archive.read("mimetype"), b"application/epub+zip")
            self.assertIn("OEBPS/content.opf", archive.namelist())
            self.assertIn("Once upon a time", archive.read("OEBPS/section-1.xhtml").decode())

    def test_docx_export_contains_scene_text(self):
        chapter = self.project.documents()[0]
        scene = self.project.add_document("Scene One", chapter.id, "scene")
        self.project.write_content(scene.id, "<p>Exported prose.</p>")
        destination = Path(self.temporary.name) / "book.docx"
        self.project.export_docx(destination)
        from docx import Document as DocxDocument
        output = DocxDocument(destination)
        self.assertIn("Exported prose.", [paragraph.text for paragraph in output.paragraphs])

    def test_metadata_is_available_to_export_templates(self):
        document = self.project.documents()[0]
        self.project.set_metadata(document.id, {"POV": "Maya", "Location": "Delhi"})
        rendered = self.project.render_template(
            document, "POV: {metadata:POV}\nPlace: {metadata:Location}\n{content}"
        )
        self.assertIn("POV: Maya", rendered)
        self.assertIn("Place: Delhi", rendered)

    def test_export_can_select_individual_scenes(self):
        chapter = self.project.documents()[0]
        first = self.project.add_document("First", chapter.id, "scene")
        second = self.project.add_document("Second", chapter.id, "scene")
        self.project.write_content(first.id, "<p>Include this.</p>")
        self.project.write_content(second.id, "<p>Exclude this.</p>")
        destination = Path(self.temporary.name) / "selection.txt"
        self.project.export_text(destination, {first.id}, "{metadata:POV}\n{content}")
        exported = destination.read_text(encoding="utf-8")
        self.assertIn("Include this.", exported)
        self.assertNotIn("Exclude this.", exported)

    def test_date_metadata_type_and_value_are_persisted(self):
        document = self.project.documents()[0]
        self.project.set_metadata(
            document.id, {"Story date": "2026-10-20"}, {"Story date": "date"}
        )
        self.assertEqual(
            self.project.metadata_entries(document.id)["Story date"],
            ("2026-10-20", "date", []),
        )
        self.assertIn(
            "2026-10-20",
            self.project.render_template(document, "{metadata:Story date}"),
        )

    def test_dropdown_metadata_restricts_and_persists_options(self):
        document = self.project.documents()[0]
        self.project.set_metadata(
            document.id,
            {"Status": "Revised"},
            {"Status": "choice"},
            {"Status": ["Draft", "Revised", "Final"]},
        )
        self.assertEqual(
            self.project.metadata_entries(document.id)["Status"],
            ("Revised", "choice", ["Draft", "Revised", "Final"]),
        )
        self.assertEqual(
            self.project.render_template(document, "{metadata:Status}"), "Revised"
        )

    def test_seeded_draft_is_a_folder(self):
        self.assertEqual(self.project.documents()[0].kind, "folder")

    def test_folder_kind_is_allowed(self):
        folder = self.project.add_document("Worldbuilding", kind="folder")
        self.assertEqual(folder.kind, "folder")
        with self.assertRaises(ValueError):
            self.project.add_document("Bad", kind="character-sheet")

    def test_parallel_top_level_roots(self):
        manuscript = self.project.add_document("Manuscript", kind="folder")
        characters = self.project.add_document("Characters", kind="folder")
        self.assertIsNone(manuscript.parent_id)
        self.assertIsNone(characters.parent_id)
        roots = [d for d in self.project.documents() if d.parent_id is None]
        self.assertEqual(len(roots), 3)

    def test_arbitrary_nesting_regardless_of_kind(self):
        world = self.project.add_document("Worldbuilding", kind="folder")
        chapter = self.project.add_document("Interlude", world.id, "chapter")
        scene = self.project.add_document("Deep Scene", chapter.id, "scene")
        nested = self.project.add_document("Appendix", scene.id, "folder")
        self.assertEqual(self.project.parent_of(nested.id), scene.id)
        self.assertEqual(
            [d.id for d in self.project.ordered_documents() if d.id in {
                world.id, chapter.id, scene.id, nested.id}],
            [world.id, chapter.id, scene.id, nested.id],
        )

    def test_export_skips_folders_and_notes(self):
        root = self.project.documents()[0]
        self.project.write_content(root.id, "<p>Folder text should not export.</p>")
        chapter = self.project.add_document("Chapter", root.id, "chapter")
        self.project.write_content(chapter.id, "<p>Chapter prose.</p>")
        note = self.project.add_document("Aside", chapter.id, "note")
        self.project.write_content(note.id, "<p>Note text should not export.</p>")
        destination = Path(self.temporary.name) / "book.txt"
        self.project.export_text(destination)
        exported = destination.read_text(encoding="utf-8")
        self.assertIn("Chapter prose.", exported)
        self.assertNotIn("Folder text", exported)
        self.assertNotIn("Note text", exported)

    def test_old_draft_chapter_migrates_to_folder(self):
        import sqlite3
        self.project.close()
        connection = sqlite3.connect(self.project.db_path)
        connection.execute(
            "UPDATE documents SET kind='chapter' "
            "WHERE title='Draft' AND parent_id IS NULL"
        )
        connection.commit()
        connection.close()
        self.project.open()
        self.assertEqual(self.project.documents()[0].kind, "folder")


if __name__ == "__main__":
    unittest.main()
