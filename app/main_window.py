"""Main window: menus, toolbars, status bar and document life-cycle."""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QActionGroup, QCloseEvent, QColor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from app.autosave_controller import AutosaveController
from app.services import Services
from app.settings import APP_DISPLAY_NAME, APP_VERSION
from app.window_features import WindowFeatures
from core.document import FILE_EXTENSION, Document, DocumentDefaults, DocumentFormatError, PageSettings
from core.persian import format_number, to_persian_digits
from editor.export import export_html, export_pdf
from editor.formatting import document_statistics
from editor.text_editor import RichTextEditor
from editor.toolbar import ACTION_SPECS, LINE_SPACINGS, EditorActions, EditorToolbars, connect_editor_actions
from storage.autosave import Snapshot
from storage.document_repository import DocumentRepository
from ui.components.find_bar import FindBar
from ui.dialogs.document_dialog import DocumentDialog
from ui.dialogs.page_setup_dialog import PageSetupDialog
from ui.dialogs.paragraph_dialog import ParagraphDialog
from ui.dialogs.recovery_dialog import RecoveryDialog
from ui.dialogs.shortcuts_dialog import ShortcutsDialog
from ui.icons import icon
from ui.theme import THEMES, apply_theme, theme_colors

logger = logging.getLogger(__name__)

UNTITLED = "سند بی‌نام"
DOCUMENT_FILTER = f"سند دبیره (*{FILE_EXTENSION})"
OPEN_FILTER = (f"همهٔ سندهای پشتیبانی‌شده (*{FILE_EXTENSION} *.docx *.txt);;{DOCUMENT_FILTER};;"
               "Word (*.docx);;متن ساده (*.txt)")


class MainWindow(WindowFeatures, QMainWindow):
    def __init__(self, services: Services) -> None:
        super().__init__()
        self.services = services
        self._path: Path | None = None
        self._doc_key = uuid.uuid4().hex
        settings = services.settings

        self.editor = RichTextEditor()
        colors = theme_colors(settings.theme)
        apply_theme(QApplication.instance(), settings.theme)
        self.editor.set_workspace_colors(QColor(colors.workspace), QColor(colors.page_border))
        self.find_bar = FindBar(self.editor)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.find_bar)
        layout.addWidget(self.editor, 1)
        self.setCentralWidget(central)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        self.commands = EditorActions(self, settings.shortcuts)
        connect_editor_actions(self.commands, self.editor)
        self.toolbars = EditorToolbars(self, self.commands, self.editor)
        self._build_menus()
        self._build_status_bar()
        self._connect_window_actions()
        self._connect_feature_signals()
        self.setAcceptDrops(True)

        self.autosave = AutosaveController(
            services.autosave_store, self._make_snapshot, settings.autosave_interval_seconds, parent=self
        )
        self.autosave.saved.connect(self._on_autosaved)
        self.autosave.failed.connect(lambda _message: self.autosave_label.setText("ذخیرهٔ خودکار ناموفق بود"))

        self._statistics_timer = QTimer(self)
        self._statistics_timer.setSingleShot(True)
        self._statistics_timer.setInterval(350)
        self._statistics_timer.timeout.connect(self._update_statistics)

        document = self.editor.document()
        document.modificationChanged.connect(self._on_modification_changed)
        document.contentsChanged.connect(self._on_contents_changed)
        self.editor.cursorPositionChanged.connect(self._sync_format_controls)
        self.editor.currentCharFormatChanged.connect(lambda _format: self._sync_format_controls())

        self.commands["visual_cursor"].setChecked(settings.visual_cursor_movement)
        self.commands["autosave_enabled"].setChecked(settings.autosave_enabled)
        self.autosave.set_enabled(settings.autosave_enabled)

        self.resize(settings.window_width, settings.window_height)
        self.setMinimumSize(560, 420)
        self._set_document(self._blank_document(), None)

    # ---------------------------------------------------------------- menus
    def _build_menus(self) -> None:
        commands = self.commands
        bar = self.menuBar()

        file_menu = bar.addMenu("پرونده")
        self._add(file_menu, "new", "new_template", "open")
        self.recent_menu = file_menu.addMenu("سندهای اخیر")
        self.recent_menu.aboutToShow.connect(self._populate_recent_menu)
        self._add(file_menu, None, "save", "save_as", "save_template")
        export_menu = file_menu.addMenu("برون‌برد")
        self._add(export_menu, "export_pdf", "export_docx", "export_rtf", "export_html", "export_text", None,
                  "export_png", "export_svg", None, "export_history")
        self._add(file_menu, None, "print", "print_preview", None, "page_setup", "header_footer",
                  "document_properties", "statistics", None)
        history_menu = file_menu.addMenu("نسخه‌ها و بازیابی")
        self._add(history_menu, "versions", "backups", "recover", None, "autosave_enabled", "autosave_settings")
        self._add(file_menu, None, "quit")

        edit_menu = bar.addMenu("ویرایش")
        self._add(edit_menu, "undo", "redo", None, "cut", "copy", "paste", "paste_plain", None,
                  "select_all", None, "copy_format", "paste_format", "format_painter", None,
                  "find", "replace", "go_to_page")

        self._build_feature_menus(bar.addMenu("درج"), bar.addMenu("جدول"))

        format_menu = bar.addMenu("قالب")
        self._add(format_menu, "bold", "italic", "underline", "strike", "superscript", "subscript", None,
                  "char_spacing", "styles", None, "clear_format", "script_fonts")

        paragraph_menu = bar.addMenu("بند")
        self._add(paragraph_menu, "align_right", "align_center", "align_left", "align_justify", None,
                  "dir_rtl", "dir_ltr", None, "bullet", "numbered", "list_circle", "list_square", "list_alpha",
                  "list_roman", None, "indent_more", "indent_less", None)
        spacing_menu = paragraph_menu.addMenu("فاصلهٔ سطرها")
        for multiple in LINE_SPACINGS:
            spacing_menu.addAction(commands[f"spacing_{multiple}"])
        self._add(paragraph_menu, "paragraph")

        tools_menu = bar.addMenu("ابزار فارسی")
        self._add(tools_menu, "zwnj", "insert_lrm", "insert_rlm", "isolate_ltr", None,
                  "digits_persian", "digits_latin", None, "visual_cursor", "autosave_enabled")

        view_menu = bar.addMenu("نمایش")
        theme_menu = view_menu.addMenu("پوستهٔ برنامه")
        self.theme_group = QActionGroup(self)
        self.theme_actions = {}
        for name, (label, _colors) in THEMES.items():
            action = theme_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(name == self.services.settings.theme)
            self.theme_group.addAction(action)
            action.triggered.connect(lambda _checked=False, n=name: self._set_theme(n))
            self.theme_actions[name] = action
        view_menu.addSeparator()
        view_menu.addAction(self.toolbars.main_toolbar.toggleViewAction())
        view_menu.addAction(self.toolbars.paragraph_toolbar.toggleViewAction())

        help_menu = bar.addMenu("راهنما")
        self._add(help_menu, "shortcuts", "customize_shortcuts", "about")

    def _set_theme(self, name: str) -> None:
        if name not in THEMES:
            return
        self.services.settings.theme = name
        apply_theme(QApplication.instance(), name)
        colors = theme_colors(name)
        self.editor.set_workspace_colors(QColor(colors.workspace), QColor(colors.page_border))
        for spec in ACTION_SPECS:
            if spec.icon:
                self.commands[spec.id].setIcon(icon(spec.icon))
        self.toolbars.spacing_button.setIcon(icon("line_spacing"))
        self.toolbars.color_button._refresh_icon()
        self.toolbars.highlight_button._refresh_icon()
        for button, icon_name in ((self.find_bar.previous_button, "up"),
                                  (self.find_bar.next_button, "down"),
                                  (self.find_bar.close_button, "close")):
            button.setIcon(icon(icon_name))
        self.services.settings_store.save(self.services.settings)

    def _add(self, menu: QMenu, *ids: str | None) -> None:
        for action_id in ids:
            if action_id is None:
                menu.addSeparator()
            else:
                menu.addAction(self.commands[action_id])

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        bar.setSizeGripEnabled(True)
        self.page_label = QLabel()
        self.words_label = QLabel()
        self.direction_label = QLabel()
        self.autosave_label = QLabel()
        for label in (self.page_label, self.words_label, self.direction_label, self.autosave_label):
            bar.addPermanentWidget(label)

    def _connect_window_actions(self) -> None:
        handlers = {
            "new": self.new_document,
            "open": self.open_document,
            "save": self.save_document,
            "save_as": self.save_document_as,
            "export_pdf": self.export_pdf,
            "export_html": self.export_html,
            "export_text": self.export_text,
            "page_setup": self.show_page_setup,
            "document_properties": self.show_document_properties,
            "recover": lambda: self.check_recovery(announce_empty=True),
            "quit": self.close,
            "find": lambda: self.find_bar.open_bar(with_replace=False),
            "replace": lambda: self.find_bar.open_bar(with_replace=True),
            "paragraph": self.show_paragraph_dialog,
            "script_fonts": self.apply_script_fonts,
            "isolate_ltr": self.isolate_selection,
            "digits_persian": lambda: self.convert_digits("persian"),
            "digits_latin": lambda: self.convert_digits("latin"),
            "shortcuts": lambda: ShortcutsDialog(self.commands.shortcut_table(), self).exec(),
            "about": self.show_about,
        }
        handlers.update(self._feature_handlers())
        for action_id, handler in handlers.items():
            self.commands[action_id].triggered.connect(lambda _checked=False, h=handler: h())
        self.commands["autosave_enabled"].toggled.connect(self._set_autosave_enabled)
        self.commands["visual_cursor"].toggled.connect(self._set_visual_cursor)

    # ------------------------------------------------------- document state
    @property
    def current_path(self) -> Path | None:
        return self._path

    def display_name(self) -> str:
        return self.editor.metadata.title or (self._path.stem if self._path else UNTITLED)

    def _blank_document(self) -> Document:
        settings = self.services.settings
        margin = settings.default_margin_mm
        document = Document(
            defaults=DocumentDefaults(
                font_family=settings.default_font_family,
                font_size=settings.default_font_size,
                latin_font=settings.default_latin_font,
                math_font=settings.default_math_font,
                direction=settings.default_direction,
            ),
            page=PageSettings(
                size=settings.default_page_size,
                margin_top=margin, margin_bottom=margin, margin_left=margin, margin_right=margin,
            ),
        )
        document.metadata.author = settings.author
        return document

    def _set_document(
        self, document: Document, path: Path | None, doc_key: str | None = None, modified: bool = False
    ) -> None:
        """Replace the edited document. The caller has already handled unsaved changes."""
        self.autosave.discard(self._doc_key)
        self.editor.load_document(document)
        self.toolbars.refresh_styles()
        self.editor.set_visual_cursor_movement(self.commands["visual_cursor"].isChecked())
        self._path = path
        self._doc_key = doc_key or uuid.uuid4().hex
        self.editor.document().setModified(modified)
        if modified:
            self.autosave.note_edit()
        self.autosave_label.clear()
        self._update_title()
        self._sync_format_controls()
        self._update_statistics()
        self.editor.setFocus()

    def _update_title(self) -> None:
        self.setWindowTitle(f"{self.display_name()}[*] — {APP_DISPLAY_NAME}")
        self.setWindowModified(self.editor.document().isModified())
        self.setWindowFilePath(str(self._path) if self._path else "")

    def _on_modification_changed(self, modified: bool) -> None:
        self.setWindowModified(modified)
        if modified:
            self.autosave.note_edit()

    def _on_contents_changed(self) -> None:
        self.autosave.note_edit()
        self._statistics_timer.start()

    def _sync_format_controls(self) -> None:
        state = self.editor.format_state()
        self.toolbars.sync(state)
        self.direction_label.setText("راست‌به‌چپ" if state.direction == "rtl" else "چپ‌به‌راست")
        self._update_page_label()

    def _update_page_label(self) -> None:
        self.page_label.setText(
            f"صفحهٔ {format_number(self.editor.cursor_page())} از {format_number(self.editor.page_count())}"
        )

    def _update_statistics(self) -> None:
        words, characters = document_statistics(self.editor.document())
        self.words_label.setText(f"{format_number(words)} واژه  ·  {format_number(characters)} نویسه")
        self._update_page_label()

    # ------------------------------------------------------------- messages
    def _show_error(self, text: str, details: str = "") -> None:
        box = QMessageBox(QMessageBox.Icon.Critical, APP_DISPLAY_NAME, text, QMessageBox.StandardButton.Ok, self)
        box.button(QMessageBox.StandardButton.Ok).setText("باشه")
        if details:
            box.setInformativeText(details)
        box.exec()

    def _show_info(self, text: str) -> None:
        box = QMessageBox(QMessageBox.Icon.Information, APP_DISPLAY_NAME, text, QMessageBox.StandardButton.Ok, self)
        box.button(QMessageBox.StandardButton.Ok).setText("باشه")
        box.exec()

    def _ask_save_changes(self) -> str:
        """Ask what to do with unsaved changes: "save", "discard" or "cancel"."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(APP_DISPLAY_NAME)
        box.setText(f"تغییرات «{self.display_name()}» ذخیره نشده است.")
        box.setInformativeText("می‌خواهید پیش از ادامه، سند ذخیره شود؟")
        save = box.addButton("ذخیره", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("ذخیره نکن", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("انصراف", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save:
            return "save"
        return "discard" if clicked is discard else "cancel"

    def maybe_save(self) -> bool:
        """Return ``True`` when it is safe to drop the current document."""
        if not self.editor.document().isModified():
            return True
        choice = self._ask_save_changes()
        if choice == "save":
            return self.save_document()
        return choice == "discard"

    # ----------------------------------------------------------- file: open
    def new_document(self) -> None:
        if self.maybe_save():
            self._set_document(self._blank_document(), None)

    def open_document(self) -> None:
        name, _filter = QFileDialog.getOpenFileName(self, "باز کردن سند", self._start_directory(), OPEN_FILTER)
        if name:
            self.open_path(Path(name))

    def open_path(self, path: Path) -> bool:
        if not self.maybe_save():
            return False
        path = Path(path)
        is_docx = path.suffix.lower() == ".docx"
        try:
            if is_docx:
                document = self.import_docx(path)
            else:
                document = self.services.repository.load(path, self._blank_document())
        except FileNotFoundError:
            self.services.recents.remove(path.resolve())
            self._show_error("پرونده پیدا نشد.", str(path))
            return False
        except DocumentFormatError as error:
            self._show_error("این پرونده باز نشد.", str(error))
            return False
        except OSError as error:
            self._show_error("خواندن پرونده ممکن نشد.", str(error))
            return False
        self._remember_directory(path)
        if DocumentRepository.is_native(path):
            self._set_document(document, path)
            self.services.recents.add(path, self.display_name())
        else:
            # Imported text keeps its source untouched; saving asks for a .dbr name.
            document.metadata.title = path.stem
            self._set_document(document, None)
        return True

    def _populate_recent_menu(self) -> None:
        self.recent_menu.clear()
        entries = self.services.recents.entries()
        if not entries:
            self.recent_menu.addAction("سندی در فهرست نیست").setEnabled(False)
            return
        for index, entry in enumerate(entries, start=1):
            label = f"{to_persian_digits(str(index))}. {entry.title or Path(entry.path).stem}  —  {entry.path}"
            action = self.recent_menu.addAction(label.replace("&", "&&"))
            action.triggered.connect(lambda _checked=False, p=entry.path: self.open_path(Path(p)))
        self.recent_menu.addSeparator()
        self.recent_menu.addAction("پاک‌کردن فهرست").triggered.connect(self.services.recents.clear)

    # ----------------------------------------------------------- file: save
    def save_document(self) -> bool:
        if self._path is None:
            return self.save_document_as()
        return self.save_to_path(self._path)

    def save_document_as(self) -> bool:
        suggestion = str(self._path) if self._path else str(Path(self._start_directory()) / self.display_name())
        name, _filter = QFileDialog.getSaveFileName(self, "ذخیره با نام", suggestion, DOCUMENT_FILTER)
        if not name:
            return False
        path = Path(name)
        if path.suffix.lower() != FILE_EXTENSION:
            path = path.with_name(path.name + FILE_EXTENSION)
        return self.save_to_path(path)

    def save_to_path(self, path: Path) -> bool:
        """Write the document; on failure the document stays open and modified."""
        try:
            document = self.editor.to_document()
            if self.services.settings.backup_limit > 0:
                self.services.backups.backup(path)  # keep the previous file content
            self.services.repository.save(document, path)
        except OSError as error:
            logger.exception("Saving failed")
            self._show_error("ذخیرهٔ سند ممکن نشد. سند همچنان باز است.", str(error))
            return False
        self._path = Path(path)
        self.editor.metadata.modified = document.metadata.modified
        self.editor.document().setModified(False)
        self.autosave.discard(self._doc_key)
        self.autosave_label.clear()
        self.services.recents.add(self._path, self.display_name())
        try:
            self.services.versions.add(self._path, document, document_statistics(self.editor.document())[0])
        except Exception:  # noqa: BLE001 - history must never make a successful save look failed
            logger.exception("Could not record the document version")
        self._remember_directory(self._path)
        self._update_title()
        self.statusBar().showMessage("سند ذخیره شد", 4000)
        return True

    def _export(self, title: str, file_filter: str, suffix: str, writer) -> None:  # noqa: ANN001
        suggestion = str(Path(self._start_directory()) / f"{self.display_name()}{suffix}")
        name, _filter = QFileDialog.getSaveFileName(self, title, suggestion, file_filter)
        if not name:
            return
        path = Path(name)
        if path.suffix.lower() != suffix:
            path = path.with_name(path.name + suffix)
        self.export_to(path, writer)

    def export_to(self, path: Path, writer) -> bool:  # noqa: ANN001
        """Run an export writer, report errors and record the export."""
        self._prepare_output()
        try:
            writer(path)
        except OSError as error:
            logger.exception("Export failed")
            self._show_error("برون‌برد ممکن نشد.", str(error))
            return False
        try:
            self.services.export_history.add(self.display_name(), path.suffix.lstrip(".").upper(), path)
        except Exception:  # noqa: BLE001
            logger.exception("Could not record the export")
        self.statusBar().showMessage(f"برون‌برد انجام شد: {path.name}", 5000)
        return True

    def export_pdf(self) -> None:
        self._export(
            "برون‌برد PDF", "PDF (*.pdf)", ".pdf",
            lambda path: export_pdf(self.editor.document(), self.editor.page_settings, path, self.display_name(),
                                    self.editor.header_footer),
        )

    def export_html(self) -> None:
        self._export("برون‌برد HTML", "HTML (*.html)", ".html",
                     lambda path: export_html(self.editor.document(), path))

    def export_text(self) -> None:
        self._export(
            "برون‌برد متن ساده", "متن ساده (*.txt)", ".txt",
            lambda path: self.services.repository.export_plain_text(self.editor.to_document(), path),
        )

    def _start_directory(self) -> str:
        if self._path:
            return str(self._path.parent)
        last = self.services.settings.last_directory
        return last if last and Path(last).is_dir() else str(Path.home())

    def _remember_directory(self, path: Path) -> None:
        self.services.settings.last_directory = str(Path(path).parent)

    # ------------------------------------------------------------- autosave
    def _make_snapshot(self) -> Snapshot | None:
        if not self.editor.document().isModified():
            return None
        return Snapshot(
            doc_key=self._doc_key,
            source_path=str(self._path) if self._path else "",
            title=self.display_name(),
            payload=self.editor.to_document().to_dict(),
        )

    def _on_autosaved(self, saved_at: str) -> None:
        try:
            moment = datetime.fromisoformat(saved_at).astimezone()
        except ValueError:
            return
        self.autosave_label.setText(f"ذخیرهٔ خودکار: {to_persian_digits(moment.strftime('%H:%M:%S'))}")

    def _set_autosave_enabled(self, enabled: bool) -> None:
        self.services.settings.autosave_enabled = enabled
        self.autosave.set_enabled(enabled)
        if not enabled:
            self.autosave_label.setText("ذخیرهٔ خودکار خاموش است")
        else:
            self.autosave_label.clear()

    def _set_visual_cursor(self, enabled: bool) -> None:
        self.services.settings.visual_cursor_movement = enabled

    def check_recovery(self, announce_empty: bool = False) -> None:
        """Offer documents that were autosaved but never saved (e.g. after a crash)."""
        store = self.services.autosave_store
        snapshots = store.snapshots(exclude_key=self._doc_key)
        if not snapshots:
            if announce_empty:
                self._show_info("سند ذخیره‌نشده‌ای برای بازیابی وجود ندارد.")
            return
        dialog = RecoveryDialog(snapshots, self)
        dialog.exec()
        for snapshot in dialog.deleted:
            store.delete(snapshot.doc_key)
        if dialog.selected is not None:
            self.recover_snapshot(dialog.selected)

    def recover_snapshot(self, snapshot: Snapshot) -> bool:
        if not self.maybe_save():
            return False
        try:
            document = snapshot.document()
        except DocumentFormatError as error:
            self._show_error("بازیابی این نسخه ممکن نشد.", str(error))
            return False
        path = Path(snapshot.source_path) if snapshot.source_path else None
        # Keep the snapshot (same key) until the user saves the recovered document.
        self._set_document(document, path, doc_key=snapshot.doc_key, modified=True)
        self.statusBar().showMessage("سند بازیابی شد؛ برای نگه‌داری آن را ذخیره کنید.", 8000)
        return True

    # -------------------------------------------------------------- dialogs
    def show_paragraph_dialog(self) -> None:
        default_is_rtl = self.editor.defaults.direction != "ltr"
        dialog = ParagraphDialog(self.editor.paragraph_style(), default_is_rtl, self)
        if dialog.exec():
            self.editor.apply_paragraph_style(dialog.paragraph_style())
            self._sync_format_controls()

    def show_page_setup(self) -> None:
        dialog = PageSetupDialog(self.editor.page_settings, self)
        if dialog.exec():
            self.editor.set_page_settings(dialog.page_settings())
            self._update_statistics()

    def show_document_properties(self) -> None:
        words, characters = document_statistics(self.editor.document())
        dialog = DocumentDialog(
            replace(self.editor.metadata),
            replace(self.editor.defaults),
            (words, characters, self.editor.page_count()),
            str(self._path) if self._path else "",
            self,
        )
        if dialog.exec():
            self.editor.set_metadata(dialog.metadata())
            self.editor.set_defaults(dialog.defaults())
            self._update_title()
            self._sync_format_controls()

    def apply_script_fonts(self) -> None:
        scheme = self.editor.font_scheme()
        self.editor.apply_script_fonts()
        self.statusBar().showMessage(
            f"قلم‌ها اعمال شد — فارسی: {scheme.persian}، لاتین: {scheme.latin}، ریاضی: {scheme.math}", 6000
        )

    def isolate_selection(self) -> None:
        if not self.editor.isolate_selection_ltr():
            self.statusBar().showMessage("ابتدا بخشی از یک بند را انتخاب کنید.", 5000)

    def convert_digits(self, target: str) -> None:
        count = self.editor.convert_digits(target)
        self.statusBar().showMessage(f"{format_number(count)} رقم تبدیل شد", 4000)

    def show_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(f"دربارهٔ {APP_DISPLAY_NAME}")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(
            f"<h3>{APP_DISPLAY_NAME} <span style='font-weight:normal'>{to_persian_digits(APP_VERSION)}</span></h3>"
            "<p>واژه‌پرداز رومیزی برای نوشتن فارسی، انگلیسی و متن‌های دوجهته.</p>"
            "<p>قلم وزیرمتن با پروانهٔ SIL OFL همراه برنامه عرضه می‌شود.</p>"
        )
        box.addButton("بستن", QMessageBox.ButtonRole.AcceptRole)
        box.exec()

    # ----------------------------------------------------------- drag & drop
    def dragEnterEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: ANN001, N802
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            suffix = path.suffix.lower()
            if suffix in (FILE_EXTENSION, ".docx", ".txt"):
                self.open_path(path)
                break
            if suffix.lstrip(".") in ("png", "jpg", "jpeg", "webp", "svg", "bmp", "gif"):
                self.insert_image_path(path)
        event.acceptProposedAction()

    # ---------------------------------------------------------------- close
    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.maybe_save():
            event.ignore()
            return
        # The user saved or chose to discard: no recovery copy is needed any more.
        self.autosave.set_enabled(False)
        self.autosave.discard(self._doc_key)
        settings = self.services.settings
        settings.window_maximized = self.isMaximized()
        if not self.isMaximized():
            settings.window_width = self.width()
            settings.window_height = self.height()
        self.services.settings_store.save(settings)
        event.accept()
