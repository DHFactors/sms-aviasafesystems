# ============================================================================
# FILE: migrate_tenant_ids.py
# PATH: backend/scripts/migrate_tenant_ids.py
# PURPOSE: Reconcile `tenants.id` with the canonical uuid5('tenant:'+slug)
#          tenant id used across every tenant-scoped table. The tenants PK was
#          provisioned with a gen_random_uuid() default, so seeded/demo rows
#          (written under uuid5 of the slug) never matched their tenants
#          record — the data appeared "seeded to the wrong tenant".
#
#          This script rewrites each tenants row's id to uuid5('tenant:'+slug)
#          and reports a per-tenant inventory of the demo/operational rows that
#          become attributable to the tenant for the first time. Idempotent;
#          safe to re-run (no-op when already aligned).
#
# Usage:
#   $env:PYTHONPATH="backend"; python scripts/migrate_tenant_ids.py
# ============================================================================

import asyncio
import uuid

from sqlalchemy import text

from app.db.session import get_engine

# Namespace/name scheme must match app/db/ids.py tenant_uuid().
def tenant_uuid(slug: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"tenant:{slug}"))

# Tables carrying tenant_id that the report aggregates over.
_TENANT_SCOPED_TABLES = [
    "hazards", "cans", "caps", "reports", "surveys", "survey_responses",
    "risk_register", "barrier_register", "psoe_assessments", "psoe_findings",
    "flight_diversions", "state_risk_register", "regulatory_reports",
    "hazard_rca_entries", "hazard_assessments", "hazard_capas",
    "bow_tie_analyses", "verifications", "closures", "corrective_actions",
    "safety_deficiencies",
]


async def main() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        rows = (await conn.execute(
            text("SELECT id, slug FROM tenants ORDER BY slug")
        )).all()

        # Guard: the target ids must be unique before we start.
        targets = [tenant_uuid(slug) for _, slug in rows]
        dupes = {t for t in targets if targets.count(t) > 1}
        if dupes:
            raise SystemExit(f"collision in computed tenant ids: {dupes}")

        changed = 0
        for row_id, slug in rows:
            expected = tenant_uuid(slug)
            if str(row_id) == expected:
                print(f"  {slug:<16} already aligned ({expected})")
                continue
            res = await conn.execute(
                text("UPDATE tenants SET id = CAST(:tid AS uuid) WHERE slug = :slug AND id = :old")
                .bindparams(tid=uuid.UUID(expected), slug=slug, old=row_id)
            )
            if res.rowcount != 1:
                print(f"  {slug:<16} SKIPPED (guard did not match, rowcount={res.rowcount})")
                continue
            changed += 1
            print(f"  {slug:<16} re-keyed {row_id} -> {expected}")

        print(f"\n== tenants re-keyed: {changed} ==")

        # Inventory: rows now attributable to each tenant.
        for _, slug in rows:
            tid = tenant_uuid(slug)
            parts = []
            for table in _TENANT_SCOPED_TABLES:
                try:
                    n = (await conn.execute(text(
                        f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :tid"
                    )).bindparams(tid=uuid.UUID(tid))).scalar()
                    if n:
                        parts.append(f"{table}={n}")
                except Exception:
                    pass  # table absent in this DB — ignore
            print(f"  {slug:<16} {', '.join(parts) if parts else '(no rows)'}")

        # Any rows still hanging off a re-keyed (now orphaned) id?
        orphans = 0
        old_ids = {str(o) for o, _ in rows}
        current = {str(r[0]) for r in (await conn.execute(
            text("SELECT id FROM tenants")
        )).all()}
        stale = old_ids - current
        for table in _TENANT_SCOPED_TABLES:
            for oid in stale:
                try:
                    n = (await conn.execute(text(
                        f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :tid"
                    )).bindparams(tid=uuid.UUID(oid))).scalar()
                    if n:
                        print(f"  STALE {table} rows under {oid}: {n}")
                        orphans += n
                except Exception:
                    pass
        if orphans:
            print(f"\n  WARNING: {orphans} rows remain under stale tenant ids")
        else:
            print("\n  no rows left under stale tenant ids")

    await engine.dispose()


asyncio.run(main())