"""State-vs-operator scoping verification for the reporting endpoints.

Verifies the ``_effective_tenant`` helper and the two production behaviors it
drives for a CAAN inspector:

1. Explicit ``?tenant_id=sita-air``  -> report scoped to the sita-air tenant
   (stored in regulatory_reports under the sita-air tenant uuid).
2. No ``tenant_id``                 -> state scope (None -> caan_reports).

The endpoints are Postgres-primary (app.db.pg): generation persists via
``pg.upsert``, and listing/reading via ``pg.fetch_all``/``pg.fetch_by``. These
tests mock the PG accessors and assert scoping on the stored/returned payloads
— NOT on Firestore constructor call sites (Firestore was removed from the data
plane). A ``data.state`` vs legacy ``data.national`` contract guard is kept.

Also asserts the pure helper matrix for both cross-tenant and tenant roles.
"""

from typing import Any, Dict
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user
from app.db.db_models import CaanReport, RegulatoryReport
from app.db.ids import tenant_uuid
from app.routes import reporting

CAAN_SMD = {"uid": "smd-caan-001", "role": "CAAN_SMD", "tenant_id": "caan"}


# ============================================================================
# 1. Pure helper matrix
# ============================================================================

def test_effective_tenant_caan_scoped_to_operator():
    """CAAN inspector with ?tenant_id=sita-air resolves to sita-air."""
    assert reporting._effective_tenant(CAAN_SMD, "sita-air") == "sita-air"


def test_effective_tenant_caan_omitted_is_state():
    """CAAN inspector with no tenant_id resolves to None (state)."""
    assert reporting._effective_tenant(CAAN_SMD) is None
    assert reporting._effective_tenant(CAAN_SMD, None) is None


def test_effective_tenant_super_admin_scope():
    assert reporting._effective_tenant(
        {"role": "SUPER_ADMIN", "tenant_id": "caan"}, "buddha-air") == "buddha-air"
    assert reporting._effective_tenant({"role": "SUPER_ADMIN", "tenant_id": "caan"}) is None


def test_effective_tenant_operator_role_always_own_tenant():
    """A tenant role ignores cross-tenant scoping and uses its own tenant."""
    op = {"role": "AIRLINE_ADMIN", "tenant_id": "sita-air"}
    assert reporting._effective_tenant(op) == "sita-air"
    assert reporting._effective_tenant(op, None) == "sita-air"


# ============================================================================
# 2. Endpoint behavior: generate quarterly report
# ============================================================================

class _FakeGenerator:
    def __init__(self):
        self.init_tenants = []
        self._counter = 0

    def __call__(self, tenant_id):
        self.init_tenants.append(tenant_id)
        self._tenant = tenant_id
        return self

    def generate_quarterly_report(self, year, quarter, user):
        self.called_year = year
        self.called_quarter = quarter
        self.called_user = user
        return {
            "period": f"{year}-Q{quarter}",
            "summary": {"pillar_scores": {"safety_policy": 3.2}, "tenant": self._tenant},
            "data": {"state": self._tenant is None},
        }

    def generate_annual_report(self, year, user):
        return {
            "period": str(year),
            "summary": {"pillar_scores": {"safety_policy": 3.2}, "tenant": self._tenant},
            "data": {"state": self._tenant is None},
        }


def _override_user(user: Dict[str, Any]):
    app.dependency_overrides[get_current_user] = lambda: user


def _teardown():
    app.dependency_overrides.pop(get_current_user, None)


def _assert_no_legacy_national(payload):
    """Recursively assert no 'national' key or value-key survives anywhere.

    Guards the API contract: after the State terminology refactor the report
    payload must expose `data.state` and zero legacy `data.national` keys.
    """
    if isinstance(payload, dict):
        for k, v in payload.items():
            assert "national" not in k.lower(), f"legacy 'national' key survived: {k}"
            _assert_no_legacy_national(v)
    elif isinstance(payload, list):
        for item in payload:
            _assert_no_legacy_national(item)


def test_quarterly_generation_scopes_to_operator_when_tenant_id_given():
    """Operator scope persists to PG regulatory_reports (tenant uuid) only."""
    gen = _FakeGenerator()
    _override_user(CAAN_SMD)
    try:
        with patch.object(reporting, "ReportGenerator", gen), \
             patch.object(reporting.pg, "upsert") as upsert:
            client = TestClient(app)
            resp = client.post(
                "/api/v1/reporting/quarterly?year=2026&quarter=2&tenant_id=sita-air"
            )
            assert resp.status_code == 201, resp.text
            body = resp.json()
            assert body["tenant_id"] == "sita-air"
            assert "state" in body["data"]
            assert "national" not in body["data"]
            assert body["data"]["state"] is False
            assert gen.init_tenants == ["sita-air"]
            rid = reporting._report_id("sita-air", "quarterly", 2026, 2)
            assert body["id"] == rid
            assert upsert.call_args.args[0] is RegulatoryReport
            assert upsert.call_args.args[1] == "id"
            assert upsert.call_args.args[2] == rid
            stored = upsert.call_args.args[3]
            assert stored["tenant_id"] == tenant_uuid("sita-air")
            assert stored["data"]["state"] is False
            _assert_no_legacy_national(body)
            _assert_no_legacy_national(stored)
    finally:
        _teardown()


def test_quarterly_generation_reverts_to_state_when_tenant_id_omitted():
    """State scope (no tenant_id) persists to PG caan_reports with tenant None."""
    gen = _FakeGenerator()
    _override_user(CAAN_SMD)
    try:
        with patch.object(reporting, "ReportGenerator", gen), \
             patch.object(reporting.pg, "upsert") as upsert:
            client = TestClient(app)
            resp = client.post("/api/v1/reporting/quarterly?year=2026&quarter=2")
            assert resp.status_code == 201, resp.text
            body = resp.json()
            assert body["tenant_id"] is None
            assert "state" in body["data"]
            assert "national" not in body["data"]
            assert body["data"]["state"] is True
            assert gen.init_tenants == [None]
            rid = reporting._report_id(None, "quarterly", 2026, 2)
            assert body["id"] == rid
            assert upsert.call_args.args[0] is CaanReport
            assert upsert.call_args.args[1] == "report_id"
            assert upsert.call_args.args[2] == rid
            stored = upsert.call_args.args[3]
            assert stored["tenant_id"] is None
            assert stored["data"]["state"] is True
            _assert_no_legacy_national(body)
            _assert_no_legacy_national(stored)
    finally:
        _teardown()


# ============================================================================
# 3. Endpoint behavior: list + get quarterly reports
# ============================================================================

def test_list_quarterly_reports_state_reads_caan_reports():
    """State scope queries the PG caan_reports table, filtered by report_type."""
    _override_user(CAAN_SMD)
    rid = reporting._report_id(None, "quarterly", 2026, 1)
    row = {
        "id": rid,
        "report_id": rid,
        "report_type": "quarterly",
        "period": "2026-Q1",
        "year": 2026,
        "quarter": 1,
        "status": "completed",
        "generated_at": None,
        "generated_by": "smd-caan-001",
    }

    try:
        with patch.object(reporting.pg, "fetch_all", return_value=[row]) as fetch_all:
            client = TestClient(app)
            resp = client.get("/api/v1/reporting/quarterly")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert len(body) == 1
            assert body[0]["id"] == rid
            assert fetch_all.call_args.args[0] is CaanReport
            where = fetch_all.call_args.kwargs["where"]
            assert where[0].right.value == "quarterly"
    finally:
        _teardown()


def test_list_quarterly_reports_scoped_reads_operator_collection():
    """Operator scope queries PG regulatory_reports, scoped to the tenant uuid."""
    _override_user(CAAN_SMD)
    tid_uuid = tenant_uuid("sita-air")
    row = {
        "tenant_id": tid_uuid,
        "report_type": "quarterly",
        "period": "2026-Q2",
        "year": 2026,
        "quarter": 2,
        "status": "completed",
        "generated_at": None,
        "generated_by": "smd-caan-001",
    }

    try:
        with patch.object(reporting.pg, "fetch_all", return_value=[row]) as fetch_all:
            client = TestClient(app)
            resp = client.get("/api/v1/reporting/quarterly?tenant_id=sita-air")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body[0]["id"] == reporting._report_id("sita-air", "quarterly", 2026, 2)
            assert fetch_all.call_args.args[0] is RegulatoryReport
            where = fetch_all.call_args.kwargs["where"]
            assert where[0].right.value == tid_uuid
            assert where[1].right.value == "quarterly"
    finally:
        _teardown()


def test_get_quarterly_report_returns_state_payload():
    """GET /api/v1/reporting/quarterly/{id} returns data.state, no national key."""
    _override_user(CAAN_SMD)
    rid = reporting._report_id(None, "quarterly", 2026, 2)
    row = {
        "report_id": rid,
        "tenant_id": None,
        "report_type": "quarterly",
        "period": "2026-Q2",
        "year": 2026,
        "quarter": 2,
        "status": "completed",
        "summary": {"pillar_scores": {"safety_policy": 3.2}},
        "data": {"state": True},
    }

    try:
        with patch.object(reporting.pg, "fetch_by", return_value=row) as fetch_by:
            client = TestClient(app)
            resp = client.get(f"/api/v1/reporting/quarterly/{rid}")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["id"] == rid
            assert "state" in body["data"]
            assert body["data"]["state"] is True
            assert "national" not in body["data"]
            _assert_no_legacy_national(body)
            assert fetch_by.call_args.args[0] is CaanReport
            assert fetch_by.call_args.args[1] == "report_id"
            assert fetch_by.call_args.args[2] == rid
    finally:
        _teardown()