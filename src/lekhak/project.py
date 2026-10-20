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

from .templates import TemplateSet


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
    word_count: int = 0


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
                word_count INTEGER NOT NULL DEFAULT 0,
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
        if "word_count" not in columns:
            self.connection.execute(
                "ALTER TABLE documents ADD COLUMN word_count INTEGER NOT NULL DEFAULT 0"
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
        if self.get_setting("word_count_backfill") != "1":
            for row in self.connection.execute("SELECT id FROM documents").fetchall():
                count = len(self.plain_text(self.read_content(row[0])).split())
                self.connection.execute(
                    "UPDATE documents SET word_count=? WHERE id=?", (count, row[0])
                )
            self.set_setting("word_count_backfill", "1")

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
        return Document(document_id, parent_id, title, "", position, 0, kind, 0)

    def documents(self) -> list[Document]:
        rows = self.db.execute(
            "SELECT id,parent_id,title,synopsis,position,word_target,kind,word_count "
            "FROM documents"
        ).fetchall()
        by_parent: dict[str | None, list[Document]] = {}
        for row in rows:
            document = Document(**dict(row))
            by_parent.setdefault(document.parent_id, []).append(document)
        ordered: list[Document] = []

        def visit(parent_id: str | None) -> None:
            for document in sorted(by_parent.get(parent_id, []),
                                   key=lambda d: d.position):
                ordered.append(document)
                visit(document.id)

        visit(None)
        return ordered

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

    def next_sibling(self, document_id: str) -> Document | None:
        """The document following this one under the same parent, if any."""
        row = self.db.execute(
            "SELECT parent_id,position FROM documents WHERE id=?", (document_id,)
        ).fetchone()
        if row is None:
            return None
        sibling = self.db.execute(
            "SELECT id,parent_id,title,synopsis,position,word_target,kind,word_count "
            "FROM documents WHERE parent_id IS ? AND position>? "
            "ORDER BY position LIMIT 1", (row[0], row[1]),
        ).fetchone()
        return Document(**dict(sibling)) if sibling else None

    def split_document(self, document_id: str, before_html: str,
                       after_html: str, *, new_title: str | None = None) -> Document:
        """Split a section into two at the cursor.

        The caller extracts the two HTML halves (Qt document fragments keep
        the formatting); this method snapshots the original, inserts a
        sibling right after it and writes both halves.
        """
        row = self.db.execute(
            "SELECT parent_id,title,position,kind FROM documents WHERE id=?",
            (document_id,),
        ).fetchone()
        if row is None:
            raise KeyError(document_id)
        if not self.plain_text(before_html):
            raise ValueError("Nothing before the cursor to keep.")
        if not self.plain_text(after_html):
            raise ValueError("Nothing after the cursor to split off.")
        parent_id, title, position, kind = row
        self.create_snapshot(document_id, "Before split")

        if new_title is None:
            taken = {
                r[0] for r in self.db.execute(
                    "SELECT title FROM documents WHERE parent_id IS ?",
                    (parent_id,),
                ).fetchall()
            }
            number = 2
            while f"{title} ({number})" in taken:
                number += 1
            new_title = f"{title} ({number})"

        new_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self.db:
            self.db.execute(
                "UPDATE documents SET position=position+1 "
                "WHERE parent_id IS ? AND position>?",
                (parent_id, position),
            )
            self.db.execute(
                "INSERT INTO documents(id,parent_id,title,position,kind,"
                "created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (new_id, parent_id, new_title, position + 1, kind, now, now),
            )
        self.write_content(document_id, before_html)
        self.write_content(new_id, after_html)
        return Document(new_id, parent_id, new_title, "", position + 1, 0, kind, 0)

    def merge_documents(self, first_id: str, second_id: str) -> Document:
        """Append the next sibling's content onto this document and delete it.

        `second` must immediately follow `first` under the same parent and
        must have no sub-documents. `first` is snapshotted before the merge;
        `second`'s snapshots are re-homed under `first` so its history
        survives. `second`'s metadata is dropped (the row cascade removes it).
        """
        if first_id == second_id:
            raise ValueError("A document cannot merge with itself.")
        for doc_id in (first_id, second_id):
            if not self.db.execute(
                "SELECT 1 FROM documents WHERE id=?", (doc_id,)
            ).fetchone():
                raise KeyError(doc_id)
        following = self.next_sibling(first_id)
        if following is None or following.id != second_id:
            raise ValueError(
                "Merge works with the immediately following sibling only."
            )
        if self.db.execute(
            "SELECT 1 FROM documents WHERE parent_id=? LIMIT 1", (second_id,)
        ).fetchone():
            raise ValueError(
                "The following section contains sub-documents; move them out first."
            )
        self.create_snapshot(first_id, "Before merge")
        with self.db:
            self.db.execute(
                "UPDATE snapshots SET document_id=? WHERE document_id=?",
                (first_id, second_id),
            )
        combined = self._join_html(self.read_content(first_id),
                                   self.read_content(second_id))
        self.write_content(first_id, combined)
        self.delete_document(second_id)
        row = self.db.execute(
            "SELECT id,parent_id,title,synopsis,position,word_target,kind,"
            "word_count FROM documents WHERE id=?", (first_id,),
        ).fetchone()
        return Document(**dict(row))

    @staticmethod
    def _body_content(html: str) -> str:
        match = re.search(r"<body[^>]*>(.*)</body>", html, flags=re.S | re.I)
        return match.group(1) if match else html

    @classmethod
    def _join_html(cls, first: str, second: str) -> str:
        body = cls._body_content(first) + cls._body_content(second)
        if re.search(r"<body[^>]*>.*</body>", first, flags=re.S | re.I):
            return re.sub(
                r"(<body[^>]*>).*(</body>)",
                lambda m: m.group(1) + body + m.group(2),
                first, count=1, flags=re.S | re.I,
            )
        return f"<html><body>{body}</body></html>"

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
        count = len(self.plain_text(html).split())
        self.db.execute(
            "UPDATE documents SET updated_at=?, word_count=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), count, document_id),
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

    @staticmethod
    def _compile_query(query: str, *, regex: bool, ignore_case: bool) -> re.Pattern:
        pattern = query if regex else re.escape(query)
        return re.compile(pattern, re.IGNORECASE if ignore_case else 0)

    def search_snippets(self, query: str, *, regex: bool = False,
                        ignore_case: bool = True, context: int = 40,
                        limit: int = 500,
                        fields: set[str] | None = None) -> list[tuple[Document, str, str]]:
        """Every match with its field and surrounding text, for previews.

        `fields` filters to any of "content", "title", "synopsis"; None means
        all three.
        """
        if not query:
            return []
        compiled = self._compile_query(query, regex=regex, ignore_case=ignore_case)
        results: list[tuple[Document, str, str]] = []
        for document in self.documents():
            candidates = [
                ("content", self.plain_text(self.read_content(document.id))),
                ("title", document.title),
                ("synopsis", document.synopsis),
            ]
            for field, text in candidates:
                if fields is not None and field not in fields:
                    continue
                for match in compiled.finditer(text):
                    start = max(0, match.start() - context)
                    end = min(len(text), match.end() + context)
                    prefix = "…" if start > 0 else ""
                    suffix = "…" if end < len(text) else ""
                    results.append((document, field, f"{prefix}{text[start:end]}{suffix}"))
                    if len(results) >= limit:
                        return results
        return results

    def replace(self, query: str, replacement: str, *,
                document_ids: set[str] | None = None,
                regex: bool = False, ignore_case: bool = True,
                in_titles: bool = False, in_synopses: bool = False) -> dict:
        """Replace across the project. Returns a count dict.

        In literal mode the replacement is inserted verbatim; in regex mode
        it is a normal re.sub pattern (backreferences work). The search runs
        against stored HTML, so matches interrupted by markup will not hit —
        the same limitation every plain exporter has.
        """
        if not query:
            return {"replacements": 0, "documents": 0, "titles": 0, "synopses": 0}
        compiled = self._compile_query(query, regex=regex, ignore_case=ignore_case)
        targets = [
            document for document in self.documents()
            if document_ids is None or document.id in document_ids
        ]
        counts = {"replacements": 0, "documents": 0, "titles": 0, "synopses": 0}
        insert = (lambda _match: replacement) if not regex else replacement
        for document in targets:
            touched = False
            html = self.read_content(document.id)
            replaced, count = compiled.subn(insert, html)
            if count:
                self.write_content(document.id, replaced)
                counts["replacements"] += count
                touched = True
            if in_titles and compiled.search(document.title):
                new_title, count = compiled.subn(insert, document.title)
                if count:
                    self.update_document(document.id, title=new_title)
                    counts["titles"] += count
                    counts["replacements"] += count
                    touched = True
            if in_synopses and compiled.search(document.synopsis):
                new_synopsis, count = compiled.subn(insert, document.synopsis)
                if count:
                    self.update_document(document.id, synopsis=new_synopsis)
                    counts["synopses"] += count
                    counts["replacements"] += count
                    touched = True
            if touched:
                counts["documents"] += 1
        return counts

    def metadata(self, document_id: str) -> dict[str, str]:
        rows = self.db.execute(
            "SELECT key,value FROM document_metadata WHERE document_id=? ORDER BY key",
            (document_id,),
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def metadata_keys(self) -> list[str]:
        """Every metadata key used anywhere in the project, sorted."""
        rows = self.db.execute(
            "SELECT DISTINCT key FROM document_metadata ORDER BY key"
        ).fetchall()
        return [row[0] for row in rows]

    def word_rollups(self) -> dict[str, int]:
        """Word count per document, containers summing all descendants."""
        documents = self.documents()
        by_id = {d.id: d for d in documents}
        children: dict[str | None, list[str]] = {}
        for document in documents:
            children.setdefault(document.parent_id, []).append(document.id)
        rollup: dict[str, int] = {}

        def visit(document_id: str) -> int:
            total = by_id[document_id].word_count
            for child_id in children.get(document_id, []):
                total += visit(child_id)
            rollup[document_id] = total
            return total

        for document in documents:
            if document.id not in rollup:
                visit(document.id)
        return rollup

    def metadata_entries(self, document_id: str) -> dict[str, tuple[str, str, list[str]]]:
        rows = self.db.execute(
            "SELECT key,value,value_type,options_json FROM document_metadata "
            "WHERE document_id=? ORDER BY key", (document_id,),
        ).fetchall()
        return {row[0]: (row[1], row[2], json.loads(row[3])) for row in rows}

    def metadata_entries_all(self) -> dict[str, dict[str, tuple[str, str, list[str]]]]:
        """Every document's metadata in one query, keyed by document id."""
        rows = self.db.execute(
            "SELECT document_id,key,value,value_type,options_json "
            "FROM document_metadata ORDER BY document_id,key"
        ).fetchall()
        result: dict[str, dict[str, tuple[str, str, list[str]]]] = {}
        for row in rows:
            result.setdefault(row[0], {})[row[1]] = (row[2], row[3], json.loads(row[4]))
        return result

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
        # documents() already walks the tree in binder order
        return self.documents()

    def _export_documents(self, selected_ids: set[str] | None) -> list[Document]:
        documents = [d for d in self.ordered_documents() if d.kind in EXPORT_KINDS]
        return documents if selected_ids is None else [d for d in documents if d.id in selected_ids]

    def _template_values(self, document: Document, content: str | None = None,
                         extra: dict[str, str] | None = None) -> dict[str, str]:
        if content is None:
            content = self.read_content(document.id)
        values = {
            "Title": document.title,
            "Kind": document.kind,
            "Synopsis": document.synopsis,
            "WordCount": str(document.word_count),
            "Content": content,
        }
        for key, value in self.metadata(document.id).items():
            values[f"Metadata.{key}"] = value
        if extra:
            values.update(extra)
        return values

    def render_template(self, document: Document, template: str,
                        *, html: bool = False) -> str:
        """Fill a one-off template string with ``${...}`` placeholders."""
        from .templates import PLACEHOLDER_RE

        values = self._template_values(document)
        if not html:
            values["Content"] = self.plain_text(values["Content"])

        def substitute(match: re.Match) -> str:
            key = match.group(1).strip()
            value = values.get(key, "")
            if html and key.lower() != "content":
                return escape(value)
            return value

        return PLACEHOLDER_RE.sub(substitute, template)

    def _nearest_chapter_ancestor(self, document_id: str,
                                  parent_map: dict[str, str | None],
                                  kinds: dict[str, str]) -> str | None:
        current = parent_map.get(document_id)
        while current is not None:
            if kinds.get(current) == "chapter":
                return current
            current = parent_map.get(current)
        return None

    def _render_document(self, document: Document, templates: TemplateSet,
                         html: bool, *, slot: str | None = None,
                         content: str | None = None,
                         extra: dict[str, str] | None = None) -> str:
        body = self.read_content(document.id) if content is None else content
        if not html:
            body = self.plain_text(body)
        values = self._template_values(document, content=body, extra=extra)
        if slot is None:
            slot = "chapter" if document.kind == "chapter" else "scene"
        return templates.render(slot, values, html=html)

    def compile_units(self, selected_ids: set[str] | None = None,
                      templates: TemplateSet | None = None,
                      *, html: bool = True) -> list[tuple[str, str]]:
        """Compile the manuscript into ordered ``(title, body)`` units.

        A unit is one chapter (its own text plus its descendant scenes, in
        binder order, separated by the scene-divider slot) or one standalone
        scene that belongs to no chapter. Every body is fully rendered
        through the template set.
        """
        templates = templates or TemplateSet.builtin()
        export_docs = self._export_documents(selected_ids)
        export_ids = {d.id for d in export_docs}
        all_docs = self.documents()
        parent_map = {d.id: d.parent_id for d in all_docs}
        kinds = {d.id: d.kind for d in all_docs}
        chapter_scenes: dict[str, list[Document]] = {}
        ordered: list[Document] = []
        for document in export_docs:
            chapter_id = self._nearest_chapter_ancestor(document.id, parent_map, kinds)
            if document.kind == "scene" and chapter_id in export_ids:
                chapter_scenes.setdefault(chapter_id, []).append(document)
            else:
                ordered.append(document)

        units: list[tuple[str, str]] = []
        chapter_number = 0
        scene_number = 0
        words_total = 0
        divider = templates.slot("scene_divider", html=html).strip()
        scene_end = templates.slot("scene_end", html=html).strip()
        chapter_end = templates.slot("chapter_end", html=html).strip()
        for document in ordered:
            if document.kind == "chapter":
                chapter_number += 1
                scene_number = 0
                parts: list[str] = []
                own = self.read_content(document.id)
                if not html:
                    own = self.plain_text(own)
                if own.strip():
                    parts.append(own)
                for index, scene in enumerate(chapter_scenes.get(document.id, [])):
                    scene_number += 1
                    if index > 0 and divider:
                        parts.append(templates.render("scene_divider", {}, html=html))
                    slot = "scene"
                    if index == 0 and templates.slot("first_scene", html=html).strip():
                        slot = "first_scene"
                    extra = {"ChapterNumber": str(chapter_number),
                             "SceneNumber": str(scene_number),
                             "WordsTotal": str(words_total + scene.word_count)}
                    parts.append(self._render_document(
                        scene, templates, html, slot=slot, extra=extra))
                    words_total += scene.word_count
                    if scene_end:
                        parts.append(templates.render(
                            "scene_end",
                            self._template_values(scene, content=""), html=html))
                extra = {"ChapterNumber": str(chapter_number),
                         "SceneNumber": "0",
                         "WordsTotal": str(words_total)}
                body = self._render_document(
                    document, templates, html, slot="chapter",
                    content="\n".join(parts), extra=extra)
                words_total += document.word_count
                if chapter_end:
                    body += "\n" + templates.render(
                        "chapter_end",
                        self._template_values(document, content=""), html=html)
                units.append((document.title, body))
            else:
                scene_number += 1
                extra = {"ChapterNumber": str(chapter_number),
                         "SceneNumber": str(scene_number),
                         "WordsTotal": str(words_total)}
                body = self._render_document(
                    document, templates, html, extra=extra)
                words_total += document.word_count
                if scene_end:
                    body += "\n" + templates.render(
                        "scene_end",
                        self._template_values(document, content=""), html=html)
                units.append((document.title, body))
        return units

    def export_text(self, destination: Path, selected_ids: set[str] | None = None,
                    templates: TemplateSet | None = None) -> None:
        templates = templates or TemplateSet.builtin()
        units = self.compile_units(selected_ids, templates, html=False)
        header = templates.render("project_header", {}, html=False)
        footer = templates.render("project_footer", {}, html=False)
        body = "\n\n\n".join(body for _title, body in units if body.strip())
        content = "\n".join(part for part in (header, body, footer) if part.strip())
        self._atomic_write(Path(destination), content.rstrip() + "\n")

    def export_html(self, destination: Path, selected_ids: set[str] | None = None,
                    templates: TemplateSet | None = None) -> None:
        templates = templates or TemplateSet.builtin()
        units = self.compile_units(selected_ids, templates, html=True)
        header = templates.render("project_header", {}, html=True)
        footer = templates.render("project_footer", {}, html=True)
        title = escape(self.get_setting("title", "Lekhak"))
        content = (
            "<!doctype html><meta charset='utf-8'>"
            f"<title>{title}</title>{header}"
            f"{''.join(body for _t, body in units)}{footer}"
        )
        self._atomic_write(Path(destination), content)

    def export_docx(self, destination: Path, selected_ids: set[str] | None = None,
                    templates: TemplateSet | None = None) -> None:
        """DOCX keeps structural headings (title as Heading 1/2) and plain
        body text; header/footer slots do not apply here. A Word TOC field
        (page numbers only) is inserted at the top; Word or LibreOffice
        fills it in on field update."""
        from docx import Document as DocxDocument
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        output = DocxDocument()
        output.core_properties.title = self.get_setting("title", "Lekhak")
        paragraph = output.add_paragraph()
        run = paragraph.add_run()
        begin = OxmlElement("w:fldChar")
        begin.set(qn("w:fldCharType"), "begin")
        instruction = OxmlElement("w:instrText")
        instruction.set(qn("xml:space"), "preserve")
        instruction.text = 'TOC \\o "1-3" \\z \\u'
        separate = OxmlElement("w:fldChar")
        separate.set(qn("w:fldCharType"), "separate")
        placeholder = OxmlElement("w:t")
        placeholder.text = "Update this field to build the table of contents."
        end = OxmlElement("w:fldChar")
        end.set(qn("w:fldCharType"), "end")
        for element in (begin, instruction, separate, placeholder, end):
            run._r.append(element)
        for document in self._export_documents(selected_ids):
            output.add_heading(document.title, level=1 if document.kind == "chapter" else 2)
            for paragraph in self.plain_text(self.read_content(document.id)).split("\n"):
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
                    templates: TemplateSet | None = None) -> None:
        templates = templates or TemplateSet.builtin()
        units = self.compile_units(selected_ids, templates, html=True)
        header = templates.render("project_header", {}, html=True)
        footer = templates.render("project_footer", {}, html=True)
        manifest, spine, nav_items, pages = [], [], [], []
        section_names = [f"section-{index}.xhtml" for index in range(1, len(units) + 1)]
        for index, ((title, body), filename) in enumerate(zip(units, section_names), start=1):
            item_id = f"section-{index}"
            pages.append((filename, "<?xml version='1.0' encoding='utf-8'?>"
                "<html xmlns='http://www.w3.org/1999/xhtml'><head>"
                f"<title>{escape(title)}</title></head><body>"
                f"{header}{body}{footer}</body></html>"))
            manifest.append(f"<item id='{item_id}' href='{filename}' media-type='application/xhtml+xml'/>")
            spine.append(f"<itemref idref='{item_id}'/>")
            nav_items.append(f"<li><a href='{filename}'>{escape(title)}</a></li>")
        if templates.slot("toc_page", html=True).strip():
            entries = "".join(
                f"<li><a href='{filename}'>{escape(title)}</a></li>"
                for (title, _body), filename in zip(units, section_names)
            )
            toc_body = templates.render("toc_page", {"Entries": entries}, html=True)
            pages.insert(0, ("toc.xhtml", "<?xml version='1.0' encoding='utf-8'?>"
                "<html xmlns='http://www.w3.org/1999/xhtml'><head>"
                "<title>Contents</title></head><body>"
                f"{header}{toc_body}{footer}</body></html>"))
            manifest.insert(0, "<item id='toc-page' href='toc.xhtml' "
                "media-type='application/xhtml+xml'/>")
            spine.insert(0, "<itemref idref='toc-page'/>")
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
