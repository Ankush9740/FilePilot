from dataclasses import dataclass, field
from pathlib import Path

from filepilot.core.categories import Category


@dataclass(frozen=True, slots=True)
class FileRecord:
    path: Path
    size: int
    modified_ns: int
    created: float | None
    category: Category
    device: int
    inode: int

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def extension(self) -> str:
        return self.path.suffix.lower()

    @property
    def modified(self) -> float:
        return self.modified_ns / 1_000_000_000


@dataclass(frozen=True, slots=True)
class Issue:
    path: Path
    message: str


@dataclass(slots=True)
class ScanResult:
    root: Path
    files: list[FileRecord] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    skipped_links: int = 0
    skipped_protected: int = 0
    cancelled: bool = False

    @property
    def total_size(self) -> int:
        return sum(file.size for file in self.files)


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    digest: str
    files: tuple[FileRecord, ...]

    @property
    def redundant_size(self) -> int:
        return (len(self.files) - 1) * self.files[0].size


@dataclass(slots=True)
class DuplicateResult:
    groups: list[DuplicateGroup] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    cancelled: bool = False
    hashed_files: int = 0

    @property
    def extra_copies(self) -> int:
        return sum(len(group.files) - 1 for group in self.groups)

    @property
    def redundant_size(self) -> int:
        return sum(group.redundant_size for group in self.groups)


@dataclass(frozen=True, slots=True)
class PlanItem:
    file: FileRecord
    destination: Path
    conflict: str = ""


@dataclass(slots=True)
class OrganizationPlan:
    root: Path
    items: list[PlanItem] = field(default_factory=list)
    already_organized: int = 0

    @property
    def actionable(self) -> list[PlanItem]:
        return [item for item in self.items if not item.conflict]


@dataclass(slots=True)
class OperationResult:
    operation_id: int
    succeeded: int
    failed: int
    status: str
    issues: list[Issue] = field(default_factory=list)


@dataclass(slots=True)
class Settings:
    theme: str = "Light"
    old_days: int = 365
    large_mb: int = 100
    destinations: dict[str, str] = field(default_factory=lambda: {str(c): str(c) for c in Category})
