"""Draggable text and shapes in a document-anchored layout canvas."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from core.document import Document
from editor import export
from editor.text_editor import RichTextEditor
from tests.conftest import type_text
from ui.dialogs.canvas_dialog import CanvasDialog


def test_canvas_items_drag_and_edit(qapp: QApplication) -> None:
    dialog = CanvasDialog(width=500, height=280)
    dialog.show()
    dialog.add_item("textbox")
    first = dialog.selected_item()
    dialog.text.setPlainText("متن فارسی\nEnglish")
    dialog.font_size.setValue(22)
    dialog.add_item("rect")
    second = dialog.selected_item()
    assert second.x() >= first.x() + first.width
    qapp.processEvents()

    start = dialog.view.mapFromScene(second.sceneBoundingRect().center())
    end = start + type(start)(45, 50)
    QTest.mousePress(dialog.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(dialog.view.viewport(), end, delay=20)
    QTest.mouseRelease(dialog.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    qapp.processEvents()
    assert second.x() > 200 and second.y() >= 50
    assert dialog.x.value() == pytest.approx(second.x(), abs=0.1)
    dialog.width.setValue(490)
    assert second.x() + second.width <= dialog.canvas_width + 0.01
    dialog.duplicate_selected()
    assert len(dialog.object()["children"]) == 3
    dialog.reorder(False)
    assert dialog.object()["children"][0]["kind"] == "rect"
    dialog.delete_selected()
    assert len(dialog.object()["children"]) == 2
    dialog.close()


def test_canvas_round_trip_undo_and_text_separation(editor: RichTextEditor, qapp: QApplication) -> None:
    dialog = CanvasDialog(width=480, height=240)
    dialog.add_item("textbox")
    dialog.text.setPlainText("متن یک")
    dialog.add_item("ellipse")
    dialog.text.setPlainText("متن دو")
    canvas = dialog.object()
    type_text(editor, "قبل بعد")
    cursor = editor.textCursor()
    cursor.setPosition(4)
    editor.setTextCursor(cursor)
    editor.insert_layout_canvas(canvas)
    doc = editor.to_document()
    assert [p.text for p in doc.paragraphs] == ["قبل ", "", "بعد"]
    assert doc.paragraphs[1].runs[0].object == canvas
    other = RichTextEditor()
    other.load_document(Document.from_json(doc.to_json()))
    assert other.to_document() == doc
    reopened = CanvasDialog(canvas)
    assert [item.shape_data["text"] for item in reopened._items()] == ["متن یک", "متن دو"]
    assert reopened.object() == canvas
    reopened.close()
    other.deleteLater()
    editor.undo()
    assert editor.toPlainText() == "قبل بعد"
    dialog.close()


def test_canvas_export_pdf_and_docx(editor: RichTextEditor, qapp: QApplication, tmp_path: Path) -> None:
    dialog = CanvasDialog(width=450, height=200)
    dialog.add_item("textbox")
    dialog.text.setPlainText("Hello canvas")
    dialog.add_item("rect")
    editor.insert_layout_canvas(dialog.object())
    pdf = tmp_path / "canvas.pdf"
    export.export_pdf(editor.document(), editor.page_settings, pdf, "")
    pymupdf = pytest.importorskip("pymupdf")
    with pymupdf.open(pdf) as document:
        assert "Hello canvas" in document[0].get_text()
    docx = tmp_path / "canvas.docx"
    export.export_docx(editor.to_document(), editor.document(), docx)
    from docx import Document as WordDocument
    assert len(WordDocument(docx).inline_shapes) == 1
    dialog.close()


def test_canvas_action_and_reopening(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import window_features

    canvas = {"type": "shape", "kind": "group", "layout_canvas": True, "width": 200,
              "height": 100, "rotation": 0, "opacity": 1, "children": []}
    received = []

    class FakeDialog:
        def __init__(self, obj=None, parent=None, **kwargs):
            received.append(obj)

        def exec(self):
            return True

        def object(self):
            return canvas

    monkeypatch.setattr(window_features, "CanvasDialog", FakeDialog)
    window.commands["insert_canvas"].trigger()
    doc = window.editor.to_document()
    assert doc.paragraphs[0].runs[0].object == canvas
    window.edit_object(0, canvas)
    assert received == [None, canvas]


def test_canvas_resize_handle_and_keyboard(qapp: QApplication) -> None:
    from PySide6.QtCore import QPoint, QPointF

    dialog = CanvasDialog(width=500, height=280)
    dialog.show()
    dialog.add_item("rect")
    item = dialog.selected_item()
    qapp.processEvents()
    start = dialog.view.mapFromScene(item.mapToScene(QPointF(item.width - 4, item.height - 4)))
    end = start + QPoint(30, 20)
    QTest.mousePress(dialog.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(dialog.view.viewport(), end, delay=20)
    QTest.mouseRelease(dialog.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    qapp.processEvents()
    assert item.width == pytest.approx(190, abs=1)
    assert item.height == pytest.approx(90, abs=1)
    assert dialog.width.value() == pytest.approx(item.width, abs=0.1)
    before = item.x()
    QTest.keyClick(dialog.view, Qt.Key.Key_Right)
    assert item.x() == before + 1
    QTest.keyClick(dialog.view, Qt.Key.Key_Delete)
    assert not dialog.object()["children"]
    dialog.close()


def test_cancelled_canvas_edit_does_not_change_document(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import window_features

    canvas = {"type": "shape", "kind": "group", "layout_canvas": True, "width": 200,
              "height": 100, "rotation": 0, "opacity": 1, "children": []}
    window.editor.insert_layout_canvas(canvas)
    before = window.editor.to_document()

    class CancelDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return False

    monkeypatch.setattr(window_features, "CanvasDialog", CancelDialog)
    window.edit_object(0, canvas)
    assert window.editor.to_document() == before
