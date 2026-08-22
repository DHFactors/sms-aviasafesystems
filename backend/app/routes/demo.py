# ============================================================================
# FILE: backend/app/routes/demo.py
# PURPOSE: Virtual Tenant Mirroring — demo session & analytics endpoints
#          (Chunk 7). All writes land in the isolated demo_sessions /
#          demo_analytics trees; master archetype collections are never
#          modified through these routes.
#
# SAFE FALLBACK: every endpoint validates the caller as a registered prospect
# AE (ae@* present in PROSPECT_REGISTRY). Anything else receives
# {"ok": false, "reason": "not_a_demo_session"} — standard tenants are
# completely unaffected.
#
# Mounted at /api/v1/demo (see app/main.py).
# ============================================================================

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.auth import get_current_user
from demo import analytics, session_manager

router = APIRouter()


def _require_demo_ae(user: Dict[str, Any]) -> str:
    email = str((user or {}).get("email") or "").lower()
    if not session_manager.is_demo_ae(email):
        raise HTTPException(status_code=403, detail="Not a demo AE session")
    return email


class SessionStart(BaseModel):
    email: str


class ActionEvent(BaseModel):
    email: str
    action_type: str
    payload: Optional[dict] = None


class DecisionEvent(BaseModel):
    email: str
    cap_id: str
    decision: str = "accept_risk"           # accept_risk | authorize
    signature: Optional[str] = None         # typed AE signature (accept_risk)
    interval_days: Optional[int] = None     # mandatory review interval
    note: Optional[str] = None              # authorization note / feedback
    residual_severity: Optional[int] = None
    residual_probability: Optional[int] = None


class AnalyticsEvent(BaseModel):
    email: str
    event_type: str
    payload: Optional[dict] = None
    created_at: Optional[str] = None


class AnalyticsBatch(BaseModel):
    email: str
    events: List[AnalyticsEvent]


@router.post("/session/start")
async def start_session(body: SessionStart, user: Dict[str, Any] = Depends(get_current_user)):
    """Get-or-create the caller's 24h demo session. Non-demo callers receive
    ok=False instead of an error so standard tenants are never disturbed."""
    _require_demo_ae(user)
    if str(body.email).lower() != str(user.get("email", "")).lower():
        raise HTTPException(status_code=403, detail="Email mismatch")
    from app.firebase import get_db

    sid = session_manager.get_or_create_session(get_db(), body.email, uid=user.get("uid"))
    return {"ok": bool(sid), "session_id": sid}


@router.post("/session/action")
async def log_action(body: ActionEvent, user: Dict[str, Any] = Depends(get_current_user)):
    _require_demo_ae(user)
    if str(body.email).lower() != str(user.get("email", "")).lower():
        raise HTTPException(status_code=403, detail="Email mismatch")
    from app.firebase import get_db

    action_id = session_manager.log_action(get_db(), body.email, body.action_type, body.payload, uid=user.get("uid"))
    return {"ok": action_id is not None, "action_id": action_id}


@router.post("/session/decision")
async def log_decision(body: DecisionEvent, user: Dict[str, Any] = Depends(get_current_user)):
    """Record a formal AE governance decision as a session overlay.

    Masters are untouched; the returned overlay is merged client-side and by
    /dashboard/master-register for the remainder of the 24h session."""
    _require_demo_ae(user)
    if str(body.email).lower() != str(user.get("email", "")).lower():
        raise HTTPException(status_code=403, detail="Email mismatch")
    if body.decision not in ("authorize", "accept_risk"):
        raise HTTPException(status_code=422, detail="decision must be 'authorize' or 'accept_risk'")
    if body.decision == "accept_risk" and not (body.signature or "").strip():
        raise HTTPException(status_code=422, detail="Typed executive signature is required")

    from datetime import datetime, timedelta, timezone

    from app.firebase import get_db

    now = datetime.now(timezone.utc)
    interval = body.interval_days or (60 if body.decision == "accept_risk" else None)
    review_date = (now + timedelta(days=interval)).isoformat() if interval else None

    overlay = session_manager.log_decision(get_db(), body.email, uid=user.get("uid"), decision={
        "target": {"kind": "cap", "id": body.cap_id},
        "decision": body.decision,
        "result_status": "In Progress",
        "manager_approval": "Approved" if body.decision == "authorize" else "Accepted Risk",
        "signature": (body.signature or "").strip() or None,
        "review_interval_days": interval,
        "review_date": review_date,
        "note": (body.note or "").strip() or None,
        "residual_severity": body.residual_severity,
        "residual_probability": body.residual_probability,
    })
    if overlay is None:
        raise HTTPException(status_code=403, detail="Not a demo AE session")

    return {
        "ok": True,
        "decision_id": overlay["decision_id"],
        # Client-side merge payload for the CAP row.
        "overlay": {
            "id": body.cap_id,
            "status": "In Progress",
            "escalated_to_ae": False,
            "ae_signature": overlay.get("signature"),
            "ae_signed_at": overlay.get("created_at"),
            "ae_review_date": review_date,
            "manager_approval": overlay.get("manager_approval"),
            "review_comments": overlay.get("note"),
        },
    }


@router.post("/analytics/event")
async def track_analytics_event(body: AnalyticsEvent, user: Dict[str, Any] = Depends(get_current_user)):
    _require_demo_ae(user)
    if str(body.email).lower() != str(user.get("email", "")).lower():
        raise HTTPException(status_code=403, detail="Email mismatch")
    from app.firebase import get_db

    event_id = analytics.track_event(get_db(), body.email, body.event_type, body.payload)
    return {"ok": event_id is not None, "event_id": event_id}


@router.post("/analytics/batch")
async def track_analytics_batch(body: AnalyticsBatch, user: Dict[str, Any] = Depends(get_current_user)):
    _require_demo_ae(user)
    if str(body.email).lower() != str(user.get("email", "")).lower():
        raise HTTPException(status_code=403, detail="Email mismatch")
    from app.firebase import get_db

    written = analytics.track_events(
        get_db(), body.email,
        [e.model_dump() for e in body.events],
    )
    return {"ok": True, "written": written}



