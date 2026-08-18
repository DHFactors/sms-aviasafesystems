# ============================================================================
# FILE: copilot.py
# PATH: backend/app/routes/copilot.py
# PURPOSE: "How Can I Help You?" Safety & Compliance Copilot chat endpoint.
#
# POST /api/v1/copilot/chat — authenticated (Firebase JWT). Delegates to the
# Groq-powered assistant service (see app/services/groq_copilot.py) and always
# returns a reply: on missing API key / upstream errors the service degrades to
# a graceful offline response so the frontend widget never breaks.
# AUTHOR: AviaSAFE Systems
# ============================================================================

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from loguru import logger

from app.middleware.auth import get_current_user
from app.middleware.rate_limit import rate_limit
from app.services.groq_copilot import chat

router = APIRouter()


class CopilotHistoryItem(BaseModel):
    role: str = Field(..., max_length=16)
    content: str = Field(..., max_length=4000)


class CopilotChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    page_context: Optional[str] = Field(None, max_length=200)
    history: Optional[List[CopilotHistoryItem]] = Field(default_factory=list, max_length=20)


class CopilotChatResponse(BaseModel):
    status: str = "success"
    reply: str
    model: str


@router.post("/chat", response_model=CopilotChatResponse, status_code=status.HTTP_200_OK)
@rate_limit("copilot")
async def copilot_chat(
    payload: CopilotChatRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> CopilotChatResponse:
    """Send a safety/SMS question to the Ghanshyam Executive Safety Copilot.

    The assistant receives the authenticated user's role, department, tenant
    classification and current page so guidance is scoped to the operator
    (Fixed-Wing, Rotary, Part-145 AMO or Aerodrome) and role.
    """
    history = [item.dict() for item in (payload.history or [])]

    reply = chat(
        payload.message,
        history=history,
        role=user.get("role"),
        department=user.get("department"),
        tenant_id=user.get("tenant_id"),
        page_context=payload.page_context,
    )

    logger.info(
        f"Copilot reply delivered to {user.get('email')} "
        f"(role={user.get('role')}, tenant={user.get('tenant_id')})"
    )
    return CopilotChatResponse(reply=reply, model="groq")