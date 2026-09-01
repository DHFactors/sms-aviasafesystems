from fastapi import APIRouter

from app.api.v1.state_risk import router as state_risk_router
from app.api.v1.cron import router as cron_router
from app.api.v1.tenant_reports import router as tenant_reports_router
from app.api.v1.nhrc import router as nhrc_router
from app.api.v1.spi import router as spi_router

router = APIRouter()

router.include_router(state_risk_router, prefix="/state-risk", tags=["CAAN State Risk Oversight"])
router.include_router(cron_router, prefix="/cron", tags=["Cron & Scheduled Tasks"])
router.include_router(tenant_reports_router, prefix="/tenants", tags=["Tenant SMS & SRB Reporting"])
router.include_router(nhrc_router, tags=["N-HRC National High-Risk Categories"])
router.include_router(spi_router, tags=["SPI/SPT Safety Performance"])
