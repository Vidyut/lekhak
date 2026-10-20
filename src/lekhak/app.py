from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction, QFont, QKeySequence, QTextBlockFormat, QTextCharFormat, QTextCursor,
    QTextListFormat,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
    QFontComboBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QSplitter, QStatusBar, QStyle, QTabWidget,
    QTableWidget, QTableWidgetItem, QTextEdit, QToolBar, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .project import Project


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
    def __init__(self, documents, template: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Options")
        self.resize(620, 620)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Include these chapters and scenes:"))
        self.documents = QListWidget()
        for document in documents:
            prefix = "Chapter" if document.kind == "chapter" else "    Scene"
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
            "Section body template — placeholders: {title}, {kind}, {synopsis}, "
            "{word_count}, {content}, {metadata:Field}"
        ))
        self.template = QPlainTextEdit(template)
        layout.addWidget(self.template)
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.project: Project | None = None
        self.current_id: str | None = None
        self.loading = False
        self.focus_mode = False
        self.setWindowTitle("Lekhak")
        self.resize(1280, 820)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setDragDropMode(QTreeWidget.InternalMove)
        self.tree.currentItemChanged.connect(self._selection_changed)
        self.tree.itemChanged.connect(self._title_changed)
        self.tree.model().rowsMoved.connect(self._tree_moved)

        self.editor = QTextEdit()
        self.editor.setAcceptRichText(True)
        self.editor.setPlaceholderText("Start writing…")
        self.editor.textChanged.connect(self._content_changed)

        self.corkboard = QListWidget()
        self.corkboard.setViewMode(QListWidget.IconMode)
        self.corkboard.setResizeMode(QListWidget.Adjust)
        self.corkboard.setMovement(QListWidget.Static)
        self.corkboard.setWordWrap(True)
        self.corkboard.setGridSize(QSize(220, 150))
        self.corkboard.itemDoubleClicked.connect(self._open_card)

        self.views = QTabWidget()
        self.views.addTab(self.editor, "Editor")
        self.views.addTab(self.corkboard, "Corkboard")
        self.views.currentChanged.connect(lambda _index: self._refresh_corkboard())

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
        self.style_box.addItems(["Paragraph", "Title", "Heading 1", "Heading 2", "Heading 3", "Quote"])
        self.style_box.activated.connect(self.apply_paragraph_style)
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
        self._action(edit_menu, "Find / Replace in Section…", QKeySequence.Find, self.find_replace)
        self._action(edit_menu, "Find in Project", "Ctrl+Shift+F", self.search_box.setFocus)

        view_menu = self.menuBar().addMenu("&View")
        self._action(view_menu, "Zoom In", QKeySequence.ZoomIn, lambda: self.editor.zoomIn(1))
        self._action(view_menu, "Zoom Out", QKeySequence.ZoomOut, lambda: self.editor.zoomOut(1))
        self._action(view_menu, "Reset Zoom", "Ctrl+0", self.reset_zoom)
        self._action(view_menu, "Focus Mode", "F11", self.toggle_focus_mode)

        document_menu = self.menuBar().addMenu("&Document")
        self._action(document_menu, "Edit Metadata…", None, self.edit_metadata)
        self._action(document_menu, "Create Snapshot…", None, self.create_snapshot)
        self._action(document_menu, "Restore Snapshot…", None, self.restore_snapshot)

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
        self.setWindowTitle(f"{project.get_setting('title', project.root.stem)} — Lekhak")
        self._reload_tree()
        self._set_project_enabled(True)
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

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

    def _selection_changed(self, current, previous) -> None:
        if self.loading:
            return
        self.save_current()
        self.current_id = current.data(0, Qt.UserRole) if current else None
        self.loading = True
        if self.project and self.current_id:
            document = next(d for d in self.project.documents() if d.id == self.current_id)
            self.editor.setHtml(self.project.read_content(self.current_id))
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
            self.project.write_content(self.current_id, self.editor.toHtml())
            self.project.update_document(
                self.current_id,
                synopsis=self.synopsis.toPlainText(),
                word_target=self.target.value(),
            )
            self.statusBar().showMessage("Saved", 1500)
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
            card = QListWidgetItem(f"{document.title}\n\n{synopsis}")
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

    def export(self, kind: str) -> None:
        if not self.project:
            return
        self.save_current()
        documents = [
            item for item in self.project.ordered_documents()
            if item.kind in {"chapter", "scene"}
        ]
        template = self.project.get_setting("export_template", "{content}")
        options = ExportOptionsDialog(documents, template, self)
        if options.exec() != QDialog.Accepted:
            return
        selected_ids = options.selected_ids()
        if not selected_ids:
            QMessageBox.warning(self, "Nothing selected", "Select at least one chapter or scene.")
            return
        template = options.template.toPlainText() or "{content}"
        self.project.set_setting("export_template", template)
        suffix = {"text": ".txt", "html": ".html", "docx": ".docx", "epub": ".epub"}[kind]
        selected, _ = QFileDialog.getSaveFileName(self, "Export manuscript", "lekhak" + suffix)
        if selected:
            try:
                if kind == "text":
                    self.project.export_text(Path(selected), selected_ids, template)
                elif kind == "html":
                    self.project.export_html(Path(selected), selected_ids, template)
                elif kind == "docx":
                    self.project.export_docx(Path(selected), selected_ids, template)
                else:
                    self.project.export_epub(Path(selected), selected_ids, template)
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
        sizes = [12, 28, 22, 18, 15, 12]
        weights = [QFont.Normal, QFont.Bold, QFont.Bold, QFont.Bold, QFont.Bold, QFont.Normal]
        char_format = QTextCharFormat()
        char_format.setFontPointSize(sizes[index])
        char_format.setFontWeight(weights[index])
        char_format.setFontItalic(index == 5)
        block_format = QTextBlockFormat()
        if index == 5:
            block_format.setLeftMargin(32)
            block_format.setRightMargin(32)
        cursor = self.editor.textCursor()
        cursor.mergeBlockFormat(block_format)
        cursor.mergeCharFormat(char_format)
        self.editor.mergeCurrentCharFormat(char_format)

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
        if target:
            percent = min(100, round(words * 100 / target))
            self.statusBar().showMessage(f"{words:,} / {target:,} words ({percent}%)")
        else:
            self.statusBar().showMessage(f"{words:,} words")

    def closeEvent(self, event) -> None:
        self.save_current()
        if self.project:
            self.project.close()
        event.accept()


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("Lekhak")
    application.setOrganizationName("Lekhak")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
