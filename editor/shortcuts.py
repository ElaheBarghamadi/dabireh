"""Central keyboard-shortcut table (action id → key sequence)."""

from __future__ import annotations

SHORTCUTS: dict[str, str] = {
    # file
    "new": "Ctrl+N",
    "open": "Ctrl+O",
    "save": "Ctrl+S",
    "save_as": "Ctrl+Shift+S",
    "export_pdf": "Ctrl+Shift+P",
    "quit": "Ctrl+Q",
    # edit
    "undo": "Ctrl+Z",
    "redo": "Ctrl+Y",
    "cut": "Ctrl+X",
    "copy": "Ctrl+C",
    "paste": "Ctrl+V",
    "paste_plain": "Ctrl+Shift+V",
    "select_all": "Ctrl+A",
    "find": "Ctrl+F",
    "replace": "Ctrl+H",
    # character format
    "bold": "Ctrl+B",
    "italic": "Ctrl+I",
    "underline": "Ctrl+U",
    "strike": "Ctrl+Shift+X",
    "superscript": "Ctrl+Shift+=",
    "subscript": "Ctrl+=",
    "clear_format": "Ctrl+\\",
    # paragraph
    "align_right": "Ctrl+R",
    "align_center": "Ctrl+E",
    "align_left": "Ctrl+L",
    "align_justify": "Ctrl+J",
    "dir_rtl": "Ctrl+Shift+R",
    "dir_ltr": "Ctrl+Shift+L",
    "bullet": "Ctrl+Shift+8",
    "numbered": "Ctrl+Shift+7",
    "indent_more": "Ctrl+M",
    "indent_less": "Ctrl+Shift+M",
    "spacing_1.0": "Ctrl+1",
    "spacing_1.5": "Ctrl+5",
    "spacing_2.0": "Ctrl+2",
    # Persian tools
    "zwnj": "Ctrl+Shift+2",
    # phase 2
    "print": "Ctrl+P",
    "new_template": "Ctrl+Shift+N",
    "export_docx": "Ctrl+Shift+D",
    "go_to_page": "Ctrl+G",
    "copy_format": "Ctrl+Shift+C",
    "paste_format": "Ctrl+Alt+V",
    "insert_table": "Ctrl+Alt+T",
    "insert_image": "Ctrl+Alt+I",
    "insert_equation": "Alt+=",
    "insert_link": "Ctrl+K",
    "insert_note": "Ctrl+Alt+F",
    "page_break": "Ctrl+Return",
    "update_fields": "F9",
    "styles": "Ctrl+Shift+Alt+S",
    # help
    "shortcuts": "F1",
}

# Editing keys handled inside the editor rather than through an action.
EXTRA_SHORTCUTS: list[tuple[str, str]] = [
    ("نیم‌فاصله هنگام تایپ", "Shift+Space"),
    ("خانهٔ بعدی / قبلی جدول", "Tab / Shift+Tab"),
    ("ویرایش تصویر، شکل، معادله یا پانوشت", "دوبار کلیک روی آن"),
    ("ویرایش سرصفحه و پاصفحه", "دوبار کلیک در حاشیهٔ بالا یا پایین صفحه"),
    ("دنبال‌کردن پیوند", "Ctrl+کلیک"),
    ("سطر جدید در همان بند", "Shift+Enter"),
    ("پایان فهرست", "Enter روی مورد خالی"),
    ("انتخاب با صفحه‌کلید", "Shift+جهت‌نما"),
    ("حرکت واژه‌به‌واژه", "Ctrl+جهت‌نما"),
]


def shortcut_for(action_id: str) -> str:
    return SHORTCUTS.get(action_id, "")
