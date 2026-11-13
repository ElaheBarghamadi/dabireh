"""Drawing tools, undo, compositing and output safety."""

from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from ui.dialogs.drawing_dialog import DrawingCanvas, DrawingDialog


def stroke(canvas: DrawingCanvas, start: QPoint, end: QPoint) -> None:
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas, end, delay=10)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)


def test_draw_erase_undo_redo_and_zoom(qapp: QApplication) -> None:
    canvas = DrawingCanvas(200, 120)
    canvas.show()
    canvas.color = QColor("red")
    canvas.stroke_width = 10
    stroke(canvas, QPoint(20, 30), QPoint(100, 30))
    assert canvas.output_image().pixelColor(60, 30).red() > 200
    canvas.tool = "eraser"
    stroke(canvas, QPoint(60, 30), QPoint(60, 30))
    assert canvas.output_image().pixelColor(60, 30).alpha() == 0
    canvas.undo()
    assert canvas.output_image().pixelColor(60, 30).alpha() == 255
    canvas.redo()
    assert canvas.output_image().pixelColor(60, 30).alpha() == 0
    canvas.undo()
    canvas.undo()
    assert canvas.output_image().pixelColor(60, 30).alpha() == 0
    canvas.set_zoom(200)
    assert canvas.size().width() == 400
    canvas.tool = "pen"
    stroke(canvas, QPoint(40, 60), QPoint(200, 60))
    assert canvas.output_image().pixelColor(60, 30).alpha() > 0
    canvas.close()


def test_shapes_fill_text_and_resize_undo(qapp: QApplication) -> None:
    canvas = DrawingCanvas(200, 120)
    canvas.show()
    canvas.tool = "rect"
    canvas.fill_enabled = True
    canvas.fill_color = QColor("#33aa66")
    stroke(canvas, QPoint(20, 20), QPoint(80, 70))
    assert canvas.output_image().pixelColor(40, 40).name() == "#33aa66"
    canvas.add_text(QPointF(10, 80), "Hello سلام")
    assert canvas.output_image().pixelColor(40, 40).alpha() == 255
    canvas.resize_canvas(80, 64)
    assert canvas.output_image().size().width() == 80
    canvas.undo()
    assert canvas.output_image().size().width() == 200
    assert canvas.output_image().pixelColor(40, 40).name() == "#33aa66"
    canvas.clear()
    assert canvas.output_image().pixelColor(40, 40).alpha() == 0
    canvas.undo()
    assert canvas.output_image().pixelColor(40, 40).alpha() == 255
    canvas.close()


def test_png_transparency_background_and_jpeg(qapp: QApplication, tmp_path: Path) -> None:
    canvas = DrawingCanvas(100, 80)
    canvas.add_text(QPointF(10, 10), "A")
    transparent = tmp_path / "transparent.png"
    canvas.save_image(transparent)
    image = QImage(str(transparent))
    assert image.size().width() == 100 and image.pixelColor(0, 0).alpha() == 0
    jpg = tmp_path / "opaque.jpg"
    jpg.write_bytes(b"original")
    with pytest.raises(ValueError):
        canvas.save_image(jpg)
    assert jpg.read_bytes() == b"original"
    canvas.transparent = False
    canvas.background = QColor("#f3ce87")
    opaque = tmp_path / "opaque.png"
    canvas.save_image(opaque)
    assert QImage(str(opaque)).pixelColor(0, 0) == QColor("#f3ce87")
    canvas.save_image(jpg)
    assert jpg.read_bytes().startswith(b"\xff\xd8")
    canvas.close()


def test_import_image_and_undo(qapp: QApplication, tmp_path: Path) -> None:
    canvas = DrawingCanvas(100, 100)
    image = QImage(40, 20, QImage.Format.Format_RGB32)
    image.fill(QColor("#ff0000"))
    path = tmp_path / "photo.png"
    assert image.save(str(path))
    assert not canvas.import_image(tmp_path / "missing.png")
    assert canvas.import_image(path)
    assert canvas.output_image().pixelColor(50, 50).red() > 200
    canvas.undo()
    assert canvas.output_image().pixelColor(50, 50).alpha() == 0
    canvas.close()


def test_dialog_tool_settings_and_unsaved_confirmation(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    dialog = DrawingDialog()
    dialog.show()
    dialog.tool_buttons["rect"].click()
    dialog.fill_enabled.setChecked(True)
    dialog.stroke.setValue(7)
    assert dialog.canvas.tool == "rect" and dialog.canvas.fill_enabled and dialog.canvas.stroke_width == 7
    dialog.canvas.add_text(QPointF(20, 20), "text")
    assert dialog._dirty
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    dialog.reject()
    assert dialog.isVisible()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    dialog.reject()
    assert not dialog.isVisible()


def test_insert_drawing_into_document(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import window_features

    image = QImage(120, 80, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    image.setPixelColor(30, 30, QColor("red"))

    class FakeDialog:
        def __init__(self, parent):
            self.inserted_image = image

        def exec(self):
            return True

    monkeypatch.setattr(window_features, "DrawingDialog", FakeDialog)
    window.commands["drawing_studio"].trigger()
    doc = window.editor.to_document()
    obj = doc.paragraphs[0].runs[0].object
    assert obj["type"] == "image" and obj["resource"] in doc.resources
    assert window.editor.objects.image(obj["resource"]).pixelColor(0, 0).alpha() == 0


@pytest.mark.parametrize("tool", ["pen", "highlighter", "line", "arrow", "rect", "ellipse"])
def test_all_drawing_tools_produce_pixels(qapp: QApplication, tool: str) -> None:
    canvas = DrawingCanvas(160, 120)
    canvas.show()
    canvas.tool = tool
    stroke(canvas, QPoint(20, 30), QPoint(120, 90))
    image = canvas.output_image()
    assert any(image.pixelColor(x, y).alpha() > 0 for x in range(0, 160, 4) for y in range(0, 120, 4))
    canvas.undo()
    assert not any(canvas.output_image().pixelColor(x, y).alpha() > 0
                   for x in range(0, 160, 4) for y in range(0, 120, 4))
    canvas.close()


def test_export_failure_does_not_clear_dirty_flag(qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
                                                  tmp_path: Path) -> None:
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    dialog = DrawingDialog()
    dialog.canvas.add_text(QPointF(20, 20), "hello")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(tmp_path / "out.jpg"), "JPEG (*.jpg *.jpeg)"))
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args))
    dialog._export()
    assert errors and dialog._dirty and not (tmp_path / "out.jpg").exists()
    dialog._dirty = False
    dialog.close()
