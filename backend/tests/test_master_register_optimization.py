"""Master Register optimization tests — Firestore filtering, pagination, cursor, tenant isolation."""
import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import master_register


def _dt(days_ago=0, hours_ago=0):
    return datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)

def _encode_cursor(iso):
    return base64.urlsafe_b64encode(json.dumps({"last_date": iso}).encode()).decode().rstrip("=")


# --- Mock Firestore helpers that support where/order_by/limit/start_after/count ---

class MockDoc:
    def __init__(self, id, data, caps=None, path=None):
        self.id = id
        self._data = dict(data)
        self.reference = MockRef(self, caps)
        self._path = path or f"tenants/t1/can_cap/{id}"
    def to_dict(self):
        return dict(self._data)
    def get(self, field):
        # For order_by cursor simulation, support get(field)
        return self._data.get(field)

class MockRef:
    def __init__(self, owner, caps):
        self._owner = owner
        self._caps = caps or []
        self.path = owner._path if hasattr(owner, "_path") else ""
        self._path = self.path
    def collection(self, name):
        assert name == "caps"
        return MockColl(self._caps)

class MockColl:
    def __init__(self, docs):
        self._docs = list(docs)
        self._filters = []
        self._order_field = None
        self._order_dir = None
        self._limit = None
        self._start_after = None
        self.calls = {"where": 0, "order_by": 0, "limit": 0, "start_after": 0, "count": 0, "get": 0}
    def where(self, field, op, value):
        self.calls["where"] += 1
        # Simple filtering for test
        filtered = []
        for d in self._docs:
            v = d.to_dict().get(field)
            # handle created_at datetime comparison
            if op == "==":
                if v == value:
                    filtered.append(d)
            elif op == ">=":
                if v is not None and v >= value:
                    filtered.append(d)
            elif op == "<=":
                if v is not None and v <= value:
                    filtered.append(d)
            elif op == "<":
                if v is not None and v < value:
                    filtered.append(d)
            else:
                filtered.append(d)
        c = MockColl(filtered)
        c.calls = self.calls
        return c
    def order_by(self, field, direction=None):
        self.calls["order_by"] += 1
        c = MockColl(self._docs)
        c.calls = self.calls
        c._order_field = field
        # sort descending if direction is DESCENDING
        try:
            c._docs.sort(key=lambda d: d.to_dict().get(field) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        except: pass
        return c
    def limit(self, n):
        self.calls["limit"] += 1
        c = MockColl(self._docs[:n])
        c.calls = self.calls
        return c
    def start_after(self, val):
        self.calls["start_after"] += 1
        # val can be dict or datetime
        cursor_dt = None
        if isinstance(val, dict):
            cursor_dt = list(val.values())[0] if val else None
        else:
            cursor_dt = val
        if cursor_dt is None:
            return self
        # filter where order_field < cursor_dt
        field = self._order_field or "created_at"
        filtered = []
        for d in self._docs:
            v = d.to_dict().get(field) or d.to_dict().get("created_at")
            if v is not None and hasattr(v, "isoformat"):
                if v < cursor_dt:
                    filtered.append(d)
            else:
                filtered.append(d)
        c = MockColl(filtered)
        c.calls = self.calls
        return c
    def get(self):
        self.calls["get"] += 1
        return self._docs
    def count(self):
        self.calls["count"] += 1
        m = MagicMock()
        m.get.return_value = [MagicMock(value=len(self._docs))]
        return m
    def stream(self):
        return self.get()

class MockGroupColl(MockColl):
    pass

class MockDB:
    def __init__(self, caps=None):
        self._caps = caps or []
        self._group_calls = 0
    def collection_group(self, name):
        self._group_calls += 1
        assert name == "caps"
        return MockColl(self._caps)


# --- Tests ---

def _patch_master(monkeypatch, hazards, cans, caps_group=None):
    """Patch master_register to use MockColl for hazards/cans and MockDB for caps."""
    haz_coll = MockColl(hazards)
    can_coll = MockColl(cans)
    db = MockDB(caps_group or [])

    def _tenant_coll(tid, name):
        if name == "hazards":
            return haz_coll
        if name == "can_cap":
            return can_coll
        raise AssertionError(name)
    def _cross_coll(name):
        if name == "hazards":
            return haz_coll
        if name == "can_cap":
            return can_coll
        raise AssertionError(name)

    monkeypatch.setattr("app.services.master_register.get_tenant_collection", _tenant_coll)
    monkeypatch.setattr("app.services.master_register.get_cross_tenant_collection", _cross_coll)
    monkeypatch.setattr("app.services.master_register.get_db", lambda: db)
    return haz_coll, can_coll, db

def test_filter_department_firestore(monkeypatch):
    hazards = [
        MockDoc("h1", {"hazard_id": "H1", "title": "Ops", "status": "Open", "department": "Flight Operations", "created_at": _dt(1)}),
        MockDoc("h2", {"hazard_id": "H2", "title": "Maint", "status": "Open", "department": "Part-145", "created_at": _dt(1)}),
    ]
    haz_coll, can_coll, db = _patch_master(monkeypatch, hazards, [])
    user = {"role": "AIRLINE_ADMIN", "tenant_id": "t1", "uid": "u1", "email": "a@t1.com"}
    result = master_register.build_master_register(user, department="Flight Operations")
    assert len([r for r in result["rows"] if r["type"]=="Hazard"]) == 1
    assert result["rows"][0]["department"] == "Flight Operations"
    # Verify Firestore-level where was used
    assert haz_coll.calls["where"] >= 1

def test_filter_assignee_firestore(monkeypatch):
    cans = [
        MockDoc("c1", {"can_reference": "CAN-001", "title": "Mine", "status": "Open", "assigned_to_uid": "u2", "department": "", "created_at": _dt(1)}),
        MockDoc("c2", {"can_reference": "CAN-002", "title": "Other", "status": "Open", "assigned_to_uid": "u9", "department": "", "created_at": _dt(1)}),
    ]
    haz_coll, can_coll, db = _patch_master(monkeypatch, [], cans)
    user = {"role": "AIRLINE_ADMIN", "tenant_id": "t1", "uid": "u1", "email": "a@t1.com"}
    result = master_register.build_master_register(user, assigned_to_uid="u2")
    assert len([r for r in result["rows"] if r["type"]=="CAN"]) == 1
    assert result["rows"][0]["reference"] == "CAN-001"

def test_filter_date_range(monkeypatch):
    old = MockDoc("h1", {"hazard_id": "H1", "title": "Old", "status": "Open", "department": "", "created_at": _dt(10)})
    recent = MockDoc("h2", {"hazard_id": "H2", "title": "Recent", "status": "Open", "department": "", "created_at": _dt(1)})
    haz_coll, can_coll, db = _patch_master(monkeypatch, [old, recent], [])
    user = {"role": "AIRLINE_ADMIN", "tenant_id": "t1", "uid": "u1", "email": "a@t1.com"}
    result = master_register.build_master_register(user, days=5)
    refs = {r["reference"] for r in result["rows"]}
    assert "H2" in refs
    assert "H1" not in refs

def test_pagination_page_size_default_and_max(monkeypatch):
    hazards = [MockDoc(f"h{i}", {"hazard_id": f"H{i}", "title": f"T{i}", "status": "Open", "department": "", "created_at": _dt(i)}) for i in range(10)]
    haz_coll, can_coll, db = _patch_master(monkeypatch, hazards, [])
    user = {"role": "AIRLINE_ADMIN", "tenant_id": "t1", "uid": "u1", "email": "a@t1.com"}
    # default 50
    r1 = master_register.build_master_register(user)
    assert r1["pagination"]["page_size"] == 50
    # explicit 25
    r2 = master_register.build_master_register(user, page_size=25)
    assert r2["pagination"]["page_size"] == 25
    # max 100 enforcement
    r3 = master_register.build_master_register(user, page_size=200)
    assert r3["pagination"]["page_size"] == 100
    # pagination limit applied
    r4 = master_register.build_master_register(user, page_size=3)
    assert len(r4["rows"]) == 3
    assert r4["pagination"]["has_more"] is True
    assert r4["pagination"]["next_cursor"] is not None

def test_cursor_pagination_uses_start_after(monkeypatch):
    # Create 5 hazards with distinct dates descending
    hazards = [MockDoc(f"h{i}", {"hazard_id": f"H{i}", "title": f"T{i}", "status": "Open", "department": "", "created_at": _dt(i)}) for i in range(5)]
    haz_coll, can_coll, db = _patch_master(monkeypatch, hazards, [])
    user = {"role": "AIRLINE_ADMIN", "tenant_id": "t1", "uid": "u1", "email": "a@t1.com"}
    first = master_register.build_master_register(user, page_size=2)
    assert len(first["rows"]) == 2
    cursor = first["pagination"]["next_cursor"]
    assert cursor is not None
    second = master_register.build_master_register(user, page_size=2, cursor=cursor)
    # second page should not overlap first
    first_ids = {r["id"] for r in first["rows"]}
    second_ids = {r["id"] for r in second["rows"]}
    assert first_ids.isdisjoint(second_ids)
    # Verify start_after was used (or where fallback)
    assert haz_coll.calls["order_by"] >= 1
    # start_after or where for cursor
    assert haz_coll.calls["start_after"] >= 1 or haz_coll.calls["where"] >= 1

def test_tenant_isolation(monkeypatch):
    hazards_t1 = [MockDoc("h1", {"hazard_id": "H1", "title": "T1", "status": "Open", "department": "", "created_at": _dt(1), "tenant_id": "t1"})]
    hazards_t2 = [MockDoc("h2", {"hazard_id": "H2", "title": "T2", "status": "Open", "department": "", "created_at": _dt(1), "tenant_id": "t2"})]
    # For tenant t1 user, only t1 hazards should be returned via get_tenant_collection (we mock to return only t1)
    haz_coll, can_coll, db = _patch_master(monkeypatch, hazards_t1, [])
    user = {"role": "AIRLINE_ADMIN", "tenant_id": "t1", "uid": "u1", "email": "a@t1.com"}
    result = master_register.build_master_register(user)
    assert all(r["reference"] != "H2" for r in result["rows"])
    # Cross-tenant should see both if we mock cross to return both
    cross_coll = MockColl(hazards_t1 + hazards_t2)
    monkeypatch.setattr("app.services.master_register.get_cross_tenant_collection", lambda name: cross_coll)
    user_caan = {"role": "CAAN_SMD", "tenant_id": None, "uid": "u2", "email": "caan@t.com"}
    result2 = master_register.build_master_register(user_caan)
    assert len([r for r in result2["rows"] if r["reference"] in ("H1","H2")]) == 2

def test_empty_results(monkeypatch):
    haz_coll, can_coll, db = _patch_master(monkeypatch, [], [])
    user = {"role": "AIRLINE_ADMIN", "tenant_id": "t1", "uid": "u1", "email": "a@t1.com"}
    result = master_register.build_master_register(user)
    assert result["rows"] == []
    assert result["total"] == 0
    assert result["by_status"] == {}
    assert result["by_type"] == {}
    assert result["pagination"]["next_cursor"] is None
    assert result["pagination"]["has_more"] is False

def test_cap_batch_no_n_plus_one(monkeypatch):
    # 2 CANs each with 1 CAP via collection_group batch
    can1 = MockDoc("c1", {"can_reference": "CAN-001", "title": "C1", "status": "Open", "priority": "H", "assigned_to": "a@t.com", "assigned_to_uid": "u1", "department": "Safety", "created_at": _dt(1)}, caps=[])
    can2 = MockDoc("c2", {"can_reference": "CAN-002", "title": "C2", "status": "Open", "priority": "H", "assigned_to": "b@t.com", "assigned_to_uid": "u2", "department": "Safety", "created_at": _dt(2)}, caps=[])
    # Caps via group
    cap1 = MockDoc("cap1", {"cap_reference": "CAN-001-CAP-001", "action_plan": "Fix 1", "status": "In Progress", "department": "Safety", "created_at": _dt(1), "tenant_id": "t1", "can_id": "c1"}, path="tenants/t1/can_cap/c1/caps/cap1")
    cap2 = MockDoc("cap2", {"cap_reference": "CAN-002-CAP-001", "action_plan": "Fix 2", "status": "In Progress", "department": "Safety", "created_at": _dt(1), "tenant_id": "t1", "can_id": "c2"}, path="tenants/t1/can_cap/c2/caps/cap2")
    # For per-CAN fallback, can's reference returns caps, but group should be used
    can1.reference = MockRef(can1, [cap1])
    can2.reference = MockRef(can2, [cap2])
    haz_coll, can_coll, db = _patch_master(monkeypatch, [], [can1, can2], caps_group=[cap1, cap2])
    user = {"role": "AIRLINE_ADMIN", "tenant_id": "t1", "uid": "u1", "email": "a@t1.com"}
    result = master_register.build_master_register(user)
    caps = [r for r in result["rows"] if r["type"]=="CAP"]
    assert len(caps) == 2
    assert {c["reference"] for c in caps} == {"CAN-001-CAP-001", "CAN-002-CAP-001"}
    # Verify collection_group was used (batch), not per-CAN N+1 (group calls 1 for fetch + 1 for count = 2)
    assert db._group_calls >= 1
    assert db._group_calls <= 2

def test_api_route_pagination(monkeypatch):
    # Test the FastAPI route supports page_size/cursor
    from unittest.mock import patch
    mock_data = {
        "rows": [{"id": "h1", "reference": "H1", "title": "T1", "type": "Hazard", "status": "Open", "department": "", "date": _dt(1).isoformat()}],
        "total": 1,
        "by_status": {"Open": 1},
        "by_type": {"Hazard": 1},
        "pagination": {"page_size": 50, "next_cursor": "abc", "has_more": False, "cursor": None}
    }
    with patch("app.services.master_register.build_master_register", return_value=mock_data) as mock_build:
        client = TestClient(app)
        # Need auth mock
        import app.middleware.auth as auth_mod
        orig = auth_mod.verify_firebase_token
        auth_mod.verify_firebase_token = lambda t: {"uid": "u1", "email": "a@t1.com", "role": "AIRLINE_ADMIN", "tenant_id": "t1"}
        from app.firebase import get_db
        # bypass firebase init
        resp = client.get("/api/v1/dashboard/master-register?page_size=25&cursor=abc", headers={"Authorization": "Bearer test"})
        # Should be 200 and have called build with page_size 25
        assert resp.status_code == 200
        # Check that page_size and cursor were forwarded
        assert mock_build.called
        kwargs = mock_build.call_args[1]
        assert kwargs["page_size"] == 25
        assert kwargs["cursor"] == "abc"
        auth_mod.verify_firebase_token = orig
