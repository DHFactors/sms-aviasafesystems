from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums — ICAO Annex 19 / CAR-19 CAAN oversight taxonomy
# ---------------------------------------------------------------------------

class HrcCategory(str, Enum):
    CFIT = "CFIT"
    LOC_I = "LOC_I"
    MAC = "MAC"
    RE = "RE"
    ARC = "ARC"
    FIRE = "FIRE"
    GROUND = "GROUND"
    OTHER = "OTHER"


class SpiDomain(str, Enum):
    HAZARD_ID = "hazard_id"
    RISK_REDUCTION = "risk_reduction"
    SAFETY_CULTURE = "safety_culture"
    TRAINING = "training"
    REPORTING_RATE = "reporting_rate"
    OCCURRENCE_RATE = "occurrence_rate"


class SpiType(str, Enum):
    LEADING = "leading"
    LAGGING = "lagging"


class SpiStatus(str, Enum):
    ON_TARGET = "on_target"
    ACCEPTABLE = "acceptable"
    UNACCEPTABLE = "unacceptable"
    NOT_MEASURED = "not_measured"


class TrajectoryDirection(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DETERIORATING = "deteriorating"


# ---------------------------------------------------------------------------
# Pydantic models — CAAN SSP oversight aggregate payload
# ---------------------------------------------------------------------------

class HrcDistribution(BaseModel):
    category: HrcCategory
    count: int = 0
    high_risk_count: int = 0
    level_ii_count: int = 0
    level_iii_count: int = 0
    level_iv_count: int = 0
    percentage_of_total: float = 0.0


class SpiMetric(BaseModel):
    domain: SpiDomain
    spi_type: SpiType
    name: str
    current_value: Optional[float] = None
    target_value: Optional[float] = None
    status: SpiStatus = SpiStatus.NOT_MEASURED
    trajectory: TrajectoryDirection = TrajectoryDirection.STABLE
    unit: Optional[str] = None
    reporting_period: Optional[str] = None


class OperatorSurveillanceSummary(BaseModel):
    tenant_id: str
    operator_name: str
    total_hazards: int = 0
    open_hazards: int = 0
    closed_hazards: int = 0
    total_reports: int = 0
    total_cans: int = 0
    open_cans: int = 0
    overdue_cans: int = 0
    risk_index: Optional[float] = None
    last_surveillance_date: Optional[datetime] = None
    compliance_score: Optional[float] = None


class AlospEvaluation(BaseModel):
    """Annual Level of Safety Performance evaluation for a single HRC."""
    category: HrcCategory
    year: int
    current_risk_index: Optional[int] = None
    ssp_target: Optional[int] = None
    gap: Optional[int] = None
    tolerability: Optional[str] = None
    trend: TrajectoryDirection = TrajectoryDirection.STABLE
    operator_count: int = 0
    contributing_operators: List[str] = Field(default_factory=list)


class StateAggregateReport(BaseModel):
    """Top-level payload for the CAAN oversight workspace."""
    reporting_year: int
    reporting_quarter: Optional[int] = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    regulator_id: Optional[str] = None

    total_operators: int = 0
    total_hazards: int = 0
    total_reports: int = 0
    total_cans: int = 0
    open_cans: int = 0
    overdue_cans: int = 0
    industry_risk_index: Optional[float] = None

    hrc_distribution: List[HrcDistribution] = Field(default_factory=list)
    spi_metrics: List[SpiMetric] = Field(default_factory=list)
    operator_summaries: List[OperatorSurveillanceSummary] = Field(default_factory=list)
    alosp_evaluations: List[AlospEvaluation] = Field(default_factory=list)

    insights: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
