# ============================================================================
# FILE: reports.py (Unified Router)
# PATH: backend/app/routes/reports.py
# PURPOSE: Unified Reports router — consolidates operational (VSR/MOR) and
#          aggregated (Quarterly/Annual) reporting under /api/v1/reports.
#          Single entry point for all reporting; keeps legacy prefixes via
#          main.py for backward compat. New unified sub-paths
#          /occurrences/* and /aggregated/* are also exposed (hidden from
#          schema to avoid duplicate operation IDs).
# ============================================================================

from fastapi import APIRouter

from app.routes import occurrence_reports
from app.routes import reporting

router = APIRouter()

# Primary (legacy) — preserves existing frontend paths:
#   POST /api/v1/reports/      (VSR), /mor, /vsr, GET / etc.
#   POST /api/v1/reporting/quarterly etc. via separate mount in main.py
router.include_router(occurrence_reports.router, tags=["Reports — Occurrences"])
router.include_router(reporting.router, tags=["Reports — Aggregated"])

# Unified sub-paths (new) — also available, hidden from schema to avoid dup IDs
router.include_router(occurrence_reports.router, prefix="/occurrences", tags=["Reports — Occurrences (unified)"], include_in_schema=False)
router.include_router(reporting.router, prefix="/aggregated", tags=["Reports — Aggregated (unified)"], include_in_schema=False)
