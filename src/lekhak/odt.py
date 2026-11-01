"""ODT → DOCX for import — the same UNO path PDF export drives (1.6).

The ODT itself is never parsed here: ``uno_odt.py`` loads it over a
socket and saves a DOCX where the caller asks, and python-docx reads
that (``importer.import_docx``) — ODF outline levels ride across as
Word heading styles, so one heading map serves both formats.

The probes and the kill-the-process-group seam belong to pdf.py and are
imported rather than copied: one LibreOffice path, one set of failure
messages about missing installs, one rule about not leaving soffice
running on top of a deleted profile directory.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import pdf
from .pdf import (
    ConversionError, _find_uno_interpreter, _run_uno, find_converter,
)

UNO_SCRIPT = Path(__file__).with_name("uno_odt.py")


def _converter_missing_message() -> str:
    message = (
        "ODT import needs LibreOffice on PATH. Install it "
        "(for example: sudo apt install libreoffice-writer) and import again."
    )
    if pdf._converter_errors:
        message += ("\n\nDetails from the failed probe:\n"
                    + "\n".join(pdf._converter_errors))
    return message


def _uno_missing_message() -> str:
    message = (
        "LibreOffice is installed, but no Python could load its scripting "
        "bindings (the 'uno' module), which ODT import drives. Install them "
        "(on Debian/Ubuntu: sudo apt install python3-uno) and import again."
    )
    if pdf._uno_errors:
        message += "\n\nDetails from the failed probe:\n" + "\n".join(pdf._uno_errors)
    return message


def convert(odt: Path, destination: Path) -> None:
    """Convert an ODT to a DOCX at ``destination``.

    Scratch and profile live beside the destination so the final move is
    an ``os.replace`` on the writer's own filesystem, exactly like the
    PDF route — and so LibreOffice's private profile never collides with
    a LibreOffice the writer already has open.
    """
    command = find_converter()
    if command is None:
        raise ConversionError(_converter_missing_message())
    interpreter = _find_uno_interpreter()
    if interpreter is None:
        raise ConversionError(_uno_missing_message())
    workdir = Path(tempfile.mkdtemp(
        prefix=".lekhak-odt-", dir=str(destination.parent)))
    try:
        produced = workdir / (odt.stem + ".docx")
        try:
            result = _run_uno(interpreter, odt, produced, command[0],
                              workdir, script=UNO_SCRIPT)
        except subprocess.TimeoutExpired as error:
            raise ConversionError(
                f"LibreOffice did not finish within {pdf.CONVERT_TIMEOUT} "
                "seconds; gave up."
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
