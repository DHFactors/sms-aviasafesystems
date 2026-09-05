# ============================================================================
# FILE: migrate_hazard_ids_to_function_format.py
# PATH: backend/scripts/migrate_hazard_ids_to_function_format.py
# PURPOSE: One-way migration of legacy hazard references onto the CAAN
#          Annex 19 / CAR-19 function format {FUNCTION}/{SEQ}/{PRIORITY}/{YEAR}
#          (e.g. OPS/001/M/2026) within the relational `hazards` table.
#
#   Transaction rules per tenant_uuid + (function, year) sequence-scope:
#     * New-format refs  (OPS/001/M/2026)            -> kept as-is; function
#                                                       column synced to the
#                                                       parsed function code.
#     * Legacy refs      (FW-001-H-2026, HZ-...)     -> rebuilt with the
#                                                       function resolved from
#                                                       the stored `function`
#                                                       column or the user's
#                                                       department label.
#     * Unparseable refs (FW-HZ-0007-26, HAZ-SDC-..) -> reassigned the next free
#                                                       sequence for the
#                                                       function/year.
#   Sequences that collide under the new per-(function, year) scope are bumped
#   to the next free number. Repeats are safe: new-format rows are skipped.
#
# Usage:
#   python backend/scripts/migrate_hazard_ids_to_function_format.py           # dry run
#   python backend/scripts/migrate_hazard_ids_to_function_format.py --apply   # commit
# ============================================================================

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(BACKEND, ".env"), override=False)

from loguru import logger  # noqa: E402

from app.db.db_models import Hazard  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.services.hazard_service import (  # noqa: E402
    generate_hazard_id,
    parse_hazard_id,
    resolve_function_code,
)

NEW_FORMAT_FUNC = "new"
MIGRATED_FUNC = "migrated"
REASSIGNED_FUNC = "reassigned"
COLLISION_FUNC = "collision_bumped"


def _next_free_seq(used: Dict[str, Dict[int, set]], function: str, year: int) -> int:
    """Return the smallest unused positive sequence for (function, year)."""
    by_year = used.setdefault(function, {})
    used_seqs = by_year.setdefault(year, set())
    seq = 1
    while seq in used_seqs:
        seq += 1
    by_year[year] = used_seqs
    return seq


def _claim_seq(used: Dict[str, Dict[int, set]], function: str, year: int, seq: int) -> bool:
    """Return True when (function, year, seq) was free and is now claimed."""
    by_year = used.setdefault(function, {})
    used_seqs = by_year.setdefault(year, set())
    if seq in used_seqs:
        return False
    by_year[year] = used_seqs | {seq}
    return True


async def run_migration(apply: bool = False) -> Dict[str, Any]:
    factory = get_session_factory()
    async with factory() as session:
        rows: List[Hazard] = list((await session.execute(
            Hazard.__table__.select()
        )).scalars().all())

    used: Dict[str, Dict[str, Dict[int, set]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(set))
    )
    changes: List[Dict[str, Any]] = []
    stats = {NEW_FORMAT_FUNC: 0, MIGRATED_FUNC: 0, REASSIGNED_FUNC: 0, COLLISION_FUNC: 0}

    # First pass: claim sequences so legacy/unparseable rows cannot collide
    # with existing new-format rows.
    for row in rows:
        parsed = parse_hazard_id(row.hazard_id)
        if parsed and isinstance(row.hazard_id, str) and "/" in row.hazard_id:
            _claim_seq(used[row.tenant_id], parsed["function"], parsed["year"], parsed["seq"])
            stats[NEW_FORMAT_FUNC] += 1

    for row in rows:
        hazard_id = row.hazard_id or ""
        tenant_used = used[row.tenant_id]
        action = "kept"
        new_reference = None
        new_function = None
        bumped = False

        parsed = parse_hazard_id(hazard_id)
        legacy = parsed and "-" in hazard_id

        if parsed and "/" in hazard_id:
            # Already CAAN format — sync the function column to the reference.
            if row.function != parsed["function"]:
                new_function = parsed["function"]
            action = "synced_function"

        elif legacy:
            # Rebuild the reference around the resolved function while keeping
            # the historical sequence/priority/year.
            function = (row.function or "").upper()
            function = function if function in _VALID_MIGRATE_FUNCTIONS else resolve_function_code(
                row.department, row.function
            )
            target_seq = parsed["seq"]
            if not _claim_seq(tenant_used, function, parsed["year"], target_seq):
                bumped = True
                target_seq = _next_free_seq(tenant_used, function, parsed["year"])
                _claim_seq(tenant_used, function, parsed["year"], target_seq)
            new_reference = generate_hazard_id(
                function, parsed["priority"], parsed["year"], target_seq
            )
            new_function = function
            action = "migrated"

        else:
            # Unparseable (FW-HZ-0007-26, HAZ-SDC-...) -> reassign a fresh
            # sequence under the resolved function/year.
            function = (row.function or "").upper()
            function = function if function in _VALID_MIGRATE_FUNCTIONS else resolve_function_code(
                row.department, row.function
            )
            year = row.created_at.year if row.created_at else datetime.now(timezone.utc).year
            target_seq = _next_free_seq(tenant_used, function, year)
            _claim_seq(tenant_used, function, year, target_seq)
            priority = (row.priority or "M").upper()
            new_reference = generate_hazard_id(function, priority, year, target_seq)
            new_function = function
            action = "reassigned"

        if new_reference and new_reference != hazard_id:
            stat_key = COLLISION_FUNC if bumped else (
                MIGRATED_FUNC if action == "migrated" else REASSIGNED_FUNC
            )
            changes.append({
                "id": row.id,
                "tenant_id": row.tenant_id,
                "old_reference": hazard_id,
                "new_reference": new_reference,
                "function": new_function,
                "action": action if action != "migrated" else stat_key,
                "bumped": bumped,
            })
            stats[stat_key] += 1
        elif new_function and new_function != row.function:
            changes.append({
                "id": row.id,
                "tenant_id": row.tenant_id,
                "old_reference": hazard_id,
                "new_reference": hazard_id,
                "function": new_function,
                "action": "synced_function",
                "bumped": False,
            })
            stats["synced_function"] = stats.get("synced_function", 0) + 1

    if not apply:
        logger.info(f"DRY RUN — {len(changes)} hazard(s) would change. Re-run with --apply.")
    else:
        async with factory() as session:
            for change in changes:
                row = await session.get(Hazard, change["id"])
                if row is None:
                    continue
                row.hazard_id = change["new_reference"]
                if change.get("function"):
                    row.function = change["function"]
                row.updated_at = datetime.now(timezone.utc)
            await session.commit()
        logger.info(f"Applied: {len(changes)} hazard row(s) updated.")

    for change in changes:
        logger.info(
            f"[{change['action']}] tenant={change['tenant_id']} "
            f"{change['old_reference']!r} -> {change['new_reference']!r} "
            f"(function={change.get('function')}, bumped={change['bumped']})"
        )
    return {"dry_run": not apply, "changed": len(changes), "stats": stats}


# Function codes acceptable as a *stored* function during migration. Anything
# else (legacy GEN defaults without a concrete department) is re-resolved.
_VALID_MIGRATE_FUNCTIONS = {
    "OPS", "ENG", "CAB", "MNT", "GHD", "DSP", "SAF", "SEC",
    "MED", "TRN", "ADM", "ENV", "HUM", "ORG", "GEN",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate hazard ids to CAAN function format")
    parser.add_argument("--apply", action="store_true", help="commit changes (default: dry run)")
    args = parser.parse_args()

    import asyncio

    result = asyncio.run(run_migration(apply=args.apply))
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())