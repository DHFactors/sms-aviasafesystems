# ============================================================================
# FILE: tenants.py
# PATH: backend/app/api/v1/endpoints/tenants.py
# PURPOSE: CAAN / enterprise tenant onboarding endpoint.
#
#   POST /api/v1/tenants/onboard
#       Provisions a tenant (Firestore + admin Auth user), seeds its ICAO
#       hazard register into Firestore AND Supabase via the unified seeder,
#       then sends the admin welcome email. Body mirrors the self-service
#       registration model (organization_name, admin_full_name, admin_title,
#       email, password, classification) plus optional seeding knobs.
#
# Error mapping (mirrors app/routes/auth.py):
#   PermissionError -> 403, DisposableEmailError -> 400, DuplicateEmailError
#   -> 409, LookupError -> 404, ValueError -> 422, RuntimeError -> 500.
# ============================================================================

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.onboarding_service import onboard_tenant
from app.services.tenant_registration import (
    DisposableEmailError,
    DuplicateEmailError,
)

router = APIRouter()


class OnboardTenantRequest(BaseModel):
    organization_name: str = Field(..., min_length=2, max_length=120)
    admin_full_name: str = Field(..., min_length=2, max_length=120)
    admin_title: str = Field("Safety Manager", max_length=120)
    email: str = Field(..., max_length=254)
    password: str = Field(..., min_length=8, max_length=128)
    classification: str = Field("airline_fixed_wing", max_length=40)
    seed_count: int = Field(6, ge=0, le=50)
    seed_function: str | None = Field(None, max_length=8)
    priority_override: str | None = Field(None, pattern="^[HML]$")


@router.post("/onboard", status_code=201)
async def onboard(request: Request, body: OnboardTenantRequest):
    """Provision a tenant end-to-end and seed its ICAO hazard register."""
    try:
        result = await onboard_tenant(
            organization_name=body.organization_name.strip(),
            admin_full_name=body.admin_full_name.strip(),
            admin_title=body.admin_title.strip(),
            email=body.email.strip().lower(),
            password=body.password,
            classification=body.classification.strip(),
            seed_count=body.seed_count,
            seed_function=body.seed_function,
            priority_override=body.priority_override,
            request=request,
        )
    except DisposableEmailError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DuplicateEmailError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, **result}