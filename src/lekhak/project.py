from __future__ import annotations

import os
import json
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape, unescape
from pathlib import Path


TAG_RE = re.compile(r"<[^>]+>")

# Kinds are labels, not structure: any item may contain any other, at any
# depth, and several items may share the top level. Folder is a neutral
# container; chapter/scene/note are the writer's shorthand for intended use.
DOCUMENT_KINDS = {"folder", "chapter", "scene", "note"}
# Kinds that contribute prose to a compile by default. Book-level compile
# settings will override this per document later; folders and notes stay out.
EXPORT_KINDS = {"chapter", "scene"}


@dataclass(frozen=True)
class Document:
    id: str
    parent_id: str | None
    title: str
    synopsis: str
    position: int
    word_target: int
    kind: str


@dataclass(frozen=True)
class Snapshot:
    id: str
    document_id: str
    name: str
    created_at: str


class Project:
    """Transparent project storage with atomic document writes."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.documents_dir = self.root / "documents"
        self.backups_dir = self.root / "backups"
        self.db_path = self.root / "project.sqlite3"
        self.connection: sqlite3.Connection | None = None

    @classmethod
    def create(cls, root: Path, title: str = "Untitled Project") -> "Project":
        root = Path(root)
        if root.suffix not in {".lekhak", ".manuscript"}:
            root = root.with_suffix(".lekhak")
        if root.exists() and any(root.iterdir()):
            raise FileExistsError(f"Project directory is not empty: {root}")
        root.mkdir(parents=True, exist_ok=True)
        project = cls(root)
        project.documents_dir.mkdir(exist_ok=True)
        project.backups_dir.mkdir(exist_ok=True)
        project.open(create=True)
        project.set_setting("title", title)
        project.add_document("Draft", kind="folder")
        return project

    def open(self, create: bool = False) -> None:
        if not create and not self.db_path.exists():
            raise FileNotFoundError(f"Not a Lekhak project: {self.root}")
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                parent_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                synopsis TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL,
                word_target INTEGER NOT NULL DEFAULT 0,
                kind TEXT NOT NULL DEFAULT 'scene',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS document_parent_order
                ON documents(parent_id, position);
            CREATE TABLE IF NOT EXISTS snapshots (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                html TEXT NOT NULL,
                synopsis TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS snapshot_document_date
                ON snapshots(document_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS document_metadata (
                document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                value_type TEXT NOT NULL DEFAULT 'text',
                options_json TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY(document_id, key)
            );
            """
        )
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(documents)")}
        if "word_target" not in columns:
            self.connection.execute(
                "ALTER TABLE documents ADD COLUMN word_target INTEGER NOT NULL DEFAULT 0"
            )
        if "kind" not in columns:
            self.connection.execute(
                "ALTER TABLE documents ADD COLUMN kind TEXT NOT NULL DEFAULT 'scene'"
            )
        metadata_columns = {
            row[1] for row in self.connection.execute("PRAGMA table_info(document_metadata)")
        }
        if "value_type" not in metadata_columns:
            self.connection.execute(
                "ALTER TABLE document_metadata ADD COLUMN value_type TEXT NOT NULL DEFAULT 'text'"
            )
        if "options_json" not in metadata_columns:
            self.connection.execute(
                "ALTER TABLE document_metadata ADD COLUMN options_json TEXT NOT NULL DEFAULT '[]'"
            )
        # Migration: earlier versions seeded "Draft" as a chapter; it is a
        # neutral folder now. Only touch the seeded root, never user content.
        self.connection.execute(
            "UPDATE documents SET kind='folder' "
            "WHERE title='Draft' AND parent_id IS NULL AND kind='chapter'"
        )
        self.connection.commit()

    def close(self) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None

    @property
    def db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("Project is not open")
        return self.connection

    def set_setting(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.db.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_backup_folder(self, folder: Path | None) -> None:
        self.set_setting("backup_folder", str(Path(folder).resolve()) if folder else "")

    def backup_directory(self) -> Path:
        configured = self.get_setting("backup_folder")
        if configured:
            return Path(configured).expanduser() / self.root.name
        return self.backups_dir

    def add_document(self, title: str, parent_id: str | None = None,
                     kind: str = "scene") -> Document:
        if kind not in DOCUMENT_KINDS:
            raise ValueError(f"Unknown document kind: {kind}")
        document_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        row = self.db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM documents "
            "WHERE parent_id IS ?",
            (parent_id,),
        ).fetchone()
        position = int(row[0])
        self.db.execute(
            "INSERT INTO documents(id,parent_id,title,position,kind,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (document_id, parent_id, title, position, kind, now, now),
        )
        self.db.commit()
        self.write_content(document_id, "")
        return Document(document_id, parent_id, title, "", position, 0, kind)

    def documents(self) -> list[Document]:
        rows = self.db.execute(
            "SELECT id,parent_id,title,synopsis,position,word_target,kind FROM documents "
            "ORDER BY parent_id,position"
        ).fetchall()
        return [Document(**dict(row)) for row in rows]

    def update_document(self, document_id: str, *, title: str | None = None,
                        synopsis: str | None = None,
                        word_target: int | None = None) -> None:
        fields: list[str] = []
        values: list[str] = []
        if title is not None:
            fields.append("title=?")
            values.append(title)
        if synopsis is not None:
            fields.append("synopsis=?")
            values.append(synopsis)
        if word_target is not None:
            fields.append("word_target=?")
            values.append(str(max(0, word_target)))
        if not fields:
            return
        fields.append("updated_at=?")
        values.append(datetime.now(timezone.utc).isoformat())
        values.append(document_id)
        self.db.execute(
            f"UPDATE documents SET {', '.join(fields)} WHERE id=?", values
        )
        self.db.commit()

    def reorder(self, document_id: str, parent_id: str | None, position: int) -> None:
        if parent_id == document_id or self._is_descendant(parent_id, document_id):
            raise ValueError("A document cannot contain itself")
        with self.db:
            self.db.execute(
                "UPDATE documents SET position=position-1 WHERE parent_id IS "
                "(SELECT parent_id FROM documents WHERE id=?) AND position > "
                "(SELECT position FROM documents WHERE id=?)",
                (document_id, document_id),
            )
            self.db.execute(
                "UPDATE documents SET position=position+1 WHERE parent_id IS ? AND position>=?",
                (parent_id, position),
            )
            self.db.execute(
                "UPDATE documents SET parent_id=?,position=?,updated_at=? WHERE id=?",
                (parent_id, position, datetime.now(timezone.utc).isoformat(), document_id),
            )

    def parent_of(self, document_id: str) -> str | None:
        row = self.db.execute(
            "SELECT parent_id FROM documents WHERE id=?", (document_id,)
        ).fetchone()
        return row[0] if row else None

    def _is_descendant(self, candidate: str | None, ancestor: str) -> bool:
        current = candidate
        while current:
            if current == ancestor:
                return True
            row = self.db.execute(
                "SELECT parent_id FROM documents WHERE id=?", (current,)
            ).fetchone()
            current = row[0] if row else None
        return False

    def delete_document(self, document_id: str) -> None:
        descendants = self._descendant_ids(document_id)
        with self.db:
            self.db.execute("DELETE FROM documents WHERE id=?", (document_id,))
        for item_id in descendants:
            self.content_path(item_id).unlink(missing_ok=True)

    def _descendant_ids(self, document_id: str) -> list[str]:
        result = [document_id]
        for row in self.db.execute(
            "SELECT id FROM documents WHERE parent_id=?", (document_id,)
        ):
            result.extend(self._descendant_ids(row[0]))
        return result

    def content_path(self, document_id: str) -> Path:
        return self.documents_dir / f"{document_id}.html"

    def read_content(self, document_id: str) -> str:
        path = self.content_path(document_id)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def write_content(self, document_id: str, html: str) -> None:
        path = self.content_path(document_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{document_id}-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(html)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise
        self.db.execute(
            "UPDATE documents SET updated_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), document_id),
        )
        self.db.commit()

    @staticmethod
    def plain_text(html: str) -> str:
        text = re.sub(r"<(br|/p|/div|/h[1-6])\b[^>]*>", "\n", html, flags=re.I)
        return unescape(TAG_RE.sub("", text)).strip()

    def search(self, query: str) -> list[Document]:
        needle = query.casefold().strip()
        if not needle:
            return []
        return [
            document for document in self.documents()
            if needle in document.title.casefold()
            or needle in document.synopsis.casefold()
            or needle in self.plain_text(self.read_content(document.id)).casefold()
        ]

    def metadata(self, document_id: str) -> dict[str, str]:
        rows = self.db.execute(
            "SELECT key,value FROM document_metadata WHERE document_id=? ORDER BY key",
            (document_id,),
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def metadata_entries(self, document_id: str) -> dict[str, tuple[str, str, list[str]]]:
        rows = self.db.execute(
            "SELECT key,value,value_type,options_json FROM document_metadata "
            "WHERE document_id=? ORDER BY key", (document_id,),
        ).fetchall()
        return {row[0]: (row[1], row[2], json.loads(row[3])) for row in rows}

    def set_metadata(self, document_id: str, values: dict[str, str],
                     value_types: dict[str, str] | None = None,
                     options: dict[str, list[str]] | None = None) -> None:
        cleaned = {key.strip(): value for key, value in values.items() if key.strip()}
        value_types = value_types or {}
        options = options or {}
        with self.db:
            self.db.execute("DELETE FROM document_metadata WHERE document_id=?", (document_id,))
            self.db.executemany(
                "INSERT INTO document_metadata"
                "(document_id,key,value,value_type,options_json) VALUES(?,?,?,?,?)",
                [
                    (
                        document_id, key, value, value_types.get(key, "text"),
                        json.dumps(options.get(key, []), ensure_ascii=False),
                    )
                    for key, value in cleaned.items()
                ],
            )

    def create_snapshot(self, document_id: str, name: str) -> Snapshot:
        snapshot_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        row = self.db.execute(
            "SELECT synopsis FROM documents WHERE id=?", (document_id,)
        ).fetchone()
        if row is None:
            raise KeyError(document_id)
        self.db.execute(
            "INSERT INTO snapshots(id,document_id,name,html,synopsis,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (snapshot_id, document_id, name, self.read_content(document_id), row[0], created_at),
        )
        self.db.commit()
        return Snapshot(snapshot_id, document_id, name, created_at)

    def snapshots(self, document_id: str) -> list[Snapshot]:
        rows = self.db.execute(
            "SELECT id,document_id,name,created_at FROM snapshots "
            "WHERE document_id=? ORDER BY created_at DESC", (document_id,)
        ).fetchall()
        return [Snapshot(**dict(row)) for row in rows]

    def restore_snapshot(self, snapshot_id: str) -> str:
        row = self.db.execute(
            "SELECT document_id,html,synopsis FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        document_id, html, synopsis = row
        # Preserve the state being replaced so restore is itself reversible.
        self.create_snapshot(document_id, "Before snapshot restore")
        self.write_content(document_id, html)
        self.update_document(document_id, synopsis=synopsis)
        return document_id

    def ordered_documents(self) -> list[Document]:
        all_documents = self.documents()
        children: dict[str | None, list[Document]] = {}
        for document in all_documents:
            children.setdefault(document.parent_id, []).append(document)
        ordered: list[Document] = []

        def visit(parent_id: str | None) -> None:
            for document in sorted(children.get(parent_id, []), key=lambda d: d.position):
                ordered.append(document)
                visit(document.id)

        visit(None)
        return ordered

    def _export_documents(self, selected_ids: set[str] | None) -> list[Document]:
        documents = [d for d in self.ordered_documents() if d.kind in EXPORT_KINDS]
        return documents if selected_ids is None else [d for d in documents if d.id in selected_ids]

    def render_template(self, document: Document, template: str, *, html: bool = False) -> str:
        content = self.read_content(document.id)
        if not html:
            content = self.plain_text(content)
        values = {
            "title": document.title,
            "kind": document.kind,
            "synopsis": document.synopsis,
            "content": content,
            "word_count": str(len(self.plain_text(self.read_content(document.id)).split())),
        }
        metadata = self.metadata(document.id)
        rendered = re.sub(
            r"\{metadata:([^{}]+)\}",
            lambda match: (
                escape(metadata.get(match.group(1).strip(), ""))
                if html else metadata.get(match.group(1).strip(), "")
            ),
            template,
        )
        for key, value in values.items():
            replacement = value if key == "content" or not html else escape(value)
            rendered = rendered.replace("{" + key + "}", replacement)
        return rendered

    def export_text(self, destination: Path, selected_ids: set[str] | None = None,
                    template: str = "{content}") -> None:
        parts = []
        for document in self._export_documents(selected_ids):
            body = self.render_template(document, template)
            parts.append(f"{document.title}\n\n{body}".strip())
        self._atomic_write(Path(destination), "\n\n\n".join(parts) + "\n")

    def export_html(self, destination: Path, selected_ids: set[str] | None = None,
                    template: str = "{content}") -> None:
        body = []
        for document in self._export_documents(selected_ids):
            body.append(
                f"<section><h1>{escape(document.title)}</h1>"
                f"{self.render_template(document, template, html=True)}</section>"
            )
        title = self.get_setting("title", "Lekhak")
        content = (
            "<!doctype html><meta charset='utf-8'>"
            f"<title>{escape(title)}</title><main>{''.join(body)}</main>"
        )
        self._atomic_write(Path(destination), content)

    def export_docx(self, destination: Path, selected_ids: set[str] | None = None,
                    template: str = "{content}") -> None:
        from docx import Document as DocxDocument

        output = DocxDocument()
        output.core_properties.title = self.get_setting("title", "Lekhak")
        for document in self._export_documents(selected_ids):
            output.add_heading(document.title, level=1 if document.kind == "chapter" else 2)
            for paragraph in self.render_template(document, template).split("\n"):
                if paragraph.strip():
                    output.add_paragraph(paragraph.strip())
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}-", dir=destination.parent)
        os.close(fd)
        try:
            output.save(temporary_name)
            os.replace(temporary_name, destination)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise

    def export_epub(self, destination: Path, selected_ids: set[str] | None = None,
                    template: str = "{content}") -> None:
        documents = self._export_documents(selected_ids)
        manifest, spine, nav_items, pages = [], [], [], []
        for index, document in enumerate(documents, start=1):
            filename, item_id = f"section-{index}.xhtml", f"section-{index}"
            body = self.render_template(document, template, html=True)
            pages.append((filename, "<?xml version='1.0' encoding='utf-8'?>"
                "<html xmlns='http://www.w3.org/1999/xhtml'><head>"
                f"<title>{escape(document.title)}</title></head><body>"
                f"<h1>{escape(document.title)}</h1>{body}</body></html>"))
            manifest.append(f"<item id='{item_id}' href='{filename}' media-type='application/xhtml+xml'/>")
            spine.append(f"<itemref idref='{item_id}'/>")
            nav_items.append(f"<li><a href='{filename}'>{escape(document.title)}</a></li>")
        title = escape(self.get_setting("title", "Lekhak"))
        nav = ("<?xml version='1.0' encoding='utf-8'?><html xmlns='http://www.w3.org/1999/xhtml' "
            "xmlns:epub='http://www.idpf.org/2007/ops'><head><title>Contents</title></head>"
            f"<body><nav epub:type='toc'><h1>Contents</h1><ol>{''.join(nav_items)}</ol></nav></body></html>")
        opf = ("<?xml version='1.0' encoding='utf-8'?><package xmlns='http://www.idpf.org/2007/opf' "
            "version='3.0' unique-identifier='book-id'><metadata xmlns:dc='http://purl.org/dc/elements/1.1/'>"
            f"<dc:identifier id='book-id'>{uuid.uuid4().urn}</dc:identifier><dc:title>{title}</dc:title>"
            "<dc:language>en</dc:language></metadata><manifest>"
            "<item id='nav' href='nav.xhtml' media-type='application/xhtml+xml' properties='nav'/>"
            f"{''.join(manifest)}</manifest><spine>{''.join(spine)}</spine></package>")
        container = ("<?xml version='1.0' encoding='UTF-8'?><container version='1.0' "
            "xmlns='urn:oasis:names:tc:opendocument:xmlns:container'><rootfiles>"
            "<rootfile full-path='OEBPS/content.opf' media-type='application/oebps-package+xml'/>"
            "</rootfiles></container>")
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}-", dir=destination.parent)
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary_name, "w") as archive:
                archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
                archive.writestr("META-INF/container.xml", container)
                archive.writestr("OEBPS/content.opf", opf)
                archive.writestr("OEBPS/nav.xhtml", nav)
                for filename, page in pages:
                    archive.writestr(f"OEBPS/{filename}", page)
            os.replace(temporary_name, destination)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise

    def backup(self, keep: int = 10) -> Path:
        self.db.execute("PRAGMA wal_checkpoint(FULL)")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_directory = self.backup_directory()
        backup_directory.mkdir(parents=True, exist_ok=True)
        destination = backup_directory / stamp
        destination.mkdir(parents=True)
        shutil.copy2(self.db_path, destination / self.db_path.name)
        shutil.copytree(self.documents_dir, destination / "documents")
        backups = sorted((p for p in backup_directory.iterdir() if p.is_dir()), reverse=True)
        for old in backups[keep:]:
            shutil.rmtree(old)
        return destination
