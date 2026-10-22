# Lekhak

Lekhak is an early Linux-first desktop environment for planning and writing
long documents. It is deliberately not a Scrivener clone: its project format is
transparent, recoverable, and designed around ordinary files.

For screenshots, a detailed feature tour and more help, see the
[Lekhak page on vidyut.info](https://vidyut.info/downloads/lekhak/).

## Current MVP

- Neutral binder: folders contain anything, several roots sit side by side,
  nesting is unlimited; chapter/scene/note are labels, not structure
- Explicit folder, chapter and scene creation actions that land relative to
  the selection
- Outliner view: hierarchical table with Title, Kind, Words, Target and
  user-chosen metadata columns; column picker persisted per project;
  rollup word counts on containers
- Corkboard cards linked to binder structure and synopses
- Rich-text editor and synopsis inspector
- Distraction-free focus mode and adjustable interface font size
  (Edit → Preferences…, `Ctrl+,`) — separate from the editor's own zoom
- Paragraph styles, font controls, alignment, lists, and clear formatting
  in the editor's own format bar, above the text it acts on
- Display-only editor zoom (`Ctrl`+scroll, View menu, `Ctrl+0` to reset):
  enlarges the writing without touching the document's formatting, and is
  remembered with the project — the Page view scales with it to match
- Section find/replace, and distraction-free focus mode
- Per-section word targets with live progress
- Debounced autosave using atomic file replacement
- `Ctrl+S` immediate save plus a timestamped full-project backup — rename a
  backup folder to keep that version forever, and to label it however you
  like: `20261011-093015-441002` becomes `11Oct26 before the rewrite`.
  Pruning only ever touches folders still carrying a raw timestamp
- Per-project selectable backup folder with isolated project subdirectories
- SQLite metadata with foreign keys and ordered siblings
- Project-wide search, plus preview-and-confirm replace (regex supported)
- Plain-text and HTML manuscript export
- DOCX and EPUB 3 manuscript export in binder order
- Selective export of any combination of chapters and scenes
- yw2html-style template sets: slot files per chapter/scene/divider role,
  `${...}` and `${Metadata.Key}` placeholders, user sets selectable per
  export, "New set" and "Open folder" in the export dialog
- Inline table of contents page for EPUB (`toc_page` slot); page-number
  TOC field for DOCX (update fields in Word/LibreOffice)
- Cached word counts on every document
- Arbitrary per-document metadata and reusable export templates
- Typed metadata with text fields and calendar-backed date fields
- Dropdown metadata with project-defined allowed values
- Template fields for title, type, synopsis, word count, content, and metadata
- Automatic timestamped backups on project open
- Named section snapshots with reversible restoration
- Split a section at the cursor (`Ctrl+K`); merge a section with its next
  sibling (snapshots first, history preserved) — menu and binder context menu
- Obsidian-style `[[Title]]` internal links that resolve by title, survive a
  retitle, and are click-through in the editor; broken targets show in the
  status bar; insert one with `Ctrl+L`
- Word counts and keyboard shortcuts

Projects are directories ending in `.lekhak`. Section contents live in
`documents/*.html`; `project.sqlite3` stores titles, ordering, and metadata.

## Install

You need **Python 3.9 or newer**: on Windows, install it from
[python.org](https://www.python.org/downloads/) and tick "Add python.exe
to PATH"; on Linux use your package manager (`sudo apt install python3`);
on macOS use Homebrew (`brew install python3`) or python.org — the
macOS system stub alone is not enough. Everything else is installed
below.

### Step 1 — get the code

```bash
git clone https://github.com/Vidyut/lekhak.git
cd lekhak
```

No Git? On the GitHub page click **Code → Download ZIP**, unzip it, and
run every command below from inside the unzipped `lekhak` folder.

### Step 2 — install

Run from the `lekhak` folder. This builds a private Python environment
inside the checkout — nothing system-wide is touched.

**Linux / macOS** (Terminal):

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

**Windows** (PowerShell or Command Prompt):

```powershell
py -3 -m venv .venv
.venv\Scripts\pip install -e .
```

### Step 3 — add a launcher

No root or admin rights on any platform.

**Linux** — application-menu entry plus icons:

```bash
python3 scripts/install_linux.py          # --check, --uninstall
```

**Windows** — Start Menu shortcut (add `-Desktop` for the desktop too):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1
```

**macOS** — builds `~/Applications/Lekhak.app` (`--remove` deletes it):

```bash
bash scripts/install_macos.sh
```

### Start it

Search for **Lekhak** in your application menu, Start Menu, or Spotlight.
From a terminal: `.venv/bin/lekhak` (Windows: `.venv\Scripts\lekhak`).

Already comfortable with pipx? `pipx install .` replaces Step 2, and the
Step 3 script finds it on your PATH.

`scripts/render_icons.py` bakes `packaging/lekhak.svg` into the PNG/ICO
artifacts; re-run it after changing the icon.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Reliability contract

Content writes go to a sibling temporary file, are flushed and synced, and are
then atomically moved into place. The database uses WAL mode. Project backups
copy the database and document directory without changing the working project.

## Trying this build (testers)

If you are here to test rather than to write, the most valuable thing you can
try first is the **Scrivener import**: `File → Import Scrivener Project…`,
pointed at a `.scriv` package, then compare against Scrivener itself —
structure, word counts, bold and italic, synopses.
[`docs/SCRIVENER-IMPORT.md`](docs/SCRIVENER-IMPORT.md) states exactly what
crosses over, what deliberately does not, and how to report a difference.

Also worth a look: the exports (DOCX, PDF, EPUB), the editor zoom
(`Ctrl`+scroll), and the safety behaviour — a failed save never discards your
text, and deleting or overwriting always asks with a checkbox.

The bugs that matter most are the ones where text is lost, a word count
changes, or something is overwritten. Those reports are worth their weight.

## License

GNU General Public License v3.0 or later.
