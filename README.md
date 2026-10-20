# Lekhak

Lekhak is an early Linux-first desktop environment for planning and writing
long documents. It is deliberately not a Scrivener clone: its project format is
transparent, recoverable, and designed around ordinary files.

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
- Paragraph styles, font controls, alignment, lists, and clear formatting
- Section find/replace, zoom controls, and distraction-free focus mode
- Per-section word targets with live progress
- Debounced autosave using atomic file replacement
- `Ctrl+S` immediate save plus a timestamped full-project backup
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
- Word counts and keyboard shortcuts

Projects are directories ending in `.lekhak`. Existing `.manuscript` projects
remain supported. Section contents live in
`documents/*.html`; `project.sqlite3` stores titles, ordering, and metadata.

## Run on Ubuntu

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
lekhak
```

The application requires Python 3.11+ and Qt 6 via PySide6.

## Desktop launchers

After installing the package (steps above), put Lekhak in your
launcher/menu with the platform script — all are user-level, no root:

```bash
# Linux: ~/.local/share/applications/lekhak.desktop + hicolor icons
python3 scripts/install_linux.py            # --check, --uninstall
```

```powershell
# Windows: Start Menu shortcut (add -Desktop for the desktop too)
powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1
```

```bash
# macOS: builds ~/Applications/Lekhak.app (--remove to delete)
bash scripts/install_macos.sh
```

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
