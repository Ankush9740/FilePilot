from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractItemModel, QModelIndex, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

from filepilot.core.categories import human_size
from filepilot.models.records import DuplicateGroup
from filepilot.ui.components.icons import category_icon
from filepilot.ui.components.tables import GROUP_ROLE, RECORD_ROLE
from filepilot.ui.theme import current_colors


class DuplicateModel(QAbstractItemModel):
    """Preserves the existing group/member index scheme and service results."""
    def __init__(self) -> None:
        super().__init__()
        self.groups: list[DuplicateGroup] = []
        self.root: Path | None = None

    def set_groups(self, groups: list[DuplicateGroup]) -> None:
        self.beginResetModel()
        self.groups = groups
        self.endResetModel()

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if row < 0 or column < 0 or column >= 4:
            return QModelIndex()
        if not parent.isValid():
            return self.createIndex(row, column, (row + 1) << 32) if row < len(self.groups) else QModelIndex()
        if parent.column() != 0 or parent.internalId() & 0xFFFFFFFF:
            return QModelIndex()
        group = (parent.internalId() >> 32) - 1
        return self.createIndex(row, column, ((group + 1) << 32) | (row + 1)) if row < len(self.groups[group].files) else QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid() or not index.internalId() & 0xFFFFFFFF:
            return QModelIndex()
        group = (index.internalId() >> 32) - 1
        return self.createIndex(group, 0, (group + 1) << 32)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not parent.isValid():
            return len(self.groups)
        if parent.column() != 0 or parent.internalId() & 0xFFFFFFFF:
            return 0
        return len(self.groups[(parent.internalId() >> 32) - 1].files)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 4

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        group = self.groups[(index.internalId() >> 32) - 1]
        member = (index.internalId() & 0xFFFFFFFF) - 1
        if role == GROUP_ROLE:
            return member < 0
        if role == RECORD_ROLE:
            return group if member < 0 else group.files[member]
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{group.files[member].name}\n{group.files[member].path}" if member >= 0 else (
                f"{group.files[0].name}\n{len(group.files)} identical copies\nSHA-256: {group.digest}\n"
                f"{human_size(group.redundant_size)} redundant logical bytes")
        if role == Qt.ItemDataRole.DecorationRole and member >= 0 and index.column() == 0:
            return category_icon(group.files[member].category, 20)
        if role == Qt.ItemDataRole.DisplayRole:
            if member < 0:
                return (group.files[0].name, f"{len(group.files)} copies", human_size(group.files[0].size),
                        f"{human_size(group.redundant_size)} redundant")[index.column()]
            file = group.files[member]
            parent = file.path.parent.relative_to(self.root) if self.root else file.path.parent
            return (file.name, str(file.category), human_size(file.size), "Top level" if str(parent) == "." else str(parent))[index.column()]
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ("Matching files", "Copies / category", "Each file", "Location / redundant storage")[section]
        return None

    def selected_path(self, index: QModelIndex):
        if index.isValid() and index.internalId() & 0xFFFFFFFF:
            return self.groups[(index.internalId() >> 32) - 1].files[(index.internalId() & 0xFFFFFFFF) - 1].path
        return None


class DuplicateDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:
        return QSize(100, 60 if index.data(GROUP_ROLE) else 44)

    def paint(self, painter, option, index) -> None:
        c = current_colors()
        if not index.data(GROUP_ROLE):
            super().paint(painter, option, index)
            painter.save()
            border = QColor(c.border)
            border.setAlpha(90)
            painter.setPen(QPen(border, 1))
            painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
            painter.restore()
            return
        group = index.data(RECORD_ROLE)
        painter.save()
        rect = option.rect
        painter.fillRect(rect, QColor(c.tint if option.state & QStyle.StateFlag.State_Selected else c.raised))
        painter.fillRect(rect.adjusted(0, 0, 0, -rect.height() + 4), QColor(c.surface))
        if index.column() == 0:
            painter.fillRect(rect.adjusted(0, 6, -rect.width() + 3, -5), QColor(c.accent))
        font = QFont(option.font)
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(c.accent if index.column() == 3 else c.text))
        text = painter.fontMetrics().elidedText(index.data(), Qt.TextElideMode.ElideMiddle, rect.width() - 22)
        painter.drawText(rect.adjusted(11, 10, -10, -25), Qt.AlignmentFlag.AlignVCenter, text)
        font.setPixelSize(10)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QColor(c.muted))
        categories = {str(file.category) for file in group.files}
        secondary = (f"MATCH GROUP {(index.internalId() >> 32):02d}", next(iter(categories)) if len(categories) == 1 else "Mixed file types",
                     "Per identical file", "Extra copies · logical bytes")[index.column()]
        painter.drawText(rect.adjusted(11, 32, -10, -7), Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(secondary, Qt.TextElideMode.ElideRight, rect.width() - 22))
        if option.state & QStyle.StateFlag.State_HasFocus:
            painter.setPen(QPen(QColor(c.accent), 1))
            painter.drawRect(rect.adjusted(1, 5, -2, -2))
        painter.restore()
