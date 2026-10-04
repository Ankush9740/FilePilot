import os
import sqlite3
from pathlib import Path
from threading import Event

import pytest

from filepilot.core.safety import SafetyError, SafetyPolicy, hash_file, move_no_replace
from filepilot.database.store import Store
from filepilot.models.records import Settings
from filepilot.services.organizer import Organizer, validate_settings
from filepilot.services.scanner import Scanner


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "files"
    root.mkdir()
    store = Store(tmp_path / "data" / "filepilot.sqlite3")
    policy = SafetyPolicy((store.path.parent,))
    return root, store, Organizer(policy, store), Scanner(policy)


def test_preview_is_read_only_and_avoids_repeated_categories(setup):
    root, store, organizer, scanner = setup
    (root / "report.pdf").write_bytes(b"report")
    nested = root / "Documents" / "nested"
    nested.mkdir(parents=True)
    (nested / "already.pdf").write_bytes(b"already")
    plan = organizer.plan(scanner.scan(root), Settings())
    assert len(plan.items) == 1 and plan.already_organized == 1
    assert plan.items[0].destination == root / "Documents" / "report.pdf"
    assert (root / "report.pdf").exists()
    assert not (root / "Documents" / "report.pdf").exists()
    assert not store.history()


def test_existing_and_planned_collisions_are_skipped(setup):
    root, store, organizer, scanner = setup
    (root / "Documents").mkdir()
    (root / "Documents" / "report.pdf").write_bytes(b"original destination")
    (root / "report.pdf").write_bytes(b"source")
    for folder in ("one", "two"):
        (root / folder).mkdir()
        (root / folder / "same.txt").write_text(folder)
    plan = organizer.plan(scanner.scan(root), Settings())
    assert len(plan.items) == 3
    assert len(plan.actionable) == 1
    result = organizer.apply(plan)
    assert result.succeeded == 1 and result.failed == 2 and result.status == "partial"
    assert (root / "Documents" / "report.pdf").read_bytes() == b"original destination"
    assert (root / "report.pdf").read_bytes() == b"source"
    assert store.history()[0]["failures"] == 2


def test_apply_history_undo_and_persistence(setup):
    root, store, organizer, scanner = setup
    source = root / "hello.txt"
    source.write_bytes(b"precious content")
    plan = organizer.plan(scanner.scan(root), Settings())
    result = organizer.apply(plan)
    destination = root / "Documents" / "hello.txt"
    assert result.succeeded == 1 and result.status == "completed"
    assert not source.exists() and destination.read_bytes() == b"precious content"
    reopened = Store(store.path)
    assert reopened.history()[0]["remaining"] == 1
    item = reopened.items(result.operation_id)[0]
    assert item["state"] == "moved" and len(item["digest"]) == 64
    undone = Organizer(organizer.policy, reopened).undo(result.operation_id)
    assert undone.status == "undone" and undone.succeeded == 1
    assert source.read_bytes() == b"precious content" and not destination.exists()
    assert reopened.history()[0]["remaining"] == 0


def test_collision_created_after_preview_is_not_overwritten(setup):
    root, store, organizer, scanner = setup
    source = root / "report.txt"
    source.write_text("source")
    plan = organizer.plan(scanner.scan(root), Settings())
    target = plan.items[0].destination
    target.parent.mkdir()
    target.write_text("existing")
    result = organizer.apply(plan)
    assert result.status == "failed" and result.failed == 1
    assert target.read_text() == "existing" and source.read_text() == "source"


def test_atomic_move_primitive_refuses_overwrite(tmp_path):
    first, second = tmp_path / "first.txt", tmp_path / "second.txt"
    first.write_text("first")
    second.write_text("second")
    with pytest.raises(OSError):
        move_no_replace(first, second)
    assert first.read_text() == "first" and second.read_text() == "second"


def test_changed_and_missing_sources_fail_individually(setup):
    root, store, organizer, scanner = setup
    for name in ("changed.txt", "missing.txt", "okay.txt"):
        (root / name).write_text("original")
    plan = organizer.plan(scanner.scan(root), Settings())
    (root / "changed.txt").write_text("now changed")
    (root / "missing.txt").unlink()
    result = organizer.apply(plan)
    assert result.succeeded == 1 and result.failed == 2
    assert (root / "changed.txt").read_text() == "now changed"
    assert (root / "Documents" / "okay.txt").exists()


def test_permission_failure_is_recorded_without_success(setup, monkeypatch):
    root, store, organizer, scanner = setup
    source = root / "locked.txt"
    source.write_text("original")
    plan = organizer.plan(scanner.scan(root), Settings())
    def denied(*args):
        raise PermissionError("test file is locked")
    monkeypatch.setattr("filepilot.services.organizer.move_no_replace", denied)
    result = organizer.apply(plan)
    assert result.succeeded == 0 and result.status == "failed"
    assert source.exists()
    assert "locked" in store.items(result.operation_id)[0]["error"]


def test_partial_undo_collision_then_retry(setup):
    root, store, organizer, scanner = setup
    for name in ("a.txt", "b.txt"):
        (root / name).write_text(name)
    moved = organizer.apply(organizer.plan(scanner.scan(root), Settings()))
    (root / "a.txt").write_text("new file must survive")
    result = organizer.undo(moved.operation_id)
    assert result.succeeded == 1 and result.failed == 1 and result.status == "partial_undo"
    assert (root / "a.txt").read_text() == "new file must survive"
    assert (root / "Documents" / "a.txt").read_text() == "a.txt"
    assert store.history()[0]["remaining"] == 1
    (root / "a.txt").unlink()  # Test-created obstruction only.
    retry = organizer.undo(moved.operation_id)
    assert retry.succeeded == 1 and retry.status == "undone"


def test_undo_refuses_content_edit_even_if_size_and_mtime_restored(setup):
    root, store, organizer, scanner = setup
    (root / "file.txt").write_bytes(b"original")
    result = organizer.apply(organizer.plan(scanner.scan(root), Settings()))
    destination = root / "Documents" / "file.txt"
    before = destination.stat()
    destination.write_bytes(b"modified")
    os.utime(destination, ns=(before.st_atime_ns, before.st_mtime_ns))
    undo = organizer.undo(result.operation_id)
    assert undo.failed == 1 and undo.status == "partial_undo"
    assert destination.read_bytes() == b"modified"
    assert not (root / "file.txt").exists()


def test_undo_missing_destination(setup):
    root, store, organizer, scanner = setup
    (root / "file.txt").write_text("content")
    result = organizer.apply(organizer.plan(scanner.scan(root), Settings()))
    (root / "Documents" / "file.txt").unlink()
    undo = organizer.undo(result.operation_id)
    assert undo.failed == 1 and undo.status == "partial_undo"
    assert store.items(result.operation_id)[0]["state"] == "undo_failed"


def test_cancellation_is_persisted(setup):
    root, store, organizer, scanner = setup
    (root / "file.txt").write_text("content")
    plan = organizer.plan(scanner.scan(root), Settings())
    cancel = Event()
    cancel.set()
    result = organizer.apply(plan, cancel)
    assert result.status == "cancelled" and result.succeeded == 0
    assert (root / "file.txt").exists()
    assert store.items(result.operation_id)[0]["state"] == "failed"


def test_cancel_after_first_move_then_undo_preserves_unmoved_files_and_cleans_folder(setup):
    root, store, organizer, scanner = setup
    for name in ("one.txt", "two.txt", "three.txt"):
        (root / name).write_bytes(name.encode())
    plan = organizer.plan(scanner.scan(root), Settings())
    cancel = Event()
    applied = organizer.apply(plan, cancel, progress=lambda *args: cancel.set())
    assert (applied.succeeded, applied.failed, applied.status) == (1, 2, "cancelled")
    restored = organizer.undo(applied.operation_id)
    assert (restored.succeeded, restored.failed, restored.status) == (1, 0, "undone")
    assert not (root / "Documents").exists()
    assert all((root / name).read_bytes() == name.encode() for name in ("one.txt", "two.txt", "three.txt"))
    history = store.history()[0]
    assert (history["restored"], history["remaining"], history["failures"]) == (1, 0, 2)


@pytest.mark.parametrize("name", ["../escape", "CON", "NUL.txt", "x/y", "x\\y", "bad.", " leading", "", "..", "a:b"])
def test_destination_folder_validation(name):
    settings = Settings()
    settings.destinations["Documents"] = name
    with pytest.raises(ValueError):
        validate_settings(settings)


def test_destination_case_insensitive_duplicates_rejected():
    settings = Settings()
    settings.destinations["Documents"] = "images"
    with pytest.raises(ValueError):
        validate_settings(settings)


def test_custom_category_destinations_and_settings_persist(setup):
    root, store, organizer, scanner = setup
    settings = Settings(theme="Dark", old_days=90, large_mb=500)
    settings.destinations["Documents"] = "Reading"
    store.save_settings(settings)
    assert Store(store.path).load_settings() == settings
    (root / "book.pdf").write_text("book")
    plan = organizer.plan(scanner.scan(root), settings)
    assert plan.items[0].destination == root / "Reading" / "book.pdf"


def test_database_initialization_and_version_guard(tmp_path):
    path = tmp_path / "data" / "filepilot.sqlite3"
    store = Store(path)
    assert not store.history() and store.load_settings() == Settings()
    with store.connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        connection.execute("PRAGMA user_version = 999")
    with pytest.raises(RuntimeError):
        Store(path)


def test_database_failure_before_intent_cannot_move_files(setup, monkeypatch):
    root, store, organizer, scanner = setup
    (root / "file.txt").write_text("original")
    plan = organizer.plan(scanner.scan(root), Settings())
    def failure(*args, **kwargs):
        raise sqlite3.OperationalError("test disk full")
    monkeypatch.setattr(store, "update_item", failure)
    with pytest.raises(sqlite3.OperationalError):
        organizer.apply(plan)
    assert (root / "file.txt").read_text() == "original"
    assert not (root / "Documents" / "file.txt").exists()


def test_recovery_after_move_before_completion_record(setup, monkeypatch):
    root, store, organizer, scanner = setup
    (root / "file.txt").write_text("original")
    plan = organizer.plan(scanner.scan(root), Settings())
    original_update = store.update_item
    def fail_after_move(item_id, state, *args, **kwargs):
        if state == "moved":
            raise sqlite3.OperationalError("test process interruption")
        return original_update(item_id, state, *args, **kwargs)
    monkeypatch.setattr(store, "update_item", fail_after_move)
    with pytest.raises(sqlite3.OperationalError):
        organizer.apply(plan)
    assert not (root / "file.txt").exists()
    monkeypatch.setattr(store, "update_item", original_update)
    assert organizer.recover() == []
    op = store.history()[0]
    assert op["status"] == "completed" and op["remaining"] == 1
    assert organizer.undo(op["id"]).succeeded == 1
    assert (root / "file.txt").read_text() == "original"


def test_unsafe_paths_cannot_be_used_for_operations(setup):
    root, store, organizer, scanner = setup
    from filepilot.models.records import OrganizationPlan, PlanItem
    (root / "file.txt").write_text("original")
    file = scanner.scan(root).files[0]
    plan = OrganizationPlan(root, [PlanItem(file, root.parent / "escape.txt")])
    result = organizer.apply(plan)
    assert result.failed == 1 and (root / "file.txt").exists()
    assert not (root.parent / "escape.txt").exists()


def test_parent_traversal_destination_cannot_escape_root(setup):
    root, store, organizer, scanner = setup
    from filepilot.models.records import OrganizationPlan, PlanItem
    (root / "file.txt").write_text("original")
    file = scanner.scan(root).files[0]
    plan = OrganizationPlan(root, [PlanItem(file, root / ".." / "escape.txt")])
    result = organizer.apply(plan)
    assert result.failed == 1 and result.succeeded == 0
    assert (root / "file.txt").read_text() == "original"
    assert not (root.parent / "escape.txt").exists()


def test_protected_destination_cannot_be_written(setup):
    root, store, organizer, scanner = setup
    protected = root / "Documents"
    protected.mkdir()
    organizer.policy = SafetyPolicy((protected, store.path.parent))
    (root / "file.txt").write_text("original")
    plan = organizer.plan(scanner.scan(root), Settings())
    assert plan.items[0].conflict and not plan.actionable


def test_category_path_is_file_is_a_conflict(setup):
    root, store, organizer, scanner = setup
    (root / "Documents").write_text("not a directory")
    (root / "file.txt").write_text("document")
    plan = organizer.plan(scanner.scan(root), Settings())
    item = next(item for item in plan.items if item.file.name == "file.txt")
    assert item.conflict


def test_collision_racing_the_move_primitive_is_not_overwritten(setup, monkeypatch):
    root, store, organizer, scanner = setup
    (root / "file.txt").write_text("source")
    plan = organizer.plan(scanner.scan(root), Settings())
    def raced(source, destination):
        destination.write_text("race winner")
        move_no_replace(source, destination)
    monkeypatch.setattr("filepilot.services.organizer.move_no_replace", raced)
    result = organizer.apply(plan)
    assert result.succeeded == 0 and result.failed == 1
    assert (root / "file.txt").read_text() == "source"
    assert (root / "Documents" / "file.txt").read_text() == "race winner"


def test_recovery_after_restore_before_completion_record(setup, monkeypatch):
    root, store, organizer, scanner = setup
    (root / "file.txt").write_text("original")
    moved = organizer.apply(organizer.plan(scanner.scan(root), Settings()))
    original_update = store.update_item
    def fail_after_restore(item_id, state, *args, **kwargs):
        if state == "restored":
            raise sqlite3.OperationalError("test process interruption")
        return original_update(item_id, state, *args, **kwargs)
    monkeypatch.setattr(store, "update_item", fail_after_restore)
    with pytest.raises(sqlite3.OperationalError):
        organizer.undo(moved.operation_id)
    assert (root / "file.txt").read_text() == "original"
    monkeypatch.setattr(store, "update_item", original_update)
    assert organizer.recover() == []
    assert store.history()[0]["status"] == "undone"


def test_ambiguous_recovery_is_left_for_review(setup):
    root, store, organizer, scanner = setup
    (root / "file.txt").write_text("original")
    file = scanner.scan(root).files[0]
    destination = root / "Documents" / "file.txt"
    destination.parent.mkdir()
    destination.write_text("also present")
    operation_id = store.begin_operation(root, [(file, destination, "")])
    item_id = store.items(operation_id)[0]["id"]
    store.update_item(item_id, "moving", digest=hash_file(file))
    issues = organizer.recover()
    assert len(issues) == 1
    assert store.operation(operation_id)["status"] == "interrupted"
    assert store.items(operation_id)[0]["state"] == "moving"
    assert (root / "file.txt").read_text() == "original"
    assert destination.read_text() == "also present"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction safety")
def test_junction_destination_added_after_preview_is_refused(setup):
    import subprocess
    root, store, organizer, scanner = setup
    (root / "file.txt").write_text("original")
    plan = organizer.plan(scanner.scan(root), Settings())
    outside = root.parent / "outside"
    outside.mkdir()
    junction = root / "Documents"
    created = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(junction), str(outside)],
                             capture_output=True, text=True)
    assert created.returncode == 0, created.stderr
    try:
        result = organizer.apply(plan)
        assert result.succeeded == 0 and result.failed == 1
        assert not list(outside.iterdir())
        assert (root / "file.txt").read_text() == "original"
    finally:
        os.rmdir(junction)
