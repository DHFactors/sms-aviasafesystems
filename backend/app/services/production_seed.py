# ============================================================================
# FILE: production_seed.py
# PATH: backend/app/services/production_seed.py
# PURPOSE: Super-Admin web "Production Setup" panel backend. Creates State
#          Regulator and operator tenant documents (assigning each tenant its
#          regulator), supports individual + bulk tenant import, and records
#          every action to the `audit_logs` collection.
#
#          Tenants are created at Step 2 for both demo and production; there is
#          no hardcoded operator list. Operational dummy data (VSR/MOR/CAN/CAP/
#          Survey) is seeded separately by the Step-5 Dummy Data tool into
#          PostgreSQL (is_demo=true); this module manages only regulator/tenant
#          identity metadata in Firestore.
# ============================================================================

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import settings
from app.db.ids import tenant_uuid
from app.firebase import get_db

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


# ============================================================================
# Audit logging
# ============================================================================

def _audit(action: str, actor: Dict[str, Any], target: str, detail: str,
           result: str = "success") -> None:
    """Persist one audit entry under the top-level `audit_logs` collection."""
    try:
        now = datetime.now(timezone.utc)
        db = get_db()
        db.collection(settings.FIREBASE_COLLECTION_AUDIT_LOGS).add({
            "action": action,
            "actor": {
                "uid": actor.get("uid"),
                "email": actor.get("email"),
            },
            "target": target,
            "detail": detail,
            "result": result,
            "timestamp": now.isoformat(),
            "created_at": now,
        })
    except Exception as e:
        logger.error(f"Audit log write failed ({action}): {e}")


def list_audit_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """Most recent seeding/admin audit entries (newest first)."""
    limit = max(1, min(int(limit or 50), 200))
    try:
        docs = (
            get_db().collection(settings.FIREBASE_COLLECTION_AUDIT_LOGS)
            .order_by("timestamp", direction="DESCENDING").limit(limit).get()
        )
        rows = []
        for d in docs:
            data = d.to_dict() or {}
            data["id"] = d.id
            rows.append(data)
        return rows
    except Exception as e:
        logger.warning(f"Failed to list audit logs: {e}")
        return []


# ============================================================================
# Validation + creation
# ============================================================================

def _validate_id(value: str, label: str = "id") -> str:
    value = (value or "").strip()
    if not value or not ID_RE.match(value):
        raise ValueError(f"{label} must be lowercase letters/numbers/hyphens (e.g. sita-air)")
    return value


def create_regulator(data: Dict[str, Any], actor: Dict[str, Any]) -> Dict[str, Any]:
    """Create a State Regulator document. 409 when the id already exists."""
    rid = _validate_id(data.get("id"), "regulator id")
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("regulator name is required")

    db = get_db()
    if db.collection(settings.FIREBASE_COLLECTION_REGULATORS).document(rid).get().exists:
        raise ValueError(f"regulator already exists: {rid}")

    now = datetime.now(timezone.utc)
    doc = {
        "id": rid,
        "type": "state_regulator",
        "name": name,
        "short_name": (data.get("short_name") or "").strip() or rid.upper(),
        "country": (data.get("country") or "").strip(),
        "country_name": (data.get("country_name") or "").strip(),
        "domain": (data.get("domain") or "").strip() or None,
        "operator_tenant_ids": list(data.get("operator_tenant_ids") or []),
        "active": bool(data.get("active", True)),
        "created_at": now,
        "updated_at": now,
    }
    db.collection(settings.FIREBASE_COLLECTION_REGULATORS).document(rid).set(doc)

    _audit("REGULATOR_CREATED", actor, rid,
           f"Created State Regulator '{name}' ({data.get('country_name') or data.get('country') or ''})")
    logger.info(f"Regulator {rid} created by {actor.get('uid')}")
    return doc


def create_tenant(data: Dict[str, Any], actor: Dict[str, Any]) -> Dict[str, Any]:
    """Create an operator tenant document. 409 when the id already exists."""
    tid = _validate_id(data.get("tenant_id") or data.get("id"), "tenant id")
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("tenant name is required")

    db = get_db()
    if db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tid).get().exists:
        raise ValueError(f"tenant already exists: {tid}")

    regulator_id = (data.get("regulator_id") or "").strip() or None
    if regulator_id:
        _validate_id(regulator_id, "regulator id")

    now = datetime.now(timezone.utc)
    doc = {
        "tenant_id": tid,
        "name": name,
        "icao": (data.get("icao") or "").strip(),
        "country": (data.get("country") or "Nepal").strip(),
        "category": (data.get("category") or "CONTRACTED").upper(),
        "status": (data.get("status") or "ACTIVE").upper(),
        "trial_expires_at": data.get("trial_expires_at"),
        "active": bool(data.get("active", True)),
        "created_at": now,
        "updated_at": now,
    }
    if regulator_id:
        doc["regulator_id"] = regulator_id
    sm = data.get("safety_manager")
    if isinstance(sm, dict) and sm:
        doc["safety_manager"] = sm
    survey_config = data.get("survey_config")
    if isinstance(survey_config, dict) and survey_config:
        doc["survey_config"] = survey_config

    db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tid).set(doc)

    if regulator_id:
        # Keep the regulator link bidirectional: append this tenant to the
        # regulator's operator_tenant_ids so downstream tools (production-setup
        # tables, seeders, cross-tenant aggregation) can resolve operators from
        # the regulator alone.
        _link_tenant_to_regulator(tid, regulator_id)

    _audit("TENANT_CREATED", actor, tid,
           f"Created operator tenant '{name}' (regulator={regulator_id or 'none'})")
    logger.info(f"Tenant {tid} created by {actor.get('uid')}")
    return doc


def bulk_create_tenants(records: List[Dict[str, Any]], actor: Dict[str, Any]) -> Dict[str, Any]:
    """Create many tenants from a parsed list; returns per-record results."""
    results = []
    for rec in records:
        try:
            doc = create_tenant(rec, actor)
            results.append({"tenant_id": doc["tenant_id"], "status": "ok"})
        except ValueError as e:
            results.append({"tenant_id": rec.get("tenant_id") or rec.get("id"), "status": "error", "detail": str(e)})
        except Exception as e:
            results.append({"tenant_id": rec.get("tenant_id") or rec.get("id"), "status": "error", "detail": str(e)})

    ok = sum(1 for r in results if r["status"] == "ok")
    _audit("TENANTS_BULK_IMPORT", actor, f"{ok}/{len(results)}",
           f"Bulk import created {ok} of {len(results)} tenants")
    return {"total": len(results), "ok": ok, "results": results}


# ============================================================================
# Admin lists
# ============================================================================

# State regulators that legacy demo seeding also wrote into the tenants
# collection (e.g. tenants/demostate). These must never surface as operators.
_REGULATOR_TYPE_MARKERS = {"state_regulator", "STATE_REGULATOR"}


def _is_regulator_doc(data: Dict[str, Any]) -> bool:
    """True when a tenants-collection doc is really a State Regulator record."""
    raw_type = str(data.get("type") or "").strip()
    if raw_type and raw_type in _REGULATOR_TYPE_MARKERS:
        return True
    raw_name = str(data.get("name") or "").strip().lower()
    return bool(raw_name) and raw_name.endswith("state regulator")


def _link_tenant_to_regulator(tid: str, regulator_id: str) -> None:
    """Idempotently add `tid` to the regulator's operator_tenant_ids."""
    try:
        db = get_db()
        reg_ref = db.collection(settings.FIREBASE_COLLECTION_REGULATORS).document(regulator_id)
        reg_doc = reg_ref.get()
        if not reg_doc.exists:
            return
        ops = list((reg_doc.to_dict() or {}).get("operator_tenant_ids") or [])
        if tid not in ops:
            ops.append(tid)
            reg_ref.set({"operator_tenant_ids": ops}, merge=True)
    except Exception as e:
        logger.warning(f"Failed to link tenant {tid} to regulator {regulator_id}: {e}")


def list_regulators_admin() -> List[Dict[str, Any]]:
    try:
        docs = get_db().collection(settings.FIREBASE_COLLECTION_REGULATORS).get()
        return [dict(d.to_dict() or {}, id=d.id) for d in docs]
    except Exception as e:
        logger.warning(f"Failed to list regulators (admin): {e}")
        return []


def list_tenants_admin() -> List[Dict[str, Any]]:
    try:
        db = get_db()
        # Operators overseen by a State Regulator (regulators collection). Any
        # tenants-collection doc that is actually a regulator (legacy demo seed
        # writes, e.g. tenants/demostate) must be excluded from operator lists.
        regulator_ids = {
            snap.id for snap in db.collection(settings.FIREBASE_COLLECTION_REGULATORS).get()
        }
        tenants = db.collection(settings.FIREBASE_COLLECTION_TENANTS).get()
        rows = []
        for t in tenants:
            td = dict(t.to_dict() or {})
            td["id"] = t.id
            if t.id in regulator_ids or _is_regulator_doc(td):
                continue
            td["counts"] = {}
            for sub in ("surveys", "hazards", "reports", "can_cap"):
                try:
                    td["counts"][sub if sub != "can_cap" else "cans"] = len(list(t.reference.collection(sub).limit(500).get()))
                except Exception:
                    td["counts"]["cans" if sub == "can_cap" else sub] = 0
            rows.append(td)
        rows.sort(key=lambda r: (r.get("name") or r.get("id") or "").lower())
        return rows
    except Exception as e:
        logger.warning(f"Failed to list tenants (admin): {e}")
        return []


async def _postgres_tenant_counts(slugs: List[str]) -> Dict[str, Dict[str, int]]:
    """Per-tenant operational counts from PostgreSQL by slug.

    Tenant documents live in Firestore (by slug) while hazards/reports/cans/
    caps/surveys rows live in Supabase keyed by a deterministic
    ``uuid5('tenant', slug)``. Returns ``{slug: {surveys, hazards, reports,
    cans, caps}}``. Falls back to empty counts when DATABASE_URL is unset or
    the read fails (keep the Firestore-only path working).
    """
    slugs = [s for s in (slugs or []) if s]
    if not slugs:
        return {}
    try:
        from sqlalchemy import text
        from app.db.session import get_engine
        engine = get_engine()
    except Exception as e:
        logger.warning(f"PostgreSQL unavailable for tenant counts: {e}")
        return {}

    by_uuid = {tenant_uuid(s): s for s in slugs}
    counts = {s: {"surveys": 0, "hazards": 0, "reports": 0, "cans": 0, "caps": 0} for s in slugs}
    try:
        async with engine.connect() as conn:
            for label in ("hazards", "reports", "cans", "caps", "surveys"):
                result = await conn.execute(
                    text(
                        f"SELECT tenant_id, count(*) AS c FROM {label} "
                        "WHERE tenant_id = ANY(:ids) GROUP BY tenant_id"
                    ),
                    {"ids": list(by_uuid.keys())},
                )
                for row in result:
                    slug = by_uuid.get(str(row.tenant_id))
                    if slug:
                        counts[slug][label] = row.c
        return counts
    except Exception as e:
        logger.warning(f"Failed to read PostgreSQL tenant counts: {e}")
        return {}


async def list_tenants_admin_pg() -> List[Dict[str, Any]]:
    """List operator tenants enriched for the Super Admin dashboard.

    Merges Firestore tenant metadata (country, regulator_id, status, contract,
    payment) with PostgreSQL operational counts and resolves regulator name +
    country from the `regulators` collection. Falls back to Firestore
    subcollection counts when PostgreSQL is not configured.
    """
    rows = list_tenants_admin()
    pg_counts = await _postgres_tenant_counts([r.get("id") for r in rows])

    regs = {}
    try:
        db = get_db()
        for snap in db.collection(settings.FIREBASE_COLLECTION_REGULATORS).stream():
            regs[snap.id] = snap.to_dict() or {}
    except Exception as e:
        logger.warning(f"Failed to list regulators for tenant enrichment: {e}")

    for r in rows:
        slug = r.get("id")
        if slug and slug in pg_counts:
            r["counts"] = pg_counts[slug]
        rid = r.get("regulator_id")
        reg = regs.get(rid) if rid else None
        r["regulator_name"] = (reg or {}).get("name") if reg else None
        r["regulator_country"] = (
            (reg or {}).get("country_name") or (reg or {}).get("country")
        ) if reg else None
        r["is_demo"] = bool(r.get("is_demo") or r.get("is_beta_sandbox"))
    rows.sort(key=lambda r: (r.get("name") or r.get("id") or "").lower())
    return rows
