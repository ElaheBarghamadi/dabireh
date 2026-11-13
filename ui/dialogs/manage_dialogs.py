"""Document-management dialogs: versions, backups, export log, templates,
statistics, autosave settings and the shortcut editor."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.persian import format_number
from ui.dialogs.common import persian_button_box


class RecordsDialog(QDialog):
    """A table of records with action buttons.

    ``actions`` are (label, handler) pairs; a handler receives the selected
    row index and returns True when the dialog should close or "refresh" to
    reload rows through ``loader``.
    """

    def __init__(self, title: str, headers: Sequence[str], loader: Callable[[], list[Sequence[str]]],
                 actions: Sequence[tuple[str, Callable[[int], object]]], empty_text: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(640, 380)
        self._loader = loader
        self._empty_text = empty_text
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(list(headers))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.empty_label = QLabel(empty_text)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons = QHBoxLayout()
        self.action_buttons: list[QPushButton] = []
        for label, handler in actions:
            button = QPushButton(label)
            button.setAutoDefault(False)
            button.clicked.connect(lambda _checked=False, h=handler: self._run(h))
            buttons.addWidget(button)
            self.action_buttons.append(button)
        buttons.addStretch(1)
        close = QPushButton("بستن")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.empty_label)
        layout.addLayout(buttons)
        self.reload()

    def reload(self) -> None:
        rows = self._loader()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(str(value)))
        if rows:
            self.table.selectRow(0)
        self.table.setVisible(bool(rows))
        self.empty_label.setVisible(not rows)
        for button in self.action_buttons:
            button.setEnabled(bool(rows))

    def _run(self, handler: Callable[[int], object]) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        result = handler(row)
        if result == "refresh":
            self.reload()
        elif result:
            self.accept()


class TemplateDialog(QDialog):
    def __init__(self, builtin: Sequence[tuple[str, str]], user: Sequence[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("سند جدید از الگو")
        self.setMinimumSize(380, 380)
        self.list = QListWidget()
        for identifier, title in builtin:
            item = QListWidgetItem(title, self.list)
            item.setData(Qt.ItemDataRole.UserRole, ("builtin", identifier))
        for name in user:
            item = QListWidgetItem(f"{name} (الگوی من)", self.list)
            item.setData(Qt.ItemDataRole.UserRole, ("user", name))
        self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        self.delete_requested: str | None = None
        delete = QPushButton("حذف الگوی من")
        delete.setAutoDefault(False)
        delete.clicked.connect(self._delete)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("الگو را انتخاب کنید؛ سند ساخته‌شده کاملاً ویرایش‌پذیر است."))
        layout.addWidget(self.list, 1)
        layout.addWidget(delete)
        layout.addWidget(persian_button_box(self, "ساختن سند"))

    def _delete(self) -> None:
        choice = self.choice()
        if choice and choice[0] == "user":
            self.delete_requested = choice[1]
            self.reject()

    def choice(self) -> tuple[str, str] | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None


class StatisticsDialog(QDialog):
    def __init__(self, statistics: dict[str, int], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("آمار سند")
        form = QFormLayout()
        labels = (("pages", "صفحه"), ("paragraphs", "بند"), ("words", "واژه"), ("characters", "نویسه (با فاصله)"),
                  ("characters_no_spaces", "نویسه (بدون فاصله)"), ("tables", "جدول"), ("images", "تصویر"),
                  ("equations", "معادله"))
        for key, label in labels:
            form.addRow(label + ":", QLabel(format_number(statistics.get(key, 0))))
        minutes = max(1, round(statistics.get("words", 0) / 200)) if statistics.get("words") else 0
        form.addRow("زمان تقریبی خواندن:", QLabel(f"{format_number(minutes)} دقیقه"))
        close = QPushButton("بستن")
        close.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(close)


class AutosaveSettingsDialog(QDialog):
    def __init__(self, enabled: bool, interval: int, versions: int, backups: int,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("تنظیمات ذخیرهٔ خودکار و پشتیبان")
        self.enabled = QCheckBox("ذخیرهٔ خودکار برای بازیابی روشن باشد")
        self.enabled.setChecked(enabled)
        self.interval = QSpinBox()
        self.interval.setRange(5, 3600)
        self.interval.setSuffix(" ثانیه")
        self.interval.setValue(interval)
        self.versions = QSpinBox()
        self.versions.setRange(1, 200)
        self.versions.setValue(versions)
        self.backups = QSpinBox()
        self.backups.setRange(0, 100)
        self.backups.setValue(backups)
        form = QFormLayout()
        form.addRow(self.enabled)
        form.addRow("فاصلهٔ ذخیرهٔ خودکار:", self.interval)
        form.addRow("تعداد نسخه‌های نگه‌داری‌شده از هر سند:", self.versions)
        form.addRow("تعداد پشتیبان هر پرونده (صفر = خاموش):", self.backups)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(persian_button_box(self))

    def values(self) -> tuple[bool, int, int, int]:
        return self.enabled.isChecked(), self.interval.value(), self.versions.value(), self.backups.value()


class ShortcutEditorDialog(QDialog):
    """Lets the user change the key sequence of every command."""

    def __init__(self, rows: Sequence[tuple[str, str, str, str]], parent: QWidget | None = None) -> None:
        """``rows``: (action id, label, current shortcut, default shortcut)."""
        super().__init__(parent)
        self.setWindowTitle("تنظیم میان‌برهای صفحه‌کلید")
        self.setMinimumSize(560, 520)
        self._rows = list(rows)
        self.table = QTableWidget(len(self._rows), 2)
        self.table.setHorizontalHeaderLabels(["فرمان", "میان‌بر"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 220)
        self.editors: dict[str, QKeySequenceEdit] = {}
        for index, (action_id, label, current, _default) in enumerate(self._rows):
            item = QTableWidgetItem(label)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(index, 0, item)
            editor = QKeySequenceEdit(QKeySequence(current))
            editor.setClearButtonEnabled(True)
            self.editors[action_id] = editor
            self.table.setCellWidget(index, 1, editor)
        reset = QPushButton("بازگردانی همه به پیش‌فرض")
        reset.setAutoDefault(False)
        reset.clicked.connect(self._reset)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("روی خانهٔ میان‌بر کلیک کنید و کلیدهای تازه را بفشارید."))
        layout.addWidget(self.table, 1)
        layout.addWidget(reset)
        layout.addWidget(persian_button_box(self))

    def _reset(self) -> None:
        for action_id, _label, _current, default in self._rows:
            self.editors[action_id].setKeySequence(QKeySequence(default))

    def conflicts(self) -> list[str]:
        seen: dict[str, str] = {}
        duplicates: list[str] = []
        for action_id, label, _current, _default in self._rows:
            sequence = self.editors[action_id].keySequence().toString()
            if not sequence:
                continue
            if sequence in seen:
                duplicates.append(f"{sequence}: «{seen[sequence]}» و «{label}»")
            seen[sequence] = label
        return duplicates

    def accept(self) -> None:
        duplicates = self.conflicts()
        if duplicates:
            QMessageBox.warning(self, "میان‌بر تکراری", "این میان‌برها به دو فرمان داده شده‌اند:\n" + "\n".join(duplicates))
            return
        super().accept()

    def overrides(self) -> dict[str, str]:
        """Shortcuts that differ from the defaults (action id -> key sequence, "" = none)."""
        result: dict[str, str] = {}
        for action_id, _label, _current, default in self._rows:
            sequence = self.editors[action_id].keySequence().toString()
            if sequence != QKeySequence(default).toString():
                result[action_id] = sequence
        return result
