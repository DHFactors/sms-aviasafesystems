#!/usr/bin/env python3
"""
UAT API Smoke Runner — validates all Phase 1 endpoints via FastAPI TestClient.

Runs against the in-process app (no live server required). Patches auth
dependencies so no real Firebase tokens are needed. Tests:

  1. GET  /health
  2. GET  /api/v1/state-risk/aggregate   (CAAN regulated)
  3. GET  /api/v1/state-risk/export-pdf  (PDF binary + SHA-256)
  4. GET  /api/v1/tenants/sms/monthly-summary  (tenant scoped)
  5. GET  /api/v1/tenants/sms/export-pdf       (PDF binary)
  6. POST /api/v1/cron/weekly-ssp-dispatch     (task key protected)
  7. GET  /api/v1/state-risk/audit-logs        (regulator audit)
  8. GET  /api/v1/tenants/sms/audit-logs       (tenant audit)

Usage:
  python scripts/run_uat_smoke.py
"""

import hashlib
import sys
import os
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from fastapi.testclient import TestClient
from app.main import app
from app.middleware.auth import get_caan_user, get_tenant_user


# ── Fake user fixtures ────────────────────────────────────────────────────────

FAKE_CAAN_USER = {
    "uid": "uid-caan-smoke",
    "email": "caan@caanepal.gov.np",
    "role": "CAAN_SMD",
    "tenant_id": None,
    "department": None,
    "claims": {"role": "CAAN_SMD", "tenant_id": None, "department": None},
}

FAKE_TENANT_USER = {
    "uid": "uid-tenant-smoke",
    "email": "safety@fishtail-air.com.np",
    "role": "AIRLINE_ADMIN",
    "tenant_id": "fishtail-air",
    "department": None,
    "claims": {"role": "AIRLINE_ADMIN", "tenant_id": "fishtail-air", "department": None},
}


# ── Fake Firestore DB ─────────────────────────────────────────────────────────

class _FakeDoc:
    def __init__(self, data, exists=True, doc_id="snap"):
        self._data = data or {}
        self.exists = exists
        self.id = doc_id

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self, data=None, exists=True):
        self._data = data or {}
        self.exists = exists

    def get(self):
        return _FakeDoc(self._data, exists=self.exists)

    def to_dict(self):
        return self._data


class _FakeCollection:
    def __init__(self, rows=None):
        self._rows = rows or []
        self._by_id = {r.get("id", r.get("tenant_id", "")): r for r in self._rows}

    def document(self, doc_id):
        data = self._by_id.get(doc_id, {})
        exists = doc_id in self._by_id
        return _FakeDocRef(data, exists=exists)

    def where(self, *a, **kw):
        return self

    def order_by(self, *a, **kw):
        return self

    def limit(self, *a):
        return self

    def stream(self):
        return [_FakeDoc(r, doc_id=r.get("id", "x")) for r in self._rows]

    def get(self):
        return [_FakeDoc(r, doc_id=r.get("id", "x")) for r in self._rows]

    def set(self, *a, **kw):
        pass

    def update(self, *a, **kw):
        pass


def _fake_db():
    class FakeDB:
        def collection(self, path):
            if path == "tenants":
                return _FakeCollection([
                    {"id": "fishtail-air", "operator_name": "Fishtail Air", "aoc_number": "AOC-042-NEP",
                     "flight_hours": 8420.5, "total_flights": 2340, "status": "active"},
                ])
            if path.endswith("/hazards"):
                return _FakeCollection([
                    {"id": "hz-1", "status": "OPEN", "risk_level": "High", "occurrence_category": "LOCI"},
                    {"id": "hz-2", "status": "CLOSED", "risk_level": "Low", "occurrence_category": "BIRD"},
                ])
            if path.endswith("/reports"):
                return _FakeCollection([
                    {"id": "rpt-1", "type": "voluntary"},
                    {"id": "rpt-2", "type": "mandatory"},
                ])
            if path.endswith("/cans"):
                return _FakeCollection([
                    {"id": "capa-1", "can_number": "CAPA-001", "description": "Fix brakes",
                     "responsible": "CP", "due_date": "2026-09-30", "status": "OPEN", "priority": "HIGH"},
                ])
            if path.endswith("/spis"):
                return _FakeCollection([
                    {"id": "spi-1", "name": "Dispatch Reliability", "domain": "MAINT",
                     "current_value": 97.8, "target_value": 98.0, "is_on_target": False, "trend": "declining"},
                ])
            if path.startswith("regulators"):
                return _FakeCollection([{"id": "caan", "notification_emails": ["caan@caanepal.gov.np"]}])
            if path.startswith("audit_logs"):
                return _FakeCollection([])
            return _FakeCollection([])

        def collection_group(self, name):
            return self.collection(name)

    return FakeDB()


# ── Test runner ───────────────────────────────────────────────────────────────

class UatSmokeRunner:
    def __init__(self):
        self.results: list[Dict[str, Any]] = []
        self.client = TestClient(app)

    def _record(self, name: str, passed: bool, detail: str = ""):
        status = "PASS" if passed else "FAIL"
        self.results.append({"test": name, "status": status, "detail": detail})
        icon = "[OK]" if passed else "[!!]"
        print(f"  {icon} {status}: {name}" + (f" -- {detail}" if detail else ""))

    def run_all(self):
        print("=" * 70)
        print("  aviaSDCPS UAT API Smoke Runner")
        print("=" * 70)

        self._test_health()
        self._test_state_risk_aggregate()
        self._test_state_risk_export_pdf()
        self._test_tenant_monthly_summary()
        self._test_tenant_export_pdf()
        self._test_cron_weekly_dispatch()
        self._test_regulator_audit_logs()
        self._test_tenant_audit_logs()

        # Summary
        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = total - passed
        print("\n" + "=" * 70)
        print(f"  Results: {passed}/{total} passed, {failed} failed")
        print("=" * 70)
        return failed == 0

    # ── Test cases ────────────────────────────────────────────────────────

    def _test_health(self):
        resp = self.client.get("/health")
        ok = resp.status_code == 200 and resp.json().get("status") == "healthy"
        self._test_health_status = ok
        self._record("GET /health", ok, f"status={resp.status_code}")

    def _test_state_risk_aggregate(self):
        with patch("app.services.state_risk_service.get_db", return_value=_fake_db()):
            app.dependency_overrides[get_caan_user] = lambda: FAKE_CAAN_USER
            resp = self.client.get("/api/v1/state-risk/aggregate?year=2026&quarter=3")
            app.dependency_overrides.clear()
            body = resp.json() if resp.status_code == 200 else {}
            ok = resp.status_code == 200 and "risks" in body
            self._test_aggregate_status = ok
            risk_count = len(body.get("risks", []))
            self._record("GET /state-risk/aggregate", ok, f"risks={risk_count}")

    def _test_state_risk_export_pdf(self):
        with patch("app.services.state_risk_service.get_db", return_value=_fake_db()):
            with patch("app.api.v1.state_risk.StateRiskService") as MockSvc:
                mock_svc = MockSvc.return_value
                mock_svc.aggregate_state_risk.return_value = {
                    "risks": [], "total_hazards": 0, "total_operators": 0,
                }
                app.dependency_overrides[get_caan_user] = lambda: FAKE_CAAN_USER
                resp = self.client.get("/api/v1/state-risk/export-pdf?year=2026&quarter=3")
                app.dependency_overrides.clear()

                is_pdf = resp.status_code == 200 and resp.content[:5] == b"%PDF-"
                sha256 = hashlib.sha256(resp.content).hexdigest() if is_pdf else ""
                ok = is_pdf and len(sha256) == 64
                self._test_pdf_status = ok
                self._record("GET /state-risk/export-pdf", ok,
                             f"size={len(resp.content)}, sha256={sha256[:16]}...")

    def _test_tenant_monthly_summary(self):
        with patch("app.api.v1.tenant_reports.get_db", return_value=_fake_db()):
            app.dependency_overrides[get_tenant_user] = lambda: FAKE_TENANT_USER
            resp = self.client.get("/api/v1/tenants/sms/monthly-summary?year=2026&month=8")
            app.dependency_overrides.clear()
            body = resp.json() if resp.status_code == 200 else {}
            ok = resp.status_code == 200 and body.get("success") is True
            report = body.get("report", {})
            self._test_summary_status = ok
            self._record("GET /tenants/sms/monthly-summary", ok,
                         f"hazards={report.get('total_hazards')}, capas={len(report.get('open_capas', []))}")

    def _test_tenant_export_pdf(self):
        with patch("app.api.v1.tenant_reports.get_db", return_value=_fake_db()):
            app.dependency_overrides[get_tenant_user] = lambda: FAKE_TENANT_USER
            resp = self.client.get("/api/v1/tenants/sms/export-pdf?year=2026&month=8")
            app.dependency_overrides.clear()
            is_pdf = resp.status_code == 200 and resp.content[:5] == b"%PDF-"
            sha256 = hashlib.sha256(resp.content).hexdigest() if is_pdf else ""
            ok = is_pdf and len(sha256) == 64
            self._record("GET /tenants/sms/export-pdf", ok,
                         f"size={len(resp.content)}, sha256={sha256[:16]}...")

    def _test_cron_weekly_dispatch(self):
        with patch("app.api.v1.cron.settings") as mock_settings:
            mock_settings.TASK_API_KEY = "uat-test-key"
            with patch("app.api.v1.cron._verify_task_key", return_value=True):
                with patch("app.api.v1.cron.ScheduledReportWorker") as MockWorker:
                    MockWorker.return_value.run_weekly_ssp_dispatch.return_value = {
                        "dispatched": 1, "results": []
                    }
                    resp = self.client.post("/api/v1/cron/weekly-ssp-dispatch?taskKey=uat-test-key")
                    ok = resp.status_code == 200 and resp.json().get("success") is True
                    self._test_cron_status = ok
                    self._record("POST /cron/weekly-ssp-dispatch", ok,
                                 f"dispatched={resp.json().get('result', {}).get('dispatched', '?')}")

    def _test_regulator_audit_logs(self):
        with patch("app.api.v1.state_risk.list_recent_dispatches", return_value=[
            {"audit_id": "ssp-caan-2026Q3", "status": "delivered",
             "pdf_sha256_checksum": "a" * 64, "created_at": datetime.now(timezone.utc).isoformat()}
        ]):
            app.dependency_overrides[get_caan_user] = lambda: FAKE_CAAN_USER
            resp = self.client.get("/api/v1/state-risk/audit-logs?limit=10")
            app.dependency_overrides.clear()
            body = resp.json() if resp.status_code == 200 else {}
            ok = resp.status_code == 200 and body.get("success") is True
            logs = body.get("logs", [])
            sha_valid = all(len(l.get("pdf_sha256_checksum", "")) == 64 for l in logs) if logs else True
            self._record("GET /state-risk/audit-logs", ok and sha_valid,
                         f"count={len(logs)}, sha_valid={sha_valid}")

    def _test_tenant_audit_logs(self):
        with patch("app.api.v1.tenant_reports.list_tenant_dispatches", return_value=[
            {"audit_id": "srb-fishtail-202608", "status": "delivered",
             "pdf_sha256_checksum": "b" * 64, "created_at": datetime.now(timezone.utc).isoformat()}
        ]):
            app.dependency_overrides[get_tenant_user] = lambda: FAKE_TENANT_USER
            resp = self.client.get("/api/v1/tenants/sms/audit-logs?limit=10")
            app.dependency_overrides.clear()
            body = resp.json() if resp.status_code == 200 else {}
            ok = resp.status_code == 200 and body.get("success") is True
            logs = body.get("logs", [])
            sha_valid = all(len(l.get("pdf_sha256_checksum", "")) == 64 for l in logs) if logs else True
            self._record("GET /tenants/sms/audit-logs", ok and sha_valid,
                         f"count={len(logs)}, sha_valid={sha_valid}")


if __name__ == "__main__":
    runner = UatSmokeRunner()
    success = runner.run_all()
    sys.exit(0 if success else 1)
