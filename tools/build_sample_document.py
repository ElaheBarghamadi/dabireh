"""Generate the representative Persian test documents in tests/data."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.document import (  # noqa: E402
    CharStyle,
    Document,
    ListInfo,
    Paragraph,
    ParagraphStyle,
    TextRun,
)

LATIN = CharStyle(font_family="DejaVu Serif")
BOLD = CharStyle(bold=True)


def paragraph(*runs: TextRun | str, style: ParagraphStyle | None = None, list_info: ListInfo | None = None) -> Paragraph:
    items = [TextRun(run) if isinstance(run, str) else run for run in runs]
    return Paragraph(runs=items, style=style or ParagraphStyle(space_after=8, line_spacing=1.3), list=list_info)


def build() -> Document:
    body = ParagraphStyle(alignment="justify", space_after=8, line_spacing=1.4, first_line_indent=20)
    document = Document()
    document.metadata.title = "نمونهٔ سند دبیره"
    document.metadata.author = "گروه دبیره"
    document.metadata.created = document.metadata.modified = "2026-01-01T08:00:00+00:00"
    document.paragraphs = [
        paragraph(
            TextRun("دبیره؛ واژه‌پرداز فارسی", CharStyle(font_size=24, bold=True, color="#1f5fbf")),
            style=ParagraphStyle(alignment="center", space_after=14),
        ),
        paragraph(
            "دبیره برای نوشتن متن‌های فارسی و ",
            TextRun("English", LATIN),
            " در کنار هم ساخته شده است. در این بند واژه‌هایی مانند ",
            TextRun("Unicode Bidirectional Algorithm", CharStyle(font_family="DejaVu Serif", italic=True)),
            " و عددهایی مثل ۱۴۰۴ و 2026 بدون جابه‌جایی نویسه‌ها نمایش داده می‌شوند (حتی درون پرانتز [و کروشه]).",
            style=body,
        ),
        paragraph(
            "قالب‌بندی: ",
            TextRun("پررنگ", BOLD),
            "، ",
            TextRun("مورب", CharStyle(italic=True)),
            "، ",
            TextRun("زیرخط‌دار", CharStyle(underline=True)),
            "، ",
            TextRun("خط‌خورده", CharStyle(strike=True)),
            "، ",
            TextRun("رنگی", CharStyle(color="#c0392b")),
            " و ",
            TextRun("برجسته‌شده", CharStyle(highlight="#fff59d")),
            "؛ همچنین E = mc",
            TextRun("2", CharStyle(vertical_align="super")),
            " و H",
            TextRun("2", CharStyle(vertical_align="sub")),
            "O.",
            style=body,
        ),
        paragraph("نشانی وبگاه: https://example.com/fa/docs?id=42&lang=fa و رایانامه: info@example.com", style=body),
        paragraph("ریاضی: اگر x ≥ 0 و y = 2x + 3 باشد آنگاه ∑ aᵢ ≤ ∫ f(x) dx و ۲ × ۳ = ۶ است.", style=body),
        paragraph("ویژگی‌های مرحلهٔ نخست:", style=ParagraphStyle(space_before=6, space_after=4)),
        paragraph("پشتیبانی کامل از بندهای راست‌به‌چپ و چپ‌به‌راست", list_info=ListInfo("bullet", 1, 1)),
        paragraph("قلم جداگانه برای فارسی و لاتین (Mixed typography)", list_info=ListInfo("bullet", 1, 1)),
        paragraph("ذخیرهٔ خودکار و بازیابی پس از بسته‌شدن ناگهانی", list_info=ListInfo("bullet", 1, 1)),
        paragraph("گام اول: نوشتن", list_info=ListInfo("number", 1, 2)),
        paragraph("گام دوم: قالب‌بندی", list_info=ListInfo("number", 1, 2)),
        paragraph(
            TextRun(
                "This is a left-to-right paragraph that contains a Persian word (سلام) and the number ۱۲۳ in the middle.",
                LATIN,
            ),
            style=ParagraphStyle(direction="ltr", space_before=8, space_after=8, line_spacing=1.3),
        ),
        paragraph(
            "این بند چپ‌چین است و تورفتگی دارد.",
            style=ParagraphStyle(alignment="end", indent_left=40, space_after=8),
        ),
    ]
    return document


MIXED_TEXT = """سلام دنیا
این یک متن آزمایشی با English words و عدد ۱۲۳ و 456 است.
قیمت کالا ۲۵٬۰۰۰ تومان (حدود 0.5 دلار) است.
نشانی: https://example.com/path?q=1&lang=fa
رایانامه: info@example.com
فرمول: (a + b)² = a² + 2ab + b² و x ≥ 0
می‌خواهم کتاب‌ها را به کتابخانه ببرم.
[فهرست] {مجموعه} <برچسب> «گیومه»
"""

if __name__ == "__main__":
    data_dir = ROOT / "tests" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "sample_document.dbr").write_text(build().to_json(), encoding="utf-8")
    (data_dir / "mixed_text.txt").write_text(MIXED_TEXT, encoding="utf-8")
    print("wrote sample documents to", data_dir)
