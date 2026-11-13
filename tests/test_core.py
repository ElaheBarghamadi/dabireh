"""Qt-free logic: bidi helpers, Persian utilities, typography, model, geometry."""

from __future__ import annotations

import re

import pytest

from core import bidi
from core.bidi import Direction
from core.document import (
    FORMAT_VERSION,
    CharStyle,
    Document,
    DocumentFormatError,
    ListInfo,
    PageSettings,
    Paragraph,
    ParagraphStyle,
    TextRun,
)
from core.pagination import page_count, page_geometry, page_of_offset, page_size_mm
from core.persian import (
    ZWNJ,
    count_words,
    gregorian_to_jalali,
    search_pattern,
    to_latin_digits,
    to_persian_digits,
)
from core.typography import FontScheme, Script, choose_font, split_script_runs, utf16_length


# ------------------------------------------------------------------- bidi
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("سلام دنیا", Direction.RTL),
        ("Hello دنیا", Direction.LTR),
        ("123 سلام", Direction.RTL),
        ("(۱۲) test", Direction.LTR),
        ("https://example.com نشانی", Direction.LTR),
        ("۱۲۳ + 456", None),
        ("", None),
    ],
)
def test_first_strong_direction(text: str, expected: Direction | None) -> None:
    assert bidi.first_strong_direction(text) == expected


def test_first_strong_skips_isolated_content() -> None:
    assert bidi.first_strong_direction(bidi.isolate_ltr("abc") + " سلام") == Direction.RTL


def test_paragraph_direction_fallback() -> None:
    assert bidi.paragraph_direction("۱۲۳") == Direction.RTL
    assert bidi.paragraph_direction("123", Direction.LTR) == Direction.LTR


def test_isolate_keeps_logical_text() -> None:
    wrapped = bidi.isolate_ltr("x + y = 2")
    assert wrapped[0] == bidi.LRI and wrapped[-1] == bidi.PDI
    assert bidi.strip_bidi_controls(wrapped) == "x + y = 2"
    assert bidi.has_mixed_direction("سلام world") and not bidi.has_mixed_direction("سلام ۱۲۳")


# ---------------------------------------------------------------- persian
def test_digit_conversion_is_lossless_and_length_preserving() -> None:
    text = "سال 2026 و ٣٤ و ۱۴۰۴"
    persian = to_persian_digits(text)
    assert persian == "سال ۲۰۲۶ و ۳۴ و ۱۴۰۴"
    assert len(persian) == len(text)
    assert to_latin_digits(persian) == "سال 2026 و 34 و 1404"


def test_search_pattern_tolerates_arabic_yeh_and_kaf() -> None:
    pattern = re.compile(search_pattern("کتابی"))
    assert pattern.search("این كتابي است")  # Arabic Kaf and Yeh
    assert pattern.search("این کتابی است")
    assert not re.compile(search_pattern("کتابی", tolerant=False)).search("این كتابي است")


def test_search_pattern_escapes_special_characters_and_whole_words() -> None:
    assert re.compile(search_pattern("(a+b)")).search("x (a+b) y")
    whole = re.compile(search_pattern("می", whole_words=True))
    assert whole.search("من می روم")
    assert not whole.search(f"من می{ZWNJ}روم")  # the half-space joins one word
    assert not whole.search("میز")


def test_word_count_treats_half_space_as_one_word() -> None:
    assert count_words(f"می{ZWNJ}خواهم کتاب{ZWNJ}ها را ببرم") == 4


@pytest.mark.parametrize(
    ("gregorian", "jalali"),
    [((2024, 3, 20), (1403, 1, 1)), ((2026, 11, 13), (1405, 8, 22)), ((1979, 2, 11), (1357, 11, 22))],
)
def test_jalali_conversion(gregorian: tuple[int, int, int], jalali: tuple[int, int, int]) -> None:
    assert gregorian_to_jalali(*gregorian) == jalali


# ------------------------------------------------------------- typography
def test_script_runs_for_mixed_text() -> None:
    text = "سلام Hello ۱۲۳ ∑ x"
    runs = split_script_runs(text)
    assert [(text[r.start:r.end], r.script) for r in runs] == [
        ("سلام ", Script.PERSIAN),
        ("Hello ", Script.LATIN),
        ("۱۲۳ ", Script.PERSIAN),
        ("∑ ", Script.MATH),
        ("x", Script.LATIN),
    ]
    assert "".join(text[r.start:r.end] for r in runs) == text


def test_neutral_characters_follow_their_context() -> None:
    text = "قیمت 25 (تومان)"
    assert [r.script for r in split_script_runs(text)] == [Script.PERSIAN]
    assert split_script_runs("(abc) فارسی")[0].script is Script.LATIN
    assert split_script_runs("") == []


def test_utf16_length_counts_surrogate_pairs() -> None:
    assert utf16_length("a𝑥b") == 4


def test_choose_font_falls_back_to_installed_family() -> None:
    assert choose_font("Cambria", ["DejaVu Serif", "Vazirmatn"], ("Times New Roman", "DejaVu Serif")) == "DejaVu Serif"
    assert choose_font("cambria", ["Cambria"], ()) == "Cambria"
    scheme = FontScheme("Vazirmatn", "Cambria", "Cambria Math")
    assert scheme.family_for(Script.MATH) == "Cambria Math" and scheme.family_for(Script.NEUTRAL) == "Vazirmatn"


# --------------------------------------------------------- document model
def _rich_document() -> Document:
    document = Document()
    document.metadata.title = "آزمون"
    document.page = PageSettings(size="A5", orientation="landscape", margin_left=12.5)
    document.paragraphs = [
        Paragraph(
            runs=[TextRun("سلام ", CharStyle(bold=True, font_size=16)), TextRun("World", CharStyle(font_family="Cambria"))],
            style=ParagraphStyle(alignment="justify", direction="rtl", line_spacing=1.5, first_line_indent=14),
        ),
        Paragraph(runs=[TextRun("مورد")], list=ListInfo("number", 1, 3)),
        Paragraph(),
    ]
    return document


def test_document_json_round_trip() -> None:
    document = _rich_document()
    restored = Document.from_json(document.to_json())
    assert restored == document
    assert "سلام" in document.to_json()  # stored as readable UTF-8, not escapes


def test_document_rejects_foreign_and_damaged_files() -> None:
    with pytest.raises(DocumentFormatError):
        Document.from_json("{not json")
    with pytest.raises(DocumentFormatError):
        Document.from_json('{"format": "something-else"}')
    newer = _rich_document().to_dict() | {"version": FORMAT_VERSION + 1}
    with pytest.raises(DocumentFormatError):
        Document.from_dict(newer)


def test_document_tolerates_missing_and_invalid_optional_values() -> None:
    document = Document.from_dict(
        {
            "format": "dabireh-document",
            "version": 1,
            "page": {"size": "B9", "margin_top": "big"},
            "paragraphs": [{"runs": [{"text": "متن", "style": {"bold": "yes", "font_size": -4}}]}],
        }
    )
    assert document.page.size == "A4" and document.page.margin_top == 25.0
    assert document.paragraphs[0].runs[0].style == CharStyle(font_size=1.0)
    assert document.plain_text() == "متن"


def test_plain_text_import_and_export() -> None:
    document = Document.from_plain_text("سطر یک\r\n\r\nLine three")
    assert [p.text for p in document.paragraphs] == ["سطر یک", "", "Line three"]
    assert document.plain_text() == "سطر یک\n\nLine three"


# ------------------------------------------------------------- pagination
def test_page_geometry_for_a4_a5_and_landscape() -> None:
    assert page_size_mm(PageSettings(size="A4")) == (210.0, 297.0)
    assert page_size_mm(PageSettings(size="A5", orientation="landscape")) == (210.0, 148.0)
    a4 = page_geometry(PageSettings(size="A4", margin_left=20, margin_right=30))
    assert (a4.width, a4.height) == (794, 1123)
    assert a4.content_width == a4.width - a4.margin_left - a4.margin_right
    a5 = page_geometry(PageSettings(size="A5"))
    assert (a5.width, a5.height) == (559, 794)


def test_page_counting() -> None:
    assert page_count(0, 1000) == 1
    assert page_count(1000, 1000) == 1
    assert page_count(1001, 1000) == 2
    assert page_of_offset(0, 1000) == 1 and page_of_offset(1000, 1000) == 2


def test_malformed_document_structures_report_format_error() -> None:
    document = Document().to_dict()
    document["styles"] = 42
    with pytest.raises(DocumentFormatError):
        Document.from_dict(document)

    document = Document().to_dict()
    document["blocks"] = [{"type": "table", "rows": [[{"blocks": None}]]}]
    with pytest.raises(DocumentFormatError):
        Document.from_dict(document)

    document = Document().to_dict()
    document["version"] = True
    with pytest.raises(DocumentFormatError):
        Document.from_dict(document)


def test_non_finite_document_numbers_use_safe_defaults() -> None:
    document = Document().to_dict()
    document["page"]["margin_top"] = float("nan")
    document["defaults"]["font_size"] = float("inf")
    document["blocks"] = [{"runs": [{"text": "x", "style": {"stretch": float("nan")}}]}]
    loaded = Document.from_dict(document)
    assert loaded.page.margin_top == 25.0
    assert loaded.defaults.font_size == 13.0
    assert loaded.paragraphs[0].runs[0].style.stretch is None
