"""Inline document objects: images, equations, shapes and note marks.

An object occupies one U+FFFC character whose character format carries the
object description (a JSON string) in a custom property.  The description is
exactly what ``core.document.TextRun.object`` stores:

* image    – ``resource`` (key in ``Document.resources``), ``width``, ``height`` (px),
  ``rotation`` (degrees), ``crop`` ([left, top, right, bottom] fractions),
  ``border_width``, ``border_color``, ``wrap`` (inline | square_left | square_right)
* equation – ``latex``, ``display`` (bool), ``numbered`` (bool)
* shape    – ``kind``, ``width``, ``height``, ``fill``, ``stroke``, ``stroke_width``,
  ``opacity`` (0–1), ``rotation``, ``text``, ``sides``; a group has ``children``
  with relative ``x``/``y``/``w``/``h`` (0–1)
* note     – ``text`` (footnote/endnote text; the mark is numbered automatically)

Everything is painted with QPainter primitives, so shapes and equations stay
vector graphics in PDF/print and images are drawn from their original data.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from typing import Any

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPointF, QRectF, QSizeF, Qt, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QPyTextObject,
    QTextCharFormat,
    QTextDocument,
    QTextFormat,
    QTextFrameFormat,
    QTextImageFormat,
    QTextOption,
)
from PySide6.QtSvg import QSvgRenderer

from core.persian import to_persian_digits
from editor.equation_render import layout_equation, paint_equation

OBJECT_TYPE = int(QTextFormat.ObjectTypes.UserObject) + 1
PROP_DATA = int(QTextFormat.Property.UserProperty) + 1
PROP_STYLE_NAME = int(QTextFormat.Property.UserProperty) + 2
OBJECT_CHAR = "\ufffc"
FLOAT_WRAPS = {"square_left": QTextFrameFormat.Position.FloatLeft, "square_right": QTextFrameFormat.Position.FloatRight}
SHAPE_KINDS = ("line", "arrow", "connector", "rect", "rounded", "ellipse", "circle", "polygon", "callout", "textbox")
IMAGE_SUFFIXES = ("png", "jpg", "jpeg", "webp", "svg", "bmp", "gif")


def dumps(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def object_from_format(fmt: QTextFormat) -> dict[str, Any] | None:
    """The object description stored in a character format, if any."""
    if not fmt.hasProperty(PROP_DATA):
        return None
    try:
        data = json.loads(str(fmt.property(PROP_DATA)))
    except ValueError:
        return None
    return data if isinstance(data, dict) and isinstance(data.get("type"), str) else None


def resource_id(data: bytes, suffix: str) -> str:
    return hashlib.sha1(data).hexdigest()[:16] + "." + suffix.lower().lstrip(".")


def image_to_png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


class ObjectHandler(QPyTextObject):
    """Sizes and paints the inline objects of one QTextDocument."""

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self.resources: dict[str, str] = {}
        self._images: dict[str, QImage] = {}
        self._svgs: dict[str, QSvgRenderer] = {}
        self._numbers: tuple[int, dict[int, int], dict[int, int]] = (-1, {}, {})
        self.number_digits = "persian"
        self.math_font = "Cambria Math"

    # ----------------------------------------------------------- resources
    def add_resource(self, data: bytes, suffix: str) -> str:
        key = resource_id(data, suffix)
        self.resources.setdefault(key, base64.b64encode(data).decode("ascii"))
        return key

    def resource_bytes(self, key: str) -> bytes:
        try:
            return base64.b64decode(self.resources.get(key, ""))
        except ValueError:
            return b""

    def is_svg(self, key: str) -> bool:
        return key.lower().endswith(".svg")

    def image(self, key: str) -> QImage:
        if key not in self._images:
            image = QImage()
            image.loadFromData(QByteArray(self.resource_bytes(key)))
            self._images[key] = image
        return self._images[key]

    def svg(self, key: str) -> QSvgRenderer:
        if key not in self._svgs:
            self._svgs[key] = QSvgRenderer(QByteArray(self.resource_bytes(key)), self)
        return self._svgs[key]

    def natural_size(self, key: str) -> QSizeF:
        if self.is_svg(key):
            size = self.svg(key).defaultSize()
            return QSizeF(size.width() or 200, size.height() or 200)
        image = self.image(key)
        return QSizeF(image.width() or 100, image.height() or 100)

    def used_resources(self, keys: set[str]) -> dict[str, str]:
        return {key: value for key, value in self.resources.items() if key in keys}

    # ------------------------------------------------------------ numbering
    def _number_maps(self, document: QTextDocument) -> tuple[dict[int, int], dict[int, int]]:
        revision = document.revision()
        if self._numbers[0] != revision:
            equations: dict[int, int] = {}
            notes: dict[int, int] = {}
            block = document.begin()
            while block.isValid():
                iterator = block.begin()
                while not iterator.atEnd():
                    fragment = iterator.fragment()
                    obj = object_from_format(fragment.charFormat()) if fragment.isValid() else None
                    if obj is not None:
                        text = fragment.text()
                        for offset in range(fragment.length()):
                            if text[offset] != OBJECT_CHAR:
                                continue  # text typed with a stale object format
                            if obj["type"] == "equation" and obj.get("numbered"):
                                equations[fragment.position() + offset] = len(equations) + 1
                            elif obj["type"] == "note":
                                notes[fragment.position() + offset] = len(notes) + 1
                    iterator += 1
                block = block.next()
            self._numbers = (revision, equations, notes)
        return self._numbers[1], self._numbers[2]

    def format_number(self, number: int) -> str:
        return to_persian_digits(str(number)) if self.number_digits == "persian" else str(number)

    def equation_number(self, document: QTextDocument, position: int) -> int:
        return self._number_maps(document)[0].get(position, 0)

    def note_number(self, document: QTextDocument, position: int) -> int:
        return self._number_maps(document)[1].get(position, 0)

    # ---------------------------------------------------------------- sizes
    def _font_px(self, document: QTextDocument, fmt: QTextFormat) -> float:
        char_format = fmt.toCharFormat()
        points = char_format.fontPointSize() if char_format.hasProperty(QTextFormat.Property.FontPointSize) else 0
        if points <= 0:
            points = document.defaultFont().pointSizeF()
        return points * 96.0 / 72.0

    def _text_width(self, document: QTextDocument) -> float:
        frame_format = document.rootFrame().frameFormat()
        width = document.pageSize().width()
        if width <= 0:
            width = document.textWidth()
        return max(120.0, width - frame_format.leftMargin() - frame_format.rightMargin() - 8)

    def object_size(self, obj: dict[str, Any], document: QTextDocument, fmt: QTextFormat) -> QSizeF:
        kind = obj["type"]
        if kind == "equation":
            size = self._font_px(document, fmt)
            display = bool(obj.get("display"))
            box = layout_equation(str(obj.get("latex", "")), self.math_font, size * (1.1 if display else 1.0), display)
            width, height = box.width + 4, box.height + (10 if display else 2)
            if display and obj.get("numbered"):
                width = max(width + 2 * size * 3, self._text_width(document))
            return QSizeF(width, height)
        if kind == "note":
            size = self._font_px(document, fmt)
            font = QFont(document.defaultFont())
            font.setPixelSize(max(1, round(size * 0.65)))
            from PySide6.QtGui import QFontMetricsF

            return QSizeF(QFontMetricsF(font).horizontalAdvance("۰۰") + 2, size * 1.25)
        width = float(obj.get("width", 100) or 100)
        height = float(obj.get("height", 100) or 100)
        return rotated_bounds(width, height, float(obj.get("rotation", 0) or 0))

    def intrinsicSize(self, document: QTextDocument, position: int, fmt: QTextFormat) -> QSizeF:  # noqa: N802
        obj = object_from_format(fmt)
        return self.object_size(obj, document, fmt) if obj else QSizeF(0, 0)

    # ------------------------------------------------------------- painting
    def drawObject(self, painter: QPainter, rect: QRectF, document: QTextDocument, position: int,  # noqa: N802
                   fmt: QTextFormat) -> None:
        obj = object_from_format(fmt)
        if obj is None:
            return
        color = QColor("#000000")
        char_format = fmt.toCharFormat()
        if char_format.hasProperty(QTextFormat.Property.ForegroundBrush):
            color = char_format.foreground().color()
        self.paint_object(painter, rect, obj, document, position, color, self._font_px(document, fmt))

    def paint_object(self, painter: QPainter, rect: QRectF, obj: dict[str, Any], document: QTextDocument,
                     position: int, color: QColor, font_px: float) -> None:
        kind = obj["type"]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if kind == "equation":
            display = bool(obj.get("display"))
            size = font_px * (1.1 if display else 1.0)
            paint_equation(painter, rect, str(obj.get("latex", "")), self.math_font, size, display, color)
            number = self.equation_number(document, position)
            if number:
                font = QFont(document.defaultFont())
                font.setPixelSize(max(1, round(font_px)))
                painter.setFont(font)
                painter.setPen(color)
                painter.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
                painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 f"({self.format_number(number)})")
        elif kind == "note":
            font = QFont(document.defaultFont())
            font.setPixelSize(max(1, round(font_px * 0.65)))
            painter.setFont(font)
            painter.setPen(QColor("#1f5fbf"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                             self.format_number(self.note_number(document, position) or 1))
        elif kind == "image":
            self.paint_image(painter, rect, obj)
        elif kind == "shape":
            font = QFont(document.defaultFont())
            font.setPixelSize(max(1, round(font_px * 0.85)))
            painter.setFont(font)
            paint_shape(painter, rect, obj)
        painter.restore()

    def paint_image(self, painter: QPainter, rect: QRectF, obj: dict[str, Any]) -> None:
        width = float(obj.get("width", rect.width()) or rect.width())
        height = float(obj.get("height", rect.height()) or rect.height())
        key = str(obj.get("resource", ""))
        painter.save()
        painter.translate(rect.center())
        painter.rotate(float(obj.get("rotation", 0) or 0))
        target = QRectF(-width / 2, -height / 2, width, height)
        crop = obj.get("crop") or [0, 0, 0, 0]
        left, top, right, bottom = (min(max(float(v), 0.0), 0.95) for v in (list(crop) + [0, 0, 0, 0])[:4])
        if self.is_svg(key) and self.svg(key).isValid():
            painter.setClipRect(target, Qt.ClipOperation.IntersectClip)
            full_w = width / max(0.05, 1 - left - right)
            full_h = height / max(0.05, 1 - top - bottom)
            self.svg(key).render(painter, QRectF(target.x() - left * full_w, target.y() - top * full_h, full_w, full_h))
        else:
            image = self.image(key)
            if image.isNull():
                painter.fillRect(target, QColor("#eef0f3"))
                painter.setPen(QColor("#9aa1ab"))
                painter.drawRect(target)
                painter.drawLine(target.topLeft(), target.bottomRight())
            else:
                source = QRectF(left * image.width(), top * image.height(),
                                image.width() * max(0.05, 1 - left - right),
                                image.height() * max(0.05, 1 - top - bottom))
                painter.drawImage(target, image, source)
        border = float(obj.get("border_width", 0) or 0)
        if border > 0:
            painter.setClipping(False)
            painter.setPen(QPen(QColor(str(obj.get("border_color", "#000000"))), border))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(target.adjusted(border / 2, border / 2, -border / 2, -border / 2))
        painter.restore()

    def render_to_image(self, obj: dict[str, Any], document: QTextDocument, scale: float = 2.0,
                        fmt: QTextFormat | None = None) -> QImage:
        """Raster rendering of an object (float images, DOCX/HTML export of shapes)."""
        fmt = fmt or QTextCharFormat()
        size = self.object_size(obj, document, fmt)
        image = QImage(max(1, math.ceil(size.width() * scale)), max(1, math.ceil(size.height() * scale)),
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.scale(scale, scale)
        self.paint_object(painter, QRectF(0, 0, size.width(), size.height()), obj, document, -1,
                          QColor("#000000"), self._font_px(document, fmt))
        painter.end()
        return image


def rotated_bounds(width: float, height: float, rotation: float) -> QSizeF:
    angle = math.radians(rotation % 360)
    cos, sin = abs(math.cos(angle)), abs(math.sin(angle))
    return QSizeF(width * cos + height * sin, width * sin + height * cos)


# ------------------------------------------------------------------- shapes
def _arrow_head(painter: QPainter, tip: QPointF, origin: QPointF, size: float) -> None:
    angle = math.atan2(tip.y() - origin.y(), tip.x() - origin.x())
    points = [tip]
    for delta in (2.6, -2.6):
        points.append(QPointF(tip.x() + size * math.cos(angle + delta), tip.y() + size * math.sin(angle + delta)))
    painter.save()
    painter.setBrush(painter.pen().color())
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPolygon(QPolygonF(points))
    painter.restore()


def paint_shape(painter: QPainter, rect: QRectF, obj: dict[str, Any]) -> None:
    """Paint a shape (or group) inside ``rect`` using vector primitives."""
    width = float(obj.get("width", rect.width()) or rect.width())
    height = float(obj.get("height", rect.height()) or rect.height())
    painter.save()
    painter.translate(rect.center())
    painter.rotate(float(obj.get("rotation", 0) or 0))
    painter.setOpacity(painter.opacity() * min(max(float(obj.get("opacity", 1.0)), 0.0), 1.0))
    box = QRectF(-width / 2, -height / 2, width, height)
    kind = obj.get("kind", "rect")
    if kind == "group":
        for child in obj.get("children", []):
            child_rect = QRectF(box.x() + float(child.get("x", 0)) * width, box.y() + float(child.get("y", 0)) * height,
                                float(child.get("w", 1)) * width, float(child.get("h", 1)) * height)
            scaled = dict(child, width=child_rect.width(), height=child_rect.height())
            paint_shape(painter, child_rect, scaled)
        painter.restore()
        return
    stroke_width = float(obj.get("stroke_width", 1.5))
    stroke = obj.get("stroke", "#1f2937")
    pen = QPen(QColor(str(stroke)), stroke_width) if stroke and stroke_width > 0 else QPen(Qt.PenStyle.NoPen)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    fill = obj.get("fill")
    painter.setBrush(QBrush(QColor(str(fill))) if fill else QBrush(Qt.BrushStyle.NoBrush))
    inset = stroke_width / 2 + 0.5
    inner = box.adjusted(inset, inset, -inset, -inset)
    text_rect = inner
    if kind in ("line", "arrow"):
        start, end = QPointF(inner.left(), 0), QPointF(inner.right() - (stroke_width * 2 if kind == "arrow" else 0), 0)
        painter.drawLine(start, end)
        if kind == "arrow":
            _arrow_head(painter, QPointF(inner.right(), 0), start, max(8.0, stroke_width * 4))
    elif kind == "connector":
        middle = inner.center().x()
        path = QPainterPath(inner.topLeft())
        path.lineTo(middle, inner.top())
        path.lineTo(middle, inner.bottom())
        path.lineTo(inner.right() - stroke_width * 2, inner.bottom())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        _arrow_head(painter, inner.bottomRight(), QPointF(middle, inner.bottom()), max(8.0, stroke_width * 4))
    elif kind == "rounded":
        radius = min(inner.width(), inner.height()) * 0.2
        painter.drawRoundedRect(inner, radius, radius)
    elif kind in ("ellipse", "circle"):
        if kind == "circle":
            side = min(inner.width(), inner.height())
            inner = QRectF(-side / 2, -side / 2, side, side)
        painter.drawEllipse(inner)
        text_rect = inner.adjusted(inner.width() * 0.12, inner.height() * 0.12, -inner.width() * 0.12,
                                   -inner.height() * 0.12)
    elif kind == "polygon":
        sides = int(min(max(int(obj.get("sides", 5) or 5), 3), 12))
        points = [QPointF(inner.center().x() + inner.width() / 2 * math.sin(2 * math.pi * i / sides),
                          inner.center().y() - inner.height() / 2 * math.cos(2 * math.pi * i / sides))
                  for i in range(sides)]
        painter.drawPolygon(QPolygonF(points))
        text_rect = inner.adjusted(inner.width() * 0.2, inner.height() * 0.2, -inner.width() * 0.2,
                                   -inner.height() * 0.2)
    elif kind == "callout":
        body = QRectF(inner.left(), inner.top(), inner.width(), inner.height() * 0.78)
        radius = min(body.width(), body.height()) * 0.18
        path = QPainterPath()
        path.addRoundedRect(body, radius, radius)
        tail = QPainterPath(QPointF(body.left() + body.width() * 0.62, body.bottom() - 1))
        tail.lineTo(body.left() + body.width() * 0.8, inner.bottom())
        tail.lineTo(body.left() + body.width() * 0.8, body.bottom() - 1)
        tail.closeSubpath()
        painter.drawPath(path.united(tail))
        text_rect = body
    else:  # rect, textbox
        painter.drawRect(inner)
    text = str(obj.get("text", "") or "")
    if text and kind not in ("line", "arrow", "connector"):
        option = QTextOption(Qt.AlignmentFlag.AlignCenter)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        painter.setPen(QColor(str(obj.get("text_color", "#111827"))))
        painter.drawText(text_rect.adjusted(4, 2, -4, -2), text, option)
    painter.restore()


# ------------------------------------------------------- document plumbing
def handler_for(document: QTextDocument) -> ObjectHandler:
    """The object handler of ``document`` (installed on first use)."""
    handler = document.findChild(ObjectHandler)
    if handler is None:
        handler = ObjectHandler(document)
    # QTextDocument.clear() keeps the layout, but registering again is harmless.
    document.documentLayout().registerHandler(OBJECT_TYPE, handler)
    return handler


def object_format(obj: dict[str, Any], base: QTextCharFormat | None = None) -> QTextCharFormat:
    fmt = QTextCharFormat(base) if base is not None else QTextCharFormat()
    fmt.setObjectType(OBJECT_TYPE)
    fmt.setProperty(PROP_DATA, dumps(obj))
    if obj.get("type") == "equation" and not obj.get("display"):
        fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignMiddle)
    elif obj.get("type") == "note":
        fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
    return fmt


def insert_object(cursor, obj: dict[str, Any], base: QTextCharFormat | None = None) -> None:  # noqa: ANN001
    """Insert ``obj`` at the cursor (floating images become Qt float frames)."""
    document = cursor.document()
    handler = handler_for(document)
    wrap = obj.get("wrap", "inline")
    if obj.get("type") == "image" and wrap in FLOAT_WRAPS:
        name = "dbr-float:" + hashlib.sha1(dumps(obj).encode("utf-8")).hexdigest()
        image = handler.render_to_image(obj, document, scale=_float_scale(handler, obj))
        document.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
        size = handler.object_size(obj, document, QTextCharFormat())
        fmt = QTextImageFormat()
        fmt.setName(name)
        fmt.setWidth(size.width())
        fmt.setHeight(size.height())
        fmt.setProperty(PROP_DATA, dumps(obj))
        cursor.insertImage(fmt, FLOAT_WRAPS[wrap])
        return
    following = cursor.charFormat()
    cursor.insertText(OBJECT_CHAR, object_format(obj, base))
    cursor.setCharFormat(base if base is not None else without_object(following))


def without_object(fmt: QTextCharFormat) -> QTextCharFormat:
    result = QTextCharFormat(fmt)
    result.clearProperty(PROP_DATA)
    result.clearProperty(QTextFormat.Property.ObjectType)
    if fmt.hasProperty(PROP_DATA):
        result.clearProperty(QTextFormat.Property.TextVerticalAlignment)
    for prop in (QTextFormat.Property.ImageName, QTextFormat.Property.ImageWidth, QTextFormat.Property.ImageHeight):
        result.clearProperty(prop)
    return result


def _float_scale(handler: ObjectHandler, obj: dict[str, Any]) -> float:
    natural = handler.natural_size(str(obj.get("resource", "")))
    width = float(obj.get("width", 100) or 100)
    return min(6.0, max(1.0, natural.width() / max(1.0, width)))


def object_at(document: QTextDocument, position: int) -> dict[str, Any] | None:
    """Object whose placeholder character is at ``position``."""
    if position < 0 or document.characterAt(position) != OBJECT_CHAR:
        return None
    from PySide6.QtGui import QTextCursor

    cursor = QTextCursor(document)
    cursor.setPosition(position + 1)
    return object_from_format(cursor.charFormat())
