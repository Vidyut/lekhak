# Scrivener import: what comes across, what does not

For the people who will try this before release — and for us, so a bug report
can say *what* differs instead of *something feels off*.

## What we import

- **The Draft / Manuscript subtree only**, in binder order. Folders become
  folders, text items become scenes. Research, Trash and everything else stay
  behind — Scrivener's own compile ignores them for the same reason.
- **Prose**, converted from Scrivener's `content.rtf` with a deliberately
  narrow RTF reader: bold and italic, paragraph and line breaks, the
  typographic characters Scrivener emits (em/en dashes, curly quotes,
  bullets), and both cp1252 and Unicode escapes.
- **Titles** (with an optional override) and **synopses**
  (`synopsis.txt`).

## What we deliberately do not import

| Skipped | Why |
|---|---|
| Research, Trash, other binder subtrees | not manuscript; Scrivener's compile skips them too |
| **Inline images** (`pict`) | the RTF pass is narrow by design; images are not brought over yet |
| Headers/footers, stylesheets, theme, revision marks, fields | document furniture, not prose |
| **Labels, Status, Keywords, custom metadata, collections** | not read today — this is the most likely thing a Scrivener user notices missing |
| Comments, annotations, footnotes | not verified either way — please tell us if yours are lost |

## How to check it, in five minutes

1. **Structure:** compare the binder tree against Scrivener's. Names and
   nesting should match, minus Research/Trash.
2. **Text:** compare word counts — total, and a few scenes you know are long.
   *A count that differs is the single most useful bug report we can get.*
3. **Formatting:** spot-check a scene with bold and italic, and one with
   dashes and curly quotes.
4. **Synopses:** they should sit on the same items they do in Scrivener.
5. **Control:** if something looks wrong, use Scrivener's own
   *File → Compile* to DOCX or markdown and compare against that — it tells
   us whether the file was already that way.

## What to send us

The importer never overwrites anything, and a refused import leaves your
project untouched (`docs/IMPORTS.md`), so the safest thing is: import into a
scratch project and compare there. Then report:

- what the structure should be and what it was;
- any word-count difference, with the scene's title;
- formatting that was lost (what it should look like, and what it became);
- anything in the "not imported" list above that you *wanted* — Labels,
  Status and custom metadata are the top candidates, and knowing which ones
  matter decides what gets built next.

Nothing here is a promise to fix everything; it is a promise that a report
that says *what* differs will be actionable.
