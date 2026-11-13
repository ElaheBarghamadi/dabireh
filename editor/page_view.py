"""A QTextEdit that shows the document as pages on a workspace.

The Qt document layout is given the real page size, so it keeps every line
inside a page's content box and applies the top/bottom margins on each page.
This widget centres the page column, draws the gaps between pages and reports
page numbers.  It contains no editing logic.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPalette, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QFrame, QTextEdit, QWidget

from core.document import HeaderFooter, PageSettings
from core.pagination import PageGeometry, page_geometry, page_of_offset
from editor.page_render import paint_header_footer, paint_page_border


class PageTextEdit(QTextEdit):
    OUTER_MARGIN = 24  # workspace space around the page column
    PAGE_GAP = 14  # visual gap drawn between consecutive pages

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._page = PageSettings()
        self._running = HeaderFooter()
        self._running_title = ""
        self._geometry = page_geometry(self._page)
        self._workspace_color = QColor("#e6e9ee")
        self._page_border_color = QColor("#cfd4dc")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAutoFillBackground(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.verticalScrollBar().rangeChanged.connect(self._extend_scroll_range)
        self.document().documentLayout().documentSizeChanged.connect(self._extend_scroll_range)
        self.apply_page_settings(self._page)

    # ------------------------------------------------------------ settings
    @property
    def page_settings(self) -> PageSettings:
        return replace(self._page)

    @property
    def page_geometry(self) -> PageGeometry:
        return self._geometry

    def set_workspace_colors(self, background: QColor, page_border: QColor) -> None:
        self._workspace_color = QColor(background)
        self._page_border_color = QColor(page_border)
        self._apply_palette()

    def apply_page_settings(self, page: PageSettings) -> None:
        """Apply page size, orientation, margins and background.

        Page setup is a document property rather than an editing step, so it
        is kept out of the undo stack (changing it clears the undo history).
        """
        self._page = replace(page)
        self._geometry = geometry = page_geometry(self._page)
        document = self.document()
        was_modified = document.isModified()
        document.setUndoRedoEnabled(False)
        frame_format = document.rootFrame().frameFormat()
        frame_format.setMargin(0)
        frame_format.setTopMargin(geometry.margin_top)
        frame_format.setBottomMargin(geometry.margin_bottom)
        frame_format.setLeftMargin(geometry.margin_left)
        frame_format.setRightMargin(geometry.margin_right)
        document.rootFrame().setFrameFormat(frame_format)
        document.setUndoRedoEnabled(True)
        document.setModified(was_modified)

        self.setLineWrapMode(QTextEdit.LineWrapMode.FixedPixelWidth)
        self.setLineWrapColumnOrWidth(int(geometry.width))
        self._enforce_page_size()
        self._apply_palette()
        self._update_viewport_margins()
        self._extend_scroll_range()
        self.viewport().update()

    def set_running_content(self, header_footer: HeaderFooter, title: str) -> None:
        """Header/footer templates and document title painted on every page."""
        self._running = header_footer
        self._running_title = title
        self.viewport().update()

    def in_page_margin(self, viewport_y: float) -> bool:
        """Whether a viewport y coordinate lies in a page's top or bottom margin."""
        geometry = self._geometry
        offset = (viewport_y + self.verticalScrollBar().value()) % geometry.height
        return offset < geometry.margin_top or offset > geometry.height - geometry.margin_bottom

    def _apply_palette(self) -> None:
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, self._workspace_color)
        self.setPalette(palette)
        viewport_palette = self.viewport().palette()
        viewport_palette.setColor(QPalette.ColorRole.Base, QColor(self._page.background))
        self.viewport().setPalette(viewport_palette)

    def _enforce_page_size(self) -> None:
        """QTextEdit resets the page height on relayout; put it back."""
        size = QSizeF(self._geometry.width, self._geometry.height)
        if self.document().pageSize() != size:
            self.document().setPageSize(size)

    def _extend_scroll_range(self, *_args: object) -> None:
        """Let the view scroll to the end of the last page.

        Qt sizes the document to the end of its content, which would cut the
        last sheet short; pages are always shown at their full height.
        """
        bar = self.verticalScrollBar()
        pages = max(1, self.document().pageCount())
        wanted = int(pages * self._geometry.height - self.viewport().height())
        if wanted > bar.maximum():
            bar.setMaximum(wanted)

    def _update_viewport_margins(self) -> None:
        available = self.width() - self.verticalScrollBar().sizeHint().width()
        side = max(self.OUTER_MARGIN, int((available - self._geometry.width) // 2))
        self.setViewportMargins(side, self.OUTER_MARGIN, side, self.OUTER_MARGIN)

    # ---------------------------------------------------------------- pages
    def page_count(self) -> int:
        self._enforce_page_size()
        return max(1, self.document().pageCount())

    def cursor_page(self) -> int:
        """1-based number of the page that contains the text cursor."""
        offset = self.cursorRect().center().y() + self.verticalScrollBar().value()
        return min(self.page_count(), page_of_offset(offset, self._geometry.height))

    def _horizontal_offset(self) -> int:
        bar = self.horizontalScrollBar()
        return bar.maximum() - bar.value() if self.isRightToLeft() else bar.value()

    # --------------------------------------------------------------- events
    def resizeEvent(self, event: QResizeEvent) -> None:
        self._update_viewport_margins()
        super().resizeEvent(event)
        self._enforce_page_size()
        self._extend_scroll_range()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._update_viewport_margins()
        self._enforce_page_size()
        self._extend_scroll_range()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        geometry = self._geometry
        painter = QPainter(self.viewport())
        x = -self._horizontal_offset()
        scroll_y = self.verticalScrollBar().value()
        viewport_height = self.viewport().height()
        pages = max(1, self.document().pageCount())
        half_gap = self.PAGE_GAP / 2

        rtl = self.document().defaultTextOption().textDirection() != Qt.LayoutDirection.LeftToRight
        for page in range(pages):
            top = page * geometry.height - scroll_y
            if top > viewport_height or top + geometry.height < 0:
                continue
            paint_page_border(painter, x, top, geometry, self._page)
            paint_header_footer(painter, x, top, geometry, self._running, page + 1, pages,
                                self._running_title, self.document().defaultFont(), rtl)

        painter.setPen(self._page_border_color)
        painter.drawLine(x, 0, x, viewport_height)
        painter.drawLine(int(x + geometry.width - 1), 0, int(x + geometry.width - 1), viewport_height)
        for page in range(1, pages):
            y = page * geometry.height - scroll_y
            if y + half_gap < 0 or y - half_gap > viewport_height:
                continue
            gap = QRectF(x - 1, y - half_gap, geometry.width + 2, self.PAGE_GAP)
            painter.fillRect(gap, self._workspace_color)
            painter.drawLine(gap.topLeft(), gap.topRight())
            painter.drawLine(gap.bottomLeft(), gap.bottomRight())
        painter.end()
