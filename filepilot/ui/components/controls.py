from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QButtonGroup, QComboBox, QHBoxLayout, QLabel,
    QLineEdit, QListView, QPushButton, QSizePolicy, QSpinBox, QWidget,
)

from filepilot.ui.components.icons import icon
from filepilot.ui.theme import DARK, LIGHT, current_colors


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class ElidedLabel(QLabel):
    """Elision follows available width; the full value is always accessible."""
    def __init__(self, text: str = "", role: str = "muted") -> None:
        super().__init__()
        self.full_text = ""
        self.setProperty("role", role)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setText(text)

    def setText(self, text: str) -> None:
        self.full_text = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        self._elide()

    def _elide(self) -> None:
        super().setText(self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideMiddle,
                                                    max(0, self.contentsRect().width())))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if hasattr(self, "full_text"):
            self._elide()


class CopyButton(QPushButton):
    def __init__(self, accessible_name: str = "Copy full path") -> None:
        super().__init__()
        self.value = ""
        self.setProperty("quiet", True)
        self.setProperty("iconOnly", True)
        self.setToolTip(accessible_name)
        self.setAccessibleName(accessible_name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(17, 17))
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.reset_icon)
        self.clicked.connect(self.copy)
        self.reset_icon()

    def reset_icon(self) -> None:
        self.setIcon(icon("copy", current_colors().muted, 17))

    def copy(self) -> None:
        if self.value:
            QApplication.clipboard().setText(self.value)
            self.setIcon(icon("check", current_colors().accent, 17))
            self.timer.start(1400)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if hasattr(self, "timer") and not self.timer.isActive():
            self.reset_icon()


class SearchField(QLineEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setPlaceholderText("Search filenames")
        self.setClearButtonEnabled(True)
        self.setAccessibleName("Search scanned filenames")
        self.search_action = self.addAction(icon("search", current_colors().muted, 17), QLineEdit.ActionPosition.LeadingPosition)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if hasattr(self, "search_action"):
            self.search_action.setIcon(icon("search", current_colors().muted, 17))


class FilterCombo(QComboBox):
    def __init__(self, default: str, accessible_name: str) -> None:
        super().__init__()
        self.default = default
        self.addItem(default)
        self.setAccessibleName(accessible_name)
        self.setMinimumWidth(120)
        self.setMaximumWidth(190)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(9)
        self.setView(QListView())
        self.currentTextChanged.connect(self.update_active)

    def update_active(self, *args) -> None:
        active = bool(self.currentText() and self.currentText() != self.default)
        if self.property("activeFilter") != active:
            self.setProperty("activeFilter", active)
            repolish(self)


class UnitSpinBox(QSpinBox):
    """Wheel scrolling the page cannot accidentally change an unfocused threshold."""
    def wheelEvent(self, event) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class ThemeOption(QAbstractButton):
    def __init__(self, name: str, description: str) -> None:
        super().__init__()
        self.name, self.description = name, description
        self.setText(name)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"{name} theme")
        self.setAccessibleDescription(description)
        self.setMinimumSize(112, 72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.toggled.connect(self.update)

    def sizeHint(self) -> QSize:
        return QSize(160, 72)

    def paintEvent(self, event) -> None:
        c = current_colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(c.accent if self.isChecked() or self.hasFocus() else c.border), 1.5 if self.hasFocus() else 1))
        p.setBrush(QColor(c.tint if self.isChecked() else c.hover if self.underMouse() else c.surface))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 4, 4)
        swatch = DARK if self.name == "Dark" else LIGHT
        p.setBrush(QColor(swatch.background))
        p.setPen(QPen(QColor(c.border), 1))
        p.drawRoundedRect(12, 14, 27, 22, 2, 2)
        p.fillRect(13, 15, 6, 20, QColor(swatch.sidebar))
        if self.name == "System":
            p.fillRect(25, 15, 13, 20, QColor(DARK.background))
        font = QFont(self.font())
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(QColor(c.text))
        p.drawText(self.rect().adjusted(47, 13, -8, -33), Qt.AlignmentFlag.AlignVCenter, self.name)
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.Normal)
        p.setFont(font)
        p.setPen(QColor(c.muted))
        p.drawText(self.rect().adjusted(12, 42, -8, -10), Qt.AlignmentFlag.AlignVCenter, self.description)
        if self.isChecked():
            icon("check", c.accent, 14).paint(p, self.width() - 25, 16, 14, 14)
        p.end()

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)


class ThemeSelector(QWidget):
    currentTextChanged = Signal(str)

    def __init__(self, current: str = "Light") -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.group = QButtonGroup(self)
        self.options = {}
        for name, description in (("Light", "Warm paper"), ("Dark", "Graphite"), ("System", "Follow Windows")):
            option = ThemeOption(name, description)
            self.group.addButton(option)
            layout.addWidget(option)
            self.options[name] = option
        self.options[current].setChecked(True)
        self.group.buttonToggled.connect(lambda option, checked: self.currentTextChanged.emit(option.name) if checked else None)

    def currentText(self) -> str:
        return self.group.checkedButton().name

    def setCurrentText(self, name: str) -> None:
        if name in self.options:
            self.options[name].setChecked(True)
