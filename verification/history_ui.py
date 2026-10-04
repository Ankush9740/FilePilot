"""Verify focused History rendering with actual operations in disposable fixtures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile

if "--native" not in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEventLoop, Qt, QTimer, qInstallMessageHandler
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem, QWidget
from filepilot.core.safety import SafetyPolicy
from filepilot.database.store import Store
from filepilot.ui.theme import current_colors
from filepilot.ui.window import MainWindow
from verification.render_ui import wait

if "--native" in sys.argv:
    os.environ.pop("QT_QPA_PLATFORM", None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--expect-defect", action="store_true")
    parser.add_argument("--restart-data", type=Path, help="Reopen an isolated audit database in a fresh process")
    args = parser.parse_args()
    output = Path(__file__).parent / "output" / ("history-before" if args.expect_defect else "history-fixed")
    output.mkdir(exist_ok=True)
    messages = []
    qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    app = QApplication([])
    app.setStyle("Fusion")
    if not QFontDatabase.families():
        for name in ("segoeui.ttf", "seguisb.ttf", "segoeuib.ttf"):
            QFontDatabase.addApplicationFont(f"C:/Windows/Fonts/{name}")
    captures, checks = [], []
    with tempfile.TemporaryDirectory(prefix="fp-history-") as temporary:
        base = Path(temporary)
        root = base / "History review"
        root.mkdir()
        for index in range(40):
            folder = root / "nested" if index % 3 == 0 else root
            folder.mkdir(exist_ok=True)
            (folder / f"File {index:02d}{('.txt', '.png', '.zip', '.py')[index % 4]}").write_bytes(f"Content {index}".encode())
        original = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
        store = Store(args.restart_data or base / "data/filepilot.sqlite3")
        notices = []

        def open_window():
            instance = MainWindow(Store(store.path), SafetyPolicy((store.path.parent,)))
            instance.notice = lambda *args, **kwargs: notices.append(args[0])
            instance.confirm = lambda *args: True  # Only disposable fixture moves.
            instance.show()
            instance.activateWindow()
            wait(instance)
            return instance

        window = open_window()

        def settle():
            app.processEvents()
            loop = QEventLoop()
            QTimer.singleShot(20, loop.quit)
            loop.exec()
            app.processEvents()

        def focus_row(row):
            view = window.history.view
            index = window.history.model.index(row, 0)
            view.scrollTo(index)
            settle()
            QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view.visualRect(index).center())
            view.setFocus(Qt.FocusReason.MouseFocusReason)
            settle()
            assert view.hasFocus() and view.currentIndex() == index

        def capture(name):
            assert window.grab().save(str(output / f"{name}.png"))
            captures.append(name)

        def inspect(name):
            view = window.history.view
            image = view.viewport().grab().toImage()
            scale = image.devicePixelRatio()
            rect = view.visualRect(view.currentIndex())
            sample = image.pixelColor(round((rect.right() - 30) * scale), round((rect.top() + 88) * scale)).name()
            sizes = [view.visualRect(window.history.model.index(i, 0)) for i in range(window.history.model.rowCount())]
            expected_height = view.itemDelegate().sizeHint(QStyleOptionViewItem(), view.currentIndex()).height()
            assert all(r.height() == expected_height for r in sizes)
            assert all(b.top() == a.bottom() + 1 for a, b in zip(sizes, sizes[1:]))
            assert view.horizontalScrollBar().maximum() == 0
            assert window.pages.currentWidget().width() <= window.pages.width()
            if not args.expect_defect:
                assert sample == QColor(current_colors().tint).name(), (name, sample, current_colors().tint)
            checks.append(dict(state=name, rows=len(sizes), row_heights=[r.height() for r in sizes],
                               current_row=view.currentIndex().row(), focused=view.hasFocus(),
                               interior_color=sample, expected_color=current_colors().tint,
                               timeline_children=len(view.findChildren(QWidget)),
                               viewport_size=[view.viewport().width(), view.viewport().height()]))
            return sample

        def matrix(state, row=0):
            for theme in ("Light", "Dark", "System"):
                window.state.settings.theme = theme
                window.set_theme()
                for width, height in ((1440, 900), (1280, 800), (1000, 680)):
                    window.resize(width, height)
                    window.navigate(4)
                    settle()
                    assert (window.width(), window.height()) == (width, height)
                    focus_row(row)
                    name = f"{state}-{theme.lower()}-{width}"
                    inspect(name)
                    capture(name)

        def apply(source=root):
            window.scan_folder(source)
            wait(window)
            window.create_preview()
            wait(window)
            window.apply_organization()
            wait(window)
            return store.history()[0]["id"]

        def undo(operation_id):
            window.navigate(4)
            window.history.select_operation(operation_id)
            focus_row(window.history.view.currentIndex().row())
            QTest.mouseClick(window.history.undo, Qt.MouseButton.LeftButton)
            wait(window)
            assert store.operation(operation_id)["status"] == "undone"
            assert not window.history.undo.isEnabled() and window.history.undo.text() == "No moves to undo"
            focus_row(window.history.view.currentIndex().row())

        if args.restart_data:
            matrix("restarted-history-top")
            matrix("restarted-history-bottom", len(store.history()) - 1)
            report = dict(platform=app.platformName(), captures=captures, checks=checks,
                          qt_messages=messages, notices=notices, fresh_process=True)
            (output / "restart-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            window.close()
            settle()
            assert not messages and not notices
            return

        first = apply()
        if not args.expect_defect:
            matrix("one-completed")
        undo(first)
        if not args.expect_defect:
            matrix("one-undone-immediate")
        second = apply()
        if not args.expect_defect:
            matrix("new-completed-old-undone")
            matrix("switch-to-older-undone", 1)
        undo(second)
        restored = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
        assert restored == original
        if args.expect_defect:
            window.resize(1280, 800)
            window.navigate(4)
            focus_row(0)
            before = inspect("two-undone-focused")
            capture("two-undone-focused")
            assert before == QColor(current_colors().accent).name(), "Original defect was not reproduced"
        else:
            matrix("two-undone-immediate")
            matrix("switch-to-older-undone-again", 1)
            for _ in range(3):
                window.history.refresh(store.history())
                settle()
            matrix("two-undone-refreshed", 1)
            window.navigate(0)
            settle()
            window.navigate(4)
            matrix("two-undone-returned", 1)
            third = apply()
            small = base / "Later review"
            small.mkdir()
            (small / "Later.txt").write_bytes(b"later file")
            fourth = apply(small)
            undo(fourth)
            assert store.operation(third)["status"] == "completed"
            matrix("new-undone-old-completed")
            # Real short operations create a long persistent journal for scroll checks.
            for i in range(14):
                another = base / f"Scroll fixture {i}"
                another.mkdir()
                (another / "Note.txt").write_bytes(f"Note {i}".encode())
                op = apply(another)
                if i % 2 == 0:
                    undo(op)
            matrix("long-history-top")
            matrix("long-history-bottom", len(store.history()) - 1)
            assert window.history.view.verticalScrollBar().maximum() > 0
            window.close()
            window.deleteLater()
            settle()
            command = [sys.executable, str(Path(__file__).resolve()), "--restart-data", str(store.path)]
            if args.native:
                command.append("--native")
            subprocess.run(command, check=True, capture_output=True, text=True)
            restarted = json.loads((output / "restart-report.json").read_text(encoding="utf-8"))
            assert restarted["fresh_process"] and restarted["platform"] == app.platformName()
            captures.extend(restarted["captures"])
            checks.extend(restarted["checks"])
            messages.extend(restarted["qt_messages"])
            notices.extend(restarted["notices"])
            # The original window was destroyed; report the last live inspected geometry.
            window = open_window()
            window.navigate(4)
            focus_row(0)
        view = window.history.view
        hierarchy = []
        ancestor = view
        while ancestor:
            hierarchy.append(dict(type=type(ancestor).__name__, object_name=ancestor.objectName(),
                                  size=[ancestor.width(), ancestor.height()],
                                  vertical_policy=str(ancestor.sizePolicy().verticalPolicy()),
                                  minimum_height=ancestor.minimumHeight(), maximum_height=ancestor.maximumHeight()))
            ancestor = ancestor.parentWidget()
        report = dict(platform=app.platformName(), device_pixel_ratio=window.devicePixelRatioF(),
                      captures=len(captures), states=sorted({c["state"].rsplit("-", 2)[0] for c in checks}),
                      checks=checks, hierarchy=hierarchy, splitter_sizes=view.parentWidget().sizes(),
                      qt_messages=messages, notices=notices, exact_40_file_restoration=restored == original,
                      history_statuses=[op["status"] for op in store.history()],
                      fresh_process_restart_verified=not args.expect_defect)
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items() if k not in ("checks", "hierarchy")}, indent=2))
        window.close()
        settle()
        assert not messages and not notices


if __name__ == "__main__":
    main()
