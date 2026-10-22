# Preferences: how it should be built

A proposal, for a fresh-brained session. The dialog is currently a wall of
prose (see `docs/UI-NOTES.md` 4); this is the shape it should take instead,
and why.

## The pattern: a category list, not tabs

Apps that carry a lot of settings converge on the same layout, and it is not
tabs:

| App | Pattern |
|---|---|
| **Manuskript** | a vertical category list (General, Views, Editor, Fullscreen, Focus, Composition, Revisions, Saving, Notifications, …) with the page beside it |
| **Scrivener** | a grid of *panes* on top (General, Appearance, Behaviors, Corrections, Auto-Save, Formatting, Backups, Keyboard, Import/Export, Templates) with the chosen pane below |
| **VS Code / GNOME apps** | the same left list + right page |
| **Word / LibreOffice** | horizontally scrolling tabs — the one nobody copies on purpose |

So: **`QListWidget` + `QStackedWidget` in a `QDialog`**. Every category is
visible at once, the list scales past the point where tabs start wrapping or
scrolling, and a category can be reached in one click without hunting. Inside
a page, use an **accordion** only when a category genuinely has sub-groups
(the AI page and Updates are candidates); otherwise a plain form with a
heading per group is clearer.

Tabs are the wrong tool here for a concrete reason: at ten categories they
either scroll (invisible options) or wrap (ugly), and neither tells the writer
that something is missing.

## The categories, with their contents

App-wide settings and **defaults** only. Anything that travels with a
manuscript belongs to the project, in the inspector
(`docs/UI-NOTES.md`, the app-defaults vs per-project line).

1. **Appearance** — interface font size, as a **slider with a live sample**
   rather than a spin box. (No theme setting: the desktop's own is used; that
   is a settled decision, `docs/IDEAS.md`.)
2. **Editor** — spell-check on/off and the location of the writer's
   `dictionary.txt` (their world's words, `docs/AI.md`); default paragraph
   style for a new document. Small, and a natural home for whatever else
   becomes an editor default.
3. **Files & saving** — backup folder, how many backups to keep, autosave
   delay, "reopen the last project on start". All of this exists today as
   settings with no home in the UI.
4. **Pasting** — the four checkboxes that already exist, each with one line,
   and the existing note that Ctrl+Shift+V always pastes plain.
5. **Links & export defaults** — unpublished-link policy (plain text /
   keep-as-note / strip), the **default template set** for new work, and the
   **Author** default. This is where "defaults for new work" lives; the
   project's own values override them in the inspector.
6. **AI** — endpoint, model, key; the small-model warning from `docs/AI.md`;
   the `ollama pull` line; the proofreading prompt behind an accordion with
   its do-not-edit-unless-you-know warning.
7. **Read aloud** — voice and rate, as today.
8. **Help** — manual source: online (the blog, the live copy) or offline
   (packaged), with the honest "still new, incomplete" caveat.
9. **Updates** — mode (take fixes / ask / never), "check now", and the update
   log from `docs/TEMPLATES.md` §8.
10. **Metadata (this computer)** — the app-level key/value list that applies
    to every export unless a project overrides it (§3.1).
11. **Advanced** — where the config lives, "open config folder", and a
    verbose-logging toggle. The place to put things that are useful twice a
    year and alarming every other day.

## Each category, in detail

`scope` is the part that matters: **app** is a setting of this installation,
**default** is a value a new project starts from (the project's own value, in
the inspector, always wins). Nothing here is per-document.

| Category | Control | Key | scope | default |
|---|---|---|---|---|
| Appearance | interface font size, slider + live sample | `ui/fontSize` | app | the system's |
| Editor | spell check on/off | `spell/enabled` | app | on if a dictionary is found |
| Editor | word list file | `spell/dictionary` | app | `<project>/dictionary.txt` |
| Files & saving | backup folder | `backup/defaultFolder` | default | inside the project |
| Files & saving | backups to keep | `backup/keep` | default | 10 |
| Files & saving | autosave delay | `editor/autosaveMs` | app | 700 |
| Files & saving | reopen last project on start | `session/reopenLast` | app | on |
| Pasting | four checkboxes | `paste/fonts`, `paste/paragraphs`, `paste/inline`, `paste/alignment` | app | as today |
| Links & export | unpublished-link policy | `link_policy/default` | default | `keep-as-note` |
| Links & export | default template set | `templates/default` | default | `default` |
| Links & export | Author | `metadata/Author` | default | empty |
| AI | endpoint, model, key | `ai/endpoint`, `ai/model`, `ai/key` | app | Ollama on localhost |
| AI | proofreading prompt | `ai/prompt` | app | ours, behind the accordion |
| Read aloud | voice, rate | `tts/voice`, `tts/rate` | app | engine default |
| Help | manual source: online / offline | `help/source` | app | online |
| Updates | take fixes / ask / never | `update/mode` | app | take fixes |
| Updates | check now, and the log | — | app | — |
| Metadata | key/value rows for every project | `metadata/*` | default | empty |
| Advanced | open config folder, verbose log | `log/verbose` | app | off |

Two notes that follow from writing it out:

- **"Backups to keep" belongs to the project, not the app** — the backup folder
  and how many copies live there are decisions about *that* manuscript, and
  they already live in project settings (`Project.backup`). Preferences can
  only offer the default for a new project.
- **No "editor font size" here.** The editor is pinned to 12 pt with its own
  display zoom (`docs/TEMPLATES.md`, 1.8); a second place to change type size
  is a second thing to get wrong.

## Rules the dialog should follow

- **One line per control.** Long explanation behind a "?" — that is level-1
  help, already owed (`docs/TEMPLATES.md` §7).
- **Defaults shown, not implied**: `(built-in)`, `(app default)`, `(from the
  project — change it there)` — so the writer can tell what is decided and
  what is merely inherited.
- **From the consequence to the setting**: anything that changes an export, a
  save or a network call says so next to the control that does it.
- **Nothing that belongs to a manuscript.** If a setting would travel with a
  project, it is not here. A dialog whose meaning depends on what happens to
  be open is how settings screens become hated.
- **Searchable, eventually.** With ~11 categories a filter box at the top of
  the list is cheap and makes "where is X" a non-question. Worth doing when a
  category count passes about eight.

## Build notes

- Its **own module** (`src/lekhak/preferences.py`), not a rewrite inside
  `app.py` — the interruption rule (`docs/WORK-SPLIT.md`): a half-applied
  rebuild of a 5,000-line file breaks everything that builds against it, which
  is exactly what happened to MiMo's attempt. A new module plus one wiring
  line in `app.py` survives being cut off.
- Existing keys keep their names (`ui/fontSize`, `paste/*`, `ai/*`,
  `update/*`, `help/source`, `metadata/*`), so nothing needs migrating and the
  old dialog can be deleted in the same commit that adds the new one.
- Tests: build the dialog, walk the category list, assert every category
  shows a page and that the known keys round-trip — no screenshots needed.
