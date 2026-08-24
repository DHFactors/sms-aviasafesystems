# ============================================================================
# FILE: master_register.py
# PATH: backend/app/services/master_register.py
# PURPOSE: Unified Master Register view combining hazards, CANs, and CAPs into
#          a single register with common fields (ID, title, type, status, risk
#          level, assigned to, department, dates). Supports department and
#          assignment scoping for responsible-manager views.
#          Optimized: Firestore-level filtering, pagination, cursor support,
#          and removal of N+1 CAP reads via collection_group batch fetch.
# AUTHOR: AviaSAFE Systems
# ============================================================================

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import base64
import json

from loguru import logger

from app.core.config import settings
from app.firebase import get_tenant_collection, get_cross_tenant_collection, get_db

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


def _parse_cursor(cursor: Optional[str]) -> Optional[datetime]:
    """Decode cursor (base64 JSON with last_date or plain ISO string)."""
    if not cursor:
        return None
    # Try base64 JSON first
    try:
        # padded base64
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode()).decode()
        obj = json.loads(decoded)
        iso = obj.get("last_date") if isinstance(obj, dict) else None
        if iso:
            return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        pass
    # Fallback: plain ISO
    try:
        return datetime.fromisoformat(cursor.replace("Z", "+00:00"))
    except Exception:
        return None


def _encode_cursor(last_date_iso: Optional[str]) -> Optional[str]:
    if not last_date_iso:
        return None
    payload = json.dumps({"last_date": last_date_iso})
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _coerce_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    if hasattr(value, "to_datetime"):
        try:
            dt = value.to_datetime()
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def build_master_register(
    user: dict,
    department: Optional[str] = None,
    assigned_to_uid: Optional[str] = None,
    assigned_to_email: Optional[str] = None,
    user_department: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page_size: Optional[int] = None,
    cursor: Optional[str] = None,
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

    Optimization:
      - Firestore-level where() for department/status + order_by + limit
      - Cursor pagination via created_at < cursor
      - Single collection_group fetch for CAPs (removes N+1 per-CAN reads)
    """
    tenant_id = user.get("tenant_id")
    cross_tenant = user.get("role") in settings.CROSS_TENANT_ROLES

    # Pagination bounds
    try:
        ps = int(page_size) if page_size is not None else 50
    except Exception:
        ps = 50
    ps = max(1, min(ps, settings.REPO_MAX_PAGE_SIZE))
    cursor_dt = _parse_cursor(cursor)

    # Normalized department for DB where (if provided)
    norm_dept = normalize_department(department) if department else None
    # For CAP dept fallback
    norm_dept_for_cap = norm_dept

    # Determine per-collection limits: fetch enough to fill page after merge.
    # Hazards + CANs + CAPs merged; allocate ps per type initially, will slice later.
    per_type_limit = max(ps, 25)  # at least 25 to allow merge diversity

    def _build_filtered_query(base, dept_val: Optional[str], status_val: Optional[str], cursor_dt_val: Optional[datetime], order_field: str = "created_at"):
        """Apply department/status where + cursor + order_by + limit. Falls back gracefully."""
        q = base
        try:
            # Department filter at DB level
            if dept_val:
                q = q.where("department", "==", dept_val)
            if status_val:
                q = q.where("status", "==", status_val)
            # Cursor as created_at < cursor for DESC order
            if cursor_dt_val is not None:
                # Need to apply before order_by for Firestore
                q = q.where(order_field, "<", cursor_dt_val)
        except Exception as e:
            logger.warning(f"Master register DB filter build failed (fallback to Python): {e}")
            # Return base without filters if where fails (missing index etc.)
            q = base
            if cursor_dt_val is not None:
                try:
                    q = q.where(order_field, "<", cursor_dt_val)
                except Exception:
                    pass
        try:
            from google.cloud.firestore import Query as FirestoreQuery
            q = q.order_by(order_field, direction=FirestoreQuery.DESCENDING).limit(per_type_limit)
        except Exception as e:
            logger.warning(f"Master register order/limit failed (fallback): {e}")
            try:
                q = q.limit(per_type_limit)
            except Exception:
                pass
        return q

    # We try DB-filtered queries; on failure fall back to full fetch + Python filter
    def _safe_get(query, fallback_getter):
        try:
            return list(query.get())
        except Exception as e:
            # Missing composite index or other query error -> fallback
            logger.warning(f"Master register filtered query failed, falling back to Python filtering: {e}")
            try:
                return list(fallback_getter().get())
            except Exception as e2:
                logger.error(f"Master register fallback fetch failed: {e2}")
                return []

    def _hazard_base():
        if cross_tenant:
            return get_cross_tenant_collection(HAZARD_COLLECTION)
        return get_tenant_collection(tenant_id, HAZARD_COLLECTION)

    def _can_base():
        if cross_tenant:
            return get_cross_tenant_collection(CAN_COLLECTION)
        return get_tenant_collection(tenant_id, CAN_COLLECTION)

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

    def _match_status(data: dict) -> bool:
        if not status:
            return True
        return (data.get("status") or "") == status

    def _match_search(data: dict, fields: List[str]) -> bool:
        if not search:
            return True
        s = search.strip().lower()
        if not s:
            return True
        for f in fields:
            v = str(data.get(f) or "").lower()
            if s in v:
                return True
        return False

    rows: List[dict] = []

    # --- Hazards: Firestore-level filtering ---
    try:
        # Use DB filtering for department/status + limit; assignee/search remain Python
        hazard_query = _build_filtered_query(_hazard_base(), norm_dept, status, cursor_dt, order_field="created_at")
        hazard_docs = _safe_get(hazard_query, lambda: _hazard_base())
        # If query already filtered at DB, we still apply Python checks for safety (search, alias edge)
        for doc in hazard_docs:
            data = doc.to_dict() or {}
            # Hazards skip assignee filter but apply department/status/search
            # Department already DB-filtered, but double-check for alias mismatches
            if not _match_department(data):
                continue
            if not _match_status(data):
                continue
            if not _match_search(data, ["hazard_id", "title", "description"]):
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

    # --- CANs: Firestore-level filtering ---
    can_docs_cache: List[Any] = []
    try:
        # For assignee filtering, try to push assigned_to_uid or assigned_to if single filter
        can_base = _can_base()
        can_query = can_base
        # Apply department/status at DB
        try:
            if norm_dept:
                can_query = can_query.where("department", "==", norm_dept)
            if status:
                can_query = can_query.where("status", "==", status)
            # If only one assignee dimension, push to DB for efficiency; OR case stays Python
            single_assignee = sum(bool(x) for x in [assigned_to_uid, assigned_to_email, user_department]) == 1
            if single_assignee:
                if assigned_to_uid:
                    can_query = can_query.where("assigned_to_uid", "==", assigned_to_uid)
                elif assigned_to_email:
                    can_query = can_query.where("assigned_to", "==", assigned_to_email)
                elif user_department:
                    can_query = can_query.where("department", "==", normalize_department(user_department))
            if cursor_dt is not None:
                # CANs order by issued_at or created_at; use created_at for cursor
                can_query = can_query.where("created_at", "<", cursor_dt)
        except Exception as e:
            logger.warning(f"Master register CAN DB filter build partial failure: {e}")

        try:
            from google.cloud.firestore import Query as FirestoreQuery
            # Prefer issued_at/created_at; fallback to created_at
            can_query = can_query.order_by("created_at", direction=FirestoreQuery.DESCENDING).limit(per_type_limit)
        except Exception as e:
            logger.warning(f"Master register CAN order/limit failed: {e}")
            try:
                can_query = can_query.limit(per_type_limit)
            except Exception:
                pass

        can_docs_cache = _safe_get(can_query, lambda: _can_base())
        for can_doc in can_docs_cache:
            can_data = can_doc.to_dict() or {}
            if not _match_department(can_data):
                continue
            if not _match_assignee(can_data):
                continue
            if not _match_status(can_data):
                continue
            if not _match_search(can_data, ["can_reference", "title"]):
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
    except Exception as e:
        logger.error(f"Master register CAN scan failed: {e}")

    # --- CAPs: SINGLE collection_group batch fetch (removes N+1) ---
    try:
        caps_fetched: List[Any] = []
        # Build a map from can_id -> can_data for quick join
        can_map: Dict[str, Dict[str, Any]] = {}
        for c in can_docs_cache:
            try:
                can_map[c.id] = c.to_dict() or {}
            except Exception:
                continue

        # Attempt collection_group fetch for caps
        cap_limit = per_type_limit
        cap_query = None
        caps_via_group = False
        try:
            db = get_db()
            cap_query = db.collection_group(CAP_SUBCOLLECTION)
            # Tenant isolation via tenant_id field when not cross_tenant
            if not cross_tenant and tenant_id:
                # Caps created after fix store tenant_id; filter on it
                cap_query = cap_query.where("tenant_id", "==", tenant_id)
            if norm_dept_for_cap:
                cap_query = cap_query.where("department", "==", norm_dept_for_cap)
            if status:
                # CAP status filter
                cap_query = cap_query.where("status", "==", status)
            if cursor_dt is not None:
                cap_query = cap_query.where("created_at", "<", cursor_dt)
            from google.cloud.firestore import Query as FirestoreQuery
            cap_query = cap_query.order_by("created_at", direction=FirestoreQuery.DESCENDING).limit(cap_limit)
            caps_fetched = list(cap_query.get())
            caps_via_group = True
            # If group query returned 0 but we have CANs with caps missing tenant_id, fallback may still be needed
            # Check if any caps missing tenant_id by seeing if can_map caps not in result
            # We will supplement fallback only if needed below
        except Exception as e:
            logger.warning(f"Master register CAP collection_group query failed (fallback to per-CAN bounded): {e}")
            cap_query = None

        # If group query succeeded but tenant caps may be legacy without tenant_id, supplement with bounded per-CAN fetch for those CANs not covered
        # For efficiency, if group query returned some results, we use them; for legacy caps we do bounded fallback limited to 5 per CAN up to cap_limit
        cap_docs_by_id: Dict[str, Any] = {}
        for cap in caps_fetched:
            cap_docs_by_id[cap.id] = cap

        # Determine if we need fallback for legacy caps (when not all CAN caps are represented)
        # Only fallback if group query returned fewer than expected and tenant is not cross_tenant
        need_fallback = False
        if not caps_via_group:
            need_fallback = True
        elif not cross_tenant and tenant_id:
            # If tenant has CANs but group returned 0, likely legacy caps without tenant_id
            if can_docs_cache and len(caps_fetched) == 0:
                # Check if any legacy caps exist by sampling one CAN
                need_fallback = True

        if need_fallback:
            # Bounded per-CAN fetch: at most 5 caps per CAN, total cap_limit
            fallback_caps = []
            remaining = cap_limit
            for can_doc in can_docs_cache:
                if remaining <= 0:
                    break
                try:
                    coll = can_doc.reference.collection(CAP_SUBCOLLECTION)
                    # Try order_by+limit if supported (real Firestore), else just get()
                    try:
                        if hasattr(coll, "order_by"):
                            from google.cloud.firestore import Query as _Q
                            coll_q = coll.order_by("created_at", direction=_Q.DESCENDING)
                            if hasattr(coll_q, "limit"):
                                coll_q = coll_q.limit(min(5, remaining))
                            per_can_caps = list(coll_q.get())
                        elif hasattr(coll, "limit"):
                            per_can_caps = list(coll.limit(min(5, remaining)).get())
                        else:
                            per_can_caps = list(coll.get())
                    except Exception:
                        # Final fallback: plain get()
                        try:
                            per_can_caps = list(can_doc.reference.collection(CAP_SUBCOLLECTION).get())
                        except Exception:
                            per_can_caps = []
                    for cap in per_can_caps:
                        if cap.id not in cap_docs_by_id:
                            fallback_caps.append(cap)
                            cap_docs_by_id[cap.id] = cap
                    remaining = cap_limit - len(cap_docs_by_id)
                except Exception:
                    continue
            caps_fetched = list(cap_docs_by_id.values())

        # Now join caps to rows with Python filters (assignee, search, department fallback)
        for cap in caps_fetched:
            cap_data = cap.to_dict() or {}
            # Determine parent CAN for join (if collection_group, parent id not directly known; try can_id field or lookup)
            parent_can_id = cap_data.get("can_id") or cap_data.get("can_reference") or None
            # Try to find parent CAN data via map
            parent_can_data = None
            if parent_can_id and parent_can_id in can_map:
                parent_can_data = can_map[parent_can_id]
            else:
                # For collection_group results, try to infer parent via reference path
                try:
                    # cap.reference.path is like "tenants/t1/can_cap/CANID/caps/CAPID"
                    path = getattr(cap.reference, "path", "") or getattr(cap.reference, "_path", "")
                    # Extract CAN id from path
                    if "/can_cap/" in str(path):
                        parts = str(path).split("/can_cap/")
                        if len(parts) > 1:
                            sub = parts[1].split("/")
                            cand = sub[0]
                            if cand in can_map:
                                parent_can_data = can_map[cand]
                                parent_can_id = cand
                except Exception:
                    pass
                # Fallback: use first CAN's department etc. if single CAN context
                if parent_can_data is None and len(can_map) == 1:
                    parent_can_data = list(can_map.values())[0]

            dept = cap_data.get("department") or (parent_can_data.get("department", "") if parent_can_data else "")
            if department and normalize_department(dept) != normalize_department(department):
                continue
            # CAP search: cap_reference or action_plan
            if search and not _match_search({**cap_data, "can_reference": parent_can_data.get("can_reference") if parent_can_data else ""}, ["cap_reference", "action_plan", "can_reference"]):
                # For CAP, also check action_plan
                s = search.strip().lower()
                if s not in str(cap_data.get("cap_reference") or "").lower() and s not in str(cap_data.get("action_plan") or "").lower():
                    continue
            # CAPs inherit assignment from parent CAN for filtering; if cap itself has assignment, use it else parent
            assignee_source = cap_data if cap_data.get("assigned_to") or cap_data.get("assigned_to_uid") else (parent_can_data or {})
            # For CAP assignee filter, check parent's assignee as well
            cap_assignee_data = {** (parent_can_data or {}), **cap_data}
            if assignee_filters and not _match_assignee(cap_assignee_data):
                # Also check dept alias for CAP
                if not (user_department and normalize_department(dept) == normalize_department(user_department)):
                    continue
            if status and (cap_data.get("status") or "In Progress") != status:
                continue

            # Resolve parent CAN id for detail_url
            detail_can_id = parent_can_id or (cap_data.get("can_id") or "")
            if not detail_can_id:
                # Try map lookup: if we have can_map, pick first matching dept
                detail_can_id = next(iter(can_map.keys()), "")

            rows.append({
                "id": cap.id,
                "reference": cap_data.get("cap_reference") or cap.id,
                "title": cap_data.get("action_plan", ""),
                "type": "CAP",
                "status": cap_data.get("status", "In Progress"),
                "risk_level": None,
                "priority": (parent_can_data.get("priority") if parent_can_data else None),
                "assigned_to": (parent_can_data.get("assigned_to") if parent_can_data else cap_data.get("assigned_to")),
                "assigned_to_uid": (parent_can_data.get("assigned_to_uid") if parent_can_data else cap_data.get("assigned_to_uid")),
                "department": dept,
                "date": _iso(cap_data.get("submitted_at") or cap_data.get("created_at")),
                "target_date": _iso(cap_data.get("target_completion_date")),
                "detail_url": f"/can_cap/can_detail.html?id={detail_can_id}",
            })
    except Exception as e:
        logger.error(f"Master register CAP batch scan failed: {e}")

    def _sort_key(row: dict):
        # Use date string; ISO sorts lexicographically but we parse for safety
        dt = _coerce_dt(row.get("date"))
        return dt or datetime.min.replace(tzinfo=timezone.utc)

    rows.sort(key=_sort_key, reverse=True)

    # Apply Python pagination slice after merge (handles cross-type ordering)
    # If cursor provided, rows already DB-filtered by cursor_dt, but double-check
    if cursor_dt is not None:
        # Ensure rows after cursor (already filtered, but ensure for fallback paths)
        filtered = []
        for r in rows:
            dt = _coerce_dt(r.get("date"))
            if dt is None or dt < cursor_dt:
                filtered.append(r)
        rows = filtered

    # Handle search that wasn't pushed to DB (already done per item, but ensure)
    # Slice to page_size
    paged_rows = rows[:ps]
    has_more = len(rows) > ps

    # Compute next cursor from last item in paged result
    next_cursor = None
    if paged_rows and (len(rows) > ps or len(paged_rows) == ps):
        last = paged_rows[-1]
        last_iso = last.get("date")
        if last_iso:
            next_cursor = _encode_cursor(last_iso)
        # If we have exactly ps items, indicate there may be more; frontend checks has_more
        # For precise has_more, we would need to know if DB has more, but this heuristic suffices
        has_more = len(rows) > ps or len(paged_rows) == ps

    # But to avoid false has_more when exactly ps and no more data, check if total fetched limited
    # If we fetched per_type_limit and paged_rows == ps and rows length == paged_rows length, we may still have more; keep has_more true
    # For now, set has_more = len(rows) >= ps and not all data exhausted (conservative)

    status_counts: Dict[str, int] = {}
    type_counts: Dict[str, int] = {}
    for row in paged_rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        type_counts[row["type"]] = type_counts.get(row["type"], 0) + 1

    return {
        "rows": paged_rows,
        "total": len(paged_rows),
        "total_unpaged": len(rows),
        "by_status": status_counts,
        "by_type": type_counts,
        "filters": {
            "department": department,
            "assigned_to_uid": assigned_to_uid,
            "assigned_to_email": assigned_to_email,
            "user_department": user_department,
            "status": status,
            "search": search,
        },
        "pagination": {
            "page_size": ps,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "cursor": cursor,
        },
    }
