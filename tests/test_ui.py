import pytest
from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from filepilot.core.safety import SafetyPolicy
from filepilot.database.store import Store
from filepilot.models.records import Settings
from filepilot.ui.window import MainWindow


@pytest.fixture(scope="session")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyle("Fusion")
    # Qt's Windows offscreen plugin doesn't discover installed fonts automatically.
    if not QFontDatabase.families():
        for name in ("segoeui.ttf", "seguisb.ttf", "segoeuib.ttf"):
            QFontDatabase.addApplicationFont(f"C:/Windows/Fonts/{name}")
    return instance


@pytest.fixture
def window(tmp_path, app, monkeypatch):
    store = Store(tmp_path / "data" / "filepilot.sqlite3")
    instance = MainWindow(store, SafetyPolicy((store.path.parent,)))
    notices = []
    monkeypatch.setattr(instance, "notice", lambda *args, **kwargs: notices.append((args, kwargs)))
    instance.test_notices = notices
    instance.show()
    app.processEvents()
    yield instance
    if instance.job:
        instance.job.cancel()
        wait_idle(instance)
    instance.close()
    app.processEvents()


def wait_idle(window, timeout=20):
    # Use Qt's real event loop, which releases the GIL to Python QThread workers.
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(10)
    poll.timeout.connect(lambda: loop.quit() if window.job is None else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start()
    deadline.start(int(timeout * 1000))
    loop.exec()
    poll.stop()
    deadline.stop()
    assert window.job is None, "Background worker did not finish"
    errors = [notice for notice in window.test_notices if notice[0][0] == "Operation could not finish"]
    assert not errors, errors


def test_first_launch_empty_states_and_responsive_themes(window, app):
    assert window.state.scan is None
    assert window.dashboard.stack.currentIndex() == 0
    assert window.duplicates.stack.currentIndex() == 0
    assert not window.rescan.isEnabled()
    for theme in ("Light", "Dark", "System"):
        window.state.settings.theme = theme
        window.set_theme()
        for width, height in ((1440, 900), (1280, 800), (1000, 680)):
            window.resize(width, height)
            app.processEvents()
            assert window.pages.width() == width - 216
            assert not window.grab().isNull()
            for page in range(6):
                window.navigate(page)
                app.processEvents()
                assert window.pages.currentWidget().isVisible()


def test_threaded_scan_sort_filter_duplicate_preview_apply_undo(window, tmp_path, monkeypatch):
    root = tmp_path / "files"
    root.mkdir()
    (root / "a.txt").write_bytes(b"exact match")
    (root / "b.pdf").write_bytes(b"exact match")
    (root / "large.png").write_bytes(b"x" * 200)
    window.scan_folder(root)
    assert window.job is not None and not window.choose.isEnabled()
    wait_idle(window)
    assert len(window.state.scan.files) == 3
    assert window.choose.isEnabled()
    window.files.search.setText("a.txt")
    assert window.files.proxy.rowCount() == 1
    window.files.search.clear()
    window.files.category.setCurrentText("Images")
    assert window.files.proxy.rowCount() == 1
    window.files.category.setCurrentText("All categories")
    window.files.view.sortByColumn(2, Qt.SortOrder.DescendingOrder)
    first = window.files.proxy.mapToSource(window.files.proxy.index(0, 0))
    assert window.files.model.rows[first.row()].name == "large.png"
    window.analyze_duplicates()
    wait_idle(window)
    assert window.state.duplicates.extra_copies == 1
    group = window.duplicates.model.index(0, 0)
    child = window.duplicates.model.index(0, 0, group)
    assert window.duplicates.model.parent(child) == group
    window.create_preview()
    wait_idle(window)
    assert len(window.state.plan.actionable) == 3
    assert (root / "a.txt").exists() and not window.store.history()
    monkeypatch.setattr(window, "confirm", lambda *args: False)
    window.apply_organization()
    assert window.job is None and (root / "a.txt").exists()
    monkeypatch.setattr(window, "confirm", lambda *args: True)
    window.apply_organization()
    wait_idle(window)
    assert not (root / "a.txt").exists()
    assert (root / "Documents" / "a.txt").read_bytes() == b"exact match"
    assert window.state.plan is None
    operation_id = window.store.history()[0]["id"]
    assert window.history.undo.isEnabled()
    window.undo_operation(operation_id)
    wait_idle(window)
    assert (root / "a.txt").read_bytes() == b"exact match"
    assert (root / "b.pdf").exists() and (root / "large.png").exists()
    assert window.store.history()[0]["status"] == "undone"
    assert not (root / "Documents").exists() and not (root / "Images").exists()
    assert not window.history.undo.isEnabled()
    assert window.history.undo.text() == "No moves to undo"


def test_settings_persist_and_update_real_analysis(window, tmp_path):
    root = tmp_path / "files"
    root.mkdir()
    (root / "large.bin").write_bytes(b"x" * 1024 * 1024)
    window.scan_folder(root)
    wait_idle(window)
    assert not window.state.analysis.large
    settings = Settings(theme="Dark", large_mb=1, old_days=30)
    window.save_preferences(settings)
    wait_idle(window)
    assert len(window.state.analysis.large) == 1
    assert Store(window.store.path).load_settings() == settings
    window.browse_files("Large files")
    assert window.files.proxy.rowCount() == 1


def test_cancel_preview_does_not_change_files(window, tmp_path):
    root = tmp_path / "files"
    root.mkdir()
    (root / "a.txt").write_text("untouched")
    window.scan_folder(root)
    wait_idle(window)
    window.create_preview()
    wait_idle(window)
    window.cancel_preview()
    assert window.state.plan is None
    assert (root / "a.txt").read_text() == "untouched"
    assert not window.store.history()


def test_recovery_runs_in_worker_on_startup(window):
    window.initialize()
    assert window.job is not None
    wait_idle(window)
    assert not window.store.history()


def test_thousand_file_scan_keeps_gui_event_loop_live(window, tmp_path):
    root = tmp_path / "many-files"
    root.mkdir()
    for index in range(1200):
        (root / f"file-{index:04d}.txt").write_bytes(b"read-only fixture")
    ticks = []
    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(lambda: ticks.append(window.job is not None))
    timer.start()
    window.scan_folder(root)
    wait_idle(window)
    timer.stop()
    assert len(window.state.scan.files) == 1200
    assert any(ticks), "GUI timer did not run while the scan worker was active"


def test_dashboard_summary_stays_visible_through_entire_scroll(window, tmp_path, app):
    root = tmp_path / "scroll-fixture"
    root.mkdir()
    for index in range(40):
        (root / f"document-{index:02d}.txt").write_bytes(b"x" * (index + 1))
    window.scan_folder(root)
    wait_idle(window)
    window.navigate(0)
    for theme in ("Light", "Dark", "System"):
        window.state.settings.theme = theme
        window.set_theme()
        for size in ((1440, 900), (1280, 800), (1000, 680)):
            window.resize(*size)
            app.processEvents()
            scrollbar = window.dashboard.scroll.verticalScrollBar()
            positions = [metric.value.mapTo(window, metric.value.rect().topLeft()) for metric in window.dashboard.summary.metrics]
            for value in (0, scrollbar.maximum() // 2, scrollbar.maximum()):
                scrollbar.setValue(value)
                app.processEvents()
                for metric, position in zip(window.dashboard.summary.metrics, positions):
                    assert metric.value.mapTo(window, metric.value.rect().topLeft()) == position
                    assert metric.value.visibleRegion().boundingRect().contains(metric.value.rect())
                    assert metric.value.height() >= metric.value.fontMetrics().height()
            if size[0] == 1000:
                assert scrollbar.maximum() > 0


def test_full_values_remain_inspectable_and_copyable(window, tmp_path, app):
    from pathlib import Path
    from filepilot.core.categories import Category
    from filepilot.models.records import FileRecord, ScanResult
    from filepilot.services.analysis import analyze
    from PySide6.QtWidgets import QPlainTextEdit

    # Deliberately beyond MAX_PATH: model inspection must not truncate the source value.
    name = "final-design-with-reviewed-revisions-" * 5 + ".png"
    root = tmp_path / "root"
    path = root / ("very-long-folder-" * 12) / name
    record = FileRecord(path, 123456, 1_700_000_000_000_000_000, None, Category.IMAGES, 1, 2)
    window.state.scan = ScanResult(root, [record])
    window.state.analysis = analyze([record], window.state.settings)
    window.refresh()
    window.navigate(1)
    window.resize(1000, 680)
    window.files.view.selectRow(0)
    app.processEvents()
    details = window.files.details
    assert name in details.title.toolTip()
    assert str(path) in details.details_text
    assert str(path) in window.files.model.index(0, 0).data(Qt.ItemDataRole.ToolTipRole)
    QTest.mouseClick(details.copy, Qt.MouseButton.LeftButton)
    assert app.clipboard().text() == str(path)
    dialog = details.create_dialog()
    editor = dialog.findChild(QPlainTextEdit)
    assert editor.isReadOnly() and str(path) in editor.toPlainText()
    assert name in editor.toPlainText()
    dialog.deleteLater()
    assert window.header.path.toolTip() == str(root)


def test_filter_reset_and_insight_navigation_clear_unrelated_filters(window, tmp_path, app):
    root = tmp_path / "filter-fixture"
    root.mkdir()
    (root / "drawing.png").write_bytes(b"png fixture")
    (root / "notes.txt").write_bytes(b"text fixture")
    window.scan_folder(root)
    wait_idle(window)
    window.navigate(1)
    window.files.search.setText("missing")
    window.files.extension.setCurrentText(".txt")
    window.files.mode.setCurrentText("Older files")
    window.files.category.setCurrentText("Documents")
    assert window.files.proxy.rowCount() == 0
    assert window.files.category.property("activeFilter")
    assert window.files.active_filters.text() == "4 active filters"
    assert window.files.no_results.isVisible()
    QTest.mouseClick(window.files.reset, Qt.MouseButton.LeftButton)
    assert window.files.proxy.rowCount() == 2
    assert not window.files.reset.isVisible()
    assert not window.files.category.property("activeFilter")
    window.files.search.setText("notes")
    window.files.extension.setCurrentText(".txt")
    window.browse_category("Images")
    assert window.pages.currentIndex() == 1
    assert window.files.proxy.rowCount() == 1
    assert window.files.search.text() == ""
    assert window.files.extension.currentText() == "All extensions"
    window.browse_files("All files")
    assert window.files.proxy.rowCount() == 2


def test_background_work_allows_reading_but_disables_conflicting_actions(window, tmp_path, app):
    from threading import Event
    root = tmp_path / "busy-fixture"
    root.mkdir()
    (root / "notes.txt").write_bytes(b"read-only fixture")
    window.scan_folder(root)
    wait_idle(window)
    window.create_preview()
    wait_idle(window)
    release = Event()
    window.start_job("Comparing file contents locally", lambda cancel, progress: release.wait(5), lambda result: None)
    try:
        window.focus_search()
        assert window.pages.isEnabled() and window.files.search.isEnabled()
        window.files.search.setText("notes")
        assert window.files.proxy.rowCount() == 1
        window.files.view.selectRow(0)
        assert window.files.details.inspect.isEnabled()
        assert window.files.details.copy.isEnabled()
        assert not window.choose.isEnabled()
        assert not window.duplicates.analyze.isEnabled()
        assert not window.organize.apply.isEnabled()
        assert not window.organize.cancel.isEnabled()
        window.navigate(5)
        window.preferences.old_days.setValue(99)
        assert not window.preferences.save.isEnabled()
        assert window.preferences.old_days.isEnabled()
        assert window.status_bar.progress.isVisible()
    finally:
        release.set()
        wait_idle(window)
    assert window.organize.apply.isEnabled()
    assert window.preferences.save.isEnabled()
    assert not window.status_bar.progress.isVisible()


def test_nested_move_confirmation_is_complete_and_cancelling_is_read_only(window, tmp_path, monkeypatch):
    from filepilot.ui.pages.organize import NESTED_EXPLANATION
    root = tmp_path / "nested-fixture"
    nested = root / "assets" / "originals"
    nested.mkdir(parents=True)
    file = nested / "picture.png"
    file.write_bytes(b"untouched")
    window.scan_folder(root)
    wait_idle(window)
    window.create_preview()
    wait_idle(window)
    captured = []
    monkeypatch.setattr(window, "confirm", lambda *args: captured.append(args) or False)
    window.apply_organization()
    assert len(captured) == 1
    text = captured[0][1]
    assert "Move 1 file" in text and str(root) in text
    assert NESTED_EXPLANATION in text and "1 nested file" in text
    assert "History for undo" in text
    assert window.job is None and file.read_bytes() == b"untouched"
    assert not window.store.history()


def test_history_requires_explicit_selection_and_names_undo_target(window, tmp_path, monkeypatch):
    from filepilot.ui.pages.history import undo_available
    root = tmp_path / "history-fixture"
    root.mkdir()
    (root / "record.txt").write_bytes(b"undo fixture")
    window.scan_folder(root)
    wait_idle(window)
    window.create_preview()
    wait_idle(window)
    monkeypatch.setattr(window, "confirm", lambda *args: True)
    window.apply_organization()
    wait_idle(window)
    rows = window.store.history()
    window.history.view.clearSelection()
    window.history.refresh(rows)
    assert window.history.selected_operation() is None
    assert not window.history.undo.isEnabled()
    window.history.select_operation(rows[0]["id"])
    assert window.history.undo.isEnabled()
    assert f"#{rows[0]['id']:04d}" in window.history.undo.text()
    captured = []
    monkeypatch.setattr(window, "confirm", lambda *args: captured.append(args) or False)
    window.history.undo_selected()
    assert str(root) in captured[0][1] and "Restore 1 file" in captured[0][1]
    for status in ("running", "undoing", "interrupted"):
        assert not undo_available({**rows[0], "status": status})
    assert undo_available({**rows[0], "status": "partial_undo"})
    assert not undo_available({**rows[0], "remaining": 0})


def test_theme_keyboard_save_feedback_and_system_palette(window, app):
    from filepilot.ui.theme import DARK, LIGHT, colors_for
    window.navigate(5)
    dark = window.preferences.theme.options["Dark"]
    dark.setFocus()
    QTest.keyClick(dark, Qt.Key.Key_Space)
    assert window.preferences.theme.currentText() == "Dark"
    assert window.preferences.feedback.text() == "Unsaved changes"
    assert window.preferences.save.isEnabled()
    QTest.mouseClick(window.preferences.save, Qt.MouseButton.LeftButton)
    assert window.store.load_settings().theme == "Dark"
    assert window.colors == DARK
    assert window.preferences.feedback.text() == "Saved locally"
    assert not window.preferences.save.isEnabled()
    assert not window.test_notices
    assert colors_for("System", Qt.ColorScheme.Dark) == DARK
    assert colors_for("System", Qt.ColorScheme.Light) == LIGHT
    assert colors_for("System", Qt.ColorScheme.Unknown) == LIGHT


def test_duplicate_group_inspection_exposes_every_path_and_digest(window, tmp_path, app):
    root = tmp_path / "comparison-fixture"
    nested = root / "originals"
    nested.mkdir(parents=True)
    for file in (root / "a.png", nested / "b.png", root / "c.jpg"):
        file.write_bytes(b"identical")
    window.scan_folder(root)
    wait_idle(window)
    window.analyze_duplicates()
    wait_idle(window)
    window.navigate(2)
    group = window.duplicates.model.index(0, 0)
    window.duplicates.view.setCurrentIndex(group)
    app.processEvents()
    details = window.duplicates.details.details_text
    result = window.state.duplicates.groups[0]
    assert result.digest in details
    assert all(str(file.path) in details for file in result.files)
    assert not window.duplicates.reveal.isEnabled()
    child = window.duplicates.model.index(0, 0, group)
    window.duplicates.view.setCurrentIndex(child)
    app.processEvents()
    assert window.duplicates.reveal.isEnabled()
    assert str(result.files[0].path) in window.duplicates.details.details_text


def test_threshold_wheel_changes_only_the_focused_field(window, app):
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent
    window.navigate(5)
    spin = window.preferences.old_days
    initial = spin.value()
    window.choose.setFocus()
    app.processEvents()

    def wheel():
        point = QPointF(spin.rect().center())
        event = QWheelEvent(point, QPointF(spin.mapToGlobal(spin.rect().center())), QPoint(), QPoint(0, 120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        app.sendEvent(spin, event)

    wheel()
    assert spin.value() == initial
    spin.setFocus()
    app.processEvents()
    wheel()
    assert spin.value() == initial + 1


def test_storage_proportions_zero_bytes_and_keyboard_category_navigation(window, tmp_path, app):
    from filepilot.core.categories import Category
    root = tmp_path / "storage-fixture"
    root.mkdir()
    (root / "installer.exe").write_bytes(b"x" * 1000)
    (root / "tiny.py").write_bytes(b"x")
    (root / "empty.txt").write_bytes(b"")
    window.scan_folder(root)
    wait_idle(window)
    window.navigate(0)
    app.processEvents()
    segments = dict(window.dashboard.storage.segments)
    assert segments[Category.INSTALLERS].width() / segments[Category.CODE].width() == pytest.approx(1000)
    assert Category.DOCUMENTS not in segments
    documents = window.dashboard.legend.buttons[Category.DOCUMENTS]
    documents.setFocus()
    QTest.keyClick(documents, Qt.Key.Key_Space)
    assert window.pages.currentIndex() == 1
    assert window.files.category.currentText() == "Documents"
    assert window.files.proxy.rowCount() == 1
    for file in root.iterdir():
        file.write_bytes(b"")
    window.scan_folder(root)
    wait_idle(window)
    window.navigate(0)
    app.processEvents()
    assert not window.dashboard.storage.segments
    assert window.dashboard.zero_note.isVisible()
    assert window.dashboard.summary.metrics[1].value.text() == "0 B"
    window.browse_files("All files")
    assert window.files.proxy.rowCount() == 3


def test_history_distinguishes_skips_restores_and_completed_undo(window, tmp_path, monkeypatch):
    from filepilot.ui.pages.history import operation_label
    root = tmp_path / "history-outcomes"
    root.mkdir()
    (root / "a.txt").write_bytes(b"first")
    (root / "b.txt").write_bytes(b"second")
    window.scan_folder(root)
    wait_idle(window)
    window.create_preview()
    wait_idle(window)
    monkeypatch.setattr(window, "confirm", lambda *args: True)
    window.apply_organization()
    wait_idle(window)
    operation_id = window.store.history()[0]["id"]
    assert {window.history.detail_model.index(row, 2).data() for row in range(2)} == {"Moved"}
    (root / "a.txt").write_bytes(b"occupied original")
    window.undo_operation(operation_id)
    wait_idle(window)
    assert operation_label(window.store.history()[0]["status"]) == "Partial restore"
    assert {window.history.detail_model.index(row, 2).data() for row in range(2)} == {"Restored", "Restore skipped"}
    for row in range(2):
        index = window.history.detail_model.index(row, 2)
        assert index.data(Qt.ItemDataRole.ToolTipRole).split("\n")[0] == index.data()
    assert window.history.undo.isEnabled()
    (root / "a.txt").unlink()
    window.undo_operation(operation_id)
    wait_idle(window)
    assert {window.history.detail_model.index(row, 2).data() for row in range(2)} == {"Restored"}
    assert not window.history.undo.isEnabled() and window.history.undo.text() == "No moves to undo"
    assert not (root / "Documents").exists()


def test_history_labels_preview_conflicts_as_skipped(window, tmp_path, monkeypatch):
    root = tmp_path / "skipped-outcome"
    root.mkdir()
    (root / "Documents").mkdir()
    (root / "Documents" / "a.txt").write_bytes(b"existing user file")
    (root / "a.txt").write_bytes(b"source")
    (root / "b.txt").write_bytes(b"move me")
    window.scan_folder(root)
    wait_idle(window)
    window.create_preview()
    wait_idle(window)
    monkeypatch.setattr(window, "confirm", lambda *args: True)
    window.apply_organization()
    wait_idle(window)
    assert {window.history.detail_model.index(row, 2).data() for row in range(2)} == {"Moved", "Skipped"}
    assert (root / "Documents" / "a.txt").read_bytes() == b"existing user file"


@pytest.mark.parametrize("theme", ("Light", "Dark", "System"))
@pytest.mark.parametrize("selected", (False, True))
def test_history_focus_outline_preserves_card_contents(app, theme, selected):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QStyle, QStyleOptionViewItem
    from filepilot.ui.pages.history import HistoryModel, TimelineDelegate
    from filepilot.ui.theme import apply_theme

    apply_theme(app, theme)
    model = HistoryModel()
    model.set_rows([dict(id=2, created_at="2026-10-04T12:00:00Z", source_root="C:/fixture",
                         item_count=40, remaining=0, restored=40, failures=0, status="undone")])
    delegate = TimelineDelegate()

    def paint(focused):
        image = QImage(720, 120, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        option = QStyleOptionViewItem()
        option.font = app.font()
        option.rect = QRect(10, 10, 700, 100)
        option.state = QStyle.StateFlag.State_Enabled
        if selected:
            option.state |= QStyle.StateFlag.State_Selected
        if focused:
            option.state |= QStyle.StateFlag.State_HasFocus
        painter = QPainter(image)
        delegate.paint(painter, option, model.index(0, 0))
        painter.end()
        return image

    normal, focused = paint(False), paint(True)
    # Focus may add a border, but must preserve all metadata, text and interior fill.
    interior = QRect(15, 15, 690, 90)
    assert focused.copy(interior) == normal.copy(interior)
    assert focused != normal, "The keyboard-focus outline must remain visible"


def test_history_focused_cards_survive_undo_refresh_and_navigation(window, tmp_path, monkeypatch, app):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QWidget
    from filepilot.ui.theme import current_colors

    root = tmp_path / "focused-history"
    root.mkdir()
    for i in range(40):
        (root / f"File {i:02d}.txt").write_bytes(f"Original content {i}".encode())
    monkeypatch.setattr(window, "confirm", lambda *args: True)
    window.scan_folder(root)
    wait_idle(window)
    initial_children = len(window.history.view.findChildren(QWidget))

    def inspect_selected():
        view = window.history.view
        view.setFocus()
        view.scrollTo(view.currentIndex())
        app.processEvents()
        assert view.hasFocus()
        rect = view.visualRect(view.currentIndex())
        image = view.viewport().grab().toImage()
        scale = image.devicePixelRatio()
        assert image.pixelColor(round((rect.right() - 30) * scale), round((rect.top() + 88) * scale)) == QColor(current_colors().tint)

    for _ in range(2):
        window.create_preview()
        wait_idle(window)
        window.apply_organization()
        wait_idle(window)
        operation_id = window.store.history()[0]["id"]
        window.navigate(4)
        inspect_selected()
        window.undo_operation(operation_id)
        wait_idle(window)
        assert window.store.history()[0]["restored"] == 40
        assert not window.history.undo.isEnabled() and window.history.undo.text() == "No moves to undo"
        inspect_selected()
        for _ in range(3):
            window.history.refresh(window.store.history())
            inspect_selected()
        window.navigate(0)
        window.navigate(4)
        inspect_selected()
    for row in range(2):
        window.history.view.setCurrentIndex(window.history.model.index(row, 0))
        inspect_selected()
        assert len(window.history.detail_model.rows) == 40
    assert len(window.history.view.findChildren(QWidget)) == initial_children


def test_clear_history_confirmation_availability_empty_state_and_retained_undo(window, tmp_path, monkeypatch, app):
    root = tmp_path / "clear-ui"
    root.mkdir()
    (root / "Report.txt").write_bytes(b"original")
    assert not window.history.clear.isEnabled()
    assert "No completed history" in window.history.clear.toolTip()
    window.scan_folder(root)
    wait_idle(window)
    monkeypatch.setattr(window, "confirm", lambda *args: True)
    window.create_preview()
    wait_idle(window)
    window.apply_organization()
    wait_idle(window)
    first = window.store.history()[0]["id"]
    assert not window.history.clear.isEnabled()
    window.undo_operation(first)
    wait_idle(window)
    assert window.history.clear.isEnabled()
    confirmations = []
    monkeypatch.setattr(window, "confirm", lambda *args: confirmations.append(args) or False)
    QTest.mouseClick(window.history.clear, Qt.MouseButton.LeftButton)
    assert len(window.store.history()) == 1
    assert confirmations[0][0] == "Clear completed history?" and confirmations[0][2] == "Clear history"
    assert "Your files will not be changed" in confirmations[0][1]
    monkeypatch.setattr(window, "confirm", lambda *args: True)
    window.create_preview()
    wait_idle(window)
    window.apply_organization()
    wait_idle(window)
    active = window.store.history()[0]["id"]
    window.history.select_operation(first)  # Selected record is about to be cleared.
    plan, scan = window.state.plan, window.state.scan
    QTest.mouseClick(window.history.clear, Qt.MouseButton.LeftButton)
    assert not window.history.clear.isEnabled()
    wait_idle(window)
    assert [row["id"] for row in window.history.model.rows] == [active]
    assert window.history.selected_operation() is None
    assert window.history.detail_model.rows == [] and not window.history.copy_root.isEnabled()
    assert window.state.plan is plan and window.state.scan is scan
    window.history.select_operation(active)
    assert window.history.undo.isEnabled() and not window.history.clear.isEnabled()
    window.undo_operation(active)
    wait_idle(window)
    assert window.history.clear.isEnabled()
    QTest.mouseClick(window.history.clear, Qt.MouseButton.LeftButton)
    wait_idle(window)
    assert window.store.history() == [] and window.history.stack.currentWidget() is window.history.empty
    assert not window.history.clear.isEnabled() and not window.history.undo.isEnabled()
    assert window.history.detail_model.rows == [] and window.history.copy_root.value == ""
    assert (root / "Report.txt").read_bytes() == b"original"
    window.navigate(0)
    window.navigate(4)
    assert window.history.stack.currentWidget() is window.history.empty
    assert Store(window.store.path).history() == []


def test_clear_history_database_error_preserves_preview_files_and_history(window, tmp_path, monkeypatch):
    import sqlite3
    root = tmp_path / "clear-error"
    root.mkdir()
    (root / "Report.txt").write_bytes(b"original")
    window.scan_folder(root)
    wait_idle(window)
    monkeypatch.setattr(window, "confirm", lambda *args: True)
    window.create_preview()
    wait_idle(window)
    window.apply_organization()
    wait_idle(window)
    window.undo_operation(window.store.history()[0]["id"])
    wait_idle(window)
    window.create_preview()
    wait_idle(window)
    plan, scan, rows = window.state.plan, window.state.scan, window.store.history()
    def fail():
        raise sqlite3.OperationalError("Injected database error")
    monkeypatch.setattr(window.store, "clear_history", fail)
    window.clear_history()
    wait_idle(window)
    assert window.state.plan is plan and window.state.scan is scan
    assert window.store.history() == rows
    assert (root / "Report.txt").read_bytes() == b"original"
    assert window.history.clear.isEnabled()
    assert window.test_notices[-1][0][0] == "History could not be cleared"
    assert "Your files were not changed" in window.status.text()
