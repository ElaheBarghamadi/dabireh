"""Phase 2 commands of the main window: insert, tables, references, printing,
interchange formats, templates, versions, backups and shortcut settings."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import QColorDialog, QDialog, QFileDialog, QInputDialog, QMenu

from core.document import Document, DocumentFormatError
from core.persian import format_number
from core.templates import TEMPLATES, build_template
from editor import export
from editor.formatting import document_statistics
from editor.objects import OBJECT_CHAR, image_to_png_bytes, object_from_format
from editor.page_render import PageRenderer
from editor.qt_bridge import style_from_block
from storage.document_repository import write_text_atomically
from ui.dialogs.canvas_dialog import CanvasDialog
from ui.dialogs.drawing_dialog import DrawingDialog
from ui.dialogs.insert_dialogs import (
    IMAGE_FILTER,
    CaptionDialog,
    CrossReferenceDialog,
    EquationDialog,
    ImageDialog,
    InsertTableDialog,
    LinkDialog,
    ShapeDialog,
    TablePropertiesDialog,
)
from ui.dialogs.layout_dialogs import CharacterSpacingDialog, HeaderFooterDialog, PrintOptionsDialog, StylesDialog
from ui.dialogs.manage_dialogs import (
    AutosaveSettingsDialog,
    RecordsDialog,
    ShortcutEditorDialog,
    StatisticsDialog,
    TemplateDialog,
)

logger = logging.getLogger(__name__)

TEMPLATE_EXTENSION = ".dbrt"
TABLE_ACTIONS = ("table_row_above", "table_row_below", "table_col_before", "table_col_after", "table_delete_row",
                 "table_delete_col", "table_delete", "table_merge", "table_split", "table_cell_color",
                 "table_cell_no_color", "table_valign_top", "table_valign_middle", "table_valign_bottom",
                 "table_properties")


def _local_time(iso: str) -> str:
    return iso.replace("T", "  ")[:20]


class WindowFeatures:
    """Mixin for ``MainWindow``; relies on its ``editor``, ``commands``, ``services`` and helpers."""

    # ----------------------------------------------------------------- menus
    def _build_feature_menus(self, insert_menu: QMenu, table_menu: QMenu) -> None:
        self._add(insert_menu, "insert_table", "insert_image", "insert_shape", "insert_canvas", "drawing_studio", "insert_equation", None,
                  "insert_link", "remove_link", "insert_bookmark", "go_to_bookmark", "insert_crossref", None,
                  "insert_caption", "insert_note", None)
        lists = insert_menu.addMenu("فهرست‌های خودکار")
        self._add(lists, "insert_toc", "insert_lof", "insert_lot", None, "update_fields")
        self._add(insert_menu, None, "page_break", "header_footer", None, "object_properties")
        shapes = insert_menu.addMenu("گروه شکل‌ها")
        self._add(shapes, "group_shapes", "ungroup_shapes", "shape_to_front", "shape_to_back")
        self._add(table_menu, "insert_table", None, "table_row_above", "table_row_below", "table_col_before",
                  "table_col_after", None, "table_delete_row", "table_delete_col", "table_delete", None,
                  "table_merge", "table_split", None, "table_cell_color", "table_cell_no_color",
                  "table_valign_top", "table_valign_middle", "table_valign_bottom", None, "table_properties")
        table_menu.aboutToShow.connect(self._sync_table_actions)

    def _sync_table_actions(self) -> None:
        inside = self.editor.in_table()
        for action_id in TABLE_ACTIONS:
            self.commands[action_id].setEnabled(inside)

    def _feature_handlers(self) -> dict[str, Any]:
        return {
            "new_template": self.new_from_template,
            "save_template": self.save_as_template,
            "export_docx": self.export_docx,
            "export_rtf": self.export_rtf,
            "export_png": self.export_png,
            "export_svg": self.export_svg,
            "print": self.print_document,
            "print_preview": self.print_preview,
            "versions": self.show_versions,
            "backups": self.show_backups,
            "export_history": self.show_export_history,
            "autosave_settings": self.show_autosave_settings,
            "statistics": self.show_statistics,
            "go_to_page": self.go_to_page,
            "update_fields": self.update_fields,
            "char_spacing": self.show_character_spacing,
            "styles": self.show_styles,
            "insert_table": self.insert_table,
            "insert_image": self.insert_image,
            "insert_shape": self.insert_shape,
            "insert_canvas": self.insert_canvas,
            "drawing_studio": self.open_drawing_studio,
            "insert_equation": self.insert_equation,
            "insert_link": self.insert_link,
            "insert_bookmark": self.insert_bookmark,
            "go_to_bookmark": self.go_to_bookmark,
            "insert_crossref": self.insert_cross_reference,
            "insert_caption": self.insert_caption,
            "insert_note": self.insert_note,
            "header_footer": self.show_header_footer,
            "object_properties": self.edit_selected_object,
            "table_cell_color": self.choose_cell_color,
            "table_properties": self.show_table_properties,
            "customize_shortcuts": self.customize_shortcuts,
        }

    def _connect_feature_signals(self) -> None:
        self.editor.objectActivated.connect(self.edit_object)
        self.editor.marginActivated.connect(self.show_header_footer)

    def _message(self, text: str, timeout: int = 5000) -> None:
        self.statusBar().showMessage(text, timeout)

    # ---------------------------------------------------------------- insert
    def insert_table(self) -> None:
        dialog = InsertTableDialog(self.editor.defaults.direction != "ltr", self)
        if dialog.exec():
            rows, columns, header_rows, direction = dialog.values()
            self.editor.insert_table(rows, columns, header_rows=header_rows, direction=direction)

    def show_table_properties(self) -> None:
        table = self.editor.table_properties()
        if table is None:
            self._message("مکان‌نما درون جدول نیست.")
            return
        dialog = TablePropertiesDialog(table, self)
        if dialog.exec():
            self.editor.set_table_properties(dialog.table())

    def choose_cell_color(self) -> None:
        if not self.editor.in_table():
            return
        color = QColorDialog.getColor(QColor("#eef2f8"), self, "رنگ زمینهٔ خانه")
        if color.isValid():
            self.editor.table_command("cell_background", color)

    def insert_image(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "درج تصویر", self._start_directory(), IMAGE_FILTER)
        if name:
            self.insert_image_path(Path(name))

    def insert_image_path(self, path: Path) -> bool:
        try:
            obj = self.editor.insert_image_file(path)
        except OSError as error:
            self._show_error("تصویر خوانده نشد.", str(error))
            return False
        if obj is None:
            self._show_error("این پرونده یک تصویر پشتیبانی‌شده نیست.", str(path))
            return False
        self._message("برای تنظیم اندازه و جای تصویر، روی آن دوبار کلیک کنید یا «ویژگی‌های شیء» را بزنید.", 8000)
        return True

    def open_drawing_studio(self) -> None:
        dialog = DrawingDialog(self)
        if dialog.exec() and dialog.inserted_image is not None:
            self.editor.insert_image_data(image_to_png_bytes(dialog.inserted_image), "png")
            self._message("نقاشی به صورت تصویر در سند درج شد.", 5000)

    def insert_canvas(self) -> None:
        geometry = self.editor.page_geometry
        width = max(40.0, min(520.0, geometry.content_width - 12))
        height = max(40.0, min(300.0, geometry.content_height - 24))
        dialog = CanvasDialog(parent=self, width=width, height=height)
        if dialog.exec():
            self.editor.insert_layout_canvas(dialog.object())
            self._message("برای ویرایش چیدمان، روی آن دوبار کلیک کنید.", 8000)

    def insert_shape(self) -> None:
        dialog = ShapeDialog(None, self)
        if dialog.exec():
            self.editor.insert_object(dialog.object())

    def insert_equation(self) -> None:
        dialog = EquationDialog(None, self.editor.defaults.math_font, self)
        if dialog.exec():
            obj = dialog.object()
            self.editor.insert_equation(obj["latex"], display=obj["display"], numbered=obj["numbered"])

    def insert_note(self) -> None:
        text, ok = QInputDialog.getMultiLineText(self, "پی‌نوشت", "متن پی‌نوشت:")
        if ok and text.strip():
            self.editor.insert_note(text.strip())

    def insert_caption(self) -> None:
        dialog = CaptionDialog("table" if self.editor.in_table() else "figure", self)
        if dialog.exec():
            kind, text = dialog.values()
            self.editor.insert_caption(kind, text)

    def insert_link(self) -> None:
        cursor = self.editor.textCursor()
        current = cursor.charFormat().anchorHref() if cursor.charFormat().isAnchor() else ""
        dialog = LinkDialog(cursor.selectedText(), current, self.editor.bookmarks(), cursor.hasSelection(), self)
        if dialog.exec():
            target, text = dialog.values()
            if not target:
                self.editor.remove_hyperlink()
            elif not self.editor.set_hyperlink(target, text):
                self._message("برای ساختن پیوند، متنی را انتخاب کنید یا متن پیوند را بنویسید.")

    def insert_bookmark(self) -> None:
        name, ok = QInputDialog.getText(self, "نشانک", "نام نشانک:")
        if ok and name.strip() and not self.editor.add_bookmark(name.strip()):
            self._message("نشانک ساخته نشد (نام تکراری یا نامعتبر).")

    def go_to_bookmark(self) -> None:
        names = self.editor.bookmarks()
        if not names:
            self._message("این سند نشانکی ندارد.")
            return
        name, ok = QInputDialog.getItem(self, "رفتن به نشانک", "نشانک:", names, 0, False)
        if ok and name:
            self.editor.go_to_bookmark(name)

    def insert_cross_reference(self) -> None:
        targets = self.editor.reference_targets()
        if not targets:
            self._message("هنوز سرفصل، شرح یا نشانکی برای ارجاع وجود ندارد.")
            return
        dialog = CrossReferenceDialog(targets, self)
        if dialog.exec() and dialog.selection():
            kind, label, target, with_page = dialog.selection()
            self.editor.insert_cross_reference(kind, label, target, with_page=with_page)

    def update_fields(self) -> None:
        result = self.editor.update_fields()
        self._message(f"به‌روزرسانی شد — شرح‌ها: {format_number(result.get('captions', 0))}، "
                      f"پی‌نوشت‌ها: {format_number(result.get('notes', 0))}، "
                      f"فهرست‌ها: {format_number(result.get('lists', 0))}")

    def go_to_page(self) -> None:
        pages = self.editor.page_count()
        page, ok = QInputDialog.getInt(self, "رفتن به صفحه", f"شمارهٔ صفحه (۱ تا {format_number(pages)}):",
                                       self.editor.cursor_page(), 1, pages)
        if ok:
            self.editor.go_to_page(page)

    # --------------------------------------------------------------- objects
    def edit_selected_object(self) -> None:
        selected = self.editor.selected_object()
        if selected is None:
            self._message("ابتدا یک تصویر، شکل، معادله یا پی‌نوشت را انتخاب کنید (یا روی آن دوبار کلیک کنید).")
            return
        self.edit_object(*selected)

    def edit_object(self, position: int, obj: dict[str, Any]) -> None:
        kind = obj.get("type")
        if kind == "image":
            obj = dict(obj)
            if obj.get("wrap") == "block":
                block = self.editor.document().findBlock(position)
                alignment = style_from_block(block).alignment
                rtl = block.textDirection() == Qt.LayoutDirection.RightToLeft
                obj["block_alignment"] = ("center" if alignment == "center" else
                                          "right" if (alignment == "start") == rtl else "left")
            natural = self.editor.objects.natural_size(str(obj.get("resource", "")))
            size = QSize(int(natural.width()), int(natural.height())) if natural is not None else None
            geometry = self.editor.page_geometry
            dialog = ImageDialog(obj, size, self, handler=self.editor.objects,
                                 page_size=QSize(int(geometry.content_width - 12), int(geometry.content_height - 24)))
            if not dialog.exec():
                return
            updated = dialog.object()
            if dialog.replacement:
                self._replace_image(position, updated, Path(dialog.replacement))
                return
        elif kind == "shape":
            dialog = CanvasDialog(obj, self) if obj.get("layout_canvas") is True else ShapeDialog(obj, self)
            if not dialog.exec():
                return
            updated = dialog.object()
        elif kind == "equation":
            dialog = EquationDialog(obj, self.editor.defaults.math_font, self)
            if not dialog.exec():
                return
            updated = {**obj, **dialog.object()}
        elif kind == "note":
            text, ok = QInputDialog.getMultiLineText(self, "پی‌نوشت", "متن پی‌نوشت:", str(obj.get("text", "")))
            if not ok:
                return
            updated = {**obj, "text": text.strip()}
        else:
            return
        self.editor.replace_object(position, updated)
        if kind in ("note", "equation"):
            self.editor.update_fields()

    def _replace_image(self, position: int, obj: dict[str, Any], path: Path) -> None:
        try:
            data = path.read_bytes()
        except OSError as error:
            self._show_error("تصویر خوانده نشد.", str(error))
            return
        fresh = self.editor.prepare_image_data(data, path.suffix)
        if fresh is None:
            self._show_error("این پرونده یک تصویر پشتیبانی‌شده نیست.", str(path))
            return
        # Validate and load the replacement before touching the existing image.
        self.editor.replace_object(position, {**obj, "resource": fresh["resource"]})

    # ------------------------------------------------------ format and layout
    def show_character_spacing(self) -> None:
        fmt = self.editor.currentCharFormat()
        spacing = fmt.fontLetterSpacing() or 100.0
        scale = float(fmt.fontStretch() or 100)
        underline = None
        if fmt.fontUnderline() or fmt.underlineStyle() != fmt.UnderlineStyle.NoUnderline:
            underline = {fmt.UnderlineStyle.DashUnderline: "dash", fmt.UnderlineStyle.DotLine: "dot",
                         fmt.UnderlineStyle.WaveUnderline: "wave"}.get(fmt.underlineStyle(), "single")
        dialog = CharacterSpacingDialog(spacing, scale, underline, self)
        if dialog.exec():
            new_spacing, new_scale, new_underline = dialog.values()
            cursor = self.editor.textCursor()
            cursor.beginEditBlock()
            if abs(new_spacing - spacing) > 0.01:
                self.editor.set_letter_spacing(new_spacing)
            if abs(new_scale - scale) > 0.01:
                self.editor.set_character_scale(new_scale)
            if new_underline != underline:
                self.editor.set_underline_style(new_underline)
            cursor.endEditBlock()

    def show_styles(self) -> None:
        StylesDialog(self.editor, self).exec()
        self.toolbars.refresh_styles()
        self._sync_format_controls()

    def show_header_footer(self) -> None:
        dialog = HeaderFooterDialog(self.editor.header_footer, self)
        if dialog.exec():
            self.editor.set_header_footer(dialog.value())
            self.editor.document().setModified(True)

    # ---------------------------------------------------------------- export
    def _renderer(self) -> PageRenderer:
        return PageRenderer(self.editor.document(), self.editor.page_settings, self.editor.header_footer,
                            self.display_name())

    def _prepare_output(self) -> None:
        """Bring numbers, notes and generated lists up to date before output."""
        modified = self.editor.document().isModified()
        self.editor.update_fields()
        if not modified:
            self.editor.document().setModified(False)

    def export_docx(self) -> None:
        self._export("برون‌برد Word", "Word (*.docx)", ".docx",
                     lambda path: export.export_docx(self.editor.to_document(), self.editor.document(), path))

    def export_rtf(self) -> None:
        from interchange.rtf_export import export_rtf

        self._export("برون‌برد RTF", "RTF (*.rtf)", ".rtf", lambda path: export_rtf(self.editor.to_document(), path))

    def export_png(self) -> None:
        self._export("برون‌برد تصویر PNG (هر صفحه یک پرونده)", "PNG (*.png)", ".png",
                     lambda path: export.export_png(self.editor.document(), self.editor.page_settings, path,
                                                    self.display_name(), self.editor.header_footer))

    def export_svg(self) -> None:
        self._export("برون‌برد SVG (هر صفحه یک پرونده)", "SVG (*.svg)", ".svg",
                     lambda path: export.export_svg(self.editor.document(), self.editor.page_settings, path,
                                                    self.display_name(), self.editor.header_footer))

    # ----------------------------------------------------------------- print
    def print_document(self) -> None:
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        self._prepare_output()
        renderer = self._renderer()
        options = PrintOptionsDialog(renderer.page_count(), self.editor.cursor_page(), self)
        if not options.exec():
            return
        pages = options.selected_pages()
        if not pages:
            self._show_error("شمارهٔ صفحه‌ها نامعتبر است.", "نمونه: ۱-۳، ۵")
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageLayout(export.page_layout_for(self.editor.page_settings))
        printer.setDocName(self.display_name())
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("چاپ")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            sheets = export.print_pages(printer, renderer, pages, fit_to_paper=options.fit_to_paper(),
                                        scale_percent=options.scale_percent())
        except OSError as error:
            self._show_error("چاپ انجام نشد.", str(error))
            return
        self._message(f"{format_number(sheets)} صفحه برای چاپ فرستاده شد")

    def print_preview(self) -> None:
        from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog

        self._prepare_output()
        renderer = self._renderer()
        printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
        printer.setPageLayout(export.page_layout_for(self.editor.page_settings))
        dialog = QPrintPreviewDialog(printer, self)
        dialog.setWindowTitle("پیش‌نمایش چاپ")
        dialog.resize(900, 700)
        dialog.paintRequested.connect(
            lambda target: export.print_pages(target, renderer, export.pages_from_printer(
                target, renderer.page_count(), self.editor.cursor_page())))
        dialog.exec()

    def render_page_preview(self, index: int = 0, dpi: float = 96.0):  # noqa: ANN201
        """Image of one page exactly as it is exported and printed."""
        return export.render_page_image(self._renderer(), index, dpi)

    # ------------------------------------------------------------- templates
    def _user_templates(self) -> dict[str, Path]:
        directory = self.services.templates_dir
        if not directory.is_dir():
            return {}
        return {path.stem: path for path in sorted(directory.glob(f"*{TEMPLATE_EXTENSION}"))}

    def new_from_template(self) -> None:
        user = self._user_templates()
        dialog = TemplateDialog([(identifier, title) for identifier, title, _builder in TEMPLATES], list(user), self)
        accepted = dialog.exec()
        if dialog.delete_requested:
            user[dialog.delete_requested].unlink(missing_ok=True)
            self._message("الگو حذف شد")
            return
        choice = dialog.choice()
        if accepted and choice:
            self.create_from_template(*choice)

    def create_from_template(self, source: str, identifier: str) -> bool:
        if not self.maybe_save():
            return False
        try:
            if source == "builtin":
                document = build_template(identifier)
                blank = self._blank_document()
                document.defaults, document.page = blank.defaults, blank.page
                document.metadata.author = blank.metadata.author
            else:
                document = Document.from_json(self._user_templates()[identifier].read_text(encoding="utf-8"))
        except (OSError, KeyError, DocumentFormatError) as error:
            self._show_error("الگو باز نشد.", str(error))
            return False
        self._set_document(document, None)
        self.toolbars.refresh_styles()
        return True

    def save_as_template(self) -> None:
        name, ok = QInputDialog.getText(self, "ذخیره به‌عنوان الگو", "نام الگو:", text=self.display_name())
        name = re.sub(r'[\\/:*?"<>|]+', " ", name).strip()
        if ok and name:
            self.save_template_named(name)

    def save_template_named(self, name: str) -> Path | None:
        directory = self.services.templates_dir
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{name}{TEMPLATE_EXTENSION}"
            write_text_atomically(path, self.editor.to_document().to_json())
        except OSError as error:
            self._show_error("الگو ذخیره نشد.", str(error))
            return None
        self._message(f"الگوی «{name}» ذخیره شد")
        return path

    # ------------------------------------------------- versions and backups
    def show_versions(self) -> None:
        if self._path is None:
            self._show_info("نسخه‌ها پس از نخستین ذخیرهٔ سند نگه‌داری می‌شوند.")
            return
        store = self.services.versions
        versions: list = []

        def load() -> list[list[str]]:
            versions[:] = store.versions(self._path)
            return [[_local_time(v.saved_at), v.title or "—", format_number(v.words)] for v in versions]

        def restore(row: int) -> bool:
            return self.restore_version(versions[row].id)

        def delete(row: int) -> str:
            store.delete(versions[row].id)
            return "refresh"

        RecordsDialog("تاریخچهٔ نسخه‌ها", ["زمان ذخیره", "عنوان", "واژه"], load,
                      [("بازگردانی این نسخه", restore), ("حذف", delete)],
                      "هنوز نسخه‌ای از این سند ذخیره نشده است.", self).exec()

    def restore_version(self, version_id: int) -> bool:
        """Load an older version into the editor; the file changes only when the user saves."""
        if not self.maybe_save():
            return False
        document = self.services.versions.load(version_id)
        if document is None:
            return False
        self._set_document(document, self._path, modified=True)
        self.toolbars.refresh_styles()
        self._message("نسخهٔ پیشین بازگردانی شد؛ برای جایگزینی پرونده، ذخیره کنید.", 8000)
        return True

    def show_backups(self) -> None:
        manager = self.services.backups
        backups: list = []

        def load() -> list[list[str]]:
            backups[:] = manager.backups()
            return [[b.original_name, _local_time(b.created_at), f"{format_number(max(1, b.size // 1024))} کیلوبایت"]
                    for b in backups]

        def open_backup(row: int) -> bool:
            return self.open_backup(backups[row].path, backups[row].original_name)

        def delete(row: int) -> str:
            manager.delete(backups[row])
            return "refresh"

        RecordsDialog("پشتیبان‌ها", ["پرونده", "زمان پشتیبان", "اندازه"], load,
                      [("باز کردن پشتیبان", open_backup), ("حذف", delete)],
                      "پشتیبانی وجود ندارد. پیش از هر بازنویسی پرونده، نسخهٔ قبلی اینجا نگه داشته می‌شود.", self).exec()

    def open_backup(self, path: Path, original_name: str) -> bool:
        """Open a backup as an unsaved copy, leaving the original file untouched."""
        if not self.maybe_save():
            return False
        try:
            document = Document.from_json(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, DocumentFormatError) as error:
            self._show_error("این پشتیبان باز نشد.", str(error))
            return False
        if not document.metadata.title:
            document.metadata.title = Path(original_name).stem
        self._set_document(document, None, modified=True)
        self.toolbars.refresh_styles()
        return True

    def show_export_history(self) -> None:
        history = self.services.export_history
        records: list = []

        def load() -> list[list[str]]:
            records[:] = history.records()
            return [[_local_time(r.exported_at), r.format, r.title or "—", r.path] for r in records]

        def clear(_row: int) -> str:
            history.clear()
            return "refresh"

        RecordsDialog("تاریخچهٔ برون‌بردها", ["زمان", "قالب", "سند", "مسیر"], load, [("پاک‌کردن تاریخچه", clear)],
                      "هنوز برون‌بردی انجام نشده است.", self).exec()

    def show_autosave_settings(self) -> None:
        settings = self.services.settings
        dialog = AutosaveSettingsDialog(settings.autosave_enabled, settings.autosave_interval_seconds,
                                        settings.version_limit, settings.backup_limit, self)
        if dialog.exec():
            enabled, interval, versions, backups = dialog.values()
            self.apply_autosave_settings(enabled, interval, versions, backups)

    def apply_autosave_settings(self, enabled: bool, interval: int, versions: int, backups: int) -> None:
        settings = self.services.settings
        settings.autosave_interval_seconds = interval
        settings.version_limit = versions
        settings.backup_limit = backups
        settings.normalise()
        self.autosave.set_interval(settings.autosave_interval_seconds)
        self.services.versions.limit = settings.version_limit
        self.services.backups.keep = settings.backup_limit
        self.commands["autosave_enabled"].setChecked(enabled)  # toggles the controller and the setting
        self.services.settings_store.save(settings)

    # ------------------------------------------------------------ statistics
    def document_statistics(self) -> dict[str, int]:
        document = self.editor.document()
        words, characters = document_statistics(document)
        text = document.toPlainText()
        counts = {"image": 0, "equation": 0}
        tables = 0
        paragraphs = 0
        block = document.begin()
        seen_tables: set[int] = set()
        while block.isValid():
            if block.text().strip(OBJECT_CHAR + " \u200c"):
                paragraphs += 1
            table = QTextCursor(block).currentTable()
            if table is not None:
                seen_tables.add(table.objectIndex())
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                obj = object_from_format(fragment.charFormat()) if OBJECT_CHAR in fragment.text() else None
                if obj and obj.get("type") in counts:
                    counts[obj["type"]] += fragment.text().count(OBJECT_CHAR)
                iterator += 1
            block = block.next()
        tables = len(seen_tables)
        clean = text.replace("\n", "").replace(OBJECT_CHAR, "")
        return {
            "pages": self.editor.page_count(), "paragraphs": paragraphs, "words": words,
            "characters": len(clean), "characters_no_spaces": len(re.sub(r"\s", "", clean)),
            "tables": tables, "images": counts["image"], "equations": counts["equation"],
        }

    def show_statistics(self) -> None:
        StatisticsDialog(self.document_statistics(), self).exec()

    # ------------------------------------------------------------- shortcuts
    def customize_shortcuts(self) -> None:
        dialog = ShortcutEditorDialog(self.commands.editable_shortcuts(), self)
        if dialog.exec():
            self.apply_shortcut_overrides(dialog.overrides())

    def apply_shortcut_overrides(self, overrides: dict[str, str]) -> None:
        self.commands.set_overrides(overrides)
        self.services.settings.shortcuts = self.commands.overrides()
        self.services.settings_store.save(self.services.settings)
        self._message("میان‌برها به‌روز شدند")

    # --------------------------------------------------------- docx and drop
    def import_docx(self, path: Path) -> Document:
        from interchange.docx_import import import_docx

        return import_docx(path, self._blank_document())


__all__ = ["TEMPLATE_EXTENSION", "WindowFeatures"]
