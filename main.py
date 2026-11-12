#!/usr/bin/env python3
"""Punto de entrada de Sonora."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.main_window import MainWindow  # noqa: E402
from ui.theme import preferred_font  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Sonora")
    app.setApplicationDisplayName("Sonora")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Sonora")
    app.setDesktopFileName("sonora")
    app.setStyle("Fusion")
    app.setFont(preferred_font())
    app.setWindowIcon(QIcon(str(ROOT / "assets" / "icon.svg")))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
