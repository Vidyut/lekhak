"""2.3, next slice: yWriter 7 (.yw7) project import — parsing and
placement, against a synthetic project in the documented format.
"""

import tempfile
import unittest
from pathlib import Path

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lekhak.project import Project  # noqa: E402
from lekhak.ywriter import import_yw7, parse_yw7  # noqa: E402


def yw7_xml(*, utf_decl: str = 'encoding="utf-8"') -> str:
    """A minimal but shape-faithful yWriter 7 project file.

    Two normal chapters (one empty), a Notes chapter, an Unused
    chapter, an Unused scene, and a scene referenced out of document
    order to prove the ScID list rules.
    """
    return f'''<?xml version="1.0" {utf_decl}?>
<YWRITER7>
  <PROJECT>
    <Title>Solo Voyage</Title>
    <Desc>A test novel.</Desc>
  </PROJECT>
  <SCENES>
    <SCENE>
      <ID>sc1</ID>
      <Title>Cold Open</Title>
      <Desc>The ice cracks.</Desc>
      <SceneContent>&lt;p&gt;Ice &lt;i&gt;everywhere&lt;/i&gt;.&lt;/p&gt;</SceneContent>
    </SCENE>
    <SCENE>
      <ID>sc2</ID>
      <Title>Second</Title>
      <SceneContent>&lt;p&gt;The radio answers.&lt;/p&gt;</SceneContent>
    </SCENE>
    <SCENE>
      <ID>sc9</ID>
      <Title>Unused Scene</Title>
      <Unused>-1</Unused>
      <SceneContent>&lt;p&gt;Cut material.&lt;/p&gt;</SceneContent>
    </SCENE>
  </SCENES>
  <CHAPTERS>
    <CHAPTER>
      <ID>ch1</ID>
      <Title>The War</Title>
      <Type>0</Type>
      <Scenes>
        <ScID>sc2</ScID>
        <ScID>sc1</ScID>
      </Scenes>
    </CHAPTER>
    <CHAPTER>
      <ID>ch2</ID>
      <Title>Empty Chapter</Title>
      <Type>0</Type>
      <Scenes>
        <ScID>sc9</ScID>
      </Scenes>
    </CHAPTER>
    <CHAPTER>
      <ID>ch3</ID>
      <Title>Notes Chapter</Title>
      <Type>1</Type>
      <ChapterType>1</ChapterType>
      <Unused>-1</Unused>
      <Scenes/>
    </CHAPTER>
    <CHAPTER>
      <ID>ch4</ID>
      <Title>Todo Chapter</Title>
      <Type>1</Type>
      <ChapterType>2</ChapterType>
      <Unused>-1</Unused>
      <Scenes/>
    </CHAPTER>
    <CHAPTER>
      <ID>ch5</ID>
      <Title>Normal Type Zero</Title>
      <Type>0</Type>
      <Scenes>
        <ScID>sc1</ScID>
      </Scenes>
    </CHAPTER>
  </CHAPTERS>
</YWRITER7>
'''


class ParseYw7Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.file = Path(self.temporary.name) / "solo.yw7"
        self.file.write_text(yw7_xml(), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_normal_chapters_and_scenes_in_order(self):
        parsed = parse_yw7(self.file)

        self.assertEqual(parsed.title, "Solo Voyage")
        self.assertEqual([c.title for c in parsed.chapters],
                         ["The War", "Empty Chapter", "Normal Type Zero"])

    def test_scene_order_follows_the_scid_references(self):
        parsed = parse_yw7(self.file)

        self.assertEqual([s.title for s in parsed.chapters[0].scenes],
                         ["Second", "Cold Open"])

    def test_notes_todo_and_unused_are_skipped(self):
        parsed = parse_yw7(self.file)

        titles = {c.title for c in parsed.chapters}
        self.assertNotIn("Notes Chapter", titles)
        self.assertNotIn("Todo Chapter", titles)
        self.assertNotIn("Unused Scene",
                         {s.title for c in parsed.chapters for s in c.scenes})

    def test_empty_normal_chapter_survives(self):
        parsed = parse_yw7(self.file)

        self.assertEqual(parsed.chapters[1].scenes, [])

    def test_content_and_synopsis_come_through(self):
        parsed = parse_yw7(self.file)

        scene = next(s for c in parsed.chapters for s in c.scenes
                     if s.title == "Cold Open")
        self.assertIn("<i>everywhere</i>", scene.content)
        self.assertEqual(scene.synopsis, "The ice cracks.")

    def test_utf16_file_parses(self):
        self.file.write_text(yw7_xml(utf_decl='encoding="utf-16"'),
                             encoding="utf-16")

        self.assertEqual(parse_yw7(self.file).title, "Solo Voyage")


class ImportYw7Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.file = self.root / "solo.yw7"
        self.file.write_text(yw7_xml(), encoding="utf-8")
        self.project = Project.create(self.root / "Novel", "Novel")

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def _by_title(self, title, kind=None):
        return next((d for d in self.project.documents()
                     if d.title == title
                     and (kind is None or d.kind == kind)), None)

    def test_structure_lands_under_the_project_title(self):
        folder_id = import_yw7(self.project, self.file)

        folder = self._by_title("Solo Voyage")
        self.assertEqual(folder.id, folder_id)
        self.assertEqual(folder.kind, "folder")
        chapter = self._by_title("The War")
        self.assertEqual(chapter.parent_id, folder_id)
        scene = self._by_title("Second")
        self.assertEqual(scene.parent_id, chapter.id)

    def test_scene_content_is_stored(self):
        import_yw7(self.project, self.file)

        scene = self._by_title("Cold Open", kind="scene")
        content = self.project.read_content(scene.id)
        self.assertIn("<p>", content)
        self.assertIn("everywhere", content)

    def test_synopsis_metadata_is_set(self):
        import_yw7(self.project, self.file)

        scene = self._by_title("Cold Open", kind="scene")
        entry = self.project.metadata_entries(scene.id).get("synopsis")
        self.assertIsNotNone(entry)
        self.assertEqual(entry[0], "The ice cracks.")

    def test_title_override(self):
        import_yw7(self.project, self.file, title="Renamed")

        self.assertIsNotNone(self._by_title("Renamed"))
        self.assertIsNone(self._by_title("Solo Voyage"))


if __name__ == "__main__":
    unittest.main()
