# Templates and export defaults — design

Status: **design, pre-implementation.** Everything here is decided unless a
line says PROPOSED (a choice made for you — say the word and it changes).

The goal in one sentence: **a project with no templates at all still exports
a readable manuscript** — titles, heading pages, page breaks, A4 — and
everything beyond that is opt-in, visible, and shareable.

---

## 1. The layers, and what each is for

Four scopes, one file format, resolved in this order (first match wins for a
given document):

| # | Scope | Lives where | Editable | Purpose |
|---|---|---|---|---|
| 0 | **Baseline** | in the code (`templates.py`) | no | the floor: "AT LEAST this formatting, no matter what" |
| 1 | **App library** | `$XDG_CONFIG_HOME/lekhak/templates/<name>/` | yes (files) | your own reusable sets, any project |
| 2 | **Project / shared** | `<project>/Templates/<name>/` or any `Templates/` beside an ancestor of the project | yes (files) | the project's look; shared across sibling projects |
| 3 | **Explicit pick** | `book_settings["template"]` on a folder; `doc_template` on a document | in-app | this book/document, right now |

A template in a higher-numbered scope shadows the same name lower down.

**A template governs wherever one applies; the baseline is what you get when
none does.** The baseline is not a floor laid under a template — it is the
*default template* plus the default pagination (A4, a page per document). The
author's rule: *"if there is a template, we use it; if there isn't, we use
our baseline. Somebody may make a chapter template that contains the titles of
all the documents in it — a scene list of sorts. Another may want a list of
characters. So no scene text. Somebody may want no title, just the scene
text. As long as they can tell us what they want, we're good."*

So a template may legitimately produce something far sparser than the
baseline — titles and no prose, prose and no title, a character list, a scene
list, chrome with an empty body — and that is the template working, not a
bug. What makes those expressible is the value namespace (§3.1):
`${Content}`, `${Children}`, `${Entries}`, `${Title}`, `${Metadata.Key}`. A
slot the template does **not** define falls back to the *built-in default
slot* — which is itself just a template, not the baseline's behaviour layered
underneath.

Three axes stay independent of all this, because they are not prose:
**paper** comes from Page setup (1.15), a template that defines pagination
overrides the default, and the default is A4 with a page per document (§4).

**`Templates` is a protected name.** A folder called `Templates` is a
template library, never manuscript: it is excluded from exports, and its
children are templates rather than chapters. The name — not a database flag —
is what carries this, so a `Templates` folder can be dragged next to any
project, zipped, mailed, and still work. (The existing `is_templates_root`
flag keeps working for projects that already use it.)

**It shows in the sidebar even when empty.** The Templates area is always
present, and with no user templates it holds the baseline as non-editable
reference entries — so "where do templates live" is answered by looking, not
by reading. A folder named `Templates` is display-lifted to the **last
position under its parent**, in the binder and the outliner, exactly as the
2.1 flag's areas already are — drop one into a folder and it appears at the
bottom of that folder's subtree.

### Discovery, exactly

For an export from project `P`:

1. list `P/Templates/` (and `P/templates/`, lower-case, for compatibility);
2. walk up from `P`'s parent: the *nearest* ancestor directory containing a
   `Templates/` directory — every subfolder of it is a template, and it
   serves that ancestor's whole subtree (so `Series/Templates/` serves
   `Series/Book One.lekhak`, `Series/Book Two.lekhak`, …);
3. the app library;
4. the baseline.

Within a scope, a template named `default` (case-insensitive) is the default;
failing that, the first by name, alphabetically. PROPOSED: keep alphabetical
here because for disk templates it is the only order that exists (binder drag
order is a database thing, and a shared folder has no database); a template
explicitly named `default` is the way to say it.

## 2. Which template a document gets

1. `doc_template` on the document (the inspector's slot combo), if it names
   something that exists;
2. `book_settings["template"]` on the nearest ancestor folder that has one;
3. **`Type` match**: the nearest `Type` metadata value — the document's, then
   each ancestor folder's, then the project's (§3.1) — matches a template
   name. A folder's `Type` therefore dresses everything inside it, and a
   `Type` on a chapter can pick a chapter-shaped template;
4. **title match**: the document's, chapter's or book's title matches a
   template name (case-insensitive) — e.g. a folder "Short stories" finds a
   template `short stories`;
5. the scope's default template (§1);
6. baseline.

**Reserved names, and only names.** Three things are reserved: the folder name
`Templates` (§1); the format tags `docx`, `pdf`, `epub`, `html` (with the
aliases 2.1 already uses — `ebook`, `print`, `web`, `text`/`txt`/`plain`);
and the metadata key **`Type`**. What a writer *puts* in `Type` is theirs —
`short story`, `news article`, `Book`, `research paper`, `diary entry`,
whatever their own dropdown or text field holds — and a template named after
that value is applied. No list of type names could ever be reserved, so none
is.

**Matching is opportunistic; it never invents anything.** A `Type` or a
format that matches no template falls back to the template that *is*
applicable: `Format: pdf` with no pdf override simply uses the same template
as everything else. A template is always HTML — it decides how the content is
presented — and a format tag only chooses which presentation applies.

If step 1 or 2 names something that does not resolve, **warn and fall back**
down the chain rather than exporting nothing or silently using baseline. The
warning is a line in the export dialog ("'Penguin' has no match — using
default"), not a modal.

Metadata-driven rules (a table mapping `Type = short story → template`) are
**reserved**: the title match plus an explicit pick already cover it, and a
rule table without a UI is a feature only we can use.

### 2.1 Overriding the template for one export

One book has to come out in different clothes: the book template for the
reading copy, an "editor submission" template for the version you send out —
both DOCX, from the same project. The export dialog therefore carries a
selector with an override checkbox.

- **The row always shows the resolved answer.** The selector is
  pre-populated with whatever the association rules (§2) pick for *this*
  selection, and it is recomputed every time the dialog opens — never
  remembered from last time, and never a stored setting. The configuration
  has already happened by then; this row reports it, for the export about to
  run.
- **Changing it is an override, and says so.** Choosing a different entry
  warns, in these terms: *"You are overriding the template for this
  selection. This applies to this export only. To make it stick, assign the
  template to the folder (Book template) or to the document."* — naming the
  persistent place rather than merely refusing to persist.
- **Existing templates only.** The selector lists what discovery found
  (§1); nothing is created or edited here. Choosing a look is not authoring
  one.
- **One-off, not preserved.** The choice lives in the dialog and is cleared
  when the export finishes. It is not written to project settings, and we
  promise nothing about carrying it across sessions — an override that
  lingered would silently govern a later export the writer had forgotten
  about. **If a look should stick, apply it to the folder** (or chapter, or
  document): that is the persistent mechanism, and this is deliberately not a
  second one. The override must also be cleared before the ordinary
  per-folder selections are consulted, or the two would contradict each
  other.
- **Granularity:** the same checkbox is available at chapter and scene level
  in the export scope, so a single chapter can go out under a different
  template than the rest while the override is in play.

PROPOSED reading of that last point: the per-item checkbox means "this item
overrides its folder's association **for this export**", not "this item is
permanently re-associated". Say if it means something else and it changes.

## 3. Anatomy of a template

**Say only what you need.** A template is not a form to fill in. If every
scene is a title and some prose, then title and prose are all you touch —
no `Type`, no format folders, nothing else. Reach for the rest only when
something must be presented differently, and prefer a conditional in one
template over a second template for a small variation:

```
$if(Format = pouchebook)$else…$endif      ← one decision, one file
if epub or html: the ordinary back matter
if docx or pdf: the print back matter, where clickable links
                are replaced by QR codes
```

The rest of the template is identical, so a whole separate DOCX template for
that one change would be duplication with a maintenance bill. Make a separate
format template when the *presentation* genuinely differs — a document size,
margins, fonts, running heads or page numbers: things HTML and EPUB cannot
express at all.

A template is a directory. Everything in it is optional except the HTML set.

```
Templates/
└── Penguin paperback/          ← the template; its name is what title-match uses
    ├── html/                   ← the mandatory set: ALL css and metadata live here
    │   ├── title_page.html
    │   ├── project_header.html
    │   ├── project_footer.html
    │   ├── toc_page.html
    │   ├── chapter.html
    │   ├── chapter_end.html
    │   ├── scene.html
    │   ├── first_scene.html
    │   ├── scene_end.html
    │   ├── scene_divider.html
    │   └── documents/          ← document-level slots: <name>.html
    │       └── bare.html       ← built-in: `${Content}` and nothing else
    ├── text/                   ← same slot names as .txt, for plain-text export
    ├── docx/                   ← format override for DOCX (1.6/1.15 do most of this)
    ├── ebook/                  ← EPUB override ("tagged as ebook": see below)
    └── print/                  ← print/PDF override
```

- **`html/` is mandatory and authoritative**: CSS, page setup defaults,
  metadata (`<meta>`, EPUB OPF bits) all come from it. Every other format is
  derived from it unless it has its own override.
- **Format tags are folder names.** A child folder named `ebook`/`epub`,
  `docx`/`print`, `html`/`web`, `text`/`txt`/`plain` is that format's
  override — the mechanism 2.1 already uses for variants. No metadata, no
  flags: the tag is a portable folder name.

  **An override need not be a full HTML set.** What HTML cannot express for
  DOCX — page size, margins, running heads, page numbers, per-kind page
  starts — belongs in the `docx/` folder, in one of two forms:

  **1. A quick config.** A small text file; the first line is the marker that
  says what it is, `#` starts a comment, and the rest is one setting per line.
  The filename carries no meaning, the marker does.

  ```
  Docx
  # Sample configuration. Delete anything you do not need.
  Page size (inches - horizontal, vertical): 5,7
  Margins (L,T,R,B/I,T,O,B): 0.5, 0.3, 0.3, 0.3
  # Running heads, left/middle/right; blank slots keep their commas
  Header: {Series}, , {Author}
  Header (Left, Middle, Right): , , {Book}
  Footer: , {Page}, ${PagesTotal}
  # Page starts, per kind
  New Chapter: Recto
  New Scene: Page break
  ```

  Units are inches, or millimetres with an `mm` suffix. Margins are four
  values (left/top/right/bottom) or a mirrored pair (inside/outside).
  Placeholders are the same `${…}` namespace as everywhere else — `{Book}`
  in the sketch above is shorthand for `${Book}` — so a running head can say
  `${Series}`, `${Author}`, `${Book}`, `${Title}`, `${Date}` or any metadata
  key. `New Chapter` / `New Scene` take the page-start vocabulary.

  **2. A reference DOCX.** Format a document in Word or LibreOffice, drop it
  in the `docx/` folder, and point the config at it:

  ```
  Docx
  Reference file: template.docx
  # Only add mappings that differ from the reference's defaults.
  Title style: Book Title
  Document type diary: Page style diary
  ```

  The file's **text is ignored**; only its formatting is used — its page
  setup, styles, headers and footers become the export's. This is the
  idiot-proof path: no syntax to learn, just format a document the way you
  want your book to look and bring it back. Style mappings are the one thing
  that cannot be inferred, so they are named explicitly.

  **3. Generate the reference file.** Rather than start from a blank
  document, a template can write its own starting point: **"Generate
  reference DOCX/ODT"** produces a document holding one sample of every part
  the template defines — a title page with `${Title}` and `${Author}`, a
  contents page, a preface, an introduction, a chapter heading, a scene
  heading, body paragraphs, a scene divider — each carrying a **named
  paragraph style** that matches what the mapping will look for, so the
  "only add mappings that differ" line stays nearly empty.

  Generation knows the *structure*, not the writer's typography: the output
  is deliberately plain, and restyling it in Word or LibreOffice is the whole
  point. Bring it back, point `Reference file:` at it, done. ODT is the same
  document in the other container — LibreOffice converts it, and we already
  drive LibreOffice for PDF (1.6), so that path exists.

  **Precedence, and how to keep your own design.** The reference file
  supplies everything; **each config line overrides it**; the book's own Page
  setup (1.15) wins over both, being a decision about *this* book. So when
  something cannot be set in the writer's editor — recto starts are a classic
  (Google Docs, we are looking at you) — it goes in the config, and when the
  config would override a thing already designed in the reference file, the
  line is **deleted or commented out** and the reference's version stands.
  One idiom covers both directions, and nothing is hidden: the config says
  only what it says.

  **Third-party templates come along for free.** Because we lift only what we
  understand and ignore the rest, a downloaded "free book template" — or a
  vendor's KDP formatting template for a particular trim — can be dropped in
  as the reference file: we take its page size, margins and named styles,
  ignore its sample prose and its irrelevant styles, and the writer tweaks
  anything glitchy through the config. Knowing how to format a book stops
  being a prerequisite for having one formatted.
- **Missing format override ⇒ the html set is adapted**, as today: html/text
  render slots; DOCX/PDF take structure from the HTML and their typography
  from page setup (1.15) and book settings.
- **Document templates** (`documents/<name>.html`) are the named slots a
  document can be rendered with ("nothing, not even a title" = `bare`).
- Old flat sets (`<set>/<slot>.html`, no `html/` subdirectory) keep loading —
  the layout in 2.4a is what ships today, so `html/` is a *preferred* shape,
  not a breaking change. PROPOSED: accept both, prefer `html/`.

### 3.1 Values: what a slot can ask for, and where the answer comes from

Slots are strings with `${Value}` placeholders and `$if(Value)…$endif`
conditionals (2.2). Conditionals read the same namespace, so
`$if(Metadata.Status = Final)` works anywhere a `${…}` does.

| Value | Meaning |
|---|---|
| `${Title}`, `${Kind}`, `${Synopsis}`, `${WordCount}` | the unit being rendered |
| `${Content}` | the unit's prose (raw, not escaped) |
| `${Children}`, `${Entries}` | nested units / TOC entries (raw) |
| `${ChapterNumber}`, `${SceneNumber}`, `${WordsTotal}` | counters; template and heading pages never take numbers (2.1) |
| `${Metadata.Key}` | any metadata key, resolved as below |
| `${Parent}` | the immediate container's title |
| `${Book}` | PROPOSED: the nearest ancestor that is "the book being dressed" — a folder with a page setup or a template association; failing that, the export's title-page container |
| `${Format}` | the format being written (`docx`, `pdf`, `epub`, `html`, `text`) — the value that makes `$if(Format = docx)` possible, so a small difference never needs a second template |
| `${Page}`, `${PagesTotal}` | page numbers, where the format has pages (below) |

**Metadata inherits down the binder, and outward from the writer.** A value
resolves nearest-first: the document's own metadata, then each ancestor
folder upward, then the project's, then the **application preference** list
below — and the first **non-empty** value wins, so an empty field on a scene
deliberately shows the chapter's or the book's value rather than blanking it.
This is what makes `${Metadata.Author}` in a scene's page footer, or
`${Metadata.Status}` on a single scene, work without repeating anything:
folder metadata is metadata for everything inside the folder.

**Application-level metadata (Preferences).** A key/value list in
Preferences applies to every export of every project: set `Author = …` once
if you are always the same writer, or an imprint if you only publish ebooks.
Stored in the app's `QSettings` (`metadata/…`), **never in a project** — so
sharing a manuscript does not carry your identity with it, and a project,
folder or document that sets the same key simply overrides it. `${Author}`
is always `Author`: the key name is a convention templates may rely on. Like
every metadata value it is used at compile time only; it never reaches stored
manuscript content (§2.4's display rule).

**Page numbers are format-specific**, because pages are: DOCX/PDF insert real
Word fields (`PAGE`, `NUMPAGES`) so Word and LibreOffice keep them correct as
the text reflows; HTML can use CSS `@page` margin counters when printed;
EPUB has no page numbers (readers define their own) and ignores `${Page}`.



| Rule | Value |
|---|---|
| Paper | **A4** (210 × 297 mm) when the book has no page setup |
| Title page | the selected container's title; the author **only** if project metadata has an `Author` |
| Author key | project metadata `Author`, and nothing else — no fallback, nothing invented. A collection of protest fliers has no author, and that is not our business |
| Containers | each container on the way to a document prints its name as its own heading page |
| Heading levels | by depth in the export: the container chain gets H1, H2, H3… in order, documents one level deeper |
| Documents | every exported document starts on a **new page**, and prints its own title (also when it is the only thing selected) |
| Chapters | plain page break, **recto** (odd page) when the book has a real print trim set (an explicit page setup, not the A4 fallback) |
| TOC | HTML/EPUB: a `toc_page`; DOCX/PDF: the Word TOC field, placed **after** the title page and any front matter |
| Running heads / page numbers | DOCX/PDF: page number bottom-centre, book title top-outer once page setup exists — **new work** |
| Cover | a cover page in every format when a cover resolves (see §5); **DOCX cover is new work** |
| Numbering | none. Titles are the writer's; the baseline invents no "Chapter 1" |
| Counters | title/heading pages contribute no words and take no numbers (2.1's rule, generalised) |

A4, not Letter: A4 is the ISO 216 standard used essentially everywhere except
the USA and Canada (and common-not-standard in Mexico and the Philippines).
Letter is the outlier; A4 is the democratic choice, and for real books the
trim (5×8, 6×9, A5…) overrides it anyway. The current Letter fallback came
from python-docx's template, not from a decision.

## 5. Covers

**Discovery**, in order: `book_settings["cover"]` (explicit path, chosen in
the inspector) → `images/<folder_id>/cover.{jpg,jpeg,png,webp,gif}`.

**Emission**: cover image is page 1, unnumbered, in every format —
EPUB (already), HTML (first block), DOCX/PDF (new: a page with zeroed margins
and the image scaled to the trim width, aspect preserved). PROPOSED: the image
is inserted **as-is**, scaled to fit the trim width, never cropped or padded;
cover *preparation* (crop to exact ratio, EPUB-typical 1600×2400) is a later
convenience, not a gate. The writer decides; we do not police aspect ratios.

A cover only applies when the export resolves to a book folder; a
single-document export has none.

## 6. Workflows this has to support

**The hobbyist (zero configuration).** Write in folders, export, get A4 with
title pages, heading pages and page breaks. Nothing to learn. This is the
baseline and it is always at least this good.

**The author making a book.** Copy the baseline into the project
(`Templates/` next to the manuscript, or the binder's Templates area →
"New template from default"), edit the html slots in the in-app slot editor
(2.4a) or in any text editor, set page setup for the trim, pick a cover.
Export gets the TOC, running heads, cover and recto chapters.

**Someone sharing a look.** Zip `Series/Templates/` and send it. The
recipient drops it beside their project. Their exports use it. No import
step, no database rows, no app-specific container format.

**The binder's Templates area** is the *view* onto all of this: the baseline
shown as non-editable reference entries, the app library and any discovered
`Templates` folders listed, with "copy to project" for anything the writer
wants to edit. It never becomes a second, divergent store: the files on disk
are the truth.

## 7. Help, in two levels

**Level 1 — the hovering question mark.** Every non-obvious control gets a
"?" whose tooltip says what the thing does *and what it costs*: the page-start
combo ("Recto: starts on a right-hand page, inserting a blank page if the
flow lands wrong — only meaningful with a print trim set"), the template set
dropdown, the cover row, `blog_settings`-style rows, the export scope summary,
the Templates area. In-app, offline, no manual needed for the common path.
This is the level that has to be *abundant*: a writer should never have to
guess what a control does in order to avoid breaking their book.

**Level 2 — the manual, with the source chosen in Preferences.** A proper
instruction document, read either:

- **Online** (default): <https://vidyut.info/downloads/lekhak/> — the live
  version, which keeps improving without an app release;
- **Offline**: the packaged copy, shipped with the app (`docs/`, readable
  with no network) — for writers who prefer to stay offline;
- and the choice is remembered in Preferences (`help/source`).

Both open from Help → *Manual*, and from the Templates area and the export
dialog's set dropdown. The manual opens with the honest caveat: *Lekhak is
new; the manual is incomplete and still being written — the online copy is
the more current of the two.* The user decides what to do with that.

**Packaging requirement:** the offline manual must actually ship —
`pyproject.toml` needs the docs in the wheel/sdist (or `scripts/install`
copies them), or "offline" silently means "not there". Phase 6 covers it.

## 8. Updates

The default is **take the fixes**: you already installed Lekhak, so when the
author pushes a repair, you get it. The one thing that changes that behaviour
is a breaking change, which is rare and never silent.

| Preference `update/mode` | Behaviour |
|---|---|
| `auto` (**default**) | check at most once a day on start; if newer, apply it (git checkouts), and say so in the update log |
| `ask` | check, then show what changed and apply only on a click |
| `never` | no network calls at all |

- **Check**: one GET to the public GitHub API for the newest commit on
  `main`, compared with `__version__` and the installed commit. Offline is
  silent; being current is silent.
- **Apply, git checkout**: `git pull --ff-only`, and only when the working
  tree is clean — the writer's own edits are never stashed, merged or
  overwritten; a dirty tree means we report and stop. The commits being taken
  are listed by subject and date, and the log records what was taken.
  **We promise no way back.** An earlier commit can be checked out if it ever
  matters, but a rollback restores code only: template files you have edited,
  settings, and anything a project has already written into a newer shape are
  not restored by it. The log exists so the situation is knowable, not so it
  is undoable.
- **Apply, pipx/pip/zip**: we do not rewrite an install behind the writer's
  back. The update becomes one click that runs and *shows* the exact command
  (`pipx upgrade lekhak`, …) and its output in the log.
- **Breaking changes**: if the incoming range is flagged breaking (or the
  version's major part moves), `auto` behaves like `ask`: the breaking items
  are shown first, with a link to the notes.
- **Nothing happens without a trace.** Every check and apply is written to
  Help → *Update log*: timestamp, URL or command, and result. As this is
  written, the app makes two kinds of outbound request — the LLM endpoint the
  writer configured (2.4) and this update check — and the manual says so in
  one sentence. Restarting is what picks up a new version, and the log says
  that too.

The honest caveat from §7 applies here as well: this is a fresh project, so
"newer" means "the author has been fixing things", not a supported release
channel.

## 9. Implementation order

1. **Baseline behaviour** (§4): A4 fallback, title page (+author), heading
   pages by depth, new page per document, recto-with-trim, DOCX TOC placement.
   Touches `_compile_scope` (breaks + title-page list), the four exporters,
   the inspector's page-start combo (add `page`, rename `auto`), tests.
   *Shipped 2026-10-21* — but note what it means for later: the DOCX title
   page, heading levels and breaks are still **code**. Once templates land
   they have to be the output of the built-in default slots, so a template can
   replace them wholesale (§1) — a scene-list chapter, a character list, a
   document with no title at all. Until then the baseline is hard-coded and a
   template cannot change those three things.
2. **Covers in every format** (§5), including the DOCX cover page.
3. **Discovery and precedence** (§1–2): protected `Templates` name, ancestor
   walk, `Type` and title matching, `default` designation, format tags,
   opportunistic fallback (nothing is ever invented), warn-and-fall-back.
4. **Binder Templates area** as the library view + copy-to-project.
5. **`html/` slot layout** accepted alongside the flat layout.
6. **Help — level 1** (§7): hovering "?" on every non-obvious control.
7. **Help — level 2** (§7): the manual, its online/offline choice in
   Preferences, packaged docs, Help menu and the caveat line.
8. **Update check** (§8): the read-only check, the Preferences toggle, and
   the one-click pull for git checkouts.
9. **Preferences metadata** (§3.1): the app-level key/value list that applies
   to every export of every project.
10. Reserved: cover preparation; one-click updating for non-git installs.
   (`Type` matching is no longer reserved — it ships with phase 3; only its
   values, and every other metadata vocabulary, belong to the writer.)

## 10. Open, small

- Text export stays structural (titles and headings as lines, no form feeds)
  — PROPOSED. Markdown likewise.
- A container that has prose of its own prints that prose on its heading page
  rather than dropping it — PROPOSED (nothing is ever silently discarded).
- Running heads: only once page setup exists, or always? PROPOSED: only with
  page setup (a "book"), so a stray export of notes does not sprout headers.
- Update check frequency: PROPOSED daily, silently skipping when offline or
  already current.
