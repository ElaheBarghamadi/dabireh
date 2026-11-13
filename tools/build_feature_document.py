"""Build the Phase 2 sample document and screenshots.

Usage (from the project root):
    python tools/build_feature_document.py [output directory]

Writes ``feature_sample.dbr`` plus PDF, DOCX and PNG renderings and
screenshots of the main window and two dialogs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DABIREH_HOME", str(Path(__file__).resolve().parent.parent / ".cache" / "sample-home"))

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QKeyEvent, QPainter, QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.application import create_application  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from app.services import Services, app_data_dir  # noqa: E402
from core.document import HeaderFooter  # noqa: E402
from editor import export  # noqa: E402
from ui.dialogs.insert_dialogs import EquationDialog, TablePropertiesDialog  # noqa: E402


def _type(editor, text: str) -> None:  # noqa: ANN001
    for char in text:
        if char == "\n":
            event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier, "\r")
        elif char == "\t":
            event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier, "\t")
        else:
            event = QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, char)
        QApplication.sendEvent(editor, event)


def _end(editor) -> None:  # noqa: ANN001
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)


def _style_last(editor, style: str) -> None:  # noqa: ANN001
    editor.apply_style(style)


def _picture(path: Path) -> None:
    image = QImage(360, 220, QImage.Format.Format_RGB32)
    image.fill(QColor("#e8f0fb"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("#1f5fbf"))
    painter.setBrush(QColor("#9dbcf0"))
    painter.drawEllipse(40, 40, 140, 140)
    painter.setBrush(QColor("#f3c56b"))
    painter.drawRect(200, 70, 120, 100)
    painter.end()
    image.save(str(path))


def build(window: MainWindow, work: Path) -> None:
    editor = window.editor
    _type(editor, "گزارش آزمایش فیزیک")
    _style_last(editor, "Title")
    _type(editor, "\nنمونهٔ امکانات دبیره — Dabireh feature sample")
    _style_last(editor, "Subtitle")
    _type(editor, "\n")
    _style_last(editor, "Normal")
    editor.insert_generated_list("toc")
    _end(editor)
    _type(editor, "مقدمه")
    _style_last(editor, "Heading 1")
    _type(editor, "\n")
    _style_last(editor, "Normal")
    _type(editor, "در این آزمایش رابطهٔ انرژی و جرم بررسی می‌شود. رابطهٔ مشهور ")
    editor.insert_equation(r"E = mc^2")
    _type(editor, " را Einstein در سال ۱۹۰۵ ارائه کرد")
    editor.insert_note("Albert Einstein، مقالهٔ سال ۱۹۰۵ در Annalen der Physik.")
    _type(editor, ". ریشه‌های معادلهٔ درجهٔ دوم نیز چنین‌اند:\n")
    editor.insert_equation(r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}", display=True, numbered=True)
    editor.set_alignment("center")
    _type(editor, "\n")
    editor.set_alignment("right")
    _type(editor, "اندازه‌گیری‌ها")
    _style_last(editor, "Heading 1")
    _type(editor, "\n")
    _style_last(editor, "Normal")
    _type(editor, "نتیجهٔ سه بار اندازه‌گیری در جدول زیر آمده است.\n")
    editor.insert_table(4, 4, header_rows=1, direction="rtl")
    cells = ["ردیف", "جرم (kg)", "سرعت (m/s)", "انرژی (J)", "۱", "۲٫۰", "۳٫۰", "۹٫۰", "۲", "۴٫۰", "۵٫۰", "۵۰٫۰",
             "۳", "۶٫۰", "۷٫۰", "۱۴۷٫۰"]
    for index, text in enumerate(cells):
        _type(editor, text)
        if index < 4:
            editor.table_command("cell_background", QColor("#e3ecfa"))
        if index < len(cells) - 1:
            _type(editor, "\t")
    editor.insert_caption("table", "نتیجهٔ اندازه‌گیری‌ها")
    _end(editor)
    _type(editor, "\n")
    _style_last(editor, "Normal")
    editor.set_alignment("right")
    _type(editor, "شکل‌ها و تصویر")
    _style_last(editor, "Heading 1")
    _type(editor, "\n")
    _style_last(editor, "Normal")
    picture = work / "picture.png"
    _picture(picture)
    obj = editor.insert_image_file(picture)
    position = editor.textCursor().position() - 1
    editor.replace_object(position, {**obj, "width": 200, "height": 122, "wrap": "square_left", "border_width": 1,
                                     "border_color": "#1f5fbf"})
    _end(editor)
    _type(editor, "تصویر در سمت چپ شناور است و متن فارسی از کنار آن می‌گذرد. شکل‌های برداری نیز درون متن "
                  "می‌نشینند و با دوبار کلیک ویرایش می‌شوند: ")
    for shape in (
        {"kind": "rounded", "fill": "#dfe9fb", "stroke": "#1f5fbf", "text": "آغاز", "width": 90, "height": 44},
        {"kind": "arrow", "fill": None, "stroke": "#444444", "text": "", "width": 60, "height": 20},
        {"kind": "ellipse", "fill": "#fdebc8", "stroke": "#b9770e", "text": "پایان", "width": 90, "height": 44},
    ):
        editor.insert_object({"type": "shape", "stroke_width": 1.5, "opacity": 1.0, "rotation": 0, "sides": 5,
                              **shape})
        _type(editor, " ")
    editor.insert_caption("figure", "تصویر شناور و شکل‌های برداری")
    _end(editor)
    editor.set_header_footer(HeaderFooter(header="{title}", footer="صفحهٔ {page} از {pages}"))
    metadata = editor.metadata
    metadata.title = "گزارش آزمایش فیزیک"
    editor.set_metadata(metadata)
    editor.update_fields()


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/screenshots")
    output.mkdir(parents=True, exist_ok=True)
    app = create_application(sys.argv[:1])
    window = MainWindow(Services.create(app_data_dir()))
    window.resize(1180, 900)
    window.show()
    app.processEvents()
    build(window, output)
    app.processEvents()
    editor = window.editor
    window.save_to_path(output / "feature_sample.dbr")
    export.export_pdf(editor.document(), editor.page_settings, output / "feature_sample.pdf", window.display_name(),
                      editor.header_footer)
    export.export_docx(editor.to_document(), editor.document(), output / "feature_sample.docx")
    window.render_page_preview(0, 110).save(str(output / "feature_page.png"))
    editor.verticalScrollBar().setValue(0)
    app.processEvents()
    window.grab().save(str(output / "feature_window.png"))
    dialog = EquationDialog({"latex": r"\int_0^\infty e^{-x^2}\,dx = \frac{\sqrt{\pi}}{2}", "display": True,
                             "numbered": True}, editor.defaults.math_font, window)
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(output / "equation_dialog.png"))
    dialog.close()
    cursor = editor.textCursor()
    cursor.setPosition(editor.toPlainText().index("ردیف"))
    editor.setTextCursor(cursor)
    properties = TablePropertiesDialog(editor.table_properties(), window)
    properties.show()
    app.processEvents()
    properties.grab().save(str(output / "table_dialog.png"))
    properties.close()
    print(f"pages: {editor.page_count()}  statistics: {window.document_statistics()}")
    editor.document().setModified(False)
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
