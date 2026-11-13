"""Saved versions, file backups and the export log."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.document import Document
from storage.database import Database

_SCHEMA = """
CREATE TABLE IF NOT EXISTS document_versions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    path      TEXT NOT NULL,
    title     TEXT NOT NULL DEFAULT '',
    payload   TEXT NOT NULL,
    words     INTEGER NOT NULL DEFAULT 0,
    saved_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_versions_path ON document_versions(path, id);
CREATE TABLE IF NOT EXISTS export_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL DEFAULT '',
    format      TEXT NOT NULL,
    path        TEXT NOT NULL,
    exported_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass(frozen=True)
class Version:
    id: int
    path: str
    title: str
    words: int
    saved_at: str


@dataclass(frozen=True)
class ExportRecord:
    id: int
    title: str
    format: str
    path: str
    exported_at: str


@dataclass(frozen=True)
class Backup:
    path: Path
    original_name: str
    created_at: str
    size: int


class VersionStore:
    """Keeps the last ``limit`` saved states of every document file."""

    def __init__(self, database: Database, limit: int = 20) -> None:
        self._database = database
        self.limit = limit
        with database.connection() as conn:
            conn.executescript(_SCHEMA)

    def add(self, path: Path | str, document: Document, words: int = 0) -> None:
        key = str(Path(path).resolve())
        payload = document.to_json()
        with self._database.connection() as conn:
            last = conn.execute("SELECT payload FROM document_versions WHERE path = ? ORDER BY id DESC LIMIT 1",
                                (key,)).fetchone()
            if last is not None and last["payload"] == payload:
                return  # nothing changed since the last version
            conn.execute("INSERT INTO document_versions(path, title, payload, words, saved_at) VALUES (?,?,?,?,?)",
                         (key, document.metadata.title, payload, words, _now()))
            conn.execute(
                "DELETE FROM document_versions WHERE path = ? AND id NOT IN "
                "(SELECT id FROM document_versions WHERE path = ? ORDER BY id DESC LIMIT ?)",
                (key, key, self.limit))

    def versions(self, path: Path | str) -> list[Version]:
        key = str(Path(path).resolve())
        with self._database.connection() as conn:
            rows = conn.execute("SELECT id, path, title, words, saved_at FROM document_versions WHERE path = ? "
                                "ORDER BY id DESC", (key,)).fetchall()
        return [Version(row["id"], row["path"], row["title"], row["words"], row["saved_at"]) for row in rows]

    def load(self, version_id: int) -> Document | None:
        with self._database.connection() as conn:
            row = conn.execute("SELECT payload FROM document_versions WHERE id = ?", (version_id,)).fetchone()
        return Document.from_json(row["payload"]) if row else None

    def delete(self, version_id: int) -> None:
        with self._database.connection() as conn:
            conn.execute("DELETE FROM document_versions WHERE id = ?", (version_id,))

    def move(self, old_path: Path | str, new_path: Path | str) -> None:
        with self._database.connection() as conn:
            conn.execute("UPDATE document_versions SET path = ? WHERE path = ?",
                         (str(Path(new_path).resolve()), str(Path(old_path).resolve())))


class ExportHistory:
    def __init__(self, database: Database, limit: int = 200) -> None:
        self._database = database
        self.limit = limit
        with database.connection() as conn:
            conn.executescript(_SCHEMA)

    def add(self, title: str, file_format: str, path: Path | str) -> None:
        with self._database.connection() as conn:
            conn.execute("INSERT INTO export_history(title, format, path, exported_at) VALUES (?,?,?,?)",
                         (title, file_format, str(path), _now()))
            conn.execute("DELETE FROM export_history WHERE id NOT IN "
                         "(SELECT id FROM export_history ORDER BY id DESC LIMIT ?)", (self.limit,))

    def records(self) -> list[ExportRecord]:
        with self._database.connection() as conn:
            rows = conn.execute("SELECT * FROM export_history ORDER BY id DESC").fetchall()
        return [ExportRecord(r["id"], r["title"], r["format"], r["path"], r["exported_at"]) for r in rows]

    def clear(self) -> None:
        with self._database.connection() as conn:
            conn.execute("DELETE FROM export_history")


class BackupManager:
    """Copies the previous file content into the backup folder before it is overwritten."""

    def __init__(self, directory: Path, keep: int = 10) -> None:
        self.directory = Path(directory)
        self.keep = keep

    def backup(self, path: Path | str) -> Path | None:
        """Back up ``path`` if it exists; returns the backup file."""
        source = Path(path)
        if self.keep <= 0 or not source.is_file():
            return None
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = self.directory / f"{source.name}.{self._source_id(source)}.{stamp}.bak"
        shutil.copy2(source, target)
        self._prune(source)
        return target

    @staticmethod
    def _source_id(source: Path) -> str:
        # Separate files with the same name in different directories.
        path = os.path.normcase(str(source.resolve()))
        return hashlib.sha256(os.fsencode(path)).hexdigest()[:16]

    def _matching(self, source: Path) -> list[Path]:
        prefix = f"{glob_escape(source.name)}.{self._source_id(source)}."
        return sorted(self.directory.glob(f"{prefix}*.bak"))

    def _prune(self, source: Path) -> None:
        matches = self._matching(source)
        for old in (matches[:-self.keep] if self.keep > 0 else matches):
            old.unlink(missing_ok=True)

    def backups(self) -> list[Backup]:
        if not self.directory.is_dir():
            return []
        result: list[Backup] = []
        for file in sorted(self.directory.glob("*.bak"), reverse=True):
            name = file.name[:-4]  # strip .bak
            new_parts = name.rsplit(".", 2)  # original name, source id, timestamp
            if (len(new_parts) == 3 and re.fullmatch(r"[0-9a-f]{16}", new_parts[1])
                    and re.fullmatch(r"\d{8}-\d{6}-\d{6}", new_parts[2])):
                original = new_parts[0]
            else:
                # Keep older backups available after upgrading.
                parts = name.rsplit(".", 2)  # stem, timestamp, suffix
                original = f"{parts[0]}.{parts[2]}" if len(parts) == 3 else file.name
            stat = file.stat()
            created = datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")
            result.append(Backup(file, original, created, stat.st_size))
        return result

    def delete(self, backup: Backup) -> None:
        backup.path.unlink(missing_ok=True)

    def restore(self, backup: Backup, target: Path | str) -> None:
        shutil.copy2(backup.path, target)


def glob_escape(text: str) -> str:
    import glob

    return glob.escape(text)
