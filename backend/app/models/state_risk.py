# ============================================================================
# FILE: state_risk.py
# PATH: backend/app/models/state_risk.py
# VERSION: 1.0.0
# DATE CREATED: 2026-08-04
# PURPOSE: State-level risk register models. Aggregates industry risk across
#          all operator tenants and measures against the country's State
#          Safety Programme (SSP) targets, aligned to ICAO top-risk taxonomy.
# AUTHOR: Ghanshyam Acharya
# CODE OWNER: AviaSafeSystems
# ============================================================================

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class RiskTolerability(str, Enum):
    ACCEPTABLE = "Acceptable"
    TOLERABLE = "Tolerable"
    INTOLERABLE = "Intolerable"


class RiskTolerabilityTier(str, Enum):
    LOW = "LOW"
    HIGH = "HIGH"
    VERY_HIGH = "VERY HIGH"


class RiskTrend(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DETERIORATING = "deteriorating"


class StateRiskRegisterCreate(BaseModel):
    icoc_category: str = Field(...)
    description: str = Field(..., min_length=10)
    icao_reference: Optional[str] = None
    current_risk_index: Optional[int] = Field(None, ge=1, le=25)
    tolerability: RiskTolerability = RiskTolerability.TOLERABLE
    tolerability_tier: Optional[RiskTolerabilityTier] = None
    level: Optional[str] = None
    ssp_target: Optional[float] = None
    actual_ssp_value: Optional[float] = None
    risk_reduction_rate: Optional[float] = None
    trend: RiskTrend = RiskTrend.STABLE
    contributing_tenants: List[str] = Field(default_factory=list)
    quarter: int = Field(..., ge=1, le=4)
    year: int = Field(...)


class StateRiskRegisterUpdate(BaseModel):
    icoc_category: Optional[str] = None
    description: Optional[str] = None
    icao_reference: Optional[str] = None
    current_risk_index: Optional[int] = Field(None, ge=1, le=25)
    tolerability: Optional[RiskTolerability] = None
    tolerability_tier: Optional[RiskTolerabilityTier] = None
    level: Optional[str] = None
    ssp_target: Optional[float] = None
    actual_ssp_value: Optional[float] = None
    risk_reduction_rate: Optional[float] = None
    trend: Optional[RiskTrend] = None
    contributing_tenants: Optional[List[str]] = None
    quarter: Optional[int] = None
    year: Optional[int] = None


class StateRiskRegisterResponse(BaseModel):
    id: str
    icoc_category: str
    description: str
    icao_reference: Optional[str] = None
    current_risk_index: Optional[int] = None
    tolerability: str
    tolerability_tier: Optional[str] = None
    level: Optional[str] = None
    ssp_target: Optional[float] = None
    actual_ssp_value: Optional[float] = None
    risk_reduction_rate: Optional[float] = None
    trend: str
    contributing_tenants: List[str] = Field(default_factory=list)
    quarter: Optional[int] = None
    year: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None

    model_config = {"from_attributes": True}
