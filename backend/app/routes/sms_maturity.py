# ============================================================================
# FILE: sms_maturity.py
# PATH: backend/app/routes/sms_maturity.py
# PURPOSE: Module A's public SMS maturity assessment cache endpoints. The
#          dashboard layer (and any other consumer) reads/writes the cache
#          through these routes instead of touching Module A's `sms_maturity`
#          table directly (MODULE_A_CONTRACT.md §7.1 boundary).
# ============================================================================

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings
from app.middleware.auth import get_current_user
from app.services import sms_maturity_service

router = APIRouter()


class SmsMaturityCachePayload(BaseModel):
    """Assessment payload written to the Module A `sms_maturity` cache.

    Extra keys (legacy ``pcts``/``tiers``/``period_days``/``generated_at``) are
    accepted and ignored so existing dashboard callers keep working.
    """

    model_config = {"extra": "allow"}

    overall_sms_maturity: Optional[float] = None
    pillars: Optional[Dict[str, Any]] = None
    question_averages: Optional[Dict[str, Any]] = None
    element_scores: Optional[Dict[str, Any]] = None
    low_pillars: Optional[List[Dict[str, Any]]] = None
    gap_analysis: Optional[Any] = None
    recommendations: Optional[List[Dict[str, Any]]] = None


def _assert_tenant_scope(user: Dict[str, Any], tenant_id: str) -> None:
    """A tenant-scoped user may only touch their own tenant's cache."""
    user_tenant = user.get("tenant_id")
    if (
        user_tenant
        and user_tenant != tenant_id
        and user.get("role") not in settings.CROSS_TENANT_ROLES
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant_id does not match the authenticated user's tenant",
        )


@router.post("/{tenant_id}/cache", status_code=status.HTTP_201_CREATED)
async def write_sms_maturity_cache(
    tenant_id: str,
    payload: SmsMaturityCachePayload,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Persist an SMS maturity assessment into Module A's cache."""
    _assert_tenant_scope(user, tenant_id)
    sms_maturity_service.write_sms_maturity(tenant_id, payload.model_dump())
    return {"status": "success", "tenant_id": tenant_id}


@router.get("/{tenant_id}/cache")
async def read_sms_maturity_cache(
    tenant_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Read the latest cached SMS maturity assessment for a tenant."""
    _assert_tenant_scope(user, tenant_id)
    data = sms_maturity_service.read_sms_maturity(tenant_id)
    return {"status": "success", "tenant_id": tenant_id, "data": data}
