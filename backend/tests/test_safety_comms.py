# ============================================================================
# P2-13 — safety-communications service (draft → review → published → archived).
# ============================================================================

import pytest

from app.services.safety_comms_service import SafetyCommsService

from _mbb import cleanup, create_tenant, unique_slug

TABLES = ("safety_communications",)


def test_lifecycle_and_approval_gate():
    slug = unique_slug("comms")
    create_tenant(slug)
    try:
        svc = SafetyCommsService(slug)
        officer = {"role": "SAFETY_OFFICER", "email": "so@x.com"}
        manager = {"role": "TENANT_ADMIN", "email": "sm@x.com"}

        comm = svc.create_draft(officer, "Runway safety bulletin", body="...",
                                audience={"roles": "all"})
        assert comm["status"] == "draft"

        comm = svc.submit_for_review(comm["id"], officer)
        assert comm["status"] == "review"

        # Publication requires the safety-manager capability.
        with pytest.raises(PermissionError):
            svc.publish(comm["id"], officer)

        published = svc.publish(comm["id"], manager)
        assert published["status"] == "published"
        assert published["published_at"] is not None

        archived = svc.archive(comm["id"], manager)
        assert archived["status"] == "archived"

        assert len(svc.list_communications("archived")) == 1
        assert svc.list_communications("draft") == []
    finally:
        cleanup(slug, TABLES)


def test_invalid_transition_rejected():
    slug = unique_slug("comms2")
    create_tenant(slug)
    try:
        svc = SafetyCommsService(slug)
        manager = {"role": "TENANT_ADMIN", "email": "sm@x.com"}
        comm = svc.create_draft(manager, "Title")
        # draft -> published is not allowed (must pass through review).
        with pytest.raises(ValueError):
            svc.publish(comm["id"], manager)
    finally:
        cleanup(slug, TABLES)
