# Build-now list

What gets built **before** the template engine, in order, with the thing that
tells us it works. Nothing here depends on the template design, so none of it
can be invalidated by the spec review still in progress.

## 0. Folder view: outliner by default, remembered

Clicking a folder currently switches to the corkboard
(`_selection_changed`: `setCurrentWidget(self.corkboard)`). It should open the
**outliner** by default, and remember whichever view the writer actually uses
for folders — per project, as session state beside `editor_zoom`, so a
corkboard lover is not fought either.
*Acceptance:* selecting a folder shows the outliner; switching to the
corkboard with a folder selected and then selecting another folder shows the
corkboard; reopening the project keeps that choice.

**Built (2026-10-22).** The folder branch opens `_folder_view_widget()`,
which reads `folder_view` from the project settings (default, junk-safe:
outliner). A hand click on the corkboard/outliner tab while a folder is
selected writes the preference; the programmatic switch fires inside
`_selection_changed` while the selection is loading and writes nothing, and
document selections never touch it. Five tests in
`tests/test_folder_view.py`, one per acceptance clause plus junk and the
document guard. Suite 457, exit 0.

## Parallel work for an idle small model

Not code. A tiny local model must not edit this repository — and it must not
edit anyone's manuscript either (docs/AI.md). What it *can* usefully produce
are **verifiable text artefacts**, where a bad result is obvious in seconds:
a synthetic manuscript fixture with known structure (chapters, scenes, front
matter, injected typos) to drive the importer and word-count tests, and a
corpus of realistic bloopers to exercise the proofreading pass. Structure and
detectability matter; prose quality does not.

## 1. File → Open Recent
Projects remembered in `QSettings` (`session/recentProjects`), newest first,
capped at eight, entries pruned when the folder is gone, updated on a
successful switch only.
*Acceptance:* switching projects twice leaves both at the top of the menu,
and deleting one on disk removes it from the list rather than offering a
broken entry.

## 2. Quick open — `Ctrl+P`
A one-field palette over document titles in binder order (substring, then
fuzzy), Enter selects, Esc closes; it only *navigates*, never edits or
deletes.
*Acceptance:* typing three letters of a scene name jumps to it from anywhere;
the palette never appears with no project open.

## 3. Selection word count
The status bar already recomputes on cursor moves — add "N words selected"
when there is a selection.
*Acceptance:* selecting a paragraph shows its count; deselecting restores
the document count.

## 4. Print — `Ctrl+P`
Reuse the PDF path (1.6/1.7): write the PDF to a temp file, hand it to the
desktop's handler (or Qt's print dialog if it behaves), delete the temp file
afterwards.
*Acceptance:* printing a short story opens the system print flow with the
same pagination the export produces; the temp file does not survive.

## 5. Insert date/time
An editor command inserting the date (and optionally the time) at the caret;
feeds the metadata `Date` value rather than being typed by hand.
*Acceptance:* inserts today's date in the project's locale and is undoable as
one step.

## 6. Session goal
A per-day word target beside the existing per-section targets, with progress
in the status bar and the day's delta from the session start.
*Acceptance:* a target survives a restart; writing 500 words shows 500 of the
goal without re-opening a dialog.

## 7. DOCX/ODT manuscript import
The gap the author spotted: we export DOCX beautifully and cannot read one.
Use the existing import floor — never overwrite, numbered second copies,
identical content reported (`docs/IMPORTS.md`) — with `python-docx` reading
paragraphs and styles, and the LibreOffice UNO path we already drive for ODT.
*Acceptance:* a Word document imports as book → chapter → scene using its
heading styles; importing it twice warns "identical"; nothing existing is
touched.

## 8. AI: local-model default
Per `docs/AI.md`: the Preferences wording and warning, the `ollama pull`
instruction, a "minimal edits only" proofreading prompt, and — separately —
a deterministic `hunspell`/`aspell` typo underliner with no model involved.
*Acceptance:* with Ollama running and a small model named, Proofread
Selection lands exactly one tracked change per edit; with no model
configured, the AI menu explains how to set one up instead of failing
silently.

## 9. Phase-1 leftovers
Text export pagination (form feed or not) and the EPUB note that per-unit
files already are pages.

## Print copies, and covers (near-term: the author needs book 1 and 2 on KDP)

Two different DOCX jobs, and they must not be confused:

| | Reading / submission copy | **Print copy** |
|---|---|---|
| Cover | may carry one | **must not** — the print copy is the *inner* book; the cover is a separate PDF the printer wraps |
| Margins | simple | mirrored, per the book's trim |
| Images | any | **no full-colour content images** unless the book is genuinely an illustrated one (bleed, plates); colour content gets a print job rejected |
| Output | DOCX, for editors and readers | the inner-block PDF to upload, plus a separate cover PDF |

The cover creator is **optional and a later update** — it is not Lekhak's core
competence. What it should do when it arrives, because the author asked for a
full pipeline rather than an art studio: place cover, back and a sensibly
proportioned spine for the book's trim, lay out margins per the printer's
template, **overlay a grid so nothing important is provably cropped**,
scale images to the required size with a quality warning when upscaling, allow
text fields where the template permits, and export a print-ready PDF. Cover
and inner copy are edited and exported **separately**.

This is why the print copy belongs after the template engine: it needs the
DOCX config/reference machinery (trim, mirrored margins, running heads,
per-kind page starts) before it can be anything but a guess.

## Then, after the spec review
The template engine — discovery, `Type`/format matching, the slot-driven
DOCX render, the config/reference/generate forms, per-export override
(`docs/TEMPLATES.md` §9). This is deliberately last: it is the part where an
early wrong decision would cascade.
