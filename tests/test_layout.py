"""The filesystem layout: names, the YAML subset, and the tree round trip.

Order is the thing most worth pinning here. A folder's manifest *is* its
order; nothing sorts children by name, because the author's scene titles run
`1---`, `2---`, … `10---`, which sort as text `1, 10, 2`.
"""

import tempfile
import unittest
from pathlib import Path

from lekhak import layout
from lekhak.layout import Node


class SlugTests(unittest.TestCase):
    def test_titles_from_the_real_binder(self):
        self.assertEqual(layout.slug("3 - Zayn meets Ari"), "3-Zayn-meets-Ari")
        self.assertEqual(layout.slug("1---AxAm's room"), "1-AxAm-s-room")
        self.assertEqual(layout.slug("The daughter of the moon"),
                         "The-daughter-of-the-moon")
        self.assertEqual(layout.slug("3---Tank 5 for Dome 91-110, Wastelands"),
                         "3-Tank-5-for-Dome-91-110-Wastelands")

    def test_no_spaces_ever(self):
        for title in ("Chapter One", "a  b", " lead", "trail ", "  "):
            self.assertNotIn(" ", layout.slug(title))

    def test_illegal_characters_go(self):
        self.assertEqual(layout.slug("A/B\\C:D*E?F"), "A-B-C-D-E-F")
        self.assertEqual(layout.slug("Scene\twith\ttabs"), "Scene-with-tabs")

    def test_letters_in_any_script_survive(self):
        self.assertEqual(layout.slug("Émile's Ångström"), "Émile-s-Ångström")
        self.assertEqual(layout.slug("अंत"), "अंत")

    def test_edges_and_limits(self):
        self.assertEqual(layout.slug(""), "Untitled")
        self.assertEqual(layout.slug("   "), "Untitled")
        self.assertEqual(layout.slug("...draft..."), "draft")
        self.assertEqual(layout.slug("- - -"), "Untitled")
        self.assertEqual(len(layout.slug("x" * 200)), layout.MAX_LENGTH)

    def test_reserved_names_are_avoided(self):
        self.assertEqual(layout.slug("NUL"), "_NUL")
        self.assertEqual(layout.slug("com1"), "_com1")
        self.assertEqual(layout.slug("comic"), "comic")

    def test_collisions_are_suffixed_case_insensitively(self):
        taken = set()
        names = []
        for title in ("Book", "book", "BOOK"):
            name = layout.unique_name(layout.slug(title), taken)
            taken.add(name.casefold())
            names.append(name)
        self.assertEqual(names, ["Book", "book-2", "BOOK-3"])


class FrontmatterTests(unittest.TestCase):
    def test_round_trip_with_nesting_and_types(self):
        values = {
            "title": "Scene: the meeting",
            "id": "abc123",
            "type": "Scene",
            "word_target": 1200,
            "synopsis": "",
            "metadata": {"PoV": "Zayn", "Status": "Draft", "Count": 3},
        }
        block = layout.dump_frontmatter(values)
        parsed, rest = layout.parse_frontmatter(block + "<p>prose</p>")
        self.assertEqual(parsed["title"], "Scene: the meeting")
        self.assertEqual(parsed["word_target"], 1200)
        self.assertEqual(parsed["metadata"], {"PoV": "Zayn", "Status": "Draft",
                                              "Count": 3})
        self.assertEqual(rest, "<p>prose</p>")

    def test_lists_round_trip(self):
        block = layout.dump_frontmatter({"children": ["a.html", "b/", "c.html"]})
        parsed, _rest = layout.parse_frontmatter(block)
        self.assertEqual(parsed["children"], ["a.html", "b/", "c.html"])

    def test_a_file_without_frontmatter_is_all_content(self):
        parsed, rest = layout.parse_frontmatter("<p>just prose</p>")
        self.assertEqual(parsed, {})
        self.assertEqual(rest, "<p>just prose</p>")

    def test_hand_written_frontmatter_is_tolerated(self):
        text = ("---\n"
                "# my own note\n"
                "title: Hand written\n"
                "type: Chapter\n"
                "metadata:\n"
                "  Status: Final\n"
                "---\n"
                "<p>body</p>")
        parsed, rest = layout.parse_frontmatter(text)
        self.assertEqual(parsed["title"], "Hand written")
        self.assertEqual(parsed["metadata"], {"Status": "Final"})
        self.assertEqual(rest, "<p>body</p>")


class TreeRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "Project.lekhak"
        # Deliberately *not* in alphabetical order, so a test can prove that
        # nothing sorts by name: these would sort 1, 10, 2.
        self.scenes = [
            Node(id="id-m", title="2---The monsoon", content="<p>m</p>",
                 type="Scene"),
            Node(id="id-a", title="10---Aaxyl follows", content="<p>a</p>",
                 type="Scene"),
            Node(id="id-z", title="1---Zayn leaves", content="<p>z</p>",
                 type="Scene", metadata={"PoV": "Zayn"}),
        ]
        self.chapter = Node(id="ch-1", title="Chapter One", kind="folder",
                            type="Chapter", content="<p>chapter words</p>",
                            children=self.scenes)
        self.notes = Node(id="note-1", title="Research notes", kind="folder",
                          type="Research")
        self.book = Node(id="book-1", title="Marginally Human", kind="folder",
                         type="Book",
                         children=[self.chapter, self.notes])

    def tearDown(self):
        self.temporary.cleanup()

    def _write(self):
        return layout.write_tree(self.root, [self.book], title="Test")

    def test_write_then_read_back(self):
        stats = self._write()
        self.assertEqual(stats["folders"], 3)      # book, chapter, notes
        self.assertEqual(stats["documents"], 3)
        self.assertEqual(stats["indexes"], 1)      # the chapter has prose

        nodes, project = layout.load_tree(self.root)
        self.assertEqual(project["title"], "Test")
        self.assertEqual(len(nodes), 1)
        book = nodes[0]
        self.assertEqual(book.title, "Marginally Human")
        self.assertEqual(book.type, "Book")
        self.assertEqual(book.id, "book-1")
        self.assertEqual([child.title for child in book.children],
                         ["Chapter One", "Research notes"])

    def test_order_is_preserved_not_alphabetical(self):
        self._write()
        book = layout.load_tree(self.root)[0][0]
        chapter = book.children[0]
        self.assertEqual([scene.title for scene in chapter.children],
                         ["2---The monsoon", "10---Aaxyl follows",
                          "1---Zayn leaves"])
        # …which is emphatically not what sorting the filenames would give.
        names = sorted(layout.slug(scene.title) for scene in self.scenes)
        self.assertNotEqual(
            names,
            [layout.slug(scene.title) for scene in chapter.children])

    def test_a_container_with_prose_keeps_it_as_index_html(self):
        self._write()
        index = (self.root / "Marginally-Human/Chapter-One/index.html")
        self.assertTrue(index.exists())
        chapter = layout.load_tree(self.root)[0][0].children[0]
        self.assertEqual(chapter.content, "<p>chapter words</p>")

    def test_a_container_without_prose_has_no_index(self):
        self._write()
        self.assertFalse((self.root / "Marginally-Human/Research-notes/"
                          "index.html").exists())

    def test_metadata_and_ids_survive(self):
        self._write()
        chapter = layout.load_tree(self.root)[0][0].children[0]
        zayn = [scene for scene in chapter.children
                if scene.title == "1---Zayn leaves"][0]
        self.assertEqual(zayn.metadata, {"PoV": "Zayn"})
        self.assertEqual(zayn.id, "id-z")

    def test_the_manifest_is_the_order(self):
        """Reorder the manifest by hand and the tree follows — proof that
        filenames are not consulted for order."""
        self._write()
        manifest = self.root / "Marginally-Human/Chapter-One/.lekhak/folder.yaml"
        text = manifest.read_text(encoding="utf-8")
        text = text.replace("  - 1-Zayn-leaves.html\n", "")
        text = text.replace("children:\n",
                            "children:\n  - 1-Zayn-leaves.html\n")
        manifest.write_text(text, encoding="utf-8")

        chapter = layout.load_tree(self.root)[0][0].children[0]
        self.assertEqual([scene.title for scene in chapter.children],
                         ["1---Zayn leaves", "2---The monsoon",
                          "10---Aaxyl follows"])

    def test_a_file_added_from_outside_lands_last(self):
        self._write()
        folder = self.root / "Marginally-Human/Chapter-One"
        (folder / "By-hand.html").write_text(
            "---\ntitle: By hand\ntype: Scene\n---\n<p>typed elsewhere</p>",
            encoding="utf-8")

        chapter = layout.load_tree(self.root)[0][0].children[0]
        self.assertEqual(chapter.children[-1].title, "By hand")
        self.assertEqual(chapter.children[-1].content, "<p>typed elsewhere</p>")

    def test_a_renamed_file_keeps_its_identity(self):
        """The id lives in the frontmatter, so a rename by hand loses nothing."""
        self._write()
        folder = self.root / "Marginally-Human/Chapter-One"
        (folder / "1-Zayn-leaves.html").rename(folder / "Renamed-by-hand.html")

        chapter = layout.load_tree(self.root)[0][0].children[0]
        renamed = [scene for scene in chapter.children
                   if scene.title == "1---Zayn leaves"]
        self.assertEqual(len(renamed), 1)
        self.assertEqual(renamed[0].id, "id-z")
        self.assertEqual(renamed[0].metadata, {"PoV": "Zayn"})

    def test_colliding_titles_in_one_folder_get_suffixed(self):
        zayn = [scene for scene in self.scenes
                if scene.title == "1---Zayn leaves"][0]
        twin = Node(id="id-z2", title="1---Zayn leaves", content="<p>again</p>")
        chapter = Node(id="ch-2", title="Chapter", kind="folder",
                       children=[zayn, twin])
        layout.write_tree(self.root, [chapter])
        names = sorted(entry.name for entry in
                       (self.root / "Chapter").iterdir()
                       if entry.suffix == ".html")
        self.assertEqual(names, ["1-Zayn-leaves-2.html", "1-Zayn-leaves.html"])


if __name__ == "__main__":
    unittest.main()
