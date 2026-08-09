"""
Phase 4: Automated E2E ICAO Risk Assessment Lifecycle Tests.

Tests the complete operational flow:
  1. Submission with severity_level/probability_level → auto-calculates risk_index
  2. AI analysis → stores ai_suggested_assessment with explanations
  3. Safety Manager confirmation → updates official risk_assessment
  4. RBAC enforcement → USER role rejected with 403
"""

import json
import time
from datetime import datetime, timezone
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings


# ============================================================================
# Firestore Mock Infrastructure
# ============================================================================

class MockDocumentSnapshot:
    """Simulates a Firestore document snapshot."""
    def __init__(self, data: dict, doc_id: str = None, ref=None):
        self._data = dict(data) if data else {}
        self._data["id"] = doc_id or "mock_id"
        self.id = doc_id or "mock_id"
        self.reference = ref
        self.exists = True

    def to_dict(self):
        return dict(self._data)

    def get(self, key):
        return self._data.get(key)


class MockDocumentReference:
    """Simulates a Firestore DocumentReference with write-then-read semantics.
    Supports chained .collection() calls for the tenants/{tid}/reports/ pattern.
    """

    def __init__(self, doc_id: str = None, parent_fs: 'MockFirestoreClient' = None, tenant_id: str = None):
        self._stored: Dict[str, Any] = {}
        self.id = doc_id or "mock_doc_id"
        self._parent_fs = parent_fs
        self._tenant_id = tenant_id
        self._subcollections: Dict[str, MockCollectionReference] = {}

    def set(self, data: dict):
        self._stored.update(data)

    def update(self, data: dict):
        self._stored.update(data)

    def get(self):
        return MockDocumentSnapshot(self._stored, self.id, ref=self)

    def collection(self, subcollection: str):
        if subcollection not in self._subcollections:
            self._subcollections[subcollection] = MockCollectionReference()
        return self._subcollections[subcollection]

    def delete(self):
        pass


class MockCollectionReference:
    """Simulates a Firestore CollectionReference."""

    def __init__(self):
        self._docs: Dict[str, MockDocumentReference] = {}
        self._add_counter = 0

    def document(self, doc_id: str = None):
        if doc_id is None:
            doc_id = f"auto_{self._add_counter}"
            self._add_counter += 1
        if doc_id not in self._docs:
            self._docs[doc_id] = MockDocumentReference(doc_id)
        return self._docs[doc_id]

    def add(self, data: dict):
        doc = self.document()
        doc.set(data)
        # Return (write_result, doc_ref) — FastAPI firestore client style
        write_result = MagicMock()
        write_result.update_time = None
        return write_result, doc

    def get(self):
        return [doc.get() for doc in self._docs.values()]

    def limit(self, n: int):
        return self

    def where(self, field: str, op: str, value):
        return self

    def order_by(self, field: str, **kwargs):
        return self

    def stream(self):
        return [doc.get() for doc in self._docs.values()]


class MockFirestoreClient:
    """Mock Firestore client: tenants/{tid}/reports/..."""

    def __init__(self):
        self._tenants: Dict[str, MockCollectionReference] = {}

    def collection(self, path: str):
        return self._get_or_create_top(path)

    def _get_or_create_top(self, path: str):
        return _TopLevelCollection(path, self)

    def collection_group(self, collection_name: str):
        return _CollectionGroupMock(collection_name, self)

    def get_tenant_reports(self, tenant_id: str) -> MockCollectionReference:
        return self._get_or_create_top("tenants").document(tenant_id).collection("reports")


class _TopLevelCollection:
    def __init__(self, path: str, client: MockFirestoreClient):
        self._path = path
        self._client = client
        if path not in client._tenants:
            client._tenants[path] = MockCollectionReference()
        self._ref = client._tenants[path]

    def document(self, doc_id: str = None):
        return self._ref.document(doc_id)

    def add(self, data: dict):
        return self._ref.add(data)

    def where(self, field: str, op: str, value):
        return self._ref.where(field, op, value)

    def get(self):
        return self._ref.get()


class _CollectionGroupMock:
    """Collection group mock that traverses tenant sub-collections.

    This makes cross-tenant (collection_group) queries observable in tests so
    the CAAN_SMD / SUPER_ADMIN cross-tenant paths are actually exercised.
    """
    def __init__(self, collection_name: str, client: MockFirestoreClient):
        self._name = collection_name
        self._client = client
        self._filters = []

    def where(self, field: str, op: str, value):
        self._filters.append((field, op, value))
        return self

    def limit(self, n: int):
        return self

    def get(self):
        results = []
        tenants = self._client._tenants.get("tenants")
        if tenants:
            for tenant_doc in tenants._docs.values():
                for sub_name, sub_ref in tenant_doc._subcollections.items():
                    if sub_name != self._name:
                        continue
                    for doc_id, doc_ref in sub_ref._docs.items():
                        snap = MockDocumentSnapshot(dict(doc_ref._stored), doc_id, ref=doc_ref)
                        results.append(snap)
        for field, op, value in self._filters:
            if field == "__name__" and op == "==":
                results = [r for r in results if r.id == value]
        return results


# ============================================================================
# Pytest Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def mock_firebase_and_gemini(monkeypatch):
    """Replace Firebase and Gemini with in-memory mocks for clean test isolation."""

    # -- Firestore mock --
    fs_client = MockFirestoreClient()
    monkeypatch.setattr("app.firebase.get_db", lambda: fs_client)
    monkeypatch.setattr("app.firebase.get_tenant_collection",
                        lambda tid, coll: fs_client._get_or_create_top("tenants").document(tid).collection(coll))
    monkeypatch.setattr("app.firebase.get_cross_tenant_collection",
                        lambda coll: fs_client.collection_group(coll))
    monkeypatch.setattr("app.firebase.initialize_firebase", lambda: None)
    monkeypatch.setattr("app.firebase.is_firebase_ready", lambda: True)
    monkeypatch.setattr("app.firebase.get_tenant_metadata",
                        lambda tid: {"risk_matrix": {"thresholds": {"low_max": 5, "medium_max": 9, "high_max": 15}}})
    monkeypatch.setattr("app.firebase._db", fs_client)

    # -- Token verification: return decoded token based on a simple "token" string --
    import app.firebase as fb_mod
    import app.middleware.auth as auth_mod

    def fake_verify(token: str) -> Dict[str, Any]:
        claims = {"role": "USER", "tenant_id": None}
        if token == "AIRLINE_ADMIN_TOKEN":
            claims = {"role": "AIRLINE_ADMIN", "tenant_id": "test_airline"}
        elif token == "SUPER_ADMIN_TOKEN":
            claims = {"role": "SUPER_ADMIN", "tenant_id": None}
        elif token == "CAAN_SMD_TOKEN":
            claims = {"role": "CAAN_SMD", "tenant_id": None}
        elif token == "USER_TOKEN":
            claims = {"role": "USER", "tenant_id": None}
        return {"uid": "mock_user", "email": "test@aviasafe.com", **claims}

    monkeypatch.setattr(fb_mod, "verify_firebase_token", fake_verify)
    monkeypatch.setattr(auth_mod, "verify_firebase_token", fake_verify)

    # -- Gemini mock: return a controlled AI analysis --
    # Must patch both the module AND the import site (report_service uses `from gemini import analyze_report`)
    fake_analysis = {
        "occurrence_type": "System/Component Failure",
        "human_factors": ["Procedural Deviation"],
        "risk_level": "Medium",
        "phase_of_flight": "En-route",
        "summary": "Test AI analysis summary.",
        "recommendations": ["Review maintenance procedures."],
        "suggested_severity": 4,
        "severity_explanation": "Severity 4 based on keyword indicators. In aviation, this corresponds to events with life-threatening injuries, similar to serious incidents documented in NTSB accident reports.",
        "suggested_probability": 2,
        "probability_explanation": "Probability 2 based on recurrence keywords. Industry data shows events at this level correspond to improbable occurrences per EASA Annual Safety Review.",
    }
    monkeypatch.setattr("app.services.gemini.analyze_report", lambda narrative: fake_analysis)
    monkeypatch.setattr("app.services.report_service.analyze_report", lambda narrative: fake_analysis)
    monkeypatch.setattr("app.services.gemini.classify_mandatory",
                        lambda narrative: {"is_mandatory": True, "category": "A", "confidence": 0.95})
    monkeypatch.setattr("app.services.report_service.classify_mandatory",
                        lambda narrative: {"is_mandatory": True, "category": "A", "confidence": 0.95})

    yield fs_client


def _auth_header(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(mock_firebase_and_gemini):
    """FastAPI TestClient created AFTER Firebase + Gemini patches are applied."""
    return TestClient(app)


# ============================================================================
# Test 1: Submission & Auto-Calculation
# ============================================================================

class TestSubmissionAutoCalculation:
    """Verify that submitting with severity_level & probability_level auto-computes risk_index."""

    def test_auto_calculation_3x3_equals_9(self, client):
        body = {
            "narrative": "Test report narrative for auto-calculation verification. Engine vibration during cruise.",
            "location": "KTM",
            "occurrence_date": datetime.now(timezone.utc).isoformat(),
            "report_type": "mandatory",
            "severity_level": 3,
            "probability_level": 3,
        }
        resp = client.post("/api/v1/reports/", json=body,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))

        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert data["severity_level"] == 3, f"Expected severity_level=3, got {data.get('severity_level')}"
        assert data["probability_level"] == 3, f"Expected probability_level=3, got {data.get('probability_level')}"
        assert data["risk_index"] == 9, f"Expected risk_index=9 (3×3), got {data.get('risk_index')}"
        assert data["risk_level"] == "Medium", f"Expected risk_level=Medium, got {data.get('risk_level')}"
        assert data["report_type"] == "mandatory"
        assert data["status"] == "NEW"

    def test_auto_calculation_5x5_equals_25(self, client):
        body = {
            "narrative": "Critical engine failure during takeoff causing hull loss.",
            "location": "KTM",
            "occurrence_date": datetime.now(timezone.utc).isoformat(),
            "report_type": "mandatory",
            "severity_level": 5,
            "probability_level": 5,
        }
        resp = client.post("/api/v1/reports/", json=body,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["risk_index"] == 25, f"Expected risk_index=25 (5×5), got {data.get('risk_index')}"
        assert data["risk_level"] == "Very High", f"Expected Very High, got {data.get('risk_level')}"

    def test_auto_calculation_1x1_equals_1(self, client):
        body = {
            "narrative": "Minor cabin event during pushback.",
            "location": "KTM",
            "occurrence_date": datetime.now(timezone.utc).isoformat(),
            "report_type": "voluntary",
            "severity_level": 1,
            "probability_level": 1,
        }
        resp = client.post("/api/v1/reports/", json=body,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["risk_index"] == 1, f"Expected risk_index=1, got {data.get('risk_index')}"
        assert data["risk_level"] == "Low", f"Expected Low, got {data.get('risk_level')}"

    def test_submission_without_icao_fields_backward_compat(self, client):
        body = {
            "narrative": "Legacy format report without ICAO risk fields.",
            "location": "KTM",
            "occurrence_date": datetime.now(timezone.utc).isoformat(),
            "report_type": "voluntary",
        }
        resp = client.post("/api/v1/reports/", json=body,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("severity_level") is None, f"Expected None, got {data.get('severity_level')}"
        assert data.get("risk_index") is None, f"Expected None, got {data.get('risk_index')}"

    def test_submission_with_invalid_severity_rejected(self, client):
        body = {
            "narrative": "Report with out-of-range severity.",
            "location": "KTM",
            "occurrence_date": datetime.now(timezone.utc).isoformat(),
            "report_type": "voluntary",
            "severity_level": 6,
        }
        resp = client.post("/api/v1/reports/", json=body,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp.status_code == 422, f"Expected 422 for invalid severity, got {resp.status_code}"

    def test_submission_with_invalid_probability_rejected(self, client):
        body = {
            "narrative": "Report with out-of-range probability.",
            "location": "KTM",
            "occurrence_date": datetime.now(timezone.utc).isoformat(),
            "report_type": "voluntary",
            "probability_level": 0,
        }
        resp = client.post("/api/v1/reports/", json=body,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp.status_code == 422, f"Expected 422 for invalid probability, got {resp.status_code}"


# ============================================================================
# Test 2: AI Grounding & Suggestion
# ============================================================================

class TestAiGroundingAndSuggestion:
    """Verify that AI analysis correctly populates ai_suggested_assessment."""

    def test_ai_suggested_assessment_stored_with_explanations(self, client):
        # Submit report without ICAO fields (so AI provides initial assessment)
        body = {
            "narrative": "Engine flameout during initial climb after bird ingestion. Two engines affected, emergency declared, returned to airport.",
            "location": "KTM",
            "occurrence_date": datetime.now(timezone.utc).isoformat(),
            "report_type": "mandatory",
        }
        resp = client.post("/api/v1/reports/", json=body,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp.status_code == 201
        report = resp.json()
        report_id = report["id"]

        # Trigger AI analysis (normally done via background task, call directly)
        from app.services.report_service import ReportService
        svc = ReportService("test_airline")
        svc.run_ai_analysis(report_id, body["narrative"])

        # Retrieve updated report
        resp2 = client.get(f"/api/v1/reports/{report_id}",
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp2.status_code == 200
        updated = resp2.json()

        ai_suggested = updated.get("ai_suggested_assessment")
        assert ai_suggested is not None, "ai_suggested_assessment should be present after AI analysis"

        # Verify structure
        assert ai_suggested["suggested_severity"] == 4, f"Expected 4, got {ai_suggested.get('suggested_severity')}"
        assert ai_suggested["suggested_probability"] == 2, f"Expected 2, got {ai_suggested.get('suggested_probability')}"
        assert ai_suggested["suggested_risk_index"] == 8, f"Expected 8 (4×2), got {ai_suggested.get('suggested_risk_index')}"
        assert ai_suggested["suggested_risk_level"] == "Medium", f"Expected Medium, got {ai_suggested.get('suggested_risk_level')}"

        # Verify explanations are present (Phase 2 grounding requirement)
        assert "severity_explanation" in ai_suggested, "Missing severity_explanation"
        assert "probability_explanation" in ai_suggested, "Missing probability_explanation"
        assert len(ai_suggested["severity_explanation"]) > 20, "severity_explanation too short"
        assert len(ai_suggested["probability_explanation"]) > 20, "probability_explanation too short"

        # Verify ai_analysis is also present
        assert updated.get("ai_analysis") is not None, "ai_analysis should be present"
        assert updated["ai_status"] == "COMPLETED"

    def test_ai_suggested_assessment_contains_real_aviation_references(self, client):
        """Verify severity_explanation contains aviation-specific terminology."""
        body = {
            "narrative": "Near mid-air collision during approach.",
            "location": "KTM",
            "occurrence_date": datetime.now(timezone.utc).isoformat(),
            "report_type": "mandatory",
        }
        resp = client.post("/api/v1/reports/", json=body,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp.status_code == 201
        report = resp.json()

        from app.services.report_service import ReportService
        svc = ReportService("test_airline")
        svc.run_ai_analysis(report["id"], body["narrative"])

        resp2 = client.get(f"/api/v1/reports/{report['id']}",
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        updated = resp2.json()
        ai = updated["ai_suggested_assessment"]

        # Should reference aviation concepts
        aviation_terms = ["NTSB", "EASA", "accident", "incident", "aviation", "ICAO", "safety"]
        has_term = any(term in ai.get("severity_explanation", "") or term in ai.get("probability_explanation", "")
                       for term in aviation_terms)
        assert has_term, f"Expected aviation reference in explanations, got: sev={ai.get('severity_explanation')}, prob={ai.get('probability_explanation')}"


# ============================================================================
# Test 3: Safety Manager Override & RBAC
# ============================================================================

class TestSafetyManagerOverride:
    """Verify Safety Manager can override assessment and RBAC is enforced."""

    def test_airline_admin_can_confirm_risk_assessment(self, client):
        body = {
            "narrative": "Report requiring Safety Manager assessment confirmation.",
            "location": "KTM",
            "occurrence_date": datetime.now(timezone.utc).isoformat(),
            "report_type": "mandatory",
            "severity_level": 2,
            "probability_level": 3,
        }
        resp = client.post("/api/v1/reports/", json=body,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp.status_code == 201
        report = resp.json()
        assert report["risk_index"] == 6  # 2×3
        assert report["risk_level"] == "Medium"

        report_id = report["id"]

        # Safety Manager overrides: severity=4, probability=4
        override = {"severity": 4, "probability": 4, "notes": "Safety Manager override: actual severity higher based on flight data analysis."}
        resp2 = client.put(f"/api/v1/reports/{report_id}/risk-assessment",
                           json=override,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))

        assert resp2.status_code == 200, f"Expected 200, got {resp2.status_code}: {resp2.text}"
        updated = resp2.json()

        # Final risk_index should be 4×4 = 16
        assert updated["severity_level"] == 4, f"Expected severity_level=4, got {updated.get('severity_level')}"
        assert updated["probability_level"] == 4, f"Expected probability_level=4, got {updated.get('probability_level')}"
        assert updated["risk_index"] == 16, f"Expected risk_index=16 (4×4), got {updated.get('risk_index')}"
        assert updated["risk_level"] == "Very High", f"Expected Very High, got {updated.get('risk_level')}"

        # Verify official risk_assessment block
        ra = updated.get("risk_assessment")
        assert ra is not None, "risk_assessment should be present"
        assert ra["severity"] == 4
        assert ra["probability"] == 4
        assert ra["risk_index"] == 16
        assert ra["risk_level"] == "Very High"
        assert ra["assessed_by"] == "mock_user", f"Expected mock_user, got {ra.get('assessed_by')}"
        assert "assessed_at" in ra, "assessed_at timestamp should be present"

    def test_user_role_rejected_with_403(self, client):
        """Standard USER token must be rejected with 403 for risk-assessment endpoint."""
        body = {
            "narrative": "Report for RBAC test.",
            "location": "KTM",
            "occurrence_date": datetime.now(timezone.utc).isoformat(),
            "report_type": "voluntary",
        }
        resp = client.post("/api/v1/reports/", json=body,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp.status_code == 201
        report_id = resp.json()["id"]

        # Attempt override with USER token
        override = {"severity": 3, "probability": 3}
        resp2 = client.put(f"/api/v1/reports/{report_id}/risk-assessment",
                           json=override,
                           headers=_auth_header("USER_TOKEN"))

        assert resp2.status_code == 403, f"Expected 403 for USER role, got {resp2.status_code}: {resp2.text}"

    def test_caan_smd_can_confirm_risk_assessment(self, client):
        """CAAN_SMD should have same authority as AIRLINE_ADMIN."""
        body = {
            "narrative": "Report assessed by regulator.",
            "location": "KTM",
            "occurrence_date": datetime.now(timezone.utc).isoformat(),
            "report_type": "mandatory",
        }
        resp = client.post("/api/v1/reports/", json=body,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp.status_code == 201
        report_id = resp.json()["id"]

        override = {"severity": 5, "probability": 3}
        resp2 = client.put(f"/api/v1/reports/{report_id}/risk-assessment",
                           json=override,
                           headers=_auth_header("CAAN_SMD_TOKEN"))
        assert resp2.status_code == 200, f"Expected 200 for CAAN_SMD, got {resp2.status_code}: {resp2.text}"
        data = resp2.json()
        assert data["risk_index"] == 15, f"Expected 15 (5×3), got {data.get('risk_index')}"
        assert data["risk_level"] == "High", f"Expected High, got {data.get('risk_level')}"

    def test_super_admin_can_confirm_risk_assessment(self, client):
        """SUPER_ADMIN should have full access."""
        body = {
            "narrative": "Report assessed by super admin.",
            "location": "KTM",
            "occurrence_date": datetime.now(timezone.utc).isoformat(),
            "report_type": "voluntary",
        }
        resp = client.post("/api/v1/reports/", json=body,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp.status_code == 201
        report_id = resp.json()["id"]

        override = {"severity": 2, "probability": 5}
        resp2 = client.put(f"/api/v1/reports/{report_id}/risk-assessment",
                           json=override,
                           headers=_auth_header("SUPER_ADMIN_TOKEN"))
        assert resp2.status_code == 200, f"Expected 200 for SUPER_ADMIN, got {resp2.status_code}: {resp2.text}"
        data = resp2.json()
        assert data["risk_index"] == 10, f"Expected 10 (2×5), got {data.get('risk_index')}"


# ============================================================================
# Test 4: End-to-End Lifecycle (complete flow)
# ============================================================================

class TestFullLifecycle:
    """Complete operational flow from submission to final official assessment."""

    def test_complete_lifecycle(self, client):
        # Step 1: Submit MOR with initial assessment (S=3, P=3 → RI=9, Medium)
        body = {
            "narrative": "Dual hydraulic system failure during approach. Emergency checklists performed. Landed safely with reduced braking.",
            "location": "KTM",
            "occurrence_date": datetime.now(timezone.utc).isoformat(),
            "report_type": "mandatory",
            "severity_level": 3,
            "probability_level": 3,
        }
        resp = client.post("/api/v1/reports/", json=body,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp.status_code == 201
        report = resp.json()
        assert report["risk_index"] == 9
        assert report["risk_level"] == "Medium"
        report_id = report["id"]

        # Step 2: AI analysis (simulated by mock) provides suggested assessment
        from app.services.report_service import ReportService
        svc = ReportService("test_airline")
        svc.run_ai_analysis(report_id, body["narrative"])

        resp2 = client.get(f"/api/v1/reports/{report_id}",
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        updated = resp2.json()
        ai = updated["ai_suggested_assessment"]
        assert ai["suggested_severity"] == 4
        assert ai["suggested_probability"] == 2
        assert ai["suggested_risk_index"] == 8  # 4×2
        assert "severity_explanation" in ai
        assert "probability_explanation" in ai

        # Step 3: Safety Manager reviews AI suggestion, disagrees, overrides
        override = {
            "severity": 3,
            "probability": 2,
            "notes": "Safety Manager review: severity is major but probability is improbable due to redundant systems. Override AI suggestion."
        }
        resp3 = client.put(f"/api/v1/reports/{report_id}/risk-assessment",
                           json=override,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp3.status_code == 200
        final = resp3.json()

        # Step 4: Verify final state
        assert final["severity_level"] == 3
        assert final["probability_level"] == 2
        assert final["risk_index"] == 6  # 3×2
        assert final["risk_level"] == "Medium"

        ra = final["risk_assessment"]
        assert ra["severity"] == 3
        assert ra["probability"] == 2
        assert ra["risk_index"] == 6
        assert ra["assessed_by"] == "mock_user"
        assert ra["notes"] == override["notes"]

        # Step 5: Verify ai_suggested_assessment is preserved alongside official
        assert final["ai_suggested_assessment"] is not None
        assert final["ai_suggested_assessment"]["suggested_severity"] == 4

        # Step 6: Verify legacy fields preserved
        assert "narrative" in final
        assert final["report_type"] == "mandatory"

    def test_unauthorized_user_cannot_access_report(self, client):
        """USER without tenant access should be rejected."""
        resp = client.get("/api/v1/reports/",
                          headers=_auth_header("USER_TOKEN"))
        # USER has no tenant_id, so get_tenant_user should reject
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


# ============================================================================
# RC-4 UAT regression tests — cross-tenant & authorization findings
# ============================================================================

class TestCrossTenantAndAuthorization:
    """Regression tests for verified RC-4 defects (UAT-001/002/003/007)."""

    def test_caan_confirm_lands_in_owner_tenant(self, client):
        """CAAN (no tenant claim) confirms a report created by an airline;
        the update must land on the airline's report (cross-tenant)."""
        body = {
            "narrative": "Regulator confirmation of cross-tenant assessment.",
            "location": "KTM",
            "occurrence_date": datetime.now(timezone.utc).isoformat(),
            "report_type": "mandatory",
        }
        resp = client.post("/api/v1/reports/", json=body,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp.status_code == 201, resp.text
        report_id = resp.json()["id"]

        override = {"severity": 4, "probability": 2, "notes": "CAAN cross-tenant confirmation."}
        resp2 = client.put(f"/api/v1/reports/{report_id}/risk-assessment",
                           json=override,
                           headers=_auth_header("CAAN_SMD_TOKEN"))
        assert resp2.status_code == 200, f"Expected 200, got {resp2.status_code}: {resp2.text}"
        assert resp2.json()["risk_index"] == 8, resp2.text

        # The owner airline must now see the CAAN-confirmed assessment
        resp3 = client.get(f"/api/v1/reports/{report_id}",
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp3.status_code == 200, resp3.text
        confirmed = resp3.json()
        assert confirmed["risk_assessment"]["severity"] == 4, resp3.text
        assert confirmed["risk_level"] == "Medium"

    def test_caan_lists_reports_across_tenants(self, client):
        """CAAN (no tenant claim) can list reports across tenants (regression for
        the 403 thrown when GET /api/v1/reports used get_tenant_user)."""
        resp = client.get("/api/v1/reports/",
                          headers=_auth_header("CAAN_SMD_TOKEN"))
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_caan_reads_can_caps_across_tenants(self, client):
        """CAAN can list CAPs and latest-CAP across tenants (UAT-002)."""
        can_body = {
            "hazard_id": "haz-1",
            "title": "Engine vibration during climb",
            "description": "Observed persistent engine vibration during climb.",
            "required_action": "Inspect and rectify per maintenance manual.",
            "target_completion_date": "2026-12-31T00:00:00Z",
            "assigned_to": "Engineer A",
            "assigned_to_uid": "user-1",
            "priority": "High",
        }
        resp = client.post("/api/v1/cans/", json=can_body,
                           headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        can_id = resp.json()["id"]

        cap_body = {
            "can_id": can_id,
            "action_plan": "Perform full engine inspection and replace vibration sensors.",
            "timeline": "30 days",
            "resources_required": "Borescope kit",
            "target_completion_date": "2026-12-31T00:00:00Z",
        }
        resp2 = client.post(f"/api/v1/cans/{can_id}/caps", json=cap_body,
                            headers=_auth_header("AIRLINE_ADMIN_TOKEN"))
        assert resp2.status_code == 201, f"Expected 201, got {resp2.status_code}: {resp2.text}"
        cap_id = resp2.json()["id"]

        resp3 = client.get(f"/api/v1/cans/{can_id}",
                           headers=_auth_header("CAAN_SMD_TOKEN"))
        assert resp3.status_code == 200, resp3.text
        assert resp3.json().get("latest_cap") is not None, "latest_cap should be present for CAAN"

        resp4 = client.get(f"/api/v1/cans/{can_id}/caps",
                           headers=_auth_header("CAAN_SMD_TOKEN"))
        assert resp4.status_code == 200, resp4.text
        caps = resp4.json()
        assert any(c["id"] == cap_id for c in caps), f"CAAN should see the CAP, got {caps}"

    def test_caan_cannot_write_can_without_tenant(self, client):
        """Cross-tenant roles cannot write CAN/CAP without a tenant (UAT-007)."""
        body = {
            "hazard_id": "haz-1",
            "title": "Engine vibration during climb",
            "description": "Observed persistent engine vibration during climb.",
            "required_action": "Inspect and rectify per maintenance manual.",
            "target_completion_date": "2026-12-31T00:00:00Z",
            "assigned_to": "Engineer A",
            "assigned_to_uid": "user-1",
            "priority": "High",
        }
        resp = client.post("/api/v1/cans/", json=body,
                           headers=_auth_header("CAAN_SMD_TOKEN"))
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"

    def test_user_cannot_override_tenant_for_report(self, client):
        """USER cannot select another tenant when generating reports (UAT-003)."""
        resp = client.post(
            "/api/v1/reporting/quarterly?year=2026&quarter=1&tenant_id=other_airline",
            json={},
            headers=_auth_header("USER_TOKEN"),
        )
        # USER has no tenant claim and must not be able to reach another tenant
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"

    def test_airline_admin_still_generates_own_tenant_report(self, client):
        """AIRLINE_ADMIN report generation for their own tenant still works."""
        resp = client.post(
            "/api/v1/reporting/quarterly?year=2026&quarter=1",
            json={},
            headers=_auth_header("AIRLINE_ADMIN_TOKEN"),
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["tenant_id"] == "test-airline", resp.text

    def test_caan_generates_national_report(self, client):
        """CAAN can still generate a national (cross-tenant) quarterly report."""
        resp = client.post(
            "/api/v1/reporting/quarterly?year=2026&quarter=1",
            json={},
            headers=_auth_header("CAAN_SMD_TOKEN"),
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["tenant_id"] is None, resp.text
        assert data["report_type"] == "quarterly"
