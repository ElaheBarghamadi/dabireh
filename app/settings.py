"""Application settings stored as JSON, and the per-user data folder."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from storage.document_repository import write_text_atomically

APP_NAME = "Dabireh"
APP_DISPLAY_NAME = "دبیره"
APP_VERSION = "0.2.0"

logger = logging.getLogger(__name__)


def app_data_dir() -> Path:
    """Per-user folder for settings, the database and logs.

    ``DABIREH_HOME`` overrides the location (used by tests and portable use).
    """
    override = os.environ.get("DABIREH_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


@dataclass
class AppSettings:
    autosave_enabled: bool = True
    autosave_interval_seconds: int = 30
    visual_cursor_movement: bool = False
    default_font_family: str = "Vazirmatn"
    default_font_size: float = 13.0
    default_latin_font: str = "Cambria"
    default_math_font: str = "Cambria Math"
    default_direction: str = "rtl"
    default_page_size: str = "A4"
    default_margin_mm: float = 25.0
    author: str = ""
    recent_limit: int = 10
    window_width: int = 1280
    window_height: int = 860
    window_maximized: bool = False
    last_directory: str = ""
    shortcuts: dict[str, str] = field(default_factory=dict)  # action id -> key sequence overrides
    version_limit: int = 20
    backup_limit: int = 10

    def normalise(self) -> None:
        self.autosave_interval_seconds = min(max(self.autosave_interval_seconds, 5), 3600)
        self.recent_limit = min(max(self.recent_limit, 1), 30)
        self.window_width = min(max(self.window_width, 640), 10000)
        self.window_height = min(max(self.window_height, 480), 10000)
        self.default_font_size = min(max(self.default_font_size, 6.0), 96.0)
        self.default_margin_mm = min(max(self.default_margin_mm, 5.0), 100.0)
        if self.default_direction not in ("rtl", "ltr", "auto"):
            self.default_direction = "rtl"
        self.version_limit = min(max(self.version_limit, 1), 200)
        self.backup_limit = min(max(self.backup_limit, 0), 100)
        if not isinstance(self.shortcuts, dict):
            self.shortcuts = {}
        self.shortcuts = {str(k): str(v) for k, v in self.shortcuts.items() if isinstance(v, str)}
        if self.default_page_size not in ("A4", "A5", "Letter", "Legal"):
            self.default_page_size = "A4"


class SettingsStore:
    """Loads and saves :class:`AppSettings`; a damaged file yields defaults."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> AppSettings:
        settings = AppSettings()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return settings
        except (OSError, ValueError) as error:
            logger.warning("Settings file is unreadable, using defaults: %s", error)
            return settings
        if not isinstance(data, dict):
            return settings
        for item in fields(AppSettings):
            value = data.get(item.name)
            default = getattr(settings, item.name)
            if isinstance(default, bool):
                valid = isinstance(value, bool)
            elif isinstance(default, (int, float)):
                valid = isinstance(value, (int, float)) and not isinstance(value, bool)
                value = type(default)(value) if valid else value
            elif isinstance(default, dict):
                valid = isinstance(value, dict)
            else:
                valid = isinstance(value, str)
            if valid:
                setattr(settings, item.name, value)
        settings.normalise()
        return settings

    def save(self, settings: AppSettings) -> None:
        try:
            write_text_atomically(self.path, json.dumps(asdict(settings), ensure_ascii=False, indent=2))
        except OSError as error:
            logger.error("Could not save settings: %s", error)
