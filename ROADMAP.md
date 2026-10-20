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

### 1.6 DOCX page control — DONE
**Request:** mark chapters/scenes as starting on a right or left page; insert
a blank page when the flow lands on the wrong side.
**Add:** a per-document `page_break` property (`auto`, `left`, `right`,
`next-odd`, `next-even`); DOCX export emits the right
`WD_SECTION_START` / page break.
**PDF is explicitly deferred, not merely missing.** Decision (2026-10-20):
no bundled PDF engine, no LibreOffice or pandoc detection, no new
dependency. The DOCX export is the exact artifact — anyone who needs a
PDF takes that DOCX through whatever converter they already have. This
makes DOCX fidelity the priority for this item and for 1.7's page
numbers; a future PDF export, if it ever happens, is a thin wrapper over
this DOCX, not a parallel renderer.
**Implemented (2026-10-20):** `page_break` is a documents column (guarded
migration, default `auto`) carried on `Document`, written through
`update_document`, chosen in the inspector's "Page start" combo and saved
with the document. DOCX export opens a new section per marked document:
`right`/`next-odd` emit ODD_PAGE, `left`/`next-even` emit EVEN_PAGE — the
user chose to keep all five values as the writer's vocabulary even though
each pair is one demand (recto = odd in an LTR book), and Word inserts the
blank page itself when the flow lands wrong. `auto` adds no section, so
existing exports are byte-identical until something is marked. Scope
decision (2026-10-20): page presets (paper size, mirror margins, footer
page numbers, gutter) were NOT part of this item — no spec for them exists
in the repo; capture separately if wanted. Tests: 2 project-level (parity
counts in the DOCX XML, persistence + rejection) and 4 offscreen GUI tests
in `tests/test_app_pagebreak.py`.

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

### 1.9 Resume where you left off — DONE
**Request:** "When the software is started, resume from where the cursor was
when it was closed the last time."
**Model:** on close, remember the open document id and the cursor position
(character offset in the plain text) per project; on project open, select
that document and put the caret back (clamped to length if the text moved).
Stored in project settings — it is session state about this manuscript, not
app-wide state, so it travels with the project.
**Implemented (2026-10-20):** `save_current()` writes `last_document` +
`last_cursor` on every save path (debounce, document switch, close — so a
crash still resumes); `_switch_project` selects the remembered document
(fallback: first binder item, stale cursor not applied) and `_restore_cursor`
clamps the offset (hand-edited junk settings leave the caret at start).
Scope confirmed with author: startup also reopens the project itself —
app-level `QSettings` key `session/lastProject`, written on successful
switch, read by `MainWindow.reopen_last_project()`; missing/moved/corrupt
project falls back to the empty window with no dialog.
Tests: `tests/test_app_resume.py` (9 offscreen GUI tests; QSettings
redirected to a temp dir so the suite never touches real config).

### 1.10 Paste that doesn't mangle formatting, with preferences — DONE
**Request:** "default behaviour should copy stuff like bold/italics, but not
paragraph formatting or font… paste in something and line break turns into
two line breaks, indents change, line spacing changes, font changes… and if
you do ctrl+shift+V, you lose your bold/italics!… Formatting is imported as
intended to continue the project. So overall para, font, line spacing,
indent, etc don't change — unless user preferences WANT them to change. But
any bold, italics, etc come through… alignment and inline formatting should
survive (alignment is rarely an accident)."
**Model:** paste goes through our own HTML sanitizer (override
`insertFromMimeData`), not Qt's raw import. Default policy: keep inline
character formatting (bold/italic/underline) and alignment; drop font
family/size, paragraph indents, line spacing and block margins; collapse the
double-line-break noise that clipboard HTML carries. Preferences gain a
checkbox section — font, paragraph formatting, alignment, inline formatting
— plus a "keep everything" path for pasting a fully formatted passage on
purpose (which feeds 1.11). Ctrl+Shift+V stays plain-text paste.
**Implemented (2026-10-20):** `LinkEditor.insertFromMimeData` scrubs every
HTML paste through `sanitize_pasted_html()` — a scratch document rebuilt
read-then-write: each fragment gets a fresh char format holding only the
kept properties, each block a fresh block format (alignment kept by
default; margins/indent/line-height only when asked), and blank-paragraph
runs collapse (leading/trailing runs go, interior runs shrink to one) —
except when paragraph formatting is kept, which leaves structure alone.
Anchors ride along whatever the boxes say (a link is content, not skin);
image objects pass through untouched. Policy lives in `QSettings` keys
`paste/fonts|paragraphs|inline|alignment`, read live by
`load_paste_prefs()`; `PreferencesDialog` gains the four checkboxes. Edit
menu gains Cut/Copy/Paste plus "Paste as Plain Text" (Ctrl+Shift+V — Qt
has no plain-paste API, so `paste_as_plain_text()` recovers the words even
from an HTML-only clipboard) and "Paste and Keep All Formatting"
(`paste_keep_all()`, the deliberate full-fidelity path feeding 1.11).
Tests: `tests/test_app_paste.py` (31 offscreen tests; QSettings redirected
to a temp dir, same contract as the resume tests).

### 1.11 Paragraph styles from real formatting — DONE
**Request:** "paste beautifully formatted text, right click, update paragraph
preset or create new preset… now you can save it as a template and change
your whole document accordingly." (Called "styles" in Word, "classes" in
CSS — user settled on paragraph preset/style.)
**Model:** named paragraph styles stored per project (name → block+character
format signature). Right-click in the editor: "Create style from paragraph…"
/ "Update style '<name>'". The toolbar's six hardcoded entries
(`apply_paragraph_style`) become the seed list, user styles join them and
replace them. Scope check before building: this is formatting metadata only
— never a second way to store prose.
**Implemented (2026-10-20):** `SEED_STYLES` holds the six built-ins as
signatures (size/weight/italic + full margins/indent — the complete margins
are deliberate: switching away from Quote now actually resets the 32 pt
instead of leaking it, which the old parallel arrays left behind). A
signature captured by `capture_paragraph_signature()` records the block and
the character format at the caret — underline, family, line-height and
alignment only when present, so a plain paragraph still matches the seed it
wears — and `style_signature_formats()` rebuilds formats from one, writing
only the keys carried (seeds therefore never touch alignment, underline or
family). Storage is one JSON string in the existing project-settings table
(`paragraph_styles`): `save_style_from_cursor` / `update_style_from_cursor` /
`remove_style` write it, `_load_styles` merges user styles over seeds (an
override keeps its seed's place in the toolbar combo), junk settings fall
back to seeds. Editor right-click extends Qt's own menu with Create / Update
/ Delete; Update prefills the style `style_at_cursor()` detects by
signature. Tests: `tests/test_app_styles.py` (11 offscreen tests).

### 1.12 Metadata panel on the right — DONE
**Request:** "panel on the right for metadata — overall metadata setup on
outliner type pages and document specific metadata on chapter/scene/note
pages."
**Model:** the right-hand inspector (currently Synopsis + Section target)
grows a metadata section: project-level fields when a folder/outliner root
is selected, per-document fields on chapters/scenes/notes — the same
`document_metadata` rows `MetadataDialog` edits, inline instead of modal.
Project-level metadata needs a home first (project settings or a table) —
decide at build time, don't invent early.
**Implemented (2026-10-20):** the dialog's Field/Type/Options/Value grid
was extracted into `MetadataTable`, so the inspector hosts exactly the rows
the dialog edits — the dialog keeps Save/Cancel, the panel saves live.
Project-level metadata went to a single JSON string in the existing
settings table (`project_metadata`) — the channel paragraph styles use —
not a new table or a magic document id: no schema, no migration, junk
degrades to no fields. Selection decides the target: `current_id` on
chapters/scenes/notes, `PROJECT_METADATA_TARGET` on folders and with
nothing selected (uuid-hex ids cannot collide); Edit Metadata… follows the
same rule, so menu and panel always edit one target. Live writes are
replace-the-whole-set, guarded against the mid-edit windows inline saving
creates: a row that lost its key while holding a value blocks the write
(rename safety), population runs signal-quiet, and an edit always targets
the id captured when the table filled, never `current_id` at fire time.
Known edges (refine later): the 4-column grid is cramped at the default
270 px splitter width; folder documents' own metadata rows stay in storage
and in search but no longer have UI (the request moves folders to
project-level fields); project-level fields are not searchable.
**Follow-up (2026-10-20):** column order is now Field | Value | Type —
"seeing name:value next to each other is efficient" — with the Value
column stretching while Field/Type size to content. The Dropdown type
and its options column ("Allowed options", briefly renamed "Choices")
are removed at the author's request: no field in their corpus wants a
fixed vocabulary, and a stored legacy "choice" row loads as Text and
heals on the next save. Dates open as a real picker even for
Scrivener's long format ("Wednesday, January 7, 2443" parses via a
second format and normalises to ISO on the next save).

### 1.13 Auto-linked related files (title mentions) — DONE
**Request:** "auto-linking/tagging — if a file contains words that are an
EXACT match for another file, it gets linked in metadata as a related file,
for eg. character or location names. Handy for checking continuity, updating
character sheets, or providing an AI additional info about the
characters/locations in a scene. So if a scene has 'Aaxyl went to Ridnam'
and there are files aaxyl.html and ridnam.html, they show up as related
files in the metadata without needing the writer to do it specifically."
**Model:** computed, never stored. A project-level scan matches whole-word
occurrences of document titles (case-insensitive — the example matches
"Aaxyl" against a file named aaxyl) in each document's plain text; the
result is shown as a "Related files" list in the metadata panel (1.12),
clickable to jump. Shown in both directions where it's cheap: this scene
mentions these characters/locations, and (on a character sheet) which
documents mention it — the continuity view. No new tables, no write path,
nothing to go stale: titles are the vocabulary and the scan runs on view.
Scope check before building: do not turn mentions into stored links or
editable relations — that would be a second source of truth for prose.
**Implemented (2026-10-20):** `Project.related_documents(id)` returns the
two directions from one pass — titles found in this document's plain text
("Mentions") and documents whose text contains this document's title
("Mentioned by") — with word-character boundaries so "Rid" never matches
inside "Ridnam", casefolded both sides, self excluded, every kind's title
in the vocabulary. Plain texts are cached against file mtime+size on the
Project instance, so the scan re-parses only what was written and a stale
string cannot outlive a save. The inspector shows a collapsible
"Related files" tree (hidden with no matches), and clicking a child jumps
like a wiki link — save first, then switch. Nothing is stored: retitle or
rewrite and the next view is correct.

### 1.14 Metadata value types: text area and checkbox — DONE
**Request:** "type of input text area — so metadata has text, date, drop
down selector, and text area. Maybe people may want checkboxes?"
**Add:** two more value types beside the existing text/date/dropdown:
a multi-line text area, and a checkbox that stores "yes"/"no". The
storage column was already free-form, so nothing about the project
format changes; this is a panel feature only.
**Implemented (2026-10-20):** the Type combo in the shared metadata
table (inspector and Edit Metadata dialog alike) offers Text, Text
area, Checkbox and Date — Dropdown, part of 1.12, was removed the same
day as useless to the author. The text area is an inline
QPlainTextEdit with a taller row that commits when the caret leaves the
widget — the line edit's editingFinished equivalent — so live-save in
the inspector never runs per keystroke. The checkbox stores "yes"/"no"
rather than booleans because the value is what a template predicate
compares and what a transparent project file shows a plain-text editor;
"true"/"1" are accepted on load and normalised on the next save.
Switching a row's type carries the current value across where it still
makes sense and falls back to the neutral default where it does not.

## Phase 2 — books, variants, and conditional content

### 2.1 Book-level compile settings
**Request:** "if book is MH/TI/PF, front/back matter is this, that or the
other — set on the book folder level; if an image is present in the folder it
is the book image."
**Model:** the request grew through follow-up Q&A into the anatomy below
(decisions the author answered directly: the doc templates are files in the
template set's `documents/` directory; a format variant replaces the basic
content rather than adding to it; the export dialog offers a set dropdown
while the four File-menu entries keep picking the format).

- **A TEMPLATES area, not a book flag.** Any folder can be flagged as the
  special templates root. It renders below the regular folders in binder and
  outliner wherever it sits (display-lift), and its subtree never exports as
  manuscript — template pages reach output only through compile settings.
- **A template is a direct child of a templates root** ("default",
  "Marginally Human", …). Its subfolders are format variants, matched by
  title: epub → `("ebook", "epub")`, docx → `("docx", "print")`,
  html → `("html", "web")`, text → `("text", "txt", "plain")`. A matching
  variant folder *replaces* the template's basic content for that export. A
  child folder titled "Back matter" (casefold/strip) marks the pages that go
  after the book; everything else in the template is front matter.
- **Association** — `book_settings["template"]` (an explicit folder id) >
  title match against the book folder > `default`, applied when a folder is
  directly selected. Chrome fires only when the folder is in the raw export
  selection, or on a whole-project export where the override/match holds; a
  chapter- or scene-only selection gets document-level treatment only, and
  the project header/footer/toc_page wrap only a whole-project compile.
  Nested dressed folders bookend inward (wrapper outside, book inside).
- **Document templates** are named slots in the set: `documents/<name>.html`
  (or `.txt`) plus the builtin `bare` = `${Content}` — "nothing, not even
  title". Stored per document in the `doc_template` column; a name the set
  does not have falls back to the default slot rendering.
- **Counters** never credit template pages: no chapter/scene numbers, no
  contribution to `${WordsTotal}` — front matter is not manuscript.
- **Cover** — explicit `book_settings["cover"]` path, else auto-detect
  `images/<folder_id>/cover.{jpg,jpeg,png,webp,gif}`; EPUB embeds the first
  dressed book that resolves one (`properties="cover-image"`).
- The originally drafted **expose-keys metadata allowlist** (which metadata
  keys a book publishes) is deferred — see open edges.

**Implemented (2026-10-20):** three commits — storage (`de405b7`), compile
(`e09a78f`), window (`87f5a3e`). Columns `is_templates_root` and
`doc_template` arrive through the guarded-migration pattern; book settings
live as one JSON string in the existing settings table (blank removes).
Compile side: `_export_documents` expands folder selections but excludes
template subtrees, `_chrome_books`/`_variant_folder`/`_template_pages`/
`_assemble_with_book_chrome` dress the export, `compile_units(fmt=…)`
carries template-aware counters, and all four exporters honour the scope
rules (EPUB adds the cover, DOCX breaks pages around injected template
pages). Window side: the inspector shows the TEMPLATES flag, book-template
combo (Automatic = match by name), cover row and — on chapters/scenes/notes
— the document-template slot combo; binder and outliner render the lifted
template area in italic; both trees allow multi-select and export gathers
the union of their selections (empty = whole project, replacing the old
"Nothing selected" warning); `ExportOptionsDialog` now shows a scope summary
plus the set dropdown instead of the per-document checklist;
`_project_total` skips template words. Tests: `tests/test_book_compile.py`
and `tests/test_app_booksettings.py` (12 each, suite 202).
**Open edges:** expose-keys deferred; the DOCX TOC field still lands before
front matter (page breaks work, ordering not yet considered); "Back matter"
is a title convention, not a flag; outliner word *tooltips* (project
rollups) still count template words under a regular folder even though the
project total does not; the binder keeps its current item selected, so a
whole-project export needs an explicit deselect (the scope summary makes
this visible); a stored template/slot id that no longer exists shows as
Automatic/Default and heals on the next actual change.

### 2.2 Conditional content and link stripping
**Request:** "only internal links to documents getting published should be
available to publish; all other internal links stripped."
**Model:** resolved at compile time, not at write time — the editor keeps
storing bare `[[wiki]]` markers and its `lekhak://` anchors unchanged, so a
link's meaning depends on what the current export contains (the same
manuscript can be whole-project for EPUB and a single chapter for a draft).

- **Resolution is exact-title only**, matching what the editor never
  auto-opens: a casefold-equal title resolves (first in binder order on a
  duplicate), a substring-only or ambiguous target is treated like a broken
  one — picker candidates are the editor's job, not compile's.
- **Published links** (target in the exported set) become real links wherever
  the format can carry one: `#unit-N` fragment anchors in single-file HTML
  (one invisible anchor per unit), `section-N.xhtml` in EPUB, Word-internal
  `w:hyperlink`/`w:bookmarkStart` pairs in DOCX (python-docx has no hyperlink
  API, so the elements are built by hand; every heading gets a `d<id>`
  bookmark). Plain text keeps the words — a text file cannot link.
- **Unpublished links** (broken, ambiguous or outside the set) follow a strip
  policy: `strip` removes the link's words from the output entirely,
  `plain-text` (the default) keeps the words with no link, `keep-as-note`
  keeps them plus " (not in this export)". The policy is per **source**
  document: the first ancestor folder with `book_settings["links"]` wins, else
  the project's `link_policy` setting (a Preferences-dialog row; inert when no
  project is open). Published links ignore the policy — a link to a published
  document is never stripped.
- **Header/footer slots** run through the same link pass, against this
  compile's document set, with the global policy (project chrome belongs to no
  one book). Selection exports have no project chrome, so this only matters
  for whole-project compiles.
- **Conditional blocks** live in template slots only, never in document prose:
  `$if(Key)`, `$if(Key = Value)`, `$if(Key != Value)`, `$else`, `$endif`,
  evaluated in `TemplateSet.fill()` against the same values that fill
  `${...}`. Conditions compare case-insensitively; a bare key is true when
  its value is non-empty; the operators need surrounding spaces so keys may
  contain them; nesting works. A hand-edited slot degrades to something
  printable — an unmatched `$if` keeps its branch state to the end, a stray
  `$else`/`$endif` is dropped, markers never leak into output.

**Implemented (2026-10-20):** two commits — core (`4bb615f`), window
(`07c2c0b`). `TemplateSet.conditionals` plus `_compile_scope`/`_prepare_links`/`rewrite_wiki_links` in `project.py`
(scope extracted from `compile_units` so header/footer strings run through the
same machinery), thread-through in `compile_units`/`_render_document`, unit
anchors in `export_html`, bookmarks and the token-splitting run builder in
`export_docx` (`\x02<id>\x03<text>\x04` survives `plain_text`). Window: the
inspector's folder book section gains an "Unpublished links" combo
(Automatic = project default), Preferences gains the project-wide default
row. Tests: `tests/test_content_rules.py` (14) plus three app tests, suite
225.
**Open edges:** a `$if(...)` condition value containing `)` cannot be matched
(the piece parser stops at the first one); conditionals do not apply to DOCX
(the DOCX path has no template slots); an epub/html link to a *scene* lands on
its chapter's unit/section top — DOCX gets scene-level precision via the
scene's own heading; header/footer links always use the global policy, never a
book's; the exact-title-only rule means a deliberately shortened
`[[Chapter]]` for "Chapter Two" is an unresolved link and follows the policy
rather than silently picking a target.

### 2.3 Importers and full round-trip export
**Request:** "eventually, importer/exporter." Then: "I can give you a huge
dump from Scrivener… books + WIPs (so you can also test behaviour under
load…) Or we can do just one book at a time." And: "Don't import the old
export. I can give you a fresh export (with latest edits)."
**Model:** start with the author's fresh Scrivener multi-document markdown
dump (the `===DOCUMENT===` block format with Type/Parent/Position headers —
already proven by the earlier Astray migration audit, 0 warnings), one book
at a time, structured as chapters/scenes/kinds the way the dump declares.
The 2026-10 archived exports in `Writing/Scrivener/*.md` are stale and are
not a source. Serves two purposes at once: the author's real corpus in
Lekhak for daily writing, and a load fixture for exports/word counts under
real volume. Further targets: plain Markdown import (pandoc-free), yWriter 7
`.yw7`, Scrivener `.scriv` XML as stretch. Export already covers txt/html/
docx/epub; PDF and a clean Markdown export join it.
**Partial (2026-10-20): Scrivener dump import is done.**
`lekhak/importer.py` parses the `===DOCUMENT===` format (blank-line header
fields, multi-line Synopsis values recognised by a known-key whitelist,
markdown-ish bodies converted to the rich text Lekhak stores: paragraphs,
`*em*`, `**strong**`, `#` headings) and places documents with an
ancestor-stack walk — parent-by-title is safe because the dump is
depth-first binder order, verified against the full 326-document corpus
with zero orphans. Books appear only as parent titles (folders are never
in the dump); the import rebuilds every book as its own folder — the
splitting is the app's job, per the author's correction on first use
("I don't know how to split it when I import… I thought you would do
it"), not a book-by-book picker. Duplicate chapter titles across books
cannot cross-wire because each book is placed by its own stack pass.
**Shelf handling:** a generic container whose direct children are all
chapters (Scrivener's "Manuscript": 8 works stored as chapter-level
docs) is not a book — each child is, and the author's reference
structure shows Marginally Human and Terminally-Immortal inside
Manuscript beside them too. Since folder blocks are absent from the
dump, that containment is an assumption, recorded here as such: with
exactly one shelf in the dump, the shelf becomes a wrapper folder and
every book imports inside it, matching the author's screenshot; with
none or several, books import at the top level where the dump cannot
misplace them. Real books are never mistaken for shelves because each
has a book-level scene (a title page) among its children — verified
against all three top-level containers of the real corpus.
Scrivener's unset sentinels ("No Status", "No Label", PoV "None") are
dropped rather than stored; every real value (PoV, Location, Date, Quote,
Source, Keywords, custom outline keys) lands in document_metadata, and
Synopsis lands in the synopsis column — the meta fields are headers and
never leak into prose (asserted by test). The dump's Date column
imports typed as `date` so it opens in the panel's picker directly, not
as text ("dates changed to dates directly"). Whole-library import of the
author's real dump: 3 books, 330 documents, 406k words in ~0.15s — the
2.6MB file is not too big. File menu: "Import Scrivener Dump…" into the
open project, and "…into New Project…" which creates a fresh `.lekhak`
named after the dump file. Still open in this item: plain Markdown
import, `.yw7`, `.scriv` XML, clean Markdown export, PDF.
**Design note for the Markdown import (author's idea, 2026-10-20):**
"insert specific strings as dividers for the splitter — [this string]
begins a chapter, [that string] begins a scene." The importer should
not impose a heading convention: the writer names the divider strings
(defaults `#` for a chapter, `##` for a scene) in a small import dialog
and the file splits on those, pandoc-free, everything between dividers
becoming the document's prose. Same placement stack as the dump import
once the blocks exist.

### 2.4 Tracked edits with accept/reject, and AI as a source of them — DONE
**Request:** "eventually, AI integration and tracked edits to
accept/reject."

**Layer 1 — tracked changes (no AI required).** Word-style revision marks
inside the editor: insertions and deletions carry a change id, an author
label (Preferences → "Change author label", default "Author"), and a
timestamp. Rendering is a pair of sentinel styles Qt round-trips — a
blue-tinted underline for inserts, a red-tinted strike for deletes —
because `toHtml()` keeps a background colour but drops custom format
properties; the live change ids ride those custom properties while the
document is open, and re-attach to the marks **by span order per kind**
after a reload (`attach_ids`). Storage is the marked-up HTML plus
pending-only rows in a `revisions` table; accept deletes the row with the
mark, reject deletes the insert or unmarks the deletion. A session
("revision pass") groups changes and is created per tracking toggle-on;
the Revision Passes dialog accepts or rejects one whole pass, and Accept
All / Reject All cover the document. Word counts, search and every export
see the **accepted** rendering (`plain_text` → `accepted_html`) — the
stored file keeps its marks until the writer resolves them.

**Layer 2 — AI integration.** A provider-agnostic client (`ai.py`, urllib
only, no extra dependency): any OpenAI-compatible `/chat/completions`
endpoint, Ollama's localhost server as the default, endpoint/model/key in
Preferences (app settings, never the project). First uses shipped:
**AI → Continue Scene** (the section's tail, capped, at the caret) and
**AI → Proofread Selection**. Both land through
`apply_tracked_replacement` as one tracked pair under an "AI" byline and
their own session — never a direct write, and the tracking toggle does not
gate them, so accept/reject stays the writer's call.

**Implemented (2026-10-20):** three commits — core (`c0a5ec5`), AI layer
(`ba0beac`), ROADMAP. Storage and marks: `revisions` table + sentinel
constants + `accepted_html`/`reconcile_revisions` in `project.py`, the
live-mark half in a new `revisions.py` (`runs`/`segments`/`apply_accept`/
`apply_reject`/`attach_ids`). Editor: `LinkEditor` gained the tracking
state machine — typing bursts coalesce into one insert until the caret
leaves the end, backspacing a plain char strikes it in place, erasing
already-marked text removes it and its row, pastes are one change,
paragraph-mark joins at block boundaries stay with Qt untracked. Window:
Track Changes (Ctrl+Shift+T), Accept/Reject All in Section, Revision
Passes…; reconcile runs on every save; AI menu + Preferences AI section.
Also fixed en route: `plain_text` leaked Qt's CSS head, adding ~19
phantom words per stored document. Tests: `tests/test_revisions.py` (24)
plus `tests/test_ai.py` (9, canned loopback endpoint), suite 258.
**Open edges:** deleting a paragraph mark (block join) is untracked —
the separator is invisible and Qt owns the merge; bursts split on caret
moves, not on punctuation or pauses; marks left without rows (undo
removed them behind the table's back) keep rendering but are
unaddressable until neighbours resolve — the table never invents rows,
only prunes; per-change granularity keeps its data (ids on every row)
but ships no list yet, so the passes dialog is document+pass only; undo
can desync rows from marks until the next save's reconcile heals it; the
live status-bar word count still counts struck words until the next
save recomputes; restoring a snapshot taken with pending marks restores
the marked-up prose and reconcile prunes the orphaned rows; AI context
is the section tail, not the export pipeline (compile-aware context and
the remaining uses — synopsis generation, binder Q&A — wait on a later
pass); no streaming or cancel; the API key sits in QSettings plaintext.

### 2.4a Template-slot editor — DONE
**Request:** (captured 2026-10-20, queued "after 2.4") an in-app editor
for the export template slots, with the placeholder vocabulary offered as
a dropdown and the slot checked for mistakes.

Document → Edit Template Set…: plain-text editing of a set's nine export
slots (html and text mode) plus its document templates, with a completer
over the real `${...}` / `$if` / `$else` / `$endif` vocabulary and live
tier-1 validation — unknown keys (case-sensitive, matching `fill()`'s
lookup), unbalanced `$if`, orphan `$else`, stray markers — plus a Qt
round-trip sniff for html slots that catches an unclosed tag swallowing a
placeholder. Saves are atomic (temp + `os.replace`, the document-content
contract) and stay allowed with warnings, because `fill()` already
degrades a bad slot to something printable; the built-in set is
view-only and New set forks it into the project. This edits slots; the
expose-keys metadata allowlist (2.1) stays deferred and is a different
feature.
**Implemented (2026-10-20):** one commit; `validate_slot` / `TEMPLATE_KEYS`
/ `TEMPLATE_COMPLETIONS` / `write_slot` in `templates.py` (stays
Qt-free), `TemplateSlotEditorDialog` + `_roundtrip_issues` in `app.py`.
Tests: `tests/test_template_slots.py` (19), suite 277.
**Open edges:** validation does not parse the bare keys inside `$if(...)`
conditions; a second `$else` inside one `$if` is tolerated silently
(`fill()` flips the branch twice); the completer offers the fixed
vocabulary, not the project's actual `Metadata.*` key names.

## Phase 3 — wish-fulfilling fairy software

### 3.1 Text to speech
Read the current scene or selection aloud. Qt ships `QTextToSpeech`, so this
is likely a thin wrapper with a voice picker and a play/stop/pause toolbar.

### 3.2 Everything else in the wish list
Anything above that didn't earn a slot gets collected here as it arrives.

**Book cover generator (captured 2026-10-20, not scheduled).** Full-wrap
cover from user-provided images: front, back, spine. The value is doing
the parts writers get wrong and waste days on — spine width computed from
page count × paper type (Amazon's white vs cream constants differ),
bleed added outside the trim, a check that spine lettering and back-cover
blurbs stay inside the safe zone, and a PDF at the exact dimensions
KDP/IngramSpark accept. Front/back/spine laid out from a template per
trim size; user drops in their artwork and text. Depends on 1.6 (page
geometry + realistic page count) and on a PDF writer, so it lands after
both — see the PDF deferral above.

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
- **Lean over clever, and every line must earn its place.** Before
  implementing a feature, check both sides: what it costs (a new mechanism,
  a new stored role, a new regex in a write path, a new code path that can
  touch content) and what it buys. A cosmetic or low-value feature that
  needs a lot of code is bad code regardless of how well it is written —
  8000 lines to make the interface sparkly is a no. If the cost is real,
  stop and say "I don't advise this because…" with the specific risk or
  bloat, and let the decision be made explicitly rather than by default —
  this applies even to essential features, where the answer is to explain
  the trade-off and get an opinion rather than to proceed silently. Prefer
  the representation that has no way to corrupt data over the one that
  merely looks tidier.
- **Comment the why, not the what.** Every load-bearing or non-obvious
  block says what it does *and why it is done that way*, so that a future
  change to the "why" makes the comment visibly stale rather than silently
  wrong. The test: can a reader tell, at the point of use, whether these
  lines are safe to remove? If not, the comment is missing. This is not
  decoration — uncommented invariants get "tidied up" and break in ways
  that cost someone their work.
