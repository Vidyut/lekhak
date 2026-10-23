"""The protected Type role (docs/MODEL.md): type_of, default_type,
creation seeding, and the dropdown's project-scoped memory."""

import tempfile
import unittest
from pathlib import Path

from lekhak.project import Project


class TypeOfTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temporary.name) / "Novel")
        self.draft = self.project.documents()[0]

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def test_defaults_match_the_physical_kind(self):
        chapter = self.project.add_document("Ch", self.draft.id, "chapter")
        scene = self.project.add_document("Sc", chapter.id, "scene")
        note = self.project.add_document("Nt", chapter.id, "note")
        self.assertEqual(self.project.default_type(self.draft), "Folder")
        self.assertEqual(self.project.default_type(chapter), "Chapter")
        self.assertEqual(self.project.default_type(scene), "Scene")
        self.assertEqual(self.project.default_type(note), "Note")

    def test_book_settings_promote_a_folder_to_book(self):
        self.project.set_book_settings(self.draft.id, {"template": "x"})
        self.assertEqual(self.project.default_type(self.draft), "Book")
        self.assertEqual(self.project.type_of(self.draft), "Book")

    def test_page_setup_alone_promotes_a_folder_to_book(self):
        self.project.set_page_setup(self.draft.id, {
            "width": 6.0, "height": 9.0, "top": 0.5, "bottom": 0.5,
            "inside": 0.75, "outside": 0.5,
        })
        self.assertEqual(self.project.default_type(self.draft), "Book")
        self.assertEqual(self.project.type_of(self.draft), "Book")

    def test_stored_type_wins_over_the_default(self):
        chapter = self.project.add_document("Ch", self.draft.id, "chapter")
        self.project.set_metadata(chapter.id, {"Type": "Short story"})
        self.assertEqual(self.project.type_of(chapter), "Short story")

    def test_blank_stored_type_falls_back(self):
        chapter = self.project.add_document("Ch", self.draft.id, "chapter")
        self.project.set_metadata(chapter.id, {"Type": "   "})
        self.assertEqual(self.project.type_of(chapter), "Chapter")

    def test_defaults_are_not_seeded_into_storage(self):
        # A stored default would shadow a later heal (book settings
        # promoting the folder), so creation writes no Type at all.
        scene = self.project.add_document("Sc", self.draft.id, "scene")
        self.assertNotIn("Type", self.project.metadata(scene.id))
        self.assertEqual(self.project.type_of(scene), "Scene")

    def test_type_values_lists_what_the_project_uses(self):
        chapter = self.project.add_document("Ch", self.draft.id, "chapter")
        self.project.set_metadata(chapter.id, {"Type": "Weird"})
        other = self.project.add_document("Sc", chapter.id, "scene")
        self.project.set_metadata(other.id, {"Type": "Weird"})
        # Only explicitly set values count; derived defaults are not
        # stored, so they never pad the dropdown's project list.
        self.assertEqual(self.project.type_values(), ["Weird"])


if __name__ == "__main__":
    unittest.main()
