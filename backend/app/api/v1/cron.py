from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from app.core.config import settings
from app.middleware.auth import get_caan_user
from app.services.dlq_service import DlqService
from app.workers.scheduler import ScheduledReportWorker

router = APIRouter()


def _verify_task_key(task_key: str = Query(..., alias="taskKey")) -> bool:
    """Verify the internal task API key for cron endpoints."""
    if not settings.TASK_API_KEY:
        raise HTTPException(status_code=503, detail="TASK_API_KEY not configured")
    if task_key != settings.TASK_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid task key")
    return True


@router.post("/weekly-ssp-dispatch")
async def weekly_ssp_dispatch(
    _verified: bool = Depends(_verify_task_key),
):
    """Protected cron endpoint: compile and dispatch weekly CAAN SSP oversight
    reports to all registered regulator authorities."""
    worker = ScheduledReportWorker()
    result = worker.run_weekly_ssp_dispatch()
    logger.info(f"Weekly SSP dispatch cron executed: {result}")
    return {"success": True, "result": result}


@router.post("/dlq/replay/{dlq_id}")
async def replay_dlq_record(
    dlq_id: str,
    user: Dict[str, Any] = Depends(get_caan_user),
):
    """Replay a quarantined dead-letter record by re-executing the original operation."""
    dlq = DlqService()
    record = dlq.get_record(dlq_id)
    if not record:
        raise HTTPException(status_code=404, detail="DLQ record not found")

    operation = record.get("original_operation", "")
    payload = record.get("payload", {})

    if operation == "email_dispatch":
        from app.services.email_service import send_regulatory_report
        try:
            result = send_regulatory_report(
                to=payload.get("to", ""),
                subject=payload.get("subject", "Replayed Report"),
                html_body=payload.get("html_body", ""),
                text_body=payload.get("text_body", ""),
            )
            if result.get("sent"):
                dlq.mark_replayed(dlq_id, user=user.get("uid"), note="Replayed successfully")
                return {"success": True, "message": "Email dispatched", "dlq_id": dlq_id}
            else:
                dlq.mark_investigating(dlq_id, user=user.get("uid"))
                return {"success": False, "message": "Dispatch failed again", "dlq_id": dlq_id}
        except Exception as e:
            dlq.mark_investigating(dlq_id, user=user.get("uid"))
            raise HTTPException(status_code=500, detail=f"Replay failed: {e}")
    else:
        raise HTTPException(status_code=400, detail=f"Unknown operation for replay: {operation}")


@router.post("/dlq/discard/{dlq_id}")
async def discard_dlq_record(
    dlq_id: str,
    user: Dict[str, Any] = Depends(get_caan_user),
):
    """Mark a DLQ record as discarded (no further retry)."""
    dlq = DlqService()
    record = dlq.get_record(dlq_id)
    if not record:
        raise HTTPException(status_code=404, detail="DLQ record not found")
    dlq.mark_discarded(dlq_id, user=user.get("uid"), note="Discarded by operator")
    return {"success": True, "message": f"DLQ record {dlq_id} discarded"}
