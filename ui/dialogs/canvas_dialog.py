"""A small, draggable layout canvas stored as a standard Dabireh shape group."""

from __future__ import annotations

import copy
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog, QDoubleSpinBox, QFormLayout, QGraphicsItem, QGraphicsObject,
    QGraphicsScene, QGraphicsView, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from editor.objects import paint_shape
from ui.dialogs.common import ColorField, choice_combo, persian_button_box


def _number(value: float, maximum: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0, maximum)
    spin.setDecimals(1)
    spin.setSuffix(" px")
    spin.setValue(value)
    return spin


class CanvasItem(QGraphicsObject):
    """One movable item; its description uses the existing shape renderer."""

    def __init__(self, shape: dict[str, Any], width: float, height: float, dialog: CanvasDialog) -> None:
        super().__init__()
        self.shape_data = copy.deepcopy(shape)
        self.width, self.height = width, height
        self.dialog = dialog
        self._resizing = False
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges |
                      QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: ANN001
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont("Vazirmatn")
        font.setPixelSize(15)
        painter.setFont(font)
        paint_shape(painter, self.boundingRect(), {**self.shape_data, "width": self.width, "height": self.height})
        if self.isSelected():
            painter.setPen(QPen(QColor("#2468c9"), 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(0.75, 0.75, -0.75, -0.75))
            painter.setPen(QPen(QColor("#2468c9"), 1))
            painter.setBrush(QColor("#ffffff"))
            painter.drawRect(QRectF(self.width - 8, self.height - 8, 7, 7))

    def itemChange(self, change, value):  # noqa: N802, ANN001, ANN201
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            area = self.scene().sceneRect()
            return QPointF(max(0.0, min(value.x(), area.width() - self.width)),
                           max(0.0, min(value.y(), area.height() - self.height)))
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene() and self.isSelected():
            self.dialog._sync_position(self)
        return result

    def set_size(self, width: float, height: float) -> None:
        self.prepareGeometryChange()
        self.width, self.height = width, height
        area = self.scene().sceneRect()
        self.setPos(min(self.x(), area.width() - width), min(self.y(), area.height() - height))
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802, ANN001
        handle = QRectF(self.width - 14, self.height - 14, 14, 14)
        if event.button() == Qt.MouseButton.LeftButton and self.isSelected() and handle.contains(event.pos()):
            self._resizing = True
            self._resize_start = event.scenePos()
            self._original_size = (self.width, self.height)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802, ANN001
        if self._resizing:
            delta = event.scenePos() - self._resize_start
            area = self.scene().sceneRect()
            width = min(area.width() - self.x(), max(8.0, self._original_size[0] + delta.x()))
            height = min(area.height() - self.y(), max(8.0, self._original_size[1] + delta.y()))
            self.set_size(width, height)
            self.dialog._sync_size(self)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802, ANN001
        if self._resizing:
            self._resizing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802, ANN001
        self.setSelected(True)
        self.dialog.text.setFocus()
        event.accept()


class CanvasView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, dialog: CanvasDialog) -> None:
        super().__init__(scene)
        self.dialog = dialog
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(260, 220)
        self.setToolTip("برای جابه‌جایی، شیء را بکشید. با کلیدهای جهت‌نما نیز می‌توانید آن را حرکت دهید.")

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        painter.fillRect(rect, QColor("#e7ebf1"))
        painter.fillRect(self.sceneRect(), QColor("#ffffff"))
        painter.setPen(QPen(QColor("#c4ceda"), 1))
        painter.drawRect(self.sceneRect())

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        item = self.dialog.selected_item()
        if item and event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.dialog.delete_selected()
            event.accept()
            return
        deltas = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
                  Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        if item and event.key() in deltas:
            dx, dy = deltas[event.key()]
            step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            item.setPos(item.x() + dx * step, item.y() + dy * step)
            event.accept()
            return
        super().keyPressEvent(event)


class CanvasDialog(QDialog):
    """Arrange text boxes and shapes freely within a bounded, inline canvas."""

    def __init__(self, obj: dict[str, Any] | None = None, parent: QWidget | None = None,
                 *, width: float = 520, height: float = 300) -> None:
        super().__init__(parent)
        self.setWindowTitle("چیدمان آزاد متن و شکل")
        self.resize(900, 680)
        self._obj = copy.deepcopy(obj or {"type": "shape", "kind": "group", "layout_canvas": True,
                                           "width": width, "height": height, "rotation": 0,
                                           "opacity": 1.0, "children": []})
        self.canvas_width = max(40.0, float(self._obj.get("width", width)))
        self.canvas_height = max(40.0, float(self._obj.get("height", height)))
        self._syncing = False
        self.scene = QGraphicsScene(0, 0, self.canvas_width, self.canvas_height, self)
        self.view = CanvasView(self.scene, self)
        self.view.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("متن این کادر یا شکل را بنویسید")
        self.text.setMaximumHeight(90)
        self.x = _number(0, self.canvas_width)
        self.y = _number(0, self.canvas_height)
        self.width = _number(120, self.canvas_width)
        self.height = _number(70, self.canvas_height)
        self.width.setMinimum(8)
        self.height.setMinimum(8)
        self.font_size = _number(16, 96)
        self.font_size.setMinimum(6)
        self.alignment = choice_combo([("right", "راست"), ("center", "وسط"), ("left", "چپ")], "right")
        self.fill = ColorField(None, none_text="بدون رنگ")
        self.stroke = ColorField(None, none_text="بدون خط")
        self.text_color = ColorField("#1f2430", allow_none=False)
        self.properties = QGroupBox("ویژگی‌های انتخاب‌شده")
        form = QFormLayout(self.properties)
        form.addRow("متن:", self.text)
        form.addRow("موقعیت افقی:", self.x)
        form.addRow("موقعیت عمودی:", self.y)
        form.addRow("پهنا:", self.width)
        form.addRow("بلندی:", self.height)
        form.addRow("اندازهٔ متن:", self.font_size)
        form.addRow("تراز متن:", self.alignment)
        form.addRow("رنگ متن:", self.text_color)
        form.addRow("رنگ درون:", self.fill)
        form.addRow("رنگ خط:", self.stroke)
        self.properties.setMaximumWidth(350)
        self.properties.setEnabled(False)

        add_text = QPushButton("+ کادر متن")
        add_rect = QPushButton("+ مستطیل")
        add_ellipse = QPushButton("+ بیضی")
        add_arrow = QPushButton("+ پیکان")
        remove = QPushButton("حذف")
        duplicate = QPushButton("رونوشت")
        front = QPushButton("به جلو")
        back = QPushButton("به عقب")
        for button in (add_text, add_rect, add_ellipse, add_arrow, remove, duplicate, front, back):
            button.setAutoDefault(False)
        add_text.clicked.connect(lambda: self.add_item("textbox"))
        add_rect.clicked.connect(lambda: self.add_item("rect"))
        add_ellipse.clicked.connect(lambda: self.add_item("ellipse"))
        add_arrow.clicked.connect(lambda: self.add_item("arrow"))
        remove.clicked.connect(self.delete_selected)
        duplicate.clicked.connect(self.duplicate_selected)
        front.clicked.connect(lambda: self.reorder(True))
        back.clicked.connect(lambda: self.reorder(False))
        tools = QGridLayout()
        for index, button in enumerate((add_text, add_rect, add_ellipse, add_arrow, duplicate, remove, front, back)):
            tools.addWidget(button, index // 4, index % 4)
        hint = QLabel("اشیا را بکشید؛ گوشهٔ پایین برای تغییر اندازه است. برای ویرایش متن دوبار کلیک کنید. محدودهٔ سفید بخشی از سند است.")
        hint.setWordWrap(True)
        hint.setObjectName("DialogHint")
        body = QHBoxLayout()
        body.addWidget(self.view, 1)
        body.addWidget(self.properties)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(tools)
        layout.addLayout(body, 1)
        layout.addWidget(persian_button_box(self))

        self.scene.selectionChanged.connect(self._selection_changed)
        self.text.textChanged.connect(self._update_selected)
        for control in (self.x, self.y, self.width, self.height, self.font_size):
            control.valueChanged.connect(self._update_selected)
        self.alignment.currentIndexChanged.connect(self._update_selected)
        # ColorField's own handler runs first; its buttons are only user-driven here.
        for field in (self.fill, self.stroke, self.text_color):
            for button in field.findChildren(QPushButton):
                button.clicked.connect(self._update_selected)

        for child in self._obj.get("children", []):
            if not isinstance(child, dict):
                continue
            w = min(self.canvas_width, max(8.0, float(child.get("w", 0.3)) * self.canvas_width))
            h = min(self.canvas_height, max(8.0, float(child.get("h", 0.3)) * self.canvas_height))
            self._add_shape(child, w, h, float(child.get("x", 0)) * self.canvas_width,
                            float(child.get("y", 0)) * self.canvas_height, select=False)
        self._selection_changed()

    def selected_item(self) -> CanvasItem | None:
        selected = self.scene.selectedItems()
        return selected[0] if selected and isinstance(selected[0], CanvasItem) else None

    def _items(self) -> list[CanvasItem]:
        return [item for item in self.scene.items(Qt.SortOrder.AscendingOrder) if isinstance(item, CanvasItem)]

    def _add_shape(self, shape: dict[str, Any], width: float, height: float, x: float, y: float,
                   *, select: bool = True) -> CanvasItem:
        item = CanvasItem(shape, width, height, self)
        self.scene.addItem(item)
        item.setZValue(len(self._items()) - 1)
        item.setPos(x, y)
        if select:
            self.scene.clearSelection()
            item.setSelected(True)
        return item

    def add_item(self, kind: str) -> None:
        index = len(self._items())
        shape = {"type": "shape", "kind": kind, "fill": None if kind in ("textbox", "arrow") else "#dfe9fb",
                 "stroke": None if kind == "textbox" else "#1f5fbf", "stroke_width": 2,
                 "opacity": 1.0, "rotation": 0, "text": "متن را اینجا بنویسید" if kind == "textbox" else "",
                 "font_size": 16, "font_family": "Vazirmatn", "text_color": "#1f2430",
                 "text_alignment": "right", "clip_text": True}
        width = min(160.0, self.canvas_width)
        height = min(70.0, self.canvas_height)
        columns = max(1, int((self.canvas_width - 12) // (width + 12)))
        self._add_shape(shape, width, height, 12 + (index % columns) * (width + 12),
                        12 + (index // columns) * (height + 12))

    def _selection_changed(self) -> None:
        item = self.selected_item()
        self.properties.setEnabled(item is not None)
        if item is None:
            return
        supports_text = item.shape_data.get("kind") not in ("line", "arrow", "connector")
        for control in (self.text, self.font_size, self.alignment, self.text_color):
            control.setEnabled(supports_text)
        self._syncing = True
        self.x.setValue(item.x())
        self.y.setValue(item.y())
        self.width.setValue(item.width)
        self.height.setValue(item.height)
        self.text.setPlainText(str(item.shape_data.get("text", "")))
        self.font_size.setValue(float(item.shape_data.get("font_size", 16)))
        self.alignment.setCurrentIndex(max(0, self.alignment.findData(item.shape_data.get("text_alignment", "right"))))
        self.fill.set_color(item.shape_data.get("fill"))
        self.stroke.set_color(item.shape_data.get("stroke"))
        self.text_color.set_color(item.shape_data.get("text_color", "#1f2430"))
        self._syncing = False

    def _sync_position(self, item: CanvasItem) -> None:
        if self._syncing:
            return
        self._syncing = True
        self.x.setValue(item.x())
        self.y.setValue(item.y())
        self._syncing = False

    def _sync_size(self, item: CanvasItem) -> None:
        if self._syncing:
            return
        self._syncing = True
        self.width.setValue(item.width)
        self.height.setValue(item.height)
        self._syncing = False

    def _update_selected(self, *_args: object) -> None:
        item = self.selected_item()
        if self._syncing or item is None:
            return
        item.shape_data.update(text=self.text.toPlainText(), font_size=self.font_size.value(),
                          text_alignment=self.alignment.currentData(), text_color=self.text_color.color(),
                          fill=self.fill.color(), stroke=self.stroke.color())
        item.set_size(self.width.value(), self.height.value())
        item.setPos(self.x.value(), self.y.value())
        self._sync_position(item)
        item.update()

    def delete_selected(self) -> None:
        item = self.selected_item()
        if item is not None:
            self.scene.removeItem(item)
            self._selection_changed()

    def duplicate_selected(self) -> None:
        item = self.selected_item()
        if item is not None:
            self._add_shape(item.shape_data, item.width, item.height, item.x() + 15, item.y() + 15)

    def reorder(self, front: bool) -> None:
        item = self.selected_item()
        if item is None:
            return
        items = [other for other in self._items() if other is not item]
        items = items + [item] if front else [item] + items
        for index, other in enumerate(items):
            other.setZValue(index)

    def object(self) -> dict[str, Any]:
        children = []
        for item in self._items():
            child = copy.deepcopy(item.shape_data)
            child.update(x=item.x() / self.canvas_width, y=item.y() / self.canvas_height,
                         w=item.width / self.canvas_width, h=item.height / self.canvas_height)
            children.append(child)
        result = copy.deepcopy(self._obj)
        result.update(type="shape", kind="group", layout_canvas=True, width=self.canvas_width,
                      height=self.canvas_height, children=children)
        return result
