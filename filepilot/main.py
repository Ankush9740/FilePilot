import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from filepilot.core.paths import data_directory
from filepilot.database.store import Store
from filepilot.ui.window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="FilePilot — local file analysis and safe organization")
    parser.add_argument("--folder", type=Path, help="Read-only scan of this folder on startup")
    parser.add_argument("--data-dir", type=Path, help="Override the application data directory for development")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("FilePilot")
    app.setOrganizationName("FilePilot")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "ui" / "assets" / "filepilot.svg")))
    try:
        store = Store((args.data_dir or data_directory()) / "filepilot.sqlite3")
        window = MainWindow(store)
    except Exception as error:
        QMessageBox.critical(None, "FilePilot could not start", str(error))
        return 1
    window.show()
    QTimer.singleShot(0, lambda: window.initialize(args.folder))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
