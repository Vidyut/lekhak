# Storage: the filesystem *is* the structure

Status: **decided** (author, 2026-10-25). This supersedes the "metadata is
SQLite" half of the project-format working agreement in `ROADMAP.md`: metadata
moves into the files, and SQLite becomes a cache that can be rebuilt by
scanning.

## Why

- **Extract and nest.** Copy `Book Three/` out and open it as its own project;
  drop it back and it is a folder again. A series can live in one collection
  while a WIP is opened on its own without touching published books.
- **Portability.** Copy a project folder to your editor; it opens, with its
  templates inside it.
- **Legibility.** A file manager shows the book's shape, and Git shows prose
  diffs rather than a database blob.
- **The Obsidian property:** any folder can be a project, so the unit of work
  is whatever the writer carved out.

## Layout

```
Abrahamha's Strays.lekhak/          ← a project: a folder with .lekhak/project.yaml
├── .lekhak/                        ← machinery, hidden from the writer's view
│   ├── project.yaml                ← title, format version, app settings
│   ├── index.sqlite3               ← rebuilt cache: search, counts, history
│   └── lock                        ← one instance per project
├── Book Three/
│   ├── .lekhak/folder.yaml         ← id, Type, association, child order
│   ├── Chapter-12.html             ← prose + frontmatter
│   └── Scene-Zayn-meets-Ari.html
├── Templates/                      ← a normal directory, recognised by name
├── Trash/                          ← root-level area, mirrored structure
├── images/
└── backups/
```

The `.lekhak` **suffix is a convention**, not a requirement: any folder
containing `.lekhak/project.yaml` is a project.

## Documents

One file per document. Prose is HTML as it is today; everything that is not
prose lives in a **YAML frontmatter block** at the top of the file:

```html
---
title: 3 - Zayn meets Ari
id: 5f3c…            # stable across renames
type: Scene
synopsis: Zayn finally meets Ari, and it goes badly.
word_target: 1200
metadata:
  PoV: Zayn
  Status: Draft
---
<p>…the prose…</p>
```

- **The title is the truth**; the filename is a slug derived from it. Titles
  are free text and filenames are not, so the two cannot be the same thing.
- **`id` is stable and permanent** — the thing that makes a rename harmless:
  covers keep finding their folder, snapshots and revisions keep their
  document, and an external move looks like a move rather than a delete plus a
  create. *Recommended; amend if you'd rather have no ids at all and accept
  that renames lose history and covers.*
- **Frontmatter never reaches an export.** It is stripped on the way out and
  restored on the way in — the same display-layer rule that already governs
  binder numbers and resolved links (working agreements, "Manuscripts are
  precious").
- **YAML subset.** Keys, scalars, simple lists, nested maps by indentation.
  No anchors, aliases, multi-document streams or tags. A hand-rolled parser
  keeps the two-dependency agreement intact; if the subset ever pinches, we
  move to PyYAML and record the reason then.

## Folders

**Anything with children is a directory, whatever its role.** A filesystem item
cannot be a file and a directory at once, and real binders contain chapters
that hold both their own prose *and* their scenes — the dry run against the
author's project found exactly that. So a document with children becomes a
directory, and its own words, if it has any, become **`index.html`** inside it.
A container with no prose of its own has no index file. (Whether a container's
own `index.html` exports is a question of role, settled by `Type`, not by where
it sits.)

`.lekhak/folder.yaml` inside each folder holds what the directory itself
knows: `id`, `type`, the template association, and **the order of its
children** as a list of names. It lives *inside* the folder because a copied
folder must be a valid project on its own.

Order is a list of **names**, not numeric prefixes: reordering rewrites one
small file instead of renaming every document.

**Order is never derived from filenames, and nothing sorts children by name.**
The manifest *is* the order: the migration writes it from the database's
sibling order, and every reorder rewrites it. Sorting by name would scramble
real binders — the author's scene titles run `1---`, `2---`, … `10---`, which
as text sort `1, 10, 2` — and a filesystem's own enumeration order is
arbitrary on top of that. New documents append; the writer drags to reorder;
the numbers in a title stay decoration, never mechanism.

## Stored versus indexed

| Stored (the truth) | Indexed (rebuildable) |
|---|---|
| prose, frontmatter, folder manifests | search index, word counts |
| templates, images | revisions and snapshots |
| backups | anything derivable by scanning |

**History does not travel with an extracted folder.** The prose travels, and
so do tracked changes (their marks live in the HTML), but snapshot and
revision history stays with the project it happened in. A folder split off
today starts with no history of its own.

## Projects, and opening any folder

- `.lekhak/project.yaml` marks a project: title, format version, app settings.
- **Opening a folder with no marker offers to make it a project** — write the
  machinery, index what is there, and let the areas appear as they are needed.
- **Converting an old project is the same code path** plus one step: read the
  old database and write the tree from it. One implementation, not a converter
  and an opener.

## Nesting

A project marker is honoured **only at the root you opened**. Nested inside
another project, a project is a folder: its project settings are ignored, its
`.lekhak/` is machinery rather than content, and its documents are simply
content — counted, exported, reordered. Its own `Templates/` still governs its
subtree, by the nearest-wins rule, which is what lets ten books carry ten
formats inside one collection.

**Locks.** On open, check `.lekhak/lock` in the ancestors *and* immediate
descendants: warn that the same files are open at another level, and allow an
**override**, because a crashed session must not leave a project permanently
unopenable. No arbitration beyond that.

## The areas

- **`Templates`** is recognised by name **anywhere** — a folder dropped inside
  any folder governs that subtree. It sits **last among its own siblings**
  (per-level lift), and every marked folder also appears in the Templates area
  as **jump rows** that navigate to the real folder. The bundled default is
  shown there read-only, from package data; *Duplicate for editing* creates an
  editable copy (project root when triggered from the library, the folder
  itself when triggered inside one).
- **`Trash`** is a **root-level area**: your deletes go there, mirrored into
  the same structure, and emptying it prunes the directories it emptied.
  The **name** is recognised *anywhere* to mean "not manuscript", so a nested
  project's discards never count or export; the area lists any nested `Trash/`
  as jump rows so nothing is hidden. It is not renamable, restoring means
  moving something out (with **Rename** as the default and **Overwrite**
  behind a checkbox that promises nothing about backups), and manuscript
  folders are never pruned — only explicit deletion removes them.

## Filenames: no spaces, enforced on sight

**Author's decision (2026-10-25):** *"Lekhak filenames must not contain
spaces"* — and the app enforces it rather than merely preferring it. Anybody
who can take an HTML document out of a project folder and edit it can write a
compliant filename; the alternative is a tree that every other tool reads
differently from the way Lekhak does.

- **On open, and on any rescan, non-compliant names are normalised**: spaces
  and illegal characters become a single hyphen, runs collapse, ends trim.
  Files **and folders** — a policy that stops at the last path separator is
  not a policy — and because the walk is top-down, renaming a folder needs no
  second pass for its children.
- **Files from outside are accepted, never refused.** Enforcement is a rename,
  not a rejection: bring in whatever a file manager or another editor made,
  and Lekhak tidies the names on sight.
- **Guards:** only while we hold the project lock; a single pass before any
  editing begins; never on a name that is already compliant; collisions get
  `-2`, `-3`, compared case-insensitively because macOS and Windows
  filesystems are; and every change is **reported** in the session summary, so
  no rename is a mystery. A per-project setting can switch normalisation off
  for someone deliberately syncing a project with another tool.
- **Slug rules:** letters and digits in any script, plus `-` and `_`; spaces
  and everything else become `-`; runs collapse; ends trim; no leading dot;
  80-character cap; an empty title becomes `Untitled`; Windows-illegal
  characters and reserved names (`CON`, `NUL`, `COM1`…) are avoided.
- **The title is never touched.** It lives in the frontmatter; normalisation
  changes filenames only, and the writer's words are not rewritten (working
  agreements, "Manuscripts are precious").

## Backups, locks, and edits from outside

- **Backups** are full-tree copies, excluding `backups/`, `.lekhak/` and
  `Trash/` — content and templates travel, machinery and discards do not, and
  a backup can never contain backups. Location comes from Preferences, with
  the per-project override that exists today.
- **Edits from outside are expected**: rescan when the project regains focus,
  and if a file changed on disk while it was open here, offer **Reload**,
  **Keep mine** or **Keep both** — never a silent reload, which would discard
  what is in the editor.

## Risks to keep in view

- Case-insensitive filesystems (hence the collision suffix and casefolded
  comparison).
- Cloud-sync tools and hidden directories.
- Frontmatter leaking into an export if any new writer forgets to strip it.
- Lock blind spots across nesting, and stale locks.
- Folder renames cascading through children, and anything still keyed by path
  — which is what the stable `id` exists to prevent.

## Build order

1. This spec, and the `ROADMAP.md` amendment it requires.
2. **The dry-run migration tool** — read-only, run against the author's real
   project, reporting the tree it would write before anything is touched.
3. Loader and index rebuild, then the writer: create, rename, move, reorder,
   delete — atomic renames wherever the filesystem allows.
4. Trash, the areas, and the per-level lift.
5. Extract, nest and absorb — which by then is "copy a folder, open it".
6. The example/documentation project, authored as markdown in the repo.
