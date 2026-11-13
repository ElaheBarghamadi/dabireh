"""Shared fixtures. Tests run headless on Qt's "offscreen" platform."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["DABIREH_HOME"] = tempfile.mkdtemp(prefix="dabireh-tests-")

import pytest  # noqa: E402
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.application import create_application  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from app.services import Services  # noqa: E402
from editor.text_editor import RichTextEditor  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def qapp() -> Iterator[QApplication]:
    app = QApplication.instance() or create_application(["dabireh-tests"])
    yield app
    # Destroy leftover widgets while the application still exists.
    for widget in app.topLevelWidgets():
        widget.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.fixture
def editor(qapp: QApplication) -> Iterator[RichTextEditor]:
    widget = RichTextEditor()
    widget.resize(1100, 800)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()


@pytest.fixture
def services(tmp_path: Path) -> Services:
    return Services.create(tmp_path / "appdata")


@pytest.fixture
def window(qapp: QApplication, services: Services) -> Iterator[MainWindow]:
    main_window = MainWindow(services)
    main_window.show()
    qapp.processEvents()
    yield main_window
    main_window.editor.document().setModified(False)  # never block on the save prompt
    main_window.close()
    main_window.deleteLater()


def type_text(widget: RichTextEditor, text: str) -> None:
    """Type ``text`` through real key events, as a keyboard layout would."""
    for char in text:
        if char == "\n":
            event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier, "\r")
        else:
            event = QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, char)
        QApplication.sendEvent(widget, event)


def select(widget: RichTextEditor, start: int, end: int) -> QTextCursor:
    cursor = widget.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    widget.setTextCursor(cursor)
    return cursor


def select_text(widget: RichTextEditor, needle: str) -> QTextCursor:
    start = widget.toPlainText().index(needle)
    return select(widget, start, start + len(needle))
