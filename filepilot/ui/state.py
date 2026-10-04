from dataclasses import dataclass, field

from filepilot.models.records import DuplicateResult, OrganizationPlan, ScanResult, Settings
from filepilot.services.analysis import Analysis


@dataclass(slots=True)
class AppState:
    settings: Settings = field(default_factory=Settings)
    scan: ScanResult | None = None
    analysis: Analysis | None = None
    duplicates: DuplicateResult | None = None
    plan: OrganizationPlan | None = None
