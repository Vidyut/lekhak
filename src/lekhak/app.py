"""The Qt application: one window over one Project.

Everything user-visible lives here. The window owns a Project and a set of
views onto it; the Project owns storage. Nothing in this module writes
files or SQL directly — it calls into Project, which is where the storage
contract is enforced.

Layout of the window:

    left   binder tree (QTreeWidget, drag to reorder)
    center tabbed views: editor / corkboard / outliner
    right  inspector: synopsis, word target, metadata

Three rules that govern how views and Project interact, and where the
tricky parts of this file come from:

- Saving is debounced. The editor's textChanged starts a timer; when it
  fires, save_current() writes through Project. The binder, outliner and
  corkboard are refreshed from Project after any change, never updated in
  place — Project is the single source of truth.
- Display must never leak into storage. Binder numbers, resolved wiki
  links and interface fonts are all rendered on the way *out* (on load,
  on paint) and stripped on the way back in (canonicalize_links() before
  write_content()). Anything that reads a widget's text back into the
  project has to undo the display layer first.
- The editor font is pinned, not inherited. Interface font preferences
  change QApplication's font; the writing editor keeps an explicit 12 pt
  so preference changes never round-trip into document HTML.

Dialogs at the top of the file are self-contained: each gathers input and
returns it, with no Project access. MainWindow methods that open them
apply the result.
"""

import json
import re
import sys
from html import escape
from pathlib import Path

from PySide6.QtCore import QDate, QSize, QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction, QDesktopServices, QFont, QKeySequence, QTextBlockFormat,
    QTextCharFormat, QTextCursor, QTextDocument, QTextDocumentFragment,
    QTextFormat, QTextListFormat,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QFileDialog, QFontComboBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QMenu,
    QMainWindow, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QSplitter, QStatusBar, QStyle, QTabWidget,
    QTableWidget, QTableWidgetItem, QTextEdit, QToolBar, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .project import EXPORT_KINDS, Project
from .templates import (
    copy_template_set, discover_template_sets, project_template_root,
)


class FindReplaceDialog(QDialog):
    def __init__(self, editor: QTextEdit, parent=None) -> None:
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle("Find and Replace")
        self.find_text = QLineEdit()
        self.replace_text = QLineEdit()
        form = QFormLayout(self)
        form.addRow("Find:", self.find_text)
        form.addRow("Replace with:", self.replace_text)
        controls = QHBoxLayout()
        find_next = QPushButton("Find Next")
        replace = QPushButton("Replace")
        replace_all = QPushButton("Replace All")
        controls.addWidget(find_next)
        controls.addWidget(replace)
        controls.addWidget(replace_all)
        form.addRow(controls)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        form.addRow(buttons)
        find_next.clicked.connect(self.find_next)
        replace.clicked.connect(self.replace_one)
        replace_all.clicked.connect(self.replace_everywhere)
        self.find_text.returnPressed.connect(self.find_next)

    def find_next(self) -> bool:
        needle = self.find_text.text()
        if not needle:
            return False
        if self.editor.find(needle):
            return True
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.editor.setTextCursor(cursor)
        return self.editor.find(needle)

    def replace_one(self) -> None:
        cursor = self.editor.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == self.find_text.text():
            cursor.insertText(self.replace_text.text())
        self.find_next()

    def replace_everywhere(self) -> None:
        needle = self.find_text.text()
        if not needle:
            return
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.Start)
        self.editor.setTextCursor(cursor)
        count = 0
        while self.editor.find(needle):
            self.editor.textCursor().insertText(self.replace_text.text())
            count += 1
        cursor.endEditBlock()
        QMessageBox.information(self, "Replace All", f"Replaced {count} occurrence(s).")


class ProjectReplaceDialog(QDialog):
    def __init__(self, project: Project, on_goto=None, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.on_goto = on_goto
        self.setWindowTitle("Replace in Project")
        self.resize(640, 480)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.find_text = QLineEdit()
        self.replace_text = QLineEdit()
        form.addRow("Find:", self.find_text)
        form.addRow("Replace with:", self.replace_text)
        layout.addLayout(form)
        options = QHBoxLayout()
        self.regex_box = QCheckBox("Regular expressions")
        self.case_box = QCheckBox("Ignore case")
        self.case_box.setChecked(True)
        self.titles_box = QCheckBox("Titles")
        self.titles_box.setChecked(True)
        self.synopses_box = QCheckBox("Synopses")
        self.synopses_box.setChecked(True)
        for box in (self.regex_box, self.case_box, self.titles_box, self.synopses_box):
            options.addWidget(box)
        options.addStretch(1)
        layout.addLayout(options)
        self.preview = QListWidget()
        layout.addWidget(self.preview, 1)
        self.count_label = QLabel("")
        layout.addWidget(self.count_label)
        buttons = QDialogButtonBox()
        self.find_button = buttons.addButton("Find", QDialogButtonBox.ActionRole)
        self.replace_button = buttons.addButton("Replace All", QDialogButtonBox.ActionRole)
        buttons.addButton(QDialogButtonBox.Close)
        layout.addWidget(buttons)
        self.find_button.clicked.connect(self.refresh_preview)
        self.replace_button.clicked.connect(self.replace_all)
        buttons.rejected.connect(self.close)
        self.find_text.returnPressed.connect(self.refresh_preview)
        self.preview.itemDoubleClicked.connect(self._goto_hit)
        for box in (self.regex_box, self.case_box, self.titles_box, self.synopses_box):
            box.stateChanged.connect(self.refresh_preview)

    def _goto_hit(self, item: QListWidgetItem) -> None:
        if self.on_goto:
            self.on_goto(item.data(Qt.UserRole))

    def _fields(self) -> set[str]:
        fields = {"content"}
        if self.titles_box.isChecked():
            fields.add("title")
        if self.synopses_box.isChecked():
            fields.add("synopsis")
        return fields

    def refresh_preview(self) -> None:
        self.preview.clear()
        self.count_label.setText("")
        query = self.find_text.text()
        if not query:
            return
        try:
            hits = self.project.search_snippets(
                query, regex=self.regex_box.isChecked(),
                ignore_case=self.case_box.isChecked(), fields=self._fields(),
            )
        except re.error as error:
            self.count_label.setText(f"Invalid pattern: {error}")
            return
        for document, field, snippet in hits:
            item = QListWidgetItem(f"{document.title} · {field}: {snippet}")
            item.setData(Qt.UserRole, document.id)
            self.preview.addItem(item)
        self.count_label.setText(f"{len(hits)} match(es) (preview capped at 500)")

    def replace_all(self) -> None:
        query = self.find_text.text()
        if not query:
            return
        try:
            self.project.search_snippets(query, regex=self.regex_box.isChecked(),
                                         ignore_case=self.case_box.isChecked())
        except re.error as error:
            QMessageBox.warning(self, "Replace in Project", f"Invalid pattern: {error}")
            return
        answer = QMessageBox.question(
            self, "Replace in Project",
            "Replace every match in the whole project? Undo is not available "
            "for project-wide replaces.",
        )
        if answer != QMessageBox.Yes:
            return
        counts = self.project.replace(
            query, self.replace_text.text(), regex=self.regex_box.isChecked(),
            ignore_case=self.case_box.isChecked(),
            in_titles=self.titles_box.isChecked(),
            in_synopses=self.synopses_box.isChecked(),
        )
        QMessageBox.information(
            self, "Replace in Project",
            f"Replaced {counts['replacements']} occurrence(s) in "
            f"{counts['documents']} document(s).",
        )
        self.refresh_preview()


class PreferencesDialog(QDialog):
    def __init__(self, font_size: int, paste: dict[str, bool], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 24)
        self.size_spin.setValue(font_size)
        self.size_spin.setSuffix(" pt")
        form.addRow("Interface font size:", self.size_spin)
        layout.addLayout(form)
        note = QLabel(
            "Applies to menus, binder, corkboard, outliner and panels. "
            "The writing editor keeps its own size and zoom."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        layout.addWidget(QLabel("When pasting, keep:"))
        self.paste_fonts = QCheckBox("Fonts and colours")
        self.paste_paragraphs = QCheckBox(
            "Paragraph formatting — indents, line spacing, margins, "
            "blank-line structure"
        )
        self.paste_inline = QCheckBox("Bold, italics and underline")
        self.paste_alignment = QCheckBox("Alignment")
        self.paste_fonts.setChecked(paste["fonts"])
        self.paste_paragraphs.setChecked(paste["paragraphs"])
        self.paste_inline.setChecked(paste["inline"])
        self.paste_alignment.setChecked(paste["alignment"])
        for box in (self.paste_fonts, self.paste_paragraphs,
                    self.paste_inline, self.paste_alignment):
            layout.addWidget(box)
        paste_note = QLabel(
            "Unchecked items are stripped when you paste. Ctrl+Shift+V "
            "always pastes as plain text, and Edit → Paste and Keep "
            "All Formatting ignores every box."
        )
        paste_note.setWordWrap(True)
        layout.addWidget(paste_note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class MetadataDialog(QDialog):
    def __init__(self, entries: dict[str, tuple[str, str, list[str]]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Document Metadata")
        self.resize(520, 360)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Add any fields you need, such as POV, Location, Date, or Status."))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Field", "Type", "Allowed options", "Value"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        for key, entry in entries.items():
            value, value_type, options = entry
            self._append_row(key, value, value_type, options)
        controls = QHBoxLayout()
        add_button = QPushButton("Add field")
        remove_button = QPushButton("Remove selected")
        add_button.clicked.connect(lambda: self._append_row("", "", "text", []))
        remove_button.clicked.connect(self._remove_selected)
        controls.addWidget(add_button)
        controls.addWidget(remove_button)
        controls.addStretch()
        layout.addLayout(controls)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _append_row(self, key: str, value: str, value_type: str,
                    options: list[str]) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(key))
        type_box = QComboBox()
        type_box.addItem("Text", "text")
        type_box.addItem("Date", "date")
        type_box.addItem("Dropdown", "choice")
        type_box.setCurrentIndex({"text": 0, "date": 1, "choice": 2}.get(value_type, 0))
        self.table.setCellWidget(row, 1, type_box)
        options_editor = QLineEdit(", ".join(options))
        options_editor.setPlaceholderText("Draft, Revised, Final")
        options_editor.setEnabled(value_type == "choice")
        self.table.setCellWidget(row, 2, options_editor)
        self._set_value_widget(row, value_type, value, options)
        type_box.currentIndexChanged.connect(lambda _index, box=type_box: self._type_changed(box))
        options_editor.editingFinished.connect(
            lambda editor=options_editor: self._options_changed(editor)
        )

    def _type_changed(self, type_box: QComboBox) -> None:
        row = self.table.indexAt(type_box.pos()).row()
        if row < 0:
            return
        value = self._row_value(row)
        options_editor = self.table.cellWidget(row, 2)
        options_editor.setEnabled(type_box.currentData() == "choice")
        self._set_value_widget(row, type_box.currentData(), value, self._row_options(row))

    def _options_changed(self, options_editor: QLineEdit) -> None:
        row = self.table.indexAt(options_editor.pos()).row()
        if row >= 0 and self.table.cellWidget(row, 1).currentData() == "choice":
            self._set_value_widget(row, "choice", self._row_value(row), self._row_options(row))

    def _row_options(self, row: int) -> list[str]:
        editor = self.table.cellWidget(row, 2)
        return list(dict.fromkeys(
            option.strip() for option in editor.text().split(",") if option.strip()
        ))

    def _row_value(self, row: int) -> str:
        widget = self.table.cellWidget(row, 3)
        if isinstance(widget, QDateEdit):
            return widget.date().toString(Qt.ISODate)
        if isinstance(widget, QComboBox):
            return widget.currentText()
        item = self.table.item(row, 3)
        return item.text() if item else ""

    def _set_value_widget(self, row: int, value_type: str, value: str,
                          options: list[str]) -> None:
        self.table.removeCellWidget(row, 3)
        self.table.takeItem(row, 3)
        if value_type == "date":
            editor = QDateEdit()
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("dd MMM yyyy")
            date = QDate.fromString(value, Qt.ISODate)
            editor.setDate(date if date.isValid() else QDate.currentDate())
            self.table.setCellWidget(row, 3, editor)
        elif value_type == "choice":
            editor = QComboBox()
            editor.addItems(options)
            if value in options:
                editor.setCurrentText(value)
            self.table.setCellWidget(row, 3, editor)
        else:
            self.table.setItem(row, 3, QTableWidgetItem(value))

    def _remove_selected(self) -> None:
        for row in sorted({item.row() for item in self.table.selectedItems()}, reverse=True):
            self.table.removeRow(row)

    def values_types_options(self) -> tuple[
        dict[str, str], dict[str, str], dict[str, list[str]]
    ]:
        values, value_types, options = {}, {}, {}
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            key = key_item.text().strip() if key_item else ""
            if key:
                type_box = self.table.cellWidget(row, 1)
                value_type = type_box.currentData()
                value_types[key] = value_type
                values[key] = self._row_value(row)
                options[key] = self._row_options(row) if value_type == "choice" else []
        return values, value_types, options


class ExportOptionsDialog(QDialog):
    def __init__(self, documents, template_sets, current_set_name: str,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Options")
        self.resize(620, 480)
        self.template_sets = template_sets
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Include these chapters and scenes:"))
        self.documents = QListWidget()
        for document in documents:
            prefix = document.kind.capitalize()
            item = QListWidgetItem(f"{prefix}: {document.title}")
            item.setData(Qt.UserRole, document.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.documents.addItem(item)
        layout.addWidget(self.documents)
        selection_buttons = QHBoxLayout()
        select_all = QPushButton("Select all")
        select_none = QPushButton("Select none")
        select_all.clicked.connect(lambda: self._check_all(Qt.Checked))
        select_none.clicked.connect(lambda: self._check_all(Qt.Unchecked))
        selection_buttons.addWidget(select_all)
        selection_buttons.addWidget(select_none)
        selection_buttons.addStretch()
        layout.addLayout(selection_buttons)
        layout.addWidget(QLabel(
            "Template set — slot files with ${Title}, ${Content}, "
            "${Synopsis}, ${WordCount}, ${ChapterNumber}, ${SceneNumber}, "
            "${WordsTotal}, ${Metadata.Key}, and ${Entries} in toc_page"
        ))
        set_row = QHBoxLayout()
        self.set_box = QComboBox()
        for template_set in template_sets:
            self.set_box.addItem(template_set.name)
            if template_set.name == current_set_name:
                self.set_box.setCurrentIndex(self.set_box.count() - 1)
        set_row.addWidget(self.set_box)
        new_set = QPushButton("New set…")
        new_set.clicked.connect(self._new_set)
        set_row.addWidget(new_set)
        open_folder = QPushButton("Open folder")
        open_folder.clicked.connect(self._open_folder)
        set_row.addWidget(open_folder)
        layout.addLayout(set_row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _check_all(self, state) -> None:
        for index in range(self.documents.count()):
            self.documents.item(index).setCheckState(state)

    def selected_ids(self) -> set[str]:
        return {
            self.documents.item(index).data(Qt.UserRole)
            for index in range(self.documents.count())
            if self.documents.item(index).checkState() == Qt.Checked
        }

    def selected_template_set(self):
        name = self.set_box.currentText()
        return next(s for s in self.template_sets if s.name == name)

    def _new_set(self) -> None:
        project = getattr(self.parent(), "project", None)
        if not project:
            return
        name, accepted = QInputDialog.getText(self, "New template set", "Set name:")
        if not accepted or not name.strip():
            return
        try:
            current = self.selected_template_set()
            created = copy_template_set(current, name.strip(), project.root)
        except (ValueError, FileExistsError) as error:
            QMessageBox.warning(self, "Cannot create set", str(error))
            return
        self.template_sets = discover_template_sets(project.root)
        self.set_box.clear()
        for template_set in self.template_sets:
            self.set_box.addItem(template_set.name)
            if template_set.name == created.name:
                self.set_box.setCurrentIndex(self.set_box.count() - 1)

    def _open_folder(self) -> None:
        project = getattr(self.parent(), "project", None)
        if not project:
            return
        root = project_template_root(project.root)
        root.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(root)))


class ColumnPickerDialog(QDialog):
    """Choose which columns the outliner shows: built-ins plus any metadata
    key used in the project."""

    def __init__(self, available: list[tuple[str, str]], selected: list[str],
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Outliner Columns")
        self.resize(360, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Show these columns (Title is always shown):"))
        self.columns = QListWidget()
        for column_id, label in available:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, column_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if column_id in selected else Qt.Unchecked)
            if column_id == "title":
                item.setCheckState(Qt.Checked)
                item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
            self.columns.addItem(item)
        layout.addWidget(self.columns)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_columns(self) -> list[str]:
        chosen = ["title"]
        for index in range(self.columns.count()):
            item = self.columns.item(index)
            column_id = item.data(Qt.UserRole)
            if column_id != "title" and item.checkState() == Qt.Checked:
                chosen.append(column_id)
        return chosen


def load_paste_prefs() -> dict[str, bool]:
    """The paste policy from Preferences, read on every paste.

    Read live rather than cached, so ticking a box takes effect on the
    very next paste with no restart.
    """
    settings = QSettings()
    return {
        "fonts": settings.value("paste/fonts", False, type=bool),
        "paragraphs": settings.value("paste/paragraphs", False, type=bool),
        "inline": settings.value("paste/inline", True, type=bool),
        "alignment": settings.value("paste/alignment", True, type=bool),
    }


def _scrub_char_format(source: QTextCharFormat, keep_fonts: bool,
                       keep_inline: bool) -> QTextCharFormat:
    """Rebuild one fragment's format holding only what the policy keeps.

    Rebuilt from a fresh format instead of deleting properties: a fresh
    QTextCharFormat already carries exactly the editor's defaults, and it
    sidesteps the property enums PySide6 doesn't expose by name. Image
    objects come back untouched — their format *is* the image, so a
    filtered copy would leave a missing-glyph box. Anchors ride along
    whatever the flags say: a link is content, not skin.
    """
    if source.objectType() != QTextFormat.NoObject:
        return source
    result = QTextCharFormat()
    if keep_inline:
        result.setFontWeight(source.fontWeight())
        result.setFontItalic(source.fontItalic())
        result.setFontUnderline(source.fontUnderline())
    if keep_fonts:
        families = source.fontFamilies()
        if families:
            result.setFontFamilies(families)
        if source.fontPointSize() > 0:
            result.setFontPointSize(source.fontPointSize())
        foreground = source.foreground()
        if foreground.style() != Qt.BrushStyle.NoBrush:
            result.setForeground(foreground)
        background = source.background()
        if background.style() != Qt.BrushStyle.NoBrush:
            result.setBackground(background)
    if source.isAnchor():
        result.setAnchor(True)
        href = source.anchorHref()
        if href:
            result.setAnchorHref(href)
    return result


def _scrub_block_format(source: QTextBlockFormat, keep_paragraphs: bool,
                        keep_alignment: bool) -> QTextBlockFormat:
    """Rebuild one block's format: editor defaults plus only what's kept.

    The fresh format *is* the default policy — a Word document's 72 pt
    "before paragraph" margin and its line height are what make a paste
    land at double height, and they all live on the block format.
    """
    result = QTextBlockFormat()
    if keep_alignment:
        alignment = source.alignment()
        if int(alignment):
            result.setAlignment(alignment)
    if keep_paragraphs:
        result.setTopMargin(source.topMargin())
        result.setBottomMargin(source.bottomMargin())
        result.setLeftMargin(source.leftMargin())
        result.setRightMargin(source.rightMargin())
        result.setIndent(source.indent())
        result.setTextIndent(source.textIndent())
        line_height = source.lineHeight()
        if line_height > 0:
            result.setLineHeight(line_height, source.lineHeightType())
    return result


def sanitize_pasted_html(html: str, *, fonts: bool, paragraphs: bool,
                         inline: bool, alignment: bool) -> QTextDocument:
    """Turn clipboard HTML into a scratch document that obeys the paste policy.

    Why: clipboard HTML drags its source application along — font families
    and sizes, indents, line spacing, block margins, blank-paragraph
    scaffolding — and lands in the manuscript as visual chaos. The pass:

        html ── setHtml ──▶ scratch document
              ── read ──▶ record every fragment (start, length, scrubbed
                          format) and every block (start, source format)
              ── apply ──▶ write the recorded formats back. Read first,
                          edit second: editing invalidates QTextBlock
                          handles, so the records hold plain integers and
                          implicitly-shared format copies.
              ── collapse ──▶ (unless paragraphs are kept) delete
                          blank-paragraph runs — leading and trailing runs
                          vanish, interior runs shrink to one blank line

    Object fragments (images) pass through with their format intact and
    never count as blank. QMimeData.html() decodes exactly what Qt's own
    paste path decodes, so there is no charset handling to redo.
    """
    document = QTextDocument()
    document.setHtml(html)
    character_ops: list[tuple[int, int, QTextCharFormat]] = []
    block_ops: list[tuple[int, QTextBlockFormat]] = []
    blank: list[bool] = []
    block = document.firstBlock()
    while block.isValid():
        block_ops.append((block.position(), block.blockFormat()))
        has_object = False
        fragment = block.begin()
        while not fragment.atEnd():
            item = fragment.fragment()
            if item.charFormat().objectType() != QTextFormat.NoObject:
                has_object = True
            else:
                character_ops.append(
                    (item.position(), item.length(),
                     _scrub_char_format(item.charFormat(), fonts, inline)))
            fragment += 1
        text = block.text()
        blank.append(not has_object and not text.replace("\u2028", "").strip())
        block = block.next()
    cursor = QTextCursor(document)
    cursor.beginEditBlock()
    for position, length, char_format in character_ops:
        cursor.setPosition(position)
        cursor.setPosition(position + length, QTextCursor.KeepAnchor)
        cursor.setCharFormat(char_format)
    for position, source_format in block_ops:
        cursor.setPosition(position)
        cursor.setBlockFormat(
            _scrub_block_format(source_format, paragraphs, alignment))
    cursor.endEditBlock()
    if not paragraphs:
        _collapse_blank_blocks(document, blank)
    return document


def _collapse_blank_blocks(document: QTextDocument, blank: list[bool]) -> None:
    """Delete blank-paragraph noise from the scratch document.

    A leading run of blanks (with real text after it) goes entirely, a
    trailing run goes entirely, an interior run shrinks to one blank line,
    and an all-blank document is left whole. Deletions run back to front
    and re-walk the live document each step: blocks before the one being
    cut never move, while the block *after* a cut is read fresh — by the
    time a trailing run is half-eaten its last survivor really is the tail,
    which is exactly when the separator in front of it has to go.
    """
    count = len(blank)
    if count < 2 or not any(blank) or all(blank):
        return
    doomed: list[int] = []
    index = 0
    while index < count:
        if not blank[index]:
            index += 1
            continue
        end = index
        while end < count and blank[end]:
            end += 1
        if index == 0 or end == count:
            # Leading run (real text follows) or trailing run: all of it.
            doomed.extend(range(index, end))
        else:
            # Interior run: keep one blank line between the paragraphs.
            doomed.extend(range(index + 1, end))
        index = end
    cursor = QTextCursor(document)
    cursor.beginEditBlock()
    for index in sorted(doomed, reverse=True):
        block = document.findBlockByNumber(index)
        following = block.next()
        if following.isValid():
            cursor.setPosition(block.position())
            cursor.setPosition(following.position(), QTextCursor.KeepAnchor)
        else:
            # Tail block: swallow the separator in front, or the emptied
            # block would survive as the new tail.
            cursor.setPosition(block.position() - 1)
            cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
    cursor.endEditBlock()


class LinkEditor(QTextEdit):
    """QTextEdit that reports internal `lekhak://` anchor clicks and puts
    pasted HTML through the paste policy.

    Plain QTextEdit has no link-click support (that is QTextBrowser's API),
    so a click on an anchor is turned into a signal here instead, and its
    raw HTML import is replaced: Qt would happily paste a Word document's
    fonts and margins straight into the manuscript.
    """

    internal_link_clicked = Signal(str)

    def insertFromMimeData(self, source) -> None:
        """Paste under the Preferences policy; let Qt handle the rest.

        Clipboard HTML goes through `sanitize_pasted_html`; plain text,
        images and anything carrying no HTML fall through to Qt's own
        import, which is already correct for them.
        """
        if source is None:
            return
        html = source.html() if source.hasHtml() else ""
        if not html:
            super().insertFromMimeData(source)
            return
        prefs = load_paste_prefs()
        self._insert_scratch(sanitize_pasted_html(
            html,
            fonts=prefs["fonts"],
            paragraphs=prefs["paragraphs"],
            inline=prefs["inline"],
            alignment=prefs["alignment"],
        ))

    def paste_as_plain_text(self) -> None:
        """Ctrl+Shift+V: take only the clipboard's text, never its format.

        QTextEdit exposes no plain-paste entry of its own, and this is
        what the shortcut has always meant: the words, in whatever
        formatting already surrounds the caret. Quirky sources can ship
        HTML with no text/plain twin — the words are still recoverable,
        and plain paste has to stay plain even then.
        """
        source = QApplication.clipboard().mimeData()
        if source is None:
            return
        text = source.text()
        if not text and source.hasHtml():
            scratch = QTextDocument()
            scratch.setHtml(source.html())
            text = scratch.toPlainText()
        if not text:
            self.paste()  # images and other non-text take the normal path
            return
        self.insertPlainText(text)

    def paste_keep_all(self) -> None:
        """Paste keeping everything — fonts, spacing, colours, alignment.

        The deliberate escape hatch (feeds 1.11): when a passage is pasted
        *for* its formatting, the policy must not touch it. No HTML means
        there is nothing to keep, so the regular paste path runs instead.
        """
        source = QApplication.clipboard().mimeData()
        html = source.html() if source is not None and source.hasHtml() else ""
        if not html:
            self.paste()
            return
        document = QTextDocument()
        document.setHtml(html)
        self._insert_scratch(document)

    def _insert_scratch(self, document: QTextDocument) -> None:
        """Drop a prepared scratch document in at the caret.

        insertFragment only moves the cursor it is given, never the
        widget's own, so the caret is handed back explicitly — otherwise
        typing would carry on at the pre-paste spot. One edit block keeps
        the whole paste a single undo step.
        """
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.insertFragment(QTextDocumentFragment(document))
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def mousePressEvent(self, event) -> None:
        anchor = self.anchorAt(event.position().toPoint())
        if anchor.startswith("lekhak://"):
            self.internal_link_clicked.emit(anchor)
            return
        super().mousePressEvent(event)


# The toolbar's six built-in paragraph styles as signatures — the seed
# list user styles join and may replace by name (1.11). Each signature
# carries exactly what apply_paragraph_style always set, made explicit so
# stored styles and seeds round-trip through the same code; margins and
# indent ride along on every seed so switching styles resets them instead
# of leaking the previous style's. Alignment, underline, family and
# line-height are deliberately absent: the built-ins never touched them.
SEED_STYLES: dict[str, dict] = {
    "Paragraph": {"size": 12.0, "weight": int(QFont.Normal),
                  "italic": False, "top_margin": 0.0, "bottom_margin": 0.0,
                  "left_margin": 0.0, "right_margin": 0.0, "indent": 0,
                  "text_indent": 0.0},
    "Title": {"size": 28.0, "weight": int(QFont.Bold), "italic": False,
              "top_margin": 0.0, "bottom_margin": 0.0, "left_margin": 0.0,
              "right_margin": 0.0, "indent": 0, "text_indent": 0.0},
    "Heading 1": {"size": 22.0, "weight": int(QFont.Bold), "italic": False,
                  "top_margin": 0.0, "bottom_margin": 0.0, "left_margin": 0.0,
                  "right_margin": 0.0, "indent": 0, "text_indent": 0.0},
    "Heading 2": {"size": 18.0, "weight": int(QFont.Bold), "italic": False,
                  "top_margin": 0.0, "bottom_margin": 0.0, "left_margin": 0.0,
                  "right_margin": 0.0, "indent": 0, "text_indent": 0.0},
    "Heading 3": {"size": 15.0, "weight": int(QFont.Bold), "italic": False,
                  "top_margin": 0.0, "bottom_margin": 0.0, "left_margin": 0.0,
                  "right_margin": 0.0, "indent": 0, "text_indent": 0.0},
    "Quote": {"size": 12.0, "weight": int(QFont.Normal), "italic": True,
              "top_margin": 0.0, "bottom_margin": 0.0, "left_margin": 32.0,
              "right_margin": 32.0, "indent": 0, "text_indent": 0.0},
}


def capture_paragraph_signature(cursor: QTextCursor) -> dict:
    """Snapshot the formatting of the paragraph under the cursor.

    The signature a saved style is: what you see is what a later
    application reproduces. The character side comes from the format at
    the caret (a mixed paragraph gives the part you are standing in);
    underline, family and line-height are recorded only when actually
    present, so a paragraph wearing none of them compares equal to the
    built-in seed it matches. Size falls back to the 12 pt the editor
    writes in when nothing has set one yet.
    """
    char_format = cursor.charFormat()
    block_format = cursor.blockFormat()
    signature = {
        "size": char_format.fontPointSize() or 12.0,
        "weight": int(char_format.fontWeight()),
        "italic": bool(char_format.fontItalic()),
        "top_margin": block_format.topMargin(),
        "bottom_margin": block_format.bottomMargin(),
        "left_margin": block_format.leftMargin(),
        "right_margin": block_format.rightMargin(),
        "indent": int(block_format.indent()),
        "text_indent": block_format.textIndent(),
        "alignment": int(block_format.alignment() or 0),
    }
    if char_format.fontUnderline():
        signature["underline"] = True
    families = char_format.fontFamilies()
    if families:
        signature["family"] = str(families[0])
    line_height = block_format.lineHeight()
    if line_height > 0:
        signature["line_height"] = [line_height, int(block_format.lineHeightType())]
    return signature


def style_signature_formats(signature: dict) -> tuple[QTextBlockFormat, QTextCharFormat]:
    """Rebuild the Qt formats a stored style signature stands for.

    A signature is explicit about what it does NOT touch: keys it doesn't
    carry are never written, which is how the built-in seeds leave
    alignment, underline, family and line-height exactly as they found
    them while still fully resetting size, weight, italic and margins.
    """
    char_format = QTextCharFormat()
    char_format.setFontPointSize(signature.get("size", 12.0))
    char_format.setFontWeight(signature.get("weight", int(QFont.Normal)))
    char_format.setFontItalic(bool(signature.get("italic", False)))
    if "underline" in signature:
        char_format.setFontUnderline(bool(signature["underline"]))
    family = signature.get("family")
    if family:
        char_format.setFontFamilies([family])
    block_format = QTextBlockFormat()
    if signature.get("alignment"):
        block_format.setAlignment(Qt.Alignment(signature["alignment"]))
    block_format.setTopMargin(signature.get("top_margin", 0.0))
    block_format.setBottomMargin(signature.get("bottom_margin", 0.0))
    block_format.setLeftMargin(signature.get("left_margin", 0.0))
    block_format.setRightMargin(signature.get("right_margin", 0.0))
    block_format.setIndent(signature.get("indent", 0))
    block_format.setTextIndent(signature.get("text_indent", 0.0))
    line_height = signature.get("line_height")
    if line_height:
        block_format.setLineHeight(line_height[0], line_height[1])
    return block_format, char_format


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.project: Project | None = None
        self.current_id: str | None = None
        self.loading = False
        self.focus_mode = False
        self._project_total = 0
        # Paragraph styles (1.11): seeds plus this project's saved overrides.
        self._styles = dict(SEED_STYLES)
        self._user_styles: dict[str, dict] = {}
        self.setWindowTitle("Lekhak")
        self.resize(1280, 820)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setDragDropMode(QTreeWidget.InternalMove)
        self.tree.currentItemChanged.connect(self._selection_changed)
        self.tree.itemChanged.connect(self._title_changed)
        self.tree.model().rowsMoved.connect(self._tree_moved)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_context_menu)

        self.editor = LinkEditor()
        self.editor.setAcceptRichText(True)
        self.editor.setPlaceholderText("Start writing…")
        self.editor.textChanged.connect(self._content_changed)
        self.editor.cursorPositionChanged.connect(self._update_word_count)
        self.editor.internal_link_clicked.connect(self._link_clicked)
        # Qt's own right-click menu, extended with the style commands (1.11).
        self.editor.setContextMenuPolicy(Qt.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self._editor_context_menu)
        # Pin the writing font so interface-font preferences never leak into
        # document content (toHtml() round-trips the body size); 12 pt is
        # what reset_zoom already assumed.
        writing_font = self.editor.font()
        writing_font.setPointSize(12)
        self.editor.setFont(writing_font)

        self.corkboard = QListWidget()
        self.corkboard.setViewMode(QListWidget.IconMode)
        self.corkboard.setResizeMode(QListWidget.Adjust)
        self.corkboard.setMovement(QListWidget.Static)
        self.corkboard.setWordWrap(True)
        self.corkboard.setGridSize(QSize(220, 150))
        self.corkboard.itemDoubleClicked.connect(self._open_card)

        self.outliner = QTreeWidget()
        self.outliner.setUniformRowHeights(True)
        self.outliner.itemClicked.connect(self._outliner_clicked)

        self.views = QTabWidget()
        self.views.addTab(self.editor, "Editor")
        self.views.addTab(self.corkboard, "Corkboard")
        self.views.addTab(self.outliner, "Outliner")
        self.views.currentChanged.connect(lambda _index: self._refresh_corkboard())
        self.views.currentChanged.connect(
            lambda index: self._refresh_outliner() if self.views.widget(index) is self.outliner else None)

        self.synopsis = QPlainTextEdit()
        self.synopsis.setPlaceholderText("Synopsis…")
        self.synopsis.textChanged.connect(self._metadata_changed)

        self.target = QSpinBox()
        self.target.setRange(0, 1_000_000)
        self.target.setSingleStep(100)
        self.target.setSuffix(" words")
        self.target.setSpecialValueText("No target")
        self.target.valueChanged.connect(self._metadata_changed)

        inspector = QWidget()
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.addWidget(QLabel("Synopsis"))
        inspector_layout.addWidget(self.synopsis)
        inspector_layout.addWidget(QLabel("Section target"))
        inspector_layout.addWidget(self.target)

        splitter = QSplitter()
        splitter.addWidget(self.tree)
        splitter.addWidget(self.views)
        splitter.addWidget(inspector)
        splitter.setSizes([250, 760, 270])
        self.setCentralWidget(splitter)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search project")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.returnPressed.connect(self.search)

        toolbar = QToolBar("Writing")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addAction("New Folder", self.add_folder)
        toolbar.addAction("New Chapter", self.add_chapter)
        toolbar.addAction("New Scene", self.add_scene)
        toolbar.addAction("Delete", self.delete_section)
        toolbar.addSeparator()
        toolbar.addAction("B", self.bold)
        toolbar.addAction("I", self.italic)
        toolbar.addAction("U", self.underline)
        self.style_box = QComboBox()
        self.style_box.activated.connect(self.apply_paragraph_style)
        self._rebuild_style_box()
        toolbar.addWidget(self.style_box)
        self.font_box = QFontComboBox()
        self.font_box.currentFontChanged.connect(lambda font: self.editor.setCurrentFont(font))
        toolbar.addWidget(self.font_box)
        self.size_box = QComboBox()
        self.size_box.setEditable(True)
        self.size_box.addItems(["9", "10", "11", "12", "14", "16", "18", "24", "32"])
        self.size_box.setCurrentText("12")
        self.size_box.currentTextChanged.connect(self.set_font_size)
        toolbar.addWidget(self.size_box)
        toolbar.addAction("• List", self.bullet_list)
        toolbar.addAction("1. List", self.numbered_list)
        toolbar.addAction("Left", lambda: self.editor.setAlignment(Qt.AlignLeft))
        toolbar.addAction("Centre", lambda: self.editor.setAlignment(Qt.AlignCenter))
        toolbar.addAction("Right", lambda: self.editor.setAlignment(Qt.AlignRight))
        toolbar.addAction("Clear", self.clear_formatting)
        toolbar.addSeparator()
        toolbar.addWidget(self.search_box)
        toolbar.addAction("Search", self.search)

        self.setStatusBar(QStatusBar())
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(700)
        self.save_timer.timeout.connect(self.save_current)
        self._build_menu()
        self._set_project_enabled(False)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self._action(file_menu, "&New Project…", QKeySequence.New, self.new_project)
        self._action(file_menu, "&Open Project…", QKeySequence.Open, self.open_project)
        self._action(file_menu, "&Save and Back Up", QKeySequence.Save, self.manual_save)
        self._action(file_menu, "Choose Backup Folder…", None, self.choose_backup_folder)
        file_menu.addSeparator()
        self._action(file_menu, "Export Plain Text…", None, lambda: self.export("text"))
        self._action(file_menu, "Export HTML…", None, lambda: self.export("html"))
        self._action(file_menu, "Export DOCX…", None, lambda: self.export("docx"))
        self._action(file_menu, "Export EPUB…", None, lambda: self.export("epub"))
        file_menu.addSeparator()
        self._action(file_menu, "Quit", QKeySequence.Quit, self.close)

        edit_menu = self.menuBar().addMenu("&Edit")
        self._action(edit_menu, "Undo", QKeySequence.Undo, self.editor.undo)
        self._action(edit_menu, "Redo", QKeySequence.Redo, self.editor.redo)
        edit_menu.addSeparator()
        self._action(edit_menu, "Cut", QKeySequence.Cut, self.editor.cut)
        self._action(edit_menu, "Copy", QKeySequence.Copy, self.editor.copy)
        self._action(edit_menu, "Paste", QKeySequence.Paste, self.editor.paste)
        self._action(edit_menu, "Paste as Plain Text", "Ctrl+Shift+V",
                     self.editor.paste_as_plain_text)
        self._action(edit_menu, "Paste and Keep All Formatting", None,
                     self.editor.paste_keep_all)
        edit_menu.addSeparator()
        self._action(edit_menu, "Find / Replace in Section…", QKeySequence.Find, self.find_replace)
        self._action(edit_menu, "Find in Project", "Ctrl+Shift+F", self.search_box.setFocus)
        self._action(edit_menu, "Replace in Project…", "Ctrl+Shift+H",
                     self.replace_in_project)
        edit_menu.addSeparator()
        self._action(edit_menu, "Preferences…", "Ctrl+,", self.preferences)

        view_menu = self.menuBar().addMenu("&View")
        self._action(view_menu, "Zoom In", QKeySequence.ZoomIn, lambda: self.editor.zoomIn(1))
        self._action(view_menu, "Zoom Out", QKeySequence.ZoomOut, lambda: self.editor.zoomOut(1))
        self._action(view_menu, "Reset Zoom", "Ctrl+0", self.reset_zoom)
        self._action(view_menu, "Focus Mode", "F11", self.toggle_focus_mode)

        document_menu = self.menuBar().addMenu("&Document")
        self._action(document_menu, "Split at Cursor", "Ctrl+K", self.split_section)
        self._action(document_menu, "Merge with Next Sibling", None,
                     self.merge_with_next)
        document_menu.addSeparator()
        self._action(document_menu, "Edit Metadata…", None, self.edit_metadata)
        self._action(document_menu, "Outliner Columns…", None, self.pick_outliner_columns)
        self._action(document_menu, "Create Snapshot…", None, self.create_snapshot)
        self._action(document_menu, "Restore Snapshot…", None, self.restore_snapshot)
        self._action(document_menu, "Link to Section…", "Ctrl+L", self._link_section)

    def _action(self, menu, text, shortcut, callback) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def _set_project_enabled(self, enabled: bool) -> None:
        self.tree.setEnabled(enabled)
        self.editor.setEnabled(enabled)
        self.corkboard.setEnabled(enabled)
        self.synopsis.setEnabled(enabled)

    def new_project(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose project location")
        if not selected:
            return
        title, accepted = QInputDialog.getText(self, "Project title", "Title:")
        if not accepted or not title.strip():
            return
        try:
            project = Project.create(Path(selected) / title.strip(), title.strip())
            self._switch_project(project)
        except Exception as error:
            QMessageBox.critical(self, "Could not create project", str(error))

    def open_project(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Open .lekhak or .manuscript project")
        if not selected:
            return
        try:
            project = Project(Path(selected))
            project.open()
            project.backup()
            self._switch_project(project)
        except Exception as error:
            QMessageBox.critical(self, "Could not open project", str(error))

    def _switch_project(self, project: Project) -> None:
        self.save_current()
        if self.project:
            self.project.close()
        self.project = project
        self.current_id = None
        # Startup resume (1.9): which project was open is app-wide state —
        # written only on a successful switch, read by main() at startup.
        QSettings().setValue("session/lastProject", str(project.root))
        self.setWindowTitle(f"{project.get_setting('title', project.root.stem)} — Lekhak")
        last_document = project.get_setting("last_document")
        self._reload_tree(select_id=last_document or None)
        self._set_project_enabled(True)
        if not self.tree.currentItem() and self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        # Restore the caret only into the document it was saved from —
        # a deleted last_document falls back to the first item above and
        # this cursor belongs to a document that isn't open.
        if last_document and self.current_id == last_document:
            self._restore_cursor()
        self._load_styles()

    def _restore_cursor(self) -> None:
        """Session resume (1.9): put the caret back where the last save left it.

        Offsets are plain-text characters (the units QTextCursor reports).
        Clamped because the text may have moved since; the format is
        transparent, so settings can be hand-edited — a junk value leaves
        the caret at the start rather than failing.
        """
        if not self.project or not self.current_id:
            return
        raw = self.project.get_setting("last_cursor", "0")
        try:
            offset = int(raw)
        except ValueError:
            return
        offset = min(max(offset, 0), self.editor.document().characterCount() - 1)
        cursor = self.editor.textCursor()
        cursor.setPosition(offset)
        self.editor.setTextCursor(cursor)

    def _reload_tree(self, select_id: str | None = None) -> None:
        if not self.project:
            return
        self.loading = True
        self.tree.clear()
        items: dict[str, QTreeWidgetItem] = {}
        documents = self.project.documents()
        pending = documents[:]
        while pending:
            progressed = False
            for document in pending[:]:
                if document.parent_id is None or document.parent_id in items:
                    item = QTreeWidgetItem([document.title])
                    item.setData(0, Qt.UserRole, document.id)
                    item.setData(0, Qt.UserRole + 1, document.kind)
                    item.setToolTip(0, document.kind.capitalize())
                    if document.kind == "folder":
                        item.setIcon(0, self.style().standardIcon(QStyle.SP_DirIcon))
                    item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
                    if document.parent_id:
                        items[document.parent_id].addChild(item)
                    else:
                        self.tree.addTopLevelItem(item)
                    items[document.id] = item
                    pending.remove(document)
                    progressed = True
            if not progressed:
                break
        self.tree.expandAll()
        self.loading = False
        if select_id and select_id in items:
            self.tree.setCurrentItem(items[select_id])
        self._refresh_outliner()

    def _outliner_column_ids(self) -> list[str]:
        if not self.project:
            return ["title", "kind", "words", "target"]
        raw = self.project.get_setting("outliner_columns")
        if not raw:
            return ["title", "kind", "words", "target"]
        try:
            columns = json.loads(raw)
        except ValueError:
            return ["title", "kind", "words", "target"]
        return columns if isinstance(columns, list) and "title" in columns else ["title", "kind", "words", "target"]

    def _available_outliner_columns(self, documents) -> list[tuple[str, str]]:
        builtins = [
            ("title", "Title"),
            ("kind", "Kind"),
            ("words", "Words"),
            ("target", "Target"),
        ]
        if not self.project:
            return builtins
        children = {d.id for d in documents if d.parent_id}
        metadata = [
            (f"meta:{key}", key) for key in self.project.metadata_keys()
        ]
        return builtins + metadata

    def _refresh_outliner(self) -> None:
        if not self.project:
            self.outliner.clear()
            return
        documents = self.project.documents()
        rollups = self.project.word_rollups()
        metadata = self.project.metadata_entries_all()
        self._project_total = sum(d.word_count for d in documents)
        column_ids = [c for c in self._outliner_column_ids()]
        labels = dict(self._available_outliner_columns(documents))
        self.outliner.setColumnCount(len(column_ids))
        self.outliner.setHeaderLabels([labels.get(c, c) for c in column_ids])
        self.outliner.clear()
        children: dict[str | None, list] = {}
        for document in documents:
            children.setdefault(document.parent_id, []).append(document)
        has_children = {d.id for d in documents if children.get(d.id)}

        self.outliner.blockSignals(True)
        items: dict[str, QTreeWidgetItem] = {}

        def add_row(document, parent_item=None):
            cells = []
            for column_id in column_ids:
                if column_id == "title":
                    cells.append(document.title)
                elif column_id == "kind":
                    cells.append(document.kind.capitalize())
                elif column_id == "words":
                    cells.append(f"{rollups.get(document.id, document.word_count):,}")
                elif column_id == "target":
                    cells.append(f"{document.word_target:,}" if document.word_target else "")
                elif column_id.startswith("meta:"):
                    key = column_id[5:]
                    cells.append(metadata.get(document.id, {}).get(key, ("", "", []))[0])
                else:
                    cells.append("")
            item = QTreeWidgetItem(cells)
            item.setData(0, Qt.UserRole, document.id)
            if document.id in has_children:
                item.setText(0, document.title)
            for index, column_id in enumerate(column_ids):
                if column_id == "words":
                    own = f"{document.word_count:,} own"
                    total = f"{rollups.get(document.id, document.word_count):,} total"
                    item.setToolTip(index, f"{own} ({total})" if document.id in has_children else own)
            if parent_item is None:
                self.outliner.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            items[document.id] = item
            for child in sorted(children.get(document.id, []), key=lambda d: d.position):
                add_row(child, item)

        for document in sorted(children.get(None, []), key=lambda d: d.position):
            add_row(document)
        self.outliner.expandAll()
        self.outliner.blockSignals(False)
        self._sync_outliner_selection()

    def _sync_outliner_selection(self) -> None:
        if not self.current_id:
            return
        for index in range(self.outliner.topLevelItemCount()):
            item = self._find_outliner_item(self.outliner.topLevelItem(index))
            if item and item.data(0, Qt.UserRole) == self.current_id:
                self.outliner.blockSignals(True)
                self.outliner.setCurrentItem(item)
                self.outliner.blockSignals(False)
                return

    def _find_outliner_item(self, item):
        if item.data(0, Qt.UserRole) == self.current_id:
            return item
        for index in range(item.childCount()):
            found = self._find_outliner_item(item.child(index))
            if found:
                return found
        return None

    def _outliner_clicked(self, item, _column) -> None:
        document_id = item.data(0, Qt.UserRole)
        for tree_item in self._all_items():
            if tree_item.data(0, Qt.UserRole) == document_id:
                self.tree.setCurrentItem(tree_item)
                return

    def pick_outliner_columns(self) -> None:
        if not self.project:
            return
        documents = self.project.documents()
        available = self._available_outliner_columns(documents)
        current = self._outliner_column_ids()
        dialog = ColumnPickerDialog(available, current, self)
        if dialog.exec() == QDialog.Accepted:
            self.project.set_setting(
                "outliner_columns", json.dumps(dialog.selected_columns())
            )
            self._refresh_outliner()

    def _resolve_wiki_links(self) -> None:
        """Turn `[[Title]]` spans into clickable links in the editor.

        Runs on load only, so the stored document keeps the plain `[[Title]]`
        text (links survive a retitle and stay readable in the file).
        """
        if not self.project:
            return
        document = self.editor.document()
        link_color = self.palette().link().color().name()
        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        text = self.editor.toPlainText()
        # Right-to-left so replacements never disturb pending positions.
        for match in reversed(list(self.project.WIKI_LINK_RE.finditer(text))):
            target = match.group(1).strip()
            resolved = self.project.resolve_link(target)
            # Select the whole token, brackets included; insertHtml then
            # replaces it outright, so no stray [[ ]] survive.
            span_cursor = QTextCursor(document)
            span_cursor.setPosition(match.start())
            span_cursor.setPosition(match.end(), QTextCursor.KeepAnchor)
            if len(resolved) == 1:
                html = (
                    f'<a href="lekhak://doc/{resolved[0].id}" '
                    f'style="color:{link_color}; text-decoration:underline">'
                    f"{escape(target)}</a>"
                )
            elif not resolved:
                html = (
                    '<a href="lekhak://missing" '
                    'style="color:#c0392b; text-decoration:underline">'
                    f"[missing: {escape(target)}]</a>"
                )
            else:
                html = (
                    f'<a href="lekhak://pick/{escape(target)}" '
                    f'style="color:{link_color}; text-decoration:underline">'
                    f"{escape(target)}</a>"
                )
            span_cursor.insertHtml(html)
        cursor.endEditBlock()

    def _link_clicked(self, address: str) -> None:
        if not self.project or address == "lekhak://missing":
            return
        if address.startswith("lekhak://doc/"):
            self.save_current()
            self._select_document(address[len("lekhak://doc/"):])
        elif address.startswith("lekhak://pick/"):
            self._pick_link_target(address[len("lekhak://pick/"):])

    def _pick_link_target(self, target: str) -> None:
        matches = self.project.resolve_link(target)
        labels = [f"{d.title}  ({d.kind})" for d in matches]
        chosen, accepted = QInputDialog.getItem(
            self, "Follow link", f"‘{target}’ matches several sections:",
            labels, 0, False,
        )
        if accepted:
            self.save_current()
            self._select_document(matches[labels.index(chosen)].id)

    def _link_section(self) -> None:
        if not self.project:
            return
        cursor = self.editor.textCursor()
        selected = cursor.selectedText().strip()
        documents = [
            d for d in self.project.documents() if d.kind != "folder"
        ]
        if not documents:
            return
        titles = [d.title for d in documents]
        if selected and selected in titles:
            start = titles.index(selected)
        else:
            start = 0
        chosen, accepted = QInputDialog.getItem(
            self, "Insert link", "Link to section:", titles, start, False,
        )
        if not accepted:
            return
        self.save_current()
        cursor.insertText(f"[[{chosen}]]")
        self._content_changed()

    def _broken_links(self) -> list[str]:
        if not self.project:
            return []
        return [
            target for target, resolved in
            self.project.wiki_targets(self.current_id) if not resolved
        ]

    def _selection_changed(self, current, previous) -> None:
        if self.loading:
            return
        self.save_current()
        self.current_id = current.data(0, Qt.UserRole) if current else None
        self.loading = True
        if self.project and self.current_id:
            document = next(d for d in self.project.documents() if d.id == self.current_id)
            self.editor.setHtml(self.project.read_content(self.current_id))
            self._resolve_wiki_links()
            self.synopsis.setPlainText(document.synopsis)
            self.target.setValue(document.word_target)
            if document.kind == "folder" and self.views.currentWidget() is self.editor:
                self.views.setCurrentWidget(self.corkboard)
        else:
            self.editor.clear()
            self.synopsis.clear()
            self.target.setValue(0)
        self.loading = False
        self._update_word_count()
        self._refresh_corkboard()
        self._sync_outliner_selection()

    def _content_changed(self) -> None:
        if not self.loading:
            self.save_timer.start()
            self._update_word_count()

    def _metadata_changed(self) -> None:
        if not self.loading:
            self.save_timer.start()

    def save_current(self) -> None:
        if not self.project or not self.current_id or self.loading:
            return
        self.save_timer.stop()
        try:
            html = self.project.canonicalize_links(self.editor.toHtml())
            self.project.write_content(self.current_id, html)
            self.project.update_document(
                self.current_id,
                synopsis=self.synopsis.toPlainText(),
                word_target=self.target.value(),
            )
            # 1.9 session resume: written on every save path (debounce,
            # document switch, close) so a crash still resumes — the
            # caret offset is plain-text characters, same units on read.
            self.project.set_setting("last_document", self.current_id)
            self.project.set_setting(
                "last_cursor", str(self.editor.textCursor().position())
            )
            self.statusBar().showMessage("Saved", 1500)
            self._refresh_outliner()
        except Exception as error:
            QMessageBox.critical(self, "Save failed", str(error))

    def manual_save(self) -> None:
        if not self.project:
            return
        self.save_current()
        try:
            destination = self.project.backup()
            self.statusBar().showMessage(
                f"Saved and backed up to {destination.name}", 5000
            )
        except Exception as error:
            QMessageBox.critical(
                self, "Backup failed",
                f"Your document was saved, but the backup could not be created.\n\n{error}",
            )

    def reopen_last_project(self) -> None:
        """1.9 resume: reopen the project that was open at last close.

        App-level QSettings points at the project; the document and caret
        inside it come from that project's own settings (see
        _switch_project). Any failure — moved, deleted, corrupt — falls
        back to the empty window; no dialog at startup.
        """
        path = QSettings().value("session/lastProject", "", type=str)
        if not path or not Path(path).exists():
            return
        project = Project(Path(path))
        try:
            project.open()
            project.backup()
            self._switch_project(project)
        except Exception:
            # _switch_project may have half-assigned state before failing;
            # rewind so the fallback really is the empty window. close() is
            # safe even if open() never got far (connection starts None).
            project.close()
            self.project = None
            self.current_id = None
            return

    def choose_backup_folder(self) -> None:
        if not self.project:
            return
        current = self.project.get_setting("backup_folder", str(self.project.root.parent))
        selected = QFileDialog.getExistingDirectory(
            self, "Choose backup folder", current,
        )
        if not selected:
            return
        self.project.set_backup_folder(Path(selected))
        destination = self.project.backup_directory()
        QMessageBox.information(
            self, "Backup folder changed",
            f"Ctrl+S backups for this project will be stored in:\n\n{destination}",
        )

    def _title_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self.loading or not self.project:
            return
        document_id = item.data(0, Qt.UserRole)
        title = item.text(0).strip() or "Untitled"
        item.setText(0, title)
        self.project.update_document(document_id, title=title)
        self._refresh_corkboard()
        self._refresh_outliner()

    def _tree_moved(self, *args) -> None:
        if self.loading or not self.project:
            return
        for parent_item in [None] + self._all_items():
            count = self.tree.topLevelItemCount() if parent_item is None else parent_item.childCount()
            parent_id = None if parent_item is None else parent_item.data(0, Qt.UserRole)
            for position in range(count):
                item = self.tree.topLevelItem(position) if parent_item is None else parent_item.child(position)
                self.project.reorder(item.data(0, Qt.UserRole), parent_id, position)

    def _all_items(self) -> list[QTreeWidgetItem]:
        result = []
        def collect(item):
            result.append(item)
            for index in range(item.childCount()):
                collect(item.child(index))
        for index in range(self.tree.topLevelItemCount()):
            collect(self.tree.topLevelItem(index))
        return result

    def _select_document(self, document_id: str) -> None:
        for item in self._all_items():
            if item.data(0, Qt.UserRole) == document_id:
                self.tree.setCurrentItem(item)
                return

    def _refresh_corkboard(self) -> None:
        self.corkboard.clear()
        if not self.project:
            return
        documents = self.project.documents()
        selected = next((d for d in documents if d.id == self.current_id), None)
        if selected and any(d.parent_id == selected.id for d in documents):
            cards = [d for d in documents if d.parent_id == selected.id]
        else:
            parent_id = selected.parent_id if selected else None
            cards = [d for d in documents if d.parent_id == parent_id]
        for document in sorted(cards, key=lambda item: item.position):
            synopsis = document.synopsis.strip() or "No synopsis"
            progress = ""
            if document.word_target:
                percent = min(100, round(document.word_count * 100 / document.word_target))
                progress = f"\n{document.word_count:,} / {document.word_target:,} ({percent}%)"
            elif document.word_count:
                progress = f"\n{document.word_count:,} words"
            card = QListWidgetItem(f"{document.title}\n\n{synopsis}{progress}")
            card.setData(Qt.UserRole, document.id)
            card.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
            card.setSizeHint(QSize(200, 130))
            self.corkboard.addItem(card)

    def _open_card(self, card: QListWidgetItem) -> None:
        document_id = card.data(Qt.UserRole)
        for item in self._all_items():
            if item.data(0, Qt.UserRole) == document_id:
                self.tree.setCurrentItem(item)
                self.views.setCurrentWidget(self.editor)
                self.editor.setFocus()
                return

    def _new_document(self, title: str, kind: str) -> None:
        """Create a document of the given kind at the sensible place.

        The binder is neutral: folders contain anything, chapters and scenes
        may nest arbitrarily, and several roots may sit side by side. The
        kind only decides where a fresh item lands relative to the selection:
        containers receive children; a scene prefers a chapter parent; a leaf
        selection gets a sibling.
        """
        if not self.project:
            return
        current = self.tree.currentItem()
        current_id = current.data(0, Qt.UserRole) if current else None
        current_kind = current.data(0, Qt.UserRole + 1) if current else None
        parent_id = None
        if current is not None:
            accepts_child = (
                kind == "folder"
                or (kind == "chapter" and current_kind == "folder")
                or (kind == "scene" and current_kind in {"folder", "chapter"})
            )
            if accepts_child:
                parent_id = current_id
            else:
                parent_id = self.project.parent_of(current_id)
        document = self.project.add_document(title, parent_id, kind)
        self._reload_tree(document.id)
        item = self.tree.currentItem()
        if item:
            self.tree.editItem(item, 0)

    def add_folder(self) -> None:
        self._new_document("New Folder", "folder")

    def add_chapter(self) -> None:
        self._new_document("New Chapter", "chapter")

    def add_scene(self) -> None:
        self._new_document("New Scene", "scene")

    def delete_section(self) -> None:
        if not self.project or not self.current_id:
            return
        answer = QMessageBox.question(
            self, "Delete section", "Delete this section and all of its children?"
        )
        if answer == QMessageBox.Yes:
            self.project.delete_document(self.current_id)
            self.current_id = None
            self._reload_tree()

    def search(self) -> None:
        if not self.project:
            return
        query = self.search_box.text().strip()
        if not query:
            for item in self._all_items():
                item.setHidden(False)
            self.statusBar().showMessage("Search cleared", 1500)
            return
        results = self.project.search(query)
        if not results:
            self.statusBar().showMessage("No matches", 3000)
            return
        matches = {document.id for document in results}
        for item in self._all_items():
            item.setHidden(item.data(0, Qt.UserRole) not in matches)
        self.statusBar().showMessage(f"{len(results)} matching section(s); clear search to restore")

    def create_snapshot(self) -> None:
        if not self.project or not self.current_id:
            return
        self.save_current()
        name, accepted = QInputDialog.getText(self, "Create snapshot", "Snapshot name:")
        if accepted and name.strip():
            self.project.create_snapshot(self.current_id, name.strip())
            self.statusBar().showMessage(f"Snapshot ‘{name.strip()}’ created", 3000)

    def edit_metadata(self) -> None:
        if not self.project or not self.current_id:
            return
        dialog = MetadataDialog(self.project.metadata_entries(self.current_id), self)
        if dialog.exec() == QDialog.Accepted:
            values, value_types, options = dialog.values_types_options()
            self.project.set_metadata(self.current_id, values, value_types, options)
            self.statusBar().showMessage("Metadata saved", 2000)
            self._refresh_outliner()

    def restore_snapshot(self) -> None:
        if not self.project or not self.current_id:
            return
        snapshots = self.project.snapshots(self.current_id)
        if not snapshots:
            QMessageBox.information(self, "Snapshots", "This section has no snapshots yet.")
            return
        labels = [f"{item.name} — {item.created_at[:19].replace('T', ' ')}" for item in snapshots]
        selected, accepted = QInputDialog.getItem(
            self, "Restore snapshot", "Choose a snapshot:", labels, 0, False
        )
        if not accepted:
            return
        index = labels.index(selected)
        answer = QMessageBox.question(
            self, "Restore snapshot",
            "Replace the current section with this snapshot? The current version will be preserved.",
        )
        if answer == QMessageBox.Yes:
            self.save_current()
            self.project.restore_snapshot(snapshots[index].id)
            current = self.tree.currentItem()
            self._selection_changed(current, current)
            self.statusBar().showMessage("Snapshot restored", 3000)

    def split_section(self) -> None:
        if not self.project or not self.current_id:
            return
        self.save_current()
        document = self.editor.document()
        position = self.editor.textCursor().position()
        first = QTextCursor(document)
        first.setPosition(0)
        first.setPosition(position, QTextCursor.KeepAnchor)
        second = QTextCursor(document)
        second.setPosition(position)
        second.setPosition(document.characterCount() - 1, QTextCursor.KeepAnchor)
        before = QTextDocumentFragment(first)
        after = QTextDocumentFragment(second)
        if not before.toPlainText().strip() or not after.toPlainText().strip():
            QMessageBox.information(
                self, "Split Section",
                "Both halves need some text — put the cursor between them.",
            )
            return
        try:
            before_html = self.project.canonicalize_links(before.toHtml())
            after_html = self.project.canonicalize_links(after.toHtml())
            new = self.project.split_document(
                self.current_id, before_html, after_html)
        except (ValueError, KeyError) as error:
            QMessageBox.warning(self, "Split Section", str(error))
            return
        title = next(d.title for d in self.project.documents()
                     if d.id == self.current_id)
        self._reload_tree(self.current_id)
        self.statusBar().showMessage(
            f"Split ‘{title}’ and ‘{new.title}’", 4000)

    def merge_with_next(self) -> None:
        if not self.project or not self.current_id:
            return
        self.save_current()
        following = self.project.next_sibling(self.current_id)
        if following is None:
            QMessageBox.information(
                self, "Merge Sections", "No following sibling to merge with.")
            return
        answer = QMessageBox.question(
            self, "Merge Sections",
            f"Append ‘{following.title}’ to the end of this section and "
            "remove it?\n\nThis section is snapshotted first; the other "
            "section's metadata is dropped.",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            merged = self.project.merge_documents(self.current_id, following.id)
        except (ValueError, KeyError) as error:
            QMessageBox.warning(self, "Merge Sections", str(error))
            return
        self._reload_tree(self.current_id)
        self.statusBar().showMessage(
            f"Merged into ‘{merged.title}’", 4000)

    def _tree_context_menu(self, position) -> None:
        item = self.tree.itemAt(position)
        if item is None or not self.project:
            return
        if item.data(0, Qt.UserRole) != self.current_id:
            self.tree.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction("Split at Cursor", self.split_section)
        menu.addAction("Merge with Next Sibling", self.merge_with_next)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def export(self, kind: str) -> None:
        if not self.project:
            return
        self.save_current()
        documents = [
            item for item in self.project.ordered_documents()
            if item.kind in EXPORT_KINDS
        ]
        template_sets = discover_template_sets(self.project.root)
        current_set = self.project.get_setting("template_set", "default")
        options = ExportOptionsDialog(documents, template_sets, current_set, self)
        if options.exec() != QDialog.Accepted:
            return
        selected_ids = options.selected_ids()
        if not selected_ids:
            QMessageBox.warning(self, "Nothing selected", "Select at least one chapter or scene.")
            return
        templates = options.selected_template_set()
        self.project.set_setting("template_set", templates.name)
        suffix = {"text": ".txt", "html": ".html", "docx": ".docx", "epub": ".epub"}[kind]
        selected, _ = QFileDialog.getSaveFileName(self, "Export manuscript", "lekhak" + suffix)
        if selected:
            try:
                if kind == "text":
                    self.project.export_text(Path(selected), selected_ids, templates)
                elif kind == "html":
                    self.project.export_html(Path(selected), selected_ids, templates)
                elif kind == "docx":
                    self.project.export_docx(Path(selected), selected_ids, templates)
                else:
                    self.project.export_epub(Path(selected), selected_ids, templates)
                self.statusBar().showMessage(f"Exported to {selected}", 5000)
            except Exception as error:
                QMessageBox.critical(self, "Export failed", str(error))

    def bold(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Normal if self.editor.fontWeight() > QFont.Normal else QFont.Bold)
        self.editor.mergeCurrentCharFormat(fmt)

    def italic(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self.editor.fontItalic())
        self.editor.mergeCurrentCharFormat(fmt)

    def underline(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not self.editor.fontUnderline())
        self.editor.mergeCurrentCharFormat(fmt)

    def set_font_size(self, value: str) -> None:
        try:
            size = float(value)
        except ValueError:
            return
        if 6 <= size <= 144:
            self.editor.setFontPointSize(size)

    def apply_paragraph_style(self, index: int) -> None:
        style = self._styles.get(self.style_box.itemData(index))
        if style is None:
            return
        block_format, char_format = style_signature_formats(style)
        cursor = self.editor.textCursor()
        cursor.mergeBlockFormat(block_format)
        cursor.mergeCharFormat(char_format)
        self.editor.mergeCurrentCharFormat(char_format)

    # --- paragraph styles (1.11) ------------------------------------------
    # Named styles are formatting metadata about a manuscript — never
    # prose — so one JSON string in the existing project-settings table
    # is the whole storage; seeds live in code and need no file.

    def _load_styles(self) -> None:
        """Seeds plus this project's saved overrides; box rebuilt to match."""
        raw = self.project.get_setting("paragraph_styles") if self.project else ""
        try:
            stored = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            stored = {}  # hand-edited settings may be junk; seeds still work
        if not isinstance(stored, dict):
            stored = {}
        self._user_styles = {name: signature for name, signature in stored.items()
                             if isinstance(name, str) and isinstance(signature, dict)}
        self._refresh_styles()

    def _refresh_styles(self) -> None:
        """Effective list: a saved style keeps its seed's place when it
        replaces the seed by name; new names join at the end."""
        self._styles = {**SEED_STYLES, **self._user_styles}
        self._rebuild_style_box()

    def _rebuild_style_box(self) -> None:
        current = self.style_box.currentData()
        self.style_box.clear()
        for name in self._styles:
            self.style_box.addItem(name, name)
        index = self.style_box.findData(current)
        if index >= 0:
            self.style_box.setCurrentIndex(index)

    def _persist_styles(self) -> bool:
        if not self.project:
            return False
        self.project.set_setting("paragraph_styles",
                                 json.dumps(self._user_styles, indent=1))
        return True

    def save_style_from_cursor(self, name: str) -> bool:
        """Create: capture the paragraph under the caret under a new name.

        False means nothing happened — no project, empty name, or the
        name is already taken (that is what Update is for).
        """
        name = name.strip()
        if not self.project or not name or name in self._styles:
            return False
        self._user_styles[name] = capture_paragraph_signature(self.editor.textCursor())
        self._refresh_styles()
        self._persist_styles()
        return True

    def update_style_from_cursor(self, name: str) -> bool:
        """Update: the named style's signature becomes the paragraph's now."""
        if not self.project or name not in self._styles:
            return False
        self._user_styles[name] = capture_paragraph_signature(self.editor.textCursor())
        self._refresh_styles()
        self._persist_styles()
        return True

    def remove_style(self, name: str) -> bool:
        """Delete a saved style; deleting a seed's override brings the
        seed back, seeds themselves are never stored or removable."""
        if not self.project or name not in self._user_styles:
            return False
        del self._user_styles[name]
        self._refresh_styles()
        self._persist_styles()
        return True

    def style_at_cursor(self) -> str | None:
        """The style the paragraph under the caret already wears, or None.

        Compared on the style's own keys only, so a built-in seed (which
        never mentions alignment or family) matches the very paragraph it
        just formatted even though the capture recorded more.
        """
        captured = capture_paragraph_signature(self.editor.textCursor())
        for name, style in self._styles.items():
            if all(captured.get(key) == value for key, value in style.items()):
                return name
        return None

    def _editor_context_menu(self, position) -> None:
        menu = self._build_editor_menu()
        menu.exec(self.editor.mapToGlobal(position))

    def _build_editor_menu(self) -> QMenu:
        """Qt's own right-click menu, extended with the style commands.

        Split from the exec so tests can inspect the actions; the dialogs
        stay thin — capture and persistence live in
        save_style_from_cursor and friends, which tests call directly
        instead of driving a dialog.
        """
        menu = self.editor.createStandardContextMenu()
        menu.addSeparator()
        create = menu.addAction("Create Style from Paragraph…")
        update = menu.addAction("Update Style from Paragraph…")
        delete = menu.addAction("Delete Style…")
        update.setEnabled(bool(self._styles))
        delete.setEnabled(bool(self._user_styles))
        create.triggered.connect(self._create_style_dialog)
        update.triggered.connect(self._update_style_dialog)
        delete.triggered.connect(self._delete_style_dialog)
        return menu

    def _create_style_dialog(self) -> None:
        if not self.project:
            self.statusBar().showMessage("Open a project before saving styles", 3000)
            return
        name, ok = QInputDialog.getText(self, "Create Style", "Style name:")
        if not ok or not name or not name.strip():
            return
        name = name.strip()
        if not self.save_style_from_cursor(name):
            QMessageBox.warning(
                self, "Style exists",
                f'A style called "{name}" already exists — use '
                "Update Style to replace it.",
            )
            return
        self.statusBar().showMessage(f'Style "{name}" saved', 3000)

    def _update_style_dialog(self) -> None:
        if not self.project:
            self.statusBar().showMessage("Open a project before saving styles", 3000)
            return
        names = list(self._styles)
        current = self.style_at_cursor()
        index = names.index(current) if current is not None else 0
        name, ok = QInputDialog.getItem(
            self, "Update Style",
            "Replace this style with the current paragraph:", names, index, False,
        )
        if not ok:
            return
        self.update_style_from_cursor(name)
        self.statusBar().showMessage(f'Style "{name}" updated', 3000)

    def _delete_style_dialog(self) -> None:
        if not self.project or not self._user_styles:
            return
        name, ok = QInputDialog.getItem(
            self, "Delete Style", "Style to delete:",
            list(self._user_styles), 0, False,
        )
        if not ok:
            return
        self.remove_style(name)
        self.statusBar().showMessage(f'Style "{name}" deleted', 3000)

    def bullet_list(self) -> None:
        self.editor.textCursor().createList(QTextListFormat.ListDisc)

    def numbered_list(self) -> None:
        self.editor.textCursor().createList(QTextListFormat.ListDecimal)

    def clear_formatting(self) -> None:
        cursor = self.editor.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontPointSize(12)
        cursor.mergeCharFormat(fmt)
        cursor.setBlockFormat(QTextBlockFormat())
        self.editor.setTextCursor(cursor)

    def preferences(self) -> None:
        current = QApplication.font().pointSize()
        dialog = PreferencesDialog(current, load_paste_prefs(), self)
        if dialog.exec() != QDialog.Accepted:
            return
        size = dialog.size_spin.value()
        font = QApplication.font()
        font.setPointSize(size)
        QApplication.setFont(font)
        # QApplication.setFont alone doesn't reach widgets that already
        # exist; set it on the window so it cascades. The editor is pinned
        # with an explicit font, so it ignores the cascade and keeps its
        # 12 pt writing size.
        self.setFont(font)
        settings = QSettings()
        settings.setValue("ui/fontSize", size)
        settings.setValue("paste/fonts", dialog.paste_fonts.isChecked())
        settings.setValue("paste/paragraphs", dialog.paste_paragraphs.isChecked())
        settings.setValue("paste/inline", dialog.paste_inline.isChecked())
        settings.setValue("paste/alignment", dialog.paste_alignment.isChecked())
        self.statusBar().showMessage(f"Interface font set to {size} pt", 3000)

    def replace_in_project(self) -> None:
        if not self.project:
            return
        self.save_current()
        dialog = ProjectReplaceDialog(self.project, on_goto=self._select_document,
                                      parent=self)
        dialog.exec()
        self._reload_tree(self.current_id)

    def find_replace(self) -> None:
        dialog = FindReplaceDialog(self.editor, self)
        dialog.show()
        dialog.find_text.setFocus()
        self._find_dialog = dialog

    def reset_zoom(self) -> None:
        font = self.editor.font()
        font.setPointSize(12)
        self.editor.setFont(font)

    def toggle_focus_mode(self) -> None:
        self.focus_mode = not self.focus_mode
        self.tree.setVisible(not self.focus_mode)
        self.synopsis.parentWidget().setVisible(not self.focus_mode)
        self.menuBar().setVisible(not self.focus_mode)
        for toolbar in self.findChildren(QToolBar):
            toolbar.setVisible(not self.focus_mode)
        self.statusBar().setVisible(not self.focus_mode)
        if self.focus_mode:
            self.views.setCurrentWidget(self.editor)
            self.editor.setFocus()

    def _update_word_count(self) -> None:
        words = len(self.editor.toPlainText().split())
        target = self.target.value()
        cursor = self.editor.textCursor()
        parts = []
        if target:
            percent = min(100, round(words * 100 / target))
            parts.append(f"{words:,} / {target:,} words ({percent}%)")
        else:
            parts.append(f"{words:,} words")
        if cursor.hasSelection():
            selected = len(cursor.selectedText().split())
            parts.append(f"{selected:,} selected")
        if self._project_total:
            parts.append(f"{self._project_total:,} in project")
        if self.current_id:
            broken = self._broken_links()
            if broken:
                parts.append(f"broken link(s): {', '.join(broken)}")
        self.statusBar().showMessage(" · ".join(parts))

    def closeEvent(self, event) -> None:
        self.save_current()
        if self.project:
            self.project.close()
        event.accept()


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("Lekhak")
    application.setOrganizationName("Lekhak")
    application.setDesktopFileName("lekhak")  # matches lekhak.desktop on Wayland/GNOME
    # Interface font only; the editor is pinned to 12 pt independently, so
    # this never reaches document content.
    stored_size = QSettings().value("ui/fontSize", type=int)
    if stored_size:
        interface_font = application.font()
        interface_font.setPointSize(stored_size)
        application.setFont(interface_font)
    window = MainWindow()
    window.show()
    window.reopen_last_project()  # 1.9 resume-on-start
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
