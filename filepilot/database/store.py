import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from filepilot.models.records import FileRecord, Settings

SCHEMA_VERSION = 2

# Unknown states are preserved. Terminal labels alone do not prove Undo is unnecessary.
CLEARABLE_OPERATION_SQL = """
    o.status IN ('completed','partial','failed','cancelled','undone')
    AND NOT EXISTS (SELECT 1 FROM operation_items pending
                    WHERE pending.operation_id=o.id AND pending.state NOT IN ('failed','restored'))
"""


class Store:
    """Short-lived connections let workers and the GUI use one store safely."""

    def __init__(self, path: Path) -> None:
        self.path = Path(os.path.abspath(path))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError("This database belongs to a newer FilePilot version")
            if version < 1:
                connection.executescript("""
                    BEGIN;
                    CREATE TABLE operations (
                        id INTEGER PRIMARY KEY,
                        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                        source_root TEXT NOT NULL,
                        item_count INTEGER NOT NULL,
                        status TEXT NOT NULL DEFAULT 'running'
                    );
                    CREATE TABLE operation_items (
                        id INTEGER PRIMARY KEY,
                        operation_id INTEGER NOT NULL REFERENCES operations(id),
                        original_path TEXT NOT NULL,
                        destination_path TEXT NOT NULL,
                        size INTEGER NOT NULL,
                        modified_ns INTEGER NOT NULL,
                        device TEXT NOT NULL,
                        inode TEXT NOT NULL,
                        digest TEXT NOT NULL DEFAULT '',
                        state TEXT NOT NULL DEFAULT 'queued',
                        error TEXT NOT NULL DEFAULT ''
                    );
                    CREATE INDEX items_operation ON operation_items(operation_id);
                    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    PRAGMA user_version = 1;
                    COMMIT;
                """)
            if version < 2:
                # An additive transaction preserves every v1 operation, item and preference.
                # Old operations have no directory provenance, so their folders are retained.
                connection.executescript("""
                    BEGIN;
                    CREATE TABLE operation_directories (
                        operation_id INTEGER NOT NULL REFERENCES operations(id),
                        path TEXT NOT NULL,
                        state TEXT NOT NULL DEFAULT 'creating',
                        device TEXT NOT NULL DEFAULT '',
                        inode TEXT NOT NULL DEFAULT '',
                        birth_ns INTEGER NOT NULL DEFAULT 0,
                        cleanup_error TEXT NOT NULL DEFAULT '',
                        PRIMARY KEY (operation_id, path)
                    );
                    PRAGMA user_version = 2;
                    COMMIT;
                """)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def load_settings(self) -> Settings:
        with self.connection() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key='preferences'").fetchone()
        if row is None:
            return Settings()
        try:
            settings = Settings(**json.loads(row[0]))
            from filepilot.services.organizer import validate_settings
            validate_settings(settings)
            return settings
        except (TypeError, ValueError, KeyError):
            return Settings()

    def save_settings(self, settings: Settings) -> None:
        from dataclasses import asdict
        from filepilot.services.organizer import validate_settings
        validate_settings(settings)
        with self.connection() as connection:
            connection.execute("INSERT INTO settings(key,value) VALUES('preferences',?) "
                               "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                               (json.dumps(asdict(settings)),))

    def begin_operation(self, root: Path, items: list[tuple[FileRecord, Path, str]]) -> int:
        with self.connection() as connection:
            operation_id = connection.execute(
                "INSERT INTO operations(source_root,item_count) VALUES(?,?)", (str(root), len(items))
            ).lastrowid
            connection.executemany("""
                INSERT INTO operation_items(operation_id,original_path,destination_path,
                    size,modified_ns,device,inode,state,error) VALUES(?,?,?,?,?,?,?,?,?)
            """, [(operation_id, str(file.path), str(destination), file.size, file.modified_ns,
                   str(file.device), str(file.inode), 'failed' if conflict else 'queued', conflict)
                  for file, destination, conflict in items])
        assert operation_id is not None
        return operation_id

    def items(self, operation_id: int) -> list[dict[str, Any]]:
        with self.connection() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM operation_items WHERE operation_id=? ORDER BY id", (operation_id,))]

    def update_item(self, item_id: int, state: str, error: str = "", digest: str | None = None) -> None:
        with self.connection() as connection:
            if digest is None:
                connection.execute("UPDATE operation_items SET state=?,error=? WHERE id=?",
                                   (state, error, item_id))
            else:
                connection.execute("UPDATE operation_items SET state=?,error=?,digest=? WHERE id=?",
                                   (state, error, digest, item_id))

    def set_status(self, operation_id: int, status: str) -> None:
        with self.connection() as connection:
            connection.execute("UPDATE operations SET status=? WHERE id=?", (status, operation_id))

    def operation(self, operation_id: int) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
        if row is None:
            raise ValueError("Operation does not exist")
        return dict(row)

    def directory_intent(self, operation_id: int, path: Path) -> None:
        with self.connection() as connection:
            connection.execute("INSERT INTO operation_directories(operation_id,path) VALUES(?,?)",
                               (operation_id, str(path)))

    def directory_created(self, operation_id: int, path: Path, info: os.stat_result | None) -> None:
        with self.connection() as connection:
            connection.execute("""
                UPDATE operation_directories SET state=?,device=?,inode=?,birth_ns=?
                WHERE operation_id=? AND path=? AND state='creating'
            """, ("created" if info else "existing", str(info.st_dev) if info else "",
                  str(info.st_ino) if info else "", getattr(info, "st_birthtime_ns", 0) if info else 0,
                  operation_id, str(path)))

    def directories(self, operation_id: int) -> list[dict[str, Any]]:
        with self.connection() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM operation_directories WHERE operation_id=? ORDER BY path", (operation_id,))]

    @contextmanager
    def directory_cleanup_lock(self) -> Iterator[sqlite3.Connection]:
        # Hold the journal writer lock across reference validation and rmdir. Another
        # FilePilot instance cannot publish a new file intent between those steps.
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            yield connection

    def directory_cleanup(self, operation_id: int, path: Path, state: str, error: str = "",
                          connection: sqlite3.Connection | None = None) -> None:
        if connection is None:
            with self.connection() as opened:
                self.directory_cleanup(operation_id, path, state, error, opened)
            return
        connection.execute("""UPDATE operation_directories SET state=?,cleanup_error=?
                              WHERE operation_id=? AND path=?""", (state, error, operation_id, str(path)))

    def directory_in_use(self, operation_id: int, path: Path,
                         connection: sqlite3.Connection | None = None) -> bool:
        """Other unfinished file intents may need either side of their recorded paths."""
        if connection is None:
            with self.connection() as opened:
                return self.directory_in_use(operation_id, path, opened)
        rows = connection.execute("""
            SELECT original_path,destination_path FROM operation_items
            WHERE operation_id<>? AND state IN ('queued','moving','moved','undo_failed','restoring')
        """, (operation_id,)).fetchall()
        return any(path == candidate or path in candidate.parents for row in rows
                   for candidate in (Path(row["original_path"]), Path(row["destination_path"])))

    def history(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            return [dict(row) for row in connection.execute(f"""
                SELECT o.*, COUNT(CASE WHEN i.state IN ('moved','undo_failed') THEN 1 END) AS remaining,
                    COUNT(CASE WHEN i.state='restored' THEN 1 END) AS restored,
                    COUNT(CASE WHEN i.state='failed' THEN 1 END) AS failures,
                    ({CLEARABLE_OPERATION_SQL}) AS clearable
                FROM operations o LEFT JOIN operation_items i ON i.operation_id=o.id
                GROUP BY o.id ORDER BY o.id DESC
            """)]

    def clear_history(self) -> int:
        """Remove only terminal, non-actionable journal records; never touch file paths."""
        with self.connection() as connection:
            # Recheck under the writer lock, rather than trusting an earlier UI snapshot.
            connection.execute("BEGIN IMMEDIATE")
            ids = [(row[0],) for row in connection.execute(
                f"SELECT o.id FROM operations o WHERE {CLEARABLE_OPERATION_SQL}")]
            connection.executemany("DELETE FROM operation_directories WHERE operation_id=?", ids)
            connection.executemany("DELETE FROM operation_items WHERE operation_id=?", ids)
            connection.executemany("DELETE FROM operations WHERE id=?", ids)
        return len(ids)
