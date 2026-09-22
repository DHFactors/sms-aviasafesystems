# ============================================================================
# P2-10 — hazard enrichment service (add-not-replace; create-only rejected).
# ============================================================================

import pytest
from sqlalchemy import select

from app.db.db_models import Hazard
from app.db.isolation import demo_scope
from app.db.session import session_scope
from app.services.hazard_enrichment_service import HazardEnrichmentService

from _mbb import cleanup, create_tenant, run, unique_slug

TABLES = ("hazards",)


def _seed_hazard(tid: str) -> str:
    async def _go():
        async with session_scope() as s:
            s.add(Hazard(
                tenant_id=tid, hazard_id="ENR-001", title="Enrich me",
                description="original", source="voluntary", taxonomy="Organizational",
                priority="M", status="Open", is_demo=demo_scope(),
            ))

    run(_go())
    return "ENR-001"


def test_enrichment_adds_and_records_before_after():
    slug = unique_slug("enrich")
    tid = create_tenant(slug)
    _seed_hazard(tid)
    try:
        svc = HazardEnrichmentService(slug)
        result = svc.enrich_hazard("ENR-001", {"role": "SAFETY_OFFICER"}, {
            "description": "updated description",
            "equipment": "B737",
            "enrichment_data": {"fdm": {"event": "hard landing"}},
        })
        fields = {c["field"]: c for c in result["changes"]}
        assert fields["description"]["before"] == "original"
        assert fields["description"]["after"] == "updated description"
        assert fields["enrichment_data"]["after"] == {"fdm": {"event": "hard landing"}}

        async def _go():
            async with session_scope() as s:
                return (await s.execute(
                    select(Hazard).where(Hazard.hazard_id == "ENR-001")
                )).scalars().first()

        h = run(_go())
        assert h.description == "updated description"
        assert h.equipment == "B737"
        assert h.enrichment_data == {"fdm": {"event": "hard landing"}}
    finally:
        cleanup(slug, TABLES)


def test_create_only_fields_rejected():
    slug = unique_slug("enrco")
    tid = create_tenant(slug)
    _seed_hazard(tid)
    try:
        svc = HazardEnrichmentService(slug)
        with pytest.raises(ValueError) as exc:
            svc.enrich_hazard("ENR-001", {}, {"source": "mandatory"})
        assert "create-only" in str(exc.value)

        with pytest.raises(ValueError):
            svc.enrich_hazard("ENR-001", {}, {"identified_at": "2026-01-01"})

        with pytest.raises(ValueError):
            svc.enrich_hazard("ENR-001", {}, {"bogus_field": 1})
    finally:
        cleanup(slug, TABLES)
