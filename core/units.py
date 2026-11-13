"""Length unit conversions.

The on-screen document uses CSS-style logical pixels (96 per inch).  Qt keeps
the logical DPI at 96 on Windows and applies the device pixel ratio on top, so
these conversions stay valid on high-DPI displays.
"""

from __future__ import annotations

MM_PER_INCH = 25.4
POINTS_PER_INCH = 72.0
SCREEN_DPI = 96.0


def mm_to_px(mm: float, dpi: float = SCREEN_DPI) -> float:
    return mm * dpi / MM_PER_INCH


def px_to_mm(px: float, dpi: float = SCREEN_DPI) -> float:
    return px * MM_PER_INCH / dpi


def pt_to_px(pt: float, dpi: float = SCREEN_DPI) -> float:
    return pt * dpi / POINTS_PER_INCH


def px_to_pt(px: float, dpi: float = SCREEN_DPI) -> float:
    return px * POINTS_PER_INCH / dpi


def mm_to_pt(mm: float) -> float:
    return mm * POINTS_PER_INCH / MM_PER_INCH


def pt_to_mm(pt: float) -> float:
    return pt * MM_PER_INCH / POINTS_PER_INCH
