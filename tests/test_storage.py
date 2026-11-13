"""Saving, reopening, recent documents, settings, autosave and recovery."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from app.autosave_controller import AutosaveController
from app.main_window import MainWindow
from app.services import Services
from app.settings import AppSettings, SettingsStore
from core.document import Document, DocumentFormatError
from editor.text_editor import RichTextEditor
from storage.autosave import AutosaveStore, Snapshot
from storage.database import Database
from storage.document_repository import DocumentRepository, RecentDocuments, write_text_atomically
from tests.conftest import DATA_DIR, select_text, type_text

SAMPLE = DATA_DIR / "sample_document.dbr"


# 9. Document save and reopen ----------------------------------------------------
def test_sample_document_round_trips_through_editor_and_file(editor: RichTextEditor, tmp_path: Path) -> None:
    repository = DocumentRepository()
    original = repository.load(SAMPLE)
    editor.load_document(original)
    assert not editor.document().isModified()
    assert editor.toPlainText() == original.plain_text()

    from_editor = editor.to_document()
    assert from_editor.paragraphs == original.paragraphs  # nothing lost or altered by the editor
    assert (from_editor.page, from_editor.defaults) == (original.page, original.defaults)

    target = tmp_path / "پوشه" / "سند آزمایشی.dbr"  # Persian file and folder names
    repository.save(from_editor, target)
    reopened = repository.load(target)
    assert reopened.paragraphs == original.paragraphs
    assert reopened.metadata.title == "نمونهٔ سند دبیره"
    assert reopened.metadata.modified >= original.metadata.modified
    assert json.loads(target.read_text(encoding="utf-8"))["format"] == "dabireh-document"


def test_failed_save_keeps_the_previous_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "doc.dbr"
    write_text_atomically(target, "نسخهٔ قدیمی")

    def broken_replace(_source: str, _target: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError):
        write_text_atomically(target, "نسخهٔ جدید")
    assert target.read_text(encoding="utf-8") == "نسخهٔ قدیمی"
    assert list(tmp_path.iterdir()) == [target]  # no temporary files left behind


def test_loading_invalid_files(tmp_path: Path) -> None:
    repository = DocumentRepository()
    bad = tmp_path / "bad.dbr"
    bad.write_bytes(b"\xff\xfe\x00garbage")
    with pytest.raises(DocumentFormatError):
        repository.load(bad)
    with pytest.raises(FileNotFoundError):
        repository.load(tmp_path / "missing.dbr")


def test_plain_text_import_handles_legacy_windows_encoding(tmp_path: Path) -> None:
    repository = DocumentRepository()
    legacy = tmp_path / "old.txt"
    legacy.write_bytes("سلام دنيا\r\nخط دوم".encode("cp1256"))  # Windows-1256 only has the Arabic Yeh
    assert repository.load(legacy).plain_text() == "سلام دنيا\nخط دوم"
    assert repository.load(DATA_DIR / "mixed_text.txt").paragraphs[0].text == "سلام دنیا"
    exported = tmp_path / "out.txt"
    repository.export_plain_text(repository.load(SAMPLE), exported)
    assert "دبیره؛ واژه‌پرداز فارسی" in exported.read_text(encoding="utf-8")


# Recent documents and settings -----------------------------------------------------
def test_recent_documents_order_limit_and_removal(tmp_path: Path) -> None:
    recents = RecentDocuments(Database(tmp_path / "db.sqlite3"), limit=3)
    paths = [tmp_path / f"سند{index}.dbr" for index in range(5)]
    for path in paths:
        recents.add(path, path.stem)
    recents.add(paths[3], "دوباره")
    entries = recents.entries()
    assert [Path(entry.path).name for entry in entries] == ["سند3.dbr", "سند4.dbr", "سند2.dbr"]
    assert entries[0].title == "دوباره"
    recents.remove(entries[0].path)
    assert len(recents.entries()) == 2
    recents.clear()
    assert recents.entries() == []


def test_settings_round_trip_and_damaged_file(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    assert store.load() == AppSettings()
    settings = AppSettings(autosave_interval_seconds=45, default_font_size=14.0, author="نویسنده")
    store.save(settings)
    assert store.load() == settings
    store.path.write_text('{"autosave_interval_seconds": "soon", "recent_limit": 9999, "author": 5}', encoding="utf-8")
    loaded = store.load()
    assert (loaded.autosave_interval_seconds, loaded.recent_limit, loaded.author) == (30, 30, "")
    store.path.write_text("{broken", encoding="utf-8")
    assert store.load() == AppSettings()


# 10. Autosave and recovery --------------------------------------------------------
def _snapshot(key: str = "k1", text: str = "متن ذخیره‌نشده") -> Snapshot:
    return Snapshot(key, "", "سند", Document.from_plain_text(text).to_dict())


def test_autosave_store_save_list_delete(tmp_path: Path) -> None:
    store = AutosaveStore(Database(tmp_path / "db.sqlite3"))
    store.save(_snapshot("a", "یک"))
    store.save(_snapshot("b", "دو"))
    store.save(_snapshot("a", "یک ویرایش‌شده"))  # same document: replaced, not duplicated
    snapshots = {s.doc_key: s for s in store.snapshots()}
    assert set(snapshots) == {"a", "b"}
    assert snapshots["a"].document().plain_text() == "یک ویرایش‌شده"
    assert [s.doc_key for s in store.snapshots(exclude_key="a")] == ["b"]
    store.delete("a")
    assert [s.doc_key for s in store.snapshots()] == ["b"]


def test_autosave_store_survives_a_damaged_row(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite3")
    store = AutosaveStore(database)
    store.save(_snapshot("good"))
    with sqlite3.connect(database.path) as conn:
        conn.execute("INSERT INTO autosave_snapshots VALUES ('bad', '', '', '{oops', '2026-01-01')")
    assert [s.doc_key for s in store.snapshots()] == ["good"]


def test_autosave_controller_writes_in_background(qapp: QApplication, tmp_path: Path) -> None:
    store = AutosaveStore(Database(tmp_path / "db.sqlite3"))
    provided: list[Snapshot | None] = [_snapshot()]
    controller = AutosaveController(store, lambda: provided[0], interval_seconds=1, idle_ms=10_000)
    saved: list[str] = []
    controller.saved.connect(saved.append)

    controller._on_timer()  # nothing changed yet
    assert store.snapshots() == []

    controller.note_edit()
    controller._on_timer()  # the user is still typing: postponed, typing is not interrupted
    assert store.snapshots() == []

    assert controller.save_now() is True
    controller.flush()
    qapp.processEvents()
    assert [s.doc_key for s in store.snapshots()] == ["k1"]
    assert len(saved) == 1

    provided[0] = None  # unmodified document: nothing to store
    assert controller.save_now() is False
    controller.discard("k1")
    assert store.snapshots() == []
    controller.set_enabled(False)


def test_autosave_controller_reports_failures(qapp: QApplication, tmp_path: Path) -> None:
    store = AutosaveStore(Database(tmp_path / "db.sqlite3"))

    def failing_provider() -> Snapshot:
        raise RuntimeError("boom")

    controller = AutosaveController(store, failing_provider)
    errors: list[str] = []
    controller.failed.connect(errors.append)
    assert controller.save_now(blocking=True) is False
    assert errors


# Main window document life-cycle -----------------------------------------------------
def test_window_starts_with_a_usable_untitled_document(window: MainWindow) -> None:
    assert window.current_path is None
    assert "سند بی‌نام" in window.windowTitle()
    assert not window.isWindowModified()
    type_text(window.editor, "سلام")
    assert window.isWindowModified()


def test_window_save_and_reopen(window: MainWindow, tmp_path: Path) -> None:
    type_text(window.editor, "سلام Hello ۱۲۳")
    select_text(window.editor, "Hello")
    window.editor.set_bold(True)
    window.editor.set_alignment("center")
    target = tmp_path / "نامه.dbr"
    assert window.save_to_path(target)
    assert not window.isWindowModified() and window.current_path == target
    assert "نامه" in window.windowTitle()
    assert [Path(e.path).name for e in window.services.recents.entries()] == ["نامه.dbr"]

    window.new_document()
    assert window.editor.toPlainText() == "" and window.current_path is None
    assert window.open_path(target)
    assert window.editor.toPlainText() == "سلام Hello ۱۲۳"
    paragraph = window.editor.to_document().paragraphs[0]
    assert paragraph.style.alignment == "center"
    assert [run.text for run in paragraph.runs if run.style.bold] == ["Hello"]
    assert not window.isWindowModified()


def test_unsaved_changes_are_never_dropped_silently(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    type_text(window.editor, "متن مهم")
    answers = iter(["cancel", "cancel", "discard"])
    monkeypatch.setattr(window, "_ask_save_changes", lambda: next(answers))
    window.new_document()
    assert window.editor.toPlainText() == "متن مهم"  # cancelled: document kept
    assert window.open_path(SAMPLE) is False
    assert window.editor.toPlainText() == "متن مهم"
    assert window.open_path(SAMPLE) is True  # explicit discard


def test_failed_save_and_failed_open_keep_the_document(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    errors: list[str] = []
    monkeypatch.setattr(window, "_show_error", lambda text, details="": errors.append(text))
    type_text(window.editor, "متن")
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert window.save_to_path(blocker / "inside" / "doc.dbr") is False  # a file is in the way
    assert window.isWindowModified() and window.editor.toPlainText() == "متن"

    window.editor.document().setModified(False)
    broken = tmp_path / "broken.dbr"
    broken.write_text("not a document", encoding="utf-8")
    assert window.open_path(broken) is False
    assert window.open_path(tmp_path / "missing.dbr") is False
    assert window.editor.toPlainText() == "متن"
    assert len(errors) == 3


def test_text_files_are_imported_not_overwritten(window: MainWindow) -> None:
    assert window.open_path(DATA_DIR / "mixed_text.txt")
    assert window.current_path is None  # saving will ask for a .dbr name
    assert window.editor.document().firstBlock().text() == "سلام دنیا"
    assert "mixed_text" in window.windowTitle()


def test_autosave_and_crash_recovery(qapp: QApplication, services: Services, tmp_path: Path) -> None:
    first = MainWindow(services)
    type_text(first.editor, "نوشتهٔ ذخیره‌نشده with English")
    first.editor.set_alignment("center")
    assert first.autosave.save_now() is True
    first.autosave.flush()
    qapp.processEvents()
    assert first.autosave_label.text().startswith("ذخیرهٔ خودکار")
    # Simulate a crash: the window is dropped without closeEvent / saving.
    first.autosave.set_enabled(False)
    first.deleteLater()

    second = MainWindow(Services.create(services.data_dir))
    snapshots = second.services.autosave_store.snapshots()
    assert len(snapshots) == 1
    assert second.recover_snapshot(snapshots[0])
    assert second.editor.toPlainText() == "نوشتهٔ ذخیره‌نشده with English"
    assert second.editor.to_document().paragraphs[0].style.alignment == "center"
    assert second.isWindowModified()  # recovered work still has to be saved
    assert len(second.services.autosave_store.snapshots()) == 1  # kept until it is saved

    assert second.save_to_path(tmp_path / "recovered.dbr")
    assert second.services.autosave_store.snapshots() == []
    second.close()
    second.deleteLater()


def test_clean_close_leaves_no_recovery_snapshot(qapp: QApplication, services: Services, tmp_path: Path) -> None:
    window = MainWindow(services)
    window.show()
    window.resize(1000, 700)
    type_text(window.editor, "متن")
    window.autosave.save_now(blocking=True)
    assert len(services.autosave_store.snapshots()) == 1
    assert window.save_to_path(tmp_path / "a.dbr")
    window.close()
    assert services.autosave_store.snapshots() == []
    assert services.settings_store.load().window_width == 1000
    window.deleteLater()


def test_autosave_retries_after_failed_write(qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = AutosaveStore(Database(tmp_path / "db.sqlite3"))
    original = store.save
    monkeypatch.setattr(store, "save", lambda _snapshot: (_ for _ in ()).throw(OSError("disk full")))
    controller = AutosaveController(store, _snapshot, interval_seconds=1, idle_ms=0)
    controller.note_edit()
    assert controller.save_now(blocking=True) is False
    monkeypatch.setattr(store, "save", original)
    controller._on_timer()
    controller.flush()
    qapp.processEvents()
    assert store.snapshots()[0].document().plain_text() == "متن ذخیره‌نشده"


def test_blocking_autosave_waits_for_older_writes(qapp: QApplication, tmp_path: Path) -> None:
    import threading

    store = AutosaveStore(Database(tmp_path / "db.sqlite3"))
    real_save = store.save
    started = threading.Event()
    release = threading.Event()

    def slow_save(snapshot: Snapshot) -> str:
        if snapshot.document().plain_text() == "old":
            started.set()
            assert release.wait(5)
        return real_save(snapshot)

    store.save = slow_save
    current = [_snapshot(text="old")]
    controller = AutosaveController(store, lambda: current[0])
    assert controller.save_now()
    assert started.wait(5)
    current[0] = _snapshot(text="new")
    timer = threading.Timer(0.1, release.set)
    timer.start()
    try:
        assert controller.save_now(blocking=True)
    finally:
        release.set()
        timer.join()
        controller.flush()
    assert store.snapshots()[0].document().plain_text() == "new"


def test_late_autosave_failure_does_not_retry_discarded_document(qapp: QApplication, tmp_path: Path) -> None:
    store = AutosaveStore(Database(tmp_path / "db.sqlite3"))
    store.save = lambda _snapshot: (_ for _ in ()).throw(OSError("disk full"))
    controller = AutosaveController(store, _snapshot)
    controller.note_edit()
    assert controller.save_now()
    controller.discard("k1")
    qapp.processEvents()
    assert not controller._dirty


def test_background_autosave_failure_is_retried(qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = AutosaveStore(Database(tmp_path / "db.sqlite3"))
    original = store.save
    monkeypatch.setattr(store, "save", lambda _snapshot: (_ for _ in ()).throw(OSError("disk full")))
    controller = AutosaveController(store, _snapshot, idle_ms=0)
    controller.note_edit()
    assert controller.save_now()
    controller.flush()
    qapp.processEvents()
    assert controller._dirty
    monkeypatch.setattr(store, "save", original)
    controller._on_timer()
    controller.flush()
    qapp.processEvents()
    assert store.snapshots()[0].doc_key == "k1"


def test_changing_autosave_interval_updates_maximum_delay(qapp: QApplication, tmp_path: Path) -> None:
    controller = AutosaveController(AutosaveStore(Database(tmp_path / "db.sqlite3")), _snapshot)
    controller.set_interval(120)
    assert controller._max_delay_seconds == 240
