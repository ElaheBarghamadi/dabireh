"""Generated content: table of contents, lists of figures/tables, captions,
notes, bookmarks and cross-reference targets."""

from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtGui import QTextBlock, QTextCharFormat, QTextCursor, QTextDocument, QTextTable

from core.document import CharStyle, NamedStyle, Paragraph, ParagraphStyle, Table, TableCell, TextRun
from core.fields import format_page_number
from core.persian import to_latin_digits, to_persian_digits
from editor import qt_bridge
from editor.objects import PROP_STYLE_NAME, object_from_format
from editor.style_commands import style_name_of

CAPTION_LABELS = {"figure": "شکل", "table": "جدول"}
LIST_TITLES = {"toc": "فهرست مطالب", "lof": "فهرست شکل‌ها", "lot": "فهرست جدول‌ها"}
NOTES_STYLE = "Notes"
NOTES_TITLE = "پی‌نوشت‌ها"
_CAPTION_RE = re.compile(r"^\s*(شکل|جدول)\s+([0-9۰-۹]+)")


@dataclass
class Entry:
    level: int
    text: str
    block: QTextBlock
    kind: str = "heading"
    number: int = 0


def page_of_block(document: QTextDocument, block: QTextBlock) -> int:
    height = document.pageSize().height()
    if height <= 0:
        return 1
    top = document.documentLayout().blockBoundingRect(block).top()
    return int(top // height) + 1


def _in_table(block: QTextBlock) -> bool:
    return QTextCursor(block).currentTable() is not None


def headings(document: QTextDocument, styles: dict[str, NamedStyle]) -> list[Entry]:
    entries: list[Entry] = []
    block = document.begin()
    while block.isValid():
        style = styles.get(style_name_of(block))
        if style is not None and style.heading_level and block.text().strip() and not _in_table(block):
            entries.append(Entry(style.heading_level, block.text().strip(), block))
        block = block.next()
    return entries


def captions(document: QTextDocument) -> list[Entry]:
    entries: list[Entry] = []
    block = document.begin()
    while block.isValid():
        if style_name_of(block) == "Caption":
            match = _CAPTION_RE.match(block.text())
            if match:
                kind = "figure" if match.group(1) == CAPTION_LABELS["figure"] else "table"
                entries.append(Entry(1, block.text().strip(), block, kind, int(to_latin_digits(match.group(2)))))
        block = block.next()
    return entries


def caption_text(kind: str, number: int, text: str, digits: str = "persian") -> str:
    label = f"{CAPTION_LABELS[kind]} {format_page_number(number, digits)}"
    return f"{label}: {text}" if text else label


def renumber_captions(document: QTextDocument, digits: str = "persian") -> int:
    """Number figure and table captions in document order; returns the number of changes."""
    counters = {"figure": 0, "table": 0}
    changes = 0
    cursor = QTextCursor(document)
    cursor.beginEditBlock()
    for entry in captions(document):
        counters[entry.kind] += 1
        match = _CAPTION_RE.match(entry.block.text())
        wanted = format_page_number(counters[entry.kind], digits)
        if match and match.group(2) != wanted:
            start = entry.block.position() + match.start(2)
            cursor.setPosition(start)
            cursor.setPosition(start + len(match.group(2)), QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(wanted, cursor.charFormat())
            changes += 1
    cursor.endEditBlock()
    return changes


def next_caption_number(document: QTextDocument, kind: str, before_position: int) -> int:
    return 1 + sum(1 for e in captions(document) if e.kind == kind and e.block.position() < before_position)


# ---------------------------------------------------------- generated lists
def _list_table(role: str, entries: list[tuple[int, str, int]], digits: str) -> Table:
    rows: list[list[TableCell | None]] = []
    for level, text, page in entries:
        title_style = ParagraphStyle(indent_right=(level - 1) * 16.0)
        title = Paragraph(runs=[TextRun(text, CharStyle(bold=level == 1 and role == "toc"))], style=title_style)
        number = Paragraph(runs=[TextRun(format_page_number(page, digits))], style=ParagraphStyle(alignment="end"))
        rows.append([TableCell([title]), TableCell([number])])
    if not rows:
        rows.append([TableCell([Paragraph(runs=[TextRun("—")])]), TableCell()])
    return Table(rows=rows, column_widths=[88.0, 12.0], border_width=0.0, cell_padding=2.0, role=role)


def find_generated_table(document: QTextDocument, role: str) -> QTextTable | None:
    for frame in document.rootFrame().childFrames():
        if isinstance(frame, QTextTable):
            fmt = frame.format()
            if fmt.hasProperty(PROP_STYLE_NAME) and fmt.property(PROP_STYLE_NAME) == role:
                return frame
    return None


def _entries_for(document: QTextDocument, styles: dict[str, NamedStyle], role: str) -> list[tuple[int, str, int]]:
    if role == "toc":
        source = headings(document, styles)
    else:
        kind = "figure" if role == "lof" else "table"
        source = [entry for entry in captions(document) if entry.kind == kind]
    return [(entry.level, entry.text, page_of_block(document, entry.block)) for entry in source]


def _replace_table(document: QTextDocument, old: QTextTable, table: Table) -> None:
    """Rewrite a generated list in place.

    The table object is kept (only its rows and cell texts change), so the
    paragraphs around it are never touched.
    """
    rows = len(table.rows)
    if old.rows() < rows:
        old.appendRows(rows - old.rows())
    elif old.rows() > rows:
        old.removeRows(rows, old.rows() - rows)
    columns = old.columns()
    rtl = table.direction != "ltr"
    for r, row in enumerate(table.rows):
        for c, cell in enumerate(row[:columns]):
            qcell = old.cellAt(r, columns - c - 1 if rtl else c)
            cursor = qcell.firstCursorPosition()
            cursor.setPosition(qcell.lastCursorPosition().position(), QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            paragraph = cell.blocks[0] if cell is not None and cell.blocks else None
            if paragraph is None:
                continue
            cursor.setBlockFormat(qt_bridge.block_format_from_style(paragraph.style))
            for run in paragraph.runs:
                cursor.insertText(run.text, qt_bridge.char_format_from_style(run.style))


def insert_generated_list(cursor: QTextCursor, styles: dict[str, NamedStyle], role: str, digits: str = "persian"
                          ) -> None:
    """Insert (or refresh) the table of contents / list of figures / list of tables."""
    document = cursor.document()
    cursor.beginEditBlock()
    if find_generated_table(document, role) is None:
        title_format = QTextCharFormat()
        title_format.setFontWeight(qt_bridge.WEIGHT_BOLD)
        title_format.setFontPointSize(document.defaultFont().pointSizeF() * 1.25)
        if cursor.block().text():
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cursor.insertBlock()
        block_format = qt_bridge.block_format_from_style(ParagraphStyle(space_after=6, style_name=role.upper()))
        cursor.setBlockFormat(block_format)
        cursor.insertText(LIST_TITLES[role], title_format)
        qt_bridge.insert_table(cursor, _list_table(role, _entries_for(document, styles, role), digits))
        block = cursor.block()  # the separator paragraph Qt adds after a table
        if not block.text() and block.next().isValid():
            cursor.deleteChar()
    cursor.endEditBlock()
    update_generated_lists(document, styles, digits)


def update_generated_lists(document: QTextDocument, styles: dict[str, NamedStyle], digits: str = "persian") -> int:
    """Refresh every generated list; page numbers are recomputed until stable."""
    updated = 0
    cursor = QTextCursor(document)
    cursor.beginEditBlock()
    for role in LIST_TITLES:
        for _ in range(3):
            old = find_generated_table(document, role)
            if old is None:
                break
            entries = _entries_for(document, styles, role)
            current = qt_bridge._read_table(old, {})
            wanted = _list_table(role, entries, digits)
            if [[c.text if c else "" for c in row] for row in current.rows] == \
                    [[c.text if c else "" for c in row] for row in wanted.rows]:
                break
            _replace_table(document, old, wanted)
            document.documentLayout().documentSize()  # force a layout so page numbers are current
            updated += 1
    cursor.endEditBlock()
    return updated


# -------------------------------------------------------------------- notes
def collect_notes(document: QTextDocument) -> list[str]:
    notes: list[str] = []
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            obj = object_from_format(fragment.charFormat()) if fragment.isValid() else None
            if obj is not None and obj.get("type") == "note":
                notes.extend([str(obj.get("text", ""))] * fragment.text().count("\ufffc"))
            iterator += 1
        block = block.next()
    return notes


def update_notes_section(document: QTextDocument, digits: str = "persian") -> int:
    """Rebuild the notes list at the end of the document; returns the number of notes."""
    notes = collect_notes(document)
    cursor = QTextCursor(document)
    cursor.beginEditBlock()
    generated = re.compile(r"^[0-9۰-۹]+\. ")
    first = last = None
    block = document.begin()
    while block.isValid():
        is_generated = style_name_of(block) == NOTES_STYLE and (
            block.text() == NOTES_TITLE or generated.match(block.text()) is not None)
        if is_generated and first is None:
            first = block
        if first is not None:
            if not is_generated:
                break  # text the user typed after the list is never removed
            last = block
        block = block.next()
    if first is not None and last is not None:
        at_start = first.position() == 0
        cursor.setPosition(0 if at_start else first.position() - 1)
        end = last.position() + last.length() - 1
        if at_start and last.next().isValid():
            end += 1
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
    if notes:
        cursor.movePosition(QTextCursor.MoveOperation.End)
        title_format = QTextCharFormat()
        title_format.setFontWeight(qt_bridge.WEIGHT_BOLD)
        small = QTextCharFormat()
        small.setFontPointSize(max(6.0, document.defaultFont().pointSizeF() * 0.85))
        title_style = ParagraphStyle(space_before=18, space_after=4, style_name=NOTES_STYLE)
        cursor.insertBlock(qt_bridge.block_format_from_style(title_style), title_format)
        cursor.insertText(NOTES_TITLE, title_format)
        entry_style = ParagraphStyle(style_name=NOTES_STYLE)
        for index, text in enumerate(notes, start=1):
            cursor.insertBlock(qt_bridge.block_format_from_style(entry_style), small)
            cursor.insertText(f"{format_page_number(index, digits)}. {text}", small)
    cursor.endEditBlock()
    return len(notes)


# ---------------------------------------------------------------- bookmarks
def bookmarks(document: QTextDocument) -> list[str]:
    names: list[str] = []
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid() and fragment.charFormat().isAnchor():
                for name in fragment.charFormat().anchorNames():
                    if name and name not in names:
                        names.append(str(name))
            iterator += 1
        block = block.next()
    return names


def find_bookmark(document: QTextDocument, name: str) -> int:
    """Position of the bookmark ``name`` or -1."""
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid() and name in fragment.charFormat().anchorNames():
                return fragment.position()
            iterator += 1
        block = block.next()
    return -1


def ensure_block_bookmark(block: QTextBlock, prefix: str = "ref") -> str:
    """Bookmark covering ``block``'s text (created when missing); returns its name."""
    document = block.document()
    iterator = block.begin()
    while not iterator.atEnd():
        names = iterator.fragment().charFormat().anchorNames()
        if names:
            return str(names[0])
        iterator += 1
    existing = set(bookmarks(document))
    index = 1
    while f"{prefix}{index}" in existing:
        index += 1
    name = f"{prefix}{index}"
    cursor = QTextCursor(block)
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
    fmt = QTextCharFormat()
    fmt.setAnchor(True)
    fmt.setAnchorNames([name])
    cursor.mergeCharFormat(fmt)
    return name


def digits_text(text: str, digits: str) -> str:
    return to_persian_digits(text) if digits == "persian" else to_latin_digits(text)
