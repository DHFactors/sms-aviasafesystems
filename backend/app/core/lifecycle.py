"""APScheduler lifecycle — mounts scheduled jobs into FastAPI lifespan.

Jobs:
  * Weekly CAAN SSP report dispatch  — every Monday 02:00 NPT (Asia/Kathmandu)
  * Monthly tenant SRB dispatch     — 1st of every month 00:00 NPT

The scheduler starts on application startup and shuts down gracefully with the
app lifespan. APScheduler's BackgroundScheduler runs in a daemon thread and does
not block the async event loop.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger


_SCHEDULER: Optional[BackgroundScheduler] = None


def _run_weekly_ssp_dispatch() -> None:
    """Entry point for APScheduler: weekly CAAN SSP report dispatch."""
    logger.info("APScheduler trigger: weekly SSP dispatch starting")
    try:
        from app.workers.scheduler import ScheduledReportWorker
        worker = ScheduledReportWorker()
        result = worker.run_weekly_ssp_dispatch()
        logger.info(f"Weekly SSP dispatch completed: {result}")
    except Exception as e:
        logger.error(f"Weekly SSP dispatch failed: {e}")


def _run_monthly_tenant_dispatch() -> None:
    """Entry point for APScheduler: monthly tenant SRB dispatch."""
    logger.info("APScheduler trigger: monthly tenant SRB dispatch starting")
    try:
        from app.workers.tenant_scheduler import TenantReportWorker
        worker = TenantReportWorker()
        result = worker.run_monthly_tenant_dispatch()
        logger.info(f"Monthly tenant SRB dispatch completed: {result}")
    except Exception as e:
        logger.error(f"Monthly tenant SRB dispatch failed: {e}")


def _run_dlq_replay() -> None:
    """Entry point for APScheduler: daily DLQ replay sweep at 03:00 NPT."""
    logger.info("APScheduler trigger: DLQ replay sweep starting")
    try:
        from app.services.dlq_service import DlqService
        svc = DlqService()
        unresolved = svc.list_unresolved(limit=20)
        logger.info(f"DLQ sweep found {len(unresolved)} unresolved records")
    except Exception as e:
        logger.error(f"DLQ replay sweep failed: {e}")


def get_scheduler() -> BackgroundScheduler:
    """Return the module-level scheduler, creating it on first access."""
    global _SCHEDULER
    if _SCHEDULER is None:
        _SCHEDULER = BackgroundScheduler(
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 3600,
            }
        )
    return _SCHEDULER


def start_scheduler() -> None:
    """Register all scheduled jobs and start the scheduler.

    Safe to call multiple times — the scheduler is idempotent on restart.
    """
    scheduler = get_scheduler()

    # Remove existing jobs (idempotent restart)
    scheduler.remove_all_jobs()

    # Weekly CAAN SSP dispatch — Monday 02:00 Asia/Kathmandu (UTC+5:45 = 18:15 UTC Sunday)
    scheduler.add_job(
        _run_weekly_ssp_dispatch,
        trigger=CronTrigger(
            day_of_week="mon",
            hour=2,
            minute=0,
            timezone="Asia/Kathmandu",
        ),
        id="weekly_ssp_dispatch",
        name="Weekly CAAN SSP Report Dispatch",
        replace_existing=True,
    )
    logger.info("Scheduled job: weekly_ssp_dispatch (Monday 02:00 NPT)")

    # Monthly tenant SRB dispatch — 1st of month 00:00 Asia/Kathmandu (UTC+5:45 = 18:15 UTC last day prior)
    scheduler.add_job(
        _run_monthly_tenant_dispatch,
        trigger=CronTrigger(
            day=1,
            hour=0,
            minute=0,
            timezone="Asia/Kathmandu",
        ),
        id="monthly_tenant_dispatch",
        name="Monthly Tenant SRB Dispatch",
        replace_existing=True,
    )
    logger.info("Scheduled job: monthly_tenant_dispatch (1st of month 00:00 NPT)")

    # Daily DLQ replay sweep — 03:00 Asia/Kathmandu
    scheduler.add_job(
        _run_dlq_replay,
        trigger=CronTrigger(
            hour=3,
            minute=0,
            timezone="Asia/Kathmandu",
        ),
        id="daily_dlq_replay",
        name="Daily DLQ Replay Sweep",
        replace_existing=True,
    )
    logger.info("Scheduled job: daily_dlq_replay (03:00 NPT)")

    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler background scheduler started")


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    global _SCHEDULER
    if _SCHEDULER is not None and _SCHEDULER.running:
        _SCHEDULER.shutdown(wait=False)
        logger.info("APScheduler background scheduler stopped")
    _SCHEDULER = None
