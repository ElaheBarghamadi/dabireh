"""Light theme: one palette of design tokens and the application stylesheet."""

from __future__ import annotations

from dataclasses import dataclass
from string import Template

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

from ui.resources import resource_dir

UI_FONT_FAMILIES = ["Vazirmatn", "Segoe UI", "Tahoma"]
UI_FONT_SIZE = 10


@dataclass(frozen=True)
class Colors:
    accent: str = "#1f5fbf"
    accent_hover: str = "#1a52a6"
    accent_soft: str = "#dce8fb"
    accent_softer: str = "#eef4fd"
    surface: str = "#ffffff"
    chrome: str = "#f6f7f9"
    workspace: str = "#e6e9ee"
    border: str = "#d9dde3"
    border_strong: str = "#c3c9d2"
    text: str = "#1f2430"
    text_muted: str = "#667085"
    hover: str = "#eceff3"
    pressed: str = "#dfe4ea"
    page_border: str = "#cfd4dc"


COLORS = Colors()

_STYLESHEET = Template(
    """
QMainWindow, QDialog { background: $chrome; }
QToolTip { background: #2b303b; color: #ffffff; border: none; padding: 5px 8px; border-radius: 4px; }

QMenuBar { background: $surface; border-bottom: 1px solid $border; padding: 2px 6px; }
QMenuBar::item { padding: 6px 12px; border-radius: 6px; background: transparent; }
QMenuBar::item:selected, QMenuBar::item:pressed { background: $hover; }
QMenu { background: $surface; border: 1px solid $border_strong; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 7px 28px 7px 28px; border-radius: 5px; margin: 1px 0; }
QMenu::item:selected { background: $accent_soft; color: $text; }
QMenu::item:disabled { color: #a6adb8; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }
QMenu::icon { padding-right: 8px; padding-left: 8px; }

QToolBar { background: $surface; border: none; border-bottom: 1px solid $border; padding: 5px 8px; spacing: 2px; }
QToolBar::separator { width: 1px; background: $border; margin: 5px 6px; }
QToolButton { border: 1px solid transparent; border-radius: 6px; padding: 5px; min-width: 22px; min-height: 22px; background: transparent; }
QToolButton:hover { background: $hover; }
QToolButton:pressed { background: $pressed; }
QToolButton:checked { background: $accent_soft; border-color: #b7cdf3; }
QToolButton:disabled { background: transparent; }
QToolButton[popupMode="1"] { padding-left: 18px; }
QToolButton::menu-button { border: none; width: 16px; border-radius: 6px; }
QToolButton::menu-arrow { image: url($icons/chevron-down.svg); width: 10px; height: 10px; }
QToolButton::menu-indicator { image: none; }

QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
    background: $surface; border: 1px solid $border_strong; border-radius: 6px;
    padding: 4px 8px; min-height: 22px; selection-background-color: $accent; selection-color: #ffffff;
}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover { border-color: #9aa5b5; }
QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: $accent; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { image: url($icons/chevron-down.svg); width: 11px; height: 11px; }
QComboBox QAbstractItemView {
    background: $surface; border: 1px solid $border_strong; outline: none;
    selection-background-color: $accent_soft; selection-color: $text;
}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {
    border: none; width: 18px; background: transparent;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url($icons/chevron-up.svg); width: 9px; height: 9px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url($icons/chevron-down.svg); width: 9px; height: 9px; }

QPushButton {
    background: $surface; border: 1px solid $border_strong; border-radius: 6px;
    padding: 6px 16px; min-height: 22px; min-width: 64px;
}
QPushButton:hover { background: $hover; }
QPushButton:pressed { background: $pressed; }
QPushButton:default { background: $accent; border-color: $accent; color: #ffffff; }
QPushButton:default:hover { background: $accent_hover; }
QPushButton:disabled { color: #a6adb8; background: $chrome; }

QCheckBox { spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid $border_strong; border-radius: 4px; background: $surface; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url($icons/check.svg); }

QGroupBox { border: 1px solid $border; border-radius: 8px; margin-top: 14px; padding: 12px 10px 8px 10px; background: $surface; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top right; padding: 0 6px; right: 10px; color: $text_muted; }

QListWidget, QTableWidget { background: $surface; border: 1px solid $border; border-radius: 8px; outline: none; }
QListWidget::item { padding: 8px 10px; border-radius: 6px; }
QListWidget::item:selected, QTableWidget::item:selected { background: $accent_soft; color: $text; }
QHeaderView::section { background: $chrome; border: none; border-bottom: 1px solid $border; padding: 6px 10px; }

QStatusBar { background: $surface; border-top: 1px solid $border; color: $text_muted; }
QStatusBar::item { border: none; }
QStatusBar QLabel { color: $text_muted; padding: 3px 10px; }

#FindBar { background: $surface; border-bottom: 1px solid $border; }
#FindBar QLabel#FindStatus { color: $text_muted; }
#ColorSwatch { border: 1px solid $border_strong; border-radius: 4px; min-width: 20px; min-height: 20px; max-width: 20px; max-height: 20px; padding: 0; }
#ColorSwatch:hover { border: 2px solid $accent; }
#DialogHint { color: $text_muted; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #b9c0cb; border-radius: 4px; min-height: 36px; margin: 2px; }
QScrollBar::handle:vertical:hover { background: #99a2b0; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
QScrollBar::handle:horizontal { background: #b9c0cb; border-radius: 4px; min-width: 36px; margin: 2px; }
QScrollBar::handle:horizontal:hover { background: #99a2b0; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""
)


def build_stylesheet(colors: Colors = COLORS) -> str:
    tokens = dict(vars(colors))
    tokens["icons"] = (resource_dir() / "icons").as_posix()
    return _STYLESHEET.substitute(tokens)


def build_palette(colors: Colors = COLORS) -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: colors.chrome,
        QPalette.ColorRole.WindowText: colors.text,
        QPalette.ColorRole.Base: colors.surface,
        QPalette.ColorRole.AlternateBase: colors.chrome,
        QPalette.ColorRole.Text: colors.text,
        QPalette.ColorRole.Button: colors.surface,
        QPalette.ColorRole.ButtonText: colors.text,
        QPalette.ColorRole.Highlight: colors.accent,
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: "#2b303b",
        QPalette.ColorRole.ToolTipText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: "#98a1ae",
    }
    for role, value in roles.items():
        palette.setColor(role, QColor(value))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#a6adb8"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#a6adb8"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#a6adb8"))
    # Keep the text selection visible while a dialog or toolbar has the focus.
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor("#b9d0f5"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, QColor(colors.text))
    return palette


def ui_font() -> QFont:
    font = QFont()
    font.setFamilies(UI_FONT_FAMILIES)
    font.setPointSize(UI_FONT_SIZE)
    return font


def apply_theme(app: QApplication) -> None:
    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:
        app.setStyle(fusion)
    app.setPalette(build_palette())
    app.setFont(ui_font())
    app.setStyleSheet(build_stylesheet())
