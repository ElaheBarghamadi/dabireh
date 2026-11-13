"""Page geometry.

Phase 1 delegates line/page breaking to Qt's document layout (which keeps
lines inside the page's content box).  This module owns the *geometry* so a
future custom pagination engine (headers, footers, widow/orphan control) can
replace the layout step without touching the UI or the file format.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.document import PageSettings
from core.units import SCREEN_DPI, mm_to_px

PAGE_SIZES_MM: dict[str, tuple[float, float]] = {
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
}


@dataclass(frozen=True)
class PageGeometry:
    """Page box and margins in device-independent pixels."""

    width: float
    height: float
    margin_top: float
    margin_bottom: float
    margin_left: float
    margin_right: float

    @property
    def content_width(self) -> float:
        return self.width - self.margin_left - self.margin_right

    @property
    def content_height(self) -> float:
        return self.height - self.margin_top - self.margin_bottom


def page_size_mm(page: PageSettings) -> tuple[float, float]:
    """Physical page size (width, height) honouring the orientation."""
    if page.size == "Custom":
        width, height = page.custom_width, page.custom_height
    else:
        width, height = PAGE_SIZES_MM.get(page.size, PAGE_SIZES_MM["A4"])
    return (height, width) if page.orientation == "landscape" else (width, height)


def page_geometry(page: PageSettings, dpi: float = SCREEN_DPI) -> PageGeometry:
    width_mm, height_mm = page_size_mm(page)
    return PageGeometry(
        width=round(mm_to_px(width_mm, dpi)),
        height=round(mm_to_px(height_mm, dpi)),
        margin_top=round(mm_to_px(page.margin_top, dpi)),
        margin_bottom=round(mm_to_px(page.margin_bottom, dpi)),
        margin_left=round(mm_to_px(page.margin_left, dpi)),
        margin_right=round(mm_to_px(page.margin_right, dpi)),
    )


def page_count(content_height: float, page_height: float) -> int:
    """Number of pages needed for a laid-out height (at least one)."""
    if page_height <= 0:
        return 1
    return max(1, math.ceil(content_height / page_height - 1e-6))


def page_of_offset(offset_y: float, page_height: float) -> int:
    """1-based page number containing the vertical offset ``offset_y``."""
    if page_height <= 0:
        return 1
    return max(1, int(offset_y // page_height) + 1)
