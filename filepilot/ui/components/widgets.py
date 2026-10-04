from pathlib import Path
import os
import subprocess

from PySide6.QtCore import QRectF, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPainterPath
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget

from filepilot.ui.components.icons import icon
from filepilot.ui.components.illustrations import FileIllustration
from filepilot.ui.theme import current_colors


def count_label(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count:,} {singular if count == 1 else plural or singular + 's'}"


def label(text: str = "", role: str = "", *, wrap: bool = False):
    from PySide6.QtWidgets import QLabel
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        widget.setProperty("role", role)
    widget.setWordWrap(wrap)
    return widget


def button(text: str, primary: bool = False) -> QPushButton:
    widget = QPushButton(text)
    widget.setProperty("primary", primary)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


def divider() -> QFrame:
    widget = QFrame()
    widget.setObjectName("Divider")
    return widget


class BrandMark(QWidget):
    def __init__(self, size: int = 32) -> None:
        super().__init__()
        self.setFixedSize(size, size)
        self.color = current_colors().accent

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.color))
        p.drawRoundedRect(QRectF(self.rect()), 5, 5)
        p.scale(self.width() / 36, self.height() / 36)
        path = QPainterPath()
        path.moveTo(8, 24)
        for point in ((8, 12), (18, 12), (18, 8), (28, 18), (18, 28), (18, 24), (8, 24)):
            path.lineTo(*point)
        p.setBrush(QColor(current_colors().on_accent))
        p.drawPath(path)


class EmptyState(QWidget):
    def __init__(self, title: str, description: str, action: str | None = None,
                 *, kind: str = "dashboard", eyebrow: str = "") -> None:
        super().__init__()
        self.kind = kind
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(10)
        layout.addStretch(1)
        self.illustration = FileIllustration(kind)
        layout.addWidget(self.illustration, alignment=Qt.AlignmentFlag.AlignHCenter)
        if eyebrow:
            layout.addWidget(label(eyebrow, "eyebrow"), alignment=Qt.AlignmentFlag.AlignHCenter)
        heading = label(title, "title", wrap=True)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)
        copy = label(description, "muted", wrap=True)
        copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copy.setFixedWidth(440)
        copy.setMinimumHeight(52)
        layout.addWidget(copy, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.action = button(action, True) if action else None
        if self.action:
            layout.addSpacing(6)
            layout.addWidget(self.action, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(2)


class Page(QWidget):
    def __init__(self, title: str, description: str) -> None:
        super().__init__()
        self.busy = False
        self.setObjectName("Page")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(24, 20, 24, 18)
        self.layout.setSpacing(14)
        header = QHBoxLayout()
        header.setSpacing(16)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        self.page_title = label(title, "title")
        titles.addWidget(self.page_title)
        titles.addWidget(label(description, "muted", wrap=True))
        header.addLayout(titles, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        header.addLayout(self.actions)
        self.layout.addLayout(header)

    def set_busy(self, busy: bool) -> None:
        self.busy = busy


def scroll_body() -> tuple[QScrollArea, QWidget, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    body = QWidget()
    body.setObjectName("ScrollBody")
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 0, 4, 0)
    layout.setSpacing(16)
    layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
    scroll.setWidget(body)
    return scroll, body, layout


def show_in_explorer(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"File no longer exists: {path}")
    if os.name == "nt":
        subprocess.Popen(["explorer.exe", "/select,", str(path)], shell=False)
    elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent))):
        raise OSError("The file manager could not be opened")
