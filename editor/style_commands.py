"""Named paragraph styles and the format painter."""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtGui import QTextBlock, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument

from core.document import NamedStyle
from editor.formatting import selected_blocks
from editor.objects import OBJECT_CHAR, PROP_STYLE_NAME, object_from_format
from editor.qt_bridge import block_format_from_style, char_format_from_style, style_from_block


def style_name_of(block: QTextBlock) -> str:
    fmt = block.blockFormat()
    return str(fmt.property(PROP_STYLE_NAME) or "") if fmt.hasProperty(PROP_STYLE_NAME) else ""


def _apply_to_block(block: QTextBlock, style: NamedStyle) -> None:
    cursor = QTextCursor(block)
    current = style_from_block(block)
    paragraph = replace(style.paragraph)
    if paragraph.direction == "auto":
        paragraph.direction = current.direction  # a style does not change the writing direction by itself
    paragraph.page_break_before = current.page_break_before or paragraph.page_break_before
    paragraph.style_name = "" if style.name == "Normal" else style.name
    cursor.setBlockFormat(block_format_from_style(paragraph))
    char_format = char_format_from_style(style.char)
    cursor.setBlockCharFormat(char_format)
    # Replace the character formatting of text; objects, links and bookmarks are kept.
    iterator = block.begin()
    spans: list[tuple[int, int, QTextCharFormat]] = []
    while not iterator.atEnd():
        fragment = iterator.fragment()
        if fragment.isValid() and not (OBJECT_CHAR in fragment.text()
                                        and object_from_format(fragment.charFormat()) is not None):
            fmt = QTextCharFormat(char_format)
            old = fragment.charFormat()
            if old.isAnchor():
                fmt.setAnchor(True)
                fmt.setAnchorHref(old.anchorHref())
                fmt.setAnchorNames(old.anchorNames())
            spans.append((fragment.position(), fragment.length(), fmt))
        iterator += 1
    for position, length, fmt in spans:
        cursor.setPosition(position)
        cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(fmt)


def apply_named_style(cursor: QTextCursor, style: NamedStyle) -> None:
    """Apply ``style`` to every paragraph touched by the cursor."""
    cursor.beginEditBlock()
    for block in selected_blocks(cursor):
        _apply_to_block(block, style)
    cursor.endEditBlock()


def reapply_style(document: QTextDocument, style: NamedStyle) -> int:
    """Re-apply an edited style to all paragraphs using it; returns how many."""
    wanted = "" if style.name == "Normal" else style.name
    if not wanted:
        return 0
    cursor = QTextCursor(document)
    cursor.beginEditBlock()
    count = 0
    block = document.begin()
    while block.isValid():
        if style_name_of(block) == wanted:
            _apply_to_block(block, style)
            count += 1
        block = block.next()
    cursor.endEditBlock()
    return count


def rename_style_in_document(document: QTextDocument, old: str, new: str) -> None:
    cursor = QTextCursor(document)
    cursor.beginEditBlock()
    block = document.begin()
    while block.isValid():
        if style_name_of(block) == old:
            fmt = QTextBlockFormat()
            fmt.setProperty(PROP_STYLE_NAME, new)
            QTextCursor(block).mergeBlockFormat(fmt)
        block = block.next()
    cursor.endEditBlock()


@dataclass
class CopiedFormat:
    char: QTextCharFormat
    block: QTextBlockFormat


def copy_format(cursor: QTextCursor) -> CopiedFormat:
    probe = QTextCursor(cursor)
    if probe.hasSelection():
        probe.setPosition(probe.selectionStart() + 1)
    char = QTextCharFormat(probe.charFormat())
    for prop in (PROP_STYLE_NAME,):
        char.clearProperty(prop)
    return CopiedFormat(char, QTextBlockFormat(cursor.blockFormat()))


def paste_format(cursor: QTextCursor, copied: CopiedFormat) -> None:
    """Apply a copied format: characters for a selection, paragraph format when a whole
    paragraph (or nothing) is selected."""
    cursor.beginEditBlock()
    first = cursor.document().findBlock(cursor.selectionStart())
    last = cursor.document().findBlock(cursor.selectionEnd())
    covers_block = (cursor.selectionStart() == first.position()
                    and cursor.selectionEnd() == last.position() + last.length() - 1)
    whole = not cursor.hasSelection() or first != last or covers_block
    if cursor.hasSelection():
        cursor.setCharFormat(copied.char)
    else:
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        cursor.setCharFormat(copied.char)
    if whole:
        direction = cursor.blockFormat().layoutDirection()
        fmt = QTextBlockFormat(copied.block)
        fmt.setLayoutDirection(direction)
        for block in selected_blocks(cursor):
            QTextCursor(block).setBlockFormat(fmt)
    cursor.endEditBlock()
