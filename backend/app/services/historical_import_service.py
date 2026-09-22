# ============================================================================
# FILE: historical_import_service.py
# PATH: backend/app/services/historical_import_service.py
# PURPOSE: Module B §25 (SN12) — historical import pipeline.
#          Upload -> Parse -> Stage -> Validate -> Review -> Promote.
#          Excel (.xlsx) + CSV native; .xlsm/.xlsb/.xltm rejected on extension
#          AND content sniffing. Provenance columns are written on promotion.
#
#          Scope (P2-14): hazards are fully staged/validated/promoted; other
#          entity types are staged + validated but flagged for manual mapping
#          (their promotion targets are a follow-up).
# ============================================================================

from __future__ import annotations

import csv
import hashlib
import io
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import select

from app.db.db_models import Hazard, ImportBatch, ImportRow
from app.db.ids import register_tenant, tenant_slug
from app.db.isolation import demo_scope
from app.db.runner import run
from app.db.session import session_scope
from app.services.actor import resolve_actor_uuid
from app.services.audit_service import log_audit

REJECTED_EXTENSIONS = {".xlsm", ".xlsb", ".xltm"}
SUPPORTED_EXTENSIONS = {".xlsx", ".csv", ".xls"}
HARD_ROW_CAP = 100_000

ENTITY_TYPES = {"hazard", "risk_register", "sram_risk_register", "bow_tie",
                "barrier", "can", "cap"}

# Sheet-name → entity type hints (multi-sheet workbooks, §25.4).
SHEET_ENTITY_HINTS = {
    "hazard": "hazard", "hazards": "hazard",
    "risk register": "risk_register", "risk_register": "risk_register",
    "sram": "sram_risk_register", "sram risk register": "sram_risk_register",
    "bowtie": "bow_tie", "bow-tie": "bow_tie", "bow tie": "bow_tie",
    "barrier": "barrier", "barriers": "barrier",
    "can": "can", "cans": "can", "cap": "cap", "caps": "cap",
}

HAZARD_REQUIRED = ("title", "description", "source")
VALID_TAXONOMY = {"Organizational", "Technical", "Human", "Environmental"}
VALID_PRIORITY = {"H", "M", "L"}


def _row_to_dict(row: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for col in row.__table__.columns:
        value = getattr(row, col.name)
        if isinstance(value, uuid.UUID):
            value = str(value)
        elif isinstance(value, datetime):
            value = value.isoformat()
        data[col.name] = value
    return data


def _entity_for_sheet(sheet_name: str) -> str:
    return SHEET_ENTITY_HINTS.get((sheet_name or "").strip().lower(), "hazard")


def _decode_csv(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def _parse_csv(data: bytes) -> List[Dict[str, Any]]:
    text = _decode_csv(data)
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for i, raw in enumerate(reader, start=2):  # header is line 1
        rows.append({
            "entity_type": "hazard",
            "sheet_name": None,
            "row_number": i,
            "original_row_ref": f"line {i}",
            "raw_data": {k: v for k, v in raw.items() if k is not None},
        })
    return rows


def _parse_xlsx(data: bytes) -> List[Dict[str, Any]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    rows: List[Dict[str, Any]] = []
    try:
        for sheet in wb.worksheets:
            entity = _entity_for_sheet(sheet.title)
            header: Optional[List[str]] = None
            for i, values in enumerate(sheet.iter_rows(values_only=True), start=1):
                if header is None:
                    header = [str(c).strip() if c is not None else "" for c in values]
                    continue
                if all(v is None for v in values):
                    continue
                raw = {
                    header[j]: values[j]
                    for j in range(min(len(header), len(values)))
                    if header[j]
                }
                rows.append({
                    "entity_type": entity,
                    "sheet_name": sheet.title,
                    "row_number": i,
                    "original_row_ref": f"{sheet.title}!row {i}",
                    "raw_data": raw,
                })
    finally:
        wb.close()
    return rows


def _normalize(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _validate_hazard(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    errors: List[str] = []
    normalized = {k: _normalize(v) for k, v in raw.items()}
    for field in HAZARD_REQUIRED:
        if not normalized.get(field):
            errors.append(f"{field} is required")

    taxonomy = normalized.get("taxonomy")
    if taxonomy and taxonomy not in VALID_TAXONOMY:
        errors.append(f"taxonomy must be one of {sorted(VALID_TAXONOMY)}")

    priority = normalized.get("priority")
    if priority and str(priority).upper() not in VALID_PRIORITY:
        errors.append("priority must be H, M or L")

    if normalized.get("hazard_id"):
        normalized["legacy_hazard_code"] = normalized.get("legacy_hazard_code") or normalized["hazard_id"]
    return normalized, errors


class HistoricalImportService:
    """Staging + validation + promotion for historical operator records."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    # -- public -------------------------------------------------------------

    def create_batch(self, user: Dict[str, Any], file_bytes: bytes,
                     filename: str) -> Dict[str, Any]:
        return run(self._create_batch_async(user, file_bytes, filename))

    def list_rows(self, batch_id: str,
                  status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        return run(self._list_rows_async(batch_id, status_filter))

    def promote_batch(self, batch_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
        return run(self._promote_batch_async(batch_id, user))

    def reject_batch(self, batch_id: str, user: Dict[str, Any], reason: str) -> Dict[str, Any]:
        return run(self._reject_batch_async(batch_id, user, reason))

    # -- parsing / staging --------------------------------------------------

    @staticmethod
    def parse_upload(file_bytes: bytes, filename: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Return (format, staged rows). Validates extension + magic bytes."""
        name = (filename or "").lower()
        ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        if ext in REJECTED_EXTENSIONS:
            raise ValueError(f"Macro-enabled/binary format {ext} is not permitted")
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported format {ext!r}; use .xlsx or .csv")

        if ext == ".xlsx":
            if not file_bytes.startswith(b"PK\x03\x04"):
                raise ValueError("File content is not a valid .xlsx (zip) container")
            rows = _parse_xlsx(file_bytes)
            fmt = "xlsx"
        elif ext == ".xls":
            raise ValueError("Legacy .xls is not supported by the native parser")
        else:
            rows = _parse_csv(file_bytes)
            fmt = "csv"

        if len(rows) > HARD_ROW_CAP:
            raise ValueError(f"Row count {len(rows)} exceeds the {HARD_ROW_CAP} cap")
        return fmt, rows

    async def _create_batch_async(self, user, file_bytes, filename):
        fmt, parsed = self.parse_upload(file_bytes, filename)
        tid = register_tenant(self.tenant_id)
        uploader = await resolve_actor_uuid(user)
        now = datetime.now(timezone.utc)
        source_hash = hashlib.sha256(file_bytes).hexdigest()

        valid = warning = error = 0
        async with session_scope() as session:
            batch = ImportBatch(
                tenant_id=uuid.UUID(tid),
                source_filename=filename,
                source_format=fmt,
                source_size_bytes=len(file_bytes),
                source_hash=source_hash,
                status="validated",
                total_rows=len(parsed),
                uploaded_by=uploader,
            )
            session.add(batch)
            await session.flush()

            for staged in parsed:
                raw = staged["raw_data"]
                if staged["entity_type"] == "hazard":
                    normalized, errors = _validate_hazard(raw)
                else:
                    normalized, errors = raw, []
                if errors:
                    status = "error"
                    error += 1
                else:
                    status = "valid"
                    valid += 1
                session.add(ImportRow(
                    batch_id=batch.id,
                    tenant_id=uuid.UUID(tid),
                    entity_type=staged["entity_type"],
                    sheet_name=staged["sheet_name"],
                    row_number=staged["row_number"],
                    original_row_ref=staged["original_row_ref"],
                    raw_data=raw,
                    normalized_data=normalized,
                    validation_status=status,
                    validation_errors=errors or None,
                ))

            batch.valid_rows = valid
            batch.error_rows = error
            batch.updated_at = now
            await session.flush()
            result = _row_to_dict(batch)
        result["tenant_id"] = tenant_slug(result["tenant_id"])

        log_audit(
            action="IMPORT_BATCH_CREATED",
            user=(user or {}).get("email") or (user or {}).get("uid"),
            tenant_id=self.tenant_id,
            target_type="import_batch",
            target_id=result["id"],
            metadata={"filename": filename, "format": fmt,
                      "total": len(parsed), "valid": valid, "error": error},
        )
        return result

    async def _list_rows_async(self, batch_id, status_filter):
        tid = register_tenant(self.tenant_id)
        stmt = select(ImportRow).where(
            ImportRow.batch_id == uuid.UUID(str(batch_id)),
            ImportRow.tenant_id == uuid.UUID(tid),
        )
        if status_filter:
            stmt = stmt.where(ImportRow.validation_status == status_filter)
        stmt = stmt.order_by(ImportRow.row_number)
        async with session_scope() as session:
            rows = (await session.scalars(stmt)).all()
        return [_row_to_dict(r) for r in rows]

    # -- promotion ----------------------------------------------------------

    async def _promote_batch_async(self, batch_id, user):
        tid = register_tenant(self.tenant_id)
        now = datetime.now(timezone.utc)
        promoted = 0
        skipped = 0

        async with session_scope() as session:
            batch = (await session.execute(
                select(ImportBatch).where(
                    ImportBatch.id == uuid.UUID(str(batch_id)),
                    ImportBatch.tenant_id == uuid.UUID(tid),
                )
            )).scalars().first()
            if not batch:
                raise ValueError(f"Import batch {batch_id!r} not found")

            rows = (await session.scalars(
                select(ImportRow).where(
                    ImportRow.batch_id == batch.id,
                    ImportRow.validation_status == "valid",
                    ImportRow.promoted == False,  # noqa: E712
                )
            )).all()

            for row in rows:
                if row.entity_type != "hazard":
                    # Staged + validated, promotion target pending manual mapping.
                    skipped += 1
                    continue
                data = dict(row.normalized_data or {})
                legacy = data.get("legacy_hazard_code")
                hazard_ref = legacy or f"IMP-{str(batch.id)[:8]}-{row.row_number or 0}"
                session.add(Hazard(
                    tenant_id=uuid.UUID(tid),
                    hazard_id=hazard_ref,
                    title=data.get("title") or "",
                    description=data.get("description") or "",
                    source=data.get("source") or "",
                    taxonomy=data.get("taxonomy") or "Organizational",
                    priority=(str(data.get("priority") or "M").upper()),
                    status="Open",
                    legacy_hazard_code=legacy,
                    imported_at=now,
                    import_batch_id=batch.id,
                    original_row_ref=row.original_row_ref,
                    is_demo=demo_scope(),
                    created_at=now,
                    updated_at=now,
                ))
                row.promoted = True
                promoted += 1

            batch.status = "promoted"
            batch.updated_at = now
            await session.flush()

        log_audit(
            action="IMPORT_BATCH_PROMOTED",
            user=(user or {}).get("email") or (user or {}).get("uid"),
            tenant_id=self.tenant_id,
            target_type="import_batch",
            target_id=str(batch_id),
            metadata={"promoted": promoted, "skipped": skipped},
        )
        logger.info(f"Import batch {batch_id} promoted {promoted} hazard(s) ({self.tenant_id})")
        return {"batch_id": str(batch_id), "promoted": promoted, "skipped": skipped}

    async def _reject_batch_async(self, batch_id, user, reason):
        tid = register_tenant(self.tenant_id)
        now = datetime.now(timezone.utc)
        async with session_scope() as session:
            batch = (await session.execute(
                select(ImportBatch).where(
                    ImportBatch.id == uuid.UUID(str(batch_id)),
                    ImportBatch.tenant_id == uuid.UUID(tid),
                )
            )).scalars().first()
            if not batch:
                raise ValueError(f"Import batch {batch_id!r} not found")
            batch.status = "failed"
            batch.updated_at = now
            await session.flush()

        log_audit(
            action="IMPORT_BATCH_REJECTED",
            user=(user or {}).get("email") or (user or {}).get("uid"),
            tenant_id=self.tenant_id,
            target_type="import_batch",
            target_id=str(batch_id),
            metadata={"reason": reason},
        )
        return {"batch_id": str(batch_id), "status": "failed", "reason": reason}
