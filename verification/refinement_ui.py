"""Capture every refined page from real services and disposable Windows fixtures.

Default: offscreen reproducible matrix. --native uses the Windows Qt platform.
"""
import json
import os
import sys
import tempfile
import time
import argparse
from pathlib import Path
from threading import Event

if "--native" not in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer, qInstallMessageHandler
from PySide6.QtGui import QColor, QFontDatabase, QImage, QPainter
from PySide6.QtWidgets import QApplication, QMessageBox
from filepilot.core.safety import SafetyPolicy
from filepilot.database.store import Store
from filepilot.models.records import Settings
from filepilot.ui.window import MainWindow
from verification.render_ui import wait

if "--native" in sys.argv:
    os.environ.pop("QT_QPA_PLATFORM", None)

NAMES = ("dashboard", "files", "duplicates", "organize", "history", "settings")
SIZES = ((1440, 900), (1280, 800), (1000, 680))


def fixture(root):
    root.mkdir()
    entries = {
        "Brand guidelines.pdf": 148103,
        "Quarterly review.pptx": 398320,
        "Planning notes.txt": 2024,
        "Budget.xlsx": 25098,
        "Product sketches.png": 201020,
        "Campaign film.mp4": 18 * 1024 * 1024,
        "Voice memo.wav": 165333,
        "Layout.tsx": 9042,
        "Configuration.json": 1528,
        "Project backup.bin": 123454,
        "Empty placeholder.txt": 0,
        "assets/Brand reference.jpg": 1048576,
        "assets/Brand reference - copy.jpg": 1048576,
        "assets/archive/Brand reference - approved.jpg": 1048576,
        "Spring assets.zip": int(6.1 * 1024 * 1024),
        "assets/Spring assets - copy.zip": int(6.1 * 1024 * 1024),
    }
    long_name = "Brand identity — final approved presentation with client revisions and export settings for the autumn product campaign — reference version.pdf"
    long_relative = "assets/Reviewed/Approved/" + long_name
    entries[long_relative] = 451293
    for index in range(22):
        entries[f"Editorial notes {index + 1:02d}.txt"] = 3000 + index * 101
    # Exactly 40 files and 251.5 MiB logical storage, with singleton large-size candidates.
    entries["Studio installer.exe"] = int(251.5 * 1024 * 1024) - sum(entries.values())
    for name, size in entries.items():
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        payload = b"brand-image" if "Brand reference" in name else b"spring-archive" if "Spring assets" in name else name.encode("utf-8")
        with file.open("wb") as stream:
            if size > 10 * 1024 * 1024:
                stream.write(payload)
                stream.truncate(size)
            else:
                stream.write((payload * (size // len(payload) + 1))[:size])
        if name.startswith("Editorial notes"):
            old = time.time() - 500 * 86400
            os.utime(file, (old, old))
    assert len(entries) == 40
    return root / long_relative


def contact(output, theme, width, prefix=""):
    first = QImage(str(output / f"{prefix}dashboard-{theme}-{width}.png"))
    target = QImage(1280, 3 * (round(640 * first.height() / first.width()) + 28), QImage.Format.Format_RGB32)
    target.fill(QColor("#ddd9d1"))
    painter = QPainter(target)
    height = round(640 * first.height() / first.width())
    for i, name in enumerate(NAMES):
        screenshot = QImage(str(output / f"{prefix}{name}-{theme}-{width}.png"))
        x, y = i % 2 * 640, i // 2 * (height + 28)
        painter.setPen(QColor("#29332e"))
        painter.drawText(x + 10, y + 19, f"{name.title()} · {theme} · {width}px")
        painter.drawImage(x, y + 28, screenshot.scaled(640, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    painter.end()
    target.save(str(output / f"contact-{theme}-{width}.png"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--current-scale", action="store_true", help="Use only sizes that fit the current monitor at its normal scale")
    args = parser.parse_args()
    sizes = SIZES[1:] if args.current_scale else SIZES
    output = Path(__file__).parent / "output" / ("refinement-native" if "--native" in sys.argv else "refinement")
    if args.current_scale:
        output = output.with_name("refinement-native-current-scale")
    output.mkdir(exist_ok=True)
    warnings = []
    qInstallMessageHandler(lambda kind, context, message: warnings.append(message))
    app = QApplication([])
    app.setStyle("Fusion")
    if not QFontDatabase.families():
        for name in ("segoeui.ttf", "seguisb.ttf", "segoeuib.ttf"):
            QFontDatabase.addApplicationFont(f"C:/Windows/Fonts/{name}")
    captures = []
    geometry_errors = []
    with tempfile.TemporaryDirectory(prefix="fp-review-") as temporary:
        base = Path(temporary)
        root = base / "Studio archive"
        long_file = fixture(root)
        store = Store(base / "data" / "filepilot.sqlite3")
        store.save_settings(Settings(large_mb=95))
        window = MainWindow(store, SafetyPolicy((store.path.parent,)))
        notices = []
        window.notice = lambda *args, **kwargs: notices.append(args[0])
        window.show()

        def settle():
            # Two event turns allow Qt to lay out newly shown scroll bodies.
            app.processEvents()
            app.processEvents()

        def capture(name, widget=window):
            settle()
            destination = output / f"{name}.png"
            assert widget.grab().save(str(destination))
            captures.append(destination.name)

        def theme(name):
            window.state.settings.theme = name
            window.preferences.theme.setCurrentText(name)
            window.set_theme()

        window.resize(1000, 680)
        for mode in ("Light", "Dark", "System"):
            theme(mode)
            for page, name in enumerate(NAMES[:5]):
                window.navigate(page)
                capture(f"empty-{name}-{mode.lower()}-1000")

        # Real completed and partially restored operations, exclusively on fixture files.
        history_root = base / "Earlier review"
        history_root.mkdir()
        for name in ("Brief.txt", "Notes.pdf", "Logo.png"):
            (history_root / name).write_bytes(name.encode())
        window.confirm = lambda *args: True
        window.scan_folder(history_root)
        wait(window)
        window.create_preview()
        wait(window)
        window.apply_organization()
        wait(window)
        first_id = store.history()[0]["id"]
        window.undo_operation(first_id)
        wait(window)
        window.create_preview()
        wait(window)
        window.apply_organization()
        wait(window)
        partial_id = store.history()[0]["id"]
        occupied = history_root / "Notes.pdf"
        occupied.write_bytes(b"Temporary conflicting file")
        window.undo_operation(partial_id)
        wait(window)
        assert store.history()[0]["status"] == "partial_undo"
        assert store.history()[0]["remaining"] == 1
        window.feedback.hide()

        window.scan_folder(root)
        wait(window)
        assert len(window.state.scan.files) == 40 and not window.state.scan.issues
        window.navigate(0)
        theme("Light")
        window.resize(1280, 800)
        capture("dashboard-not-analyzed-light-1280")
        window.analyze_duplicates()
        wait(window)
        duplicates = window.state.duplicates
        assert len(duplicates.groups) == 2 and duplicates.extra_copies == 3
        window.create_preview()
        wait(window)
        assert len(window.state.plan.actionable) == 40 and not any(item.conflict for item in window.state.plan.items)
        window.history.select_operation(partial_id)
        # Inspect real long file using ordinary selection, and the first duplicate group.
        window.files.search.setText(long_file.name)
        window.files.view.selectRow(0)
        assert str(long_file) in window.files.details.details_text
        window.files.reset_filters()
        source_row = next(i for i, record in enumerate(window.files.model.rows) if record.path == long_file)
        mapped = window.files.proxy.mapFromSource(window.files.model.index(source_row, 0))
        window.files.view.selectRow(mapped.row())
        window.duplicates.view.setCurrentIndex(window.duplicates.model.index(0, 0))
        window.organize.view.selectRow(0)
        window.history.details.selectRow(0)

        for mode in ("Light", "Dark", "System"):
            theme(mode)
            for size in sizes:
                window.resize(*size)
                for page, name in enumerate(NAMES):
                    window.navigate(page)
                    if page == 0:
                        window.dashboard.scroll.verticalScrollBar().setValue(0)
                    if page == 5:
                        window.preferences.scroll.verticalScrollBar().setValue(0)
                    capture(f"{name}-{mode.lower()}-{size[0]}")
                    if (window.width(), window.height()) != size:
                        geometry_errors.append((mode, size, name, "window constrained by monitor"))
                    if window.pages.currentWidget().width() > window.pages.width():
                        geometry_errors.append((mode, size, name, "page exceeds shell"))
                window.navigate(0)
                settle()
                scrollbar = window.dashboard.scroll.verticalScrollBar()
                positions = [metric.value.mapTo(window, QPoint(0, 0)) for metric in window.dashboard.summary.metrics]
                for fraction, caption in ((0, "top"), (.5, "middle"), (1, "bottom")):
                    scrollbar.setValue(round(scrollbar.maximum() * fraction))
                    capture(f"dashboard-scroll-{caption}-{mode.lower()}-{size[0]}")
                    for metric, position in zip(window.dashboard.summary.metrics, positions):
                        if metric.value.mapTo(window, QPoint(0, 0)) != position or not metric.value.visibleRegion().boundingRect().contains(metric.value.rect()):
                            geometry_errors.append((mode, size, caption, "summary clipped or moved"))
                window.navigate(5)
                window.preferences.scroll.verticalScrollBar().setValue(window.preferences.scroll.verticalScrollBar().maximum())
                capture(f"settings-bottom-{mode.lower()}-{size[0]}")
                contact(output, mode.lower(), size[0])

        theme("Light")
        window.resize(1000, 680)
        window.navigate(1)
        window.files.search.setText("no files with this name")
        capture("files-no-results-light-1000")
        window.files.reset_filters()
        window.files.category.setCurrentText("Images")
        capture("files-active-filter-light-1000")
        window.files.reset_filters()
        mapped = window.files.proxy.mapFromSource(window.files.model.index(source_row, 0))
        window.files.view.selectRow(mapped.row())
        dialog = window.files.details.create_dialog()
        dialog.show()
        capture("long-file-full-details", dialog)
        dialog.close()
        dialog.deleteLater()

        # The actual pre-move confirmation defaults to Cancel; take its capture and cancel.
        window.navigate(3)
        def cancel_confirmation():
            for widget in app.topLevelWidgets():
                if isinstance(widget, QMessageBox):
                    capture("organization-confirmation", widget)
                    widget.button(QMessageBox.StandardButton.Cancel).click()
        window.confirm = MainWindow.confirm.__get__(window)
        QTimer.singleShot(30, cancel_confirmation)
        window.apply_organization()
        assert long_file.exists() and window.state.plan is not None

        release = Event()
        window.start_job("Comparing file contents locally", lambda cancel, progress: release.wait(10), lambda result: None)
        window.navigate(1)
        capture("background-browsing-light-1000")
        release.set()
        wait(window)

        # Full actual undo retry after releasing the fixture collision.
        occupied.unlink()
        window.confirm = lambda *args: True
        window.undo_operation(partial_id)
        wait(window)
        assert store.history()[0]["status"] == "undone"

        report_data = {
            "platform": app.platformName(), "captures": len(captures), "capture_files": captures,
            "themes": ["Light", "Dark", "System"], "sizes": sizes, "geometry_errors": geometry_errors,
            "device_pixel_ratio": window.devicePixelRatioF(),
            "files": 40, "logical_bytes": sum(record.size for record in window.scanner.scan(root).files),
            "duplicate_groups": len(duplicates.groups), "extra_copies": duplicates.extra_copies,
            "redundant_bytes": duplicates.redundant_size,
            "long_path_characters": len(str(long_file)), "long_filename_characters": len(long_file.name),
            "history_statuses_before_retry": ["undone", "partial_undo"], "retry_status": store.history()[0]["status"],
            "qt_messages": warnings, "notices": notices,
        }
        # Empty, zero-byte single, and no-duplicate folders through actual background services.
        for case, count in (("empty-folder", 0), ("single-zero-byte", 1), ("single-file", 1)):
            folder = base / case
            folder.mkdir()
            if count:
                (folder / "Only document.txt").write_bytes(b"" if case == "single-zero-byte" else b"only file")
            window.scan_folder(folder)
            wait(window)
            window.analyze_duplicates()
            wait(window)
            window.create_preview()
            wait(window)
            assert len(window.state.scan.files) == count
            assert window.duplicates.stack.currentIndex() == 2
            for page, name in enumerate(NAMES[:4]):
                window.navigate(page)
                capture(f"{case}-{name}-light-1000")
        report_data["captures"] = len(captures)
        report_data["qt_messages"] = warnings
        report_data["geometry_errors"] = geometry_errors
        assert not geometry_errors, geometry_errors
        # Offscreen cannot propagate native dialog size hints. Native runs allow no messages.
        expected = [message for message in warnings if app.platformName() == "offscreen" and message == "This plugin does not support propagateSizeHints()"]
        report_data["expected_platform_messages"] = expected
        report_data["unexpected_qt_messages"] = [message for message in warnings if message not in expected]
        (output / "report.json").write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        assert not report_data["unexpected_qt_messages"], report_data["unexpected_qt_messages"]
        window.close()
        print(json.dumps({key: value for key, value in report_data.items() if key != "capture_files"}, indent=2))


if __name__ == "__main__":
    main()
