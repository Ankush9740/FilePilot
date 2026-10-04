from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QLineEdit, QVBoxLayout

from filepilot.core.categories import Category, EXTENSIONS
from filepilot.models.records import Settings
from filepilot.ui.components.controls import ThemeSelector, UnitSpinBox
from filepilot.ui.components.icons import category_icon
from filepilot.ui.components.widgets import Page, button, label, scroll_body


class SettingsPage(Page):
    save_requested = Signal(object)

    def __init__(self, settings: Settings) -> None:
        super().__init__("Preferences", "A workspace that fits you. Preferences stay on this computer.")
        self.busy = False
        self.saved = settings
        self.feedback = label("Saved locally", "helper")
        self.feedback.setAccessibleName("Preference save status")
        self.actions.addWidget(self.feedback)
        self.save = button("Save preferences", True)
        self.save.clicked.connect(self.save_settings)
        self.actions.addWidget(self.save)
        self.scroll, _, layout = scroll_body()
        self.layout.addWidget(self.scroll, 1)
        appearance = self.section(layout, "Appearance", "Choose a reading environment. System follows your Windows appearance.")
        self.theme = ThemeSelector(settings.theme)
        appearance.addWidget(self.theme)
        analysis = self.section(layout, "Files worth a closer look", "These thresholds shape insights and filters. They never trigger deletion.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)
        self.old_days = UnitSpinBox()
        self.old_days.setRange(1, 36500)
        self.old_days.setSuffix(" days")
        self.old_days.setValue(settings.old_days)
        self.old_days.setAccessibleName("Older file threshold in days")
        self.large_mb = UnitSpinBox()
        self.large_mb.setRange(1, 1_000_000)
        self.large_mb.setSuffix(" MB")
        self.large_mb.setValue(settings.large_mb)
        self.large_mb.setAccessibleName("Large file threshold in megabytes")
        for row, (caption, edit) in enumerate((("Not modified for at least", self.old_days), ("Large file size at least", self.large_mb))):
            grid.addWidget(label(caption), row, 0)
            edit.setFixedWidth(155)
            grid.addWidget(edit, row, 1)
        grid.setColumnStretch(2, 1)
        analysis.addLayout(grid)
        mappings = self.section(layout, "Category destinations", "Folder names used by future previews. Each destination is a direct child of the working folder.")
        rules = QGridLayout()
        rules.setHorizontalSpacing(14)
        rules.setVerticalSpacing(7)
        rules.addWidget(label("CATEGORY", "eyebrow"), 0, 0, 1, 2)
        rules.addWidget(label("DESTINATION FOLDER", "eyebrow"), 0, 2)
        rules.addWidget(label("RECOGNIZED TYPES", "eyebrow"), 0, 3)
        self.destinations = {}
        self.category_glyphs = []
        for row, category in enumerate(Category, 1):
            glyph = label()
            glyph.setFixedSize(20, 20)
            self.category_glyphs.append((category, glyph))
            rules.addWidget(glyph, row, 0)
            rules.addWidget(label(str(category), "strong"), row, 1)
            edit = QLineEdit(settings.destinations[str(category)])
            edit.setAccessibleName(f"{category} destination folder")
            edit.setMaxLength(80)
            edit.setMinimumWidth(130)
            edit.setMaximumWidth(235)
            rules.addWidget(edit, row, 2)
            extensions = sorted(EXTENSIONS[category])
            complete = ", ".join(extensions) or "Unrecognized extensions"
            summary = ", ".join(extensions[:4]) + (f"  +{len(extensions) - 4}" if len(extensions) > 4 else "") if extensions else "Everything else"
            types = label(summary, "helper")
            types.setToolTip(complete)
            types.setAccessibleName(f"{category}: {complete}")
            rules.addWidget(types, row, 3)
            self.destinations[str(category)] = edit
        rules.setColumnStretch(3, 1)
        mappings.addLayout(rules)
        privacy = self.section(layout, "Local & private", "No account. No telemetry. No uploads.")
        privacy.addWidget(label("FilePilot reads metadata and content hashes locally. Your document contents are never stored in its database.", "helper", wrap=True))
        layout.addStretch()
        self.theme.currentTextChanged.connect(self.changed)
        self.old_days.valueChanged.connect(self.changed)
        self.large_mb.valueChanged.connect(self.changed)
        for edit in self.destinations.values():
            edit.textChanged.connect(self.changed)
        self.update_icons()
        self.changed()

    @staticmethod
    def section(layout, title, description):
        frame = QFrame()
        frame.setObjectName("SettingSection")
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(16, 14, 16, 16)
        inner.setSpacing(10)
        inner.addWidget(label(title, "section"))
        inner.addWidget(label(description, "helper", wrap=True))
        layout.addWidget(frame)
        return inner

    def current_settings(self) -> Settings:
        return Settings(self.theme.currentText(), self.old_days.value(), self.large_mb.value(),
                        {category: edit.text() for category, edit in self.destinations.items()})

    def changed(self, *args) -> None:
        dirty = self.current_settings() != self.saved
        self.feedback.setText("Unsaved changes" if dirty else "Saved locally")
        self.save.setEnabled(dirty and not self.busy)

    def mark_saved(self, settings: Settings) -> None:
        self.saved = settings
        self.theme.setCurrentText(settings.theme)
        self.old_days.setValue(settings.old_days)
        self.large_mb.setValue(settings.large_mb)
        for category, edit in self.destinations.items():
            edit.setText(settings.destinations[category])
        self.changed()

    def update_icons(self) -> None:
        for category, glyph in self.category_glyphs:
            glyph.setPixmap(category_icon(category, 18).pixmap(18, 18))

    def set_busy(self, busy: bool) -> None:
        super().set_busy(busy)
        self.changed()

    def save_settings(self) -> None:
        if not self.busy:
            self.save_requested.emit(self.current_settings())
