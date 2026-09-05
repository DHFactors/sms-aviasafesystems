"""Chunk 15 — route-level archetype resolution with safe fallback.

Verifies through the FastAPI layer (dependency-overridden auth + patched
services) that:

  * ?archetypeId=demo-* scopes cans / caps / hazards / PSOE / master-register
    to the virtual archetype tenant;
  * non-demo values are IGNORED (caller falls back to their own tenant) —
    cross-operator access stays impossible;
  * CAAN_SMD may target archetypes explicitly.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user

AE_EMAIL = "ae@buddha-air.com"


class _CaptureService:
    """Stands in for CanCapService / HazardService, recording init tenant."""
    last_tenant = None
    last_filters = None

    def __init__(self, tenant):
        _CaptureService.last_tenant = tenant

    def list_cans(self, user, filters):
        return [{"can_reference": "FW-CAN-0001-26", "id": "c1", "title": "t",
                 "status": "Open", "priority": "High", "issued_at": None,
                 "target_completion_date": None}]

    def list_all_caps(self, user, filters):
        return [{"id": "cap1", "cap_reference": "FW-CAP-0001-26",
                 "can_reference": "FW-CAN-0001-26", "action_plan": "plan",
                 "status": "In Progress", "submitted_by": "x",
                 "residual_risk_index": 4, "barrier_health": {}}]

    def list_hazards(self, user, filters):
        return [{"id": "h1", "hazard_id": "OPS/001/H/2026", "title": "t",
                 "status": "Open", "severity": 3, "probability": 3,
                 "risk_index": 9, "created_at": None}]


def _override(user):
    app.dependency_overrides[get_current_user] = lambda: user


def _clear():
    app.dependency_overrides.clear()


# ── CANs ────────────────────────────────────────────────────────────────────

def test_cans_archetype_scopes_to_virtual_tenant(monkeypatch):
    from app.routes import can_cap as cc
    monkeypatch.setattr(cc, "CanCapService", _CaptureService)
    _override({"uid": "ae1", "email": AE_EMAIL, "role": "AIRLINE_ADMIN",
               "tenant_id": "buddha-air"})
    try:
        c = TestClient(app)
        r = c.get("/api/v1/cans/", params={"archetypeId": "demo-fixed-wing"})
        assert r.status_code == 200
        assert _CaptureService.last_tenant == "demo-fixed-wing"
        assert any(x["can_reference"].startswith("FW-CAN-") for x in r.json())
    finally:
        _clear()


def test_cans_non_demo_value_is_ignored_safe_fallback(monkeypatch):
    from app.routes import can_cap as cc
    monkeypatch.setattr(cc, "CanCapService", _CaptureService)
    _override({"uid": "ae1", "email": AE_EMAIL, "role": "AIRLINE_ADMIN",
               "tenant_id": "buddha-air"})
    try:
        r = TestClient(app).get("/api/v1/cans/",
                                params={"archetypeId": "yeti-airlines"})
        assert r.status_code == 200
        # Non-demo value ignored -> safe fallback to caller's own tenant.
        assert _CaptureService.last_tenant == "buddha-air"
    finally:
        _clear()


# ── CAPs ────────────────────────────────────────────────────────────────────

def test_caps_safe_fallback_ignores_non_demo_value(monkeypatch):
    from app.routes import can_cap as cc
    monkeypatch.setattr(cc, "CanCapService", _CaptureService)
    _override({"uid": "ae1", "email": AE_EMAIL, "role": "AIRLINE_ADMIN",
               "tenant_id": "buddha-air"})
    try:
        r = TestClient(app).get("/api/v1/cans/caps",
                                params={"archetypeId": "yeti-airlines"})
        assert r.status_code == 200
        assert _CaptureService.last_tenant == "buddha-air"
    finally:
        _clear()


# ── Hazards ─────────────────────────────────────────────────────────────────

def test_hazards_demo_scope_beats_cross_tenant_role(monkeypatch):
    from app.routes import hazards as hz
    monkeypatch.setattr(hz, "HazardService", _CaptureService)

    caan = {"uid": "smd", "email": "smd@caanepal.gov.np", "role": "CAAN_SMD",
            "tenant_id": "caan"}
    _override(caan)
    try:
        c = TestClient(app)
        r = c.get("/api/v1/hazards/", params={"archetypeId": "demo-rotary-wing"})
        assert r.status_code == 200
        assert _CaptureService.last_tenant == "demo-rotary-wing"
    finally:
        _clear()


def test_hazards_ae_email_demo_scope_via_department_guard(monkeypatch):
    """145@/camo@ style department guards don't exist for AEs; an AE email with
    a demo archetype must still land on the virtual tenant."""
    from app.routes import hazards as hz
    monkeypatch.setattr(hz, "HazardService", _CaptureService)

    ae = {"uid": "ae2", "email": AE_EMAIL, "role": "AIRLINE_ADMIN",
          "tenant_id": "fishtail-air"}
    _override(ae)
    try:
        c = TestClient(app)
        r = c.get("/api/v1/hazards/", params={"archetypeId": "demo-fixed-wing"})
        assert r.status_code == 200
        assert _CaptureService.last_tenant == "demo-fixed-wing"
    finally:
        _clear()


# ── PSOE ────────────────────────────────────────────────────────────────────

class _Snap:
    def __init__(self, id, data):
        self._d = data
        self.id = id

    def to_dict(self):
        return dict(self._d)


def test_psoe_assessments_archetype_scope(monkeypatch):
    docs = [
        _Snap("a1", {"tenant_id": "demo-rotary-wing", "title": "RW audit",
                     "status": "completed", "overall_score_pct": 80.0}),
        _Snap("a2", {"tenant_id": "buddha-air", "title": "BA audit",
                     "status": "completed", "overall_score_pct": 70.0}),
    ]
    from app.routes import psoe as psoe_routes

    class _Coll:
        def get(self):
            return docs

    monkeypatch.setattr(psoe_routes, "_coll", lambda: _Coll())
    _override({"uid": "smd", "email": "smd@caanepal.gov.np",
               "role": "CAAN_SMD", "tenant_id": "caan"})
    try:
        c = TestClient(app)
        r = c.get("/api/v1/psoe/assessments",
                  params={"archetypeId": "demo-rotary-wing"})
        assert r.status_code == 200
        titles = [i["title"] for i in r.json()]
        assert titles == ["RW audit"]
    finally:
        _clear()


# ── Master register ─────────────────────────────────────────────────────────

def test_master_register_archetype_scopes_user(monkeypatch):
    from app.routes import dashboard as dash

    captured = {}

    def fake_build(user, **kw):
        captured["user"] = dict(user)
        captured["kw"] = kw
        return {"rows": [], "total": 0, "by_status": {}, "by_type": {},
                "filters": {}}

    # The route pulls build_master_register inside the handler, so patch the
    # service-module name (source of truth for the late import).
    monkeypatch.setattr("app.services.master_register.build_master_register",
                        fake_build)
    monkeypatch.setattr(
        "app.middleware.auth.get_department_scope", lambda u: None)

    caan = {"uid": "smd", "email": "smd@caanepal.gov.np", "role": "CAAN_SMD",
            "tenant_id": "caan"}
    _override(caan)
    try:
        c = TestClient(app)
        r = c.get("/api/v1/dashboard/master-register",
                  params={"archetypeId": "demo-rotary-wing"})
        assert r.status_code == 200
        assert captured["user"]["tenant_id"] == "demo-rotary-wing"
    finally:
        _clear()
