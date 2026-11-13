"""Built-in named paragraph styles."""

from __future__ import annotations

from core.document import CharStyle, Document, NamedStyle, ParagraphStyle

NORMAL = "Normal"
CAPTION = "Caption"
TOC_STYLES = ("TOC", "LOF", "LOT")  # generated lists; replaced when updated

PERSIAN_NAMES = {
    "Normal": "متن عادی",
    "Title": "عنوان",
    "Subtitle": "زیرعنوان",
    "Heading 1": "سرفصل ۱",
    "Heading 2": "سرفصل ۲",
    "Heading 3": "سرفصل ۳",
    "Quote": "نقل‌قول",
    "Caption": "شرح (شکل و جدول)",
    "Code": "کد",
    "TOC": "فهرست مطالب",
    "LOF": "فهرست شکل‌ها",
    "LOT": "فهرست جدول‌ها",
}


def display_name(name: str) -> str:
    return PERSIAN_NAMES.get(name or NORMAL, name)


def _style(name: str, char: CharStyle, paragraph: ParagraphStyle, level: int = 0) -> NamedStyle:
    paragraph.style_name = "" if name == NORMAL else name
    return NamedStyle(name, char, paragraph, level, builtin=True)


def builtin_styles() -> dict[str, NamedStyle]:
    """Fresh copies of the built-in styles, keyed by name."""
    styles = [
        _style("Normal", CharStyle(), ParagraphStyle(line_spacing=1.15, space_after=6)),
        _style("Title", CharStyle(font_size=26, bold=True), ParagraphStyle(alignment="center", space_after=12)),
        _style("Subtitle", CharStyle(font_size=15, color="#5b6472"),
               ParagraphStyle(alignment="center", space_after=14)),
        _style("Heading 1", CharStyle(font_size=20, bold=True, color="#1f5fbf"),
               ParagraphStyle(space_before=16, space_after=8), 1),
        _style("Heading 2", CharStyle(font_size=16, bold=True, color="#1f5fbf"),
               ParagraphStyle(space_before=12, space_after=6), 2),
        _style("Heading 3", CharStyle(font_size=14, bold=True), ParagraphStyle(space_before=10, space_after=4), 3),
        _style("Quote", CharStyle(italic=True, color="#4a5260"),
               ParagraphStyle(indent_left=28, indent_right=28, space_before=6, space_after=6, background="#f3f5f8")),
        _style("Caption", CharStyle(font_size=10.5, color="#4a5260"),
               ParagraphStyle(alignment="center", space_before=2, space_after=10)),
        _style("Code", CharStyle(font_family="Consolas", font_size=10.5),
               ParagraphStyle(direction="ltr", background="#f3f5f8", indent_left=10, indent_right=10)),
    ]
    return {style.name: style for style in styles}


def ensure_styles(document: Document) -> None:
    """Make sure every built-in style exists in the document (user edits are kept)."""
    for name, style in builtin_styles().items():
        document.styles.setdefault(name, style)


def heading_level(document_styles: dict[str, NamedStyle], style_name: str) -> int:
    style = document_styles.get(style_name)
    return style.heading_level if style else 0
