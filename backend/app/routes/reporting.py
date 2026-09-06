from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from typing import Dict, Any, Optional, List
from loguru import logger

from app.models.reporting import ReportResponse, ReportListItem, ReportType, ReportStatus
from app.middleware.auth import get_current_user, get_tenant_user
from app.services.report_generator import ReportGenerator
from app.services.pdf_generator import generate_report_pdf
from app.firebase import get_db, get_tenant_collection
from app.core.config import settings
from app.db import pg
from app.db.db_models import CaanReport, RegulatoryReport, Tenant
from app.db.ids import tenant_uuid, uuid5

router = APIRouter()
REPORT_COLLECTION = "reporting"

TENANT_COLLECTION = "tenants"


def _get_tenant_name(tenant_id: str) -> Optional[str]:
    try:
        doc = pg.fetch_by(Tenant, "slug", tenant_id)
        if doc:
            return doc.get("name") or doc.get("icao") or tenant_id
    except Exception:
        pass
    return tenant_id


def _effective_tenant(user: Dict[str, Any], tenant_id: Optional[str] = None) -> Optional[str]:
    """Resolve the report scope for the authenticated user.

    Cross-tenant roles (CAAN_SMD / SUPER_ADMIN) are state by default and may
    only scope to an operator when an explicit ``tenant_id`` query param is given.
    Tenant roles always use their own tenant (query param is already nulled).
    """
    if user.get("role") in settings.CROSS_TENANT_ROLES:
        return tenant_id
    return tenant_id or user.get("tenant_id")


def _report_id(effective_tenant: Optional[str], report_type: str, year: int, quarter: Optional[int]) -> str:
    parts = (report_type, str(year), str(quarter or 0))
    if effective_tenant:
        return uuid5("reg-report", effective_tenant, *parts)
    return uuid5("caan-report", *parts)


def _save_report(doc_data: Dict[str, Any], effective_tenant: Optional[str]) -> Dict[str, Any]:
    rid = _report_id(effective_tenant, doc_data["report_type"], doc_data.get("year"), doc_data.get("quarter"))
    doc_data["id"] = rid
    try:
        if effective_tenant:
            stored = dict(doc_data)
            stored["tenant_id"] = tenant_uuid(effective_tenant)
            pg.upsert(RegulatoryReport, "id", rid, stored)
            try:
                get_tenant_collection(effective_tenant, REPORT_COLLECTION).document(rid).set(dict(doc_data))
            except Exception as mirror_e:
                logger.warning(f"Report mirror write failed ({rid}): {mirror_e}")
        else:
            stored = dict(doc_data)
            stored["report_id"] = rid
            pg.upsert(CaanReport, "report_id", rid, stored)
            try:
                get_db().collection("caan_reports").document(rid).set(dict(doc_data))
            except Exception as mirror_e:
                logger.warning(f"CAAN report mirror write failed ({rid}): {mirror_e}")
    except Exception as e:
        logger.error(f"Failed to save report: {e}")
        raise HTTPException(500, "Failed to save report")
    return doc_data


def _fetch_report(effective_tenant: Optional[str], report_id: str) -> Optional[Dict[str, Any]]:
    if effective_tenant:
        doc = pg.fetch_by(RegulatoryReport, "id", report_id)
        if doc is None:
            return None
        doc["id"] = report_id
        return doc
    doc = pg.fetch_by(CaanReport, "report_id", report_id)
    if doc is None:
        return None
    doc.setdefault("id", doc.get("report_id"))
    return doc


def _list_reports(
    effective_tenant: Optional[str],
    report_type: str,
    year: Optional[int],
    user: Dict[str, Any],
) -> List[Dict[str, Any]]:
    results = []
    try:
        if effective_tenant:
            tid_uuid = tenant_uuid(effective_tenant)
            rows = pg.fetch_all(
                RegulatoryReport,
                where=[
                    RegulatoryReport.tenant_id == tid_uuid,
                    RegulatoryReport.report_type == report_type,
                ],
            )
            for data in rows:
                if year and data.get("year") != year:
                    continue
                results.append({
                    "id": _report_id(effective_tenant, report_type, data.get("year"), data.get("quarter")),
                    "report_type": report_type,
                    "period": data.get("period", ""),
                    "year": data.get("year"),
                    "quarter": data.get("quarter"),
                    "status": data.get("status", "completed"),
                    "generated_at": data.get("generated_at"),
                    "generated_by": data.get("generated_by"),
                })
        else:
            if user.get("role") in ("CAAN_SMD", "SUPER_ADMIN"):
                rows = pg.fetch_all(
                    CaanReport,
                    where=[CaanReport.data["report_type"].astext == report_type],
                )
                for data in rows:
                    if year and data.get("year") != year:
                        continue
                    results.append({
                        "id": data.get("id") or data.get("report_id"),
                        "report_type": report_type,
                        "period": data.get("period", ""),
                        "year": data.get("year"),
                        "quarter": data.get("quarter"),
                        "status": data.get("status", "completed"),
                        "generated_at": data.get("generated_at"),
                        "generated_by": data.get("generated_by"),
                    })
    except Exception as e:
        logger.error(f"Failed to list {report_type} reports: {e}")
        raise HTTPException(500, "Failed to list reports")

    if report_type == "quarterly":
        results.sort(key=lambda r: (r.get("year") or 0, r.get("quarter") or 0), reverse=True)
    else:
        results.sort(key=lambda r: r.get("year") or 0, reverse=True)
    return results


def _export_report_pdf(
    effective_tenant: Optional[str],
    report_type: str,
    report_id: str,
):
    data = _fetch_report(effective_tenant, report_id)
    if data is None:
        raise HTTPException(404, "Report not found")
    report_data = {"summary": data.get("summary", {}), "data": data.get("data", {})}
    period = data.get("period", "")
    tenant_name = _get_tenant_name(effective_tenant) if effective_tenant else None

    pdf_bytes = generate_report_pdf(report_data, report_type, period, tenant_name)
    filename = f"{report_type}_report_{data.get('period', report_id).replace(' ', '_')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )


# ── Generate Quarterly Report ──


@router.post("/quarterly", response_model=dict, status_code=status.HTTP_201_CREATED)
async def generate_quarterly_report(
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    tenant_id: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    if user.get("role") not in settings.CROSS_TENANT_ROLES:
        tenant_id = None
    effective_tenant = _effective_tenant(user, tenant_id)
    if user.get("role") not in settings.CROSS_TENANT_ROLES and not effective_tenant:
        raise HTTPException(403, "No tenant assigned")

    generator = ReportGenerator(effective_tenant)
    report_data = generator.generate_quarterly_report(year, quarter, user)
    now = datetime.now(timezone.utc)

    doc_data = {
        "tenant_id": effective_tenant,
        "report_type": ReportType.QUARTERLY.value,
        "period": report_data["period"],
        "year": year,
        "quarter": quarter,
        "status": ReportStatus.COMPLETED.value,
        "summary": report_data["summary"],
        "data": report_data["data"],
        "generated_at": now,
        "generated_by": user.get("uid"),
        "created_at": now,
        "updated_at": now,
    }

    doc_data = _save_report(doc_data, effective_tenant)
    return _to_report_response(doc_data)


@router.get("/quarterly", response_model=List[ReportListItem])
async def list_quarterly_reports(
    year: Optional[int] = Query(None),
    tenant_id: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    if user.get("role") not in settings.CROSS_TENANT_ROLES:
        tenant_id = None
    effective_tenant = _effective_tenant(user, tenant_id)
    return _list_reports(effective_tenant, "quarterly", year, user)


@router.get("/quarterly/{report_id}", response_model=dict)
async def get_quarterly_report(
    report_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    effective_tenant = _effective_tenant(user)
    try:
        data = _fetch_report(effective_tenant, report_id)
        if data is None:
            raise HTTPException(404, "Report not found")
        return _to_report_response(data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get report {report_id}: {e}")
        raise HTTPException(500, "Failed to get report")


@router.get("/quarterly/{report_id}/export")
async def export_quarterly_report(
    report_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    effective_tenant = _effective_tenant(user)
    try:
        return _export_report_pdf(effective_tenant, "quarterly", report_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export report {report_id}: {e}")
        raise HTTPException(500, "Failed to export report")


# ── Annual Report Endpoints ──


@router.post("/annual", response_model=dict, status_code=status.HTTP_201_CREATED)
async def generate_annual_report(
    year: int = Query(..., ge=2020, le=2100),
    tenant_id: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    if user.get("role") not in settings.CROSS_TENANT_ROLES:
        tenant_id = None
    effective_tenant = _effective_tenant(user, tenant_id)
    if user.get("role") not in settings.CROSS_TENANT_ROLES and not effective_tenant:
        raise HTTPException(403, "No tenant assigned")

    generator = ReportGenerator(effective_tenant)
    report_data = generator.generate_annual_report(year, user)
    now = datetime.now(timezone.utc)

    doc_data = {
        "tenant_id": effective_tenant,
        "report_type": ReportType.ANNUAL.value,
        "period": report_data["period"],
        "year": year,
        "quarter": None,
        "status": ReportStatus.COMPLETED.value,
        "summary": report_data["summary"],
        "data": report_data["data"],
        "generated_at": now,
        "generated_by": user.get("uid"),
        "created_at": now,
        "updated_at": now,
    }

    doc_data = _save_report(doc_data, effective_tenant)
    return _to_report_response(doc_data)


@router.get("/annual", response_model=List[ReportListItem])
async def list_annual_reports(
    year: Optional[int] = Query(None),
    tenant_id: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    if user.get("role") not in settings.CROSS_TENANT_ROLES:
        tenant_id = None
    effective_tenant = _effective_tenant(user, tenant_id)
    return _list_reports(effective_tenant, "annual", year, user)


@router.get("/annual/{report_id}", response_model=dict)
async def get_annual_report(
    report_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    effective_tenant = _effective_tenant(user)
    try:
        data = _fetch_report(effective_tenant, report_id)
        if data is None:
            raise HTTPException(404, "Report not found")
        return _to_report_response(data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get report {report_id}: {e}")
        raise HTTPException(500, "Failed to get report")


@router.get("/annual/{report_id}/export")
async def export_annual_report(
    report_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    effective_tenant = _effective_tenant(user)
    try:
        return _export_report_pdf(effective_tenant, "annual", report_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export report {report_id}: {e}")
        raise HTTPException(500, "Failed to export report")


# ── Response Helper ──


def _to_report_response(data: dict) -> dict:
    return {
        "id": data.get("id", ""),
        "tenant_id": data.get("tenant_id"),
        "report_type": data.get("report_type", ""),
        "period": data.get("period", ""),
        "year": data.get("year"),
        "quarter": data.get("quarter"),
        "status": data.get("status", "completed"),
        "summary": data.get("summary", {}),
        "data": data.get("data", {}),
        "generated_at": _serialize_dt(data.get("generated_at")),
        "generated_by": data.get("generated_by"),
        "file_url": data.get("file_url"),
        "created_at": _serialize_dt(data.get("created_at")),
        "updated_at": _serialize_dt(data.get("updated_at")),
    }


def _serialize_dt(val):
    if val and hasattr(val, "isoformat"):
        return val.isoformat()
    return val