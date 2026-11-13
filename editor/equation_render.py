"""Layout and painting of equations parsed by ``core.equation``.

Every symbol is placed at explicit left-to-right coordinates, so an equation
looks the same inside a right-to-left paragraph and nothing is mirrored.
Painting uses text and line primitives only, which keeps equations vector
graphics in PDF and print output.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen

from core.equation import BINARY, RELATIONS, EquationError, Node, parse

SCRIPT_SCALE = 0.7
MIN_SIZE = 6.0


@dataclass
class Box:
    width: float
    ascent: float
    descent: float
    paint: Callable[[QPainter, float, float], None]  # (painter, x, baseline_y)

    @property
    def height(self) -> float:
        return self.ascent + self.descent


def _font(family: str, size: float, italic: bool = False, bold: bool = False) -> QFont:
    font = QFont()
    font.setFamilies([family, "Cambria Math", "STIX Two Math", "DejaVu Serif", "DejaVu Sans"])
    font.setPixelSize(max(1, round(size)))
    font.setItalic(italic)
    font.setBold(bold)
    return font


class _Layout:
    def __init__(self, family: str, display: bool) -> None:
        self.family = family
        self.display = display

    # ------------------------------------------------------------ helpers
    def text(self, text: str, size: float, italic: bool = False, bold: bool = False, pad: float = 0.0) -> Box:
        font = _font(self.family, size, italic, bold)
        metrics = QFontMetricsF(font)
        width = metrics.horizontalAdvance(text)

        def paint(painter: QPainter, x: float, y: float) -> None:
            painter.setFont(font)
            painter.drawText(QPointF(x + pad, y), text)

        return Box(width + 2 * pad, metrics.ascent(), metrics.descent(), paint)

    @staticmethod
    def hbox(boxes: list[Box]) -> Box:
        offsets: list[float] = []
        x = 0.0
        for box in boxes:
            offsets.append(x)
            x += box.width

        def paint(painter: QPainter, x0: float, y: float) -> None:
            for box, offset in zip(boxes, offsets, strict=True):
                box.paint(painter, x0 + offset, y)

        return Box(x, max((b.ascent for b in boxes), default=0.0), max((b.descent for b in boxes), default=0.0), paint)

    @staticmethod
    def shifted(box: Box, dx: float, dy: float) -> Box:
        """``box`` moved by (dx, dy); positive dy moves down."""
        return Box(box.width + dx, box.ascent - dy, box.descent + dy,
                   lambda painter, x, y: box.paint(painter, x + dx, y + dy))

    def axis(self, size: float) -> float:
        """Height of the maths axis (fraction bar) above the baseline."""
        return QFontMetricsF(_font(self.family, size)).xHeight() * 0.56

    def delimiter(self, char: str, size: float, ascent: float, descent: float) -> Box:
        if not char:
            return Box(0, 0, 0, lambda *_: None)
        font = _font(self.family, size)
        metrics = QFontMetricsF(font)
        natural = metrics.ascent() + metrics.descent()
        height = ascent + descent
        if height <= natural * 1.15:
            return self.text(char, size)
        scale = height / natural
        width = metrics.horizontalAdvance(char) * min(scale, 1.6)

        def paint(painter: QPainter, x: float, y: float) -> None:
            painter.save()
            painter.setFont(font)
            painter.translate(x, y - ascent)
            painter.scale(min(scale, 1.6), scale)
            painter.drawText(QPointF(0, metrics.ascent()), char)
            painter.restore()

        return Box(width, ascent, descent, paint)

    # -------------------------------------------------------------- nodes
    def layout(self, node: Node, size: float) -> Box:
        size = max(size, MIN_SIZE)
        method = getattr(self, "_" + node.kind)
        return method(node, size)

    def _row(self, node: Node, size: float) -> Box:
        boxes: list[Box] = []
        for index, item in enumerate(node.items):
            box = self.layout(item, size)
            if item.kind == "sym" and len(item.text) == 1:
                gap = 0.0
                if item.text in RELATIONS:
                    gap = size * 0.28
                elif item.text in BINARY and index > 0 and node.items[index - 1].kind != "sym" or (
                    item.text in BINARY and index > 0 and node.items[index - 1].text not in RELATIONS | BINARY | {"("}
                ):
                    gap = size * 0.2
                if gap:
                    box = Box(box.width + 2 * gap, box.ascent, box.descent,
                              lambda painter, x, y, b=box, g=gap: b.paint(painter, x + g, y))
            elif item.kind == "sym" and item.left == "func" or item.kind == "bigop":
                gap = size * 0.15
                box = Box(box.width + gap + (gap if boxes else 0), box.ascent, box.descent,
                          lambda painter, x, y, b=box, g=(gap if boxes else 0): b.paint(painter, x + g, y))
            boxes.append(box)
        if not boxes:
            metrics = QFontMetricsF(_font(self.family, size))
            return Box(0, metrics.ascent() * 0.7, 0, lambda *_: None)
        return self.hbox(boxes)

    def _sym(self, node: Node, size: float) -> Box:
        return self.text(node.text, size, italic=not node.upright)

    def _text(self, node: Node, size: float) -> Box:
        return self.text(node.text, size, bold=node.left == "bold")

    def _space(self, node: Node, size: float) -> Box:
        return Box(max(0.0, node.size * size), 0, 0, lambda *_: None)

    def _frac(self, node: Node, size: float) -> Box:
        inner = size if self.display and size > 0 else size * 0.85
        inner = size * (1.0 if self.display else 0.8)
        top = self.layout(node.items[0], inner)
        bottom = self.layout(node.items[1], inner)
        pad = size * 0.12
        rule = max(1.0, size * 0.06)
        gap = size * 0.14
        width = max(top.width, bottom.width) + 2 * pad
        axis = self.axis(size)
        ascent = axis + rule / 2 + gap + top.height
        descent = -axis + rule / 2 + gap + bottom.height

        def paint(painter: QPainter, x: float, y: float) -> None:
            top.paint(painter, x + (width - top.width) / 2, y - axis - rule / 2 - gap - top.descent)
            bottom.paint(painter, x + (width - bottom.width) / 2, y - axis + rule / 2 + gap + bottom.ascent)
            pen = QPen(painter.pen().color(), rule)
            painter.save()
            painter.setPen(pen)
            painter.drawLine(QLineF(x + pad / 2, y - axis, x + width - pad / 2, y - axis))
            painter.restore()

        return Box(width, ascent, descent, paint)

    def _sqrt(self, node: Node, size: float) -> Box:
        body = self.layout(node.items[0], size)
        rule = max(1.0, size * 0.06)
        gap = size * 0.12
        hook = size * 0.55
        index = self.layout(node.sup, size * 0.55) if node.sup is not None else None
        lead = max(0.0, (index.width - hook * 0.45) if index else 0.0)
        ascent = body.ascent + gap + rule
        descent = body.descent
        width = lead + hook + body.width + size * 0.08

        def paint(painter: QPainter, x: float, y: float) -> None:
            painter.save()
            painter.setPen(QPen(painter.pen().color(), rule, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
            x0 = x + lead
            top, bottom = y - ascent + rule / 2, y + descent
            path = QPainterPath(QPointF(x0, y - (ascent - descent) * 0.35))
            path.lineTo(x0 + hook * 0.2, y - (ascent - descent) * 0.42)
            path.lineTo(x0 + hook * 0.5, bottom - rule)
            path.lineTo(x0 + hook * 0.92, top)
            path.lineTo(x0 + hook + body.width + size * 0.06, top)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            painter.restore()
            body.paint(painter, x0 + hook, y)
            if index is not None:
                index.paint(painter, x, y - (ascent - descent) * 0.5 - index.descent)

        return Box(width, max(ascent, (index.height + (ascent - descent) * 0.5) if index else 0), descent, paint)

    def _scripts(self, base: Box, node: Node, size: float, italic_fix: float = 0.0) -> Box:
        small = size * SCRIPT_SCALE
        sup = self.layout(node.sup, small) if node.sup is not None else None
        sub = self.layout(node.sub, small) if node.sub is not None else None
        metrics = QFontMetricsF(_font(self.family, size))
        sup_shift = max(base.ascent - (sup.height * 0.55 if sup else 0), metrics.xHeight() * 0.75)
        sub_shift = max(base.descent + (sub.ascent * 0.35 if sub else 0), metrics.xHeight() * 0.3)
        if sup and sub:
            clash = (sup.descent - sup_shift) + (sub.ascent - sub_shift) + size * 0.1
            if clash > 0:
                sup_shift += clash / 2
                sub_shift += clash / 2
        script_width = max(sup.width if sup else 0, sub.width if sub else 0)
        gap = size * 0.04 + italic_fix

        def paint(painter: QPainter, x: float, y: float) -> None:
            base.paint(painter, x, y)
            if sup:
                sup.paint(painter, x + base.width + gap, y - sup_shift)
            if sub:
                sub.paint(painter, x + base.width + size * 0.04, y + sub_shift)

        return Box(
            base.width + gap + script_width + size * 0.05,
            max(base.ascent, sup_shift + sup.ascent if sup else 0),
            max(base.descent, sub_shift + sub.descent if sub else 0),
            paint,
        )

    def _script(self, node: Node, size: float) -> Box:
        return self._scripts(self.layout(node.items[0], size), node, size)

    def _bigop(self, node: Node, size: float) -> Box:
        if node.upright:
            operator = self.text(node.text, size)
        else:
            scale = 1.5 if self.display else 1.15
            operator = self.text(node.text, size * scale)
            axis = self.axis(size)
            # Centre the enlarged operator on the maths axis.
            shift = (operator.ascent - operator.descent) / 2 - axis
            operator = Box(operator.width, operator.ascent - shift, operator.descent + shift,
                           lambda painter, x, y, b=operator, s=shift: b.paint(painter, x, y + s))
        if node.sub is None and node.sup is None:
            return operator
        if not (node.limits and self.display):
            return self._scripts(operator, node, size, italic_fix=size * 0.1 if node.text in "∫∬∮" else 0)
        small = size * SCRIPT_SCALE
        over = self.layout(node.sup, small) if node.sup is not None else None
        under = self.layout(node.sub, small) if node.sub is not None else None
        gap = size * 0.1
        width = max(operator.width, over.width if over else 0, under.width if under else 0)

        def paint(painter: QPainter, x: float, y: float) -> None:
            operator.paint(painter, x + (width - operator.width) / 2, y)
            if over:
                over.paint(painter, x + (width - over.width) / 2, y - operator.ascent - gap - over.descent)
            if under:
                under.paint(painter, x + (width - under.width) / 2, y + operator.descent + gap + under.ascent)

        return Box(width, operator.ascent + (over.height + gap if over else 0),
                   operator.descent + (under.height + gap if under else 0), paint)

    def _accent(self, node: Node, size: float) -> Box:
        body = self.layout(node.items[0], size)
        gap = size * 0.1
        mark = size * 0.14
        rule = max(1.0, size * 0.055)
        kind = node.text

        def paint(painter: QPainter, x: float, y: float) -> None:
            body.paint(painter, x, y)
            painter.save()
            painter.setPen(QPen(painter.pen().color(), rule, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            top = y - body.ascent - gap
            left, right, middle = x + size * 0.05, x + body.width, x + body.width / 2 + size * 0.04
            if kind in ("bar", "overline"):
                painter.drawLine(QLineF(left, top, right, top))
            elif kind == "vec":
                painter.drawLine(QLineF(left, top, right, top))
                painter.drawLine(QLineF(right - mark, top - mark * 0.7, right, top))
                painter.drawLine(QLineF(right - mark, top + mark * 0.7, right, top))
            elif kind == "hat":
                painter.drawLine(QLineF(middle - mark, top, middle, top - mark))
                painter.drawLine(QLineF(middle, top - mark, middle + mark, top))
            elif kind == "tilde":
                path = QPainterPath(QPointF(middle - mark * 1.4, top))
                path.cubicTo(middle - mark * 0.7, top - mark * 1.4, middle + mark * 0.7, top + mark * 1.0,
                             middle + mark * 1.4, top - mark * 0.4)
                painter.drawPath(path)
            else:  # dot
                painter.setBrush(painter.pen().color())
                painter.drawEllipse(QPointF(middle, top - mark * 0.3), rule, rule)
            painter.restore()

        return Box(body.width + size * 0.05, body.ascent + gap + mark + rule, body.descent, paint)

    def _fenced(self, body: Box, left: str, right: str, size: float) -> Box:
        axis = self.axis(size)
        half = max(body.ascent - axis, body.descent + axis) + size * 0.05
        left_box = self.delimiter(left, size, half + axis, half - axis)
        right_box = self.delimiter(right, size, half + axis, half - axis)
        return self.hbox([left_box, body, right_box])

    def _delim(self, node: Node, size: float) -> Box:
        return self._fenced(self.layout(node.items[0], size), node.left, node.right, size)

    def _matrix(self, node: Node, size: float) -> Box:
        cells = [[self.layout(cell, size) for cell in row] for row in node.rows]
        columns = max((len(row) for row in cells), default=0)
        widths = [max((row[c].width for row in cells if c < len(row)), default=0.0) for c in range(columns)]
        ascents = [max((b.ascent for b in row), default=size * 0.7) for row in cells]
        descents = [max((b.descent for b in row), default=size * 0.2) for row in cells]
        column_gap, row_gap = size * 0.8, size * 0.35
        total_width = sum(widths) + column_gap * max(0, columns - 1) + size * 0.2
        total_height = sum(ascents) + sum(descents) + row_gap * max(0, len(cells) - 1)
        axis = self.axis(size)
        ascent = total_height / 2 + axis

        def paint(painter: QPainter, x: float, y: float) -> None:
            top = y - ascent
            for row, row_ascent, row_descent in zip(cells, ascents, descents, strict=True):
                baseline = top + row_ascent
                cx = x + size * 0.1
                for column, box in enumerate(row):
                    box.paint(painter, cx + (widths[column] - box.width) / 2, baseline)
                    cx += widths[column] + column_gap
                top += row_ascent + row_descent + row_gap

        body = Box(total_width, ascent, total_height - ascent, paint)
        return self._fenced(body, node.left, node.right, size)


@lru_cache(maxsize=512)
def _cached(latex: str, family: str, size: float, display: bool) -> Box | None:
    try:
        tree = parse(latex)
    except EquationError:
        return None
    return _Layout(family, display).layout(tree, size)


def layout_equation(latex: str, family: str, size_px: float, display: bool) -> Box:
    """Box for the equation; invalid LaTeX yields a box showing the source."""
    box = _cached(latex, family, round(size_px, 1), display)
    if box is not None:
        return box
    fallback = _Layout("DejaVu Sans Mono", False).text(latex or "?", size_px * 0.85)

    def paint(painter: QPainter, x: float, y: float) -> None:
        painter.save()
        painter.setPen(QColor("#c0392b"))
        fallback.paint(painter, x, y)
        painter.restore()

    return Box(fallback.width, fallback.ascent, fallback.descent, paint)


def paint_equation(painter: QPainter, rect: QRectF, latex: str, family: str, size_px: float, display: bool,
                   color: QColor | None = None) -> None:
    """Paint the equation centred in ``rect``."""
    box = layout_equation(latex, family, size_px, display)
    painter.save()
    painter.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(color or QColor("#000000"))
    x = rect.x() + (rect.width() - box.width) / 2
    y = rect.y() + (rect.height() - box.height) / 2 + box.ascent
    box.paint(painter, x, y)
    painter.restore()
