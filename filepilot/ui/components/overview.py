from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QFrame, QGridLayout, QHBoxLayout, QSizePolicy, QToolTip, QVBoxLayout, QWidget

from filepilot.core.categories import CATEGORY_COLORS, Category, human_size
from filepilot.ui.components.controls import repolish
from filepilot.ui.components.icons import category_icon, icon
from filepilot.ui.components.widgets import count_label, label
from filepilot.ui.theme import current_colors


class MetricDisplay(QWidget):
    def __init__(self, title: str, symbol: str, accent: bool = False) -> None:
        super().__init__()
        self.symbol = symbol
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 10, 12)
        layout.setSpacing(5)
        heading = QHBoxLayout()
        heading.setSpacing(7)
        self.glyph = label()
        self.glyph.setFixedSize(15, 15)
        heading.addWidget(self.glyph)
        heading.addWidget(label(title, "eyebrow"))
        heading.addStretch()
        layout.addLayout(heading)
        self.value = label("0", "metric")
        self.value.setProperty("accent", accent)
        self.hint = label("", "helper")
        layout.addWidget(self.value)
        layout.addWidget(self.hint)
        self.setAccessibleName(title)
        self.update_icon()

    def update_icon(self) -> None:
        self.glyph.setPixmap(icon(self.symbol, current_colors().muted, 15).pixmap(15, 15))

    def set_value(self, value: str, hint: str, *, waiting: bool = False) -> None:
        if self.value.property("waiting") != waiting:
            self.value.setProperty("waiting", waiting)
            repolish(self.value)
        self.value.setText(value)
        self.hint.setText(hint)
        self.setAccessibleDescription(f"{value}. {hint}")

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if hasattr(self, "glyph"):
            self.update_icon()


class SummaryStrip(QFrame):
    def __init__(self, metrics: list[tuple[str, str]]) -> None:
        super().__init__()
        self.setObjectName("SummaryStrip")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(106)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.metrics = []
        for index, (title, symbol) in enumerate(metrics):
            if index:
                separator = QFrame()
                separator.setObjectName("MetricDivider")
                separator.setFixedHeight(66)
                layout.addWidget(separator)
            metric = MetricDisplay(title, symbol, index == len(metrics) - 1)
            layout.addWidget(metric, 1)
            self.metrics.append(metric)


class StorageBar(QWidget):
    category_clicked = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.values = {}
        self.segments: list[tuple[Category, QRectF]] = []
        self.hovered: Category | None = None
        self.setFixedHeight(34)
        self.setMouseTracking(True)
        self.setAccessibleName("Proportional storage by category")

    def set_values(self, values: dict[Category, tuple[int, int]]) -> None:
        self.values = values
        self.setAccessibleDescription("; ".join(f"{category}: {count} files, {human_size(size)}" for category, (count, size) in values.items()))
        self.update_segments()
        self.update()

    def update_segments(self) -> None:
        total = sum(size for _, size in self.values.values())
        active = [(category, size) for category, (_, size) in self.values.items() if size]
        available = max(0, self.width() - max(0, len(active) - 1) * 2)
        x = 0.0
        self.segments = []
        for category, size in active:
            width = available * size / total
            self.segments.append((category, QRectF(x, 2, width, self.height() - 4)))
            x += width + 2

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        if not self.segments:
            p.setBrush(QColor(current_colors().raised))
            p.drawRoundedRect(QRectF(self.rect()), 3, 3)
        for category, rect in self.segments:
            color = QColor(CATEGORY_COLORS[category])
            if category == self.hovered:
                color = color.lighter(112)
            p.setBrush(color)
            p.drawRoundedRect(rect, 2, 2)
        p.end()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_segments()

    def mouseMoveEvent(self, event) -> None:
        category = next((category for category, rect in self.segments if rect.contains(event.position())), None)
        if category != self.hovered:
            self.hovered = category
            self.setCursor(Qt.CursorShape.PointingHandCursor if category else Qt.CursorShape.ArrowCursor)
            self.update()
        if category:
            count, size = self.values[category]
            total = sum(value for _, value in self.values.values())
            QToolTip.showText(event.globalPosition().toPoint(), f"{category}\n{count_label(count, 'file')} · {human_size(size)} · {size / total:.1%}", self)

    def leaveEvent(self, event) -> None:
        self.hovered = None
        QToolTip.hideText()
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            category = next((category for category, rect in self.segments if rect.contains(event.position())), None)
            if category:
                self.category_clicked.emit(str(category))
        super().mouseReleaseEvent(event)


class CategoryButton(QAbstractButton):
    def __init__(self, category: Category) -> None:
        super().__init__()
        self.category = category
        self.count = self.size = self.total = 0
        self.setFixedHeight(54)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"Browse {category} files")

    def set_values(self, count: int, size: int, total: int) -> None:
        self.count, self.size, self.total = count, size, total
        self.setToolTip(f"{self.category}\n{count_label(count, 'file')} · {human_size(size)} · {size / total:.1%}" if total else f"{self.category}\n{count_label(count, 'file')} · 0 B")
        self.setAccessibleDescription(self.toolTip())
        self.update()

    def paintEvent(self, event) -> None:
        c = current_colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse() or self.hasFocus():
            p.setBrush(QColor(c.hover))
            p.setPen(QPen(QColor(c.accent), 1) if self.hasFocus() else Qt.PenStyle.NoPen)
            p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 3, 3)
        category_icon(self.category, 22).paint(p, 8, 15, 22, 22)
        font = QFont(self.font())
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(QColor(c.text))
        p.drawText(self.rect().adjusted(39, 6, -8, -24), Qt.AlignmentFlag.AlignVCenter, str(self.category))
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.Normal)
        p.setFont(font)
        p.setPen(QColor(c.muted))
        percent = "<1%" if self.total and 0 < self.size / self.total < .01 else f"{self.size / self.total:.0%}" if self.total else "0%"
        p.drawText(self.rect().adjusted(39, 28, -8, -6), Qt.AlignmentFlag.AlignVCenter,
                   f"{count_label(self.count, 'file')} · {human_size(self.size)} · {percent}" if self.total else f"{count_label(self.count, 'file')} · 0 B")
        p.end()

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)


class CategoryLegend(QWidget):
    category_clicked = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(4)
        self.buttons = {}
        self.columns = 0
        for category in Category:
            item = CategoryButton(category)
            item.clicked.connect(lambda checked=False, category=category: self.category_clicked.emit(str(category)))
            self.buttons[category] = item
        self.reflow(2)

    def reflow(self, columns: int) -> None:
        if columns == self.columns:
            return
        while self.grid.count():
            self.grid.takeAt(0)
        self.columns = columns
        for index, item in enumerate(self.buttons.values()):
            self.grid.addWidget(item, index // columns, index % columns)
        for column in range(4):
            self.grid.setColumnStretch(column, int(column < columns))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.reflow(4 if self.width() >= 860 else 2)

    def set_values(self, values: dict[Category, tuple[int, int]], total: int) -> None:
        for category, item in self.buttons.items():
            item.set_values(*values[category], total)


class InsightRow(QAbstractButton):
    def __init__(self, symbol: str) -> None:
        super().__init__()
        self.symbol = symbol
        self.title = self.detail = ""
        self.setFixedHeight(66)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(190)

    def set_text(self, title: str, detail: str) -> None:
        self.title, self.detail = title, detail
        self.setAccessibleName(title)
        self.setAccessibleDescription(detail)
        self.setToolTip(f"{title}\n{detail}")
        self.update()

    def paintEvent(self, event) -> None:
        c = current_colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(c.border), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        if self.underMouse() or self.hasFocus():
            p.fillRect(self.rect().adjusted(0, 0, 0, -1), QColor(c.hover))
        if self.hasFocus():
            p.setPen(QPen(QColor(c.accent), 1))
            p.drawRect(self.rect().adjusted(1, 1, -2, -2))
        icon(self.symbol, c.accent, 20).paint(p, 8, 17, 20, 20)
        icon("arrow", c.muted, 15).paint(p, self.width() - 23, 22, 15, 15)
        font = QFont(self.font())
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(QColor(c.text))
        title = p.fontMetrics().elidedText(self.title, Qt.TextElideMode.ElideMiddle, self.width() - 74)
        p.drawText(self.rect().adjusted(38, 10, -28, -31), Qt.AlignmentFlag.AlignVCenter, title)
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.Normal)
        p.setFont(font)
        p.setPen(QColor(c.muted))
        detail = p.fontMetrics().elidedText(self.detail, Qt.TextElideMode.ElideMiddle, self.width() - 66)
        p.drawText(self.rect().adjusted(38, 32, -28, -9), Qt.AlignmentFlag.AlignVCenter, detail)
        p.end()

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)
