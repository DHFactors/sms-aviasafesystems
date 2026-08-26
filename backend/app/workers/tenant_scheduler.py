from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.firebase import get_db
from app.repositories.audit_repo import (
    list_tenant_dispatches,
    record_tenant_dispatch_intent,
    update_tenant_dispatch_status,
)
from app.services.dlq_service import DlqService
from app.services.email_service import send_regulatory_report
from app.services.tenant_pdf_generator import TenantPdfGenerator


class TenantReportWorker:
    """Background worker that compiles monthly SRB packages for active
    paid tenants and dispatches them to the tenant's Safety Action Group."""

    def __init__(self):
        self.db = get_db()

    def run_monthly_tenant_dispatch(self) -> Dict[str, Any]:
        """Main entry point for monthly scheduled dispatch. Iterates all
        active tenants, compiles SRB reports, generates PDFs, records audit
        entries with SHA-256 checksums, and dispatches emails."""
        now = datetime.now(timezone.utc)
        year = now.year
        month = now.month
        results: List[Dict[str, Any]] = []

        tenants = self._get_active_tenants()
        if not tenants:
            logger.warning("No active tenants found for monthly SRB dispatch")
            return {"dispatched": 0, "total": 0, "results": []}

        for tenant in tenants:
            tenant_id = tenant.get("tenant_id") or tenant.get("id", "")
            if not tenant_id:
                continue

            try:
                result = self._dispatch_for_tenant(
                    tenant_id=tenant_id,
                    tenant_data=tenant,
                    year=year,
                    month=month,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Monthly SRB dispatch failed for tenant {tenant_id}: {e}")
                results.append({
                    "tenant_id": tenant_id,
                    "success": False,
                    "error": str(e),
                })

        dispatched = sum(1 for r in results if r.get("success"))
        logger.info(f"Monthly tenant SRB dispatch complete: {dispatched}/{len(results)} tenants")
        return {"dispatched": dispatched, "total": len(results), "results": results}

    def _dispatch_for_tenant(
        self,
        tenant_id: str,
        tenant_data: Dict[str, Any],
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        report_data = self._compile_tenant_report(tenant_id, tenant_data, year, month)
        pdf_bytes = TenantPdfGenerator.build_srb_report_pdf(report_data)
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()

        audit_id = f"srb-{tenant_id}-{year}{month:02d}"
        recipients = self._get_sag_recipients(tenant_id, tenant_data)

        record_tenant_dispatch_intent(
            tenant_id=tenant_id,
            audit_id=audit_id,
            dispatched_by_user="system/scheduler",
            reporting_year=year,
            reporting_month=month,
            recipients=recipients,
            pdf_sha256_checksum=sha256,
        )

        operator_name = tenant_data.get("operator_name") or tenant_data.get("name", tenant_id)
        subject = f"Monthly SRB Safety Report — {operator_name} ({year}-{month:02d})"
        html_body = (
            f"<h2>Monthly Safety Review Board Report</h2>"
            f"<p><strong>Operator:</strong> {operator_name}</p>"
            f"<p><strong>Period:</strong> {year}-{month:02d}</p>"
            f"<p>Please find the attached SRB safety report for your review.</p>"
        )
        text_body = (
            f"Monthly Safety Review Board Report\n"
            f"Operator: {operator_name}\n"
            f"Period: {year}-{month:02d}\n\n"
            f"Please find the attached SRB safety report for your review.\n"
        )

        all_sent = True
        for recipient in recipients:
            result = send_regulatory_report(
                to=recipient,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                attachment_bytes=pdf_bytes,
                attachment_filename=f"SRB_Report_{tenant_id}_{year}{month:02d}.pdf",
            )
            if not result.get("sent"):
                all_sent = False
                logger.warning(f"SRB dispatch to {recipient} for tenant {tenant_id} failed")

        status = "delivered" if all_sent else "failed"
        update_tenant_dispatch_status(tenant_id, audit_id, status=status)

        return {
            "tenant_id": tenant_id,
            "audit_id": audit_id,
            "success": all_sent,
            "status": status,
            "pdf_sha256": sha256,
            "recipients": recipients,
        }

    def _compile_tenant_report(
        self,
        tenant_id: str,
        tenant_data: Dict[str, Any],
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        """Gather tenant hazard/report data and build the monthly SRB payload."""
        hazards = self._cross_tenant_hazards(tenant_id)
        reports = self._cross_tenant_reports(tenant_id)
        caps = self._get_tenant_caps(tenant_id)

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
            "active_tier": tenant_data.get("sms_tier", ""),
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
            "insights": [
                f"Monthly review: {len(hazards)} active hazards, {len(open_capas)} open CAPAs."
            ],
            "recommendations": [],
        }

    def _get_active_tenants(self) -> List[Dict[str, Any]]:
        try:
            docs = self.db.collection("tenants").where("status", "==", "active").stream()
            tenants = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                tenants.append(data)
            return tenants
        except Exception as e:
            logger.error(f"Failed to fetch active tenants: {e}")
            return []

    def _get_sag_recipients(self, tenant_id: str, tenant_data: Dict[str, Any]) -> List[str]:
        emails = []
        sm = tenant_data.get("safety_manager") or {}
        if sm.get("email"):
            emails.append(sm["email"])
        for member in tenant_data.get("sag_members") or []:
            if isinstance(member, dict) and member.get("email"):
                emails.append(member["email"])
            elif isinstance(member, str):
                emails.append(member)
        return emails

    def _cross_tenant_hazards(self, tenant_id: str) -> list:
        try:
            docs = self.db.collection(f"tenants/{tenant_id}/hazards").stream()
            return [d.to_dict() for d in docs]
        except Exception:
            return []

    def _cross_tenant_reports(self, tenant_id: str) -> list:
        try:
            docs = self.db.collection(f"tenants/{tenant_id}/reports").stream()
            return [d.to_dict() for d in docs]
        except Exception:
            return []

    def _get_tenant_caps(self, tenant_id: str) -> list:
        try:
            docs = self.db.collection(f"tenants/{tenant_id}/cans").stream()
            return [d.to_dict() for d in docs]
        except Exception:
            return []
