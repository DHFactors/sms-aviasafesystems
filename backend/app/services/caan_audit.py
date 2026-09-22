# ============================================================================
# FILE: caan_audit.py
# PATH: backend/app/services/caan_audit.py
# PURPOSE: Module C §5/§6/§12 (DP-3, SS-2, HV-2) — audit writers for CAAN
#          cross-tenant reads, safety-information shares, and escalations.
#          Reuses the shared `audit_logs` writer.
# ============================================================================

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.audit_service import log_audit


def _actor(user: Optional[Dict[str, Any]]) -> str:
    return (user or {}).get("email") or (user or {}).get("uid") or "caan"


def log_caan_read(user, resource: str, *, target_type: str = "aggregate",
                  target_id: Optional[str] = None,
                  tenant_id: Optional[str] = None,
                  metadata: Optional[Dict[str, Any]] = None) -> None:
    """Audit a CAAN cross-tenant read (`CAAN_READ_<RESOURCE>`)."""
    log_audit(
        action=f"CAAN_READ_{resource.upper()}",
        user=_actor(user),
        tenant_id=tenant_id,
        target_type=target_type,
        target_id=target_id,
        metadata=metadata or {},
    )


def log_caan_share(user, resource: str, *, recipient: Optional[str] = None,
                   target_id: Optional[str] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> None:
    """Audit a safety-information share (`CAAN_SHARE_<RESOURCE>`)."""
    meta = dict(metadata or {})
    if recipient:
        meta["recipient"] = recipient
    log_audit(
        action=f"CAAN_SHARE_{resource.upper()}",
        user=_actor(user),
        tenant_id=None,
        target_type="share",
        target_id=target_id,
        metadata=meta,
    )


def log_caan_escalated_read(user, *, tenant_id: Optional[str] = None,
                            target_id: Optional[str] = None,
                            metadata: Optional[Dict[str, Any]] = None) -> None:
    """Audit a CAAN escalated (temporary-access) read (`CAAN_ESCALATED_READ`)."""
    log_audit(
        action="CAAN_ESCALATED_READ",
        user=_actor(user),
        tenant_id=tenant_id,
        target_type="escalated_read",
        target_id=target_id,
        metadata=metadata or {},
    )
