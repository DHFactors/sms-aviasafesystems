# ============================================================================
# FILE: regulator_service.py
# PATH: backend/app/services/regulator_service.py
# PURPOSE: State Regulator model. A State Regulator (e.g. CAAN for Nepal,
#          DGCA for India) is the state civil-aviation authority that
#          oversees a set of operator tenants. Regulators live in the
#          `regulators` collection and each operator tenant carries a
#          `regulator_id` + `country` tag. This service enumerates regulators
#          and their operators, and provides the flat operator-tenant list used
#          to scope cross-tenant aggregations (SMS maturity, state risk).
# ============================================================================

from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import settings
from app.firebase import get_db

REGULATOR_STATUSES = {"demo", "trial", "active", "suspended", "retired", "cancelled", "inactive", "retired/cancelled"}
REGULATOR_STATUS_ALIASES = {"retired_cancelled": "retired", "canceled": "cancelled"}


def _normalize_status(data: Dict[str, Any]) -> str:
    """Normalize the regulator doc to a display status.

    Supports commercial lifecycle: demo, trial, active, suspended, retired, cancelled.
    Falls back to active/inactive for legacy docs.
    """
    raw = str(data.get("status") or "").strip().lower().replace("/", "_").replace("-", "_")
    if raw in ("retired_cancelled", "retired/cancelled"):
        raw = "retired"
    raw = REGULATOR_STATUS_ALIASES.get(raw, raw)
    if raw in REGULATOR_STATUSES:
        return raw
    return "active" if data.get("active", True) else "inactive"


def _parse_regulator_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        from datetime import date
        date.fromisoformat(value.strip())
        return value.strip()
    except Exception as e:
        raise ValueError(f"invalid date '{value}' (expected YYYY-MM-DD)") from e


def _serialize_regulator(doc: Any) -> Dict[str, Any]:
    data = doc.to_dict() or {}
    data["id"] = doc.id
    data["operator_count"] = len(list(data.get("operator_tenant_ids") or []))
    data["status"] = _normalize_status(data)
    return data


def list_regulators() -> List[Dict[str, Any]]:
    """All State Regulators in the system, enriched with operator_count/status."""
    try:
        docs = get_db().collection(settings.FIREBASE_COLLECTION_REGULATORS).get()
        return [_serialize_regulator(d) for d in docs]
    except Exception as e:
        logger.warning(f"Failed to list regulators: {e}")
        return []


def get_regulator(regulator_id: str) -> Optional[Dict[str, Any]]:
    """One regulator document enriched with its operator list."""
    regulator_id = (regulator_id or "").strip()
    try:
        doc = (
            get_db().collection(settings.FIREBASE_COLLECTION_REGULATORS)
            .document(regulator_id).get()
        )
    except Exception as e:
        logger.warning(f"Regulator lookup failed for {regulator_id}: {e}")
        return None
    if not doc.exists:
        return None
    data = _serialize_regulator(doc)
    data["operators"] = list_regulator_operators(regulator_id, data)
    return data


def list_regulator_operators(
    regulator_id: str, regulator: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Operators overseen by a regulator.

    The regulator doc may declare `operator_tenant_ids` explicitly. When it
    does not, operators are derived from the tenants collection (any tenant
    doc tagged with `regulator_id == <id>`).
    """
    reg = regulator or {}
    operator_ids = list(reg.get("operator_tenant_ids") or [])
    try:
        db = get_db()
        tenants = db.collection(settings.FIREBASE_COLLECTION_TENANTS)
        if not operator_ids:
            snaps = tenants.where("regulator_id", "==", regulator_id).get()
            operator_ids = [s.id for s in snaps]

        operators = []
        for tid in operator_ids:
            try:
                snap = tenants.document(tid).get()
            except Exception as e:
                logger.warning(f"Failed to read operator tenant {tid}: {e}")
                continue
            if not snap.exists:
                continue
            td = snap.to_dict() or {}
            operators.append({
                "tenant_id": tid,
                "name": td.get("name") or tid,
                "country": td.get("country"),
                "regulator_id": td.get("regulator_id") or regulator_id,
                "active": td.get("active", True),
            })
        operators.sort(key=lambda o: (o["name"] or "").lower())
        return operators
    except Exception as e:
        logger.warning(f"Failed to list operators for regulator {regulator_id}: {e}")
        return []


def operator_tenant_ids_for_regulator(regulator_id: str) -> List[str]:
    """Flat operator-tenant ids under a regulator, for scoping aggregations."""
    reg = get_regulator(regulator_id)
    if not reg:
        return []
    return [o["tenant_id"] for o in reg.get("operators", [])]


def update_regulator_status(
    regulator_id: str,
    actor: Dict[str, Any],
    status: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    contract_start_date: Optional[str] = None,
    contract_end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Update a regulator's commercial lifecycle status + date range.

    Supports demo, trial, active, suspended, retired, cancelled and aliases
    retired/cancelled. from_date/to_date are commercial aliases for
    contract_start_date/contract_end_date and are stored at top-level plus
    inside contract for backwards compat. Returns updated doc.
    """
    from datetime import datetime, timezone

    regulator_id = (regulator_id or "").strip().lower()
    if not regulator_id:
        raise ValueError("regulator id is required")
    # Allow from_date/to_date as aliases
    if from_date and not contract_start_date:
        contract_start_date = from_date
    if to_date and not contract_end_date:
        contract_end_date = to_date

    # Validate status
    norm_status = None
    if status is not None:
        raw = str(status).strip().lower().replace("/", "_").replace("-", "_")
        if raw in ("retired_cancelled",):
            raw = "retired"
        raw = REGULATOR_STATUS_ALIASES.get(raw, raw)
        if raw not in REGULATOR_STATUSES:
            raise ValueError(f"invalid status '{status}' (allowed: {sorted(REGULATOR_STATUSES)})")
        norm_status = raw

    if contract_start_date:
        _parse_regulator_date(contract_start_date)
    if contract_end_date:
        _parse_regulator_date(contract_end_date)

    db = get_db()
    ref = db.collection(settings.FIREBASE_COLLECTION_REGULATORS).document(regulator_id)
    snap = ref.get()
    if not snap.exists:
        raise ValueError(f"regulator not found: {regulator_id}")
    data = snap.to_dict() or {}
    contract = dict(data.get("contract") or {})
    if contract_start_date:
        contract["start_date"] = contract_start_date.strip()
        contract["from_date"] = contract_start_date.strip()
    if contract_end_date:
        contract["end_date"] = contract_end_date.strip()
        contract["to_date"] = contract_end_date.strip()
    if from_date:
        contract["from_date"] = from_date.strip()
    if to_date:
        contract["to_date"] = to_date.strip()

    now = datetime.now(timezone.utc)
    updates: Dict[str, Any] = {
        "contract": contract,
        "status_updated_at": now,
        "status_updated_by": actor.get("uid"),
        "updated_at": now,
    }
    if norm_status:
        updates["status"] = norm_status
        updates["active"] = norm_status in ("active", "trial", "demo")
    if from_date:
        updates["from_date"] = from_date.strip()
        updates["contract_from_date"] = from_date.strip()
    elif contract_start_date:
        updates["from_date"] = contract_start_date.strip()
    if to_date:
        updates["to_date"] = to_date.strip()
        updates["contract_to_date"] = to_date.strip()
    elif contract_end_date:
        updates["to_date"] = contract_end_date.strip()

    ref.set(updates, merge=True)
    # Return merged view
    merged = dict(data)
    merged.update(updates)
    merged["id"] = regulator_id
    return merged
