import re
import sqlite3
import stat
from pathlib import Path
from threading import Event

from filepilot.core.categories import Category
from filepilot.core.safety import Cancelled, SafetyError, SafetyPolicy, hash_file, move_no_replace, verify_record
from filepilot.database.store import Store
from filepilot.models.records import (
    FileRecord, Issue, OperationResult, OrganizationPlan, PlanItem, ScanResult, Settings,
)
from filepilot.services.scanner import Progress

RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                  *(f"LPT{i}" for i in range(1, 10))}


def validate_settings(settings: Settings) -> None:
    if settings.theme not in ("Light", "Dark", "System"):
        raise ValueError("Choose Light, Dark, or System")
    if not 1 <= settings.old_days <= 36500 or not 1 <= settings.large_mb <= 1_000_000:
        raise ValueError("Analysis thresholds must be positive and within the displayed limits")
    if set(settings.destinations) != {str(category) for category in Category}:
        raise ValueError("Every category needs one destination folder")
    names = list(settings.destinations.values())
    for name in names:
        if (not isinstance(name, str) or not name or name in (".", "..") or len(name) > 80
                or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name != name.strip()
                or name.endswith(".") or name.split(".")[0].upper() in RESERVED_NAMES):
            raise ValueError(f"Invalid destination folder name: {name!r}")
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("Category destination folders must have different names")


class Organizer:
    def __init__(self, policy: SafetyPolicy, store: Store) -> None:
        self.policy, self.store = policy, store

    def plan(self, scan: ScanResult, settings: Settings, cancel: Event | None = None,
             progress: Progress | None = None) -> OrganizationPlan:
        validate_settings(settings)
        self.policy.check(scan.root, scan.root)
        plan = OrganizationPlan(scan.root)
        reserved: set[str] = set()
        for index, file in enumerate(scan.files):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            target_name = settings.destinations[str(file.category)]
            relative = file.path.relative_to(scan.root)
            if len(relative.parts) > 1 and relative.parts[0].casefold() == target_name.casefold():
                plan.already_organized += 1
                continue
            destination = scan.root / target_name / file.name
            conflict = ""
            try:
                self.policy.check(file.path, scan.root)
                verify_record(file)
                self.policy.check(destination, scan.root, allow_missing=True)
                key = str(destination).casefold()
                if destination.exists() or key in reserved:
                    conflict = "Destination filename already exists or is claimed by another file; skipped"
                elif destination.parent.exists() and not destination.parent.is_dir():
                    conflict = "Destination category path is not a folder; skipped"
                else:
                    reserved.add(key)
            except OSError as error:
                conflict = str(error)
            plan.items.append(PlanItem(file, destination, conflict))
            if progress and index % 100 == 0:
                progress(index + 1, len(scan.files), file.name)
        return plan

    def apply(self, plan: OrganizationPlan, cancel: Event | None = None,
              progress: Progress | None = None) -> OperationResult:
        self.policy.check(plan.root, plan.root)
        operation_id = self.store.begin_operation(
            plan.root, [(item.file, item.destination, item.conflict) for item in plan.items])
        rows = self.store.items(operation_id)
        issues: list[Issue] = []
        succeeded, failed = 0, 0
        cancelled = False
        prepared_directories: set[Path] = set()
        for index, (item, row) in enumerate(zip(plan.items, rows, strict=True)):
            if item.conflict:
                failed += 1
                issues.append(Issue(item.file.path, item.conflict))
                continue
            if cancel is not None and cancel.is_set():
                cancelled = True
                self.store.update_item(row["id"], "failed", "Cancelled before moving")
                failed += 1
                continue
            try:
                source, destination = item.file.path, item.destination
                self.policy.check(source, plan.root)
                self.policy.check(destination, plan.root, allow_missing=True)
                verify_record(item.file)
                if destination.exists():
                    raise SafetyError("Destination now exists; file was not moved")
                digest = hash_file(item.file, cancel)
                if destination.parent not in prepared_directories:
                    self._prepare_directory(operation_id, destination.parent, plan.root)
                    prepared_directories.add(destination.parent)
                self.policy.check(destination, plan.root, allow_missing=True)
                verify_record(item.file)
                # Durable intent precedes the filesystem mutation. Recovery resolves an interruption.
                self.store.update_item(row["id"], "moving", digest=digest)
                move_no_replace(source, destination)
            except (OSError, Cancelled) as error:
                message = "Cancelled before moving" if isinstance(error, Cancelled) else str(error)
                cancelled |= isinstance(error, Cancelled)
                self.store.update_item(row["id"], "failed", message)
                issues.append(Issue(item.file.path, message))
                failed += 1
            else:
                # If this database write fails, 'moving' remains recoverable on next launch.
                self.store.update_item(row["id"], "moved")
                succeeded += 1
            if progress:
                progress(index + 1, len(plan.items), item.file.name)
        status = "cancelled" if cancelled else "partial" if failed and succeeded else "failed" if failed else "completed"
        self.store.set_status(operation_id, status)
        return OperationResult(operation_id, succeeded, failed, status, issues)

    def _prepare_directory(self, operation_id: int, directory: Path, root: Path) -> None:
        # Organization destinations are direct category children; never create ancestors.
        if directory.parent != root:
            raise SafetyError("Destination directory must be a direct child of the working folder")
        self.policy.check(directory, root, allow_missing=True)
        self.store.directory_intent(operation_id, directory)
        try:
            directory.mkdir()  # Atomic ownership decision: no parents=True or exist_ok=True.
        except FileExistsError:
            self.store.directory_created(operation_id, directory, None)
            self.policy.check(directory, root)
            if not directory.is_dir():
                raise SafetyError("Destination category path is not a folder")
        else:
            self.policy.check(directory, root)
            self.store.directory_created(operation_id, directory, directory.stat(follow_symlinks=False))

    def _record(self, row: dict, path: Path) -> FileRecord:
        from filepilot.core.categories import classify
        return FileRecord(path, row["size"], row["modified_ns"], None, classify(path),
                          int(row["device"]), int(row["inode"]))

    def undo(self, operation_id: int, cancel: Event | None = None,
             progress: Progress | None = None) -> OperationResult:
        operation = self.store.operation(operation_id)
        root = Path(operation["source_root"])
        self.policy.check(root, root)
        rows = [row for row in self.store.items(operation_id) if row["state"] in ("moved", "undo_failed")]
        self.store.set_status(operation_id, "undoing")
        succeeded, failed, issues = 0, 0, []
        for index, row in enumerate(rows):
            original, destination = Path(row["original_path"]), Path(row["destination_path"])
            try:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                self.policy.check(destination, root)
                self.policy.check(original, root, allow_missing=True)
                if original.exists():
                    raise SafetyError("Original location is occupied; nothing was overwritten")
                file = self._record(row, destination)
                verify_record(file)
                if hash_file(file, cancel) != row["digest"]:
                    raise SafetyError("File content changed after organization; undo refused")
                original.parent.mkdir(parents=True, exist_ok=True)
                self.policy.check(original, root, allow_missing=True)
                verify_record(file)
                self.store.update_item(row["id"], "restoring")
                move_no_replace(destination, original)
            except (OSError, Cancelled) as error:
                message = "Undo cancelled" if isinstance(error, Cancelled) else str(error)
                self.store.update_item(row["id"], "undo_failed", message)
                issues.append(Issue(destination, message))
                failed += 1
            else:
                self.store.update_item(row["id"], "restored")
                succeeded += 1
            if progress:
                progress(index + 1, len(rows), destination.name)
        all_rows = self.store.items(operation_id)
        remaining = any(row["state"] in ("moved", "undo_failed", "restoring") for row in all_rows)
        status = "partial_undo" if remaining else "undone"
        self.store.set_status(operation_id, status)
        if not remaining and any(row["state"] == "restored" for row in all_rows):
            issues.extend(self._cleanup_directories(operation_id, root, cancel))
        return OperationResult(operation_id, succeeded, failed, status, issues)

    def _cleanup_directories(self, operation_id: int, root: Path, cancel: Event | None) -> list[Issue]:
        """Best effort after durable file restoration. Counts/status remain file outcomes."""
        issues: list[Issue] = []
        try:
            directories = self.store.directories(operation_id)
        except sqlite3.Error as error:
            return [Issue(root, f"Files restored; directory cleanup journal unavailable: {error}")]
        for row in directories:
            if cancel is not None and cancel.is_set():
                break
            if row["state"] != "created":
                continue  # Existing, uncertain creation intent and old operations are not owned.
            directory = Path(row["path"])
            try:
                if directory.parent != root:
                    raise SafetyError("Recorded category directory is not a direct child of the working folder")
                self.policy.check(directory, root, allow_missing=True)
                if not directory.exists():
                    self.store.directory_cleanup(operation_id, directory, "missing")
                    continue
                with self.store.directory_cleanup_lock() as connection:
                    if self.store.directory_in_use(operation_id, directory, connection):
                        raise SafetyError("Another operation still references this directory; folder retained")
                    # Recheck identity and safety after querying other intents, immediately
                    # before rmdir. It refuses all contents, including hidden entries.
                    self.policy.check(directory, root)
                    info = directory.stat(follow_symlinks=False)
                    identity = (str(info.st_dev), str(info.st_ino), getattr(info, "st_birthtime_ns", 0))
                    if (not stat.S_ISDIR(info.st_mode) or not info.st_ino
                            or identity != (row["device"], row["inode"], row["birth_ns"])):
                        raise SafetyError("Directory identity changed or cannot be verified; folder retained")
                    directory.rmdir()
                    self.store.directory_cleanup(operation_id, directory, "removed", "", connection)
            except (OSError, sqlite3.Error) as error:
                message = f"Files restored; category folder retained or cleanup unconfirmed: {error}"
                issues.append(Issue(directory, message))
                try:
                    self.store.directory_cleanup(operation_id, directory, "created", message)
                except sqlite3.Error:
                    pass  # The completed file journal must not be undone by cleanup failure.
        return issues

    def recover(self, cancel: Event | None = None, progress: Progress | None = None) -> list[Issue]:
        """Reconcile durable intent after a crash; never move anything during recovery."""
        issues: list[Issue] = []
        operations = [op for op in self.store.history() if op["status"] in ("running", "undoing", "interrupted")]
        for operation in operations:
            root = Path(operation["source_root"])
            for row in self.store.items(operation["id"]):
                if cancel is not None and cancel.is_set():
                    return issues
                if row["state"] == "queued":
                    self.store.update_item(row["id"], "failed", "Interrupted before moving")
                elif row["state"] in ("moving", "restoring"):
                    restoring = row["state"] == "restoring"
                    arrived = Path(row["original_path"] if restoring else row["destination_path"])
                    departed = Path(row["destination_path"] if restoring else row["original_path"])
                    try:
                        self.policy.check(arrived, root)
                        self.policy.check(departed, root, allow_missing=True)
                        if departed.exists() or hash_file(self._record(row, arrived), cancel) != row["digest"]:
                            raise SafetyError("Interrupted item needs manual review; paths or content differ")
                        self.store.update_item(row["id"], "restored" if restoring else "moved")
                    except (OSError, Cancelled) as error:
                        # Keep unresolved intent in the journal; don't make it undoable by guessing.
                        self.store.update_item(row["id"], row["state"], str(error))
                        issues.append(Issue(arrived, str(error)))
            rows = self.store.items(operation["id"])
            unresolved = any(row["state"] in ("moving", "restoring") for row in rows)
            if unresolved:
                status = "interrupted"
            elif operation["status"] == "undoing":
                status = "partial_undo" if any(row["state"] in ("moved", "undo_failed") for row in rows) else "undone"
            else:
                status = "partial" if any(row["state"] == "failed" for row in rows) else "completed"
            self.store.set_status(operation["id"], status)
        return issues
