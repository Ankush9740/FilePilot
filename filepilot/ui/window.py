from collections.abc import Callable
from pathlib import Path
import sqlite3
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from filepilot.core.paths import application_directory
from filepilot.core.safety import SafetyPolicy
from filepilot.database.store import Store
from filepilot.models.records import DuplicateResult, Issue, OperationResult, Settings
from filepilot.services.analysis import analyze
from filepilot.services.duplicates import find_duplicates
from filepilot.services.organizer import Organizer, validate_settings
from filepilot.services.scanner import Scanner
from filepilot.ui.components.shell import FeedbackBar, Sidebar, StatusBar, WorkspaceHeader
from filepilot.ui.components.widgets import count_label, divider, show_in_explorer
from filepilot.ui.pages.dashboard import DashboardPage
from filepilot.ui.pages.duplicates import DuplicatesPage
from filepilot.ui.pages.files import FilesPage
from filepilot.ui.pages.history import HistoryPage, undo_available
from filepilot.ui.pages.organize import OrganizePage, NESTED_EXPLANATION
from filepilot.ui.pages.settings import SettingsPage
from filepilot.ui.state import AppState
from filepilot.ui.theme import apply_theme
from filepilot.ui.workers import Job


class MainWindow(QMainWindow):
    def __init__(self, store: Store, policy: SafetyPolicy | None = None) -> None:
        super().__init__()
        self.store = store
        self.policy = policy or SafetyPolicy((application_directory(), store.path.parent))
        self.scanner = Scanner(self.policy)
        self.organizer = Organizer(self.policy, store)
        self.state = AppState(settings=store.load_settings())
        self.job: Job | None = None
        self.close_pending = False
        self.setWindowTitle("FilePilot — Organize smarter. Find what matters.")
        self.resize(1280, 800)
        self.setMinimumSize(1000, 680)
        shell = QWidget()
        shell.setObjectName("Shell")
        self.setCentralWidget(shell)
        root = QHBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = Sidebar()
        root.addWidget(self.sidebar)
        work = QVBoxLayout()
        work.setContentsMargins(0, 0, 0, 0)
        work.setSpacing(0)
        self.header = WorkspaceHeader()
        work.addWidget(self.header)
        work.addWidget(divider())
        self.pages = QStackedWidget()
        self.dashboard = DashboardPage()
        self.files = FilesPage()
        self.duplicates = DuplicatesPage()
        self.organize = OrganizePage()
        self.history = HistoryPage()
        self.preferences = SettingsPage(self.state.settings)
        self.page_widgets = (self.dashboard, self.files, self.duplicates, self.organize, self.history, self.preferences)
        for page in self.page_widgets:
            self.pages.addWidget(page)
        work.addWidget(self.pages, 1)
        self.feedback = FeedbackBar()
        work.addWidget(self.feedback)
        work.addWidget(divider())
        self.status_bar = StatusBar()
        work.addWidget(self.status_bar)
        root.addLayout(work, 1)
        # Stable public controls used by the startup and UI verification harnesses.
        self.nav, self.mark = self.sidebar.nav, self.sidebar.mark
        self.side_folder = self.sidebar.folder
        self.folder_label = self.header.path
        self.rescan, self.choose = self.header.rescan, self.header.choose
        self.status = self.status_bar.message
        self.progress, self.cancel = self.status_bar.progress, self.status_bar.cancel
        self.sidebar.navigate_requested.connect(self.navigate)
        self.choose.clicked.connect(self.choose_folder)
        self.rescan.clicked.connect(self.rescan_folder)
        self.cancel.clicked.connect(self.cancel_job)
        self.feedback.history_requested.connect(lambda: self.navigate(4))
        for page in (self.dashboard, self.files, self.duplicates, self.organize):
            page.choose_folder.connect(self.choose_folder)
        self.dashboard.files_requested.connect(self.browse_files)
        self.dashboard.category_requested.connect(self.browse_category)
        self.dashboard.duplicates_requested.connect(lambda: self.navigate(2))
        for page in (self.dashboard, self.files, self.duplicates):
            page.reveal_requested.connect(self.reveal)
        self.duplicates.analyze_requested.connect(self.analyze_duplicates)
        self.organize.preview_requested.connect(self.create_preview)
        self.organize.apply_requested.connect(self.apply_organization)
        self.organize.cancel_requested.connect(self.cancel_preview)
        self.history.undo_requested.connect(self.undo_operation)
        self.history.selection_requested.connect(self.history_details)
        self.history.clear_requested.connect(self.clear_history)
        self.preferences.save_requested.connect(self.save_preferences)
        self.shortcuts = []
        for key, callback in (("Ctrl+O", self.choose_folder), ("Ctrl+R", self.rescan_folder), ("Ctrl+F", self.focus_search)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        QApplication.instance().styleHints().colorSchemeChanged.connect(self.system_theme_changed)
        self.set_theme()
        self.refresh()
        self.navigate(0)


    def initialize(self, folder: Path | None = None) -> None:
        def recovered(issues: list[Issue]) -> None:
            self.refresh_history()
            if issues:
                self.notice("Interrupted operations", "Some interrupted items need manual review in History. No files were moved during recovery.", issues)
            if folder:
                self.scan_folder(folder)
        self.start_job("Checking local history", self.organizer.recover, recovered)

    def set_theme(self) -> None:
        colors = apply_theme(QApplication.instance(), self.state.settings.theme)
        self.colors = colors
        self.mark.color = colors.accent
        self.mark.update()
        self.update_nav_icons()
        self.header.update_icons()
        self.preferences.update_icons()
        self.update()

    def update_nav_icons(self) -> None:
        self.sidebar.update_icons()

    def system_theme_changed(self, *args) -> None:
        if self.state.settings.theme == "System":
            self.set_theme()

    def navigate(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.nav[index].setChecked(True)
        self.update_nav_icons()

    def browse_files(self, mode: str) -> None:
        self.files.reset_filters(mode=mode)
        self.navigate(1)

    def browse_category(self, category: str) -> None:
        self.files.reset_filters(category=category)
        self.navigate(1)

    def focus_search(self) -> None:
        self.navigate(1)
        self.files.search.setFocus()

    def choose_folder(self) -> None:
        if self.job:
            return
        root = QFileDialog.getExistingDirectory(self, "Choose a folder to analyze", str(self.state.scan.root) if self.state.scan else "")
        if root:
            self.scan_folder(Path(root))

    def rescan_folder(self) -> None:
        if self.state.scan and not self.job:
            self.scan_folder(self.state.scan.root)

    def scan_folder(self, root: Path, completion_status: str = "") -> None:
        if self.job:
            return
        settings = self.state.settings
        def work(cancel, progress):
            result = self.scanner.scan(root, cancel, progress)
            return result, analyze(result.files, settings)
        def finished(result):
            self.state.scan, self.state.analysis = result
            self.state.duplicates, self.state.plan = None, None
            self.refresh()
            scan = self.state.scan
            message = f"{'Partial scan' if scan.cancelled else 'Scan complete'} · {len(scan.files):,} files · {len(scan.issues):,} access issues · {scan.skipped_links:,} links skipped · {scan.skipped_protected:,} protected paths skipped"
            self.set_status(completion_status or f"{'Partial scan' if scan.cancelled else 'Scanned'} · {count_label(len(scan.files), 'file')}", message)
            if scan.issues:
                self.notice("Scan completed with access issues", message, scan.issues)
        self.start_job("Scanning folder", work, finished)

    def analyze_duplicates(self) -> None:
        if self.state.scan is None or self.job:
            return
        files = self.state.scan.files
        def finished(result: DuplicateResult):
            self.state.duplicates = result
            self.refresh()
            self.set_status(f"{'Partial comparison' if result.cancelled else 'Comparison complete'} · {len(result.groups):,} duplicate groups",
                            f"{result.hashed_files:,} files hashed · {len(result.issues):,} issues")
            if result.issues:
                self.notice("Duplicate analysis issues", "Some files could not be compared. Results include only files successfully read.", result.issues)
        self.start_job("Comparing file contents", lambda cancel, progress: find_duplicates(files, cancel, progress), finished)

    def create_preview(self) -> None:
        if self.state.scan is None or self.state.scan.cancelled or self.job:
            return
        scan, settings = self.state.scan, self.state.settings
        def finished(plan):
            self.state.plan = plan
            self.organize.refresh(self.state)
            self.set_status("Preview ready. No files have been moved.")
        self.start_job("Preparing organization preview", lambda cancel, progress: self.organizer.plan(scan, settings, cancel, progress), finished)

    def cancel_preview(self) -> None:
        if self.job:
            return
        self.state.plan = None
        self.organize.refresh(self.state)
        self.set_status("Preview cancelled. No files were moved.")

    def confirm(self, title: str, text: str, action: str) -> bool:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle(title)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(text)
        proceed = dialog.addButton(action, QMessageBox.ButtonRole.AcceptRole)
        cancel = dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(cancel)
        dialog.setEscapeButton(cancel)
        dialog.exec()
        return dialog.clickedButton() == proceed

    def apply_organization(self) -> None:
        plan = self.state.plan
        if not plan or not plan.actionable or self.job:
            return
        nested = sum(item.file.path.parent != plan.root for item in plan.actionable)
        text = (f"Move {count_label(len(plan.actionable), 'file')} within:\n{plan.root}\n\n{NESTED_EXPLANATION}\n"
                f"This preview includes {count_label(nested, 'nested file')}.\n\nFilename conflicts will be skipped. "
                "Successful moves will be recorded in History for undo.")
        if not self.confirm("Apply organization?", text, "Move files"):
            return
        self.start_job("Organizing files", lambda cancel, progress: self.organizer.apply(plan, cancel, progress),
                       lambda result: self.operation_finished(result, "Organization"))

    def undo_operation(self, operation_id: int) -> None:
        if self.job:
            return
        operation = next((row for row in self.history.model.rows if row["id"] == operation_id), None)
        if not operation or not undo_available(operation):
            return
        text = (f"Restore {count_label(operation['remaining'], 'file')} from operation #{operation_id:04d}?\n"
                f"Working folder: {operation['source_root']}\n\nFilePilot checks each file before restoring it. "
                "Occupied locations and changed files will be skipped. Partial restores stay recorded in History.")
        if not self.confirm("Restore original locations?", text, "Restore files"):
            return
        self.start_job("Restoring original locations", lambda cancel, progress: self.organizer.undo(operation_id, cancel, progress),
                       lambda result: self.operation_finished(result, "Undo"))

    def operation_finished(self, result: OperationResult, title: str) -> None:
        self.state.plan = None
        self.refresh_history()
        self.history.select_operation(result.operation_id)
        message = f"{count_label(result.succeeded, 'file')} {'restored' if title == 'Undo' else 'moved'} · {result.failed:,} skipped · {result.status.replace('_', ' ')}"
        self.feedback.show_result(message)
        if result.issues:
            self.notice(f"{title} needs review", message, result.issues)
        if self.state.scan:
            self.scan_folder(self.state.scan.root, message)
        else:
            self.refresh()
            self.set_status(message.replace("\n", " · "))

    def history_details(self, operation_id: int) -> None:
        try:
            self.history.detail_model.set_rows(self.store.items(operation_id))
        except sqlite3.Error as error:
            self.history.undo.setEnabled(False)
            self.notice("History unavailable", str(error))

    def clear_history(self) -> None:
        if self.job or not any(row.get("clearable", False) for row in self.history.model.rows):
            return
        if not self.confirm("Clear completed history?",
                            "This removes completed history records only. Your files will not be changed. "
                            "Operations that can still be undone will be kept.", "Clear history"):
            return

        def clear(cancel, progress):
            try:
                return self.store.clear_history(), ""
            except (sqlite3.Error, OSError) as error:
                return 0, str(error)

        def finished(result):
            count, error = result
            self.refresh_history()
            if error:
                self.set_status("History could not be cleared. Your files were not changed.")
                self.notice("History could not be cleared", "Your files were not changed. Please try again.", detail=error)
                return
            message = (f"{count_label(count, 'history record')} cleared. Your files were not changed." if count else
                       "No completed history records were eligible to clear. Your files were not changed.")
            self.feedback.show_result(message)
            self.set_status(message)

        self.start_job("Clearing completed history", clear, finished)

    def refresh_history(self) -> None:
        try:
            self.history.refresh(self.store.history())
        except sqlite3.Error as error:
            self.history.undo.setEnabled(False)
            self.history.clear.setEnabled(False)
            self.history.clear.setToolTip("History is unavailable. Refresh or restart FilePilot to try again.")
            self.set_status(f"History unavailable: {error}")

    def save_preferences(self, settings: Settings) -> None:
        if self.job:
            return
        try:
            validate_settings(settings)
            self.store.save_settings(settings)
        except (ValueError, OSError, sqlite3.Error) as error:
            self.notice("Preferences could not be saved", str(error))
            return
        self.state.settings, self.state.plan = settings, None
        self.preferences.mark_saved(settings)
        self.set_theme()
        if self.state.scan:
            files = self.state.scan.files
            def finished(result):
                self.state.analysis = result
                self.refresh()
                self.set_status("Preferences saved. Analysis reflects your new thresholds.")
            self.start_job("Updating insights", lambda cancel, progress: analyze(files, settings), finished)
        else:
            self.refresh()
            self.set_status("Preferences saved on this computer.")

    def refresh(self) -> None:
        for page in (self.dashboard, self.files, self.duplicates, self.organize):
            page.refresh(self.state)
        self.refresh_history()
        self.rescan.setEnabled(self.state.scan is not None and self.job is None)
        self.header.set_folder(self.state.scan.root if self.state.scan else None)
        self.sidebar.set_scan(self.state.scan)

    def set_busy(self, busy: bool) -> None:
        for page in self.page_widgets:
            page.set_busy(busy)
        self.choose.setEnabled(not busy)
        self.rescan.setEnabled(not busy and self.state.scan is not None)
        self.status_bar.set_busy(busy)

    def start_job(self, title: str, function: Callable, done: Callable[[Any], None]) -> None:
        if self.job:
            return
        self.set_busy(True)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.cancel.setEnabled(True)
        self.cancel.show()
        self.set_status(title + "…")
        job = Job(function)
        self.job = job
        job.progress.connect(lambda current, total, detail: self.job_progress(title, current, total, detail))
        def finish():
            self.job = None
            self.set_busy(False)
            try:
                if job.error:
                    self.set_status("Operation stopped. Review the error details.")
                    self.state.plan = None
                    self.refresh()
                    self.notice("Operation could not finish", "FilePilot stopped after an error. History records any completed moves; unresolved items are checked on next launch.", detail=job.error)
                elif job.cancelled:
                    self.set_status("Cancelled. No new changes were applied by this step.")
                else:
                    done(job.result)
            finally:
                job.deleteLater()
                if self.close_pending:
                    # A completion callback may have started a rescan. Cancel it before closing.
                    if self.job:
                        self.job.cancel()
                    else:
                        self.close()
        job.finished.connect(finish)
        job.start()

    def job_progress(self, title: str, current: int, total: int, detail: str) -> None:
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
        self.set_status(f"{title} · {current:,}{f' / {total:,}' if total else ' files'}", detail)

    def cancel_job(self) -> None:
        if self.job:
            self.job.cancel()
            self.cancel.setEnabled(False)
            self.set_status("Cancelling safely. Waiting for the current work unit…")

    def set_status(self, text: str, detail: str = "") -> None:
        self.status.setText(text)
        self.status.setToolTip(f"{text}\n{detail}" if detail else text)

    def notice(self, title: str, text: str, issues: list[Issue] | None = None, detail: str = "") -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(text)
        dialog.setIcon(QMessageBox.Icon.Warning if issues or detail else QMessageBox.Icon.Information)
        if issues:
            # Avoid building an enormous modal dialog for millions of inaccessible paths.
            detail = "\n\n".join(f"{issue.path}\n{issue.message}" for issue in issues[:200])
            if len(issues) > 200:
                detail += f"\n\n{len(issues) - 200:,} additional issues."
        if detail:
            dialog.setDetailedText(detail)
        dialog.exec()

    def reveal(self, path: Path) -> None:
        try:
            show_in_explorer(path)
        except OSError as error:
            self.notice("File could not be revealed", str(error))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.job and self.job.isRunning():
            self.close_pending = True
            self.cancel_job()
            event.ignore()
        else:
            event.accept()
