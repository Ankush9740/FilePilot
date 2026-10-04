from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from filepilot.core.categories import human_size
from filepilot.ui.components.icons import category_icon, icon
from filepilot.ui.components.tables import TableModel
from filepilot.ui.theme import current_colors


class PlanModel(TableModel):
    def __init__(self) -> None:
        self.root = None
        super().__init__(("Current location", "", "Proposed destination", "Review"), self.display_item,
                         tooltip=self.item_tooltip)

    def display_item(self, item, column: int) -> str:
        return (str(item.file.path.relative_to(self.root)), "", str(item.destination.relative_to(self.root)),
                "Skipped · conflict" if item.conflict else f"Ready · {human_size(item.file.size)}")[column]

    def item_tooltip(self, item, column: int) -> str:
        return (str(item.file.path), f"{item.file.path}\n→ {item.destination}", str(item.destination),
                item.conflict or "Ready to move after confirmation")[column]

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if index.isValid():
            item = self.rows[index.row()]
            c = current_colors()
            if role == Qt.ItemDataRole.DecorationRole:
                if index.column() in (0, 2):
                    return category_icon(item.file.category, 20)
                if index.column() == 1:
                    return icon("arrow", c.muted, 17)
                if index.column() == 3 and not item.conflict:
                    return icon("check", c.accent, 15)
            if role == Qt.ItemDataRole.ForegroundRole and index.column() == 3:
                return QColor(c.warning if item.conflict else c.accent)
            if role == Qt.ItemDataRole.FontRole and index.column() == 2:
                font = QFont()
                font.setWeight(QFont.Weight.DemiBold)
                return font
        return super().data(index, role)
