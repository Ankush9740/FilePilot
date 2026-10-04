"""Exercise the approved native product end to end on disposable data only."""
import ctypes
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt, QTimer, qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from filepilot.core.safety import SafetyPolicy
from filepilot.database.store import Store
from filepilot.models.records import Settings
from filepilot.ui.window import MainWindow
from verification.refinement_ui import fixture, wait


def snapshot(root):
    files = {}
    folders = set()
    for path in root.rglob("*"):
        relative = str(path.relative_to(root))
        if path.is_dir():
            folders.add(relative)
        else:
            info = path.stat()
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            files[relative] = (info.st_size, info.st_mtime_ns, digest.hexdigest(), getattr(info, "st_file_attributes", 0))
    return files, folders


def main():
    messages = []
    qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    app = QApplication([])
    app.setStyle("Fusion")
    output = Path(__file__).parent / "output" / "production-audit"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fp-final-") as temporary:
        base = Path(temporary)
        root = base / "Studio archive"
        long_file = fixture(root)
        (root / "Documents").mkdir()  # A user-created empty category must survive.
        (root / "Empty user folder").mkdir()
        if os.name == "nt":
            hidden = root / "Editorial notes 22.txt"
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.SetFileAttributesW.argtypes = (ctypes.c_wchar_p, ctypes.c_uint32)
            kernel.SetFileAttributesW.restype = ctypes.c_int
            assert kernel.SetFileAttributesW(str(hidden), hidden.stat().st_file_attributes | 2)
        before = snapshot(root)
        store = Store(base / "data" / "filepilot.sqlite3")
        store.save_settings(Settings(large_mb=95))
        window = MainWindow(store, SafetyPolicy((store.path.parent,)))
        notices = []
        window.notice = lambda *args, **kwargs: notices.append(args[0])
        window.resize(1280, 800)
        window.show()
        window.initialize()
        wait(window)
        # The native picker entry point is exercised with a deterministic fixture selection.
        original_picker = QFileDialog.getExistingDirectory
        QFileDialog.getExistingDirectory = lambda *args, **kwargs: str(root)
        try:
            window.choose_folder()
            wait(window)
        finally:
            QFileDialog.getExistingDirectory = original_picker
        assert len(window.state.scan.files) == 40 and not window.state.scan.issues
        for _ in range(2):
            window.rescan_folder()
            wait(window)
        window.navigate(1)
        window.files.search.setText(long_file.name)
        assert window.files.proxy.rowCount() == 1
        window.files.view.selectRow(0)
        assert str(long_file) in window.files.details.details_text
        window.browse_category("Images")
        assert window.files.proxy.rowCount() == 4
        window.browse_files("Large files")
        assert window.files.proxy.rowCount() == 1
        window.browse_files("Older files")
        assert window.files.proxy.rowCount() == 22
        window.browse_files("All files")
        window.files.view.sortByColumn(2, Qt.SortOrder.DescendingOrder)
        assert window.files.selected_file() is None
        first = window.files.proxy.mapToSource(window.files.proxy.index(0, 0))
        assert window.files.model.rows[first.row()].name == "Studio installer.exe"
        window.files.view.sortByColumn(3, Qt.SortOrder.AscendingOrder)
        first = window.files.proxy.mapToSource(window.files.proxy.index(0, 0))
        assert window.files.model.rows[first.row()].name.startswith("Editorial notes")
        duplicate_groups = None
        for _ in range(2):
            window.analyze_duplicates()
            wait(window)
            current = window.state.duplicates
            assert len(current.groups) == 2 and current.extra_copies == 3
            read_hashes = snapshot(root)[0]
            assert all(all(read_hashes[str(file.path.relative_to(root))][2] == group.digest for file in group.files) for group in current.groups)
            groups = [(group.digest, tuple(file.path for file in group.files)) for group in current.groups]
            assert duplicate_groups is None or groups == duplicate_groups
            duplicate_groups = groups
        for _ in range(2):
            window.create_preview()
            wait(window)
            assert len(window.state.plan.actionable) == 40
        assert snapshot(root) == before, "Scan, hashing, sorting and preview changed fixture contents"

        def capture(name, widget=window):
            app.processEvents()
            app.processEvents()
            assert widget.grab().save(str(output / f"{name}.png"))

        window.navigate(3)
        capture("preview-before-apply")
        confirmations = []
        def confirm_fixture(action):
            def accept():
                for dialog in app.topLevelWidgets():
                    if isinstance(dialog, QMessageBox):
                        if action == "Clear history":
                            assert "Your files will not be changed" in dialog.text()
                            assert "can still be undone will be kept" in dialog.text()
                            assert dialog.defaultButton() == dialog.button(QMessageBox.StandardButton.Cancel)
                        else:
                            assert str(root) in dialog.text() and "40" in dialog.text()
                        confirmations.append(dialog.text())
                        capture("apply-confirmation" if action == "Move files" else
                                "clear-history-confirmation" if action == "Clear history" else "undo-confirmation", dialog)
                        button = next(button for button in dialog.buttons() if button.text() == action)
                        button.click()
            QTimer.singleShot(30, accept)

        busy_navigation = []
        navigation = QTimer()
        navigation.setInterval(50)
        def navigate_during_work():
            if window.job:
                index = len(busy_navigation) % 6
                window.navigate(index)
                assert window.pages.isEnabled() and not window.choose.isEnabled()
                busy_navigation.append(index)
        navigation.timeout.connect(navigate_during_work)
        navigation.start()
        confirm_fixture("Move files")
        window.apply_organization()
        wait(window)
        operation = store.history()[0]
        assert (operation["remaining"], operation["restored"], operation["failures"], operation["status"]) == (40, 0, 0, "completed")
        ownership = store.directories(operation["id"])
        assert len(ownership) == 8
        assert sum(row["state"] == "created" for row in ownership) == 7
        assert next(row for row in ownership if Path(row["path"]).name == "Documents")["state"] == "existing"
        window.navigate(4)
        capture("history-after-apply")
        confirm_fixture("Restore files")
        window.undo_operation(operation["id"])
        wait(window)
        navigation.stop()
        assert busy_navigation, "Navigation did not run during the actual file worker"
        restored = store.history()[0]
        assert (restored["remaining"], restored["restored"], restored["failures"], restored["status"]) == (0, 40, 0, "undone")
        assert sum(row["state"] == "removed" for row in store.directories(operation["id"])) == 7
        assert (root / "Documents").is_dir() and (root / "Empty user folder").is_dir()
        assert snapshot(root) == before, "Undo failed to restore exactly the original files and folder tree"
        assert len(window.state.scan.files) == 40
        assert not window.history.undo.isEnabled() and window.history.undo.text() == "No moves to undo"
        window.navigate(4)
        window.history.details.selectRow(0)
        window.history.view.setFocus()
        capture("history-after-cleanup")
        assert len(confirmations) == 2
        assert window.history.clear.isEnabled()
        scan_before_clear = window.state.scan
        confirm_fixture("Clear history")
        window.history.clear.click()
        wait(window)
        assert store.history() == [] and Store(store.path).history() == []
        assert window.history.stack.currentWidget() is window.history.empty
        assert not window.history.clear.isEnabled() and not window.history.undo.isEnabled()
        assert window.state.scan is scan_before_clear and snapshot(root) == before
        capture("history-after-clear")
        assert len(confirmations) == 3
        window.navigate(5)
        window.preferences.theme.options["Dark"].click()
        window.preferences.old_days.setValue(90)
        window.preferences.save.click()
        wait(window)
        assert Store(store.path).load_settings().theme == "Dark"
        assert Store(store.path).load_settings().old_days == 90
        assert window.preferences.feedback.text() == "Saved locally"
        capture("saved-settings")
        assert not notices, notices
        assert not messages, messages
        report = dict(platform=app.platformName(), logical_size=[window.width(), window.height()],
                      device_pixel_ratio=window.devicePixelRatioF(), files_scanned=40, files_moved=40,
                      files_restored=40, remaining=0, skipped=0, created_categories=7,
                      removed_categories=7, preexisting_category_preserved=True,
                      exact_file_and_folder_snapshot_restored=True, repeated_scans=3,
                      repeated_duplicate_runs=2, sha256_groups_verified=True, repeated_previews=2,
                      native_confirmations=len(confirmations), navigation_events_during_real_workers=len(busy_navigation),
                      windows_hidden_file_verified=os.name == "nt", settings_persisted=True,
                      cleared_history_records=1, clear_history_snapshot_unchanged=True,
                      qt_messages=messages, notices=notices)
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        window.close()


if __name__ == "__main__":
    main()
