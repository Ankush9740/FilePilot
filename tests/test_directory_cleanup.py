import os
import sqlite3
from pathlib import Path
from threading import Event

import pytest

from filepilot.core.safety import SafetyPolicy
from filepilot.database.store import Store
from filepilot.models.records import Settings
from filepilot.services.organizer import Organizer
from filepilot.services.scanner import Scanner


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "files"
    root.mkdir()
    store = Store(tmp_path / "data" / "filepilot.sqlite3")
    policy = SafetyPolicy((store.path.parent,))
    return root, store, Organizer(policy, store), Scanner(policy)


def move_document(setup, name="report.txt"):
    root, store, organizer, scanner = setup
    source = root / name
    source.write_bytes(name.encode())
    result = organizer.apply(organizer.plan(scanner.scan(root), Settings()))
    assert result.succeeded == 1
    return result.operation_id, source, root / "Documents"


def test_created_category_is_removed_after_persisted_undo(setup):
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    tracked = store.directories(operation_id)[0]
    assert tracked["state"] == "created" and int(tracked["inode"]) == directory.stat().st_ino
    reopened = Store(store.path)
    result = Organizer(organizer.policy, reopened).undo(operation_id)
    assert source.read_bytes() == b"report.txt" and not directory.exists()
    assert result.succeeded == 1 and result.failed == 0 and result.status == "undone"
    assert reopened.directories(operation_id)[0]["state"] == "removed"
    history = reopened.history()[0]
    assert (history["item_count"], history["restored"], history["remaining"]) == (1, 1, 0)


def test_preexisting_empty_category_remains(setup):
    root, store, organizer, scanner = setup
    (root / "Documents").mkdir()
    operation_id, source, directory = move_document(setup)
    assert store.directories(operation_id)[0]["state"] == "existing"
    assert organizer.undo(operation_id).succeeded == 1
    assert directory.is_dir() and not list(directory.iterdir()) and source.exists()


def test_folder_created_by_another_process_during_mkdir_is_not_owned(setup, monkeypatch):
    root, store, organizer, scanner = setup
    original_mkdir = Path.mkdir
    def raced(directory, *args, **kwargs):
        if directory == root / "Documents" and not directory.exists():
            original_mkdir(directory)
            raise FileExistsError("Another process won directory creation")
        return original_mkdir(directory, *args, **kwargs)
    monkeypatch.setattr(Path, "mkdir", raced)
    operation_id, source, directory = move_document(setup)
    assert store.directories(operation_id)[0]["state"] == "existing"
    organizer.undo(operation_id)
    assert directory.is_dir() and source.exists()


@pytest.mark.parametrize("entry", ["unrelated.txt", ".hidden", "empty-subfolder"])
def test_unrelated_contents_are_never_deleted(setup, entry):
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    unrelated = directory / entry
    if entry == "empty-subfolder":
        unrelated.mkdir()
    else:
        unrelated.write_bytes(b"user data")
    result = organizer.undo(operation_id)
    assert result.succeeded == 1 and result.failed == 0 and result.status == "undone"
    assert source.exists() and directory.is_dir() and unrelated.exists()
    if unrelated.is_file():
        assert unrelated.read_bytes() == b"user data"
    assert store.directories(operation_id)[0]["cleanup_error"]
    assert store.history()[0]["restored"] == 1


@pytest.mark.parametrize("obstruction", ["occupied", "modified", "missing", "cancelled"])
def test_partial_restore_retains_created_directory(setup, obstruction):
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    destination = directory / source.name
    cancel = Event()
    if obstruction == "occupied":
        source.write_bytes(b"new user file")
    elif obstruction == "modified":
        destination.write_bytes(b"changed content")
    elif obstruction == "missing":
        destination.unlink()
    else:
        cancel.set()
    result = organizer.undo(operation_id, cancel)
    assert result.status == "partial_undo" and result.failed == 1
    assert directory.is_dir() and store.history()[0]["remaining"] == 1
    assert store.directories(operation_id)[0]["state"] == "created"


def test_partial_restore_then_retry_cleans_folder(setup):
    root, store, organizer, scanner = setup
    for name in ("a.txt", "b.txt"):
        (root / name).write_bytes(name.encode())
    moved = organizer.apply(organizer.plan(scanner.scan(root), Settings()))
    (root / "a.txt").write_bytes(b"temporary obstruction")
    partial = organizer.undo(moved.operation_id)
    assert partial.succeeded == 1 and partial.failed == 1 and (root / "Documents").is_dir()
    (root / "a.txt").unlink()
    retry = organizer.undo(moved.operation_id)
    assert retry.succeeded == 1 and retry.failed == 0 and not (root / "Documents").exists()
    assert store.history()[0]["restored"] == 2 and store.history()[0]["remaining"] == 0


def test_shared_category_is_retained_for_another_operation(setup):
    root, store, organizer, scanner = setup
    first_id, first_source, directory = move_document(setup, "first.txt")
    second_id, second_source, _ = move_document(setup, "second.txt")
    assert store.directories(second_id)[0]["state"] == "existing"
    first_undo = organizer.undo(first_id)
    assert first_undo.succeeded == 1 and directory.is_dir()
    assert (directory / "second.txt").read_bytes() == b"second.txt"
    organizer.undo(second_id)
    # The second operation never owned the directory and cannot dispose of it.
    assert directory.is_dir() and first_source.exists() and second_source.exists()
    assert organizer.undo(first_id).status == "undone"
    assert not directory.exists()


def test_empty_shared_category_with_unresolved_item_is_retained(setup):
    root, store, organizer, scanner = setup
    first_id, source, directory = move_document(setup, "first.txt")
    second_id, _, _ = move_document(setup, "second.txt")
    (directory / "second.txt").unlink()
    result = organizer.undo(first_id)
    assert result.succeeded == 1 and source.exists() and directory.is_dir()
    assert not list(directory.iterdir())
    assert store.history()[0]["id"] == second_id and store.history()[0]["remaining"] == 1
    assert "Another operation" in store.directories(first_id)[0]["cleanup_error"]


def test_other_operation_original_path_reference_also_prevents_cleanup(setup):
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    record = scanner.scan(root).files[0]
    pending_id = store.begin_operation(root, [(record, root / "Reading" / record.name, "")])
    assert pending_id != operation_id
    result = organizer.undo(operation_id)
    assert result.succeeded == 1 and source.exists() and directory.is_dir()
    assert not list(directory.iterdir())


def test_replaced_directory_identity_is_not_removed(setup):
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    original_directory = root / "original-directory-kept"
    def replace_after_restore(*args):
        directory.rename(original_directory)
        directory.mkdir()
    result = organizer.undo(operation_id, progress=replace_after_restore)
    assert result.succeeded == 1 and result.failed == 0 and source.exists()
    assert directory.is_dir() and original_directory.is_dir()
    assert "identity" in store.directories(operation_id)[0]["cleanup_error"]


def test_identity_is_checked_after_cross_operation_reference_query(setup, monkeypatch):
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    def replace_during_query(*args):
        directory.rename(root / "original-directory-kept")
        directory.mkdir()
        return False
    monkeypatch.setattr(store, "directory_in_use", replace_during_query)
    result = organizer.undo(operation_id)
    assert result.succeeded == 1 and source.exists() and directory.is_dir()
    assert "identity" in store.directories(operation_id)[0]["cleanup_error"]


def test_cleanup_lock_serializes_new_operation_intents(setup):
    from threading import Thread
    root, store, organizer, scanner = setup
    (root / "report.txt").write_bytes(b"content")
    record = scanner.scan(root).files[0]
    started, finished = Event(), Event()
    errors = []
    def publish_intent():
        started.set()
        try:
            store.begin_operation(root, [(record, root / "Documents" / record.name, "")])
        except Exception as error:
            errors.append(error)
        finally:
            finished.set()
    thread = Thread(target=publish_intent)
    with store.directory_cleanup_lock():
        thread.start()
        assert started.wait(2)
        assert not finished.wait(.1), "A new intent bypassed the cleanup writer lock"
    thread.join(3)
    assert finished.is_set() and not errors
    assert len(store.history()) == 1


def test_cleanup_permission_failure_does_not_change_file_results(setup, monkeypatch):
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    original_rmdir = Path.rmdir
    def denied(path):
        if path == directory:
            raise PermissionError("Directory in use by another application")
        return original_rmdir(path)
    monkeypatch.setattr(Path, "rmdir", denied)
    result = organizer.undo(operation_id)
    assert (result.succeeded, result.failed, result.status) == (1, 0, "undone")
    assert source.exists() and directory.is_dir() and result.issues
    assert store.history()[0]["remaining"] == 0
    monkeypatch.setattr(Path, "rmdir", original_rmdir)
    retry = organizer.undo(operation_id)
    assert retry.succeeded == 0 and retry.failed == 0 and not directory.exists()


def test_cleanup_database_failure_does_not_rollback_restoration(setup, monkeypatch):
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    def unavailable(*args):
        raise sqlite3.OperationalError("Cleanup journal unavailable")
    monkeypatch.setattr(store, "directories", unavailable)
    result = organizer.undo(operation_id)
    assert (result.succeeded, result.failed, result.status) == (1, 0, "undone")
    assert source.exists() and directory.is_dir() and result.issues
    assert store.history()[0]["remaining"] == 0


def test_cleanup_journal_failure_after_rmdir_keeps_restored_counts(setup, monkeypatch):
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    def unavailable(*args):
        raise sqlite3.OperationalError("Cleanup completion could not be committed")
    monkeypatch.setattr(store, "directory_cleanup", unavailable)
    result = organizer.undo(operation_id)
    assert (result.succeeded, result.failed, result.status) == (1, 0, "undone")
    assert source.exists() and not directory.exists() and result.issues
    assert store.history()[0]["remaining"] == 0 and store.history()[0]["restored"] == 1


def test_file_arriving_at_rmdir_is_never_deleted(setup, monkeypatch):
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    original_rmdir = Path.rmdir
    def raced(path):
        if path == directory:
            (path / "new-file.txt").write_bytes(b"must survive")
        return original_rmdir(path)
    monkeypatch.setattr(Path, "rmdir", raced)
    result = organizer.undo(operation_id)
    assert result.succeeded == 1 and source.exists()
    assert (directory / "new-file.txt").read_bytes() == b"must survive"


def test_cancellation_after_last_restore_retains_folder_without_changing_counts(setup):
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    cancel = Event()
    result = organizer.undo(operation_id, cancel, progress=lambda *args: cancel.set())
    assert (result.succeeded, result.failed, result.status) == (1, 0, "undone")
    assert source.exists() and directory.is_dir() and store.history()[0]["remaining"] == 0


def test_unverifiable_recorded_identity_is_retained(setup):
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    with store.connection() as connection:
        connection.execute("UPDATE operation_directories SET inode='0' WHERE operation_id=?", (operation_id,))
    result = organizer.undo(operation_id)
    assert result.succeeded == 1 and source.exists() and directory.is_dir()


def test_missing_created_directory_is_recorded_without_touching_replacement_paths(setup):
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    result = organizer.undo(operation_id, progress=lambda *args: directory.rmdir())
    assert result.succeeded == 1 and source.exists() and not directory.exists()
    assert store.directories(operation_id)[0]["state"] == "missing"


def test_creation_journal_failure_prevents_mkdir_and_move(setup, monkeypatch):
    root, store, organizer, scanner = setup
    (root / "report.txt").write_bytes(b"original")
    plan = organizer.plan(scanner.scan(root), Settings())
    def unavailable(*args):
        raise sqlite3.OperationalError("Directory intent could not be committed")
    monkeypatch.setattr(store, "directory_intent", unavailable)
    with pytest.raises(sqlite3.OperationalError):
        organizer.apply(plan)
    assert (root / "report.txt").read_bytes() == b"original"
    assert not (root / "Documents").exists()


def test_interruption_before_directory_ownership_confirmation_retains_folder(setup, monkeypatch):
    root, store, organizer, scanner = setup
    (root / "report.txt").write_bytes(b"original")
    plan = organizer.plan(scanner.scan(root), Settings())
    def interrupted(*args):
        raise sqlite3.OperationalError("Interrupted after mkdir")
    monkeypatch.setattr(store, "directory_created", interrupted)
    with pytest.raises(sqlite3.OperationalError):
        organizer.apply(plan)
    operation_id = store.history()[0]["id"]
    assert store.directories(operation_id)[0]["state"] == "creating"
    assert organizer.recover() == []
    organizer.undo(operation_id)
    assert (root / "Documents").is_dir() and (root / "report.txt").read_bytes() == b"original"


@pytest.mark.parametrize("invalid", ["root", "outside", "traversal"])
def test_cleanup_revalidates_journal_path_confinement(setup, invalid):
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    outside = root.parent / "unrelated"
    outside.mkdir()
    recorded = root if invalid == "root" else outside if invalid == "outside" else root / "Documents" / ".." / "Documents"
    with store.connection() as connection:
        connection.execute("UPDATE operation_directories SET path=? WHERE operation_id=?", (str(recorded), operation_id))
    result = organizer.undo(operation_id)
    assert result.succeeded == 1 and source.exists()
    assert directory.is_dir() and root.is_dir() and outside.is_dir()


def test_newly_protected_category_is_retained(setup):
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    def protect_after_restore(*args):
        organizer.policy = SafetyPolicy((directory, store.path.parent))
    result = organizer.undo(operation_id, progress=protect_after_restore)
    assert result.succeeded == 1 and source.exists() and directory.is_dir()
    assert store.directories(operation_id)[0]["cleanup_error"]


@pytest.mark.skipif(os.name != "nt", reason="Windows junction safety")
def test_category_replaced_with_junction_is_not_removed(setup):
    import subprocess
    root, store, organizer, scanner = setup
    operation_id, source, directory = move_document(setup)
    outside = root.parent / "junction-target"
    outside.mkdir()
    (outside / "user-file.txt").write_bytes(b"unrelated data")
    def replace_after_restore(*args):
        directory.rename(root / "original-directory-kept")
        created = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(directory), str(outside)],
                                 capture_output=True, text=True)
        assert created.returncode == 0, created.stderr
    try:
        result = organizer.undo(operation_id, progress=replace_after_restore)
        assert result.succeeded == 1 and source.exists() and directory.is_junction()
        assert (outside / "user-file.txt").read_bytes() == b"unrelated data"
    finally:
        if directory.is_junction():
            os.rmdir(directory)  # Remove only this known fixture junction, never its contents.
