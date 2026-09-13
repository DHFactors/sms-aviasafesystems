# ============================================================================
# FILE: reset_to_virgin.py
# PATH: backend/scripts/reset_to_virgin.py
# PURPOSE: Full reset to virgin state - OPERATOR-ONLY.
#
#   * Wipes every tenant-scoped row (tenants, operational registers,
#     surveys, PSOE, SPI/N-HRC, state risk, barriers, bow-ties, audit logs),
#     only DEMO regulator rows (is_demo = TRUE), and every Firebase Auth user
#     EXCEPT the super-admin.
#   * PRESERVES non-demo regulators (is_demo = FALSE) - state authorities
#     such as CAAN are shared reference data, not tenant-scoped, and are
#     never purgeable. If the regulators table lacks an is_demo column,
#     ALL regulator rows are preserved.
#   * Keeps: super-admin users row (tenant_id NULL), all static reference
#     tables (psoe_questions, ADREP/HFACS taxonomies + mappings), and - by
#     design - does NOT touch Firestore (deprecated).
#   * CLI-only. No HTTP endpoint.
#
# SAFETY GATES (all required):
#   1. DRY-RUN IS THE DEFAULT. Deletion requires BOTH --execute AND
#      --confirm-virgin-reset.
#   2. Before running, the script verifies the super-admin exists in BOTH
#      Firebase Auth (Admin SDK, by UID) AND the users table (by UID,
#      tenant_id IS NULL). If either check fails the script aborts.
#   3. Prints a before/after count table for every table it will clear.
#   4. Writes an audit marker to backend/logs/reset-virgin-<timestamp>.log
#      (actor email, actor UID, date, before/after counts).
#   5. No HTTP endpoint; standalone CLI.
#
# Usage (from backend/):
#   python scripts/reset_to_virgin.py                          # dry-run
#   python scripts/reset_to_virgin.py --skip-auth              # DB-only dry-run
#   python scripts/reset_to_virgin.py --execute --confirm-virgin-reset
#   python scripts/reset_to_virgin.py --database-url <url> --execute ...
# ============================================================================

from __future__ import annotations

import argparse
import logging
import os
import sys
import urllib.parse
from datetime import datetime, timezone

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

import psycopg2  # noqa: E402
import psycopg2.errors  # noqa: E402

DEFAULT_SUPER_ADMIN_UID = "hLXs4mvtf5bb1hRSifnh6HuUHpC2"
DEFAULT_SUPER_ADMIN_EMAIL = "ezondiza.dhf@gmail.com"

# Primary scope mirrors the operator list. Entries with '*' are queried-in and
# silently skipped when the table does not exist (same as audit_logs).
PRIMARY_SCOPE = [
    "hazards",
    "reports",
    "cans",
    "caps",
    "surveys",
    "survey_responses",
    "flight_diversions",
    "psoe_assessments",
    "psoe_findings",
    "psoe_responses",        # * may not exist yet
    "spi_calculations",      # *
    "spi_targets",           # *
    "nhrc_calculations",     # *
    "sram_assessments",      # *
    "risk_register",
    "barriers",              # mapped -> barrier_register
    "bowties",               # mapped -> bow_tie_* family
    "state_risk_categories",
    "regulators",            # demo-only wipe (is_demo=TRUE rows); non-demo preserved
    "tenants",
    "audit_logs",            # included only when the table exists
]

# Tenant-scoped rows referencing the primary scope (or carrying seeded tenant
# aggregates). Cleared so the target "all tenant-scoped tables: 0 rows" is met
# without leaving orphan FK children.
DEPENDENT_SCOPE = [
    "corrective_actions",
    "safety_deficiencies",
    "verifications",
    "closures",
    "hazard_rca_entries",
    "hazard_rca_factors",
    "hazard_assessments",
    "hazard_capas",
    "regulatory_reports",
    "state_risk_register",
    "caan_reports",
    "sms_maturity",
]

# Never touched. Only reported (counts must remain unchanged).
PRESERVED = [
    "psoe_questions",
    "icao_adrep_taxonomies",  # * may not exist yet
    "hfacs_nanocodes",        # *
    "hazard_adrep_mappings",  # *
    "hazard_hfacs_codes",     # *
    "report_adrep_mappings",  # *
    "report_hfacs_codes",     # *
]

ALIASES = {
    "barriers": ["barrier_register"],
    "bowties": [
        "bow_tie_analyses",
        "bow_tie_threats",
        "bow_tie_consequences",
        "bow_tie_controls",
    ],
}

# FK-safe order for the no-replica fallback (children before parents).
_FALLBACK_ORDER = [
    "hazard_rca_factors",
    "hazard_assessments",
    "hazard_capas",
    "hazard_rca_entries",
    "corrective_actions",
    "safety_deficiencies",
    "verifications",
    "closures",
    "bow_tie_controls",
    "bow_tie_consequences",
    "bow_tie_threats",
    "bow_tie_analyses",
    "barrier_register",
    "caps",
    "cans",
    "risk_register",
    "flight_diversions",
    "survey_responses",
    "surveys",
    "regulatory_reports",
    "state_risk_register",
    "psoe_findings",
    "psoe_assessments",
    "sms_maturity",
    "caan_reports",
    "state_risk_categories",
    "regulators",
    "hazards",
    "reports",
    "audit_logs",
    "tenants",
    "users",
    "psoe_responses",
    "spi_calculations",
    "spi_targets",
    "nhrc_calculations",
    "sram_assessments",
]

logger = logging.getLogger("reset_virgin")


def resolve_delete_tables():
    out = []
    for entry in PRIMARY_SCOPE + DEPENDENT_SCOPE:
        out.extend(ALIASES.get(entry) or [entry])
    return list(dict.fromkeys(out))


def get_existing(conn, tables):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = ANY(%s)",
            (list(tables),),
        )
        return {row[0] for row in cur.fetchall()}


def count_rows(conn, table):
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM "public"."%s"' % table)
        return cur.fetchone()[0]


def normalize_url(url):
    parts = urllib.parse.urlsplit(url)
    scheme = "postgresql" if parts.scheme in ("postgresql+asyncpg", "postgresql+psycopg2") else parts.scheme
    return urllib.parse.urlunsplit((scheme, parts.netloc, parts.path, "", parts.fragment))


def sanitize_url(url):
    parts = urllib.parse.urlsplit(url)
    netloc = parts.netloc
    if "@" in netloc:
        user, host = netloc.rsplit("@", 1)
        netloc = f"{user.split(':', 1)[0]}:****@{host}"
    return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def print_before_after(rows):
    width = max(len(r) for r in (rows or [""])) + 2
    for label, before, after in rows:
        print(f"  {label:<{width}}  before={str(before):<6} after={str(after):<6}")


def audit_log_path():
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return os.path.join("logs", f"reset-virgin-{ts}.log")


def write_audit(log_path, actor_email, actor_uid, mode, before, after):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write("AviaSAFE SMS - reset-to-virgin audit marker\n")
        fh.write(f"mode        : {mode}\n")
        fh.write(f"actor email : {actor_email}\n")
        fh.write(f"actor uid   : {actor_uid}\n")
        fh.write(f"date        : {datetime.now(timezone.utc).isoformat()}\n")
        for table in before:
            fh.write(f"{table} before= {before[table]!s:>8}  after= {after.get(table, '-'):>8}\n")
    print(f"\n[audit] marker written to {log_path}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="OPERATOR-ONLY full reset to virgin state. Dry-run by default.",
    )
    parser.add_argument("--execute", action="store_true",
                        help="Actually delete rows (dry-run is the default).")
    parser.add_argument("--confirm-virgin-reset", action="store_true",
                        help="Acknowledge 'full reset to virgin state' (required with --execute).")
    parser.add_argument("--skip-auth", action="store_true",
                        help="Skip the Firebase Auth user-deletion phase (still verifies the super-admin users row).")
    parser.add_argument("--database-url", default=None,
                        help="Override DATABASE_URL (e.g. a scratch database).")
    parser.add_argument("--super-admin-uid", default=DEFAULT_SUPER_ADMIN_UID)
    parser.add_argument("--super-admin-email", default=DEFAULT_SUPER_ADMIN_EMAIL)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(message)s", stream=sys.stderr)

    if args.execute != args.confirm_virgin_reset:
        print("Refusing: --execute and --confirm-virgin-reset must BOTH be present "
              "(and --confirm-virgin-reset alone does nothing).")
        return 1

    dry_run = not args.execute
    mode = "dry-run" if dry_run else "execute"

    db_url = args.database_url
    if not db_url:
        from app.core.config import settings
        db_url = settings.DATABASE_URL
    if not db_url:
        print("No DATABASE_URL configured. Pass --database-url or set DATABASE_URL.")
        return 1

    db_url = normalize_url(db_url)

    print("=" * 76)
    print(f"RESET-TO-VIRGIN  [{mode.upper()}]")
    print(f"  database target : {sanitize_url(db_url)}")
    print(f"  super-admin UID : {args.super_admin_uid}")
    print(f"  super-admin mail: {args.super_admin_email}")
    print(f"  firebase auth   : {'SKIPPED (deletion phase)' if args.skip_auth else 'ACTIVE'}")
    print("=" * 76)

    delete_tables = resolve_delete_tables()
    all_checked = delete_tables + ["users"] + PRESERVED

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
    except Exception as e:  # noqa: BLE001
        print(f"DB connection failed: {type(e).__name__}")
        logger.debug("connect error detail: %s", e)
        return 2

    existing = get_existing(conn, all_checked)
    missing = [t for t in all_checked if t not in existing]
    if missing:
        print(f"Note: tables absent in this schema (skipped): {', '.join(missing)}")
    present_delete = [t for t in delete_tables if t in existing]

    if "users" not in existing:
        print("ABORT: users table does not exist; cannot run the safety gate.")
        conn.close()
        return 2

    # -- Gate 2 (DB side): exactly one super-admin users row, tenant_id NULL ----
    with conn.cursor() as cur:
        cur.execute(
            "SELECT uid, email, role, tenant_id "
            "FROM users WHERE uid = %s AND tenant_id IS NULL",
            (args.super_admin_uid,),
        )
        super_rows = cur.fetchall()
    if len(super_rows) != 1:
        print(f"ABORT: expected exactly 1 super-admin users row (uid={args.super_admin_uid!r}, "
              f"tenant_id IS NULL); found {len(super_rows)}.")
        conn.close()
        return 2
    sr = super_rows[0]
    print(f"\n[gate] users row OK: uid={sr[0]} email={sr[1]} role={sr[2]}")

    # -- Gate 2 (Auth side), skipped only with --skip-auth ----------------------
    actor_email = args.super_admin_email
    if not args.skip_auth:
        try:
            from app.firebase import get_auth, initialize_firebase
            initialize_firebase()
            auth_user = get_auth().get_user(args.super_admin_uid)
            print(f"[gate] Firebase Auth OK: uid={auth_user.uid} email={auth_user.email} "
                  f"claims={dict(auth_user.custom_claims or {})}")
            actor_email = auth_user.email or args.super_admin_email
        except Exception as e:  # noqa: BLE001
            print(f"ABORT: Firebase Auth gate failed for uid {args.super_admin_uid}: {e}")
            conn.close()
            return 2
    else:
        print("[gate] Firebase Auth phase skipped (--skip-auth); users row verified only.")

    before = {t: count_rows(conn, t) for t in ["users"] + present_delete}
    preserved_before = {t: count_rows(conn, t) for t in PRESERVED if t in existing}

    # Non-demo regulators (state authorities, e.g. CAAN) are shared reference
    # data and are PRESERVED across the reset. Only is_demo=TRUE rows are wiped.
    reg_preserved_before = None
    has_reg_is_demo = False
    if "regulators" in existing:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name = 'regulators' AND column_name = 'is_demo'"
            )
            has_reg_is_demo = cur.fetchone()[0] > 0
        with conn.cursor() as cur:
            if has_reg_is_demo:
                cur.execute("SELECT COUNT(*) FROM regulators WHERE is_demo = FALSE")
            else:
                cur.execute("SELECT COUNT(*) FROM regulators")
            reg_preserved_before = cur.fetchone()[0]
        print(f"[preserve] regulators: keeping {reg_preserved_before} non-demo row(s) "
              f"(state authorities are shared reference data, not purgeable)")

    print("\n--- BEFORE ---")
    print_before_after([(t, before[t], "-") for t in ["users"] + present_delete])

    if dry_run:
        print("\nDRY RUN - no rows were modified.")
        print("Re-run with --execute --confirm-virgin-reset to perform the reset.")
        conn.close()
        return 0

    # -- Executable path: DB wipe inside one transaction -------------------------
    order = [t for t in _FALLBACK_ORDER if t in present_delete] + ["users"]
    use_replica = False
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL session_replication_role = replica")
        use_replica = True
        logger.debug("session_replication_role=replica (FK checks suspended)")
    except psycopg2.errors.InsufficientPrivilege:
        conn.rollback()
        logger.debug("replica role unavailable; falling back to FK-safe ordered deletes")

    try:
        with conn.cursor() as cur:
            for table in order:
                if table == "users":
                    cur.execute("DELETE FROM users WHERE uid <> %s", (args.super_admin_uid,))
                elif table == "regulators":
                    if has_reg_is_demo:
                        cur.execute('DELETE FROM "public"."regulators" WHERE is_demo = TRUE')
                else:
                    cur.execute('DELETE FROM "public"."%s"' % table)
        conn.commit()
        print("\n[wiped] DB transaction committed.")
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        print(f"ABORT: DB wipe failed, transaction rolled back: {e}")
        conn.close()
        return 3

    conn.autocommit = True
    with conn.cursor() as cur:
        for table in ["users"] + present_delete:
            try:
                cur.execute(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = %s AND column_name = 'id'",
                    (table,),
                )
                if not cur.fetchone():
                    continue
                cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
                seq = cur.fetchone()[0]
                if seq:
                    cur.execute("SELECT setval(%s, 1, false)", (seq,))
            except Exception:  # noqa: BLE001
                pass
    conn.autocommit = False

    after = {t: count_rows(conn, t) for t in ["users"] + present_delete}

    # -- Firebase Auth deletion (skipped with --skip-auth) ----------------------
    auth_before = auth_after = None
    if not args.skip_auth:
        auth = get_auth()
        pool = [u for u in auth.list_users().iterate_all() if u.uid != args.super_admin_uid]
        auth_before = len(pool)
        print(f"\n[auth] deleting {auth_before} Firebase Auth user(s), keeping {args.super_admin_uid}...")
        failed = 0
        for u in pool:
            try:
                auth.delete_user(u.uid)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"  FAILED {u.uid} {u.email}: {e}")
        remaining = [u for u in auth.list_users().iterate_all()]
        auth_after = len(remaining)
        print(f"[auth] pool before={auth_before} after={auth_after} failures={failed}")
        if failed:
            print("[auth] failures detected - inspect and re-run the auth phase.")

    print("\n--- AFTER ---")
    print_before_after([(t, before.get(t, "?"), after.get(t, "?"))
                        for t in ["users"] + present_delete])

    # -- Verification block ------------------------------------------------------
    verify_tables = ["users"] + present_delete
    verification = []
    for tbl in verify_tables:
        cnt = count_rows(conn, tbl)
        verification.append((tbl, cnt))
    print("\n--- VERIFICATION (virgin state) ---")
    virgin = True
    for tbl, cnt in verification:
        if tbl == "users":
            ok = cnt == 1
        elif tbl == "regulators":
            ok = cnt == reg_preserved_before
        else:
            ok = cnt == 0
        virgin = virgin and ok
        print(f"  {tbl:>28} count={cnt:<5} [{'OK' if ok else 'CHECK'}]")
    preserved_after = {t: count_rows(conn, t) for t in PRESERVED if t in existing}
    for t in PRESERVED:
        if t in existing:
            ok = preserved_after[t] == preserved_before[t]
            virgin = virgin and ok
            print(f"  {t:>28} count={preserved_after[t]:<5} [{'OK (unchanged)' if ok else 'CHECK'}]")

    conn.close()

    log_path = audit_log_path()
    write_audit(log_path, actor_email, args.super_admin_uid, mode,
                {**before, **preserved_before}, {**after, **preserved_after})

    if args.skip_auth:
        auth_note = "auth pool: SKIPPED (--skip-auth)"
    else:
        auth_note = f"auth pool: before={auth_before} after={auth_after}"
    print("\nVIRGIN STATE ACHIEVED" if virgin else "\nVERIFY: non-zero/CHANGED counts remain - inspect above.",
          f"({auth_note})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())