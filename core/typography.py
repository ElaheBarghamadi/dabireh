"""Script detection for mixed Persian / Latin / mathematical typography."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from core.persian import ZWJ, ZWNJ


class Script(str, Enum):
    PERSIAN = "persian"
    LATIN = "latin"
    MATH = "math"
    NEUTRAL = "neutral"


_ARABIC_RANGES = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
)
_MATH_RANGES = (
    (0x2190, 0x21FF),  # arrows
    (0x2200, 0x22FF),  # mathematical operators
    (0x27C0, 0x27EF),
    (0x2980, 0x2AFF),
    (0x1D400, 0x1D7FF),  # mathematical alphanumerics
)
_LATIN_LIKE_RANGES = (
    (0x00C0, 0x024F),  # Latin-1 letters and Latin Extended
    (0x0370, 0x03FF),  # Greek
    (0x0400, 0x04FF),  # Cyrillic
    (0x1E00, 0x1EFF),
)

PERSIAN_FONT_FALLBACKS = ("Vazirmatn", "Segoe UI", "Tahoma", "Noto Sans Arabic", "DejaVu Sans")
LATIN_FONT_FALLBACKS = ("Cambria", "Times New Roman", "Georgia", "Liberation Serif", "DejaVu Serif")
MATH_FONT_FALLBACKS = ("Cambria Math", "STIX Two Math", "Latin Modern Math", "DejaVu Sans")


def _in_ranges(code: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(low <= code <= high for low, high in ranges)


def classify_char(char: str) -> Script:
    """Classify one character by the font family it should be set in."""
    code = ord(char)
    if _in_ranges(code, _ARABIC_RANGES):
        return Script.PERSIAN
    if char in (ZWNJ, ZWJ):
        return Script.NEUTRAL
    if code < 0x80:
        return Script.LATIN if char.isalpha() else Script.NEUTRAL
    if _in_ranges(code, _MATH_RANGES) or unicodedata.category(char) == "Sm":
        return Script.MATH
    if _in_ranges(code, _LATIN_LIKE_RANGES) and char.isalpha():
        return Script.LATIN
    return Script.NEUTRAL


@dataclass(frozen=True)
class ScriptRun:
    """A maximal run of one script; offsets are Python (code point) indices."""

    start: int
    end: int
    script: Script


def split_script_runs(text: str) -> list[ScriptRun]:
    """Split ``text`` into script runs, resolving neutral characters.

    Neutral characters (spaces, ASCII digits and punctuation) join the run
    before them, or the run after them at the start of the text, so that a
    number or a bracket never ends up in a different font from its context.
    """
    if not text:
        return []
    scripts = [classify_char(char) for char in text]
    first_strong = next((s for s in scripts if s is not Script.NEUTRAL), Script.PERSIAN)
    previous = first_strong
    for index, script in enumerate(scripts):
        if script is Script.NEUTRAL:
            scripts[index] = previous
        else:
            previous = script

    runs: list[ScriptRun] = []
    start = 0
    for index in range(1, len(text) + 1):
        if index == len(text) or scripts[index] is not scripts[start]:
            runs.append(ScriptRun(start, index, scripts[start]))
            start = index
    return runs


def utf16_length(text: str) -> int:
    """Length of ``text`` in UTF-16 code units (the unit Qt positions use)."""
    return len(text) + sum(1 for char in text if ord(char) > 0xFFFF)


@dataclass(frozen=True)
class FontScheme:
    """Font families used for each script of a document."""

    persian: str
    latin: str
    math: str

    def family_for(self, script: Script) -> str:
        if script is Script.LATIN:
            return self.latin
        if script is Script.MATH:
            return self.math
        return self.persian


def choose_font(preferred: str, available: Iterable[str], fallbacks: Iterable[str]) -> str:
    """Pick ``preferred`` if installed, otherwise the first installed fallback."""
    installed = {name.casefold(): name for name in available}
    for candidate in (preferred, *fallbacks):
        match = installed.get(candidate.casefold())
        if match:
            return match
    return preferred
