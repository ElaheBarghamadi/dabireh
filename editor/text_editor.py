"""The Dabireh rich-text editor widget.

Text is stored in logical Unicode order and laid out by Qt's bidirectional
text engine; nothing here reorders characters.
"""

from __future__ import annotations

import copy
from dataclasses import replace

from PySide6.QtCore import QMimeData, QRegularExpression, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFontDatabase,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import QWidget

from core import bidi
from core.document import (
    Document,
    DocumentDefaults,
    HeaderFooter,
    Metadata,
    NamedStyle,
    PageSettings,
    ParagraphStyle,
)
from core.styles import ensure_styles
from editor.objects import OBJECT_CHAR, PROP_DATA, ObjectHandler, handler_for, object_from_format, without_object
from core.persian import ZWNJ, to_latin_digits, to_persian_digits
from core.typography import (
    LATIN_FONT_FALLBACKS,
    MATH_FONT_FALLBACKS,
    PERSIAN_FONT_FALLBACKS,
    FontScheme,
    choose_font,
)
from editor import formatting, tables
from editor.editor_features import MIME_BLOCKS, FeatureMixin
from editor.page_view import PageTextEdit
from editor.qt_bridge import (
    WEIGHT_BOLD,
    WEIGHT_NORMAL,
    apply_defaults,
    read_blocks,
    used_resource_keys,
    write_document,
)


class RichTextEditor(FeatureMixin, PageTextEdit):
    objectActivated = Signal(int, dict)  # position, object description
    marginActivated = Signal()  # double click in the header/footer area
    formatPainted = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._info = Document(blocks=[])
        self.setAcceptRichText(True)
        self.setTabChangesFocus(False)
        self.load_document(Document())
        self.cursorPositionChanged.connect(self._drop_object_typing_format)

    def _drop_object_typing_format(self) -> None:
        """Text typed next to an object must not inherit the object's format."""
        if self.textCursor().hasSelection():
            return
        current = self.currentCharFormat()
        if current.hasProperty(PROP_DATA) or current.objectType() != 0:
            self.setCurrentCharFormat(without_object(current))

    # ------------------------------------------------------ document model
    @property
    def metadata(self) -> Metadata:
        return self._info.metadata

    @property
    def defaults(self) -> DocumentDefaults:
        return self._info.defaults

    def load_document(self, document: Document) -> None:
        """Show ``document`` in the editor (resets undo history and cursor)."""
        self._info = Document(
            metadata=replace(document.metadata),
            page=replace(document.page),
            defaults=replace(document.defaults),
            blocks=[],
            styles=copy.deepcopy(document.styles),
            header_footer=replace(document.header_footer),
        )
        ensure_styles(self._info)
        self.objects.math_font = self.font_scheme().math
        write_document(self.document(), document)
        self.set_running_content(self._info.header_footer, document.metadata.title)
        self.apply_page_settings(document.page)
        self.setTextCursor(QTextCursor(self.document()))
        self.document().setModified(False)

    def to_document(self) -> Document:
        """Snapshot the editor content as a structured document."""
        blocks = read_blocks(self.document())
        return Document(
            metadata=replace(self._info.metadata),
            page=self.page_settings,
            defaults=replace(self._info.defaults),
            blocks=blocks,
            styles=copy.deepcopy(self._info.styles),
            header_footer=replace(self._info.header_footer),
            resources=self.objects.used_resources(used_resource_keys(blocks)),
        )

    @property
    def objects(self) -> ObjectHandler:
        return handler_for(self.document())

    @property
    def styles(self) -> dict[str, NamedStyle]:
        return self._info.styles

    @property
    def header_footer(self) -> HeaderFooter:
        return self._info.header_footer

    def set_header_footer(self, value: HeaderFooter) -> None:
        if value != self._info.header_footer:
            self._info.header_footer = replace(value)
            self.set_running_content(self._info.header_footer, self._info.metadata.title)
            self.document().setModified(True)
            self.viewport().update()

    def set_metadata(self, metadata: Metadata) -> None:
        if metadata != self._info.metadata:
            self._info.metadata = replace(metadata)
            self.set_running_content(self._info.header_footer, metadata.title)
            self.document().setModified(True)

    def set_page_settings(self, page: PageSettings) -> None:
        if page != self.page_settings:
            self._info.page = replace(page)
            self.apply_page_settings(page)
            self.document().setModified(True)

    def set_defaults(self, defaults: DocumentDefaults) -> None:
        if defaults != self._info.defaults:
            self._info.defaults = replace(defaults)
            apply_defaults(self.document(), self._info)
            self.objects.math_font = self.font_scheme().math
            self._enforce_page_size()
            self.document().setModified(True)

    def font_scheme(self) -> FontScheme:
        """Per-script fonts of this document, resolved to installed families."""
        available = QFontDatabase.families()
        defaults = self._info.defaults
        return FontScheme(
            persian=choose_font(defaults.font_family, available, PERSIAN_FONT_FALLBACKS),
            latin=choose_font(defaults.latin_font, available, LATIN_FONT_FALLBACKS),
            math=choose_font(defaults.math_font, available, MATH_FONT_FALLBACKS),
        )

    # --------------------------------------------------- character format
    def _merge(self, modifier: QTextCharFormat) -> None:
        # Applies to the selection, or to the typing format when nothing is selected.
        self.mergeCurrentCharFormat(modifier)

    def set_bold(self, enabled: bool) -> None:
        modifier = QTextCharFormat()
        modifier.setFontWeight(WEIGHT_BOLD if enabled else WEIGHT_NORMAL)
        self._merge(modifier)

    def set_italic(self, enabled: bool) -> None:
        modifier = QTextCharFormat()
        modifier.setFontItalic(enabled)
        self._merge(modifier)

    def set_underline(self, enabled: bool) -> None:
        modifier = QTextCharFormat()
        modifier.setFontUnderline(enabled)
        self._merge(modifier)

    def set_strikethrough(self, enabled: bool) -> None:
        modifier = QTextCharFormat()
        modifier.setFontStrikeOut(enabled)
        self._merge(modifier)

    def set_vertical_alignment(self, mode: str | None) -> None:
        """``mode`` is "super", "sub" or ``None`` for normal text."""
        alignments = {
            "super": QTextCharFormat.VerticalAlignment.AlignSuperScript,
            "sub": QTextCharFormat.VerticalAlignment.AlignSubScript,
        }
        modifier = QTextCharFormat()
        modifier.setVerticalAlignment(alignments.get(mode, QTextCharFormat.VerticalAlignment.AlignNormal))
        self._merge(modifier)

    def set_font_family(self, family: str) -> None:
        modifier = QTextCharFormat()
        modifier.setFontFamilies([family])
        self._merge(modifier)

    def set_font_size(self, points: float) -> None:
        if points <= 0:
            return
        modifier = QTextCharFormat()
        modifier.setFontPointSize(points)
        self._merge(modifier)

    def set_text_color(self, color: QColor | None) -> None:
        """Set the text colour; ``None`` restores the automatic colour."""
        modifier = QTextCharFormat()
        modifier.setForeground(QBrush(color) if color is not None else QBrush(Qt.BrushStyle.NoBrush))
        self._merge(modifier)

    def set_highlight(self, color: QColor | None) -> None:
        """Set the highlight colour; ``None`` removes the highlight."""
        modifier = QTextCharFormat()
        modifier.setBackground(QBrush(color) if color is not None else QBrush(Qt.BrushStyle.NoBrush))
        self._merge(modifier)

    def clear_formatting(self) -> None:
        """Remove character formatting from the selection / typing format."""
        cursor = self.textCursor()
        if cursor.hasSelection():
            formatting.clear_char_formatting(cursor)
        self.setCurrentCharFormat(QTextCharFormat())

    def apply_script_fonts(self) -> int:
        return formatting.apply_script_fonts(self.textCursor(), self.font_scheme())

    # --------------------------------------------------- paragraph format
    def set_alignment(self, alignment: str) -> None:
        formatting.set_alignment(self.textCursor(), alignment)

    def set_direction(self, direction: str) -> None:
        formatting.set_direction(self.textCursor(), direction)

    def set_line_spacing(self, multiple: float) -> None:
        formatting.set_line_spacing(self.textCursor(), multiple)

    def set_paragraph_spacing(self, before_pt: float | None = None, after_pt: float | None = None) -> None:
        formatting.set_paragraph_spacing(self.textCursor(), before_pt, after_pt)

    def set_indents(
        self,
        left_pt: float | None = None,
        right_pt: float | None = None,
        first_line_pt: float | None = None,
    ) -> None:
        formatting.set_indents(self.textCursor(), left_pt, right_pt, first_line_pt)

    def increase_indent(self) -> None:
        formatting.change_leading_indent(self.textCursor(), formatting.INDENT_STEP_PT)

    def decrease_indent(self) -> None:
        formatting.change_leading_indent(self.textCursor(), -formatting.INDENT_STEP_PT)

    def toggle_list(self, style: str) -> None:
        formatting.toggle_list(self.textCursor(), style)

    def paragraph_style(self) -> ParagraphStyle:
        return formatting.paragraph_style_at(self.textCursor())

    def apply_paragraph_style(self, style: ParagraphStyle) -> None:
        formatting.apply_paragraph_style(self.textCursor(), style)

    def format_state(self) -> formatting.FormatState:
        return formatting.format_state(self.textCursor(), self.currentCharFormat(), self.document().defaultFont())

    # ------------------------------------------------ Persian / bidi tools
    def set_visual_cursor_movement(self, enabled: bool) -> None:
        """Arrow keys follow the screen (visual) or the typing order (logical)."""
        style = Qt.CursorMoveStyle.VisualMoveStyle if enabled else Qt.CursorMoveStyle.LogicalMoveStyle
        self.document().setDefaultCursorMoveStyle(style)

    def insert_text(self, text: str) -> None:
        self.textCursor().insertText(text, without_object(self.currentCharFormat()))

    def insert_zwnj(self) -> None:
        self.insert_text(ZWNJ)

    def isolate_selection_ltr(self) -> bool:
        """Wrap the selection in LRI…PDI so it reads left-to-right as a unit.

        Only two invisible Unicode controls are inserted; the selected
        characters stay untouched.  Returns ``False`` if there is no selection
        or it spans more than one paragraph.
        """
        cursor = self.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        document = self.document()
        if start == end or document.findBlock(start) != document.findBlock(end):
            return False
        cursor.beginEditBlock()
        cursor.setPosition(end)
        cursor.insertText(bidi.PDI)
        cursor.setPosition(start)
        cursor.insertText(bidi.LRI)
        cursor.endEditBlock()
        return True

    def convert_digits(self, target: str) -> int:
        """Convert digits in the selection (or whole document) to "persian" or "latin".

        Each digit is replaced in place and keeps its formatting.
        """
        convert = to_persian_digits if target == "persian" else to_latin_digits
        pattern = "[0-9٠-٩]" if target == "persian" else "[۰-۹٠-٩]"
        expression = QRegularExpression(pattern)
        document = self.document()
        cursor = self.textCursor()
        if cursor.hasSelection():
            position, end = cursor.selectionStart(), cursor.selectionEnd()
        else:
            position, end = 0, document.characterCount()
        count = 0
        cursor.beginEditBlock()
        while True:
            found = document.find(expression, position)
            if found.isNull() or found.selectionEnd() > end:
                break
            char_format = found.charFormat()
            found.insertText(convert(found.selectedText()), char_format)
            position = found.position()
            count += 1
        cursor.endEditBlock()
        return count

    # ------------------------------------------------------------ clipboard
    def paste_plain_text(self) -> None:
        text = QGuiApplication.clipboard().text()
        if text:
            self.textCursor().insertText(text)
            self.ensureCursorVisible()

    _drag_stash: tuple[str, str] | None = None  # (plain text, blocks payload) of the last dragged selection

    def selection_mime(self) -> QMimeData:
        """The selection as plain text, HTML and Dabireh blocks (tables and objects survive)."""
        source = super().createMimeDataFromSelection()
        mime = QMimeData()
        if source.hasText():
            mime.setText(source.text().replace(OBJECT_CHAR, ""))
        if source.hasHtml():
            mime.setHtml(source.html())
        if self.textCursor().hasSelection():
            self.add_blocks_to_mime(mime, self.blocks_mime())
        return mime

    def copy(self) -> None:
        if self.textCursor().hasSelection():
            QGuiApplication.clipboard().setMimeData(self.selection_mime())  # the clipboard takes ownership

    def cut(self) -> None:
        if self.textCursor().hasSelection() and not self.isReadOnly():
            self.copy()
            self.textCursor().removeSelectedText()

    def createMimeDataFromSelection(self) -> QMimeData:  # noqa: N802
        """Used by Qt for drag and drop.

        Qt's mime object ignores extra formats, so the blocks of the dragged
        selection are remembered here and matched again in ``insertFromMimeData``.
        """
        mime = super().createMimeDataFromSelection()
        if self.textCursor().hasSelection():
            RichTextEditor._drag_stash = (mime.text(), self.blocks_mime())
        return mime

    def canInsertFromMimeData(self, source: QMimeData) -> bool:  # noqa: N802
        return source.hasFormat(MIME_BLOCKS) or source.hasImage() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source: QMimeData) -> None:  # noqa: N802
        """Paste through the document model.

        Content copied from Dabireh keeps everything (tables, images, shapes,
        equations).  Other rich content is reduced to what the model stores:
        styled paragraphs, lists and tables; a bitmap on the clipboard becomes
        an image.  Images referenced by pasted HTML are not fetched.
        """
        stash = RichTextEditor._drag_stash
        if source.hasFormat(MIME_BLOCKS) and self.paste_blocks_mime(bytes(source.data(MIME_BLOCKS))):
            pass
        elif (stash is not None and source.hasText() and source.text() == stash[0]
              and self.paste_blocks_mime(stash[1].encode("utf-8"))):
            pass
        elif source.hasImage() and not source.hasHtml() and self.paste_image(source.imageData()):
            pass
        elif source.hasHtml():
            scratch = QTextDocument()
            scratch.setHtml(source.html())
            self.insert_model_blocks(read_blocks(scratch))
        elif source.hasText():
            self.textCursor().insertText(source.text())
        self.ensureCursorVisible()

    # --------------------------------------------------------------- events
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy()
            return
        if event.matches(QKeySequence.StandardKey.Cut):
            self.cut()
            return
        modifiers = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        if event.key() == Qt.Key.Key_Space and modifiers == Qt.KeyboardModifier.ShiftModifier:
            self.insert_zwnj()  # Persian keyboard convention for the half-space
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and modifiers == Qt.KeyboardModifier.NoModifier:
            block = self.textCursor().block()
            if block.textList() is not None and not block.text() and not self.textCursor().hasSelection():
                formatting.remove_from_list(block)  # Enter on an empty item ends the list
                return
        if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab) and self.textCursor().currentTable() is not None:
            # Tab follows the reading order of the table (right to left in an RTL table).
            table = self.textCursor().currentTable()
            cell = table.cellAt(self.textCursor())
            backward = event.key() == Qt.Key.Key_Backtab
            target = tables.next_cell(table, cell, backward) if cell.isValid() else None
            if target is None and not backward:
                table.appendRows(1)
                target = tables.next_cell(table, cell)
            if target is not None:
                cursor = self.textCursor()
                cursor.setPosition(target.firstPosition())
                self.setTextCursor(cursor)
            return
        super().keyPressEvent(event)

    def _object_position_at(self, event: QMouseEvent) -> int:
        """Document position of the object under the mouse, or -1."""
        cursor = self.cursorForPosition(event.position().toPoint())
        document = self.document()
        for position in (cursor.position(), cursor.position() - 1):
            if position >= 0 and document.characterAt(position) == "\ufffc":
                probe = QTextCursor(document)
                probe.setPosition(position + 1)
                if object_from_format(probe.charFormat()) is not None:
                    return position
        return -1

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        position = self._object_position_at(event)
        if position >= 0:
            cursor = self.textCursor()
            cursor.setPosition(position)
            cursor.setPosition(position + 1, QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(cursor)
            selected = self.selected_object()
            if selected is not None:
                self.objectActivated.emit(*selected)
            return
        if self.in_page_margin(event.position().y()):
            self.marginActivated.emit()
            return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.format_painter_active():
            self.paste_format()
            self.set_format_painter(False)
            self.formatPainted.emit()
        elif event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            href = self.anchorAt(event.position().toPoint())
            if href:
                self.follow_link(href)


def release_clipboard() -> None:
    """Replace clipboard data created by the editor with plain text.

    Mime data created from Python must not outlive the interpreter (Qt would
    delete it after Python has shut down), so this runs when the application
    quits; other programs still receive the copied text.
    """
    app = QGuiApplication.instance()
    if app is None:
        return
    clipboard = QGuiApplication.clipboard()
    mime = clipboard.mimeData()
    # The offscreen platform (tests) never reports ownership; there the clipboard is always ours.
    ours = clipboard.ownsClipboard() or QGuiApplication.platformName() == "offscreen"
    if mime is not None and (ours or mime.hasFormat(MIME_BLOCKS)):
        text = mime.text()
        if text:
            clipboard.setText(text)
        else:
            clipboard.clear()
