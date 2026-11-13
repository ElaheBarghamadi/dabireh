"""Reading and writing document files, and the recent-documents list."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.document import FILE_EXTENSION, Document, DocumentFormatError, now_iso
from storage.database import Database

TEXT_EXTENSIONS = (".txt", ".text")


def write_text_atomically(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` without ever leaving a half-written file.

    The data goes to a temporary file in the same folder, is flushed to disk
    and then atomically renamed over the target, so a crash or a full disk
    cannot destroy the previous version of the document.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


class DocumentRepository:
    """Loads and saves :class:`Document` objects from/to the file system."""

    @staticmethod
    def is_native(path: Path) -> bool:
        return Path(path).suffix.lower() == FILE_EXTENSION

    def load(self, path: Path, template: Document | None = None) -> Document:
        """Load a ``.dbr`` document, or import a plain-text file.

        Raises ``OSError`` for I/O problems and ``DocumentFormatError`` when
        the content cannot be understood.
        """
        path = Path(path)
        if path.suffix.lower() in TEXT_EXTENSIONS:
            return Document.from_plain_text(self._read_plain_text(path), template)
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as error:
            raise DocumentFormatError("این پرونده یک سند دبیره نیست.") from error
        return Document.from_json(text)

    def save(self, document: Document, path: Path) -> None:
        document.metadata.modified = now_iso()
        write_text_atomically(Path(path), document.to_json())

    def export_plain_text(self, document: Document, path: Path) -> None:
        write_text_atomically(Path(path), document.plain_text() + "\n")

    @staticmethod
    def _read_plain_text(path: Path) -> str:
        raw = path.read_bytes()
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            encodings: tuple[str, ...] = ("utf-16",)
        else:
            encodings = ("utf-8-sig", "cp1256")  # cp1256: legacy Persian/Arabic Windows text
        for encoding in encodings:
            try:
                return raw.decode(encoding)
            except UnicodeError:
                continue
        raise DocumentFormatError("رمزگذاری این پروندهٔ متنی پشتیبانی نمی‌شود.")


@dataclass(frozen=True)
class RecentEntry:
    path: str
    title: str
    opened_at: str


class RecentDocuments:
    """Most-recently-used document list stored in SQLite."""

    def __init__(self, database: Database, limit: int = 10) -> None:
        self._db = database
        self.limit = limit

    def add(self, path: Path, title: str = "") -> None:
        with self._db.connection() as conn:
            conn.execute(
                "INSERT INTO recent_documents(path, title, opened_at) VALUES (?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET title = excluded.title, opened_at = excluded.opened_at",
                (str(Path(path).resolve()), title, _precise_now()),
            )
            conn.execute(
                "DELETE FROM recent_documents WHERE path NOT IN "
                "(SELECT path FROM recent_documents ORDER BY opened_at DESC LIMIT ?)",
                (self.limit,),
            )

    def entries(self) -> list[RecentEntry]:
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT path, title, opened_at FROM recent_documents ORDER BY opened_at DESC LIMIT ?",
                (self.limit,),
            ).fetchall()
        return [RecentEntry(row["path"], row["title"], row["opened_at"]) for row in rows]

    def remove(self, path: Path | str) -> None:
        with self._db.connection() as conn:
            conn.execute("DELETE FROM recent_documents WHERE path = ?", (str(path),))

    def clear(self) -> None:
        with self._db.connection() as conn:
            conn.execute("DELETE FROM recent_documents")


def _precise_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")
