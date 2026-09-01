# ============================================================================
# FILE: runner.py
# PATH: backend/seeders/runner.py
# PURPOSE: Orchestrate all modules of the demo Airline/Airport SMS seeder in
#          dependency-correct order, with a single seed-all / unseed-all /
#          module-specific entry point used by the CLI.
#
# Seeder order (dependencies flow top-down):
#   1. TenantSeeder    - Foundation: tenants + role users (must run first)
#   2. HazardSeeder    - Module 2 hazards (referenced by reports/CANs)
#   3. ReportSeeder    - Module 2 VSR/MOR reports
#   4. CanSeeder       - Module 2 CANs linked to seeded hazards
#   5. CapSeeder       - Module 2 CAPs linked to seeded CANs
#   6. PsoeSeeder      - Module 3 PSOE surveillance assessments (Firestore)
#   7. SspSeeder       - State Safety Programme, demostate only (Firestore)
#   8. DiversionSeeder - Module 2 flight diversions (Firestore)
#
# Every seeder is instantiated with (tenant_ids, dry_run) and exposes seed()
# / unseed() returning a get_summary() dict (created / skipped / errors /
# dry_run). Failures are captured per seeder so one broken module never aborts
# the whole run.
#
# Invocation (from backend/):
#   python -m seeders.runner --all
#   python -m seeders.runner --module Hazard --tenants fixedwing
#   python -m seeders.runner --all --dry-run
#   python -m seeders.runner --unseed
# ============================================================================

import argparse
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base_seeder import BaseSeeder
from .tenants.tenant_seeder import TenantSeeder
from .hazards.hazard_seeder import HazardSeeder
from .reports.report_seeder import ReportSeeder
from .cans_caps.can_seeder import CanSeeder
from .cans_caps.cap_seeder import CapSeeder
from .psoe.psoe_seeder import PsoeSeeder
from .ssp.ssp_seeder import SspSeeder
from .diversions.diversion_seeder import DiversionSeeder

logger = logging.getLogger(__name__)


class SeedRunner:
    """
    Orchestrates all seeders in the correct order.

    Seeder Order:
    1. TenantSeeder - Creates tenants and users (Foundation)
    2. HazardSeeder - Creates hazards (Module 2)
    3. ReportSeeder - Creates VSR/MOR reports (Module 2)
    4. CanSeeder - Creates CANs linked to hazards (Module 2)
    5. CapSeeder - Creates CAPs linked to CANs (Module 2)
    6. PsoeSeeder - Creates PSOE assessments (Module 3 - Optional)
    7. SspSeeder - Creates State Safety Programme data (State)
    8. DiversionSeeder - Creates flight diversions (Module 2)
    """

    SEEDERS = [
        TenantSeeder,      # Foundation - always first
        HazardSeeder,      # Module 2
        ReportSeeder,      # Module 2
        CanSeeder,         # Module 2
        CapSeeder,         # Module 2
        PsoeSeeder,        # Module 3 (Optional)
        SspSeeder,         # State (demostate)
        DiversionSeeder,   # Module 2
    ]

    # Indices keyed by the short module name used with --module.
    MODULE_NAMES = [
        "Tenant",
        "Hazard",
        "Report",
        "Can",
        "Cap",
        "Psoe",
        "Ssp",
        "Diversion",
    ]

    def __init__(
        self, tenant_ids: Optional[List[str]] = None, dry_run: bool = False
    ):
        self.tenant_ids = tenant_ids
        self.dry_run = dry_run
        self.results: List[Dict[str, Any]] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def seed_all(self) -> List[Dict[str, Any]]:
        """Run all seeders in sequence."""
        self.start_time = datetime.now()
        self.results = []
        logger.info("=" * 70)
        logger.info("STARTING SEED RUNNER")
        logger.info(f"   Tenants: {self.tenant_ids or 'All'}")
        logger.info(f"   Dry Run: {self.dry_run}")
        logger.info("=" * 70)

        for seeder_class in self.SEEDERS:
            seeder_name = seeder_class.__name__
            if self.dry_run:
                logger.info(f"\n[DRY RUN] Would run {seeder_name}...")
            else:
                logger.info(f"\nRunning {seeder_name}...")

            seeder = seeder_class(
                tenant_ids=self.tenant_ids,
                dry_run=self.dry_run,
            )

            try:
                result = seeder.seed()
                self.results.append(result)
                logger.info(
                    f"{seeder_name} complete: {result['created']} created, "
                    f"{result['skipped']} skipped"
                )
            except Exception as e:
                logger.error(f"{seeder_name} failed: {e}")
                self.results.append({
                    "seeder": seeder_name,
                    "created": 0,
                    "skipped": 0,
                    "errors": 1,
                    "dry_run": self.dry_run,
                    "error": str(e),
                })

        self.end_time = datetime.now()
        self._print_summary()
        return self.results

    def unseed_all(self) -> List[Dict[str, Any]]:
        """Run all unseeders in reverse order."""
        self.start_time = datetime.now()
        self.results = []
        logger.info("=" * 70)
        logger.info("STARTING UNSEED RUNNER")
        logger.info(f"   Tenants: {self.tenant_ids or 'All'}")
        logger.info(f"   Dry Run: {self.dry_run}")
        logger.info("=" * 70)

        for seeder_class in reversed(self.SEEDERS):
            seeder_name = seeder_class.__name__
            if self.dry_run:
                logger.info(f"\n[DRY RUN] Would unseed {seeder_name}...")
            else:
                logger.info(f"\nUnseeding {seeder_name}...")

            seeder = seeder_class(
                tenant_ids=self.tenant_ids,
                dry_run=self.dry_run,
            )

            try:
                result = seeder.unseed()
                self.results.append(result)
                logger.info(
                    f"{seeder_name} unseed complete: {result['created']} removed"
                )
            except Exception as e:
                logger.error(f"{seeder_name} unseed failed: {e}")
                self.results.append({
                    "seeder": seeder_name,
                    "created": 0,
                    "skipped": 0,
                    "errors": 1,
                    "dry_run": self.dry_run,
                    "error": str(e),
                })

        self.end_time = datetime.now()
        self._print_summary()
        return self.results

    # ------------------------------------------------------------------
    # Module-specific
    # ------------------------------------------------------------------

    def seed_module(self, module_name: str) -> Optional[Dict[str, Any]]:
        """Run a specific module by name (Tenant, Hazard, Report, Can, Cap,
        Psoe, Ssp, Diversion)."""
        module_map = dict(zip(self.MODULE_NAMES, self.SEEDERS))
        seeder_class = module_map.get(module_name)
        if not seeder_class:
            logger.error(
                f"Module '{module_name}' not found. Valid: "
                f"{', '.join(self.MODULE_NAMES)}"
            )
            return None

        self.start_time = datetime.now()
        self.results = []
        seeder = seeder_class(
            tenant_ids=self.tenant_ids,
            dry_run=self.dry_run,
        )
        logger.info(f"\nRunning {seeder_class.__name__}...")
        result = seeder.seed()
        self.results.append(result)
        self.end_time = datetime.now()
        logger.info(
            f"{seeder_class.__name__} complete: {result['created']} created, "
            f"{result['skipped']} skipped"
        )
        return result

    # ------------------------------------------------------------------
    # Summary helpers
    # ------------------------------------------------------------------

    def _print_summary(self) -> None:
        """Print a summary of all seed results."""
        duration = (
            (self.end_time - self.start_time).total_seconds()
            if self.end_time and self.start_time
            else 0.0
        )

        logger.info("\n" + "=" * 70)
        logger.info("SEED RUNNER SUMMARY")
        logger.info("=" * 70)

        total_created = 0
        total_skipped = 0
        total_errors = 0

        for result in self.results:
            seeder = result.get("seeder", "Unknown")
            created = result.get("created", 0)
            skipped = result.get("skipped", 0)
            errors = result.get("errors", 0)
            dry_run = result.get("dry_run", False)

            total_created += created
            total_skipped += skipped
            total_errors += errors

            status = "[DRY-RUN]" if dry_run else ""
            logger.info(
                f"  {status} {seeder}: {created} created, {skipped} skipped, "
                f"{errors} errors"
            )

        logger.info("-" * 70)
        logger.info(
            f"  TOTAL: {total_created} created, {total_skipped} skipped, "
            f"{total_errors} errors"
        )
        logger.info(f"  Duration: {duration:.2f}s")
        logger.info("=" * 70)

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all results."""
        return {
            "total_modules": len(self.results),
            "total_created": sum(r.get("created", 0) for r in self.results),
            "total_skipped": sum(r.get("skipped", 0) for r in self.results),
            "total_errors": sum(r.get("errors", 0) for r in self.results),
            "dry_run": self.dry_run,
            "duration": (
                (self.end_time - self.start_time).total_seconds()
                if self.end_time and self.start_time
                else 0
            ),
            "results": self.results,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Runner")
    parser.add_argument("--all", action="store_true", help="Seed all modules")
    parser.add_argument("--module", "-m", help="Seed specific module")
    parser.add_argument(
        "--unseed", "-u", action="store_true", help="Remove seeded data"
    )
    parser.add_argument(
        "--tenants", "-t", help="Comma-separated tenant IDs"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without executing"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose logging"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    tenant_ids = args.tenants.split(",") if args.tenants else None
    runner = SeedRunner(tenant_ids=tenant_ids, dry_run=args.dry_run)

    if args.unseed:
        runner.unseed_all()
    elif args.module:
        runner.seed_module(args.module)
    elif args.all:
        runner.seed_all()
    else:
        runner.seed_all()

    summary = runner.get_summary()
    if summary["total_errors"] > 0:
        raise SystemExit(1)