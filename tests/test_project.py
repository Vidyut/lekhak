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
            document, "POV: ${Metadata.POV}\nPlace: ${Metadata.Location}\n${Content}"
        )
        self.assertIn("POV: Maya", rendered)
        self.assertIn("Place: Delhi", rendered)

    def test_export_can_select_individual_scenes(self):
        from lekhak.templates import TemplateSet

        root = self.project.documents()[0]
        first = self.project.add_document("First", root.id, "scene")
        second = self.project.add_document("Second", root.id, "scene")
        self.project.set_metadata(first.id, {"POV": "Maya"})
        self.project.write_content(first.id, "<p>Include this.</p>")
        self.project.write_content(second.id, "<p>Exclude this.</p>")
        templates = TemplateSet(
            "test", None,
            {"scene": "${Metadata.POV}\n${Content}"},
            {"scene": "${Metadata.POV}\n${Content}"},
        )
        destination = Path(self.temporary.name) / "selection.txt"
        self.project.export_text(destination, {first.id}, templates)
        exported = destination.read_text(encoding="utf-8")
        self.assertIn("Include this.", exported)
        self.assertNotIn("Exclude this.", exported)
        self.assertIn("Maya", exported)

    def test_project_metadata_round_trips_types_and_options(self):
        self.project.set_project_metadata({
            "Series": ("Strays", "text", []),
            "Story date": ("2026-10-20", "date", []),
            "Status": ("Draft", "choice", ["Draft", "Final"]),
        })
        entries = self.project.project_metadata()
        self.assertEqual(entries["Series"], ("Strays", "text", []))
        self.assertEqual(entries["Story date"], ("2026-10-20", "date", []))
        self.assertEqual(entries["Status"], ("Draft", "choice", ["Draft", "Final"]))

    def test_set_project_metadata_replaces_and_ignores_blank_keys(self):
        self.project.set_project_metadata({"Series": ("Strays", "text", [])})
        self.project.set_project_metadata(
            {"Verse": ("Three", "text", []), "   ": ("x", "text", [])}
        )
        self.assertEqual(list(self.project.project_metadata()), ["Verse"])

    def test_junk_project_metadata_setting_falls_back_to_empty(self):
        self.project.set_setting("project_metadata", "{not json")
        self.assertEqual(self.project.project_metadata(), {})
        self.project.set_setting("project_metadata", '[1, 2, {"value": 5}]')
        self.assertEqual(self.project.project_metadata(), {})
        self.project.set_setting(
            "project_metadata", '{"Series": 5, "Verse": {"value": "Three"}}'
        )
        self.assertEqual(self.project.project_metadata(),
                         {"Verse": ("Three", "text", [])})

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
            self.project.render_template(document, "${Metadata.Story date}"),
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
            self.project.render_template(document, "${Metadata.Status}"), "Revised"
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


    def test_sibling_rank_is_per_parent_and_survives_reorder(self):
        root = self.project.documents()[0]
        folder_one = self.project.add_document("One", root.id, "folder")
        folder_two = self.project.add_document("Two", root.id, "folder")
        self.project.add_document("A", folder_one.id, "scene")
        self.project.add_document("B", folder_one.id, "scene")
        self.project.add_document("C", folder_two.id, "scene")

        def rank(document_id):
            parent = next(d for d in self.project.documents()
                          if d.id == document_id).parent_id
            siblings = [d for d in self.project.documents()
                        if d.parent_id == parent]
            siblings.sort(key=lambda d: d.position)
            return [d.id for d in siblings].index(document_id) + 1

        c = next(d for d in self.project.documents() if d.title == "C")
        b = next(d for d in self.project.documents() if d.title == "B")
        self.assertEqual(rank(c.id), 1)
        self.assertEqual(rank(b.id), 2)
        # Rank is per parent: C's first-in-its-own-folder must not be
        # affected by how many siblings its uncle has.
        self.project.add_document("D", folder_two.id, "scene")
        self.assertEqual(rank(c.id), 1)
        # A reorder renumbers the ranks that follow it.
        self.project.reorder(b.id, folder_one.id, 0)
        self.assertEqual(rank(b.id), 1)
        self.assertEqual(rank(next(d for d in self.project.documents()
                                   if d.title == "A").id), 2)


class SearchReplaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temporary.name) / "Novel", "Novel")
        draft = self.project.documents()[0]
        self.chapter = self.project.add_document("Chapter One", draft.id, "chapter")
        self.scene = self.project.add_document("Scene", self.chapter.id, "scene")
        self.project.write_content(self.scene.id, "<p>Kael opened the airlock twice.</p>")
        self.project.update_document(self.chapter.id, synopsis="Kael waits")

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def test_replace_literal_is_case_insensitive_by_default(self):
        counts = self.project.replace("kael", "Vidyut", in_synopses=True)
        self.assertEqual(counts["replacements"], 2)
        self.assertEqual(counts["documents"], 2)
        self.assertIn("Vidyut opened", self.project.plain_text(
            self.project.read_content(self.scene.id)))
        self.assertEqual(self.project.documents()[1].synopsis, "Vidyut waits")

    def test_replace_respects_field_flags(self):
        counts = self.project.replace("Kael", "Vidyut", in_titles=False,
                                      in_synopses=False)
        self.assertEqual(counts["titles"] + counts["synopses"], 0)
        self.assertEqual(counts["replacements"], 1)
        self.assertIn("Kael waits", self.project.documents()[1].synopsis)

    def test_replace_takes_titles_when_asked(self):
        counts = self.project.replace("Chapter One", "Chapter 1", in_titles=True)
        self.assertEqual(counts["titles"], 1)
        self.assertEqual(self.project.documents()[1].title, "Chapter 1")

    def test_literal_replacement_is_verbatim_with_backslashes(self):
        self.project.write_content(self.scene.id, "<p>path a\\b</p>")
        counts = self.project.replace("a\\b", "x\\y")
        self.assertEqual(counts["replacements"], 1)
        self.assertIn("x\\y", self.project.read_content(self.scene.id))

    def test_regex_replace_supports_backreferences(self):
        counts = self.project.replace(r"twice", r"thrice", regex=True)
        self.assertEqual(counts["replacements"], 1)
        self.assertIn("thrice", self.project.plain_text(
            self.project.read_content(self.scene.id)))

    def test_replace_can_target_single_document(self):
        counts = self.project.replace("the", "a", document_ids={self.scene.id})
        self.assertEqual(counts["documents"], 1)

    def test_search_snippets_reports_field_and_context(self):
        hits = self.project.search_snippets("Kael")
        fields = {field for _doc, field, _snippet in hits}
        self.assertEqual(fields, {"content", "synopsis"})
        content_hit = next(s for _d, f, s in hits if f == "content")
        self.assertIn("opened", content_hit)

    def test_search_snippets_field_filter(self):
        hits = self.project.search_snippets("Kael", fields={"synopsis"})
        self.assertTrue(all(field == "synopsis" for _d, field, _s in hits))
        self.assertEqual(len(hits), 1)

    def test_search_snippets_rejects_bad_regex_loudly(self):
        with self.assertRaises(Exception):
            self.project.search_snippets("(", regex=True)

    def test_replace_empty_query_is_noop(self):
        self.assertEqual(self.project.replace("", "x")["replacements"], 0)


class SplitMergeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temporary.name) / "Novel", "Novel")
        draft = self.project.documents()[0]
        self.scene_a = self.project.add_document("A", draft.id, "scene")
        self.scene_b = self.project.add_document("B", draft.id, "scene")
        self.scene_c = self.project.add_document("C", draft.id, "scene")
        self.project.write_content(self.scene_a.id, "<p>alpha beta gamma</p>")
        self.project.write_content(self.scene_b.id, "<p>second scene</p>")
        self.project.write_content(self.scene_c.id, "<p>third scene</p>")

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def test_split_inserts_sibling_right_after_and_snapshots(self):
        new = self.project.split_document(
            self.scene_a.id, "<p>alpha</p>", "<p>beta gamma</p>")
        self.assertEqual(new.title, "A (2)")
        self.assertEqual(new.kind, "scene")
        self.assertEqual(new.position, self.scene_a.position + 1)
        self.assertEqual(self.project.plain_text(
            self.project.read_content(self.scene_a.id)), "alpha")
        self.assertEqual(self.project.plain_text(
            self.project.read_content(new.id)), "beta gamma")
        names = [s.name for s in self.project.snapshots(self.scene_a.id)]
        self.assertIn("Before split", names)

    def test_split_renumbers_following_siblings_in_binder_order(self):
        self.project.split_document(self.scene_a.id, "<p>alpha</p>", "<p>beta</p>")
        titles = [d.title for d in self.project.documents()]
        self.assertEqual(titles[1:4], ["A", "A (2)", "B"])

    def test_split_title_avoids_collisions(self):
        self.project.split_document(self.scene_a.id, "<p>alpha</p>", "<p>beta</p>")
        new2 = self.project.split_document(
            self.scene_a.id, "<p>alp</p>", "<p>ha beta</p>")
        self.assertEqual(new2.title, "A (3)")

    def test_split_refuses_empty_half(self):
        with self.assertRaises(ValueError):
            self.project.split_document(self.scene_a.id, "<p>alpha beta</p>", "<p></p>")
        with self.assertRaises(ValueError):
            self.project.split_document(self.scene_a.id, "<p></p>", "<p>alpha</p>")

    def test_split_refuses_unknown_document(self):
        with self.assertRaises(KeyError):
            self.project.split_document("nope", "<p>x</p>", "<p>y</p>")

    def test_merge_appends_next_sibling_and_deletes_it(self):
        merged = self.project.merge_documents(self.scene_a.id, self.scene_b.id)
        text = self.project.plain_text(self.project.read_content(self.scene_a.id))
        self.assertIn("alpha beta gamma", text)
        self.assertIn("second scene", text)
        self.assertEqual(merged.word_count, 5)
        remaining = {d.title for d in self.project.documents()}
        self.assertNotIn("B", remaining)
        names = [s.name for s in self.project.snapshots(self.scene_a.id)]
        self.assertIn("Before merge", names)

    def test_merge_keeps_first_title_and_position(self):
        merged = self.project.merge_documents(self.scene_a.id, self.scene_b.id)
        self.assertEqual(merged.title, "A")
        self.assertEqual(merged.id, self.scene_a.id)

    def test_merge_rehomes_second_snapshots(self):
        self.project.create_snapshot(self.scene_b.id, "b history")
        self.project.merge_documents(self.scene_a.id, self.scene_b.id)
        names = [s.name for s in self.project.snapshots(self.scene_a.id)]
        self.assertIn("b history", names)

    def test_merge_requires_immediately_following_sibling(self):
        with self.assertRaises(ValueError):
            self.project.merge_documents(self.scene_a.id, self.scene_c.id)
        with self.assertRaises(ValueError):
            self.project.merge_documents(self.scene_b.id, self.scene_a.id)

    def test_merge_refuses_when_second_has_children(self):
        child = self.project.add_document("child", self.scene_b.id, "note")
        with self.assertRaises(ValueError):
            self.project.merge_documents(self.scene_a.id, self.scene_b.id)
        self.assertIsNotNone(child.id)
        titles = {d.title for d in self.project.documents()}
        self.assertIn("B", titles)

    def test_merge_refuses_same_document_and_unknown_ids(self):
        with self.assertRaises(ValueError):
            self.project.merge_documents(self.scene_a.id, self.scene_a.id)
        with self.assertRaises(KeyError):
            self.project.merge_documents(self.scene_a.id, "nope")

    def test_next_sibling_walks_the_same_parent(self):
        self.assertEqual(self.project.next_sibling(self.scene_a.id).id,
                         self.scene_b.id)
        self.assertEqual(self.project.next_sibling(self.scene_c.id), None)
        self.assertEqual(self.project.next_sibling("nope"), None)

    def test_split_then_merge_round_trips_content(self):
        new = self.project.split_document(
            self.scene_a.id, "<p>alpha</p>", "<p>beta gamma</p>")
        merged = self.project.merge_documents(self.scene_a.id, new.id)
        text = self.project.plain_text(self.project.read_content(self.scene_a.id))
        self.assertIn("alpha", text)
        self.assertIn("beta gamma", text)
        self.assertEqual(merged.word_count, 3)


class WikiLinkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temporary.name) / "Novel", "Novel")
        self.root = self.project.documents()[0]
        self.chapter = self.project.add_document(
            "Chapter One", self.root.id, "chapter")
        self.scene_a = self.project.add_document(
            "Scene A", self.chapter.id, "scene")
        self.scene_b = self.project.add_document(
            "Scene B", self.chapter.id, "scene")
        self.project.set_metadata(self.scene_a.id, {"Location": "Mars"})
        self.project.set_metadata(self.scene_b.id, {"Location": "Venus"})

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def test_resolve_link_exact_and_case_insensitive(self):
        self.assertEqual(
            [d.id for d in self.project.resolve_link("Scene A")],
            [self.scene_a.id])
        self.assertEqual(
            [d.id for d in self.project.resolve_link("scene a")],
            [self.scene_a.id])

    def test_resolve_link_substring_offers_candidates_without_winning(self):
        matches = self.project.resolve_link("Scene")
        self.assertEqual(
            {d.id for d in matches},
            {self.scene_a.id, self.scene_b.id})

    def test_resolve_link_broken_and_empty(self):
        self.assertEqual(self.project.resolve_link("Nope"), [])
        self.assertEqual(self.project.resolve_link("   "), [])

    def test_resolve_link_follows_a_retitle(self):
        self.project.update_document(self.scene_a.id, title="Renamed")
        self.assertEqual(
            [d.id for d in self.project.resolve_link("Renamed")],
            [self.scene_a.id])
        self.assertEqual(self.project.resolve_link("Scene A"), [])

    def test_wiki_targets_reports_resolution_per_document(self):
        self.project.write_content(
            self.scene_a.id,
            "<p>See [[Scene B]] and [[Nope]].</p>")
        targets = dict(self.project.wiki_targets(self.scene_a.id))
        self.assertEqual(
            [d.id for d in targets["Scene B"]],
            [self.scene_b.id])
        self.assertEqual(targets["Nope"], [])

    def test_plain_text_strips_wiki_markers_for_counts_and_export(self):
        self.project.write_content(
            self.scene_a.id,
            "<p>See [[Scene B]] and [[Nope]].</p>")
        text = self.project.plain_text(self.project.read_content(self.scene_a.id))
        self.assertNotIn("[[", text)
        self.assertNotIn("]]", text)
        self.assertEqual(text, "See Scene B and Nope.")

    def test_plain_text_stripping_is_idempotent(self):
        self.project.write_content(self.scene_a.id, "<p>See [[Scene B]].</p>")
        once = self.project.plain_text(self.project.read_content(self.scene_a.id))
        self.assertEqual(self.project.plain_text(once), once)

    def test_canonicalize_links_restores_editor_markup_to_wiki_form(self):
        html = (
            '<p>See <a href="lekhak://doc/x"><span style="color:#0000ff;">'
            "Scene B</span></a> and "
            '<a href="lekhak://missing"><span style="color:#c0392b;">'
            "[missing: Nope]</span></a>.</p>"
        )
        canonical = self.project.canonicalize_links(html)
        self.assertIn("[[Scene B]]", canonical)
        self.assertIn("[[Nope]]", canonical)
        self.assertNotIn("<a ", canonical)
        self.assertNotIn("missing:", canonical)

    def test_canonicalize_links_is_idempotent_and_leaves_plain_text_alone(self):
        plain = "<p>Ordinary prose with no links.</p>"
        self.assertEqual(self.project.canonicalize_links(plain), plain)
        once = self.project.canonicalize_links(
            '<p><a href="lekhak://doc/x">Scene B</a></p>')
        self.assertEqual(self.project.canonicalize_links(once), once)


if __name__ == "__main__":
    unittest.main()
