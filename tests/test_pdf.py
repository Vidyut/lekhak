"""1.6's PDF route: a thin wrapper over the DOCX.

Everything runs against a stub LibreOffice — a shell script that answers
--version and writes a fake PDF — so the suite never needs a real
converter; the live conversion is a manual smoke. The last test checks
the window actually dispatches Export PDF… through this module.
"""

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from lekhak import pdf  # noqa: E402
from lekhak.app import ExportOptionsDialog, MainWindow  # noqa: E402
from lekhak.project import Project  # noqa: E402

_application = QApplication.instance() or QApplication([])
_application.setOrganizationName("Lekhak")
_application.setApplicationName("Lekhak")
_settings_dir = tempfile.mkdtemp(prefix="lekhak-pdf-settings-")
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)

# The stub's whole contract: --version speaks, anything else writes
# <input-stem>.pdf into the --outdir. $LEKHAK_STUB_FAIL turns it into a
# failing converter for the error-path tests.
_STUB = """#!/bin/bash
for arg in "$@"; do
    if [ "$arg" = "--version" ]; then
        echo "LibreOffice 99.9.9"
        exit 0
    fi
done
if [ -n "$LEKHAK_STUB_FAIL" ]; then
    echo "stub: refusing to convert" >&2
    exit 1
fi
outdir=""
previous=""
for arg in "$@"; do
    if [ "$previous" = "--outdir" ]; then outdir="$arg"; fi
    previous="$arg"
done
input="${@: -1}"
stem="$(basename "$input")"
stem="${stem%.*}"
mkdir -p "$outdir"
printf '%%PDF-1.4 stub' > "$outdir/$stem.pdf"
"""

_BROKEN_STUB = """#!/bin/bash
if [ "$1" = "--version" ]; then
    echo "snap-confine is packaged without necessary permissions" >&2
    exit 1
fi
exit 1
"""


def _make_stub(directory: Path, script: str) -> str:
    path = directory / "libreoffice"
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def _path_env(directory: Path) -> str:
    # The stub itself needs coreutils; PATH tests prepend, not replace.
    return f"{directory}{os.pathsep}/usr/bin:/bin"


class FakeProject:
    """export_docx is the only method export_pdf touches."""

    def __init__(self):
        self.calls = []

    def export_docx(self, destination, selected_ids, templates):
        self.calls.append((destination, selected_ids, templates))
        destination.write_bytes(b"docx placeholder")


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_find_converter_returns_the_working_candidate(self):
        _make_stub(self.root, _STUB)

        with patch.dict(os.environ, {"PATH": _path_env(self.root)}):
            command = pdf.find_converter()

        self.assertIsNotNone(command)
        self.assertTrue(command[0].endswith("libreoffice"))

    def test_find_converter_is_none_without_a_converter(self):
        # PATH points nowhere in particular (not even /usr/bin): on a
        # machine that does have LibreOffice this must still be None.
        empty = self.root / "empty"
        empty.mkdir()

        with patch.dict(os.environ, {"PATH": str(empty)}):
            command = pdf.find_converter()

        self.assertIsNone(command)

    def test_broken_converter_is_probed_and_explained(self):
        _make_stub(self.root, _BROKEN_STUB)

        # Stub alone on PATH: no healthy candidate can rescue the probe.
        with patch.dict(os.environ, {"PATH": str(self.root)}):
            self.assertIsNone(pdf.find_converter())
            destination = self.root / "book.pdf"
            with self.assertRaises(pdf.ConversionError) as caught:
                pdf.convert(self.root / "missing.docx", destination)

        message = str(caught.exception)
        self.assertIn("sudo apt install libreoffice-writer", message)
        self.assertIn("snap-confine", message)   # the real probe detail

    def test_convert_moves_the_pdf_into_place_and_cleans_up(self):
        _make_stub(self.root, _STUB)
        source = self.root / "book.docx"
        source.write_bytes(b"docx")
        destination = self.root / "out" / "final.pdf"
        destination.parent.mkdir()

        with patch.dict(os.environ, {"PATH": _path_env(self.root)}):
            pdf.convert(source, destination)

        self.assertEqual(destination.read_bytes(), b"%PDF-1.4 stub")
        # No .lekhak-pdf-* scratch directory left beside it.
        leftovers = [p.name for p in destination.parent.iterdir()
                     if p.name.startswith(".lekhak-")]
        self.assertEqual(leftovers, [])

    def test_convert_reports_the_converters_stderr(self):
        _make_stub(self.root, _STUB)
        source = self.root / "book.docx"
        source.write_bytes(b"docx")

        with patch.dict(os.environ, {"PATH": _path_env(self.root)}), \
                patch.dict(os.environ, {"LEKHAK_STUB_FAIL": "1"}):
            with self.assertRaises(pdf.ConversionError) as caught:
                pdf.convert(source, self.root / "book.pdf")

        self.assertIn("stub: refusing to convert", str(caught.exception))

    def test_export_pdf_compiles_a_scratch_docx_then_converts(self):
        _make_stub(self.root, _STUB)
        destination = self.root / "novel.pdf"
        project = FakeProject()

        with patch.dict(os.environ, {"PATH": _path_env(self.root)}):
            pdf.export_pdf(project, destination, {"id-1"}, "templates")

        self.assertEqual(destination.read_bytes(), b"%PDF-1.4 stub")
        self.assertEqual(len(project.calls), 1)
        scratch, ids, templates = project.calls[0]
        self.assertEqual(ids, {"id-1"})
        self.assertEqual(templates, "templates")
        self.assertFalse(scratch.exists())     # temp docx cleaned up
        leftovers = [p.name for p in self.root.iterdir()
                     if p.name.startswith(".lekhak-")]
        self.assertEqual(leftovers, [])


class ExportPdfMenuTests(unittest.TestCase):
    """The window's Export PDF… reaches pdf.export_pdf with the scope
    and template set the shared dialog produced."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Project.create(
            Path(self.temporary.name) / "Novel", "Novel"
        )
        self.window = MainWindow()
        self.window._switch_project(self.project)

    def tearDown(self):
        self.window.project = None
        self.project.close()
        self.temporary.cleanup()

    def test_export_dispatches_through_the_pdf_wrapper(self):
        destination = Path(self.temporary.name) / "book.pdf"
        with patch.object(ExportOptionsDialog, "exec",
                          return_value=QDialog.Accepted), \
                patch("lekhak.app.QFileDialog.getSaveFileName",
                      return_value=(str(destination), "")), \
                patch("lekhak.app.pdf.export_pdf") as export_pdf:
            self.window.export("pdf")

        export_pdf.assert_called_once()
        project, target, _ids, _templates = export_pdf.call_args.args
        self.assertIs(project, self.project)
        self.assertEqual(target, destination)


if __name__ == "__main__":
    unittest.main()
