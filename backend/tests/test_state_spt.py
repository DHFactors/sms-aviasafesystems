# ============================================================================
# P2-19 — state safety performance targets (CAAN-gated).
# ============================================================================

import pytest
from sqlalchemy import text

from app.db.session import session_scope
from app.services.state_spt_service import StateSPTService

from _mbb import cleanup, create_tenant, run, unique_slug

CAAN = {"role": "CAAN_SMD", "email": "smd@caan.gov.np"}
OFFICER = {"role": "SAFETY_OFFICER", "email": "so@air.com"}


def _wipe_spts():
    async def _go():
        async with session_scope() as s:
            await s.execute(text("DELETE FROM public.state_safety_performance_targets"))

    run(_go())


def test_set_approve_list_delete():
    slug = unique_slug("spt")
    create_tenant(slug)
    try:
        svc = StateSPTService()
        spt = svc.set_state_spt("SPI-LAG-002", 95.0, "annual", CAAN)
        assert spt["target_value"] == 95.0
        assert spt["target_period"] == "annual"
        assert spt["set_by"] == "smd@caan.gov.np"
        assert spt["approved_by"] is None

        approved = svc.approve_state_spt(spt["id"], CAAN)
        assert approved["approved_by"] == "smd@caan.gov.np"
        assert approved["approved_at"] is not None

        assert len(svc.list_state_spts()) == 1
        assert len(svc.list_state_spts("annual")) == 1
        assert svc.list_state_spts("quarterly") == []

        assert svc.delete_state_spt(spt["id"], CAAN) is True
        assert svc.list_state_spts() == []
    finally:
        _wipe_spts()
        cleanup(slug)


def test_caan_gate_enforced():
    slug = unique_slug("sptgate")
    create_tenant(slug)
    try:
        svc = StateSPTService()
        with pytest.raises(PermissionError):
            svc.set_state_spt("SPI-LAG-002", 95.0, "annual", OFFICER)
    finally:
        _wipe_spts()
        cleanup(slug)
