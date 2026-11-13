"""Render the real main window to PNG files for visual verification.

Usage:  python tools/render_preview.py [output_dir]

Runs headless (Qt "offscreen" platform) so it also works on CI.  The images
show the actual widgets and Qt text layout — not mock-ups — and are meant to
be inspected by a person: shaping, bidi order, toolbar state and resizing.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DABIREH_HOME", tempfile.mkdtemp(prefix="dabireh-preview-"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.application import create_application  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from app.services import Services  # noqa: E402

SIZES = {"wide": (1440, 900), "medium": (1100, 760), "narrow": (700, 620)}


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "preview"
    output.mkdir(parents=True, exist_ok=True)
    app = create_application(sys.argv[:1])
    window = MainWindow(Services.create())
    window.open_path(ROOT / "tests" / "data" / "sample_document.dbr")
    window.show()
    for name, (width, height) in SIZES.items():
        window.resize(width, height)
        QApplication.processEvents()
        QApplication.processEvents()
        target = output / f"main_window_{name}.png"
        window.grab().save(str(target))
        print("wrote", target)
    window.find_bar.open_bar(with_replace=True)
    window.find_bar.find_edit.setText("دبیره")
    window.find_bar.find_next()
    window.resize(1100, 760)
    QApplication.processEvents()
    window.grab().save(str(output / "find_replace.png"))
    window.editor.document().setModified(False)
    window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    sys.exit(main())
