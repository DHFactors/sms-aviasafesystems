# ============================================================================
# FILE: escalation_service.py
# PATH: backend/app/services/escalation_service.py
# PURPOSE: Automated overdue/escalation detection for CANs and CAPs.
#
#          The daily task (POST /api/v1/admin/tasks/check-overdue) runs this
#          service across every tenant:
#            - CAN with target_completion_date passed and status != Closed
#              -> status "Escalated"
#            - CAP with target_completion_date passed and status not terminal
#              -> status "Overdue"
#          Every change is persisted and written to the audit_logs collection.
# AUTHOR: AviaSAFE Systems
# ============================================================================

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.db import pg
from app.db.db_models import Can, Cap, Tenant
from app.db.ids import tenant_uuid
from app.services.audit_service import log_audit

CAN_COLLECTION = "can_cap"
CAP_SUBCOLLECTION = "caps"

# Statuses that are considered finished and must never be escalated/overdue'd.
CAN_TERMINAL_STATUSES = {"Closed"}
CAP_TERMINAL_STATUSES = {"Completed", "Overdue"}


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return value


def check_tenant_overdue(tenant_id: str) -> Dict[str, Any]:
    """Scan a single tenant's CANs + CAPs and escalate anything past due.

    Returns a summary of what changed:
      {"cans_escalated": n, "caps_overdue": n, "escalated_cans": [...], "overdue_caps": [...]}
    """
    now = datetime.now(timezone.utc)
    tid_uuid = tenant_uuid(tenant_id)
    cans = pg.fetch_all(Can, where=[Can.tenant_id == tid_uuid])
    caps_by_can: Dict[str, List[Dict[str, Any]]] = {}
    for cap in pg.fetch_all(Cap, where=[Cap.tenant_id == tid_uuid]):
        caps_by_can.setdefault(str(cap.get("can_id") or cap.get("id") or ""), []).append(cap)

    escalated_cans: List[str] = []
    overdue_caps: List[str] = []

    for can_data in cans:
        can_id = str(can_data.get("id") or "")
        can_ref = can_data.get("can_reference") or can_id
        status = can_data.get("status", "Open")
        target = _parse_dt(can_data.get("target_completion_date"))

        if status not in CAN_TERMINAL_STATUSES and target is not None and target < now:
            if status != "Escalated":
                try:
                    pg.update(Can, "id", can_id, {"status": "Escalated", "updated_at": now})
                    log_audit(
                        action="CAN_ESCALATED",
                        user="system",
                        tenant_id=tenant_id,
                        target_type="can",
                        target_id=can_id,
                        metadata={
                            "can_reference": can_ref,
                            "target_completion_date": target.isoformat() if hasattr(target, "isoformat") else str(target),
                        },
                    )
                    logger.info(f"CAN {can_ref} escalated for tenant {tenant_id}")
                except Exception as e:
                    logger.error(f"Failed to escalate CAN {can_ref} ({tenant_id}): {e}")
                    continue
            escalated_cans.append(can_ref)

        for cap in caps_by_can.get(can_id, []):
            cap_id = str(cap.get("id") or "")
            cap_ref = cap.get("cap_reference") or cap_id
            cap_status = cap.get("status", "In Progress")
            cap_target = _parse_dt(cap.get("target_completion_date"))

            if cap_status not in CAP_TERMINAL_STATUSES and cap_target is not None and cap_target < now:
                if cap_status != "Overdue":
                    try:
                        pg.update(Cap, "id", cap_id, {"status": "Overdue", "updated_at": now})
                        log_audit(
                            action="CAP_OVERDUE",
                            user="system",
                            tenant_id=tenant_id,
                            target_type="cap",
                            target_id=cap_id,
                            metadata={
                                "cap_reference": cap_ref,
                                "can_reference": can_ref,
                                "target_completion_date": cap_target.isoformat() if hasattr(cap_target, "isoformat") else str(cap_target),
                            },
                        )
                        logger.info(f"CAP {cap_ref} overdue for tenant {tenant_id}")
                    except Exception as e:
                        logger.error(f"Failed to mark CAP {cap_ref} overdue ({tenant_id}): {e}")
                        continue
                overdue_caps.append(cap_ref)

    return {
        "tenant_id": tenant_id,
        "cans_escalated": len(escalated_cans),
        "caps_overdue": len(overdue_caps),
        "escalated_cans": escalated_cans,
        "overdue_caps": overdue_caps,
    }


def check_all_overdue(tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """Run the overdue scan across all tenants (or one tenant when given)."""
    now = datetime.now(timezone.utc)
    results = []

    if tenant_id:
        results.append(check_tenant_overdue(tenant_id))
    else:
        tenants = pg.fetch_all(Tenant)
        for tenant in tenants:
            slug = tenant.get("slug") or tenant.get("id")
            if not slug:
                continue
            try:
                results.append(check_tenant_overdue(slug))
            except Exception as e:
                logger.error(f"Overdue scan failed for tenant {slug}: {e}")

    total_cans = sum(r["cans_escalated"] for r in results)
    total_caps = sum(r["caps_overdue"] for r in results)

    log_audit(
        action="OVERDUE_CHECK_RUN",
        user="system",
        tenant_id=tenant_id,
        target_type="system",
        target_id="check-overdue",
        metadata={
            "tenants_processed": len(results),
            "cans_escalated": total_cans,
            "caps_overdue": total_caps,
            "run_at": now.isoformat(),
        },
    )

    return {
        "status": "success",
        "run_at": now.isoformat(),
        "tenants_processed": len(results),
        "cans_escalated": total_cans,
        "caps_overdue": total_caps,
        "details": results,
    }
