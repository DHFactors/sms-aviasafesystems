from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from loguru import logger

from app.firebase import get_db


def check_overdue_cans() -> Dict[str, Any]:
    """Scan all tenant CAN/CAP collections for items past their due date and
    mark them overdue. Returns a summary of actions taken."""
    now = datetime.now(timezone.utc)
    tenants_snap = get_db().collection("tenants").stream()
    results: Dict[str, Any] = {"tenants_scanned": 0, "cans_overdue": 0, "updated": 0}

    for tenant_doc in tenants_snap:
        tenant_id = tenant_doc.id
        results["tenants_scanned"] += 1
        try:
            caps = (
                get_db()
                .collection(f"tenants/{tenant_id}/cans")
                .where("status", "in", ["Open", "Under Review"])
                .stream()
            )
            for cap_doc in caps:
                cap_data = cap_doc.to_dict() or {}
                due_date = cap_data.get("due_date")
                if due_date is None:
                    continue
                if hasattr(due_date, "timestamp"):
                    due_dt = datetime.fromtimestamp(due_date.timestamp(), tz=timezone.utc)
                elif isinstance(due_date, str):
                    try:
                        due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                elif isinstance(due_date, datetime):
                    due_dt = due_date if due_date.tzinfo else due_date.replace(tzinfo=timezone.utc)
                else:
                    continue

                if due_dt < now and cap_data.get("status") != "Overdue":
                    results["cans_overdue"] += 1
                    get_db().document(f"tenants/{tenant_id}/cans/{cap_doc.id}").update({
                        "status": "Overdue",
                        "overdue_at": now,
                        "updated_at": now,
                    })
                    results["updated"] += 1
                    logger.warning(f"CAN/CAP {cap_doc.id} in tenant {tenant_id} marked overdue")
        except Exception as e:
            logger.error(f"Escalation scan failed for tenant {tenant_id}: {e}")

    logger.info(f"Overdue CAN/CAP check complete: {results}")
    return results
