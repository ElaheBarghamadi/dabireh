"""A raster drawing workspace with transparent or opaque image export."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QIODevice, QPointF, QRectF, QSaveFile, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QImage, QImageReader, QKeySequence, QMouseEvent, QPainter, QPen, QPixmap, QPolygonF, QTextOption
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QFileDialog, QGridLayout, QInputDialog, QLabel,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from ui.dialogs.common import ColorField

MAX_SIDE = 4096
MAX_HISTORY_BYTES = 96 * 1024 * 1024
MAX_HISTORY_STEPS = 30


def _empty_image(width: int, height: int) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    if image.isNull():
        raise MemoryError("Could not allocate the drawing canvas")
    image.fill(Qt.GlobalColor.transparent)
    return image


class DrawingCanvas(QWidget):
    """A transparent raster layer; the background is composited only on export."""

    changed = Signal()
    historyChanged = Signal(bool, bool)

    def __init__(self, width: int = 900, height: int = 600, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image = _empty_image(width, height)
        checker = QPixmap(32, 32)
        checker.fill(QColor("#ffffff"))
        painter = QPainter(checker)
        painter.fillRect(16, 0, 16, 16, QColor("#eeeeee"))
        painter.fillRect(0, 16, 16, 16, QColor("#eeeeee"))
        painter.end()
        self._checker = QBrush(checker)
        self._undo: list[QImage] = []
        self._redo: list[QImage] = []
        self.tool = "pen"
        self.color = QColor("#1f5fbf")
        self.fill_color = QColor("#dce8fb")
        self.background = QColor("#ffffff")
        self.transparent = True
        self.fill_enabled = False
        self.stroke_width = 4
        self.opacity = 100
        self.text_size = 24
        self.zoom = 1.0
        self._start: QPointF | None = None
        self._last: QPointF | None = None
        self._current: QPointF | None = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._resize_widget()

    def _resize_widget(self) -> None:
        self.setFixedSize(max(1, round(self._image.width() * self.zoom)),
                          max(1, round(self._image.height() * self.zoom)))
        self.update()

    def set_zoom(self, percent: int) -> None:
        self.zoom = percent / 100.0
        self._resize_widget()

    def _snapshot(self) -> None:
        self._undo.append(self._image.copy())
        self._redo.clear()
        # Bound memory as well as the step count; retain at least one undo state.
        while len(self._undo) > 1 and (len(self._undo) > MAX_HISTORY_STEPS or
                                        sum(image.sizeInBytes() for image in self._undo) > MAX_HISTORY_BYTES):
            self._undo.pop(0)
        self.historyChanged.emit(bool(self._undo), False)

    def _modified(self) -> None:
        self.changed.emit()
        self.update()

    def undo(self) -> None:
        if self._undo:
            self._redo.append(self._image)
            self._image = self._undo.pop()
            self._resize_widget()
            self.historyChanged.emit(bool(self._undo), True)
            self._modified()

    def redo(self) -> None:
        if self._redo:
            self._undo.append(self._image)
            self._image = self._redo.pop()
            self._resize_widget()
            self.historyChanged.emit(True, bool(self._redo))
            self._modified()

    def clear(self) -> None:
        self._snapshot()
        self._image.fill(Qt.GlobalColor.transparent)
        self._modified()

    def resize_canvas(self, width: int, height: int) -> None:
        if not (1 <= width <= MAX_SIDE and 1 <= height <= MAX_SIDE):
            raise ValueError("Invalid canvas size")
        if (width, height) == (self._image.width(), self._image.height()):
            return
        image = _empty_image(width, height)
        painter = QPainter(image)
        painter.drawImage(0, 0, self._image)
        painter.end()
        self._snapshot()
        self._image = image
        self._resize_widget()
        self._modified()

    def import_image(self, path: Path) -> bool:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and (size.width() > MAX_SIDE or size.height() > MAX_SIDE):
            return False
        image = reader.read()
        if image.isNull() or image.width() > MAX_SIDE or image.height() > MAX_SIDE:
            return False
        image = image.scaled(self._image.size(), Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        self._snapshot()
        painter = QPainter(self._image)
        painter.drawImage((self._image.width() - image.width()) // 2,
                          (self._image.height() - image.height()) // 2, image)
        painter.end()
        self._modified()
        return True

    def output_image(self, transparent: bool | None = None) -> QImage:
        transparent = self.transparent if transparent is None else transparent
        image = _empty_image(self._image.width(), self._image.height())
        if not transparent:
            image.fill(self.background)
        painter = QPainter(image)
        painter.drawImage(0, 0, self._image)
        painter.end()
        return image

    def save_image(self, path: Path | str) -> None:
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg"):
            raise ValueError("فرمت تصویر باید PNG یا JPG باشد.")
        if suffix in (".jpg", ".jpeg") and self.transparent:
            raise ValueError("JPEG از پس‌زمینهٔ شفاف پشتیبانی نمی‌کند؛ PNG را انتخاب کنید یا شفافیت را خاموش کنید.")
        output = QSaveFile(str(path))
        if not output.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(output.errorString())
        image = self.output_image(transparent=self.transparent if suffix == ".png" else False)
        if not image.save(output, "PNG" if suffix == ".png" else "JPEG"):
            output.cancelWriting()
            raise OSError("نوشتن تصویر ممکن نشد.")
        if not output.commit():
            raise OSError(output.errorString())

    def _point(self, point: QPointF) -> QPointF:
        return QPointF(min(max(point.x() / self.zoom, 0), self._image.width() - 1),
                       min(max(point.y() / self.zoom, 0), self._image.height() - 1))

    def _pen(self, tool: str) -> QPen:
        color = QColor(self.color)
        alpha = self.opacity / 100 * (0.35 if tool == "highlighter" else 1.0)
        color.setAlphaF(alpha)
        pen = QPen(color, self.stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                   Qt.PenJoinStyle.RoundJoin)
        return pen

    def _stroke(self, start: QPointF, end: QPointF) -> None:
        painter = QPainter(self._image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.tool == "eraser":
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        pen = self._pen(self.tool)
        painter.setPen(pen)
        if start == end:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(pen.color())
            painter.drawEllipse(start, self.stroke_width / 2, self.stroke_width / 2)
        else:
            painter.drawLine(start, end)
        painter.end()
        self.update()

    def _draw_shape(self, painter: QPainter, start: QPointF, end: QPointF) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self._pen(self.tool))
        fill = QColor(self.fill_color)
        fill.setAlphaF(self.opacity / 100)
        painter.setBrush(fill if self.fill_enabled else Qt.BrushStyle.NoBrush)
        rect = QRectF(start, end).normalized()
        if self.tool in ("line", "arrow"):
            painter.drawLine(start, end)
            if self.tool == "arrow":
                angle = math.atan2(end.y() - start.y(), end.x() - start.x())
                size = max(10.0, self.stroke_width * 3.0)
                points = [end] + [QPointF(end.x() + size * math.cos(angle + d),
                                          end.y() + size * math.sin(angle + d)) for d in (2.6, -2.6)]
                painter.setBrush(painter.pen().color())
                painter.drawPolygon(QPolygonF(points))
        elif self.tool == "rect":
            painter.drawRect(rect)
        elif self.tool == "ellipse":
            painter.drawEllipse(rect)

    def add_text(self, point: QPointF, text: str) -> None:
        if not text.strip():
            return
        self._snapshot()
        painter = QPainter(self._image)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont("Vazirmatn")
        font.setPixelSize(self.text_size)
        painter.setFont(font)
        painter.setPen(self._pen("text"))
        option = QTextOption(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        painter.drawText(QRectF(point.x(), point.y(), max(1, self._image.width() - point.x()),
                                max(1, self._image.height() - point.y())), text, option)
        painter.end()
        self._modified()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = self._point(event.position())
        if self.tool == "text":
            text, ok = QInputDialog.getMultiLineText(self, "درج متن", "متن:")
            if ok:
                self.add_text(point, text)
            return
        self._start = self._last = self._current = point
        if self.tool in ("pen", "highlighter", "eraser"):
            self._snapshot()
            self._stroke(point, point)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._start is None or not event.buttons() & Qt.MouseButton.LeftButton:
            return
        point = self._point(event.position())
        if self.tool in ("pen", "highlighter", "eraser") and self._last is not None:
            self._stroke(self._last, point)
        self._last = self._current = point
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self._start is None:
            return
        end = self._point(event.position())
        if self.tool in ("line", "arrow", "rect", "ellipse"):
            self._snapshot()
            painter = QPainter(self._image)
            self._draw_shape(painter, self._start, end)
            painter.end()
        elif self._last is not None:
            self._stroke(self._last, end)
        self._start = self._last = self._current = None
        self._modified()
        event.accept()

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        painter = QPainter(self)
        painter.scale(self.zoom, self.zoom)
        if self.transparent:
            painter.fillRect(QRectF(0, 0, self._image.width(), self._image.height()), self._checker)
        else:
            painter.fillRect(QRectF(0, 0, self._image.width(), self._image.height()), self.background)
        painter.drawImage(0, 0, self._image)
        if self._start is not None and self._current is not None and self.tool in ("line", "arrow", "rect", "ellipse"):
            self._draw_shape(painter, self._start, self._current)
        painter.end()


class DrawingDialog(QDialog):
    """Standalone drawing window; its finished raster can also be inserted into a document."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("کارگاه نقاشی")
        self.resize(1050, 800)
        self._dirty = False
        self.inserted_image: QImage | None = None
        self.canvas = DrawingCanvas()
        self.canvas.changed.connect(self._set_dirty)

        self.tools = QButtonGroup(self)
        self.tools.setExclusive(True)
        tools_grid = QGridLayout()
        self.tool_buttons: dict[str, QToolButton] = {}
        for i, (key, label) in enumerate((("pen", "قلم"), ("highlighter", "ماژیک"), ("eraser", "پاک‌کن"),
                                         ("line", "خط"), ("arrow", "پیکان"), ("rect", "مستطیل"),
                                         ("ellipse", "بیضی"), ("text", "متن"))):
            button = QToolButton()
            button.setText(label)
            button.setObjectName("DrawingTool")
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            button.setCheckable(True)
            button.setToolTip(label)
            button.clicked.connect(lambda _checked=False, name=key: self._select_tool(name))
            self.tools.addButton(button)
            self.tool_buttons[key] = button
            tools_grid.addWidget(button, i // 4, i % 4)
        self.tool_buttons["pen"].setChecked(True)

        self.color = ColorField("#1f5fbf", allow_none=False)
        self.fill = ColorField("#dce8fb", allow_none=False)
        self.background = ColorField("#ffffff", allow_none=False)
        self.fill_enabled = QCheckBox("پر کردن شکل")
        self.transparent = QCheckBox("خروجی با پس‌زمینهٔ شفاف")
        self.transparent.setChecked(True)
        self.stroke = QSpinBox()
        self.stroke.setRange(1, 200)
        self.stroke.setValue(4)
        self.stroke.setSuffix(" px")
        self.opacity = QSpinBox()
        self.opacity.setRange(1, 100)
        self.opacity.setValue(100)
        self.opacity.setSuffix(" ٪")
        self.text_size = QSpinBox()
        self.text_size.setRange(8, 150)
        self.text_size.setValue(24)
        self.text_size.setSuffix(" px")
        self.zoom = QSpinBox()
        self.zoom.setRange(25, 200)
        self.zoom.setSingleStep(25)
        self.zoom.setValue(75)
        self.canvas.set_zoom(75)
        self.zoom.setSuffix(" ٪")
        self.width = QSpinBox()
        self.height = QSpinBox()
        for spin, value in ((self.width, 900), (self.height, 600)):
            spin.setRange(64, MAX_SIDE)
            spin.setValue(value)
            spin.setSuffix(" px")
        resize_button = QPushButton("تغییر اندازهٔ بوم")
        resize_button.clicked.connect(self._resize_canvas)
        for field, callback in ((self.color, self._set_color), (self.fill, self._set_fill),
                                (self.background, self._set_background)):
            field.button.clicked.connect(callback)
        self.fill_enabled.toggled.connect(self._set_fill_enabled)
        self.transparent.toggled.connect(self._set_transparent)
        self.stroke.valueChanged.connect(lambda n: setattr(self.canvas, "stroke_width", n))
        self.opacity.valueChanged.connect(lambda n: setattr(self.canvas, "opacity", n))
        self.text_size.valueChanged.connect(lambda n: setattr(self.canvas, "text_size", n))
        self.zoom.valueChanged.connect(self.canvas.set_zoom)

        settings = QGridLayout()
        settings.addWidget(QLabel("رنگ قلم:"), 0, 0)
        settings.addWidget(self.color, 0, 1)
        settings.addWidget(QLabel("رنگ پرکردن:"), 0, 2)
        settings.addWidget(self.fill, 0, 3)
        settings.addWidget(self.fill_enabled, 0, 4)
        settings.addWidget(QLabel("ضخامت:"), 1, 0)
        settings.addWidget(self.stroke, 1, 1)
        settings.addWidget(QLabel("شفافیت قلم:"), 1, 2)
        settings.addWidget(self.opacity, 1, 3)
        settings.addWidget(QLabel("اندازهٔ متن:"), 1, 4)
        settings.addWidget(self.text_size, 1, 5)
        settings.addWidget(QLabel("رنگ پس‌زمینه:"), 2, 0)
        settings.addWidget(self.background, 2, 1)
        settings.addWidget(self.transparent, 2, 2, 1, 2)
        settings.addWidget(QLabel("بزرگ‌نمایی:"), 2, 4)
        settings.addWidget(self.zoom, 2, 5)
        settings.addWidget(QLabel("پهنا:"), 3, 0)
        settings.addWidget(self.width, 3, 1)
        settings.addWidget(QLabel("بلندی:"), 3, 2)
        settings.addWidget(self.height, 3, 3)
        settings.addWidget(resize_button, 3, 4, 1, 2)

        self.undo_button = QPushButton("واگرد")
        self.redo_button = QPushButton("ازنو")
        self.undo_button.setEnabled(False)
        self.redo_button.setEnabled(False)
        self.undo_button.clicked.connect(self.canvas.undo)
        self.redo_button.clicked.connect(self.canvas.redo)
        self.canvas.historyChanged.connect(self._history_changed)
        clear = QPushButton("پاک‌کردن بوم")
        clear.clicked.connect(self._clear)
        import_button = QPushButton("افزودن تصویر…")
        import_button.clicked.connect(self._import)
        self.export_button = QPushButton("ذخیرهٔ تصویر…")
        self.export_button.clicked.connect(self._export)
        insert = QPushButton("درج در سند")
        insert.clicked.connect(self._insert)
        close = QPushButton("بستن")
        close.clicked.connect(self.reject)
        actions = QGridLayout()
        for i, button in enumerate((self.undo_button, self.redo_button, clear, import_button,
                                    self.export_button, insert, close)):
            button.setAutoDefault(False)
            actions.addWidget(button, i // 4, i % 4)
        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setWidgetResizable(False)
        scroll.setMinimumSize(350, 220)
        hint = QLabel("ابزار را انتخاب کنید و روی بوم بکشید؛ برای متن، روی محل دلخواه کلیک کنید. شطرنجی یعنی شفاف.")
        hint.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(tools_grid)
        layout.addLayout(settings)
        layout.addWidget(scroll, 1)
        layout.addLayout(actions)

        for shortcut, callback in ((QKeySequence.StandardKey.Undo, self.canvas.undo),
                                   (QKeySequence.StandardKey.Redo, self.canvas.redo)):
            action = QAction(self)
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(callback)
            self.addAction(action)

    def _set_dirty(self) -> None:
        self._dirty = True
        self.width.setValue(self.canvas._image.width())
        self.height.setValue(self.canvas._image.height())

    def _history_changed(self, can_undo: bool, can_redo: bool) -> None:
        self.undo_button.setEnabled(can_undo)
        self.redo_button.setEnabled(can_redo)

    def _select_tool(self, tool: str) -> None:
        self.canvas.tool = tool

    def _set_color(self) -> None:
        self.canvas.color = QColor(self.color.color())

    def _set_fill(self) -> None:
        self.canvas.fill_color = QColor(self.fill.color())

    def _set_fill_enabled(self, enabled: bool) -> None:
        self.canvas.fill_enabled = enabled

    def _set_background(self) -> None:
        color = QColor(self.background.color())
        if color != self.canvas.background:
            self.canvas.background = color
            if not self.canvas.transparent:
                self._set_dirty()
            self.canvas.update()

    def _set_transparent(self, transparent: bool) -> None:
        if self.canvas.transparent != transparent:
            self.canvas.transparent = transparent
            self._set_dirty()
            self.canvas.update()

    def _resize_canvas(self) -> None:
        if self.width.value() < self.canvas._image.width() or self.height.value() < self.canvas._image.height():
            answer = QMessageBox.question(self, "تغییر اندازه", "بخش بیرون از اندازهٔ جدید بریده می‌شود. ادامه می‌دهید؟")
            if answer != QMessageBox.StandardButton.Yes:
                self.width.setValue(self.canvas._image.width())
                self.height.setValue(self.canvas._image.height())
                return
        self.canvas.resize_canvas(self.width.value(), self.height.value())

    def _clear(self) -> None:
        if QMessageBox.question(self, "پاک‌کردن بوم", "تمام نقاشی پاک شود؟ می‌توانید آن را واگرد کنید.") == QMessageBox.StandardButton.Yes:
            self.canvas.clear()

    def _import(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "افزودن تصویر", "", "تصویر (*.png *.jpg *.jpeg *.webp *.bmp)")
        if name and not self.canvas.import_image(Path(name)):
            QMessageBox.warning(self, "افزودن تصویر", "تصویر خوانده نشد یا اندازهٔ آن بیشتر از ۴۰۹۶ پیکسل است.")

    def _export(self) -> None:
        name, selected = QFileDialog.getSaveFileName(self, "ذخیرهٔ تصویر", "نقاشی.png", "PNG (*.png);;JPEG (*.jpg *.jpeg)")
        if not name:
            return
        path = Path(name)
        if not path.suffix:
            path = path.with_suffix(".jpg" if selected.startswith("JPEG") else ".png")
        try:
            self.canvas.save_image(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "ذخیرهٔ تصویر", str(error))
            return
        self._dirty = False

    def _insert(self) -> None:
        self.inserted_image = self.canvas.output_image()
        self._dirty = False
        self.accept()

    def _confirm_discard(self) -> bool:
        return not self._dirty or QMessageBox.question(
            self, "بستن کارگاه", "تغییرات نقاشی خروجی گرفته نشده‌اند. بدون ذخیره ببندم؟"
        ) == QMessageBox.StandardButton.Yes

    def reject(self) -> None:
        if self._confirm_discard():
            super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001
        if self._confirm_discard():
            self._dirty = False
            super().closeEvent(event)
        else:
            event.ignore()
