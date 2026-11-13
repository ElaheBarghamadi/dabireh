"""Drag image and shape anchors in the paged editor without losing content."""

from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.document import Document
from editor.text_editor import RichTextEditor
from tests.conftest import type_text


@pytest.fixture
def image_file(tmp_path: Path) -> Path:
    image = QImage(120, 70, QImage.Format.Format_RGB32)
    image.fill(QColor("#318ad2"))
    path = tmp_path / "photo.png"
    assert image.save(str(path))
    return path


def all_objects(editor: RichTextEditor) -> list[dict]:
    return [run.object for p in editor.to_document().iter_paragraphs() for run in p.runs if run.object]


def caret(editor: RichTextEditor, position: int) -> QPoint:
    cursor = QTextCursor(editor.document())
    cursor.setPosition(position)
    return editor.cursorRect(cursor).center()


def drag(editor: RichTextEditor, start: QPoint, end: QPoint) -> None:
    viewport = editor.viewport()
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(viewport, end, delay=20)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=end)


def test_move_inline_picture_with_mouse_and_undo(editor: RichTextEditor, image_file: Path,
                                                  qapp: QApplication) -> None:
    type_text(editor, "before middle after")
    cursor = editor.textCursor()
    cursor.setPosition(7)
    editor.setTextCursor(cursor)
    picture = editor.insert_image_file(image_file)
    qapp.processEvents()
    start = caret(editor, 7) + QPoint(30, 30)
    assert editor._object_hit(start)[0] == 7
    end = caret(editor, 17)
    drag(editor, start, end)
    qapp.processEvents()
    assert editor.toPlainText() == "before middle af\ufffcter"
    assert all_objects(editor) == [picture]
    saved = editor.to_document()
    other = RichTextEditor()
    other.load_document(Document.from_json(saved.to_json()))
    assert other.to_document() == saved
    other.deleteLater()
    editor.undo()
    assert editor.toPlainText() == "before \ufffcmiddle after"
    assert all_objects(editor) == [picture]
    editor.redo()
    assert editor.toPlainText() == "before middle af\ufffcter"


def test_moving_object_programmatically_to_earlier_anchor(editor: RichTextEditor, image_file: Path) -> None:
    type_text(editor, "ABCD")
    picture = editor.insert_image_file(image_file)
    target = QTextCursor(editor.document())
    target.setPosition(1)
    assert editor.move_object(4, target)
    assert editor.toPlainText() == "A\ufffcBCD"
    assert all_objects(editor) == [picture]
    editor.undo()
    assert editor.toPlainText() == "ABCD\ufffc"


def test_drag_float_image_and_keep_wrap(editor: RichTextEditor, image_file: Path, qapp: QApplication) -> None:
    type_text(editor, "first paragraph\nsecond paragraph")
    cursor = editor.textCursor()
    cursor.setPosition(2)
    editor.setTextCursor(cursor)
    obj = editor.insert_image_file(image_file)
    editor.replace_object(2, {**obj, "wrap": "square_left"})
    qapp.processEvents()
    frame = editor.document().rootFrame().childFrames()[0]
    rect = editor.document().documentLayout().frameBoundingRect(frame)
    start = rect.center().toPoint()
    assert editor._object_hit(start)[0] == 2
    target = QTextCursor(editor.document())
    target.movePosition(QTextCursor.MoveOperation.End)
    assert editor.move_object(2, target)
    assert editor.toPlainText().replace("\ufffc", "") == "first paragraph\nsecond paragraph"
    assert len(all_objects(editor)) == 1 and all_objects(editor)[0]["wrap"] == "square_left"
    editor.undo()
    assert editor.toPlainText().index("\ufffc") == 2


def test_move_block_picture_keeps_text_and_alignment(editor: RichTextEditor, image_file: Path) -> None:
    type_text(editor, "before after")
    cursor = editor.textCursor()
    cursor.setPosition(7)
    editor.setTextCursor(cursor)
    picture = editor.insert_image_file(image_file)
    editor.replace_object(7, {**picture, "wrap": "block", "block_alignment": "center"})
    start = editor.toPlainText().index("\ufffc")
    target = QTextCursor(editor.document())
    target.movePosition(QTextCursor.MoveOperation.End)
    old = editor.toPlainText()
    assert editor.move_object(start, target, placement="left")
    assert editor.toPlainText().replace("\ufffc", "").replace("\n", "") == "before after"
    assert len(all_objects(editor)) == 1 and all_objects(editor)[0]["block_alignment"] == "left"
    editor.undo()
    assert editor.toPlainText() == old


def test_drag_cancel_and_drop_outside_preserves_contents(editor: RichTextEditor, image_file: Path,
                                                         qapp: QApplication) -> None:
    obj = editor.insert_image_file(image_file)
    qapp.processEvents()
    start = QPoint(min(caret(editor, 0).x(), caret(editor, 1).x()) + 30, caret(editor, 0).y())
    assert editor._object_hit(start)
    before = editor.to_document()
    drag(editor, start, QPoint(2, 2))
    assert editor.to_document() == before and all_objects(editor) == [obj]
    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(editor.viewport(), start + QPoint(30, 30))
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    QTest.mouseRelease(editor.viewport(), Qt.MouseButton.LeftButton, pos=start + QPoint(30, 30))
    assert editor.to_document() == before


def test_object_hit_does_not_select_adjacent_blank_area(editor: RichTextEditor, image_file: Path,
                                                         qapp: QApplication) -> None:
    editor.insert_image_file(image_file)
    qapp.processEvents()
    x = min(caret(editor, 0).x(), caret(editor, 1).x())
    y = caret(editor, 0).y()
    assert editor._object_hit(QPoint(x + 20, y))
    assert editor._object_hit(QPoint(x + 125, y)) is None


def test_drag_shape_and_undo(editor: RichTextEditor, qapp: QApplication) -> None:
    type_text(editor, "abc defghi")
    cursor = editor.textCursor()
    cursor.setPosition(4)
    editor.setTextCursor(cursor)
    shape = {"type": "shape", "kind": "rect", "width": 70, "height": 40,
             "fill": "#dfe9fb", "stroke": "#1f5fbf", "text": "hello"}
    editor.insert_object(shape)
    qapp.processEvents()
    start = QPoint(min(caret(editor, 4).x(), caret(editor, 5).x()) + 30, caret(editor, 4).y())
    assert editor._object_hit(start)[0] == 4
    drag(editor, start, caret(editor, 9))
    assert editor.toPlainText() == "abc defg\ufffchi"
    assert all_objects(editor) == [shape]
    editor.undo()
    assert editor.toPlainText() == "abc \ufffcdefghi"


def test_drag_auto_scrolls_and_stops(editor: RichTextEditor, image_file: Path, qapp: QApplication) -> None:
    editor.insert_image_file(image_file)
    editor.insertPlainText("\n" + "long line\n" * 100)
    editor.verticalScrollBar().setValue(0)
    qapp.processEvents()
    start = QPoint(min(caret(editor, 0).x(), caret(editor, 1).x()) + 30, caret(editor, 0).y())
    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=start)
    edge = QPoint(200, editor.viewport().height() - 5)
    QTest.mouseMove(editor.viewport(), edge, delay=20)
    assert editor._drag_scroll_timer.isActive()
    editor._scroll_during_object_drag()
    assert editor.verticalScrollBar().value() > 0
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    assert not editor._drag_scroll_timer.isActive()
    QTest.mouseRelease(editor.viewport(), Qt.MouseButton.LeftButton, pos=edge)
    assert len(all_objects(editor)) == 1


def test_drag_respects_read_only_and_invalid_sources(editor: RichTextEditor, image_file: Path) -> None:
    editor.insert_image_file(image_file)
    cursor = QTextCursor(editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setReadOnly(True)
    assert not editor.move_object(0, cursor)
    editor.setReadOnly(False)
    assert not editor.move_object(-1, cursor)
    assert len(all_objects(editor)) == 1


def test_external_image_drop_inserts_at_target_and_undoes(editor: RichTextEditor, image_file: Path,
                                                           qapp: QApplication) -> None:
    from PySide6.QtCore import QMimeData, QPointF, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent

    type_text(editor, "hello world")
    qapp.processEvents()
    point = caret(editor, 5)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(image_file))])
    enter = QDragEnterEvent(point, Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(editor.viewport(), enter)
    assert enter.isAccepted()
    move = QDragMoveEvent(point, Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                          Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(editor.viewport(), move)
    assert move.isAccepted()
    drop = QDropEvent(QPointF(point), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(editor.viewport(), drop)
    assert drop.isAccepted()
    assert editor.toPlainText() == "hello\ufffc world"
    assert len(all_objects(editor)) == 1
    editor.undo()
    assert editor.toPlainText() == "hello world"


def test_image_drop_invalid_files_and_remote_urls_are_safe(editor: RichTextEditor, image_file: Path,
                                                           tmp_path: Path, qapp: QApplication) -> None:
    from PySide6.QtCore import QMimeData, QPointF, QUrl
    from PySide6.QtGui import QDropEvent

    type_text(editor, "text")
    qapp.processEvents()
    point = caret(editor, 2)
    missing = tmp_path / "missing.png"
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(missing))])
    errors = []
    editor.imageDropFailed.connect(errors.append)
    drop = QDropEvent(QPointF(point), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier)
    editor.dropEvent(drop)
    assert editor.toPlainText() == "text" and errors == ["missing.png"]
    mime.setUrls([QUrl("https://example.com/image.png")])
    assert editor._image_file_paths(mime) == []


def test_multiple_external_images_drop_as_one_undo(editor: RichTextEditor, image_file: Path,
                                                    qapp: QApplication) -> None:
    from PySide6.QtCore import QMimeData, QPointF, QUrl
    from PySide6.QtGui import QDropEvent

    type_text(editor, "word")
    qapp.processEvents()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(image_file)), QUrl.fromLocalFile(str(image_file))])
    event = QDropEvent(QPointF(caret(editor, 2)), Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    editor.dropEvent(event)
    assert len(all_objects(editor)) == 2
    editor.undo()
    assert editor.toPlainText() == "word"


def test_move_image_between_table_cells(editor: RichTextEditor, image_file: Path) -> None:
    from core.document import Table

    editor.insert_table(1, 2, direction="ltr")
    table = editor.textCursor().currentTable()
    first = table.cellAt(0, 0).firstCursorPosition()
    editor.setTextCursor(first)
    type_text(editor, "first")
    obj = editor.insert_image_file(image_file)
    pos = editor.textCursor().position() - 1
    second = table.cellAt(0, 1).firstCursorPosition()
    assert editor.move_object(pos, second)
    result = next(block for block in editor.to_document().blocks if isinstance(block, Table))
    assert result.rows[0][0].text == "first"
    assert result.rows[0][1].blocks[0].runs[0].object == obj
    editor.undo()
    result = next(block for block in editor.to_document().blocks if isinstance(block, Table))
    assert result.rows[0][0].blocks[0].runs[-1].object == obj
    assert result.rows[0][1].text == ""


def test_drag_preview_is_rendered_and_double_click_still_works(editor: RichTextEditor, image_file: Path,
                                                                 qapp: QApplication) -> None:
    editor.insert_image_file(image_file)
    qapp.processEvents()
    start = QPoint(min(caret(editor, 0).x(), caret(editor, 1).x()) + 30, caret(editor, 0).y())
    calls = []
    editor.objectActivated.connect(lambda position, obj: calls.append((position, obj)))
    QTest.mouseDClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=start)
    assert calls and calls[0][0] == 0
    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(editor.viewport(), start + QPoint(-30, 25), delay=20)
    qapp.processEvents()
    assert editor._object_drag["active"]
    assert not editor.viewport().grab().isNull()
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    QTest.mouseRelease(editor.viewport(), Qt.MouseButton.LeftButton, pos=start + QPoint(-30, 25))


def test_mouse_drop_changes_block_alignment(editor: RichTextEditor, image_file: Path, qapp: QApplication) -> None:
    picture = editor.insert_image_file(image_file)
    editor.replace_object(0, {**picture, "wrap": "block", "block_alignment": "center"})
    qapp.processEvents()
    pos = editor.toPlainText().index("\ufffc")
    start = QPoint(min(caret(editor, pos).x(), caret(editor, pos + 1).x()) + 30, caret(editor, pos).y())
    end = QPoint(int(editor.page_geometry.margin_left + 20), start.y())
    drag(editor, start, end)
    assert all_objects(editor)[0]["block_alignment"] == "left"
    editor.undo()
    assert all_objects(editor)[0]["block_alignment"] == "center"


def test_image_hit_after_vertical_scroll(editor: RichTextEditor, image_file: Path, qapp: QApplication) -> None:
    type_text(editor, "line\n" * 22)
    position = editor.textCursor().position()
    editor.insert_image_file(image_file)
    qapp.processEvents()
    editor.ensureCursorVisible()
    qapp.processEvents()
    assert editor.verticalScrollBar().value() > 0
    start = QPoint(min(caret(editor, position).x(), caret(editor, position + 1).x()) + 30,
                   caret(editor, position).y())
    assert editor._object_hit(start)[0] == position


def test_external_drop_read_only_never_changes_document(editor: RichTextEditor, image_file: Path,
                                                         qapp: QApplication) -> None:
    from PySide6.QtCore import QMimeData, QPointF, QUrl
    from PySide6.QtGui import QDropEvent

    type_text(editor, "text")
    point = caret(editor, 2)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(image_file))])
    editor.setReadOnly(True)
    event = QDropEvent(QPointF(point), Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    editor.dropEvent(event)
    assert not event.isAccepted()
    assert editor.toPlainText() == "text"


def test_double_click_next_to_image_does_not_open_properties(editor: RichTextEditor, image_file: Path,
                                                            qapp: QApplication) -> None:
    editor.insert_image_file(image_file)
    qapp.processEvents()
    x = min(caret(editor, 0).x(), caret(editor, 1).x())
    y = caret(editor, 0).y()
    called = []
    editor.objectActivated.connect(lambda *_: called.append(True))
    QTest.mouseDClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(x + 125, y))
    assert not called


def test_dragging_object_preserves_a_multicharacter_selection(editor: RichTextEditor, image_file: Path,
                                                             qapp: QApplication) -> None:
    type_text(editor, "before after")
    cursor = editor.textCursor()
    cursor.setPosition(7)
    editor.setTextCursor(cursor)
    editor.insert_image_file(image_file)
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(10, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    qapp.processEvents()
    x = min(caret(editor, 7).x(), caret(editor, 8).x())
    start = QPoint(x + 30, caret(editor, 7).y())
    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=start)
    assert editor._object_drag is None
    QTest.mouseRelease(editor.viewport(), Qt.MouseButton.LeftButton, pos=start)


def test_moved_image_stays_in_pdf_export(editor: RichTextEditor, image_file: Path, tmp_path: Path) -> None:
    from editor.export import export_pdf

    pymupdf = pytest.importorskip("pymupdf")
    type_text(editor, "Before and after")
    cursor = editor.textCursor()
    cursor.setPosition(7)
    editor.setTextCursor(cursor)
    editor.insert_image_file(image_file)
    destination = QTextCursor(editor.document())
    destination.movePosition(QTextCursor.MoveOperation.End)
    assert editor.move_object(7, destination)
    path = tmp_path / "moved.pdf"
    export_pdf(editor.document(), editor.page_settings, path, "")
    with pymupdf.open(path) as pdf:
        assert pdf[0].get_images()
        assert "Before and after" in pdf[0].get_text()


def test_center_drop_preserves_float_side(editor: RichTextEditor, image_file: Path) -> None:
    obj = editor.insert_image_file(image_file)
    editor.replace_object(0, {**obj, "wrap": "square_left"})
    cursor = QTextCursor(editor.document())
    cursor.setPosition(0)
    assert not editor.move_object(0, cursor, placement="center")
    assert all_objects(editor)[0]["wrap"] == "square_left"
