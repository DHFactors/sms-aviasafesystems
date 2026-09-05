# ============================================================================
# Tests for the "Purge Demo Data" capability (POST /api/v1/admin/purge-demo-data)
# ============================================================================

import asyncio
from types import SimpleNamespace

import pytest

from app.db import db_models as dm
from app.services.admin_data_service import purge_all_demo_data

EXPECTED_ORDER = [
    "hazard_rca_factors",
    "hazard_assessments",
    "hazard_capas",
    "hazard_rca_entries",
    "verifications",
    "closures",
    "corrective_actions",
    "flight_diversions",
    "safety_deficiencies",
    "psoe_findings",
    "psoe_assessments",
    "survey_responses",
    "surveys",
    "caps",
    "cans",
    "reports",
    "hazards",
    "bow_tie_controls",
    "bow_tie_consequences",
    "bow_tie_threats",
    "bow_tie_analyses",
    "risk_register",
    "barrier_register",
    "state_risk_register",
    "regulatory_reports",
]


class _FakeResult:
    rowcount = 3


class _FakeSession:
    def __init__(self):
        self.executed = []

    async def execute(self, stmt, *args, **kwargs):
        self.executed.append(stmt)
        return _FakeResult()


class _FakeScope:
    def __init__(self):
        self.session = _FakeSession()

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


@pytest.fixture
def fake_scope(monkeypatch):
    scope = _FakeScope()
    monkeypatch.setattr(
        "app.services.admin_data_service.session_scope", lambda: scope
    )
    return scope


def _sql(stmt) -> str:
    try:
        return str(stmt.whereclause)
    except Exception:
        return ""


def test_purge_reports_counts_and_success(fake_scope):
    result = asyncio.run(
        purge_all_demo_data({"uid": "u1", "email": "admin@aviasafe.test"})
    )
    assert result["success"] is True
    assert result["deleted_count"] == len(EXPECTED_ORDER) * 3
    assert list(result["details"].keys()) == EXPECTED_ORDER
    for table in EXPECTED_ORDER:
        assert result["details"][table] == 3


def test_purge_covers_every_is_demo_table(fake_scope):
    tables_with_is_demo = {
        mapper.class_.__tablename__
        for mapper in dm.Base.registry.mappers
        for col in mapper.columns
        if col.name == "is_demo"
    }
    result = asyncio.run(
        purge_all_demo_data({"uid": "u1", "email": "admin@aviasafe.test"})
    )
    purged = set(result["details"].keys())
    assert tables_with_is_demo - purged == set(), (
        f"is_demo tables missing from purge: {sorted(tables_with_is_demo - purged)}"
    )


def test_purge_never_touches_psoe_questions(fake_scope):
    result = asyncio.run(
        purge_all_demo_data({"uid": "u1", "email": "admin@aviasafe.test"})
    )
    assert "psoe_questions" not in result["details"]


def test_purge_parent_tables_filter_on_is_demo(fake_scope):
    asyncio.run(purge_all_demo_data({"uid": "u1", "email": "admin@aviasafe.test"}))
    executed = dict(zip(EXPECTED_ORDER, fake_scope.session.executed))
    for table in [
        "psoe_assessments",
        "survey_responses",
        "surveys",
        "caps",
        "cans",
        "reports",
        "hazards",
        "bow_tie_analyses",
        "risk_register",
        "barrier_register",
        "state_risk_register",
        "regulatory_reports",
    ]:
        assert "is_demo" in _sql(executed[table]), f"{table} must filter on is_demo"


def test_purge_child_tables_scope_to_demo_parents(fake_scope):
    asyncio.run(purge_all_demo_data({"uid": "u1", "email": "admin@aviasafe.test"}))
    executed = dict(zip(EXPECTED_ORDER, fake_scope.session.executed))
    for table in ["verifications", "closures", "corrective_actions", "flight_diversions"]:
        sql = _sql(executed[table])
        assert "hazards" in sql, f"{table} must reference demo hazards"
        assert f"{table}.is_demo" not in sql, f"{table} has no is_demo column — must not filter on it"


def test_purge_endpoint_registered_on_admin_router():
    from app.routes.admin import router

    paths = {getattr(r, "path", None) for r in router.routes}
    assert "/purge-demo-data" in paths