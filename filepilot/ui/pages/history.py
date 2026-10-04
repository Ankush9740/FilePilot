from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QListView, QSplitter, QStackedWidget, QStyledItemDelegate, QStyle, QVBoxLayout, QWidget

from filepilot.ui.components.controls import CopyButton, ElidedLabel
from filepilot.ui.components.details import DetailStrip
from filepilot.ui.components.tables import RECORD_ROLE, TableModel, table
from filepilot.ui.components.widgets import EmptyState, Page, button, label
from filepilot.ui.theme import current_colors


def operation_time(row: dict) -> str:
    return datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")).astimezone().strftime("%d %b %Y · %H:%M")


def undo_available(row: dict) -> bool:
    return row["remaining"] > 0 and row["status"] not in ("running", "undoing", "interrupted")


def operation_label(status: str) -> str:
    return "Partial restore" if status == "partial_undo" else status.replace("_", " ").title()


def file_outcome_label(state: str) -> str:
    return {"failed": "Skipped", "undo_failed": "Restore skipped"}.get(state, state.replace("_", " ").title())


class HistoryModel(QAbstractListModel):
    def __init__(self) -> None:
        super().__init__()
        self.rows = []

    def set_rows(self, rows) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        if role == RECORD_ROLE:
            return row
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            return (f"Operation #{row['id']:04d} · {operation_time(row)}\n{row['source_root']}\n"
                    f"{operation_label(row['status'])} · {row['remaining']} moved, {row['restored']} restored, {row['failures']} skipped")


class TimelineDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:
        return QSize(400, 100)

    def paint(self, painter, option, index) -> None:
        row = index.data(RECORD_ROLE)
        c = current_colors()
        painter.save()
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.fillRect(rect, QColor(c.tint if selected else c.hover if hovered else c.surface))
        painter.setPen(QPen(QColor(c.border), 1))
        painter.drawLine(rect.left() + 23, rect.top(), rect.left() + 23, rect.bottom())
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.setBrush(QColor(c.accent if selected else c.surface))
        painter.setPen(QPen(QColor(c.accent), 1.3))
        painter.drawEllipse(rect.left() + 19, rect.top() + 22, 8, 8)
        left = rect.left() + 45
        font = QFont(option.font)
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(QColor(c.muted))
        painter.drawText(left, rect.top() + 27, f"{operation_time(row)}  /  #{row['id']:04d}")
        status = operation_label(row["status"])
        status_width = painter.fontMetrics().horizontalAdvance(status)
        painter.setPen(QColor(c.warning if row["status"] in ("failed", "partial", "partial_undo", "interrupted") else c.accent))
        painter.drawText(rect.right() - status_width - 16, rect.top() + 27, status)
        font.setPixelSize(14)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(c.text))
        root = Path(row["source_root"])
        name = root.name or str(root)
        painter.drawText(left, rect.top() + 53, painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideMiddle, rect.width() - 65))
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QColor(c.muted))
        outcomes = f"{row['item_count']:,} files reviewed · {row['remaining']:,} moved · {row['restored']:,} restored"
        if row["failures"]:
            outcomes += f" · {row['failures']:,} skipped"
        outcomes += " · Undo available" if undo_available(row) else " · Manual review needed" if row["status"] == "interrupted" else ""
        painter.drawText(left, rect.top() + 77, painter.fontMetrics().elidedText(outcomes, Qt.TextElideMode.ElideRight, rect.width() - 65))
        if option.state & QStyle.StateFlag.State_HasFocus:
            # The timeline dot leaves a brush set; focus must outline, not fill, the card.
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(c.accent), 1))
            painter.drawRect(rect.adjusted(1, 1, -2, -2))
        painter.restore()


class HistoryPage(Page):
    undo_requested = Signal(int)
    selection_requested = Signal(int)
    clear_requested = Signal()

    def __init__(self) -> None:
        super().__init__("Operation history", "A local timeline of your changes, with a verified way back.")
        self.clear = button("Clear history")
        self.clear.setProperty("quiet", True)
        self.clear.setAccessibleName("Clear completed history, keeping operations that can still be undone")
        self.clear.clicked.connect(self.clear_requested)
        self.actions.addWidget(self.clear)
        self.undo = button("Select an operation to undo")
        self.undo.clicked.connect(self.undo_selected)
        self.actions.addWidget(self.undo)
        self.stack = QStackedWidget()
        self.layout.addWidget(self.stack, 1)
        self.empty = EmptyState("No operation history yet", "Organization changes will appear here when FilePilot moves files.",
                                kind="history", eyebrow="A TRACEABLE WAY BACK")
        self.stack.addWidget(self.empty)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.model = HistoryModel()
        self.view = QListView()
        self.view.setObjectName("Timeline")
        self.view.setModel(self.model)
        self.view.setItemDelegate(TimelineDelegate(self.view))
        self.view.setMouseTracking(True)
        self.view.setUniformItemSizes(True)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setAccessibleName("Operation timeline, select an operation to inspect or undo")
        splitter.addWidget(self.view)
        individual = QWidget()
        detail_layout = QVBoxLayout(individual)
        detail_layout.setContentsMargins(0, 8, 0, 0)
        detail_layout.setSpacing(8)
        heading = QHBoxLayout()
        self.operation_heading = ElidedLabel("Select an operation to inspect its file outcomes.", "strong")
        heading.addWidget(self.operation_heading, 1)
        self.copy_root = CopyButton("Copy selected operation folder path")
        self.copy_root.setEnabled(False)
        heading.addWidget(self.copy_root)
        detail_layout.addLayout(heading)
        self.detail_model = TableModel(("Original location", "Organized location", "Outcome"),
                                      lambda row, col: (self.relative_location(row["original_path"]), self.relative_location(row["destination_path"]),
                                                        file_outcome_label(row["state"]))[col],
                                      tooltip=lambda row, col: (row["original_path"], row["destination_path"],
                                                                file_outcome_label(row["state"]) + (f"\n{row['error']}" if row["error"] else ""))[col])
        self.details = table(self.detail_model)
        self.details.setColumnWidth(0, 245)
        self.details.setColumnWidth(1, 245)
        self.details.setAccessibleName("Individual outcomes for the selected operation")
        detail_layout.addWidget(self.details, 1)
        splitter.addWidget(individual)
        splitter.setSizes([230, 250])
        layout.addWidget(splitter, 1)
        self.file_details = DetailStrip("Select a file outcome to inspect the original and organized paths.")
        layout.addWidget(self.file_details)
        layout.addWidget(label("Undo checks occupied locations and changed files. Partial restores remain visible and can be retried.", "helper", wrap=True))
        self.stack.addWidget(body)
        self.view.selectionModel().selectionChanged.connect(self.selection_changed)
        self.details.selectionModel().selectionChanged.connect(self.select_file)
        self.undo.setEnabled(False)
        self.update_clear_action()

    def update_clear_action(self) -> None:
        count = sum(bool(row.get("clearable", False)) for row in self.model.rows)
        self.clear.setEnabled(bool(count) and not self.busy)
        self.clear.setToolTip("Wait for the current operation to finish." if self.busy else
                             f"Clear {count:,} completed history {'record' if count == 1 else 'records'}. Operations that can still be undone will be kept." if count else
                             "No completed history to clear. Operations that can still be undone are kept.")

    def selected_operation(self) -> dict | None:
        rows = self.view.selectionModel().selectedRows()
        return self.model.rows[rows[0].row()] if rows else None

    def relative_location(self, path: str) -> str:
        operation = self.selected_operation()
        if operation:
            try:
                return str(Path(path).relative_to(operation["source_root"]))
            except ValueError:
                pass
        return path

    def selection_changed(self, *args) -> None:
        operation = self.selected_operation()
        self.undo.setEnabled(bool(operation and undo_available(operation) and not self.busy))
        self.undo.setText(f"Undo operation #{operation['id']:04d}" if operation and undo_available(operation) else
                          "Manual review needed" if operation and operation["status"] == "interrupted" else
                          "No moves to undo" if operation else "Select an operation to undo")
        self.copy_root.setEnabled(operation is not None)
        if operation:
            self.operation_heading.setText(f"Operation #{operation['id']:04d} · {operation['source_root']}")
            self.copy_root.value = operation["source_root"]
            self.selection_requested.emit(operation["id"])
        else:
            self.operation_heading.setText("Select an operation to inspect its file outcomes.")
            self.detail_model.set_rows([])
            self.copy_root.value = ""
        self.file_details.clear()

    def select_file(self, *args) -> None:
        rows = self.details.selectionModel().selectedRows()
        if rows:
            row = self.detail_model.rows[rows[0].row()]
            self.file_details.set_details(Path(row["original_path"]).name, [("Original location", row["original_path"]),
                ("Organized location", row["destination_path"]), ("State", file_outcome_label(row["state"])), ("Issue", row["error"] or "None")],
                row["original_path"], "Recorded file outcome")
        else:
            self.file_details.clear()

    def undo_selected(self) -> None:
        operation = self.selected_operation()
        if operation and undo_available(operation) and not self.busy:
            self.undo_requested.emit(operation["id"])

    def select_operation(self, operation_id: int) -> None:
        index = next((i for i, row in enumerate(self.model.rows) if row["id"] == operation_id), None)
        if index is not None:
            self.view.setCurrentIndex(self.model.index(index, 0))
            self.selection_changed()

    def refresh(self, rows: list[dict]) -> None:
        selected = self.selected_operation()
        self.stack.setCurrentIndex(int(bool(rows)))
        self.model.set_rows(rows)
        if selected and any(row["id"] == selected["id"] for row in rows):
            self.select_operation(selected["id"])
        else:
            self.selection_changed()
        self.update_clear_action()

    def set_busy(self, busy: bool) -> None:
        super().set_busy(busy)
        operation = self.selected_operation()
        self.undo.setEnabled(bool(operation and undo_available(operation) and not busy))
        self.update_clear_action()
