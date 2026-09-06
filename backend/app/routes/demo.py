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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from datetime import datetime, timezone
from loguru import logger

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


# ============================================================================
# DEMO CONTRACT ACCEPTANCE — User Acceptance Agreement (public/demo-contract.html)
# ============================================================================

class DemoAcceptance(BaseModel):
    full_name: str
    organization: str
    email: EmailStr
    accepted_at: str
    user_agent: Optional[str] = None


@router.post("/accept")
async def accept_demo(data: DemoAcceptance, request: Request):
    """Record demo acceptance agreement — private, after agreement reached.

    Stores acceptance in audit log and, if available, in Supabase
    `demo_contract_acceptances` table. Always returns success so the
    frontend can redirect to the demo dashboard.
    """
    try:
        from app.services.audit_service import log_audit, request_context
        ip, request_id = request_context(request)
        # Primary store: audit log (always available)
        log_audit(
            action="DEMO_CONTRACT_ACCEPTED",
            user=data.email,
            tenant_id=data.organization,
            target_type="demo_contract",
            target_id=data.email,
            ip=ip,
            request_id=request_id,
            metadata={
                "full_name": data.full_name,
                "organization": data.organization,
                "accepted_at": data.accepted_at,
                "user_agent": data.user_agent,
            },
        )
        # Best-effort Supabase store if table exists
        try:
            from app.db import pg
            from app.db.db_models import AuditLog
            # Also try dedicated table if present (optional)
            from sqlalchemy import text
            from app.db.session import get_session_factory
            factory = get_session_factory()
            if factory is not None:
                async with factory() as session:
                    await session.execute(
                        text("""
                            CREATE TABLE IF NOT EXISTS demo_contract_acceptances (
                                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                full_name TEXT NOT NULL,
                                organization TEXT NOT NULL,
                                email TEXT NOT NULL,
                                accepted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                                user_agent TEXT,
                                ip_address TEXT,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                            )
                        """)
                    )
                    await session.commit()
                    await session.execute(
                        text("""
                            INSERT INTO demo_contract_acceptances
                            (full_name, organization, email, accepted_at, user_agent, ip_address)
                            VALUES (:full_name, :organization, :email, :accepted_at, :user_agent, :ip)
                        """),
                        {
                            "full_name": data.full_name,
                            "organization": data.organization,
                            "email": data.email,
                            "accepted_at": data.accepted_at,
                            "user_agent": data.user_agent,
                            "ip": ip,
                        },
                    )
                    await session.commit()
        except Exception as e:
            logger.debug(f"Demo contract Supabase store skipped: {e}")

        logger.info(f"Demo contract accepted: {data.email} ({data.organization})")
        return {"success": True, "message": "Acceptance recorded"}
    except Exception as e:
        logger.error(f"Demo contract acceptance failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))




