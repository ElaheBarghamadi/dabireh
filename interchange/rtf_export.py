"""RTF export (text, basic character/paragraph formatting, direction, tables as rows).

Images, shapes and equations are not written; equations are exported as their
LaTeX source so no content silently disappears.
"""

from __future__ import annotations

from pathlib import Path

from core import bidi
from core.document import Document, Paragraph, Table, TextRun


def _escape(text: str) -> str:
    parts: list[str] = []
    for char in text:
        code = ord(char)
        if char in "\\{}":
            parts.append("\\" + char)
        elif char == "\u2028":
            parts.append("\\line ")
        elif char == "\t":
            parts.append("\\tab ")
        elif code < 128:
            parts.append(char)
        else:
            encoded = char.encode("utf-16-le")
            for index in range(0, len(encoded), 2):
                value = int.from_bytes(encoded[index:index + 2], "little")
                parts.append(f"\\u{value - 65536 if value > 32767 else value}?")
    return "".join(parts)


class _Writer:
    def __init__(self, document: Document) -> None:
        self.document = document
        self.fonts = [document.defaults.font_family, document.defaults.latin_font]
        self.colors: list[str] = []

    def font(self, family: str | None) -> int:
        if not family:
            return 0
        if family not in self.fonts:
            self.fonts.append(family)
        return self.fonts.index(family)

    def color(self, value: str | None) -> int:
        if not value:
            return 0
        value = value.lower()
        if value not in self.colors:
            self.colors.append(value)
        return self.colors.index(value) + 1

    def run(self, run: TextRun) -> str:
        if run.object is not None:
            if run.object.get("type") == "equation":
                return "{" + _escape(" " + str(run.object.get("latex", "")) + " ") + "}"
            if run.object.get("type") == "note":
                return "{\\super *}"
            return ""
        style = run.style
        codes = [f"\\f{self.font(style.font_family)}"]
        if style.font_size:
            codes.append(f"\\fs{round(style.font_size * 2)}")
        codes += [code for flag, code in ((style.bold, "\\b"), (style.italic, "\\i"), (style.underline, "\\ul"),
                                          (style.strike, "\\strike")) if flag]
        if style.vertical_align:
            codes.append("\\super" if style.vertical_align == "super" else "\\sub")
        if style.color:
            codes.append(f"\\cf{self.color(style.color)}")
        if style.highlight:
            codes.append(f"\\highlight{self.color(style.highlight)}")
        rtl = any(bidi.first_strong_direction(c) == bidi.Direction.RTL for c in run.text)
        codes.append("\\rtlch" if rtl else "\\ltrch")
        return "{" + "".join(codes) + " " + _escape(run.text) + "}"

    def paragraph(self, paragraph: Paragraph, in_table: bool = False) -> str:
        style = paragraph.style
        direction = style.direction
        if direction == "auto":
            direction = (bidi.first_strong_direction(paragraph.text) or bidi.Direction(
                self.document.defaults.direction if self.document.defaults.direction != "auto" else "rtl")).value
        rtl = direction == "rtl"
        align = {"start": "\\qr" if rtl else "\\ql", "end": "\\ql" if rtl else "\\qr", "center": "\\qc",
                 "justify": "\\qj"}[style.alignment]
        codes = ["\\pard", "\\intbl" if in_table else "", "\\rtlpar" if rtl else "\\ltrpar", align,
                 f"\\sb{round(style.space_before * 20)}", f"\\sa{round(style.space_after * 20)}",
                 f"\\sl{round(style.line_spacing * 240)}\\slmult1",
                 f"\\li{round(style.indent_left * 20)}", f"\\ri{round(style.indent_right * 20)}",
                 f"\\fi{round(style.first_line_indent * 20)}"]
        if style.page_break_before:
            codes.insert(1, "\\pagebb")
        prefix = ""
        if paragraph.list is not None:
            prefix = "{\\f0 " + _escape("• " if paragraph.list.style in ("bullet", "circle", "square") else "– ") + "}"
        return "".join(codes) + " " + prefix + "".join(self.run(run) for run in paragraph.runs)

    def table(self, table: Table) -> str:
        rows: list[str] = []
        columns = max(1, table.column_count)
        width = 9000 // columns
        for row in table.rows:
            parts = ["\\trowd" + ("\\rtlrow" if table.direction != "ltr" else "\\ltrrow")]
            edge = 0
            for cell in row:
                if cell is None:
                    continue
                edge += width * cell.col_span
                parts.append("\\clbrdrt\\brdrs\\clbrdrl\\brdrs\\clbrdrb\\brdrs\\clbrdrr\\brdrs" + f"\\cellx{edge}")
            for cell in row:
                if cell is None:
                    continue
                body = "\\par ".join(self.paragraph(block, in_table=True) for block in cell.blocks)
                parts.append(body + "\\cell ")
            parts.append("\\row")
            rows.append("".join(parts))
        return "\n".join(rows) + "\n\\pard"

    def build(self) -> str:
        body: list[str] = []
        for block in self.document.blocks:
            if isinstance(block, Table):
                body.append(self.table(block))
            else:
                body.append(self.paragraph(block) + "\\par")
        fonts = "".join(f"{{\\f{i}\\fnil\\fcharset178 {_escape(name)};}}" for i, name in enumerate(self.fonts))
        colors = ";" + "".join(
            f"\\red{int(c[1:3], 16)}\\green{int(c[3:5], 16)}\\blue{int(c[5:7], 16)};" for c in self.colors
            if len(c) == 7)
        size = round(self.document.defaults.font_size * 2)
        header = f"{{\\rtf1\\ansi\\ansicpg1256\\uc1\\deff0{{\\fonttbl{fonts}}}{{\\colortbl{colors}}}\\fs{size}\n"
        return header + "\n".join(body) + "\n}"


def export_rtf(document: Document, path: Path | str) -> None:
    Path(path).write_text(_Writer(document).build(), encoding="ascii")
