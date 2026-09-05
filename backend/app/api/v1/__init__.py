# ============================================================================
# backend/app/api/v1/__init__.py
# PURPOSE: API v1 package. Router assembly lives in router.py (mounted at
#          /api/v1 in app/main.py); feature routers are re-exported here for
#          discoverability.
# ============================================================================

from app.api.v1.endpoints.sram import router as sram_router

__all__ = ["sram_router"]