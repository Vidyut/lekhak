"""PDF export — a thin wrapper over the DOCX, as 1.6's decision recorded.

The DOCX stays the exact artifact and the single renderer: instead of
growing a second layout engine inside Lekhak, this module hands the
compiled DOCX to whatever LibreOffice the writer already has (deb, snap
or tarball) and moves the result into place atomically. Nothing here
parses or understands PDF — we shell out, and when the converter is
missing or broken the message says how to fix it.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .project import Project

# Candidate commands, in order: the deb/snap/tarball all install one of
# these names on PATH.
CANDIDATES = ("libreoffice", "soffice")
PROBE_TIMEOUT = 10       # --version is instant on a healthy install
CONVERT_TIMEOUT = 300    # a full manuscript can take a while

# Why the last find_converter() run came up empty, one line per failed
# candidate; folded into the error message so "broken install" and
# "not installed" read differently.
_probe_errors: list[str] = []


class ConversionError(RuntimeError):
    """An impossible or failed DOCX -> PDF step, with a message meant
    for a writer rather than a log file."""


def find_converter() -> list[str] | None:
    """The first LibreOffice on PATH that actually runs.

    ``which`` alone lies here: a broken snap shim sits on PATH on the
    author's machine and dies before doing any work, so every candidate
    is asked to speak first. PATH is stable within a session, but the
    probe is one ``--version`` per export — re-probing beats caching a
    miss made before the writer installed anything.
    """
    _probe_errors.clear()
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
            _probe_errors.append(f"{name}: {error}")
            continue
        if result.returncode == 0:
            return [path]
        detail = (result.stderr or result.stdout).strip()
        _probe_errors.append(f"{name}: {detail[:300] or 'exit ' + str(result.returncode)}")
    return None


def _missing_message() -> str:
    message = (
        "PDF export needs LibreOffice on PATH. Install it "
        "(for example: sudo apt install libreoffice-writer) and export again."
    )
    if _probe_errors:
        message += "\n\nDetails from the failed probe:\n" + "\n".join(_probe_errors)
    return message


def convert(docx: Path, destination: Path) -> None:
    """Convert a DOCX to a PDF at ``destination``.

    The scratch outdir lives beside the destination rather than in
    ``/tmp``: the final move is an ``os.replace``, which only works
    within one filesystem, and exports land on the writer's disk.
    A private LibreOffice profile keeps this run from talking to (or
    deadlocking on) a LibreOffice the writer already has open.
    """
    command = find_converter()
    if command is None:
        raise ConversionError(_missing_message())
    workdir = Path(tempfile.mkdtemp(
        prefix=".lekhak-pdf-", dir=str(destination.parent)))
    try:
        profile = workdir / "profile"
        arguments = command + [
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless", "--norestore",
            "--convert-to", "pdf",
            "--outdir", str(workdir),
            str(docx),
        ]
        try:
            result = subprocess.run(
                arguments, capture_output=True, text=True,
                timeout=CONVERT_TIMEOUT,
            )
        except subprocess.TimeoutExpired as error:
            raise ConversionError(
                f"LibreOffice did not finish within {CONVERT_TIMEOUT} seconds; "
                "gave up."
            ) from error
        produced = workdir / (docx.stem + ".pdf")
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
