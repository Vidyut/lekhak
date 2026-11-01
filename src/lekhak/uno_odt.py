"""LibreOffice UNO worker for ODT import — run as a subprocess.

Mirrors ``uno_pdf.py`` (1.6): the ODT is never parsed by Lekhak.
LibreOffice loads it over a socket and saves a DOCX where the caller
asks, and python-docx does the reading — ODF outline levels ride across
as Word heading styles, so one heading map serves both formats.

Two differences from the PDF worker, both about *reading* a manuscript
rather than typesetting one:

- No ``index.update()``: page numbers mean nothing to an importer.
- Content indexes (a table of contents) are removed before saving:
  their cached entries would otherwise arrive as prose — lines of
  "Chapter One .... 3" dumped into the book's opening scene.

Usage: uno_odt.py <in.odt> <out.docx> <soffice> <workdir>
The LibreOffice profile and log live under workdir; the caller owns
that directory (and cleans it up), so hard-killed runs leak nothing.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit(
            "usage: uno_odt.py <in.odt> <out.docx> <soffice> <workdir>")
    try:
        import uno
        from com.sun.star.beans import PropertyValue
    except ImportError as error:
        # The caller probes for uno before getting here; this is the
        # belt for probes that raced the environment.
        raise SystemExit(f"no-uno: {error}")

    document_path = Path(sys.argv[1])
    docx_path = Path(sys.argv[2])
    soffice = sys.argv[3]
    workdir = Path(sys.argv[4])
    profile = workdir / "profile"
    profile.mkdir(parents=True, exist_ok=True)
    log_path = workdir / "soffice.log"

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [soffice,
             f"-env:UserInstallation={profile.as_uri()}",
             "--headless", "--norestore", "--nofirststartwizard",
             "--invisible",
             f"--accept=socket,host=127.0.0.1,port={port};urp;"],
            stdout=log, stderr=subprocess.STDOUT,
        )

    document = None
    desktop = None
    try:
        local_context = uno.getComponentContext()
        resolver = local_context.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", local_context)
        context = None
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                context = resolver.resolve(
                    f"uno:socket,host=127.0.0.1,port={port};urp;"
                    "StarOffice.ComponentContext")
                break
            except Exception:
                if process.poll() is not None:
                    raise SystemExit(
                        "LibreOffice exited before it was ready: "
                        + log_path.read_text(encoding="utf-8")[-1000:])
                time.sleep(0.2)
        if context is None:
            raise SystemExit(
                "could not reach LibreOffice over the socket within 20s; "
                "profile log: " + log_path.read_text(encoding="utf-8")[-1000:])

        def property_value(name, value):
            item = PropertyValue()
            item.Name = name
            item.Value = value
            return item

        desktop = context.ServiceManager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", context)
        document = desktop.loadComponentFromURL(
            uno.systemPathToFileUrl(str(document_path)), "_blank", 0,
            (property_value("Hidden", True),),
        )
        # A contents page is structure for a typesetter and junk for an
        # importer — its cached entries are prose-shaped lines. Gone.
        try:
            indexes = document.getDocumentIndexes()
            for index in range(indexes.getCount() - 1, -1, -1):
                document.Text.removeTextContent(indexes.getByIndex(index))
        except Exception:
            pass                     # no indexes, or a foreign shape: keep the prose
        document.storeToURL(
            uno.systemPathToFileUrl(str(docx_path)),
            (property_value("FilterName", "Office Open XML Text"),),
        )
    except SystemExit:
        raise
    except Exception:
        raise SystemExit(traceback.format_exc(limit=8))
    finally:
        if document is not None:
            try:
                document.close(False)
            except Exception:
                pass
        if desktop is not None:
            try:
                desktop.terminate()
            except Exception:
                pass
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    main()
