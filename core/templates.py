"""Built-in document templates (plain model documents, fully editable)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from core.document import (
    CharStyle,
    Document,
    HeaderFooter,
    Paragraph,
    ParagraphStyle,
    Table,
    TableCell,
    TextRun,
)
from core.styles import builtin_styles


def _styled(document: Document, style_name: str, text: str, **paragraph: object) -> Paragraph:
    style = document.styles[style_name]
    paragraph_style = replace(style.paragraph, **paragraph)
    return Paragraph(runs=[TextRun(text, style.char)], style=paragraph_style)


def _text(text: str, *, bold: bool = False, **paragraph: object) -> Paragraph:
    return Paragraph(runs=[TextRun(text, CharStyle(bold=bold))],
                     style=ParagraphStyle(line_spacing=1.5, space_after=6, **paragraph))


def _equation(latex: str, numbered: bool = True) -> Paragraph:
    return Paragraph(runs=[TextRun("", CharStyle(), {"type": "equation", "latex": latex, "display": True,
                                                    "numbered": numbered})],
                     style=ParagraphStyle(alignment="center", space_before=6, space_after=6))


def _table(header: list[str], rows: int) -> Table:
    cells = [[TableCell([Paragraph(runs=[TextRun(text, CharStyle(bold=True))])], background="#eef2f8")
              for text in header]]
    cells += [[TableCell() for _ in header] for _ in range(rows)]
    return Table(rows=cells, header_rows=1)


def _base(title: str) -> Document:
    document = Document(blocks=[])
    document.styles = builtin_styles()
    document.metadata.title = title
    return document


def general_document() -> Document:
    document = _base("")
    document.blocks = [Paragraph(style=ParagraphStyle(line_spacing=1.5, space_after=6))]
    return document


def school_notes() -> Document:
    document = _base("جزوهٔ درسی")
    document.header_footer = HeaderFooter(header="{title}", footer="صفحهٔ {page}")
    document.blocks = [
        _styled(document, "Title", "جزوهٔ درس …"),
        _styled(document, "Subtitle", "پایه: …    |    دبیر: …    |    تاریخ: …"),
        _styled(document, "Heading 1", "درس اول: عنوان درس"),
        _text("هدف‌های این درس را اینجا بنویسید."),
        _styled(document, "Heading 2", "نکته‌های مهم"),
        _text("نکتهٔ نخست"),
        _text("نکتهٔ دوم"),
        _styled(document, "Heading 2", "تمرین"),
        _text("۱. …"),
        _styled(document, "Quote", "یادآوری: مطالب مهم را در این کادر بنویسید."),
    ]
    return document


def lecture_notes() -> Document:
    document = _base("جزوهٔ دانشگاهی")
    document.header_footer = HeaderFooter(header="{title}", footer="{page} از {pages}", different_first=True)
    document.blocks = [
        _styled(document, "Title", "نام درس"),
        _styled(document, "Subtitle", "استاد: …    |    نیم‌سال: …    |    جلسهٔ: …"),
        _styled(document, "Heading 1", "۱. مقدمه"),
        _text("خلاصهٔ جلسهٔ پیش و طرح بحث امروز.", alignment="justify"),
        _styled(document, "Heading 1", "۲. مطالب جلسه"),
        _styled(document, "Heading 2", "۲.۱ تعریف‌ها"),
        _text("تعریف: …", alignment="justify"),
        _styled(document, "Heading 2", "۲.۲ قضیه‌ها و اثبات‌ها"),
        _text("قضیه: …", bold=True),
        _text("اثبات: …", alignment="justify"),
        _styled(document, "Heading 1", "۳. جمع‌بندی و منابع"),
        _text("منبع‌های پیشنهادی برای مطالعهٔ بیشتر."),
    ]
    return document


def mathematics_notes() -> Document:
    document = _base("یادداشت‌های ریاضی")
    document.header_footer = HeaderFooter(footer="{page}")
    document.blocks = [
        _styled(document, "Title", "یادداشت‌های ریاضی"),
        _styled(document, "Heading 1", "معادلهٔ درجهٔ دوم"),
        _text("ریشه‌های معادلهٔ درجهٔ دوم از رابطهٔ زیر به دست می‌آیند:", alignment="justify"),
        _equation(r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}"),
        _styled(document, "Heading 1", "حد و انتگرال"),
        _equation(r"\lim_{x \to 0} \frac{\sin x}{x} = 1"),
        _equation(r"\int_0^\infty e^{-x^2}\,dx = \frac{\sqrt{\pi}}{2}"),
        _styled(document, "Heading 1", "ماتریس و مجموع"),
        _equation(r"A = \begin{pmatrix} a & b \\ c & d \end{pmatrix}, \quad \det A = ad - bc"),
        _equation(r"\sum_{i=1}^{n} i = \frac{n(n+1)}{2}"),
        _text("توضیح و حل تمرین‌ها را اینجا بنویسید."),
    ]
    return document


def scientific_report() -> Document:
    document = _base("گزارش علمی")
    document.header_footer = HeaderFooter(header="{title}", footer="صفحهٔ {page} از {pages}", different_first=True)
    document.blocks = [
        _styled(document, "Title", "عنوان گزارش"),
        _styled(document, "Subtitle", "نویسنده: …    |    تاریخ: …"),
        _styled(document, "Heading 1", "چکیده"),
        _text("چکیدهٔ گزارش در یک بند.", alignment="justify"),
        _styled(document, "Heading 1", "مقدمه"),
        _text("زمینه، پرسش و هدف گزارش.", alignment="justify"),
        _styled(document, "Heading 1", "روش کار"),
        _text("مواد، ابزار و روش انجام کار.", alignment="justify"),
        _styled(document, "Heading 1", "یافته‌ها"),
        _table(["ردیف", "کمیت", "مقدار", "یکا"], 3),
        _styled(document, "Caption", "جدول ۱: نتیجهٔ اندازه‌گیری‌ها"),
        _styled(document, "Heading 1", "بحث و نتیجه‌گیری"),
        _text("تحلیل یافته‌ها و نتیجهٔ نهایی.", alignment="justify"),
        _styled(document, "Heading 1", "منابع"),
        _text("[۱] …"),
    ]
    return document


def research_paper() -> Document:
    document = _base("مقالهٔ پژوهشی")
    document.header_footer = HeaderFooter(footer="{page}")
    document.blocks = [
        _styled(document, "Title", "عنوان مقاله"),
        _styled(document, "Subtitle", "نام نویسنده(ها) — وابستگی سازمانی — رایانامه"),
        _styled(document, "Heading 2", "چکیده"),
        _styled(document, "Quote", "چکیدهٔ مقاله در ۱۵۰ تا ۲۵۰ واژه."),
        _text("کلیدواژه‌ها: …، …، …", bold=True),
        _styled(document, "Heading 1", "۱. مقدمه"),
        _text("بیان مسئله و پیشینهٔ پژوهش.", alignment="justify"),
        _styled(document, "Heading 1", "۲. روش پژوهش"),
        _text("طرح پژوهش، داده‌ها و روش تحلیل.", alignment="justify"),
        _styled(document, "Heading 1", "۳. نتایج"),
        _text("یافته‌های پژوهش.", alignment="justify"),
        _styled(document, "Heading 1", "۴. بحث"),
        _text("تفسیر نتایج و مقایسه با پژوهش‌های دیگر.", alignment="justify"),
        _styled(document, "Heading 1", "۵. نتیجه‌گیری"),
        _text("جمع‌بندی و پیشنهاد برای پژوهش‌های آینده.", alignment="justify"),
        _styled(document, "Heading 1", "منابع"),
        _text("[1] Author, A. (Year). Title. Journal, 1(2), 3–4.", direction="ltr"),
    ]
    return document


def formal_letter() -> Document:
    document = _base("نامهٔ اداری")
    document.blocks = [
        _text("شماره: …", alignment="end", space_before=0),
        _text("تاریخ: …", alignment="end"),
        _text("پیوست: …", alignment="end"),
        _text("به نام خدا", bold=True, alignment="center"),
        _text("جناب آقای / سرکار خانم …", bold=True),
        _text("مدیر محترم …", bold=True),
        _text("موضوع: …", bold=True),
        _text("با سلام و احترام؛", space_before=10),
        _text("متن نامه را اینجا بنویسید.", alignment="justify", first_line_indent=18),
        _text("با سپاس", alignment="end", space_before=24),
        _text("نام و نام خانوادگی", alignment="end", bold=True),
        _text("سمت", alignment="end"),
    ]
    return document


TEMPLATES: tuple[tuple[str, str, Callable[[], Document]], ...] = (
    ("general", "سند عمومی", general_document),
    ("school", "جزوهٔ مدرسه", school_notes),
    ("lecture", "جزوهٔ دانشگاهی", lecture_notes),
    ("math", "یادداشت‌های ریاضی", mathematics_notes),
    ("report", "گزارش علمی", scientific_report),
    ("paper", "مقالهٔ پژوهشی", research_paper),
    ("letter", "نامهٔ اداری", formal_letter),
)


def build_template(template_id: str) -> Document:
    for identifier, _title, builder in TEMPLATES:
        if identifier == template_id:
            return builder()
    raise KeyError(template_id)
