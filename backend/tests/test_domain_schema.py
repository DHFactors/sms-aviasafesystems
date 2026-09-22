# ============================================================================
# Tests for the Firestore → Postgres migration schema (Batch 0): the domain
# SQLAlchemy models (app/db/db_models.py) and the idempotent DDL that
# materialises them (app/db/schema_init.py).
# ============================================================================

import pytest

from app.db import db_models
from app.db.schema_init import _DOMAIN_DDL, _MODULE_B_DDL, _MODULE_C_DDL


def _table(name):
    return db_models.Base.metadata.tables.get(name)


@pytest.mark.parametrize(
    "table,key_col,unique_cols",
    [
        ("tenants", "id", ["slug"]),
        ("regulators", "id", ["slug"]),
        ("users", "uid", []),
        ("audit_logs", "id", []),
        ("sms_dispatches", "id", []),
        ("invites", "id", ["code"]),
        ("feedback", "id", []),
        ("caan_reports", "id", []),
        ("sms_maturity", "id", []),
        ("state_risk_categories", "slug", []),
        ("dead_letter_queue", "id", []),
    ],
)
def test_domain_model_registered(table, key_col, unique_cols):
    t = _table(table)
    assert t is not None, f"table {table} missing from db_models"
    assert key_col in t.columns
    for col in unique_cols:
        assert t.columns[col].unique is True


@pytest.mark.parametrize(
    "table,jsonb_cols",
    [
        ("tenants", ["safety_manager", "data"]),
        ("regulators", ["operator_tenant_ids", "data"]),
        # users flatten claims/data into first-class columns; no JSONB bags remain
        ("users", []),
        ("audit_logs", ["metadata_json"]),
        ("sms_dispatches", ["data"]),
        ("invites", []),
        ("feedback", []),
        ("caan_reports", ["data"]),
        ("sms_maturity", []),
        ("state_risk_categories", ["data"]),
        ("dead_letter_queue", ["data"]),
    ],
)
def test_domain_models_capture_json_document(table, jsonb_cols):
    t = _table(table)
    assert t is not None
    for col in jsonb_cols:
        assert col in t.columns, f"{table}.{col} missing"


@pytest.mark.parametrize(
    "table",
    ["tenants", "regulators", "users", "audit_logs", "sms_dispatches",
     "invites", "feedback", "caan_reports", "sms_maturity",
     "state_risk_categories", "dead_letter_queue"],
)
def test_domain_ddl_covers_every_model(table):
    ddl = "\n".join(_DOMAIN_DDL).lower()
    assert f"create table if not exists {table} " in ddl


def test_domain_models_are_collectible():
    models = [
        db_models.Tenant,
        db_models.Regulator,
        db_models.UserProfile,
        db_models.AuditLog,
        db_models.SmsDispatch,
        db_models.Invite,
        db_models.Feedback,
        db_models.CaanReport,
        db_models.SmsMaturity,
        db_models.StateRiskCategory,
        db_models.DeadLetterEntry,
    ]
    assert list(db_models.Base.metadata.sorted_tables)
    for m in models:
        assert m.__tablename__
        assert m.__table__ is not None


@pytest.mark.parametrize("table", ["invites", "feedback", "sms_maturity"])
def test_domain_models_tenant_fk_to_tenants(table):
    t = _table(table)
    assert t is not None
    col = t.columns.get("tenant_id")
    assert col is not None, f"{table}.tenant_id missing"
    assert col.foreign_keys, f"{table}.tenant_id has no FK"
    refs = {fk.column.table.name for fk in col.foreign_keys}
    assert "tenants" in refs, f"{table}.tenant_id must FK to tenants.id"


def test_sms_maturity_level_check_constraint():
    t = _table("sms_maturity")
    c = next(
        (c for c in t.constraints if getattr(c, "name", None) == "sms_maturity_level_check"),
        None,
    )
    assert c is not None
    assert "BETWEEN 1 AND 5" in str(c.sqltext)


def test_feedback_rating_check_constraint():
    t = _table("feedback")
    c = next(
        (c for c in t.constraints if getattr(c, "name", None) == "feedback_rating_check"),
        None,
    )
    assert c is not None
    assert "BETWEEN 1 AND 5" in str(c.sqltext)


@pytest.mark.parametrize(
    "col",
    [
        "tenant_id", "assessment_date", "overall_score", "level",
        "pillar_scores", "element_scores", "gap_analysis", "recommendations",
        "created_at", "updated_at",
    ],
)
def test_sms_maturity_live_columns_present(col):
    t = _table("sms_maturity")
    assert col in t.columns, f"sms_maturity.{col} missing from the live shape"


@pytest.mark.parametrize("col", ["days", "data"])
def test_sms_maturity_legacy_columns_dropped(col):
    t = _table("sms_maturity")
    assert col not in t.columns, f"sms_maturity.{col} is a legacy column"


# ============================================================================
# Module B — Phase 1 schema (P1-4..P1-19)
# ============================================================================

MODULE_B_PHASE1_TABLES = [
    "hazard_triage", "import_batches", "import_rows", "import_mappings",
    "import_links", "sag_meetings", "srb_meetings", "action_items",
    "safety_communications",
]


@pytest.mark.parametrize("table", MODULE_B_PHASE1_TABLES)
def test_module_b_phase1_tables_registered(table):
    t = _table(table)
    assert t is not None, f"table {table} missing from db_models"
    assert "id" in t.columns
    assert "tenant_id" in t.columns


@pytest.mark.parametrize("table", MODULE_B_PHASE1_TABLES)
def test_module_b_ddl_creates_table(table):
    ddl = "\n".join(_MODULE_B_DDL).lower()
    assert f"create table if not exists {table} " in ddl


@pytest.mark.parametrize(
    "col",
    [
        "identified_at", "first_priority_at", "equipment", "imported_at",
        "import_batch_id", "original_row_ref", "legacy_hazard_code",
        "enrichment_data", "enrichment_sources",
    ],
)
def test_hazards_phase1_columns_present(col):
    assert col in _table("hazards").columns, f"hazards.{col} missing"


@pytest.mark.parametrize(
    "col",
    [
        "regulatory_category", "regulatory_deadline_at",
        "regulatory_submitted_at", "regulatory_submission_ref",
    ],
)
def test_reports_regulatory_columns_present(col):
    assert col in _table("reports").columns, f"reports.{col} missing"


@pytest.mark.parametrize(
    "col",
    [
        "process_by", "process_signed_at", "initial_authority",
        "resultant_authority", "consequence_id",
    ],
)
def test_sram_phase1_columns_present(col):
    assert col in _table("sram_risk_register").columns, f"sram.{col} missing"


def test_hazards_status_check_constraint():
    t = _table("hazards")
    c = next(
        (c for c in t.constraints if getattr(c, "name", None) == "ck_hazards_status"),
        None,
    )
    assert c is not None
    text = str(c.sqltext)
    assert "Open" in text and "Reopened" in text


def test_reports_regulatory_category_check_constraint():
    t = _table("reports")
    c = next(
        (c for c in t.constraints
         if getattr(c, "name", None) == "ck_reports_regulatory_category"),
        None,
    )
    assert c is not None
    assert "'A'" in str(c.sqltext)


def test_sram_unique_key_includes_consequence():
    t = _table("sram_risk_register")
    names = {i.name for i in t.indexes}
    assert "ux_sram_risk_register_tenant_hazard_consequence" in names
    assert "ux_sram_risk_register_tenant_hazard" not in names


def test_sram_consequence_fk_to_bow_tie_consequences():
    t = _table("sram_risk_register")
    col = t.columns.get("consequence_id")
    assert col is not None and col.foreign_keys
    refs = {fk.column.table.name for fk in col.foreign_keys}
    assert "bow_tie_consequences" in refs


def test_hazards_import_batch_fk_to_import_batches():
    t = _table("hazards")
    col = t.columns.get("import_batch_id")
    assert col is not None and col.foreign_keys
    refs = {fk.column.table.name for fk in col.foreign_keys}
    assert "import_batches" in refs


# ============================================================================
# Module C — Phase 1 schema (P1-20..P1-28)
# ============================================================================

MODULE_C_PHASE1_TABLES = [
    "module_c_aggregates",
    "state_safety_performance_targets",
    "metric_definitions",
    "taxonomy_mappings",
]


@pytest.mark.parametrize("table", MODULE_C_PHASE1_TABLES)
def test_module_c_phase1_tables_registered(table):
    t = _table(table)
    assert t is not None, f"table {table} missing from db_models"
    assert "id" in t.columns


@pytest.mark.parametrize("table", MODULE_C_PHASE1_TABLES)
def test_module_c_ddl_creates_table(table):
    ddl = "\n".join(_MODULE_C_DDL).lower()
    assert f"create table if not exists {table} " in ddl


@pytest.mark.parametrize(
    "col",
    [
        "tenant_id", "metric_type", "metric_key", "period_start", "period_end",
        "payload", "computed_at", "ttl_seconds", "source_version",
    ],
)
def test_module_c_aggregates_columns_present(col):
    assert col in _table("module_c_aggregates").columns, f"aggregates.{col} missing"


@pytest.mark.parametrize(
    "col",
    [
        "spi_definition_id", "target_value", "target_period", "set_by", "set_at",
        "approved_by", "approved_at", "valid_from", "valid_to",
    ],
)
def test_state_spt_columns_present(col):
    assert col in _table("state_safety_performance_targets").columns, f"state_spt.{col} missing"


@pytest.mark.parametrize(
    "col", ["metric_type", "metric_key", "window_type", "window_days", "min_periods"]
)
def test_metric_definitions_columns_present(col):
    assert col in _table("metric_definitions").columns, f"metric_definitions.{col} missing"


@pytest.mark.parametrize(
    "col", ["icao_code", "adrep_code", "hfacs_nanocode", "nhrc_category"]
)
def test_taxonomy_mappings_columns_present(col):
    assert col in _table("taxonomy_mappings").columns, f"taxonomy_mappings.{col} missing"


def test_metric_definitions_window_check_constraint():
    t = _table("metric_definitions")
    c = next(
        (c for c in t.constraints
         if getattr(c, "name", None) == "ck_metric_definitions_window_type"),
        None,
    )
    assert c is not None
    text = str(c.sqltext)
    assert "rolling_12m" in text and "rolling_90d" in text


def test_hazards_nhrc_category_present():
    assert "nhrc_category" in _table("hazards").columns


def test_psoe_finding_cap_fk():
    t = _table("psoe_findings")
    col = t.columns.get("cap_id")
    assert col is not None and col.foreign_keys
    refs = {fk.column.table.name for fk in col.foreign_keys}
    assert "caps" in refs


def test_cap_source_psoe_finding_fk():
    t = _table("caps")
    col = t.columns.get("source_psoe_finding_id")
    assert col is not None and col.foreign_keys
    refs = {fk.column.table.name for fk in col.foreign_keys}
    assert "psoe_findings" in refs