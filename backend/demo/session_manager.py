# ============================================================================
# FILE: backend/demo/__init__.py
# ============================================================================

# ============================================================================
# FILE: backend/demo/session_manager.py
# PURPOSE: Demo Session Isolation for Virtual Tenant Mirroring (Chunk 7).
#
# Prospect AE actions (risk acceptances, escalation decisions) are written to
# per-session overlay collections instead of the master archetype data:
#
#     demo_sessions/{session_id}            ← session doc (email, created_at)
#     demo_sessions/{session_id}/actions    ← generic AE actions
#     demo_sessions/{session_id}/decisions  ← formal governance decisions
#
# SAFE FALLBACK: every entry point validates the caller against the prospect
# registry (ae@* + registered email). Standard tenants (145@, safety@, …) and
# unregistered accounts short-circuit to None/[] — nothing is ever written and
# real tenant operations are untouched. Master archetype collections are never
# written to either; the client merges overlays on display.
#
# Sessions auto-expire after SESSION_TTL_HOURS (24h). Expiry is enforced lazily
# on every read and opportunistically purged.
# ============================================================================

from datetime import datetime, timedelta, timezone

from seed.prospect_registry import PROSPECT_REGISTRY

SESSIONS_COLLECTION = "demo_sessions"
ACTIONS_SUBCOLLECTION = "actions"
DECISIONS_SUBCOLLECTION = "decisions"

SESSION_TTL_HOURS = 24


def _now():
    return datetime.now(timezone.utc)


def is_demo_ae(email: str) -> bool:
    """True only for registered prospect Accountable Executive accounts."""
    e = str(email or "").lower()
    if not e.startswith("ae@"):
        return False
    return e in {k.lower() for k in PROSPECT_REGISTRY.keys()}


def session_expiry(cutoff_now: datetime = None) -> datetime:
    now = cutoff_now or _now()
    return now - timedelta(hours=SESSION_TTL_HOURS)


def make_session_id(email: str, ts: datetime = None) -> str:
    ts = ts or _now()
    return f"{str(email).lower()}_{int(ts.timestamp())}"


# ── Core API ────────────────────────────────────────────────────────────────

def get_or_create_session(db, email: str):
    """Return the active session doc id for a demo AE, creating one when
    absent. Returns None for non-demo callers (safe fallback) — no writes."""
    if not db or not is_demo_ae(email):
        return None

    now = _now()
    email_key = str(email).lower()
    sessions_ref = db.collection(SESSIONS_COLLECTION)

    # Lazy expiry: drop this user's stale sessions (bounded scan).
    stale_cutoff = session_expiry(now)
    stale = []
    for snap in sessions_ref.where("email", "==", email_key).stream():
        data = snap.to_dict() or {}
        created = data.get("created_at")
        if created and created < stale_cutoff:
            stale.append(snap.reference)
    for ref in stale[:20]:
        ref.delete()

    existing = sessions_ref.where("email", "==", email_key) \
        .where("expires_at", ">", now).limit(1).get()
    for snap in existing:
        return snap.id

    session_id = make_session_id(email_key, now)
    expires_at = now + timedelta(hours=SESSION_TTL_HOURS)
    sessions_ref.document(session_id).set({
        "session_id": session_id,
        "email": email_key,
        "archetype": None,
        "created_at": now,
        "expires_at": expires_at,
        "ttl_hours": SESSION_TTL_HOURS,
    })
    return session_id


def get_active_session_id(db, email: str):
    """Active (non-expired) session id for the email, or None."""
    if not db or not is_demo_ae(email):
        return None
    now = _now()
    for snap in db.collection(SESSIONS_COLLECTION) \
            .where("email", "==", str(email).lower()) \
            .where("expires_at", ">", now).limit(1).stream():
        return snap.id
    return None


def log_action(db, email: str, action_type: str, payload: dict = None):
    """Record a generic AE action into the active session's actions log.
    Safe fallback: returns None for non-demo callers."""
    if not db or not is_demo_ae(email):
        return None
    sid = get_or_create_session(db, email)
    if not sid:
        return None
    now = _now()
    ref = db.collection(SESSIONS_COLLECTION).document(sid) \
        .collection(ACTIONS_SUBCOLLECTION).document()
    ref.set({
        "action_type": action_type,
        "payload": payload or {},
        "email": str(email).lower(),
        "created_at": now,
    })
    return ref.id


def log_decision(db, email: str, decision: dict):
    """Record a formal governance decision. Returns the display overlay that
    the client merges onto master rows (masters are never modified)."""
    if not db or not is_demo_ae(email):
        return None
    sid = get_or_create_session(db, email)
    if not sid:
        return None
    now = _now()
    ref = db.collection(SESSIONS_COLLECTION).document(sid) \
        .collection(DECISIONS_SUBCOLLECTION).document()
    doc = {
        "decision_id": ref.id,
        "email": str(email).lower(),
        "created_at": now,
        **(decision or {}),
    }
    ref.set(doc)
    return {"decision_id": ref.id, **doc}


def load_cap_overlays(db, email: str) -> dict:
    """Overlay map for display merging: {cap_doc_id: fields} from the active
    session's decisions (newest wins). Non-demo callers get {}."""
    sid = get_active_session_id(db, email)
    if not sid:
        return {}
    overlays = {}
    docs = db.collection(SESSIONS_COLLECTION).document(sid) \
        .collection(DECISIONS_SUBCOLLECTION).stream()
    for snap in docs:
        d = snap.to_dict() or {}
        target = d.get("target") or {}
        if target.get("kind") != "cap" or not target.get("id"):
            continue
        overlays[target["id"]] = {
            "status": d.get("result_status", "In Progress"),
            "ae_signature": d.get("signature"),
            "ae_signed_at": d.get("created_at"),
            "ae_review_date": d.get("review_date"),
            "escalated_to_ae": False,
            "manager_approval": d.get("manager_approval"),
            "review_comments": d.get("note"),
            "_overlay": True,
        }
    return overlays


def apply_overlay(rows: list, overlays: dict) -> list:
    """Merge session overlays onto master rows (display only)."""
    if not overlays:
        return rows
    merged = []
    for row in rows:
        ov = overlays.get(row.get("id"))
        if ov:
            row = {**row, **{k: v for k, v in ov.items() if not k.startswith("_")}}
            row["_overlay"] = True
        merged.append(row)
    return merged
