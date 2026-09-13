"""Automated escalation + master register tests.

Covers the escalation service (CAN -> Escalated, CAP -> Overdue), audit logging,
and the unified master register builder (hazards + CANs + CAPs with department
and assignee scoping).
"""

from datetime import datetime, timedelta, timezone

from app.db.db_models import Can, Cap, Tenant
from app.db.ids import tenant_uuid
from app.services import escalation_service
from app.services import master_register


# ============================================================================
# Escalation service
# ============================================================================

def _dt(days_ago):
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


class _Snap:
    def __init__(self, id, data, caps=None):
        self.id = id
        self._data = data
        self.reference = _Ref(self)
        self._caps = caps or []

    def to_dict(self):
        return self._data


class _Ref:
    def __init__(self, owner):
        self._owner = owner

    def update(self, data):
        self._owner._data.update(data)

    def collection(self, name):
        assert name == "caps"
        return _CapsColl(self._owner._caps)


class _CapSnap:
    def __init__(self, id, data):
        self.id = id
        self._data = data
        self.reference = _CapRef(self)

    def to_dict(self):
        return self._data


class _CapRef:
    def __init__(self, owner):
        self._owner = owner

    def update(self, data):
        self._owner._data.update(data)


class _CapsColl:
    def __init__(self, caps):
        self._caps = caps

    def get(self):
        return self._caps


class _TenantSnap:
    def __init__(self, id, cans):
        self.id = id
        self._cans = cans

    def collection(self, name):
        assert name == "can_cap"
        return _CansColl(self._cans)


class _CansColl:
    def __init__(self, cans):
        self._cans = cans

    def get(self):
        return self._cans


class _FakeAudit:
    def __init__(self):
        self.entries = []

    def __call__(self, **kwargs):
        self.entries.append(kwargs)


class _FakeDB:
    def __init__(self, tenants):
        self._tenants = tenants
        self._audit = []

    def collection(self, name):
        if name == "tenants":
            return _TenantsColl(self._tenants)
        if name == "audit_logs":
            return _AuditColl(self._audit)
        raise AssertionError(f"unexpected collection {name}")


class _TenantsColl:
    def __init__(self, tenants):
        self._tenants = tenants

    def get(self):
        return self._tenants

    def document(self, id):
        for t in self._tenants:
            if t.id == id:
                return t
        raise KeyError(id)


class _AuditColl:
    def __init__(self, entries):
        self._entries = entries

    def add(self, entry):
        self._entries.append(entry)


class _FakePg:
    """Minimal stub for the Postgres query layer used by escalation_service.

    ``fetch_all`` returns rows keyed by model table name. When a ``where`` clause
    carries a tenant UUID (``Can.tenant_id == <uuid>``) and a matching entry
    exists in ``tenant_rows``, the per-tenant (cans, caps) rows are returned so
    ``check_all_overdue`` sees isolated tenant data just like real Postgres.
    """

    def __init__(self, rows_by_model, tenant_rows=None):
        self._static = {m.__tablename__: list(r) for m, r in rows_by_model.items()}
        self._tenant_rows = tenant_rows or {}

    @staticmethod
    def _tenant_of(where):
        for cond in where or []:
            try:
                return str(cond.right.value)
            except Exception:
                continue
        return None

    def fetch_all(self, model, where=None):
        name = model.__tablename__
        tid = self._tenant_of(where)
        if tid is not None and tid in self._tenant_rows:
            cans, caps = self._tenant_rows[tid]
            rows = cans if name == "cans" else caps if name == "caps" else []
            return [dict(r) for r in rows]
        return [dict(r) for r in self._static.get(name, [])]

    def update(self, model, key_col, key, data):
        name = model.__tablename__
        if name in ("cans", "caps"):
            stores = [pair[0] if name == "cans" else pair[1]
                      for pair in self._tenant_rows.values()]
            if not stores:
                stores = [self._static.get(name)]
        else:
            stores = [self._static.get(name)]
        for store in stores:
            if not store:
                continue
            for r in store:
                if str(r.get(key_col)) == str(key):
                    r.update(data)
                    return


def test_can_escalated_when_past_due(monkeypatch):
    cans = [
        {"id": "can1", "can_reference": "CAN-001", "status": "Open",
         "target_completion_date": _dt(5)},
        {"id": "can2", "can_reference": "CAN-002", "status": "Closed",
         "target_completion_date": _dt(5)},
        {"id": "can3", "can_reference": "CAN-003", "status": "Open",
         "target_completion_date": _dt(-5)},
    ]
    audit = _FakeAudit()
    monkeypatch.setattr(escalation_service, "pg", _FakePg({Can: cans}))
    monkeypatch.setattr(escalation_service, "log_audit", audit)

    result = escalation_service.check_tenant_overdue("t1")
    assert result["cans_escalated"] == 1
    # only the past-due open CAN gets the new status; the future one stays Open,
    # and the Closed CAN is never touched
    assert cans[0]["status"] == "Escalated"
    assert cans[2]["status"] == "Open"
    assert cans[1]["status"] == "Closed"


def test_can_escalated_idempotent(monkeypatch):
    cans = [
        {"id": "can1", "can_reference": "CAN-001", "status": "Escalated",
         "target_completion_date": _dt(5)},
    ]
    audit = _FakeAudit()
    monkeypatch.setattr(escalation_service, "pg", _FakePg({Can: cans}))
    monkeypatch.setattr(escalation_service, "log_audit", audit)

    result = escalation_service.check_tenant_overdue("t1")
    assert result["cans_escalated"] == 1
    # status unchanged because it was already Escalated
    assert cans[0]["status"] == "Escalated"
    # no duplicate audit entry for the already-escalated CAN
    can_audits = [a for a in audit.entries if a["action"] == "CAN_ESCALATED"]
    assert can_audits == []


def test_cap_overdue_when_past_due(monkeypatch):
    caps = [
        {"id": "cap1", "can_id": "can1", "cap_reference": "CAN-001-CAP-001",
         "status": "In Progress", "target_completion_date": _dt(4)},
        {"id": "cap2", "can_id": "can1", "cap_reference": "CAN-001-CAP-002",
         "status": "In Progress", "target_completion_date": _dt(-4)},
    ]
    cans = [
        {"id": "can1", "can_reference": "CAN-001", "status": "Under Review",
         "target_completion_date": _dt(4)},
    ]
    monkeypatch.setattr(escalation_service, "pg", _FakePg({Can: cans, Cap: caps}))
    monkeypatch.setattr(escalation_service, "log_audit", _FakeAudit())

    result = escalation_service.check_tenant_overdue("t1")
    assert result["caps_overdue"] == 1
    assert caps[0]["status"] == "Overdue"
    assert caps[1]["status"] == "In Progress"


def test_check_all_overdue_returns_summary(monkeypatch):
    cans_t1 = [
        {"id": "can1", "can_reference": "CAN-001", "status": "Open",
         "target_completion_date": _dt(3)},
    ]
    tenants = [
        {"id": "t1", "slug": "t1"},
        {"id": "t2", "slug": "t2"},
    ]
    audit = _FakeAudit()
    monkeypatch.setattr(escalation_service, "pg", _FakePg(
        {Tenant: tenants},
        tenant_rows={
            str(tenant_uuid("t1")): (cans_t1, []),
            str(tenant_uuid("t2")): ([], []),
        },
    ))
    monkeypatch.setattr(escalation_service, "log_audit", audit)

    result = escalation_service.check_all_overdue()
    assert result["tenants_processed"] == 2
    assert result["cans_escalated"] == 1
    assert result["caps_overdue"] == 0
    assert any(a["action"] == "OVERDUE_CHECK_RUN" for a in audit.entries)


# ============================================================================
# Master register
# ============================================================================

class _MRUser:
    def __init__(self, role="AIRLINE_ADMIN", tenant_id="t1", uid="u1"):
        self._u = {"role": role, "tenant_id": tenant_id, "uid": uid, "email": "a@t1.com"}

    def get(self, key):
        return self._u.get(key)


class _MRRef:
    def __init__(self, caps):
        self._caps = caps

    def collection(self, name):
        assert name == "caps"
        return _MRCapsColl(self._caps)


class _MRCapsColl:
    def __init__(self, caps):
        self._caps = caps

    def get(self):
        return self._caps


class _MRDoc:
    def __init__(self, id, data, caps=None):
        self.id = id
        self._data = data
        self.reference = _MRRef(caps or [])

    def to_dict(self):
        return self._data


class _MRColl:
    def __init__(self, docs):
        self._docs = docs

    def get(self):
        return self._docs


class _MRDB:
    def __init__(self, hazards, cans):
        self._hazards = hazards
        self._cans = cans
        self._tenant_id = None

    def collection(self, name):
        if name == "hazards":
            return _MRColl(self._hazards)
        if name == "can_cap":
            return _MRColl(self._cans)
        raise AssertionError(f"unexpected collection {name}")


def _patch_mr(monkeypatch, db, user):
    def _tenant_collection(tid, name):
        assert tid == user["tenant_id"]
        return db.collection(name)

    def _cross_tenant_collection(name):
        return db.collection(name)

    def _group_db():
        class _Group:
            def collection_group(self, coll):
                assert coll == "caps"
                return _MRColl([])
        return _Group()

    monkeypatch.setattr("app.services.master_register.get_tenant_collection", _tenant_collection)
    monkeypatch.setattr("app.services.master_register.get_cross_tenant_collection", _cross_tenant_collection)
    monkeypatch.setattr("app.services.master_register.get_db", lambda: _group_db())


def test_master_register_combines_types(monkeypatch):
    hazards = [_MRDoc("h1", {
        "hazard_id": "T1-HZ-ORG-01-26",
        "title": "Runway incursion hazard",
        "status": "Open",
        "risk_level": "High",
        "priority": "H",
        "assigned_to": "A. Gurung",
        "assigned_to_uid": "u2",
        "department": "Engineering & Maintenance",
        "created_at": _dt(1),
    })]
    cans = [_MRDoc("c1", {
        "can_reference": "CAN-001",
        "title": "Replace fire extinguisher seals",
        "status": "Open",
        "priority": "High",
        "assigned_to": "A. Gurung",
        "assigned_to_uid": "u2",
        "department": "Engineering & Maintenance",
        "issued_at": _dt(1),
    }, caps=[_MRDoc("cap1", {
        "cap_reference": "CAN-001-CAP-001",
        "action_plan": "Replace seals and inspect all units",
        "status": "In Progress",
        "target_completion_date": _dt(-2),
    })])]

    db = _MRDB(hazards, cans)
    user = {"role": "AIRLINE_ADMIN", "tenant_id": "t1", "uid": "u1", "email": "a@t1.com"}
    _patch_mr(monkeypatch, db, user)

    result = master_register.build_master_register(user)
    types = {r["type"] for r in result["rows"]}
    assert types == {"Hazard", "CAN", "CAP"}
    assert result["total"] == 3
    assert result["by_type"]["Hazard"] == 1
    assert result["by_type"]["CAN"] == 1
    assert result["by_type"]["CAP"] == 1


def test_master_register_department_filter(monkeypatch):
    hazards = [
        _MRDoc("h1", {
            "hazard_id": "T1-HZ-ORG-01-26",
            "title": "Ops hazard",
            "status": "Open",
            "assigned_to_uid": "u2",
            "department": "Flight Operations",
            "created_at": _dt(1),
        }),
        _MRDoc("h2", {
            "hazard_id": "T1-HZ-ORG-02-26",
            "title": "Maint hazard",
            "status": "Open",
            "assigned_to_uid": "u3",
            "department": "Engineering & Maintenance",
            "created_at": _dt(1),
        }),
    ]
    db = _MRDB(hazards, [])
    user = {"role": "AIRLINE_ADMIN", "tenant_id": "t1", "uid": "u1", "email": "a@t1.com"}
    _patch_mr(monkeypatch, db, user)

    result = master_register.build_master_register(user, department="Flight Operations")
    assert result["total"] == 1
    assert result["rows"][0]["title"] == "Ops hazard"


def test_master_register_assignee_filter(monkeypatch):
    # Assignee filtering applies to CANs/CAPs; hazards are tenant-wide and
    # intentionally bypass the assignee dimensions.
    cans = [
        _MRDoc("c1", {
            "can_reference": "CAN-001",
            "title": "Mine",
            "status": "Open",
            "assigned_to_uid": "u2",
            "created_at": _dt(1),
        }),
        _MRDoc("c2", {
            "can_reference": "CAN-002",
            "title": "Someone else's",
            "status": "Open",
            "assigned_to_uid": "u9",
            "created_at": _dt(1),
        }),
    ]
    db = _MRDB([], cans)
    user = {"role": "AIRLINE_ADMIN", "tenant_id": "t1", "uid": "u1", "email": "a@t1.com"}
    _patch_mr(monkeypatch, db, user)

    result = master_register.build_master_register(user, assigned_to_uid="u2")
    assert result["total"] == 1
    assert result["rows"][0]["title"] == "Mine"
