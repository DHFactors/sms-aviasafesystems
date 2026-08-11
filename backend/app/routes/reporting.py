from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from typing import Dict, Any, Optional, List
from loguru import logger

from app.models.reporting import ReportResponse, ReportListItem, ReportType, ReportStatus
from app.middleware.auth import get_current_user, get_tenant_user
from app.services.report_generator import ReportGenerator
from app.services.pdf_generator import generate_report_pdf
from app.firebase import get_tenant_collection, get_cross_tenant_collection
from app.core.config import settings

router = APIRouter()
REPORT_COLLECTION = "reporting"

TENANT_COLLECTION = "tenants"


def _get_tenant_name(tenant_id: str) -> Optional[str]:
    try:
        from app.firebase import get_db
        doc = get_db().collection(TENANT_COLLECTION).document(tenant_id).get()
        if doc.exists:
            return doc.to_dict().get("name") or doc.to_dict().get("icao") or tenant_id
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

    try:
        if effective_tenant:
            ref = get_tenant_collection(effective_tenant, REPORT_COLLECTION).add(doc_data)
        else:
            from app.firebase import get_db
            ref = get_db().collection("caan_reports").add(doc_data)
        doc_id = ref[1].id
        doc_data["id"] = doc_id
    except Exception as e:
        logger.error(f"Failed to save report: {e}")
        raise HTTPException(500, "Failed to save report")

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

    try:
        if effective_tenant:
            docs = get_tenant_collection(effective_tenant, REPORT_COLLECTION) \
                .where("report_type", "==", "quarterly").get()
        else:
            from app.firebase import get_db
            if user.get("role") in ("CAAN_SMD", "SUPER_ADMIN"):
                docs = get_db().collection("caan_reports") \
                    .where("report_type", "==", "quarterly").get()
            else:
                docs = []
    except Exception as e:
        logger.error(f"Failed to list quarterly reports: {e}")
        raise HTTPException(500, "Failed to list reports")

    results = []
    for doc in docs:
        data = doc.to_dict()
        if year and data.get("year") != year:
            continue
        results.append({
            "id": doc.id,
            "report_type": "quarterly",
            "period": data.get("period", ""),
            "year": data.get("year"),
            "quarter": data.get("quarter"),
            "status": data.get("status", "completed"),
            "generated_at": data.get("generated_at"),
            "generated_by": data.get("generated_by"),
        })
    results.sort(key=lambda r: (r.get("year") or 0, r.get("quarter") or 0), reverse=True)
    return results


@router.get("/quarterly/{report_id}", response_model=dict)
async def get_quarterly_report(
    report_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    effective_tenant = _effective_tenant(user)

    try:
        if effective_tenant:
            doc = get_tenant_collection(effective_tenant, REPORT_COLLECTION).document(report_id).get()
        else:
            from app.firebase import get_db
            doc = get_db().collection("caan_reports").document(report_id).get()

        if not doc.exists:
            raise HTTPException(404, "Report not found")
        data = doc.to_dict()
        data["id"] = doc.id
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
        if effective_tenant:
            doc = get_tenant_collection(effective_tenant, REPORT_COLLECTION).document(report_id).get()
        else:
            from app.firebase import get_db
            doc = get_db().collection("caan_reports").document(report_id).get()

        if not doc.exists:
            raise HTTPException(404, "Report not found")

        data = doc.to_dict()
        report_data = {"summary": data.get("summary", {}), "data": data.get("data", {})}
        period = data.get("period", "")
        tenant_name = _get_tenant_name(effective_tenant) if effective_tenant else None

        pdf_bytes = generate_report_pdf(report_data, "quarterly", period, tenant_name)
        filename = f"quarterly_report_{data.get('period', report_id).replace(' ', '_')}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
        )
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

    try:
        if effective_tenant:
            ref = get_tenant_collection(effective_tenant, REPORT_COLLECTION).add(doc_data)
        else:
            from app.firebase import get_db
            ref = get_db().collection("caan_reports").add(doc_data)
        doc_id = ref[1].id
        doc_data["id"] = doc_id
    except Exception as e:
        logger.error(f"Failed to save annual report: {e}")
        raise HTTPException(500, "Failed to save report")

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

    try:
        if effective_tenant:
            docs = get_tenant_collection(effective_tenant, REPORT_COLLECTION) \
                .where("report_type", "==", "annual").get()
        else:
            from app.firebase import get_db
            if user.get("role") in ("CAAN_SMD", "SUPER_ADMIN"):
                docs = get_db().collection("caan_reports") \
                    .where("report_type", "==", "annual").get()
            else:
                docs = []
    except Exception as e:
        logger.error(f"Failed to list annual reports: {e}")
        raise HTTPException(500, "Failed to list reports")

    results = []
    for doc in docs:
        data = doc.to_dict()
        if year and data.get("year") != year:
            continue
        results.append({
            "id": doc.id,
            "report_type": "annual",
            "period": data.get("period", ""),
            "year": data.get("year"),
            "quarter": None,
            "status": data.get("status", "completed"),
            "generated_at": data.get("generated_at"),
            "generated_by": data.get("generated_by"),
        })
    results.sort(key=lambda r: r.get("year") or 0, reverse=True)
    return results


@router.get("/annual/{report_id}", response_model=dict)
async def get_annual_report(
    report_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    effective_tenant = _effective_tenant(user)

    try:
        if effective_tenant:
            doc = get_tenant_collection(effective_tenant, REPORT_COLLECTION).document(report_id).get()
        else:
            from app.firebase import get_db
            doc = get_db().collection("caan_reports").document(report_id).get()

        if not doc.exists:
            raise HTTPException(404, "Report not found")
        data = doc.to_dict()
        data["id"] = doc.id
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
        if effective_tenant:
            doc = get_tenant_collection(effective_tenant, REPORT_COLLECTION).document(report_id).get()
        else:
            from app.firebase import get_db
            doc = get_db().collection("caan_reports").document(report_id).get()

        if not doc.exists:
            raise HTTPException(404, "Report not found")

        data = doc.to_dict()
        report_data = {"summary": data.get("summary", {}), "data": data.get("data", {})}
        period = data.get("period", "")
        tenant_name = _get_tenant_name(effective_tenant) if effective_tenant else None

        pdf_bytes = generate_report_pdf(report_data, "annual", period, tenant_name)
        filename = f"annual_report_{data.get('period', report_id).replace(' ', '_')}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export annual report {report_id}: {e}")
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
