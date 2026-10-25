"""The Templates area always exists, and always holds a template.

The author's rule: "the Templates folder should show/exist in every condition
Lekhak is open and it will always contain at least one template", so nobody has
to dig through code or the filesystem to find out what a template is.
"""

import tempfile
import unittest
from pathlib import Path

from lekhak.project import Project


class TemplatesAreaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(Path(self.temporary.name) / "Novel",
                                      "Novel")

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def _areas(self):
        return [document for document in self.project.documents()
                if document.is_templates_root]

    def test_a_new_project_gains_the_area(self):
        created = self.project.ensure_templates_area()
        self.assertIsNotNone(created)
        areas = self._areas()
        self.assertEqual(len(areas), 1)
        self.assertEqual(areas[0].title, "Templates")
        self.assertIsNone(areas[0].parent_id)      # top level, so it lifts

    def test_it_brings_a_template_with_it(self):
        self.project.ensure_templates_area()
        set_dir = self.project.root / "templates" / "Default"
        self.assertTrue(set_dir.is_dir())
        for slot in ("chapter.html", "scene.html", "project_header.html",
                     "chapter.txt", "README.txt", "documents/bare.html"):
            self.assertTrue((set_dir / slot).exists(), slot)

    def test_it_runs_once(self):
        self.project.ensure_templates_area()
        self.assertIsNone(self.project.ensure_templates_area())
        self.assertEqual(len(self._areas()), 1)

    def test_a_deleted_area_does_not_grow_back(self):
        """A writer who removes the area meant it — no resurrection on open."""
        created = self.project.ensure_templates_area()
        self.project.delete_document(created)
        self.assertIsNone(self.project.ensure_templates_area())
        self.assertEqual(self._areas(), [])

    def test_an_existing_area_is_left_alone(self):
        existing = self.project.add_document("My templates", None, "folder")
        self.project.set_templates_root(existing.id, True)
        self.assertIsNone(self.project.ensure_templates_area())
        self.assertEqual([area.id for area in self._areas()], [existing.id])

    def test_the_area_is_not_manuscript(self):
        """Excluded from exports and counts by the rule that already governs
        template subtrees (2.1) — the flag, not a special case."""
        self.project.ensure_templates_area()
        area = self._areas()[0]
        page = self.project.add_document("Front matter", area.id, "scene")
        self.project.write_content(page.id, "<p>To my mother.</p>")
        destination = Path(self.temporary.name) / "book.txt"
        self.project.export_text(destination)
        self.assertNotIn("To my mother", destination.read_text(encoding="utf-8"))

    def test_a_read_only_project_still_opens(self):
        """A template on disk is a convenience, never a gate."""
        self.project.set_setting("templates_area_created", "0")
        self.project.root.chmod(0o500)
        try:
            self.project.ensure_templates_area()      # must not raise
        finally:
            self.project.root.chmod(0o700)


if __name__ == "__main__":
    unittest.main()
