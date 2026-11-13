"""Locating and loading bundled resources (fonts, icons)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase


def resource_dir() -> Path:
    """Folder of bundled resources, both from source and a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "resources"


def load_bundled_fonts() -> list[str]:
    """Register the fonts shipped with Dabireh; returns the loaded families."""
    families: list[str] = []
    fonts_dir = resource_dir() / "fonts"
    if not fonts_dir.is_dir():
        return families
    for font_file in sorted(fonts_dir.glob("*.[ot]tf")):
        font_id = QFontDatabase.addApplicationFont(str(font_file))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return sorted(set(families))
