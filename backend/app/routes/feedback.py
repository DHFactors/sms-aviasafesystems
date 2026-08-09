# ============================================================================
# FILE: feedback.py
# PATH: backend/app/routes/feedback.py
# PURPOSE: Lightweight in-product feedback collection for the safety
#          intelligence dashboards (CAAN + operator). Feedback is written to
#          Firestore `feedback` collection with role/tenant context so it can
#          be reviewed quarterly (aligned with the SSP reporting cycle).
#          No PII is required - only the authenticated user's uid/role/tenant.
# AUTHOR: AviaSAFE Systems
# ============================================================================

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from loguru import logger

from app.middleware.auth import get_current_user
from app.firebase import get_db

router = APIRouter()

FEEDBACK_COLLECTION = "feedback"


class FeedbackMessage(BaseModel):
    subject: str = Field(..., min_length=2, max_length=200)
    message: str = Field(..., min_length=5, max_length=3000)
    rating: Optional[int] = Field(None, ge=1, le=5)
    page: Optional[str] = Field(None, max_length=200)


def _envelope(data: Any) -> Dict[str, Any]:
    return {
        "status": "success",
        "timestamp": datetime.now(),
        "data": data,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    payload: FeedbackMessage,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Store in-product safety-intelligence feedback.

    Records the authenticated user's uid/role/tenant (no other personal data),
    the page context, optional 1-5 rating, and the message. Reviewable via the
    Firestore `feedback` collection or a future admin endpoint.
    """
    now = datetime.now(timezone.utc)
    doc = {
        "uid": user.get("uid"),
        "email": user.get("email"),
        "role": user.get("role"),
        "tenant_id": user.get("tenant_id"),
        "subject": payload.subject.strip(),
        "message": payload.message.strip(),
        "rating": payload.rating,
        "page": payload.page,
        "created_at": now,
        "status": "new",
    }

    try:
        db = get_db()
        _, ref = db.collection(FEEDBACK_COLLECTION).add(doc)
    except Exception as e:
        logger.error(f"Failed to store feedback from {user.get('email')}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="We could not store your feedback right now. Please try again later.",
        )

    logger.info(f"Feedback received from {user.get('email')} (role={user.get('role')})")
    return _envelope({"id": ref.id, "ok": True})
