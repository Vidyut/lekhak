# Lekhak

Lekhak is a free, open-source writing app I'm building because I wanted
something that would let me concentrate on writing novels instead of
wrestling with software.

One thing led to another, and it came together quickly enough that I decided
to add features other writers might find useful and release it for everyone.

The idea is simple: **just write.**

Organise your book into chapters, scenes, notes, folders, or whatever makes
sense to you. Write in a comfortable editor, keep track of your progress,
rearrange things as needed, and export when you're ready.

Lekhak aims to make producing a properly formatted book as painless as
possible. Ideally, you should be able to hit Export without knowing anything
about ebook formatting and still get something usable.

It currently supports Word documents (DOCX), EPUB ebooks, PDF, HTML, Markdown
and plain text. You can also use templates to control how your finished book
looks.

## What's inside

- **A binder that thinks like a book.** Chapters, scenes, notes, folders —
  nested however you like, rearranged by dragging. A real corkboard and an
  outliner when you want to see the shape of the thing instead of the words.
- **Word counts everywhere.** Every scene, every chapter, every folder, the
  whole project, how much you've written today. Pacing is half of writing,
  and it's nice to see it.
- **Targets and progress.** Per-section word goals, and a daily goal if you
  like watching a number climb.
- **A comfortable editor.** Paragraph styles, fonts, alignment, lists, a
  distraction-free mode, and a zoom that makes the letters bigger without
  touching your document's formatting.
- **Snapshots and backups.** Take a snapshot before a big change, restore it
  if the change was a mistake, and keep full-project backups. Rename a backup
  and it's kept forever.
- **Tracked changes.** Suggestions — yours or an AI's — arrive as changes you
  accept or reject. Nothing rewrites your manuscript behind your back.
- **Links and related files.** `[[Link]]` to any section, and the app shows
  which documents mention each other. Hover to preview, click to jump.
- **Metadata that behaves.** Status, POV, dates, your own fields — set on a
  folder and everything inside inherits it.
- **Exports you can hand to anyone.** Manuscript or finished book, in DOCX,
  EPUB, PDF, HTML, Markdown or plain text. Templates decide how it looks.
- **Imports to bring your work over.** Scrivener projects, yWriter, Word and
  LibreOffice documents, markdown and HTML — with a safety rule I care about:
  an import never overwrites anything you already have.
- **Read your prose aloud**, and if you want, let a local or hosted AI
  suggest fixes.

## There's more in the works

- **Ready-made book formatting:** download a free book template or one of
  Amazon's templates, add it to Lekhak, and let the software try to match the
  formatting.
- **Print-ready manuscripts:** interiors that satisfy print-on-demand rules,
  plus help preparing a cover — spine, bleed and all — without either of us
  becoming a graphic designer.
- **AI-assisted editing:** catch typos, mistakes and bloopers, with tracked
  changes so you review suggestions rather than have an AI quietly rewrite
  your work. Works with a small local model if you'd rather not send your
  writing anywhere.
- **Importing existing manuscripts:** more tools, and more of what they
  carry — labels, statuses, notes, metadata. Some imports need careful
  exporting to preserve chapters and notes; that's the part I want to make
  invisible.

Those are goals, not promises about what already works.

## Your writing stays yours

Your book is saved in ordinary files rather than locked into a proprietary
format — you can open the folder and read it. Lekhak also makes backups and
lets you restore earlier versions, and it asks before it deletes or
overwrites anything. Ever.

## Getting it running

Lekhak will run on almost any Python you already have (3.9 or newer). If you
haven't got Python, download it from
[python.org](https://www.python.org/downloads/) — and on Windows, tick
"Add python.exe to PATH" while you're installing it.

**First, get the code.** In a terminal:

```bash
git clone https://github.com/Vidyut/lekhak.git   # download it
cd lekhak                                        # go into that folder
```

No Git? On the [GitHub page](https://github.com/Vidyut/lekhak) click
**Code → Download ZIP**, unzip it, and open a terminal in the folder you
unzipped. Either way, every command below runs from inside that folder.

**Now set it up.** This keeps Lekhak's bits in a private folder inside the
checkout — nothing system-wide, no administrator rights needed.

On Linux or Mac:

```bash
python3 -m venv .venv          # make a small private Python for Lekhak
.venv/bin/pip install -e .     # install Lekhak into it
```

On Windows (in PowerShell):

```powershell
py -3 -m venv .venv
.venv\Scripts\pip install -e .
```

**Finally, make it start like a normal app.** One command, and Lekhak will
show up in your applications menu.

On Linux:

```bash
python3 scripts/install_linux.py
```

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1
```

On Mac:

```bash
bash scripts/install_macos.sh
```

If you'd rather just have a look first, you can start it right away without
any of that: `.venv/bin/lekhak` on Linux and Mac, `.venv\Scripts\lekhak` on
Windows.

Screenshots, and the same steps with pictures, are on the
[Lekhak page at vidyut.info](https://vidyut.info/downloads/lekhak/).

It's still an early release, so expect rough edges; the roadmap is in
[ROADMAP.md](ROADMAP.md).

**Lekhak is free and open source, licensed under the GPL.** Use it, modify
it, share it. Donations are welcome but entirely optional.

Source code: [GitHub](https://github.com/Vidyut/lekhak).
