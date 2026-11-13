"""Shared helpers for dialogs."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QPushButton,
    QWidget,
)


def persian_button_box(dialog: QDialog, ok_text: str = "تأیید", cancel_text: str = "انصراف") -> QDialogButtonBox:
    """OK/Cancel button box with Persian captions wired to the dialog."""
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
    buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(cancel_text)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    return buttons


def length_spin(value: float, minimum: float, maximum: float, suffix: str, step: float = 1.0) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(1)
    spin.setSingleStep(step)
    spin.setSuffix(f" {suffix}")
    spin.setValue(value)
    return spin


def choice_combo(choices: list[tuple[str, str]], current: str) -> QComboBox:
    """Combo box of (value, label) pairs with ``current`` preselected."""
    combo = QComboBox()
    for value, label in choices:
        combo.addItem(label, value)
    index = combo.findData(current)
    combo.setCurrentIndex(max(0, index))
    return combo


class ColorField(QWidget):
    """Button showing a colour, with an optional "none" button; value is "#rrggbb" or ``None``."""

    def __init__(self, color: str | None, *, allow_none: bool = True, none_text: str = "بدون رنگ",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.button = QPushButton()
        self.button.clicked.connect(self._choose)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.button, 1)
        if allow_none:
            clear = QPushButton(none_text)
            clear.clicked.connect(lambda: self.set_color(None))
            layout.addWidget(clear)
        self._none_text = none_text
        self.set_color(color)

    def color(self) -> str | None:
        return self._color

    def set_color(self, color: str | None) -> None:
        self._color = color
        if color is None:
            self.button.setText(self._none_text)
            self.button.setStyleSheet("")
            return
        text_color = "#000000" if QColor(color).lightness() > 128 else "#ffffff"
        self.button.setText(color)
        self.button.setStyleSheet(f"background: {color}; color: {text_color};")

    def _choose(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._color or "#ffffff"), self, "انتخاب رنگ")
        if chosen.isValid():
            self.set_color(chosen.name())
