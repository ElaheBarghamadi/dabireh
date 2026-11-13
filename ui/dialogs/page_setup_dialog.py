"""Page setup: paper size (incl. custom), orientation, margins, border and background colour."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.document import PageSettings
from ui.dialogs.common import ColorField, choice_combo, length_spin, persian_button_box


class PageSetupDialog(QDialog):
    def __init__(self, page: PageSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("تنظیمات صفحه")
        self.setMinimumWidth(400)
        self._background = QColor(page.background)
        self._page = page

        self.size_combo = choice_combo(
            [("A4", "A4 — ۲۱۰ × ۲۹۷ میلی‌متر"), ("A5", "A5 — ۱۴۸ × ۲۱۰ میلی‌متر"),
             ("Letter", "Letter — ۲۱۶ × ۲۷۹ میلی‌متر"), ("Legal", "Legal — ۲۱۶ × ۳۵۶ میلی‌متر"),
             ("Custom", "اندازهٔ دلخواه")], page.size
        )
        self.orientation_combo = choice_combo([("portrait", "عمودی"), ("landscape", "افقی")], page.orientation)
        paper = QGroupBox("کاغذ")
        paper_form = QFormLayout(paper)
        paper_form.addRow("اندازه:", self.size_combo)
        paper_form.addRow("جهت صفحه:", self.orientation_combo)
        self.custom_width = length_spin(page.custom_width, 50, 1000, "میلی‌متر")
        self.custom_height = length_spin(page.custom_height, 50, 1500, "میلی‌متر")
        paper_form.addRow("پهنای دلخواه:", self.custom_width)
        paper_form.addRow("بلندی دلخواه:", self.custom_height)
        self.size_combo.currentIndexChanged.connect(self._sync_custom)
        self._sync_custom()

        self.margin_top = length_spin(page.margin_top, 5, 100, "میلی‌متر")
        self.margin_bottom = length_spin(page.margin_bottom, 5, 100, "میلی‌متر")
        self.margin_right = length_spin(page.margin_right, 5, 100, "میلی‌متر")
        self.margin_left = length_spin(page.margin_left, 5, 100, "میلی‌متر")
        margins = QGroupBox("حاشیه‌ها")
        margins_form = QFormLayout(margins)
        margins_form.addRow("بالا:", self.margin_top)
        margins_form.addRow("پایین:", self.margin_bottom)
        margins_form.addRow("راست:", self.margin_right)
        margins_form.addRow("چپ:", self.margin_left)

        self.background_button = QPushButton()
        self.background_button.clicked.connect(self._choose_background)
        reset_button = QPushButton("سفید")
        reset_button.clicked.connect(lambda: self._set_background(QColor("#ffffff")))
        background_row = QHBoxLayout()
        background_row.addWidget(self.background_button, 1)
        background_row.addWidget(reset_button)
        appearance = QGroupBox("ظاهر")
        appearance_form = QFormLayout(appearance)
        appearance_form.addRow("رنگ زمینهٔ صفحه:", background_row)
        self.border_width = length_spin(page.border_width, 0, 12, "پوینت", 0.5)
        self.border_color = ColorField(page.border_color, allow_none=False)
        appearance_form.addRow("ضخامت کادر صفحه:", self.border_width)
        appearance_form.addRow("رنگ کادر صفحه:", self.border_color)
        self._set_background(self._background)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)
        for group in (paper, margins, appearance):
            layout.addWidget(group)
        layout.addWidget(persian_button_box(self))

    def _sync_custom(self) -> None:
        custom = self.size_combo.currentData() == "Custom"
        self.custom_width.setEnabled(custom)
        self.custom_height.setEnabled(custom)

    def _set_background(self, color: QColor) -> None:
        self._background = color
        text_color = "#000000" if color.lightness() > 128 else "#ffffff"
        self.background_button.setText(color.name())
        self.background_button.setStyleSheet(f"background: {color.name()}; color: {text_color};")

    def _choose_background(self) -> None:
        color = QColorDialog.getColor(self._background, self, "رنگ زمینهٔ صفحه")
        if color.isValid():
            self._set_background(color)

    def page_settings(self) -> PageSettings:
        return PageSettings(
            size=self.size_combo.currentData(),
            orientation=self.orientation_combo.currentData(),
            margin_top=self.margin_top.value(),
            margin_bottom=self.margin_bottom.value(),
            margin_left=self.margin_left.value(),
            margin_right=self.margin_right.value(),
            background=self._background.name(),
            custom_width=self.custom_width.value(),
            custom_height=self.custom_height.value(),
            border_width=self.border_width.value(),
            border_color=self.border_color.color() or "#000000",
        )
