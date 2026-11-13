"""Paragraph settings: alignment, direction, indents and spacing."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.document import ParagraphStyle
from core.units import mm_to_pt, pt_to_mm
from ui.dialogs.common import ColorField, choice_combo, length_spin, persian_button_box


class ParagraphDialog(QDialog):
    """Edits a :class:`ParagraphStyle`.

    Alignment is shown as a physical side (right/left) because that is what
    users see; it is converted to/from the direction-relative model value.
    """

    def __init__(self, style: ParagraphStyle, default_is_rtl: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("تنظیمات بند")
        self.setMinimumWidth(420)
        self._default_is_rtl = default_is_rtl
        self._style = style

        self.direction_combo = choice_combo(
            [("auto", "پیش‌فرض سند"), ("rtl", "راست‌به‌چپ"), ("ltr", "چپ‌به‌راست")], style.direction
        )
        self.alignment_combo = choice_combo(
            [("right", "راست‌چین"), ("center", "وسط‌چین"), ("left", "چپ‌چین"), ("justify", "تراز دوطرفه")],
            self._visual_alignment(style),
        )
        general = QGroupBox("چینش")
        general_form = QFormLayout(general)
        general_form.addRow("جهت بند:", self.direction_combo)
        general_form.addRow("تراز:", self.alignment_combo)

        self.indent_right = length_spin(pt_to_mm(style.indent_right), 0, 150, "میلی‌متر")
        self.indent_left = length_spin(pt_to_mm(style.indent_left), 0, 150, "میلی‌متر")
        self.first_line = length_spin(pt_to_mm(style.first_line_indent), -50, 100, "میلی‌متر")
        indents = QGroupBox("تورفتگی")
        indents_form = QFormLayout(indents)
        indents_form.addRow("از راست:", self.indent_right)
        indents_form.addRow("از چپ:", self.indent_left)
        indents_form.addRow("سطر اول:", self.first_line)

        self.space_before = length_spin(style.space_before, 0, 200, "پوینت")
        self.space_after = length_spin(style.space_after, 0, 200, "پوینت")
        self.line_spacing = QDoubleSpinBox()
        self.line_spacing.setRange(0.8, 5.0)
        self.line_spacing.setDecimals(2)
        self.line_spacing.setSingleStep(0.05)
        self.line_spacing.setSuffix(" برابر")
        self.line_spacing.setValue(style.line_spacing)
        spacing = QGroupBox("فاصله‌گذاری")
        spacing_form = QFormLayout(spacing)
        spacing_form.addRow("پیش از بند:", self.space_before)
        spacing_form.addRow("پس از بند:", self.space_after)
        spacing_form.addRow("فاصلهٔ سطرها:", self.line_spacing)
        presets = QHBoxLayout()
        for label, value in (("تک", 1.0), ("۱٫۱۵", 1.15), ("۱٫۵", 1.5), ("دو برابر", 2.0)):
            button = QPushButton(label)
            button.setAutoDefault(False)
            button.clicked.connect(lambda _checked=False, v=value: self.line_spacing.setValue(v))
            presets.addWidget(button)
        spacing_form.addRow("", presets)

        self.hanging = QCheckBox("تورفتگی آویخته (سطر اول بیرون، سطرهای بعد تو)")
        self.hanging.setChecked(style.first_line_indent < 0)
        self.hanging.toggled.connect(self._apply_hanging)
        indents_form.addRow(self.hanging)
        self.page_break = QCheckBox("شروع بند از صفحهٔ جدید")
        self.page_break.setChecked(style.page_break_before)
        self.background = ColorField(style.background)
        extras = QGroupBox("صفحه‌بندی و زمینه")
        extras_form = QFormLayout(extras)
        extras_form.addRow(self.page_break)
        extras_form.addRow("رنگ زمینهٔ بند:", self.background)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)
        for group in (general, indents, spacing, extras):
            layout.addWidget(group)
        layout.addWidget(persian_button_box(self))

    def _apply_hanging(self, enabled: bool) -> None:
        """Hanging indent = negative first-line indent plus an equal leading indent."""
        amount = abs(self.first_line.value()) or 7.5
        leading = self.indent_right if self._is_rtl(self.direction_combo.currentData()) else self.indent_left
        if enabled:
            self.first_line.setValue(-amount)
            leading.setValue(max(leading.value(), amount))
        else:
            self.first_line.setValue(0)

    def _is_rtl(self, direction: str) -> bool:
        return self._default_is_rtl if direction == "auto" else direction == "rtl"

    def _visual_alignment(self, style: ParagraphStyle) -> str:
        if style.alignment in ("center", "justify"):
            return style.alignment
        leading_is_right = self._is_rtl(style.direction)
        return "right" if (style.alignment == "start") == leading_is_right else "left"

    def paragraph_style(self) -> ParagraphStyle:
        direction = self.direction_combo.currentData()
        visual = self.alignment_combo.currentData()
        if visual in ("center", "justify"):
            alignment = visual
        else:
            alignment = "start" if (visual == "right") == self._is_rtl(direction) else "end"
        return replace(
            self._style,
            page_break_before=self.page_break.isChecked(),
            background=self.background.color(),
            alignment=alignment,
            direction=direction,
            line_spacing=round(self.line_spacing.value(), 2),
            space_before=self.space_before.value(),
            space_after=self.space_after.value(),
            first_line_indent=round(mm_to_pt(self.first_line.value()), 2),
            indent_left=round(mm_to_pt(self.indent_left.value()), 2),
            indent_right=round(mm_to_pt(self.indent_right.value()), 2),
        )
