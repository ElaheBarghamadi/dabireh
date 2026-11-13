"""Regression tests for damaged settings and backup handling."""

import json
from pathlib import Path

from app.settings import SettingsStore
from storage.history import BackupManager


def test_non_finite_settings_do_not_prevent_startup(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    store.path.write_text(json.dumps({"window_width": float("nan"), "default_font_size": float("inf"),
                                     "recent_limit": 10 ** 1000}), encoding="utf-8")
    settings = store.load()
    assert settings.window_width == 1280
    assert settings.default_font_size == 13
    assert settings.recent_limit == 10


def test_zero_backup_limit_creates_no_backup(tmp_path: Path) -> None:
    source = tmp_path / "doc.dbr"
    source.write_text("old", encoding="utf-8")
    manager = BackupManager(tmp_path / "backups", keep=0)
    assert manager.backup(source) is None
    assert manager.backups() == []


def test_backups_for_same_named_files_are_pruned_independently(tmp_path: Path) -> None:
    first = tmp_path / "one" / "document.dbr"
    second = tmp_path / "two" / "document.dbr"
    first.parent.mkdir()
    second.parent.mkdir()
    manager = BackupManager(tmp_path / "backups", keep=1)
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    manager.backup(first)
    manager.backup(second)
    first.write_text("new first", encoding="utf-8")
    manager.backup(first)
    backups = manager.backups()
    assert len(backups) == 2
    assert {backup.original_name for backup in backups} == {"document.dbr"}
    assert {backup.path.read_text(encoding="utf-8") for backup in backups} == {"new first", "second"}


def test_legacy_backups_remain_visible(tmp_path: Path) -> None:
    directory = tmp_path / "backups"
    directory.mkdir()
    (directory / "old.file.20261113-120000-123456.dbr.bak").write_text("old", encoding="utf-8")
    assert BackupManager(directory).backups()[0].original_name == "old.file.dbr"
