from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.firebase import get_db

COLLECTION_PATH = "audit_logs/regulatory/dispatches"
TENANT_COLLECTION_PREFIX = "audit_logs/sms_dispatches"


def _collection():
    return get_db().collection(COLLECTION_PATH)


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
        _collection().document(audit_id).set(doc)
        logger.info(f"Audit dispatch intent recorded: {audit_id}")
    except Exception as e:
        logger.error(f"Failed to record dispatch intent {audit_id}: {e}")
        raise
    return doc


def log_retry_attempt(audit_id: str, error_message: Optional[str] = None) -> None:
    now = datetime.now(timezone.utc)
    try:
        ref = _collection().document(audit_id)
        updates: Dict[str, Any] = {
            "status": "retrying",
            "last_attempt_at": now,
            "updated_at": now,
        }
        doc_snap = ref.get()
        if doc_snap.exists:
            data = doc_snap.to_dict() or {}
            updates["attempt_count"] = data.get("attempt_count", 0) + 1
        else:
            updates["attempt_count"] = 1
        if error_message:
            updates["failure_reason"] = error_message
        ref.update(updates)
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
        updates: Dict[str, Any] = {
            "status": status,
            "updated_at": now,
        }
        if delivered_at:
            updates["delivered_at"] = delivered_at
        if failure_reason:
            updates["failure_reason"] = failure_reason
        _collection().document(audit_id).update(updates)
        logger.info(f"Dispatch status updated for audit {audit_id}: {status}")
    except Exception as e:
        logger.error(f"Failed to update dispatch status for audit {audit_id}: {e}")


def list_recent_dispatches(
    limit: int = 50,
    regulator_id: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    try:
        query = _collection().order_by("created_at", direction="DESCENDING")
        if regulator_id:
            query = query.where("regulator_id", "==", regulator_id)
        if status:
            query = query.where("status", "==", status)
        docs = query.limit(limit).get()
        results: List[Dict[str, Any]] = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            for key in ("created_at", "updated_at", "last_attempt_at", "delivered_at"):
                val = data.get(key)
                if val and hasattr(val, "isoformat"):
                    data[key] = val.isoformat()
            results.append(data)
        return results
    except Exception as e:
        logger.error(f"Failed to list recent dispatches: {e}")
        return []


# =========================================================================
# Tenant-Isolated Audit Trail (scoped under tenants/{tenantId}/...)
# =========================================================================

def _tenant_audit_collection(tenant_id: str):
    return get_db().collection(f"tenants/{tenant_id}/audit_logs/sms_dispatches")


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
        _tenant_audit_collection(tenant_id).document(audit_id).set(doc)
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
        updates: Dict[str, Any] = {"status": status, "updated_at": now}
        if delivered_at:
            updates["delivered_at"] = delivered_at
        if failure_reason:
            updates["failure_reason"] = failure_reason
        _tenant_audit_collection(tenant_id).document(audit_id).update(updates)
        logger.info(f"Tenant dispatch status updated: {audit_id} -> {status}")
    except Exception as e:
        logger.error(f"Failed to update tenant dispatch status for {audit_id}: {e}")


def list_tenant_dispatches(
    tenant_id: str,
    limit: int = 50,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    try:
        query = _tenant_audit_collection(tenant_id).order_by("created_at", direction="DESCENDING")
        if status:
            query = query.where("status", "==", status)
        docs = query.limit(limit).get()
        results: List[Dict[str, Any]] = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            for key in ("created_at", "updated_at", "last_attempt_at", "delivered_at"):
                val = data.get(key)
                if val and hasattr(val, "isoformat"):
                    data[key] = val.isoformat()
            results.append(data)
        return results
    except Exception as e:
        logger.error(f"Failed to list tenant dispatches for {tenant_id}: {e}")
        return []
