# ============================================================================
# FILE: migrate_jsonb_defaults.py
# PATH: backend/scripts/migrate_jsonb_defaults.py
# PURPOSE: Firestore -> Supabase migration type hardening. asyncpg rejects a
#          bare varchar bound to a jsonb column (DatatypeMismatchError), so
#          every JSONB/JSON column in the public schema that lacks a default
#          gets one: '{}'::jsonb for object-shaped columns, '[]'::jsonb for
#          the array-shaped ones (action_items, root_causes, contributing_tenants,
#          human_factors, contributing_factors). Idempotent and data-driven from
#          information_schema (no per-field mapping to keep in sync).
#
#          The caps.ae_signature / caps.closed_signature Text <-> jsonb mismatch
#          that produced the reported INSERT failures is fixed at the model
#          (db_models.py). This script only adds the defaults so INSERTs that
#          omit JSONB columns land as '{}'/'[]' instead of NULL.
#
# Usage:
#   $env:PYTHONPATH="backend"; python scripts/migrate_jsonb_defaults.py
# ============================================================================

import asyncio

from sqlalchemy import text

from app.db.session import get_engine

# Array-shaped JSONB columns (seeder/docs that omit them should end up []).
_ARRAY_COLUMNS = frozenset(
    {
        "action_items",
        "root_causes",
        "human_factors",
        "contributing_factors",
        "contributing_tenants",
        "operator_tenant_ids",
    }
)


async def main() -> None:
    lookup = text(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND data_type IN ('jsonb', 'json')
          AND column_default IS NULL
        ORDER BY table_name, ordinal_position
        """
    )
    engine = get_engine()
    async with engine.begin() as conn:
        rows = (await conn.execute(lookup)).all()
        if not rows:
            print("no JSONB columns missing a default; nothing to do")
            return
        for table, column in rows:
            default = "'[]'::jsonb" if column in _ARRAY_COLUMNS else "'{}'::jsonb"
            alter = text(
                f'ALTER TABLE "{table}" ALTER COLUMN "{column}" SET DEFAULT {default}'
            )
            await conn.execute(alter)
            print(f"{table}.{column} -> DEFAULT {default}")


if __name__ == "__main__":
    asyncio.run(main())