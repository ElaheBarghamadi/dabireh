"""Vector icon set drawn from inline SVG paths (24×24 grid, stroke style)."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette

DEFAULT_COLOR = "#3b4350"
DISABLED_COLOR = "#b4bac4"
_SCALE = 3  # render at 3× so icons stay crisp on high-DPI displays

_PATHS: dict[str, str] = {
    "table": '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M3 9.5h18M3 14.5h18M9 4v16M15 4v16"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9.5" r="1.6"/><path d="M21 16l-5-5-8 8"/>',
    "draw": '<path d="M4 20l4-1 11-11-3-3L5 16zM14.5 6.5l3 3M4 20l1-4M3 22h18"/>',
    "layout": '<rect x="3" y="4" width="18" height="16" rx="1.5"/><rect x="5.5" y="7" width="6" height="5" rx=".5"/><path d="M14 8h4M14 11h4M6 16h12"/>',
    "shape": '<rect x="3" y="10" width="11" height="11" rx="1"/><circle cx="15.5" cy="8.5" r="5.5"/>',
    "equation": '<path d="M18 5H7l5.5 7L7 19h11"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "print": '<path d="M7 9V3h10v6"/><rect x="4" y="9" width="16" height="8" rx="1.5"/><rect x="7" y="14" width="10" height="7"/>',
    "painter": '<rect x="4" y="3" width="14" height="6" rx="1"/><path d="M18 6h2v5h-8v3"/><rect x="10.5" y="14" width="3" height="7" rx="1"/>',
    "header_footer": '<rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M8 7h8M8 17h8"/>',
    "page_break": '<path d="M6 3v5h12V3M6 21v-5h12v5"/><path d="M3 12h2M8 12h2M14 12h2M19 12h2" />',
    "note": '<path d="M5 4h14v12l-4 4H5z"/><path d="M15 20v-4h4"/><path d="M8 9h8M8 13h5"/>',
    "styles": '<path d="M4 7V5h12v2M10 5v14M7.5 19h5"/><path d="M15 12h5M17.5 12v7"/>',
    "toc": '<path d="M4 6h10M4 12h10M4 18h10M18 6h2M18 12h2M18 18h2"/>',
    "new": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M12 11.5v6M9 14.5h6"/>',
    "open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "save": '<path d="M5 3h11l5 5v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M7 3v5h8V3"/><path d="M7 21v-7h10v7"/>',
    "save_as": '<path d="M12 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v3"/><path d="M7 3v5h8V3"/><path d="M15.5 21l.6-2.7 4.6-4.6 2 2-4.6 4.6z"/>',
    "export": '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
    "undo": '<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
    "redo": '<path d="M15 14l5-5-5-5"/><path d="M20 9H10a6 6 0 0 0 0 12h3"/>',
    "cut": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12"/>',
    "copy": '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>',
    "paste": '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/>',
    "find": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    "replace": '<path d="M4 8h14M15 5l3 3-3 3"/><path d="M20 16H6M9 13l-3 3 3 3"/>',
    "bold": '<path stroke-width="2.4" d="M7 5h6a3.5 3.5 0 0 1 0 7H7zM7 12h7a3.5 3.5 0 0 1 0 7H7z"/>',
    "italic": '<path d="M19 4h-9M14 20H5M15 4L9 20"/>',
    "underline": '<path d="M6 4v7a6 6 0 0 0 12 0V4M4 21h16"/>',
    "strike": '<path d="M16 4H9a3 3 0 0 0-2.8 4M14 12a4 4 0 0 1 0 8H6M4 12h16"/>',
    "superscript": '<path d="M4 19l8-10M4 9l8 10"/><path d="M16 5.5a1.75 1.75 0 0 1 3.4.6c0 1.2-3.4 2.4-3.4 3.9h3.5"/>',
    "subscript": '<path d="M4 5l8 10M4 15l8-10"/><path d="M16 15.5a1.75 1.75 0 0 1 3.4.6c0 1.2-3.4 2.4-3.4 3.9h3.5"/>',
    "clear_format": '<path d="M7 21l-4.3-4.3a1 1 0 0 1 0-1.4l10-10a1 1 0 0 1 1.4 0l5.6 5.6a1 1 0 0 1 0 1.4L11 21zM22 21H7M5.5 11.5l8 8"/>',
    "align_left": '<path d="M3 6h18M3 12h12M3 18h16"/>',
    "align_right": '<path d="M3 6h18M9 12h12M5 18h16"/>',
    "align_center": '<path d="M3 6h18M6 12h12M4 18h16"/>',
    "align_justify": '<path d="M3 6h18M3 12h18M3 18h18"/>',
    "dir_rtl": '<path d="M17 3H10.5a3.5 3.5 0 0 0 0 7H12M12 3v10M16 3v10"/><path d="M7.5 15.5l-3 3 3 3M4.5 18.5h15"/>',
    "dir_ltr": '<path d="M17 3H10.5a3.5 3.5 0 0 0 0 7H12M12 3v10M16 3v10"/><path d="M16.5 15.5l3 3-3 3M19.5 18.5h-15"/>',
    "bullet": '<path d="M3 6h13M3 12h13M3 18h13"/><path stroke-width="3" d="M20 6h.01M20 12h.01M20 18h.01"/>',
    "numbered": '<path d="M3 6h12M3 12h12M3 18h12"/><path stroke-width="1.5" d="M19 4.5l1.2-.7V8M18.6 15.2a1.3 1.3 0 0 1 2.5.4c0 1-2.5 1.7-2.5 3.2h2.7"/>',
    "indent_more": '<path d="M3 6h18M3 18h18M3 12h9"/><path d="M21 12h-6M17.5 9.5L15 12l2.5 2.5"/>',
    "indent_less": '<path d="M3 6h18M3 18h18M3 12h9"/><path d="M15 12h6M18.5 9.5L21 12l-2.5 2.5"/>',
    "line_spacing": '<path d="M10 6h11M10 12h11M10 18h11"/><path d="M5 5v14M3 7l2-2 2 2M3 17l2 2 2-2"/>',
    "paragraph": '<path d="M18 4H9.5a4.5 4.5 0 0 0 0 9H12M12 4v16M16 4v16"/>',
    "text_color": '<path d="M6.5 15L12 3l5.5 12M8.6 10.5h6.8"/>',
    "highlight": '<path d="M14.5 3.5l5 5-8.5 8.5H7.5l-1.5-1.5v-3.5z"/><path d="M4 16.5h3"/>',
    "page": '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.4"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "up": '<path d="M6 15l6-6 6 6"/>',
    "down": '<path d="M6 9l6 6 6-6"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2"/>',
    "fonts": '<path d="M3 7V5h10v2M8 5v12M6 17h4"/><path d="M14 13v-1h7v1M17.5 12v7M16 19h3"/>',
    "keyboard": '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
    "zwnj": '<path d="M12 3v18M4 8l4 4-4 4M20 8l-4 4 4 4"/>',
    "digits": '<path d="M5 8l2-2v12M12 8a2.5 2.5 0 0 1 5 0c0 3-5 5-5 10h5"/>',
}


def _svg(name: str, color: str, extra: str = "") -> bytes:
    body = _PATHS[name]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        f"{body}{extra}</svg>"
    ).encode("utf-8")


def _render(svg: bytes, size: int) -> QPixmap:
    pixmap = QPixmap(size * _SCALE, size * _SCALE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg)).render(painter, QRectF(0, 0, size * _SCALE, size * _SCALE))
    painter.end()
    pixmap.setDevicePixelRatio(_SCALE)
    return pixmap


def _build(name: str, color: str, size: int, extra: str = "") -> QIcon:
    icon = QIcon()
    icon.addPixmap(_render(_svg(name, color, extra), size), QIcon.Mode.Normal)
    icon.addPixmap(_render(_svg(name, DISABLED_COLOR, extra), size), QIcon.Mode.Disabled)
    return icon


@lru_cache(maxsize=256)
def _cached_icon(name: str, color: str, size: int) -> QIcon:
    return _build(name, color, size)


def icon_color() -> str:
    app = QApplication.instance()
    return app.palette().color(QPalette.ColorRole.WindowText).name() if app else DEFAULT_COLOR


def icon(name: str, color: str | None = None, size: int = 20) -> QIcon:
    """Return an icon in the current theme's foreground colour."""
    return _cached_icon(name, color or icon_color(), size)


def color_bar_icon(name: str, bar_color: str | None, size: int = 20) -> QIcon:
    """Icon with a colour bar underneath (text colour / highlight buttons)."""
    fill = bar_color or "#ffffff"
    bar = f'<rect x="3" y="18.5" width="18" height="4" rx="1" fill="{fill}" stroke="#9aa2ae" stroke-width="0.6"/>'
    return _build(name, icon_color(), size, bar)


def app_icon() -> QIcon:
    """Application icon: the letter «د» on the accent colour."""
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1f5fbf"))
        painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
        font = QFont("Vazirmatn")
        font.setBold(True)
        font.setPixelSize(int(size * 0.62))
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(QRectF(0, -size * 0.08, size, size), Qt.AlignmentFlag.AlignCenter, "د")
        painter.end()
        result.addPixmap(pixmap)
    return result
