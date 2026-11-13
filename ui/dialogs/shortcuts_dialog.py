"""Keyboard shortcut reference."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ShortcutsDialog(QDialog):
    def __init__(self, shortcuts: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("میان‌برهای صفحه‌کلید")
        self.resize(480, 560)
        table = QTableWidget(len(shortcuts), 2)
        table.setHorizontalHeaderLabels(["فرمان", "میان‌بر"])
        table.verticalHeader().hide()
        table.setShowGrid(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for row, (label, keys) in enumerate(shortcuts):
            table.setItem(row, 0, QTableWidgetItem(label))
            key_item = QTableWidgetItem(keys)
            key_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 1, key_item)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("بستن")
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.addWidget(table, 1)
        layout.addWidget(buttons)
