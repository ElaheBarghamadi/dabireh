"""Header/footer fields and page-number formats (Qt-free)."""

from __future__ import annotations

from datetime import datetime

from core.persian import gregorian_to_jalali, to_persian_digits

FIELDS: tuple[tuple[str, str], ...] = (
    ("{page}", "شمارهٔ صفحه"),
    ("{pages}", "تعداد صفحه‌ها"),
    ("{date}", "تاریخ"),
    ("{time}", "ساعت"),
    ("{title}", "عنوان سند"),
)

_ROMAN = ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
          (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"))


def to_roman(number: int) -> str:
    if number <= 0:
        return str(number)
    parts: list[str] = []
    for value, numeral in _ROMAN:
        while number >= value:
            parts.append(numeral)
            number -= value
    return "".join(parts)


def format_page_number(number: int, number_format: str = "persian") -> str:
    if number_format == "roman":
        return to_roman(number)
    if number_format == "latin":
        return str(number)
    return to_persian_digits(str(number))


def resolve_fields(template: str, *, page: int, pages: int, title: str = "", number_format: str = "persian",
                   now: datetime | None = None) -> str:
    """Replace the fields of a header/footer template with their values."""
    if "{" not in template:
        return template
    now = now or datetime.now()
    persian = number_format == "persian"
    if persian:
        year, month, day = gregorian_to_jalali(now.year, now.month, now.day)
        date = to_persian_digits(f"{year}/{month:02d}/{day:02d}")
        time = to_persian_digits(now.strftime("%H:%M"))
    else:
        date, time = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
    values = {
        "{page}": format_page_number(page, number_format),
        "{pages}": format_page_number(pages, number_format),
        "{date}": date,
        "{time}": time,
        "{title}": title,
    }
    for key, value in values.items():
        template = template.replace(key, value)
    return template
