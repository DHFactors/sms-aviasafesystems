"""Admin feedback review endpoint tests.

Covers GET /api/v1/admin/feedback: CROSS-TENANT role gating (SUPER_ADMIN /
CAAN_SMD allowed, others rejected) and response shape.
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import get_current_user


class _Snap:
    def __init__(self, data, doc_id):
        self._data = data or {}
        self.id = doc_id

    def to_dict(self):
        return self._data


class _FakeColl:
    def __init__(self, db, name):
        self._db = db
        self._name = name

    def where(self, field, op, value):
        return _Query(self._db, self._name, [(field, op, value)])

    def limit(self, n):
        return _Query(self._db, self._name, [], n)


class _Query:
    def __init__(self, db, name, filters, limit=None):
        self._db = db
        self._name = name
        self._filters = filters
        self._limit = limit

    def where(self, field, op, value):
        return _Query(self._db, self._name, self._filters + [(field, op, value)], self._limit)

    def limit(self, n):
        return _Query(self._db, self._name, self._filters, n)

    def stream(self):
        items = []
        for doc_id, data in self._db._stores.get(self._name, {}).items():
            for field, op, value in self._filters:
                if op == "==" and data.get(field) != value:
                    break
            else:
                items.append(_Snap(dict(data), doc_id))
        if self._limit:
            items = items[: self._limit]
        return items


class _FakeDB:
    def __init__(self):
        self._stores = {}

    def collection(self, name):
        return _FakeColl(self, name)


def _patch(monkeypatch, db):
    import app.routes.admin as admin_mod

    monkeypatch.setattr(admin_mod.get_db, "__wrapped__", None, raising=False)
    monkeypatch.setattr("app.routes.admin.get_db", lambda: db)


def _user(role="SUPER_ADMIN"):
    return {"uid": "super-1", "email": "super-admin@aviasafesystems.com", "role": role, "tenant_id": None}


def _client(user=None):
    app.dependency_overrides[get_current_user] = lambda: user or _user()
    return TestClient(app)


def _clear():
    app.dependency_overrides.pop(get_current_user, None)


def _seed(db):
    now = datetime.now(timezone.utc)
    db._stores["feedback"] = {
        "f1": {
            "uid": "safety-buddha-air-001",
            "email": "safety@buddha-air.com",
            "role": "AIRLINE_ADMIN",
            "tenant_id": "buddha-air",
            "subject": "SSM Risk Trends",
            "message": "Live verification feedback.",
            "rating": 5,
            "page": "/safety.html",
            "created_at": now,
            "status": "new",
        },
        "f2": {
            "uid": "smd-caan-001",
            "email": "smd@caanepal.gov.np",
            "role": "CAAN_SMD",
            "tenant_id": "caan",
            "subject": "SSP Reporting",
            "message": "Reviewing dashboards.",
            "rating": None,
            "page": "/caan.html",
            "created_at": now,
            "status": "new",
        },
    }


def test_admin_feedback_super_admin_allowed(monkeypatch):
    db = _FakeDB()
    _seed(db)
    _patch(monkeypatch, db)
    try:
        resp = _client(_user("SUPER_ADMIN")).get("/api/v1/admin/feedback")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        by_id = {f["id"]: f for f in body["feedback"]}
        assert by_id["f1"]["email"] == "safety@buddha-air.com"
        assert by_id["f1"]["tenant_id"] == "buddha-air"
        assert by_id["f1"]["subject"] == "SSM Risk Trends"
        assert by_id["f1"]["rating"] == 5
        assert "created_at" in by_id["f1"]
    finally:
        _clear()


def test_admin_feedback_caan_smd_allowed(monkeypatch):
    db = _FakeDB()
    _seed(db)
    _patch(monkeypatch, db)
    try:
        resp = _client(_user("CAAN_SMD")).get("/api/v1/admin/feedback")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2
    finally:
        _clear()


def test_admin_feedback_status_filter(monkeypatch):
    db = _FakeDB()
    _seed(db)
    _patch(monkeypatch, db)
    try:
        resp = _client(_user("SUPER_ADMIN")).get("/api/v1/admin/feedback?status=reviewed")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        resp = _client(_user("SUPER_ADMIN")).get("/api/v1/admin/feedback?status=new")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2
    finally:
        _clear()


def test_admin_feedback_airline_admin_denied(monkeypatch):
    db = _FakeDB()
    _seed(db)
    _patch(monkeypatch, db)
    try:
        resp = _client(_user("AIRLINE_ADMIN")).get("/api/v1/admin/feedback")
        assert resp.status_code == 403
    finally:
        _clear()