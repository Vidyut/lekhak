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

## 4. Preferences is a wall of prose

Screenshot-worthy as an anti-pattern: paragraphs of explanation sitting
between form rows, labels inline with prose, no grouping. It should be:

- grouped into sections with short headings (Appearance, Links, Pasting,
  AI, Read aloud);
- one line of explanation per control at most;
- the long explanation behind the "?" hover (§7 of `docs/TEMPLATES.md`),
  which is the level-1 help we already owe the writer;
- labels in their own column, so the eye can run down them.

Nothing here changes behaviour; it is all presentation, which is why it is
worth doing properly rather than patching one dialog.
