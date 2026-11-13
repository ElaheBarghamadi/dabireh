"""Lists autosaved snapshots that were not saved before the app closed."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.persian import format_timestamp
from storage.autosave import Snapshot


class RecoveryDialog(QDialog):
    """Result: ``selected`` holds the snapshot to recover; ``deleted`` those to drop."""

    def __init__(self, snapshots: list[Snapshot], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("بازیابی سندهای ذخیره‌نشده")
        self.setMinimumSize(520, 360)
        self.selected: Snapshot | None = None
        self.deleted: list[Snapshot] = []

        message = QLabel(
            "نسخه‌های زیر به‌طور خودکار نگه‌داری شده‌اند اما ذخیرهٔ نهایی نشده‌اند. "
            "سندی را برای بازیابی برگزینید."
        )
        message.setWordWrap(True)
        self.list_widget = QListWidget()
        for snapshot in snapshots:
            name = snapshot.title or (Path(snapshot.source_path).name if snapshot.source_path else "سند بی‌نام")
            location = snapshot.source_path or "ذخیره‌نشده"
            item = QListWidgetItem(f"{name}\n{format_timestamp(snapshot.saved_at)}  —  {location}")
            item.setData(Qt.ItemDataRole.UserRole, snapshot)
            self.list_widget.addItem(item)
        self.list_widget.setCurrentRow(0)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._recover())

        self.recover_button = QPushButton("بازیابی")
        self.recover_button.setDefault(True)
        self.delete_button = QPushButton("حذف نسخه")
        close_button = QPushButton("بعداً")
        self.recover_button.clicked.connect(self._recover)
        self.delete_button.clicked.connect(self._delete)
        close_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(self.recover_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(message)
        layout.addWidget(self.list_widget, 1)
        layout.addLayout(buttons)

    def _current(self) -> Snapshot | None:
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _recover(self) -> None:
        self.selected = self._current()
        if self.selected is not None:
            self.accept()

    def _delete(self) -> None:
        snapshot = self._current()
        if snapshot is None:
            return
        self.deleted.append(snapshot)
        self.list_widget.takeItem(self.list_widget.currentRow())
        if self.list_widget.count() == 0:
            self.reject()
