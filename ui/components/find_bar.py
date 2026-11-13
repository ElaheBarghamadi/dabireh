"""Inline, non-modal find and replace bar."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QToolButton,
    QWidget,
)

from core.persian import format_number
from editor import find_replace
from editor.find_replace import SearchOptions
from ui.icons import icon


class FindBar(QFrame):
    def __init__(self, editor: QTextEdit, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor = editor
        self.setObjectName("FindBar")

        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("جست‌وجو در سند")
        self.find_edit.setClearButtonEnabled(True)
        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("جایگزین با")
        self.replace_label = QLabel("جایگزینی:")

        self.previous_button = self._tool_button("up", "مورد قبلی (Shift+Enter)")
        self.next_button = self._tool_button("down", "مورد بعدی (Enter)")
        self.close_button = self._tool_button("close", "بستن (Esc)")
        self.replace_button = QPushButton("جایگزینی")
        self.replace_all_button = QPushButton("جایگزینی همه")

        self.case_check = QCheckBox("تطابق بزرگی و کوچکی حروف")
        self.whole_check = QCheckBox("فقط واژهٔ کامل")
        self.tolerant_check = QCheckBox("یکسان‌گرفتن «ی/ک» فارسی و عربی")
        self.tolerant_check.setChecked(True)
        self.format_combo = QComboBox()
        for value, label in (("", "هر قالبی"), ("bold", "فقط پررنگ"), ("italic", "فقط مورب"),
                             ("underline", "فقط زیرخط‌دار"), ("highlight", "فقط هایلایت‌شده"), ("link", "فقط پیوندها")):
            self.format_combo.addItem(label, value)
        self.format_combo.setToolTip("جست‌وجو بر پایهٔ قالب متن")
        self.status_label = QLabel()
        self.status_label.setObjectName("FindStatus")

        options = QHBoxLayout()
        options.setSpacing(14)
        for widget in (self.case_check, self.whole_check, self.tolerant_check):
            options.addWidget(widget)
        options.addWidget(self.format_combo)
        options.addStretch(1)
        options.addWidget(self.status_label)

        layout = QGridLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(6)
        layout.addWidget(QLabel("جست‌وجو:"), 0, 0)
        layout.addWidget(self.find_edit, 0, 1)
        layout.addWidget(self.previous_button, 0, 2)
        layout.addWidget(self.next_button, 0, 3)
        layout.addWidget(self.close_button, 0, 5)
        layout.addWidget(self.replace_label, 1, 0)
        layout.addWidget(self.replace_edit, 1, 1)
        layout.addWidget(self.replace_button, 1, 2, 1, 2)
        layout.addWidget(self.replace_all_button, 1, 4)
        layout.addLayout(options, 2, 1, 1, 5)
        layout.setColumnStretch(1, 1)

        self.find_edit.returnPressed.connect(self._on_return_pressed)
        self.find_edit.textChanged.connect(lambda: self.status_label.clear())
        self.replace_edit.returnPressed.connect(self.replace_one)
        self.next_button.clicked.connect(self.find_next)
        self.previous_button.clicked.connect(self.find_previous)
        self.replace_button.clicked.connect(self.replace_one)
        self.replace_all_button.clicked.connect(self.replace_all)
        self.close_button.clicked.connect(self.close_bar)
        self.hide()

    @staticmethod
    def _tool_button(icon_name: str, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setIcon(icon(icon_name))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        return button

    # ------------------------------------------------------------------ api
    def options(self) -> SearchOptions:
        return SearchOptions(
            case_sensitive=self.case_check.isChecked(),
            whole_words=self.whole_check.isChecked(),
            tolerant=self.tolerant_check.isChecked(),
            format_filter=self.format_combo.currentData() or "",
        )

    def open_bar(self, with_replace: bool) -> None:
        for widget in (self.replace_label, self.replace_edit, self.replace_button, self.replace_all_button):
            widget.setVisible(with_replace)
        selected = self._editor.textCursor().selectedText()
        if selected and "\u2029" not in selected:
            self.find_edit.setText(selected)
        self.status_label.clear()
        self.show()
        self.find_edit.setFocus()
        self.find_edit.selectAll()

    def close_bar(self) -> None:
        self.hide()
        self._editor.setFocus()

    def find_next(self) -> bool:
        return self._find(backward=False)

    def find_previous(self) -> bool:
        return self._find(backward=True)

    def _on_return_pressed(self) -> None:
        shift = QGuiApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        self._find(backward=bool(shift))

    def _find(self, backward: bool) -> bool:
        query = self.find_edit.text()
        if not query:
            return False
        found = find_replace.find(self._editor, query, self.options(), backward=backward)
        if found:
            total = find_replace.count_matches(self._editor.document(), query, self.options())
            self.status_label.setText(f"{format_number(total)} مورد")
        else:
            self.status_label.setText("موردی یافت نشد")
        return found

    def replace_one(self) -> None:
        query = self.find_edit.text()
        if not query:
            return
        find_replace.replace_current(self._editor, query, self.replace_edit.text(), self.options())
        remaining = find_replace.count_matches(self._editor.document(), query, self.options())
        self.status_label.setText(f"{format_number(remaining)} مورد باقی‌مانده" if remaining else "موردی باقی نمانده است")

    def replace_all(self) -> None:
        count = find_replace.replace_all(
            self._editor.document(), self.find_edit.text(), self.replace_edit.text(), self.options()
        )
        self.status_label.setText(f"{format_number(count)} مورد جایگزین شد" if count else "موردی یافت نشد")

    # --------------------------------------------------------------- events
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_bar()
            return
        super().keyPressEvent(event)
