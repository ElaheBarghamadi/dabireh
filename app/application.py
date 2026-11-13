"""Application startup."""

from __future__ import annotations

import atexit
import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from app.services import Services
from app.settings import APP_DISPLAY_NAME, APP_NAME, APP_VERSION, app_data_dir
from ui.icons import app_icon
from ui.resources import load_bundled_fonts
from ui.theme import apply_theme

logger = logging.getLogger(__name__)


def configure_logging(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(data_dir / "dabireh.log", maxBytes=512_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _integrate_with_windows() -> None:
    """Give the process its own taskbar identity (icon, grouping, jump list)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"Dabireh.WordProcessor.{APP_VERSION}")
    except (AttributeError, OSError):
        logger.warning("Could not set the Windows AppUserModelID")


def create_application(argv: list[str]) -> QApplication:
    """Create and style the QApplication (fonts, theme, RTL interface)."""
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    _integrate_with_windows()
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    load_bundled_fonts()
    apply_theme(app)
    app.setWindowIcon(app_icon())
    from editor.text_editor import release_clipboard

    app.aboutToQuit.connect(release_clipboard)
    atexit.register(release_clipboard)  # also covers runs without an event loop (tests, scripts)
    return app


def _install_exception_hook(window) -> None:  # noqa: ANN001
    """Log unexpected errors, keep a recovery copy and keep the app running."""

    def handle(exc_type: type[BaseException], value: BaseException, trace: TracebackType | None) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, value, trace)
            return
        logger.error("Unhandled exception:\n%s", "".join(traceback.format_exception(exc_type, value, trace)))
        try:
            window.autosave.save_now(blocking=True)
        except Exception:
            logger.exception("Emergency autosave failed")
        box = QMessageBox(QMessageBox.Icon.Critical, APP_DISPLAY_NAME, "خطای پیش‌بینی‌نشده‌ای رخ داد.")
        box.setInformativeText(
            "یک نسخهٔ بازیابی از سند نگه‌داری شد. می‌توانید به کار ادامه دهید؛ "
            "بهتر است سند را ذخیره و برنامه را دوباره اجرا کنید."
        )
        box.setDetailedText(f"{exc_type.__name__}: {value}")
        box.addButton("باشه", QMessageBox.ButtonRole.AcceptRole)
        box.exec()

    sys.excepthook = handle


def run(argv: list[str] | None = None) -> int:
    from app.main_window import MainWindow

    argv = list(sys.argv if argv is None else argv)
    configure_logging(app_data_dir())
    app = create_application(argv)
    services = Services.create()
    window = MainWindow(services)
    _install_exception_hook(window)
    if services.settings.window_maximized:
        window.showMaximized()
    else:
        window.show()

    files = [Path(arg) for arg in argv[1:] if not arg.startswith("-")]
    if files:
        QTimer.singleShot(0, lambda: window.open_path(files[0]))
    QTimer.singleShot(0, window.check_recovery)
    return app.exec()
