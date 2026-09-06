from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from loguru import logger

from app.db import pg
from app.db.db_models import Can, Tenant
from app.db.ids import tenant_uuid
from app.db.isolation import demo_scope


def check_overdue_cans() -> Dict[str, Any]:
    """Scan all tenant CAN/CAP collections for items past their due date and
    mark them overdue. Returns a summary of actions taken."""
    now = datetime.now(timezone.utc)
    results: Dict[str, Any] = {"tenants_scanned": 0, "cans_overdue": 0, "updated": 0}

    try:
        tenants = pg.fetch_all(Tenant)
    except Exception as e:
        logger.error(f"Escalation scan failed to list tenants: {e}")
        return results

    for tenant_row in tenants:
        slug = tenant_row.get("slug") or ""
        if not slug:
            continue
        tenant_id = slug
        results["tenants_scanned"] += 1
        try:
            tid = tenant_uuid(tenant_id)
            cans = pg.fetch_all(
                Can,
                where=[
                    Can.tenant_id == tid,
                    Can.is_demo == demo_scope(),
                ],
            )
            for cap_data in cans:
                cap_data = dict(cap_data)
                if (cap_data.get("status") or "") not in ("Open", "Under Review"):
                    continue
                # Firestore used 'due_date'; PG model uses target_completion_date + data bag fallback
                due_date = cap_data.get("due_date") or cap_data.get("target_completion_date") or cap_data.get("dueDate")
                if due_date is None:
                    continue
                if hasattr(due_date, "timestamp"):
                    try:
                        due_dt = datetime.fromtimestamp(due_date.timestamp(), tz=timezone.utc)
                    except Exception:
                        continue
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
                    try:
                        pg.update(
                            Can,
                            "id",
                            str(cap_data.get("id") or ""),
                            {
                                "status": "Overdue",
                                "overdue_at": now,
                                "updated_at": now,
                            },
                        )
                        results["updated"] += 1
                        logger.warning(f"CAN/CAP {cap_data.get('id')} in tenant {tenant_id} marked overdue")
                    except Exception as ue:
                        logger.error(f"Failed to mark overdue for {cap_data.get('id')}: {ue}")
        except Exception as e:
            logger.error(f"Escalation scan failed for tenant {tenant_id}: {e}")

    logger.info(f"Overdue CAN/CAP check complete: {results}")
    return results
