# ============================================================================
# FILE: db_models.py
# PATH: backend/app/db/db_models.py
# PURPOSE: SQLAlchemy 2.x ORM models mirroring backend/app/db/schema.sql
#          (the 15 relational tables) plus the v2 ICAO/HFACS RCA table set
#          used by the async HazardService created for self-async hazard
#          analysis. PRIMARY KEYs default to gen_random_uuid().
# ============================================================================

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid_pk():
    """Primary key column backed by the table's gen_random_uuid() default."""
    return mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


# ============================================================================
# 1. HAZARDS
# ============================================================================

SEVERITY_CHECK = CheckConstraint(
    "severity BETWEEN 1 AND 5", name="ck_hazards_severity"
)
PROBABILITY_CHECK = CheckConstraint(
    "probability BETWEEN 1 AND 5", name="ck_hazards_probability"
)
PRIORITY_HML_CHECK = CheckConstraint(
    "priority IN ('H', 'M', 'L')", name="ck_hazards_priority"
)


class Hazard(Base):
    __tablename__ = "hazards"

    id: Mapped[object] = _uuid_pk()
    hazard_id: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url: Mapped[object] = mapped_column(Text, nullable=True)

    adrep_category: Mapped[object] = mapped_column(Text, nullable=True)
    occurrence_type: Mapped[object] = mapped_column(Text, nullable=True)
    taxonomy: Mapped[str] = mapped_column(Text, nullable=False)
    taxonomy_specific: Mapped[object] = mapped_column(Text, nullable=True)
    consequence: Mapped[object] = mapped_column(Text, nullable=True)

    severity: Mapped[object] = mapped_column(Integer, nullable=True)
    probability: Mapped[object] = mapped_column(Integer, nullable=True)
    risk_index: Mapped[object] = mapped_column(Integer, nullable=True)
    risk_level: Mapped[object] = mapped_column(Text, nullable=True)
    risk_outcome: Mapped[object] = mapped_column(Text, nullable=True)
    tolerability_tier: Mapped[object] = mapped_column(Text, nullable=True)

    priority: Mapped[str] = mapped_column(Text, nullable=False, default="M")
    recommended_action: Mapped[object] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[object] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[object] = mapped_column(Text, nullable=True)
    assigned_to_uid: Mapped[object] = mapped_column(Text, nullable=True)
    department: Mapped[object] = mapped_column(Text, nullable=True)

    srm_conducted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    srm_date: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    srm_status: Mapped[object] = mapped_column(Text, nullable=True)
    analysis_mode: Mapped[str] = mapped_column(
        Text, nullable=False, default="FISHBONE_ONLY"
    )
    sram_data: Mapped[object] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False)
    follow_up_date: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[object] = mapped_column(Text, nullable=True)
    remarks: Mapped[object] = mapped_column(Text, nullable=True)

    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_by: Mapped[object] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        SEVERITY_CHECK,
        PROBABILITY_CHECK,
        PRIORITY_HML_CHECK,
        Index("ux_hazards_tenant_id", "tenant_id", "hazard_id", unique=True),
        Index("ix_hazards_tenant", "tenant_id"),
        Index("ix_hazards_tenant_status", "tenant_id", "status"),
        Index("ix_hazards_tenant_assignee", "tenant_id", "assigned_to"),
        Index("ix_hazards_tenant_created", "tenant_id", "created_at"),
        Index("idx_hazards_tenant_demo", "tenant_id", "is_demo"),
    )


# ============================================================================
# 2. REPORTS (VSR / MOR)
# ============================================================================

REPORT_TYPE_CHECK = CheckConstraint(
    "report_type IN ('voluntary', 'mandatory')", name="ck_reports_type"
)
REPORT_LEVEL_CHECK = CheckConstraint(
    "severity_level BETWEEN 1 AND 5", name="ck_reports_severity_level"
)
REPORT_PROB_CHECK = CheckConstraint(
    "probability_level BETWEEN 1 AND 5", name="ck_reports_probability_level"
)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)

    report_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    ai_status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING")

    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(Text, nullable=False)
    occurrence_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    flight_number: Mapped[object] = mapped_column(Text, nullable=True)
    aircraft_registration: Mapped[object] = mapped_column(Text, nullable=True)
    occurrence_type: Mapped[object] = mapped_column(Text, nullable=True)
    severity: Mapped[object] = mapped_column(Text, nullable=True)
    investigation_status: Mapped[object] = mapped_column(Text, nullable=True)

    severity_level: Mapped[object] = mapped_column(Integer, nullable=True)
    probability_level: Mapped[object] = mapped_column(Integer, nullable=True)
    risk_index: Mapped[object] = mapped_column(Integer, nullable=True)
    risk_level: Mapped[object] = mapped_column(Text, nullable=True)
    risk_assessment: Mapped[object] = mapped_column(JSONB, nullable=True)
    ai_suggested_assessment: Mapped[object] = mapped_column(JSONB, nullable=True)
    ai_analysis: Mapped[object] = mapped_column(JSONB, nullable=True)

    occurrence_class: Mapped[object] = mapped_column(Text, nullable=True)
    latitude: Mapped[object] = mapped_column(Float, nullable=True)
    longitude: Mapped[object] = mapped_column(Float, nullable=True)
    country: Mapped[object] = mapped_column(Text, nullable=True)

    aircraft_make: Mapped[object] = mapped_column(Text, nullable=True)
    aircraft_model: Mapped[object] = mapped_column(Text, nullable=True)
    aircraft_serial_number: Mapped[object] = mapped_column(Text, nullable=True)
    operator: Mapped[object] = mapped_column(Text, nullable=True)
    operator_icao: Mapped[object] = mapped_column(Text, nullable=True)
    aircraft_category: Mapped[object] = mapped_column(Text, nullable=True)
    engine_make: Mapped[object] = mapped_column(Text, nullable=True)
    engine_model: Mapped[object] = mapped_column(Text, nullable=True)
    engine_serial_number: Mapped[object] = mapped_column(Text, nullable=True)

    flight_phase: Mapped[object] = mapped_column(Text, nullable=True)
    flight_type: Mapped[object] = mapped_column(Text, nullable=True)
    departure_airport: Mapped[object] = mapped_column(Text, nullable=True)
    destination_airport: Mapped[object] = mapped_column(Text, nullable=True)
    aircraft_utilisation_hours: Mapped[object] = mapped_column(Float, nullable=True)
    aircraft_utilisation_cycles: Mapped[object] = mapped_column(Integer, nullable=True)

    crew_count: Mapped[object] = mapped_column(Integer, nullable=True)
    passenger_count: Mapped[object] = mapped_column(Integer, nullable=True)
    fatal_injuries: Mapped[object] = mapped_column(Integer, nullable=True)
    serious_injuries: Mapped[object] = mapped_column(Integer, nullable=True)
    minor_injuries: Mapped[object] = mapped_column(Integer, nullable=True)

    occurrence_category: Mapped[object] = mapped_column(Text, nullable=True)
    human_factors: Mapped[object] = mapped_column(JSONB, nullable=True)
    contributing_factors: Mapped[object] = mapped_column(JSONB, nullable=True)
    investigation_agency: Mapped[object] = mapped_column(Text, nullable=True)

    reporter_name: Mapped[object] = mapped_column(Text, nullable=True)
    reporter_role: Mapped[object] = mapped_column(Text, nullable=True)
    reporter_email: Mapped[object] = mapped_column(Text, nullable=True)
    reporter_phone: Mapped[object] = mapped_column(Text, nullable=True)
    reporter_organisation: Mapped[object] = mapped_column(Text, nullable=True)
    reporting_date: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)

    etops: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    propeller_make: Mapped[object] = mapped_column(Text, nullable=True)
    propeller_model: Mapped[object] = mapped_column(Text, nullable=True)
    call_sign: Mapped[object] = mapped_column(Text, nullable=True)
    organisation_comments: Mapped[object] = mapped_column(Text, nullable=True)
    manufacturer_advised: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    fdr_data_retained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        REPORT_TYPE_CHECK,
        REPORT_LEVEL_CHECK,
        REPORT_PROB_CHECK,
        Index("ix_reports_tenant", "tenant_id"),
        Index("ix_reports_tenant_status", "tenant_id", "status"),
        Index("ix_reports_tenant_occdate", "tenant_id", "occurrence_date"),
        Index("ix_reports_tenant_aircraft", "tenant_id", "aircraft_registration"),
        Index("ix_reports_tenant_created", "tenant_id", "created_at"),
        Index("idx_reports_tenant_demo", "tenant_id", "is_demo"),
    )


# ============================================================================
# 3. CANS
# ============================================================================

CAN_PRIORITY_CHECK = CheckConstraint(
    "priority IN ('High', 'Medium', 'Low')", name="ck_cans_priority"
)
CAN_SEVERITY_CHECK = CheckConstraint(
    "initial_severity BETWEEN 1 AND 5", name="ck_cans_initial_severity"
)
CAN_PROB_CHECK = CheckConstraint(
    "initial_probability BETWEEN 1 AND 5", name="ck_cans_initial_probability"
)
CAN_INDEX_CHECK = CheckConstraint(
    "initial_risk_index BETWEEN 1 AND 25", name="ck_cans_initial_risk_index"
)


class Can(Base):
    __tablename__ = "cans"

    id: Mapped[object] = _uuid_pk()
    can_reference: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)
    hazard_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hazards.id"), nullable=False
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    required_action: Mapped[str] = mapped_column(Text, nullable=False)

    issued_by: Mapped[str] = mapped_column(Text, nullable=False)
    issued_by_uid: Mapped[str] = mapped_column(Text, nullable=False)
    issued_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    target_completion_date: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    assigned_to: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_to_uid: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[object] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)

    copies_to: Mapped[object] = mapped_column(Text, nullable=True)
    requested_function: Mapped[object] = mapped_column(Text, nullable=True)
    addressed_function: Mapped[object] = mapped_column(Text, nullable=True)
    initial_severity: Mapped[object] = mapped_column(Integer, nullable=True)
    initial_probability: Mapped[object] = mapped_column(Integer, nullable=True)
    initial_risk_index: Mapped[object] = mapped_column(Integer, nullable=True)
    initial_risk_level: Mapped[object] = mapped_column(Text, nullable=True)
    initial_risk_outcome: Mapped[object] = mapped_column(Text, nullable=True)
    initial_tolerability_tier: Mapped[object] = mapped_column(Text, nullable=True)
    initial_sra: Mapped[object] = mapped_column(JSONB, nullable=True)
    classification_type: Mapped[object] = mapped_column(Text, nullable=True)
    classification_level: Mapped[object] = mapped_column(Text, nullable=True)

    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_by: Mapped[object] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        CAN_PRIORITY_CHECK,
        CAN_SEVERITY_CHECK,
        CAN_PROB_CHECK,
        CAN_INDEX_CHECK,
        Index("ux_cans_tenant_ref", "tenant_id", "can_reference", unique=True),
        Index("ix_cans_tenant", "tenant_id"),
        Index("ix_cans_tenant_status", "tenant_id", "status"),
        Index("ix_cans_tenant_assignee", "tenant_id", "assigned_to"),
        Index("ix_cans_hazard", "tenant_id", "hazard_id"),
        Index("idx_cans_tenant_demo", "tenant_id", "is_demo"),
    )


# ============================================================================
# 4. CAPS
# ============================================================================

CAP_RCA_METHOD_CHECK = CheckConstraint(
    "rca_method IN ('bow_tie', 'fishbone')", name="ck_caps_rca_method"
)
CAP_RESIDUAL_SEV_CHECK = CheckConstraint(
    "residual_severity BETWEEN 1 AND 5", name="ck_caps_residual_severity"
)
CAP_RESIDUAL_PROB_CHECK = CheckConstraint(
    "residual_probability BETWEEN 1 AND 5", name="ck_caps_residual_probability"
)
CAP_RESIDUAL_INDEX_CHECK = CheckConstraint(
    "residual_risk_index BETWEEN 1 AND 25", name="ck_caps_residual_risk_index"
)
CAP_AE_INTERVAL_CHECK = CheckConstraint(
    "ae_review_interval_days BETWEEN 1 AND 365", name="ck_caps_ae_review_interval"
)


class Cap(Base):
    __tablename__ = "caps"

    id: Mapped[object] = _uuid_pk()
    cap_reference: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)
    can_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("cans.id"), nullable=False
    )

    action_plan: Mapped[str] = mapped_column(Text, nullable=False)
    timeline: Mapped[str] = mapped_column(Text, nullable=False)
    resources_required: Mapped[str] = mapped_column(Text, nullable=False)
    implementation_plan: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[object] = mapped_column(Text, nullable=True)
    target_completion_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    submitted_by: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_by_uid: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by: Mapped[object] = mapped_column(Text, nullable=True)
    reviewed_by_uid: Mapped[object] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    review_comments: Mapped[object] = mapped_column(Text, nullable=True)
    revision_deadline: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    company_name: Mapped[object] = mapped_column(Text, nullable=True)
    base_location: Mapped[object] = mapped_column(Text, nullable=True)
    area_system_of_interest: Mapped[object] = mapped_column(Text, nullable=True)
    finding_number: Mapped[object] = mapped_column(Text, nullable=True)
    file_ref: Mapped[object] = mapped_column(Text, nullable=True)

    factual_review: Mapped[object] = mapped_column(Text, nullable=True)
    rca: Mapped[object] = mapped_column(Text, nullable=True)
    short_term_ca: Mapped[object] = mapped_column(Text, nullable=True)
    long_term_ca: Mapped[object] = mapped_column(Text, nullable=True)
    implementation_timeline: Mapped[object] = mapped_column(Text, nullable=True)

    managerial_approval: Mapped[object] = mapped_column(JSONB, nullable=True)
    caa_acceptance: Mapped[object] = mapped_column(JSONB, nullable=True)

    residual_severity: Mapped[object] = mapped_column(Integer, nullable=True)
    residual_probability: Mapped[object] = mapped_column(Integer, nullable=True)
    residual_risk_index: Mapped[object] = mapped_column(Integer, nullable=True)
    residual_risk_level: Mapped[object] = mapped_column(Text, nullable=True)
    residual_risk_outcome: Mapped[object] = mapped_column(Text, nullable=True)
    residual_tolerability_tier: Mapped[object] = mapped_column(Text, nullable=True)
    residual_sra: Mapped[object] = mapped_column(JSONB, nullable=True)

    root_causes: Mapped[object] = mapped_column(JSONB, nullable=True)
    action_items: Mapped[object] = mapped_column(JSONB, nullable=True)
    rca_method: Mapped[object] = mapped_column(Text, nullable=True)
    sram_data: Mapped[object] = mapped_column(JSONB, nullable=True)

    escalated_to_ae: Mapped[object] = mapped_column(Boolean, nullable=True)
    escalated_by: Mapped[object] = mapped_column(Text, nullable=True)
    escalated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    escalation_reason: Mapped[object] = mapped_column(Text, nullable=True)
    ae_signature: Mapped[object] = mapped_column(Text, nullable=True)
    ae_signed_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    ae_review_interval_days: Mapped[object] = mapped_column(Integer, nullable=True)
    ae_review_date: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)

    sag_sign: Mapped[object] = mapped_column(Text, nullable=True)
    sag_signed_by: Mapped[object] = mapped_column(Text, nullable=True)
    sag_signed_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    manager_approval: Mapped[object] = mapped_column(Text, nullable=True)
    ca_acceptance: Mapped[object] = mapped_column(Text, nullable=True)
    process_owner: Mapped[object] = mapped_column(Text, nullable=True)
    manager_confirmation: Mapped[object] = mapped_column(Text, nullable=True)
    closing_remarks: Mapped[object] = mapped_column(Text, nullable=True)
    closed_by: Mapped[object] = mapped_column(Text, nullable=True)
    closed_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_signature: Mapped[object] = mapped_column(Text, nullable=True)

    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        CAP_RCA_METHOD_CHECK,
        CAP_RESIDUAL_SEV_CHECK,
        CAP_RESIDUAL_PROB_CHECK,
        CAP_RESIDUAL_INDEX_CHECK,
        CAP_AE_INTERVAL_CHECK,
        Index("ux_caps_tenant_ref", "tenant_id", "cap_reference", unique=True),
        Index("ix_caps_tenant", "tenant_id"),
        Index("ix_caps_tenant_status", "tenant_id", "status"),
        Index("ix_caps_can", "tenant_id", "can_id"),
        Index("idx_caps_tenant_demo", "tenant_id", "is_demo"),
    )


# ============================================================================
# 5. SURVEYS (scored)
# ============================================================================

SURVEY_SCORE_CHECK = CheckConstraint("safety_policy BETWEEN 1 AND 5")
SURVEY_SRM_CHECK = CheckConstraint("safety_risk_management BETWEEN 1 AND 5")
SURVEY_SA_CHECK = CheckConstraint("safety_assurance BETWEEN 1 AND 5")
SURVEY_SP_CHECK = CheckConstraint("safety_promotion BETWEEN 1 AND 5")
SURVEY_OVERALL_CHECK = CheckConstraint("overall_sms_maturity BETWEEN 1 AND 5")


class Survey(Base):
    __tablename__ = "surveys"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    respondent_id: Mapped[object] = mapped_column(Text, nullable=True)
    department: Mapped[object] = mapped_column(Text, nullable=True)
    employee_category: Mapped[object] = mapped_column(Text, nullable=True)
    years_experience: Mapped[object] = mapped_column(Text, nullable=True)
    language_used: Mapped[object] = mapped_column(Text, nullable=True)
    survey_version: Mapped[str] = mapped_column(Text, nullable=False)
    seed_version: Mapped[object] = mapped_column(Text, nullable=True)

    answers: Mapped[object] = mapped_column(JSONB, nullable=False)
    question_scores: Mapped[object] = mapped_column(JSONB, nullable=True)
    element_scores: Mapped[object] = mapped_column(JSONB, nullable=True)

    safety_policy: Mapped[object] = mapped_column(Integer, nullable=True)
    safety_risk_management: Mapped[object] = mapped_column(Integer, nullable=True)
    safety_assurance: Mapped[object] = mapped_column(Integer, nullable=True)
    safety_promotion: Mapped[object] = mapped_column(Integer, nullable=True)
    overall_sms_maturity: Mapped[object] = mapped_column(Integer, nullable=True)
    overall_score_pct: Mapped[object] = mapped_column(Numeric(5, 2), nullable=True)

    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        SURVEY_SCORE_CHECK,
        SURVEY_SRM_CHECK,
        SURVEY_SA_CHECK,
        SURVEY_SP_CHECK,
        SURVEY_OVERALL_CHECK,
        Index("ix_surveys_tenant", "tenant_id"),
        Index("ix_surveys_tenant_date", "tenant_id", "submitted_at"),
        Index("ix_surveys_tenant_dept", "tenant_id", "department"),
        Index("idx_surveys_tenant_demo", "tenant_id", "is_demo"),
    )


# ============================================================================
# 6. SURVEY RESPONSES (raw)
# ============================================================================


class SurveyResponse(Base):
    __tablename__ = "survey_responses"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)

    respondent_id: Mapped[object] = mapped_column(Text, nullable=True)
    answers: Mapped[object] = mapped_column(JSONB, nullable=False)
    department: Mapped[object] = mapped_column(Text, nullable=True)
    employee_category: Mapped[object] = mapped_column(Text, nullable=True)
    years_experience: Mapped[object] = mapped_column(Text, nullable=True)
    language_used: Mapped[object] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    survey_version: Mapped[str] = mapped_column(Text, nullable=False)

    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_survey_responses_tenant", "tenant_id"),
        Index("ix_survey_responses_tenant_date", "tenant_id", "submitted_at"),
        Index("idx_survey_responses_tenant_demo", "tenant_id", "is_demo"),
    )


# ============================================================================
# 7. CORRECTIVE ACTIONS
# ============================================================================

CA_PRIORITY_CHECK = CheckConstraint(
    "priority IN ('High', 'Medium', 'Low')", name="ck_corrective_actions_priority"
)


class CorrectiveAction(Base):
    __tablename__ = "corrective_actions"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)

    hazard_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hazards.id"), nullable=True
    )
    can_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("cans.id"), nullable=True
    )
    event_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=True)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    action_plan: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(Text, nullable=False, default="Medium")

    assigned_to: Mapped[object] = mapped_column(Text, nullable=True)
    assigned_to_uid: Mapped[object] = mapped_column(Text, nullable=True)
    assigned_by: Mapped[object] = mapped_column(Text, nullable=True)
    assigned_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    target_completion_date: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)

    reviewed_by: Mapped[object] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    review_comments: Mapped[object] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    remarks: Mapped[object] = mapped_column(Text, nullable=True)

    created_by: Mapped[object] = mapped_column(Text, nullable=True)
    updated_by: Mapped[object] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        CA_PRIORITY_CHECK,
        Index("ix_corrective_actions_tenant", "tenant_id"),
        Index(
            "ix_corrective_actions_tenant_status", "tenant_id", "status"
        ),
        Index(
            "ix_corrective_actions_tenant_assignee", "tenant_id", "assigned_to"
        ),
        Index("ix_corrective_actions_hazard", "tenant_id", "hazard_id"),
        Index("ix_corrective_actions_can", "tenant_id", "can_id"),
    )


# ============================================================================
# 8. RISK REGISTER (per-hazard SRM)
# ============================================================================

RR_EXISTING_SEV_CHECK = CheckConstraint(
    "existing_severity BETWEEN 1 AND 5", name="ck_risk_register_existing_severity"
)
RR_EXISTING_PROB_CHECK = CheckConstraint(
    "existing_probability BETWEEN 1 AND 5", name="ck_risk_register_existing_probability"
)
RR_RESULTANT_SEV_CHECK = CheckConstraint(
    "resultant_severity BETWEEN 1 AND 5", name="ck_risk_register_resultant_severity"
)
RR_RESULTANT_PROB_CHECK = CheckConstraint(
    "resultant_probability BETWEEN 1 AND 5", name="ck_risk_register_resultant_probability"
)


class RiskRegisterEntry(Base):
    __tablename__ = "risk_register"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)
    hazard_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hazards.id"), nullable=False
    )

    srm_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ultimate_consequence: Mapped[str] = mapped_column(Text, nullable=False)

    existing_severity: Mapped[object] = mapped_column(Integer, nullable=True)
    existing_probability: Mapped[object] = mapped_column(Integer, nullable=True)
    existing_risk_index: Mapped[object] = mapped_column(Integer, nullable=True)
    existing_risk_tolerability: Mapped[object] = mapped_column(Text, nullable=True)

    resultant_severity: Mapped[object] = mapped_column(Integer, nullable=True)
    resultant_probability: Mapped[object] = mapped_column(Integer, nullable=True)
    resultant_risk_index: Mapped[object] = mapped_column(Integer, nullable=True)
    resultant_risk_tolerability: Mapped[object] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False)
    follow_up_date: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    date_completed: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    remarks: Mapped[object] = mapped_column(Text, nullable=True)
    concerned_department: Mapped[object] = mapped_column(Text, nullable=True)

    created_by: Mapped[object] = mapped_column(Text, nullable=True)
    updated_by: Mapped[object] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        RR_EXISTING_SEV_CHECK,
        RR_EXISTING_PROB_CHECK,
        RR_RESULTANT_SEV_CHECK,
        RR_RESULTANT_PROB_CHECK,
        Index("ix_risk_register_tenant", "tenant_id"),
        Index("ix_risk_register_tenant_status", "tenant_id", "status"),
        Index("ix_risk_register_tenant_hazard", "tenant_id", "hazard_id"),
        Index("ix_risk_register_tenant_srmdate", "tenant_id", "srm_date"),
    )


# ============================================================================
# 9. SAFETY DEFICIENCIES
# ============================================================================

SD_PRIORITY_CHECK = CheckConstraint(
    "priority IN ('H', 'M', 'L')", name="ck_safety_deficiencies_priority"
)
SD_SEVERITY_CHECK = CheckConstraint(
    "severity IN ('Low', 'Medium', 'High', 'Critical')",
    name="ck_safety_deficiencies_severity",
)


class SafetyDeficiency(Base):
    __tablename__ = "safety_deficiencies"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)

    event_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    hazard_code: Mapped[object] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    taxonomy_main: Mapped[object] = mapped_column(Text, nullable=True)
    taxonomy_type: Mapped[object] = mapped_column(Text, nullable=True)
    taxonomy_specific: Mapped[object] = mapped_column(Text, nullable=True)
    unsafe_event: Mapped[object] = mapped_column(Text, nullable=True)
    identified_hazard: Mapped[object] = mapped_column(Text, nullable=True)

    priority: Mapped[object] = mapped_column(Text, nullable=True)
    severity: Mapped[object] = mapped_column(Text, nullable=True)

    assigned_to: Mapped[object] = mapped_column(Text, nullable=True)
    assigned_to_uid: Mapped[object] = mapped_column(Text, nullable=True)
    assigned_by: Mapped[object] = mapped_column(Text, nullable=True)
    assigned_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    follow_up_date: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False)
    remarks: Mapped[object] = mapped_column(Text, nullable=True)
    csd_remarks: Mapped[object] = mapped_column(Text, nullable=True)

    created_by: Mapped[object] = mapped_column(Text, nullable=True)
    updated_by: Mapped[object] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        SD_PRIORITY_CHECK,
        SD_SEVERITY_CHECK,
        Index("ix_safety_deficiencies_tenant", "tenant_id"),
        Index("ix_safety_deficiencies_tenant_status", "tenant_id", "status"),
        Index(
            "ix_safety_deficiencies_tenant_assignee", "tenant_id", "assigned_to"
        ),
    )


# ============================================================================
# 10. FLIGHT DIVERSIONS
# ============================================================================


class FlightDiversion(Base):
    __tablename__ = "flight_diversions"

    id: Mapped[object] = _uuid_pk()
    diversion_id: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)

    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    flight_number: Mapped[str] = mapped_column(Text, nullable=False)
    aircraft_registration: Mapped[str] = mapped_column(Text, nullable=False)
    sector_from: Mapped[str] = mapped_column(Text, nullable=False)
    sector_to: Mapped[str] = mapped_column(Text, nullable=False)
    diverted_to: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reason_details: Mapped[object] = mapped_column(Text, nullable=True)
    captain: Mapped[object] = mapped_column(Text, nullable=True)
    first_officer: Mapped[object] = mapped_column(Text, nullable=True)
    air_hostess: Mapped[object] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    additional_fuel_cost: Mapped[object] = mapped_column(Numeric(12, 2), nullable=True)
    passenger_impact: Mapped[object] = mapped_column(Integer, nullable=True)
    delay_minutes: Mapped[object] = mapped_column(Integer, nullable=True)
    remarks: Mapped[object] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False)
    hazard_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hazards.id"), nullable=True
    )
    hazard_link_url: Mapped[object] = mapped_column(Text, nullable=True)

    created_by: Mapped[object] = mapped_column(Text, nullable=True)
    updated_by: Mapped[object] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index(
            "ux_flight_diversions_tenant_ref",
            "tenant_id",
            "diversion_id",
            unique=True,
        ),
        Index("ix_flight_diversions_tenant", "tenant_id"),
        Index("ix_flight_diversions_tenant_date", "tenant_id", "date"),
        Index("ix_flight_diversions_tenant_status", "tenant_id", "status"),
        Index("ix_flight_diversions_hazard", "tenant_id", "hazard_id"),
    )


# ============================================================================
# 11. VERIFICATIONS (CAP effectiveness)
# ============================================================================


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)
    hazard_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hazards.id"), nullable=False
    )
    cap_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("caps.id"), nullable=False
    )

    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    comments: Mapped[object] = mapped_column(Text, nullable=True)
    evidence: Mapped[object] = mapped_column(JSONB, nullable=True)
    verified_by: Mapped[str] = mapped_column(Text, nullable=False)
    verified_by_uid: Mapped[str] = mapped_column(Text, nullable=False)
    verification_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revision_deadline: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    revision_notes: Mapped[object] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_verifications_tenant", "tenant_id"),
        Index("ix_verifications_tenant_date", "tenant_id", "verification_date"),
        Index("ix_verifications_tenant_hazard", "tenant_id", "hazard_id"),
        Index("ix_verifications_tenant_cap", "tenant_id", "cap_id"),
    )


# ============================================================================
# 12. HAZARD CLOSURES
# ============================================================================


class Closure(Base):
    __tablename__ = "closures"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)
    hazard_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hazards.id"), nullable=False
    )

    lessons_learned: Mapped[object] = mapped_column(Text, nullable=True)
    recommendations: Mapped[object] = mapped_column(Text, nullable=True)
    approval_notes: Mapped[object] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by_uid: Mapped[str] = mapped_column(Text, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_closures_tenant", "tenant_id"),
        Index("ix_closures_tenant_hazard", "tenant_id", "hazard_id"),
    )


# ============================================================================
# 13. STATE RISK REGISTER (SSP)
# ============================================================================

SRR_INDEX_CHECK = CheckConstraint(
    "current_risk_index BETWEEN 1 AND 25", name="ck_state_risk_register_index"
)
SRR_QUARTER_CHECK = CheckConstraint(
    "quarter BETWEEN 1 AND 4", name="ck_state_risk_register_quarter"
)


class StateRiskRegisterEntry(Base):
    __tablename__ = "state_risk_register"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)

    icoc_category: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icao_reference: Mapped[object] = mapped_column(Text, nullable=True)
    current_risk_index: Mapped[object] = mapped_column(Integer, nullable=True)
    tolerability: Mapped[str] = mapped_column(Text, nullable=False)
    tolerability_tier: Mapped[object] = mapped_column(Text, nullable=True)
    level: Mapped[object] = mapped_column(Text, nullable=True)

    ssp_target: Mapped[object] = mapped_column(Float, nullable=True)
    actual_ssp_value: Mapped[object] = mapped_column(Float, nullable=True)
    risk_reduction_rate: Mapped[object] = mapped_column(Float, nullable=True)
    trend: Mapped[str] = mapped_column(Text, nullable=False)
    contributing_tenants: Mapped[object] = mapped_column(JSONB, nullable=True)

    quarter: Mapped[object] = mapped_column(Integer, nullable=True)
    year: Mapped[object] = mapped_column(Integer, nullable=True)

    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    updated_by: Mapped[object] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        SRR_INDEX_CHECK,
        SRR_QUARTER_CHECK,
        Index("ix_state_risk_register_tenant", "tenant_id"),
        Index(
            "ix_state_risk_register_tenant_period",
            "tenant_id",
            "year",
            "quarter",
        ),
        Index("idx_state_risk_register_tenant_demo", "tenant_id", "is_demo"),
    )


# ============================================================================
# 14. PSOE ASSESSMENTS
# ============================================================================


class PsoeAssessment(Base):
    __tablename__ = "psoe_assessments"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    department: Mapped[object] = mapped_column(Text, nullable=True)
    scope: Mapped[object] = mapped_column(Text, nullable=True)
    auditor_name: Mapped[object] = mapped_column(Text, nullable=True)
    assessor_email: Mapped[object] = mapped_column(Text, nullable=True)
    assessment_date: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    template_version: Mapped[str] = mapped_column(Text, nullable=False)

    responses: Mapped[object] = mapped_column(JSONB, nullable=False)
    component_scores: Mapped[object] = mapped_column(JSONB, nullable=True)
    overall_score_pct: Mapped[object] = mapped_column(Float, nullable=True)
    overall_level: Mapped[object] = mapped_column(Text, nullable=True)
    notes: Mapped[object] = mapped_column(Text, nullable=True)

    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_by: Mapped[object] = mapped_column(Text, nullable=True)
    created_by_uid: Mapped[object] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_psoe_assessments_tenant", "tenant_id"),
        Index("ix_psoe_assessments_tenant_status", "tenant_id", "status"),
        Index("ix_psoe_assessments_tenant_date", "tenant_id", "assessment_date"),
        Index("idx_psoe_assessments_tenant_demo", "tenant_id", "is_demo"),
    )


# ============================================================================
# 15. REGULATORY REPORTS
# ============================================================================

RR_TYPE_CHECK = CheckConstraint(
    "report_type IN ('quarterly', 'annual')", name="ck_regulatory_reports_type"
)


class RegulatoryReport(Base):
    __tablename__ = "regulatory_reports"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)

    report_type: Mapped[str] = mapped_column(Text, nullable=False)
    period: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[object] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[object] = mapped_column(JSONB, nullable=True)
    data: Mapped[object] = mapped_column(JSONB, nullable=True)
    generated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_by: Mapped[object] = mapped_column(Text, nullable=True)
    file_url: Mapped[object] = mapped_column(Text, nullable=True)

    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        RR_TYPE_CHECK,
        Index("ix_regulatory_reports_tenant", "tenant_id"),
        Index("ix_regulatory_reports_tenant_status", "tenant_id", "status"),
        Index(
            "ix_regulatory_reports_tenant_period",
            "tenant_id",
            "report_type",
            "year",
            "quarter",
        ),
        Index("ix_regulatory_reports_tenant_created", "tenant_id", "created_at"),
        Index("idx_regulatory_reports_tenant_demo", "tenant_id", "is_demo"),
    )


# ============================================================================
# V2 ICAO / HFACS RCA table set (async HazardService path).
# These backdocs are document-shaped: the resource_id column holds the
# business reference (HAZ-../rca_../asm_../capa_..), the parent link is the
# row UUID of the owning entry.
# ============================================================================


class HazardRcaEntry(Base):
    __tablename__ = "hazard_rca_entries"

    id: Mapped[object] = _uuid_pk()
    resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_reference_id: Mapped[object] = mapped_column(Text, nullable=True)
    functional_area: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="under_assessment")
    risk_summary: Mapped[object] = mapped_column(JSONB, nullable=True)
    hfacs_summary: Mapped[object] = mapped_column(JSONB, nullable=True)
    identified_by: Mapped[object] = mapped_column(JSONB, nullable=True)
    assigned_owner: Mapped[object] = mapped_column(JSONB, nullable=True)
    target_completion_date: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    closed_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "ux_hazard_rca_entries_tenant",
            "tenant_id",
            "resource_id",
            unique=True,
        ),
        Index("ix_hazard_rca_entries_tenant", "tenant_id"),
    )


class HazardRcaFactor(Base):
    __tablename__ = "hazard_rca_factors"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)
    entry_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hazard_rca_entries.id"), nullable=False
    )
    resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[object] = mapped_column(Integer, nullable=True)
    category: Mapped[object] = mapped_column(Text, nullable=True)
    subcategory: Mapped[object] = mapped_column(Text, nullable=True)
    nanocode: Mapped[object] = mapped_column(Text, nullable=True)
    definition: Mapped[object] = mapped_column(Text, nullable=True)
    contributing_narrative: Mapped[object] = mapped_column(Text, nullable=True)
    order_sequence: Mapped[object] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (Index("ix_hazard_rca_factors_tenant", "tenant_id"),)


class HazardAssessment(Base):
    __tablename__ = "hazard_assessments"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)
    entry_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hazard_rca_entries.id"), nullable=False
    )
    resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    assessment_type: Mapped[object] = mapped_column(Text, nullable=True)
    severity: Mapped[object] = mapped_column(JSONB, nullable=True)
    probability: Mapped[object] = mapped_column(JSONB, nullable=True)
    risk_index: Mapped[object] = mapped_column(Text, nullable=True)
    tolerability: Mapped[object] = mapped_column(Text, nullable=True)
    assessed_by: Mapped[object] = mapped_column(Text, nullable=True)
    assessed_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (Index("ix_hazard_assessments_tenant", "tenant_id"),)


class HazardCapa(Base):
    __tablename__ = "hazard_capas"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)
    entry_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hazard_rca_entries.id"), nullable=False
    )
    resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[object] = mapped_column(Text, nullable=True)
    implemented_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[object] = mapped_column(Text, nullable=True)
    data: Mapped[object] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (Index("ix_hazard_capas_tenant", "tenant_id"),)