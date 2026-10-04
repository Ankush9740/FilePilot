import os
import stat
from collections.abc import Callable
from pathlib import Path
from threading import Event

from filepilot.core.categories import classify
from filepilot.core.safety import SafetyPolicy, is_link
from filepilot.models.records import FileRecord, Issue, ScanResult

Progress = Callable[[int, int, str], None]


class Scanner:
    def __init__(self, policy: SafetyPolicy) -> None:
        self.policy = policy

    def scan(self, root: Path, cancel: Event | None = None,
             progress: Progress | None = None) -> ScanResult:
        root = Path(os.path.abspath(root))
        self.policy.check(root, root)
        if not root.is_dir():
            raise NotADirectoryError(root)
        result = ScanResult(root)
        pending = [root]
        while pending:
            if cancel is not None and cancel.is_set():
                result.cancelled = True
                break
            folder = pending.pop()
            try:
                self.policy.check(folder, root)
                with os.scandir(folder) as entries:
                    for entry in entries:
                        if cancel is not None and cancel.is_set():
                            result.cancelled = True
                            break
                        path = Path(entry.path)
                        try:
                            if self.policy.protected_path(path):
                                result.skipped_protected += 1
                                continue
                            if is_link(path):
                                result.skipped_links += 1
                                continue
                            info = entry.stat(follow_symlinks=False)
                            if stat.S_ISDIR(info.st_mode):
                                pending.append(path)
                            elif stat.S_ISREG(info.st_mode):
                                # Windows DirEntry.stat may omit file identity (st_ino/st_dev).
                                # Use a full stat for records that will later be safety-checked.
                                info = path.stat(follow_symlinks=False)
                                created = getattr(info, "st_birthtime", None)
                                if created is None and os.name == "nt":
                                    created = info.st_ctime
                                result.files.append(FileRecord(
                                    path, info.st_size, info.st_mtime_ns, created,
                                    classify(path), info.st_dev, info.st_ino,
                                ))
                            if progress and len(result.files) % 100 == 0:
                                progress(len(result.files), 0, str(folder))
                        except OSError as error:
                            result.issues.append(Issue(path, str(error)))
            except OSError as error:
                result.issues.append(Issue(folder, str(error)))
            if progress:
                progress(len(result.files), 0, str(folder))
        return result
