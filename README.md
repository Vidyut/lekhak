# Lekhak

Lekhak is an early Linux-first desktop environment for planning and writing
long documents. It is deliberately not a Scrivener clone: its project format is
transparent, recoverable, and designed around ordinary files.

## Current MVP

- Neutral binder: folders contain anything, several roots sit side by side,
  nesting is unlimited; chapter/scene/note are labels, not structure
- Explicit folder, chapter and scene creation actions that land relative to
  the selection
- Corkboard cards linked to binder structure and synopses
- Rich-text editor and synopsis inspector
- Paragraph styles, font controls, alignment, lists, and clear formatting
- Section find/replace, zoom controls, and distraction-free focus mode
- Per-section word targets with live progress
- Debounced autosave using atomic file replacement
- `Ctrl+S` immediate save plus a timestamped full-project backup
- Per-project selectable backup folder with isolated project subdirectories
- SQLite metadata with foreign keys and ordered siblings
- Project-wide search
- Plain-text and HTML manuscript export
- DOCX and EPUB 3 manuscript export in binder order
- Selective export of any combination of chapters and scenes
- Arbitrary per-document metadata and reusable export templates
- Typed metadata with text fields and calendar-backed date fields
- Dropdown metadata with project-defined allowed values
- Template fields for title, type, synopsis, word count, content, and metadata
- Automatic timestamped backups on project open
- Named section snapshots with reversible restoration
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

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Reliability contract

Content writes go to a sibling temporary file, are flushed and synced, and are
then atomically moved into place. The database uses WAL mode. Project backups
copy the database and document directory without changing the working project.
