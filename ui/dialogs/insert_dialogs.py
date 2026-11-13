"""Dialogs for inserting and editing tables, images, shapes, equations, links and references."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.document import Table
from core.equation import EquationError, parse
from editor.equation_render import layout_equation, paint_equation
from editor.objects import SHAPE_KINDS, paint_shape
from ui.dialogs.common import ColorField, choice_combo, length_spin, persian_button_box

SHAPE_LABELS = {
    "line": "خط", "arrow": "پیکان", "connector": "اتصال‌دهنده", "rect": "مستطیل", "rounded": "مستطیل گوشه‌گرد",
    "ellipse": "بیضی", "circle": "دایره", "polygon": "چندضلعی", "callout": "حباب گفت‌وگو", "textbox": "کادر متن",
}
EQUATION_SNIPPETS: tuple[tuple[str, str], ...] = (
    ("کسر", r"\frac{a}{b}"), ("توان", r"x^{2}"), ("زیرنویس", r"x_{i}"), ("رادیکال", r"\sqrt{x}"),
    ("ریشهٔ چندم", r"\sqrt[n]{x}"), ("انتگرال", r"\int_{a}^{b} f(x)\,dx"), ("مجموع", r"\sum_{i=1}^{n} a_i"),
    ("حاصل‌ضرب", r"\prod_{i=1}^{n} a_i"), ("حد", r"\lim_{x \to 0} f(x)"),
    ("ماتریس", r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}"), ("بردار", r"\vec{v}"),
    ("α", r"\alpha"), ("β", r"\beta"), ("π", r"\pi"), ("θ", r"\theta"), ("λ", r"\lambda"), ("Δ", r"\Delta"),
    ("∞", r"\infty"), ("≤", r"\leq"), ("≥", r"\geq"), ("≠", r"\neq"), ("±", r"\pm"), ("×", r"\times"),
    ("→", r"\to"), ("∈", r"\in"), ("∂", r"\partial"),
)


def _spin(value: int, minimum: int, maximum: int) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(minimum, maximum)
    spin.setValue(value)
    return spin


def _double(value: float, minimum: float, maximum: float, suffix: str = "", step: float = 1.0,
            decimals: int = 1) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSingleStep(step)
    if suffix:
        spin.setSuffix(" " + suffix)
    spin.setValue(value)
    return spin


class InsertTableDialog(QDialog):
    def __init__(self, default_rtl: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("درج جدول")
        self.rows = _spin(3, 1, 200)
        self.columns = _spin(3, 1, 30)
        self.header = QCheckBox("سطر اول سرستون است (در هر صفحه تکرار می‌شود)")
        self.header.setChecked(True)
        self.direction = choice_combo([("rtl", "راست‌به‌چپ"), ("ltr", "چپ‌به‌راست")], "rtl" if default_rtl else "ltr")
        form = QFormLayout()
        form.addRow("تعداد سطر:", self.rows)
        form.addRow("تعداد ستون:", self.columns)
        form.addRow("جهت جدول:", self.direction)
        form.addRow(self.header)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(persian_button_box(self, "درج"))

    def values(self) -> tuple[int, int, int, str]:
        return (self.rows.value(), self.columns.value(), 1 if self.header.isChecked() and self.rows.value() > 1 else 0,
                self.direction.currentData())


class TablePropertiesDialog(QDialog):
    """Table-level properties; column widths are percentages of the table width."""

    def __init__(self, table: Table, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ویژگی‌های جدول")
        self._table = table
        self.direction = choice_combo([("rtl", "راست‌به‌چپ"), ("ltr", "چپ‌به‌راست")], table.direction)
        self.alignment = choice_combo([("start", "ابتدای سطر"), ("center", "وسط"), ("end", "انتهای سطر")],
                                      table.alignment)
        self.width = _double(table.width_percent, 10, 100, "٪")
        self.header_rows = _spin(table.header_rows, 0, max(0, len(table.rows) - 1))
        self.border_width = _double(table.border_width, 0, 10, "px", 0.5)
        self.border_color = ColorField(table.border_color, allow_none=False)
        self.padding = _double(table.cell_padding, 0, 40, "px")
        form = QFormLayout()
        form.addRow("جهت جدول:", self.direction)
        form.addRow("جای جدول در صفحه:", self.alignment)
        form.addRow("پهنای جدول:", self.width)
        form.addRow("سطرهای سرستون (تکرار در هر صفحه):", self.header_rows)
        form.addRow("ضخامت خط‌ها (صفر = بدون خط):", self.border_width)
        form.addRow("رنگ خط‌ها:", self.border_color)
        form.addRow("فاصلهٔ درونی خانه‌ها:", self.padding)
        columns = table.column_count
        widths = table.column_widths if len(table.column_widths) == columns else [100.0 / max(1, columns)] * columns
        self.column_spins = [_double(w, 2, 100, "٪") for w in widths]
        group = QGroupBox("پهنای ستون‌ها (از نخستین ستون)")
        grid = QGridLayout(group)
        for index, spin in enumerate(self.column_spins):
            grid.addWidget(QLabel(f"ستون {index + 1}:"), index // 3, (index % 3) * 2)
            grid.addWidget(spin, index // 3, (index % 3) * 2 + 1)
        equal = QPushButton("هم‌اندازه")
        equal.setAutoDefault(False)
        equal.clicked.connect(lambda: [s.setValue(100.0 / max(1, columns)) for s in self.column_spins])
        grid.addWidget(equal, (columns - 1) // 3 + 1, 0, 1, 2)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(group)
        layout.addWidget(persian_button_box(self))

    def table(self) -> Table:
        widths = [spin.value() for spin in self.column_spins]
        total = sum(widths) or 1.0
        return replace(
            self._table,
            direction=self.direction.currentData(),
            alignment=self.alignment.currentData(),
            width_percent=self.width.value(),
            header_rows=self.header_rows.value(),
            border_width=self.border_width.value(),
            border_color=self.border_color.color() or "#7a828e",
            cell_padding=self.padding.value(),
            column_widths=[round(w * 100.0 / total, 3) for w in widths],
        )


class ImageDialog(QDialog):
    """Size (with locked aspect ratio), rotation, crop, border and wrapping of an image."""

    def __init__(self, obj: dict[str, Any], natural: QSize | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ویژگی‌های تصویر")
        self._obj = dict(obj)
        self.replacement: str | None = None
        width, height = float(obj.get("width", 100)), float(obj.get("height", 100))
        self._ratio = width / height if height else 1.0
        self.width = _double(width, 8, 4000, "px")
        self.height = _double(height, 8, 4000, "px")
        self.lock = QCheckBox("حفظ نسبت پهنا به بلندی")
        self.lock.setChecked(True)
        self.width.valueChanged.connect(self._width_changed)
        self.height.valueChanged.connect(self._height_changed)
        self.rotation = _double(float(obj.get("rotation", 0)), -360, 360, "درجه", 90, 0)
        crop = list(obj.get("crop") or [0, 0, 0, 0]) + [0, 0, 0, 0]
        self.crop = [_double(float(crop[i]) * 100, 0, 90, "٪") for i in range(4)]
        self.border_width = _double(float(obj.get("border_width", 0)), 0, 20, "px", 0.5)
        self.border_color = ColorField(str(obj.get("border_color", "#000000")), allow_none=False)
        self.wrap = choice_combo([("inline", "هم‌ردیف با متن"), ("square_right", "شناور در راست (متن دور تصویر)"),
                                  ("square_left", "شناور در چپ (متن دور تصویر)")], str(obj.get("wrap", "inline")))
        size_box = QGroupBox("اندازه و چرخش")
        size_form = QFormLayout(size_box)
        size_form.addRow("پهنا:", self.width)
        size_form.addRow("بلندی:", self.height)
        size_form.addRow(self.lock)
        if natural is not None and natural.width() > 0:
            reset = QPushButton(f"اندازهٔ اصلی ({natural.width()} × {natural.height()})")
            reset.setAutoDefault(False)
            reset.clicked.connect(lambda: self._set_size(natural.width(), natural.height()))
            size_form.addRow(reset)
        size_form.addRow("چرخش:", self.rotation)
        crop_box = QGroupBox("برش (درصد از هر لبه)")
        crop_form = QFormLayout(crop_box)
        for label, spin in zip(("چپ:", "بالا:", "راست:", "پایین:"), self.crop, strict=True):
            crop_form.addRow(label, spin)
        look_box = QGroupBox("کادر و چینش")
        look_form = QFormLayout(look_box)
        look_form.addRow("ضخامت کادر:", self.border_width)
        look_form.addRow("رنگ کادر:", self.border_color)
        look_form.addRow("جای‌گیری در متن:", self.wrap)
        hint = QLabel("برای «بالا و پایین متن» تصویر را در بندی جدا بگذارید و بند را تراز کنید.")
        hint.setWordWrap(True)
        hint.setObjectName("DialogHint")
        look_form.addRow(hint)
        replace_button = QPushButton("جایگزینی تصویر…")
        replace_button.setAutoDefault(False)
        replace_button.clicked.connect(self._choose_replacement)
        self.replace_label = QLabel("")
        layout = QVBoxLayout(self)
        columns = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(size_box)
        left.addWidget(look_box)
        columns.addLayout(left)
        columns.addWidget(crop_box)
        layout.addLayout(columns)
        row = QHBoxLayout()
        row.addWidget(replace_button)
        row.addWidget(self.replace_label, 1)
        layout.addLayout(row)
        layout.addWidget(persian_button_box(self))

    def _set_size(self, width: float, height: float) -> None:
        self._ratio = width / height if height else 1.0
        for spin, value in ((self.width, width), (self.height, height)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    def _width_changed(self, value: float) -> None:
        if self.lock.isChecked() and self._ratio:
            self.height.blockSignals(True)
            self.height.setValue(value / self._ratio)
            self.height.blockSignals(False)
        elif self.height.value():
            self._ratio = value / self.height.value()

    def _height_changed(self, value: float) -> None:
        if self.lock.isChecked():
            self.width.blockSignals(True)
            self.width.setValue(value * self._ratio)
            self.width.blockSignals(False)
        elif value:
            self._ratio = self.width.value() / value

    def _choose_replacement(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        name, _ = QFileDialog.getOpenFileName(self, "جایگزینی تصویر", "", IMAGE_FILTER)
        if name:
            self.replacement = name
            self.replace_label.setText(name)

    def object(self) -> dict[str, Any]:
        result = dict(self._obj)
        result.update({
            "width": round(self.width.value(), 1), "height": round(self.height.value(), 1),
            "rotation": self.rotation.value(), "crop": [round(s.value() / 100, 4) for s in self.crop],
            "border_width": self.border_width.value(), "border_color": self.border_color.color() or "#000000",
            "wrap": self.wrap.currentData(),
        })
        return result


IMAGE_FILTER = "تصویر (*.png *.jpg *.jpeg *.webp *.svg *.bmp *.gif)"


class _ShapePreview(QWidget):
    def __init__(self, dialog: ShapeDialog) -> None:
        super().__init__()
        self._dialog = dialog
        self.setMinimumSize(220, 160)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        obj = self._dialog.object()
        scale = min((self.width() - 20) / max(1.0, obj["width"]), (self.height() - 20) / max(1.0, obj["height"]), 1.5)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(scale, scale)
        paint_shape(painter, QRectF(-obj["width"] / 2, -obj["height"] / 2, obj["width"], obj["height"]), obj)


class ShapeDialog(QDialog):
    def __init__(self, obj: dict[str, Any] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("شکل")
        obj = obj or {"type": "shape", "kind": "rect", "width": 160, "height": 90, "fill": "#dfe9fb",
                      "stroke": "#1f5fbf", "stroke_width": 2, "opacity": 1.0, "rotation": 0, "text": "", "sides": 5}
        self._obj = dict(obj)
        self._is_group = obj.get("kind") == "group"
        self.kind = choice_combo([(kind, SHAPE_LABELS[kind]) for kind in SHAPE_KINDS], str(obj.get("kind", "rect")))
        self.width = _double(float(obj.get("width", 160)), 8, 2000, "px")
        self.height = _double(float(obj.get("height", 90)), 4, 2000, "px")
        self.fill = ColorField(obj.get("fill"), none_text="بدون رنگ")
        self.stroke = ColorField(obj.get("stroke", "#1f5fbf"), none_text="بدون خط")
        self.stroke_width = _double(float(obj.get("stroke_width", 2)), 0, 30, "px", 0.5)
        self.opacity = _double(float(obj.get("opacity", 1.0)) * 100, 5, 100, "٪", 5, 0)
        self.rotation = _double(float(obj.get("rotation", 0)), -360, 360, "درجه", 15, 0)
        self.sides = _spin(int(obj.get("sides", 5) or 5), 3, 12)
        self.text = QLineEdit(str(obj.get("text", "")))
        form = QFormLayout()
        if not self._is_group:
            form.addRow("نوع شکل:", self.kind)
        form.addRow("پهنا:", self.width)
        form.addRow("بلندی:", self.height)
        if not self._is_group:
            form.addRow("رنگ درون:", self.fill)
            form.addRow("رنگ خط:", self.stroke)
            form.addRow("ضخامت خط:", self.stroke_width)
            form.addRow("تعداد ضلع (چندضلعی):", self.sides)
            form.addRow("متن درون شکل:", self.text)
        form.addRow("شفافیت (۱۰۰ = مات):", self.opacity)
        form.addRow("چرخش:", self.rotation)
        self.preview = _ShapePreview(self)
        body = QHBoxLayout()
        body.addLayout(form)
        body.addWidget(self.preview, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(body)
        layout.addWidget(persian_button_box(self))
        for widget in (self.width, self.height, self.stroke_width, self.opacity, self.rotation):
            widget.valueChanged.connect(lambda _v: self.preview.update())
        self.sides.valueChanged.connect(lambda _v: self.preview.update())
        self.kind.currentIndexChanged.connect(lambda _i: self.preview.update())
        self.text.textChanged.connect(lambda _t: self.preview.update())
        for field in (self.fill, self.stroke):
            field.button.clicked.connect(self.preview.update)

    def object(self) -> dict[str, Any]:
        result = dict(self._obj)
        result.update({"type": "shape", "width": round(self.width.value(), 1), "height": round(self.height.value(), 1),
                       "opacity": round(self.opacity.value() / 100, 2), "rotation": self.rotation.value()})
        if not self._is_group:
            result.update({"kind": self.kind.currentData(), "fill": self.fill.color(), "stroke": self.stroke.color(),
                           "stroke_width": self.stroke_width.value(), "sides": self.sides.value(),
                           "text": self.text.text()})
        return result


class _EquationPreview(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.latex = ""
        self.display = True
        self.family = "Cambria Math"
        self.setMinimumHeight(110)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.setPen(QColor("#cfd4dc"))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if not self.latex.strip():
            return
        size = 26.0
        box = layout_equation(self.latex, self.family, size, self.display)
        while size > 9 and (box.width > self.width() - 16 or box.height > self.height() - 12):
            size -= 2
            box = layout_equation(self.latex, self.family, size, self.display)
        paint_equation(painter, QRectF(self.rect()), self.latex, self.family, size, self.display)


class EquationDialog(QDialog):
    """LaTeX equation editor with a live preview."""

    def __init__(self, obj: dict[str, Any] | None = None, math_font: str = "Cambria Math",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("معادله")
        self.setMinimumWidth(560)
        obj = obj or {"latex": "", "display": True, "numbered": False}
        self.source = QPlainTextEdit(str(obj.get("latex", "")))
        self.source.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(11)
        self.source.setFont(mono)
        self.source.setFixedHeight(90)
        self.source.setPlaceholderText(r"\frac{a}{b} + x^2")
        self.preview = _EquationPreview()
        self.preview.family = math_font
        self.status = QLabel("")
        self.status.setObjectName("DialogHint")
        self.display = QCheckBox("معادلهٔ نمایشی (در سطر جدا و وسط‌چین)")
        self.display.setChecked(bool(obj.get("display")))
        self.numbered = QCheckBox("شماره‌گذاری خودکار")
        self.numbered.setChecked(bool(obj.get("numbered")))
        palette = QGridLayout()
        palette.setSpacing(4)
        for index, (label, snippet) in enumerate(EQUATION_SNIPPETS):
            button = QToolButton()
            button.setText(label)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setMinimumHeight(30)
            button.setToolTip(snippet)
            button.clicked.connect(lambda _checked=False, s=snippet: self._insert(s))
            palette.addWidget(button, index // 7, index % 7)
        self.buttons = persian_button_box(self)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("کد LaTeX:"))
        layout.addWidget(self.source)
        layout.addLayout(palette)
        layout.addWidget(QLabel("پیش‌نمایش:"))
        layout.addWidget(self.preview)
        layout.addWidget(self.status)
        layout.addWidget(self.display)
        layout.addWidget(self.numbered)
        layout.addWidget(self.buttons)
        self.source.textChanged.connect(self._refresh)
        self.display.toggled.connect(self._refresh)
        self._refresh()

    def _insert(self, snippet: str) -> None:
        self.source.insertPlainText(snippet)
        self.source.setFocus()

    def latex(self) -> str:
        return self.source.toPlainText().strip()

    def is_valid(self) -> bool:
        try:
            parse(self.latex())
        except EquationError:
            return False
        return bool(self.latex())

    def _refresh(self) -> None:
        latex = self.latex()
        message = ""
        try:
            parse(latex)
        except EquationError as error:
            message = f"خطا: {error}"
        self.status.setText(message)
        self.numbered.setEnabled(self.display.isChecked())
        self.preview.latex = latex
        self.preview.display = self.display.isChecked()
        self.preview.update()
        from PySide6.QtWidgets import QDialogButtonBox

        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(latex) and not message)

    def object(self) -> dict[str, Any]:
        display = self.display.isChecked()
        return {"type": "equation", "latex": self.latex(), "display": display,
                "numbered": display and self.numbered.isChecked()}


class LinkDialog(QDialog):
    def __init__(self, text: str, target: str, bookmarks: list[str], has_selection: bool,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("پیوند")
        self.text = QLineEdit(text)
        self.text.setEnabled(not has_selection)
        self.target = QLineEdit(target)
        self.target.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.target.setPlaceholderText("https://example.com")
        self.bookmark = QComboBox()
        self.bookmark.addItem("—", "")
        for name in bookmarks:
            self.bookmark.addItem(name, "#" + name)
        self.bookmark.currentIndexChanged.connect(
            lambda _i: self.target.setText(self.bookmark.currentData()) if self.bookmark.currentData() else None)
        form = QFormLayout()
        form.addRow("متن پیوند:", self.text)
        form.addRow("نشانی:", self.target)
        form.addRow("یا نشانک درون سند:", self.bookmark)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(persian_button_box(self))

    def values(self) -> tuple[str, str]:
        return self.target.text().strip(), self.text.text()


class CaptionDialog(QDialog):
    def __init__(self, kind: str = "figure", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("درج شرح")
        self.kind = choice_combo([("figure", "شکل"), ("table", "جدول")], kind)
        self.text = QLineEdit()
        form = QFormLayout()
        form.addRow("برچسب:", self.kind)
        form.addRow("متن شرح:", self.text)
        hint = QLabel("شماره به‌صورت خودکار و به ترتیب جای شرح‌ها در سند گذاشته می‌شود.")
        hint.setObjectName("DialogHint")
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(persian_button_box(self, "درج"))

    def values(self) -> tuple[str, str]:
        return self.kind.currentData(), self.text.text().strip()


class CrossReferenceDialog(QDialog):
    KIND_LABELS = {"heading": "سرفصل", "figure": "شکل", "table": "جدول", "bookmark": "نشانک"}

    def __init__(self, targets: list[tuple[str, str, Any]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ارجاع متقابل")
        self.setMinimumSize(420, 360)
        self._targets = targets
        self.list = QListWidget()
        for kind, label, _target in targets:
            QListWidgetItem(f"{self.KIND_LABELS.get(kind, kind)}: {label}", self.list)
        if targets:
            self.list.setCurrentRow(0)
        self.page = QCheckBox("درج شمارهٔ صفحه به‌جای متن")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("مقصد ارجاع:"))
        layout.addWidget(self.list, 1)
        layout.addWidget(self.page)
        layout.addWidget(persian_button_box(self, "درج"))

    def selection(self) -> tuple[str, str, Any, bool] | None:
        row = self.list.currentRow()
        if row < 0:
            return None
        kind, label, target = self._targets[row]
        return kind, label, target, self.page.isChecked()


__all__ = ["CaptionDialog", "CrossReferenceDialog", "EquationDialog", "IMAGE_FILTER", "ImageDialog",
           "InsertTableDialog", "LinkDialog", "ShapeDialog", "TablePropertiesDialog", "length_spin"]
