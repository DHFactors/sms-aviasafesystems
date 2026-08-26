from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums — ICAO Annex 19 / Doc 9859 5x5 Risk Matrix
# ---------------------------------------------------------------------------

class SeverityLevel(str, Enum):
    ONE_NEGLIGIBLE = "1_NEGLIGIBLE"
    TWO_MINOR = "2_MINOR"
    THREE_MAJOR = "3_MAJOR"
    FOUR_HAZARDOUS = "4_HAZARDOUS"
    FIVE_CATASTROPHIC = "5_CATASTROPHIC"


class LikelihoodLevel(str, Enum):
    A_FREQUENT = "A_FREQUENT"
    B_OCCASIONAL = "B_OCCASIONAL"
    C_REMOTE = "C_REMOTE"
    D_IMPROBABLE = "D_IMPROBABLE"
    E_EXTREMELY_IMPROBABLE = "E_EXTREMELY_IMPROBABLE"


class RiskTolerability(str, Enum):
    ACCEPTABLE = "ACCEPTABLE"
    TOLERABLE_WITH_MITIGATION = "TOLERABLE_WITH_MITIGATION"
    INTOLERABLE = "INTOLERABLE"


class MitigationStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    VERIFIED_CLOSED = "VERIFIED_CLOSED"


class ActionPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ---------------------------------------------------------------------------
# 5x5 Risk Matrix Lookup
# ---------------------------------------------------------------------------

_SEVERITY_VALUE = {
    SeverityLevel.ONE_NEGLIGIBLE: 1,
    SeverityLevel.TWO_MINOR: 2,
    SeverityLevel.THREE_MAJOR: 3,
    SeverityLevel.FOUR_HAZARDOUS: 4,
    SeverityLevel.FIVE_CATASTROPHIC: 5,
}

_LIKELIHOOD_VALUE = {
    LikelihoodLevel.A_FREQUENT: 5,
    LikelihoodLevel.B_OCCASIONAL: 4,
    LikelihoodLevel.C_REMOTE: 3,
    LikelihoodLevel.D_IMPROBABLE: 2,
    LikelihoodLevel.E_EXTREMELY_IMPROBABLE: 1,
}

# 5x5 tolerability zones: (severity_axis, likelihood_axis) -> tolerability
# Row = likelihood (A=5 down to E=1), Col = severity (1 left to 5 right)
_TOLERABILITY_MATRIX = {
    (1, 1): RiskTolerability.ACCEPTABLE,
    (1, 2): RiskTolerability.ACCEPTABLE,
    (1, 3): RiskTolerability.ACCEPTABLE,
    (1, 4): RiskTolerability.ACCEPTABLE,
    (1, 5): RiskTolerability.TOLERABLE_WITH_MITIGATION,
    (2, 1): RiskTolerability.ACCEPTABLE,
    (2, 2): RiskTolerability.ACCEPTABLE,
    (2, 3): RiskTolerability.TOLERABLE_WITH_MITIGATION,
    (2, 4): RiskTolerability.TOLERABLE_WITH_MITIGATION,
    (2, 5): RiskTolerability.INTOLERABLE,
    (3, 1): RiskTolerability.ACCEPTABLE,
    (3, 2): RiskTolerability.TOLERABLE_WITH_MITIGATION,
    (3, 3): RiskTolerability.TOLERABLE_WITH_MITIGATION,
    (3, 4): RiskTolerability.INTOLERABLE,
    (3, 5): RiskTolerability.INTOLERABLE,
    (4, 1): RiskTolerability.TOLERABLE_WITH_MITIGATION,
    (4, 2): RiskTolerability.TOLERABLE_WITH_MITIGATION,
    (4, 3): RiskTolerability.INTOLERABLE,
    (4, 4): RiskTolerability.INTOLERABLE,
    (4, 5): RiskTolerability.INTOLERABLE,
    (5, 1): RiskTolerability.TOLERABLE_WITH_MITIGATION,
    (5, 2): RiskTolerability.INTOLERABLE,
    (5, 3): RiskTolerability.INTOLERABLE,
    (5, 4): RiskTolerability.INTOLERABLE,
    (5, 5): RiskTolerability.INTOLERABLE,
}

_TOLERABILITY_COLOR = {
    RiskTolerability.ACCEPTABLE: "#22c55e",
    RiskTolerability.TOLERABLE_WITH_MITIGATION: "#f59e0b",
    RiskTolerability.INTOLERABLE: "#dc2626",
}


def compute_risk_index(severity: SeverityLevel, likelihood: LikelihoodLevel) -> str:
    """Return the 5x5 risk code, e.g. '4C'."""
    s_val = _SEVERITY_VALUE[severity]
    l_letter = likelihood.value.split("_")[0]
    return f"{s_val}{l_letter}"


def compute_tolerability(severity: SeverityLevel, likelihood: LikelihoodLevel) -> RiskTolerability:
    s_val = _SEVERITY_VALUE[severity]
    l_val = _LIKELIHOOD_VALUE[likelihood]
    return _TOLERABILITY_MATRIX.get((s_val, l_val), RiskTolerability.TOLERABLE_WITH_MITIGATION)


def tolerability_color(tolerability: RiskTolerability) -> str:
    return _TOLERABILITY_COLOR[tolerability]


# ---------------------------------------------------------------------------
# Pydantic Schemas — Tenant-level SMS models
# ---------------------------------------------------------------------------

class TenantRiskAssessment(BaseModel):
    """5x5 risk assessment for a tenant hazard or occurrence."""
    hazard_id: str
    description: str
    severity: SeverityLevel
    likelihood: LikelihoodLevel
    risk_index: Optional[str] = None
    tolerability: Optional[RiskTolerability] = None
    mitigation_actions: List[str] = Field(default_factory=list)
    mitigation_status: MitigationStatus = MitigationStatus.OPEN
    risk_owner: Optional[str] = None
    assessed_by: Optional[str] = None
    assessed_at: Optional[datetime] = None
    review_date: Optional[date] = None

    def model_post_init(self, __context: object) -> None:
        if self.risk_index is None:
            self.risk_index = compute_risk_index(self.severity, self.likelihood)
        if self.tolerability is None:
            self.tolerability = compute_tolerability(self.severity, self.likelihood)


class TenantSpiMetric(BaseModel):
    """Safety Performance Indicator tracked at tenant level."""
    spi_id: Optional[str] = None
    name: str
    domain: str
    description: Optional[str] = None
    current_value: Optional[float] = None
    target_value: Optional[float] = None
    alert_threshold: Optional[float] = None
    warning_threshold: Optional[float] = None
    unit: Optional[str] = None
    measurement_period: Optional[str] = None
    is_on_target: Optional[bool] = None
    trend: Optional[str] = None


class CorrectiveActionItem(BaseModel):
    """CAPA item tracked within tenant safety action register."""
    action_id: Optional[str] = None
    source_reference: str
    description: str
    responsible_post_holder: str
    target_close_out_date: Optional[date] = None
    implementation_status: MitigationStatus = MitigationStatus.OPEN
    priority: ActionPriority = ActionPriority.MEDIUM
    risk_reference: Optional[str] = None
    completed_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None


class HeatmapCell(BaseModel):
    """Single cell in the 5x5 tenant risk heatmap."""
    severity: SeverityLevel
    likelihood: LikelihoodLevel
    hazard_count: int = 0
    tolerability: Optional[RiskTolerability] = None
    color: Optional[str] = None

    def model_post_init(self, __context: object) -> None:
        if self.tolerability is None:
            self.tolerability = compute_tolerability(self.severity, self.likelihood)
        if self.color is None:
            self.color = tolerability_color(self.tolerability)


class TenantMonthlySmsReport(BaseModel):
    """Aggregate monthly SMS report for the tenant Safety Review Board."""
    tenant_id: str
    operator_name: Optional[str] = None
    aoc_number: Optional[str] = None
    reporting_year: int
    reporting_month: int
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    flight_hours_logged: float = 0.0
    total_flights: int = 0
    safety_reports_submitted: int = 0
    safety_culture_index: Optional[float] = None

    total_hazards: int = 0
    open_hazards: int = 0
    intolerable_risks: int = 0
    risk_heatmap: List[HeatmapCell] = Field(default_factory=list)

    spi_metrics: List[TenantSpiMetric] = Field(default_factory=list)
    open_capas: List[CorrectiveActionItem] = Field(default_factory=list)
    overdue_capas: int = 0

    insights: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
