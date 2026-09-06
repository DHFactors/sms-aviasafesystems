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
        ("invites", "code", []),
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
        ("users", ["claims", "data"]),
        ("audit_logs", ["metadata_json"]),
        ("sms_dispatches", ["data"]),
        ("invites", ["data"]),
        ("feedback", ["data"]),
        ("caan_reports", ["data"]),
        ("sms_maturity", ["data"]),
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