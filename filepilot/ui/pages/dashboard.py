from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QHeaderView, QStackedWidget, QVBoxLayout, QWidget

from filepilot.core.categories import human_size
from filepilot.ui.components.controls import ElidedLabel
from filepilot.ui.components.overview import CategoryLegend, InsightRow, StorageBar, SummaryStrip
from filepilot.ui.components.tables import FileTableModel, table
from filepilot.ui.components.widgets import EmptyState, Page, button, count_label, label, scroll_body
from filepilot.ui.state import AppState


class DashboardPage(Page):
    choose_folder = Signal()
    duplicates_requested = Signal()
    files_requested = Signal(str)
    category_requested = Signal(str)
    reveal_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__("Folder overview", "A clear picture of your storage, from the whole folder to the individual file.")
        self.files_action = button("Browse files")
        self.actions.addWidget(self.files_action)
        self.files_action.clicked.connect(lambda: self.files_requested.emit("All files"))
        self.stack = QStackedWidget()
        self.layout.addWidget(self.stack, 1)
        self.empty = EmptyState("Your files, under control.",
                                "Choose a folder to understand what's taking space,\nfind duplicates, and organize it safely.",
                                "Choose Folder", kind="dashboard", eyebrow="FOLDER INTELLIGENCE")
        self.empty.action.clicked.connect(self.choose_folder)
        self.stack.addWidget(self.empty)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(14)
        self.stack.addWidget(body)
        # These metrics have their own layout, outside the scrolling viewport.
        self.summary = SummaryStrip([("FILES SCANNED", "Files"), ("TOTAL STORAGE", "Archives"),
                                     ("EXTRA COPIES", "Duplicates"), ("REDUNDANT SPACE", "copy")])
        self.metrics = [(metric.value, metric.hint) for metric in self.summary.metrics]
        body_layout.addWidget(self.summary)
        self.scroll, _, content = scroll_body()
        body_layout.addWidget(self.scroll, 1)
        storage_surface = QFrame()
        storage_surface.setObjectName("Surface")
        storage_layout = QVBoxLayout(storage_surface)
        storage_layout.setContentsMargins(14, 12, 14, 8)
        storage_layout.setSpacing(7)
        storage_header = QHBoxLayout()
        storage_header.addWidget(label("Storage by category", "section"))
        self.distribution_hint = ElidedLabel("", "helper")
        storage_header.addWidget(self.distribution_hint, 1)
        self.distribution_hint.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        storage_layout.addLayout(storage_header)
        self.storage = StorageBar()
        self.storage.category_clicked.connect(self.category_requested)
        storage_layout.addWidget(self.storage)
        self.legend = CategoryLegend()
        self.legend.category_clicked.connect(self.category_requested)
        storage_layout.addWidget(self.legend)
        self.zero_note = label("No storage used by scanned files. Zero-byte files still appear in Files.", "helper", wrap=True)
        storage_layout.addWidget(self.zero_note)
        content.addWidget(storage_surface)
        lower = QHBoxLayout()
        lower.setSpacing(20)
        biggest = QVBoxLayout()
        biggest.setSpacing(10)
        biggest.addWidget(label("Biggest space takers", "section"))
        self.largest_model = FileTableModel(("Name", "Category", "Size"))
        self.largest_table = table(self.largest_model)
        self.largest_table.setFixedHeight(215)
        header = self.largest_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.largest_table.setColumnWidth(1, 90)
        self.largest_table.setColumnWidth(2, 85)
        self.largest_table.setAccessibleName("Largest files in the selected folder")
        self.largest_table.selectionModel().selectionChanged.connect(self.select_largest)
        self.largest_table.doubleClicked.connect(self.reveal_largest)
        biggest.addWidget(self.largest_table)
        self.largest_path = ElidedLabel("Select a file to inspect its location.", "helper")
        biggest.addWidget(self.largest_path)
        lower.addLayout(biggest, 3)
        insights = QVBoxLayout()
        insights.setSpacing(3)
        insights.addWidget(label("Worth a closer look", "section"))
        self.large_insight = InsightRow("large")
        self.old_insight = InsightRow("History")
        self.duplicate_insight = InsightRow("Duplicates")
        self.large_insight.clicked.connect(lambda: self.files_requested.emit("Large files"))
        self.old_insight.clicked.connect(lambda: self.files_requested.emit("Older files"))
        self.duplicate_insight.clicked.connect(self.duplicates_requested)
        for insight in (self.large_insight, self.old_insight, self.duplicate_insight):
            insights.addWidget(insight)
        insights.addWidget(label("Review cues, with no automatic cleanup.", "helper", wrap=True))
        insights.addStretch()
        lower.addLayout(insights, 2)
        content.addLayout(lower)
        content.addStretch()

    def select_largest(self, *args) -> None:
        rows = self.largest_table.selectionModel().selectedRows()
        if rows:
            file = self.largest_model.rows[rows[0].row()]
            self.largest_path.setText(f"{file.name} · {file.path}")
        else:
            self.largest_path.setText("Select a file to inspect its location.")

    def reveal_largest(self, *args) -> None:
        rows = self.largest_table.selectionModel().selectedRows()
        if rows:
            self.reveal_requested.emit(self.largest_model.rows[rows[0].row()].path)

    def refresh(self, state: AppState) -> None:
        populated = state.scan is not None and state.analysis is not None
        self.stack.setCurrentIndex(int(populated))
        self.files_action.setVisible(populated)
        if not populated:
            return
        scan, analysis, duplicates = state.scan, state.analysis, state.duplicates
        self.summary.metrics[0].set_value(f"{len(scan.files):,}", "Partial scan" if scan.cancelled else "Recursive, read-only")
        self.summary.metrics[1].set_value(human_size(analysis.total_size), "Logical file sizes")
        if duplicates is None:
            self.summary.metrics[2].set_value("Not analyzed", "Compare file contents", waiting=True)
            self.summary.metrics[3].set_value("Not analyzed", "Run duplicate review", waiting=True)
        else:
            self.summary.metrics[2].set_value(f"{duplicates.extra_copies:,}", "Partial analysis" if duplicates.cancelled else "Exact content matches")
            self.summary.metrics[3].set_value(human_size(duplicates.redundant_size), "Extra copies, review first")
        self.storage.set_values(analysis.categories)
        self.legend.set_values(analysis.categories, analysis.total_size)
        self.zero_note.setVisible(analysis.total_size == 0)
        if analysis.total_size:
            dominant = max(analysis.categories, key=lambda category: analysis.categories[category][1])
            fraction = analysis.categories[dominant][1] / analysis.total_size
            self.distribution_hint.setText(f"{dominant} · {fraction:.0%} of storage")
        else:
            self.distribution_hint.setText(f"{count_label(len(scan.files), 'file')} · no bytes used")
        self.largest_model.set_rows(analysis.largest[:4])
        self.large_insight.set_text(count_label(len(analysis.large), 'large file'), f"At least {state.settings.large_mb:,} MB per file")
        self.old_insight.set_text(count_label(len(analysis.old), 'older file'), f"Unmodified for {state.settings.old_days:,} days")
        if duplicates is None:
            self.duplicate_insight.set_text("Compare exact copies", "Local content checks with SHA-256")
        elif duplicates.groups:
            self.duplicate_insight.set_text(f"{human_size(duplicates.redundant_size)} redundant copies",
                                            f"{count_label(duplicates.extra_copies, 'extra copy', 'extra copies')} · " + ("partial analysis" if duplicates.cancelled else count_label(len(duplicates.groups), 'group')))
        else:
            self.duplicate_insight.set_text("Analysis incomplete" if duplicates.cancelled or duplicates.issues else "No exact matches",
                                            "Review comparison results" if duplicates.cancelled or duplicates.issues else "No redundant copies found")

    def set_busy(self, busy: bool) -> None:
        super().set_busy(busy)
        self.empty.action.setEnabled(not busy)
