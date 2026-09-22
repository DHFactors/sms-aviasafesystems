from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
import io

from app.services.aggregation_service import AggregationService
from app.services import caan_audit
from app.middleware.auth import get_caan_user

router = APIRouter()

def get_tenant_ids_from_query(tenant_ids: Optional[str] = Query(None, description="Comma-separated tenant IDs")) -> List[str]:
    if tenant_ids:
        return [t.strip() for t in tenant_ids.split(",") if t.strip()]
    return []

def _default_tenant_ids(tenant_ids: Optional[str]) -> List[str]:
    tids = get_tenant_ids_from_query(tenant_ids)
    if not tids:
        # Default to all known tenants (mock for demo)
        tids = ["fixedwing", "rotarywing", "demoairport"]
    return tids

def _service() -> AggregationService:
    return AggregationService()

@router.get("/industry-averages")
async def industry_averages(
    tenant_ids: Optional[str] = Query(None),
    user: dict = Depends(get_caan_user),
):
    # Regulator sees aggregated data only - tenant isolation via aggregated view
    caan_audit.log_caan_read(user, "industry_averages", metadata={"tenant_ids": _default_tenant_ids(tenant_ids)})
    tids = _default_tenant_ids(tenant_ids)
    svc = _service()
    result = await svc.calculate_industry_averages(tids)
    return result

@router.get("/top-hazards")
async def top_hazards(
    tenant_ids: Optional[str] = Query(None),
    user: dict = Depends(get_caan_user),
):
    caan_audit.log_caan_read(user, "top_hazards")
    tids = _default_tenant_ids(tenant_ids)
    svc = _service()
    return await svc.get_top_hazards(tids)

@router.get("/risk-trends")
async def risk_trends(
    tenant_ids: Optional[str] = Query(None),
    user: dict = Depends(get_caan_user),
):
    caan_audit.log_caan_read(user, "risk_trends")
    tids = _default_tenant_ids(tenant_ids)
    svc = _service()
    return await svc.get_risk_trends(tids)

@router.get("/risk-register")
async def risk_register(
    tenant_ids: Optional[str] = Query(None),
    user: dict = Depends(get_caan_user),
):
    caan_audit.log_caan_read(user, "risk_register")
    tids = _default_tenant_ids(tenant_ids)
    svc = _service()
    return await svc.get_state_risk_register(tids)

@router.get("/benchmark/{tenant_id}")
async def benchmarking(
    tenant_id: str,
    tenant_ids: Optional[str] = Query(None),
    user: dict = Depends(get_caan_user),
):
    caan_audit.log_caan_read(user, "benchmark", target_id=tenant_id, tenant_id=tenant_id)
    tids = _default_tenant_ids(tenant_ids)
    svc = _service()
    return await svc.get_benchmarking(tenant_id, tids)

@router.get("/export/pdf")
async def export_pdf(
    tenant_ids: Optional[str] = Query(None),
    user: dict = Depends(get_caan_user),
):
    caan_audit.log_caan_read(user, "export_pdf")
    tids = _default_tenant_ids(tenant_ids)
    svc = _service()
    data = await svc.calculate_industry_averages(tids)
    pdf_bytes = svc.export_pdf_data(data)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=regulator-report.pdf"})

@router.get("/export/excel")
async def export_excel(
    tenant_ids: Optional[str] = Query(None),
    user: dict = Depends(get_caan_user),
):
    caan_audit.log_caan_read(user, "export_excel")
    tids = _default_tenant_ids(tenant_ids)
    svc = _service()
    data = await svc.calculate_industry_averages(tids)
    excel_bytes = svc.export_excel_data(data)
    return StreamingResponse(io.BytesIO(excel_bytes), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=regulator-data.xlsx"})
