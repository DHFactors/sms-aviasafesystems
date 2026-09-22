# ============================================================================
# FILE: meetings.py
# PATH: backend/app/routes/meetings.py
# PURPOSE: Module B §28/§29 (P3-4) — SAG / SRB meeting + shared action-item
#          API. Thin wrappers over MeetingService; no business logic here.
# ============================================================================

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.middleware.auth import get_safety_manager
from app.services.meeting_service import MeetingService

router = APIRouter()


def _envelope(data: Any) -> Dict[str, Any]:
    return {"status": "success", "timestamp": datetime.now(timezone.utc), "data": data}


class MeetingCreate(BaseModel):
    scheduled_at: Optional[str] = None
    held_at: Optional[str] = None
    attendees: Optional[List[Any]] = None
    minutes_ref: Optional[str] = None
    minutes_summary: Optional[str] = None
    status: Optional[str] = "Scheduled"


class MeetingUpdate(BaseModel):
    scheduled_at: Optional[str] = None
    held_at: Optional[str] = None
    attendees: Optional[List[Any]] = None
    minutes_ref: Optional[str] = None
    minutes_summary: Optional[str] = None
    status: Optional[str] = None


class ActionItemCreate(BaseModel):
    meeting_type: str = Field(..., description="'sag' | 'srb'")
    meeting_id: Optional[str] = None
    hazard_id: Optional[str] = None
    cap_id: Optional[str] = None
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = "Open"
    notes: Optional[str] = None


class ActionItemUpdate(BaseModel):
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    hazard_id: Optional[str] = None
    cap_id: Optional[str] = None
    meeting_id: Optional[str] = None


def _service(user: Dict[str, Any]) -> MeetingService:
    if not user.get("tenant_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Tenant access required")
    return MeetingService(user["tenant_id"])


def _meeting_routes(meeting_type: str):
    """Register the POST/GET/PATCH meeting routes for one meeting type."""

    @router.post(f"/{meeting_type}/meetings", response_model=dict,
                 status_code=status.HTTP_201_CREATED)
    async def create_meeting(payload: MeetingCreate,
                             user: Dict[str, Any] = Depends(get_safety_manager)):
        svc = _service(user)
        try:
            return _envelope(svc.create_meeting(meeting_type, **payload.model_dump(exclude_none=True)))
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    @router.get(f"/{meeting_type}/meetings", response_model=dict)
    async def list_meetings(status_filter: Optional[str] = Query(None, alias="status"),
                            user: Dict[str, Any] = Depends(get_safety_manager)):
        svc = _service(user)
        return _envelope({"meetings": svc.list_meetings(meeting_type, status_filter)})

    @router.patch(f"/{meeting_type}/meetings/{{meeting_id}}", response_model=dict)
    async def update_meeting(meeting_id: str, payload: MeetingUpdate,
                             user: Dict[str, Any] = Depends(get_safety_manager)):
        svc = _service(user)
        try:
            return _envelope(svc.update_meeting(
                meeting_type, meeting_id, payload.model_dump(exclude_none=True)))
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return create_meeting, list_meetings, update_meeting


# Register for both SAG (quarterly) and SRB (6-monthly).
_sag = _meeting_routes("sag")
_srb = _meeting_routes("srb")


@router.post("/action-items", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_action_item(payload: ActionItemCreate,
                             user: Dict[str, Any] = Depends(get_safety_manager)):
    svc = _service(user)
    try:
        result = svc.create_action_item(
            payload.meeting_type, payload.meeting_id or "",
            payload.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return _envelope(result)


@router.patch("/action-items/{action_id}", response_model=dict)
async def update_action_item(action_id: str, payload: ActionItemUpdate,
                             user: Dict[str, Any] = Depends(get_safety_manager)):
    svc = _service(user)
    try:
        return _envelope(svc.update_action_item(
            action_id, payload.model_dump(exclude_none=True)))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
