from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from . import color_study
from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Canvas Transfer")
    window = MainWindow()
    window.show()
    # Load the color library while nobody is clicking yet. This runs on the
    # main thread: a background thread gets starved by Qt's event loop.
    QTimer.singleShot(200, color_study.warm_up)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
