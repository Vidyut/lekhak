# Lekhak roadmap

Feedback and feature requests, triaged against the current MVP. Ordered by
foundational importance, not by glamour. Items reference the code they touch.

## Phase 0 — foundations (in progress)

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

## Phase 1 — good software

### 1.1 Search and replace across the project
**Request:** project-wide search *and* replace.
**Now:** `project.py:295` `search()` finds documents; `app.py:23`
`FindReplaceDialog` replaces within the open editor only.
**Add:** project-scope replace (with preview and count), replace-in-title and
replace-in-synopsis as opt-in checkboxes, regex mode.

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

### 1.3 Word counts everywhere
**Request:** counts for scenes, outliner, selected text, selected
chapters/scenes, running totals.
**Now:** current-document count only (`app.py:814`), plus `{word_count}`
inside a template.
**Add:** cached counts on the document row (updated on save, not on every
keystroke); outliner column with per-item and rollup counts; selection count
in the status bar; project total; per-target progress in the corkboard card.

### 1.3a Outliner view with user-chosen columns
**Request:** add/remove metadata columns in the outliner view.
**Now:** no outliner exists; the binder tree shows titles only.
**Add:** a fourth view — a table of binder items in binder order, with
columns for title, kind, word count, target, and any metadata key. A column
picker (checkbox list of project-wide metadata keys, plus the built-ins)
adds or removes columns; the choice is stored per project in settings so it
survives reopening. Clicking a row selects that document in the binder.
Rollup counts appear on folder/chapter rows (sum of descendants).

### 1.4 Split and merge scenes
**Request:** split a scene at the cursor into two; merge a scene with its
sibling.
**Add:** `Project.split_document(document_id, at_html_offset)` and
`Project.merge_documents(first_id, second_id)` — both snapshot first, then
rewrite content and renumber siblings. UI: context-menu items on the binder.

### 1.5 Internal links
**Request:** link to internal documents — a picker, and Obsidian-style
`[[wiki]]` links that resolve by title and open the page on click.
**Add:** a link picker in the editor toolbar; `[[Title]]` autolinked to a
document id on render; click-through in the editor; broken-link indicator in
the binder. Resolution rules: exact title match, then case-insensitive, then
ambiguous-list disambiguation.

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
