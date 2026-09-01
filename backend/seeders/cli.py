# ============================================================================
# FILE: cli.py
# PATH: backend/seeders/cli.py
# PURPOSE: Command-line interface for the AviaSAFE seed runner. Wraps
#          SeedRunner with proper logging and exit-code handling so it can be
#          wired into CI / npm scripts. Run from backend/ so `app.*` imports
#          resolve (the app itself is not a `backend.` package).
#
# Usage (from backend/):
#   python -m seeders.cli --all
#   python -m seeders.cli --module Hazard
#   python -m seeders.cli --all --tenants fixedwing,rotarywing
#   python -m seeders.cli --all --dry-run
#   python -m seeders.cli --unseed
#   python -m seeders.cli --unseed --tenants fixedwing
# ============================================================================

import sys
import logging
import argparse

from .runner import SeedRunner


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="AviaSAFE Seed Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m seeders.cli --all
  python -m seeders.cli --module Hazard
  python -m seeders.cli --all --tenants fixedwing,rotarywing
  python -m seeders.cli --all --dry-run
  python -m seeders.cli --unseed
  python -m seeders.cli --unseed --tenants fixedwing
        """,
    )

    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Seed all modules",
    )
    parser.add_argument(
        "--module", "-m",
        help="Seed specific module (Tenant, Hazard, Report, Can, Cap, Psoe, Ssp, Diversion)",
    )
    parser.add_argument(
        "--unseed", "-u",
        action="store_true",
        help="Remove seeded data",
    )
    parser.add_argument(
        "--tenants", "-t",
        help="Comma-separated tenant IDs (e.g., fixedwing,rotarywing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without executing",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    # If no arguments, show help
    if not any([args.all, args.module, args.unseed]):
        parser.print_help()
        sys.exit(0)

    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Parse tenant IDs
    tenant_ids = args.tenants.split(",") if args.tenants else None

    # Initialize runner
    runner = SeedRunner(tenant_ids=tenant_ids, dry_run=args.dry_run)

    # Execute
    try:
        if args.unseed:
            logger.info("Starting unseed operation...")
            runner.unseed_all()
        elif args.module:
            logger.info(f"Seeding module: {args.module}")
            runner.seed_module(args.module)
        else:
            logger.info("Seeding all modules...")
            runner.seed_all()

        # Print final summary
        summary = runner.get_summary()
        logger.info(
            f"\nDone. Created: {summary['total_created']}, "
            f"Skipped: {summary['total_skipped']}, "
            f"Errors: {summary['total_errors']}"
        )

        if summary["total_errors"] > 0:
            sys.exit(1)

    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()