"""H1 — /api/v1/spi auth + tenant-match gate (SECURITY_REVIEW H1 remediation).

Previously all SPI routes had no auth dependency: cross-tenant reads of SPI
values / status / trend and an unauthenticated write path for SPT targets.
Now:

  * All routes require a valid Firebase ID token (Depends(get_current_user)).
  * GET|POST /spi/tenant/{tenant_id}/values|status|trend|targets require the
    caller's tenant_id to match {tenant_id} unless the role is cross-tenant
    (CAAN_SMD / SUPER_ADMIN) — shared require_tenant_access helper.
  * GET /spi/state/values|status are State aggregates and require the CAAN
    role (Depends(get_caan_user)).

Covers:
  GET  /spi/definitions
  GET  /spi/tenant/{tid}/values | status | trend
  GET  /spi/state/values | status
  POST /spi/tenant/{tid}/targets
"""

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user
from app.services.spi_service import SPIService


SPI_TENANT_GET_URLS = [
    "/api/v1/spi/tenant/fixedwing/values",
    "/api/v1/spi/tenant/fixedwing/status",
    "/api/v1/spi/tenant/fixedwing/trend?months=6",
]

SPI_STATE_URLS = [
    "/api/v1/spi/state/values",
    "/api/v1/spi/state/status",
]

SPI_GET_URLS = SPI_TENANT_GET_URLS + [
    "/api/v1/spi/definitions",
] + SPI_STATE_URLS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user(role="AIRLINE_ADMIN", tenant_id="fixedwing", uid="u-fw"):
    return {
        "uid": uid,
        "email": "safety@fixedwing.com.np",
        "role": role,
        "tenant_id": tenant_id,
        "department": "safety",
        "claims": {"role": role, "tenant_id": tenant_id},
    }


def _override(user):
    app.dependency_overrides[get_current_user] = lambda: user


def _patch_service(monkeypatch):
    """Stub the DB-backed SPI reads so tests exercise the auth gate only."""
    monkeypatch.setattr(SPIService, "calculate_all_spis", lambda self, tid, h=0, f=0: {})
    monkeypatch.setattr(SPIService, "get_tenant_status", lambda self, tid, h=0, f=0: [])
    monkeypatch.setattr(SPIService, "get_tenant_trend", lambda self, tid, months=6: [])
    monkeypatch.setattr(SPIService, "get_state_values", lambda self, h=0, f=0: {})
    monkeypatch.setattr(SPIService, "get_state_status", lambda self, h=0, f=0: [])


# ---------------------------------------------------------------------------
# Unauthenticated — must be rejected
# ---------------------------------------------------------------------------

def test_spi_routes_reject_unauthenticated():
    c = TestClient(app)
    for url in SPI_GET_URLS:
        resp = c.get(url)
        assert resp.status_code in (401, 403), (url, resp.status_code)
    resp = c.post(
        "/api/v1/spi/tenant/fixedwing/targets",
        json={"hazard_id_rate": 12.0},
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /tenant/{tid}/* — tenant-match enforcement
# ---------------------------------------------------------------------------

def test_tenant_get_routes_allow_own_tenant(monkeypatch):
    _patch_service(monkeypatch)
    _override(_user(tenant_id="fixedwing"))
    try:
        c = TestClient(app)
        for url in SPI_TENANT_GET_URLS:
            resp = c.get(url)
            assert resp.status_code == 200, (url, resp.status_code)
    finally:
        app.dependency_overrides.clear()


def test_tenant_get_routes_reject_cross_tenant(monkeypatch):
    _patch_service(monkeypatch)
    _override(_user(tenant_id="rotarywing"))
    try:
        c = TestClient(app)
        for url in SPI_TENANT_GET_URLS:
            resp = c.get(url)
            assert resp.status_code == 403, (url, resp.status_code)
            assert "tenant" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_tenant_get_routes_allow_caan_any_tenant(monkeypatch):
    _patch_service(monkeypatch)
    _override(_user(role="CAAN_SMD", tenant_id=None, uid="u-caan"))
    try:
        c = TestClient(app)
        for url in SPI_TENANT_GET_URLS:
            resp = c.get(url)
            assert resp.status_code == 200, (url, resp.status_code)
    finally:
        app.dependency_overrides.clear()


def test_tenant_get_routes_allow_super_admin_any_tenant(monkeypatch):
    _patch_service(monkeypatch)
    _override(_user(role="SUPER_ADMIN", tenant_id=None, uid="u-sa"))
    try:
        c = TestClient(app)
        for url in SPI_TENANT_GET_URLS:
            resp = c.get(url)
            assert resp.status_code == 200, (url, resp.status_code)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /state/* — CAAN role only (state-level aggregate)
# ---------------------------------------------------------------------------

def test_state_get_routes_reject_airline_user(monkeypatch):
    _patch_service(monkeypatch)
    _override(_user(tenant_id="fixedwing"))
    try:
        c = TestClient(app)
        for url in SPI_STATE_URLS:
            resp = c.get(url)
            assert resp.status_code == 403, (url, resp.status_code)
            assert "CAAN" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_state_get_routes_allow_caan_user(monkeypatch):
    _patch_service(monkeypatch)
    _override(_user(role="CAAN_SMD", tenant_id=None, uid="u-caan"))
    try:
        c = TestClient(app)
        for url in SPI_STATE_URLS:
            resp = c.get(url)
            assert resp.status_code == 200, (url, resp.status_code)
    finally:
        app.dependency_overrides.clear()


def test_state_get_routes_allow_super_admin(monkeypatch):
    _patch_service(monkeypatch)
    _override(_user(role="SUPER_ADMIN", tenant_id=None, uid="u-sa"))
    try:
        c = TestClient(app)
        for url in SPI_STATE_URLS:
            resp = c.get(url)
            assert resp.status_code == 200, (url, resp.status_code)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /definitions — any authenticated user (static config, not tenant-scoped)
# ---------------------------------------------------------------------------

def test_spi_definitions_pure_endpoint_allows_authenticated_user():
    _override(_user())
    try:
        resp = TestClient(app).get("/api/v1/spi/definitions")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert len(resp.json()) == 8


# ---------------------------------------------------------------------------
# POST targets — tenant-scope enforcement (unchanged from prior session)
# ---------------------------------------------------------------------------

def test_update_targets_allows_same_tenant_user():
    _override(_user(tenant_id="fixedwing"))
    try:
        resp = TestClient(app).post(
            "/api/v1/spi/tenant/fixedwing/targets",
            json={"hazard_id_rate": 12.0},
        )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["status"] == "updated"


def test_update_targets_rejects_cross_tenant_user():
    _override(_user(tenant_id="rotarywing"))
    try:
        resp = TestClient(app).post(
            "/api/v1/spi/tenant/fixedwing/targets",
            json={"hazard_id_rate": 12.0},
        )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 403
    assert "tenant" in resp.json()["detail"].lower()


def test_update_targets_allows_caan_for_any_tenant():
    _override(_user(role="CAAN_SMD", tenant_id=None, uid="u-caan"))
    try:
        resp = TestClient(app).post(
            "/api/v1/spi/tenant/rotarywing/targets",
            json={"can_closure_rate": 95.0},
        )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200


def test_update_targets_allows_super_admin_for_any_tenant():
    _override(_user(role="SUPER_ADMIN", tenant_id=None, uid="u-sa"))
    try:
        resp = TestClient(app).post(
            "/api/v1/spi/tenant/demoairport/targets",
            json={"can_closure_rate": 95.0},
        )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200