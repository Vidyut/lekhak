"""PDF export — a thin wrapper over the DOCX, as 1.6's decision recorded.

The DOCX stays the exact artifact and the single renderer: instead of
growing a second layout engine inside Lekhak, this module hands the
compiled DOCX to the writer's own LibreOffice and moves the result into
place atomically. The handoff goes through LibreOffice's UNO API (a
worker subprocess in ``uno_pdf.py``) rather than a bare
``--convert-to``: the CLI loader never refreshes fields, so the 1.7 TOC
would ship as its cached placeholder, while a UNO ``index.update()``
puts real page numbers in the contents page. Nothing here parses or
understands PDF — we shell out, and when the converter or its scripting
bindings are missing the message says how to fix each.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from .project import Project

# Candidate commands, in order: the deb/snap/tarball all install one of
# these names on PATH.
CANDIDATES = ("libreoffice", "soffice")
# Interpreters probed for the `uno` module: the app's own interpreter
# first (venvs created with system site-packages carry it), then the
# system python3 that LibreOffice's bindings were installed for.
UNO_CANDIDATES = (sys.executable, "python3")
PROBE_TIMEOUT = 10        # --version / import uno are both quick
CONVERT_TIMEOUT = 300     # a full manuscript can take a while
UNO_SCRIPT = Path(__file__).with_name("uno_pdf.py")

# Why the last probes came up empty, kept apart so a converter message
# never mixes in interpreter detail (and vice versa).
_converter_errors: list[str] = []
_uno_errors: list[str] = []


class ConversionError(RuntimeError):
    """An impossible or failed DOCX -> PDF step, with a message meant
    for a writer rather than a log file."""


def find_converter() -> list[str] | None:
    """The first LibreOffice on PATH that actually runs.

    ``which`` alone lies here: a broken snap shim sat on PATH on the
    author's machine and died before doing any work, so every candidate
    is asked to speak first. PATH is stable within a session, but the
    probe is one ``--version`` per export — re-probing beats caching a
    miss made before the writer installed anything.
    """
    _converter_errors.clear()
    for name in CANDIDATES:
        path = shutil.which(name)
        if not path:
            continue
        try:
            result = subprocess.run(
                [path, "--version"], capture_output=True, text=True,
                timeout=PROBE_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            _converter_errors.append(f"{name}: {error}")
            continue
        if result.returncode == 0:
            return [path]
        detail = (result.stderr or result.stdout).strip()
        _converter_errors.append(
            f"{name}: {detail[:300] or 'exit ' + str(result.returncode)}")
    return None


def _find_uno_interpreter() -> str | None:
    """The first interpreter that can ``import uno``.

    The worker runs out-of-process precisely because the app's own
    interpreter usually cannot (venvs), so both candidates are probed
    cheaply with ``-c`` before anything is launched.
    """
    _uno_errors.clear()
    for name in UNO_CANDIDATES:
        path = name if os.path.isabs(name) else shutil.which(name)
        if not path:
            _uno_errors.append(f"{name}: not found")
            continue
        try:
            result = subprocess.run(
                [path, "-c", "import uno"], capture_output=True, text=True,
                timeout=PROBE_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            _uno_errors.append(f"{path}: {error}")
            continue
        if result.returncode == 0:
            return path
        _uno_errors.append(f"{path}: cannot import the 'uno' module")
    return None


def _converter_missing_message() -> str:
    message = (
        "PDF export needs LibreOffice on PATH. Install it "
        "(for example: sudo apt install libreoffice-writer) and export again."
    )
    if _converter_errors:
        message += ("\n\nDetails from the failed probe:\n"
                    + "\n".join(_converter_errors))
    return message


def _uno_missing_message() -> str:
    message = (
        "LibreOffice is installed, but no Python could load its scripting "
        "bindings (the 'uno' module), which PDF export drives. Install them "
        "(on Debian/Ubuntu: sudo apt install python3-uno) and export again."
    )
    if _uno_errors:
        message += "\n\nDetails from the failed probe:\n" + "\n".join(_uno_errors)
    return message


def _run_uno(interpreter: str, docx: Path, pdf_path: Path,
             soffice: str, workdir: Path,
             script: Path = UNO_SCRIPT) -> subprocess.CompletedProcess:
    """The seam tests stand on: everything past here is LibreOffice.

    The worker runs as its own session leader because it starts LibreOffice
    as a child. On a timeout, killing just the worker would leave soffice
    alive — and convert() would then delete the profile directory out from
    under the survivor, so the *next* export fails for reasons nothing in
    its own run explains. Killing the whole process group takes both.

    ``script`` defaults to the PDF worker; ODT import drives the same
    seam with its own worker (``uno_odt.py``), so the kill-on-timeout
    rule holds for both without being written twice.
    """
    process = subprocess.Popen(
        [interpreter, str(script), str(docx), str(pdf_path),
         soffice, str(workdir)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True,      # so the group can be killed as one
    )
    try:
        stdout, stderr = process.communicate(timeout=CONVERT_TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)   # pid is the pgid here
        except ProcessLookupError:
            pass                     # already gone; still drain the pipes
        process.communicate()
        raise
    return subprocess.CompletedProcess(process.args, process.returncode,
                                       stdout, stderr)


def convert(docx: Path, destination: Path) -> None:
    """Convert a DOCX to a PDF at ``destination``.

    The scratch outdir lives beside the destination rather than in
    ``/tmp``: the final move is an ``os.replace``, which only works
    within one filesystem, and exports land on the writer's disk. The
    worker keeps LibreOffice's private profile inside that same scratch,
    so a run never talks to (or deadlocks on) a LibreOffice the writer
    already has open.
    """
    command = find_converter()
    if command is None:
        raise ConversionError(_converter_missing_message())
    interpreter = _find_uno_interpreter()
    if interpreter is None:
        raise ConversionError(_uno_missing_message())
    workdir = Path(tempfile.mkdtemp(
        prefix=".lekhak-pdf-", dir=str(destination.parent)))
    try:
        produced = workdir / (docx.stem + ".pdf")
        try:
            result = _run_uno(interpreter, docx, produced, command[0], workdir)
        except subprocess.TimeoutExpired as error:
            raise ConversionError(
                f"LibreOffice did not finish within {CONVERT_TIMEOUT} seconds; "
                "gave up."
            ) from error
        if result.returncode != 0 or not produced.is_file():
            detail = (result.stderr or result.stdout).strip()[-1000:]
            raise ConversionError(
                "LibreOffice failed to convert the document:\n"
                + (detail or f"exit code {result.returncode}")
            )
        os.replace(produced, destination)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def export_pdf(project: Project, destination: Path,
               selected_ids: set[str] | None = None,
               templates=None) -> None:
    """Export as PDF by compiling a scratch DOCX and converting it.

    The orchestration lives here rather than in project.py because it
    manages temporary files and a subprocess; the project layer stays
    free of process concerns and keeps writing DOCX.
    """
    workdir = Path(tempfile.mkdtemp(
        prefix=".lekhak-docx-", dir=str(destination.parent)))
    try:
        scratch = workdir / "manuscript.docx"
        project.export_docx(scratch, selected_ids, templates)
        convert(scratch, destination)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
