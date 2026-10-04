import hashlib
import sqlite3
from pathlib import Path

import pytest

from filepilot.core.safety import SafetyPolicy
from filepilot.database.store import Store
from filepilot.models.records import Settings
from filepilot.services.organizer import Organizer
from filepilot.services.scanner import Scanner


@pytest.fixture
def history(tmp_path):
    root = tmp_path / "files"
    root.mkdir()
    (root / "Empty user folder").mkdir()
    store = Store(tmp_path / "data/filepilot.sqlite3")
    policy = SafetyPolicy((store.path.parent,))
    return root, store, Organizer(policy, store), Scanner(policy)


def apply(history, name="Report.txt"):
    root, store, organizer, scanner = history
    (root / name).write_bytes(name.encode())
    result = organizer.apply(organizer.plan(scanner.scan(root), Settings()))
    assert result.succeeded == 1
    return result.operation_id


def snapshot(root):
    return {str(p.relative_to(root)): ("directory", p.stat().st_ino) if p.is_dir() else
            ("file", p.stat().st_ino, p.stat().st_size, p.stat().st_mtime_ns,
             hashlib.sha256(p.read_bytes()).hexdigest()) for p in root.rglob("*")}


def test_undone_history_clears_without_filesystem_calls_and_stays_cleared_after_reopen(history, monkeypatch):
    root, store, organizer, scanner = history
    operation_id = apply(history)
    (root / "Documents" / "Unrelated.txt").write_bytes(b"keep unrelated contents")
    organizer.undo(operation_id)
    before = snapshot(root)
    preferences = store.load_settings()
    assert store.history()[0]["clearable"]

    def forbidden(*args, **kwargs):
        raise AssertionError("Clear history must not call a filesystem mutator")

    with monkeypatch.context() as guard:
        for method in ("mkdir", "rmdir", "unlink", "rename", "replace", "touch", "write_bytes", "write_text"):
            guard.setattr(Path, method, forbidden)
        assert store.clear_history() == 1
    assert snapshot(root) == before
    assert (root / "Documents" / "Unrelated.txt").read_bytes() == b"keep unrelated contents"
    assert (root / "Empty user folder").is_dir()
    assert store.history() == [] and store.items(operation_id) == [] and store.directories(operation_id) == []
    reopened = Store(store.path)
    assert reopened.history() == [] and reopened.load_settings() == preferences
    with reopened.connection() as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_multiple_undone_records_clear(history):
    root, store, organizer, scanner = history
    for name in ("First.txt", "Second.txt", "Third.txt"):
        operation_id = apply(history, name)
        organizer.undo(operation_id)
        (root / name).unlink()  # Only test setup between independent operations.
    before = snapshot(root)
    assert store.clear_history() == 3 and store.history() == []
    assert snapshot(root) == before


def test_actionable_record_is_preserved_and_still_undoes(history):
    root, store, organizer, scanner = history
    operation_id = apply(history)
    before, rows, items, directories = snapshot(root), store.history(), store.items(operation_id), store.directories(operation_id)
    assert not rows[0]["clearable"]
    assert store.clear_history() == 0
    assert store.history() == rows and store.items(operation_id) == items and store.directories(operation_id) == directories
    assert snapshot(root) == before
    assert organizer.undo(operation_id).succeeded == 1


def test_mixed_history_removes_only_terminal_records_and_preserves_shared_provenance(history):
    root, store, organizer, scanner = history
    old = apply(history, "First.txt")
    (root / "Documents" / "Unrelated.txt").write_bytes(b"keep category")
    organizer.undo(old)
    (root / "First.txt").unlink()
    active = apply(history, "Second.txt")
    items, directories, before = store.items(active), store.directories(active), snapshot(root)
    assert store.clear_history() == 1
    assert [row["id"] for row in store.history()] == [active]
    assert store.items(active) == items and store.directories(active) == directories
    assert snapshot(root) == before
    assert organizer.undo(active).succeeded == 1
    assert (root / "Documents" / "Unrelated.txt").is_file()


def test_partial_retryable_undo_is_preserved(history):
    root, store, organizer, scanner = history
    operation_id = apply(history)
    (root / "Report.txt").write_bytes(b"occupied original")
    result = organizer.undo(operation_id)
    assert result.status == "partial_undo"
    before, rows = snapshot(root), store.history()
    assert not rows[0]["clearable"] and store.clear_history() == 0
    assert store.history() == rows and snapshot(root) == before
    (root / "Report.txt").unlink()
    assert organizer.undo(operation_id).succeeded == 1
    assert store.history()[0]["clearable"]


@pytest.mark.parametrize("state", ("queued", "moving", "moved", "undo_failed", "restoring", "future_unknown"))
def test_terminal_status_does_not_allow_actionable_or_unknown_item_to_clear(history, state):
    root, store, organizer, scanner = history
    (root / "Report.txt").write_bytes(b"journal fixture")
    record = scanner.scan(root).files[0]
    operation_id = store.begin_operation(root, [(record, root / "Documents/Report.txt", "")])
    store.update_item(store.items(operation_id)[0]["id"], state)
    store.set_status(operation_id, "undone")
    assert not store.history()[0]["clearable"]
    assert store.clear_history() == 0 and store.operation(operation_id)["status"] == "undone"


@pytest.mark.parametrize("status", ("running", "undoing", "interrupted", "partial_undo", "future_unknown"))
def test_unresolved_or_unknown_operation_is_preserved_even_without_items(history, status):
    root, store, organizer, scanner = history
    operation_id = store.begin_operation(root, [])
    store.set_status(operation_id, status)
    assert not store.history()[0]["clearable"] and store.clear_history() == 0


@pytest.mark.parametrize("status", ("completed", "partial", "failed", "cancelled", "undone"))
def test_terminal_record_with_only_skipped_items_is_clearable(history, status):
    root, store, organizer, scanner = history
    (root / "Report.txt").write_bytes(b"never moved")
    record = scanner.scan(root).files[0]
    operation_id = store.begin_operation(root, [(record, root / "Documents/Report.txt", "Destination exists")])
    store.set_status(operation_id, status)
    before = snapshot(root)
    assert store.history()[0]["clearable"] and store.clear_history() == 1
    assert snapshot(root) == before


def test_database_failure_rolls_back_entire_clear_and_never_changes_files(history):
    root, store, organizer, scanner = history
    operation_id = apply(history)
    organizer.undo(operation_id)
    before = snapshot(root)
    rows, items, directories = store.history(), store.items(operation_id), store.directories(operation_id)
    with store.connection() as connection:
        connection.execute("""CREATE TRIGGER reject_clear BEFORE DELETE ON operations
                              BEGIN SELECT RAISE(ABORT, 'Injected clear failure'); END""")
    with pytest.raises(sqlite3.DatabaseError, match="Injected clear failure"):
        store.clear_history()
    assert store.history() == rows and store.items(operation_id) == items and store.directories(operation_id) == directories
    assert snapshot(root) == before
    with store.connection() as connection:
        connection.execute("DROP TRIGGER reject_clear")
    assert store.clear_history() == 1


def test_clear_rechecks_actual_item_state_instead_of_stale_ui_eligibility(history):
    root, store, organizer, scanner = history
    operation_id = apply(history)
    organizer.undo(operation_id)
    assert store.history()[0]["clearable"]
    store.update_item(store.items(operation_id)[0]["id"], "restoring")
    assert store.clear_history() == 0 and not store.history()[0]["clearable"]
