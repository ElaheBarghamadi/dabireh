"""Main-window behaviour: toolbar wiring and sync, dialogs, export, rendering."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolButton

from app.main_window import MainWindow
from core.document import PageSettings, ParagraphStyle
from editor.shortcuts import SHORTCUTS
from editor.text_editor import RichTextEditor
from editor.toolbar import ACTION_SPECS
from tests.conftest import DATA_DIR, select, select_text, type_text
from ui.dialogs.document_dialog import DocumentDialog
from ui.dialogs.page_setup_dialog import PageSetupDialog
from ui.dialogs.paragraph_dialog import ParagraphDialog


def test_interface_is_persian_and_right_to_left(window: MainWindow, qapp: QApplication) -> None:
    assert qapp.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert qapp.font().family() == "Vazirmatn"
    menus = [action.text() for action in window.menuBar().actions()]
    assert menus == ["پرونده", "ویرایش", "درج", "جدول", "قالب", "بند", "ابزار فارسی", "نمایش", "راهنما"]


def test_every_command_is_connected_and_reachable(window: MainWindow) -> None:
    reachable = {a for menu in window.menuBar().actions() for a in menu.menu().actions()}
    for menu_action in list(reachable):
        if menu_action.menu():
            reachable.update(menu_action.menu().actions())
    for spec in ACTION_SPECS:
        action = window.commands[spec.id]
        assert action in reachable, spec.id
        connected = action.receivers("2triggered(bool)") + action.receivers("2toggled(bool)")
        assert connected > 0, f"{spec.id} does nothing"
    shortcuts = [window.commands[action_id].shortcut().toString() for action_id in SHORTCUTS]
    assert len(set(shortcuts)) == len(shortcuts)  # no two commands share a shortcut


def test_toolbar_buttons_trigger_formatting(window: MainWindow) -> None:
    editor = window.editor
    type_text(editor, "متن آزمایشی")
    select_text(editor, "آزمایشی")
    for action_id in ("bold", "italic", "underline", "strike"):
        button = window.toolbars.main_toolbar.widgetForAction(window.commands[action_id])
        assert isinstance(button, QToolButton)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    style = editor.to_document().paragraphs[0].runs[-1].style
    assert style.bold and style.italic and style.underline and style.strike

    QTest.mouseClick(
        window.toolbars.paragraph_toolbar.widgetForAction(window.commands["align_center"]), Qt.MouseButton.LeftButton
    )
    QTest.mouseClick(
        window.toolbars.paragraph_toolbar.widgetForAction(window.commands["bullet"]), Qt.MouseButton.LeftButton
    )
    paragraph = editor.to_document().paragraphs[0]
    assert paragraph.style.alignment == "center" and paragraph.list.style == "bullet"


def test_font_controls_apply_to_selection(window: MainWindow) -> None:
    editor = window.editor
    type_text(editor, "متن English")
    select_text(editor, "English")
    window.toolbars.font_combo.textActivated.emit("DejaVu Serif")
    window.toolbars.size_combo.textActivated.emit("۱۸")  # Persian digits are accepted
    window.toolbars.color_button.color_selected.emit(QColor("#1f5fbf"))
    window.toolbars.highlight_button.color_selected.emit(QColor("#fff59d"))
    style = editor.to_document().paragraphs[0].runs[-1].style
    assert (style.font_family, style.font_size, style.color, style.highlight) == ("DejaVu Serif", 18, "#1f5fbf", "#fff59d")
    window.toolbars.highlight_button.color_selected.emit(None)
    assert editor.to_document().paragraphs[0].runs[-1].style.highlight is None


def test_toolbar_follows_the_cursor(window: MainWindow, qapp: QApplication) -> None:
    editor = window.editor
    type_text(editor, "عادی پررنگ\nEnglish line")
    select_text(editor, "پررنگ")
    editor.set_bold(True)
    editor.set_font_size(20)
    select(editor, editor.toPlainText().index("English"), editor.toPlainText().index("English"))
    editor.set_direction("ltr")
    editor.set_alignment("justify")
    editor.set_line_spacing(1.5)
    commands = window.commands

    select(editor, 8, 8)  # inside the bold word, first (RTL) paragraph
    assert commands["bold"].isChecked() and commands["align_right"].isChecked() and commands["dir_rtl"].isChecked()
    assert window.toolbars.size_combo.currentText() == "20"
    assert window.toolbars.font_combo.currentFont().family() == "Vazirmatn"
    assert window.direction_label.text() == "راست‌به‌چپ"

    select(editor, 14, 14)  # second paragraph
    assert not commands["bold"].isChecked()
    assert commands["align_justify"].isChecked() and commands["dir_ltr"].isChecked()
    assert commands["spacing_1.5"].isChecked()
    assert window.toolbars.size_combo.currentText() == "13"
    assert window.direction_label.text() == "چپ‌به‌راست"


def test_keyboard_shortcuts_reach_the_editor(window: MainWindow, qapp: QApplication) -> None:
    editor = window.editor
    window.activateWindow()
    editor.setFocus()
    type_text(editor, "متن")
    editor.selectAll()
    control = Qt.KeyboardModifier.ControlModifier
    QTest.keyClick(editor, Qt.Key.Key_B, control)
    QTest.keyClick(editor, Qt.Key.Key_E, control)
    qapp.processEvents()
    paragraph = editor.to_document().paragraphs[0]
    assert paragraph.runs[0].style.bold and paragraph.style.alignment == "center"
    QTest.keyClick(editor, Qt.Key.Key_Z, control)
    assert editor.to_document().paragraphs[0].style.alignment == "start"


def test_status_bar_statistics(window: MainWindow) -> None:
    type_text(window.editor, "یک دو سه")
    window._update_statistics()
    assert window.words_label.text().startswith("۳ واژه")
    assert window.page_label.text() == "صفحهٔ ۱ از ۱"


def test_find_bar_replaces_text(window: MainWindow) -> None:
    type_text(window.editor, "سیب و سیب")
    window.commands["replace"].trigger()
    assert window.find_bar.isVisible() and window.find_bar.replace_edit.isVisible()
    window.find_bar.find_edit.setText("سیب")
    window.find_bar.replace_edit.setText("انار")
    window.find_bar.replace_all()
    assert window.editor.toPlainText() == "انار و انار"
    assert "۲" in window.find_bar.status_label.text()
    window.find_bar.close_bar()
    assert not window.find_bar.isVisible()


def test_dialogs_return_edited_values(qapp: QApplication) -> None:
    paragraph = ParagraphDialog(ParagraphStyle(alignment="end", direction="auto"), default_is_rtl=True)
    assert paragraph.alignment_combo.currentData() == "left"
    paragraph.direction_combo.setCurrentIndex(paragraph.direction_combo.findData("ltr"))
    paragraph.first_line.setValue(10)
    result = paragraph.paragraph_style()
    assert (result.direction, result.alignment) == ("ltr", "start")  # still visually left
    assert result.first_line_indent == pytest.approx(28.35, abs=0.01)

    page = PageSetupDialog(PageSettings())
    page.size_combo.setCurrentIndex(page.size_combo.findData("A5"))
    page.orientation_combo.setCurrentIndex(page.orientation_combo.findData("landscape"))
    page.margin_top.setValue(12)
    assert page.page_settings() == PageSettings(size="A5", orientation="landscape", margin_top=12)

    editor = RichTextEditor()
    dialog = DocumentDialog(editor.metadata, editor.defaults, (1, 2, 3), "")
    dialog.title_edit.setText("  گزارش  ")
    dialog.direction_combo.setCurrentIndex(dialog.direction_combo.findData("auto"))
    assert dialog.metadata().title == "گزارش" and dialog.defaults().direction == "auto"
    assert dialog.defaults() == type(editor.defaults)(direction="auto")  # uninstalled fonts (Cambria) are kept
    editor.deleteLater()


def test_exports(window: MainWindow, tmp_path: Path) -> None:
    from editor.export import export_html, export_pdf

    assert window.open_path(DATA_DIR / "sample_document.dbr")
    pdf = tmp_path / "out.pdf"
    export_pdf(window.editor.document(), window.editor.page_settings, pdf, "آزمون")
    assert pdf.read_bytes().startswith(b"%PDF") and pdf.stat().st_size > 5000
    html = tmp_path / "out.html"
    export_html(window.editor.document(), html)
    assert "واژه‌پرداز" in html.read_text(encoding="utf-8")
    assert not window.editor.document().isModified()  # exporting does not touch the document


# Automated visual checks (rendered pixels) -------------------------------------------
def _ink_columns(editor: RichTextEditor, qapp: QApplication) -> list[int]:
    """X coordinates (page-relative) of the dark pixels drawn in the page."""
    qapp.processEvents()
    image = editor.viewport().grab().toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    columns = []
    for x in range(0, image.width(), 2):
        if any(image.pixelColor(x, y).lightness() < 110 for y in range(0, image.height(), 2)):
            columns.append(x)
    return columns


def test_rendered_text_sits_on_the_correct_side(editor: RichTextEditor, qapp: QApplication) -> None:
    geometry = editor.page_geometry
    type_text(editor, "سلام دنیا")
    rtl = _ink_columns(editor, qapp)
    assert rtl, "nothing was drawn"
    assert min(rtl) > geometry.width / 2  # Persian paragraph hugs the right margin
    assert max(rtl) <= geometry.width - geometry.margin_right + 2

    editor.set_direction("ltr")
    ltr = _ink_columns(editor, qapp)
    assert max(ltr) < geometry.width / 2 and min(ltr) >= geometry.margin_left - 2

    editor.set_alignment("center")
    centered = _ink_columns(editor, qapp)
    assert abs((min(centered) + max(centered)) / 2 - geometry.width / 2) < 12


def test_window_renders_at_several_sizes(window: MainWindow, qapp: QApplication, tmp_path: Path) -> None:
    assert window.open_path(DATA_DIR / "sample_document.dbr")
    for width, height in ((1440, 900), (1024, 700), (640, 480)):
        window.resize(width, height)
        qapp.processEvents()
        image = window.grab().toImage()
        assert (image.width(), image.height()) == (width, height)
        assert window.editor.viewport().width() > 200  # the page stays usable
        colours = {image.pixelColor(x, y).name() for x in range(0, width, 40) for y in range(0, height, 40)}
        assert len(colours) > 3  # not a blank frame


def test_theme_switching_preserves_document_and_persists(window: MainWindow, qapp: QApplication) -> None:
    from PySide6.QtGui import QPalette
    from ui.theme import THEMES

    type_text(window.editor, "سلام دبیره")
    before = window.editor.to_document()
    modified = window.editor.document().isModified()
    for name in ("dark", "warm", "light"):
        window.theme_actions[name].trigger()
        qapp.processEvents()
        colors = THEMES[name][1]
        assert qapp.palette().color(QPalette.ColorRole.Window).name() == colors.chrome
        assert window.editor.palette().color(QPalette.ColorRole.Window).name() == colors.workspace
        assert window.editor.palette().color(QPalette.ColorRole.Text).name() == "#1f2430"
        assert window.theme_actions[name].isChecked()
        assert window.services.settings_store.load().theme == name
        assert window.editor.to_document() == before
        assert window.editor.document().isModified() == modified


def test_saved_theme_is_applied_when_window_opens(qapp: QApplication, services) -> None:
    from PySide6.QtGui import QPalette
    from ui.theme import THEMES, apply_theme

    services.settings.theme = "dark"
    window = MainWindow(services)
    try:
        assert window.theme_actions["dark"].isChecked()
        assert qapp.palette().color(QPalette.ColorRole.Window).name() == THEMES["dark"][1].chrome
        assert window.editor.viewport().palette().color(QPalette.ColorRole.Base).name() == "#ffffff"
    finally:
        window.close()
        window.deleteLater()
        apply_theme(qapp)


def test_view_menu_can_restore_hidden_toolbars(window: MainWindow, qapp: QApplication) -> None:
    toolbar = window.toolbars.paragraph_toolbar
    toolbar.toggleViewAction().trigger()
    qapp.processEvents()
    assert toolbar.isHidden()
    toolbar.toggleViewAction().trigger()
    qapp.processEvents()
    assert toolbar.isVisible()


def test_invalid_theme_setting_falls_back_to_light(services) -> None:
    services.settings.theme = "unknown"
    services.settings_store.save(services.settings)
    assert services.settings_store.load().theme == "light"
