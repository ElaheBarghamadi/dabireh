"""Editing behaviour: typing, cursor movement, selection, clipboard, search, pages."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QSizeF, Qt
from PySide6.QtGui import QGuiApplication, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core import bidi
from core.document import PageSettings
from core.persian import ZWNJ
from editor import find_replace
from editor.find_replace import SearchOptions
from editor.text_editor import RichTextEditor
from tests.conftest import select, select_text, type_text

MIXED = "سلام Hello دنیا 123"
NO_MOD = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier


def move_to(editor: RichTextEditor, position: int) -> None:
    select(editor, position, position)


def walk(editor: RichTextEditor, key: Qt.Key, steps: int) -> list[tuple[int, int]]:
    """Press ``key`` repeatedly; return (logical position, x pixel) after each step."""
    trail = [(editor.textCursor().position(), editor.cursorRect().x())]
    for _ in range(steps):
        QTest.keyClick(editor, key)
        trail.append((editor.textCursor().position(), editor.cursorRect().x()))
    return trail


# ------------------------------------------------------------------ typing
def test_initial_document_is_ready_for_persian_typing(editor: RichTextEditor) -> None:
    assert editor.toPlainText() == ""
    assert editor.document().defaultFont().family() == "Vazirmatn"
    assert not editor.document().isModified()
    type_text(editor, "سلام")
    assert editor.toPlainText() == "سلام" and editor.document().isModified()


def test_shift_space_inserts_half_space(editor: RichTextEditor) -> None:
    type_text(editor, "می")
    QTest.keyClick(editor, Qt.Key.Key_Space, SHIFT)
    type_text(editor, "روم")
    assert editor.toPlainText() == f"می{ZWNJ}روم"


def test_enter_creates_paragraph_and_keeps_direction(editor: RichTextEditor) -> None:
    editor.set_direction("ltr")
    type_text(editor, "One\nTwo")
    assert editor.document().blockCount() == 2
    assert editor.textCursor().block().textDirection() == Qt.LayoutDirection.LeftToRight


def test_undo_and_redo(editor: RichTextEditor) -> None:
    type_text(editor, "سلام")
    editor.set_alignment("center")
    editor.undo()
    assert editor.format_state().alignment == "right"
    editor.redo()
    assert editor.format_state().alignment == "center"
    while editor.document().isUndoAvailable():
        editor.undo()
    assert editor.toPlainText() == ""
    editor.redo()
    assert editor.toPlainText() == "سلام"


# ------------------------------------------------------- cursor navigation
def test_left_arrow_moves_forward_in_rtl_paragraph(editor: RichTextEditor) -> None:
    type_text(editor, "سلام دنیا")
    move_to(editor, 0)
    trail = walk(editor, Qt.Key.Key_Left, 4)
    assert [position for position, _x in trail] == [0, 1, 2, 3, 4]
    xs = [x for _position, x in trail]
    assert xs == sorted(xs, reverse=True) and xs[0] > xs[-1]  # the caret really moves left


def test_right_arrow_moves_forward_in_ltr_paragraph(editor: RichTextEditor) -> None:
    editor.set_direction("ltr")
    type_text(editor, "Hello")
    move_to(editor, 0)
    trail = walk(editor, Qt.Key.Key_Right, 3)
    assert [position for position, _x in trail] == [0, 1, 2, 3]
    assert trail[-1][1] > trail[0][1]


def test_logical_movement_visits_every_position_in_typing_order(editor: RichTextEditor) -> None:
    type_text(editor, MIXED)
    move_to(editor, 0)
    trail = walk(editor, Qt.Key.Key_Left, len(MIXED))
    assert [position for position, _x in trail] == list(range(len(MIXED) + 1))


def test_visual_movement_always_moves_left_on_screen(editor: RichTextEditor) -> None:
    type_text(editor, MIXED)
    editor.set_visual_cursor_movement(True)
    move_to(editor, 0)
    trail = walk(editor, Qt.Key.Key_Left, len(MIXED))
    xs = [x for _position, x in trail]
    assert all(a >= b for a, b in zip(xs, xs[1:]))
    assert sorted(position for position, _x in trail) == list(range(len(MIXED) + 1))
    assert [position for position, _x in trail] != list(range(len(MIXED) + 1))  # differs from logical order


def test_home_end_and_word_movement(editor: RichTextEditor) -> None:
    type_text(editor, MIXED)
    QTest.keyClick(editor, Qt.Key.Key_Home)
    assert editor.textCursor().position() == 0
    QTest.keyClick(editor, Qt.Key.Key_End)
    assert editor.textCursor().position() == len(MIXED)
    move_to(editor, 0)
    QTest.keyClick(editor, Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier)
    assert editor.textCursor().position() == MIXED.index("Hello")


# ---------------------------------------------------------------- selection
def test_keyboard_selection_in_rtl_text(editor: RichTextEditor) -> None:
    type_text(editor, "سلام دنیا")
    move_to(editor, 0)
    for _ in range(4):
        QTest.keyClick(editor, Qt.Key.Key_Left, SHIFT)
    assert editor.textCursor().selectedText() == "سلام"


def test_selection_across_direction_boundary_is_logical(editor: RichTextEditor) -> None:
    type_text(editor, MIXED)
    start, end = MIXED.index("لام"), MIXED.index("llo")
    select(editor, start, end)
    assert editor.textCursor().selectedText() == MIXED[start:end] == "لام He"


def test_double_click_word_selection(editor: RichTextEditor) -> None:
    type_text(editor, MIXED)
    move_to(editor, MIXED.index("Hello") + 2)
    cursor = editor.textCursor()
    cursor.select(QTextCursor.SelectionType.WordUnderCursor)
    assert cursor.selectedText() == "Hello"


# ---------------------------------------------------------------- clipboard
def test_copy_and_paste_keep_text_and_formatting(editor: RichTextEditor, qapp: QApplication) -> None:
    type_text(editor, MIXED)
    select_text(editor, "Hello")
    editor.set_bold(True)
    editor.selectAll()
    editor.copy()
    assert QGuiApplication.clipboard().text() == MIXED  # plain text for other programs

    other = RichTextEditor()
    other.paste()
    assert other.toPlainText() == MIXED
    runs = other.to_document().paragraphs[0].runs
    assert [run.text for run in runs if run.style.bold] == ["Hello"]
    other.deleteLater()


def test_cut_and_paste_plain_text(editor: RichTextEditor) -> None:
    type_text(editor, MIXED)
    select_text(editor, "Hello ")
    editor.set_italic(True)
    select_text(editor, "Hello ")
    editor.cut()
    assert editor.toPlainText() == "سلام دنیا 123"
    move_to(editor, 0)
    editor.paste_plain_text()
    assert editor.toPlainText() == "Hello سلام دنیا 123"
    assert not any(run.style.italic for run in editor.to_document().paragraphs[0].runs)


def test_pasting_several_paragraphs(editor: RichTextEditor) -> None:
    mime = QMimeData()
    mime.setText("بند یک\nParagraph two\nبند سه")
    editor.insertFromMimeData(mime)
    assert [p.text for p in editor.to_document().paragraphs] == ["بند یک", "Paragraph two", "بند سه"]


def test_pasted_html_table_is_kept_as_a_table(editor: RichTextEditor) -> None:
    mime = QMimeData()
    mime.setHtml("<p>پیش</p><table><tr><td>خانهٔ <b>یک</b></td><td>Cell 2</td></tr></table><p>پس</p>")
    editor.insertFromMimeData(mime)
    document = editor.to_document()
    text = document.plain_text()
    for expected in ("پیش", "خانهٔ یک", "Cell 2", "پس"):
        assert expected in text
    assert any(run.style.bold and run.text == "یک" for p in document.iter_paragraphs() for run in p.runs)
    assert any(type(block).__name__ == "Table" for block in document.blocks)  # Phase 2: tables are stored
    # What is shown equals what the model stores: nothing can be lost on save.
    reloaded = RichTextEditor()
    reloaded.load_document(document)
    assert reloaded.to_document().plain_text() == text
    reloaded.deleteLater()


# --------------------------------------------------------- find and replace
def test_find_wraps_and_selects_matches(editor: RichTextEditor) -> None:
    type_text(editor, "کتاب خوب و کتاب بد\nBook and book")
    options = SearchOptions()
    assert find_replace.find(editor, "کتاب", options)
    first = editor.textCursor().selectionStart()
    assert find_replace.find(editor, "کتاب", options)
    assert editor.textCursor().selectionStart() > first
    assert find_replace.find(editor, "کتاب", options)  # wraps to the first match
    assert editor.textCursor().selectionStart() == first
    assert find_replace.find(editor, "کتاب", options, backward=True)
    assert not find_replace.find(editor, "نیست", options)
    assert find_replace.count_matches(editor.document(), "book", options) == 2
    assert find_replace.count_matches(editor.document(), "book", SearchOptions(case_sensitive=True)) == 1


def test_find_matches_arabic_letter_variants(editor: RichTextEditor) -> None:
    type_text(editor, "این كتابي عربی‌نویسی شده است")
    assert find_replace.count_matches(editor.document(), "کتابی", SearchOptions()) == 1
    assert find_replace.count_matches(editor.document(), "کتابی", SearchOptions(tolerant=False)) == 0


def test_replace_current_and_replace_all(editor: RichTextEditor) -> None:
    type_text(editor, "سیب و سیب و سیبزمینی")
    move_to(editor, 0)
    options = SearchOptions(whole_words=True)
    assert find_replace.find(editor, "سیب", options)
    assert find_replace.replace_current(editor, "سیب", "انار", options)
    assert editor.toPlainText() == "انار و سیب و سیبزمینی"
    assert find_replace.replace_all(editor.document(), "سیب", "انار", options) == 1
    assert editor.toPlainText() == "انار و انار و سیبزمینی"
    assert find_replace.replace_all(editor.document(), "انار", "به", SearchOptions()) == 2
    editor.undo()  # replace-all is a single undo step
    assert editor.toPlainText() == "انار و انار و سیبزمینی"


# ------------------------------------------------------ Persian/bidi tools
def test_digit_conversion_keeps_formatting(editor: RichTextEditor) -> None:
    type_text(editor, "سال 2026 و ۱۴۰۴")
    select_text(editor, "2026")
    editor.set_bold(True)
    move_to(editor, 0)
    assert editor.convert_digits("persian") == 4
    assert editor.toPlainText() == "سال ۲۰۲۶ و ۱۴۰۴"
    assert [r.text for r in editor.to_document().paragraphs[0].runs if r.style.bold] == ["۲۰۲۶"]
    editor.convert_digits("latin")
    assert editor.toPlainText() == "سال 2026 و 1404"


def test_isolate_selection_only_adds_invisible_controls(editor: RichTextEditor) -> None:
    text = "فرمول a + b = c درست است"
    type_text(editor, text)
    select_text(editor, "a + b = c")
    assert editor.isolate_selection_ltr()
    assert editor.toPlainText() == f"فرمول {bidi.LRI}a + b = c{bidi.PDI} درست است"
    assert bidi.strip_bidi_controls(editor.toPlainText()) == text
    move_to(editor, 0)
    assert not editor.isolate_selection_ltr()


# -------------------------------------------------------------------- pages
def test_long_document_flows_onto_several_pages(editor: RichTextEditor, qapp: QApplication) -> None:
    assert editor.page_count() == 1
    cursor = editor.textCursor()
    for index in range(120):
        cursor.insertText(f"بند شمارهٔ {index} با متن فارسی و English\n")
    qapp.processEvents()
    pages = editor.page_count()
    assert pages >= 3
    geometry = editor.page_geometry
    # The view can scroll exactly to the bottom of the last full page.
    assert editor.verticalScrollBar().maximum() == pages * geometry.height - editor.viewport().height()
    # No line may be laid out inside a page's top or bottom margin.
    block = editor.document().begin()
    first_line_tops = set()
    while block.isValid():
        text_layout = block.layout()
        for index in range(text_layout.lineCount()):
            line = text_layout.lineAt(index)
            top_in_page = (text_layout.position().y() + line.y()) % geometry.height
            first_line_tops.add(top_in_page)
            assert top_in_page >= geometry.margin_top
            assert top_in_page + line.height() <= geometry.height - geometry.margin_bottom
        block = block.next()
    assert geometry.margin_top in first_line_tops  # every page starts right below its top margin
    editor.setTextCursor(cursor)
    assert editor.cursor_page() == pages


def test_page_size_survives_resizing(editor: RichTextEditor, qapp: QApplication) -> None:
    expected = QSizeF(editor.page_geometry.width, editor.page_geometry.height)
    for width, height in ((500, 400), (1600, 1000), (900, 700)):
        editor.resize(width, height)
        qapp.processEvents()
        assert editor.document().pageSize() == expected


def test_page_settings_change_layout_but_not_undo_history(editor: RichTextEditor) -> None:
    type_text(editor, "متن")
    editor.document().setModified(False)
    editor.set_page_settings(PageSettings(size="A5", orientation="landscape", margin_left=10, margin_right=30))
    geometry = editor.page_geometry
    assert (geometry.width, geometry.height) == (794, 559)
    frame = editor.document().rootFrame().frameFormat()
    assert (frame.leftMargin(), frame.rightMargin()) == (geometry.margin_left, geometry.margin_right)
    assert editor.document().pageSize() == QSizeF(794, 559)
    assert editor.document().isModified()
    assert editor.toPlainText() == "متن"
    assert editor.to_document().page.size == "A5"


def test_enter_on_empty_list_item_ends_the_list(editor: RichTextEditor) -> None:
    editor.toggle_list("bullet")
    type_text(editor, "یک\n")
    assert editor.textCursor().block().textList() is not None
    type_text(editor, "\n")
    assert editor.textCursor().block().textList() is None
    assert editor.document().blockCount() == 2
