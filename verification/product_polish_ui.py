"""Compact whole-product/native Clear History audit using disposable fixtures."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if "--native" not in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEventLoop, Qt, QTimer, qInstallMessageHandler
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from filepilot.core.safety import SafetyPolicy
from filepilot.database.store import Store
from filepilot.ui.theme import current_colors
from filepilot.ui.window import MainWindow
from verification.refinement_ui import fixture, wait
from verification.production_audit import snapshot

if "--native" in sys.argv:
    os.environ.pop("QT_QPA_PLATFORM", None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--current-scale", action="store_true")
    parser.add_argument("--restart-data", type=Path)
    args = parser.parse_args()
    sizes = ((1280, 800), (1000, 680)) if args.current_scale else ((1440, 900), (1280, 800), (1000, 680))
    output = Path(__file__).parent / "output" / ("product-polish-current-scale" if args.current_scale else "product-polish")
    output.mkdir(exist_ok=True)
    messages, notices, checks, captures = [], [], [], []
    qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    app = QApplication([])
    app.setStyle("Fusion")
    with tempfile.TemporaryDirectory(prefix="fp-polish-") as temporary:
        base = Path(temporary)
        store = Store(args.restart_data or base / "data/filepilot.sqlite3")
        window = MainWindow(store, SafetyPolicy((store.path.parent,)))
        window.notice = lambda *args, **kwargs: notices.append(args[0])
        window.confirm = lambda *args: True  # Only disposable fixture actions.
        window.show()
        window.activateWindow()
        window.initialize()
        wait(window)

        def settle():
            app.processEvents()
            loop = QEventLoop()
            QTimer.singleShot(15, loop.quit)
            loop.exec()
            app.processEvents()

        def inspect(page):
            settle()
            assert window.pages.currentWidget().width() <= window.pages.width()
            if page == 4:
                eligible = any(row["clearable"] for row in window.history.model.rows)
                assert window.history.clear.isEnabled() == eligible
                assert window.history.clear.visibleRegion().boundingRect().contains(window.history.clear.rect())
                assert window.history.undo.visibleRegion().boundingRect().contains(window.history.undo.rect())
                if window.history.model.rows:
                    selected = window.history.view.currentIndex()
                    if not selected.isValid():
                        window.history.select_operation(window.history.model.rows[0]["id"])
                    view = window.history.view
                    view.setFocus()
                    view.scrollTo(view.currentIndex())
                    settle()
                    assert view.hasFocus()
                    rect = view.visualRect(view.currentIndex())
                    image = view.viewport().grab().toImage()
                    scale = image.devicePixelRatio()
                    assert image.pixelColor(round((rect.right()-30)*scale), round((rect.top()+88)*scale)) == QColor(current_colors().tint)
                    assert view.horizontalScrollBar().maximum() == 0
                else:
                    assert window.history.stack.currentWidget() is window.history.empty
                    assert window.history.detail_model.rows == [] and not window.history.copy_root.isEnabled()
            checks.append(dict(theme=window.state.settings.theme, size=[window.width(), window.height()], page=page))

        def history_state(name):
            for theme in ("Light", "Dark", "System"):
                window.state.settings.theme = theme
                window.preferences.theme.setCurrentText(theme)
                window.set_theme()
                for size in sizes:
                    window.resize(*size)
                    window.navigate(4)
                    inspect(4)
                    assert (window.width(), window.height()) == size
                    if (theme, size[0]) in (("Light",1280), ("Dark",1000), ("System",1440)):
                        filename = f"{name}-{theme.lower()}-{size[0]}.png"
                        assert window.grab().save(str(output / filename))
                        captures.append(filename)

        if args.restart_data:
            assert store.history() == []
            history_state("restarted-empty-history")
            (output / "restart-report.json").write_text(json.dumps(dict(fresh_process=True, empty_history=True,
                qt_messages=messages, notices=notices), indent=2), encoding="utf-8")
            window.close()
            assert not messages and not notices
            return

        history_state("initial-empty-history")
        history_root = base / "Earlier review"
        history_root.mkdir()
        for name in ("Brief.txt", "Notes.pdf", "Logo.png"):
            (history_root / name).write_bytes(name.encode())

        def apply():
            window.scan_folder(history_root)
            wait(window)
            window.create_preview()
            wait(window)
            window.apply_organization()
            wait(window)
            return store.history()[0]["id"]

        first = apply()
        history_state("one-actionable")
        window.undo_operation(first)
        wait(window)
        history_state("one-undone")
        second = apply()
        history_state("mixed-history")
        root = base / "Studio archive"
        fixture(root)
        window.scan_folder(root)
        wait(window)
        window.analyze_duplicates()
        wait(window)
        window.create_preview()
        wait(window)
        window.files.view.selectRow(0)
        window.duplicates.view.setCurrentIndex(window.duplicates.model.index(0,0))
        window.organize.view.selectRow(0)

        for theme in ("Light", "Dark", "System"):
            window.state.settings.theme = theme
            window.preferences.theme.setCurrentText(theme)
            window.set_theme()
            for size in sizes:
                window.resize(*size)
                images = []
                for page in range(6):
                    window.navigate(page)
                    inspect(page)
                    assert (window.width(), window.height()) == size
                    if page in (0, 5):
                        scroll = window.dashboard.scroll if page == 0 else window.preferences.scroll
                        for fraction in (0, .5, 1):
                            scroll.verticalScrollBar().setValue(round(scroll.verticalScrollBar().maximum()*fraction))
                            settle()
                        scroll.verticalScrollBar().setValue(0)
                        settle()
                    images.append(window.grab().toImage())
                # Six pages share one contact sheet: nine sheets replace 54 individual PNGs.
                tile_height = round(640*images[0].height()/images[0].width())
                sheet = QImage(1280, 3*(tile_height+24), QImage.Format.Format_RGB32)
                sheet.fill(QColor("#ddd9d1"))
                painter = QPainter(sheet)
                for i, image in enumerate(images):
                    x, y = (i%2)*640, (i//2)*(tile_height+24)
                    painter.setPen(QColor("#29332e"))
                    painter.drawText(x+10,y+17,f"{('Dashboard','Files','Duplicates','Organize','History','Settings')[i]} · {theme} · {size[0]}")
                    scaled = image.scaled(640,tile_height,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
                    scaled.setDevicePixelRatio(1.0)
                    painter.drawImage(x,y+24,scaled)
                painter.end()
                filename = f"pages-{theme.lower()}-{size[0]}.png"
                assert sheet.save(str(output/filename))
                captures.append(filename)

        window.navigate(4)
        window.history.select_operation(first)
        before = snapshot(history_root), snapshot(root)
        window.history.clear.click()
        wait(window)
        assert [row["id"] for row in store.history()] == [second]
        assert (snapshot(history_root),snapshot(root)) == before
        history_state("clear-kept-actionable")
        occupied = history_root / "Notes.pdf"
        occupied.write_bytes(b"occupied original")
        window.undo_operation(second)
        wait(window)
        assert store.history()[0]["status"] == "partial_undo" and not window.history.clear.isEnabled()
        history_state("partial-restore-kept")
        occupied.unlink()
        window.undo_operation(second)
        wait(window)
        # Two fully undone records are clearable together.
        third = apply()
        window.undo_operation(third)
        wait(window)
        history_state("multiple-undone")
        before = snapshot(history_root), snapshot(root)
        window.history.clear.click()
        wait(window)
        assert store.history() == [] and (snapshot(history_root),snapshot(root)) == before
        window.navigate(0)
        window.navigate(4)
        history_state("cleared-empty-history")
        window.close()
        command = [sys.executable,str(Path(__file__).resolve()),"--restart-data",str(store.path)]
        if args.native:
            command.append("--native")
        if args.current_scale:
            command.append("--current-scale")
        subprocess.run(command,check=True,capture_output=True,text=True)
        restarted = json.loads((output/"restart-report.json").read_text(encoding="utf-8"))
        assert restarted["fresh_process"] and restarted["empty_history"] and not restarted["qt_messages"]
        assert notices == ["Undo needs review"], notices
        assert not messages, messages
        report = dict(platform=app.platformName(), device_pixel_ratio=window.devicePixelRatioF(), sizes=sizes,
                      themes=["Light","Dark","System"], page_checks=len(checks), captures=len(captures),
                      files=40, duplicate_groups=2, history_states=8, clear_kept_actionable=True,
                      partial_retry_preserved=True, filesystem_snapshots_unchanged_by_clear=True,
                      fresh_process_restart_cleared=True, qt_messages=messages, expected_notices=notices)
        (output/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
