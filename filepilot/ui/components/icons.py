"""Consistent Qt-painted product and file icons."""
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from filepilot.core.categories import CATEGORY_COLORS, Category


@lru_cache(maxsize=256)
def icon(name: str, color: str = "#68736B", size: int = 20) -> QIcon:
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 20, size / 20)
    p.setPen(QPen(QColor(color), 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if name == "Dashboard":
        for x, y in ((3, 3), (11, 3), (3, 11), (11, 11)):
            p.drawRoundedRect(QRectF(x, y, 6, 6), 1, 1)
    elif name in ("Files", "folder"):
        path = QPainterPath(QPointF(2.5, 5))
        for point in ((8, 5), (10, 7), (17.5, 7), (17.5, 16), (2.5, 16), (2.5, 5)):
            path.lineTo(*point)
        p.drawPath(path)
    elif name in ("Duplicates", "copy"):
        p.drawRoundedRect(QRectF(3, 3, 10, 11), 1, 1)
        p.drawRoundedRect(QRectF(7, 7, 10, 11), 1, 1)
    elif name == "Organize":
        p.drawRoundedRect(QRectF(2, 3, 6, 5), 1, 1)
        p.drawRoundedRect(QRectF(2, 12, 6, 5), 1, 1)
        p.drawLine(10, 10, 17, 10)
        p.drawLine(14, 7, 17, 10)
        p.drawLine(17, 10, 14, 13)
    elif name in ("History", "rescan"):
        p.drawArc(QRectF(3, 3, 14, 14), -35 * 16, 285 * 16)
        p.drawLine(2.5, 3.5, 2.5, 8)
        p.drawLine(2.5, 8, 7, 8)
        if name == "History":
            p.drawLine(10, 6, 10, 10)
            p.drawLine(10, 10, 13, 12)
    elif name == "Settings":
        for y, x in ((5, 7), (10, 13), (15, 8)):
            p.drawLine(3, y, 17, y)
            p.setBrush(QColor(color))
            p.drawEllipse(QPointF(x, y), 1.7, 1.7)
    elif name == "search":
        p.drawEllipse(QRectF(3, 3, 10, 10))
        p.drawLine(12, 12, 17, 17)
    elif name in ("arrow", "right"):
        p.drawLine(3, 10, 17, 10)
        p.drawLine(13, 6, 17, 10)
        p.drawLine(17, 10, 13, 14)
    elif name == "close":
        p.drawLine(5, 5, 15, 15)
        p.drawLine(15, 5, 5, 15)
    elif name == "check":
        p.drawLine(4, 10, 8, 14)
        p.drawLine(8, 14, 16, 6)
    elif name == "shield":
        path = QPainterPath(QPointF(10, 2))
        for point in ((17, 5), (16, 13), (10, 18), (4, 13), (3, 5), (10, 2)):
            path.lineTo(*point)
        p.drawPath(path)
        p.drawLine(6, 9, 9, 12)
        p.drawLine(9, 12, 14, 7)
    elif name in ("details", "large"):
        p.drawRoundedRect(QRectF(3, 3, 14, 14), 1.5, 1.5)
        for yy, end in ((7, 13), (10, 13), (13, 10)):
            p.drawLine(7, yy, end, yy)
    elif name == "Documents":
        path = QPainterPath(QPointF(5, 2))
        for point in ((12, 2), (16, 6), (16, 18), (5, 18), (5, 2)):
            path.lineTo(*point)
        p.drawPath(path)
        p.drawLine(12, 2, 12, 6)
        p.drawLine(12, 6, 16, 6)
        p.drawLine(8, 10, 13, 10)
        p.drawLine(8, 13, 13, 13)
    elif name == "Images":
        p.drawRoundedRect(QRectF(2.5, 3, 15, 14), 1.5, 1.5)
        p.drawEllipse(QPointF(7, 7), 1.2, 1.2)
        path = QPainterPath(QPointF(3, 15))
        for point in ((8, 10), (11, 13), (14, 9), (17, 13)):
            path.lineTo(*point)
        p.drawPath(path)
    elif name == "Videos":
        p.drawRoundedRect(QRectF(3, 3, 14, 14), 1.5, 1.5)
        path = QPainterPath(QPointF(8, 7))
        path.lineTo(13, 10)
        path.lineTo(8, 13)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "Audio":
        p.drawLine(8, 5, 8, 15)
        p.drawLine(8, 5, 16, 3)
        p.drawLine(16, 3, 16, 13)
        p.drawEllipse(QRectF(3, 13, 5, 4))
        p.drawEllipse(QRectF(11, 11, 5, 4))
    elif name == "Archives":
        p.drawRoundedRect(QRectF(3, 3, 14, 14), 1.5, 1.5)
        p.drawLine(3, 7, 17, 7)
        p.drawLine(8, 11, 12, 11)
        p.drawLine(10, 11, 10, 14)
    elif name == "Installers":
        p.drawRoundedRect(QRectF(3, 3, 14, 14), 1.5, 1.5)
        p.drawLine(10, 6, 10, 13)
        p.drawLine(7, 10, 10, 13)
        p.drawLine(10, 13, 13, 10)
    elif name == "Code":
        for start, middle, end in (((7, 5), (3, 10), (7, 15)), ((13, 5), (17, 10), (13, 15))):
            p.drawLine(QPointF(*start), QPointF(*middle))
            p.drawLine(QPointF(*middle), QPointF(*end))
        p.drawLine(11, 4, 9, 16)
    else:
        p.drawRoundedRect(QRectF(4, 2, 12, 16), 1.5, 1.5)
        for yy in (7, 10, 13):
            p.drawPoint(10, yy)
    p.end()
    return QIcon(pixmap)


def category_icon(category: Category | str, size: int = 20) -> QIcon:
    return icon(str(category), CATEGORY_COLORS[Category(category)], size)
