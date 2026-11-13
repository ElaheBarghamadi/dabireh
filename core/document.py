"""Structured, Qt-independent document model and its JSON file format.

A document is a list of paragraphs; a paragraph is a list of styled text runs.
Text is always stored in logical order as plain Unicode.  The model is what
gets saved to ``.dbr`` files and autosave snapshots, and it is the stable
contract for future features (pagination engine, DOCX/PDF exporters).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime, timezone
from typing import Any

FORMAT_NAME = "dabireh-document"
FORMAT_VERSION = 2
FILE_EXTENSION = ".dbr"

ALIGNMENTS = ("start", "end", "center", "justify")
DIRECTIONS = ("auto", "rtl", "ltr")
LIST_STYLES = ("bullet", "circle", "square", "number", "alpha", "roman")
BULLET_STYLES = ("bullet", "circle", "square")
PAGE_SIZES = ("A4", "A5", "Letter", "Legal", "Custom")
UNDERLINE_STYLES = ("single", "dash", "dot", "wave")
NUMBER_FORMATS = ("persian", "latin", "roman")
ORIENTATIONS = ("portrait", "landscape")
LINE_SEPARATOR = "\u2028"


class DocumentFormatError(ValueError):
    """Raised when a file is not a readable Dabireh document."""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _choice(value: Any, allowed: tuple[str, ...], default: str) -> str:
    return value if value in allowed else default


def _number(value: Any, default: float, minimum: float = 0.0, maximum: float = 10_000.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(min(max(value, minimum), maximum))


def _optional_number(value: Any, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(min(max(value, minimum), maximum))


def _text(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


@dataclass(frozen=True)
class CharStyle:
    """Character formatting. ``None`` / ``False`` means "document default"."""

    font_family: str | None = None
    font_size: float | None = None  # points
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    color: str | None = None  # "#rrggbb"
    highlight: str | None = None  # "#rrggbb"
    vertical_align: str | None = None  # "super" | "sub"
    letter_spacing: float | None = None  # percent of the normal advance (100 = normal)
    stretch: float | None = None  # horizontal scaling in percent (100 = normal)
    underline_style: str | None = None  # None = single line; "dash" | "dot" | "wave"
    link: str | None = None  # hyperlink target (URL or "#bookmark")
    bookmark: str | None = None  # anchor name

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value not in (None, False)}

    @classmethod
    def from_dict(cls, data: Any) -> CharStyle:
        if not isinstance(data, dict):
            return cls()
        size = data.get("font_size")
        return cls(
            font_family=_text(data.get("font_family")) or None,
            font_size=_number(size, 0, 1, 1000) if isinstance(size, (int, float)) else None,
            bold=data.get("bold") is True,
            italic=data.get("italic") is True,
            underline=data.get("underline") is True,
            strike=data.get("strike") is True,
            color=_text(data.get("color")) or None,
            highlight=_text(data.get("highlight")) or None,
            vertical_align=data.get("vertical_align") if data.get("vertical_align") in ("super", "sub") else None,
            letter_spacing=_optional_number(data.get("letter_spacing"), 10, 1000),
            stretch=_optional_number(data.get("stretch"), 10, 1000),
            underline_style=data.get("underline_style") if data.get("underline_style") in UNDERLINE_STYLES[1:] else None,
            link=_text(data.get("link")) or None,
            bookmark=_text(data.get("bookmark")) or None,
        )


@dataclass
class TextRun:
    """Styled text, or one inline object (image, equation, shape).

    For an object run ``text`` is empty and ``object`` holds a JSON-compatible
    description with a ``"type"`` key; see ``editor/objects.py`` for the keys.
    """

    text: str = ""
    style: CharStyle = field(default_factory=CharStyle)
    object: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"text": self.text}
        style = self.style.to_dict()
        if style:
            data["style"] = style
        if self.object is not None:
            data["object"] = self.object
        return data

    @classmethod
    def from_dict(cls, data: Any) -> TextRun:
        if not isinstance(data, dict):
            raise DocumentFormatError("ساختار متن سند معتبر نیست.")
        obj = data.get("object")
        return cls(
            text=_text(data.get("text")),
            style=CharStyle.from_dict(data.get("style")),
            object=dict(obj) if isinstance(obj, dict) and isinstance(obj.get("type"), str) else None,
        )


@dataclass
class ParagraphStyle:
    """Paragraph formatting. Lengths are in points; indents are physical sides."""

    alignment: str = "start"  # start = leading edge of the paragraph direction
    direction: str = "auto"  # auto = follow the document's default direction
    line_spacing: float = 1.0  # multiple of the natural line height
    space_before: float = 0.0
    space_after: float = 0.0
    first_line_indent: float = 0.0
    indent_left: float = 0.0
    indent_right: float = 0.0
    background: str | None = None
    page_break_before: bool = False
    style_name: str = ""  # named style ("" = Normal); see core/styles.py

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> ParagraphStyle:
        if not isinstance(data, dict):
            return cls()
        return cls(
            alignment=_choice(data.get("alignment"), ALIGNMENTS, "start"),
            direction=_choice(data.get("direction"), DIRECTIONS, "auto"),
            line_spacing=_number(data.get("line_spacing"), 1.0, 0.5, 10.0),
            space_before=_number(data.get("space_before"), 0.0),
            space_after=_number(data.get("space_after"), 0.0),
            first_line_indent=_number(data.get("first_line_indent"), 0.0, -1000.0),
            indent_left=_number(data.get("indent_left"), 0.0),
            indent_right=_number(data.get("indent_right"), 0.0),
            background=_text(data.get("background")) or None,
            page_break_before=data.get("page_break_before") is True,
            style_name=_text(data.get("style_name")),
        )


@dataclass(frozen=True)
class ListInfo:
    """List membership; paragraphs sharing ``list_id`` belong to one list."""

    style: str = "bullet"
    level: int = 1
    list_id: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> ListInfo | None:
        if not isinstance(data, dict):
            return None
        return cls(
            style=_choice(data.get("style"), LIST_STYLES, "bullet"),
            level=int(_number(data.get("level"), 1, 1, 9)),
            list_id=int(_number(data.get("list_id"), 0, 0, 1_000_000)),
        )


@dataclass
class Paragraph:
    runs: list[TextRun] = field(default_factory=list)
    style: ParagraphStyle = field(default_factory=ParagraphStyle)
    list: ListInfo | None = None

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": "paragraph",
            "style": self.style.to_dict(),
            "runs": [run.to_dict() for run in self.runs],
        }
        if self.list is not None:
            data["list"] = self.list.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Any) -> Paragraph:
        if not isinstance(data, dict):
            raise DocumentFormatError("ساختار بندهای سند معتبر نیست.")
        runs = data.get("runs", [])
        if not isinstance(runs, list):
            raise DocumentFormatError("ساختار بندهای سند معتبر نیست.")
        return cls(
            runs=[TextRun.from_dict(run) for run in runs],
            style=ParagraphStyle.from_dict(data.get("style")),
            list=ListInfo.from_dict(data.get("list")),
        )


@dataclass
class TableCell:
    """One table cell. ``row_span``/``col_span`` > 1 describe a merged cell."""

    blocks: list[Paragraph] = field(default_factory=lambda: [Paragraph()])
    row_span: int = 1
    col_span: int = 1
    background: str | None = None
    vertical_align: str = "top"  # top | middle | bottom

    @property
    def text(self) -> str:
        return "\n".join(block.text for block in self.blocks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocks": [block.to_dict() for block in self.blocks],
            "row_span": self.row_span,
            "col_span": self.col_span,
            "background": self.background,
            "vertical_align": self.vertical_align,
        }

    @classmethod
    def from_dict(cls, data: Any) -> TableCell:
        if not isinstance(data, dict):
            raise DocumentFormatError("ساختار جدول سند معتبر نیست.")
        blocks = data.get("blocks", [])
        return cls(
            blocks=[Paragraph.from_dict(item) for item in blocks if isinstance(item, dict)] or [Paragraph()],
            row_span=int(_number(data.get("row_span"), 1, 1, 1000)),
            col_span=int(_number(data.get("col_span"), 1, 1, 1000)),
            background=_text(data.get("background")) or None,
            vertical_align=_choice(data.get("vertical_align"), ("top", "middle", "bottom"), "top"),
        )


@dataclass
class Table:
    """A table block. ``rows[r][c]`` is ``None`` where a merged cell covers the slot.

    Columns are in logical order: in an RTL table column 0 is the rightmost.
    """

    rows: list[list[TableCell | None]] = field(default_factory=list)
    column_widths: list[float] = field(default_factory=list)  # percent of table width; empty = equal
    header_rows: int = 0  # repeated at the top of every page the table spans
    direction: str = "rtl"
    alignment: str = "center"  # start | center | end
    width_percent: float = 100.0
    border_width: float = 1.0  # px; 0 = no borders
    border_color: str = "#7a828e"
    cell_padding: float = 5.0  # px
    role: str = ""  # "toc" | "lof" | "lot" for generated lists, else ""

    @property
    def column_count(self) -> int:
        return max((len(row) for row in self.rows), default=0)

    @property
    def text(self) -> str:
        return "\n".join("\t".join(cell.text if cell else "" for cell in row) for row in self.rows)

    def to_dict(self) -> dict[str, Any]:
        data = {key: getattr(self, key) for key in (
            "column_widths", "header_rows", "direction", "alignment", "width_percent",
            "border_width", "border_color", "cell_padding", "role")}
        data["type"] = "table"
        data["rows"] = [[cell.to_dict() if cell else None for cell in row] for row in self.rows]
        return data

    @classmethod
    def from_dict(cls, data: Any) -> Table:
        rows = data.get("rows") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not all(isinstance(row, list) for row in rows):
            raise DocumentFormatError("ساختار جدول سند معتبر نیست.")
        widths = data.get("column_widths")
        return cls(
            rows=[[TableCell.from_dict(cell) if cell is not None else None for cell in row] for row in rows],
            column_widths=[_number(w, 10.0, 1.0, 100.0) for w in widths] if isinstance(widths, list) else [],
            header_rows=int(_number(data.get("header_rows"), 0, 0, 50)),
            direction=_choice(data.get("direction"), ("rtl", "ltr"), "rtl"),
            alignment=_choice(data.get("alignment"), ("start", "center", "end"), "center"),
            width_percent=_number(data.get("width_percent"), 100.0, 10.0, 100.0),
            border_width=_number(data.get("border_width"), 1.0, 0.0, 20.0),
            border_color=_text(data.get("border_color"), "#7a828e") or "#7a828e",
            cell_padding=_number(data.get("cell_padding"), 5.0, 0.0, 60.0),
            role=_choice(data.get("role"), ("", "toc", "lof", "lot"), ""),
        )


Block = Paragraph | Table


def block_from_dict(data: Any) -> Block:
    if isinstance(data, dict) and data.get("type") == "table":
        return Table.from_dict(data)
    return Paragraph.from_dict(data)


@dataclass
class NamedStyle:
    """A reusable paragraph style (Title, Heading 1, …)."""

    name: str
    char: CharStyle = field(default_factory=CharStyle)
    paragraph: ParagraphStyle = field(default_factory=ParagraphStyle)
    heading_level: int = 0  # 1-3 puts the paragraph in the table of contents
    builtin: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "char": self.char.to_dict(), "paragraph": self.paragraph.to_dict(),
                "heading_level": self.heading_level, "builtin": self.builtin}

    @classmethod
    def from_dict(cls, data: Any) -> NamedStyle | None:
        if not isinstance(data, dict) or not _text(data.get("name")):
            return None
        return cls(
            name=data["name"],
            char=CharStyle.from_dict(data.get("char")),
            paragraph=ParagraphStyle.from_dict(data.get("paragraph")),
            heading_level=int(_number(data.get("heading_level"), 0, 0, 3)),
            builtin=data.get("builtin") is True,
        )


@dataclass
class HeaderFooter:
    """Running header and footer texts.

    Texts may contain the fields ``{page}``, ``{pages}``, ``{date}``,
    ``{time}`` and ``{title}``, resolved when a page is drawn or exported.
    """

    header: str = ""
    footer: str = ""
    first_header: str = ""
    first_footer: str = ""
    even_header: str = ""
    even_footer: str = ""
    different_first: bool = False
    different_odd_even: bool = False
    header_align: str = "center"  # start | center | end
    footer_align: str = "center"
    number_format: str = "persian"
    font_size: float = 10.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> HeaderFooter:
        if not isinstance(data, dict):
            return cls()
        result = cls()
        for item in fields(cls):
            value = data.get(item.name)
            default = getattr(result, item.name)
            if isinstance(default, bool):
                setattr(result, item.name, value is True)
            elif isinstance(default, str) and isinstance(value, str):
                setattr(result, item.name, value)
        result.header_align = _choice(result.header_align, ("start", "center", "end"), "center")
        result.footer_align = _choice(result.footer_align, ("start", "center", "end"), "center")
        result.number_format = _choice(result.number_format, NUMBER_FORMATS, "persian")
        result.font_size = _number(data.get("font_size"), 10.0, 5.0, 40.0)
        return result

    def texts_for_page(self, page: int) -> tuple[str, str]:
        """(header, footer) templates for the 1-based page number."""
        if self.different_first and page == 1:
            return self.first_header, self.first_footer
        if self.different_odd_even and page % 2 == 0:
            return self.even_header, self.even_footer
        return self.header, self.footer


@dataclass
class PageSettings:
    """Page configuration; margins are in millimetres."""

    size: str = "A4"
    orientation: str = "portrait"
    margin_top: float = 25.0
    margin_bottom: float = 25.0
    margin_left: float = 25.0
    margin_right: float = 25.0
    background: str = "#ffffff"
    custom_width: float = 210.0  # mm, used when size == "Custom"
    custom_height: float = 297.0
    border_width: float = 0.0  # page border in points; 0 = none
    border_color: str = "#000000"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> PageSettings:
        if not isinstance(data, dict):
            return cls()
        return cls(
            size=_choice(data.get("size"), PAGE_SIZES, "A4"),
            orientation=_choice(data.get("orientation"), ORIENTATIONS, "portrait"),
            margin_top=_number(data.get("margin_top"), 25.0, 5.0, 100.0),
            margin_bottom=_number(data.get("margin_bottom"), 25.0, 5.0, 100.0),
            margin_left=_number(data.get("margin_left"), 25.0, 5.0, 100.0),
            margin_right=_number(data.get("margin_right"), 25.0, 5.0, 100.0),
            background=_text(data.get("background"), "#ffffff") or "#ffffff",
            custom_width=_number(data.get("custom_width"), 210.0, 50.0, 1000.0),
            custom_height=_number(data.get("custom_height"), 297.0, 50.0, 1500.0),
            border_width=_number(data.get("border_width"), 0.0, 0.0, 12.0),
            border_color=_text(data.get("border_color"), "#000000") or "#000000",
        )


@dataclass
class Metadata:
    title: str = ""
    author: str = ""
    subject: str = ""
    keywords: str = ""
    language: str = "fa"
    created: str = field(default_factory=now_iso)
    modified: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> Metadata:
        if not isinstance(data, dict):
            return cls()
        defaults = cls()
        return cls(**{f.name: _text(data.get(f.name), getattr(defaults, f.name)) for f in fields(cls)})


@dataclass
class DocumentDefaults:
    """Document-wide defaults: base font, per-script fonts and direction."""

    font_family: str = "Vazirmatn"
    font_size: float = 13.0
    latin_font: str = "Cambria"
    math_font: str = "Cambria Math"
    direction: str = "rtl"  # "auto" = detect each paragraph from its content

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> DocumentDefaults:
        if not isinstance(data, dict):
            return cls()
        return cls(
            font_family=_text(data.get("font_family"), "Vazirmatn") or "Vazirmatn",
            font_size=_number(data.get("font_size"), 13.0, 4.0, 200.0),
            latin_font=_text(data.get("latin_font"), "Cambria") or "Cambria",
            math_font=_text(data.get("math_font"), "Cambria Math") or "Cambria Math",
            direction=_choice(data.get("direction"), DIRECTIONS, "rtl"),
        )


@dataclass
class Document:
    metadata: Metadata = field(default_factory=Metadata)
    page: PageSettings = field(default_factory=PageSettings)
    defaults: DocumentDefaults = field(default_factory=DocumentDefaults)
    blocks: list[Block] = field(default_factory=lambda: [Paragraph()])
    styles: dict[str, NamedStyle] = field(default_factory=dict)
    header_footer: HeaderFooter = field(default_factory=HeaderFooter)
    resources: dict[str, str] = field(default_factory=dict)  # image id -> base64 of the original file

    # ------------------------------------------------------------ structure
    @property
    def paragraphs(self) -> list[Paragraph]:
        """Top-level paragraphs (tables are skipped; use ``blocks`` for everything)."""
        return [block for block in self.blocks if isinstance(block, Paragraph)]

    @paragraphs.setter
    def paragraphs(self, value: list[Paragraph]) -> None:
        self.blocks = list(value)

    def iter_paragraphs(self) -> Iterator[Paragraph]:
        """Every paragraph in reading order, including those inside table cells."""
        for block in self.blocks:
            if isinstance(block, Paragraph):
                yield block
            else:
                for row in block.rows:
                    for cell in row:
                        if cell is not None:
                            yield from cell.blocks

    # ----------------------------------------------------------------- text
    def plain_text(self) -> str:
        return "\n".join(block.text.replace(LINE_SEPARATOR, "\n") for block in self.blocks)

    @classmethod
    def from_plain_text(cls, text: str, template: Document | None = None) -> Document:
        """Create a document from plain text, one paragraph per line."""
        base = template or cls()
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        paragraphs: list[Block] = [Paragraph(runs=[TextRun(line)] if line else []) for line in lines]
        return cls(
            metadata=Metadata(),
            page=replace(base.page),
            defaults=replace(base.defaults),
            blocks=paragraphs or [Paragraph()],
            styles=dict(base.styles),
        )

    # ------------------------------------------------------------ serialise
    def to_dict(self) -> dict[str, Any]:
        return {
            "format": FORMAT_NAME,
            "version": FORMAT_VERSION,
            "metadata": self.metadata.to_dict(),
            "page": self.page.to_dict(),
            "defaults": self.defaults.to_dict(),
            "header_footer": self.header_footer.to_dict(),
            "styles": [style.to_dict() for style in self.styles.values()],
            "blocks": [block.to_dict() for block in self.blocks],
            "resources": self.resources,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=1)

    @classmethod
    def from_dict(cls, data: Any) -> Document:
        if not isinstance(data, dict) or data.get("format") != FORMAT_NAME:
            raise DocumentFormatError("این پرونده یک سند دبیره نیست.")
        version = data.get("version")
        if not isinstance(version, int) or version < 1:
            raise DocumentFormatError("نسخهٔ قالب سند نامعتبر است.")
        if version > FORMAT_VERSION:
            raise DocumentFormatError(
                "این سند با نسخهٔ جدیدتری از دبیره ساخته شده است و در این نسخه باز نمی‌شود."
            )
        # Version 1 files stored only paragraphs under "paragraphs".
        blocks = data.get("blocks", data.get("paragraphs", []))
        if not isinstance(blocks, list):
            raise DocumentFormatError("ساختار بندهای سند معتبر نیست.")
        styles = [NamedStyle.from_dict(item) for item in data.get("styles", []) or []]
        resources = data.get("resources")
        return cls(
            metadata=Metadata.from_dict(data.get("metadata")),
            page=PageSettings.from_dict(data.get("page")),
            defaults=DocumentDefaults.from_dict(data.get("defaults")),
            blocks=[block_from_dict(item) for item in blocks] or [Paragraph()],
            styles={style.name: style for style in styles if style is not None},
            header_footer=HeaderFooter.from_dict(data.get("header_footer")),
            resources={k: v for k, v in resources.items() if isinstance(k, str) and isinstance(v, str)}
            if isinstance(resources, dict) else {},
        )

    @classmethod
    def from_json(cls, text: str) -> Document:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise DocumentFormatError("پرونده آسیب دیده است یا قالب آن خوانا نیست.") from error
        return cls.from_dict(data)
