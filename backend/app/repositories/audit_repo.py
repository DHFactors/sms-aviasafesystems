from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.db import pg
from app.db.db_models import AuditDispatch
from app.firebase import get_db

COLLECTION_PATH = "audit_logs/regulatory/dispatches"
TENANT_COLLECTION_PREFIX = "audit_logs/sms_dispatches"


def _collection():
    return get_db().collection(COLLECTION_PATH)


def _tenant_audit_collection(tenant_id: str):
    return get_db().collection(f"tenants/{tenant_id}/audit_logs/sms_dispatches")


def _mirror(*, audit_id: str, collection, doc: Dict[str, Any]) -> None:
    try:
        collection.document(audit_id).set(dict(doc))
    except Exception as e:  # pragma: no cover - mirror best effort
        logger.warning(f"Audit dispatch mirror write failed ({audit_id}): {e}")


def _read(audit_id: str) -> Optional[Dict[str, Any]]:
    data = pg.fetch_by(AuditDispatch, "audit_id", audit_id)
    if data is None:
        return None
    data.pop("id", None)
    return data


def _write(audit_id: str, doc: Dict[str, Any]) -> None:
    pg.upsert(AuditDispatch, "audit_id", audit_id, doc)


def _serialize_out(data: Dict[str, Any]) -> Dict[str, Any]:
    data["id"] = data.get("audit_id")
    for key in ("created_at", "updated_at", "last_attempt_at", "delivered_at"):
        val = data.get(key)
        if val and hasattr(val, "isoformat"):
            data[key] = val.isoformat()
    return data


def record_dispatch_intent(
    audit_id: str,
    regulator_id: str,
    dispatched_by_user: str,
    reporting_year: int,
    recipients: List[str],
    pdf_sha256_checksum: Optional[str] = None,
    reporting_quarter: Optional[int] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    doc = {
        "audit_id": audit_id,
        "regulator_id": regulator_id,
        "regulator_name": None,
        "dispatched_by_user": dispatched_by_user,
        "reporting_year": reporting_year,
        "reporting_quarter": reporting_quarter,
        "recipients": recipients,
        "pdf_sha256_checksum": pdf_sha256_checksum,
        "attempt_count": 0,
        "status": "pending",
        "last_attempt_at": None,
        "delivered_at": None,
        "failure_reason": None,
        "created_at": now,
        "updated_at": now,
    }
    try:
        _write(audit_id, doc)
        _mirror(audit_id=audit_id, collection=_collection(), doc=doc)
        logger.info(f"Audit dispatch intent recorded: {audit_id}")
    except Exception as e:
        logger.error(f"Failed to record dispatch intent {audit_id}: {e}")
        raise
    return doc


def log_retry_attempt(audit_id: str, error_message: Optional[str] = None) -> None:
    now = datetime.now(timezone.utc)
    try:
        existing = _read(audit_id) or {}
        base = {
            "audit_id": audit_id,
            "status": "retrying",
            "last_attempt_at": now,
            "updated_at": now,
            "attempt_count": int(existing.get("attempt_count") or 0) + 1,
        }
        if error_message:
            base["failure_reason"] = error_message
        doc = dict(existing)
        doc.update(base)
        _write(audit_id, doc)
        _mirror(audit_id=audit_id, collection=_collection(), doc=doc)
        logger.info(f"Retry attempt logged for audit {audit_id}")
    except Exception as e:
        logger.error(f"Failed to log retry for audit {audit_id}: {e}")


def update_dispatch_status(
    audit_id: str,
    status: str,
    delivered_at: Optional[datetime] = None,
    failure_reason: Optional[str] = None,
) -> None:
    now = datetime.now(timezone.utc)
    try:
        existing = _read(audit_id) or {"audit_id": audit_id}
        doc = dict(existing)
        doc.update({"status": status, "updated_at": now})
        if delivered_at:
            doc["delivered_at"] = delivered_at
        if failure_reason:
            doc["failure_reason"] = failure_reason
        _write(audit_id, doc)
        _mirror(audit_id=audit_id, collection=_collection(), doc=doc)
        logger.info(f"Dispatch status updated for audit {audit_id}: {status}")
    except Exception as e:
        logger.error(f"Failed to update dispatch status for audit {audit_id}: {e}")


def list_recent_dispatches(
    limit: int = 50,
    regulator_id: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    try:
        where = []
        if regulator_id:
            where.append(AuditDispatch.regulator_id == regulator_id)
        if status:
            where.append(AuditDispatch.status == status)
        rows = pg.fetch_all(
            AuditDispatch,
            where=where or None,
            order_by=AuditDispatch.created_at.desc(),
            limit=limit,
        )
        return [_serialize_out(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to list recent dispatches: {e}")
        return []


# =========================================================================
# Tenant-Isolated Audit Trail (scoped under tenants/{tenantId}/...)
# =========================================================================


def record_tenant_dispatch_intent(
    tenant_id: str,
    audit_id: str,
    dispatched_by_user: str,
    reporting_year: int,
    reporting_month: int,
    recipients: list,
    pdf_sha256_checksum: Optional[str] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    doc = {
        "audit_id": audit_id,
        "tenant_id": tenant_id,
        "dispatched_by_user": dispatched_by_user,
        "reporting_year": reporting_year,
        "reporting_month": reporting_month,
        "recipients": recipients,
        "pdf_sha256_checksum": pdf_sha256_checksum,
        "attempt_count": 0,
        "status": "pending",
        "last_attempt_at": None,
        "delivered_at": None,
        "failure_reason": None,
        "created_at": now,
        "updated_at": now,
    }
    try:
        _write(audit_id, doc)
        _mirror(audit_id=audit_id, collection=_tenant_audit_collection(tenant_id), doc=doc)
        logger.info(f"Tenant audit dispatch intent recorded: {audit_id} (tenant={tenant_id})")
    except Exception as e:
        logger.error(f"Failed to record tenant dispatch intent {audit_id}: {e}")
        raise
    return doc


def update_tenant_dispatch_status(
    tenant_id: str,
    audit_id: str,
    status: str,
    delivered_at: Optional[datetime] = None,
    failure_reason: Optional[str] = None,
) -> None:
    now = datetime.now(timezone.utc)
    try:
        existing = _read(audit_id) or {"audit_id": audit_id}
        doc = dict(existing)
        doc.update({"status": status, "updated_at": now})
        if delivered_at:
            doc["delivered_at"] = delivered_at
        if failure_reason:
            doc["failure_reason"] = failure_reason
        _write(audit_id, doc)
        _mirror(audit_id=audit_id, collection=_tenant_audit_collection(tenant_id), doc=doc)
        logger.info(f"Tenant dispatch status updated: {audit_id} -> {status}")
    except Exception as e:
        logger.error(f"Failed to update tenant dispatch status for {audit_id}: {e}")


def list_tenant_dispatches(
    tenant_id: str,
    limit: int = 50,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    try:
        where = [AuditDispatch.tenant_id == tenant_id]
        if status:
            where.append(AuditDispatch.status == status)
        rows = pg.fetch_all(
            AuditDispatch,
            where=where,
            order_by=AuditDispatch.created_at.desc(),
            limit=limit,
        )
        return [_serialize_out(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to list tenant dispatches for {tenant_id}: {e}")
        return []