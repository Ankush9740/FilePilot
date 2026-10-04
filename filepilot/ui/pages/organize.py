from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QHeaderView, QStackedWidget, QVBoxLayout, QWidget

from filepilot.ui.components.details import DetailStrip
from filepilot.ui.components.overview import SummaryStrip
from filepilot.ui.components.plan_model import PlanModel
from filepilot.ui.components.tables import table
from filepilot.ui.components.widgets import EmptyState, Page, button, label
from filepilot.ui.state import AppState

NESTED_EXPLANATION = ("Organization includes files inside subfolders. Applying this preview may move them "
                      "into the category folders shown below.")


class OrganizePage(Page):
    choose_folder = Signal()
    preview_requested = Signal()
    apply_requested = Signal()
    cancel_requested = Signal()

    def __init__(self) -> None:
        super().__init__("Organization preview", "See where every file will go before you move anything.")
        self.can_preview = False
        self.can_apply = False
        self.preview = button("Create preview", True)
        self.preview.clicked.connect(self.preview_requested)
        self.actions.addWidget(self.preview)
        self.stack = QStackedWidget()
        self.layout.addWidget(self.stack, 1)
        self.no_folder = EmptyState("Give scattered files a place.", "Choose a folder to propose category destinations.\nEvery move is reviewed before it is applied.",
                                    "Choose Folder", kind="organize", eyebrow="PLAN. REVIEW. APPLY.")
        self.no_folder.action.clicked.connect(self.choose_folder)
        self.ready = EmptyState("Preview first. Move with confidence.",
                                "Propose destinations for files in this folder and its subfolders.\nCategory folders keep existing filenames; conflicts are skipped.",
                                "Create preview", kind="organize", eyebrow="YOUR FILES STAY PUT DURING PREVIEW")
        self.ready.action.clicked.connect(self.preview_requested)
        self.stack.addWidget(self.no_folder)
        self.stack.addWidget(self.ready)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.summary = SummaryStrip([("PROPOSED MOVES", "Organize"), ("SKIPPED CONFLICTS", "copy"), ("ALREADY ORGANIZED", "check")])
        self.summary.setFixedHeight(94)
        layout.addWidget(self.summary)
        notice = QFrame()
        notice.setObjectName("NoticeStrip")
        notice_layout = QVBoxLayout(notice)
        notice_layout.setContentsMargins(12, 9, 12, 9)
        notice_layout.setSpacing(4)
        self.explanation = label(NESTED_EXPLANATION, "helper", wrap=True)
        notice_layout.addWidget(self.explanation)
        layout.addWidget(notice)
        self.model = PlanModel()
        self.view = table(self.model)
        self.view.setAccessibleName("Preview of current locations and proposed category destinations")
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setColumnWidth(0, 240)
        self.view.setColumnWidth(1, 34)
        self.view.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.view.horizontalHeader().setMinimumSectionSize(30)
        self.view.setColumnWidth(1, 34)
        self.view.setColumnWidth(2, 245)
        layout.addWidget(self.view, 1)
        self.details = DetailStrip("Select a proposed move to inspect both full paths.")
        self.full_paths = self.details.subtitle
        layout.addWidget(self.details)
        self.view.selectionModel().selectionChanged.connect(self.show_full_paths)
        footer = QHBoxLayout()
        self.result_note = label("Preview only · no files moved", "helper", wrap=True)
        footer.addWidget(self.result_note, 1)
        self.cancel = button("Cancel")
        self.cancel.clicked.connect(self.cancel_requested)
        self.apply = button("Apply Organization", True)
        self.apply.clicked.connect(self.apply_requested)
        footer.addWidget(self.cancel)
        footer.addWidget(self.apply)
        layout.addLayout(footer)
        self.stack.addWidget(body)

    def show_full_paths(self, *args) -> None:
        rows = self.view.selectionModel().selectedRows()
        if rows:
            item = self.model.rows[rows[0].row()]
            self.details.set_details(item.file.name, [("Current location", str(item.file.path)),
                ("Proposed destination", str(item.destination)), ("Category", str(item.file.category)),
                ("Review", item.conflict or "Ready after confirmation")], item.file.path, "Proposed move details")
        else:
            self.details.clear()

    def refresh(self, state: AppState) -> None:
        self.can_preview = state.scan is not None and not state.scan.cancelled
        self.can_apply = bool(state.plan and state.plan.actionable)
        self.preview.setVisible(state.scan is not None)
        self.set_busy(self.busy)
        if state.scan is None:
            self.stack.setCurrentIndex(0)
        elif state.plan is None:
            self.stack.setCurrentIndex(1)
            if state.scan.cancelled:
                self.result_note.setText("Rescan to complete the folder before creating a preview.")
        else:
            plan = state.plan
            self.stack.setCurrentIndex(2)
            self.model.root = plan.root
            self.model.set_rows(plan.items)
            self.show_full_paths()
            actionable = len(plan.actionable)
            conflicts = len(plan.items) - actionable
            self.summary.metrics[0].set_value(f"{actionable:,}", "After your confirmation")
            self.summary.metrics[1].set_value(f"{conflicts:,}", "No names overwritten")
            self.summary.metrics[2].set_value(f"{plan.already_organized:,}", "Left in place")
            self.explanation.setText(NESTED_EXPLANATION if plan.items else
                                      "No moves are needed. Files are already in their category folders, or this folder is empty.")
            nested = sum(len(item.file.path.relative_to(plan.root).parts) > 1 for item in plan.actionable)
            self.result_note.setText(f"Preview only · {nested:,} proposed moves from subfolders")
            self.model.root = plan.root

    def set_busy(self, busy: bool) -> None:
        super().set_busy(busy)
        self.preview.setEnabled(self.can_preview and not busy)
        self.ready.action.setEnabled(self.can_preview and not busy)
        self.apply.setEnabled(self.can_apply and not busy)
        self.cancel.setEnabled(not busy)
        self.no_folder.action.setEnabled(not busy)
