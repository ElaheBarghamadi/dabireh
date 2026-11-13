"""Character and paragraph formatting, including mixed typography."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from core.document import CharStyle, Document, ParagraphStyle
from core.units import mm_to_pt
from editor import formatting
from editor.text_editor import RichTextEditor
from tests.conftest import select, select_text, type_text

TEXT = "متن فارسی with English و ۱۲۳"


def runs_of(editor: RichTextEditor, paragraph: int = 0) -> list[tuple[str, CharStyle]]:
    return [(run.text, run.style) for run in editor.to_document().paragraphs[paragraph].runs]


def style_of(editor: RichTextEditor, text: str) -> CharStyle:
    return next(style for run_text, style in runs_of(editor) if run_text == text)


def paragraph_style(editor: RichTextEditor, index: int = 0) -> ParagraphStyle:
    return editor.to_document().paragraphs[index].style


# 7. Font formatting --------------------------------------------------------
@pytest.mark.parametrize(
    ("method", "attribute"),
    [("set_bold", "bold"), ("set_italic", "italic"), ("set_underline", "underline"), ("set_strikethrough", "strike")],
)
def test_toggle_styles_apply_to_selection_only(editor: RichTextEditor, method: str, attribute: str) -> None:
    type_text(editor, TEXT)
    select_text(editor, "فارسی")
    getattr(editor, method)(True)
    assert getattr(style_of(editor, "فارسی"), attribute) is True
    assert [text for text, style in runs_of(editor) if getattr(style, attribute)] == ["فارسی"]
    assert getattr(editor.format_state(), attribute) is True
    getattr(editor, method)(False)
    assert not any(getattr(style, attribute) for _text, style in runs_of(editor))
    assert editor.toPlainText() == TEXT


def test_typing_format_without_selection(editor: RichTextEditor) -> None:
    type_text(editor, "عادی ")
    editor.set_bold(True)
    type_text(editor, "پررنگ")
    editor.set_bold(False)
    type_text(editor, " عادی")
    assert [(text, style.bold) for text, style in runs_of(editor)] == [("عادی ", False), ("پررنگ", True), (" عادی", False)]


def test_mixed_typography_in_one_paragraph(editor: RichTextEditor) -> None:
    type_text(editor, TEXT)
    select_text(editor, "with English")
    editor.set_font_family("DejaVu Serif")
    editor.set_font_size(11)
    select_text(editor, "فارسی")
    editor.set_font_size(18)
    assert style_of(editor, "with English") == CharStyle(font_family="DejaVu Serif", font_size=11)
    assert style_of(editor, "فارسی") == CharStyle(font_size=18)
    assert style_of(editor, "متن ") == CharStyle()  # untouched text keeps the document default
    state = editor.format_state()
    assert (state.font_family, state.font_size) == ("Vazirmatn", 18)
    assert editor.toPlainText() == TEXT


def test_script_fonts_assign_families_by_script(editor: RichTextEditor) -> None:
    type_text(editor, "جمع ∑ برابر sum است و x = 2")
    scheme = editor.font_scheme()
    assert scheme.persian == "Vazirmatn"
    editor.apply_script_fonts()
    families = {text: style.font_family for text, style in runs_of(editor)}
    assert families["جمع "] == scheme.persian
    assert families["∑ "] == scheme.math
    assert families["sum "] == scheme.latin
    assert families["x = 2"] == scheme.latin
    assert editor.toPlainText() == "جمع ∑ برابر sum است و x = 2"


def test_text_color_and_highlight(editor: RichTextEditor) -> None:
    type_text(editor, TEXT)
    select_text(editor, "English")
    editor.set_text_color(QColor("#c0392b"))
    editor.set_highlight(QColor("#fff59d"))
    assert style_of(editor, "English") == CharStyle(color="#c0392b", highlight="#fff59d")
    state = editor.format_state()
    assert (state.color, state.highlight) == ("#c0392b", "#fff59d")
    editor.set_text_color(None)
    editor.set_highlight(None)
    assert all(style == CharStyle() for _text, style in runs_of(editor))


def test_superscript_and_subscript(editor: RichTextEditor) -> None:
    type_text(editor, "x2 H2O")
    select(editor, 1, 2)
    editor.set_vertical_alignment("super")
    select(editor, 4, 5)
    editor.set_vertical_alignment("sub")
    assert [style.vertical_align for _text, style in runs_of(editor)] == [None, "super", None, "sub", None]


def test_clear_formatting(editor: RichTextEditor) -> None:
    type_text(editor, TEXT)
    editor.selectAll()
    editor.set_bold(True)
    editor.set_font_size(30)
    editor.set_text_color(QColor("#ff0000"))
    editor.clear_formatting()
    assert runs_of(editor) == [(TEXT, CharStyle())]


# 8. Paragraph alignment ---------------------------------------------------------
def test_alignment_in_rtl_paragraph(editor: RichTextEditor) -> None:
    type_text(editor, "سلام")
    assert editor.format_state().alignment == "right"  # natural side of a Persian paragraph
    expected = {"left": "end", "center": "center", "justify": "justify", "right": "start"}
    for visual, logical in expected.items():
        editor.set_alignment(visual)
        assert paragraph_style(editor).alignment == logical
        assert editor.format_state().alignment == visual


def test_alignment_in_ltr_paragraph_and_direction_switch(editor: RichTextEditor) -> None:
    type_text(editor, "Hello")
    editor.set_direction("ltr")
    assert editor.format_state().alignment == "left"
    editor.set_alignment("right")
    assert paragraph_style(editor).alignment == "end"
    editor.set_direction("rtl")  # "end" stays the trailing side, as in Word
    assert editor.format_state().alignment == "left"


def test_alignment_applies_to_all_selected_paragraphs(editor: RichTextEditor) -> None:
    type_text(editor, "یک\nدو\nسه")
    select(editor, 1, 5)
    editor.set_alignment("center")
    assert [p.style.alignment for p in editor.to_document().paragraphs] == ["center", "center", "start"]


def test_direction_is_per_paragraph_and_mirrors_indents(editor: RichTextEditor) -> None:
    type_text(editor, "فارسی\nEnglish")
    editor.set_direction("ltr")
    styles = [p.style.direction for p in editor.to_document().paragraphs]
    assert styles == ["auto", "ltr"]
    assert editor.format_state().direction == "ltr"

    editor.set_indents(left_pt=30, right_pt=0)
    editor.set_direction("rtl")
    style = paragraph_style(editor, 1)
    assert (style.direction, style.indent_left, style.indent_right) == ("rtl", 0, 30)


# Spacing and indents ------------------------------------------------------------
def test_line_and_paragraph_spacing(editor: RichTextEditor) -> None:
    type_text(editor, "سطر یک\nسطر دو\nسطر سه")
    layout = editor.document().documentLayout()

    def pitch() -> float:
        blocks = [editor.document().findBlockByNumber(index) for index in (1, 2)]
        return layout.blockBoundingRect(blocks[1]).top() - layout.blockBoundingRect(blocks[0]).top()

    single = pitch()
    editor.selectAll()
    editor.set_line_spacing(2.0)
    editor.set_paragraph_spacing(before_pt=6, after_pt=12)
    style = paragraph_style(editor)
    assert (style.line_spacing, style.space_before, style.space_after) == (2.0, 6, 12)
    assert editor.format_state().line_spacing == 2.0
    assert pitch() == pytest.approx(single * 2 + 16, abs=1)  # doubled lines + 12pt (16px) after


def test_indents_and_first_line(editor: RichTextEditor) -> None:
    type_text(editor, "متن")
    editor.set_indents(left_pt=10, right_pt=20, first_line_pt=15)
    style = paragraph_style(editor)
    assert (style.indent_left, style.indent_right, style.first_line_indent) == (10, 20, 15)


def test_indent_buttons_use_the_leading_side(editor: RichTextEditor) -> None:
    type_text(editor, "فارسی\nEnglish")
    editor.set_direction("ltr")
    editor.selectAll()
    editor.increase_indent()
    step = round(mm_to_pt(10), 2)
    first, second = (p.style for p in editor.to_document().paragraphs)
    assert (first.indent_right, first.indent_left) == (step, 0)  # RTL: starts on the right
    assert (second.indent_left, second.indent_right) == (step, 0)
    editor.decrease_indent()
    editor.decrease_indent()  # never negative
    assert all(p.style.indent_left == p.style.indent_right == 0 for p in editor.to_document().paragraphs)


def test_first_line_indent_is_on_the_right_in_rtl(editor: RichTextEditor) -> None:
    type_text(editor, "سلام")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)
    before = editor.cursorRect().x()
    editor.set_indents(first_line_pt=30)
    assert editor.cursorRect().x() == pytest.approx(before - 40, abs=1)  # 30pt = 40px


def test_paragraph_style_round_trip_through_dialog_values(editor: RichTextEditor) -> None:
    type_text(editor, "بند")
    style = ParagraphStyle("justify", "ltr", 1.5, 4, 8, 12, 20, 6)
    editor.apply_paragraph_style(style)
    assert editor.paragraph_style() == style


# Lists ---------------------------------------------------------------------------
def test_bulleted_and_numbered_lists(editor: RichTextEditor) -> None:
    type_text(editor, "یک\nدو\nسه")
    editor.selectAll()
    editor.toggle_list("bullet")
    lists = [p.list for p in editor.to_document().paragraphs]
    assert all(item and item.style == "bullet" for item in lists)
    assert len({item.list_id for item in lists}) == 1
    assert editor.format_state().list_style == "bullet"

    editor.toggle_list("number")
    assert all(p.list.style == "number" for p in editor.to_document().paragraphs)
    editor.toggle_list("number")
    assert all(p.list is None for p in editor.to_document().paragraphs)
    assert formatting.current_list_style(editor.textCursor()) is None
    assert editor.toPlainText() == "یک\nدو\nسه"


def test_new_item_joins_the_previous_list(editor: RichTextEditor) -> None:
    type_text(editor, "یک\nدو")
    select(editor, 0, 0)
    editor.toggle_list("number")
    select(editor, 4, 4)
    editor.toggle_list("number")
    first, second = (p.list for p in editor.to_document().paragraphs)
    assert first.list_id == second.list_id


def test_lists_survive_reload(editor: RichTextEditor) -> None:
    type_text(editor, "الف\nب\nمتن\nج")
    select(editor, 0, 5)
    editor.toggle_list("bullet")
    select(editor, editor.document().characterCount() - 1, editor.document().characterCount() - 1)
    editor.toggle_list("number")
    document = editor.to_document()
    other = RichTextEditor()
    other.load_document(Document.from_json(document.to_json()))
    assert other.to_document().paragraphs == document.paragraphs
    assert [p.list.style if p.list else None for p in document.paragraphs] == ["bullet", "bullet", None, "number"]
    other.deleteLater()


def test_block_direction_values(editor: RichTextEditor) -> None:
    type_text(editor, "متن")
    assert editor.textCursor().block().textDirection() == Qt.LayoutDirection.RightToLeft
