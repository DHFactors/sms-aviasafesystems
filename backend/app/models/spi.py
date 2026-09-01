# backend/app/models/spi.py

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime

class SPIType(str, Enum):
    """Type of Safety Performance Indicator"""
    LEADING = "leading"
    LAGGING = "lagging"

class SPIDomain(str, Enum):
    """Domain of SPI"""
    HAZARD_ID = "hazard_id"
    REPORTING_RATE = "reporting_rate"
    DIVERSION_RATE = "diversion_rate"
    RISK_REDUCTION = "risk_reduction"
    TRAINING = "training"
    OCCURRENCE_RATE = "occurrence_rate"
    CAN_CLOSURE = "can_closure"
    CAP_CLOSURE = "cap_closure"
    SAFETY_CULTURE = "safety_culture"
    BARRIER_EFFECTIVENESS = "barrier_effectiveness"

class SPIStatus(str, Enum):
    """Status of SPI vs target"""
    NOMINAL = "nominal"
    WATCH = "watch"
    ALERT = "alert"

class SPI(BaseModel):
    """Safety Performance Indicator"""
    id: str
    name: str
    domain: SPIDomain
    type: SPIType
    unit: str
    measurement_period: str  # daily, weekly, monthly, quarterly, annual
    target_value: float
    alert_threshold: float
    warning_threshold: float
    current_value: Optional[float] = None
    previous_value: Optional[float] = None
    status: Optional[SPIStatus] = None
    trend: Optional[str] = None  # improving, stable, deteriorating
    data_source: str
    tenant_id: Optional[str] = None
    is_demo: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class SPITarget(BaseModel):
    """Safety Performance Target (SPT)"""
    spi_id: str
    target_value: float
    target_date: datetime
    achieved: bool = False
    achieved_at: Optional[datetime] = None

class SPICalculation(BaseModel):
    """SPI calculation result"""
    spi_id: str
    value: float
    previous_value: float
    status: SPIStatus
    trend: str
    period_start: datetime
    period_end: datetime
    data_points: int