"""Dabireh — Persian word processor. Run with: python main.py [document.dbr]"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.application import run  # noqa: E402

if __name__ == "__main__":
    sys.exit(run())
