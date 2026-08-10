# ============================================================================
# FILE: surveys.py
# PATH: backend/app/routes/surveys.py
# PURPOSE: Survey submission endpoint. Accepts anonymous and authenticated
#          submissions, validates answers against the master question contract,
#          computes ICAO pillar scores server-side, and persists both the scored
#          `surveys` doc (dashboards) and the raw `responses` doc (audit).
# ============================================================================

from typing import Any, Dict, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from loguru import logger

from app.core.config import settings
from app.firebase import get_db
from app.middleware.auth import get_current_user
from app.middleware.rate_limit import rate_limit
from app.services.audit_service import log_audit, request_context
from app.services.survey_scoring import (
    SURVEY_VERSION,
    compute_overall_maturity,
    compute_percentage_score,
    compute_pillar_scores,
    compute_question_scores,
    validate_answers,
)

router = APIRouter()

optional_bearer = HTTPBearer(auto_error=False)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
) -> Optional[Dict[str, Any]]:
    """Return the authenticated user when a Bearer token is supplied.

    Anonymous submissions (no Authorization header) are allowed because the
    public survey page must remain usable without a login. A supplied but
    invalid token is still rejected with 401.
    """
    if credentials is None:
        return None
    return await get_current_user(credentials)


class SurveySubmission(BaseModel):
    tenantId: str = Field(..., min_length=1, description="Tenant id (e.g. tara-air)")
    respondentId: Optional[str] = Field(None, description="Optional respondent identifier")
    answers: Dict[str, Any] = Field(..., description="Question id -> answer map")
    department: Optional[str] = None
    employee_category: Optional[str] = None
    years_experience: Optional[str] = None
    language: Optional[str] = Field("en", max_length=8)


def _persist_tenant_survey(
    db, tenant_id: str, survey_doc: Dict[str, Any], response_doc: Dict[str, Any]
) -> str:
    """Write the scored survey + raw response doc, returning the survey id."""
    tenant_ref = db.collection(settings.FIREBASE_COLLECTION_TENANTS).document(tenant_id)
    result = tenant_ref.collection("surveys").add(survey_doc)
    survey_id = result[1].id if isinstance(result, tuple) else result.id
    tenant_ref.collection("responses").add(response_doc)
    return survey_id


@router.post("/", status_code=status.HTTP_201_CREATED)
@rate_limit("survey_submit")
async def submit_survey(
    request: Request,
    payload: SurveySubmission,
    user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    """Submit an ICAO-aligned SMS survey response.

    The response is validated against the master question contract, scored
    into the four ICAO pillars (1-5) server-side, written to both
    `tenants/{id}/surveys` (scored, consumed by the airline + CAAN SMS maturity
    dashboards) and `tenants/{id}/responses` (raw, for audit).
    """
    tenant_id = payload.tenantId.strip()
    if not tenant_id:
        raise HTTPException(status_code=422, detail="tenantId is required")

    # An authenticated user with a tenant may only submit to their own tenant
    # (cross-tenant roles such as CAAN_SMD may submit anywhere).
    if user:
        user_tenant = user.get("tenant_id")
        if user_tenant and user_tenant != tenant_id:
            if user.get("role") not in settings.CROSS_TENANT_ROLES:
                raise HTTPException(
                    status_code=403,
                    detail="tenantId does not match the authenticated user's tenant",
                )
        audit_user = payload.respondentId or user.get("email")
    else:
        audit_user = payload.respondentId or "anonymous"

    # Validate the tenant exists.
    try:
        tenant_snap = (
            get_db().collection(settings.FIREBASE_COLLECTION_TENANTS)
            .document(tenant_id).get()
        )
    except Exception as e:
        logger.warning(f"Survey tenant lookup failed for {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail="Survey storage unavailable")
    if not tenant_snap.exists:
        raise HTTPException(status_code=400, detail=f"Unknown tenant: {tenant_id}")

    # Validate answers against the master question contract.
    errors = validate_answers(payload.answers)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "message": "Survey validation failed",
                "errors": errors,
            },
        )

    pillar_scores = compute_pillar_scores(payload.answers)
    overall = compute_overall_maturity(pillar_scores)
    question_scores = compute_question_scores(payload.answers)
    now = datetime.now(timezone.utc)

    survey_doc: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "tenantId": tenant_id,
        "submitted_at": now,
        "submittedAt": now,
        "respondent_id": payload.respondentId,
        "respondentId": payload.respondentId,
        "department": payload.department,
        "employee_category": payload.employee_category,
        "years_experience": payload.years_experience,
        "language_used": payload.language,
        "survey_version": SURVEY_VERSION,
        "seed_version": None,
        "answers": payload.answers,
        "question_scores": question_scores,
        "questionScores": question_scores,
        "safety_policy": pillar_scores["safety_policy"],
        "safety_risk_management": pillar_scores["safety_risk_management"],
        "safety_assurance": pillar_scores["safety_assurance"],
        "safety_promotion": pillar_scores["safety_promotion"],
        "overall_sms_maturity": overall,
        "overallSMSMaturity": overall,
        "pillarScores": pillar_scores,
        "overall_score_pct": compute_percentage_score(overall),
    }

    response_doc: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "tenantId": tenant_id,
        "respondent_id": payload.respondentId,
        "respondentId": payload.respondentId,
        "answers": payload.answers,
        "department": payload.department,
        "employee_category": payload.employee_category,
        "years_experience": payload.years_experience,
        "language_used": payload.language,
        "submitted_at": now,
        "submittedAt": now,
        "survey_version": SURVEY_VERSION,
    }

    try:
        survey_id = _persist_tenant_survey(
            get_db(), tenant_id, survey_doc, response_doc
        )
    except Exception as e:
        logger.error(f"Failed to persist survey for tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to persist survey")

    ip, request_id = request_context(request)
    log_audit(
        action="SURVEY_SUBMITTED",
        user=audit_user,
        tenant_id=tenant_id,
        target_type="survey",
        target_id=survey_id,
        ip=ip,
        request_id=request_id,
        metadata={
            "department": payload.department,
            "language": payload.language,
            "overall_sms_maturity": overall,
        },
    )

    return {
        "status": "success",
        "data": {
            "id": survey_id,
            "tenant_id": tenant_id,
            "overall_sms_maturity": overall,
            "overall_score_pct": compute_percentage_score(overall),
            "pillar_scores": pillar_scores,
        },
    }
