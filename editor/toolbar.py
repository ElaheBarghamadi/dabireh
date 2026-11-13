"""Editor commands (QActions) and the formatting toolbars."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import QComboBox, QFontComboBox, QMainWindow, QMenu, QToolBar, QToolButton

from core.persian import to_latin_digits
from core.styles import display_name
from editor.formatting import FormatState
from editor.shortcuts import EXTRA_SHORTCUTS, shortcut_for
from editor.text_editor import RichTextEditor
from ui.components.color_button import HIGHLIGHT_COLORS, TEXT_COLORS, ColorButton
from ui.icons import icon

FONT_SIZES = (8, 9, 10, 11, 12, 13, 14, 16, 18, 20, 22, 24, 28, 32, 36, 48, 72)
LINE_SPACINGS = (1.0, 1.15, 1.5, 2.0, 2.5, 3.0)


@dataclass(frozen=True)
class ActionSpec:
    id: str
    text: str
    icon: str | None = None
    checkable: bool = False


ACTION_SPECS: tuple[ActionSpec, ...] = (
    # file
    ActionSpec("new", "سند جدید", "new"),
    ActionSpec("open", "باز کردن…", "open"),
    ActionSpec("save", "ذخیره", "save"),
    ActionSpec("save_as", "ذخیره با نام…", "save_as"),
    ActionSpec("export_pdf", "برون‌برد PDF…", "export"),
    ActionSpec("export_html", "برون‌برد HTML…"),
    ActionSpec("export_text", "برون‌برد متن ساده…"),
    ActionSpec("page_setup", "تنظیمات صفحه…", "page"),
    ActionSpec("document_properties", "مشخصات و تنظیمات سند…", "info"),
    ActionSpec("recover", "بازیابی سندهای ذخیره‌نشده…", "history"),
    ActionSpec("quit", "خروج"),
    # edit
    ActionSpec("undo", "واگرد", "undo"),
    ActionSpec("redo", "ازنو", "redo"),
    ActionSpec("cut", "برش", "cut"),
    ActionSpec("copy", "رونوشت", "copy"),
    ActionSpec("paste", "چسباندن", "paste"),
    ActionSpec("paste_plain", "چسباندن بدون قالب"),
    ActionSpec("select_all", "انتخاب همه"),
    ActionSpec("find", "جست‌وجو", "find"),
    ActionSpec("replace", "جست‌وجو و جایگزینی", "replace"),
    # character format
    ActionSpec("bold", "پررنگ", "bold", True),
    ActionSpec("italic", "مورب", "italic", True),
    ActionSpec("underline", "زیرخط", "underline", True),
    ActionSpec("strike", "خط‌خورده", "strike", True),
    ActionSpec("superscript", "بالانویس", "superscript", True),
    ActionSpec("subscript", "زیرنویس", "subscript", True),
    ActionSpec("clear_format", "پاک‌کردن قالب‌بندی", "clear_format"),
    ActionSpec("script_fonts", "اعمال قلم بر پایهٔ خط (فارسی / لاتین / ریاضی)", "fonts"),
    # paragraph
    ActionSpec("align_right", "راست‌چین", "align_right", True),
    ActionSpec("align_center", "وسط‌چین", "align_center", True),
    ActionSpec("align_left", "چپ‌چین", "align_left", True),
    ActionSpec("align_justify", "تراز دوطرفه", "align_justify", True),
    ActionSpec("dir_rtl", "بند راست‌به‌چپ", "dir_rtl", True),
    ActionSpec("dir_ltr", "بند چپ‌به‌راست", "dir_ltr", True),
    ActionSpec("bullet", "فهرست نشانه‌دار", "bullet", True),
    ActionSpec("numbered", "فهرست شماره‌دار", "numbered", True),
    ActionSpec("indent_more", "افزایش تورفتگی", "indent_more"),
    ActionSpec("indent_less", "کاهش تورفتگی", "indent_less"),
    ActionSpec("paragraph", "تنظیمات بند…", "paragraph"),
    # Persian / bidi tools
    ActionSpec("zwnj", "درج نیم‌فاصله", "zwnj"),
    ActionSpec("insert_lrm", "درج نشانهٔ چپ‌به‌راست (LRM)"),
    ActionSpec("insert_rlm", "درج نشانهٔ راست‌به‌چپ (RLM)"),
    ActionSpec("isolate_ltr", "جداسازی بخش انتخاب‌شده به‌صورت چپ‌به‌راست"),
    ActionSpec("digits_persian", "تبدیل ارقام به فارسی", "digits"),
    ActionSpec("digits_latin", "تبدیل ارقام به لاتین"),
    ActionSpec("visual_cursor", "حرکت دیداری مکان‌نما با کلیدهای جهت‌نما", None, True),
    ActionSpec("autosave_enabled", "ذخیرهٔ خودکار", None, True),
    # ---- phase 2: file
    ActionSpec("new_template", "سند جدید از الگو…"),
    ActionSpec("save_template", "ذخیرهٔ سند به‌عنوان الگو…"),
    ActionSpec("export_docx", "برون‌برد Word (DOCX)…"),
    ActionSpec("export_rtf", "برون‌برد RTF…"),
    ActionSpec("export_png", "برون‌برد تصویر PNG…"),
    ActionSpec("export_svg", "برون‌برد SVG…"),
    ActionSpec("print", "چاپ…", "print"),
    ActionSpec("print_preview", "پیش‌نمایش چاپ…"),
    ActionSpec("versions", "تاریخچهٔ نسخه‌های سند…", "history"),
    ActionSpec("backups", "پشتیبان‌ها…"),
    ActionSpec("export_history", "تاریخچهٔ برون‌بردها…"),
    ActionSpec("autosave_settings", "تنظیمات ذخیرهٔ خودکار و پشتیبان…"),
    ActionSpec("statistics", "آمار سند…"),
    # edit
    ActionSpec("copy_format", "رونوشت قالب"),
    ActionSpec("paste_format", "چسباندن قالب"),
    ActionSpec("format_painter", "قلم‌موی قالب", "painter", True),
    ActionSpec("go_to_page", "رفتن به صفحه…"),
    ActionSpec("update_fields", "به‌روزرسانی فهرست‌ها و شماره‌ها", "toc"),
    # format
    ActionSpec("char_spacing", "فاصله، مقیاس و زیرخط نویسه‌ها…"),
    ActionSpec("styles", "سبک‌ها…", "styles"),
    ActionSpec("list_circle", "فهرست با دایرهٔ توخالی"),
    ActionSpec("list_square", "فهرست با مربع"),
    ActionSpec("list_alpha", "فهرست حرفی"),
    ActionSpec("list_roman", "فهرست رومی"),
    # insert
    ActionSpec("insert_table", "جدول…", "table"),
    ActionSpec("insert_image", "تصویر…", "image"),
    ActionSpec("insert_shape", "شکل…", "shape"),
    ActionSpec("insert_equation", "معادله…", "equation"),
    ActionSpec("insert_link", "پیوند…", "link"),
    ActionSpec("remove_link", "برداشتن پیوند"),
    ActionSpec("insert_bookmark", "نشانک…"),
    ActionSpec("go_to_bookmark", "رفتن به نشانک…"),
    ActionSpec("insert_crossref", "ارجاع متقابل…"),
    ActionSpec("insert_caption", "شرح شکل یا جدول…"),
    ActionSpec("insert_note", "پی‌نوشت…", "note"),
    ActionSpec("insert_toc", "فهرست مطالب"),
    ActionSpec("insert_lof", "فهرست شکل‌ها"),
    ActionSpec("insert_lot", "فهرست جدول‌ها"),
    ActionSpec("page_break", "شکست صفحه", "page_break"),
    ActionSpec("header_footer", "سرصفحه و پاصفحه…", "header_footer"),
    ActionSpec("object_properties", "ویژگی‌های شیء انتخاب‌شده…"),
    ActionSpec("group_shapes", "گروه‌کردن شکل‌های انتخاب‌شده"),
    ActionSpec("ungroup_shapes", "بازکردن گروه"),
    ActionSpec("shape_to_front", "آوردن به جلو (در گروه)"),
    ActionSpec("shape_to_back", "فرستادن به عقب (در گروه)"),
    # table
    ActionSpec("table_row_above", "درج سطر در بالا"),
    ActionSpec("table_row_below", "درج سطر در پایین"),
    ActionSpec("table_col_before", "درج ستون پیش از ستون جاری"),
    ActionSpec("table_col_after", "درج ستون پس از ستون جاری"),
    ActionSpec("table_delete_row", "حذف سطر"),
    ActionSpec("table_delete_col", "حذف ستون"),
    ActionSpec("table_delete", "حذف جدول"),
    ActionSpec("table_merge", "ادغام خانه‌های انتخاب‌شده"),
    ActionSpec("table_split", "تقسیم خانهٔ ادغام‌شده"),
    ActionSpec("table_cell_color", "رنگ زمینهٔ خانه…"),
    ActionSpec("table_cell_no_color", "برداشتن رنگ زمینهٔ خانه"),
    ActionSpec("table_valign_top", "تراز عمودی: بالا"),
    ActionSpec("table_valign_middle", "تراز عمودی: وسط"),
    ActionSpec("table_valign_bottom", "تراز عمودی: پایین"),
    ActionSpec("table_properties", "ویژگی‌های جدول…"),
    # help
    ActionSpec("customize_shortcuts", "تنظیم میان‌برها…"),
    ActionSpec("shortcuts", "میان‌برهای صفحه‌کلید", "keyboard"),
    ActionSpec("about", "دربارهٔ دبیره"),
)


def spacing_label(multiple: float) -> str:
    return f"{multiple:g} برابر"


class EditorActions(QObject):
    """Registry of every command; menus and toolbars share these actions."""

    def __init__(self, parent: QMainWindow, overrides: dict[str, str] | None = None) -> None:
        super().__init__(parent)
        self._actions: dict[str, QAction] = {}
        self._overrides: dict[str, str] = dict(overrides or {})
        self._labels: dict[str, str] = {}
        for spec in ACTION_SPECS:
            self._add(spec, parent)
        for multiple in LINE_SPACINGS:
            self._add(ActionSpec(f"spacing_{multiple}", spacing_label(multiple), None, True), parent)

        self.alignment_group = self._group(parent, "align_right", "align_center", "align_left", "align_justify")
        self.direction_group = self._group(parent, "dir_rtl", "dir_ltr")
        self.spacing_group = self._group(parent, *(f"spacing_{m}" for m in LINE_SPACINGS))
        self.spacing_group.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)

    def _add(self, spec: ActionSpec, parent: QMainWindow) -> None:
        action = QAction(icon(spec.icon) if spec.icon else QIcon(), spec.text, parent)
        action.setCheckable(spec.checkable)
        parent.addAction(action)  # keeps the shortcut alive even when no menu shows it
        self._actions[spec.id] = action
        self._labels[spec.id] = spec.text.rstrip("…")
        self._apply_shortcut(spec.id)

    def _apply_shortcut(self, action_id: str) -> None:
        shortcut = self._overrides.get(action_id, shortcut_for(action_id))
        action = self._actions[action_id]
        action.setShortcut(QKeySequence(shortcut))
        label = self._labels[action_id]
        action.setToolTip(f"{label}  ({shortcut})" if shortcut else label)

    def set_overrides(self, overrides: dict[str, str]) -> None:
        """Apply user-defined shortcuts (action id -> key sequence, "" removes the shortcut)."""
        self._overrides = {k: v for k, v in overrides.items() if k in self._actions}
        for action_id in self._actions:
            self._apply_shortcut(action_id)

    def overrides(self) -> dict[str, str]:
        return dict(self._overrides)

    def editable_shortcuts(self) -> list[tuple[str, str, str, str]]:
        """(action id, label, current shortcut, default shortcut) for the shortcut editor."""
        return [(action_id, self._labels[action_id], action.shortcut().toString(), shortcut_for(action_id))
                for action_id, action in self._actions.items()]

    def _group(self, parent: QObject, *ids: str) -> QActionGroup:
        group = QActionGroup(parent)
        for action_id in ids:
            group.addAction(self._actions[action_id])
        return group

    def __getitem__(self, action_id: str) -> QAction:
        return self._actions[action_id]

    def shortcut_table(self) -> list[tuple[str, str]]:
        """(command, shortcut) pairs for the help dialog."""
        rows = [
            (action.text().rstrip("…"), action.shortcut().toString())
            for action in self._actions.values()
            if not action.shortcut().isEmpty()
        ]
        return rows + EXTRA_SHORTCUTS


def connect_editor_actions(actions: EditorActions, editor: RichTextEditor) -> None:
    """Wire the editing commands to the editor."""
    document = editor.document()
    simple = {
        "undo": editor.undo,
        "redo": editor.redo,
        "cut": editor.cut,
        "copy": editor.copy,
        "paste": editor.paste,
        "paste_plain": editor.paste_plain_text,
        "select_all": editor.selectAll,
        "clear_format": editor.clear_formatting,
        "indent_more": editor.increase_indent,
        "indent_less": editor.decrease_indent,
        "zwnj": editor.insert_zwnj,
        "insert_lrm": lambda: editor.insert_text("\u200e"),
        "insert_rlm": lambda: editor.insert_text("\u200f"),
        "align_right": lambda: editor.set_alignment("right"),
        "align_center": lambda: editor.set_alignment("center"),
        "align_left": lambda: editor.set_alignment("left"),
        "align_justify": lambda: editor.set_alignment("justify"),
        "dir_rtl": lambda: editor.set_direction("rtl"),
        "dir_ltr": lambda: editor.set_direction("ltr"),
        "bullet": lambda: editor.toggle_list("bullet"),
        "list_circle": lambda: editor.toggle_list("circle"),
        "list_square": lambda: editor.toggle_list("square"),
        "list_alpha": lambda: editor.toggle_list("alpha"),
        "list_roman": lambda: editor.toggle_list("roman"),
        "copy_format": editor.copy_format,
        "paste_format": editor.paste_format,
        "page_break": editor.insert_page_break,
        "insert_toc": lambda: editor.insert_generated_list("toc"),
        "insert_lof": lambda: editor.insert_generated_list("lof"),
        "insert_lot": lambda: editor.insert_generated_list("lot"),
        "remove_link": editor.remove_hyperlink,
        "group_shapes": editor.group_selected_shapes,
        "ungroup_shapes": editor.ungroup_shape,
        "shape_to_front": lambda: editor.reorder_group(True),
        "shape_to_back": lambda: editor.reorder_group(False),
        "table_row_above": lambda: editor.table_command("row_above"),
        "table_row_below": lambda: editor.table_command("row_below"),
        "table_col_before": lambda: editor.table_command("column_before"),
        "table_col_after": lambda: editor.table_command("column_after"),
        "table_delete_row": lambda: editor.table_command("remove_rows"),
        "table_delete_col": lambda: editor.table_command("remove_columns"),
        "table_delete": lambda: editor.table_command("delete_table"),
        "table_merge": lambda: editor.table_command("merge"),
        "table_split": lambda: editor.table_command("split"),
        "table_cell_no_color": lambda: editor.table_command("cell_background", None),
        "table_valign_top": lambda: editor.table_command("cell_valign", "top"),
        "table_valign_middle": lambda: editor.table_command("cell_valign", "middle"),
        "table_valign_bottom": lambda: editor.table_command("cell_valign", "bottom"),
        "numbered": lambda: editor.toggle_list("number"),
    }
    for action_id, handler in simple.items():
        actions[action_id].triggered.connect(lambda _checked=False, h=handler: h())

    actions["bold"].triggered.connect(editor.set_bold)
    actions["italic"].triggered.connect(editor.set_italic)
    actions["underline"].triggered.connect(editor.set_underline)
    actions["strike"].triggered.connect(editor.set_strikethrough)
    actions["superscript"].triggered.connect(lambda on: editor.set_vertical_alignment("super" if on else None))
    actions["subscript"].triggered.connect(lambda on: editor.set_vertical_alignment("sub" if on else None))
    actions["visual_cursor"].toggled.connect(editor.set_visual_cursor_movement)
    actions["format_painter"].triggered.connect(editor.set_format_painter)
    editor.formatPainted.connect(lambda: actions["format_painter"].setChecked(False))
    for multiple in LINE_SPACINGS:
        actions[f"spacing_{multiple}"].triggered.connect(
            lambda _checked=False, m=multiple: editor.set_line_spacing(m)
        )

    actions["undo"].setEnabled(False)
    actions["redo"].setEnabled(False)
    actions["cut"].setEnabled(False)
    actions["copy"].setEnabled(False)
    document.undoAvailable.connect(actions["undo"].setEnabled)
    document.redoAvailable.connect(actions["redo"].setEnabled)
    editor.copyAvailable.connect(actions["cut"].setEnabled)
    editor.copyAvailable.connect(actions["copy"].setEnabled)


class EditorToolbars(QObject):
    """Builds the two toolbar rows and keeps them in sync with the cursor."""

    def __init__(self, window: QMainWindow, actions: EditorActions, editor: RichTextEditor) -> None:
        super().__init__(window)
        self._actions = actions
        self._editor = editor

        self.font_combo = QFontComboBox()
        self.font_combo.setToolTip("قلم")
        self.font_combo.setMinimumWidth(150)
        self.font_combo.setMaximumWidth(210)
        self.font_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.font_combo.textActivated.connect(self._apply_font_family)

        self.size_combo = QComboBox()
        self.size_combo.setToolTip("اندازهٔ قلم (پوینت)")
        self.size_combo.setEditable(True)
        self.size_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.size_combo.setFixedWidth(72)
        self.size_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.size_combo.addItems([str(size) for size in FONT_SIZES])
        self.size_combo.textActivated.connect(self._apply_font_size)
        self.size_combo.lineEdit().returnPressed.connect(lambda: self._apply_font_size(self.size_combo.currentText()))

        self.color_button = ColorButton("text_color", "رنگ متن", TEXT_COLORS, "#c0392b", "رنگ خودکار")
        self.color_button.color_selected.connect(self._apply_text_color)
        self.highlight_button = ColorButton("highlight", "رنگ برجسته‌سازی", HIGHLIGHT_COLORS, "#fff59d", "بدون برجسته‌سازی")
        self.highlight_button.color_selected.connect(self._apply_highlight)

        self.style_combo = QComboBox()
        self.style_combo.setToolTip("سبک بند")
        self.style_combo.setMinimumWidth(120)
        self.style_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.style_combo.activated.connect(self._apply_style)
        self.refresh_styles()

        self.spacing_button = QToolButton()
        self.spacing_button.setIcon(icon("line_spacing"))
        self.spacing_button.setToolTip("فاصلهٔ سطرها")
        self.spacing_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        spacing_menu = QMenu(self.spacing_button)
        for multiple in LINE_SPACINGS:
            spacing_menu.addAction(actions[f"spacing_{multiple}"])
        spacing_menu.addSeparator()
        spacing_menu.addAction(actions["paragraph"])
        self.spacing_button.setMenu(spacing_menu)

        self.main_toolbar = self._toolbar(window, "ابزار اصلی", "MainToolbar")
        self._fill(
            self.main_toolbar,
            "new", "open", "save", "print", None, "undo", "redo", None, "cut", "copy", "paste", "format_painter", None,
            self.style_combo, self.font_combo, self.size_combo, None, "bold", "italic", "underline", "strike", None,
            self.color_button, self.highlight_button, "clear_format", None, "find",
        )
        window.addToolBarBreak()
        self.paragraph_toolbar = self._toolbar(window, "ابزار بند", "ParagraphToolbar")
        self._fill(
            self.paragraph_toolbar,
            "align_right", "align_center", "align_left", "align_justify", None, "dir_rtl", "dir_ltr", None,
            "bullet", "numbered", None, "indent_less", "indent_more", None,
            self.spacing_button, "paragraph", None, "zwnj", "script_fonts", "digits_persian", None,
            "insert_table", "insert_image", "insert_shape", "insert_equation", "insert_link", "insert_note",
            "page_break", "header_footer", "update_fields",
        )

    @staticmethod
    def _toolbar(window: QMainWindow, title: str, name: str) -> QToolBar:
        toolbar = QToolBar(title, window)
        toolbar.setObjectName(name)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        window.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        return toolbar

    def _fill(self, toolbar: QToolBar, *items: object) -> None:
        for item in items:
            if item is None:
                toolbar.addSeparator()
            elif isinstance(item, str):
                toolbar.addAction(self._actions[item])
            else:
                toolbar.addWidget(item)  # type: ignore[arg-type]

    # ------------------------------------------------------------ handlers
    def refresh_styles(self) -> None:
        """Reload the style list from the editor's document."""
        current = self._editor.current_style_name() or "Normal"
        self.style_combo.blockSignals(True)
        self.style_combo.clear()
        names = list(self._editor.styles)
        if "Normal" not in names:
            names.insert(0, "Normal")
        for name in names:
            style = self._editor.styles.get(name)
            self.style_combo.addItem(display_name(name) if style is None or style.builtin else name, name)
        index = self.style_combo.findData(current)
        self.style_combo.setCurrentIndex(max(0, index))
        self.style_combo.blockSignals(False)

    def _apply_style(self, index: int) -> None:
        name = self.style_combo.itemData(index)
        if name:
            self._editor.apply_style(name)
            self._editor.setFocus()

    def _apply_font_family(self, family: str) -> None:
        self._editor.set_font_family(family)
        self._editor.setFocus()

    def _apply_font_size(self, text: str) -> None:
        try:
            size = float(to_latin_digits(text).replace("٫", ".").replace(",", "."))
        except ValueError:
            return
        if 1 <= size <= 400:
            self._editor.set_font_size(size)
            self._editor.setFocus()

    def _apply_text_color(self, color: object) -> None:
        self._editor.set_text_color(color)  # type: ignore[arg-type]
        self._editor.setFocus()

    def _apply_highlight(self, color: object) -> None:
        self._editor.set_highlight(color)  # type: ignore[arg-type]
        self._editor.setFocus()

    # ---------------------------------------------------------------- sync
    def sync(self, state: FormatState) -> None:
        """Reflect the formatting at the cursor in every control."""
        actions = self._actions
        actions["bold"].setChecked(state.bold)
        actions["italic"].setChecked(state.italic)
        actions["underline"].setChecked(state.underline)
        actions["strike"].setChecked(state.strike)
        actions["superscript"].setChecked(state.superscript)
        actions["subscript"].setChecked(state.subscript)
        actions[f"align_{state.alignment}"].setChecked(True)
        actions[f"dir_{state.direction}"].setChecked(True)
        actions["bullet"].setChecked(state.list_style == "bullet")
        actions["numbered"].setChecked(state.list_style == "number")
        for multiple in LINE_SPACINGS:
            actions[f"spacing_{multiple}"].setChecked(abs(state.line_spacing - multiple) < 0.01)

        style_index = self.style_combo.findData(self._editor.current_style_name() or "Normal")
        if style_index >= 0 and style_index != self.style_combo.currentIndex():
            self.style_combo.blockSignals(True)
            self.style_combo.setCurrentIndex(style_index)
            self.style_combo.blockSignals(False)
        self.font_combo.blockSignals(True)
        self.font_combo.setCurrentFont(QFont(state.font_family))
        self.font_combo.blockSignals(False)
        if not self.size_combo.lineEdit().hasFocus():
            self.size_combo.blockSignals(True)
            self.size_combo.setEditText(f"{state.font_size:g}")
            self.size_combo.blockSignals(False)
