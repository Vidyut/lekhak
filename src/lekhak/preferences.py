"""Preferences, category by category (docs/PREFERENCES.md; UI-NOTES 4).

A QListWidget of categories beside a QStackedWidget of pages — the
layout settings-heavy apps converge on, and the one that still works at
eleven categories where tabs scroll or wrap. Every category that ships
here has a real backend today; the rest wait rather than ship as dead
controls:

- Editor — word-list location, default paragraph style (no storage yet)
- Files & saving — backup folder / backups to keep (per-project decisions,
  ``Project.backup``; an app-level default needs a project-side home)
- Links & export — default template set (template engine, unbuilt)
- Help — manual source (the manual openers are unbuilt)
- Updates — mode, check now, the log (the update check is unbuilt)
- Metadata (this computer) — app-level key/value rows; the §3.1
  inheritance chain is still the author's decision, not a builder's

Rules the dialog keeps (docs/PREFERENCES.md): one line per control,
long explanation behind a "?", defaults shown rather than implied, and
nothing that belongs to a manuscript — per-project values stay in the
inspector, where they travel with the book.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSlider,
    QSpinBox, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

from . import ai, tts
from .project import DEFAULT_LINK_POLICY

# Display labels for the strip policies, in UI order; the values are the
# strings book_settings / the project setting store.
LINK_POLICY_CHOICES = (
    ("Strip unpublished", "strip"),
    ("Plain text", "plain-text"),
    ("Keep as note", "keep-as-note"),
)

_AUTOSAVE_DEFAULT_MS = 700


def _help(text: str) -> QLabel:
    """Level-1 help (docs/TEMPLATES.md §7): the hovering question mark."""
    label = QLabel("?")
    label.setToolTip(text)
    label.setStyleSheet("font-weight: bold;")
    return label


def _row(label_text: str, control, help_text: str):
    """One line: label, "?", and the control in a two-column form row."""
    label_row = QHBoxLayout()
    label_row.addWidget(QLabel(label_text))
    label_row.addWidget(_help(help_text))
    label_row.addStretch()
    container = QWidget()
    container.setLayout(label_row)
    return container, control


class PreferencesDialog(QDialog):
    def __init__(self, font_size: int, paste: dict[str, bool],
                 revision_author: str = "Author",
                 ai_settings: "ai.AISettings | None" = None,
                 tts_settings: "tts.TTSSettings | None" = None,
                 tts_voices: list[str] | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        store = QSettings()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter categories")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self._filter_categories)
        outer.addWidget(self.search_box)

        body = QHBoxLayout()
        outer.addLayout(body, 1)

        self.categories = QListWidget()
        self.categories.setFixedWidth(170)
        self.categories.setMovement(QListWidget.Static)
        self.categories.currentRowChanged.connect(self._show_category)
        self.pages = QStackedWidget()
        body.addWidget(self.categories)
        body.addWidget(self.pages, 1)

        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(8, 24)
        self.size_slider.setValue(font_size)
        self.size_label = QLabel(f"{font_size} pt")
        self.size_sample = QLabel("The quick brown fox — menus, binder, corkboard")
        self.size_slider.valueChanged.connect(self._update_size_sample)
        self._update_size_sample(font_size)
        appearance = self._page("Appearance")
        appearance_layout = QVBoxLayout(appearance)
        label_row = QHBoxLayout()
        label_row.addWidget(QLabel("Interface font size"))
        label_row.addWidget(_help(
            "Menus, binder, corkboard, outliner and panels — this "
            "installation's chrome. The writing editor keeps its own "
            "12 pt size and zoom (View → Zoom), deliberately: a second "
            "place to change type size is a second thing to get wrong."))
        label_row.addStretch()
        appearance_layout.addLayout(label_row)
        slider_row = QHBoxLayout()
        slider_row.addWidget(self.size_slider, 1)
        slider_row.addWidget(self.size_label)
        appearance_layout.addLayout(slider_row)
        appearance_layout.addWidget(self.size_sample)
        note = QLabel("This installation's setting; nothing here travels with a book.")
        note.setWordWrap(True)
        appearance_layout.addWidget(note)
        appearance_layout.addStretch()
        self._add_category("Appearance", appearance)

        editor_page = self._page("Editor")
        editor_form = QFormLayout(editor_page)
        self.spell_check_box = QCheckBox("Spell-check squiggles in the editor")
        self.spell_check_box.setChecked(
            bool(store.value("ui/spellSquiggles", False, type=bool)))
        editor_form.addRow(*_row(
            "Spell-check", self.spell_check_box,
            "Red wavy underlines under words the system dictionary "
            "rejects. Needs aspell or hunspell installed; View → "
            "Spell-check Squiggles toggles the same thing while writing."))
        self.author_edit = QLineEdit(revision_author)
        self.author_edit.setMaxLength(80)
        editor_form.addRow(*_row(
            "Change author label", self.author_edit,
            "The name shown as the author of tracked changes — your "
            "edits and AI's — in this installation. The book's own "
            "Author is manuscript data: set it in the inspector."))
        self._add_category("Editor", editor_page)

        files_page = self._page("Files && saving")
        files_form = QFormLayout(files_page)
        self.autosave_spin = QSpinBox()
        self.autosave_spin.setRange(100, 60000)
        self.autosave_spin.setSingleStep(100)
        self.autosave_spin.setSuffix(" ms")
        self.autosave_spin.setValue(int(store.value(
            "editor/autosaveMs", _AUTOSAVE_DEFAULT_MS, type=int)))
        files_form.addRow(*_row(
            "Autosave delay", self.autosave_spin,
            "How long typing must pause before the document is written "
            "to disk. Shorter is safer if the machine crashes; longer "
            "avoids disk chatter mid-sentence. Takes effect at once."))
        self.reopen_last_box = QCheckBox(
            "Reopen the last project on start")
        self.reopen_last_box.setChecked(
            bool(store.value("session/reopenLast", True, type=bool)))
        files_form.addRow(*_row(
            "On start", self.reopen_last_box,
            "Uncheck for a fresh empty window every launch, whatever "
            "was open last."))
        backups_note = QLabel(
            "Backup folder and how many backups to keep are decisions "
            "about one manuscript — they live with the book (inspector), "
            "not here.")
        backups_note.setWordWrap(True)
        files_form.addRow(backups_note)
        self._add_category("Files & saving", files_page)

        paste_page = self._page("Pasting")
        paste_layout = QVBoxLayout(paste_page)
        paste_layout.addWidget(QLabel("When pasting, keep:"))
        self.paste_fonts = QCheckBox("Fonts and colours")
        self.paste_paragraphs = QCheckBox(
            "Paragraph formatting — indents, line spacing, margins, "
            "blank-line structure")
        self.paste_inline = QCheckBox("Bold, italics and underline")
        self.paste_alignment = QCheckBox("Alignment")
        self.paste_fonts.setChecked(paste["fonts"])
        self.paste_paragraphs.setChecked(paste["paragraphs"])
        self.paste_inline.setChecked(paste["inline"])
        self.paste_alignment.setChecked(paste["alignment"])
        for box in (self.paste_fonts, self.paste_paragraphs,
                    self.paste_inline, self.paste_alignment):
            paste_layout.addWidget(box)
        paste_note = QLabel(
            "Unchecked items are stripped when you paste. Ctrl+Shift+V "
            "always pastes as plain text, and Edit → Paste and Keep "
            "All Formatting ignores every box.")
        paste_note.setWordWrap(True)
        paste_layout.addWidget(paste_note)
        paste_layout.addStretch()
        self._add_category("Pasting", paste_page)

        links_page = self._page("Links & export")
        links_form = QFormLayout(links_page)
        self.link_default_box = QComboBox()
        for label, value in LINK_POLICY_CHOICES:
            self.link_default_box.addItem(label, value)
        self.link_default_box.setCurrentIndex(max(
            0, self.link_default_box.findData(
                str(store.value("link_policy/default", DEFAULT_LINK_POLICY)))))
        links_form.addRow(*_row(
            "Unpublished links", self.link_default_box,
            "What a [[link]] pointing outside the current export "
            "becomes. This is the default for new work; each book can "
            "override it in the inspector, and the book's setting wins."))
        self.related_box = QCheckBox("Show the Mentions / Mentioned by scan")
        self.related_box.setChecked(
            bool(store.value("related/enabled", True, type=bool)))
        links_form.addRow(*_row(
            "Related files", self.related_box,
            "The inspector's auto-link scan: documents whose titles this "
            "one's prose names, and documents naming this one. Helpful in "
            "some projects, noise in others — switch it off and the "
            "section disappears entirely."))
        author_default_note = QLabel(
            "A new project's Author starts empty — set the book's author "
            "in the inspector, where it travels with the manuscript.")
        author_default_note.setWordWrap(True)
        links_form.addRow(author_default_note)
        self._add_category("Links & export", links_page)

        active_ai = ai_settings or ai.load_settings()
        ai_page = self._page("AI")
        ai_layout = QVBoxLayout(ai_page)
        ai_form = QFormLayout()
        self.ai_endpoint_edit = QLineEdit(active_ai.endpoint)
        self.ai_model_edit = QLineEdit(active_ai.model)
        self.ai_model_edit.setPlaceholderText("e.g. qwen2.5:7b")
        self.ai_key_edit = QLineEdit(active_ai.key)
        self.ai_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_key_edit.setPlaceholderText("empty for local servers")
        ai_form.addRow("Endpoint:", self.ai_endpoint_edit)
        ai_form.addRow("Model:", self.ai_model_edit)
        ai_form.addRow("API key:", self.ai_key_edit)
        ai_layout.addLayout(ai_form)
        ai_note = QLabel(
            "Used by AI → Continue Scene and Proofread Selection. The "
            "answer is always applied as a tracked change, never written "
            "into the manuscript directly — and proofreading asks for "
            "minimal edits: bloopers, not prose.\n"
            "Local model (nothing leaves your computer): install Ollama, "
            "then  ollama pull <model-name>  (e.g. ollama pull qwen2.5:7b). "
            "The default endpoint http://localhost:11434/v1 already "
            "matches Ollama.\n"
            "Read this before you rely on it: a model that fits an "
            "ordinary computer is a very small model, and small models "
            "are error-prone — they manage typos and simple bloopers, "
            "not unsupervised work, and prompt wording will need tuning."
        )
        ai_note.setWordWrap(True)
        ai_layout.addWidget(ai_note)
        self.prompt_toggle = QPushButton("Proofreading prompt — advanced")
        self.prompt_toggle.setCheckable(True)
        self.prompt_toggle.setStyleSheet("text-align: left;")
        self.prompt_toggle.toggled.connect(self._toggle_prompt_editor)
        ai_layout.addWidget(self.prompt_toggle)
        prompt_warning = QLabel(
            "Do not edit unless you know what you are doing: this text "
            "is the contract with the model — bloopers, minimal edits, "
            "never a rewrite. Widening it invites the model to polish "
            "your prose behind your back.")
        prompt_warning.setWordWrap(True)
        prompt_warning.setVisible(False)
        ai_layout.addWidget(prompt_warning)
        self.prompt_warning = prompt_warning
        self.ai_prompt_edit = QTextEdit()
        self.ai_prompt_edit.setPlainText(
            active_ai.prompt or ai.PROOFREAD_SYSTEM)
        self.ai_prompt_edit.setAcceptRichText(False)
        self.ai_prompt_edit.setVisible(False)
        self.ai_prompt_edit.setMinimumHeight(120)
        ai_layout.addWidget(self.ai_prompt_edit)
        ai_layout.addStretch()
        self._add_category("AI", ai_page)

        active_tts = tts_settings or tts.load_settings()
        tts_page = self._page("Read aloud")
        tts_form = QFormLayout(tts_page)
        self.tts_voice_box = QComboBox()
        for name in (tts_voices or []):
            self.tts_voice_box.addItem(name)
        if active_tts.voice:
            index = self.tts_voice_box.findText(active_tts.voice)
            if index >= 0:
                self.tts_voice_box.setCurrentIndex(index)
        tts_form.addRow(*_row(
            "Voice", self.tts_voice_box,
            "Speak → Read Aloud reads the selection, else the whole "
            "scene, in this voice. The list is whatever this system "
            "offers; an empty list means no speech engine is installed."))
        self.tts_rate_slider = QSlider(Qt.Horizontal)
        self.tts_rate_slider.setRange(-100, 100)
        self.tts_rate_slider.setValue(
            round(max(-1.0, min(1.0, active_tts.rate)) * 100))
        self.tts_rate_label = QLabel()
        self._update_rate_label()
        self.tts_rate_slider.valueChanged.connect(self._update_rate_label)
        tts_form.addRow(*_row(
            "Rate", self.tts_rate_slider,
            "Left is slower, right is faster; ×1.00 is the voice's "
            "normal pace."))
        tts_form.addRow(self.tts_rate_label)
        self._add_category("Read aloud", tts_page)

        advanced_page = self._page("Advanced")
        advanced_layout = QVBoxLayout(advanced_page)
        config_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppConfigLocation)
        open_config = QPushButton("Open config folder")
        open_config.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(config_dir)))
        advanced_layout.addWidget(open_config)
        where = QLabel(
            f"Everything in this dialog is stored in {config_dir} "
            "(QSettings). Copy that folder to move a setup to another "
            "machine.")
        where.setWordWrap(True)
        advanced_layout.addWidget(where)
        advanced_layout.addStretch()
        self._add_category("Advanced", advanced_page)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.categories.setCurrentRow(0)

    def _page(self, title: str) -> QWidget:
        page = QWidget()
        self.pages.addWidget(page)
        return page

    def _add_category(self, title: str, page: QWidget) -> None:
        item = QListWidgetItem(title)
        item.setData(Qt.UserRole, self.pages.indexOf(page))
        self.categories.addItem(item)

    def _show_category(self, row: int) -> None:
        if row < 0:
            return
        item = self.categories.item(row)
        if item is not None:
            self.pages.setCurrentIndex(item.data(Qt.UserRole))

    def _filter_categories(self, text: str) -> None:
        needle = text.strip().lower()
        for index in range(self.categories.count()):
            item = self.categories.item(index)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _update_size_sample(self, value: int) -> None:
        self.size_label.setText(f"{value} pt")
        font = QFont(self.size_sample.font())
        font.setPointSize(value)
        self.size_sample.setFont(font)

    def _toggle_prompt_editor(self, visible: bool) -> None:
        self.ai_prompt_edit.setVisible(visible)
        self.prompt_warning.setVisible(visible)

    def _update_rate_label(self) -> None:
        self.tts_rate_label.setText(
            f"×{self.tts_rate_slider.value() / 100.0:.2f}")
