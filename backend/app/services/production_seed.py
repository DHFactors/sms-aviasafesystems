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
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import settings
from app.db import pg
from app.db.db_models import AuditLog, Regulator, Tenant
from app.db.ids import tenant_uuid
from app.firebase import get_db

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Tenant modules are keyed module1..module4 (M1 SMS maturity, M2 hazard & risk,
# M3 PSOE audit, M4 regulator dashboard). Defaults: M1 on, M2-M4 off.
DEFAULT_TENANT_MODULES = {
    "module1": True,
    "module2": False,
    "module3": False,
    "module4": False,
}


def _regulator_module_flags(reg: Optional[Dict[str, Any]]) -> Dict[str, bool]:
    """Flatten a regulator's module flags (module1..module3 booleans).

    Flags may live in ``module_access`` and/or ``modules`` (either on the row or
    inside the ``data`` bag), keyed as ``module_1`` or ``module1``. Missing
    flags are omitted so the caller's defaults win.
    """
    flags: Dict[str, bool] = {}
    bags = []
    for key in ("module_access", "modules"):
        bag = reg.get(key) if reg else None
        if isinstance(bag, dict):
            bags.append(bag)
    data = (reg or {}).get("data")
    if isinstance(data, dict):
        for key in ("module_access", "modules"):
            bag = data.get(key)
            if isinstance(bag, dict):
                bags.append(bag)
    for i in range(1, 4):
        for bag in bags:
            for key in (f"module_{i}", f"module{i}"):
                if key in bag:
                    flags[f"module{i}"] = bool(bag[key])
                    break
            if f"module{i}" in flags:
                break
    return flags


def _tenant_modules_from_regulator(reg: Optional[Dict[str, Any]]) -> Dict[str, bool]:
    """Tenant module map (module1..module4) resolved for a regulator.

    A SaaS regulator's module flags (M1-M3) are inherited; non-SaaS or missing
    regulators get ``DEFAULT_TENANT_MODULES`` (M4 is never inherited).
    """
    modules = dict(DEFAULT_TENANT_MODULES)
    if not reg:
        return modules
    is_saas = bool(reg.get("is_saas_customer") or (reg.get("data") or {}).get("is_saas_customer"))
    if not is_saas:
        return modules
    flags = _regulator_module_flags(reg)
    # A SaaS regulator is entitled to M1-M3. Regulators created before this
    # behavior carried the all-false server_default (or no flags at all);
    # treat that as "unset" so tenants still inherit M1-M3 rather than defaults,
    # while still honoring an explicit flag set (e.g. an admin module-3 disable).
    unset = not flags or all(flags.get(k) is False for k in ("module1", "module2", "module3"))
    if unset:
        for k in ("module1", "module2", "module3"):
            modules[k] = True
    else:
        modules.update(flags)
    return modules


# ============================================================================
# Audit logging
# ============================================================================

def _audit(action: str, actor: Dict[str, Any], target: str, detail: str,
           result: str = "success") -> None:
    """Persist one audit entry to Postgres (`audit_logs`)."""
    try:
        now = datetime.now(timezone.utc)
        doc = {
            "action": action,
            "user": (actor or {}).get("uid"),
            "target": target,
            "target_type": None,
            "target_id": target,
            "actor": (actor or {}).get("uid"),
            "detail": detail,
            "result": result,
            "timestamp": now.isoformat(),
            "created_at": now,
        }
        pg.insert(AuditLog, doc)
    except Exception as e:
        logger.error(f"Audit log pg write failed ({action}): {e}")


def list_audit_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """Most recent seeding/admin audit entries (newest first)."""
    limit = max(1, min(int(limit or 50), 200))
    try:
        rows = pg.fetch_all(
            AuditLog,
            order_by=AuditLog.created_at.desc(),
            limit=limit,
        )
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


def _json_safe(value: Any) -> Any:
    """Convert date/datetime values to ISO strings for JSONB storage."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _firestore_safe(value: Any) -> Any:
    """Sanitize a doc for the Firestore mirror write.

    Firestore natively accepts ``datetime`` (stored as a Timestamp) but rejects
    plain ``date``; convert those to ISO strings while keeping ``datetime``.
    """
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _firestore_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_firestore_safe(v) for v in value]
    return value


def _firestore_tenant_doc_exists(tid: str) -> bool:
    """True when the tenant's Firestore mirror document exists.

    Fails closed (treats the mirror as existing) when the check itself errors
    so a storage outage keeps the previous duplicate-creation 409 behaviour.
    """
    try:
        return get_db().collection(settings.FIREBASE_COLLECTION_TENANTS).document(tid).get().exists
    except Exception as e:
        logger.warning(f"Tenant Firestore existence check failed ({tid}): {e}")
        return True


def sync_tenant_to_firestore(tid: str, tenant_row: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Write/refresh a tenant's Firestore mirror from its PostgreSQL row.

    Used when a tenant exists in Postgres but its Firestore document was
    removed (e.g. a demo purge) so tenant-scoped pages resolve again. Raises
    ValueError when the Postgres row is missing or the mirror write fails.
    """
    row = tenant_row if tenant_row is not None else pg.fetch_by(Tenant, "slug", tid)
    if row is None:
        raise ValueError(f"tenant does not exist: {tid}")
    safe = _firestore_safe(dict(row))
    try:
        get_db().collection(settings.FIREBASE_COLLECTION_TENANTS).document(tid).set(safe)
    except Exception as e:
        logger.warning(f"Tenant mirror sync failed ({tid}): {e}")
        raise ValueError(f"tenant sync failed: {e}")
    logger.info(f"Tenant {tid} synced to Firestore")
    return safe


def _json_safe_doc(model: type, doc: Dict[str, Any]) -> Dict[str, Any]:
    """Mirror ``pg._split_doc`` routing but stringify date/datetime values
    wherever they land in JSONB (typed JSONB columns or the ``data`` bag).

    Typed ``Date``/``DateTime`` columns keep native values (asyncpg requires
    them); only JSONB-bound values are converted so serialization never fails.
    """
    from sqlalchemy.dialects.postgresql import JSONB

    table = model.__table__
    out: Dict[str, Any] = {}
    extras: Dict[str, Any] = {}
    has_data = "data" in table.columns
    for key, value in doc.items():
        if value is None:
            continue
        if key in table.columns:
            if isinstance(table.columns[key].type, JSONB):
                out[key] = _json_safe(value)
            else:
                out[key] = value
        elif has_data:
            extras[key] = _json_safe(value)
        else:
            extras[key] = value
    if extras and has_data:
        out["data"] = extras
    return out


def create_regulator(data: Dict[str, Any], actor: Dict[str, Any]) -> Dict[str, Any]:
    """Create a State Regulator document. 409 when the id already exists."""
    rid = _validate_id(data.get("id"), "regulator id")
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("regulator name is required")

    if pg.fetch_by(Regulator, "slug", rid) is not None:
        raise ValueError(f"regulator already exists: {rid}")

    now = datetime.now(timezone.utc)
    # Correct mapping per instruction:
    # - regulators.id = generated UUID (auto, not frontend regId)
    # - regulators.slug = frontend regId (e.g., "caan")
    # - regulators.data = regulator metadata
    is_saas_customer = bool(data.get("is_saas_customer", False))
    # SaaS regulators are entitled to M1-M3; honor explicit flags if given.
    raw_modules = data.get("module_access")
    if isinstance(raw_modules, dict) and raw_modules:
        module_access = {
            f"module_{i}": bool(raw_modules.get(f"module_{i}", raw_modules.get(f"module{i}", False)))
            for i in (1, 2, 3)
        }
    else:
        module_access = {
            "module_1": is_saas_customer,
            "module_2": is_saas_customer,
            "module_3": is_saas_customer,
        }
    doc = {
        "slug": rid,
        "name": name,
        "display_name": (data.get("short_name") or "").strip() or rid.upper(),
        "operator_tenant_ids": list(data.get("operator_tenant_ids") or []),
        "is_demo": bool(data.get("is_demo", True)),
        "is_saas_customer": is_saas_customer,
        "module_access": module_access,
        "subscription_start": data.get("subscription_start"),
        "subscription_end": data.get("subscription_end"),
        "data": {
            "type": "state_regulator",
            "short_name": (data.get("short_name") or "").strip() or rid.upper(),
            "country": (data.get("country") or "").strip(),
            "country_name": (data.get("country_name") or "").strip(),
            "domain": (data.get("domain") or "").strip() or None,
            "active": bool(data.get("active", True)),
            "is_demo": bool(data.get("is_demo", True)),
            "is_saas_customer": is_saas_customer,
            "module_access": module_access,
            "subscription_start": data.get("subscription_start"),
            "subscription_end": data.get("subscription_end"),
        },
        "created_at": now,
        "updated_at": now,
    }
    # Clean None values from data
    doc["data"] = {k: v for k, v in doc["data"].items() if v is not None}
    pg.upsert(Regulator, "slug", rid, _json_safe_doc(Regulator, doc))
    try:
        get_db().collection(settings.FIREBASE_COLLECTION_REGULATORS).document(rid).set(_firestore_safe(dict(doc)))
    except Exception as e:
        logger.warning(f"Regulator mirror write failed ({rid}): {e}")

    row = pg.fetch_by(Regulator, "slug", rid)
    if row is not None and row.get("id") is not None:
        doc["id"] = row["id"]

    _audit("REGULATOR_CREATED", actor, rid,
           f"Created State Regulator '{name}' ({data.get('country_name') or data.get('country') or ''})")
    logger.info(f"Regulator {rid} created by {actor.get('uid')}")
    return doc


def create_tenant(data: Dict[str, Any], actor: Dict[str, Any]) -> Dict[str, Any]:
    """Create an operator tenant document. 409 when the id already exists.

    A tenant that exists in PostgreSQL but whose Firestore mirror document was
    removed (e.g. a demo purge) is silently re-synced instead of rejected, so
    tenant-scoped pages resolve again.
    """
    tid = _validate_id(data.get("tenant_id") or data.get("id"), "tenant id")
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("tenant name is required")

    existing = pg.fetch_by(Tenant, "slug", tid)
    if existing is not None:
        if not _firestore_tenant_doc_exists(tid):
            # Postgres row exists but the Firestore mirror is missing — rebuild
            # it so the tenant is visible again (the case the "tenant already
            # exists" 409 used to reject).
            sync_tenant_to_firestore(tid, existing)
            _audit("TENANT_SYNCED", actor, tid,
                   f"Synced existing tenant '{name}' back to Firestore")
            logger.info(f"Tenant {tid} (existing PG row) synced to Firestore by {actor.get('uid')}")
            return existing
        raise ValueError(f"tenant already exists: {tid}")

    regulator_id = (data.get("regulator_id") or "").strip() or None
    if regulator_id:
        _validate_id(regulator_id, "regulator id")

    now = datetime.now(timezone.utc)
    doc = {
        "tenant_id": tid,
        "slug": tid,
        "name": name,
        "icao": (data.get("icao") or "").strip() or None,
        "country": (data.get("country") or "Nepal").strip(),
        "category": (data.get("category") or "CONTRACTED").upper(),
        "status": (data.get("status") or "ACTIVE").upper(),
        "trial_expires_at": data.get("trial_expires_at"),
        "active": bool(data.get("active", True)),
        "is_demo": bool(data.get("is_demo", True)),
        "created_at": now,
        "updated_at": now,
    }
    if regulator_id:
        doc["regulator_id"] = regulator_id
        # Resolve the regulator so module access can be inherited (SaaS only).
        try:
            regulator = pg.fetch_by(Regulator, "slug", regulator_id)
        except Exception as e:
            logger.warning(f"Failed to resolve regulator {regulator_id} for module inheritance: {e}")
            regulator = None
    else:
        regulator = None
    doc["module_access"] = _tenant_modules_from_regulator(regulator)
    # Keep the legacy/typed `modules` field in sync with module_access.
    doc["modules"] = dict(doc["module_access"])
    sm = data.get("safety_manager")
    if isinstance(sm, dict) and sm:
        doc["safety_manager"] = sm
    survey_config = data.get("survey_config")
    if isinstance(survey_config, dict) and survey_config:
        doc["survey_config"] = survey_config
    for field in ("contact_name", "contact_email", "contact_phone", "contact_title"):
        if data.get(field):
            val = str(data.get(field)).strip()
            if val:
                doc[field] = val
    # Also handle nested contact dict for legacy
    contact = data.get("contact")
    if isinstance(contact, dict) and contact:
        for k in ("name", "email", "phone", "title"):
            field = f"contact_{k}"
            if contact.get(k) and field not in doc:
                doc[field] = str(contact.get(k)).strip()

    pg.upsert(Tenant, "slug", tid, _json_safe_doc(Tenant, doc))
    try:
        get_db().collection(settings.FIREBASE_COLLECTION_TENANTS).document(tid).set(_firestore_safe(dict(doc)))
    except Exception as e:
        logger.warning(f"Tenant mirror write failed ({tid}): {e}")

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
        reg = pg.fetch_by(Regulator, "slug", regulator_id)
        if reg is None:
            return
        ops = list(reg.get("operator_tenant_ids") or [])
        if tid not in ops:
            ops.append(tid)
            pg.update(Regulator, "slug", regulator_id, {"operator_tenant_ids": ops})
        try:
            db = get_db()
            reg_ref = db.collection(settings.FIREBASE_COLLECTION_REGULATORS).document(regulator_id)
            reg_ref.set({"operator_tenant_ids": ops}, merge=True)
        except Exception as e:
            logger.warning(f"Failed to mirror regulator link {tid}: {e}")
    except Exception as e:
        logger.warning(f"Failed to link tenant {tid} to regulator {regulator_id}: {e}")


def list_regulators_admin() -> List[Dict[str, Any]]:
    try:
        rows = pg.fetch_all(Regulator)
        for row in rows:
            row.setdefault("id", row.get("slug") or row.get("regulator_id"))
        return rows
    except Exception as e:
        logger.warning(f"Failed to list regulators (admin): {e}")
        return []


def list_tenants_admin() -> List[Dict[str, Any]]:
    try:
        regulator_ids = {
            r.get("slug") for r in pg.fetch_all(Regulator) if r.get("slug")
        }
        tenants = pg.fetch_all(Tenant)
        rows = []
        for td in tenants:
            td = dict(td)
            tid = td.get("slug") or td.get("tenant_id") or td.get("id")
            td["id"] = tid
            if tid in regulator_ids or _is_regulator_doc(td):
                continue
            td["counts"] = {}
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
        for snap in pg.fetch_all(Regulator):
            regs[snap.get("slug") or ""] = snap
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
