from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ReportType(str, Enum):
    VOLUNTARY = "voluntary"
    MANDATORY = "mandatory"


class ReportStatus(str, Enum):
    NEW = "NEW"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class AiStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


_OCCURRENCE_TYPES = ["ACCIDENT", "SERIOUS_INCIDENT", "INCIDENT"]

_OCCURRENCE_CLASSES = [
    "CLASS_A", "CLASS_B", "CLASS_C", "CLASS_D", "CLASS_E"
]

_OCCURRENCE_CATEGORIES = [
    "ARC", "MAC", "BIRD", "CABIN", "CFIT", "ENG", "FIRE", "GCOL",
    "LOCI", "PRO", "RE", "RI", "SYS", "WX", "OTHER"
]

_SEVERITY_LEVELS = ["Low", "Medium", "High", "Critical"]

_INVESTIGATION_STATUSES = [
    "NOT_STARTED", "UNDER_INVESTIGATION", "COMPLETED"
]

_FLIGHT_PHASES = [
    "Standing", "Pushback/Towing", "Taxi", "Takeoff", "Initial Climb",
    "Climb", "Cruise", "Descent", "Approach", "Landing", "Go-Around",
    "Emergency", "Hover", "Circuit", "Aerobatics"
]

_FLIGHT_TYPES = [
    "Commercial", "Private", "Training", "Ferry",
    "Agricultural", "Survey", "Pleasure", "Other"
]

_AIRCRAFT_CATEGORIES = ["Aeroplane", "Helicopter", "Glider", "Other"]

_HUMAN_FACTORS = [
    "Decision Making Error", "Situational Awareness", "Skill-Based Error",
    "Procedural Error", "Communication", "Fatigue", "Pressure",
    "Distraction", "Perception"
]

_REPORTER_ROLES = [
    "pilot", "first_officer", "flight_engineer", "cabin_crew",
    "atc", "maintenance", "ground", "dispatcher", "safety_manager", "other"
]


class Attachment(BaseModel):
    name: str
    url: str
    type: str = "unknown"


class CorrectiveAction(BaseModel):
    description: str
    assigned_to: Optional[str] = None
    due_date: Optional[datetime] = None
    status: str = "OPEN"


class RiskAssessment(BaseModel):
    severity: int
    probability: int
    risk_index: int
    risk_level: str
    tolerability_tier: Optional[str] = None
    assessed_by: str
    assessed_at: datetime
    notes: Optional[str] = None


class AiSuggestedAssessment(BaseModel):
    suggested_severity: int
    suggested_probability: int
    suggested_risk_index: int
    suggested_risk_level: str
    tolerability_tier: Optional[str] = None
    confidence: float
    severity_explanation: Optional[str] = None
    probability_explanation: Optional[str] = None


class ReportCreate(BaseModel):
    report_type: ReportType = ReportType.VOLUNTARY
    is_anonymous: bool = False
    narrative: str = Field(..., min_length=10, max_length=10000)
    location: str = Field(..., min_length=2, max_length=100)
    occurrence_date: datetime
    flight_number: Optional[str] = None
    aircraft_registration: Optional[str] = None
    severity_level: Optional[int] = Field(None, ge=1, le=5)
    probability_level: Optional[int] = Field(None, ge=1, le=5)

    occurrence_class: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    country: Optional[str] = None

    aircraft_make: Optional[str] = None
    aircraft_model: Optional[str] = None
    aircraft_serial_number: Optional[str] = None
    operator: Optional[str] = None
    operator_icao: Optional[str] = None
    aircraft_category: Optional[str] = None
    engine_make: Optional[str] = None
    engine_model: Optional[str] = None
    engine_serial_number: Optional[str] = None

    flight_phase: Optional[str] = None
    flight_type: Optional[str] = None
    departure_airport: Optional[str] = None
    destination_airport: Optional[str] = None
    aircraft_utilisation_hours: Optional[float] = None
    aircraft_utilisation_cycles: Optional[int] = None

    crew_count: Optional[int] = None
    passenger_count: Optional[int] = None
    fatal_injuries: Optional[int] = None
    serious_injuries: Optional[int] = None
    minor_injuries: Optional[int] = None

    occurrence_category: Optional[str] = None
    human_factors: Optional[List[str]] = None
    contributing_factors: Optional[List[str]] = None
    investigation_agency: Optional[str] = None

    reporter_name: Optional[str] = None
    reporter_role: Optional[str] = None
    reporter_email: Optional[str] = None
    reporter_phone: Optional[str] = None
    reporter_organisation: Optional[str] = None
    reporting_date: Optional[datetime] = None


class MorCreate(BaseModel):
    reporter_name: str = Field(..., min_length=2, max_length=100)
    reporter_role: str = Field(...)
    reporter_organisation: str = Field(..., min_length=2, max_length=100)
    reporter_email: EmailStr = Field(...)
    reporter_phone: Optional[str] = None
    reporting_date: datetime = Field(default_factory=datetime.utcnow)

    aircraft_make: str = Field(..., min_length=2, max_length=50)
    aircraft_model: str = Field(..., min_length=2, max_length=50)
    aircraft_registration: str = Field(..., min_length=3, max_length=20)
    aircraft_serial_number: Optional[str] = None
    operator: str = Field(..., min_length=2, max_length=100)
    operator_icao: Optional[str] = Field(None, max_length=3)
    aircraft_category: str = Field(...)
    etops: bool = False

    engine_make: Optional[str] = None
    engine_model: Optional[str] = None
    engine_serial_number: Optional[str] = None
    propeller_make: Optional[str] = None
    propeller_model: Optional[str] = None

    flight_number: Optional[str] = None
    call_sign: Optional[str] = None
    flight_type: str = Field(...)
    flight_phase: str = Field(...)
    departure_airport: Optional[str] = Field(None, max_length=4)
    destination_airport: Optional[str] = Field(None, max_length=4)

    crew_count: Optional[int] = Field(None, ge=0)
    passenger_count: Optional[int] = Field(None, ge=0)
    fatal_injuries: Optional[int] = Field(None, ge=0)
    serious_injuries: Optional[int] = Field(None, ge=0)
    minor_injuries: Optional[int] = Field(None, ge=0)

    occurrence_date_time: datetime = Field(...)
    occurrence_location: str = Field(..., min_length=2, max_length=100)
    occurrence_latitude: Optional[float] = Field(None, ge=-90, le=90)
    occurrence_longitude: Optional[float] = Field(None, ge=-180, le=180)
    occurrence_country: str = Field(..., min_length=2, max_length=100)
    occurrence_type: str = Field(...)
    occurrence_class: str = Field(...)
    occurrence_category: str = Field(...)
    human_factors: List[str] = Field(default_factory=list)
    contributing_factors: List[str] = Field(default_factory=list)
    narrative: str = Field(..., min_length=10)

    severity: Optional[int] = Field(None, ge=1, le=5)
    probability: Optional[int] = Field(None, ge=1, le=5)

    investigation_status: Optional[str] = None
    investigation_agency: Optional[str] = None
    organisation_comments: Optional[str] = None
    manufacturer_advised: bool = False
    fdr_data_retained: bool = False

    @field_validator('occurrence_type')
    @classmethod
    def mor_validate_occurrence_type(cls, v: str) -> str:
        if v not in _OCCURRENCE_TYPES:
            raise ValueError(f"occurrence_type must be one of: {', '.join(_OCCURRENCE_TYPES)}")
        return v

    @field_validator('occurrence_class')
    @classmethod
    def mor_validate_occurrence_class(cls, v: str) -> str:
        if v not in _OCCURRENCE_CLASSES:
            raise ValueError(f"occurrence_class must be one of: {', '.join(_OCCURRENCE_CLASSES)}")
        return v

    @field_validator('occurrence_category')
    @classmethod
    def mor_validate_occurrence_category(cls, v: str) -> str:
        if v not in _OCCURRENCE_CATEGORIES:
            raise ValueError(f"occurrence_category must be one of: {', '.join(_OCCURRENCE_CATEGORIES)}")
        return v

    @field_validator('flight_phase')
    @classmethod
    def mor_validate_flight_phase(cls, v: str) -> str:
        if v not in _FLIGHT_PHASES:
            raise ValueError(f"flight_phase must be one of: {', '.join(_FLIGHT_PHASES)}")
        return v

    @field_validator('flight_type')
    @classmethod
    def mor_validate_flight_type(cls, v: str) -> str:
        if v not in _FLIGHT_TYPES:
            raise ValueError(f"flight_type must be one of: {', '.join(_FLIGHT_TYPES)}")
        return v

    @field_validator('aircraft_category')
    @classmethod
    def mor_validate_aircraft_category(cls, v: str) -> str:
        if v not in _AIRCRAFT_CATEGORIES:
            raise ValueError(f"aircraft_category must be one of: {', '.join(_AIRCRAFT_CATEGORIES)}")
        return v

    @field_validator('reporter_role')
    @classmethod
    def mor_validate_reporter_role(cls, v: str) -> str:
        if v not in _REPORTER_ROLES:
            raise ValueError(f"reporter_role must be one of: {', '.join(_REPORTER_ROLES)}")
        return v

    @field_validator('human_factors')
    @classmethod
    def mor_validate_human_factors(cls, v: List[str]) -> List[str]:
        for hf in v:
            if hf not in _HUMAN_FACTORS:
                raise ValueError(f"human_factor '{hf}' must be one of: {', '.join(_HUMAN_FACTORS)}")
        return v

    @field_validator('aircraft_registration')
    @classmethod
    def mor_validate_registration(cls, v: str) -> str:
        return v.upper()

    @field_validator('investigation_status')
    @classmethod
    def mor_validate_investigation_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _INVESTIGATION_STATUSES:
            raise ValueError(f"investigation_status must be one of: {', '.join(_INVESTIGATION_STATUSES)}")
        return v

    @field_validator('narrative')
    @classmethod
    def mor_sanitize_narrative(cls, v: str) -> str:
        v = v.replace('<script>', '').replace('</script>', '')
        import re
        v = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[REDACTED_EMAIL]', v)
        v = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[REDACTED_PHONE]', v)
        return v


class AiAnalysisResult(BaseModel):
    occurrence_type: Optional[str] = None
    human_factors: List[str] = []
    risk_level: str = "High"
    phase_of_flight: Optional[str] = None
    confidence: float = 0.0
    summary: Optional[str] = None
    recommendations: List[str] = []
    mandatory_check: Optional[Dict[str, Any]] = None


class ReportResponse(BaseModel):
    id: str
    tenant_id: str
    report_type: ReportType
    status: ReportStatus
    ai_status: AiStatus
    narrative: str
    location: str
    occurrence_date: datetime
    created_by: str
    created_at: datetime
    updated_at: datetime
    is_anonymous: bool = False
    flight_number: Optional[str] = None
    aircraft_registration: Optional[str] = None
    occurrence_type: Optional[str] = None
    severity: Optional[str] = None
    investigation_status: Optional[str] = None
    severity_level: Optional[int] = None
    probability_level: Optional[int] = None
    risk_index: Optional[int] = None
    risk_level: Optional[str] = None
    risk_assessment: Optional[RiskAssessment] = None
    ai_suggested_assessment: Optional[AiSuggestedAssessment] = None
    ai_analysis: Optional[AiAnalysisResult] = None

    occurrence_class: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    country: Optional[str] = None

    aircraft_make: Optional[str] = None
    aircraft_model: Optional[str] = None
    aircraft_serial_number: Optional[str] = None
    operator: Optional[str] = None
    operator_icao: Optional[str] = None
    aircraft_category: Optional[str] = None
    engine_make: Optional[str] = None
    engine_model: Optional[str] = None
    engine_serial_number: Optional[str] = None

    flight_phase: Optional[str] = None
    flight_type: Optional[str] = None
    departure_airport: Optional[str] = None
    destination_airport: Optional[str] = None
    aircraft_utilisation_hours: Optional[float] = None
    aircraft_utilisation_cycles: Optional[int] = None

    crew_count: Optional[int] = None
    passenger_count: Optional[int] = None
    fatal_injuries: Optional[int] = None
    serious_injuries: Optional[int] = None
    minor_injuries: Optional[int] = None

    occurrence_category: Optional[str] = None
    human_factors: Optional[List[str]] = None
    contributing_factors: Optional[List[str]] = None
    investigation_agency: Optional[str] = None

    reporter_name: Optional[str] = None
    reporter_role: Optional[str] = None
    reporter_email: Optional[str] = None
    reporter_phone: Optional[str] = None
    reporter_organisation: Optional[str] = None
    reporting_date: Optional[datetime] = None

    etops: bool = False
    propeller_make: Optional[str] = None
    propeller_model: Optional[str] = None
    call_sign: Optional[str] = None
    organisation_comments: Optional[str] = None
    manufacturer_advised: bool = False
    fdr_data_retained: bool = False

    model_config = {"from_attributes": True}


class ReportListItem(BaseModel):
    id: str
    tenant_id: str
    report_type: ReportType
    status: ReportStatus
    ai_status: AiStatus
    location: str
    occurrence_date: datetime
    created_by: str
    created_at: datetime
    is_anonymous: bool
    occurrence_type: Optional[str] = None
    severity: Optional[str] = None
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None
    severity_level: Optional[int] = None
    probability_level: Optional[int] = None
    occurrence_category: Optional[str] = None
    aircraft_make: Optional[str] = None
    aircraft_model: Optional[str] = None
    operator: Optional[str] = None
    flight_phase: Optional[str] = None
