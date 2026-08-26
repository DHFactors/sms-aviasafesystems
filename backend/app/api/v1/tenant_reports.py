from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from loguru import logger

from app.middleware.auth import get_tenant_user
from app.repositories.audit_repo import list_tenant_dispatches
from app.services.tenant_pdf_generator import TenantPdfGenerator
from app.firebase import get_db

router = APIRouter()


def _compile_tenant_monthly_report(tenant_id: str, year: int, month: int) -> Dict[str, Any]:
    """Compile the TenantMonthlySmsReport payload from Firestore data."""
    db = get_db()
    tenant_doc = db.collection("tenants").document(tenant_id).get()
    tenant_data = tenant_doc.to_dict() if tenant_doc.exists else {}

    def _count(subcol: str) -> list:
        try:
            return [d.to_dict() for d in db.collection(f"tenants/{tenant_id}/{subcol}").stream()]
        except Exception:
            return []

    hazards = _count("hazards")
    reports = _count("reports")
    caps = _count("cans")

    open_hazards = [h for h in hazards if (h.get("status") or "").upper() not in ("CLOSED", "VERIFIED_CLOSED")]
    intolerable = [h for h in open_hazards if (h.get("risk_level") or "").upper() in ("VERY HIGH", "INTOLERABLE")]

    open_capas = [
        {
            "source_reference": c.get("can_number") or c.get("id", ""),
            "description": c.get("description") or c.get("finding", ""),
            "responsible_post_holder": c.get("responsible") or c.get("assigned_to", ""),
            "target_close_out_date": str(c.get("due_date", "")),
            "implementation_status": c.get("status", "OPEN"),
            "priority": c.get("priority", "MEDIUM"),
        }
        for c in caps
        if (c.get("status") or "").upper() not in ("CLOSED", "VERIFIED_CLOSED")
    ]

    return {
        "tenant_id": tenant_id,
        "operator_name": tenant_data.get("operator_name") or tenant_data.get("name", tenant_id),
        "aoc_number": tenant_data.get("aoc_number", ""),
        "reporting_year": year,
        "reporting_month": month,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "flight_hours_logged": tenant_data.get("flight_hours", 0),
        "total_flights": tenant_data.get("total_flights", 0),
        "safety_reports_submitted": len(reports),
        "safety_culture_index": None,
        "total_hazards": len(hazards),
        "open_hazards": len(open_hazards),
        "intolerable_risks": len(intolerable),
        "risk_heatmap": [],
        "spi_metrics": [],
        "open_capas": open_capas,
        "overdue_capas": sum(1 for c in open_capas if "OVERDUE" in (c.get("implementation_status") or "").upper()),
        "insights": [],
        "recommendations": [],
    }


@router.get("/sms/monthly-summary")
async def get_monthly_sms_summary(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    """Return the TenantMonthlySmsReport for the authenticated user's tenant."""
    tenant_id = user["tenant_id"]
    report = _compile_tenant_monthly_report(tenant_id, year, month)
    return {"success": True, "report": report}


@router.get("/sms/export-pdf")
async def export_tenant_srb_pdf(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    """Stream the tenant SRB monthly report as a PDF attachment."""
    tenant_id = user["tenant_id"]
    report = _compile_tenant_monthly_report(tenant_id, year, month)
    pdf_bytes = TenantPdfGenerator.build_srb_report_pdf(report)
    filename = f"SRB_Report_{tenant_id}_{year}{month:02d}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/sms/dispatch-srb")
async def dispatch_srb_report(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    recipient: str = Query(..., description="Recipient email for the SRB pack"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    """Queue a background task to generate and email the SRB report PDF."""
    tenant_id = user["tenant_id"]

    def _bg_dispatch():
        from app.services.email_service import send_regulatory_report
        report = _compile_tenant_monthly_report(tenant_id, year, month)
        pdf_bytes = TenantPdfGenerator.build_srb_report_pdf(report)
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        operator = report.get("operator_name", tenant_id)
        send_regulatory_report(
            to=recipient,
            subject=f"Monthly SRB Report — {operator} ({year}-{month:02d})",
            html_body=f"<h2>SRB Report</h2><p>Operator: {operator}</p><p>Period: {year}-{month:02d}</p>",
            text_body=f"SRB Report\nOperator: {operator}\nPeriod: {year}-{month:02d}\n",
            attachment_bytes=pdf_bytes,
            attachment_filename=f"SRB_Report_{tenant_id}_{year}{month:02d}.pdf",
        )
        logger.info(f"SRB dispatch to {recipient} for tenant {tenant_id} (sha256={sha256})")

    background_tasks.add_task(_bg_dispatch)
    return {
        "success": True,
        "message": f"SRB dispatch queued for {recipient}",
        "tenant_id": tenant_id,
    }


@router.get("/sms/audit-logs")
async def get_tenant_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_tenant_user),
):
    """Return tenant-scoped dispatch audit trail records."""
    tenant_id = user["tenant_id"]
    logs = list_tenant_dispatches(tenant_id, limit=limit, status=status)
    return {"success": True, "tenant_id": tenant_id, "count": len(logs), "logs": logs}
