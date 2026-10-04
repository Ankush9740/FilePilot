from collections import defaultdict
from threading import Event

from filepilot.core.safety import Cancelled, hash_file
from filepilot.models.records import DuplicateGroup, DuplicateResult, FileRecord, Issue
from filepilot.services.scanner import Progress


def find_duplicates(files: list[FileRecord], cancel: Event | None = None,
                    progress: Progress | None = None) -> DuplicateResult:
    sizes: dict[int, list[FileRecord]] = defaultdict(list)
    for file in files:
        sizes[file.size].append(file)
    candidates = [file for group in sizes.values() if len(group) > 1 for file in group]
    hashed: dict[tuple[int, str], list[FileRecord]] = defaultdict(list)
    result = DuplicateResult()
    for index, file in enumerate(candidates):
        if cancel is not None and cancel.is_set():
            result.cancelled = True
            break
        try:
            digest = hash_file(file, cancel)
            hashed[file.size, digest].append(file)
            result.hashed_files += 1
        except Cancelled:
            result.cancelled = True
            break
        except OSError as error:
            result.issues.append(Issue(file.path, str(error)))
        if progress:
            progress(index + 1, len(candidates), file.name)
    result.groups = sorted(
        (DuplicateGroup(digest, tuple(group)) for (_, digest), group in hashed.items() if len(group) > 1),
        key=lambda group: group.redundant_size, reverse=True,
    )
    return result
