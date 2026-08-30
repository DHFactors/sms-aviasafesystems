# ==============================================================================
# File: backend/tests/test_hazard_rca.py
# Description: Unit and integration tests for Hazard Analysis, HFACS 7.0 RCA
#              tagging, and ICAO 5x5 risk evaluation workflows (Postgres-backed).
# ==============================================================================

import pytest
from sqlalchemy import select, delete

from app.db.ids import register_tenant
from app.db.db_models import HazardRcaEntry, HazardRcaFactor, HazardAssessment, HazardCapa
from app.db.session import session_scope
from app.services.hazard_service import TOLERABILITY_MATRIX, HazardService

def test_icao_risk_tolerability_matrix():
    """Verify standard ICAO Doc 9859 5x5 risk indexes mapping."""
    assert TOLERABILITY_MATRIX[("A", 5)] == "intolerable"
    assert TOLERABILITY_MATRIX[("D", 4)] == "tolerable"
    assert TOLERABILITY_MATRIX[("E", 1)] == "acceptable"
    assert TOLERABILITY_MATRIX[("B", 2)] == "tolerable"


async def _cleanup_rca(tenant: str):
    """Remove v2 RCA rows created by the lifecycle test."""
    tid = register_tenant(tenant)
    async with session_scope() as s:
        entry_ids = (
            await s.scalars(
                select(HazardRcaEntry.id).where(HazardRcaEntry.tenant_id == tid)
            )
        ).all()
        for eid in entry_ids:
            await s.execute(delete(HazardCapa).where(HazardCapa.entry_id == eid))
            await s.execute(delete(HazardAssessment).where(HazardAssessment.entry_id == eid))
            await s.execute(delete(HazardRcaFactor).where(HazardRcaFactor.entry_id == eid))
            await s.execute(delete(HazardRcaEntry).where(HazardRcaEntry.id == eid))


@pytest.mark.asyncio
async def test_hazard_lifecycle_postgres():
    """Verify hazard creation, RCA nanocode attachment, and risk evaluation
    persist to PostgreSQL (HAZ- prefixed resource ids, rca_ factors, risk
    assessments on the v2 RCA table set)."""
    service = HazardService()

    try:
        # 1. Create Hazard
        hazard_payload = {
            "title": "Unstabilized Approach during Monsoonal Windshear",
            "description": "Tailwind component exceeded company SOP limits on final approach.",
            "source_type": "occurrence",
            "source_reference_id": "OCC-2026-0819",
            "functional_area": "flight_operations",
            "assigned_owner_email": "safety@fishtailair.com.np",
            "target_completion_date": None
        }
        user_info = {"email": "ops@fishtailair.com.np", "name": "Flight Operations"}

        hazard_id = await service.create_hazard("fishtail-air", hazard_payload, user_info)
        assert hazard_id.startswith("HAZ-")

        # 2. Add HFACS RCA Factor
        rca_payload = {
            "tier": 2,
            "category": "PRECOND",
            "subcategory": "Physical Environment",
            "nanocode": "PE101",
            "definition": "Environmental Conditions Affecting Vision",
            "contributing_narrative": "Heavy rain showers reduced visual reference.",
            "order_sequence": 1
        }
        factor_id = await service.add_rca_factor("fishtail-air", hazard_id, rca_payload)
        assert factor_id.startswith("rca_")

        # 3. Record Initial Risk Assessment (4D -> Tolerable)
        asm_payload = {
            "assessment_type": "initial",
            "severity_score": 4,
            "severity_justification": "Hazardous approach margins.",
            "probability_score": "D",
            "probability_justification": "Improbable occurrence rate."
        }
        asm_result = await service.record_assessment("fishtail-air", hazard_id, asm_payload, "safety@fishtailair.com.np")
        assert asm_result["risk_index"] == "4D"
        assert asm_result["tolerability"] == "tolerable"
    finally:
        await _cleanup_rca("fishtail-air")