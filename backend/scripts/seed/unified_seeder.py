# ============================================================================
# FILE: unified_seeder.py
# PATH: backend/scripts/seed/unified_seeder.py
# PURPOSE: Unified ICAO hazard seeder. Seeds the CAAN Chapter 2.1 hazard
#          register for a tenant into BOTH backends simultaneously:
#            * Firestore  — tenants/{tenant_id}/hazards/{doc_id}
#            * Supabase   — the relational `hazards` table (source of truth)
#          Uses the ICAO templates library (icao_templates.py) so every seeded
#          record carries the full 14-field CAAN record and a new-format
#          reference: {FUNCTION}/{SEQ}/{PRIORITY}/{YEAR} (e.g. OPS/001/M/2026).
#
#          Reusable by the tenant onboarding service (onboarding_service.py).
#
# Usage:
#   python -m scripts.seed.unified_seeder --tenant buddha-air --count 8
#   python -m scripts.seed.unified_seeder --tenant buddha-air --function OPS --priority H
#   python -m scripts.seed.unified_seeder --tenant buddha-air --count 4 --target firestore
#   python -m scripts.seed.unified_seeder --tenant buddha-air --dry-run
#   python -m scripts.seed.unified_seeder --all --count 6
#   python -m scripts.seed.unified_seeder --regulator caan --count 6 --dry-run
# ============================================================================

import argparse
import json
import os
import sys
from asyncio import run
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(BACKEND, ".env"), override=False)

from loguru import logger  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.firebase import initialize_firebase, get_db  # noqa: E402
from app.db.db_models import Hazard  # noqa: E402
from app.db.ids import register_tenant  # noqa: E402
from app.db.session import session_scope  # noqa: E402
from app.models.hazard import revalue_taxonomy  # noqa: E402
from app.services.hazard_service import (  # noqa: E402
    generate_hazard_id,
    parse_hazard_id,
)
from scripts.seed.icao_templates import (  # noqa: E402
    FUNCTION_ORDER,
    templates_for_function,
    stamp_dates,
)

SEED_CREATOR = "unified-seeder"
SEED_VERSION = "icao-unified-1"

# Keep ONLY production-setup tenants. Production-setup resolution and the CLI
# restrict seeding to this set; no removed/legacy tenant can be re-seeded.
PRODUCTION_TENANTS = ["fixedwing", "rotarywing", "demoairport", "demostate", "sita-air", "sourya-air"]


def _max_sequences(db: Any, tenant_slug: str) -> Dict[str, Dict[int, int]]:
    """Return {function: {year: max_seq}} scoped to (function, year).

    Query business references directly from Firestore so the seeder stays
    consistent across both stores (Firestore remains the register of record
    for the marker collections).
    """
    out: Dict[str, Dict[int, int]] = {}
    fb = get_db()
    try:
        docs = (
            fb.collection(settings.FIREBASE_COLLECTION_TENANTS)
            .document(tenant_slug)
            .collection("hazards")
            .stream()
        )
        for doc in docs:
            data = doc.to_dict() or {}
            fields = parse_hazard_id(str(data.get("hazard_id") or ""))
            if not fields:
                continue
            fn = fields["function"]
            out.setdefault(fn, {})
            out[fn][fields["year"]] = max(out[fn].get(fields["year"], 0), fields["seq"])
    except Exception as e:
        logger.warning(f"Failed to scan Firestore sequences for {tenant_slug}: {e}")
    return out


def _build_hazard_rows(
    tenant_id: str,
    *,
    count: int,
    function: Optional[str] = None,
    priority_override: Optional[str] = None,
    year: Optional[int] = None,
    max_seqs: Optional[Dict[str, Dict[int, int]]] = None,
) -> List[Dict[str, Any]]:
    """Build the ICAO hazard records for a tenant (deterministic ordering)."""
    year = year or datetime.now(timezone.utc).year
    max_seqs = max_seqs or {}
    rows: List[Dict[str, Any]] = []

    if function:
        funcs = [function.upper() if function.upper() in FUNCTION_ORDER else "OPS"]
    else:
        funcs = FUNCTION_ORDER

    per_function = max(1, (count + len(funcs) - 1) // len(funcs))
    remaining = count

    for fn in funcs:
        templates = templates_for_function(fn)
        seq = max((max_seqs.get(fn, {}).get(year, 0)), 0)
        for _ in range(per_function):
            if remaining <= 0:
                break
            for tmpl in templates:
                if remaining <= 0:
                    break
                template = stamp_dates(tmpl)
                seq += 1
                priority = (priority_override or template.get("priority") or "M").upper()
                hazard_id = generate_hazard_id(fn, priority, year, seq)
                taxonomy = revalue_taxonomy(template.get("taxonomy"))
                rows.append({
                    "tenant_id": tenant_id,
                    "hazard_id": hazard_id,
                    "function": fn,
                    "title": template["title"],
                    "description": template["description"],
                    "source": template["source"],
                    "source_id": f"icao-tpl-{fn.lower()}-{seq:03d}",
                    "threat": template["threat"],
                    "top_event": template["top_event"],
                    "consequence": template["consequence"],
                    "recommended_action": template["recommended_action"],
                    "corrective_action_flag": bool(template.get("corrective_action_flag", False)),
                    "srm_flag": bool(template.get("srm_flag", False)),
                    "taxonomy": taxonomy,
                    "priority": priority,
                    "remarks": template.get("remarks"),
                    "priority_date": template["priority_date"],
                    "status_date": template["status_date"],
                    "status": "Open",
                    "is_demo": False,
                    "created_by": SEED_CREATOR,
                    "created_at": template["priority_date"],
                    "updated_at": template["priority_date"],
                })
                remaining -= 1
    return rows


async def seed_tenant_hazards(
    tenant_id: str,
    *,
    count: int = 6,
    function: Optional[str] = None,
    priority_override: Optional[str] = None,
    year: Optional[int] = None,
    target: str = "both",
    dry_run: bool = False,
    is_demo: bool = False,
) -> Dict[str, Any]:
    """Seed ICAO hazard records for `tenant_id` into Firestore + Supabase.

    Args:
        tenant_id: tenant slug (e.g. "buddha-air").
        count: number of hazard records to create.
        function: restrict seeding to one ICAO function code.
        priority_override: force an H/M/L priority across seeded records.
        year: reference year (defaults to current year).
        target: "firestore", "supabase", or "both".
        dry_run: compute only, write nothing.
        is_demo: mark rows as demo data (only meaningful for Supabase writes).
    """
    tid_slug = (tenant_id or "").strip()
    if not tid_slug:
        raise ValueError("tenant_id is required")

    max_seqs = _max_sequences(get_db(), tid_slug)
    rows = _build_hazard_rows(
        tid_slug,
        count=count,
        function=function,
        priority_override=priority_override,
        year=year,
        max_seqs=max_seqs,
    )
    if not rows:
        return {"tenant_id": tid_slug, "seeded": 0, "dry_run": dry_run}

    if dry_run:
        first = rows[0]["hazard_id"]
        return {
            "tenant_id": tid_slug,
            "seeded": len(rows),
            "dry_run": True,
            "sample": first,
        }

    firestore_count = 0
    supabase_count = 0
    now = datetime.now(timezone.utc)

    if target in ("firestore", "both"):
        fb = get_db()
        coll = (
            fb.collection(settings.FIREBASE_COLLECTION_TENANTS)
            .document(tid_slug)
            .collection("hazards")
        )
        for row in rows:
            doc = dict(row)
            doc["tenant_id"] = tid_slug
            doc["created_at"] = row["created_at"]
            doc["updated_at"] = row["updated_at"]
            doc["priority_date"] = row["priority_date"]
            doc["status_date"] = row["status_date"]
            doc["seed_version"] = SEED_VERSION
            coll.document(f"haz-{row['hazard_id'].replace('/', '-')}").set(doc)
        firestore_count = len(rows)
        logger.info(f"Seeded {firestore_count} hazards to Firestore for {tid_slug}")

    if target in ("supabase", "both"):
        tid_uuid = register_tenant(tid_slug)
        async with session_scope() as session:
            for row in rows:
                session.add(Hazard(
                    tenant_id=tid_uuid,
                    hazard_id=row["hazard_id"],
                    function=row["function"],
                    title=row["title"],
                    description=row["description"],
                    source=row["source"],
                    source_id=row["source_id"],
                    occurrence_type=row.get("occurrence_type"),
                    taxonomy=row["taxonomy"],
                    threat=row["threat"],
                    top_event=row["top_event"],
                    consequence=row["consequence"],
                    risk_index=row.get("risk_index"),
                    risk_level=row.get("risk_level"),
                    priority=row["priority"],
                    recommended_action=row["recommended_action"],
                    corrective_action=row.get("corrective_action"),
                    corrective_action_flag=row["corrective_action_flag"],
                    srm_flag=row["srm_flag"],
                    status=row["status"],
                    priority_date=row["priority_date"],
                    status_date=row["status_date"],
                    remarks=row["remarks"],
                    is_demo=is_demo,
                    created_by=SEED_CREATOR,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                ))
        supabase_count = len(rows)
        logger.info(f"Seeded {supabase_count} hazards to Supabase for {tid_slug}")

    return {
        "tenant_id": tid_slug,
        "seeded": len(rows),
        "firestore": firestore_count,
        "supabase": supabase_count,
        "dry_run": dry_run,
    }


def _production_tenants(regulator_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Operator tenants created from /admin/production-setup.html.

    Walks the `regulators` collection (each State Regulator declares its
    `operator_tenant_ids`) and also picks up tenants tagged
    `regulator_id == <id>` that are not yet listed in the array. Returns
    ``[{id, regulator_id, regulator_name, country}]``.
    """
    db = get_db()
    seen: List[str] = []
    rows: List[Dict[str, Any]] = []
    try:
        regs = db.collection(settings.FIREBASE_COLLECTION_REGULATORS).stream()
        for reg_snap in regs:
            reg = reg_snap.to_dict() or {}
            if regulator_id and reg_snap.id != regulator_id:
                continue
            reg_rid = reg_snap.id
            reg_name = reg.get("name") or reg_rid
            reg_country = reg.get("country_name") or reg.get("country") or ""

            candidate_ids = [oid for oid in (reg.get("operator_tenant_ids") or []) if oid]
            try:
                tagged = (
                    db.collection(settings.FIREBASE_COLLECTION_TENANTS)
                    .where("regulator_id", "==", reg_rid)
                    .stream()
                )
                for snap in tagged:
                    if snap.id not in candidate_ids:
                        candidate_ids.append(snap.id)
            except Exception:
                pass

            for oid in candidate_ids:
                if oid in PRODUCTION_TENANTS and oid not in seen:
                    seen.append(oid)
                    rows.append({
                        "id": oid,
                        "regulator_id": reg_rid,
                        "regulator_name": reg_name,
                        "country": reg_country,
                    })
    except Exception as e:
        logger.warning(f"Failed to read production-setup operators: {e}")
    return rows


async def seed_from_production_setup(
    *,
    count: int = 6,
    function: Optional[str] = None,
    priority_override: Optional[str] = None,
    year: Optional[int] = None,
    target: str = "both",
    dry_run: bool = False,
    is_demo: bool = False,
    regulator_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Seed every operator tenant created from production-setup.html.

    Each resolved tenant (see ``_production_tenants``) gets the standard
    ICAO-compliant hazard register via ``seed_tenant_hazards``, so the same
    14-field CAAN records land in Firestore + Supabase for every operator.
    """
    targets = _production_tenants(regulator_id)
    if not targets:
        return {
            "tenants": [],
            "seeded": 0,
            "dry_run": dry_run,
            "notice": (
                "No production-setup tenants found. Create a State Regulator and at "
                "least one operator tenant in /admin/production-setup.html first."
            ),
        }

    results: List[Dict[str, Any]] = []
    total = 0
    for row in targets:
        res = await seed_tenant_hazards(
            row["id"],
            count=count,
            function=function,
            priority_override=priority_override,
            year=year,
            target=target,
            dry_run=dry_run,
            is_demo=is_demo,
        )
        results.append(res)
        total += int(res.get("seeded") or 0)
        logger.info(f"Production seed [{row['regulator_id'] or '?'}]: {res}")

    return {
        "tenants": [r["id"] for r in targets],
        "seeded": total,
        "results": results,
        "dry_run": dry_run,
    }


def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Unified ICAO hazard seeder")
    parser.add_argument("--tenant", default=None, help="tenant slug to seed (e.g. buddha-air)")
    parser.add_argument("--all", action="store_true",
                        help="seed every operator tenant created from /admin/production-setup.html")
    parser.add_argument("--regulator", default=None,
                        help="with --all: restrict seeding to one State Regulator's operators")
    parser.add_argument("--count", type=int, default=6, help="number of hazard records per tenant")
    parser.add_argument("--function", default=None, help="restrict to one ICAO function code")
    parser.add_argument("--priority", default=None, choices=["H", "M", "L"], help="force priority")
    parser.add_argument("--year", type=int, default=None, help="reference year")
    parser.add_argument("--target", default="both", choices=["firestore", "supabase", "both"],
                        help="which backend to write to")
    parser.add_argument("--demo", action="store_true", help="mark Supabase rows as demo data")
    parser.add_argument("--dry-run", action="store_true", help="compute only; write nothing")
    args = parser.parse_args(argv)

    if args.tenant and (args.all or args.regulator):
        parser.error("--tenant cannot be combined with --all/--regulator")
    if not args.tenant and not args.all and not args.regulator:
        parser.error("provide --tenant, or --all to seed production-setup tenants")

    initialize_firebase()
    if args.tenant:
        if args.tenant not in PRODUCTION_TENANTS:
            raise SystemExit(
                f"--tenant '{args.tenant}' is not in PRODUCTION_TENANTS "
                f"({', '.join(PRODUCTION_TENANTS)})"
            )
        result = run(seed_tenant_hazards(
            args.tenant,
            count=args.count,
            function=args.function,
            priority_override=args.priority,
            year=args.year,
            target=args.target,
            dry_run=args.dry_run,
            is_demo=args.demo,
        ))
    else:
        result = run(seed_from_production_setup(
            count=args.count,
            function=args.function,
            priority_override=args.priority,
            year=args.year,
            target=args.target,
            dry_run=args.dry_run,
            is_demo=args.demo,
            regulator_id=args.regulator,
        ))
    logger.info(f"Unified seed result: {result}")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())