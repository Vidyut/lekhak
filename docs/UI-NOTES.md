# Interface fixes, queued

Owner: the interface side (`docs/WORK-SPLIT.md`). Reported by the author,
recorded so nothing gets lost between sessions.

## 1. Outliner: show only the selected folder's children

The corkboard already does this and is right; the outliner still lists the
whole project, so even after finding the right folder the writer is scrolling
through everything. Selecting a folder should scope the outliner to that
folder's children, exactly as it scopes the corkboard.

## 2. Editor and Page are not available for a folder

A folder is a container. If the Editor tab is there when a folder is
selected, sooner or later somebody types into it — and prose on a container is
a formatting headache that only shows up much later, in an export. **Hide
both tabs for folders** rather than disabling them: Corkboard and Outliner
*are* the folder views, and removing the wrong ones is clearer than graying
them out.

## 3. Corkboard cards should read as cards

Today they are plain text with line breaks. They should look like cards —
padded, framed, a title line and a synopsis block — but **without relying on
theme colours**: invert the contrast against the surrounding area (a light
card on dark chrome, or the reverse) so a card can never vanish because a
desktop theme we do not control renders our colours wrongly. The same trick
is worth using anywhere that must stand out from its background.

## 4. Preferences needs rebuilding, not tidying

As it stands it is a wall: paragraphs of explanation between form rows, labels
inline with prose, subjects interleaved with no structure. The author's
direction: **it needs a lot of work — use tabs or accordions, and arrange the
settings by subject.** Concretely:

- **Split by subject** — Appearance (interface font), Editor, Links and
  export defaults, Pasting, AI, Read aloud, Updates, Metadata (the app-level
  key/value list, `docs/TEMPLATES.md` §3.1).
- **Tabs for the top level, accordions inside a tab** where a subject has more
  than about six controls. Every subject visible at a glance beats a scroll,
  and nothing should be more than one click from the top.
- **One line per control**, in its own column, with the label doing the work.
- **The long explanation lives behind a "?"** — level-1 help, owed to the
  writer anyway (`docs/TEMPLATES.md` §7). A settings dialog is not the place
  for three-sentence prose about paste policy.
- **Defaults shown, not implied**: say what will happen if the writer touches
  nothing (as the AI section partly does with "empty for local servers").

Nothing here changes behaviour, which is exactly why it deserves a proper
pass instead of a one-dialog patch — it is the screen a writer visits when the
software has already confused them.
