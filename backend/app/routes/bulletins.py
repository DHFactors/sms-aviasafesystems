# ============================================================================
# FILE: bulletins.py
# PATH: backend/app/routes/bulletins.py
# PURPOSE: Module B §31 (P3-5) — safety-communication (bulletin) API and
#          lifecycle. Thin wrappers over SafetyCommsService.
# ============================================================================

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.middleware.auth import get_safety_manager, get_current_user
from app.services.safety_comms_service import SafetyCommsService

router = APIRouter()


def _envelope(data: Any) -> Dict[str, Any]:
    return {"status": "success", "timestamp": datetime.now(timezone.utc), "data": data}


class BulletinCreate(BaseModel):
    title: str = Field(..., min_length=1)
    body: Optional[str] = None
    audience: Optional[Any] = None
    derived_from_hazard_ids: Optional[List[str]] = None


def _service(user: Dict[str, Any]) -> SafetyCommsService:
    if not user.get("tenant_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Tenant access required")
    return SafetyCommsService(user["tenant_id"])


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_bulletin(payload: BulletinCreate,
                          user: Dict[str, Any] = Depends(get_current_user)):
    """Create a bulletin draft. Safety Officer or higher may author drafts."""
    allowed = settings.SAFETY_OFFICER_ROLES + settings.TENANT_ADMIN_ROLES + ["SUPER_ADMIN"]
    if user.get("role") not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Safety Officer or higher role required")
    svc = _service(user)
    try:
        result = svc.create_draft(
            user, payload.title, payload.body, payload.audience,
            payload.derived_from_hazard_ids)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return _envelope(result)


@router.get("", response_model=dict)
@router.get("/", response_model=dict, include_in_schema=False)
async def list_bulletins(status_filter: Optional[str] = Query(None, alias="status"),
                         user: Dict[str, Any] = Depends(get_current_user)):
    svc = _service(user)
    try:
        return _envelope({"bulletins": svc.list_communications(status_filter)})
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{bulletin_id}/submit", response_model=dict)
async def submit_bulletin(bulletin_id: str,
                          user: Dict[str, Any] = Depends(get_current_user)):
    svc = _service(user)
    try:
        return _envelope(svc.submit_for_review(bulletin_id, user))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{bulletin_id}/publish", response_model=dict)
async def publish_bulletin(bulletin_id: str,
                           user: Dict[str, Any] = Depends(get_safety_manager)):
    """Publish a bulletin (SAFETY_MANAGER capability)."""
    svc = _service(user)
    try:
        return _envelope(svc.publish(bulletin_id, user))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{bulletin_id}/archive", response_model=dict)
async def archive_bulletin(bulletin_id: str,
                           user: Dict[str, Any] = Depends(get_safety_manager)):
    svc = _service(user)
    try:
        return _envelope(svc.archive(bulletin_id, user))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
