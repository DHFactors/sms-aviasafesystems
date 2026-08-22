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

# Department aliases — normalizes the many spellings used across seed data,
# account claims and UI filters onto canonical queue names.
_DEPARTMENT_ALIASES = {
    "part-145": "Part-145", "part 145": "Part-145", "145": "Part-145",
    "maintenance": "Part-145", "maintenance_145": "Part-145",
    "engineering": "Part-145", "amo": "Part-145",
    "engineering & maintenance": "Part-145",
    "engineering and maintenance": "Part-145",
    "maintenance & engineering": "Part-145",
    "maintenance and engineering": "Part-145",
    "camo": "CAMO", "camo / engineering": "CAMO",
    "camo-engineering": "CAMO", "continuing airworthiness": "CAMO",
    "flight operations": "Flight Operations", "flight ops": "Flight Operations",
    "ops": "Flight Operations", "flight_operations": "Flight Operations",
    "line crew": "Flight Operations", "line pilot": "Flight Operations",
    "ground operations": "Ground Operations", "ground ops": "Ground Operations",
    "ground handling": "Ground Operations", "ground_ops": "Ground Operations",
    "cabin services": "Cabin Services", "cabin crew": "Cabin Services",
    "cabin safety": "Cabin Services",
    "safety": "Safety", "safety & quality": "Safety",
    "safety and quality": "Safety", "qa": "Safety", "smd": "Safety",
}


def normalize_department(value: Any) -> str:
    """Canonicalize a department string (e.g. '145' -> 'Part-145')."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    return _DEPARTMENT_ALIASES.get(raw.lower().replace("_", " "), raw)


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
    assigned_to_email: Optional[str] = None,
    user_department: Optional[str] = None,
) -> dict:
    """Assemble the unified register for the authenticated user's scope.

    - CAAN/SUPER_ADMIN see every tenant (unless a department filter is given).
    - Tenant users see their own tenant, optionally filtered by department or
      assignee.

    Assignment matching is flexible — a task matches when ANY of the provided
    dimensions hit:
      * assigned_to_uid == task.assigned_to_uid
      * assigned_to_email == task.assigned_to   (case-insensitive)
      * normalize_department(user_department) ==
        normalize_department(task.department)   (e.g. '145' -> 'Part-145')
    Hazard rows are tenant-wide safety items and skip the assignee filter.
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
        return normalize_department(data.get("department") or fallback) == normalize_department(department)

    assignee_filters = any([assigned_to_uid, assigned_to_email, user_department])

    def _match_assignee(data: dict) -> bool:
        if not assignee_filters:
            return True
        if assigned_to_uid and (data.get("assigned_to_uid") or "") == assigned_to_uid:
            return True
        if assigned_to_email and str(data.get("assigned_to") or "").lower() == assigned_to_email.lower():
            return True
        if user_department and normalize_department(data.get("department")) == normalize_department(user_department):
            return True
        return False

    rows: List[dict] = []

    try:
        for doc in _hazards():
            data = doc.to_dict() or {}
            # Hazards are tenant-wide safety items — department filter applies,
            # but the assignee dimensions do not (most hazards are unassigned).
            if not _match_department(data):
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
                if department and normalize_department(dept) != normalize_department(department):
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
        "filters": {
            "department": department,
            "assigned_to_uid": assigned_to_uid,
            "assigned_to_email": assigned_to_email,
            "user_department": user_department,
        },
    }
