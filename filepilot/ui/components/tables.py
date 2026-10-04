from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QStyledItemDelegate, QStyle, QStyleOptionViewItem, QTableView

from filepilot.core.categories import human_size
from filepilot.models.records import FileRecord
from filepilot.ui.components.icons import category_icon
from filepilot.ui.theme import current_colors

SORT_ROLE = int(Qt.ItemDataRole.UserRole) + 1
RECORD_ROLE = SORT_ROLE + 1
CATEGORY_ROLE = SORT_ROLE + 2
GROUP_ROLE = SORT_ROLE + 3


class TableModel(QAbstractTableModel):
    def __init__(self, columns: Sequence[str], display: Callable[[Any, int], str],
                 sort_value: Callable[[Any, int], Any] | None = None,
                 tooltip: Callable[[Any, int], str] | None = None) -> None:
        super().__init__()
        self.columns, self.display, self.sort_value = columns, display, sort_value
        self.tooltip = tooltip
        self.rows: Sequence[Any] = []

    def set_rows(self, rows: Sequence[Any]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row, column = self.rows[index.row()], index.column()
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            if role == Qt.ItemDataRole.ToolTipRole and self.tooltip:
                return self.tooltip(row, column)
            return self.display(row, column)
        if role == SORT_ROLE:
            return self.sort_value(row, column) if self.sort_value else self.display(row, column).casefold()
        if role == RECORD_ROLE:
            return row
        return None

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.columns[section]
        return None


def file_display(file: FileRecord, column: int) -> str:
    return (file.name, str(file.category), human_size(file.size),
            datetime.fromtimestamp(file.modified).strftime("%d %b %Y, %H:%M"), str(file.path.parent))[column]


def file_sort(file: FileRecord, column: int) -> Any:
    return (file.name.casefold(), str(file.category), file.size, file.modified_ns, str(file.path.parent).casefold())[column]


class FileTableModel(TableModel):
    def __init__(self, columns=("Name", "Category", "Size", "Modified", "Location")) -> None:
        super().__init__(columns, file_display, file_sort,
                         tooltip=lambda file, col: f"{file.name}\n{file.path}" if col == 0 else file_display(file, col))

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if index.isValid():
            file = self.rows[index.row()]
            if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 2:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
                return category_icon(file.category, 20)
            if role == CATEGORY_ROLE:
                return str(file.category)
        return super().data(index, role)


class RowDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:
        local = QStyleOptionViewItem(option)
        view = self.parent()
        if getattr(view, "hover_row", -1) == index.row():
            local.state |= QStyle.StateFlag.State_MouseOver
        super().paint(painter, local, index)
        painter.save()
        border = QColor(current_colors().border)
        border.setAlpha(110)
        painter.setPen(QPen(border, 1))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.restore()


class FileTableView(QTableView):
    def __init__(self) -> None:
        super().__init__()
        self.hover_row = -1
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def mouseMoveEvent(self, event) -> None:
        row = self.indexAt(event.position().toPoint()).row()
        if row != self.hover_row:
            self.hover_row = row
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.hover_row = -1
        self.viewport().update()
        super().leaveEvent(event)


class FileFilter(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.search = ""
        self.category = "All categories"
        self.extension = "All extensions"
        self.setSortRole(SORT_ROLE)
        self.setDynamicSortFilter(True)

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        file = self.sourceModel().rows[row]
        return (self.search in file.name.casefold()
                and (self.category == "All categories" or self.category == str(file.category))
                and (self.extension == "All extensions" or self.extension == (file.extension or "(no extension)")))

    def refilter(self, search: str, category: str, extension: str) -> None:
        modern = hasattr(self, "beginFilterChange") and hasattr(self, "endFilterChange")
        if modern:
            self.beginFilterChange()
        self.search, self.category, self.extension = search.casefold(), category, extension
        if modern:
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self.invalidateFilter()


def table(model: QAbstractTableModel, *, sort: bool = False) -> QTableView:
    view = FileTableView()
    view.setModel(model)
    view.setShowGrid(False)
    view.setAlternatingRowColors(False)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.verticalHeader().hide()
    view.verticalHeader().setDefaultSectionSize(43)
    view.horizontalHeader().setMinimumSectionSize(70)
    view.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    view.horizontalHeader().setStretchLastSection(True)
    view.setSortingEnabled(sort)
    view.setTextElideMode(Qt.TextElideMode.ElideMiddle)
    view.setWordWrap(False)
    view.setItemDelegate(RowDelegate(view))
    view.setAccessibleName("File analysis table")
    return view
