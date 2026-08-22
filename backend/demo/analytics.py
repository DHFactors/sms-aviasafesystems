# ============================================================================
# FILE: backend/demo/analytics.py
# PURPOSE: Demo analytics persistence (Chunk 7).
#
# Sales-demo telemetry for prospect AE sessions is stored under:
#
#     demo_analytics/{email}/events/{event_id}
#
# Tracked client-side by public/js/demo-analytics.js and POSTed through
# /api/v1/demo/analytics/* (Admin SDK bypasses Firestore rules, so the
# collection is fully locked to clients in firestore.rules).
#
# SAFE FALLBACK: only registered prospect AE accounts (ae@* present in
# PROSPECT_REGISTRY) are ever written. Standard tenants and unregistered
# accounts short-circuit — zero writes, zero errors surfaced.
# ============================================================================

from datetime import datetime, timezone

from seed.prospect_registry import PROSPECT_REGISTRY

ANALYTICS_COLLECTION = "demo_analytics"
EVENTS_SUBCOLLECTION = "events"


def _now():
    return datetime.now(timezone.utc)


def is_demo_ae(email: str) -> bool:
    e = str(email or "").lower()
    return e.startswith("ae@") and e in {k.lower() for k in PROSPECT_REGISTRY.keys()}


def track_event(db, email: str, event_type: str, payload: dict = None):
    """Persist one analytics event. Returns the event id, or None when the
    caller is not a registered demo AE (safe fallback)."""
    if not db or not is_demo_ae(email) or not event_type:
        return None
    email_key = str(email).lower()
    ref = db.collection(ANALYTICS_COLLECTION).document(email_key) \
        .collection(EVENTS_SUBCOLLECTION).document()
    ref.set({
        "event_type": str(event_type),
        "payload": payload or {},
        "email": email_key,
        "created_at": _now(),
    })
    return ref.id


def track_events(db, email: str, events: list):
    """Batch-persist a list of {event_type, payload, created_at?} events.
    Returns the number written (0 for non-demo callers)."""
    if not db or not is_demo_ae(email):
        return 0
    email_key = str(email).lower()
    written = 0
    batch = db.batch()
    for ev in events or []:
        if not isinstance(ev, dict) or not ev.get("event_type"):
            continue
        ref = db.collection(ANALYTICS_COLLECTION).document(email_key) \
            .collection(EVENTS_SUBCOLLECTION).document()
        batch.set(ref, {
            "event_type": str(ev["event_type"]),
            "payload": ev.get("payload") or {},
            "email": email_key,
            "created_at": ev.get("created_at") or _now(),
        })
        written += 1
        if written % 400 == 0:
            batch.commit()
            batch = db.batch()
    if written:
        batch.commit()
    return written
