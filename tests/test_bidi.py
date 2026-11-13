"""Persian shaping and bidirectional layout, verified against Qt's text layout.

These tests inspect what Qt will actually draw (glyph ids and x positions of
characters) while asserting that the stored text stays in logical order.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextLayout, QTextOption

from core.document import Document, DocumentDefaults
from editor.text_editor import RichTextEditor
from tests.conftest import DATA_DIR, type_text

pytestmark = pytest.mark.usefixtures("qapp")

MIXED_LINES = [line for line in (DATA_DIR / "mixed_text.txt").read_text(encoding="utf-8").splitlines() if line]


class Laid:
    """One line of text laid out by Qt in a given paragraph direction."""

    def __init__(self, text: str, rtl: bool = True) -> None:
        self.text = text
        self.layout = QTextLayout(text, QFont("Vazirmatn", 14))
        option = QTextOption()
        option.setTextDirection(Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight)
        self.layout.setTextOption(option)
        self.layout.beginLayout()
        self.line = self.layout.createLine()
        self.line.setLineWidth(5000)
        self.layout.endLayout()

    def glyphs(self) -> list[int]:
        return [glyph for run in self.layout.glyphRuns() for glyph in run.glyphIndexes()]

    def center(self, index: int) -> float | None:
        """X position of the glyph drawn for the character at logical ``index``.

        ``None`` when the character has no glyph of its own (part of a ligature).
        """
        for run in self.layout.glyphRuns(index, 1):
            positions = run.positions()
            if positions:
                return positions[0].x()
        return None

    def centers(self, fragment: str) -> list[float]:
        start = self.text.index(fragment)
        values = [self.center(start + offset) for offset in range(len(fragment))]
        result: list[float] = []
        for value in values:
            # Skip characters merged into a ligature (لا, fi): they share one glyph.
            if value is not None and (not result or value != result[-1]):
                result.append(value)
        return result


def increasing(values: list[float]) -> bool:
    return all(a < b for a, b in zip(values, values[1:]))


def decreasing(values: list[float]) -> bool:
    return all(a > b for a, b in zip(values, values[1:]))


# 1. Persian text rendering -------------------------------------------------
def test_bundled_persian_font_is_used() -> None:
    from PySide6.QtGui import QFontInfo

    assert QFontInfo(QFont("Vazirmatn", 14)).family() == "Vazirmatn"


def test_persian_letters_are_joined_not_isolated() -> None:
    word = Laid("سلام").glyphs()
    isolated = [glyph for char in "سلام" for glyph in Laid(char).glyphs()]
    assert word and word != isolated  # contextual forms (and the لا ligature) are applied
    assert 0 not in word  # no missing-glyph boxes


def test_persian_word_runs_right_to_left() -> None:
    assert decreasing(Laid("دبیره").centers("دبیره"))


def test_half_space_keeps_letters_apart_without_a_gap() -> None:
    joined = Laid("میخواهم").glyphs()
    with_zwnj = Laid("می\u200cخواهم").glyphs()
    assert joined != with_zwnj  # ی takes its final form before the half-space


# 2. Mixed Persian and English ---------------------------------------------
def test_english_word_inside_persian_paragraph() -> None:
    laid = Laid("سلام Hello دنیا")
    assert increasing(laid.centers("Hello"))  # Latin letters read left-to-right
    assert decreasing(laid.centers("سلام"))
    # Paragraph order is right-to-left: سلام | Hello | دنیا
    assert laid.centers("سلام")[0] > laid.centers("Hello")[-1] > laid.centers("دنیا")[0]


def test_persian_word_inside_english_paragraph() -> None:
    laid = Laid("The word سلام means hello", rtl=False)
    assert decreasing(laid.centers("سلام"))
    assert laid.centers("The")[0] < laid.centers("سلام")[-1] < laid.centers("means")[0]


# 3. Persian and Latin numbers ---------------------------------------------
@pytest.mark.parametrize("number", ["۱۲۳۴", "4567", "٣٤٥"])
def test_numbers_read_left_to_right_in_rtl_text(number: str) -> None:
    laid = Laid(f"عدد {number} است")
    assert increasing(laid.centers(number))
    assert laid.centers("عدد")[0] > laid.centers(number)[-1] > laid.centers("است")[0]


def test_decimal_and_thousands_separators_stay_inside_the_number() -> None:
    laid = Laid("قیمت ۲۵٬۰۰۰ تومان (حدود 0.5 دلار)")
    assert increasing(laid.centers("۲۵٬۰۰۰"))
    assert increasing(laid.centers("0.5"))


# 4. Parentheses, brackets and mathematical symbols -------------------------
@pytest.mark.parametrize(("opening", "closing"), ["()", "[]", "{}", "<>", "«»"])
def test_brackets_are_mirrored_in_rtl_text(opening: str, closing: str) -> None:
    assert Laid(opening, rtl=True).glyphs() == Laid(closing, rtl=False).glyphs()
    laid = Laid(f"متن {opening}فارسی{closing} متن")
    # The logical opening bracket sits on the right of the word, the closing one on the left.
    assert laid.center(laid.text.index(opening)) > laid.centers("فارسی")[0]
    assert laid.center(laid.text.index(closing)) < laid.centers("فارسی")[-1]


def test_latin_formula_keeps_its_order_in_rtl_text() -> None:
    assert increasing(Laid("اگر x ≥ 0 باشد").centers("x ≥ 0"))
    assert increasing(Laid("داریم y = 2x + 3 پس").centers("y = 2x + 3"))


def test_persian_digit_expression_reads_right_to_left() -> None:
    laid = Laid("۲ × ۳ = ۶")
    assert laid.center(0) > laid.center(4) > laid.center(8)


def test_punctuation_ends_on_the_left_of_an_rtl_sentence() -> None:
    laid = Laid("سلام دنیا!")
    assert laid.center(laid.text.index("!")) < min(laid.centers("دنیا"))


# URLs and e-mail addresses --------------------------------------------------
@pytest.mark.parametrize(
    "token",
    ["https://example.com/path?q=1&lang=fa", "info@example.com", "C:\\Users\\Ali\\file.txt"],
)
def test_urls_and_emails_stay_contiguous_and_left_to_right(token: str) -> None:
    laid = Laid(f"نشانی: {token} است")
    assert increasing(laid.centers(token))


# Logical text integrity -------------------------------------------------------
@pytest.mark.parametrize("line", MIXED_LINES)
def test_typed_text_is_stored_in_logical_order(editor: RichTextEditor, line: str) -> None:
    type_text(editor, line)
    assert editor.toPlainText() == line
    assert editor.to_document().paragraphs[0].text == line
    assert Document.from_json(editor.to_document().to_json()).plain_text() == line


# Paragraph direction ------------------------------------------------------------
def test_default_document_is_right_to_left(editor: RichTextEditor) -> None:
    type_text(editor, "Hello")  # even Latin text follows the Persian document default
    assert editor.textCursor().block().textDirection() == Qt.LayoutDirection.RightToLeft
    editor.set_direction("ltr")
    assert editor.textCursor().block().textDirection() == Qt.LayoutDirection.LeftToRight


def test_auto_direction_follows_first_strong_character(editor: RichTextEditor) -> None:
    editor.load_document(Document(defaults=DocumentDefaults(direction="auto")))
    type_text(editor, "English first سلام\nفارسی اول English")
    document = editor.document()
    assert document.findBlockByNumber(0).textDirection() == Qt.LayoutDirection.LeftToRight
    assert document.findBlockByNumber(1).textDirection() == Qt.LayoutDirection.RightToLeft
