"""DOCX import: paragraphs, character/paragraph formatting, lists, tables,
inline images, hyperlinks, footnotes, equations, page settings and
header/footer text are mapped onto the Dabireh document model.

Unsupported content (text boxes, floating drawings, tracked changes, section
changes inside the document, SmartArt, …) is skipped; the text of every
ordinary paragraph and table cell is always kept.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any

from docx import Document as open_docx
from docx.oxml.ns import qn
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph

from core.document import (
    Block,
    CharStyle,
    Document,
    HeaderFooter,
    ListInfo,
    Metadata,
    PageSettings,
    Paragraph,
    ParagraphStyle,
    Table,
    TableCell,
    TextRun,
)
from core.equation import is_valid, omml_to_latex
from core.pagination import PAGE_SIZES_MM
from core.styles import builtin_styles

EMU_PER_PX = 9525
EMU_PER_MM = 36000
_M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_STYLE_NAMES = {"title": "Title", "subtitle": "Subtitle", "heading 1": "Heading 1", "heading 2": "Heading 2",
                "heading 3": "Heading 3", "quote": "Quote", "intense quote": "Quote", "caption": "Caption"}
_FIELD_NAMES = {"PAGE": "{page}", "NUMPAGES": "{pages}", "DATE": "{date}", "TIME": "{time}", "TITLE": "{title}"}
_UNDERLINES = {"dash": "dash", "dashLong": "dash", "dotted": "dot", "dotDash": "dash", "wave": "wave",
               "wavyDouble": "wave"}


class _Fields(dict):
    """Mutable copy of a frozen CharStyle's fields."""


class DocxImportError(OSError):
    """The file is not a readable .docx document."""


def _val(element, default: str | None = None) -> str | None:  # noqa: ANN001
    return element.get(qn("w:val"), default) if element is not None else default


def _on(element) -> bool:  # noqa: ANN001
    return element is not None and _val(element, "1") not in ("0", "false", "off")


def _twips(value: str | None) -> float:
    try:
        return int(value or 0) / 20.0
    except ValueError:
        return 0.0


class _Importer:
    def __init__(self, path: Path) -> None:
        try:
            self.docx = open_docx(str(path))
        except Exception as error:  # python-docx raises several unrelated types
            raise DocxImportError("این پرونده یک سند Word خوانا نیست.") from error
        self.resources: dict[str, str] = {}
        self.builtin = builtin_styles()
        self.list_ids: dict[str, int] = {}
        self.footnotes = self._read_footnotes()
        self.numbering = self._read_numbering()

    # ---------------------------------------------------------------- parts
    def _read_footnotes(self) -> dict[str, str]:
        notes: dict[str, str] = {}
        for relation in self.docx.part.rels.values():
            if relation.reltype.endswith("/footnotes") or relation.reltype.endswith("/endnotes"):
                try:
                    from docx.oxml import parse_xml

                    root = parse_xml(relation.target_part.blob)
                except Exception:  # noqa: BLE001 - a damaged notes part must not stop the import
                    continue
                prefix = "e" if relation.reltype.endswith("/endnotes") else "f"
                for note in root:
                    identifier = note.get(qn("w:id"))
                    text = "".join(t.text or "" for t in note.iter(qn("w:t"))).strip()
                    if identifier and text:
                        notes[prefix + identifier] = text
        return notes

    def _read_numbering(self) -> dict[str, str]:
        """numId -> "bullet" | "number" (first level of the abstract definition)."""
        result: dict[str, str] = {}
        try:
            root = self.docx.part.numbering_part.element
        except (KeyError, NotImplementedError, AttributeError):
            return result
        abstract: dict[str, str] = {}
        for definition in root.findall(qn("w:abstractNum")):
            level = definition.find(qn("w:lvl"))
            fmt = _val(level.find(qn("w:numFmt"))) if level is not None else None
            abstract[definition.get(qn("w:abstractNumId"))] = "bullet" if fmt == "bullet" else "number"
        for num in root.findall(qn("w:num")):
            reference = _val(num.find(qn("w:abstractNumId")))
            if reference in abstract:
                result[num.get(qn("w:numId"))] = abstract[reference]
        return result

    # ----------------------------------------------------------------- runs
    def _char_style(self, r_pr, base: CharStyle) -> CharStyle:  # noqa: ANN001
        style = _Fields(vars(base))
        if r_pr is None:
            return base
        fonts = r_pr.find(qn("w:rFonts"))
        if fonts is not None:
            family = fonts.get(qn("w:cs")) or fonts.get(qn("w:ascii")) or fonts.get(qn("w:hAnsi"))
            if family:
                style["font_family"] = family
        for tag, attribute in (("w:b", "bold"), ("w:i", "italic"), ("w:strike", "strike")):
            element = r_pr.find(qn(tag))
            if element is not None:
                style[attribute] = _on(element)
        size = r_pr.find(qn("w:sz"))
        if size is None:
            size = r_pr.find(qn("w:szCs"))
        if size is not None:
            try:
                style["font_size"] = int(_val(size, "0")) / 2 or None
            except ValueError:
                pass
        color = _val(r_pr.find(qn("w:color")))
        if color and color != "auto" and len(color) == 6:
            style["color"] = "#" + color.lower()
        underline = r_pr.find(qn("w:u"))
        if underline is not None:
            value = _val(underline, "single")
            style["underline"] = value != "none"
            style["underline_style"] = _UNDERLINES.get(value or "")
        shade = r_pr.find(qn("w:shd"))
        fill = shade.get(qn("w:fill")) if shade is not None else None
        if fill and fill != "auto" and len(fill) == 6:
            style["highlight"] = "#" + fill.lower()
        highlight = _val(r_pr.find(qn("w:highlight")))
        if highlight and highlight != "none":
            style["highlight"] = {"yellow": "#ffff00", "green": "#00ff00", "cyan": "#00ffff", "magenta": "#ff00ff",
                               "blue": "#0000ff", "red": "#ff0000", "lightGray": "#d3d3d3",
                               "darkGray": "#a9a9a9"}.get(highlight, "#ffff00")
        vertical = _val(r_pr.find(qn("w:vertAlign")))
        if vertical in ("superscript", "subscript"):
            style["vertical_align"] = "super" if vertical == "superscript" else "sub"
        scale = _val(r_pr.find(qn("w:w")))
        if scale and scale.isdigit() and scale != "100":
            style["stretch"] = float(scale)
        return CharStyle(**style)

    def _image(self, drawing, part) -> dict[str, Any] | None:  # noqa: ANN001
        blip = next(drawing.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip"), None)
        extent = next(drawing.iter("{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent"),
                      None)
        if blip is None:
            return None
        relation = blip.get(qn("r:embed"))
        try:
            image_part = part.related_parts[relation]
        except KeyError:
            return None
        data = image_part.blob
        suffix = Path(str(image_part.partname)).suffix.lower().lstrip(".") or "png"
        if suffix not in ("png", "jpg", "jpeg", "gif", "bmp", "webp", "svg"):
            return None  # e.g. EMF/WMF, which Qt cannot draw
        key = hashlib.sha1(data).hexdigest()[:16] + "." + suffix
        self.resources[key] = base64.b64encode(data).decode("ascii")
        width = int(extent.get("cx", 0)) / EMU_PER_PX if extent is not None else 200
        height = int(extent.get("cy", 0)) / EMU_PER_PX if extent is not None else 150
        return {"type": "image", "resource": key, "width": round(width, 1) or 200, "height": round(height, 1) or 150,
                "rotation": 0, "crop": [0, 0, 0, 0], "border_width": 0, "border_color": "#000000", "wrap": "inline"}

    def _runs(self, container, part, base: CharStyle, link: str | None = None) -> list[TextRun]:  # noqa: ANN001
        runs: list[TextRun] = []

        def add_text(text: str, style: CharStyle) -> None:
            if not text:
                return
            if runs and runs[-1].object is None and runs[-1].style == style:
                runs[-1].text += text
            else:
                runs.append(TextRun(text, style))

        for child in container:
            tag = child.tag
            if tag == qn("w:r"):
                style = self._char_style(child.find(qn("w:rPr")), base)
                if link:
                    style = replace(style, link=link)
                for item in child:
                    if item.tag == qn("w:t"):
                        add_text(item.text or "", style)
                    elif item.tag == qn("w:tab"):
                        add_text("\t", style)
                    elif item.tag in (qn("w:br"), qn("w:cr")):
                        if item.get(qn("w:type")) != "page":
                            add_text("\u2028", style)
                    elif item.tag == qn("w:noBreakHyphen"):
                        add_text("\u2011", style)
                    elif item.tag == qn("w:drawing"):
                        image = self._image(item, part)
                        if image is not None:
                            runs.append(TextRun("", CharStyle(), image))
                    elif item.tag in (qn("w:footnoteReference"), qn("w:endnoteReference")):
                        prefix = "f" if item.tag == qn("w:footnoteReference") else "e"
                        text = self.footnotes.get(prefix + (item.get(qn("w:id")) or ""))
                        if text:
                            runs.append(TextRun("", CharStyle(), {"type": "note", "text": text}))
            elif tag == qn("w:hyperlink"):
                target = None
                relation = child.get(qn("r:id"))
                if relation and relation in part.rels:
                    target = part.rels[relation].target_ref
                elif child.get(qn("w:anchor")):
                    target = "#" + child.get(qn("w:anchor"))
                runs.extend(self._runs(child, part, base, target))
            elif tag == qn("w:fldSimple"):
                runs.extend(self._runs(child, part, base, link))
            elif tag == f"{{{_M_NS}}}oMath":
                runs.extend(self._equation(child, display=False))
            elif tag == f"{{{_M_NS}}}oMathPara":
                for math in child.iter(f"{{{_M_NS}}}oMath"):
                    runs.extend(self._equation(math, display=True))
            elif tag in (qn("w:ins"), qn("w:smartTag"), qn("w:sdt"), qn("w:sdtContent")):
                runs.extend(self._runs(child, part, base, link))
        return runs

    @staticmethod
    def _equation(math, display: bool) -> list[TextRun]:  # noqa: ANN001
        latex = omml_to_latex(math)
        if latex and is_valid(latex):
            return [TextRun("", CharStyle(), {"type": "equation", "latex": latex, "display": display,
                                              "numbered": False})]
        text = "".join(t.text or "" for t in math.iter(f"{{{_M_NS}}}t"))
        return [TextRun(text)] if text else []

    # ----------------------------------------------------------- paragraphs
    def _paragraph(self, paragraph: DocxParagraph) -> Paragraph:
        element = paragraph._p
        p_pr = element.find(qn("w:pPr"))
        try:
            style_name = (paragraph.style.name or "").lower()
        except Exception:  # noqa: BLE001 - missing style definitions
            style_name = ""
        mapped = _STYLE_NAMES.get(style_name, "")
        named = self.builtin.get(mapped)
        base_char = CharStyle(**vars(named.char)) if named else CharStyle()
        style = ParagraphStyle(**vars(named.paragraph)) if named else ParagraphStyle()
        style.style_name = mapped
        list_info = None
        if style_name.startswith("list bullet") or style_name.startswith("list number"):
            kind = "bullet" if "bullet" in style_name else "number"
            level = int(style_name[-1]) if style_name[-1].isdigit() else 1
            list_info = ListInfo(style=kind, level=level, list_id=self.list_ids.setdefault(kind, len(self.list_ids) + 1))
        rtl = False
        if p_pr is not None:
            rtl = _on(p_pr.find(qn("w:bidi")))
            style.direction = "rtl" if rtl else ("ltr" if p_pr.find(qn("w:bidi")) is not None else "auto")
            justification = _val(p_pr.find(qn("w:jc")))
            if justification:
                style.alignment = {"left": "start", "start": "start", "right": "end", "end": "end",
                                   "center": "center", "both": "justify", "distribute": "justify"}.get(
                    justification, "start")
            spacing = p_pr.find(qn("w:spacing"))
            if spacing is not None:
                if spacing.get(qn("w:before")):
                    style.space_before = _twips(spacing.get(qn("w:before")))
                if spacing.get(qn("w:after")):
                    style.space_after = _twips(spacing.get(qn("w:after")))
                if spacing.get(qn("w:line")) and spacing.get(qn("w:lineRule"), "auto") == "auto":
                    style.line_spacing = min(max(int(spacing.get(qn("w:line"))) / 240.0, 0.5), 5.0)
            indent = p_pr.find(qn("w:ind"))
            if indent is not None and list_info is None:
                start = _twips(indent.get(qn("w:start")) or indent.get(qn("w:left")))
                end = _twips(indent.get(qn("w:end")) or indent.get(qn("w:right")))
                style.indent_left, style.indent_right = (end, start) if rtl else (start, end)
                if indent.get(qn("w:hanging")):
                    style.first_line_indent = -_twips(indent.get(qn("w:hanging")))
                elif indent.get(qn("w:firstLine")):
                    style.first_line_indent = _twips(indent.get(qn("w:firstLine")))
            shade = p_pr.find(qn("w:shd"))
            fill = shade.get(qn("w:fill")) if shade is not None else None
            if fill and fill != "auto" and len(fill) == 6:
                style.background = "#" + fill.lower()
            style.page_break_before = _on(p_pr.find(qn("w:pageBreakBefore")))
            num_pr = p_pr.find(qn("w:numPr"))
            if num_pr is not None and list_info is None:
                num_id = _val(num_pr.find(qn("w:numId")))
                if num_id and num_id != "0":
                    level = int(_val(num_pr.find(qn("w:ilvl")), "0") or 0) + 1
                    list_info = ListInfo(style=self.numbering.get(num_id, "bullet"), level=level,
                                         list_id=self.list_ids.setdefault("n" + num_id, len(self.list_ids) + 1))
        if any(br.get(qn("w:type")) == "page" for br in element.iter(qn("w:br"))):
            style.page_break_before = True
        return Paragraph(runs=self._runs(element, paragraph.part, base_char), style=style, list=list_info)

    # --------------------------------------------------------------- tables
    def _table(self, table: DocxTable) -> Table:
        tbl = table._tbl
        table_pr = tbl.tblPr
        rtl = table_pr is not None and _on(table_pr.find(qn("w:bidiVisual")))
        grid: list[list[TableCell | None]] = []
        anchors: dict[int, tuple[int, int]] = {}  # column -> (row, column) of an open vertical merge
        header_rows = 0
        for row_index, row in enumerate(tbl.findall(qn("w:tr"))):
            tr_pr = row.find(qn("w:trPr"))
            if tr_pr is not None and _on(tr_pr.find(qn("w:tblHeader"))) and header_rows == row_index:
                header_rows += 1
            cells: list[TableCell | None] = []
            column = 0
            for tc in row.findall(qn("w:tc")):
                tc_pr = tc.find(qn("w:tcPr"))
                span = 1
                merge = None
                background = None
                vertical = "top"
                if tc_pr is not None:
                    span = max(1, int(_val(tc_pr.find(qn("w:gridSpan")), "1") or 1))
                    merge_element = tc_pr.find(qn("w:vMerge"))
                    if merge_element is not None:
                        merge = _val(merge_element, "continue")
                    shade = tc_pr.find(qn("w:shd"))
                    fill = shade.get(qn("w:fill")) if shade is not None else None
                    if fill and fill != "auto" and len(fill) == 6:
                        background = "#" + fill.lower()
                    vertical = {"center": "middle", "bottom": "bottom"}.get(_val(tc_pr.find(qn("w:vAlign"))) or "",
                                                                             "top")
                if merge == "continue" and column in anchors:
                    anchor_row, anchor_column = anchors[column]
                    anchor = grid[anchor_row][anchor_column]
                    if anchor is not None:
                        anchor.row_span = row_index - anchor_row + 1
                    cells.extend([None] * span)
                else:
                    blocks = [self._paragraph(DocxParagraph(p, table)) for p in tc.findall(qn("w:p"))]
                    for nested in tc.findall(qn("w:tbl")):  # nested tables are flattened to their text
                        for paragraph in nested.iter(qn("w:p")):
                            blocks.append(self._paragraph(DocxParagraph(paragraph, table)))
                    cells.append(TableCell(blocks=blocks or [Paragraph()], col_span=span, background=background,
                                           vertical_align=vertical))
                    cells.extend([None] * (span - 1))
                    if merge == "restart":
                        anchors[column] = (row_index, column)
                    else:
                        anchors.pop(column, None)
                column += span
            grid.append(cells)
        width = max((len(row) for row in grid), default=0)
        for row in grid:
            while len(row) < width:
                row.append(TableCell())
        borders = table_pr.find(qn("w:tblBorders")) if table_pr is not None else None
        try:
            styled = table.style is not None and "grid" in (table.style.name or "").lower()
        except Exception:  # noqa: BLE001
            styled = False
        alignment = {"center": "center", "right": "end", "end": "end"}.get(
            _val(table_pr.find(qn("w:jc"))) if table_pr is not None else "", "start")
        return Table(rows=grid, header_rows=min(header_rows, max(0, len(grid) - 1)),
                     direction="rtl" if rtl else "ltr", alignment=alignment,
                     border_width=1.0 if (borders is not None or styled) else 0.0)

    # ------------------------------------------------------------- document
    def _page(self) -> PageSettings:
        section = self.docx.sections[0]
        width = (section.page_width or 7560310) / EMU_PER_MM
        height = (section.page_height or 10692130) / EMU_PER_MM
        landscape = width > height
        short, long = sorted((width, height))
        size = "Custom"
        for name, (w, h) in PAGE_SIZES_MM.items():
            if abs(short - w) < 1.5 and abs(long - h) < 1.5:
                size = name
        page = PageSettings(size=size, orientation="landscape" if landscape else "portrait")
        page.custom_width, page.custom_height = round(short, 1), round(long, 1)
        for attribute, value in (("margin_top", section.top_margin), ("margin_bottom", section.bottom_margin),
                                 ("margin_left", section.left_margin), ("margin_right", section.right_margin)):
            if value is not None:
                setattr(page, attribute, round(min(max(value / EMU_PER_MM, 0.0), 100.0), 1))
        return page

    @staticmethod
    def _template(part) -> str:  # noqa: ANN001
        """Header/footer text with Word fields turned into Dabireh fields."""
        lines: list[str] = []
        for paragraph in part.paragraphs:
            pieces: list[str] = []
            skipping = False
            for node in paragraph._p.iter():
                if node.tag == qn("w:fldSimple"):
                    code = (node.get(qn("w:instr")) or "").split()
                    pieces.append(_FIELD_NAMES.get(code[0].upper() if code else "", ""))
                    for text in node.iter(qn("w:t")):
                        text.text = ""  # the cached field result is not literal text
                elif node.tag == qn("w:instrText"):
                    code = (node.text or "").split()
                    pieces.append(_FIELD_NAMES.get(code[0].upper() if code else "", ""))
                elif node.tag == qn("w:fldChar"):
                    kind = node.get(qn("w:fldCharType"))
                    skipping = kind == "separate" or (skipping and kind != "end")
                elif node.tag == qn("w:t") and not skipping:
                    pieces.append(node.text or "")
            if "".join(pieces).strip():
                lines.append("".join(pieces).strip())
        return " ".join(lines)

    def _header_footer(self) -> HeaderFooter:
        section = self.docx.sections[0]
        result = HeaderFooter()
        try:
            if not section.header.is_linked_to_previous:
                result.header = self._template(section.header)
            if not section.footer.is_linked_to_previous:
                result.footer = self._template(section.footer)
            if section.different_first_page_header_footer:
                result.different_first = True
                result.first_header = self._template(section.first_page_header)
                result.first_footer = self._template(section.first_page_footer)
            if self.docx.settings.odd_and_even_pages_header_footer:
                result.different_odd_even = True
                result.even_header = self._template(section.even_page_header)
                result.even_footer = self._template(section.even_page_footer)
        except Exception:  # noqa: BLE001 - a broken header part must not stop the import
            pass
        return result

    def build(self, template: Document | None) -> Document:
        blocks: list[Block] = []
        body = self.docx.element.body
        for child in body:
            if child.tag == qn("w:p"):
                blocks.append(self._paragraph(DocxParagraph(child, self.docx)))
            elif child.tag == qn("w:tbl"):
                blocks.append(self._table(DocxTable(child, self.docx)))
        base = template or Document()
        properties = self.docx.core_properties
        document = Document(
            metadata=Metadata(title=properties.title or "", author=properties.author or ""),
            page=self._page(),
            defaults=type(base.defaults)(**vars(base.defaults)),
            blocks=blocks or [Paragraph()],
            header_footer=self._header_footer(),
            resources=self.resources,
        )
        rtl_votes = sum(1 for p in document.iter_paragraphs() if p.style.direction == "rtl")
        ltr_votes = sum(1 for p in document.iter_paragraphs() if p.style.direction != "rtl" and p.text.strip())
        document.defaults.direction = "rtl" if rtl_votes >= ltr_votes else "ltr"
        return document


def import_docx(path: Path | str, template: Document | None = None) -> Document:
    """Read a .docx file into a document model."""
    return _Importer(Path(path)).build(template)
