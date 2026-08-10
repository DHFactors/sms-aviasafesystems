# ============================================================================
# FILE: regulator_service.py
# PATH: backend/app/services/regulator_service.py
# PURPOSE: State Regulator model. A State Regulator (e.g. CAAN for Nepal,
#          DGCA for India) is the national civil-aviation authority that
#          oversees a set of operator tenants. Regulators live in the
#          `regulators` collection and each operator tenant carries a
#          `regulator_id` + `country` tag. This service enumerates regulators
#          and their operators, and provides the flat operator-tenant list used
#          to scope cross-tenant aggregations (SMS maturity, national risk).
# ============================================================================

from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import settings
from app.firebase import get_db


def _serialize_regulator(doc: Any) -> Dict[str, Any]:
    data = doc.to_dict() or {}
    data["id"] = doc.id
    return data


def list_regulators() -> List[Dict[str, Any]]:
    """All State Regulators in the system."""
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
