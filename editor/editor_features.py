"""Phase 2 editor commands: objects, tables, styles, references, navigation.

Mixed into :class:`editor.text_editor.RichTextEditor`; every command edits the
real QTextDocument inside one undo step.
"""

from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QImage,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)

from core.document import Block, NamedStyle, Paragraph, Table, block_from_dict
from core.styles import NORMAL, builtin_styles
from core.units import pt_to_px
from editor import references, style_commands, tables
from editor.formatting import selected_blocks
from editor.objects import (
    IMAGE_SUFFIXES,
    OBJECT_CHAR,
    image_to_png_bytes,
    insert_object,
    object_from_format,
    without_object,
)
from editor.qt_bridge import insert_blocks, read_blocks, used_resource_keys

MIME_BLOCKS = "application/x-dabireh-blocks"
LINK_COLOR = "#1f5fbf"
_UNDERLINES = {
    "single": QTextCharFormat.UnderlineStyle.SingleUnderline,
    "dash": QTextCharFormat.UnderlineStyle.DashUnderline,
    "dot": QTextCharFormat.UnderlineStyle.DotLine,
    "wave": QTextCharFormat.UnderlineStyle.WaveUnderline,
}


class FeatureMixin:
    """Requires the host class to be a QTextEdit with ``_info`` and ``objects``."""

    # ------------------------------------------------- character formatting
    def set_letter_spacing(self, percent: float) -> None:
        """Character spacing as a percentage of the normal advance (100 = normal)."""
        modifier = QTextCharFormat()
        modifier.setFontLetterSpacingType(QFont.SpacingType.PercentageSpacing)
        modifier.setFontLetterSpacing(min(max(percent, 50.0), 300.0))
        self.mergeCurrentCharFormat(modifier)

    def set_character_scale(self, percent: float) -> None:
        """Horizontal scaling of the glyphs in percent (100 = normal)."""
        modifier = QTextCharFormat()
        modifier.setFontStretch(int(min(max(percent, 50.0), 200.0)))
        self.mergeCurrentCharFormat(modifier)

    def set_underline_style(self, style: str | None) -> None:
        """``style``: "single", "dash", "dot", "wave" or ``None`` to remove the underline."""
        modifier = QTextCharFormat()
        modifier.setUnderlineStyle(_UNDERLINES.get(style or "", QTextCharFormat.UnderlineStyle.NoUnderline))
        self.mergeCurrentCharFormat(modifier)

    # ------------------------------------------------- paragraph formatting
    def set_paragraph_background(self, color: QColor | None) -> None:
        cursor = self.textCursor()
        cursor.beginEditBlock()
        for block in selected_blocks(cursor):
            block_cursor = QTextCursor(block)
            fmt = block_cursor.blockFormat()
            if color is None:
                fmt.clearBackground()
            else:
                fmt.setBackground(QBrush(color))
            block_cursor.setBlockFormat(fmt)
        cursor.endEditBlock()

    def set_page_break_before(self, enabled: bool) -> None:
        cursor = self.textCursor()
        fmt = QTextBlockFormat()
        fmt.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore if enabled
                               else QTextFormat.PageBreakFlag.PageBreak_Auto)
        cursor.mergeBlockFormat(fmt)

    def insert_page_break(self) -> None:
        """Start a new paragraph on a new page."""
        cursor = self.textCursor()
        cursor.beginEditBlock()
        fmt = cursor.blockFormat()
        fmt.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
        cursor.insertBlock(fmt)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def set_hanging_indent(self, points: float) -> None:
        """Hanging indent: every line but the first is indented by ``points``."""
        cursor = self.textCursor()
        cursor.beginEditBlock()
        for block in selected_blocks(cursor):
            block_cursor = QTextCursor(block)
            fmt = block_cursor.blockFormat()
            rtl = block.textDirection() == Qt.LayoutDirection.RightToLeft
            pixels = pt_to_px(max(0.0, points))
            if rtl:
                fmt.setRightMargin(pixels)
            else:
                fmt.setLeftMargin(pixels)
            fmt.setTextIndent(-pixels)
            block_cursor.setBlockFormat(fmt)
        cursor.endEditBlock()

    # --------------------------------------------------------------- styles
    def current_style_name(self) -> str:
        return style_commands.style_name_of(self.textCursor().block()) or NORMAL

    def apply_style(self, name: str) -> bool:
        style = self._info.styles.get(name)
        if style is None:
            return False
        style_commands.apply_named_style(self.textCursor(), style)
        return True

    def save_style(self, style: NamedStyle, old_name: str | None = None) -> None:
        """Create or update a style; paragraphs using it are reformatted."""
        styles = self._info.styles
        if old_name and old_name != style.name and old_name in styles:
            del styles[old_name]
            style_commands.rename_style_in_document(self.document(), old_name, style.name)
        style.paragraph.style_name = "" if style.name == NORMAL else style.name
        styles[style.name] = style
        style_commands.reapply_style(self.document(), style)
        self.document().setModified(True)

    def delete_style(self, name: str) -> bool:
        style = self._info.styles.get(name)
        if style is None or style.builtin:
            return False
        del self._info.styles[name]
        style_commands.rename_style_in_document(self.document(), name, "")
        self.document().setModified(True)
        return True

    def reset_builtin_style(self, name: str) -> None:
        fresh = builtin_styles().get(name)
        if fresh is not None:
            self.save_style(fresh)

    # ------------------------------------------------------- format painter
    def copy_format(self) -> None:
        self._copied_format = style_commands.copy_format(self.textCursor())

    def has_copied_format(self) -> bool:
        return getattr(self, "_copied_format", None) is not None

    def paste_format(self) -> bool:
        copied = getattr(self, "_copied_format", None)
        if copied is None:
            return False
        style_commands.paste_format(self.textCursor(), copied)
        return True

    def set_format_painter(self, active: bool) -> None:
        """While active, the next mouse selection receives the copied format."""
        if active:
            self.copy_format()
        self._painter_armed = active
        self.viewport().setCursor(Qt.CursorShape.CrossCursor if active else Qt.CursorShape.IBeamCursor)

    def format_painter_active(self) -> bool:
        return bool(getattr(self, "_painter_armed", False))

    # -------------------------------------------------------------- objects
    def insert_object(self, obj: dict[str, Any]) -> None:
        cursor = self.textCursor()
        cursor.beginEditBlock()
        base = QTextCharFormat(cursor.charFormat())
        for prop in (QTextFormat.Property.ObjectType,):
            base.clearProperty(prop)
        base = without_object(base)
        insert_object(cursor, obj, base)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.setCurrentCharFormat(base)
        self.ensureCursorVisible()

    def selected_object(self) -> tuple[int, dict[str, Any]] | None:
        """(position, object) of the selected object or the one next to the cursor."""
        cursor = self.textCursor()
        document = self.document()
        if cursor.hasSelection():
            candidates = [cursor.selectionStart()] if cursor.selectionEnd() - cursor.selectionStart() == 1 else []
        else:
            candidates = [cursor.position() - 1, cursor.position()]
        for position in candidates:
            if position >= 0 and document.characterAt(position) == OBJECT_CHAR:
                probe = QTextCursor(document)
                probe.setPosition(position + 1)
                obj = object_from_format(probe.charFormat())
                if obj is not None:
                    return position, obj
        return None

    def replace_object(self, position: int, obj: dict[str, Any]) -> None:
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        cursor.setPosition(position)
        cursor.setPosition(position + 1, QTextCursor.MoveMode.KeepAnchor)
        base = QTextCharFormat(cursor.charFormat())
        for prop in (QTextFormat.Property.ObjectType, QTextFormat.Property.ImageName,
                     QTextFormat.Property.ImageWidth, QTextFormat.Property.ImageHeight,
                     QTextFormat.Property.TextVerticalAlignment):
            base.clearProperty(prop)
        cursor.removeSelectedText()
        is_separate_object = ((obj.get("type") == "image" and obj.get("wrap") == "block") or
                          (obj.get("type") == "shape" and obj.get("layout_canvas") is True))
        text_format = QTextBlockFormat(cursor.blockFormat())
        if is_separate_object:
            # Give the object its own paragraph, preserving surrounding text.
            block = cursor.block()
            before = cursor.position() > block.position()
            after = cursor.position() < block.position() + block.length() - 1
            if before:
                cursor.insertBlock()
            if after:
                cursor.insertBlock()
                cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            if cursor.currentList():
                cursor.currentList().remove(cursor.block())
            fmt = cursor.blockFormat()
            align = obj.get("block_alignment", "center")
            fmt.setAlignment({"left": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute,
                              "right": Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute,
                              "center": Qt.AlignmentFlag.AlignHCenter}.get(align, Qt.AlignmentFlag.AlignHCenter))
            fmt.setTextIndent(0)
            cursor.setBlockFormat(fmt)
        insert_object(cursor, obj, base)
        if is_separate_object:
            # Continue typing in a separate paragraph rather than next to the object.
            next_block = cursor.block().next()
            next_cursor = QTextCursor(next_block) if next_block.isValid() else None
            if next_cursor is not None and next_cursor.currentFrame() == cursor.currentFrame():
                cursor.setPosition(next_block.position())
            else:
                cursor.insertBlock(text_format, without_object(base))
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def insert_layout_canvas(self, obj: dict[str, Any]) -> None:
        """Insert the canvas as a separate paragraph in a single undo step."""
        cursor = self.textCursor()
        cursor.beginEditBlock()
        self.insert_object(obj)
        position = self.textCursor().position() - 1
        self.replace_object(position, obj)
        cursor.endEditBlock()

    def prepare_image_data(self, data: bytes, suffix: str, max_width: float | None = None) -> dict[str, Any] | None:
        suffix = suffix.lower().lstrip(".")
        if suffix not in IMAGE_SUFFIXES:
            return None
        handler = self.objects
        key = handler.add_resource(data, suffix)
        if not handler.is_svg(key) and handler.image(key).isNull():
            handler.resources.pop(key, None)
            return None
        if handler.is_svg(key) and not handler.svg(key).isValid():
            handler.resources.pop(key, None)
            return None
        natural = handler.natural_size(key)
        geometry = self.page_geometry
        limit = max(1.0, max_width if max_width is not None else geometry.content_width - 12)
        height_limit = max(1.0, geometry.content_height - 24)
        scale = min(1.0, limit / max(1.0, natural.width()), height_limit / max(1.0, natural.height()))
        obj = {"type": "image", "resource": key, "width": round(natural.width() * scale, 1),
               "height": round(natural.height() * scale, 1), "rotation": 0, "crop": [0, 0, 0, 0],
               "border_width": 0, "border_color": "#000000", "wrap": "inline"}
        return obj

    def insert_image_data(self, data: bytes, suffix: str, max_width: float | None = None) -> dict[str, Any] | None:
        obj = self.prepare_image_data(data, suffix, max_width)
        if obj is not None:
            self.insert_object(obj)
        return obj

    def insert_image_file(self, path: Path | str) -> dict[str, Any] | None:
        path = Path(path)
        try:
            data = path.read_bytes()
        except OSError:
            return None
        return self.insert_image_data(data, path.suffix)

    def insert_equation(self, latex: str, *, display: bool = False, numbered: bool = False) -> None:
        obj = {"type": "equation", "latex": latex, "display": display, "numbered": bool(display and numbered)}
        if display:
            cursor = self.textCursor()
            cursor.beginEditBlock()
            if cursor.block().text().strip(OBJECT_CHAR + " "):
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                cursor.insertBlock()
            fmt = cursor.blockFormat()
            fmt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            fmt.setTextIndent(0)
            cursor.setBlockFormat(fmt)
            self.setTextCursor(cursor)
            self.insert_object(obj)
            cursor.endEditBlock()
        else:
            self.insert_object(obj)

    def group_selected_shapes(self) -> bool:
        """Combine the selected shapes (a selection made only of shapes) into one group."""
        cursor = self.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        if end - start < 2:
            return False
        shapes: list[dict[str, Any]] = []
        probe = QTextCursor(self.document())
        for position in range(start, end):
            if self.document().characterAt(position) != OBJECT_CHAR:
                return False
            probe.setPosition(position + 1)
            obj = object_from_format(probe.charFormat())
            if obj is None or obj.get("type") != "shape":
                return False
            shapes.append(obj)
        width = sum(float(s.get("width", 100)) for s in shapes)
        height = max(float(s.get("height", 100)) for s in shapes)
        children, x = [], 0.0
        for shape in shapes:
            w, h = float(shape.get("width", 100)), float(shape.get("height", 100))
            children.append(dict(shape, x=x / width, y=(height - h) / 2 / height, w=w / width, h=h / height))
            x += w
        group = {"type": "shape", "kind": "group", "width": width, "height": height, "rotation": 0,
                 "opacity": 1.0, "children": children}
        cursor.beginEditBlock()
        cursor.removeSelectedText()
        insert_object(cursor, group, None)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    def ungroup_shape(self) -> bool:
        selected = self.selected_object()
        if selected is None or selected[1].get("kind") != "group":
            return False
        position, group = selected
        width, height = float(group.get("width", 100)), float(group.get("height", 100))
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        cursor.setPosition(position)
        cursor.setPosition(position + 1, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        for child in group.get("children", []):
            shape = {k: v for k, v in child.items() if k not in ("x", "y", "w", "h")}
            shape["width"] = round(float(child.get("w", 1)) * width, 1)
            shape["height"] = round(float(child.get("h", 1)) * height, 1)
            insert_object(cursor, shape, None)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    def reorder_group(self, to_front: bool) -> bool:
        """Change the drawing order inside the selected group (last child is drawn on top)."""
        selected = self.selected_object()
        if selected is None or selected[1].get("kind") != "group":
            return False
        position, group = selected
        children = list(group.get("children", []))
        if len(children) < 2:
            return False
        children = children[1:] + children[:1] if to_front else children[-1:] + children[:-1]
        self.replace_object(position, dict(group, children=children))
        return True

    # --------------------------------------------------------------- tables
    def insert_table(self, rows: int, columns: int, *, header_rows: int = 0, direction: str | None = None) -> None:
        cursor = self.textCursor()
        direction = direction or ("ltr" if self._info.defaults.direction == "ltr" else "rtl")
        tables.insert_table(cursor, tables.new_table(rows, columns, header_rows=header_rows, direction=direction))
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def in_table(self) -> bool:
        return self.textCursor().currentTable() is not None

    def table_command(self, name: str, *args: Any) -> bool:
        """Run a command from ``editor.tables`` on the current cursor."""
        commands = {
            "row_above": lambda c: tables.insert_row(c, after=False),
            "row_below": lambda c: tables.insert_row(c, after=True),
            "column_before": lambda c: tables.insert_column(c, after=False),
            "column_after": lambda c: tables.insert_column(c, after=True),
            "remove_rows": tables.remove_rows,
            "remove_columns": tables.remove_columns,
            "delete_table": tables.delete_table,
            "merge": tables.merge_cells,
            "split": tables.split_cell,
            "cell_background": tables.set_cell_background,
            "cell_valign": tables.set_cell_vertical_alignment,
            "cell_align": tables.set_cell_alignment,
        }
        cursor = self.textCursor()
        cursor.beginEditBlock()
        try:
            return bool(commands[name](cursor, *args))
        finally:
            cursor.endEditBlock()

    def table_properties(self) -> Table | None:
        table = self.textCursor().currentTable()
        return tables.table_model(table) if table is not None else None

    def set_table_properties(self, properties: Table) -> bool:
        table = self.textCursor().currentTable()
        if table is None:
            return False
        cursor = self.textCursor()
        cursor.beginEditBlock()
        tables.apply_table_properties(table, properties)
        cursor.endEditBlock()
        return True

    # ----------------------------------------------------------- references
    @property
    def number_digits(self) -> str:
        return "latin" if self._info.header_footer.number_format == "latin" else "persian"

    def insert_caption(self, kind: str, text: str) -> None:
        """Insert a numbered caption paragraph below the current paragraph or table."""
        cursor = self.textCursor()
        cursor.beginEditBlock()
        table = cursor.currentTable()
        if table is not None:
            cursor.setPosition(table.lastPosition() + 1)
            if cursor.block().text():
                cursor.insertBlock()
                cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
        else:
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cursor.insertBlock()
        number = references.next_caption_number(self.document(), kind, cursor.block().position())
        cursor.insertText(references.caption_text(kind, number, text, self.number_digits), QTextCharFormat())
        self.setTextCursor(cursor)
        self.apply_style("Caption")
        references.renumber_captions(self.document(), self.number_digits)
        cursor.endEditBlock()

    def insert_generated_list(self, role: str) -> None:
        """Insert or refresh the table of contents ("toc"), figures ("lof") or tables ("lot")."""
        cursor = self.textCursor()
        cursor.beginEditBlock()
        references.insert_generated_list(cursor, self._info.styles, role, self.number_digits)
        cursor.endEditBlock()

    def insert_note(self, text: str) -> None:
        cursor = self.textCursor()
        cursor.beginEditBlock()
        self.insert_object({"type": "note", "text": text})
        position = self.textCursor().position()
        references.update_notes_section(self.document(), self.number_digits)
        cursor.endEditBlock()
        restored = self.textCursor()
        restored.setPosition(min(position, self.document().characterCount() - 1))
        self.setTextCursor(restored)

    def update_fields(self) -> dict[str, int]:
        """Refresh caption numbers, notes and generated lists."""
        cursor = self.textCursor()
        cursor.beginEditBlock()
        result = {
            "captions": references.renumber_captions(self.document(), self.number_digits),
            "notes": references.update_notes_section(self.document(), self.number_digits),
            "lists": references.update_generated_lists(self.document(), self._info.styles, self.number_digits),
        }
        cursor.endEditBlock()
        return result

    def set_hyperlink(self, target: str, text: str = "") -> bool:
        """Turn the selection into a link (or insert ``text`` as a link)."""
        cursor = self.textCursor()
        if not target or (not cursor.hasSelection() and not text):
            return False
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(target)
        fmt.setForeground(QBrush(QColor(LINK_COLOR)))
        fmt.setFontUnderline(True)
        cursor.beginEditBlock()
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            following = QTextCharFormat(cursor.charFormat())
            merged = QTextCharFormat(following)
            merged.merge(fmt)
            cursor.insertText(text, merged)
            cursor.setCharFormat(following)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    def remove_hyperlink(self) -> bool:
        cursor = self.textCursor()
        if not cursor.hasSelection():
            if not cursor.charFormat().isAnchor():
                return False
            href = cursor.charFormat().anchorHref()
            block = cursor.block()
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.contains(max(block.position(), cursor.position() - 1)) and \
                        fragment.charFormat().anchorHref() == href:
                    cursor.setPosition(fragment.position())
                    cursor.setPosition(fragment.position() + fragment.length(), QTextCursor.MoveMode.KeepAnchor)
                iterator += 1
        if not cursor.hasSelection():
            return False
        fmt = QTextCharFormat()
        fmt.setAnchorHref("")
        fmt.setForeground(QBrush(Qt.BrushStyle.NoBrush))
        fmt.setFontUnderline(False)
        names = cursor.charFormat().anchorNames()
        fmt.setAnchor(bool(names))
        cursor.mergeCharFormat(fmt)
        return True

    def add_bookmark(self, name: str) -> bool:
        name = name.strip().replace(" ", "_")
        cursor = self.textCursor()
        if not name or name in references.bookmarks(self.document()):
            return False
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        if not cursor.hasSelection():
            return False
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorNames([name])
        cursor.mergeCharFormat(fmt)
        return True

    def bookmarks(self) -> list[str]:
        return references.bookmarks(self.document())

    def go_to_bookmark(self, name: str) -> bool:
        position = references.find_bookmark(self.document(), name)
        if position < 0:
            return False
        cursor = self.textCursor()
        cursor.setPosition(position)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        return True

    def reference_targets(self) -> list[tuple[str, str, Any]]:
        """(kind, label, block-or-name) of everything a cross-reference can point to."""
        targets: list[tuple[str, str, Any]] = []
        for entry in references.headings(self.document(), self._info.styles):
            targets.append(("heading", entry.text, entry.block))
        for entry in references.captions(self.document()):
            targets.append((entry.kind, entry.text, entry.block))
        for name in references.bookmarks(self.document()):
            targets.append(("bookmark", name, name))
        return targets

    def insert_cross_reference(self, kind: str, label: str, target: Any, *, with_page: bool = False) -> None:
        """Insert a link to a heading, caption or bookmark.

        The inserted text is a snapshot (heading text, "شکل ۲", or the page
        number); it is not refreshed automatically when the target changes.
        """
        cursor = self.textCursor()
        cursor.beginEditBlock()
        if kind == "bookmark":
            name = str(target)
            position = references.find_bookmark(self.document(), name)
            block = self.document().findBlock(max(0, position))
            text = label
        else:
            block = target
            name = references.ensure_block_bookmark(block)
            text = label.split(":", 1)[0].strip() if kind in ("figure", "table") else label
        if with_page:
            page = references.page_of_block(self.document(), block)
            text = "صفحهٔ " + references.digits_text(str(page), self.number_digits)
        self.set_hyperlink("#" + name, text)
        cursor.endEditBlock()

    # ----------------------------------------------------------- navigation
    def go_to_page(self, page: int) -> None:
        page = min(max(1, page), self.page_count())
        geometry = self.page_geometry
        self.verticalScrollBar().setValue(int((page - 1) * geometry.height))
        cursor = self.cursorForPosition(self.viewport().rect().topLeft())
        hit = self.document().documentLayout().hitTest(
            QPointF(geometry.width / 2, (page - 1) * geometry.height + geometry.margin_top + 4),
            Qt.HitTestAccuracy.FuzzyHit)
        if hit >= 0:
            cursor.setPosition(hit)
        self.setTextCursor(cursor)
        self.verticalScrollBar().setValue(int((page - 1) * geometry.height))

    def follow_link(self, href: str) -> bool:
        if href.startswith("#"):
            return self.go_to_bookmark(href[1:])
        return QDesktopServices.openUrl(QUrl(href))

    # ------------------------------------------------------------ clipboard
    def selection_blocks(self) -> tuple[list[Block], dict[str, str]]:
        """Model blocks (and the image resources they use) for the current selection."""
        scratch = QTextDocument()
        QTextCursor(scratch).insertFragment(self.textCursor().selection())
        blocks = read_blocks(scratch)
        return blocks, self.objects.used_resources(used_resource_keys(blocks))

    def blocks_mime(self) -> str:
        blocks, resources = self.selection_blocks()
        return json.dumps({"blocks": [block.to_dict() for block in blocks], "resources": resources},
                          ensure_ascii=False)

    def insert_model_blocks(self, blocks: list[Block], resources: dict[str, str] | None = None) -> None:
        """Insert model blocks at the cursor (used by paste, import and templates)."""
        for key, value in (resources or {}).items():
            self.objects.resources.setdefault(key, value)
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.removeSelectedText()
        only_inline = len(blocks) == 1 and isinstance(blocks[0], Paragraph)
        inline = only_inline or not (cursor.block().length() <= 1)
        if isinstance(blocks[0], Table):
            inline = False
        insert_blocks(cursor, copy.deepcopy(blocks), inline_first=inline)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def paste_blocks_mime(self, payload: bytes) -> bool:
        try:
            data = json.loads(payload.decode("utf-8"))
            blocks = [block_from_dict(item) for item in data.get("blocks", [])]
        except (ValueError, AttributeError, TypeError):
            return False
        if not blocks:
            return False
        resources = data.get("resources") if isinstance(data.get("resources"), dict) else {}
        self.insert_model_blocks(blocks, resources)
        return True

    def paste_image(self, image: QImage) -> bool:
        if image.isNull():
            return False
        return self.insert_image_data(image_to_png_bytes(image), "png") is not None

    @staticmethod
    def add_blocks_to_mime(mime: QMimeData, payload: str) -> None:
        mime.setData(MIME_BLOCKS, payload.encode("utf-8"))

    @staticmethod
    def image_bytes_base64(data: bytes) -> str:
        return base64.b64encode(data).decode("ascii")
