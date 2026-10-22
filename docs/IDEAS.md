# Feature comparison and easy wins

Written while the author slept (2026-10-21) so there is a list to react to,
not a pile of half-built features. Each row says who else has it, where we
stand, and how big it really is.

## What other writing software does, and where we stand

| Feature | Who has it | Ours | Effort |
|---|---|---|---|
| Binder + corkboard + outliner | Scrivener, Manuskript | ✅ all three | — |
| Snapshots / versions | Scrivener, Ulysses | ✅ per document, plus full-project backups | — |
| Project-wide search & replace | Scrivener, Word | ✅ with preview, regex, per-document snapshots | — |
| Tracked changes, accept/reject | Word, Scrivener (revisions) | ✅ with revision passes | — |
| Distraction-free / focus mode | FocusWriter, ghostwriter, Ulysses | ✅ F11, hides chrome | — |
| Typewriter scrolling | FocusWriter, ghostwriter, Ulysses | ❌ | medium |
| Themes (dark/light/sepia) | every one of them | ❌ (interface font only) | medium |
| **Recent projects** | all | ❌ | **small** |
| **Quick-open a document** (Ctrl+P, fuzzy) | Ulysses, Obsidian, VS Code | ❌ (binder click or Ctrl+Shift+F only) | **small** |
| **Selection word count** | Word, Scrivener | ❌ (document count only) | **small** |
| **Session/daily word goal** | Ulysses, Scrivener (target per session) | partial (per-section targets) | **small** |
| **Insert date/time** | Scrivener, Word | ❌ | **small** |
| **Print (Ctrl+P)** | all | export→PDF then print externally | **small** (reuse the PDF path) |
| Text-to-speech | Scrivener (macOS), Word | ✅ 3.1 | — |
| AI continuation/proofreading | Scrivener (macOS), Ulysses | ✅ tracked, never direct writes | — |
| Compile/export with templates | Scrivener, Word styles | 🚧 Phase 1 landed; templates next | large |
| Import from other tools | Scrivener, Word | ✅ Scrivener/dump/yWriter/markdown, collision-safe — but **no DOCX/ODT manuscript import**, which is the one everybody will try first | medium (python-docx reads styles; ODT via the UNO we already drive for PDF) |
| Trash / undelete | Scrivener, Ulysses | ❌ (delete is confirmed + backups exist) | medium |
| Character/place sheets | Scrivener, novel-writing tools | ❌ (metadata + related files approximate it) | medium |
| Word-frequency / repetition report | Scrivener, ProWritingAid | ❌ | medium |
| Inline comments/annotations | Word, Scrivener | partial (notes as documents; tracked changes) | medium |
| Cloud sync / collaboration | Google Docs, Ulysses | deliberate non-goal (local-first, no telemetry) | — |

## The easy batch (recommended next, in this order)

1. **Recent projects** — `File → Open Recent`, remembered in `QSettings`,
   capped at eight, pruned when a project moves. Standard, expected, and it
   removes the only clumsy step in the daily loop.
2. **Quick open** (`Ctrl+P`) — a one-field palette over document titles
   (binder order, fuzzy-ish match), and it already has a cousin in
   `Find in Project`. Authors jump between scenes constantly; the binder is a
   long walk for a specific one.
3. **Selection word count** — the status bar already recomputes on cursor
   moves; add "12 words selected" when there is a selection. Writers watching
   a scene budget ask for this within a week.
4. **Print** (`Ctrl+P`) — write the same PDF the export produces into a temp
   file and hand it to the desktop's print dialog. All the hard parts exist.
5. **Insert date/time** — a small editor command, useful in journals and
   dated notes; also feeds the metadata `Date` key rather than typing it.
6. **Session goal** — a per-day word target beside the existing per-section
   targets, with progress in the status bar.

## Deliberately not doing

Cloud sync, accounts, telemetry, collaboration: this is a local-first tool
whose value is that the manuscript is a directory of plain files you own.
Also not doing a Markdown-first editing model — the rich-text editor with
sanitised paste is the point, and the exporters already cover the formats
people need.
