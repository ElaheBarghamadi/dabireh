"""Formatting commands and queries that operate on a ``QTextCursor``.

Keeping these free of widgets makes them reusable and directly testable.
Alignment is stored relative to the paragraph direction (start/end), so
switching a paragraph between RTL and LTR flips it naturally, as in Word.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QFont,
    QTextBlock,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
    QTextDocument,
    QTextListFormat,
)

from core.document import ParagraphStyle
from core.typography import FontScheme, split_script_runs, utf16_length
from core.units import mm_to_pt, pt_to_px, px_to_pt
from editor.qt_bridge import (
    block_format_from_style,
    format_font_family,
    line_spacing_of,
    list_style_name,
    logical_alignment,
    qt_alignment,
    qt_direction,
    qt_list_style,
    style_from_block,
)

INDENT_STEP_PT = mm_to_pt(10.0)
VISUAL_ALIGNMENTS = ("right", "left", "center", "justify")


def selected_blocks(cursor: QTextCursor) -> list[QTextBlock]:
    """Blocks (paragraphs) touched by the cursor or its selection."""
    document = cursor.document()
    block = document.findBlock(cursor.selectionStart())
    last = document.findBlock(cursor.selectionEnd())
    blocks = [block]
    while block != last and block.next().isValid():
        block = block.next()
        blocks.append(block)
    return blocks


def is_rtl(block: QTextBlock) -> bool:
    return block.textDirection() == Qt.LayoutDirection.RightToLeft


# ---------------------------------------------------------------- alignment
def visual_alignment(block: QTextBlock) -> str:
    """Physical alignment of a block: right / left / center / justify."""
    logical = logical_alignment(block.blockFormat(), is_rtl(block))
    if logical in ("center", "justify"):
        return logical
    leading_is_right = is_rtl(block)
    return "right" if (logical == "start") == leading_is_right else "left"


def set_alignment(cursor: QTextCursor, alignment: str) -> None:
    """Align the selected paragraphs to a physical side, center or justify."""
    if alignment not in VISUAL_ALIGNMENTS:
        raise ValueError(f"unknown alignment: {alignment}")
    cursor.beginEditBlock()
    for block in selected_blocks(cursor):
        if alignment in ("center", "justify"):
            logical = alignment
        else:
            logical = "start" if (alignment == "right") == is_rtl(block) else "end"
        modifier = QTextBlockFormat()
        modifier.setAlignment(qt_alignment(logical))
        QTextCursor(block).mergeBlockFormat(modifier)
    cursor.endEditBlock()


# ---------------------------------------------------------------- direction
def set_direction(cursor: QTextCursor, direction: str) -> None:
    """Set paragraph direction ("rtl", "ltr" or "auto") for the selection.

    Side indents are mirrored when the effective direction changes so the
    paragraph keeps its shape relative to the reading direction.
    """
    cursor.beginEditBlock()
    for block in selected_blocks(cursor):
        was_rtl = is_rtl(block)
        block_cursor = QTextCursor(block)
        modifier = QTextBlockFormat()
        modifier.setLayoutDirection(qt_direction(direction))
        block_cursor.mergeBlockFormat(modifier)
        if is_rtl(block) != was_rtl:
            fmt = block.blockFormat()
            if fmt.leftMargin() != fmt.rightMargin():
                swap = QTextBlockFormat()
                swap.setLeftMargin(fmt.rightMargin())
                swap.setRightMargin(fmt.leftMargin())
                block_cursor.mergeBlockFormat(swap)
    cursor.endEditBlock()


# ------------------------------------------------------------------ spacing
def set_line_spacing(cursor: QTextCursor, multiple: float) -> None:
    modifier = QTextBlockFormat()
    modifier.setLineHeight(multiple * 100.0, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
    cursor.mergeBlockFormat(modifier)


def set_paragraph_spacing(cursor: QTextCursor, before_pt: float | None = None, after_pt: float | None = None) -> None:
    modifier = QTextBlockFormat()
    if before_pt is not None:
        modifier.setTopMargin(pt_to_px(max(0.0, before_pt)))
    if after_pt is not None:
        modifier.setBottomMargin(pt_to_px(max(0.0, after_pt)))
    cursor.mergeBlockFormat(modifier)


# ------------------------------------------------------------------ indents
def set_indents(
    cursor: QTextCursor,
    left_pt: float | None = None,
    right_pt: float | None = None,
    first_line_pt: float | None = None,
) -> None:
    modifier = QTextBlockFormat()
    if left_pt is not None:
        modifier.setLeftMargin(pt_to_px(max(0.0, left_pt)))
    if right_pt is not None:
        modifier.setRightMargin(pt_to_px(max(0.0, right_pt)))
    if first_line_pt is not None:
        modifier.setTextIndent(pt_to_px(first_line_pt))
    cursor.mergeBlockFormat(modifier)


def change_leading_indent(cursor: QTextCursor, delta_pt: float) -> None:
    """Increase/decrease the indent on the side where each paragraph starts."""
    cursor.beginEditBlock()
    for block in selected_blocks(cursor):
        fmt = block.blockFormat()
        modifier = QTextBlockFormat()
        if is_rtl(block):
            modifier.setRightMargin(max(0.0, fmt.rightMargin() + pt_to_px(delta_pt)))
        else:
            modifier.setLeftMargin(max(0.0, fmt.leftMargin() + pt_to_px(delta_pt)))
        QTextCursor(block).mergeBlockFormat(modifier)
    cursor.endEditBlock()


def paragraph_style_at(cursor: QTextCursor) -> ParagraphStyle:
    return style_from_block(cursor.document().findBlock(cursor.selectionStart()))


def apply_paragraph_style(cursor: QTextCursor, style: ParagraphStyle) -> None:
    """Apply a complete paragraph style to the selected paragraphs."""
    cursor.beginEditBlock()
    cursor.mergeBlockFormat(block_format_from_style(style))
    for block in selected_blocks(cursor):  # merging cannot remove a property
        block_cursor = QTextCursor(block)
        fmt = block_cursor.blockFormat()
        if not style.background:
            fmt.clearBackground()
        if not style.page_break_before:
            fmt.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_Auto)
        block_cursor.setBlockFormat(fmt)
    cursor.endEditBlock()


# -------------------------------------------------------------------- lists
def current_list_style(cursor: QTextCursor) -> str | None:
    return list_style_name(cursor.document().findBlock(cursor.selectionStart()).textList())


def remove_from_list(block: QTextBlock) -> None:
    text_list = block.textList()
    if text_list is None:
        return
    text_list.remove(block)
    block_cursor = QTextCursor(block)
    fmt = block_cursor.blockFormat()
    fmt.setIndent(0)
    block_cursor.setBlockFormat(fmt)


def toggle_list(cursor: QTextCursor, style: str) -> None:
    """Turn the selected paragraphs into a list of ``style`` or back to text."""
    blocks = selected_blocks(cursor)
    cursor.beginEditBlock()
    if all(list_style_name(block.textList()) == style for block in blocks):
        for block in blocks:
            remove_from_list(block)
    else:
        target = None
        previous = blocks[0].previous()
        if previous.isValid() and list_style_name(previous.textList()) == style:
            target = previous.textList()
        for block in blocks:
            if list_style_name(block.textList()) == style:
                target = block.textList()
                continue
            remove_from_list(block)
            if target is None:
                list_format = QTextListFormat()
                list_format.setStyle(qt_list_style(style))
                list_format.setIndent(1)
                target = QTextCursor(block).createList(list_format)
            else:
                target.add(block)
    cursor.endEditBlock()


# --------------------------------------------------------- character format
def clear_char_formatting(cursor: QTextCursor) -> None:
    """Reset the selection to the document's default character format."""
    cursor.setCharFormat(QTextCharFormat())


def apply_script_fonts(cursor: QTextCursor, scheme: FontScheme) -> int:
    """Set Persian, Latin and mathematical runs in their own font families.

    Works on the selection, or the whole document when nothing is selected.
    Only the font family changes; the text itself is never touched.  Returns
    the number of runs that were formatted.
    """
    document = cursor.document()
    if cursor.hasSelection():
        start, end = cursor.selectionStart(), cursor.selectionEnd()
    else:
        start, end = 0, max(0, document.characterCount() - 1)
    count = 0
    cursor.beginEditBlock()
    block = document.findBlock(start)
    while block.isValid() and block.position() <= end:
        text = block.text()
        offset = block.position()
        for run in split_script_runs(text):
            run_start = offset + utf16_length(text[: run.start])
            run_end = offset + utf16_length(text[: run.end])
            run_start, run_end = max(run_start, start), min(run_end, end)
            if run_start >= run_end:
                continue
            run_cursor = QTextCursor(document)
            run_cursor.setPosition(run_start)
            run_cursor.setPosition(run_end, QTextCursor.MoveMode.KeepAnchor)
            modifier = QTextCharFormat()
            modifier.setFontFamilies([scheme.family_for(run.script)])
            run_cursor.mergeCharFormat(modifier)
            count += 1
        block = block.next()
    cursor.endEditBlock()
    return count


# ------------------------------------------------------------------ queries
@dataclass(frozen=True)
class FormatState:
    """Formatting at the cursor, used to keep the toolbar in sync."""

    font_family: str
    font_size: float
    bold: bool
    italic: bool
    underline: bool
    strike: bool
    superscript: bool
    subscript: bool
    color: str | None
    highlight: str | None
    alignment: str  # right / left / center / justify
    direction: str  # rtl / ltr (resolved)
    list_style: str | None
    line_spacing: float


def format_state(cursor: QTextCursor, char_format: QTextCharFormat, default_font: QFont) -> FormatState:
    block = cursor.block()
    size = char_format.fontPointSize()
    foreground = char_format.foreground()
    background = char_format.background()
    vertical = char_format.verticalAlignment()
    return FormatState(
        font_family=format_font_family(char_format) or default_font.family(),
        font_size=size if size > 0 else default_font.pointSizeF(),
        bold=char_format.fontWeight() >= 600,
        italic=char_format.fontItalic(),
        underline=char_format.fontUnderline(),
        strike=char_format.fontStrikeOut(),
        superscript=vertical == QTextCharFormat.VerticalAlignment.AlignSuperScript,
        subscript=vertical == QTextCharFormat.VerticalAlignment.AlignSubScript,
        color=foreground.color().name() if foreground.style() != Qt.BrushStyle.NoBrush else None,
        highlight=background.color().name() if background.style() != Qt.BrushStyle.NoBrush else None,
        alignment=visual_alignment(block),
        direction="rtl" if is_rtl(block) else "ltr",
        list_style=list_style_name(block.textList()),
        line_spacing=line_spacing_of(block.blockFormat()),
    )


def leading_indent_pt(block: QTextBlock) -> float:
    fmt = block.blockFormat()
    return px_to_pt(fmt.rightMargin() if is_rtl(block) else fmt.leftMargin())


def document_statistics(document: QTextDocument) -> tuple[int, int]:
    """Return (word count, character count without paragraph breaks)."""
    text = document.toPlainText()
    return len(text.split()), len(text.replace("\n", ""))
