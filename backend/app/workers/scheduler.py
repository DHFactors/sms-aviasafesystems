from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.firebase import get_db
from app.repositories.audit_repo import record_dispatch_intent, update_dispatch_status
from app.services.dlq_service import DlqService
from app.services.email_service import send_regulatory_report
from app.services.pdf_generator import CaanPdfGenerator
from app.services.state_risk_service import StateRiskService


class ScheduledReportWorker:
    """Background worker that compiles CAAN SSP oversight reports and
    dispatches them to regulator recipients on a weekly schedule."""

    def __init__(self):
        self.db = get_db()

    def run_weekly_ssp_dispatch(self) -> Dict[str, Any]:
        """Main entry point invoked by APScheduler or Cloud Scheduler.
        Iterates through registered authorities, compiles aggregate reports,
        generates PDFs, creates audit log entries, and dispatches emails."""
        now = datetime.now(timezone.utc)
        year = now.year
        quarter = (now.month - 1) // 3 + 1
        results: List[Dict[str, Any]] = []

        authorities = self._get_regulator_authorities()
        if not authorities:
            logger.warning("No regulator authorities found for weekly SSP dispatch")
            return {"dispatched": 0, "results": []}

        for authority in authorities:
            regulator_id = authority.get("id", "")
            recipients = authority.get("notification_emails", [])
            if not recipients:
                logger.warning(f"No recipients for authority {regulator_id}, skipping")
                continue

            try:
                result = self._dispatch_for_authority(
                    regulator_id=regulator_id,
                    recipients=recipients,
                    year=year,
                    quarter=quarter,
                    user="system/scheduler",
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Weekly SSP dispatch failed for {regulator_id}: {e}")
                results.append({
                    "regulator_id": regulator_id,
                    "success": False,
                    "error": str(e),
                })

        dispatched = sum(1 for r in results if r.get("success"))
        logger.info(f"Weekly SSP dispatch complete: {dispatched}/{len(results)} authorities")
        return {"dispatched": dispatched, "total": len(results), "results": results}

    def _dispatch_for_authority(
        self,
        regulator_id: str,
        recipients: List[str],
        year: int,
        quarter: int,
        user: str,
    ) -> Dict[str, Any]:
        state_svc = StateRiskService(user={"uid": user, "role": "CAAN_SMD"})
        agg = state_svc.aggregate_state_risk(year, quarter, regulator_id=regulator_id)

        report_data = {
            "reporting_year": year,
            "reporting_quarter": quarter,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "regulator_id": regulator_id,
            "total_operators": len(set(
                r.get("tenant_id") for r in agg.get("risks", [])
                for r in (r.get("contributing_tenants") or [])
            )),
            "total_hazards": sum(r.get("count", 0) for r in agg.get("risks", [])),
            "hrc_distribution": agg.get("risks", []),
            "operator_summaries": [],
            "insights": [
                f"State risk assessment for {year} Q{quarter} covers "
                f"{len(agg.get('risks', []))} ICAO risk categories."
            ],
            "recommendations": [],
        }

        pdf_bytes = CaanPdfGenerator.build_ssp_report_pdf(report_data)
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()

        audit_id = f"audit-{regulator_id}-{year}Q{quarter}"
        record_dispatch_intent(
            audit_id=audit_id,
            regulator_id=regulator_id,
            dispatched_by_user=user,
            reporting_year=year,
            reporting_quarter=quarter,
            recipients=recipients,
            pdf_sha256_checksum=sha256,
        )

        period = f"{year} Q{quarter}"
        subject = f"CAAN SSP Oversight Report — {period}"
        html_body = (
            f"<h2>CAAN State Safety Programme Oversight Report</h2>"
            f"<p>Reporting Period: {period}</p>"
            f"<p>Please find the attached SSP oversight report for your review.</p>"
            f"<p>This report was generated automatically by the AviaSAFE SMS Platform.</p>"
        )
        text_body = (
            f"CAAN State Safety Programme Oversight Report\n"
            f"Reporting Period: {period}\n\n"
            f"Please find the attached SSP oversight report for your review.\n"
        )

        all_sent = True
        for recipient in recipients:
            result = send_regulatory_report(
                to=recipient,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                attachment_bytes=pdf_bytes,
                attachment_filename=f"CAAN_SSP_Report_{year}Q{quarter}.pdf",
            )
            if not result.get("sent"):
                all_sent = False
                logger.warning(f"Dispatch to {recipient} failed: {result.get('error')}")

        status = "delivered" if all_sent else "failed"
        update_dispatch_status(audit_id, status=status)

        return {
            "regulator_id": regulator_id,
            "audit_id": audit_id,
            "success": all_sent,
            "status": status,
            "pdf_sha256": sha256,
            "recipients": recipients,
        }

    def _get_regulator_authorities(self) -> List[Dict[str, Any]]:
        try:
            docs = self.db.collection("regulators").stream()
            authorities = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                authorities.append(data)
            return authorities
        except Exception as e:
            logger.error(f"Failed to fetch regulator authorities: {e}")
            return []
