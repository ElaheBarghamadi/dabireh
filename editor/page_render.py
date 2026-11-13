"""Painting of whole pages: background, border, body text, header and footer.

The editor view, print preview, printing, PDF, PNG and SVG export all paint
pages through :class:`PageRenderer` from the *same* laid-out QTextDocument, so
their page breaks and positions are identical by construction.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import QAbstractTextDocumentLayout, QColor, QFont, QPainter, QPalette, QPen, QTextDocument

from core.document import HeaderFooter, PageSettings
from core.fields import resolve_fields
from core.pagination import PageGeometry, page_geometry
from core.units import pt_to_px

HEADER_COLOR = QColor("#4a5260")


def _alignment(align: str, rtl: bool) -> Qt.AlignmentFlag:
    if align == "center":
        return Qt.AlignmentFlag.AlignHCenter
    right = (align == "start") == rtl
    return Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft


def paint_header_footer(painter: QPainter, origin_x: float, origin_y: float, geometry: PageGeometry,
                        header_footer: HeaderFooter, page: int, pages: int, title: str, base_font: QFont,
                        rtl: bool = True) -> None:
    """Paint the running header and footer of one page whose top-left is at the origin."""
    header, footer = header_footer.texts_for_page(page)
    if not header and not footer:
        return
    font = QFont(base_font)
    font.setPixelSize(max(1, round(pt_to_px(header_footer.font_size))))
    painter.save()
    painter.setFont(font)
    painter.setPen(HEADER_COLOR)
    painter.setLayoutDirection(Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight)
    width = geometry.width - geometry.margin_left - geometry.margin_right
    left = origin_x + geometry.margin_left
    for template, top, height, align in (
        (header, origin_y, geometry.margin_top, header_footer.header_align),
        (footer, origin_y + geometry.height - geometry.margin_bottom, geometry.margin_bottom,
         header_footer.footer_align),
    ):
        if not template:
            continue
        text = resolve_fields(template, page=page, pages=pages, title=title,
                              number_format=header_footer.number_format)
        rect = QRectF(left, top, width, height)
        painter.drawText(rect, int(_alignment(align, rtl) | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap),
                         text)
    painter.restore()


def paint_page_border(painter: QPainter, origin_x: float, origin_y: float, geometry: PageGeometry,
                      page: PageSettings) -> None:
    if page.border_width <= 0:
        return
    width = pt_to_px(page.border_width)
    inset = max(width, min(geometry.margin_left, geometry.margin_right, geometry.margin_top,
                           geometry.margin_bottom) * 0.5)
    painter.save()
    pen = QPen(QColor(page.border_color), width)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(QRectF(origin_x + inset, origin_y + inset, geometry.width - 2 * inset,
                            geometry.height - 2 * inset))
    painter.restore()


class PageRenderer:
    """Paints single pages of a laid-out document in 96-dpi page pixels."""

    def __init__(self, document: QTextDocument, page: PageSettings, header_footer: HeaderFooter,
                 title: str = "") -> None:
        self.document = document
        self.page = page
        self.header_footer = header_footer
        self.title = title
        self.geometry = page_geometry(page)
        # QTextEdit can reset the page height on relayout; output must always be paginated.
        size = QSizeF(self.geometry.width, self.geometry.height)
        if document.pageSize() != size:
            document.setPageSize(size)

    def page_count(self) -> int:
        return max(1, self.document.pageCount())

    def is_rtl(self) -> bool:
        return self.document.defaultTextOption().textDirection() != Qt.LayoutDirection.LeftToRight

    def paint_page(self, painter: QPainter, index: int, *, background: bool = True) -> None:
        """Paint page ``index`` (0-based) with its top-left corner at (0, 0)."""
        geometry = self.geometry
        page_rect = QRectF(0, 0, geometry.width, geometry.height)
        painter.save()
        if background and QColor(self.page.background) != QColor("#ffffff"):
            painter.fillRect(page_rect, QColor(self.page.background))
        painter.save()
        painter.setClipRect(page_rect, Qt.ClipOperation.IntersectClip)
        painter.translate(0, -index * geometry.height)
        context = QAbstractTextDocumentLayout.PaintContext()
        context.clip = QRectF(0, index * geometry.height, geometry.width, geometry.height)
        context.palette.setColor(QPalette.ColorRole.Text, QColor("#000000"))
        self.document.documentLayout().draw(painter, context)
        painter.restore()
        paint_page_border(painter, 0, 0, geometry, self.page)
        paint_header_footer(painter, 0, 0, geometry, self.header_footer, index + 1, self.page_count(),
                            self.title, self.document.defaultFont(), self.is_rtl())
        painter.restore()
