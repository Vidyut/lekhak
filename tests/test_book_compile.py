import tempfile
import unittest
import zipfile
from pathlib import Path

from lekhak.project import Project
from lekhak.templates import TemplateSet, create_template_set


class BookCompileTests(unittest.TestCase):
    """2.1: book chrome at compile — matching templates, format variants,
    scope rules, document-level templates, and covers."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project = Project.create(self.root / "Novel", "Novel")
        self._build_structure()

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def _build_structure(self):
        """Draft
             TEMPLATES (flagged)
               Marginally Human
                 Title page (front)
                 Back matter/ Afterword (back)
                 ebook/ Ebook front (variant)
               default
                 Generic front
             Marginally Human (book) / Chapter One / First Light
             Random / Chapter Two
        """
        draft = self.project.documents()[0]
        templates = self.project.add_document("TEMPLATES", draft.id, "folder")
        self.project.set_templates_root(templates.id, True)
        mh_template = self.project.add_document(
            "Marginally Human", templates.id, "folder")
        title_page = self.project.add_document(
            "Title page", mh_template.id, "chapter")
        back = self.project.add_document(
            "Back matter", mh_template.id, "folder")
        afterword = self.project.add_document(
            "Afterword", back.id, "chapter")
        ebook = self.project.add_document("ebook", mh_template.id, "folder")
        ebook_front = self.project.add_document(
            "Ebook front", ebook.id, "chapter")
        generic_template = self.project.add_document(
            "default", templates.id, "folder")
        generic_front = self.project.add_document(
            "Generic front", generic_template.id, "chapter")

        for document, html in (
            (title_page, "<p>Title page text.</p>"),
            (afterword, "<p>Afterword text.</p>"),
            (ebook_front, "<p>Ebook front text.</p>"),
            (generic_front, "<p>Generic front text.</p>"),
        ):
            self.project.write_content(document.id, html)

        self.book = self.project.add_document(
            "Marginally Human", draft.id, "folder")
        chapter = self.project.add_document(
            "Chapter One", self.book.id, "chapter")
        self.scene = self.project.add_document(
            "First Light", chapter.id, "scene")
        self.project.write_content(chapter.id, "<p>Chapter opener.</p>")
        self.project.write_content(self.scene.id,
                                   "<p>First light prose.</p>")

        self.other = self.project.add_document("Random", draft.id, "folder")
        other_chapter = self.project.add_document(
            "Chapter Two", self.other.id, "chapter")
        self.project.write_content(other_chapter.id,
                                   "<p>Random chapter text.</p>")

        self.templates_root = templates
        self.draft = draft

    def _export_text(self, selected_ids=None, templates=None) -> str:
        destination = self.root / "book.txt"
        self.project.export_text(destination, selected_ids, templates)
        return destination.read_text(encoding="utf-8")

    def test_book_folder_selection_applies_front_and_back(self):
        exported = self._export_text({self.book.id})
        self.assertIn("Title page text.", exported)
        self.assertIn("Chapter opener.", exported)
        self.assertIn("First light prose.", exported)
        self.assertIn("Afterword text.", exported)
        self.assertLess(exported.index("Title page text."),
                        exported.index("Chapter opener."))
        self.assertLess(exported.index("First light prose."),
                        exported.index("Afterword text."))

    def test_scene_only_selection_gets_no_book_chrome(self):
        exported = self._export_text({self.scene.id})
        self.assertIn("First light prose.", exported)
        self.assertNotIn("Title page text.", exported)
        self.assertNotIn("Afterword text.", exported)
        self.assertNotIn("Chapter opener.", exported)

    def test_whole_project_dresses_named_books_only(self):
        exported = self._export_text()
        self.assertIn("Title page text.", exported)
        self.assertIn("Afterword text.", exported)
        self.assertIn("Random chapter text.", exported)
        self.assertNotIn("Generic front text.", exported)

    def test_selected_unmatched_folder_falls_back_to_default_template(self):
        exported = self._export_text({self.other.id})
        self.assertIn("Generic front text.", exported)
        self.assertIn("Random chapter text.", exported)
        self.assertLess(exported.index("Generic front text."),
                        exported.index("Random chapter text."))
        self.assertNotIn("Title page text.", exported)

    def test_template_selection_exports_no_manuscript(self):
        exported = self._export_text({self.templates_root.id})
        self.assertNotIn("Title page text.", exported)
        self.assertNotIn("Ebook front text.", exported)
        self.assertNotIn("Generic front text.", exported)
        self.assertNotIn("Afterword text.", exported)

    def test_ebook_variant_replaces_basic_content_for_epub(self):
        destination = self.root / "book.epub"
        self.project.export_epub(destination, {self.book.id})
        with zipfile.ZipFile(destination) as archive:
            sections = [n for n in archive.namelist()
                        if n.startswith("OEBPS/section-")]
            joined = "".join(archive.read(n).decode() for n in sections)
        self.assertIn("Ebook front text.", joined)
        self.assertNotIn("Title page text.", joined)
        self.assertNotIn("Afterword text.", joined)

    def test_epub_embeds_the_first_dressed_books_cover(self):
        images = self.project.root / "images" / self.book.id
        images.mkdir(parents=True)
        (images / "cover.png").write_bytes(b"png-bytes")
        destination = self.root / "book.epub"
        self.project.export_epub(destination, {self.book.id})
        with zipfile.ZipFile(destination) as archive:
            names = archive.namelist()
            opf = archive.read("OEBPS/content.opf").decode()
        self.assertIn("OEBPS/images/cover.png", names)
        self.assertIn("properties='cover-image'", opf)
        self.assertIn("name='cover'", opf)

    def test_docx_prints_template_pages_with_page_breaks(self):
        destination = self.root / "book.docx"
        self.project.export_docx(destination, {self.book.id})
        with zipfile.ZipFile(destination) as archive:
            document_xml = archive.read("word/document.xml").decode()
        self.assertIn("Title page", document_xml)
        self.assertIn("Afterword", document_xml)
        self.assertIn("Chapter One", document_xml)
        self.assertIn('w:type="page"', document_xml)

    def test_document_template_override_uses_named_slot(self):
        self.project.update_document(self.scene.id, doc_template="bare")
        exported = self._export_text({self.scene.id})
        self.assertIn("First light prose.", exported)
        self.assertNotIn("First Light", exported)

    def test_custom_document_template_slot_from_the_set(self):
        set_dir = create_template_set("news", self.project.root).directory
        documents_dir = set_dir / "documents"
        documents_dir.mkdir()
        (documents_dir / "news.html").write_text(
            "<p class='preamble'>Breaking news.</p>${Content}",
            encoding="utf-8",
        )
        templates = TemplateSet.load("news", set_dir)
        self.assertIn("news", templates.document_template_names())
        self.project.update_document(self.scene.id, doc_template="news")
        destination = self.root / "book.html"
        self.project.export_html(destination, {self.scene.id}, templates)
        exported = destination.read_text(encoding="utf-8")
        self.assertIn("Breaking news.", exported)
        self.assertIn("First light prose.", exported)

    def test_template_pages_do_not_take_chapter_numbers(self):
        set_dir = create_template_set("counted", self.project.root).directory
        (set_dir / "chapter.txt").write_text(
            "[ch${ChapterNumber}] ${Title}\n${Content}", encoding="utf-8")
        (set_dir / "scene.txt").write_text(
            "[ch${ChapterNumber}.sc${SceneNumber}] ${Title}\n${Content}",
            encoding="utf-8",
        )
        templates = TemplateSet.load("counted", set_dir)
        exported = self._export_text(None, templates)
        self.assertIn("[ch1] Chapter One", exported)
        self.assertNotIn("[ch1] Title page", exported)
        self.assertNotIn("[ch1] Generic front", exported)

    def test_selection_export_drops_project_chrome_whole_keeps_it(self):
        set_dir = create_template_set("dressed", self.project.root).directory
        (set_dir / "project_header.txt").write_text("== BEGIN ==",
                                                    encoding="utf-8")
        (set_dir / "project_footer.txt").write_text("== END ==",
                                                    encoding="utf-8")
        templates = TemplateSet.load("dressed", set_dir)

        selected = self._export_text({self.scene.id}, templates)
        self.assertNotIn("== BEGIN ==", selected)
        self.assertNotIn("== END ==", selected)

        whole = self._export_text(None, templates)
        self.assertTrue(whole.startswith("== BEGIN =="))
        self.assertIn("== END ==", whole)


if __name__ == "__main__":
    unittest.main()
