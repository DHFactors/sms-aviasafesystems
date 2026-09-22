# ============================================================================
# FILE: hazard_enrichment_service.py
# PATH: backend/app/services/hazard_enrichment_service.py
# PURPOSE: Module B §27 — enrichment ADDS to a hazard, never replaces it.
#          Create-only fields are rejected; every change is audited with
#          before/after values (SN14); machine feeds land in `enrichment_data`.
# ============================================================================

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import or_, select

from app.db.db_models import Hazard
from app.db.ids import register_tenant, tenant_slug
from app.db.isolation import demo_scope
from app.db.runner import run
from app.db.session import session_scope
from app.models.hazard import revalue_taxonomy
from app.services.audit_service import log_audit

# SN14 create-only fields — enrichment may NEVER touch these.
CREATE_ONLY_FIELDS = {
    "identified_at", "hazard_id", "hazard_code", "source",
    "initial_priority", "priority", "priority_date", "created_at", "created_by",
}

# SN14 enrichment-allowed manual fields (existing hazards columns).
ENRICHMENT_FIELDS = {
    "equipment", "description", "taxonomy", "top_event", "consequence",
    "recommended_action", "follow_up_date", "remarks",
}

# SN14 hybrid storage: machine feeds / provenance JSONB.
JSON_FIELDS = {"enrichment_data", "enrichment_sources"}


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


async def _lookup_hazard(session, tid: str, ref: str) -> Optional[Hazard]:
    conds = [Hazard.hazard_id == str(ref)]
    try:
        conds.append(Hazard.id == uuid.UUID(str(ref)))
    except (ValueError, TypeError, AttributeError):
        pass
    return (await session.execute(
        select(Hazard)
        .where(Hazard.tenant_id == uuid.UUID(tid), Hazard.is_demo == demo_scope(), or_(*conds))
        .limit(1)
    )).scalars().first()


class HazardEnrichmentService:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    def enrich_hazard(self, hazard_id: str, user: Dict[str, Any],
                      payload: Dict[str, Any]) -> Dict[str, Any]:
        return run(self._enrich_async(hazard_id, user, payload or {}))

    async def _enrich_async(self, hazard_id, user, payload):
        forbidden = set(payload) & CREATE_ONLY_FIELDS
        if forbidden:
            raise ValueError(
                "Enrichment cannot modify create-only fields: "
                f"{sorted(forbidden)} (SN14)"
            )
        unknown = set(payload) - ENRICHMENT_FIELDS - JSON_FIELDS
        if unknown:
            raise ValueError(f"Unknown enrichment fields: {sorted(unknown)}")

        tid = register_tenant(self.tenant_id)
        now = datetime.now(timezone.utc)

        changes: List[Dict[str, Any]] = []
        async with session_scope() as session:
            hazard = await _lookup_hazard(session, tid, hazard_id)
            if not hazard:
                raise ValueError(f"Hazard {hazard_id!r} not found for tenant {self.tenant_id}")

            for field, new_value in payload.items():
                if field in JSON_FIELDS:
                    existing = getattr(hazard, field) or {}
                    merged = dict(existing) if isinstance(existing, dict) else {}
                    incoming = new_value if isinstance(new_value, dict) else {}
                    before = dict(merged)
                    merged.update(incoming)
                    setattr(hazard, field, merged)
                    changes.append({"field": field, "before": before, "after": merged})
                    continue

                if field == "taxonomy":
                    new_value = revalue_taxonomy(new_value)
                if field == "follow_up_date":
                    new_value = _parse_dt(new_value)

                before = getattr(hazard, field)
                if before == new_value:
                    continue
                changes.append({
                    "field": field,
                    "before": before.isoformat() if isinstance(before, datetime) else before,
                    "after": new_value.isoformat() if isinstance(new_value, datetime) else new_value,
                })
                setattr(hazard, field, new_value)

            hazard.updated_at = now
            await session.flush()
            hazard_ref = hazard.hazard_id

        log_audit(
            action="HAZARD_ENRICHED",
            user=(user or {}).get("email") or (user or {}).get("uid"),
            tenant_id=self.tenant_id,
            target_type="hazard",
            target_id=hazard_ref,
            metadata={"changes": changes},
        )
        logger.info(f"Hazard {hazard_ref} enriched ({len(changes)} change(s)) for {self.tenant_id}")
        return {"hazard_id": hazard_ref, "tenant_id": tenant_slug(tid), "changes": changes}
