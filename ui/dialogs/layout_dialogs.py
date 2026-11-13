"""Header/footer, styles, character spacing, print options and go-to-page dialogs."""

from __future__ import annotations

import copy
from dataclasses import replace

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.document import CharStyle, HeaderFooter, NamedStyle, ParagraphStyle
from core.fields import FIELDS
from core.styles import display_name
from ui.dialogs.common import ColorField, choice_combo, persian_button_box

ALIGNMENTS = [("start", "ابتدای سطر"), ("center", "وسط"), ("end", "انتهای سطر")]


class _FieldLine(QWidget):
    """Line edit with buttons that insert header/footer fields."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.edit = QLineEdit(text)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.addWidget(self.edit)
        row = QHBoxLayout()
        row.setSpacing(3)
        for code, label in FIELDS:
            button = QPushButton(label)
            button.setAutoDefault(False)
            button.setToolTip(code)
            button.clicked.connect(lambda _checked=False, c=code: self.edit.insert(c))
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)

    def text(self) -> str:
        return self.edit.text()


class HeaderFooterDialog(QDialog):
    """Edits the running header and footer (shown on every page, in preview and exports)."""

    def __init__(self, value: HeaderFooter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("سرصفحه و پاصفحه")
        self.setMinimumWidth(560)
        self._value = value
        tabs = QTabWidget()
        self.lines: dict[str, _FieldLine] = {}
        for title, header_key, footer_key in (("همهٔ صفحه‌ها (صفحه‌های فرد)", "header", "footer"),
                                              ("صفحهٔ نخست", "first_header", "first_footer"),
                                              ("صفحه‌های زوج", "even_header", "even_footer")):
            page = QWidget()
            form = QFormLayout(page)
            for key, label in ((header_key, "سرصفحه:"), (footer_key, "پاصفحه:")):
                self.lines[key] = _FieldLine(getattr(value, key))
                form.addRow(label, self.lines[key])
            tabs.addTab(page, title)
        self.different_first = QCheckBox("صفحهٔ نخست متفاوت باشد")
        self.different_first.setChecked(value.different_first)
        self.different_odd_even = QCheckBox("صفحه‌های زوج و فرد متفاوت باشند")
        self.different_odd_even.setChecked(value.different_odd_even)
        self.header_align = choice_combo(ALIGNMENTS, value.header_align)
        self.footer_align = choice_combo(ALIGNMENTS, value.footer_align)
        self.number_format = choice_combo([("persian", "ارقام فارسی (۱، ۲، ۳)"), ("latin", "ارقام لاتین (1, 2, 3)"),
                                           ("roman", "رومی (i, ii, iii)")], value.number_format)
        self.font_size = QDoubleSpinBox()
        self.font_size.setRange(5, 40)
        self.font_size.setDecimals(1)
        self.font_size.setValue(value.font_size)
        options = QGroupBox("گزینه‌ها")
        form = QFormLayout(options)
        form.addRow(self.different_first)
        form.addRow(self.different_odd_even)
        form.addRow("تراز سرصفحه:", self.header_align)
        form.addRow("تراز پاصفحه:", self.footer_align)
        form.addRow("قالب شمارهٔ صفحه:", self.number_format)
        form.addRow("اندازهٔ قلم:", self.font_size)
        self.different_first.toggled.connect(lambda on: tabs.setTabEnabled(1, on))
        self.different_odd_even.toggled.connect(lambda on: tabs.setTabEnabled(2, on))
        tabs.setTabEnabled(1, value.different_first)
        tabs.setTabEnabled(2, value.different_odd_even)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(options)
        layout.addWidget(persian_button_box(self))

    def value(self) -> HeaderFooter:
        return replace(
            self._value,
            **{key: line.text() for key, line in self.lines.items()},
            different_first=self.different_first.isChecked(),
            different_odd_even=self.different_odd_even.isChecked(),
            header_align=self.header_align.currentData(),
            footer_align=self.footer_align.currentData(),
            number_format=self.number_format.currentData(),
            font_size=self.font_size.value(),
        )


class CharacterSpacingDialog(QDialog):
    def __init__(self, spacing: float, scale: float, underline: str | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("فاصله و مقیاس نویسه‌ها")
        self.spacing = QDoubleSpinBox()
        self.spacing.setRange(50, 300)
        self.spacing.setSuffix(" ٪")
        self.spacing.setValue(spacing or 100)
        self.scale = QSpinBox()
        self.scale.setRange(50, 200)
        self.scale.setSuffix(" ٪")
        self.scale.setValue(int(scale or 100))
        self.underline = choice_combo([("", "بدون زیرخط"), ("single", "خط ساده"), ("dash", "خط‌چین"),
                                       ("dot", "نقطه‌چین"), ("wave", "موجی")], underline or "")
        form = QFormLayout()
        form.addRow("فاصلهٔ نویسه‌ها (۱۰۰ = عادی):", self.spacing)
        form.addRow("مقیاس افقی نویسه‌ها (۱۰۰ = عادی):", self.scale)
        form.addRow("گونهٔ زیرخط:", self.underline)
        hint = QLabel("افزایش فاصلهٔ نویسه‌ها در خط فارسی اتصال حرف‌ها را از هم باز می‌کند؛ برای متن لاتین مناسب‌تر است.")
        hint.setWordWrap(True)
        hint.setObjectName("DialogHint")
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(persian_button_box(self))

    def values(self) -> tuple[float, float, str | None]:
        return self.spacing.value(), float(self.scale.value()), self.underline.currentData() or None


class StyleEditDialog(QDialog):
    def __init__(self, style: NamedStyle, existing: set[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ویرایش سبک")
        self._style = style
        self._existing = existing - {style.name}
        self.name = QLineEdit(style.name)
        self.name.setEnabled(not style.builtin)
        self.font = QLineEdit(style.char.font_family or "")
        self.font.setPlaceholderText("قلم پایهٔ سند")
        self.size = QDoubleSpinBox()
        self.size.setRange(0, 96)
        self.size.setSpecialValueText("اندازهٔ پایهٔ سند")
        self.size.setValue(style.char.font_size or 0)
        self.bold = QCheckBox("پررنگ")
        self.bold.setChecked(style.char.bold)
        self.italic = QCheckBox("مورب")
        self.italic.setChecked(style.char.italic)
        self.color = ColorField(style.char.color, none_text="خودکار")
        self.alignment = choice_combo([("start", "ابتدای سطر"), ("center", "وسط"), ("end", "انتهای سطر"),
                                       ("justify", "دوطرفه")], style.paragraph.alignment)
        self.line_spacing = QDoubleSpinBox()
        self.line_spacing.setRange(0.8, 5)
        self.line_spacing.setSingleStep(0.05)
        self.line_spacing.setValue(style.paragraph.line_spacing)
        self.before = QDoubleSpinBox()
        self.before.setRange(0, 200)
        self.before.setValue(style.paragraph.space_before)
        self.after = QDoubleSpinBox()
        self.after.setRange(0, 200)
        self.after.setValue(style.paragraph.space_after)
        self.background = ColorField(style.paragraph.background)
        self.level = choice_combo([("0", "متن (در فهرست مطالب نمی‌آید)"), ("1", "سرفصل سطح ۱"), ("2", "سرفصل سطح ۲"),
                                   ("3", "سرفصل سطح ۳")], str(style.heading_level))
        form = QFormLayout()
        form.addRow("نام سبک:", self.name)
        form.addRow("قلم:", self.font)
        form.addRow("اندازهٔ قلم:", self.size)
        row = QHBoxLayout()
        row.addWidget(self.bold)
        row.addWidget(self.italic)
        row.addStretch(1)
        form.addRow("", row)
        form.addRow("رنگ متن:", self.color)
        form.addRow("تراز:", self.alignment)
        form.addRow("فاصلهٔ سطرها:", self.line_spacing)
        form.addRow("فاصلهٔ پیش از بند (پوینت):", self.before)
        form.addRow("فاصلهٔ پس از بند (پوینت):", self.after)
        form.addRow("رنگ زمینهٔ بند:", self.background)
        form.addRow("نقش در فهرست مطالب:", self.level)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(persian_button_box(self))

    def accept(self) -> None:
        name = self.name.text().strip()
        if not name or name in self._existing:
            QMessageBox.warning(self, "سبک", "نام سبک خالی یا تکراری است.")
            return
        super().accept()

    def style(self) -> NamedStyle:
        char = replace(self._style.char, font_family=self.font.text().strip() or None,
                       font_size=self.size.value() or None, bold=self.bold.isChecked(),
                       italic=self.italic.isChecked(), color=self.color.color())
        paragraph = replace(self._style.paragraph, alignment=self.alignment.currentData(),
                            line_spacing=round(self.line_spacing.value(), 2), space_before=self.before.value(),
                            space_after=self.after.value(), background=self.background.color())
        return NamedStyle(self.name.text().strip(), char, paragraph, int(self.level.currentData()),
                          self._style.builtin)


class StylesDialog(QDialog):
    """Lists the document's styles; create, edit, rename, delete and apply them."""

    def __init__(self, editor, parent: QWidget | None = None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setWindowTitle("سبک‌ها")
        self.setMinimumSize(460, 420)
        self._editor = editor
        self.list = QListWidget()
        buttons = QVBoxLayout()
        for label, handler in (("اعمال بر بند", self._apply), ("سبک جدید…", self._new), ("ویرایش…", self._edit),
                               ("حذف", self._delete), ("بازگردانی پیش‌فرض", self._reset)):
            button = QPushButton(label)
            button.setAutoDefault(False)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        buttons.addStretch(1)
        close = QPushButton("بستن")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout = QHBoxLayout(self)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        self._fill()

    def _fill(self, select: str | None = None) -> None:
        self.list.clear()
        for name, style in self._editor.styles.items():
            label = display_name(name) if style.builtin else name
            self.list.addItem(label)
            self.list.item(self.list.count() - 1).setData(256, name)
        names = list(self._editor.styles)
        wanted = select or self._editor.current_style_name()
        self.list.setCurrentRow(names.index(wanted) if wanted in names else 0)

    def _current(self) -> NamedStyle | None:
        item = self.list.currentItem()
        return self._editor.styles.get(item.data(256)) if item else None

    def _apply(self) -> None:
        style = self._current()
        if style:
            self._editor.apply_style(style.name)

    def _new(self) -> None:
        name, ok = QInputDialog.getText(self, "سبک جدید", "نام سبک:")
        name = name.strip()
        if not ok or not name or name in self._editor.styles:
            return
        base = self._current()
        style = NamedStyle(name, copy.deepcopy(base.char) if base else CharStyle(),
                           copy.deepcopy(base.paragraph) if base else ParagraphStyle(), 0, False)
        dialog = StyleEditDialog(style, set(self._editor.styles), self)
        if dialog.exec():
            self._editor.save_style(dialog.style())
            self._fill(dialog.style().name)

    def _edit(self) -> None:
        style = self._current()
        if style is None:
            return
        dialog = StyleEditDialog(copy.deepcopy(style), set(self._editor.styles), self)
        if dialog.exec():
            self._editor.save_style(dialog.style(), old_name=style.name)
            self._fill(dialog.style().name)

    def _delete(self) -> None:
        style = self._current()
        if style is None:
            return
        if style.builtin:
            QMessageBox.information(self, "سبک‌ها", "سبک‌های پیش‌ساخته حذف نمی‌شوند؛ می‌توانید آن‌ها را ویرایش کنید.")
            return
        self._editor.delete_style(style.name)
        self._fill()

    def _reset(self) -> None:
        style = self._current()
        if style is not None and style.builtin:
            self._editor.reset_builtin_style(style.name)
            self._fill(style.name)


class PrintOptionsDialog(QDialog):
    """Page selection and scaling, shown before the system print dialog."""

    def __init__(self, page_count: int, current_page: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("گزینه‌های چاپ")
        self.page_count = page_count
        self.current_page = current_page
        self.range = choice_combo([("all", f"همهٔ صفحه‌ها ({page_count})"), ("current", f"صفحهٔ جاری ({current_page})"),
                                   ("custom", "صفحه‌های انتخابی")], "all")
        self.pages = QLineEdit()
        self.pages.setPlaceholderText("مثال: ۱-۳، ۵، ۸")
        self.pages.setEnabled(False)
        self.range.currentIndexChanged.connect(lambda _i: self.pages.setEnabled(self.range.currentData() == "custom"))
        self.fit = QCheckBox("هم‌اندازه کردن صفحه با کاغذ چاپگر")
        self.fit.setChecked(True)
        self.scale = QSpinBox()
        self.scale.setRange(10, 400)
        self.scale.setSuffix(" ٪")
        self.scale.setValue(100)
        self.scale.setEnabled(False)
        self.fit.toggled.connect(lambda on: self.scale.setEnabled(not on))
        form = QFormLayout()
        form.addRow("صفحه‌ها:", self.range)
        form.addRow("شمارهٔ صفحه‌ها:", self.pages)
        form.addRow(self.fit)
        form.addRow("مقیاس (اندازهٔ واقعی = ۱۰۰):", self.scale)
        hint = QLabel("چاپگر، تعداد نسخه، اندازه و جهت کاغذ در پنجرهٔ بعدی (چاپ سیستم) انتخاب می‌شوند.")
        hint.setWordWrap(True)
        hint.setObjectName("DialogHint")
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(persian_button_box(self, "ادامه"))

    def selected_pages(self) -> list[int]:
        from editor.export import parse_page_list

        mode = self.range.currentData()
        if mode == "current":
            return [self.current_page - 1]
        if mode == "custom":
            return parse_page_list(self.pages.text(), self.page_count)
        return list(range(self.page_count))

    def fit_to_paper(self) -> bool:
        return self.fit.isChecked()

    def scale_percent(self) -> float:
        return float(self.scale.value())
