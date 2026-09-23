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


# ============================================================================
# Permanent pilot tenants — must never be purged. See B.1 guard wiring in
# backend/scripts/reset_to_virgin.py, backend/scripts/seed_demo_data.py and
# backend/tests/_mbb.py. `is_demo` is reserved for ephemeral test artifacts
# (hash-like slugs); pilot tenants carry is_demo=FALSE.
# ============================================================================

PERMANENT_TENANT_SLUGS = frozenset({
    "sita-air",
    "air-dynasty",
    "saurya-airlines",
    "caan",
})

# Login emails owned by the permanent pilot tenants (used by the users-table
# and Firebase Auth phases of purge scripts; the CAAN user is cross-tenant).
PERMANENT_PILOT_EMAILS = frozenset({
    "safety@sitaair.com.np",
    "ae@sitaair.com.np",
    "camo@sitaair.com.np",
    "145@sitaair.com.np",
    "ops@sitaair.com.np",
    "safety@air-dynasty.com.np",
    "ae@air-dynasty.com.np",
    "camo@air-dynasty.com.np",
    "145@air-dynasty.com.np",
    "ops@air-dynasty.com.np",
    "safety@saurya.com.np",
    "ae@saurya.com.np",
    "camo@saurya.com.np",
    "145@saurya.com.np",
    "ops@saurya.com.np",
    "smd@caanepal.gov.np",
})


def is_permanent_tenant_slug(slug) -> bool:
    """True when `slug` belongs to a permanent pilot tenant."""
    return str(slug or "").strip().lower() in PERMANENT_TENANT_SLUGS


def pilot_slug_exclusion(column: str, slugs=PERMANENT_TENANT_SLUGS):
    """Build a psycopg2 WHERE fragment excluding permanent pilot tenants.

    Returns (fragment, params), e.g. for column="slug":
      ("slug NOT IN (%s,%s,%s,%s)", ["sita-air", ...]).
    Used by purge/reset scripts so pilot rows are never deleted.
    """
    ordered = sorted(slugs)
    placeholders = ",".join(["%s"] * len(ordered))
    return f"{column} NOT IN ({placeholders})", list(ordered)