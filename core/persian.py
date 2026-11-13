"""Persian-specific text utilities (digits, letter variants, search)."""

from __future__ import annotations

import re
from datetime import datetime

ZWNJ = "\u200c"  # ZERO WIDTH NON-JOINER (نیم‌فاصله)
ZWJ = "\u200d"

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
LATIN_DIGITS = "0123456789"

_TO_PERSIAN = str.maketrans(LATIN_DIGITS + ARABIC_DIGITS, PERSIAN_DIGITS * 2)
_TO_LATIN = str.maketrans(PERSIAN_DIGITS + ARABIC_DIGITS, LATIN_DIGITS * 2)

# Letters that look alike in Persian and Arabic keyboards/encodings.
_YEH_VARIANTS = "یيى"
_KAF_VARIANTS = "کك"
_NORMALISE_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})


def to_persian_digits(text: str) -> str:
    """Convert Latin and Arabic-Indic digits to Persian digits (same length)."""
    return text.translate(_TO_PERSIAN)


def to_latin_digits(text: str) -> str:
    """Convert Persian and Arabic-Indic digits to Latin digits (same length)."""
    return text.translate(_TO_LATIN)


def format_number(value: int | float) -> str:
    """Format a number for the Persian user interface."""
    return to_persian_digits(f"{value:,}".replace(",", "٬"))


def normalize_arabic_letters(text: str) -> str:
    """Map Arabic Yeh/Kaf to their Persian forms."""
    return text.translate(_NORMALISE_LETTERS)


def search_pattern(query: str, *, tolerant: bool = True, whole_words: bool = False) -> str:
    """Build a regular-expression source that finds ``query`` literally.

    With ``tolerant`` the pattern treats Persian/Arabic Yeh and Kaf as equal,
    so text typed with an Arabic keyboard is still found.  The result is valid
    for both Python's ``re`` and Qt's ``QRegularExpression`` (PCRE).
    """
    parts: list[str] = []
    for char in query:
        if tolerant and char in _YEH_VARIANTS:
            parts.append(f"[{_YEH_VARIANTS}]")
        elif tolerant and char in _KAF_VARIANTS:
            parts.append(f"[{_KAF_VARIANTS}]")
        else:
            parts.append(re.escape(char))
    pattern = "".join(parts)
    if whole_words and pattern:
        pattern = rf"(?<![\w{ZWNJ}]){pattern}(?![\w{ZWNJ}])"
    return pattern


def count_words(text: str) -> int:
    """Count words; a half-space (ZWNJ) joins parts of one Persian word."""
    return len(text.split())


def gregorian_to_jalali(year: int, month: int, day: int) -> tuple[int, int, int]:
    """Convert a Gregorian date to the Solar Hijri (Jalali) calendar."""
    cumulative_days = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    leap_year = year + 1 if month > 2 else year
    days = (
        355666 + 365 * year + (leap_year + 3) // 4 - (leap_year + 99) // 100
        + (leap_year + 399) // 400 + day + cumulative_days[month - 1]
    )
    jalali_year = -1595 + 33 * (days // 12053)
    days %= 12053
    jalali_year += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jalali_year += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jalali_year, 1 + days // 31, 1 + days % 31
    return jalali_year, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def format_timestamp(iso_text: str) -> str:
    """Format an ISO timestamp as a local Jalali date and time for display."""
    try:
        moment = datetime.fromisoformat(iso_text).astimezone()
    except (TypeError, ValueError):
        return ""
    year, month, day = gregorian_to_jalali(moment.year, moment.month, moment.day)
    return to_persian_digits(f"{year:04d}/{month:02d}/{day:02d}  {moment:%H:%M}")
