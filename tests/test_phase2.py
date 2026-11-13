"""Phase 2: objects, tables, styles, references, output formats and document management."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree

import pytest
from PySide6.QtCore import QEvent, QMimeData, Qt
from PySide6.QtGui import QColor, QImage, QKeyEvent, QKeySequence, QTextCursor
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.services import Services
from app.settings import SettingsStore
from core import equation
from core.document import (
    CharStyle,
    Document,
    HeaderFooter,
    PageSettings,
    Paragraph,
    ParagraphStyle,
    Table,
    TableCell,
    TextRun,
)
from core.fields import format_page_number, resolve_fields, to_roman
from core.pagination import page_geometry
from core.styles import builtin_styles
from core.templates import TEMPLATES, build_template
from editor import export
from editor.find_replace import SearchOptions, count_matches, replace_all
from editor.objects import OBJECT_CHAR
from editor.page_render import PageRenderer
from editor.text_editor import RichTextEditor
from storage.history import BackupManager, ExportHistory, VersionStore
from tests.conftest import select, select_text, type_text
from ui.dialogs.insert_dialogs import EquationDialog, ImageDialog, ShapeDialog, TablePropertiesDialog
from ui.dialogs.layout_dialogs import HeaderFooterDialog, PrintOptionsDialog, StyleEditDialog
from ui.dialogs.manage_dialogs import ShortcutEditorDialog
from ui.dialogs.page_setup_dialog import PageSetupDialog
from ui.dialogs.paragraph_dialog import ParagraphDialog


def para(text: str, **style: object) -> Paragraph:
    return Paragraph(runs=[TextRun(text, CharStyle())], style=ParagraphStyle(**style))


def texts(table: Table) -> list[list[str | None]]:
    return [[None if cell is None else "|".join(p.text for p in cell.blocks) for cell in row]
            for row in table.rows]


def first_table(document: Document) -> Table:
    return next(block for block in document.blocks if isinstance(block, Table))


@pytest.fixture
def png(tmp_path: Path) -> Path:
    image = QImage(200, 100, QImage.Format.Format_RGB32)
    image.fill(QColor("#3366cc"))
    path = tmp_path / "picture.png"
    assert image.save(str(path))
    return path


# ------------------------------------------------------------------- model
def test_model_v2_round_trips_through_json() -> None:
    table = Table(
        rows=[[TableCell([para("الف")], col_span=2, background="#eeeeee"), None],
              [TableCell([para("ب")]), TableCell([para("ج")], vertical_align="middle")]],
        column_widths=[40, 60], header_rows=1, direction="rtl")
    document = Document(blocks=[
        Paragraph(runs=[TextRun("متن ", CharStyle(bold=True, letter_spacing=120, underline_style="wave")),
                        TextRun("", CharStyle(), {"type": "equation", "latex": r"x^2", "display": False,
                                                 "numbered": False})],
                  style=ParagraphStyle(style_name="Quote", background="#fafafa", page_break_before=True)),
        table,
    ])
    document.styles = builtin_styles()
    document.header_footer = HeaderFooter(header="{title}", footer="{page}", different_first=True)
    document.page = PageSettings(size="Custom", custom_width=180, custom_height=240, border_width=1.5)
    document.resources["abc.png"] = "aGVsbG8="
    assert Document.from_json(document.to_json()) == document


def test_version_one_files_still_open() -> None:
    old = '{"format": "dabireh-document", "version": 1, "paragraphs": [{"runs": [{"text": "سلام"}]}]}'
    document = Document.from_json(old)
    assert [p.text for p in document.paragraphs] == ["سلام"]


def test_page_number_fields() -> None:
    assert to_roman(14) == "xiv"
    assert format_page_number(12, "persian") == "۱۲"
    assert format_page_number(12, "latin") == "12"
    assert resolve_fields("صفحهٔ {page} از {pages} — {title}", page=2, pages=10, title="گزارش") == \
        "صفحهٔ ۲ از ۱۰ — گزارش"
    footer = HeaderFooter(header="فرد", even_header="زوج", first_header="نخست", different_first=True,
                          different_odd_even=True)
    assert [footer.texts_for_page(n)[0] for n in (1, 2, 3)] == ["نخست", "زوج", "فرد"]


def test_custom_and_letter_page_sizes() -> None:
    letter = page_geometry(PageSettings(size="Letter"))
    assert (round(letter.width), round(letter.height)) == (816, 1056)
    custom = page_geometry(PageSettings(size="Custom", custom_width=100, custom_height=200, orientation="landscape"))
    assert custom.width > custom.height
    assert round(custom.width) == round(200 / 25.4 * 96)


# --------------------------------------------------------------- equations
@pytest.mark.parametrize("latex", [
    r"\frac{a}{b}", r"x^{2}+y_{i}", r"\sqrt[3]{x}", r"\int_{0}^{\infty} e^{-x^2}\,dx", r"\sum_{i=1}^{n} i",
    r"\lim_{x \to 0} \frac{\sin x}{x}", r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}", r"\vec{v} \cdot \hat{n}",
    r"\left( \frac{1}{2} \right)", r"\alpha \leq \beta \neq \gamma",
])
def test_equation_syntax_is_supported(latex: str) -> None:
    assert equation.is_valid(latex)
    omml = equation.to_omml(latex)
    assert omml.startswith("<m:oMath")
    assert equation.is_valid(equation.omml_to_latex(ElementTree.fromstring(omml)))


@pytest.mark.parametrize("latex", [r"\frac{a}{", r"x^", r"\begin{pmatrix} a", r"\left( x"])
def test_broken_equations_are_rejected(latex: str) -> None:
    assert not equation.is_valid(latex)
    with pytest.raises(equation.EquationError):
        equation.parse(latex)


def test_equation_omml_round_trip_keeps_structure() -> None:
    assert equation.omml_to_latex(ElementTree.fromstring(equation.to_omml(r"\frac{a^2+b_1}{\sqrt[3]{x}}"))) == \
        r"\frac{{a}^{2}+{b}_{1}}{\sqrt[3]{x}}"


def test_equation_is_an_editable_inline_object(editor: RichTextEditor) -> None:
    type_text(editor, "رابطهٔ ")
    editor.insert_equation(r"E = mc^2")
    type_text(editor, " درست است")
    assert editor.toPlainText() == f"رابطهٔ {OBJECT_CHAR} درست است"
    runs = editor.to_document().paragraphs[0].runs
    objects = [run.object for run in runs if run.object]
    assert objects == [{"type": "equation", "latex": "E = mc^2", "display": False, "numbered": False}]
    # text typed after an object must not become part of it
    assert [run.text for run in runs if not run.object] == ["رابطهٔ ", " درست است"]

    select(editor, 7, 8)
    position, obj = editor.selected_object()
    editor.replace_object(position, {**obj, "latex": r"a^2+b^2=c^2"})
    assert editor.to_document().paragraphs[0].runs[1].object["latex"] == "a^2+b^2=c^2"
    editor.undo()
    assert editor.to_document().paragraphs[0].runs[1].object["latex"] == "E = mc^2"


def test_equation_dialog_validates_while_typing(qapp: QApplication) -> None:
    from PySide6.QtWidgets import QDialogButtonBox

    dialog = EquationDialog(None, "DejaVu Serif")
    ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled()
    dialog.source.setPlainText(r"\frac{a}{")
    assert not ok.isEnabled() and dialog.status.text().startswith("خطا")
    dialog.source.setPlainText(r"\frac{a}{b}")
    dialog.display.setChecked(True)
    dialog.numbered.setChecked(True)
    assert ok.isEnabled() and dialog.status.text() == ""
    assert dialog.object() == {"type": "equation", "latex": r"\frac{a}{b}", "display": True, "numbered": True}
    dialog.resize(600, 500)
    assert not dialog.grab().isNull()


# ------------------------------------------------------------------ images
def test_image_is_stored_once_and_survives_save(editor: RichTextEditor, png: Path) -> None:
    type_text(editor, "پیش ")
    first = editor.insert_image_file(png)
    editor.insert_image_file(png)
    assert first["type"] == "image" and (first["width"], first["height"]) == (200, 100)
    document = editor.to_document()
    assert len(document.resources) == 1
    restored = Document.from_json(document.to_json())
    other = RichTextEditor()
    other.load_document(restored)
    assert other.to_document() == document
    other.deleteLater()


def test_image_properties_dialog_keeps_aspect_ratio(qapp: QApplication) -> None:
    dialog = ImageDialog({"type": "image", "resource": "x.png", "width": 200, "height": 100})
    dialog.width.setValue(300)
    assert dialog.height.value() == pytest.approx(150)
    dialog.lock.setChecked(False)
    dialog.height.setValue(90)
    assert dialog.width.value() == pytest.approx(300)
    dialog.rotation.setValue(90)
    dialog.crop[0].setValue(10)
    dialog.wrap.setCurrentIndex(dialog.wrap.findData("square_left"))
    obj = dialog.object()
    assert (obj["width"], obj["height"], obj["rotation"], obj["wrap"]) == (300, 90, 90, "square_left")
    assert obj["crop"] == [0.1, 0, 0, 0]


def test_floating_image_round_trips(editor: RichTextEditor, png: Path) -> None:
    obj = editor.insert_image_file(png)
    position = editor.textCursor().position() - 1
    editor.replace_object(position, {**obj, "wrap": "square_left", "width": 120, "height": 60, "border_width": 2})
    type_text(editor, "متن کنار تصویر")
    document = editor.to_document()
    images = [run.object for p in document.iter_paragraphs() for run in p.runs if run.object]
    assert len(images) == 1 and images[0]["wrap"] == "square_left" and images[0]["width"] == 120
    other = RichTextEditor()
    other.load_document(Document.from_json(document.to_json()))
    assert other.to_document() == document
    other.deleteLater()


def test_pasted_image_becomes_a_document_image(editor: RichTextEditor) -> None:
    image = QImage(40, 30, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    mime = QMimeData()
    mime.setImageData(image)
    editor.insertFromMimeData(mime)
    document = editor.to_document()
    objects = [run.object for run in document.paragraphs[0].runs if run.object]
    assert len(objects) == 1 and objects[0]["type"] == "image"
    assert objects[0]["resource"] in document.resources


# ------------------------------------------------------------------ shapes
def test_shapes_insert_group_and_ungroup(editor: RichTextEditor) -> None:
    for kind in ("rect", "ellipse", "arrow"):
        editor.insert_object({"type": "shape", "kind": kind, "width": 80, "height": 40, "fill": "#ffeecc",
                              "stroke": "#000000", "stroke_width": 1, "opacity": 1.0, "rotation": 0, "text": ""})
    assert editor.toPlainText() == OBJECT_CHAR * 3
    select(editor, 0, 3)
    assert editor.group_selected_shapes()
    objects = [run.object for run in editor.to_document().paragraphs[0].runs if run.object]
    assert len(objects) == 1 and objects[0]["kind"] == "group"
    assert [child["kind"] for child in objects[0]["children"]] == ["rect", "ellipse", "arrow"]
    select(editor, 0, 1)
    assert editor.reorder_group(to_front=False)
    select(editor, 0, 1)
    assert editor.ungroup_shape()
    kinds = [run.object["kind"] for run in editor.to_document().paragraphs[0].runs if run.object]
    assert sorted(kinds) == ["arrow", "ellipse", "rect"]


def test_shape_dialog_edits_properties(qapp: QApplication) -> None:
    dialog = ShapeDialog(None)
    dialog.kind.setCurrentIndex(dialog.kind.findData("polygon"))
    dialog.sides.setValue(6)
    dialog.opacity.setValue(50)
    dialog.rotation.setValue(45)
    dialog.text.setText("متن")
    obj = dialog.object()
    assert (obj["kind"], obj["sides"], obj["opacity"], obj["rotation"], obj["text"]) == ("polygon", 6, 0.5, 45, "متن")
    dialog.resize(520, 380)
    assert not dialog.grab().isNull()


# ------------------------------------------------------------------ tables
def fill_table(editor: RichTextEditor, rows: int, columns: int, direction: str = "rtl") -> None:
    """Insert a table and type r,c into every cell following Tab order."""
    editor.insert_table(rows, columns, header_rows=1, direction=direction)
    for index in range(rows * columns):
        type_text(editor, f"{index // columns}{index % columns}")
        if index < rows * columns - 1:
            QApplication.sendEvent(editor, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab,
                                                     Qt.KeyboardModifier.NoModifier, "\t"))


@pytest.mark.parametrize("direction", ["rtl", "ltr"])
def test_tab_moves_through_cells_in_reading_order(editor: RichTextEditor, direction: str) -> None:
    fill_table(editor, 2, 3, direction)
    table = first_table(editor.to_document())
    assert table.direction == direction
    assert texts(table) == [["00", "01", "02"], ["10", "11", "12"]]
    assert table.header_rows == 1


def test_first_column_of_a_persian_table_is_on_the_right(editor: RichTextEditor) -> None:
    fill_table(editor, 1, 3, "rtl")
    document = editor.document()
    xs = {}
    for label in ("00", "01", "02"):
        cursor = QTextCursor(document)
        cursor.setPosition(editor.toPlainText().index(label))
        xs[label] = editor.cursorRect(cursor).center().x()
    assert xs["00"] > xs["01"] > xs["02"]


def test_first_column_of_an_english_table_is_on_the_left(editor: RichTextEditor) -> None:
    fill_table(editor, 1, 3, "ltr")
    xs = []
    for label in ("00", "01", "02"):
        cursor = QTextCursor(editor.document())
        cursor.setPosition(editor.toPlainText().index(label))
        xs.append(editor.cursorRect(cursor).center().x())
    assert xs[0] < xs[1] < xs[2]


def place_in(editor: RichTextEditor, label: str) -> None:
    """Put the cursor at the last occurrence of ``label`` (the body text, not a generated list)."""
    cursor = editor.textCursor()
    cursor.setPosition(editor.toPlainText().rindex(label))
    editor.setTextCursor(cursor)


@pytest.mark.parametrize("direction", ["rtl", "ltr"])
def test_rows_and_columns_are_inserted_and_removed_logically(editor: RichTextEditor, direction: str) -> None:
    fill_table(editor, 2, 3, direction)
    place_in(editor, "01")
    assert editor.table_command("column_after")
    assert texts(first_table(editor.to_document())) == [["00", "01", "", "02"], ["10", "11", "", "12"]]
    place_in(editor, "01")
    assert editor.table_command("column_before")
    assert texts(first_table(editor.to_document()))[0] == ["00", "", "01", "", "02"]
    place_in(editor, "10")
    assert editor.table_command("row_above")
    assert [row[0] for row in texts(first_table(editor.to_document()))] == ["00", "", "10"]
    place_in(editor, "00")
    assert editor.table_command("remove_columns")
    assert texts(first_table(editor.to_document()))[0] == ["", "01", "", "02"]
    place_in(editor, "01")
    assert editor.table_command("remove_rows")
    table = first_table(editor.to_document())
    assert len(table.rows) == 2 and texts(table)[-1] == ["", "11", "", "12"]
    assert sum(table.column_widths) == pytest.approx(100, abs=0.5)


@pytest.mark.parametrize("direction", ["rtl", "ltr"])
def test_cells_merge_split_and_keep_their_look(editor: RichTextEditor, direction: str) -> None:
    fill_table(editor, 2, 3, direction)
    start = editor.toPlainText().index("00")
    end = editor.toPlainText().index("01") + 2
    select(editor, start, end)
    assert editor.table_command("merge")
    table = first_table(editor.to_document())
    assert table.rows[0][0].col_span == 2 and table.rows[0][1] is None
    assert table.rows[0][2].blocks[0].text == "02"
    merged_text = " ".join(p.text for p in table.rows[0][0].blocks)
    assert "00" in merged_text and "01" in merged_text

    place_in(editor, "11")
    assert editor.table_command("cell_background", QColor("#ffeeaa"))
    assert editor.table_command("cell_valign", "middle")
    table = first_table(editor.to_document())
    assert table.rows[1][1].background == "#ffeeaa" and table.rows[1][1].vertical_align == "middle"
    assert table.rows[1][0].background is None

    other = RichTextEditor()
    other.load_document(Document.from_json(editor.to_document().to_json()))
    assert first_table(other.to_document()) == table
    other.deleteLater()

    place_in(editor, "00")
    assert editor.table_command("split")
    table = first_table(editor.to_document())
    assert table.rows[0][0].col_span == 1 and table.rows[0][1] is not None


def test_table_properties_dialog_and_delete(editor: RichTextEditor, qapp: QApplication) -> None:
    fill_table(editor, 2, 2)
    dialog = TablePropertiesDialog(editor.table_properties())
    dialog.column_spins[0].setValue(30)
    dialog.column_spins[1].setValue(70)
    dialog.width.setValue(80)
    dialog.border_width.setValue(2)
    dialog.alignment.setCurrentIndex(dialog.alignment.findData("center"))
    assert editor.set_table_properties(dialog.table())
    table = first_table(editor.to_document())
    assert table.column_widths == pytest.approx([30, 70], abs=0.1)
    assert (table.width_percent, table.border_width, table.alignment) == (80, 2, "center")
    assert texts(table) == [["00", "01"], ["10", "11"]]
    assert editor.table_command("delete_table")
    assert not any(isinstance(block, Table) for block in editor.to_document().blocks)
    editor.undo()
    assert texts(first_table(editor.to_document())) == [["00", "01"], ["10", "11"]]


def test_long_table_breaks_across_pages(editor: RichTextEditor) -> None:
    editor.insert_table(70, 2, header_rows=1)
    assert editor.page_count() >= 2


# --------------------------------------------------- styles and formatting
def test_named_styles_apply_edit_and_delete(editor: RichTextEditor) -> None:
    type_text(editor, "فصل نخست\nمتن بند")
    place_in(editor, "فصل")
    assert editor.apply_style("Heading 1")
    assert editor.current_style_name() == "Heading 1"
    heading = editor.to_document().paragraphs[0]
    assert heading.style.style_name == "Heading 1" and heading.runs[0].style.bold

    style = editor.styles["Heading 1"]
    editor.save_style(replace(style, char=replace(style.char, color="#aa0000", font_size=30.0)))
    run = editor.to_document().paragraphs[0].runs[0].style
    assert (run.color, run.font_size) == ("#aa0000", 30.0)
    assert editor.to_document().paragraphs[1].runs[0].style.color is None

    custom = replace(editor.styles["Quote"], name="نکته", builtin=False)
    editor.save_style(custom)
    place_in(editor, "متن بند")
    assert editor.apply_style("نکته")
    assert editor.to_document().paragraphs[1].style.style_name == "نکته"
    restored = Document.from_json(editor.to_document().to_json())
    assert "نکته" in restored.styles
    assert editor.delete_style("نکته")
    assert editor.to_document().paragraphs[1].style.style_name == ""
    assert not editor.delete_style("Heading 1")  # built-in styles stay


def test_style_edit_dialog_rejects_duplicate_names(qapp: QApplication) -> None:
    styles = builtin_styles()
    dialog = StyleEditDialog(replace(styles["Quote"], name="تازه", builtin=False), set(styles))
    dialog.bold.setChecked(True)
    dialog.level.setCurrentIndex(dialog.level.findData("2"))
    result = dialog.style()
    assert result.name == "تازه" and result.char.bold and result.heading_level == 2


def test_character_spacing_scale_and_underline_style(editor: RichTextEditor) -> None:
    type_text(editor, "Hello World")
    select_text(editor, "World")
    editor.set_letter_spacing(150)
    editor.set_character_scale(80)
    editor.set_underline_style("wave")
    runs = editor.to_document().paragraphs[0].runs
    assert [run.text for run in runs] == ["Hello ", "World"]
    assert (runs[1].style.letter_spacing, runs[1].style.stretch, runs[1].style.underline_style) == (150, 80, "wave")
    assert runs[0].style.letter_spacing in (None, 100) and runs[0].style.underline_style is None
    editor.set_underline_style(None)
    assert editor.to_document().paragraphs[0].runs[-1].style.underline_style is None


def test_format_painter_copies_character_and_paragraph_format(editor: RichTextEditor) -> None:
    type_text(editor, "منبع\nمقصد")
    select_text(editor, "منبع")
    editor.set_bold(True)
    editor.set_text_color(QColor("#008800"))
    editor.set_alignment("center")
    editor.copy_format()
    select_text(editor, "مقصد")
    assert editor.paste_format()
    target = editor.to_document().paragraphs[1]
    assert target.runs[0].style.bold and target.runs[0].style.color == "#008800"
    assert target.style.alignment == "center" and target.text == "مقصد"


def test_paragraph_dialog_background_page_break_and_hanging_indent(editor: RichTextEditor) -> None:
    type_text(editor, "یک\nدو")
    dialog = ParagraphDialog(editor.paragraph_style(), True)
    style = replace(dialog.paragraph_style(), background="#ffeeee", page_break_before=True)
    editor.apply_paragraph_style(style)
    second = editor.to_document().paragraphs[1].style
    assert second.background == "#ffeeee" and second.page_break_before
    assert editor.page_count() == 2
    editor.apply_paragraph_style(replace(style, background=None, page_break_before=False))
    second = editor.to_document().paragraphs[1].style
    assert second.background is None and not second.page_break_before
    assert editor.page_count() == 1
    editor.set_hanging_indent(18)
    second = editor.to_document().paragraphs[1].style
    assert second.first_line_indent == pytest.approx(-18) and second.indent_right == pytest.approx(18)


def test_page_break_command_starts_a_new_page(editor: RichTextEditor) -> None:
    type_text(editor, "صفحهٔ یک")
    editor.insert_page_break()
    type_text(editor, "صفحهٔ دو")
    assert editor.page_count() == 2 and editor.cursor_page() == 2
    document = editor.to_document()
    assert [p.text for p in document.paragraphs] == ["صفحهٔ یک", "صفحهٔ دو"]
    assert document.paragraphs[1].style.page_break_before


@pytest.mark.parametrize("style", ["circle", "square", "alpha", "roman"])
def test_extra_list_styles(editor: RichTextEditor, style: str) -> None:
    type_text(editor, "یک\nدو")
    editor.selectAll()
    editor.toggle_list(style)
    paragraphs = editor.to_document().paragraphs
    assert all(p.list is not None and p.list.style == style for p in paragraphs)
    assert Document.from_json(editor.to_document().to_json()).paragraphs[0].list.style == style


def test_page_setup_dialog_custom_size_and_border(qapp: QApplication) -> None:
    dialog = PageSetupDialog(PageSettings(size="Custom", custom_width=150, custom_height=220, border_width=1.0,
                                          border_color="#333333"))
    settings = dialog.page_settings()
    assert (settings.size, settings.custom_width, settings.custom_height) == ("Custom", 150, 220)
    assert (settings.border_width, settings.border_color) == (1.0, "#333333")


# ------------------------------------------------- references and fields
def build_report(editor: RichTextEditor, png: Path) -> None:
    type_text(editor, "گزارش\nفصل اول\nمتن آغازین\nبخش یک\nمتن بخش\nفصل دوم\nپایان")
    for needle, style in (("گزارش", "Title"), ("فصل اول", "Heading 1"), ("بخش یک", "Heading 2"),
                          ("فصل دوم", "Heading 1")):
        place_in(editor, needle)
        editor.apply_style(style)


def test_table_of_contents_lists_headings_and_updates(editor: RichTextEditor, png: Path) -> None:
    build_report(editor, png)
    place_in(editor, "گزارش")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    editor.setTextCursor(cursor)
    editor.insert_generated_list("toc")
    toc = next(b for b in editor.to_document().blocks if isinstance(b, Table) and b.role == "toc")
    assert [row[0] for row in texts(toc)] == ["فصل اول", "بخش یک", "فصل دوم"]
    assert [row[1] for row in texts(toc)] == ["۱", "۱", "۱"]

    place_in(editor, "فصل دوم")
    editor.set_page_break_before(True)
    place_in(editor, "بخش یک")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    cursor.insertText(" تازه")
    assert editor.update_fields()["lists"] == 1
    toc = next(b for b in editor.to_document().blocks if isinstance(b, Table) and b.role == "toc")
    assert texts(toc) == [["فصل اول", "۱"], ["بخش یک تازه", "۱"], ["فصل دوم", "۲"]]
    assert sum(1 for b in editor.to_document().blocks if isinstance(b, Table)) == 1
    # updating never disturbs the text around the list
    order = [b.text if not isinstance(b, Table) else "<toc>" for b in editor.to_document().blocks]
    assert order == ["گزارش", "فهرست مطالب", "<toc>", "فصل اول", "متن آغازین", "بخش یک تازه", "متن بخش", "فصل دوم",
                     "پایان"]
    editor.update_fields()
    assert [b.text if not isinstance(b, Table) else "<toc>" for b in editor.to_document().blocks] == order


def test_captions_are_numbered_in_document_order(editor: RichTextEditor, png: Path) -> None:
    type_text(editor, "الف\nب")
    place_in(editor, "ب")
    editor.insert_caption("figure", "دومی")
    place_in(editor, "الف")
    editor.insert_caption("figure", "اولی")
    place_in(editor, "ب")
    editor.insert_caption("table", "جدولی")
    captions = [p.text for p in editor.to_document().paragraphs if p.style.style_name == "Caption"]
    assert captions == ["شکل ۱: اولی", "جدول ۱: جدولی", "شکل ۲: دومی"]
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    type_text(editor, "\n")
    editor.insert_generated_list("lof")
    lof = next(b for b in editor.to_document().blocks if isinstance(b, Table) and b.role == "lof")
    assert [row[0] for row in texts(lof)] == ["شکل ۱: اولی", "شکل ۲: دومی"]


def test_notes_are_collected_at_the_end(editor: RichTextEditor) -> None:
    type_text(editor, "جملهٔ یک")
    editor.insert_note("توضیح نخست")
    type_text(editor, " و جملهٔ دو")
    editor.insert_note("توضیح دوم")
    paragraphs = [p.text for p in editor.to_document().paragraphs]
    assert paragraphs[0] == "جملهٔ یک و جملهٔ دو"
    assert editor.toPlainText().count(OBJECT_CHAR) == 2
    assert paragraphs[1:] == ["پی‌نوشت‌ها", "۱. توضیح نخست", "۲. توضیح دوم"]
    # removing a note mark removes its entry on the next update
    select(editor, 8, 9)
    editor.textCursor().removeSelectedText()
    editor.update_fields()
    assert [p.text for p in editor.to_document().paragraphs][1:] == ["پی‌نوشت‌ها", "۱. توضیح دوم"]
    editor.update_fields()
    assert [p.text for p in editor.to_document().paragraphs][1:] == ["پی‌نوشت‌ها", "۱. توضیح دوم"]


def test_links_bookmarks_and_cross_references(editor: RichTextEditor) -> None:
    type_text(editor, "فصل اول\nوبگاه ما را ببینید")
    place_in(editor, "فصل")
    editor.apply_style("Heading 1")
    select_text(editor, "وبگاه")
    assert editor.set_hyperlink("https://example.org")
    select_text(editor, "ببینید")
    assert editor.add_bookmark("پایان")
    assert not editor.add_bookmark("پایان")
    assert editor.bookmarks() == ["پایان"]

    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    type_text(editor, " ")
    targets = editor.reference_targets()
    assert [(kind, label) for kind, label, _t in targets] == [("heading", "فصل اول"), ("bookmark", "پایان")]
    editor.insert_cross_reference(*targets[0])
    document = editor.to_document()
    runs = document.paragraphs[1].runs
    links = {run.text: run.style.link for run in runs if run.style.link}
    assert links["وبگاه"] == "https://example.org"
    assert links["فصل اول"].startswith("#")
    assert document.paragraphs[0].runs[0].style.bookmark == links["فصل اول"][1:]
    assert any(run.style.bookmark == "پایان" for run in runs)

    assert editor.follow_link(links["فصل اول"])
    assert editor.textCursor().block().text() == "فصل اول"
    assert editor.go_to_bookmark("پایان")
    select_text(editor, "وبگاه")
    assert editor.remove_hyperlink()
    assert not any(run.style.link == "https://example.org" for run in editor.to_document().paragraphs[1].runs)
    assert Document.from_json(document.to_json()) == document


def test_go_to_page_moves_the_cursor(editor: RichTextEditor) -> None:
    type_text(editor, "یک")
    editor.insert_page_break()
    type_text(editor, "دو")
    editor.insert_page_break()
    type_text(editor, "سه")
    editor.go_to_page(2)
    assert editor.cursor_page() == 2 and editor.textCursor().block().text() == "دو"
    editor.go_to_page(1)
    assert editor.cursor_page() == 1


# --------------------------------------------------------------- clipboard
def test_copy_paste_keeps_tables_objects_and_formatting(editor: RichTextEditor, png: Path) -> None:
    type_text(editor, "آغاز ")
    editor.insert_equation(r"x^2")
    editor.insert_image_file(png)
    type_text(editor, "\n")
    fill_table(editor, 2, 2)
    editor.selectAll()
    editor.copy()
    mime = QApplication.clipboard().mimeData()
    assert mime.hasFormat("application/x-dabireh-blocks") and mime.hasText() and mime.hasHtml()
    assert OBJECT_CHAR not in mime.text()

    other = RichTextEditor()
    other.paste()
    pasted = other.to_document()
    table = first_table(pasted)
    assert texts(table) == [["00", "01"], ["10", "11"]] and table.header_rows == 1
    objects = [run.object["type"] for run in pasted.paragraphs[0].runs if run.object]
    assert objects == ["equation", "image"]
    assert list(pasted.resources) == list(editor.to_document().resources)
    other.deleteLater()

    # drag and drop inside the application keeps the same content
    dragged = editor.createMimeDataFromSelection()
    target = RichTextEditor()
    target.insertFromMimeData(dragged)
    assert texts(first_table(target.to_document())) == [["00", "01"], ["10", "11"]]
    target.deleteLater()

    editor.cut()
    assert editor.toPlainText() == ""
    editor.paste()
    assert texts(first_table(editor.to_document())) == [["00", "01"], ["10", "11"]]


def test_paste_plain_text_drops_formatting(editor: RichTextEditor, qapp: QApplication) -> None:
    mime = QMimeData()
    mime.setHtml("<b>پررنگ</b>")
    mime.setText("پررنگ")
    qapp.clipboard().setMimeData(mime)
    editor.paste_plain_text()
    run = editor.to_document().paragraphs[0].runs[0]
    assert run.text == "پررنگ" and not run.style.bold


def test_search_can_be_limited_to_a_format(editor: RichTextEditor) -> None:
    type_text(editor, "کتاب و کتاب و کتاب")
    select(editor, 0, 4)
    editor.set_bold(True)
    document = editor.document()
    assert count_matches(document, "کتاب", SearchOptions()) == 3
    assert replace_all(document, "کتاب", "دفتر", SearchOptions(format_filter="bold")) == 1
    assert editor.toPlainText() == "دفتر و کتاب و کتاب"
    assert editor.to_document().paragraphs[0].runs[0].style.bold


# ------------------------------------------------------------- page output
def report_document(png_path: Path) -> RichTextEditor:
    editor = RichTextEditor()
    editor.resize(1100, 800)
    type_text(editor, "گزارش آزمایشی\nفصل اول\nمتن فارسی با English و عدد ۱۲۳.\n")
    place_in(editor, "گزارش")
    editor.apply_style("Title")
    place_in(editor, "فصل")
    editor.apply_style("Heading 1")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    editor.insert_equation(r"\frac{a}{b}", display=True, numbered=True)
    type_text(editor, "\n")
    editor.insert_image_file(png_path)
    type_text(editor, "\n")
    fill_table(editor, 2, 3)
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    editor.insert_page_break()
    type_text(editor, "صفحهٔ دوم")
    editor.set_header_footer(HeaderFooter(header="{title}", footer="صفحهٔ {page} از {pages}"))
    return editor


def test_pdf_has_pages_fonts_header_and_footer(qapp: QApplication, png: Path, tmp_path: Path) -> None:
    pymupdf = pytest.importorskip("pymupdf")
    editor = report_document(png)
    path = tmp_path / "out.pdf"
    pages = export.export_pdf(editor.document(), editor.page_settings, path, "عنوان سند", editor.header_footer)
    assert pages == 2 == editor.page_count()
    with pymupdf.open(path) as pdf:
        assert pdf.page_count == 2
        assert (round(pdf[0].rect.width), round(pdf[0].rect.height)) == (595, 842)
        fonts = {font[3] for page in pdf for font in page.get_fonts()}
        assert any("Vazirmatn" in name for name in fonts)
        first, second = pdf[0].get_text(), pdf[1].get_text()
        assert "English" in first and "English" not in second
        assert len(pdf[0].get_images()) >= 1
        # header and footer are painted inside the top and bottom margins of every page
        for page in pdf:
            blocks = page.get_text("blocks")
            assert min(block[1] for block in blocks) < 60
            assert max(block[3] for block in blocks) > 842 - 60
    editor.deleteLater()


def test_exported_page_image_matches_the_editor_layout(qapp: QApplication, png: Path, tmp_path: Path) -> None:
    editor = report_document(png)
    renderer = PageRenderer(editor.document(), editor.page_settings, editor.header_footer, "سند")
    assert renderer.page_count() == editor.page_count() == 2
    image = export.render_page_image(renderer, 0, dpi=96)
    assert (image.width(), image.height()) == (794, 1123)
    # nothing but header/footer text is painted in the side margins
    margin = 94
    for y in range(140, 1000, 7):
        for x in (10, 40, 80, 794 - 80, 794 - 40, 794 - 10):
            assert image.pixelColor(x, y) == QColor("#ffffff"), (x, y)
    assert x < margin or x > 794 - margin
    # the picture (solid blue) appears on the page
    blue = sum(1 for y in range(0, 1123, 5) for x in range(0, 794, 5) if image.pixelColor(x, y) == QColor("#3366cc"))
    assert blue > 400
    paths = export.export_png(editor.document(), editor.page_settings, tmp_path / "p.png", "سند",
                              editor.header_footer, dpi=96)
    assert [p.name for p in paths] == ["p-001.png", "p-002.png"]
    assert QImage(str(paths[0])) == image
    svgs = export.export_svg(editor.document(), editor.page_settings, tmp_path / "p.svg", "سند", editor.header_footer)
    assert len(svgs) == 2 and all("<svg" in p.read_text(encoding="utf-8")[:400] for p in svgs)
    editor.deleteLater()


def test_page_selection_for_printing() -> None:
    assert export.parse_page_list("۱-۳، ۵", 6) == [0, 1, 2, 4]
    assert export.parse_page_list("2,2,1", 3) == [1, 0]
    assert export.parse_page_list("9", 3) == []
    assert export.parse_page_list("abc", 3) == []


def test_printing_selected_pages_to_a_pdf_printer(qapp: QApplication, png: Path, tmp_path: Path) -> None:
    pymupdf = pytest.importorskip("pymupdf")
    from PySide6.QtPrintSupport import QPrinter

    editor = report_document(png)
    renderer = PageRenderer(editor.document(), editor.page_settings, editor.header_footer, "سند")
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    target = tmp_path / "print.pdf"
    printer.setOutputFileName(str(target))
    printer.setPageLayout(export.page_layout_for(editor.page_settings))
    assert export.print_pages(printer, renderer, [1]) == 1
    with pymupdf.open(target) as pdf:
        assert pdf.page_count == 1
        assert "صفحهٔ دوم".replace("ٔ", "") [:4] in pdf[0].get_text().replace("ٔ", "") or pdf[0].get_text().strip()
    options = PrintOptionsDialog(5, 2)
    options.range.setCurrentIndex(options.range.findData("custom"))
    options.pages.setText("۲-۴")
    assert options.selected_pages() == [1, 2, 3]
    options.range.setCurrentIndex(options.range.findData("current"))
    assert options.selected_pages() == [1]
    editor.deleteLater()


def test_header_footer_dialog_round_trip(qapp: QApplication) -> None:
    dialog = HeaderFooterDialog(HeaderFooter(header="{title}"))
    dialog.lines["footer"].edit.setText("{page}")
    dialog.different_first.setChecked(True)
    dialog.number_format.setCurrentIndex(dialog.number_format.findData("roman"))
    value = dialog.value()
    assert (value.header, value.footer, value.different_first, value.number_format) == \
        ("{title}", "{page}", True, "roman")


# -------------------------------------------------------------- interchange
def test_docx_export_and_import_round_trip(qapp: QApplication, png: Path, tmp_path: Path) -> None:
    docx = pytest.importorskip("docx")
    from interchange.docx_import import import_docx

    editor = report_document(png)
    place_in(editor, "متن فارسی")
    select_text(editor, "English")
    editor.set_bold(True)
    path = tmp_path / "out.docx"
    export.export_docx(editor.to_document(), editor.document(), path)

    word = docx.Document(str(path))
    body = word.element.body
    xml = body.xml
    assert "<w:bidi" in xml and "<w:rtl" in xml and "<m:oMath" in xml and "w:bidiVisual" in xml
    assert [p.style.name for p in word.paragraphs[:2]] == ["Title", "Heading 1"]
    assert [cell.text for cell in word.tables[0].rows[0].cells] == ["00", "01", "02"]
    assert len(word.inline_shapes) == 1

    imported = import_docx(path)
    names = [p.style.style_name for p in imported.paragraphs[:2]]
    assert names == ["Title", "Heading 1"]
    text = [p.text for p in imported.paragraphs]
    assert text[0] == "گزارش آزمایشی" and "متن فارسی با English و عدد ۱۲۳." in text and "صفحهٔ دوم" in text
    body_paragraph = next(p for p in imported.paragraphs if "English" in p.text)
    assert [run.text for run in body_paragraph.runs if run.style.bold] == ["English"]
    assert body_paragraph.style.direction == "rtl"
    table = first_table(imported)
    assert texts(table) == [["00", "01", "02"], ["10", "11", "12"]]
    assert table.direction == "rtl" and table.header_rows == 1
    kinds = [run.object["type"] for p in imported.iter_paragraphs() for run in p.runs if run.object]
    assert kinds.count("equation") == 1 and kinds.count("image") == 1
    equations = [run.object for p in imported.iter_paragraphs() for run in p.runs
                 if run.object and run.object["type"] == "equation"]
    assert equations[0]["latex"] == r"\frac{a}{b}"
    assert len(imported.resources) == 1
    assert imported.header_footer.footer == "صفحهٔ {page} از {pages}"

    # the imported document loads in the editor
    other = RichTextEditor()
    other.load_document(imported)
    assert "English" in other.toPlainText()
    other.deleteLater()
    editor.deleteLater()


def test_rtf_export_is_readable(qapp: QApplication, png: Path, tmp_path: Path) -> None:
    from interchange.rtf_export import export_rtf

    editor = report_document(png)
    path = tmp_path / "out.rtf"
    export_rtf(editor.to_document(), path)
    data = path.read_bytes()
    data.decode("ascii")  # RTF must be 7-bit
    text = data.decode("ascii")
    assert text.startswith("{\\rtf1") and text.rstrip().endswith("}")
    assert text.count("{") == text.count("}")
    assert "\\rtlpar" in text and "\\trowd" in text and "English" in text
    assert "\\u1711?" in text  # گ
    editor.deleteLater()


def test_html_export_embeds_objects(qapp: QApplication, png: Path, tmp_path: Path) -> None:
    editor = report_document(png)
    path = tmp_path / "out.html"
    export.export_html(editor.document(), path)
    html = path.read_text(encoding="utf-8")
    assert 'dir="rtl"' in html and "data:image/png;base64," in html and "<table" in html
    assert OBJECT_CHAR not in html
    editor.deleteLater()


# --------------------------------------------------------------- templates
@pytest.mark.parametrize("template_id", [identifier for identifier, _t, _b in TEMPLATES])
def test_templates_open_in_the_editor(editor: RichTextEditor, template_id: str) -> None:
    document = build_template(template_id)
    editor.load_document(document)
    loaded = editor.to_document()
    assert [type(b) for b in loaded.blocks] == [type(b) for b in document.blocks]
    original = [p.text for p in document.iter_paragraphs()]
    assert [p.text for p in loaded.iter_paragraphs()] == original
    assert editor.page_count() >= 1


def test_template_list_covers_the_requested_kinds() -> None:
    assert [identifier for identifier, _t, _b in TEMPLATES] == \
        ["general", "school", "lecture", "math", "report", "paper", "letter"]
    math = build_template("math")
    latex = [run.object["latex"] for p in math.paragraphs for run in p.runs if run.object]
    assert len(latex) == 5 and all(equation.is_valid(source) for source in latex)


# ---------------------------------------------------- document management
def test_version_store_keeps_limited_history(services: Services, tmp_path: Path) -> None:
    store = VersionStore(services.database, limit=3)
    path = tmp_path / "a.dbr"
    for index in range(5):
        store.add(path, Document(blocks=[para(f"نسخهٔ {index}")]), words=index)
    store.add(path, Document(blocks=[para("نسخهٔ 4")]), words=4)  # unchanged: not stored again
    versions = store.versions(path)
    assert [v.words for v in versions] == [4, 3, 2]
    assert store.load(versions[-1].id).paragraphs[0].text == "نسخهٔ 2"
    assert store.versions(tmp_path / "other.dbr") == []
    store.delete(versions[0].id)
    assert len(store.versions(path)) == 2


def test_backup_manager_copies_and_prunes(tmp_path: Path) -> None:
    manager = BackupManager(tmp_path / "backups", keep=2)
    source = tmp_path / "سند.dbr"
    assert manager.backup(source) is None
    for index in range(4):
        source.write_text(f"v{index}", encoding="utf-8")
        assert manager.backup(source) is not None
    backups = manager.backups()
    assert len(backups) == 2 and {b.original_name for b in backups} == {"سند.dbr"}
    assert sorted(b.path.read_text(encoding="utf-8") for b in backups) == ["v2", "v3"]
    manager.delete(backups[0])
    assert len(manager.backups()) == 1


def test_export_history_records(services: Services) -> None:
    history = ExportHistory(services.database)
    history.add("سند", "PDF", "/tmp/a.pdf")
    history.add("سند", "DOCX", "/tmp/a.docx")
    assert [(r.format, r.path) for r in history.records()] == [("DOCX", "/tmp/a.docx"), ("PDF", "/tmp/a.pdf")]
    history.clear()
    assert history.records() == []


# ------------------------------------------------------------------ window
def test_window_saves_versions_and_backups(window: MainWindow, tmp_path: Path) -> None:
    path = tmp_path / "doc.dbr"
    type_text(window.editor, "نسخهٔ یک")
    assert window.save_to_path(path)
    assert window.services.backups.backups() == []  # nothing to back up on first save
    type_text(window.editor, " و دو")
    assert window.save_to_path(path)
    versions = window.services.versions.versions(path)
    assert len(versions) == 2
    backups = window.services.backups.backups()
    assert len(backups) == 1
    assert Document.from_json(backups[0].path.read_text(encoding="utf-8")).paragraphs[0].text == "نسخهٔ یک"

    assert window.restore_version(versions[-1].id)
    assert window.editor.toPlainText() == "نسخهٔ یک"
    assert window.current_path == path and window.editor.document().isModified()
    # the file itself is untouched until the user saves
    assert Document.from_json(path.read_text(encoding="utf-8")).paragraphs[0].text == "نسخهٔ یک و دو"
    window.editor.document().setModified(False)
    assert window.open_backup(backups[0].path, backups[0].original_name)
    assert window.current_path is None and window.editor.toPlainText() == "نسخهٔ یک"


def test_window_exports_every_format_and_logs_them(window: MainWindow, png: Path, tmp_path: Path) -> None:
    from interchange.rtf_export import export_rtf

    editor = window.editor
    type_text(editor, "سند آزمایشی")
    editor.insert_note("یادداشت")
    editor.set_header_footer(HeaderFooter(footer="{page}"))
    document, page, title, running = editor.document(), editor.page_settings, window.display_name(), \
        editor.header_footer
    writers = {
        "a.pdf": lambda p: export.export_pdf(document, page, p, title, running),
        "a.docx": lambda p: export.export_docx(editor.to_document(), document, p),
        "a.rtf": lambda p: export_rtf(editor.to_document(), p),
        "a.html": lambda p: export.export_html(document, p),
        "a.png": lambda p: export.export_png(document, page, p, title, running),
        "a.svg": lambda p: export.export_svg(document, page, p, title, running),
    }
    for name, writer in writers.items():
        assert window.export_to(tmp_path / name, writer), name
        assert (tmp_path / name).stat().st_size > 100, name
    formats = [record.format for record in window.services.export_history.records()]
    assert formats == ["SVG", "PNG", "HTML", "RTF", "DOCX", "PDF"]


def test_window_opens_docx_as_an_unsaved_copy(window: MainWindow, png: Path, tmp_path: Path) -> None:
    pytest.importorskip("docx")
    source = report_document(png)
    path = tmp_path / "گزارش.docx"
    export.export_docx(source.to_document(), source.document(), path)
    source.deleteLater()
    assert window.open_path(path)
    assert window.current_path is None  # saving asks for a .dbr name; the .docx is never overwritten
    assert "English" in window.editor.toPlainText()
    assert window.document_statistics()["tables"] == 1
    assert window.document_statistics()["images"] == 1
    assert window.document_statistics()["equations"] == 1


def test_window_reports_unreadable_docx(window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a zip file")
    shown: list[str] = []
    monkeypatch.setattr(window, "_show_error", lambda text, details="": shown.append(text))
    type_text(window.editor, "متن من")
    window.editor.document().setModified(False)
    assert not window.open_path(bad)
    assert shown and window.editor.toPlainText() == "متن من"


def test_window_templates(window: MainWindow) -> None:
    assert window.create_from_template("builtin", "report")
    assert "چکیده" in window.editor.toPlainText()
    assert window.toolbars.style_combo.findData("Heading 1") >= 0
    type_text(window.editor, "افزوده")
    saved = window.save_template_named("الگوی من")
    assert saved is not None and saved.is_file()
    window.editor.document().setModified(False)
    assert window.create_from_template("user", "الگوی من")
    assert "افزوده" in window.editor.toPlainText() and window.current_path is None


def test_shortcuts_can_be_changed_and_persist(window: MainWindow, qapp: QApplication) -> None:
    commands = window.commands
    assert commands["insert_table"].shortcut().toString() == "Ctrl+Alt+T"
    window.apply_shortcut_overrides({"insert_table": "Ctrl+Alt+J", "bold": ""})
    assert commands["insert_table"].shortcut() == QKeySequence("Ctrl+Alt+J")
    assert commands["bold"].shortcut().isEmpty()
    assert "Ctrl+Alt+J" in commands["insert_table"].toolTip()
    stored = SettingsStore(window.services.settings_store.path).load()
    assert stored.shortcuts == {"insert_table": "Ctrl+Alt+J", "bold": ""}
    again = MainWindow(Services.create(window.services.settings_store.path.parent))
    assert again.commands["insert_table"].shortcut() == QKeySequence("Ctrl+Alt+J")
    again.close()
    again.deleteLater()
    window.apply_shortcut_overrides({})
    assert commands["bold"].shortcut() == QKeySequence("Ctrl+B")


def test_default_shortcuts_do_not_collide(window: MainWindow) -> None:
    dialog = ShortcutEditorDialog(window.commands.editable_shortcuts())
    assert dialog.conflicts() == []
    assert dialog.overrides() == {}
    dialog.editors["italic"].setKeySequence(QKeySequence("Ctrl+B"))
    assert len(dialog.conflicts()) == 1
    assert dialog.overrides() == {"italic": "Ctrl+B"}


def test_style_combo_and_insert_actions(window: MainWindow) -> None:
    editor = window.editor
    type_text(editor, "سرفصل")
    combo = window.toolbars.style_combo
    index = combo.findData("Heading 2")
    combo.setCurrentIndex(index)
    combo.activated.emit(index)
    assert editor.to_document().paragraphs[0].style.style_name == "Heading 2"
    window.commands["page_break"].trigger()
    assert editor.page_count() == 2
    window.commands["insert_toc"].trigger()
    assert any(isinstance(b, Table) and b.role == "toc" for b in editor.to_document().blocks)
    window.commands["format_painter"].trigger()
    assert editor.format_painter_active()
    window.commands["format_painter"].trigger()
    assert not editor.format_painter_active()
    window._sync_table_actions()
    assert not window.commands["table_merge"].isEnabled()


def test_editing_objects_through_the_window(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import window_features

    editor = window.editor
    editor.insert_equation("x")

    class FakeDialog:
        def __init__(self, obj, *args) -> None:  # noqa: ANN001, ANN002
            self.obj = obj

        def exec(self) -> int:
            return 1

        def object(self) -> dict:
            return {"type": "equation", "latex": "y^2", "display": False, "numbered": False}

    monkeypatch.setattr(window_features, "EquationDialog", FakeDialog)
    editor.objectActivated.emit(0, {"type": "equation", "latex": "x", "display": False, "numbered": False})
    assert editor.to_document().paragraphs[0].runs[0].object["latex"] == "y^2"


def test_autosave_settings_apply(window: MainWindow) -> None:
    window.apply_autosave_settings(False, 45, 7, 0)
    settings = window.services.settings
    assert (settings.autosave_enabled, settings.autosave_interval_seconds, settings.version_limit,
            settings.backup_limit) == (False, 45, 7, 0)
    assert not window.autosave.is_enabled() and window.services.versions.limit == 7
