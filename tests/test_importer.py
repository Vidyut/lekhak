"""2.3 Scrivener dump importer: parser and placement — pure project tests.

The synthetic dump mirrors the author's real multi-document markdown
export: blank-line-separated headers, multi-line Synopsis values,
markdown-ish bodies, and titles that repeat across books.
"""

import tempfile
import unittest
from pathlib import Path

from lekhak.importer import (
    dump_books, import_book, markdown_to_html, parse_dump,
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

Date: 

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
    def test_full_corpus_parses_and_one_book_imports(self):
        raws = parse_dump(self.DUMP)
        self.assertEqual(len(raws), 326)
        self.assertEqual(
            dump_books(raws),
            ["Marginally Human", "Terminally-Immortal", "Manuscript"],
        )

        folder_id = import_book(self.project, raws, "Terminally-Immortal")
        imported = [
            doc for doc in self.project.documents()
            if doc.id == folder_id or self._is_under(doc.id, folder_id)
        ]
        self.assertEqual(len(imported), 109)   # folder + 108 documents
        prose = [doc for doc in imported if doc.kind == "scene" and doc.word_count > 50]
        self.assertGreater(len(prose), 50)     # real prose actually landed

    def _is_under(self, document_id, ancestor_id) -> bool:
        by_id = {doc.id: doc for doc in self.project.documents()}
        current = by_id.get(document_id)
        while current and current.parent_id:
            if current.parent_id == ancestor_id:
                return True
            current = by_id.get(current.parent_id)
        return False


if __name__ == "__main__":
    unittest.main()
