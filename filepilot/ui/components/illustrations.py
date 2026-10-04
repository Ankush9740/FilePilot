from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from filepilot.ui.components.icons import icon
from filepilot.ui.theme import current_colors


class FileIllustration(QWidget):
    """A small family of purpose-specific, native-painted empty states."""
    def __init__(self, kind: str = "dashboard") -> None:
        super().__init__()
        self.kind = kind
        self.setFixedSize(220, 124)
        self.setAccessibleName(f"{kind.title()} illustration")

    def paintEvent(self, event) -> None:
        c = current_colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(c.border), 1.2))
        p.drawLine(17, 113, 203, 113)
        if self.kind == "dashboard":
            p.setBrush(QColor(c.surface))
            p.drawRoundedRect(QRectF(42, 36, 136, 67), 4, 4)
            p.drawRoundedRect(QRectF(42, 24, 58, 22), 3, 3)
            p.setPen(Qt.PenStyle.NoPen)
            for x, width, color in ((57, 42, c.accent), (101, 29, "#B18A55"), (132, 30, "#6E8291")):
                p.setBrush(QColor(color))
                p.drawRoundedRect(QRectF(x, 66, width, 11), 1, 1)
        elif self.kind == "files":
            icon("Documents", c.faint, 66).paint(p, 53, 17, 66, 75)
            icon("Documents", c.accent, 66).paint(p, 83, 24, 66, 75)
            p.setBrush(QColor(c.surface))
            p.setPen(QPen(QColor(c.accent), 2))
            p.drawEllipse(QRectF(131, 67, 30, 30))
            p.drawLine(155, 92, 170, 107)
        elif self.kind == "duplicates":
            p.setBrush(QColor(c.surface))
            for x in (49, 118):
                p.setPen(QPen(QColor(c.border), 1.2))
                p.drawRoundedRect(QRectF(x, 25, 53, 71), 3, 3)
                p.setPen(QPen(QColor(c.accent), 2))
                for y in (43, 57, 70):
                    p.drawLine(x + 12, y, x + 40, y)
            p.setPen(QPen(QColor(c.accent), 1.5))
            p.drawLine(105, 54, 115, 54)
            p.drawLine(105, 66, 115, 66)
        elif self.kind == "organize":
            icon("Documents", c.accent, 46).paint(p, 29, 36, 46, 54)
            p.setPen(QPen(QColor(c.border), 1.4))
            for y in (33, 65, 96):
                p.drawLine(87, 64, 116, y)
                icon("folder", c.accent if y == 65 else c.faint, 32).paint(p, 136, y - 16, 34, 32)
        else:
            p.setPen(QPen(QColor(c.border), 1.5))
            p.drawLine(61, 22, 61, 100)
            for y, length in ((30, 81), (63, 61), (96, 91)):
                p.setBrush(QColor(c.tint))
                p.setPen(QPen(QColor(c.accent), 1.3))
                p.drawEllipse(QPointF(61, y), 4, 4)
                p.setPen(QPen(QColor(c.border), 3))
                p.drawLine(83, y, 83 + length, y)
        p.end()
