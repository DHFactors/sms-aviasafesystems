# ============================================================================
# FILE: migrate_audit_logs.py
# PATH: backend/scripts/migrate_audit_logs.py
# PURPOSE: Align the live `audit_logs` table with the ORM model / schema_init
#          DDL. The table was originally provisioned with an early divergent
#          shape (actor_email/timestamp, `detail` jsonb, no created_at), so
#          every ORM INSERT silently failed with "column ... does not exist"
#          and the admin audit trail was never persisted. Idempotent.
#
#          Target shape (matches db_models.AuditLog / schema_init):
#            id uuid PK default gen_random_uuid, action TEXT NOT NULL,
#            actor/target/target_type/target_id/detail/result/tenant_id/ip/
#            request_id TEXT, metadata_json JSONB default '{}'::jsonb,
#            created_at TIMESTAMPTZ NOT NULL default now()
#
# Usage:
#   $env:PYTHONPATH="backend"; python scripts/migrate_audit_logs.py
# ============================================================================

import asyncio

from sqlalchemy import text

from app.db.session import get_engine

_AUDIT_DDL = """
CREATE TABLE audit_logs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action        TEXT NOT NULL,
    actor         TEXT,
    target        TEXT,
    target_type   TEXT,
    target_id     TEXT,
    detail        TEXT,
    result        TEXT,
    tenant_id     TEXT,
    ip            TEXT,
    request_id    TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_logs_tenant  ON audit_logs (tenant_id);
CREATE INDEX ix_audit_logs_created ON audit_logs (created_at);
"""


async def table_shape(conn) -> str:
    rows = (
        await conn.execute(
            text("SELECT column_name FROM information_schema.columns "
                 "WHERE table_schema = 'public' AND table_name = 'audit_logs'")
        )
    ).all()
    return {r[0] for r in rows}


async def main() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        cols = await table_shape(conn)
        if "actor" in cols:
            print("audit_logs already in target shape; nothing to do")
            return
        count = (
            await conn.execute(text("SELECT count(*) FROM audit_logs"))
        ).scalar_one()
        if count:
            # Preserve legacy rows by mapping them onto the target columns.
            print(f"mapping {count} legacy audit_logs rows onto target column set")
            await conn.execute(text(
                "ALTER TABLE audit_logs ADD COLUMN actor TEXT, "
                "ADD COLUMN target_type TEXT, ADD COLUMN target_id TEXT, "
                "ADD COLUMN tenant_id TEXT, ADD COLUMN ip TEXT, "
                "ADD COLUMN request_id TEXT, "
                "ADD COLUMN metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb, "
                "ADD COLUMN created_at TIMESTAMPTZ"
            ))
            await conn.execute(text(
                "UPDATE audit_logs SET actor = actor_email, "
                "created_at = COALESCE(timestamp, now())"
            ))
            await conn.execute(text(
                "ALTER TABLE audit_logs ALTER COLUMN actor_email DROP NOT NULL, "
                "ALTER COLUMN detail TYPE TEXT USING detail::text, "
                "ALTER COLUMN created_at SET NOT NULL, "
                "ALTER COLUMN action SET NOT NULL"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant ON audit_logs (tenant_id);"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_audit_logs_created ON audit_logs (created_at);"
            ))
            print("legacy rows preserved (actor <- actor_email, created_at <- timestamp)")
        else:
            # Legacy table is empty (writes always failed) - recreate cleanly.
            print("recreating empty legacy audit_logs table in target shape")
            await conn.execute(text("DROP TABLE audit_logs"))
            for stmt in _AUDIT_DDL.strip().split(";"):
                if stmt.strip():
                    await conn.execute(text(stmt + ";"))


if __name__ == "__main__":
    asyncio.run(main())