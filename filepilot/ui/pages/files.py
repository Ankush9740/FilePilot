import time
from datetime import datetime

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from filepilot.core.categories import Category, human_size
from filepilot.ui.components.controls import ElidedLabel, FilterCombo, SearchField
from filepilot.ui.components.details import DetailStrip
from filepilot.ui.components.tables import FileFilter, FileTableModel, table
from filepilot.ui.components.widgets import EmptyState, Page, button, label
from filepilot.ui.state import AppState


class AnalysisFilter(FileFilter):
    mode = "All files"
    large_bytes = 100 * 1024 * 1024
    old_cutoff = 0.0

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        if not super().filterAcceptsRow(row, parent):
            return False
        file = self.sourceModel().rows[row]
        return (self.mode == "All files" or self.mode == "Large files" and file.size >= self.large_bytes
                or self.mode == "Older files" and file.modified < self.old_cutoff)


class FilesPage(Page):
    choose_folder = Signal()
    reveal_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__("Your files", "Search, sort, and inspect everything in the selected folder, including subfolders.")
        self.total_size = 0
        self.reveal = button("Show in Explorer")
        self.reveal.setToolTip("Reveal the selected file in Windows Explorer")
        self.reveal.clicked.connect(self.reveal_selected)
        self.actions.addWidget(self.reveal)
        self.stack = QStackedWidget()
        self.layout.addWidget(self.stack, 1)
        self.empty = EmptyState("See the whole picture.", "Choose a folder to browse its files by name, category, size, or date.",
                                "Choose Folder", kind="files", eyebrow="FIND & INSPECT")
        self.empty.action.clicked.connect(self.choose_folder)
        self.stack.addWidget(self.empty)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.stack.addWidget(body)
        filter_bar = QFrame()
        filter_bar.setObjectName("FilterBar")
        filters = QVBoxLayout(filter_bar)
        filters.setContentsMargins(10, 10, 10, 10)
        filters.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.search = SearchField()
        top.addWidget(self.search, 1)
        self.category = FilterCombo("All categories", "Filter files by category")
        self.category.addItems(list(map(str, Category)))
        top.addWidget(self.category)
        self.extension = FilterCombo("All extensions", "Filter files by extension")
        top.addWidget(self.extension)
        filters.addLayout(top)
        detail = QHBoxLayout()
        self.mode = FilterCombo("All files", "Filter large or older files")
        self.mode.addItems(["Large files", "Older files"])
        detail.addWidget(self.mode)
        self.threshold_hint = ElidedLabel("", "helper")
        detail.addWidget(self.threshold_hint, 1)
        self.active_filters = label("", "helper")
        detail.addWidget(self.active_filters)
        self.reset = button("Reset filters")
        self.reset.setProperty("quiet", True)
        self.reset.clicked.connect(self.reset_filters)
        detail.addWidget(self.reset)
        filters.addLayout(detail)
        layout.addWidget(filter_bar)
        self.model = FileTableModel()
        self.proxy = AnalysisFilter()
        self.proxy.setSourceModel(self.model)
        self.view = table(self.proxy, sort=True)
        for col, width in enumerate((230, 105, 90, 155)):
            self.view.setColumnWidth(col, width)
        self.view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.view.setAccessibleName("Scanned files, sorted and filtered")
        layout.addWidget(self.view, 1)
        self.no_results = label("No files match these filters. Reset filters to see the full scan.", "helper", wrap=True)
        layout.addWidget(self.no_results)
        self.details = DetailStrip()
        layout.addWidget(self.details)
        result_strip = QFrame()
        result_strip.setObjectName("ResultStrip")
        result = QHBoxLayout(result_strip)
        result.setContentsMargins(10, 6, 10, 6)
        self.count = label("", "helper")
        result.addWidget(self.count, 1)
        result.addWidget(label("Click column headings to sort", "helper"))
        layout.addWidget(result_strip)
        self.search.textChanged.connect(self.filter)
        self.category.currentTextChanged.connect(self.filter)
        self.extension.currentTextChanged.connect(self.filter)
        self.mode.currentTextChanged.connect(self.filter)
        self.view.selectionModel().selectionChanged.connect(self.selection_changed)
        self.view.doubleClicked.connect(lambda _: self.reveal_selected())
        self.reveal.setEnabled(False)

    def selected_file(self):
        rows = self.view.selectionModel().selectedRows()
        return self.model.rows[self.proxy.mapToSource(rows[0]).row()] if rows else None

    def selection_changed(self, *args) -> None:
        file = self.selected_file()
        self.reveal.setEnabled(file is not None)
        if file:
            self.details.set_details(file.name, [("Full path", str(file.path)), ("Filename", file.name),
                ("Category", str(file.category)), ("Size", f"{human_size(file.size)} ({file.size:,} bytes)"),
                ("Modified", datetime.fromtimestamp(file.modified).strftime("%d %b %Y, %H:%M:%S"))], file.path)
        else:
            self.details.clear()

    def reveal_selected(self) -> None:
        file = self.selected_file()
        if file:
            self.reveal_requested.emit(file.path)

    def reset_filters(self, *args, mode: str = "All files", category: str = "All categories") -> None:
        for control in (self.search, self.category, self.extension, self.mode):
            control.blockSignals(True)
        self.search.clear()
        self.category.setCurrentText(category)
        self.extension.setCurrentText("All extensions")
        self.mode.setCurrentText(mode)
        for control in (self.search, self.category, self.extension, self.mode):
            control.blockSignals(False)
        for combo in (self.category, self.extension, self.mode):
            combo.update_active()
        self.filter()

    def filter(self, *args) -> None:
        self.proxy.mode = self.mode.currentText()
        self.proxy.refilter(self.search.text(), self.category.currentText(), self.extension.currentText())
        active = int(bool(self.search.text())) + sum(combo.currentText() != combo.default for combo in (self.category, self.extension, self.mode))
        self.active_filters.setText(f"{active} active filter{'s' if active != 1 else ''}" if active else "All files visible")
        self.reset.setVisible(bool(active))
        self.count.setText(f"{self.proxy.rowCount():,} of {len(self.model.rows):,} files · {human_size(self.total_size)} scanned")
        self.no_results.setVisible(self.proxy.rowCount() == 0 and bool(self.model.rows))
        self.selection_changed()

    def refresh(self, state: AppState) -> None:
        self.stack.setCurrentIndex(int(state.scan is not None))
        self.reveal.setVisible(state.scan is not None)
        if state.scan is None:
            return
        self.total_size = state.analysis.total_size if state.analysis else state.scan.total_size
        self.model.set_rows(state.scan.files)
        current = self.extension.currentText()
        self.extension.blockSignals(True)
        self.extension.clear()
        self.extension.addItems(["All extensions", *sorted({file.extension or "(no extension)" for file in state.scan.files})])
        self.extension.setCurrentIndex(max(0, self.extension.findText(current)))
        self.extension.blockSignals(False)
        self.extension.update_active()
        self.proxy.large_bytes = state.settings.large_mb * 1024 * 1024
        self.proxy.old_cutoff = time.time() - state.settings.old_days * 86400
        self.threshold_hint.setText(f"Large ≥ {state.settings.large_mb:,} MB  ·  Older = {state.settings.old_days:,} days without changes")
        self.filter()

    def set_busy(self, busy: bool) -> None:
        super().set_busy(busy)
        self.empty.action.setEnabled(not busy)
