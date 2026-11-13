"""Unicode bidirectional-text helpers.

Dabireh never reorders or reverses characters itself: the stored text is always
in logical (typing) order and Qt's implementation of the Unicode Bidirectional
Algorithm (UAX #9) produces the visual order at layout time.  This module only
*inspects* text (to pick a paragraph direction) and offers the standard
invisible Unicode controls for the cases the algorithm cannot guess.
"""

from __future__ import annotations

import unicodedata
from enum import Enum

LRM = "\u200e"  # LEFT-TO-RIGHT MARK
RLM = "\u200f"  # RIGHT-TO-LEFT MARK
ALM = "\u061c"  # ARABIC LETTER MARK
LRI = "\u2066"  # LEFT-TO-RIGHT ISOLATE
RLI = "\u2067"  # RIGHT-TO-LEFT ISOLATE
FSI = "\u2068"  # FIRST STRONG ISOLATE
PDI = "\u2069"  # POP DIRECTIONAL ISOLATE

_EMBEDDING_CONTROLS = "\u202a\u202b\u202c\u202d\u202e"
BIDI_CONTROLS = frozenset(LRM + RLM + ALM + LRI + RLI + FSI + PDI + _EMBEDDING_CONTROLS)

_STRONG_RTL = frozenset({"R", "AL"})
_STRONG_LTR = frozenset({"L"})
_ISOLATE_OPENERS = frozenset({LRI, RLI, FSI})


class Direction(str, Enum):
    """Paragraph direction. ``AUTO`` means "inherit / detect from content"."""

    RTL = "rtl"
    LTR = "ltr"
    AUTO = "auto"


def is_bidi_control(char: str) -> bool:
    return char in BIDI_CONTROLS


def first_strong_direction(text: str) -> Direction | None:
    """Return the direction of the first strong character (UAX #9 rules P2/P3).

    Characters inside directional isolates are skipped, as the standard
    requires.  Returns ``None`` when the text has no strong character (for
    example only digits, punctuation or whitespace).
    """
    isolate_depth = 0
    for char in text:
        if char in _ISOLATE_OPENERS:
            isolate_depth += 1
            continue
        if char == PDI:
            isolate_depth = max(0, isolate_depth - 1)
            continue
        if isolate_depth:
            continue
        bidi_class = unicodedata.bidirectional(char)
        if bidi_class in _STRONG_RTL:
            return Direction.RTL
        if bidi_class in _STRONG_LTR:
            return Direction.LTR
    return None


def paragraph_direction(text: str, fallback: Direction = Direction.RTL) -> Direction:
    """Resolve a concrete direction for ``text``; ``fallback`` if undecidable."""
    return first_strong_direction(text) or fallback


def has_mixed_direction(text: str) -> bool:
    """True when the text contains both strong RTL and strong LTR characters."""
    seen_rtl = seen_ltr = False
    for char in text:
        bidi_class = unicodedata.bidirectional(char)
        if bidi_class in _STRONG_RTL:
            seen_rtl = True
        elif bidi_class in _STRONG_LTR:
            seen_ltr = True
        if seen_rtl and seen_ltr:
            return True
    return False


def isolate_ltr(text: str) -> str:
    """Wrap ``text`` so it is laid out LTR without affecting its surroundings.

    Useful for formulas, file paths or code inside a Persian paragraph.  The
    wrapped characters keep their logical order; only two invisible controls
    are added around them.
    """
    return f"{LRI}{text}{PDI}"


def isolate_rtl(text: str) -> str:
    return f"{RLI}{text}{PDI}"


def strip_bidi_controls(text: str) -> str:
    """Remove every invisible directional control character from ``text``."""
    return "".join(char for char in text if char not in BIDI_CONTROLS)
