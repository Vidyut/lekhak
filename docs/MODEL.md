# How Lekhak thinks about your project

## Folders and documents

A project has exactly two kinds of thing in it: **folders** and **documents**.
Folders group. Documents hold your words.

Lekhak does not call them anything else. Because writers structure books,
series and research differently, we do not ship categories like "chapter" or
"note" baked into the structure. A folder is a folder. What it *is* — a book,
a chapter, Part One, a pile of research, a wiki of characters and locations —
is decided by you, in the panel on the right. The software will format and
publish exactly the structure you built.

## Roles come from Type

Select anything in the binder and the inspector (the panel on the right)
shows a **Type** row. It is always there, always filled — before you set
anything it says what the item physically is (`Folder` or `Document`), or
what it was created as (`Chapter`, `Scene`, `Note`). Set it to whatever the
item plays in your book:

- a folder holding your book — **Type: Book**
- a chapter — **Type: Chapter** (on the chapter's document, or on a folder
  that contains the chapter's scenes)
- a scene — **Type: Scene**
- front matter, back matter, author profile, glossary, bibliography — any
  words you like: **Type: Front Matter**, **Type: Glossary**, …

Type is free text. The names above are suggestions. Templates and exports
use whatever Type names you give them — to pick a template, choose a heading
style, start a chapter on a new page, or leave something out of the book
entirely.

## Keeping something out of the printed book

Any document can be printed or not, as you wish. There is no special kind of
item that refuses to print. Two ways to leave something out:

- **Give it a Type like "Do not print"**, and add a blank template for that
  Type to your template set — it renders as nothing.
- **Or simply don't select it** when exporting. The Export Options dialog's
  scope is whatever you have selected; select nothing and it is the whole
  project.

## Do what feels intuitive

If you're writing a book, create a folder for the book and start writing
documents inside it. If you think a chapter should have separate scenes in
it, create folders for the chapters and write or move scenes into them. Keep
research, character notes and worldbuilding in their own folders if that
helps you — we recommend keeping material to publish separate from references
and research, but don't worry: you can always organize folders as you need
them when a need for clarity or reorganization arises.

Do what feels intuitive for you, and the software will help you write and
publish exactly like that.

---

## For builders

The physical structure is `kind ∈ {folder, document}`-shaped and nothing
else; `chapter`, `scene` and `note` survive only as **Type values**, never as
structural categories. The protected metadata key is `Type` (already reserved
in `docs/TEMPLATES.md` §2); its vocabulary is the writer's, matching
opportunistically against template names per §2's chain.

- **`Project.type_of(document)`** (project.py) is the single source of truth:
  stored `Type` metadata if set, else the derived default — `folder` →
  `Book` when the folder has `book_settings` or `page_setup`, else `Folder`;
  `chapter` → `Chapter`, `scene` → `Scene`, `note` → `Note`, anything else →
  `Document`. Derivation *is* the migration: old projects need no backfill,
  and new documents get their Type seeded at creation.
- **No publish flag exists.** Exclusion is Type + a blank template slot, or
  the export scope selection (`ExportOptionsDialog`).
- The inspector's Type row (app.py) is an **editable dropdown**: the
  novel-writing defaults (`TYPE_SUGGESTIONS`), plus every Type already
  used in the project (so a typed value — typo included — is selectable
  next time), plus free text. It edits the **document's own** metadata —
  folders included, even though the custom-fields table below a folder
  selection shows project metadata (§3.1). It shows `type_of` defaults
  and is always populated; emptying it returns the item to its derived
  default. A derived default is never written to storage — only an
  explicit choice is stored — so a later heal is never shadowed by a
  stale seed. Idiot-proofing: an exact match snaps to the existing option
  (nothing is added); a case-only variant ('book' vs 'Book') warns and
  offers "Keep it as a separate type", snapping to the existing option
  until the checkbox is ticked.
- The metadata table's third column is **Format** (the value widget:
  Text/Text area/Checkbox/Date) — renamed from "Type" to end the collision
  with the metadata key. The Edit Metadata dialog hides the Type row and
  preserves the stored value on save; the inspector's Type row owns it.
- Outliner "Kind" column, binder tooltips and Quick Open show `type_of`,
  never the raw physical kind.
- Page setup, book templates and covers hang off folders whose Type is
  `Book` (the `type_of` heal makes existing book folders visible as books);
  project default otherwise. Export stamps each book's own paper and warns
  on mixed trims (author decision, 2026-10-23).
- Templates root stays a flag (`is_templates_root`) — app machinery, not a
  writer role.
