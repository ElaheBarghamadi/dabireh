"""Table editing commands working on the text cursor."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QTextCharFormat,
    QTextCursor,
    QTextLength,
    QTextTable,
    QTextTableCell,
)

from core.document import Paragraph, Table, TableCell, TextRun
from editor import qt_bridge


def current_table(cursor: QTextCursor) -> QTextTable | None:
    return cursor.currentTable()


def current_cell(cursor: QTextCursor) -> QTextTableCell | None:
    table = cursor.currentTable()
    if table is None:
        return None
    cell = table.cellAt(cursor)
    return cell if cell.isValid() else None


def new_table(rows: int, columns: int, *, header_rows: int = 0, direction: str = "rtl") -> Table:
    return Table(
        rows=[[TableCell() for _ in range(columns)] for _ in range(rows)],
        header_rows=header_rows,
        direction=direction,
    )


def insert_table(cursor: QTextCursor, table: Table) -> QTextTable:
    """Insert ``table`` after the cursor's paragraph and put the cursor in its first cell."""
    cursor.beginEditBlock()
    qtable = qt_bridge.insert_table(cursor, table)
    if table.header_rows:
        bold = QTextCharFormat()
        bold.setFontWeight(qt_bridge.WEIGHT_BOLD)
        for row in range(min(table.header_rows, qtable.rows())):
            for column in range(qtable.columns()):
                cell_cursor = qtable.cellAt(row, column).firstCursorPosition()
                cell_cursor.mergeBlockCharFormat(bold)
                cell_cursor.mergeCharFormat(bold)
    cursor.setPosition(first_cell(qtable).firstPosition())
    cursor.endEditBlock()
    return qtable


def is_rtl(table: QTextTable) -> bool:
    return table.format().layoutDirection() != Qt.LayoutDirection.LeftToRight


def first_cell(table: QTextTable) -> QTextTableCell:
    """The logically first cell (top right in an RTL table)."""
    return table.cellAt(0, table.columns() - 1 if is_rtl(table) else 0)


def next_cell(table: QTextTable, cell: QTextTableCell, backward: bool = False) -> QTextTableCell | None:
    """Cell after ``cell`` in reading order (Tab order), or ``None`` at the end."""
    columns = table.columns()
    rtl = is_rtl(table)
    logical = (columns - cell.column() - cell.columnSpan()) if rtl else cell.column()
    index = cell.row() * columns + logical
    step = -1 if backward else 1
    index += step * (1 if backward else cell.columnSpan())
    while 0 <= index < table.rows() * columns:
        row, column = divmod(index, columns)
        candidate = table.cellAt(row, columns - 1 - column if rtl else column)
        if candidate.isValid() and candidate != cell and candidate.row() == row:
            return candidate
        index += step
    return None


def selected_range(cursor: QTextCursor) -> tuple[int, int, int, int] | None:
    """(first_row, row_count, first_column, column_count) of the selection or current cell."""
    table = cursor.currentTable()
    if table is None:
        return None
    if cursor.hasComplexSelection():
        first_row, rows, first_column, columns = cursor.selectedTableCells()
        return first_row, rows, first_column, columns
    cell = table.cellAt(cursor)
    if not cell.isValid():
        return None
    return cell.row(), cell.rowSpan(), cell.column(), cell.columnSpan()


def _even_widths(table: QTextTable) -> None:
    fmt = table.format()
    columns = table.columns()
    fmt.setColumnWidthConstraints([QTextLength(QTextLength.Type.PercentageLength, 100.0 / columns)] * columns)
    table.setFormat(fmt)


def insert_row(cursor: QTextCursor, *, after: bool = True) -> bool:
    selection = selected_range(cursor)
    if selection is None:
        return False
    row, rows, _, _ = selection
    cursor.currentTable().insertRows(row + rows if after else row, 1)
    return True


def insert_column(cursor: QTextCursor, *, after: bool = True) -> bool:
    selection = selected_range(cursor)
    if selection is None:
        return False
    table = cursor.currentTable()
    _, _, column, columns = selection
    cursor.beginEditBlock()
    if is_rtl(table):
        after = not after  # "after" means towards the left in an RTL table
    table.insertColumns(column + columns if after else column, 1)
    _even_widths(table)
    cursor.endEditBlock()
    return True


def remove_rows(cursor: QTextCursor) -> bool:
    selection = selected_range(cursor)
    if selection is None:
        return False
    row, rows, _, _ = selection
    cursor.currentTable().removeRows(row, rows)  # removing every row deletes the table
    return True


def remove_columns(cursor: QTextCursor) -> bool:
    selection = selected_range(cursor)
    if selection is None:
        return False
    table = cursor.currentTable()
    _, _, column, columns = selection
    whole = columns >= table.columns()
    cursor.beginEditBlock()
    table.removeColumns(column, columns)
    if not whole:
        _even_widths(table)
    cursor.endEditBlock()
    return True


def delete_table(cursor: QTextCursor) -> bool:
    table = cursor.currentTable()
    if table is None:
        return False
    table.removeRows(0, table.rows())
    return True


def merge_cells(cursor: QTextCursor) -> bool:
    table = cursor.currentTable()
    if table is None or not cursor.hasComplexSelection():
        return False
    table.mergeCells(cursor)
    return True


def split_cell(cursor: QTextCursor) -> bool:
    """Undo a merge: split the current cell back into single cells."""
    cell = current_cell(cursor)
    if cell is None or (cell.rowSpan() == 1 and cell.columnSpan() == 1):
        return False
    cursor.currentTable().splitCell(cell.row(), cell.column(), 1, 1)
    return True


def _selected_cells(cursor: QTextCursor) -> list[QTextTableCell]:
    selection = selected_range(cursor)
    if selection is None:
        return []
    table = cursor.currentTable()
    row, rows, column, columns = selection
    cells: list[QTextTableCell] = []
    seen: set[tuple[int, int]] = set()
    for r in range(row, row + rows):
        for c in range(column, column + columns):
            cell = table.cellAt(r, c)
            key = (cell.row(), cell.column())
            if cell.isValid() and key not in seen:
                seen.add(key)
                cells.append(cell)
    return cells


def set_cell_background(cursor: QTextCursor, color: QColor | None) -> bool:
    cells = _selected_cells(cursor)
    cursor.beginEditBlock()
    for cell in cells:
        fmt = cell.format().toTableCellFormat()
        fmt.setBackground(QBrush(color) if color is not None else QBrush(Qt.BrushStyle.NoBrush))
        cell.setFormat(fmt)
    cursor.endEditBlock()
    return bool(cells)


def set_cell_vertical_alignment(cursor: QTextCursor, alignment: str) -> bool:
    """``alignment`` is "top", "middle" or "bottom"."""
    cells = _selected_cells(cursor)
    cursor.beginEditBlock()
    for cell in cells:
        fmt = cell.format().toTableCellFormat()
        fmt.setVerticalAlignment(qt_bridge._VERTICAL_TO_QT.get(alignment, QTextCharFormat.VerticalAlignment.AlignTop))
        cell.setFormat(fmt)
    cursor.endEditBlock()
    return bool(cells)


def set_cell_alignment(cursor: QTextCursor, alignment: str) -> bool:
    """Horizontal (logical) alignment of every paragraph in the selected cells."""
    cells = _selected_cells(cursor)
    cursor.beginEditBlock()
    for cell in cells:
        inner = cell.firstCursorPosition()
        inner.setPosition(cell.lastPosition(), QTextCursor.MoveMode.KeepAnchor)
        fmt = inner.blockFormat()
        fmt.setAlignment(qt_bridge.qt_alignment(alignment))
        block_format = type(fmt)()
        block_format.setAlignment(qt_bridge.qt_alignment(alignment))
        inner.mergeBlockFormat(block_format)
    cursor.endEditBlock()
    return bool(cells)


def table_model(table: QTextTable) -> Table:
    """Model snapshot of a Qt table (properties and content)."""
    return qt_bridge._read_table(table, {})


def apply_table_properties(table: QTextTable, properties: Table) -> None:
    """Apply table-level properties (not the content) from ``properties``."""
    reference = Table(
        rows=[[None] * table.columns() for _ in range(table.rows())],
        column_widths=properties.column_widths,
        header_rows=properties.header_rows,
        direction=properties.direction,
        alignment=properties.alignment,
        width_percent=properties.width_percent,
        border_width=properties.border_width,
        border_color=properties.border_color,
        cell_padding=properties.cell_padding,
        role=properties.role,
    )
    table.setFormat(qt_bridge.table_format_from(reference))


def caption_paragraph(text: str) -> Paragraph:
    return Paragraph(runs=[TextRun(text)])
