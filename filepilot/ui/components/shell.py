from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QProgressBar, QVBoxLayout, QWidget

from filepilot import __version__
from filepilot.core.categories import human_size
from filepilot.models.records import ScanResult
from filepilot.ui.components.controls import CopyButton, ElidedLabel
from filepilot.ui.components.icons import icon
from filepilot.ui.components.widgets import BrandMark, button, count_label, divider, label
from filepilot.ui.theme import current_colors


class Sidebar(QFrame):
    navigate_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(216)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 23, 18, 16)
        layout.setSpacing(5)
        branding = QHBoxLayout()
        branding.setSpacing(10)
        self.mark = BrandMark()
        branding.addWidget(self.mark)
        branding.addWidget(label("FilePilot", "brand"))
        branding.addStretch()
        layout.addLayout(branding)
        layout.addSpacing(8)
        layout.addWidget(label("Organize smarter.\nFind what matters.", "helper"))
        self.nav = []
        names = ("Dashboard", "Files", "Duplicates", "Organize", "History", "Settings")
        for index, name in enumerate(names):
            if index in (0, 3, 5):
                layout.addSpacing(22 if index == 0 else 14)
                layout.addWidget(label({0: "EXPLORE", 3: "ARRANGE", 5: "PREFERENCES"}[index], "eyebrow"))
                layout.addSpacing(3)
            nav = button(name)
            nav.setProperty("nav", True)
            nav.setCheckable(True)
            nav.setAutoExclusive(True)
            nav.setIconSize(QSize(19, 19))
            nav.setAccessibleName(f"{name} page")
            nav.clicked.connect(lambda checked=False, index=index: self.navigate_requested.emit(index))
            self.nav.append(nav)
            layout.addWidget(nav)
        layout.addStretch()
        layout.addWidget(divider())
        layout.addSpacing(9)
        layout.addWidget(label("WORKING FOLDER", "eyebrow"))
        self.folder = ElidedLabel("No folder selected", "strong")
        layout.addWidget(self.folder)
        self.folder_summary = label("Choose a folder to begin", "helper")
        layout.addWidget(self.folder_summary)
        layout.addSpacing(12)
        bottom = QHBoxLayout()
        bottom.addWidget(label("Local & private", "helper"))
        bottom.addStretch()
        bottom.addWidget(label(f"v{__version__}", "helper"))
        layout.addLayout(bottom)

    def set_scan(self, scan: ScanResult | None) -> None:
        self.folder.setText(scan.root.name or str(scan.root) if scan else "No folder selected")
        if scan:
            self.folder.setToolTip(str(scan.root))
        self.folder_summary.setText(f"{count_label(len(scan.files), 'file')} · {human_size(scan.total_size)}" if scan else "Choose a folder to begin")

    def update_icons(self) -> None:
        c = current_colors()
        for nav in self.nav:
            nav.setIcon(icon(nav.text(), c.accent if nav.isChecked() else c.muted, 19))


class WorkspaceHeader(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("WorkspaceHeader")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(10)
        self.glyph = label()
        self.glyph.setFixedSize(24, 24)
        layout.addWidget(self.glyph)
        path = QVBoxLayout()
        path.setSpacing(2)
        self.caption = label("WORKING FOLDER", "eyebrow")
        self.path = ElidedLabel("Choose a folder to get started", "strong")
        path.addWidget(self.caption)
        path.addWidget(self.path)
        layout.addLayout(path, 1)
        self.copy = CopyButton("Copy working folder path")
        layout.addWidget(self.copy)
        self.rescan = button("Rescan")
        self.rescan.setToolTip("Rescan the selected folder (Ctrl+R)")
        layout.addWidget(self.rescan)
        self.choose = button("Choose Folder", True)
        self.choose.setToolTip("Choose a folder (Ctrl+O)")
        layout.addWidget(self.choose)
        self.set_folder(None)

    def set_folder(self, root: Path | None) -> None:
        self.path.setText(str(root) if root else "Choose a folder to get started")
        self.caption.setText("WORKING FOLDER" if root else "FILEPILOT WORKSPACE")
        self.copy.value = str(root) if root else ""
        self.copy.setVisible(root is not None)
        self.rescan.setVisible(root is not None)
        self.update_icons()

    def update_icons(self) -> None:
        c = current_colors()
        self.glyph.setPixmap(icon("folder", c.accent, 23).pixmap(23, 23))
        self.rescan.setIcon(icon("rescan", c.muted, 16))


class StatusDot(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.busy = False
        self.setFixedSize(10, 10)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        c = current_colors()
        p.setBrush(QColor(c.warning if self.busy else c.accent))
        p.drawEllipse(2, 2, 6, 6)
        p.end()


class StatusBar(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("StatusBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 7, 24, 7)
        layout.setSpacing(10)
        self.dot = StatusDot()
        layout.addWidget(self.dot)
        self.message = ElidedLabel("Ready", "helper")
        layout.addWidget(self.message, 1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(112)
        self.progress.setTextVisible(False)
        self.progress.setAccessibleName("Current operation progress")
        self.progress.hide()
        layout.addWidget(self.progress)
        self.cancel = button("Cancel")
        self.cancel.setProperty("quiet", True)
        self.cancel.setAccessibleName("Cancel current operation")
        self.cancel.hide()
        layout.addWidget(self.cancel)

    def set_busy(self, busy: bool) -> None:
        self.dot.busy = busy
        self.dot.update()
        self.progress.setVisible(busy)
        self.cancel.setVisible(busy)


class FeedbackBar(QFrame):
    history_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("FeedbackBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 6, 6)
        self.message = ElidedLabel("", "strong")
        layout.addWidget(self.message, 1)
        history = button("View history")
        history.setProperty("quiet", True)
        history.clicked.connect(self.history_requested)
        layout.addWidget(history)
        close = button("")
        close.setProperty("quiet", True)
        close.setProperty("iconOnly", True)
        close.setIcon(icon("close", current_colors().muted, 16))
        close.setAccessibleName("Dismiss operation result")
        close.clicked.connect(self.hide)
        layout.addWidget(close)
        self.hide()

    def show_result(self, text: str) -> None:
        self.message.setText(text)
        self.show()
