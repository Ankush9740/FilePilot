import sqlite3

import pytest

from filepilot.core.safety import SafetyPolicy
from filepilot.database.store import Store
from filepilot.models.records import Settings
from filepilot.services.organizer import Organizer
from filepilot.services.scanner import Scanner


def legacy_database(tmp_path):
    """Remove only the additive v2 table to reproduce the actual unchanged v1 schema."""
    store = Store(tmp_path / "data" / "filepilot.sqlite3")
    root = tmp_path / "files"
    root.mkdir()
    (root / "report.txt").write_bytes(b"legacy user document")
    policy = SafetyPolicy((store.path.parent,))
    organizer = Organizer(policy, store)
    settings = Settings(theme="Dark", old_days=72, large_mb=95)
    store.save_settings(settings)
    moved = organizer.apply(organizer.plan(Scanner(policy).scan(root), settings))
    history, items = store.history(), store.items(moved.operation_id)
    with store.connection() as connection:
        connection.execute("DROP TABLE operation_directories")
        connection.execute("PRAGMA user_version = 1")
    return store.path, root, policy, settings, history, items


def test_v1_migration_preserves_history_items_settings_and_legacy_folders(tmp_path):
    path, root, policy, settings, history, items = legacy_database(tmp_path)
    migrated = Store(path)
    assert migrated.history() == history
    assert migrated.items(history[0]["id"]) == items
    assert migrated.load_settings() == settings
    assert migrated.directories(history[0]["id"]) == []
    with migrated.connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    result = Organizer(policy, migrated).undo(history[0]["id"])
    assert (result.succeeded, result.failed, result.status) == (1, 0, "undone")
    assert (root / "report.txt").read_bytes() == b"legacy user document"
    assert (root / "Documents").is_dir()  # No inferred ownership for legacy operations.


def test_migrated_database_tracks_new_operations_without_adopting_legacy_folders(tmp_path):
    path, root, policy, settings, history, items = legacy_database(tmp_path)
    migrated = Store(path)
    organizer = Organizer(policy, migrated)
    (root / "new.txt").write_bytes(b"new document")
    (root / "photo.png").write_bytes(b"new image")
    result = organizer.apply(organizer.plan(Scanner(policy).scan(root), settings))
    directories = {row["path"]: row["state"] for row in migrated.directories(result.operation_id)}
    assert directories[str(root / "Documents")] == "existing"
    assert directories[str(root / "Images")] == "created"
    restored = organizer.undo(result.operation_id)
    assert restored.succeeded == 2
    assert (root / "Documents" / "report.txt").exists()
    assert (root / "Documents").is_dir() and not (root / "Images").exists()


def test_migration_failure_rolls_back_table_and_schema_version(tmp_path, monkeypatch):
    path, root, policy, settings, history, items = legacy_database(tmp_path)
    real_connect = sqlite3.connect
    def connection_with_failed_version(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        def authorize(action, first, second, database, trigger):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_PRAGMA and first == "user_version" and second == "2" else sqlite3.SQLITE_OK
        connection.set_authorizer(authorize)
        return connection
    monkeypatch.setattr(sqlite3, "connect", connection_with_failed_version)
    with pytest.raises(sqlite3.DatabaseError):
        Store(path)
    with real_connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='operation_directories'").fetchone() is None
        assert connection.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 1
    monkeypatch.setattr(sqlite3, "connect", real_connect)
    migrated = Store(path)
    assert migrated.history() == history and migrated.items(history[0]["id"]) == items
    assert migrated.load_settings() == settings


def test_reopening_v2_is_idempotent(tmp_path):
    path, root, policy, settings, history, items = legacy_database(tmp_path)
    migrated = Store(path)
    (root / "photo.png").write_bytes(b"new image")
    organizer = Organizer(policy, migrated)
    moved = organizer.apply(organizer.plan(Scanner(policy).scan(root), settings))
    rows = migrated.directories(moved.operation_id)
    history = migrated.history()
    for _ in range(3):
        reopened = Store(path)
        assert reopened.history() == history
        assert reopened.directories(moved.operation_id) == rows
        assert reopened.load_settings() == settings
