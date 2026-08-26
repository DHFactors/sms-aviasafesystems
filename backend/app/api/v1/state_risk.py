from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from loguru import logger

from app.middleware.auth import get_caan_user
from app.repositories.audit_repo import list_recent_dispatches
from app.services.pdf_generator import CaanPdfGenerator
from app.services.state_risk_service import StateRiskService

router = APIRouter()


@router.get("/aggregate")
async def get_state_aggregate_report(
    year: int = Query(..., ge=2000, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    regulator_id: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_caan_user),
):
    """Return the StateAggregateReport payload for the CAAN oversight workspace."""
    svc = StateRiskService(user)
    agg = svc.aggregate_state_risk(year, quarter, regulator_id=regulator_id)

    report = {
        "reporting_year": year,
        "reporting_quarter": quarter,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regulator_id": regulator_id,
        "total_operators": len(set(
            tid for r in agg.get("risks", [])
            for tid in (r.get("contributing_tenants") or [])
        )),
        "total_hazards": sum(r.get("count", 0) for r in agg.get("risks", [])),
        "total_reports": 0,
        "total_cans": 0,
        "open_cans": 0,
        "overdue_cans": 0,
        "industry_risk_index": None,
        "hrc_distribution": agg.get("risks", []),
        "spi_metrics": [],
        "operator_summaries": [],
        "alosp_evaluations": [],
        "insights": [],
        "recommendations": [],
    }
    return {"success": True, "report": report}


@router.get("/export-pdf")
async def export_state_risk_pdf(
    year: int = Query(..., ge=2000, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    regulator_id: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_caan_user),
):
    """Stream the CAAN SSP oversight report as a PDF attachment."""
    svc = StateRiskService(user)
    agg = svc.aggregate_state_risk(year, quarter, regulator_id=regulator_id)

    report_data = {
        "reporting_year": year,
        "reporting_quarter": quarter,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regulator_id": regulator_id,
        "total_operators": len(set(
            tid for r in agg.get("risks", [])
            for tid in (r.get("contributing_tenants") or [])
        )),
        "total_hazards": sum(r.get("count", 0) for r in agg.get("risks", [])),
        "hrc_distribution": agg.get("risks", []),
        "operator_summaries": [],
        "insights": [],
        "recommendations": [],
    }

    pdf_bytes = CaanPdfGenerator.build_ssp_report_pdf(report_data)
    filename = f"CAAN_SSP_Report_{year}Q{quarter}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/dispatch-email")
async def dispatch_report_email(
    year: int = Query(..., ge=2000, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    recipient: str = Query(..., description="Recipient email address"),
    regulator_id: Optional[str] = Query(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user: Dict[str, Any] = Depends(get_caan_user),
):
    """Queue a background task to generate and email the SSP report PDF."""
    svc = StateRiskService(user)
    agg = svc.aggregate_state_risk(year, quarter, regulator_id=regulator_id)

    report_data = {
        "reporting_year": year,
        "reporting_quarter": quarter,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regulator_id": regulator_id,
        "total_operators": len(set(
            tid for r in agg.get("risks", [])
            for tid in (r.get("contributing_tenants") or [])
        )),
        "total_hazards": sum(r.get("count", 0) for r in agg.get("risks", [])),
        "hrc_distribution": agg.get("risks", []),
        "operator_summaries": [],
        "insights": [],
        "recommendations": [],
    }

    def _bg_dispatch():
        from app.services.email_service import send_regulatory_report
        pdf_bytes = CaanPdfGenerator.build_ssp_report_pdf(report_data)
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        period = f"{year} Q{quarter}"
        send_regulatory_report(
            to=recipient,
            subject=f"CAAN SSP Oversight Report — {period}",
            html_body=f"<h2>SSP Oversight Report</h2><p>Period: {period}</p><p>See attached PDF.</p>",
            text_body=f"SSP Oversight Report\nPeriod: {period}\nSee attached PDF.",
            attachment_bytes=pdf_bytes,
            attachment_filename=f"CAAN_SSP_Report_{year}Q{quarter}.pdf",
        )
        logger.info(f"SSP report dispatched to {recipient} (sha256={sha256})")

    background_tasks.add_task(_bg_dispatch)

    return {
        "success": True,
        "message": f"Report dispatch queued for {recipient}",
        "year": year,
        "quarter": quarter,
    }


@router.get("/audit-logs")
async def get_dispatch_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    regulator_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_caan_user),
):
    """Return recent dispatch audit log records."""
    logs = list_recent_dispatches(limit=limit, regulator_id=regulator_id, status=status)
    return {"success": True, "count": len(logs), "logs": logs}
