# ============================================================================
# P2-22 — PSOE finding ↔ CAP bidirectional linkage.
# ============================================================================

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text

from app.db.db_models import Can, Cap, Hazard, PsoeAssessment, PsoeFinding
from app.db.isolation import demo_scope
from app.db.session import session_scope
from app.services.psoe_cap_link_service import PsoeCapLinkService

from _mbb import create_tenant, run, unique_slug


def _cleanup(slug, tid):
    """Best-effort teardown: per-statement commits, never raises (see
    backend/tests/_mbb.py::cleanup)."""
    import logging

    async def _go():
        async with session_scope() as s:
            for stmt in (
                "DELETE FROM public.caps WHERE tenant_id = :id",
                "DELETE FROM public.cans WHERE tenant_id = :id",
                "DELETE FROM public.hazards WHERE tenant_id = :id",
                "DELETE FROM public.psoe_findings WHERE assessment_id IN "
                "(SELECT id FROM public.psoe_assessments WHERE tenant_id = :id)",
                "DELETE FROM public.psoe_assessments WHERE tenant_id = :id",
                "DELETE FROM public.users WHERE tenant_id = :id",
                "DELETE FROM public.tenants WHERE id = :id",
            ):
                try:
                    await s.execute(text(stmt), {"id": tid})
                    await s.commit()
                except Exception as e:
                    try:
                        await s.rollback()
                    except Exception:
                        pass
                    logging.getLogger(__name__).warning(
                        "test cleanup: %s failed for %s: %s",
                        stmt.split()[2], slug, e)

    try:
        run(_go())
    except Exception as e:
        logging.getLogger(__name__).warning(
            "test cleanup: session failed for %s: %s", slug, e)


def _seed(tid):
    can_id, cap_id, haz_id, asmt_id, find_id = (uuid.uuid4() for _ in range(5))
    now = datetime.now(timezone.utc)

    async def _go():
        async with session_scope() as s:
            s.add(Hazard(id=haz_id, tenant_id=tid, hazard_id="PL-1", title="h",
                         description="d", source="voluntary", taxonomy="Organizational",
                         priority="M", status="Open", is_demo=demo_scope()))
            await s.flush()
            s.add(Can(id=can_id, tenant_id=tid, hazard_id=haz_id, can_reference="CAN-PL",
                      title="t", description="d", required_action="a", issued_by="x",
                      issued_by_uid="u", assigned_to="y", assigned_to_uid="v",
                      priority="High", status="Open", is_demo=demo_scope()))
            await s.flush()
            s.add(Cap(id=cap_id, tenant_id=tid, can_id=can_id, cap_reference="CAP-PL",
                      action_plan="p", timeline="t", resources_required="r",
                      implementation_plan="i", target_completion_date=now,
                      submitted_by="x", submitted_by_uid="u", status="In Progress",
                      is_demo=demo_scope()))
            s.add(PsoeAssessment(id=asmt_id, tenant_id=tid, title="PSOE",
                                 status="draft", template_version="1.0", responses={},
                                 is_demo=demo_scope()))
            await s.flush()
            s.add(PsoeFinding(id=find_id, assessment_id=asmt_id, description="finding",
                              status="open", is_demo=demo_scope()))

    run(_go())
    return str(find_id), str(cap_id)


def test_link_unlink_bidirectional():
    slug = unique_slug("psoelink")
    tid = create_tenant(slug)
    finding_id, cap_id = _seed(tid)
    try:
        svc = PsoeCapLinkService(slug)
        linked = svc.link_finding_to_cap(finding_id, cap_id, {"role": "SAFETY_OFFICER"})
        assert linked["finding_id"] == finding_id
        assert linked["cap_id"] == cap_id

        assert svc.list_links_for_finding(finding_id)["cap_id"] == cap_id
        assert svc.list_links_for_cap(cap_id)["finding_id"] == finding_id

        async def _check():
            async with session_scope() as s:
                f = (await s.execute(select(PsoeFinding).where(
                    PsoeFinding.id == uuid.UUID(finding_id)))).scalars().first()
                c = (await s.execute(select(Cap).where(
                    Cap.id == uuid.UUID(cap_id)))).scalars().first()
                return str(f.cap_id), str(c.source_psoe_finding_id)

        f_cap, c_find = run(_check())
        assert f_cap == cap_id
        assert c_find == finding_id

        unlinked = svc.unlink_finding_from_cap(finding_id, {"role": "SAFETY_OFFICER"})
        assert unlinked["cap_id"] is None
        assert svc.list_links_for_cap(cap_id)["finding_id"] is None
    finally:
        _cleanup(slug, tid)
