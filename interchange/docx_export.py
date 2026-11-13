"""DOCX export built on python-docx plus the OOXML details it lacks
(right-to-left runs and paragraphs, complex-script fonts, fields, Office Math).

The module is Qt-free: objects that need rasterising (shapes, cropped or
rotated images, SVG/WebP) are rendered by the ``render_object`` callback.
"""

from __future__ import annotations

import base64
import io
from collections.abc import Callable
from pathlib import Path
from typing import Any

from docx import Document as new_docx
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_BREAK
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Emu, Mm, Pt

from core import bidi
from core.document import Document, HeaderFooter, Paragraph, Table, TextRun
from core.equation import EquationError, to_omml
from core.fields import format_page_number
from core.pagination import page_size_mm

RenderObject = Callable[[dict[str, Any]], tuple[bytes, float, float]]  # -> (png bytes, width px, height px)
EMU_PER_PX = 9525
DIRECT_IMAGE_SUFFIXES = ("png", "jpg", "jpeg", "gif", "bmp")
STYLE_MAP = {"Title": "Title", "Subtitle": "Subtitle", "Heading 1": "Heading 1", "Heading 2": "Heading 2",
             "Heading 3": "Heading 3", "Quote": "Quote", "Caption": "Caption"}
_UNDERLINE = {"dash": "dash", "dot": "dotted", "wave": "wave"}
_FIELD_CODES = {"{page}": "PAGE", "{pages}": "NUMPAGES", "{date}": "DATE", "{time}": "TIME"}
_NUMBER_FORMATS = {"persian": "hindiNumbers", "latin": "decimal", "roman": "lowerRoman"}


def _child(parent, tag: str, **attributes: str):  # noqa: ANN001, ANN202
    element = OxmlElement(tag)
    for key, value in attributes.items():
        element.set(qn("w:" + key), value)
    parent.append(element)
    return element


def _has_rtl(text: str) -> bool:
    return any(bidi.first_strong_direction(char) == bidi.Direction.RTL for char in text)


class _Exporter:
    def __init__(self, document: Document, render_object: RenderObject | None) -> None:
        self.model = document
        self.render_object = render_object
        self.docx = new_docx()
        self.default_rtl = document.defaults.direction != "ltr"
        self.note_count = 0
        self.equation_count = 0
        self.bookmark_id = 0
        self.digits = "latin" if document.header_footer.number_format == "latin" else "persian"

    # ------------------------------------------------------------- document
    def build(self) -> None:
        self._page_setup()
        self._defaults()
        body = self.docx.element.body
        for paragraph in list(self.docx.paragraphs):
            body.remove(paragraph._p)
        for block in self.model.blocks:
            if isinstance(block, Table):
                self._table(block)
            else:
                self._paragraph(self.docx.add_paragraph(), block)
        self._header_footer(self.model.header_footer)
        properties = self.docx.core_properties
        properties.title = self.model.metadata.title
        properties.author = self.model.metadata.author

    def _page_setup(self) -> None:
        page = self.model.page
        section = self.docx.sections[0]
        width, height = page_size_mm(page)
        section.orientation = WD_ORIENT.LANDSCAPE if width > height else WD_ORIENT.PORTRAIT
        section.page_width, section.page_height = Mm(width), Mm(height)
        section.top_margin, section.bottom_margin = Mm(page.margin_top), Mm(page.margin_bottom)
        section.left_margin, section.right_margin = Mm(page.margin_left), Mm(page.margin_right)
        section.header_distance = Mm(max(5.0, page.margin_top / 2 - 3))
        section.footer_distance = Mm(max(5.0, page.margin_bottom / 2 - 3))
        sect_pr = section._sectPr
        if self.default_rtl:
            _child(sect_pr, "w:bidi")
        if page.border_width > 0:
            borders = OxmlElement("w:pgBorders")
            borders.set(qn("w:offsetFrom"), "page")
            for side in ("top", "left", "bottom", "right"):
                _child(borders, "w:" + side, val="single", sz=str(max(2, round(page.border_width * 8))),
                       space="24", color=page.border_color.lstrip("#").upper())
            # pgBorders must precede the column/grid settings inside sectPr.
            anchor = sect_pr.find(qn("w:cols"))
            if anchor is not None:
                anchor.addprevious(borders)
            else:
                sect_pr.append(borders)
        if page.background.lower() not in ("#ffffff", "#fff"):
            background = OxmlElement("w:background")
            background.set(qn("w:color"), page.background.lstrip("#").upper())
            self.docx.element.insert(0, background)
            _child(self.docx.settings.element, "w:displayBackgroundShape")

    def _defaults(self) -> None:
        defaults = self.model.defaults
        style = self.docx.styles["Normal"]
        run_pr = style.element.get_or_add_rPr()
        fonts = run_pr.find(qn("w:rFonts"))
        if fonts is None:
            fonts = _child(run_pr, "w:rFonts")
        for attribute, family in (("ascii", defaults.latin_font), ("hAnsi", defaults.latin_font),
                                  ("cs", defaults.font_family), ("eastAsia", defaults.latin_font)):
            fonts.set(qn("w:" + attribute), family)
        size = str(round(defaults.font_size * 2))
        for tag in ("w:sz", "w:szCs"):
            element = run_pr.find(qn(tag))
            if element is None:
                element = _child(run_pr, tag)
            element.set(qn("w:val"), size)
        _child(run_pr, "w:lang", bidi="fa-IR")

    # ----------------------------------------------------------- paragraphs
    def _is_rtl(self, paragraph: Paragraph) -> bool:
        direction = paragraph.style.direction
        if direction == "auto":
            resolved = bidi.first_strong_direction(paragraph.text)
            if resolved == bidi.Direction.RTL:
                return True
            if resolved == bidi.Direction.LTR:
                return False
            return self.default_rtl
        return direction == "rtl"

    def _paragraph(self, target, paragraph: Paragraph) -> None:  # noqa: ANN001
        style = paragraph.style
        rtl = self._is_rtl(paragraph)
        word_style = STYLE_MAP.get(style.style_name)
        if paragraph.list is not None:
            base = "List Bullet" if paragraph.list.style in ("bullet", "circle", "square") else "List Number"
            level = min(max(paragraph.list.level, 1), 3)
            word_style = base if level == 1 else f"{base} {level}"
        if word_style:
            try:
                target.style = self.docx.styles[word_style]
            except KeyError:
                pass
        p_pr = target._p.get_or_add_pPr()
        if style.page_break_before:
            _child(p_pr, "w:pageBreakBefore")
        if rtl:
            _child(p_pr, "w:bidi")
        else:
            _child(p_pr, "w:bidi", val="0")
        if style.background:
            _child(p_pr, "w:shd", val="clear", color="auto", fill=style.background.lstrip("#").upper())
        _child(p_pr, "w:spacing", before=str(round(style.space_before * 20)), after=str(round(style.space_after * 20)),
               line=str(round(style.line_spacing * 240)), lineRule="auto")
        start, end = (style.indent_right, style.indent_left) if rtl else (style.indent_left, style.indent_right)
        if paragraph.list is None and (start or end or style.first_line_indent):
            indent = _child(p_pr, "w:ind", start=str(round(start * 20)), end=str(round(end * 20)))
            # "left"/"right" are read as start/end by Word for bidi paragraphs; written for older readers.
            indent.set(qn("w:left"), str(round(start * 20)))
            indent.set(qn("w:right"), str(round(end * 20)))
            if style.first_line_indent >= 0:
                indent.set(qn("w:firstLine"), str(round(style.first_line_indent * 20)))
            else:
                indent.set(qn("w:hanging"), str(round(-style.first_line_indent * 20)))
        # In a bidi paragraph Word treats jc=left as "start" (the right side).
        justification = {"start": "left", "end": "right", "center": "center", "justify": "both"}[style.alignment]
        _child(p_pr, "w:jc", val=justification)
        for run in paragraph.runs:
            if run.object is not None:
                self._object(target, run.object, run)
            elif run.text:
                self._text_run(target, run)

    def _text_run(self, paragraph, run: TextRun) -> None:  # noqa: ANN001
        style = run.style
        parent = paragraph._p
        if style.link:
            hyperlink = OxmlElement("w:hyperlink")
            if style.link.startswith("#"):
                hyperlink.set(qn("w:anchor"), style.link[1:])
            else:
                relation = paragraph.part.relate_to(style.link, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
                hyperlink.set(qn("r:id"), relation)
            parent.append(hyperlink)
            parent = hyperlink
        if style.bookmark:
            self.bookmark_id += 1
            start = OxmlElement("w:bookmarkStart")
            start.set(qn("w:id"), str(self.bookmark_id))
            start.set(qn("w:name"), style.bookmark)
            parent.append(start)
        pieces = run.text.split("\u2028")
        for index, piece in enumerate(pieces):
            docx_run = paragraph.add_run(piece)
            if parent is not paragraph._p or style.bookmark:
                parent.append(docx_run._r)  # move into the hyperlink / after the bookmark start
            self._run_properties(docx_run, run, piece)
            if index < len(pieces) - 1:
                docx_run.add_break(WD_BREAK.LINE)
        if style.bookmark:
            end = OxmlElement("w:bookmarkEnd")
            end.set(qn("w:id"), str(self.bookmark_id))
            parent.append(end)

    def _run_properties(self, docx_run, run: TextRun, text: str) -> None:  # noqa: ANN001
        style = run.style
        r_pr = docx_run._r.get_or_add_rPr()
        if style.font_family:
            fonts = _child(r_pr, "w:rFonts")
            for attribute in ("ascii", "hAnsi", "cs", "eastAsia"):
                fonts.set(qn("w:" + attribute), style.font_family)
        if style.bold:
            _child(r_pr, "w:b")
            _child(r_pr, "w:bCs")
        if style.italic:
            _child(r_pr, "w:i")
            _child(r_pr, "w:iCs")
        if style.strike:
            _child(r_pr, "w:strike")
        if style.color:
            _child(r_pr, "w:color", val=style.color.lstrip("#").upper())
        size = style.font_size or self.model.defaults.font_size
        if style.letter_spacing and abs(style.letter_spacing - 100) > 0.01:
            _child(r_pr, "w:spacing", val=str(round((style.letter_spacing - 100) / 100 * size * 0.5 * 20)))
        if style.stretch and abs(style.stretch - 100) > 0.01:
            _child(r_pr, "w:w", val=str(round(style.stretch)))
        if style.font_size:
            _child(r_pr, "w:sz", val=str(round(style.font_size * 2)))
            _child(r_pr, "w:szCs", val=str(round(style.font_size * 2)))
        if style.underline:
            _child(r_pr, "w:u", val=_UNDERLINE.get(style.underline_style or "", "single"))
        if style.highlight:
            _child(r_pr, "w:shd", val="clear", color="auto", fill=style.highlight.lstrip("#").upper())
        if style.vertical_align:
            _child(r_pr, "w:vertAlign", val="superscript" if style.vertical_align == "super" else "subscript")
        if _has_rtl(text):
            _child(r_pr, "w:rtl")

    # -------------------------------------------------------------- objects
    def _picture(self, paragraph, data: bytes, width_px: float) -> None:  # noqa: ANN001
        paragraph.add_run().add_picture(io.BytesIO(data), width=Emu(int(width_px * EMU_PER_PX)))

    def _object(self, paragraph, obj: dict[str, Any], run: TextRun) -> None:  # noqa: ANN001
        kind = obj.get("type")
        if kind == "equation":
            self._equation(paragraph, obj)
        elif kind == "note":
            self.note_count += 1
            mark = paragraph.add_run(format_page_number(self.note_count, self.digits))
            mark.font.superscript = True
        elif kind == "image":
            key = str(obj.get("resource", ""))
            suffix = key.rsplit(".", 1)[-1].lower()
            crop = obj.get("crop") or [0, 0, 0, 0]
            plain = (suffix in DIRECT_IMAGE_SUFFIXES and not any(crop) and not obj.get("rotation")
                     and not obj.get("border_width"))
            if plain and key in self.model.resources:
                # The original file is embedded untouched, so no quality is lost.
                self._picture(paragraph, base64.b64decode(self.model.resources[key]), float(obj.get("width", 100)))
            elif self.render_object is not None:
                data, width, _ = self.render_object(obj)
                self._picture(paragraph, data, width)
        elif kind == "shape" and self.render_object is not None:
            data, width, _ = self.render_object(obj)
            self._picture(paragraph, data, width)

    def _equation(self, paragraph, obj: dict[str, Any]) -> None:  # noqa: ANN001
        latex = str(obj.get("latex", ""))
        try:
            math = parse_xml(to_omml(latex))
        except EquationError:
            paragraph.add_run(latex)
            return
        paragraph._p.append(math)
        if obj.get("display") and obj.get("numbered"):
            self.equation_count += 1
            paragraph.add_run(f"\t({format_page_number(self.equation_count, self.digits)})")

    # --------------------------------------------------------------- tables
    def _table(self, table: Table) -> None:
        rows, columns = len(table.rows), table.column_count
        if rows == 0 or columns == 0:
            return
        docx_table = self.docx.add_table(rows=rows, cols=columns)
        if table.border_width > 0:
            docx_table.style = self.docx.styles["Table Grid"]
        table_pr = docx_table._tbl.tblPr
        if table.direction != "ltr":
            _child(table_pr, "w:bidiVisual")  # columns keep their logical order, laid out right to left
        _child(table_pr, "w:tblW", w=str(round(table.width_percent * 50)), type="pct")
        _child(table_pr, "w:jc", val={"start": "left", "center": "center", "end": "right"}[table.alignment])
        margins = _child(table_pr, "w:tblCellMar")
        for side in ("top", "left", "bottom", "right"):
            _child(margins, "w:" + side, w=str(round(table.cell_padding * 15)), type="dxa")
        section = self.docx.sections[0]
        usable = (section.page_width - section.left_margin - section.right_margin) * table.width_percent / 100
        widths = table.column_widths if len(table.column_widths) == columns else [100.0 / columns] * columns
        for r, row in enumerate(table.rows):
            tr_pr = docx_table.rows[r]._tr.get_or_add_trPr()
            _child(tr_pr, "w:cantSplit")  # do not break a row across pages
            if r < table.header_rows:
                _child(tr_pr, "w:tblHeader")  # repeat on every page
            for c, cell in enumerate(row):
                if cell is None:
                    continue
                target = docx_table.cell(r, c)
                if cell.row_span > 1 or cell.col_span > 1:
                    target = target.merge(docx_table.cell(min(rows - 1, r + cell.row_span - 1),
                                                          min(columns - 1, c + cell.col_span - 1)))
                target.width = Emu(int(usable * sum(widths[c:c + cell.col_span]) / 100))
                tc_pr = target._tc.get_or_add_tcPr()
                if cell.background:
                    _child(tc_pr, "w:shd", val="clear", color="auto", fill=cell.background.lstrip("#").upper())
                _child(tc_pr, "w:vAlign", val={"top": "top", "middle": "center", "bottom": "bottom"}[
                    cell.vertical_align])
                for index, block in enumerate(cell.blocks):
                    paragraph = target.paragraphs[0] if index == 0 else target.add_paragraph()
                    self._paragraph(paragraph, block)

    # -------------------------------------------------------- header/footer
    def _field_paragraph(self, paragraph, template: str, align: str, settings: HeaderFooter) -> None:  # noqa: ANN001
        p_pr = paragraph._p.get_or_add_pPr()
        if self.default_rtl:
            _child(p_pr, "w:bidi")
        _child(p_pr, "w:jc", val={"start": "left", "end": "right", "center": "center"}[align])
        template = template.replace("{title}", self.model.metadata.title)
        position = 0
        while position < len(template):
            code = next((key for key in _FIELD_CODES if template.startswith(key, position)), None)
            if code is None:
                following = min((template.find(key, position) for key in _FIELD_CODES
                                 if template.find(key, position) >= 0), default=len(template))
                run = paragraph.add_run(template[position:following])
                self._small(run, settings, template[position:following])
                position = following
                continue
            field = OxmlElement("w:fldSimple")
            instruction = _FIELD_CODES[code]
            field.set(qn("w:instr"), f" {instruction} ")
            paragraph._p.append(field)
            run = paragraph.add_run("1")
            field.append(run._r)
            self._small(run, settings, "۱")
            position += len(code)

    def _small(self, run, settings: HeaderFooter, text: str) -> None:  # noqa: ANN001
        run.font.size = Pt(settings.font_size)
        r_pr = run._r.get_or_add_rPr()
        _child(r_pr, "w:szCs", val=str(round(settings.font_size * 2)))
        if _has_rtl(text):
            _child(r_pr, "w:rtl")

    def _header_footer(self, settings: HeaderFooter) -> None:
        section = self.docx.sections[0]
        used = any((settings.header, settings.footer, settings.first_header, settings.first_footer,
                    settings.even_header, settings.even_footer))
        if not used:
            return
        number_type = OxmlElement("w:pgNumType")
        number_type.set(qn("w:fmt"), _NUMBER_FORMATS.get(settings.number_format, "decimal"))
        section._sectPr.append(number_type)
        pairs = [(section.header, settings.header, settings.header_align),
                 (section.footer, settings.footer, settings.footer_align)]
        if settings.different_first:
            section.different_first_page_header_footer = True
            pairs += [(section.first_page_header, settings.first_header, settings.header_align),
                      (section.first_page_footer, settings.first_footer, settings.footer_align)]
        if settings.different_odd_even:
            self.docx.settings.odd_and_even_pages_header_footer = True
            pairs += [(section.even_page_header, settings.even_header, settings.header_align),
                      (section.even_page_footer, settings.even_footer, settings.footer_align)]
        for part, template, align in pairs:
            part.is_linked_to_previous = False
            self._field_paragraph(part.paragraphs[0], template, align, settings)


def export_docx(document: Document, path: Path | str, render_object: RenderObject | None = None) -> None:
    """Write ``document`` as a .docx file."""
    exporter = _Exporter(document, render_object)
    exporter.build()
    exporter.docx.save(str(path))
