"""Timer-driven autosave that stays out of the typist's way.

The document is snapshotted on the UI thread (the Qt document may only be
touched there) but only once the user has paused typing; JSON encoding and
the database write then run on a worker thread.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

from storage.autosave import AutosaveStore, Snapshot

logger = logging.getLogger(__name__)


class _SaveTask(QRunnable):
    def __init__(self, controller: AutosaveController, snapshot: Snapshot, generation: int) -> None:
        super().__init__()
        self._controller = controller
        self._snapshot = snapshot
        self._generation = generation

    def run(self) -> None:
        self._controller.write(self._snapshot, self._generation)


class AutosaveController(QObject):
    saved = Signal(str)  # ISO timestamp of the stored snapshot
    failed = Signal(str)
    _retry_needed = Signal(int)

    def __init__(
        self,
        store: AutosaveStore,
        snapshot_provider: Callable[[], Snapshot | None],
        interval_seconds: int = 30,
        idle_ms: int = 1200,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._provider = snapshot_provider
        self._idle_seconds = idle_ms / 1000.0
        self._dirty = False
        self._generation = 0
        self._retry_needed.connect(self._retry_failed_save)
        self._last_edit = 0.0
        self._dirty_since = 0.0
        self._max_delay_seconds = max(10.0, interval_seconds * 2.0)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)  # one writer: snapshots are stored in order
        self._timer = QTimer(self)
        self._timer.setInterval(interval_seconds * 1000)
        self._timer.timeout.connect(self._on_timer)
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.setInterval(max(200, idle_ms // 2))
        self._idle_timer.timeout.connect(self._on_timer)

    # ------------------------------------------------------------- control
    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self._timer.start()
        else:
            self._timer.stop()
            self._idle_timer.stop()

    def is_enabled(self) -> bool:
        return self._timer.isActive()

    def set_interval(self, seconds: int) -> None:
        seconds = max(1, seconds)
        self._timer.setInterval(seconds * 1000)
        self._max_delay_seconds = max(10.0, seconds * 2.0)

    def note_edit(self) -> None:
        """Tell the controller that the document changed."""
        now = time.monotonic()
        if not self._dirty:
            self._dirty_since = now
        self._dirty = True
        self._last_edit = now

    def _on_timer(self) -> None:
        if not self._dirty:
            return
        now = time.monotonic()
        typing = now - self._last_edit < self._idle_seconds
        overdue = now - self._dirty_since > self._max_delay_seconds
        if typing and not overdue:
            self._idle_timer.start()  # user is typing: try again shortly
            return
        self.save_now()

    # -------------------------------------------------------------- saving
    def save_now(self, blocking: bool = False) -> bool:
        """Start a snapshot, or return its actual result when blocking."""
        try:
            snapshot = self._provider()
        except Exception:  # never let autosave break editing
            logger.exception("Could not create an autosave snapshot")
            self.failed.emit("ساخت نسخهٔ خودکار ممکن نشد.")
            return False
        self._dirty = False
        self._generation += 1
        generation = self._generation
        if snapshot is None:
            return False
        if blocking:
            self.flush()  # older queued writes must not overwrite this snapshot
            return self.write(snapshot, generation)
        self._pool.start(_SaveTask(self, snapshot, generation))
        return True

    def write(self, snapshot: Snapshot, generation: int | None = None) -> bool:
        """Store a snapshot (runs on the worker thread or, if blocking, inline)."""
        try:
            saved_at = self._store.save(snapshot)
        except Exception as error:
            logger.exception("Autosave failed")
            self.failed.emit(str(error))
            if generation is not None:
                self._retry_needed.emit(generation)
            return False
        self.saved.emit(saved_at)
        return True

    def _retry_failed_save(self, generation: int) -> None:
        # Ignore late results from a superseded snapshot or a discarded document.
        if generation == self._generation and not self._dirty:
            self.note_edit()

    def flush(self) -> None:
        """Wait until pending background writes are finished."""
        self._pool.waitForDone()

    def discard(self, doc_key: str) -> None:
        """Remove the snapshot of a document that was saved or abandoned."""
        self.flush()
        self._generation += 1
        self._dirty = False
        try:
            self._store.delete(doc_key)
        except Exception:
            logger.exception("Could not delete autosave snapshot")
