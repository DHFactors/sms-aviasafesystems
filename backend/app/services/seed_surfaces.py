# ============================================================================
# FILE: seed_surfaces.py
# PATH: backend/app/services/seed_surfaces.py
# PURPOSE: Super-Admin Production Setup "seed surfaces" that let the panel
#          achieve what the legacy CLI seeding did, but fully data-driven:
#             * PSOE baseline assessments (one COMPLETED + one DRAFT) for any
#               tenant that was created at Step 2 — never a hardcoded list.
#             * The ICAO state-risk reference register (global reference data,
#               seeded from the shared taxonomy, not from any tenant list).
#          Both write an audit row and are keyed off existing Postgres
#          tenants/regulators so there are no hardcoded tenants anywhere.
# ============================================================================

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import settings
from app.db import pg
from app.db.db_models import PsoeAssessment as PgAssessment, StateRiskCategory, Tenant
from app.db.ids import tenant_uuid, register_tenant
from app.db.isolation import demo_scope
from app.models.psoe import PSOEAnswer
from app.services.psoe_service import load_template, score_assessment
from app.services.production_seed import _audit, _validate_id
from app.services.state_risk_service import (
    ICAO_REFERENCE_DOCUMENT,
    ICAO_TOP_RISK_CATEGORIES,
    STATE_COLLECTION,
)

_PANE_BY_CODE = {
    "CE": "Cabin Safety",
    "EX": "Operations & Training",
    "OM": "Cargo & Dangerous Goods",
    "MH": "Maintenance",
    "AG": "Ground Handling",
    "AR": "Aerodrome Safety",
    "WL": "Wildlife & Environment",
    "SC": "Security & Facilitation",
    "AW": "Airworthiness",
    "RF": "Rescue & Firefighting",
    "AT": "Air Traffic Services",
}


# ============================================================================
# PSOE baseline assessments (data-driven, per Step-2 tenant)
# ============================================================================

_PLAN_COMPLETED = {
    "component_1": [3, 3, 3, 2, 3, 1],
    "component_2": [3, 3, 2, 3, 2, 1],
    "component_3": [3, 3, 2, 3, 1],
    "component_4": [3, 3, 3, 1],
}
_PLAN_DRAFT = {
    "component_1": [2, 2, 2, 3, 2, 1],
    "component_2": [2, 2, 1, 2, 2, 1],
    "component_3": [2, 2, 1, 2, 0],
    "component_4": [2, 2, 1, None],
}


def _tenant_exists(tid: str) -> bool:
    return pg.fetch_by(Tenant, "slug", tid) is not None


def _pane(code: str) -> str:
    if code not in _PANE_BY_CODE:
        logger.warning(f"PSOE seed: unknown pane code '{code}'")
    return _PANE_BY_CODE.get(code, "Safety Quick Reference")


def _responses_from_plan(template, plan: Dict[str, List[Any]]) -> List[PSOEAnswer]:
    out = []
    for comp in template.components:
        scores = plan.get(comp.id) or []
        for q, score in zip(comp.questions, scores):
            if score is None:
                out.append(PSOEAnswer(question_id=q.id, score=None, is_na=True))
            else:
                out.append(PSOEAnswer(
                    question_id=q.id, score=score, is_na=False,
                    comment=f"Seasonal baseline evidence ({q.id}).",
                    evidence="Super-Admin Production Setup baseline",
                ))
    return out


async def seed_psoe_tenant(tenant_id: str, actor: Dict[str, Any],
                           force: bool = False) -> Dict[str, Any]:
    """Write one COMPLETED + one DRAFT baseline PSOE assessment for a tenant.

    The tenant must already exist (created at Step 2). Deterministic doc ids
    make re-seeding idempotent unless ``force`` replaces them.
    """
    tid = _validate_id(tenant_id, "tenant id")
    if not _tenant_exists(tid):
        raise ValueError(f"tenant not found: {tid}")

    template = load_template()
    now = datetime.now(timezone.utc)

    variations = (
        ("baseline-completed", "completed", "CAAN Appendix 10 Surveillance",
         "CAAN Appendix 10 SMS surveillance",
         _PLAN_COMPLETED, 1, "CE"),
        ("baseline-draft", "draft", "CAAN Appendix 10 Self-Assessment (Draft)",
         "PSOE self-assessment", _PLAN_DRAFT, 3, "EX"),
    )

    written = []
    for suffix, status, title_head, scope, plan, days_ago, pane_code in variations:
        doc_id = f"{tid}-{suffix}"
        # Use deterministic uuid for PG id column
        from app.db.ids import uuid5
        pg_id = uuid5("psoe", tid, suffix)
        existing = pg.fetch_by(PgAssessment, "id", pg_id)
        if not force and existing is not None:
            written.append({"id": doc_id, "status": status, "skipped": True})
            continue

        responses = _responses_from_plan(template, plan)
        scores = score_assessment(responses)
        doc = {
            "id": pg_id,
            "tenant_id": tenant_uuid(tid),
            "title": f"{title_head} — {tid}",
            "status": status,
            "department": "Safety",
            "scope": scope,
            "auditor_name": "Super-Admin Baseline",
            "assessor_email": f"admin@{tid}.com",
            "assessment_date": (now - timedelta(days=days_ago)).date().isoformat(),
            "template_version": template.version,
            "responses": [r.model_dump() for r in responses],
            "component_scores": scores["component_scores"],
            "overall_score_pct": scores["overall_score_pct"],
            "overall_level": scores["overall_level"],
            "created_by": "production-setup",
            "created_at": now,
            "updated_at": now,
            "is_demo": demo_scope(),
            "notes": f"pane:{_pane(pane_code)} seed_version:production-setup-1",
        }
        register_tenant(tid)
        pg.upsert(PgAssessment, "id", pg_id, doc)
        written.append({"id": doc_id, "status": status, "skipped": False})

    written_detail = ", ".join(f"{w['id']}({w['status']})" for w in written)
    _audit("PSOE_SEEDED", actor, tid, f"Seeded PSOE baselines: {written_detail}")
    logger.info(f"PSOE baselines seeded for {tid}")
    return {"tenant_id": tid, "assessments": written}


async def seed_psoe_all(actors: List[str], actor: Dict[str, Any],
                        force: bool = False) -> Dict[str, Any]:
    """Seed PSOE baselines for every Step-2 tenant (data-driven)."""
    results = []
    for tid in actors:
        try:
            results.append(await seed_psoe_tenant(tid, actor, force=force))
        except ValueError as e:
            results.append({"tenant_id": tid, "error": str(e)})
        except Exception as e:
            logger.error(f"PSOE seed failed for {tid}: {e}")
            results.append({"tenant_id": tid, "error": str(e)})
    return {"results": results}


# ============================================================================
# ICAO state-risk reference register (global reference data)
# ============================================================================

async def seed_state_risk_reference(actor: Dict[str, Any]) -> Dict[str, Any]:
    """Write the ICAO top-risk reference categories for the state SSP register.

    This is global reference taxonomy (regulator-facing). Tenants are not
    involved, so nothing is hardcoded to any operator.
    """
    written = 0
    for cat_def in ICAO_TOP_RISK_CATEGORIES:
        doc = {
            "slug": cat_def["category"],
            "name": cat_def["name"],
            "data": dict(cat_def),
        }
        pg.upsert(StateRiskCategory, "slug", cat_def["category"], doc)
        written += 1
    _audit("STATE_RISK_REFERENCE_SEEDED", actor, ICAO_REFERENCE_DOCUMENT,
           f"Seeded {written} ICAO top-risk reference categories")
    logger.info(f"State-risk reference seeded: {written} categories")
    return {"reference": ICAO_REFERENCE_DOCUMENT, "categories": written}


if __name__ == "__main__":
    pass
