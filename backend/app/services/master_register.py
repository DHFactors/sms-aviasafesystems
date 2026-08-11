# ============================================================================
# FILE: master_register.py
# PATH: backend/app/services/master_register.py
# PURPOSE: Unified Master Register view combining hazards, CANs, and CAPs into
#          a single register with common fields (ID, title, type, status, risk
#          level, assigned to, department, dates). Supports department and
#          assignment scoping for responsible-manager views.
# AUTHOR: AviaSAFE Systems
# ============================================================================

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import settings
from app.firebase import get_tenant_collection, get_cross_tenant_collection

HAZARD_COLLECTION = "hazards"
CAN_COLLECTION = "can_cap"
CAP_SUBCOLLECTION = "caps"


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def build_master_register(
    user: dict,
    department: Optional[str] = None,
    assigned_to_uid: Optional[str] = None,
) -> dict:
    """Assemble the unified register for the authenticated user's scope.

    - CAAN/SUPER_ADMIN see every tenant (unless a department filter is given).
    - Tenant users see their own tenant, optionally filtered by department or
      the assignee uid.
    """
    tenant_id = user.get("tenant_id")
    cross_tenant = user.get("role") in settings.CROSS_TENANT_ROLES

    def _hazards():
        if cross_tenant:
            return get_cross_tenant_collection(HAZARD_COLLECTION).get()
        return get_tenant_collection(tenant_id, HAZARD_COLLECTION).get()

    def _cans():
        if cross_tenant:
            return get_cross_tenant_collection(CAN_COLLECTION).get()
        return get_tenant_collection(tenant_id, CAN_COLLECTION).get()

    def _match_department(data: dict, fallback: str = "") -> bool:
        if not department:
            return True
        return (data.get("department") or fallback or "") == department

    def _match_assignee(data: dict) -> bool:
        if not assigned_to_uid:
            return True
        return (data.get("assigned_to_uid") or "") == assigned_to_uid

    rows: List[dict] = []

    try:
        for doc in _hazards():
            data = doc.to_dict() or {}
            if not _match_department(data):
                continue
            if not _match_assignee(data):
                continue
            rows.append({
                "id": doc.id,
                "reference": data.get("hazard_id") or doc.id,
                "title": data.get("title", ""),
                "type": "Hazard",
                "status": data.get("status", "Open"),
                "risk_level": data.get("risk_level"),
                "priority": data.get("priority"),
                "assigned_to": data.get("assigned_to"),
                "assigned_to_uid": data.get("assigned_to_uid"),
                "department": data.get("department", ""),
                "date": _iso(data.get("created_at")),
                "target_date": _iso(data.get("follow_up_date")),
                "detail_url": f"/hazards/detail.html?id={doc.id}",
            })
    except Exception as e:
        logger.error(f"Master register hazard scan failed: {e}")

    try:
        for can_doc in _cans():
            can_data = can_doc.to_dict() or {}
            if not _match_department(can_data):
                continue
            if not _match_assignee(can_data):
                continue
            rows.append({
                "id": can_doc.id,
                "reference": can_data.get("can_reference") or can_doc.id,
                "title": can_data.get("title", ""),
                "type": "CAN",
                "status": can_data.get("status", "Open"),
                "risk_level": None,
                "priority": can_data.get("priority"),
                "assigned_to": can_data.get("assigned_to"),
                "assigned_to_uid": can_data.get("assigned_to_uid"),
                "department": can_data.get("department", ""),
                "date": _iso(can_data.get("issued_at") or can_data.get("created_at")),
                "target_date": _iso(can_data.get("target_completion_date")),
                "detail_url": f"/can_cap/can_detail.html?id={can_doc.id}",
            })
            try:
                caps = can_doc.reference.collection(CAP_SUBCOLLECTION).get()
            except Exception:
                caps = []
            for cap in caps:
                cap_data = cap.to_dict() or {}
                dept = cap_data.get("department") or can_data.get("department", "")
                if department and dept != department:
                    continue
                rows.append({
                    "id": cap.id,
                    "reference": cap_data.get("cap_reference") or cap.id,
                    "title": cap_data.get("action_plan", ""),
                    "type": "CAP",
                    "status": cap_data.get("status", "In Progress"),
                    "risk_level": None,
                    "priority": can_data.get("priority"),
                    "assigned_to": can_data.get("assigned_to"),
                    "assigned_to_uid": can_data.get("assigned_to_uid"),
                    "department": dept,
                    "date": _iso(cap_data.get("submitted_at") or cap_data.get("created_at")),
                    "target_date": _iso(cap_data.get("target_completion_date")),
                    "detail_url": f"/can_cap/can_detail.html?id={can_doc.id}",
                })
    except Exception as e:
        logger.error(f"Master register CAN/CAP scan failed: {e}")

    def _sort_key(row: dict):
        return row.get("date") or ""

    rows.sort(key=_sort_key, reverse=True)

    status_counts: Dict[str, int] = {}
    type_counts: Dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        type_counts[row["type"]] = type_counts.get(row["type"], 0) + 1

    return {
        "rows": rows,
        "total": len(rows),
        "by_status": status_counts,
        "by_type": type_counts,
        "filters": {"department": department, "assigned_to_uid": assigned_to_uid},
    }
