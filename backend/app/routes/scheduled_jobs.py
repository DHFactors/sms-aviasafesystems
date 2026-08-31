# ============================================================================
# FILE: scheduled_jobs.py
# PATH: backend/app/routes/scheduled_jobs.py
# PURPOSE: Internal, task-key protected scheduled-job endpoints.
#
#          POST /api/v1/jobs/check-overdue-caps scans the PostgreSQL `caps`
#          table for Corrective Action Plans whose target_completion_date has
#          passed and whose status is not terminal (Completed), then dispatches
#          an overdue email reminder to each plan's process owner / Safety
#          Manager.
#
#          Intended to be driven periodically (e.g. a daily timer or Cloud
#          Scheduler) with the X-Task-Key header (TASK_API_KEY) — the same
#          convention used by the admin check-overdue task.
# AUTHOR: AviaSAFE Systems
# ============================================================================

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from loguru import logger
from sqlalchemy import select

from app.core.config import settings
from app.db.db_models import Can, Cap
from app.db.isolation import demo_scope
from app.db.session import session_scope
from app.routes.admin import verify_task_auth

router = APIRouter()

CAP_TERMINAL_STATUSES = {"Completed", "Overdue", "Cancelled"}


@router.post("/check-overdue-caps")
async def check_overdue_caps(
    request: Request,
    _auth: Dict[str, Any] = Depends(verify_task_auth),
) -> Dict[str, Any]:
    """Find CAPs past their target completion date and email overdue reminders."""
    now = datetime.now(timezone.utc)
    sent = 0
    skipped = 0
    notified: List[str] = []

    from app.services.email_service import send_cap_overdue_email

    async with session_scope() as session:
        rows = (
            await session.execute(
                select(Cap, Can)
                .join(Can, Cap.can_id == Can.id)
                .where(
                    Cap.is_demo == demo_scope(),
                    Can.is_demo == demo_scope(),
                    Cap.target_completion_date.isnot(None),
                    Cap.target_completion_date < now,
                    Cap.status.notin_(list(CAP_TERMINAL_STATUSES)),
                )
            )
        ).all()

        for cap, can in rows:
            cap_data = {
                "cap_reference": cap.cap_reference,
                "can_reference": can.can_reference,
                "action_plan": cap.action_plan,
                "department": cap.department,
                "target_completion_date": cap.target_completion_date,
                "process_owner": cap.process_owner,
                "submitted_by": cap.submitted_by,
                "tenant_id": can.tenant_id,
            }
            try:
                recipient = cap.process_owner
                if not recipient:
                    recipient = cap.submitted_by
                result = send_cap_overdue_email(cap_data, to=recipient)
                if result.get("sent"):
                    sent += 1
                else:
                    skipped += 1
                notified.append(cap.cap_reference)
            except Exception as e:
                skipped += 1
                logger.warning(f"Overdue CAP email failed for {cap.cap_reference}: {e}")

    summary = {
        "status": "success",
        "run_at": now.isoformat(),
        "overdue_caps": len(notified),
        "emails_sent": sent,
        "emails_skipped": skipped,
        "notified": notified,
    }
    logger.info(f"Check-overdue-caps job completed: {summary}")
    return {"success": True, "result": summary}
