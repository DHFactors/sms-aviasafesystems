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
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
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
TAXONOMY_ICAO_CHECK = CheckConstraint(
    "taxonomy IN ('Organizational', 'Technical', 'Human', 'Environmental')",
    name="ck_hazards_taxonomy",
)


class Hazard(Base):
    __tablename__ = "hazards"

    id: Mapped[object] = _uuid_pk()
    hazard_id: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)

    function: Mapped[str] = mapped_column(Text, nullable=False, default="GEN")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url: Mapped[object] = mapped_column(Text, nullable=True)

    adrep_category: Mapped[object] = mapped_column(Text, nullable=True)
    occurrence_type: Mapped[object] = mapped_column(Text, nullable=True)
    taxonomy: Mapped[str] = mapped_column(Text, nullable=False)
    taxonomy_specific: Mapped[object] = mapped_column(Text, nullable=True)
    threat: Mapped[object] = mapped_column(Text, nullable=True)
    consequence: Mapped[object] = mapped_column(Text, nullable=True)
    top_event: Mapped[object] = mapped_column(Text, nullable=True)

    severity: Mapped[object] = mapped_column(Integer, nullable=True)
    probability: Mapped[object] = mapped_column(Integer, nullable=True)
    risk_index: Mapped[object] = mapped_column(Integer, nullable=True)
    risk_level: Mapped[object] = mapped_column(Text, nullable=True)
    risk_outcome: Mapped[object] = mapped_column(Text, nullable=True)
    tolerability_tier: Mapped[object] = mapped_column(Text, nullable=True)

    priority: Mapped[str] = mapped_column(Text, nullable=False, default="M")
    recommended_action: Mapped[object] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[object] = mapped_column(Text, nullable=True)
    corrective_action_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    srm_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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
    priority_date: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    status_date: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
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
        TAXONOMY_ICAO_CHECK,
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
    psoe_assessment_id: Mapped[object] = mapped_column(Text, nullable=True)

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

    po_signature: Mapped[object] = mapped_column(JSONB, nullable=True)
    po_signature_name: Mapped[object] = mapped_column(Text, nullable=True)
    po_signature_timestamp: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    po_signature_image_url: Mapped[object] = mapped_column(Text, nullable=True)
    po_signature_hash: Mapped[object] = mapped_column(Text, nullable=True)
    po_signature_verified: Mapped[bool] = mapped_column(Boolean, nullable=True)
    ma_signature: Mapped[object] = mapped_column(JSONB, nullable=True)
    ma_signature_name: Mapped[object] = mapped_column(Text, nullable=True)
    ma_signature_timestamp: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    ma_signature_image_url: Mapped[object] = mapped_column(Text, nullable=True)
    ma_signature_hash: Mapped[object] = mapped_column(Text, nullable=True)
    ma_signature_verified: Mapped[bool] = mapped_column(Boolean, nullable=True)

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
# 14a. PSOE QUESTIONS (ICAO Annex 19 / CAAN Appendix 10 checklist)
# ============================================================================

PSOE_COMPONENT_CHECK = CheckConstraint(
    "component IN ('Safety Management', 'Risk Management', 'Safety Assurance', 'Safety Promotion')",
    name="ck_psoe_questions_component",
)


class PsoeQuestion(Base):
    __tablename__ = "psoe_questions"

    id: Mapped[object] = _uuid_pk()
    component: Mapped[str] = mapped_column(Text, nullable=False)
    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        PSOE_COMPONENT_CHECK,
        Index("ix_psoe_questions_component", "component"),
        Index("uq_psoe_questions_component_number", "component", "question_number", unique=True),
    )


# ============================================================================
# 14b. PSOE FINDINGS (linked to psoe_assessments)
# ============================================================================

PSOE_FINDING_TYPE_CHECK = CheckConstraint(
    "finding_type IN ('Observation', 'Finding', 'Major Finding', 'Critical Finding')",
    name="ck_psoe_findings_type",
)

PSOE_FINDING_STATUS_CHECK = CheckConstraint(
    "status IN ('open', 'in_progress', 'closed')", name="ck_psoe_findings_status"
)


class PsoeFinding(Base):
    __tablename__ = "psoe_findings"

    id: Mapped[object] = _uuid_pk()
    assessment_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("psoe_assessments.id", ondelete="CASCADE"), nullable=False
    )

    finding_type: Mapped[object] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    corrective_action: Mapped[object] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    target_date: Mapped[object] = mapped_column(Date, nullable=True)
    closed_date: Mapped[object] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        PSOE_FINDING_TYPE_CHECK,
        PSOE_FINDING_STATUS_CHECK,
        Index("ix_psoe_findings_assessment", "assessment_id"),
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


# ============================================================================
# 17. SRAM - BOW-TIE ANALYSIS + RISK / BARRIER REGISTERS
# ============================================================================

BOW_TIE_STATUS_CHECK = CheckConstraint(
    "status IN ('In Progress', 'Assessed', 'Accepted', 'Rejected')",
    name="ck_bow_tie_analyses_status",
)
SEVERITY_LETTER_CHECK = CheckConstraint(
    "severity_level IN ('A', 'B', 'C', 'D', 'E')",
    name="ck_bow_tie_consequences_severity",
)
CONTROL_TYPE_CHECK = CheckConstraint(
    "control_type IN ('preventive', 'recovery')",
    name="ck_bow_tie_controls_type",
)
RISK_REGISTER_STATUS_CHECK = CheckConstraint(
    "status IN ('open', 'in_progress', 'closed')",
    name="ck_risk_register_status",
)
BARRIER_TYPE_CHECK = CheckConstraint(
    "barrier_type IN ('preventive', 'recovery')",
    name="ck_barrier_register_type",
)
BARRIER_IMPL_STATUS_CHECK = CheckConstraint(
    "implementation_status IN ('not_started', 'in_progress', 'implemented', 'verified')",
    name="ck_barrier_register_impl_status",
)
SEVERITY_CURRENT_CHECK = CheckConstraint(
    "severity_current IN ('A', 'B', 'C', 'D', 'E')",
    name="ck_risk_register_severity_current",
)
SEVERITY_RESULTANT_CHECK = CheckConstraint(
    "severity_resultant IS NULL OR severity_resultant IN ('A', 'B', 'C', 'D', 'E')",
    name="ck_risk_register_severity_resultant",
)


class BowTieAnalysis(Base):
    __tablename__ = "bow_tie_analyses"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)
    hazard_id: Mapped[str] = mapped_column(Text, nullable=False)
    hazard_title: Mapped[object] = mapped_column(Text, nullable=True)
    top_event: Mapped[object] = mapped_column(Text, nullable=True)
    description: Mapped[object] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="In Progress")
    created_by: Mapped[object] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        BOW_TIE_STATUS_CHECK,
        Index("ux_bow_tie_analyses_tenant_hazard", "tenant_id", "hazard_id", unique=True),
        Index("ix_bow_tie_analyses_tenant", "tenant_id"),
    )


class BowTieThreat(Base):
    __tablename__ = "bow_tie_threats"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)
    bowtie_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bow_tie_analyses.id", ondelete="CASCADE"), nullable=False
    )
    threat: Mapped[str] = mapped_column(Text, nullable=False)
    probability: Mapped[object] = mapped_column(Integer, nullable=True)
    threat_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ux_bow_tie_threats_order", "bowtie_id", "threat_order", unique=True),
        Index("ix_bow_tie_threats_tenant", "tenant_id"),
    )


class BowTieConsequence(Base):
    __tablename__ = "bow_tie_consequences"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)
    bowtie_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bow_tie_analyses.id", ondelete="CASCADE"), nullable=False
    )
    consequence: Mapped[str] = mapped_column(Text, nullable=False)
    severity_level: Mapped[str] = mapped_column(Text, nullable=False, default="C")
    consequence_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        SEVERITY_LETTER_CHECK,
        Index("ux_bow_tie_consequences_order", "bowtie_id", "consequence_order", unique=True),
        Index("ix_bow_tie_consequences_tenant", "tenant_id"),
    )


class BowTieControl(Base):
    __tablename__ = "bow_tie_controls"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)
    bowtie_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bow_tie_analyses.id", ondelete="CASCADE"), nullable=False
    )
    control: Mapped[str] = mapped_column(Text, nullable=False)
    control_type: Mapped[str] = mapped_column(Text, nullable=False)
    control_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    owner: Mapped[object] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="Planned")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        CONTROL_TYPE_CHECK,
        Index("ux_bow_tie_controls_order", "bowtie_id", "control_type", "control_order", unique=True),
        Index("ix_bow_tie_controls_tenant", "tenant_id"),
    )


class RiskRegisterEntry(Base):
    __tablename__ = "risk_register"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)
    bowtie_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bow_tie_analyses.id", ondelete="SET NULL"), nullable=True
    )
    hazard_id: Mapped[str] = mapped_column(Text, nullable=False)
    hazard_title: Mapped[object] = mapped_column(Text, nullable=True)
    probability_current: Mapped[int] = mapped_column(Integer, nullable=False)
    severity_current: Mapped[str] = mapped_column(Text, nullable=False)
    risk_index_current: Mapped[str] = mapped_column(Text, nullable=False)
    tolerability_current: Mapped[str] = mapped_column(Text, nullable=False)
    probability_resultant: Mapped[object] = mapped_column(Integer, nullable=True)
    severity_resultant: Mapped[object] = mapped_column(Text, nullable=True)
    risk_index_resultant: Mapped[object] = mapped_column(Text, nullable=True)
    tolerability_resultant: Mapped[object] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    alarp_justification: Mapped[object] = mapped_column(Text, nullable=True)
    accepted_by: Mapped[object] = mapped_column(Text, nullable=True)
    accepted_on: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    review_date: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        RISK_REGISTER_STATUS_CHECK,
        SEVERITY_CURRENT_CHECK,
        SEVERITY_RESULTANT_CHECK,
        Index("ux_risk_register_tenant_hazard", "tenant_id", "hazard_id", unique=True),
        Index("ix_risk_register_tenant", "tenant_id"),
        {"extend_existing": True},
    )


class BarrierRegisterEntry(Base):
    __tablename__ = "barrier_register"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Uuid(as_uuid=True), nullable=False)
    bowtie_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bow_tie_analyses.id", ondelete="SET NULL"), nullable=True
    )
    control_id: Mapped[object] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bow_tie_controls.id", ondelete="SET NULL"), nullable=True
    )
    hazard_id: Mapped[str] = mapped_column(Text, nullable=False)
    barrier: Mapped[str] = mapped_column(Text, nullable=False)
    barrier_type: Mapped[str] = mapped_column(Text, nullable=False)
    effectiveness: Mapped[object] = mapped_column(Integer, nullable=True)
    cost_benefit: Mapped[object] = mapped_column(Integer, nullable=True)
    practicality: Mapped[object] = mapped_column(Integer, nullable=True)
    acceptability: Mapped[object] = mapped_column(Integer, nullable=True)
    enforceability: Mapped[object] = mapped_column(Integer, nullable=True)
    durability: Mapped[object] = mapped_column(Integer, nullable=True)
    disinclination: Mapped[object] = mapped_column(Integer, nullable=True)
    bsv: Mapped[object] = mapped_column(Float, nullable=True)
    implementation_status: Mapped[str] = mapped_column(Text, nullable=False, default="not_started")
    action_by: Mapped[object] = mapped_column(Text, nullable=True)
    follow_up_date: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[object] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        BARRIER_TYPE_CHECK,
        BARRIER_IMPL_STATUS_CHECK,
        Index("ix_barrier_register_tenant", "tenant_id"),
        Index("ix_barrier_register_tenant_hazard", "tenant_id", "hazard_id"),
    )


# ============================================================================
# F/M. DOMAIN TABLES (Firestore → Postgres migration, Batch 0)
#
# Schemaless Firestore documents are stored wholesale in `data` (JSONB) so the
# one-time migration script preserves every original field; frequently queried
# fields are promoted to typed columns as consumers migrate (Batches 1-4).
#
# `tenants` is the master reference: its primary key is the deterministic
# uuid5 of the tenant slug (app/db/ids.py tenant_uuid), matching the
# `tenant_id` UUID columns already used across the operational tables.
# ============================================================================

DEFAULT_JSONB = text("'{}'::jsonb")


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Text, nullable=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[object] = mapped_column(Text, nullable=True)
    icao: Mapped[object] = mapped_column(Text, nullable=True)
    country: Mapped[object] = mapped_column(Text, nullable=True)
    regulator_id: Mapped[object] = mapped_column(Text, nullable=True)
    status: Mapped[object] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_beta_sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[object] = mapped_column(Boolean, nullable=True, default=True)
    auto_expire_days: Mapped[object] = mapped_column(Integer, nullable=True)
    safety_manager: Mapped[object] = mapped_column(JSONB, nullable=True)
    contact_id: Mapped[object] = mapped_column(Text, nullable=True)
    contact_name: Mapped[object] = mapped_column(Text, nullable=True)
    contact_email: Mapped[object] = mapped_column(Text, nullable=True)
    contact_phone: Mapped[object] = mapped_column(Text, nullable=True)
    contact_title: Mapped[object] = mapped_column(Text, nullable=True)
    contact_created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    oversight_level: Mapped[object] = mapped_column(Text, nullable=True)
    oversight_effective_date: Mapped[object] = mapped_column(Date, nullable=True)
    module_access: Mapped[object] = mapped_column(JSONB, nullable=True)
    modules: Mapped[object] = mapped_column(JSONB, nullable=True)
    data: Mapped[object] = mapped_column(JSONB, server_default=DEFAULT_JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_tenants_status", "status"),
        Index("ix_tenants_demo", "is_demo"),
    )


class Regulator(Base):
    __tablename__ = "regulators"

    id: Mapped[object] = _uuid_pk()
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[object] = mapped_column(Text, nullable=True)
    regulator_type: Mapped[object] = mapped_column(Text, nullable=True)
    display_name: Mapped[object] = mapped_column(Text, nullable=True)
    operator_tenant_ids: Mapped[object] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_saas_customer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    module_access: Mapped[object] = mapped_column(JSONB, server_default=text("'{\"module_1\":false,\"module_2\":false,\"module_3\":false}'::jsonb"))
    subscription_status: Mapped[object] = mapped_column(Text, nullable=True, default="inactive")
    subscription_start: Mapped[object] = mapped_column(Date, nullable=True)
    subscription_end: Mapped[object] = mapped_column(Date, nullable=True)
    data: Mapped[object] = mapped_column(JSONB, server_default=DEFAULT_JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class UserProfile(Base):
    __tablename__ = "users"

    uid: Mapped[str] = mapped_column(Text, primary_key=True)
    email: Mapped[object] = mapped_column(Text, nullable=True)
    display_name: Mapped[object] = mapped_column(Text, nullable=True)
    role: Mapped[object] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[object] = mapped_column(Text, nullable=True)
    department: Mapped[object] = mapped_column(Text, nullable=True)
    phone: Mapped[object] = mapped_column(Text, nullable=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    claims: Mapped[object] = mapped_column(JSONB, nullable=True)
    data: Mapped[object] = mapped_column(JSONB, server_default=DEFAULT_JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_tenant", "tenant_id"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[object] = _uuid_pk()
    action: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[object] = mapped_column(Text, nullable=True)
    target: Mapped[object] = mapped_column(Text, nullable=True)
    target_type: Mapped[object] = mapped_column(Text, nullable=True)
    target_id: Mapped[object] = mapped_column(Text, nullable=True)
    detail: Mapped[object] = mapped_column(Text, nullable=True)
    result: Mapped[object] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[object] = mapped_column(Text, nullable=True)
    ip: Mapped[object] = mapped_column(Text, nullable=True)
    request_id: Mapped[object] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[object] = mapped_column(JSONB, server_default=DEFAULT_JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_audit_logs_tenant", "tenant_id"),
        Index("ix_audit_logs_created", "created_at"),
    )


class SmsDispatch(Base):
    __tablename__ = "sms_dispatches"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[object] = mapped_column(Text, nullable=True)
    status: Mapped[object] = mapped_column(Text, nullable=True)
    data: Mapped[object] = mapped_column(JSONB, server_default=DEFAULT_JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_sms_dispatches_tenant", "tenant_id"),
        Index("ix_sms_dispatches_created", "created_at"),
    )


class AuditDispatch(Base):
    __tablename__ = "audit_dispatches"

    audit_id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id: Mapped[object] = mapped_column(Text, nullable=True)
    regulator_id: Mapped[object] = mapped_column(Text, nullable=True)
    status: Mapped[object] = mapped_column(Text, nullable=True)
    data: Mapped[object] = mapped_column(JSONB, server_default=DEFAULT_JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_audit_dispatches_tenant", "tenant_id"),
        Index("ix_audit_dispatches_regulator", "regulator_id"),
        Index("ix_audit_dispatches_created", "created_at"),
        Index("ix_audit_dispatches_status", "status"),
    )


class Invite(Base):
    __tablename__ = "invites"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id: Mapped[object] = mapped_column(Text, nullable=True)
    email: Mapped[object] = mapped_column(Text, nullable=True)
    role: Mapped[object] = mapped_column(Text, nullable=True)
    status: Mapped[object] = mapped_column(Text, nullable=True)
    data: Mapped[object] = mapped_column(JSONB, server_default=DEFAULT_JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_invites_tenant", "tenant_id"),)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[object] = _uuid_pk()
    email: Mapped[object] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[object] = mapped_column(Text, nullable=True)
    category: Mapped[object] = mapped_column(Text, nullable=True)
    data: Mapped[object] = mapped_column(JSONB, server_default=DEFAULT_JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_feedback_tenant", "tenant_id"),
        Index("ix_feedback_created", "created_at"),
    )


class CaanReport(Base):
    __tablename__ = "caan_reports"

    id: Mapped[object] = _uuid_pk()
    report_id: Mapped[object] = mapped_column(Text, nullable=True, unique=True)
    tenant_id: Mapped[object] = mapped_column(Text, nullable=True)
    data: Mapped[object] = mapped_column(JSONB, server_default=DEFAULT_JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_caan_reports_tenant", "tenant_id"),
        Index("ix_caan_reports_created", "created_at"),
    )


class SmsMaturity(Base):
    __tablename__ = "sms_maturity"

    id: Mapped[object] = _uuid_pk()
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    days: Mapped[object] = mapped_column(Integer, nullable=True)
    data: Mapped[object] = mapped_column(JSONB, server_default=DEFAULT_JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "days", name="ux_sms_maturity_tenant_days"),
        Index("ix_sms_maturity_tenant", "tenant_id"),
    )


class StateRiskCategory(Base):
    __tablename__ = "state_risk_categories"

    slug: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[object] = mapped_column(Text, nullable=True)
    data: Mapped[object] = mapped_column(JSONB, server_default=DEFAULT_JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class DeadLetterEntry(Base):
    __tablename__ = "dead_letter_queue"

    id: Mapped[object] = _uuid_pk()
    key: Mapped[object] = mapped_column(Text, nullable=True, unique=True)
    status: Mapped[object] = mapped_column(Text, nullable=True)
    data: Mapped[object] = mapped_column(JSONB, server_default=DEFAULT_JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_dead_letter_queue_created", "created_at"),
        Index("ix_dead_letter_queue_status", "status"),
    )