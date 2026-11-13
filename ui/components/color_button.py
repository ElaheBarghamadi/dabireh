"""Tool button with a colour palette menu (text colour, highlight)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QGridLayout,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ui.icons import color_bar_icon

TEXT_COLORS = (
    "#000000", "#434a54", "#7f8792", "#c0392b", "#e67e22", "#f1c40f", "#27ae60", "#16a085",
    "#1f5fbf", "#2980b9", "#8e44ad", "#d63384", "#7b241c", "#935116", "#1e8449", "#1a5276",
)
HIGHLIGHT_COLORS = (
    "#fff59d", "#ffe082", "#ffccbc", "#f8bbd0", "#e1bee7", "#c5cae9", "#b3e5fc", "#b2dfdb",
    "#c8e6c9", "#dcedc8", "#ffff00", "#00ff00", "#00ffff", "#ff80ab", "#d7ccc8", "#eceff1",
)


class ColorButton(QToolButton):
    """Click applies the current colour; the arrow opens the palette.

    ``color_selected`` carries a ``QColor``, or ``None`` for "no colour".
    """

    color_selected = Signal(object)

    def __init__(
        self,
        icon_name: str,
        tooltip: str,
        colors: tuple[str, ...],
        initial: str,
        none_label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._color: QColor | None = QColor(initial)
        self.setToolTip(tooltip)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.clicked.connect(lambda: self.color_selected.emit(self._color))
        self._menu = QMenu(self)
        self._menu.addAction(self._palette_action(colors, none_label))
        self.setMenu(self._menu)
        self._refresh_icon()

    def _palette_action(self, colors: tuple[str, ...], none_label: str) -> QWidgetAction:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        none_button = QPushButton(none_label)
        none_button.clicked.connect(lambda: self._choose(None))
        layout.addWidget(none_button)
        grid = QGridLayout()
        grid.setSpacing(5)
        for index, value in enumerate(colors):
            swatch = QPushButton()
            swatch.setObjectName("ColorSwatch")
            swatch.setStyleSheet(f"background: {value};")
            swatch.setToolTip(value)
            swatch.clicked.connect(lambda _checked=False, v=value: self._choose(QColor(v)))
            grid.addWidget(swatch, index // 8, index % 8)
        layout.addLayout(grid)
        more_button = QPushButton("رنگ‌های بیشتر…")
        more_button.clicked.connect(self._choose_custom)
        layout.addWidget(more_button)
        action = QWidgetAction(self)
        action.setDefaultWidget(panel)
        return action

    def _choose(self, color: QColor | None) -> None:
        self._menu.close()
        if color is not None:
            self._color = color
            self._refresh_icon()
        self.color_selected.emit(color)

    def _choose_custom(self) -> None:
        self._menu.close()
        color = QColorDialog.getColor(self._color or QColor("#000000"), self.window(), "انتخاب رنگ")
        if color.isValid():
            self._choose(color)

    def _refresh_icon(self) -> None:
        self.setIcon(color_bar_icon(self._icon_name, self._color.name() if self._color else None))
