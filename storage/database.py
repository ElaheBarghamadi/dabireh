"""SQLite application database (recent documents and autosave snapshots).

Every operation opens its own short-lived connection, which makes the class
safe to use from the autosave worker thread as well as the UI thread.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recent_documents (
    path      TEXT PRIMARY KEY,
    title     TEXT NOT NULL DEFAULT '',
    opened_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS autosave_snapshots (
    doc_key     TEXT PRIMARY KEY,
    source_path TEXT NOT NULL DEFAULT '',
    title       TEXT NOT NULL DEFAULT '',
    payload     TEXT NOT NULL,
    saved_at    TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection; commit on success, roll back on error."""
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _initialise(self) -> None:
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version < SCHEMA_VERSION:
                conn.executescript(_SCHEMA)
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
