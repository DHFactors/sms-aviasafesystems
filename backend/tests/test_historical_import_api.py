# ============================================================================
# P3-6 — historical import API (upload / status / promote / reject).
# ============================================================================

import io

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user, get_safety_manager
from app.services.historical_import_service import HistoricalImportService

client = TestClient(app)


def _user(role="TENANT_ADMIN", tenant_id="air1"):
    return {"uid": "u1", "email": "sm@air1.com", "role": role, "tenant_id": tenant_id}


CSV = b"title,description,source\nOld hazard,desc,voluntary\n"


def _override(role="TENANT_ADMIN"):
    fn = lambda: _user(role=role)  # noqa: E731
    app.dependency_overrides[get_current_user] = fn
    app.dependency_overrides[get_safety_manager] = fn


def test_import_requires_tenant_admin():
    _override(role="SAFETY_OFFICER")
    try:
        r = client.post("/api/v1/hazards/import",
                        files={"file": ("h.csv", CSV, "text/csv")})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_import_upload_success(monkeypatch):
    monkeypatch.setattr(HistoricalImportService, "create_batch",
                        lambda self, user, raw, filename:
                        {"id": "batch1", "total_rows": 1, "valid_rows": 1, "error_rows": 0})
    _override()
    try:
        r = client.post("/api/v1/hazards/import",
                        files={"file": ("h.csv", CSV, "text/csv")})
        assert r.status_code == 201, r.text
        assert r.json()["data"]["id"] == "batch1"
    finally:
        app.dependency_overrides.clear()


def test_import_rejects_macro_format():
    _override()
    try:
        r = client.post("/api/v1/hazards/import",
                        files={"file": ("h.xlsm", b"x", "application/vnd.ms-excel")})
        assert r.status_code == 400
        assert "format" in r.text.lower() or "macro" in r.text.lower()
    finally:
        app.dependency_overrides.clear()


def test_import_rejects_oversize():
    _override()
    try:
        big = b"a" * (51 * 1024 * 1024)
        r = client.post("/api/v1/hazards/import",
                        files={"file": ("big.csv", big, "text/csv")})
        assert r.status_code == 413
    finally:
        app.dependency_overrides.clear()


def test_import_promote_and_reject(monkeypatch):
    monkeypatch.setattr(HistoricalImportService, "promote_batch",
                        lambda self, bid, user: {"batch_id": bid, "promoted": 2, "skipped": 0})
    monkeypatch.setattr(HistoricalImportService, "reject_batch",
                        lambda self, bid, user, reason: {"batch_id": bid, "status": "failed"})
    monkeypatch.setattr(HistoricalImportService, "list_rows",
                        lambda self, bid, status=None: [{"id": "r1", "validation_status": "valid"}])
    _override()
    try:
        p = client.post("/api/v1/hazards/import/batch1/promote")
        assert p.status_code == 200 and p.json()["data"]["promoted"] == 2

        d = client.delete("/api/v1/hazards/import/batch1")
        assert d.status_code == 200 and d.json()["data"]["status"] == "failed"

        g = client.get("/api/v1/hazards/import/batch1")
        assert g.status_code == 200 and g.json()["data"]["rows"][0]["id"] == "r1"
    finally:
        app.dependency_overrides.clear()
