"""Find and replace on a Qt text document."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QTextEdit

from core.persian import search_pattern


@dataclass(frozen=True)
class SearchOptions:
    case_sensitive: bool = False
    whole_words: bool = False
    tolerant: bool = True  # treat Persian/Arabic Yeh and Kaf as the same letter
    format_filter: str = ""  # "", "bold", "italic", "underline", "highlight", "link"


def matches_format(cursor: QTextCursor, format_filter: str) -> bool:
    """Whether every character of the cursor's selection has the wanted formatting."""
    if not format_filter:
        return True
    probe = QTextCursor(cursor.document())
    for position in range(cursor.selectionStart(), cursor.selectionEnd()):
        probe.setPosition(position + 1)
        fmt = probe.charFormat()
        ok = {
            "bold": fmt.fontWeight() >= 600,
            "italic": fmt.fontItalic(),
            "underline": fmt.fontUnderline() or fmt.underlineStyle() != fmt.UnderlineStyle.NoUnderline,
            "highlight": fmt.background().style() != Qt.BrushStyle.NoBrush,
            "link": fmt.isAnchor() and bool(fmt.anchorHref()),
        }.get(format_filter, True)
        if not ok:
            return False
    return True


def _find_formatted(document: QTextDocument, expression: QRegularExpression, start: QTextCursor,
                    flags: QTextDocument.FindFlag, format_filter: str) -> QTextCursor:
    """Next match from ``start`` that also satisfies the formatting filter."""
    found = document.find(expression, start, flags)
    while not found.isNull() and found.hasSelection() and not matches_format(found, format_filter):
        found = document.find(expression, found, flags)
    return found


def build_expression(query: str, options: SearchOptions) -> QRegularExpression:
    flags = QRegularExpression.PatternOption.UseUnicodePropertiesOption
    if not options.case_sensitive:
        flags |= QRegularExpression.PatternOption.CaseInsensitiveOption
    pattern = search_pattern(query, tolerant=options.tolerant, whole_words=options.whole_words)
    return QRegularExpression(pattern, flags)


def _find_flags(options: SearchOptions, backward: bool) -> QTextDocument.FindFlag:
    flags = QTextDocument.FindFlag(0)
    if backward:
        flags |= QTextDocument.FindFlag.FindBackward
    if options.case_sensitive:
        flags |= QTextDocument.FindFlag.FindCaseSensitively
    return flags


def find(editor: QTextEdit, query: str, options: SearchOptions, *, backward: bool = False) -> bool:
    """Select the next (or previous) match, wrapping around the document."""
    if not query:
        return False
    document = editor.document()
    expression = build_expression(query, options)
    flags = _find_flags(options, backward)
    found = _find_formatted(document, expression, editor.textCursor(), flags, options.format_filter)
    if found.isNull():
        start = QTextCursor(document)
        if backward:
            start.movePosition(QTextCursor.MoveOperation.End)
        found = _find_formatted(document, expression, start, flags, options.format_filter)
    if found.isNull() or not found.hasSelection():
        return False
    editor.setTextCursor(found)
    editor.ensureCursorVisible()
    return True


def selection_matches(editor: QTextEdit, query: str, options: SearchOptions) -> bool:
    cursor = editor.textCursor()
    if not query or not cursor.hasSelection():
        return False
    selected = cursor.selectedText()
    if not matches_format(cursor, options.format_filter):
        return False
    match = build_expression(query, options).match(selected)
    return match.hasMatch() and match.capturedStart() == 0 and match.capturedLength() == len(selected)


def replace_current(editor: QTextEdit, query: str, replacement: str, options: SearchOptions) -> bool:
    """Replace the selected match (if any) and move to the next one."""
    replaced = False
    if selection_matches(editor, query, options):
        editor.textCursor().insertText(replacement)
        replaced = True
    find(editor, query, options)
    return replaced


def replace_all(document: QTextDocument, query: str, replacement: str, options: SearchOptions) -> int:
    """Replace every match as a single undo step; returns the match count."""
    if not query:
        return 0
    expression = build_expression(query, options)
    flags = _find_flags(options, backward=False)
    group = QTextCursor(document)
    group.beginEditBlock()
    count = 0
    position = 0
    while True:
        found = document.find(expression, position, flags)
        if found.isNull():
            break
        if not found.hasSelection():
            position = found.position() + 1
            continue
        if not matches_format(found, options.format_filter):
            position = found.selectionEnd()
            continue
        found.insertText(replacement)
        position = found.position()
        count += 1
    group.endEditBlock()
    return count


def count_matches(document: QTextDocument, query: str, options: SearchOptions) -> int:
    if not query:
        return 0
    expression = build_expression(query, options)
    flags = _find_flags(options, backward=False)
    count = 0
    position = 0
    while True:
        found = document.find(expression, position, flags)
        if found.isNull():
            break
        position = found.position() + (0 if found.hasSelection() else 1)
        count += found.hasSelection()
    return count
