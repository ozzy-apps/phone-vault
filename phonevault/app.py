from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from . import APP_ID, APP_NAME, __version__
from .core.settings import Settings


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--version" in argv:
        print(f"{APP_NAME} {__version__}")
        return 0
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("ozzy-apps")
    app.setDesktopFileName(APP_ID)

    from .ui.main_window import MainWindow  # import after QApplication exists

    window = MainWindow(Settings.load())
    window.show()
    return app.exec()
