"""2.3 Scrivener dump importer: parser and placement — pure project tests.

The synthetic dump mirrors the author's real multi-document markdown
export: blank-line-separated headers, multi-line Synopsis values,
markdown-ish bodies, and titles that repeat across books.
"""

import tempfile
import unittest
from pathlib import Path

from lekhak.importer import (
    dump_books, import_all_books, import_book, markdown_to_html, parse_dump,
)
from lekhak.project import Project

SYNTHETIC_DUMP = """\
Title: Synthetic Corpus
Author: Test

===DOCUMENT===

Type: Chapter

ID: 1

Hierarchy: junk

Position: 1

ParentPosition: 0

Parent: Book A

Level1: Prologue

Level2: Prologue

Title: Prologue

PoV: Maya

Location: 

Date: 

Quote: 

Source: 

Status: No Status

Label: No Label

Keywords: 

Synopsis: 1) Setup:

2) Payoff:



===TEXT===

The *opening* line.

===DOCUMENT===

Type: Scene

ID: 2

Hierarchy: junk

Position: 1

ParentPosition: 1

Parent: Prologue

Level1: Prologue

Level2: Prologue

Title: Clinic

PoV: None

Location: Delhi

Date: Wednesday, January 7, 2443

Quote: 

Source: 

Status: Draft

Label: 

Keywords: Hersh, Clinic

Synopsis: 

===TEXT===

A *quiet* scene with **weight**.

===DOCUMENT===

Type: Chapter

ID: 3

Hierarchy: junk

Position: 1

ParentPosition: 0

Parent: Book B

Level1: Prologue

Level2: Prologue

Title: Prologue

PoV: Aaxyl

Location: 

Date: 

Quote: 

Source: 

Status: No Status

Label: 

Keywords: 

Synopsis: 

===TEXT===

# Title Page #

Other Book

===DOCUMENT===

Type: Scene

ID: 4

Hierarchy: junk

Position: 1

ParentPosition: 1

Parent: Prologue

Level1: Prologue

Level2: Prologue

Title: B-clinic

PoV: Aaxyl

Location: 

Date: 

Quote: 

Source: 

Status: No Status

Label: 

Keywords: 

Synopsis: 

===TEXT===

Under the OTHER Prologue, not Book A's.

===DOCUMENT===

Type: Scene

ID: 5

Hierarchy: junk

Position: 2

ParentPosition: 0

Parent: Book A

Level1: Extra

Level2: Extra

Title: Extra

PoV: 

Location: 

Date: 

Quote: 

Source: 

Status: No Status

Label: 

Keywords: 

Synopsis: 

===TEXT===

Second child of Book A.
"""


class ImporterParserTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "dump.md"
        self.path.write_text(SYNTHETIC_DUMP, encoding="utf-8")
        self.raws = parse_dump(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def test_books_are_the_parents_that_are_not_documents(self):
        self.assertEqual(dump_books(self.raws), ["Book A", "Book B"])

    def test_unset_scrivener_sentinels_are_not_stored(self):
        clinic = next(raw for raw in self.raws if raw.title == "Clinic")
        self.assertNotIn("PoV", clinic.metadata)         # "None" is unset
        self.assertEqual(clinic.metadata["Status"], "Draft")  # real value kept
        self.assertEqual(clinic.metadata["Location"], "Delhi")
        self.assertEqual(clinic.metadata["Keywords"], "Hersh, Clinic")
        self.assertEqual(clinic.metadata["Date"], "Wednesday, January 7, 2443")
        self.assertEqual(clinic.value_types, {"Date": "date"})

    def test_multi_line_synopsis_stays_one_field(self):
        prologue_a = next(
            raw for raw in self.raws
            if raw.title == "Prologue" and raw.parent == "Book A"
        )
        self.assertIn("1) Setup:", prologue_a.synopsis)
        self.assertIn("2) Payoff:", prologue_a.synopsis)
        self.assertNotIn("Hierarchy", prologue_a.metadata)  # junk header dropped

    def test_markdown_bodies_become_rich_text(self):
        clinic = next(raw for raw in self.raws if raw.title == "Clinic")
        html = markdown_to_html(clinic.body)
        self.assertIn("<i>quiet</i>", html)
        self.assertIn("<b>weight</b>", html)
        self.assertNotIn("*", html.replace("<i>", "").replace("</i>", ""))

        title_page = next(raw for raw in self.raws if raw.title == "B-clinic")
        self.assertIn("OTHER Prologue", markdown_to_html(title_page.body))

    def test_heading_line_renders_bold(self):
        chapter_b = next(
            raw for raw in self.raws
            if raw.title == "Prologue" and raw.parent == "Book B"
        )
        html = markdown_to_html(chapter_b.body)
        self.assertIn("<b>Title Page</b>", html)
        self.assertIn("<p>Other Book</p>", html)


SHELF_DUMP = """\
===DOCUMENT===

Type: Chapter

ID: 10

Position: 1

ParentPosition: 0

Parent: Manuscript

Title: Novelette A

PoV: Maya

Location: 

Date: 

Quote: 

Source: 

Status: No Status

Label: 

Keywords: 

Synopsis: 

===TEXT===

A shell of prose.

===DOCUMENT===

Type: Scene

ID: 11

Position: 1

ParentPosition: 1

Parent: Novelette A

Title: A-beat

PoV: 

Location: 

Date: 

Quote: 

Source: 

Status: No Status

Label: 

Keywords: 

Synopsis: 

===TEXT===

Scene under the work.

===DOCUMENT===

Type: Chapter

ID: 12

Position: 2

ParentPosition: 0

Parent: Manuscript

Title: Novelette B

PoV: 

Location: 

Date: 

Quote: 

Source: 

Status: No Status

Label: 

Keywords: 

Synopsis: 

===TEXT===

Second work.
"""


class ShelfTests(unittest.TestCase):
    """A generic all-chapters container is a shelf of works, not a book."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "shelf.md"
        self.path.write_text(SHELF_DUMP, encoding="utf-8")
        self.raws = parse_dump(self.path)
        self.project = Project.create(
            Path(self.temporary.name) / "Corpus", "Corpus"
        )

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def test_shelf_children_become_the_books(self):
        self.assertEqual(dump_books(self.raws), ["Novelette A", "Novelette B"])

    def test_single_shelf_becomes_a_wrapper_holding_every_book(self):
        wrapper_id, folders = import_all_books(self.project, self.raws)

        wrapper = next(d for d in self.project.documents() if d.id == wrapper_id)
        self.assertEqual(wrapper.title, "Manuscript")
        self.assertEqual(wrapper.kind, "folder")
        self.assertIsNone(wrapper.parent_id)
        book_titles = [d.title for d in self.project.documents()
                       if d.parent_id == wrapper_id]
        self.assertEqual(book_titles, ["Novelette A", "Novelette B"])

    def test_promoted_work_keeps_its_chapter_and_its_scenes(self):
        _wrapper, folders = import_all_books(self.project, self.raws)

        folder_a = next(d for d in self.project.documents()
                        if d.id == folders[0])
        chapter = next(d for d in self.project.documents()
                       if d.parent_id == folder_a.id)
        self.assertEqual(chapter.title, "Novelette A")
        self.assertEqual(chapter.kind, "chapter")
        self.assertIn("shell of prose", self.project.read_content(chapter.id))
        scenes = [d for d in self.project.documents() if d.parent_id == chapter.id]
        self.assertEqual([s.title for s in scenes], ["A-beat"])

        folder_b = next(d for d in self.project.documents()
                        if d.id == folders[1])
        chapter_b = next(d for d in self.project.documents()
                         if d.parent_id == folder_b.id)
        self.assertEqual(chapter_b.title, "Novelette B")
        self.assertEqual(chapter_b.parent_id, folder_b.id)


class ImportBookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "dump.md"
        self.path.write_text(SYNTHETIC_DUMP, encoding="utf-8")
        self.raws = parse_dump(self.path)
        self.project = Project.create(
            Path(self.temporary.name) / "Corpus", "Corpus"
        )

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def _children_of(self, title, parent_id):
        return [
            doc for doc in self.project.documents()
            if doc.parent_id == parent_id and doc.title == title
        ]

    def test_book_a_imports_chapters_scenes_and_metadata(self):
        folder_id = import_book(self.project, self.raws, "Book A")

        folder = next(d for d in self.project.documents() if d.id == folder_id)
        self.assertEqual(folder.kind, "folder")
        chapters = self._children_of("Prologue", folder_id)
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0].kind, "chapter")
        scene_ids = [doc.id for doc in self.project.documents()
                     if doc.parent_id == chapters[0].id]
        self.assertEqual(len(scene_ids), 1)
        self.assertEqual(self.project.metadata(scene_ids[0])["Location"], "Delhi")
        self.assertGreater(
            next(d for d in self.project.documents() if d.id == scene_ids[0]).word_count, 0
        )
        # Book A's own second child, the Extra scene
        self.assertEqual(len(self._children_of("Extra", folder_id)), 1)

    def test_duplicate_chapter_titles_resolve_per_book(self):
        folder_a = import_book(self.project, self.raws, "Book A")
        folder_b = import_book(self.project, self.raws, "Book B")

        chapter_a = self._children_of("Prologue", folder_a)[0]
        chapter_b = self._children_of("Prologue", folder_b)[0]
        scenes_a = [d for d in self.project.documents() if d.parent_id == chapter_a.id]
        scenes_b = [d for d in self.project.documents() if d.parent_id == chapter_b.id]
        self.assertEqual([d.title for d in scenes_a], ["Clinic"])
        self.assertEqual([d.title for d in scenes_b], ["B-clinic"])

    def test_document_count_matches_the_dump(self):
        import_book(self.project, self.raws, "Book A")
        import_book(self.project, self.raws, "Book B")
        # 1 seeded Draft folder + 2 book folders + every block once (5)
        self.assertEqual(len(self.project.documents()), 1 + 2 + 5)

    def test_import_all_books_creates_one_folder_per_book(self):
        wrapper_id, folders = import_all_books(self.project, self.raws)

        self.assertIsNone(wrapper_id)          # no shelf in this dump
        self.assertEqual(len(folders), 2)
        titles = [d.title for d in self.project.documents()
                  if d.id in set(folders)]
        self.assertEqual(titles, ["Book A", "Book B"])


class FullCorpusTests(unittest.TestCase):
    """The author's real dump, when present — the load fixture role."""

    DUMP = Path("/home/vidyut/Writing/Scrivener/abrahamhas-strays-world.md")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(
            Path(self.temporary.name) / "Corpus", "Corpus"
        )

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    @unittest.skipUnless(DUMP.exists(), "author's dump not present")
    def test_full_corpus_imports_every_book_with_no_header_leaks(self):
        raws = parse_dump(self.DUMP)
        self.assertEqual(len(raws), 326)
        self.assertEqual(
            dump_books(raws),
            [
                "Marginally Human", "Terminally-Immortal",
                # Manuscript is a shelf: its 8 works are the books
                "Perfectly Flawed", "Prequel", "The Copper Mine",
                "SHADEs of Sapience", "Hakim's story",
                "Abrahamha's Ultimatum", "Antyeshti", "Short stories",
            ],
        )

        wrapper_id, folders = import_all_books(self.project, raws)
        self.assertEqual(len(folders), 10)
        wrapper = next(d for d in self.project.documents() if d.id == wrapper_id)
        self.assertEqual(wrapper.title, "Manuscript")
        books_inside = [d.title for d in self.project.documents()
                        if d.parent_id == wrapper_id]
        self.assertEqual(
            books_inside,
            [
                "Marginally Human", "Terminally-Immortal",
                "Perfectly Flawed", "Prequel", "The Copper Mine",
                "SHADEs of Sapience", "Hakim's story",
                "Abrahamha's Ultimatum", "Antyeshti", "Short stories",
            ],
        )
        documents = self.project.documents()
        # 1 seeded Draft + the Manuscript wrapper + 10 books + every block
        self.assertEqual(len(documents), 1 + 1 + 10 + 326)
        prose = [doc for doc in documents if doc.kind == "scene" and doc.word_count > 50]
        self.assertGreater(len(prose), 100)   # real prose actually landed
        # The dump's meta fields are headers, never prose: nothing from
        # them may survive inside any stored document.
        for doc in documents:
            content = self.project.read_content(doc.id)
            for header_junk in ("ParentPosition", "===DOCUMENT===", "\nType: "):
                self.assertNotIn(header_junk, content, doc.title)


if __name__ == "__main__":
    unittest.main()
