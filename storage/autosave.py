"""Crash-recovery snapshots.

Autosave never overwrites the user's file.  It stores a full copy of the
unsaved document in the application database; the snapshot is removed when the
document is saved or deliberately discarded, and offered for recovery if the
application did not get the chance to do so (crash, power loss).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.document import Document, now_iso
from storage.database import Database


@dataclass(frozen=True)
class Snapshot:
    doc_key: str
    source_path: str
    title: str
    payload: dict[str, Any]
    saved_at: str = ""

    def document(self) -> Document:
        return Document.from_dict(self.payload)


class AutosaveStore:
    def __init__(self, database: Database) -> None:
        self._db = database

    def save(self, snapshot: Snapshot) -> str:
        """Insert or replace the snapshot; returns the save timestamp."""
        saved_at = snapshot.saved_at or now_iso()
        payload = json.dumps(snapshot.payload, ensure_ascii=False)
        with self._db.connection() as conn:
            conn.execute(
                "INSERT INTO autosave_snapshots(doc_key, source_path, title, payload, saved_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(doc_key) DO UPDATE SET "
                "source_path = excluded.source_path, title = excluded.title, "
                "payload = excluded.payload, saved_at = excluded.saved_at",
                (snapshot.doc_key, snapshot.source_path, snapshot.title, payload, saved_at),
            )
        return saved_at

    def snapshots(self, exclude_key: str | None = None) -> list[Snapshot]:
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT doc_key, source_path, title, payload, saved_at "
                "FROM autosave_snapshots ORDER BY saved_at DESC"
            ).fetchall()
        result: list[Snapshot] = []
        for row in rows:
            if row["doc_key"] == exclude_key:
                continue
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError:
                continue  # unreadable row: keep it in the database, just do not offer it
            result.append(Snapshot(row["doc_key"], row["source_path"], row["title"], payload, row["saved_at"]))
        return result

    def delete(self, doc_key: str) -> None:
        with self._db.connection() as conn:
            conn.execute("DELETE FROM autosave_snapshots WHERE doc_key = ?", (doc_key,))
