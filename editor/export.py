"""Export and printing of the laid-out document.

PDF, PNG, SVG and the printer are all painted through
:class:`editor.page_render.PageRenderer`, i.e. from the very layout the editor
shows, so page breaks, headers/footers and page numbers match the screen.
"""

from __future__ import annotations

import base64
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QMarginsF, QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextImageFormat,
)
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtSvg import QSvgGenerator

from core.document import Document, HeaderFooter, PageSettings
from core.pagination import page_size_mm
from editor.objects import OBJECT_CHAR, handler_for, image_to_png_bytes, object_from_format
from editor.page_render import PageRenderer
from storage.document_repository import write_text_atomically

SCREEN_DPI = 96.0


class ExportError(OSError):
    """Raised when an export file cannot be produced."""


def page_layout_for(page: PageSettings) -> QPageLayout:
    width_mm, height_mm = page_size_mm(page)
    return QPageLayout(
        QPageSize(QSizeF(width_mm, height_mm), QPageSize.Unit.Millimeter),
        QPageLayout.Orientation.Portrait,  # width/height already honour the orientation
        QMarginsF(0, 0, 0, 0),
        QPageLayout.Unit.Millimeter,
    )


def _renderer(document: QTextDocument, page: PageSettings, title: str,
              header_footer: HeaderFooter | None) -> PageRenderer:
    return PageRenderer(document, page, header_footer or HeaderFooter(), title)


def export_pdf(document: QTextDocument, page: PageSettings, path: Path, title: str = "",
               header_footer: HeaderFooter | None = None) -> int:
    """Write every page to a PDF (vector text with embedded fonts); returns the page count."""
    renderer = _renderer(document, page, title, header_footer)
    writer = QPdfWriter(str(path))
    writer.setCreator("Dabireh")
    writer.setTitle(title)
    writer.setResolution(1200)
    if not writer.setPageLayout(page_layout_for(page)):
        raise ExportError("تنظیم صفحهٔ PDF ممکن نشد.")
    painter = QPainter(writer)
    if not painter.isActive():
        raise ExportError("پروندهٔ PDF ساخته نشد.")
    scale = writer.resolution() / SCREEN_DPI
    pages = renderer.page_count()
    for index in range(pages):
        if index:
            writer.newPage()
        painter.save()
        painter.scale(scale, scale)
        renderer.paint_page(painter, index)
        painter.restore()
    painter.end()
    del writer  # flush and close the file
    if not Path(path).is_file() or Path(path).stat().st_size == 0:
        raise ExportError("پروندهٔ PDF ساخته نشد.")
    return pages


def render_page_image(renderer: PageRenderer, index: int, dpi: float = 150.0) -> QImage:
    """One page as a raster image (white paper unless the page has a background colour)."""
    scale = dpi / SCREEN_DPI
    geometry = renderer.geometry
    image = QImage(QSize(round(geometry.width * scale), round(geometry.height * scale)),
                   QImage.Format.Format_RGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.scale(scale, scale)
    renderer.paint_page(painter, index)
    painter.end()
    return image


def _numbered_paths(path: Path, pages: int) -> list[Path]:
    if pages == 1:
        return [path]
    return [path.with_name(f"{path.stem}-{index + 1:03d}{path.suffix}") for index in range(pages)]


def export_png(document: QTextDocument, page: PageSettings, path: Path, title: str = "",
               header_footer: HeaderFooter | None = None, dpi: float = 150.0) -> list[Path]:
    """One PNG per page (``name-001.png`` … when there are several pages)."""
    renderer = _renderer(document, page, title, header_footer)
    paths = _numbered_paths(Path(path), renderer.page_count())
    for index, target in enumerate(paths):
        if not render_page_image(renderer, index, dpi).save(str(target), "PNG"):
            raise ExportError("پروندهٔ تصویر ساخته نشد.")
    return paths


def export_svg(document: QTextDocument, page: PageSettings, path: Path, title: str = "",
               header_footer: HeaderFooter | None = None) -> list[Path]:
    """One SVG per page."""
    renderer = _renderer(document, page, title, header_footer)
    geometry = renderer.geometry
    paths = _numbered_paths(Path(path), renderer.page_count())
    for index, target in enumerate(paths):
        generator = QSvgGenerator()
        generator.setFileName(str(target))
        generator.setSize(QSize(round(geometry.width), round(geometry.height)))
        generator.setViewBox(QRectF(0, 0, geometry.width, geometry.height))
        generator.setTitle(title)
        painter = QPainter(generator)
        if not painter.isActive():
            raise ExportError("پروندهٔ SVG ساخته نشد.")
        renderer.paint_page(painter, index)
        painter.end()
    return paths


# ------------------------------------------------------------------ printing
def pages_from_printer(printer: QPrinter, page_count: int, current_page: int = 1) -> list[int]:
    """0-based page indexes selected in the print dialog."""
    print_range = printer.printRange()
    if print_range == QPrinter.PrintRange.CurrentPage:
        return [min(max(current_page, 1), page_count) - 1]
    ranges = printer.pageRanges()
    if print_range == QPrinter.PrintRange.PageRange and not ranges.isEmpty():
        return [index for index in range(page_count) if ranges.contains(index + 1)]
    if print_range == QPrinter.PrintRange.PageRange and printer.fromPage() > 0:
        last = printer.toPage() or page_count
        return [index for index in range(page_count) if printer.fromPage() <= index + 1 <= last]
    return list(range(page_count))


def parse_page_list(text: str, page_count: int) -> list[int]:
    """Parse "1-3, 5, ۷" into 0-based page indexes (invalid parts are ignored)."""
    from core.persian import to_latin_digits

    pages: list[int] = []
    for part in to_latin_digits(text).replace("،", ",").replace("؛", ",").split(","):
        part = part.strip().replace("–", "-")
        if not part:
            continue
        first, _, last = part.partition("-")
        if not first.strip().isdigit() or (last and not last.strip().isdigit()):
            continue
        start = int(first)
        end = int(last) if last else start
        for number in range(min(start, end), max(start, end) + 1):
            if 1 <= number <= page_count and number - 1 not in pages:
                pages.append(number - 1)
    return pages


def print_pages(printer: QPrinter, renderer: PageRenderer, pages: Iterable[int] | None = None, *,
                fit_to_paper: bool = True, scale_percent: float = 100.0) -> int:
    """Paint the selected pages on ``printer``; returns the number of sheets painted.

    With ``fit_to_paper`` a page is scaled (keeping its aspect ratio) to the
    printer's paper, otherwise it is printed at true size times ``scale_percent``.
    """
    page_list = list(range(renderer.page_count())) if pages is None else list(pages)
    if not page_list:
        return 0
    printer.setFullPage(True)
    painter = QPainter(printer)
    if not painter.isActive():
        raise ExportError("چاپگر در دسترس نیست.")
    geometry = renderer.geometry
    copies = 1 if printer.supportsMultipleCopies() else max(1, printer.copyCount())
    painted = 0
    for copy_index in range(copies):
        for position, index in enumerate(page_list):
            if painted:
                printer.newPage()
            device = painter.viewport()
            if fit_to_paper:
                scale = min(device.width() / geometry.width, device.height() / geometry.height)
            else:
                scale = printer.resolution() / SCREEN_DPI * scale_percent / 100.0
            painter.save()
            painter.translate((device.width() - geometry.width * scale) / 2,
                              (device.height() - geometry.height * scale) / 2)
            painter.scale(scale, scale)
            renderer.paint_page(painter, index)
            painter.restore()
            painted += 1
    painter.end()
    return painted


# --------------------------------------------------------------- HTML / DOCX
def object_png(document: QTextDocument, obj: dict[str, Any], scale: float = 3.0) -> tuple[bytes, float, float]:
    """PNG rendering of an object and its size in px (used for DOCX/HTML export)."""
    handler = handler_for(document)
    size = handler.object_size(obj, document, QTextCharFormat())
    if obj.get("type") == "image":
        natural = handler.natural_size(str(obj.get("resource", "")))
        scale = min(6.0, max(1.0, natural.width() / max(1.0, float(obj.get("width", 100) or 100))))
    image = handler.render_to_image(obj, document, scale)
    return image_to_png_bytes(image), size.width(), size.height()


def export_html(document: QTextDocument, path: Path) -> None:
    """HTML with objects (images, shapes, equations) embedded as PNG data URIs."""
    clone = document.clone()
    handler = handler_for(document)
    clone_handler = handler_for(clone)
    clone_handler.resources = handler.resources
    clone_handler.math_font = handler.math_font
    cursor = QTextCursor(clone)
    position = 0
    while position < clone.characterCount():
        if clone.characterAt(position) == OBJECT_CHAR:
            cursor.setPosition(position + 1)
            fmt = cursor.charFormat()
            obj = object_from_format(fmt)
            if obj is not None and not fmt.isImageFormat():
                data, width, height = object_png(clone, obj)
                image_format = QTextImageFormat()
                image_format.setName("data:image/png;base64," + base64.b64encode(data).decode("ascii"))
                image_format.setWidth(width)
                image_format.setHeight(height)
                cursor.setPosition(position)
                cursor.setPosition(position + 1, QTextCursor.MoveMode.KeepAnchor)
                cursor.insertImage(image_format)
        position += 1
    html = clone.toHtml()
    direction = "ltr" if document.defaultTextOption().textDirection() == Qt.LayoutDirection.LeftToRight else "rtl"
    html = html.replace("<html>", f'<html dir="{direction}">', 1).replace("<body", f'<body dir="{direction}"', 1)
    write_text_atomically(Path(path), html)


def export_docx(model: Document, document: QTextDocument, path: Path) -> None:
    """DOCX export of the model; shapes and edited images are rendered from ``document``."""
    try:
        from interchange.docx_export import export_docx as write_docx
    except ImportError as error:  # python-docx missing
        raise ExportError("برای برون‌برد Word بستهٔ python-docx لازم است.") from error
    write_docx(model, path, lambda obj: object_png(document, obj))
    if not Path(path).is_file():
        raise ExportError("پروندهٔ Word ساخته نشد.")


__all__ = ["ExportError", "export_docx", "export_html", "export_pdf", "export_png", "export_svg",
           "page_layout_for", "pages_from_printer", "parse_page_list", "print_pages", "render_page_image"]
