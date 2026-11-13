"""Conversion between the Qt text document and the structured document model.

Only the structures the model can represent are ever written into the Qt
document, so what the user sees is exactly what gets saved.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QTextBlock,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QTextFrame,
    QTextFrameFormat,
    QTextLength,
    QTextList,
    QTextListFormat,
    QTextTable,
    QTextTableFormat,
)

from core.document import (
    Block,
    CharStyle,
    Document,
    ListInfo,
    Paragraph,
    ParagraphStyle,
    Table,
    TableCell,
    TextRun,
)
from core.units import pt_to_px, px_to_pt
from editor.objects import PROP_STYLE_NAME, handler_for, insert_object, object_from_format

OBJECT_REPLACEMENT = "\ufffc"
WEIGHT_NORMAL = 400
WEIGHT_BOLD = 700

_DIRECTION_TO_QT = {
    "rtl": Qt.LayoutDirection.RightToLeft,
    "ltr": Qt.LayoutDirection.LeftToRight,
    "auto": Qt.LayoutDirection.LayoutDirectionAuto,
}
_QT_TO_DIRECTION = {value: key for key, value in _DIRECTION_TO_QT.items()}

_ALIGNMENT_TO_QT = {
    # Without Qt.AlignAbsolute, Qt resolves left/right against the paragraph
    # direction: AlignLeft is the leading edge and AlignRight the trailing one.
    "start": Qt.AlignmentFlag.AlignLeft,
    "end": Qt.AlignmentFlag.AlignRight,
    "center": Qt.AlignmentFlag.AlignHCenter,
    "justify": Qt.AlignmentFlag.AlignJustify,
}
_LIST_STYLE_TO_QT = {
    "bullet": QTextListFormat.Style.ListDisc,
    "circle": QTextListFormat.Style.ListCircle,
    "square": QTextListFormat.Style.ListSquare,
    "number": QTextListFormat.Style.ListDecimal,
    "alpha": QTextListFormat.Style.ListLowerAlpha,
    "roman": QTextListFormat.Style.ListLowerRoman,
}
_QT_TO_LIST_STYLE = {value: key for key, value in _LIST_STYLE_TO_QT.items()}
_QT_TO_LIST_STYLE[QTextListFormat.Style.ListUpperAlpha] = "alpha"
_QT_TO_LIST_STYLE[QTextListFormat.Style.ListUpperRoman] = "roman"
_UNDERLINE_TO_QT = {
    "dash": QTextCharFormat.UnderlineStyle.DashUnderline,
    "dot": QTextCharFormat.UnderlineStyle.DotLine,
    "wave": QTextCharFormat.UnderlineStyle.WaveUnderline,
}
_QT_TO_UNDERLINE = {value: key for key, value in _UNDERLINE_TO_QT.items()}
_VERTICAL_TO_QT = {
    "top": QTextCharFormat.VerticalAlignment.AlignTop,
    "middle": QTextCharFormat.VerticalAlignment.AlignMiddle,
    "bottom": QTextCharFormat.VerticalAlignment.AlignBottom,
}
_QT_TO_VERTICAL = {value: key for key, value in _VERTICAL_TO_QT.items()}


def qt_direction(direction: str) -> Qt.LayoutDirection:
    return _DIRECTION_TO_QT.get(direction, Qt.LayoutDirection.LayoutDirectionAuto)


def qt_alignment(alignment: str) -> Qt.AlignmentFlag:
    return _ALIGNMENT_TO_QT.get(alignment, Qt.AlignmentFlag.AlignLeft)


def qt_list_style(style: str) -> QTextListFormat.Style:
    return _LIST_STYLE_TO_QT.get(style, QTextListFormat.Style.ListDisc)


def list_style_name(text_list: QTextList | None) -> str | None:
    """Model list style name for a Qt list, or ``None``."""
    if text_list is None:
        return None
    return _QT_TO_LIST_STYLE.get(text_list.format().style(), "bullet")


# ------------------------------------------------------------ char formats
def char_format_from_style(style: CharStyle) -> QTextCharFormat:
    fmt = QTextCharFormat()
    if style.font_family:
        fmt.setFontFamilies([style.font_family])
    if style.font_size:
        fmt.setFontPointSize(style.font_size)
    if style.bold:
        fmt.setFontWeight(WEIGHT_BOLD)
    if style.italic:
        fmt.setFontItalic(True)
    if style.underline:
        fmt.setFontUnderline(True)
        if style.underline_style in _UNDERLINE_TO_QT:
            fmt.setUnderlineStyle(_UNDERLINE_TO_QT[style.underline_style])
    if style.letter_spacing and abs(style.letter_spacing - 100.0) > 0.01:
        fmt.setFontLetterSpacingType(QFont.SpacingType.PercentageSpacing)
        fmt.setFontLetterSpacing(style.letter_spacing)
    if style.stretch and abs(style.stretch - 100.0) > 0.01:
        fmt.setFontStretch(int(round(style.stretch)))
    if style.link or style.bookmark:
        fmt.setAnchor(True)
        if style.link:
            fmt.setAnchorHref(style.link)
        if style.bookmark:
            fmt.setAnchorNames([style.bookmark])
    if style.strike:
        fmt.setFontStrikeOut(True)
    if style.color:
        fmt.setForeground(QBrush(QColor(style.color)))
    if style.highlight:
        fmt.setBackground(QBrush(QColor(style.highlight)))
    if style.vertical_align == "super":
        fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
    elif style.vertical_align == "sub":
        fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSubScript)
    return fmt


def format_font_family(fmt: QTextCharFormat) -> str | None:
    """First explicitly set font family of a character format, if any."""
    # Guarded: PySide crashes when reading the property while it is unset.
    if fmt.hasProperty(QTextFormat.Property.FontFamilies):
        families = fmt.fontFamilies()
        if isinstance(families, str):
            families = [families]
        if families:
            return str(families[0])
    if not fmt.hasProperty(QTextFormat.Property.FontFamily):
        return None
    return fmt.fontFamily() or None


def style_from_char_format(fmt: QTextCharFormat) -> CharStyle:
    color = None
    if fmt.hasProperty(QTextFormat.Property.ForegroundBrush):
        brush = fmt.foreground()
        if brush.style() != Qt.BrushStyle.NoBrush:
            color = brush.color().name()
    highlight = None
    if fmt.hasProperty(QTextFormat.Property.BackgroundBrush):
        brush = fmt.background()
        if brush.style() != Qt.BrushStyle.NoBrush and brush.color().alpha() > 0:
            highlight = brush.color().name()
    vertical = fmt.verticalAlignment()
    vertical_align = None
    if vertical == QTextCharFormat.VerticalAlignment.AlignSuperScript:
        vertical_align = "super"
    elif vertical == QTextCharFormat.VerticalAlignment.AlignSubScript:
        vertical_align = "sub"
    size = fmt.fontPointSize() if fmt.hasProperty(QTextFormat.Property.FontPointSize) else 0.0
    underline_style = _QT_TO_UNDERLINE.get(fmt.underlineStyle())
    letter_spacing = None
    if fmt.hasProperty(QTextFormat.Property.FontLetterSpacing) and fmt.fontLetterSpacing() > 0:
        if fmt.fontLetterSpacingType() == QFont.SpacingType.PercentageSpacing:
            if abs(fmt.fontLetterSpacing() - 100.0) > 0.01:
                letter_spacing = round(fmt.fontLetterSpacing(), 2)
    stretch = None
    if fmt.hasProperty(QTextFormat.Property.FontStretch) and fmt.fontStretch() not in (0, 100):
        stretch = float(fmt.fontStretch())
    link = bookmark = None
    if fmt.isAnchor():
        link = fmt.anchorHref() or None
        names = fmt.anchorNames()
        bookmark = str(names[0]) if names else None
    return CharStyle(
        letter_spacing=letter_spacing,
        stretch=stretch,
        underline_style=underline_style,
        link=link,
        bookmark=bookmark,
        font_family=format_font_family(fmt),
        font_size=round(size, 2) if size > 0 else None,
        bold=fmt.hasProperty(QTextFormat.Property.FontWeight) and fmt.fontWeight() >= 600,
        italic=fmt.fontItalic(),
        underline=fmt.fontUnderline() or underline_style is not None,
        strike=fmt.fontStrikeOut(),
        color=color,
        highlight=highlight,
        vertical_align=vertical_align,
    )


# ----------------------------------------------------------- block formats
def block_format_from_style(style: ParagraphStyle) -> QTextBlockFormat:
    fmt = QTextBlockFormat()
    fmt.setAlignment(qt_alignment(style.alignment))
    fmt.setLayoutDirection(qt_direction(style.direction))
    fmt.setLineHeight(style.line_spacing * 100.0, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
    fmt.setTopMargin(pt_to_px(style.space_before))
    fmt.setBottomMargin(pt_to_px(style.space_after))
    fmt.setTextIndent(pt_to_px(style.first_line_indent))
    fmt.setLeftMargin(pt_to_px(style.indent_left))
    fmt.setRightMargin(pt_to_px(style.indent_right))
    if style.background:
        fmt.setBackground(QBrush(QColor(style.background)))
    if style.page_break_before:
        fmt.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
    if style.style_name:
        fmt.setProperty(PROP_STYLE_NAME, style.style_name)
    return fmt


def logical_alignment(fmt: QTextBlockFormat, is_rtl: bool) -> str:
    """Model alignment ("start"/"end"/"center"/"justify") of a block format."""
    if not fmt.hasProperty(QTextFormat.Property.BlockAlignment):
        return "start"
    alignment = fmt.alignment()
    if alignment & Qt.AlignmentFlag.AlignJustify:
        return "justify"
    if alignment & Qt.AlignmentFlag.AlignHCenter:
        return "center"
    is_right = bool(alignment & Qt.AlignmentFlag.AlignRight)
    if alignment & Qt.AlignmentFlag.AlignAbsolute:  # physical side, e.g. pasted HTML
        return "start" if is_right == is_rtl else "end"
    return "end" if is_right else "start"


def line_spacing_of(fmt: QTextBlockFormat) -> float:
    if fmt.lineHeightType() == QTextBlockFormat.LineHeightTypes.ProportionalHeight.value and fmt.lineHeight() > 0:
        return round(fmt.lineHeight() / 100.0, 3)
    return 1.0


def style_from_block(block: QTextBlock) -> ParagraphStyle:
    fmt = block.blockFormat()
    is_rtl = block.textDirection() == Qt.LayoutDirection.RightToLeft
    return ParagraphStyle(
        alignment=logical_alignment(fmt, is_rtl),
        direction=_QT_TO_DIRECTION.get(fmt.layoutDirection(), "auto"),
        line_spacing=line_spacing_of(fmt),
        space_before=round(px_to_pt(fmt.topMargin()), 2),
        space_after=round(px_to_pt(fmt.bottomMargin()), 2),
        first_line_indent=round(px_to_pt(fmt.textIndent()), 2),
        indent_left=round(px_to_pt(fmt.leftMargin()), 2),
        indent_right=round(px_to_pt(fmt.rightMargin()), 2),
        background=_brush_name(fmt),
        page_break_before=bool(fmt.pageBreakPolicy() & QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore),
        style_name=str(fmt.property(PROP_STYLE_NAME) or "") if fmt.hasProperty(PROP_STYLE_NAME) else "",
    )


def _brush_name(fmt: QTextFormat) -> str | None:
    if not fmt.hasProperty(QTextFormat.Property.BackgroundBrush):
        return None
    brush = fmt.background()
    if brush.style() == Qt.BrushStyle.NoBrush or brush.color().alpha() == 0:
        return None
    return brush.color().name()


# --------------------------------------------------------------- reading
def _read_runs(block: QTextBlock) -> list[TextRun]:
    runs: list[TextRun] = []
    iterator = block.begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        if fragment.isValid():
            char_format = fragment.charFormat()
            obj = object_from_format(char_format)
            if obj is not None and OBJECT_REPLACEMENT in fragment.text():
                # Adjacent identical objects share one fragment.
                runs.extend(TextRun("", CharStyle(), dict(obj)) for _ in range(fragment.text().count(OBJECT_REPLACEMENT)))
            else:
                text = fragment.text().replace(OBJECT_REPLACEMENT, "")
                if text:
                    style = style_from_char_format(char_format)
                    if runs and runs[-1].object is None and runs[-1].style == style:
                        runs[-1].text += text
                    else:
                        runs.append(TextRun(text, style))
        iterator += 1
    if not runs:
        # Keep the typing format of an empty paragraph (its font decides the line height).
        style = style_from_char_format(block.charFormat())
        if style != CharStyle():
            runs.append(TextRun("", style))
    return runs


def _read_paragraph(block: QTextBlock, list_ids: dict[int, int], in_cell: bool = False) -> Paragraph:
    list_info = None
    text_list = block.textList()
    if text_list is not None:
        list_id = list_ids.setdefault(text_list.objectIndex(), len(list_ids) + 1)
        list_info = ListInfo(
            style=list_style_name(text_list) or "bullet",
            level=max(1, text_list.format().indent()),
            list_id=list_id,
        )
    runs = _read_runs(block)
    if in_cell and not block.text():
        runs = []  # the block format of an empty cell is the cell format, not a typing format
    return Paragraph(runs=runs, style=style_from_block(block), list=list_info)


def _is_structural(paragraph: Paragraph) -> bool:
    """An empty paragraph Qt requires around tables (never typed by the user)."""
    return not paragraph.text and not any(run.object for run in paragraph.runs) and paragraph.list is None


def _read_table(table: QTextTable, list_ids: dict[int, int]) -> Table:
    fmt = table.format()
    rtl = fmt.layoutDirection() != Qt.LayoutDirection.LeftToRight
    count = table.columns()
    rows: list[list[TableCell | None]] = []
    for row in range(table.rows()):
        cells: list[TableCell | None] = []
        for column in range(count):
            # Qt lays columns out left to right; an RTL table is stored mirrored (see qt_column).
            cell = table.cellAt(row, count - 1 - column if rtl else column)
            anchor = count - cell.column() - cell.columnSpan() if rtl else cell.column()
            if cell.row() != row or anchor != column:
                cells.append(None)  # covered by a merged cell
                continue
            blocks = [b for b in _read_frame_blocks(cell.begin(), list_ids, True) if isinstance(b, Paragraph)]
            cell_format = cell.format()
            cells.append(TableCell(
                blocks=blocks or [Paragraph()],
                row_span=cell.rowSpan(),
                col_span=cell.columnSpan(),
                background=_brush_name(cell_format),
                vertical_align=_QT_TO_VERTICAL.get(cell_format.verticalAlignment(), "top"),
            ))
        rows.append(cells)
    widths = [c.rawValue() for c in fmt.columnWidthConstraints()
              if c.type() == QTextLength.Type.PercentageLength]
    alignment = fmt.alignment()
    if rtl:
        widths.reverse()
    if alignment & Qt.AlignmentFlag.AlignHCenter:
        align = "center"
    else:
        is_right = bool(alignment & Qt.AlignmentFlag.AlignRight)
        align = "start" if is_right == rtl else "end"
    width = fmt.width()
    return Table(
        rows=rows,
        column_widths=[round(w, 3) for w in widths] if len(widths) == table.columns() else [],
        header_rows=fmt.headerRowCount(),
        direction="rtl" if rtl else "ltr",
        alignment=align,
        width_percent=round(width.rawValue(), 2) if width.type() == QTextLength.Type.PercentageLength else 100.0,
        border_width=round(fmt.border(), 2),
        border_color=fmt.borderBrush().color().name(),
        cell_padding=round(fmt.cellPadding(), 2),
        role=str(fmt.property(PROP_STYLE_NAME) or "") if fmt.hasProperty(PROP_STYLE_NAME) else "",
    )


def _read_frame_blocks(iterator: QTextFrame.iterator, list_ids: dict[int, int], in_cell: bool = False) -> list[Block]:
    blocks: list[Block] = []
    while not iterator.atEnd():
        frame = iterator.currentFrame()
        if frame is not None:
            if isinstance(frame, QTextTable):
                blocks.append(_read_table(frame, list_ids))
            # Other frames (floating images) belong to the paragraph that anchors them.
        else:
            block = iterator.currentBlock()
            if block.isValid():
                blocks.append(_read_paragraph(block, list_ids, in_cell))
        iterator += 1
    return blocks


def read_blocks(qdoc: QTextDocument) -> list[Block]:
    """Read every top-level block (paragraphs and tables) in document order."""
    blocks = _read_frame_blocks(qdoc.rootFrame().begin(), {})
    result: list[Block] = []
    for index, block in enumerate(blocks):
        if isinstance(block, Paragraph) and _is_structural(block):
            before_table = index + 1 < len(blocks) and isinstance(blocks[index + 1], Table)
            after_table = index > 0 and isinstance(blocks[index - 1], Table)
            at_end = index == len(blocks) - 1
            if (index == 0 and before_table) or (after_table and (before_table or at_end)):
                continue
        result.append(block)
    return result or [Paragraph()]


def read_paragraphs(qdoc: QTextDocument) -> list[Paragraph]:
    """Top-level paragraphs only (see :func:`read_blocks`)."""
    return [block for block in read_blocks(qdoc) if isinstance(block, Paragraph)] or [Paragraph()]


# --------------------------------------------------------------- writing
def table_format_from(table: Table) -> QTextTableFormat:
    fmt = QTextTableFormat()
    rtl = table.direction != "ltr"
    fmt.setLayoutDirection(Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight)
    if table.alignment == "center":
        fmt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    else:
        right = (table.alignment == "start") == rtl
        fmt.setAlignment(Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft)
    fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, table.width_percent))
    fmt.setBorder(table.border_width)
    fmt.setBorderBrush(QBrush(QColor(table.border_color)))
    fmt.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid if table.border_width > 0
                       else QTextFrameFormat.BorderStyle.BorderStyle_None)
    fmt.setBorderCollapse(True)
    fmt.setCellSpacing(0)
    fmt.setCellPadding(table.cell_padding)
    if table.role:
        fmt.setProperty(PROP_STYLE_NAME, table.role)
    fmt.setHeaderRowCount(min(table.header_rows, max(0, len(table.rows) - 1)))
    columns = table.column_count
    widths = list(table.column_widths) if len(table.column_widths) == columns else [100.0 / max(1, columns)] * columns
    if rtl:
        widths.reverse()
    fmt.setColumnWidthConstraints([QTextLength(QTextLength.Type.PercentageLength, w) for w in widths])
    return fmt


def insert_table(cursor: QTextCursor, table: Table, lists: dict[int, QTextList] | None = None) -> QTextTable:
    """Insert ``table`` at ``cursor``; the cursor ends in the paragraph after it."""
    rows, columns = len(table.rows), table.column_count
    rtl = table.direction != "ltr"

    def qt_column(column: int, span: int = 1) -> int:
        """Qt column of a model column: RTL tables put model column 0 at the right."""
        return columns - column - span if rtl else column

    qtable = cursor.insertTable(max(1, rows), max(1, columns), table_format_from(table))
    for r, row in enumerate(table.rows):
        for c, cell in enumerate(row):
            if cell is None:
                continue
            # Content goes into the cell that stays the anchor once the span is merged.
            cell_cursor = qtable.cellAt(r, qt_column(c, min(cell.col_span, columns - c))).firstCursorPosition()
            insert_blocks(cell_cursor, list(cell.blocks), inline_first=False, lists=lists, in_cell=True)
    # Cell formats live on the first character of a cell, so they are applied after the content.
    for r, row in enumerate(table.rows):
        for c, cell in enumerate(row):
            if cell is None:
                continue
            span = min(cell.col_span, columns - c)
            if cell.row_span > 1 or span > 1:
                qtable.mergeCells(r, qt_column(c, span), min(cell.row_span, rows - r), span)
            qcell = qtable.cellAt(r, qt_column(c, span))
            cell_format = qcell.format().toTableCellFormat()
            if cell.background:
                cell_format.setBackground(QBrush(QColor(cell.background)))
            cell_format.setVerticalAlignment(_VERTICAL_TO_QT.get(cell.vertical_align, _VERTICAL_TO_QT["top"]))
            qcell.setFormat(cell_format)
    cursor.setPosition(qtable.lastPosition() + 1)
    return qtable


def _insert_runs(cursor: QTextCursor, paragraph: Paragraph) -> None:
    for run in paragraph.runs:
        if run.object is not None:
            insert_object(cursor, run.object, char_format_from_style(run.style))
        elif run.text:
            cursor.insertText(run.text, char_format_from_style(run.style))


def insert_blocks(cursor: QTextCursor, blocks: list[Block], *, inline_first: bool,
                  lists: dict[int, QTextList] | None = None, in_cell: bool = False) -> None:
    """Insert ``blocks`` at ``cursor``.

    With ``inline_first`` the first paragraph's text flows into the current
    paragraph (keeping that paragraph's formatting), as expected when pasting.
    Otherwise the current paragraph takes over the first paragraph's format.
    """
    lists = {} if lists is None else lists
    fresh = True  # the cursor's paragraph has not received content from ``blocks`` yet
    for index, block in enumerate(blocks):
        if isinstance(block, Table):
            if not fresh:
                # Qt puts the table after the current paragraph.
                pass
            elif index > 0:
                # The paragraph after the previous table is still empty: Qt keeps it as separator.
                cursor.setBlockFormat(QTextBlockFormat())
            insert_table(cursor, block, lists)
            cursor.setBlockFormat(QTextBlockFormat())
            cursor.setBlockCharFormat(QTextCharFormat())
            fresh = True
            continue
        paragraph = block
        first_format = char_format_from_style(
            next((run.style for run in paragraph.runs if run.object is None), CharStyle()))
        adopt_format = index > 0 or not inline_first
        if index > 0 and not (fresh and isinstance(blocks[index - 1], Table)):
            cursor.insertBlock(block_format_from_style(paragraph.style), first_format)
        elif adopt_format:
            cursor.setBlockFormat(block_format_from_style(paragraph.style))
            if not in_cell:  # a cell's first block format carries the cell format
                cursor.setBlockCharFormat(first_format)
            cursor.setCharFormat(first_format)
        if paragraph.list is not None and adopt_format:
            text_list = lists.get(paragraph.list.list_id)
            if text_list is None:
                list_format = QTextListFormat()
                list_format.setStyle(qt_list_style(paragraph.list.style))
                list_format.setIndent(paragraph.list.level)
                lists[paragraph.list.list_id] = cursor.createList(list_format)
            else:
                text_list.add(cursor.block())
        _insert_runs(cursor, paragraph)
        fresh = False


def insert_paragraphs(cursor: QTextCursor, paragraphs: list[Block], *, inline_first: bool) -> None:
    insert_blocks(cursor, paragraphs, inline_first=inline_first)


def apply_defaults(qdoc: QTextDocument, document: Document) -> None:
    """Apply the document-wide default font and paragraph direction."""
    font = QFont()
    font.setFamilies([document.defaults.font_family])
    font.setPointSizeF(document.defaults.font_size)
    qdoc.setDefaultFont(font)
    option = qdoc.defaultTextOption()
    option.setTextDirection(qt_direction(document.defaults.direction))
    qdoc.setDefaultTextOption(option)


def write_document(qdoc: QTextDocument, document: Document) -> None:
    """Replace the content of ``qdoc`` with ``document`` (clears undo history)."""
    qdoc.setUndoRedoEnabled(False)
    try:
        qdoc.clear()
        apply_defaults(qdoc, document)
        handler = handler_for(qdoc)
        handler.resources = dict(document.resources)
        cursor = QTextCursor(qdoc)
        insert_blocks(cursor, document.blocks, inline_first=False)
    finally:
        qdoc.setUndoRedoEnabled(True)
    qdoc.setModified(False)


def used_resource_keys(blocks: list[Block]) -> set[str]:
    keys: set[str] = set()

    def visit(paragraph: Paragraph) -> None:
        for run in paragraph.runs:
            if run.object and run.object.get("type") == "image":
                keys.add(str(run.object.get("resource", "")))

    for block in blocks:
        if isinstance(block, Paragraph):
            visit(block)
        else:
            for row in block.rows:
                for cell in row:
                    if cell is not None:
                        for paragraph in cell.blocks:
                            visit(paragraph)
    return keys
