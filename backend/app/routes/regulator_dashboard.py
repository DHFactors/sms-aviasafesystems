from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
import io

from app.db.abstract_repository import AbstractRepository
from app.db.firestore_repository import FirestoreRepository
from app.services.aggregation_service import AggregationService
from app.middleware.auth import get_current_user

router = APIRouter()

def get_repository() -> AbstractRepository:
    return FirestoreRepository()

def get_tenant_ids_from_query(tenant_ids: Optional[str] = Query(None, description="Comma-separated tenant IDs")) -> List[str]:
    if tenant_ids:
        return [t.strip() for t in tenant_ids.split(",") if t.strip()]
    return []

@router.get("/industry-averages")
async def industry_averages(
    tenant_ids: Optional[str] = Query(None),
    repository: AbstractRepository = Depends(get_repository),
    user: dict = Depends(get_current_user),
):
    # Regulator sees aggregated data only - tenant isolation via aggregated view
    tids = get_tenant_ids_from_query(tenant_ids)
    if not tids:
        # Default to all known tenants (mock for demo)
        tids = ["fixedwing", "rotarywing", "demoairport"]
    svc = AggregationService(repository=repository)
    result = await svc.calculate_industry_averages(tids)
    return result

@router.get("/top-hazards")
async def top_hazards(
    tenant_ids: Optional[str] = Query(None),
    repository: AbstractRepository = Depends(get_repository),
    user: dict = Depends(get_current_user),
):
    tids = get_tenant_ids_from_query(tenant_ids)
    if not tids:
        tids = ["fixedwing", "rotarywing", "demoairport"]
    svc = AggregationService(repository=repository)
    return await svc.get_top_hazards(tids)

@router.get("/risk-trends")
async def risk_trends(
    tenant_ids: Optional[str] = Query(None),
    repository: AbstractRepository = Depends(get_repository),
    user: dict = Depends(get_current_user),
):
    tids = get_tenant_ids_from_query(tenant_ids)
    if not tids:
        tids = ["fixedwing", "rotarywing", "demoairport"]
    svc = AggregationService(repository=repository)
    return await svc.get_risk_trends(tids)

@router.get("/risk-register")
async def risk_register(
    tenant_ids: Optional[str] = Query(None),
    repository: AbstractRepository = Depends(get_repository),
    user: dict = Depends(get_current_user),
):
    tids = get_tenant_ids_from_query(tenant_ids)
    if not tids:
        tids = ["fixedwing", "rotarywing", "demoairport"]
    svc = AggregationService(repository=repository)
    return await svc.get_state_risk_register(tids)

@router.get("/benchmark/{tenant_id}")
async def benchmarking(
    tenant_id: str,
    tenant_ids: Optional[str] = Query(None),
    repository: AbstractRepository = Depends(get_repository),
    user: dict = Depends(get_current_user),
):
    tids = get_tenant_ids_from_query(tenant_ids)
    if not tids:
        tids = ["fixedwing", "rotarywing", "demoairport"]
    svc = AggregationService(repository=repository)
    return await svc.get_benchmarking(tenant_id, tids)

@router.get("/export/pdf")
async def export_pdf(
    tenant_ids: Optional[str] = Query(None),
    repository: AbstractRepository = Depends(get_repository),
    user: dict = Depends(get_current_user),
):
    tids = get_tenant_ids_from_query(tenant_ids)
    if not tids:
        tids = ["fixedwing", "rotarywing", "demoairport"]
    svc = AggregationService(repository=repository)
    data = await svc.calculate_industry_averages(tids)
    pdf_bytes = svc.export_pdf_data(data)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=regulator-report.pdf"})

@router.get("/export/excel")
async def export_excel(
    tenant_ids: Optional[str] = Query(None),
    repository: AbstractRepository = Depends(get_repository),
    user: dict = Depends(get_current_user),
):
    tids = get_tenant_ids_from_query(tenant_ids)
    if not tids:
        tids = ["fixedwing", "rotarywing", "demoairport"]
    svc = AggregationService(repository=repository)
    data = await svc.calculate_industry_averages(tids)
    excel_bytes = svc.export_excel_data(data)
    return StreamingResponse(io.BytesIO(excel_bytes), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=regulator-data.xlsx"})
