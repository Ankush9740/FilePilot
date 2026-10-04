import hashlib
import os
import stat
from collections.abc import Callable
from pathlib import Path
from threading import Event

from filepilot.models.records import FileRecord


class SafetyError(OSError):
    """A file operation could not meet its safety requirements."""


class Cancelled(Exception):
    pass


def is_link(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


class SafetyPolicy:
    def __init__(self, protected: tuple[Path, ...] = ()) -> None:
        roots = [Path(os.path.abspath(path)) for path in protected]
        # Protect both the configured and actual locations of redirected app data.
        self.protected = tuple(dict.fromkeys([*roots, *(path.resolve() for path in roots)]))

    def protected_path(self, path: Path) -> bool:
        absolute = Path(os.path.abspath(path))
        return any(is_within(absolute, root) for root in self.protected)

    def check(self, path: Path, root: Path, *, allow_missing: bool = False) -> None:
        if ".." in path.parts or ".." in root.parts:
            raise SafetyError("Parent traversal is not allowed in operation paths")
        path, root = path.absolute(), root.absolute()
        if not is_within(path, root):
            raise SafetyError("Path is outside the selected folder")
        if self.protected_path(path):
            raise SafetyError("FilePilot's application data is protected")
        # Check every existing ancestor, including ancestors above the selected root.
        for ancestor in reversed((path, *path.parents)):
            try:
                if is_link(ancestor):
                    raise SafetyError(f"Symbolic link or reparse point is not allowed: {ancestor}")
            except FileNotFoundError:
                if not allow_missing:
                    raise


def verify_record(file: FileRecord) -> os.stat_result:
    if is_link(file.path):
        raise SafetyError("File became a symbolic link or reparse point")
    info = file.path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode):
        raise SafetyError("Path is no longer a regular file")
    if (info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino) != (
        file.size, file.modified_ns, file.device, file.inode
    ):
        raise SafetyError("File changed since the scan; rescan before proceeding")
    return info


def hash_file(file: FileRecord, cancel: Event | None = None,
              activity: Callable[[int], None] | None = None) -> str:
    verify_record(file)
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(file.path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
            file.device, file.inode, file.size, file.modified_ns
        ):
            raise SafetyError("File changed while opening")
        while chunk := stream.read(1024 * 1024):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            digest.update(chunk)
            if activity:
                activity(len(chunk))
        final = os.fstat(stream.fileno())
        if (final.st_size, final.st_mtime_ns) != (file.size, file.modified_ns):
            raise SafetyError("File changed while reading")
    verify_record(file)
    return digest.hexdigest()


def move_no_replace(source: Path, destination: Path) -> None:
    """Same-volume move. Never use POSIX rename (which replaces destinations)."""
    if os.name == "nt":
        # Windows rename fails atomically if the destination exists, including races.
        os.rename(source, destination)
    else:
        os.link(source, destination, follow_symlinks=False)
        try:
            source.unlink()
        except OSError:
            destination.unlink()
            raise
