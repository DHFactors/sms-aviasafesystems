# ============================================================================
# P2-25 — confidential reporting class (flag + custodian access control).
# ============================================================================

import uuid
from datetime import datetime, timezone

from app.db.db_models import Report
from app.db.isolation import demo_scope
from app.db.session import session_scope
from app.services.confidential_reporting_service import ConfidentialReportingService

from _mbb import cleanup, create_tenant, create_user, run, unique_slug

TABLES = ("reports",)


def _seed_report(tid):
    rid = uuid.uuid4()
    now = datetime.now(timezone.utc)

    async def _go():
        async with session_scope() as s:
            s.add(Report(
                id=rid, tenant_id=tid, report_type="voluntary", status="NEW",
                narrative="confidential narrative", location="KTM",
                occurrence_date=now, created_by="system", is_demo=demo_scope(),
                reporter_name="Jane Reporter", reporter_email="jane@x.com"))

    run(_go())
    return str(rid)


def test_flag_custodian_and_deidentify():
    slug = unique_slug("conf")
    tid = create_tenant(slug)
    custodian_uid = "cust-" + uuid.uuid4().hex[:8]
    custodian_id = create_user(tid, custodian_uid, role="AIRLINE_ADMIN")
    other_uid = "other-" + uuid.uuid4().hex[:8]
    create_user(tid, other_uid, role="SAFETY_OFFICER")
    rid = _seed_report(tid)
    try:
        svc = ConfidentialReportingService(slug)
        marked = svc.mark_confidential(
            rid, {"uid": custodian_uid, "email": f"{custodian_uid}@test.local"},
            {"role": "AIRLINE_ADMIN", "uid": custodian_uid})
        assert marked["is_confidential"] is True
        assert marked["confidential_custodian_id"] == custodian_id

        report = {"is_confidential": True, "confidential_custodian_id": custodian_id}
        # The custodian can see reporter identity; another user cannot.
        assert svc.can_view_reporter_identity(
            report, {"role": "AIRLINE_ADMIN", "uid": custodian_uid, "email": f"{custodian_uid}@test.local"}) is True
        assert svc.can_view_reporter_identity(
            report, {"role": "SAFETY_OFFICER", "uid": other_uid, "email": f"{other_uid}@test.local"}) is False

        # Downstream projection is de-identified for a non-custodian.
        downstream = svc.get_for_downstream(
            rid, {"role": "SAFETY_OFFICER", "uid": other_uid, "email": f"{other_uid}@test.local"})
        assert downstream["reporter_name"] is None
        assert downstream["reporter_email"] is None
        assert downstream["is_anonymous"] is True
    finally:
        cleanup(slug, TABLES)
