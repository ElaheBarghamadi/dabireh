"""Document properties: metadata, default fonts and default direction."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from core.document import DocumentDefaults, Metadata
from core.persian import format_number, format_timestamp
from ui.dialogs.common import choice_combo, persian_button_box


class _FontChoice(QFontComboBox):
    """Font picker that keeps the stored family unless the user changes it.

    A document may name a font that is not installed on this computer (for
    example Cambria outside Windows); merely opening the dialog must not
    replace it with whatever the combo box happens to display.
    """

    def __init__(self, family: str) -> None:
        super().__init__()
        self._stored = family
        self.setCurrentFont(QFont(family))
        self._shown = self.currentFont().family()

    def family(self) -> str:
        chosen = self.currentFont().family()
        return self._stored if chosen == self._shown else chosen


def _font_combo(family: str) -> _FontChoice:
    return _FontChoice(family)


class DocumentDialog(QDialog):
    def __init__(
        self,
        metadata: Metadata,
        defaults: DocumentDefaults,
        statistics: tuple[int, int, int],
        location: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("مشخصات و تنظیمات سند")
        self.setMinimumWidth(480)
        self._metadata = metadata
        self._defaults = defaults

        self.title_edit = QLineEdit(metadata.title)
        self.author_edit = QLineEdit(metadata.author)
        self.subject_edit = QLineEdit(metadata.subject)
        self.keywords_edit = QLineEdit(metadata.keywords)
        info = QGroupBox("مشخصات")
        info_form = QFormLayout(info)
        info_form.addRow("عنوان سند:", self.title_edit)
        info_form.addRow("نویسنده:", self.author_edit)
        info_form.addRow("موضوع:", self.subject_edit)
        info_form.addRow("کلیدواژه‌ها:", self.keywords_edit)

        self.direction_combo = choice_combo(
            [("rtl", "راست‌به‌چپ (فارسی)"), ("ltr", "چپ‌به‌راست (لاتین)"), ("auto", "خودکار بر پایهٔ متن هر بند")],
            defaults.direction,
        )
        self.font_combo = _font_combo(defaults.font_family)
        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(6, 96)
        self.size_spin.setDecimals(1)
        self.size_spin.setValue(defaults.font_size)
        self.latin_combo = _font_combo(defaults.latin_font)
        self.math_combo = _font_combo(defaults.math_font)
        settings = QGroupBox("تنظیمات پایه")
        settings_form = QFormLayout(settings)
        settings_form.addRow("جهت پیش‌فرض بندها:", self.direction_combo)
        settings_form.addRow("قلم پایه (فارسی):", self.font_combo)
        settings_form.addRow("اندازهٔ قلم پایه:", self.size_spin)
        settings_form.addRow("قلم متن لاتین:", self.latin_combo)
        settings_form.addRow("قلم نمادهای ریاضی:", self.math_combo)
        hint = QLabel("قلم‌های لاتین و ریاضی با فرمان «قالب ‹ اعمال قلم بر پایهٔ خط» به کار می‌روند.")
        hint.setObjectName("DialogHint")
        hint.setWordWrap(True)
        settings_form.addRow(hint)

        words, characters, pages = statistics
        details = QGroupBox("اطلاعات")
        details_form = QFormLayout(details)
        details_form.addRow("تاریخ ایجاد:", QLabel(format_timestamp(metadata.created)))
        details_form.addRow("آخرین ذخیره:", QLabel(format_timestamp(metadata.modified)))
        details_form.addRow(
            "آمار:",
            QLabel(f"{format_number(pages)} صفحه، {format_number(words)} واژه، {format_number(characters)} نویسه"),
        )
        location_label = QLabel(location or "هنوز ذخیره نشده است")
        location_label.setWordWrap(True)
        details_form.addRow("محل پرونده:", location_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)
        for group in (info, settings, details):
            layout.addWidget(group)
        layout.addWidget(persian_button_box(self))

    def metadata(self) -> Metadata:
        return replace(
            self._metadata,
            title=self.title_edit.text().strip(),
            author=self.author_edit.text().strip(),
            subject=self.subject_edit.text().strip(),
            keywords=self.keywords_edit.text().strip(),
        )

    def defaults(self) -> DocumentDefaults:
        return replace(
            self._defaults,
            direction=self.direction_combo.currentData(),
            font_family=self.font_combo.family(),
            font_size=self.size_spin.value(),
            latin_font=self.latin_combo.family(),
            math_font=self.math_combo.family(),
        )
