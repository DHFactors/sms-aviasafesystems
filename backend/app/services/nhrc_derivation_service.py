# ============================================================================
# FILE: nhrc_derivation_service.py
# PATH: backend/app/services/nhrc_derivation_service.py
# PURPOSE: Module C §8 (Q8.2, SN-C9) — auto-derive a hazard's N-HRC category
#          from its taxonomy / ADREP category / occurrence type, using the
#          `taxonomy_mappings` reference table first and the N-HRC keyword
#          rules as a fallback. A manual value always overrides (the caller
#          only derives when `nhrc_category` is absent).
# ============================================================================

from __future__ import annotations

from typing import Any, Optional

from loguru import logger
from sqlalchemy import or_, select

from app.db.db_models import TaxonomyMapping
from app.db.runner import run
from app.db.session import session_scope

# Hazard stored taxonomy (4-value ICAO set) → N-HRC rule taxonomy codes.
TAXONOMY_TO_RULE = {
    "organizational": "ORG",
    "technical": "TEC",
    "human": "HUM",
    "environmental": "ENV",
    "env": "ENV",
    "tec": "TEC",
    "hum": "HUM",
    "org": "ORG",
    "wld": "WLD",
}


def _lookup_mapping(code: str) -> Optional[str]:
    async def _fetch():
        async with session_scope() as session:
            row = (await session.execute(
                select(TaxonomyMapping).where(
                    or_(TaxonomyMapping.icao_code == code,
                        TaxonomyMapping.adrep_code == code)
                ).limit(1)
            )).scalars().first()
            return row.nhrc_category if row else None

    try:
        return run(_fetch())
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"taxonomy_mappings lookup failed for {code}: {e}")
        return None


def derive_nhrc_category(
    taxonomy: Optional[str] = None,
    adrep_category: Optional[str] = None,
    occurrence_type: Optional[str] = None,
    title: str = "",
    description: str = "",
    priority: str = "M",
) -> Optional[str]:
    """Return the derived N-HRC category code, or None when undetermined."""
    code = (adrep_category or occurrence_type or "").strip().upper()
    if code:
        mapped = _lookup_mapping(code)
        if mapped:
            return mapped

    from app.services.nhrc_service import NHRCService

    rule_taxonomy = TAXONOMY_TO_RULE.get((taxonomy or "").strip().lower(), "")
    hazard = {
        "taxonomy": rule_taxonomy,
        "title": f"{title} {occurrence_type or ''}".strip(),
        "description": description,
        "priority": priority,
    }
    nhrc = NHRCService().map_hazard_to_nhrc(hazard)
    return nhrc.value if nhrc else None


def resolve_nhrc_category(provided: Optional[str], **derive_kwargs: Any) -> Optional[str]:
    """Manual override wins; otherwise derive (convenience wrapper)."""
    if provided:
        return provided
    return derive_nhrc_category(**derive_kwargs)
