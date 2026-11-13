"""Construction of the storage services shared by the application."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.settings import AppSettings, SettingsStore, app_data_dir
from storage.autosave import AutosaveStore
from storage.database import Database
from storage.document_repository import DocumentRepository, RecentDocuments

from storage.history import BackupManager, ExportHistory, VersionStore

@dataclass
class Services:
    data_dir: Path
    settings_store: SettingsStore
    settings: AppSettings
    repository: DocumentRepository
    recents: RecentDocuments
    autosave_store: AutosaveStore
    database: Database
    versions: VersionStore
    export_history: ExportHistory
    backups: BackupManager
    templates_dir: Path

    @classmethod
    def create(cls, data_dir: Path | None = None) -> Services:
        data_dir = Path(data_dir) if data_dir else app_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        settings_store = SettingsStore(data_dir / "settings.json")
        settings = settings_store.load()
        database = Database(data_dir / "dabireh.sqlite3")
        return cls(
            data_dir=data_dir,
            settings_store=settings_store,
            settings=settings,
            repository=DocumentRepository(),
            recents=RecentDocuments(database, settings.recent_limit),
            autosave_store=AutosaveStore(database),
            database=database,
            versions=VersionStore(database, settings.version_limit),
            export_history=ExportHistory(database),
            backups=BackupManager(data_dir / "backups", settings.backup_limit),
            templates_dir=data_dir / "templates",
        )
