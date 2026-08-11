"""State-vs-operator scoping verification for the reporting endpoints.

Verifies the ``_effective_tenant`` helper and the two production behaviors it
drives for a CAAN inspector:

1. Explicit ``?tenant_id=sita-air``  -> report scoped to the sita-air tenant
   (metrics read from tenants/sita-air, report stored under sita-air).
2. No ``tenant_id``                 -> state scope (None -> caan_reports).

Also asserts the pure helper matrix for both cross-tenant and tenant roles.
"""

from typing import Any, Dict
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user
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

class _Added:
    def __init__(self, doc_id="rpt-001"):
        self.id = doc_id


class _CaanReports:
    def __init__(self, adds):
        self._adds = adds

    def add(self, data):
        self._adds.append(data)
        return (Mock(), _Added())


class _TenantReporting:
    def __init__(self, records):
        self._records = records

    def add(self, data):
        self._records.append(data)
        return (Mock(), _Added())


class _TenantCollection:
    def __init__(self, records):
        self._records = records

    def __call__(self, tenant_id, collection):
        self._last = (tenant_id, collection)
        return _TenantReporting(self._records)


class _DB:
    def __init__(self, caan_adds):
        self._caan_adds = caan_adds

    def collection(self, name):
        self.last_collection = name
        return _CaanReports(self._caan_adds)


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
    gen = _FakeGenerator()
    tenant_adds: list = []
    _override_user(CAAN_SMD)
    try:
        with patch.object(reporting, "ReportGenerator", gen), \
             patch.object(reporting, "get_tenant_collection", _TenantCollection(tenant_adds)):
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
            assert len(tenant_adds) == 1
            assert tenant_adds[0]["tenant_id"] == "sita-air"
            assert tenant_adds[0]["data"]["state"] is False
            assert "caan_reports" not in [a.get("tenant_id") for a in tenant_adds]
            _assert_no_legacy_national(body)
            _assert_no_legacy_national(tenant_adds[0])
    finally:
        _teardown()


def test_quarterly_generation_reverts_to_state_when_tenant_id_omitted():
    gen = _FakeGenerator()
    caan_adds: list = []
    _override_user(CAAN_SMD)
    try:
        with patch.object(reporting, "ReportGenerator", gen), \
             patch.object(reporting, "get_tenant_collection", _TenantCollection([])), \
             patch("app.firebase.get_db", lambda: _DB(caan_adds)):
            client = TestClient(app)
            resp = client.post("/api/v1/reporting/quarterly?year=2026&quarter=2")
            assert resp.status_code == 201, resp.text
            body = resp.json()
            assert body["tenant_id"] is None
            assert "state" in body["data"]
            assert "national" not in body["data"]
            assert body["data"]["state"] is True
            assert gen.init_tenants == [None]
            assert len(caan_adds) == 1
            assert caan_adds[0]["tenant_id"] is None
            assert caan_adds[0]["data"]["state"] is True
            _assert_no_legacy_national(body)
            _assert_no_legacy_national(caan_adds[0])
    finally:
        _teardown()


# ============================================================================
# 3. Endpoint behavior: list + get quarterly reports
# ============================================================================

class _DocSnap:
    def __init__(self, data, exists=True):
        self._data = data
        self.id = data.get("id", "doc")
        self.exists = exists

    def to_dict(self):
        return self._data


class _DocRef:
    def __init__(self, snap):
        self._snap = snap

    def get(self):
        return self._snap


class _DocColl:
    def __init__(self, snap):
        self._snap = snap

    def document(self, doc_id):
        return _DocRef(self._snap)

class _ListDocs:
    def __init__(self, snapshots):
        self._snapshots = snapshots

    def get(self):
        return self._snapshots


class _Doc:
    def __init__(self, data):
        self._data = data
        self.id = data.get("id", "doc")

    def to_dict(self):
        return self._data


class _Query:
    def __init__(self, snaps):
        self._snaps = snaps

    def where(self, *args, **kwargs):
        return self

    def get(self):
        return self._snaps


def test_list_quarterly_reports_state_reads_caan_reports():
    _override_user(CAAN_SMD)
    seen = {}

    def fake_tenant_collection(tenant_id, collection):
        seen["tenant"] = (tenant_id, collection)
        return _Query([])

    def fake_get_db():
        db = Mock()
        db.collection.return_value = _Query(
            [_Doc({"id": "r1", "report_type": "quarterly", "period": "2026-Q1",
                   "year": 2026, "quarter": 1, "status": "completed"})]
        )
        return db

    try:
        with patch.object(reporting, "get_tenant_collection", fake_tenant_collection), \
             patch("app.firebase.get_db", fake_get_db):
            client = TestClient(app)
            resp = client.get("/api/v1/reporting/quarterly")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert len(body) == 1
            assert body[0]["id"] == "r1"
            assert "tenant" not in seen
    finally:
        _teardown()


def test_list_quarterly_reports_scoped_reads_operator_collection():
    _override_user(CAAN_SMD)
    seen = {}

    def fake_tenant_collection(tenant_id, collection):
        seen["tenant"] = (tenant_id, collection)
        return _Query(
            [_Doc({"id": "r2", "report_type": "quarterly", "period": "2026-Q2",
                   "year": 2026, "quarter": 2, "status": "completed"})]
        )

    try:
        with patch.object(reporting, "get_tenant_collection", fake_tenant_collection):
            client = TestClient(app)
            resp = client.get("/api/v1/reporting/quarterly?tenant_id=sita-air")
            assert resp.status_code == 200, resp.text
            assert seen["tenant"] == ("sita-air", "reporting")
            assert resp.json()[0]["id"] == "r2"
    finally:
        _teardown()


def test_get_quarterly_report_returns_state_payload():
    """GET /api/v1/reporting/quarterly/{id} returns data.state, no national key."""
    _override_user(CAAN_SMD)
    snap = _DocSnap({
        "id": "rpt-001",
        "tenant_id": None,
        "report_type": "quarterly",
        "period": "2026-Q2",
        "year": 2026,
        "quarter": 2,
        "status": "completed",
        "summary": {"pillar_scores": {"safety_policy": 3.2}},
        "data": {"state": True},
    })

    def fake_get_db():
        db = Mock()
        db.collection.return_value = _DocColl(snap)
        return db

    try:
        with patch("app.firebase.get_db", fake_get_db):
            client = TestClient(app)
            resp = client.get("/api/v1/reporting/quarterly/rpt-001")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["id"] == "rpt-001"
            assert "state" in body["data"]
            assert body["data"]["state"] is True
            assert "national" not in body["data"]
            _assert_no_legacy_national(body)
    finally:
        _teardown()
