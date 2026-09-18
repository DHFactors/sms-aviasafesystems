"""H2 — /api/v1/regulator/* role gate (SECURITY_REVIEW H2 remediation).

Previously every regulator endpoint depended on get_current_user, so any
authenticated airline user could read other operators' aggregated risk /
benchmark data. Now all routes require the CAAN role (get_caan_user ->
CAAN_SMD / SUPER_ADMIN from CROSS_TENANT_ROLES). Because the route is CAAN
gated, the caller-controlled tenant_ids query parameter is inherently
restricted to regulator scope.

Covers:
  GET /regulator/industry-averages
  GET /regulator/top-hazards
  GET /regulator/risk-trends
  GET /regulator/risk-register
  GET /regulator/benchmark/{tenant_id}
  GET /regulator/export/pdf
  GET /regulator/export/excel
"""

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user
from app.routes import regulator_dashboard as rd


REGULATOR_URLS = [
    "/api/v1/regulator/industry-averages",
    "/api/v1/regulator/top-hazards",
    "/api/v1/regulator/risk-trends",
    "/api/v1/regulator/risk-register",
    "/api/v1/regulator/benchmark/fixedwing",
    "/api/v1/regulator/export/pdf",
    "/api/v1/regulator/export/excel",
]

APP_CHECK_REQUIRED = ["/api/v1/regulator/export/pdf", "/api/v1/regulator/export/excel"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _airline_user():
    return {
        "uid": "u-fw",
        "email": "safety@fixedwing.com.np",
        "role": "AIRLINE_ADMIN",
        "tenant_id": "fixedwing",
        "department": "safety",
        "claims": {"role": "AIRLINE_ADMIN", "tenant_id": "fixedwing"},
    }


def _caan_user():
    return {
        "uid": "u-caan",
        "email": "smd@caanepal.gov.np",
        "role": "CAAN_SMD",
        "tenant_id": None,
        "department": None,
        "claims": {"role": "CAAN_SMD", "tenant_id": None},
    }


def _super_admin_user():
    return {
        "uid": "u-sa",
        "email": "admin@aviasafesystems.com",
        "role": "SUPER_ADMIN",
        "tenant_id": None,
        "department": None,
        "claims": {"role": "SUPER_ADMIN", "tenant_id": None},
    }


def _override(user):
    app.dependency_overrides[get_current_user] = lambda: user


class _FakeAgSvc:
    """Stand-in for AggregationService; stubs the DB reads so these tests
    exercise the role gate, not the aggregation queries."""

    async def calculate_industry_averages(self, tids):
        return {"tenant_count": 3, "anonymized": True}

    async def get_top_hazards(self, tids):
        return {"total_hazards": 1}

    async def get_risk_trends(self, tids):
        return {"total_points": 1}

    async def get_state_risk_register(self, tids):
        return {"total_high_risks": 1}

    async def get_benchmarking(self, tenant_id, tids):
        return {"tenant_id": tenant_id, "anonymized": True}

    def export_pdf_data(self, data):
        return b"%PDF-1.7 fake"

    def export_excel_data(self, data):
        return b"PK fake"


def _patch_service(monkeypatch):
    monkeypatch.setattr(rd, "AggregationService", _FakeAgSvc)


# ---------------------------------------------------------------------------
# Unauthenticated — must be rejected
# ---------------------------------------------------------------------------

def test_regulator_routes_reject_unauthenticated():
    c = TestClient(app)
    for url in REGULATOR_URLS:
        resp = c.get(url)
        assert resp.status_code in (401, 403), (url, resp.status_code)


# ---------------------------------------------------------------------------
# Authenticated airline user — must be rejected (CAAN gate)
# ---------------------------------------------------------------------------

def test_regulator_routes_reject_airline_user():
    _override(_airline_user())
    try:
        c = TestClient(app)
        for url in REGULATOR_URLS:
            resp = c.get(url)
            assert resp.status_code == 403, (url, resp.status_code)
            assert "CAAN" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# CAAN / SUPER_ADMIN — must pass
# ---------------------------------------------------------------------------

def test_regulator_routes_allow_caan_user(monkeypatch):
    _patch_service(monkeypatch)
    _override(_caan_user())
    try:
        c = TestClient(app)
        for url in REGULATOR_URLS:
            resp = c.get(url)
            assert resp.status_code == 200, (url, resp.status_code)
    finally:
        app.dependency_overrides.clear()


def test_regulator_routes_allow_super_admin(monkeypatch):
    _patch_service(monkeypatch)
    _override(_super_admin_user())
    try:
        c = TestClient(app)
        for url in REGULATOR_URLS:
            resp = c.get(url)
            assert resp.status_code == 200, (url, resp.status_code)
    finally:
        app.dependency_overrides.clear()


def test_regulator_routes_accept_tenant_ids_filter_for_caan(monkeypatch):
    _patch_service(monkeypatch)
    _override(_caan_user())
    try:
        resp = TestClient(app).get(
            "/api/v1/regulator/industry-averages?tenant_ids=fixedwing,rotarywing"
        )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200