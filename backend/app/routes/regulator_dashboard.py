from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import io

from app.core.config import settings
from app.services.aggregation_service import AggregationService
from app.services import caan_audit
from app.services.data_governance import (
    USE_LIMITATION_STATEMENT,
    classification_header,
)
from app.middleware.auth import get_caan_user, get_current_user

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


class EscalationRequest(BaseModel):
    tenant_id: str = Field(..., description="Operator tenant to escalate visibility on")
    item_type: str = Field(..., description="e.g. 'hazard' | 'report' | 'cap'")
    item_id: str = Field(..., description="Identifier of the item to escalate")
    reason: str = Field(..., min_length=5)
    window_hours: int = Field(24, ge=1, le=720,
                              description="Temporary access window (default 24h; Q12.1)")


# In-memory escalation registry. Escalations are short-lived CAAN grants
# (Q12.1); a durable store is a deployment follow-up.
_ESCALATIONS: Dict[str, Dict[str, Any]] = {}


@router.get("/share/benchmark/{tenant_id}")
async def share_benchmark(
    tenant_id: str,
    tenant_ids: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Operator benchmark vs national average (Module C §6 / P3-12).

    CAAN may read any tenant; an operator may read only their own tenant."""
    role = (user or {}).get("role")
    if role not in settings.CROSS_TENANT_ROLES and user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403,
                            detail="Cross-tenant access requires a regulator role")
    tids = _default_tenant_ids(tenant_ids)
    if tenant_id not in tids:
        tids.append(tenant_id)
    caan_audit.log_caan_share(user, "benchmark", recipient=tenant_id, target_id=tenant_id)
    result = await _service().get_benchmarking(tenant_id, tids)
    if isinstance(result, dict):
        result.setdefault("use_limitation", USE_LIMITATION_STATEMENT)
    return result


@router.post("/share/escalate", status_code=201)
async def share_escalate(payload: EscalationRequest,
                         user: dict = Depends(get_caan_user)):
    """CAAN requests temporary escalated visibility on a specific item (§12 / P3-12)."""
    from datetime import timedelta
    import uuid as _uuid

    esc_id = str(_uuid.uuid4())
    now = datetime.now(timezone.utc)
    record = {
        "id": esc_id,
        "tenant_id": payload.tenant_id,
        "item_type": payload.item_type,
        "item_id": payload.item_id,
        "reason": payload.reason,
        "granted_by": user.get("email") or user.get("uid"),
        "granted_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=payload.window_hours)).isoformat(),
        "scope": "full_detail_minus_reporter_identity",
    }
    _ESCALATIONS[esc_id] = record
    caan_audit.log_caan_share(user, "escalation", recipient=payload.tenant_id,
                              target_id=esc_id, metadata={"reason": payload.reason})
    return {"status": "success", "data": record}


@router.get("/share/escalate/{escalation_id}")
async def get_escalation(escalation_id: str, user: dict = Depends(get_caan_user)):
    """Retrieve an escalated view (temporary CAAN grant) (§12 / P3-12)."""
    record = _ESCALATIONS.get(escalation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Escalation not found")
    expires = record.get("expires_at")
    if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        raise HTTPException(status_code=403, detail="Escalation grant has expired")
    caan_audit.log_caan_escalated_read(
        user, tenant_id=record["tenant_id"], target_id=escalation_id)
    return {"status": "success", "data": record}

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
    if isinstance(result, dict):
        result.setdefault("classification", "public")
        result.setdefault("use_limitation", USE_LIMITATION_STATEMENT)
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
    headers = {"Content-Disposition": "attachment; filename=regulator-report.pdf"}
    headers.update(classification_header("aggregate"))
    headers["X-Use-Limitation"] = USE_LIMITATION_STATEMENT
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)

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
    headers = {"Content-Disposition": "attachment; filename=regulator-data.xlsx"}
    headers.update(classification_header("aggregate"))
    headers["X-Use-Limitation"] = USE_LIMITATION_STATEMENT
    return StreamingResponse(io.BytesIO(excel_bytes), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)
