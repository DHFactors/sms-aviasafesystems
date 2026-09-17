# ============================================================================
# Tests for the Firestore → Postgres migration schema (Batch 0): the domain
# SQLAlchemy models (app/db/db_models.py) and the idempotent DDL that
# materialises them (app/db/schema_init.py).
# ============================================================================

import pytest

from app.db import db_models
from app.db.schema_init import _DOMAIN_DDL


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