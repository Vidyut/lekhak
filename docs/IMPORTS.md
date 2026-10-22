# Imports and collisions — design

Status: **design.** Governed by the working agreement *"destruction is
confirmed, and never by name alone"* (ROADMAP). Two different collisions,
which must not be confused:

| Collision | Meaning | What happens |
|---|---|---|
| **Identical content** | the same source imported again — same folder names, same prose | warn: "you already imported this, as ‘X’"; the writer may take a second copy (numbered) or cancel |
| **Same names, different content** | a re-export, a new draft, someone else's file with similar structure | the writer chooses **Merge / Skip / Keep separate** for the import |

## The rule under both

Imports never overwrite prose on their own. Merging combines *structure*; a
document whose title already exists beside it is **kept both**, numbered
(`comparing folders` is crude by design: names first, contents when the names
line up — author's rule). Overwriting is possible, but it is the destructive
act of the working agreement: an explicit checkbox before it can happen,
never a side effect of pressing Import.

## Conflict walkthrough (file-manager shape, deliberately familiar)

When an import hits names that are already present, it walks the conflicts
the way Thunar/Finder/rsync do — one prompt per conflict, with the facts
needed to judge it:

```
‘Book’ already exists.            existing:  67 kB · 11,204 words
                                  incoming:  67 kB · 11,204 words

  [ Overwrite ]   [ Keep a copy ]   [ Skip ]   [ Abort ]
  [x] I understand the existing text will be replaced
  [ ] apply to all remaining conflicts
```

- **Overwrite** — replaces the existing document's prose. Gated by the
  checkbox; without it the button is dead, as everywhere else.
- **Keep a copy** — `Book (2)`, the file-manager convention. The safe
  default; this is what makes "the user can delete whatever they wish from
  the menu" work.
- **Skip** — leave what is there, bring nothing of this item in.
- **Abort** — stop, and **clean up**: nothing has landed yet (below), so the
  project is exactly as it was and the writer can study the conflicts and
  retry.
- Sizes and word counts are shown for both sides, because "30 kB vs 90 kB"
  is often the whole decision.

## Why abort can genuinely clean up

The import runs into a **scratch project** first (a throwaway `.lekhak` in a
temp directory). Conflicts are resolved against the real project while
nothing real has been written; only when every conflict is answered does the
scratch tree get merged into the live project. Consequences:

- **Abort = discard the scratch.** No partial import, no half-numbered
  folders, no orphaned files — the failure mode that `add_document` and
  `split_document` were reordered to avoid, solved here by not touching the
  project at all until the end.
- **Identity is decided by content**, not by file bytes: the same text
  re-exported from another tool with a new timestamp still reads as
  "identical", because the comparison is folder names and prose.
- One comparison path serves all four importers; none of them needs to know
  it is being measured for a diff.

## Scope of the choice

The policy (**Merge / Skip / Keep separate**) is asked **once per import**
and applies to every folder that import creates, unless the per-conflict
walkthrough (above) is in play. Asking once is the bulk-command behaviour the
author asked for; the prompt lists the colliding names so the answer is
informed.

## Imports are by *format*, not by source application

The current menu is organised by where a file came from, which is the wrong
axis: Scrivener's markdown export is markdown, not a Scrivener file, and
neither Scrivener nor yWriter owns it by the time we see it. Organise by what
the file *is*:

| The file you have | What we do |
|---|---|
| Markdown (with dividers you name) | one importer, with the divider strings in the dialog — a Scrivener dump is this, with its own divider defaults offered as a preset |
| HTML | one importer (a Scrivener/yWriter HTML export is this) |
| **DOCX** | new — `python-docx` reads paragraphs and heading styles |
| **ODT** | new — via the LibreOffice UNO path we already drive for PDF (1.6) |
| A Scrivener project folder (`.scriv`) | its own importer, because it really is a format |
| A yWriter project (`.yw7`) | its own importer, because it really is a format |

The dialog should say so plainly: *choose a file, we work out what it is* —
and where a format can be ambiguous (markdown, HTML), the divider/title
settings are the only questions asked. Separate importers for markdown that
happened to come from a particular program are one code path pretending to be
several.

## What ships first (safety floor)

Until the walkthrough exists, the floor is: imports never overwrite, never
duplicate silently (a second import is numbered), and identical content is
reported. That is enough to make a wrong import harmless, which is the
priority; the walkthrough is convenience on top.
