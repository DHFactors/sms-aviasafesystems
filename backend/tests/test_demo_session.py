"""Chunk 7 — demo session isolation & analytics (unit tests).

Covers:
  * safe fallback for non-demo callers (zero writes)
  * get-or-create idempotency within the 24h TTL
  * lazy expiry of stale sessions
  * decision logging + overlay loading/merging
  * analytics write gating
"""

from datetime import datetime, timedelta, timezone

import pytest

from demo import analytics, session_manager as sm

NOW = datetime.now(timezone.utc)


# ── Minimal in-memory Firestore stub (only the chains session_manager uses) ──

class FakeSnap:
    def __init__(self, id, data, ref):
        self.id = id
        self._data = data
        self.reference = ref

    def to_dict(self):
        return dict(self._data)


class FakeDocRef:
    def __init__(self, db, path, doc_id):
        self.db = db
        self.path = tuple(path)
        self.id = doc_id

    def _key(self):
        return self.path + (self.id,)

    def set(self, data):
        self.db.data[self._key()] = dict(data)

    def delete(self):
        self.db.data.pop(self._key(), None)

    def collection(self, name):
        return FakeColl(self.db, self.path + (name,))


class FakeColl:
    def __init__(self, db, path):
        self.db = db
        self.path = tuple(path)

    def _docs(self):
        prefix = self.path
        out = []
        for key, data in self.db.data.items():
            if key[:len(prefix)] == prefix and len(key) == len(prefix) + 1:
                ref = FakeDocRef(self.db, prefix, key[-1])
                out.append(FakeSnap(key[-1], data, ref))
        return out

    def document(self, doc_id=None):
        doc_id = doc_id or "auto-%d" % next(self.db.counter)
        return FakeDocRef(self.db, self.path, doc_id)

    def where(self, field, op, value):
        q = FakeQuery(self.db, self.path)
        q.wheres.append((field, op, value))
        return q

    def limit(self, n):
        q = FakeQuery(self.db, self.path)
        q.wheres = []
        q.limit_n = n
        return q

    def stream(self):
        return iter(self._docs())

    def get(self):
        return list(self._docs())


class FakeQuery(FakeColl):
    def __init__(self, db, path):
        super().__init__(db, path)
        self.wheres = []
        self.limit_n = None

    def where(self, field, op, value):
        self.wheres.append((field, op, value))
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def _filtered(self):
        out = []
        for snap in self._docs():
            ok = True
            for field, op, value in self.wheres:
                actual = snap._data.get(field)
                if op == "==":
                    ok = actual == value
                elif op == ">":
                    ok = actual is not None and actual > value
                else:
                    raise AssertionError("unsupported op " + op)
                if not ok:
                    break
            if ok:
                out.append(snap)
            if self.limit_n is not None and len(out) >= self.limit_n:
                break
        return out

    def stream(self):
        return iter(self._filtered())

    def get(self):
        return list(self._filtered())


class FakeBatch:
    def __init__(self, db):
        self.db = db
        self._ops = []

    def set(self, ref, data):
        self._ops.append((ref, dict(data)))

    def commit(self):
        for ref, data in self._ops:
            ref.set(data)
        return len(self._ops)


class FakeDB:
    def __init__(self):
        from itertools import count
        self.data = {}
        self.counter = count()

    def batch(self):
        return FakeBatch(self)

    def collection(self, name):
        return FakeColl(self, [name])


@pytest.fixture()
def db():
    return FakeDB()


AE = "ae@fishtailair.com"


def test_is_demo_ae_gate(db):
    assert sm.is_demo_ae(AE) is True
    assert sm.is_demo_ae("ops@buddha-air.com") is False      # standard tenant
    assert sm.is_demo_ae("ae@unknown-operator.com") is False  # unregistered


def test_safe_fallback_non_demo_email(db):
    assert sm.get_or_create_session(db, "ops@buddha-air.com") is None
    assert sm.log_action(db, "ops@buddha-air.com", "x") is None
    assert sm.log_decision(db, "ops@buddha-air.com", {"target": {}}) is None
    assert sm.load_cap_overlays(db, "ops@buddha-air.com") == {}
    assert db.data == {}, "non-demo callers must never write"


def test_get_or_create_session_idempotent_within_ttl(db):
    sid1 = sm.get_or_create_session(db, AE)
    sid2 = sm.get_or_create_session(db, AE)
    assert sid1 and sid1 == sid2
    docs = [k for k in db.data if k[0] == sm.SESSIONS_COLLECTION]
    assert len(docs) == 1


def test_expired_sessions_purged_and_replaced(db):
    stale_cutoff = NOW - timedelta(hours=sm.SESSION_TTL_HOURS + 1)
    stale_id = f"{AE}_{int(stale_cutoff.timestamp())}"
    db.collection(sm.SESSIONS_COLLECTION).document(stale_id).set({
        "session_id": stale_id,
        "email": AE,
        "created_at": stale_cutoff,
        "expires_at": NOW - timedelta(hours=1),
    })

    sid = sm.get_or_create_session(db, AE)
    assert sid != stale_id
    remaining = [k for k in db.data if k[0] == sm.SESSIONS_COLLECTION]
    assert len(remaining) == 1 and remaining[0][-1] == sid


def test_decision_logged_and_overlay_loaded(db):
    sid = sm.get_or_create_session(db, AE)
    overlay = sm.log_decision(db, AE, {
        "target": {"kind": "cap", "id": "cap_123"},
        "decision": "accept_risk",
        "result_status": "In Progress",
        "signature": "Birendra Basnet",
        "review_date": (NOW + timedelta(days=60)).isoformat(),
        "manager_approval": "Accepted Risk",
    })
    assert overlay["decision_id"]

    overlays = sm.load_cap_overlays(db, AE)
    assert "cap_123" in overlays
    ov = overlays["cap_123"]
    assert ov["status"] == "In Progress"
    assert ov["escalated_to_ae"] is False
    assert ov["ae_signature"] == "Birendra Basnet"


def test_apply_overlay_merges_display_rows():
    rows = [
        {"id": "cap_123", "status": "Under Review", "priority": "High"},
        {"id": "cap_999", "status": "In Progress"},
    ]
    overlays = {"cap_123": {"status": "In Progress", "escalated_to_ae": False}}
    merged = sm.apply_overlay(rows, overlays)
    assert merged[0]["status"] == "In Progress"
    assert merged[0]["_overlay"] is True
    assert merged[1]["status"] == "In Progress" and "_overlay" not in merged[1]


def test_analytics_gating_and_write(db):
    # Non-demo caller: no write.
    assert analytics.track_event(db, "ops@buddha-air.com", "login_time") is None
    assert db.data == {}

    # Registered demo AE: event persisted.
    eid = analytics.track_event(db, AE, "login_time", {"at": "now"})
    assert eid
    written = analytics.track_events(db, AE, [
        {"event_type": "simulator_uses", "payload": {"x": 1}},
        {"event_type": "exports_triggered", "payload": {"format": "csv"}},
    ])
    assert written == 2
    events = [k for k in db.data if k[0] == analytics.ANALYTICS_COLLECTION]
    assert len(events) == 3
