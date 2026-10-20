import tempfile
import unittest
from pathlib import Path

from lekhak.project import Project
from lekhak.templates import (
    TemplateSet, create_template_set, discover_template_sets,
)


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project = Project.create(self.root / "Novel", "Novel")

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def _chapter_with_scenes(self, titles):
        draft = self.project.documents()[0]
        chapter = self.project.add_document("Chapter One", draft.id, "chapter")
        self.project.write_content(chapter.id, "<p>Chapter opener.</p>")
        scenes = []
        for title in titles:
            scene = self.project.add_document(title, chapter.id, "scene")
            self.project.write_content(scene.id, f"<p>{title} text.</p>")
            scenes.append(scene)
        return chapter, scenes

    def test_builtin_text_export_is_title_and_content(self):
        chapter, scenes = self._chapter_with_scenes(["Alpha", "Beta"])
        destination = self.root / "book.txt"
        self.project.export_text(destination)
        exported = destination.read_text(encoding="utf-8")
        self.assertIn("Chapter One", exported)
        self.assertIn("Chapter opener.", exported)
        self.assertIn("Alpha text.", exported)
        self.assertIn("* * *", exported)

    def test_builtin_html_export_wraps_sections(self):
        self._chapter_with_scenes(["Alpha"])
        destination = self.root / "book.html"
        self.project.export_html(destination)
        exported = destination.read_text(encoding="utf-8")
        self.assertIn('class="chapter"', exported)
        self.assertIn("<h1>Chapter One</h1>", exported)
        self.assertIn('class="scene"', exported)

    def test_first_scene_slot_overrides_scene_slot(self):
        chapter, _scenes = self._chapter_with_scenes(["Alpha", "Beta"])
        set_dir = self.root / "sets" / "quote-first"
        templates = create_template_set("quote-first", self.project.root)
        scene_html = templates.directory / "scene.html"
        scene_html.write_text("<section class='scene'><h2>${Title}</h2>${Content}</section>", encoding="utf-8")
        first_html = templates.directory / "first_scene.html"
        first_html.write_text("<section class='scene opening'><blockquote>${Metadata.Epigraph}</blockquote><h2>${Title}</h2>${Content}</section>", encoding="utf-8")
        self.project.set_metadata(_scenes[0].id, {"Epigraph": "Stars, like dust."})
        templates = TemplateSet.load("quote-first", templates.directory)
        destination = self.root / "book.html"
        self.project.export_html(destination, None, templates)
        exported = destination.read_text(encoding="utf-8")
        self.assertIn("scene opening", exported)
        self.assertIn("Stars, like dust.", exported)
        self.assertEqual(exported.count("scene opening"), 1)

    def test_counters_and_running_word_total(self):
        chapter, scenes = self._chapter_with_scenes(["Alpha", "Beta"])
        set_dir = create_template_set("counters", self.project.root).directory
        (set_dir / "scene.txt").write_text(
            "[ch${ChapterNumber}.sc${SceneNumber}.tot${WordsTotal}] ${Title}\n${Content}",
            encoding="utf-8",
        )
        templates = TemplateSet.load("counters", set_dir)
        destination = self.root / "book.txt"
        self.project.export_text(destination, None, templates)
        exported = destination.read_text(encoding="utf-8")
        self.assertIn("[ch1.sc1.", exported)
        self.assertIn("[ch1.sc2.", exported)
        first_total = int(exported.split("tot")[1].split("]")[0])
        second_total = int(exported.rsplit("tot", 1)[1].split("]")[0])
        self.assertGreater(second_total, first_total)

    def test_project_set_shadows_user_name_and_is_discoverable(self):
        create_template_set("my-set", self.project.root)
        names = [s.name for s in discover_template_sets(self.project.root)]
        self.assertIn("default", names)
        self.assertIn("my-set", names)

    def test_create_set_rejects_bad_names(self):
        with self.assertRaises(ValueError):
            create_template_set("../escape", self.project.root)

    def test_project_header_and_footer_wrap_text_export(self):
        set_dir = create_template_set("dressed", self.project.root).directory
        (set_dir / "project_header.txt").write_text("== BEGIN ==", encoding="utf-8")
        (set_dir / "project_footer.txt").write_text("== END ==", encoding="utf-8")
        templates = TemplateSet.load("dressed", set_dir)
        self._chapter_with_scenes(["Alpha"])
        destination = self.root / "book.txt"
        self.project.export_text(destination, None, templates)
        exported = destination.read_text(encoding="utf-8")
        self.assertTrue(exported.startswith("== BEGIN =="))
        self.assertIn("== END ==", exported)

    def test_epub_units_are_chapters_with_embedded_scenes(self):
        chapter, scenes = self._chapter_with_scenes(["Alpha", "Beta"])
        import zipfile
        destination = self.root / "book.epub"
        self.project.export_epub(destination)
        with zipfile.ZipFile(destination) as archive:
            sections = [n for n in archive.namelist() if n.startswith("OEBPS/section-")]
            self.assertEqual(len(sections), 1)
            page = archive.read(sections[0]).decode()
        self.assertIn("Alpha text.", page)
        self.assertIn("Beta text.", page)
        self.assertIn("scene-divider", page)

    def test_epub_inline_toc_links_every_unit(self):
        import zipfile
        self._chapter_with_scenes(["Alpha"])
        standalone = self.project.add_document(
            "Epilogue", self.project.documents()[0].id, "scene")
        self.project.write_content(standalone.id, "<p>After all.</p>")
        destination = self.root / "book.epub"
        self.project.export_epub(destination)
        with zipfile.ZipFile(destination) as archive:
            self.assertIn("OEBPS/toc.xhtml", archive.namelist())
            toc = archive.read("OEBPS/toc.xhtml").decode()
            opf = archive.read("OEBPS/content.opf").decode()
        self.assertIn("Chapter One", toc)
        self.assertIn("Epilogue", toc)
        self.assertIn("section-1.xhtml", toc)
        self.assertIn("section-2.xhtml", toc)
        self.assertIn("idref='toc-page'", opf)

    def test_epub_toc_page_can_be_disabled_by_emptying_slot(self):
        import zipfile
        self._chapter_with_scenes(["Alpha"])
        set_dir = create_template_set("no-toc", self.project.root).directory
        (set_dir / "toc_page.html").write_text("", encoding="utf-8")
        templates = TemplateSet.load("no-toc", set_dir)
        destination = self.root / "book.epub"
        self.project.export_epub(destination, None, templates)
        with zipfile.ZipFile(destination) as archive:
            self.assertNotIn("OEBPS/toc.xhtml", archive.namelist())

    def test_docx_contains_page_number_toc_field(self):
        import zipfile
        self._chapter_with_scenes(["Alpha"])
        destination = self.root / "book.docx"
        self.project.export_docx(destination)
        with zipfile.ZipFile(destination) as archive:
            document_xml = archive.read("word/document.xml").decode()
        self.assertIn("TOC", document_xml)
        self.assertIn('\\o "1-3"', document_xml)
        self.assertNotIn("\\h ", document_xml)


class WordCountTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temporary.name) / "Novel", "Novel")

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def test_word_count_cached_on_write(self):
        document = self.project.documents()[0]
        self.project.write_content(document.id, "<p>One two three</p>")
        self.assertEqual(self.project.documents()[0].word_count, 3)

    def test_backfill_runs_once_for_old_projects(self):
        import sqlite3
        document = self.project.documents()[0]
        self.project.write_content(document.id, "<p>Four five six seven</p>")
        self.project.close()
        connection = sqlite3.connect(self.project.db_path)
        connection.execute("UPDATE documents SET word_count=0")
        connection.execute("DELETE FROM settings WHERE key='word_count_backfill'")
        connection.commit()
        connection.close()
        self.project.open()
        self.assertEqual(self.project.documents()[0].word_count, 4)

    def test_word_rollups_sum_descendants(self):
        draft = self.project.documents()[0]
        chapter = self.project.add_document("Chapter", draft.id, "chapter")
        scene_a = self.project.add_document("A", chapter.id, "scene")
        scene_b = self.project.add_document("B", chapter.id, "scene")
        self.project.write_content(scene_a.id, "<p>one two</p>")
        self.project.write_content(scene_b.id, "<p>one two three four</p>")
        rollups = self.project.word_rollups()
        self.assertEqual(rollups[scene_a.id], 2)
        self.assertEqual(rollups[chapter.id], 6)
        self.assertEqual(rollups[draft.id], 6)

    def test_metadata_entries_all_matches_per_document_reads(self):
        draft = self.project.documents()[0]
        chapter = self.project.add_document("Chapter", draft.id, "chapter")
        self.project.set_metadata(draft.id, {"POV": "Maya"})
        self.project.set_metadata(chapter.id, {"Status": "Draft"}, {"Status": "choice"},
                                  {"Status": ["Draft", "Final"]})
        everything = self.project.metadata_entries_all()
        self.assertEqual(everything[draft.id], self.project.metadata_entries(draft.id))
        self.assertEqual(everything[chapter.id], self.project.metadata_entries(chapter.id))
        self.assertEqual(self.project.metadata_keys(), ["POV", "Status"])


if __name__ == "__main__":
    unittest.main()
