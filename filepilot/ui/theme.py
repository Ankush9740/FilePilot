"""FilePilot's shared surfaces, typography, and native control states."""
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True, slots=True)
class Colors:
    background: str
    surface: str
    sidebar: str
    text: str
    muted: str
    border: str
    accent: str
    tint: str
    hover: str
    raised: str
    faint: str
    warning: str
    on_accent: str
    dark: bool = False


LIGHT = Colors("#F4F2ED", "#FAF9F5", "#EDEAE2", "#29332E", "#68736B", "#DADDD3",
               "#2F6651", "#E4ECE4", "#EDEFE7", "#EDEFE7", "#879187", "#94682F", "#FFFFFF")
DARK = Colors("#252A27", "#2C322E", "#202622", "#EEEEE5", "#B0B9AE", "#414B43",
              "#99BBA0", "#35483B", "#343D36", "#303A32", "#8C9C8D", "#D0AB76", "#203127", True)


def colors_for(requested: str, scheme: Qt.ColorScheme | None = None) -> Colors:
    if scheme is None:
        scheme = QApplication.instance().styleHints().colorScheme()
    return DARK if requested == "Dark" or requested == "System" and scheme == Qt.ColorScheme.Dark else LIGHT


def current_colors() -> Colors:
    app = QApplication.instance()
    return (app.property("filepilotColors") or LIGHT) if app else LIGHT


def apply_theme(app: QApplication, requested: str) -> Colors:
    c = colors_for(requested)
    app.setProperty("filepilotColors", c)
    palette = QPalette()
    roles = ((QPalette.ColorRole.Window, c.background), (QPalette.ColorRole.Base, c.surface),
             (QPalette.ColorRole.AlternateBase, c.raised), (QPalette.ColorRole.Text, c.text),
             (QPalette.ColorRole.WindowText, c.text), (QPalette.ColorRole.Button, c.surface),
             (QPalette.ColorRole.ButtonText, c.text), (QPalette.ColorRole.Highlight, c.tint),
             (QPalette.ColorRole.HighlightedText, c.text), (QPalette.ColorRole.ToolTipBase, c.surface),
             (QPalette.ColorRole.ToolTipText, c.text))
    for role, color in roles:
        palette.setColor(role, QColor(color))
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(c.faint if role in (
            QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText) else color))
    app.setPalette(palette)
    assets = (Path(__file__).parent / "assets").as_posix()
    suffix = "dark" if c.dark else "light"
    down, up, right = [f"{assets}/{name}-{suffix}.svg" for name in ("chevron-down", "chevron-up", "chevron-right")]
    app.setStyleSheet(f"""
        QWidget {{ color: {c.text}; font-family: 'Segoe UI'; font-size: 13px; }}
        QMainWindow, #Shell, #Page, QScrollArea, #ScrollBody {{ background: {c.background}; }}
        #Sidebar {{ background: {c.sidebar}; border-right: 1px solid {c.border}; }}
        #WorkspaceHeader, #StatusBar {{ background: {c.surface}; }}
        QLabel {{ background: transparent; }}
        QLabel[role='muted'], QLabel[role='helper'] {{ color: {c.muted}; }}
        QLabel[role='helper'] {{ font-size: 11px; }}
        QLabel[role='eyebrow'] {{ color: {c.muted}; font-size: 10px; font-weight: 600; letter-spacing: 1.3px; }}
        QLabel[role='title'] {{ font-size: 27px; font-weight: 600; letter-spacing: -0.6px; }}
        QLabel[role='section'] {{ font-size: 16px; font-weight: 600; }}
        QLabel[role='strong'] {{ font-weight: 600; }}
        QLabel[role='metric'] {{ font-size: 27px; font-weight: 600; letter-spacing: -0.7px; }}
        QLabel[role='metric'][waiting='true'] {{ color: {c.muted}; font-size: 16px; font-weight: 500; letter-spacing: 0px; }}
        QLabel[role='metric'][accent='true'], QLabel[role='success'] {{ color: {c.accent}; }}
        QLabel[role='warning'] {{ color: {c.warning}; }}
        QLabel[role='brand'] {{ font-size: 22px; font-weight: 650; letter-spacing: -0.7px; }}
        #Divider {{ background: {c.border}; max-height: 1px; min-height: 1px; }}
        #MetricDivider {{ background: {c.border}; min-width: 1px; max-width: 1px; }}
        #Surface, #SummaryStrip, #FilterBar, #SettingSection {{ background: {c.surface}; border: 1px solid {c.border}; border-radius: 5px; }}
        #DetailStrip, #ResultStrip {{ background: {c.raised}; border: 1px solid {c.border}; border-radius: 3px; }}
        #NoticeStrip, #FeedbackBar {{ background: {c.tint}; border: 1px solid {c.border}; border-radius: 4px; }}
        QPushButton {{ background: {c.surface}; border: 1px solid {c.border}; border-radius: 4px;
            padding: 7px 12px; font-weight: 600; min-height: 20px; }}
        QPushButton:hover {{ background: {c.hover}; border-color: {c.faint}; }}
        QPushButton:pressed {{ background: {c.tint}; border-color: {c.accent}; }}
        QPushButton:focus {{ border: 1px solid {c.accent}; outline: none; }}
        QPushButton:disabled {{ color: {c.faint}; background: {c.background}; border-color: {c.border}; }}
        QPushButton[primary='true'] {{ background: {c.accent}; color: {c.on_accent}; border-color: {c.accent}; }}
        QPushButton[primary='true']:hover {{ background: {'#B0CEB4' if c.dark else '#25553F'}; }}
        QPushButton[primary='true']:pressed {{ background: {'#82A98C' if c.dark else '#214B38'}; }}
        QPushButton[primary='true']:focus {{ border: 2px solid {c.text}; padding: 6px 11px; }}
        QPushButton[primary='true']:disabled {{ background: {c.raised}; color: {c.faint}; border-color: {c.border}; }}
        QPushButton[quiet='true'] {{ background: transparent; border-color: transparent; color: {c.muted}; font-weight: 500; }}
        QPushButton[quiet='true']:hover {{ background: {c.hover}; color: {c.text}; }}
        QPushButton[quiet='true']:focus {{ border-color: {c.accent}; }}
        QPushButton[iconOnly='true'] {{ padding: 5px; min-width: 22px; min-height: 22px; }}
        QPushButton[nav='true'] {{ text-align: left; background: transparent; border: 1px solid transparent;
            border-left: 3px solid transparent; padding: 8px 12px; font-weight: 500; border-radius: 3px; }}
        QPushButton[nav='true']:hover {{ background: {c.hover}; }}
        QPushButton[nav='true']:checked {{ background: {c.tint}; border-left-color: {c.accent}; color: {c.text}; font-weight: 600; }}
        QPushButton[nav='true']:focus {{ border-top-color: {c.accent}; border-right-color: {c.accent}; border-bottom-color: {c.accent}; }}
        QLineEdit, QComboBox, QSpinBox {{ background: {c.surface}; border: 1px solid {c.border};
            border-radius: 4px; padding: 7px 9px; min-height: 22px; selection-background-color: {c.tint}; selection-color: {c.text}; }}
        QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {c.faint}; }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {c.accent}; }}
        QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {c.faint}; background: {c.background}; }}
        QComboBox {{ padding-right: 28px; }}
        QComboBox[activeFilter='true'] {{ background: {c.tint}; border-color: {c.accent}; }}
        QComboBox::drop-down {{ border: none; width: 28px; }}
        QComboBox::down-arrow {{ image: url({down}); width: 12px; height: 12px; }}
        QComboBox QAbstractItemView {{ background: {c.surface}; border: 1px solid {c.border}; padding: 4px;
            selection-background-color: {c.tint}; selection-color: {c.text}; outline: none; }}
        QComboBox QAbstractItemView::item {{ min-height: 28px; padding: 3px 8px; border-radius: 2px; }}
        QSpinBox {{ padding-right: 28px; }}
        QSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 26px; border-left: 1px solid {c.border}; }}
        QSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 26px; border-left: 1px solid {c.border}; }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {c.tint}; }}
        QSpinBox::up-arrow {{ image: url({up}); width: 10px; height: 10px; }}
        QSpinBox::down-arrow {{ image: url({down}); width: 10px; height: 10px; }}
        QTableView, QTreeView, #Timeline {{ background: {c.surface}; alternate-background-color: {c.surface};
            border: 1px solid {c.border}; border-radius: 4px; gridline-color: {c.border};
            selection-background-color: {c.tint}; selection-color: {c.text}; outline: none; }}
        QTableView::item, QTreeView::item {{ padding: 8px; border: none; }}
        QTableView::item:hover, QTreeView::item:hover {{ background: {c.hover}; }}
        QTableView::item:selected, QTreeView::item:selected {{ background: {c.tint}; }}
        QTableView::item:focus, QTreeView::item:focus {{ border: 1px solid {c.accent}; }}
        QHeaderView::section {{ background: {c.raised}; color: {c.muted}; padding: 9px 10px;
            border: none; border-bottom: 1px solid {c.border}; font-size: 11px; font-weight: 600; }}
        QHeaderView::section:hover {{ color: {c.text}; background: {c.hover}; }}
        QHeaderView::up-arrow {{ image: url({up}); width: 10px; height: 10px; }}
        QHeaderView::down-arrow {{ image: url({down}); width: 10px; height: 10px; }}
        QTreeView::branch:has-children:closed {{ image: url({right}); }}
        QTreeView::branch:has-children:open {{ image: url({down}); }}
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 3px 1px; }}
        QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 1px 3px; }}
        QScrollBar::handle {{ background: {c.border}; border-radius: 3px; }}
        QScrollBar::handle:vertical {{ min-height: 28px; }}
        QScrollBar::handle:horizontal {{ min-width: 28px; }}
        QScrollBar::handle:hover {{ background: {c.faint}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0px; width: 0px; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
        QProgressBar {{ background: {c.border}; border: none; border-radius: 2px; min-height: 4px; max-height: 4px; }}
        QProgressBar::chunk {{ background: {c.accent}; border-radius: 2px; }}
        QToolTip {{ color: {c.text}; background: {c.surface}; border: 1px solid {c.border}; padding: 7px; }}
        QPlainTextEdit {{ background: {c.surface}; border: 1px solid {c.border}; padding: 8px; selection-background-color: {c.tint}; }}
        QSplitter::handle {{ background: {c.border}; height: 1px; }}
        QMessageBox, QDialog {{ background: {c.background}; }}
    """)
    return c
