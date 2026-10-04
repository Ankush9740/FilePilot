import heapq
import time
from dataclasses import dataclass

from filepilot.core.categories import Category
from filepilot.models.records import FileRecord, Settings


@dataclass(slots=True)
class Analysis:
    categories: dict[Category, tuple[int, int]]
    largest: list[FileRecord]
    large: list[FileRecord]
    old: list[FileRecord]
    total_size: int


def analyze(files: list[FileRecord], settings: Settings) -> Analysis:
    counts = {category: (0, 0) for category in Category}
    large, old = [], []
    cutoff = time.time() - settings.old_days * 86400
    threshold = settings.large_mb * 1024 * 1024
    for file in files:
        count, size = counts[file.category]
        counts[file.category] = count + 1, size + file.size
        if file.size >= threshold:
            large.append(file)
        if file.modified < cutoff:
            old.append(file)
    return Analysis(counts, heapq.nlargest(10, files, key=lambda f: f.size),
                    large, old, sum(size for _, size in counts.values()))
