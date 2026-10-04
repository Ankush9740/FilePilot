"""Render the real Qt interface using an isolated synthetic fixture, never personal files."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from filepilot.core.safety import SafetyPolicy
from filepilot.database.store import Store
from filepilot.ui.window import MainWindow


def wait(window):
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(10)
    poll.timeout.connect(lambda: loop.quit() if window.job is None else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start()
    deadline.start(30_000)
    loop.exec()
    poll.stop()
    deadline.stop()
    if window.job:
        raise RuntimeError("Worker did not finish")


def main():
    output = Path(__file__).parent / "output"
    output.mkdir(exist_ok=True)
    app = QApplication([])
    app.setStyle("Fusion")
    if not QFontDatabase.families():
        for name in ("segoeui.ttf", "seguisb.ttf", "segoeuib.ttf"):
            QFontDatabase.addApplicationFont(f"C:/Windows/Fonts/{name}")
    with tempfile.TemporaryDirectory(prefix="filepilot-ui-") as temporary:
        base = Path(temporary)
        root = base / "Studio archive"
        root.mkdir()
        records = {
            "Brand guidelines.pdf": 145_100,
            "Project brief.docx": 98_342,
            "Meeting notes.txt": 2_024,
            "Quarterly review.xlsx": 25_098,
            "Cover photo.jpg": 545_223,
            "Product sketches.png": 200_120,
            "Campaign film.mp4": 2_000_000,
            "Voice memo.wav": 165_333,
            "Spring assets.zip": 385_501,
            "Installer.msi": 302_901,
            "Layout.tsx": 9_042,
            "Configuration.toml": 1_528,
            "Project backup.bin": 123_454,
        }
        for name, size in records.items():
            # Small real files; screenshot data comes from the actual scan service.
            (root / name).write_bytes((name.encode() * (size // len(name.encode()) + 1))[:size])
        copy = root / "Earlier versions"
        copy.mkdir()
        for name in ("Cover photo.jpg", "Brand guidelines.pdf", "Spring assets.zip"):
            (copy / name).write_bytes((root / name).read_bytes())
        store = Store(base / "data" / "filepilot.sqlite3")
        window = MainWindow(store, SafetyPolicy((store.path.parent,)))
        notices = []
        window.notice = lambda *args, **kwargs: notices.append((args, kwargs))
        window.show()
        app.processEvents()
        for theme in ("Light", "Dark"):
            window.state.settings.theme = theme
            window.preferences.theme.setCurrentText(theme)
            window.set_theme()
            for size in ((1440, 900), (1280, 800), (1000, 680)):
                window.resize(*size)
                window.navigate(0)
                app.processEvents()
                window.grab().save(str(output / f"welcome-{theme.lower()}-{size[0]}.png"))
        window.scan_folder(root)
        wait(window)
        window.analyze_duplicates()
        wait(window)
        window.create_preview()
        wait(window)
        layout_issues = []
        for theme in ("Light", "Dark"):
            window.state.settings.theme = theme
            window.preferences.theme.setCurrentText(theme)
            window.set_theme()
            for size in ((1440, 900), (1280, 800), (1000, 680)):
                window.resize(*size)
                for page, name in enumerate(("dashboard", "files", "duplicates", "organize", "history", "settings")):
                    window.navigate(page)
                    app.processEvents()
                    window.grab().save(str(output / f"{name}-{theme.lower()}-{size[0]}.png"))
                    if window.pages.currentWidget().width() > window.pages.width():
                        layout_issues.append((theme, size, name))
        window.confirm = lambda *args: True
        window.apply_organization()
        wait(window)
        operation_id = store.history()[0]["id"]
        window.navigate(4)
        for theme in ("Light", "Dark"):
            window.state.settings.theme = theme
            window.set_theme()
            window.resize(1280, 800)
            app.processEvents()
            window.grab().save(str(output / f"history-populated-{theme.lower()}-1280.png"))
        window.undo_operation(operation_id)
        wait(window)
        report = {"rendered_images": len(list(output.glob("*.png"))), "layout_issues": layout_issues,
                  "files_scanned": len(window.state.scan.files), "operation_status": store.history()[0]["status"],
                  "notices": [item[0][0] for item in notices]}
        (output / "report.json").write_text(json.dumps(report, indent=2))
        window.close()
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
