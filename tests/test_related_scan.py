"""Related-file mentions must mean something.

A text title matches by meaning; a bare number matches by coincidence, and a
pasted URL is not a reference to this project. Both were being listed as
"mentions" — the author's own binder has chapters named "2", "3", "4", so
every year and every copied link in the prose produced a phantom relation,
and the Mentions panel became a list of chapters that had nothing to do with
the text.
"""

import tempfile
import unittest
from pathlib import Path

from lekhak.project import Project


class MentionScanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temporary.name) / "Novel",
                                      "Novel")
        self.root = self.project.documents()[0]

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def _scene(self, title: str, text: str):
        scene = self.project.add_document(title, self.root.id, "scene")
        self.project.write_content(scene.id, f"<p>{text}</p>")
        return scene

    def _mentions_of(self, document_id):
        mentions, _ = self.project.related_documents(document_id)
        return [document.id for document in mentions]

    def test_a_numeric_title_is_not_a_mention(self):
        body = self._scene("Body", "The 2024 season was long and hard.")
        self._scene("2", "Chapter two.")
        self.assertEqual(self._mentions_of(body.id), [])

    def test_a_pasted_url_is_not_a_mention(self):
        body = self._scene("Body", "Source: https://example.com/2024/2/x")
        self._scene("2", "Chapter two.")
        self.assertEqual(self._mentions_of(body.id), [])

    def test_a_text_title_still_matches_by_meaning(self):
        body = self._scene("Body", "Then Aaxyl left the wada.")
        character = self._scene("Aaxyl", "Notes and history.")
        self.assertIn(character.id, self._mentions_of(body.id))

    def test_a_numeric_title_collects_no_mentions_either(self):
        """The reverse direction: a document *called* "2" must not be listed
        as mentioned by everything containing a year or a link."""
        chapter_two = self._scene("2", "Chapter two.")
        self._scene("Body", "The 2024 season. See https://x.example/2/slash")
        _mentions, mentioned_by = self.project.related_documents(chapter_two.id)
        self.assertEqual(mentioned_by, [])

    def test_whole_word_matching_is_unchanged(self):
        body = self._scene("Body", "Ridnam rode out at dawn.")
        rid = self._scene("Rid", "Notes.")
        self.assertNotIn(rid.id, self._mentions_of(body.id))


if __name__ == "__main__":
    unittest.main()
