from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog, QFrame, QHBoxLayout, QPlainTextEdit, QVBoxLayout

from filepilot.ui.components.controls import CopyButton, ElidedLabel
from filepilot.ui.components.widgets import button, label


class DetailStrip(QFrame):
    """Compact selection context with an unabridged, copyable details dialog."""
    def __init__(self, prompt: str = "Select a file to inspect its full path.") -> None:
        super().__init__()
        self.setObjectName("DetailStrip")
        self.prompt = prompt
        self.details_text = ""
        self.dialog_title = "File details"
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        text = QVBoxLayout()
        text.setSpacing(3)
        self.title = ElidedLabel(prompt, "strong")
        self.subtitle = ElidedLabel("Full names and paths are available here.", "helper")
        text.addWidget(self.title)
        text.addWidget(self.subtitle)
        layout.addLayout(text, 1)
        self.copy = CopyButton()
        layout.addWidget(self.copy)
        self.inspect = button("Details…")
        self.inspect.setAccessibleName("Inspect complete file details")
        self.inspect.clicked.connect(self.open_details)
        layout.addWidget(self.inspect)
        self.clear()

    def clear(self) -> None:
        self.title.setText(self.prompt)
        self.subtitle.setText("Full names and paths are available here.")
        self.details_text = ""
        self.copy.value = ""
        self.copy.setEnabled(False)
        self.inspect.setEnabled(False)

    def set_details(self, title: str, lines: list[tuple[str, str]], copy_path: Path | str,
                    dialog_title: str = "File details") -> None:
        self.title.setText(title)
        self.subtitle.setText(lines[0][1] if lines else str(copy_path))
        self.details_text = "\n\n".join(f"{name}\n{value}" for name, value in lines)
        self.dialog_title = dialog_title
        self.title.setToolTip(title + "\n" + str(copy_path))
        self.subtitle.setToolTip(self.details_text)
        self.copy.value = str(copy_path)
        self.copy.setEnabled(True)
        self.inspect.setEnabled(True)

    def create_dialog(self) -> QDialog:
        dialog = QDialog(self)
        dialog.setWindowTitle(self.dialog_title)
        dialog.resize(680, 380)
        dialog.setMinimumSize(480, 260)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.addWidget(label("Full details", "section"))
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(self.details_text)
        editor.setAccessibleName("Unabridged file names, paths, and metadata")
        layout.addWidget(editor, 1)
        footer = QHBoxLayout()
        copy_all = button("Copy details")
        copy_all.clicked.connect(lambda: QApplication.clipboard().setText(self.details_text))
        footer.addWidget(copy_all)
        footer.addStretch()
        close = button("Close")
        close.clicked.connect(dialog.accept)
        footer.addWidget(close)
        layout.addLayout(footer)
        return dialog

    def open_details(self) -> None:
        if self.details_text:
            self.create_dialog().exec()
