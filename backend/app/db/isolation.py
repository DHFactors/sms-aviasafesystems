# ============================================================================
# FILE: isolation.py
# PATH: backend/app/db/isolation.py
# PURPOSE: Demo/beta data isolation. The shared Supabase cluster hosts both
#          production and demo datasets; the `is_demo` flag on the core tables
#          keeps them apart. This module is the single source of truth for the
#          scoping rule every read/write on those tables must honour.
# ============================================================================

from app.core.config import settings


def demo_scope() -> bool:
    """True when the running instance belongs to the non-production (demo /
    beta / staging / development) scope. Written rows carry is_demo=demo_scope()
    and every scoped read filters on it, so a shared database never leaks demo
    data to the production scope or vice versa."""
    return (settings.ENVIRONMENT or "production").strip().lower() != "production"