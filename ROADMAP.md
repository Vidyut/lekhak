# Lekhak roadmap

Feedback and feature requests, triaged against the current MVP. Ordered by
foundational importance, not by glamour. Items reference the code they touch.

## Phase 0 — foundations (DONE)

### 0.1 Binder rework: neutral folders, parallel roots — DONE
**Request:** "better binder — only one top level folder; Chapter/scene format
feels impossible. Folders have no quality of their own (like Scrivener); the
role is in how they are organized and used. Chapter/scene/note stay, as
labels the writer chose — they are not structure."

**Reality check:** the schema already permits multiple roots and arbitrary
depth (`parent_id` nullable, `reorder()` accepts any parent). The limitation
is UI policy plus the rigid `kind` enum:
- `app.py:611` `add_chapter()` hardcodes `parent_id=None` (top level only).
- `app.py:618` `add_scene()` guesses the parent from the current selection.
- `project.py:169` `kind` restricted to `{chapter, scene, note}`.
- `project.py:62` `create()` seeds a single "Draft" chapter at root.
- Export (`project.py:391`) hardcodes "kind in {chapter, scene}".

**Change:**
- `kind` gains `folder` as a first-class value: a container with no content
  of its own by default.
- Any item can be created at any level, under any parent, including parallel
  top-level items (a Manuscript folder beside Characters beside Locations).
- Creation actions become "add folder / add chapter / add scene here" relative
  to the selection, never top-level-only.
- Export participation stops being "kind is chapter or scene" and becomes a
  per-document/export-compile property (see 1.2), defaulting sensibly.

**Implemented (2026-10-20):** `folder` is a first-class kind; kinds are
validated against `DOCUMENT_KINDS` and export uses `EXPORT_KINDS`
(chapter+scene; folders and notes stay out). `Project.create()` seeds
"Draft" as a folder, and a one-time migration flips the old seeded root
chapter. The three toolbar actions were unified into one placement helper:
containers receive children, a scene prefers a chapter/folder parent, a leaf
selection gets a sibling; nothing is forced to the top level, so parallel
roots work. Folder items get a directory icon and selecting one flips the
central view to the corkboard. Per-document compile overrides remain open
until 1.2/2.1.
- "Draft" becomes a folder, not a chapter. Existing `.lekhak` projects must
  migrate without data loss (a kind migration plus a one-time seed rule).

### 0.2 Desktop launchers (Linux / Windows / macOS) — DONE
**Request:** easy to launch from the desktop on every platform.
**Implemented (2026-10-20):** `scripts/install_linux.py` (stdlib only) writes
`~/.local/share/applications/lekhak.desktop` plus hicolor SVG/PNG icons,
validates with `desktop-file-validate`, refreshes the desktop/icon caches,
and supports `--check` / `--uninstall`; Exec prefers the checkout's `.venv`
console script, then PATH, then `python -m lekhak`. `scripts/install_windows.ps1`
creates a Start Menu shortcut (optional `-Desktop`, `-Uninstall`) via
pythonw + `-m lekhak`, icon from `packaging/lekhak.ico`. `scripts/install_macos.sh`
builds a minimal `~/Applications/Lekhak.app` bundle with launcher and (when
iconutil is available) an `.icns`. `packaging/lekhak.svg` is the source of
truth; `scripts/render_icons.py` bakes PNG/ICO/ICNS. `python -m lekhak`
works via `src/lekhak/__main__.py`, and `main()` sets the desktop file
name so GNOME/Wayland match the window to the entry.

## Phase 1 — good software

### 1.1 Search and replace across the project — DONE
**Request:** project-wide search *and* replace.
**Implemented (2026-10-20):** Edit → Replace in Project… (Ctrl+Shift+H).
Preview list shows every match with its document, field (content/title/
synopsis) and surrounding text, capped at 500; double-click jumps to that
document. Options: regular expressions, ignore case, include titles,
include synopses (both opt-in at the API level). Replace asks for
confirmation and reports replacement/document counts. Backed by
`Project.replace()` and `Project.search_snippets()`; literal mode inserts
the replacement verbatim, regex mode supports backreferences.
Matches are searched in stored HTML, so matches interrupted by markup
will not hit.
**Related fix:** `Project.documents()` now returns binder order (tree walk
by position) instead of SQL order by uuid parent id; `ordered_documents()`
is now an alias. Search results, the outliner, corkboard and replace all
iterate in binder order as a result.

### 1.2 Export templates (yw2html model) — DONE
**Request:** default template; users add more; select per chapter/scene;
metadata tags and formatting can modulate output. Reference: peter88213/yw2html.

**Implemented (2026-10-20):** `lekhak/templates.py` provides named template
sets: directories of optional slot files (`project_header`, `project_footer`,
`chapter`, `chapter_end`, `scene`, `first_scene`, `scene_end`,
`scene_divider`), `.html` and `.txt` variants, missing slots falling back to
built-in defaults. Placeholder syntax is yw2html's `${...}` family:
`${Title}`, `${Content}`, `${Synopsis}`, `${WordCount}`, `${ChapterNumber}`,
`${SceneNumber}`, `${WordsTotal}`, `${Metadata.Key}`. Sets live under
`<project>/templates/<name>/` or `~/.config/lekhak/templates/<name>/`; the
export dialog offers a dropdown, "New set…" (forks the current one) and
"Open folder". A compile walks binder order: a chapter unit is its own text
plus descendant scenes separated by the divider; standalone scenes export on
their own. EPUB emits one page per unit. DOCX keeps structural headings
(header slots do not apply there). Word counts are cached on the document
row at save time, with a one-time backfill for older projects.

### 1.3 Word counts everywhere — DONE
**Request:** counts for scenes, outliner, selected text, selected
chapters/scenes, running totals.
**Implemented (2026-10-20):** `word_count` cached on the document row at
save time with a one-time backfill; `Project.word_rollups()` sums
descendants for container rows; the outliner shows per-item and rollup
counts (own vs total in the tooltip); the status bar shows the current
document, target progress, selected-text count, and the project total;
corkboard cards show count and target progress.

### 1.3a Outliner view with user-chosen columns — DONE
**Request:** add/remove metadata columns in the outliner view.
**Implemented (2026-10-20):** a third central view — a hierarchical table of
the binder in binder order. Columns: Title (always on), Kind, Words,
Target, plus any metadata key used in the project. The picker
(Document → Outliner Columns…) checks columns on and off; the choice is
stored in project settings and survives reopening. Clicking a row selects
that document in the binder; binder selection highlights the row. Word
cells on containers are rollups of everything beneath them. Metadata is
read with one batched query per refresh.

### 1.4 Split and merge scenes — DONE
**Request:** split a scene at the cursor into two; merge a scene with its
sibling.
**Implemented (2026-10-20):**
- `Project.split_document(document_id, before_html, after_html, new_title=)`
  — the caller extracts the two HTML halves with `QTextDocumentFragment`,
  which keeps formatting; the method snapshots ("Before split"), inserts a
  sibling right after the original (same kind, collision-free "Name (2)"
  title) and renumbers the rest. Both halves must contain text.
- `Project.merge_documents(first_id, second_id)` — target must be the
  immediately following sibling and a leaf; snapshots first ("Before
  merge"), re-homes the second document's snapshots onto the first so its
  history survives, concatenates the bodies, deletes the second (metadata
  cascades away, content file unlinked).
- `Project.next_sibling()` helper.
- UI: Document → Split at Cursor (`Ctrl+K`) and Merge with Next Sibling,
  plus binder context-menu entries (right-click loads the document first).
  Merge confirms with an explicit warning about dropped metadata.

### 1.8 Interface font size in preferences — DONE
**Request:** font-size picker in Preferences — **for the interface only**
(menus, binder, corkboard, outliner, synopsis, status bar); the editor
text keeps the existing zoom (View → Zoom In/Out, Ctrl+0).
**Implemented (2026-10-20):** Edit → Preferences… (`Ctrl+,`) opens a dialog
with a 8–24 pt interface-size picker and a note that the editor keeps its
own size. The choice persists to `QSettings` (`ui/fontSize`, org/app
"Lekhak") and is applied in `main()` *before* the window is built, so a
fresh launch starts at the right size; the dialog applies it live too.

The two footguns this had to dodge, both confirmed against a running
session rather than assumed:
- **Live propagation.** `QApplication.setFont` alone does **not** reach
  widgets that already exist — a live change left the binder at 9 pt.
  `preferences()` therefore also calls `setFont` on the window, which
  cascades to existing children. Tree items carry no per-item font, so
  they follow.
- **The editor must never inherit it.** The editor is pinned with an
  explicit `setFont` to 12 pt at construction (`reset_zoom`'s number),
  and an explicit font ignores the cascade — so the tree moves and the
  editor does not. This matters because `toHtml()` round-trips the body
  font size: if the interface size reached the editor it would be written
  into stored document content. `setHtml` still applies each document's
  own stored size on load, so existing documents are unaffected.
Verified: set 20 pt → tree 20 / editor 12 in the same session, and across
a simulated relaunch.

### 1.5 Internal links — DONE
**Request:** link to internal documents — a picker, and Obsidian-style
`[[wiki]]` links that resolve by title and open the page on click.
**Implemented (2026-10-20):** `[[Title]]` typed in the editor is resolved on
load into a clickable link and stored again as plain `[[Title]]`, so links
survive a retitle and stay readable in the file. Resolution order: exact
title, then case-insensitive, then substring (substring only ever *offers*
matches for a picker, never auto-opens one). A broken target renders as a red
`[missing: Title]` and is counted in the status bar. Document → Link to
Section… (Ctrl+L) picks a document and inserts `[[Title]]` at the cursor.
**Related fixes:** resolved-link chrome is canonicalised back to `[[Title]]`
in `Project.canonicalize_links()` before every write, so the resolved markup
never reaches disk (a save would otherwise freeze the resolution and break
retitle self-healing). Internal link clicks are handled by a `LinkEditor`
QTextEdit subclass emitting a signal, since plain QTextEdit has no link-click
support. Palette link colour is read via `.color().name()` — `palette().link()`
returns a QBrush. `plain_text()` strips `[[ ]]`, keeping link markers out of
word counts and exports.

### 1.6 DOCX/PDF page control
**Request:** mark chapters/scenes as starting on a right or left page; insert
a blank page when the flow lands on the wrong side.
**Add:** a per-document `page_break` property (`auto`, `left`, `right`,
`next-odd`, `next-even`); DOCX export emits the right
`WD_SECTION_START` / page break; PDF via LibreOffice headless or a direct
writer, chosen at export time.

### 1.7 Table of contents — DONE (PDF part waits on the PDF writer)
**Request:** TOC with links for ebook, links and/or page numbers for PDF,
page numbers only for DOCX.

**Implemented (2026-10-20):** the compile already knows the unit list, so
the TOC is a view of it. EPUB: every set gains a `toc_page` slot; when
non-empty it is rendered as the first content page with `${Entries}` —
one internal link per unit — on top of the spec-required nav document.
DOCX: export inserts a real Word TOC field (`TOC \o "1-3" \z \u`, no
`\h`, so it shows page numbers only), populated by Word or LibreOffice on
field update. **Open:** PDF export does not exist yet (1.6); when it lands,
the LibreOffice route inherits the DOCX field, giving page numbers, and an
EPUB-route PDF can add link annotations.

## Phase 2 — books, variants, and conditional content

### 2.1 Book-level compile settings
**Request:** "if book is MH/TI/PF, front/back matter is this, that or the
other — set on the book folder level; if an image is present in the folder it
is the book image."
**Model:** a folder can be flagged as a *book*. A book carries compile
settings: which front matter template, which back matter, cover image
(explicit, or auto-detected from a conventional filename inside the folder),
and which metadata keys are exposed to the template.

### 2.2 Conditional content and link stripping
**Request:** "only internal links to documents getting published should be
available to publish; all other internal links stripped."
**Model:** a compile-time rule set per book. Each internal link resolves
against the exported document set; links outside it are stripped or replaced
per a chosen policy (`strip`, `plain-text`, `keep-as-note`). Conditional
blocks in templates can include/exclude whole sections by metadata predicate
(`$if(Metadata.Status = Draft)`-style, or a small expression language).

### 2.3 Importers and full round-trip export
**Request:** "eventually, importer/exporter."
**Targets:** Markdown import (pandoc-free, our own parser for the common
case), yWriter 7 `.yw7` import (the author's own workflow), Scrivener
`.scriv` (XML) import as a stretch goal. Export already covers txt/html/
docx/epub; PDF and a clean Markdown export join it.

### 2.4 Tracked edits with accept/reject, and AI as a source of them
**Request:** "eventually, AI integration and tracked edits to
accept/reject."

**Layer 1 — tracked changes (no AI required).** Word-style revision marks
inside the editor: insertions and deletions carry a change id, an author
label, and a timestamp, rendered inline (underline/colour for inserts,
strike for deletes). Every change is addressable so it can be accepted or
rejected individually or in a batch. Storage: the HTML keeps the marked-up
form (so a project remains transparent — a plain text editor still sees the
words), with change metadata in a `revisions` table. Accept bakes the text
and drops the mark; reject removes it and restores what was there. A
session ("revision pass") groups related changes so a whole pass can be
accepted or rejected at once. Interacts with snapshots: taking a snapshot
while changes are pending stores the marked-up state.

**Layer 2 — AI integration.** A provider-agnostic client (local Ollama or
any OpenAI-compatible endpoint; keys in the app config, never in the
project). AI output never lands in the document directly — it always
arrives as a tracked-change session the writer accepts or rejects, which is
exactly what layer 1 provides. First uses: continue-the-scene from the
cursor, proofread/simplify the selection, generate a synopsis from
selection, and answer questions about the binder (POV consistency, scene
count, word targets). Context is assembled from the export pipeline, so
what the model sees is what a compile would see.

## Phase 3 — wish-fulfilling fairy software

### 3.1 Text to speech
Read the current scene or selection aloud. Qt ships `QTextToSpeech`, so this
is likely a thin wrapper with a voice picker and a play/stop/pause toolbar.

### 3.2 Everything else in the wish list
Anything above that didn't earn a slot gets collected here as it arrives.

---

## Working agreements

- The project format stays transparent: documents are plain HTML files,
  metadata is SQLite, backups are copies. No change to that contract without
  an explicit decision recorded here.
- Content writes stay atomic (`os.replace` after fsync). Any new writer
  follows the same rule.
- Codex may pick up any item directly; claim it in a commit message
  (`claim: 1.4 split/merge`) so work isn't duplicated.
- **Broad compatibility, low friction.** Python floor is **3.9** — any
  common distro/system interpreter, no exotic versions. Two runtime
  dependencies (PySide6, python-docx), no environment or tooling the user
  has to assemble; `pipx install .` or `pip install --user .` is the
  install path. No new dependency unless it is genuinely unavoidable, and
  a floor bump needs a recorded reason here. The floor is held by
  `str.removeprefix` (3.9) and the lazy `from __future__ import
  annotations` unions; keep new annotations under that import and prefer
  3.9-safe stdlib. Verify with
  `ast.parse(src, feature_version=(3, 9))` across `src/ scripts/ tests/`.
- **Manuscripts are precious.** Nothing may rewrite, prefix or reformat a
  document's stored title or content as a side effect of a display,
  numbering or import/export feature. An interchange concern (binder
  numbers, TOC markers) is shown on the way out and stripped on the way in;
  it never lands in the stored manuscript.
- **Lean over clever.** Before implementing a feature, check whether it
  needs a new mechanism, a new stored role, a new regex in a write path or
  a new code path that can touch content. If it does, stop and say
  "I don't advise this because…" with the specific risk or bloat, and let
  the decision be made explicitly rather than by default. Prefer the
  representation that has no way to corrupt data over the one that merely
  looks tidier.
