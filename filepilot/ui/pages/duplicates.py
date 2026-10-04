from PySide6.QtCore import Signal
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QStackedWidget, QTreeView, QVBoxLayout, QWidget

from filepilot.core.categories import human_size
from filepilot.models.records import DuplicateGroup
from filepilot.ui.components.details import DetailStrip
from filepilot.ui.components.duplicate_model import DuplicateDelegate, DuplicateModel
from filepilot.ui.components.overview import SummaryStrip
from filepilot.ui.components.tables import RECORD_ROLE
from filepilot.ui.components.widgets import EmptyState, Page, button, label
from filepilot.ui.state import AppState


class DuplicatesPage(Page):
    choose_folder = Signal()
    analyze_requested = Signal()
    reveal_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__("Exact duplicates", "Review content matches together. Every copy remains yours to inspect.")
        self.can_analyze = False
        self.analyze = button("Find duplicates", True)
        self.analyze.clicked.connect(self.analyze_requested)
        self.actions.addWidget(self.analyze)
        self.stack = QStackedWidget()
        self.layout.addWidget(self.stack, 1)
        self.no_folder = EmptyState("Find the hidden repetition.", "Choose a folder to compare file contents locally.",
                                    "Choose Folder", kind="duplicates", eyebrow="EXACT CONTENT COMPARISON")
        self.no_folder.action.clicked.connect(self.choose_folder)
        self.not_run = EmptyState("A closer look at your copies.", "FilePilot groups matching sizes, then compares SHA-256 hashes.\nFiles stay in place throughout the analysis.",
                                  "Find duplicates", kind="duplicates", eyebrow="SIZE FIRST. CONTENT SECOND.")
        self.not_run.action.clicked.connect(self.analyze_requested)
        self.no_matches = EmptyState("No matching copies found.", "No exact matches were found among the files successfully read.",
                                     kind="duplicates", eyebrow="COMPARISON COMPLETE")
        for widget in (self.no_folder, self.not_run, self.no_matches):
            self.stack.addWidget(widget)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.summary = SummaryStrip([("MATCHING GROUPS", "Duplicates"), ("EXTRA COPIES", "copy"), ("REDUNDANT SPACE", "Archives")])
        self.summary.setFixedHeight(94)
        layout.addWidget(self.summary)
        controls = QHBoxLayout()
        self.analysis_note = label("Verified with SHA-256 · no files deleted", "helper")
        controls.addWidget(self.analysis_note, 1)
        expand = button("Expand groups")
        expand.setProperty("quiet", True)
        expand.clicked.connect(lambda: self.view.expandAll())
        controls.addWidget(expand)
        collapse = button("Collapse")
        collapse.setProperty("quiet", True)
        collapse.clicked.connect(lambda: self.view.collapseAll())
        controls.addWidget(collapse)
        layout.addLayout(controls)
        self.model = DuplicateModel()
        self.view = QTreeView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(DuplicateDelegate(self.view))
        self.view.setUniformRowHeights(False)
        self.view.setMouseTracking(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.header().setStretchLastSection(True)
        self.view.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate((265, 125, 100)):
            self.view.setColumnWidth(col, width)
        self.view.setAccessibleName("Duplicate groups and their matching files")
        layout.addWidget(self.view, 1)
        self.details = DetailStrip("Select a group or matching file to inspect full details.")
        layout.addWidget(self.details)
        footer = QHBoxLayout()
        footer.addWidget(label("Redundant bytes count extra copies. Hard links may share actual disk space.", "helper", wrap=True), 1)
        self.reveal = button("Show in Explorer")
        self.reveal.clicked.connect(self.reveal_selected)
        footer.addWidget(self.reveal)
        layout.addLayout(footer)
        self.stack.addWidget(body)
        self.view.selectionModel().selectionChanged.connect(self.selection_changed)
        self.view.doubleClicked.connect(lambda _: self.reveal_selected())

    def selection_changed(self, *args) -> None:
        index = self.view.currentIndex()
        self.reveal.setEnabled(self.model.selected_path(index) is not None)
        record = index.data(RECORD_ROLE) if index.isValid() else None
        if isinstance(record, DuplicateGroup):
            self.details.set_details(record.files[0].name, [("Matching files", "\n".join(str(file.path) for file in record.files)),
                ("Copies", str(len(record.files))), ("Size of each file", human_size(record.files[0].size)),
                ("Redundant logical storage", human_size(record.redundant_size)), ("SHA-256", record.digest)],
                record.files[0].path, "Duplicate group details")
        elif record:
            self.details.set_details(record.name, [("Full path", str(record.path)), ("Filename", record.name),
                ("Category", str(record.category)), ("Size", human_size(record.size))], record.path)
        else:
            self.details.clear()

    def reveal_selected(self) -> None:
        path = self.model.selected_path(self.view.currentIndex())
        if path:
            self.reveal_requested.emit(path)

    def refresh(self, state: AppState) -> None:
        self.can_analyze = state.scan is not None
        self.analyze.setVisible(self.can_analyze)
        self.analyze.setText("Run again" if state.duplicates else "Find duplicates")
        self.set_busy(self.busy)
        if state.scan is None:
            self.stack.setCurrentIndex(0)
        elif state.duplicates is None:
            self.stack.setCurrentIndex(1)
        else:
            result = state.duplicates
            self.model.root = state.scan.root
            self.model.set_groups(result.groups)
            self.summary.metrics[0].set_value(f"{len(result.groups):,}", "Identical content")
            self.summary.metrics[1].set_value(f"{result.extra_copies:,}", "Beyond one per group")
            self.summary.metrics[2].set_value(human_size(result.redundant_size), "Review before cleanup")
            self.analysis_note.setText("Partial comparison · run again to complete" if result.cancelled else
                f"{len(result.issues):,} unreadable files · results cover successfully read files" if result.issues else "Verified with SHA-256 · no files deleted")
            if result.groups or result.cancelled or result.issues:
                self.stack.setCurrentIndex(3)
                for group_index in range(min(6, len(result.groups))):
                    self.view.expand(self.model.index(group_index, 0))
            else:
                self.stack.setCurrentIndex(2)
        self.selection_changed()

    def set_busy(self, busy: bool) -> None:
        super().set_busy(busy)
        self.analyze.setEnabled(self.can_analyze and not busy)
        self.not_run.action.setEnabled(self.can_analyze and not busy)
        self.no_folder.action.setEnabled(not busy)
