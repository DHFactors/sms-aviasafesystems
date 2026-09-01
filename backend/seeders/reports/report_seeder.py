# ============================================================================
# FILE: report_seeder.py
# PATH: backend/seeders/reports/report_seeder.py
# PURPOSE: Seed / unseed realistic Voluntary Safety Reports (VSR) and
#          Mandatory Occurrence Reports (MOR) using Supabase (PostgreSQL) via
#          the SQLAlchemy Report model and ReportService.
#
# Actor mapping (who may create what):
#   * VSR  -> Staff (any department)
#   * MOR  -> Part-145 / CAMO / Ops  (NOT the Safety Manager)
#
# The Report table has no `title` column, and `created_by` is always set to
# the reporting user's uid, so idempotency / unseed are keyed on the exact
# report narrative - we only ever touch the rows this seeder manages.
# Narratives are realistic and carry actor names - no "seeded by..." markers.
#
# Invocation (from backend/):
#   python -m seeders.reports.report_seeder seed                    # all tenants
#   python -m seeders.reports.report_seeder seed --tenants fixedwing
#   python -m seeders.reports.report_seeder seed --dry-run
#   python -m seeders.reports.report_seeder unseed
# ============================================================================

import json
import sys
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select

from seeders import BaseSeeder
from app.db.ids import register_tenant
from app.db.isolation import demo_scope
from app.db.runner import run
from app.db.session import session_scope
from app.db.db_models import Report
from app.services.report_service import ReportService


def _role_token_for_email(email: str) -> str:
    """Derive the role token from the email local part (e.g. 145 --> 145)."""
    return email.split("@")[0]


def _uid_for(reporter_email: str) -> str:
    """Deterministic uid for the reporting user, consistent with the tenant
    seeder's {role_token}-{tenant_id}-001 scheme."""
    token = _role_token_for_email(reporter_email)
    tenant = reporter_email.split("@")[1].split(".")[0]
    return f"{token}-{tenant}-001"


# =============================================================================
# Report templates (Fixed-Wing)
# =============================================================================

FIXED_WING_REPORTS: List[Dict[str, Any]] = [
    {
        # MOR - Part-145
        "title": "Engine Chip Light Activation - Flight FW-567",
        "report_type": "mandatory",
        "narrative": "Mr. Dipak Rai (Part-145 Manager) submitted a mandatory "
        "occurrence report on 20 August 2026 regarding engine chip light "
        "activation during post-flight inspection of aircraft 9N-ABC. Chip "
        "detector revealed metal particles. Engine oil analysis confirmed "
        "bearing material. Engine removed for overhaul. Aircraft grounded "
        "pending engine replacement.",
        "created_by": "Mr. Dipak Rai",
        "created_by_email": "145@fixedwing.test",
        "department": "Part-145",
        "occurrence_type": "Serious Incident",
        "location": "VNKT",
        "severity": 4,
        "probability": 2,
        "aircraft_registration": "9N-ABC",
        "flight_number": "FW-567",
        "occurrence_date": "2026-08-20",
    },
    {
        # MOR - CAMO
        "title": "AD Compliance - Inspection Overdue",
        "report_type": "mandatory",
        "narrative": "Mr. Suresh Ghale (CAMO Manager) submitted a mandatory "
        "occurrence report on 15 August 2026 regarding AD 2025-08-01 "
        "inspection overdue for aircraft 9N-DEF. The inspection was due at "
        "15,000 hours but aircraft operated until 15,200 hours. CAMO "
        "identified the error during records review. Corrective action "
        "implemented.",
        "created_by": "Mr. Suresh Ghale",
        "created_by_email": "camo@fixedwing.test",
        "department": "CAMO",
        "occurrence_type": "Incident",
        "location": "VNKT",
        "severity": 3,
        "probability": 2,
        "aircraft_registration": "9N-DEF",
        "occurrence_date": "2026-08-15",
    },
    {
        # MOR - Ops
        "title": "Tailstrike During Takeoff - Flight FW-902",
        "report_type": "mandatory",
        "narrative": "Capt. Sanjay Gurung (Operations Manager) submitted a "
        "mandatory occurrence report on 22 August 2026 regarding a tailstrike "
        "incident during takeoff on aircraft 9N-GHI. Aircraft rotated at "
        "excessive pitch attitude (12° vs standard 8°) resulting in tail "
        "scrape. Post-flight inspection confirmed damage to tail skid. "
        "Aircraft removed from service for inspection.",
        "created_by": "Capt. Sanjay Gurung",
        "created_by_email": "ops@fixedwing.test",
        "department": "Flight Operations",
        "occurrence_type": "Serious Incident",
        "location": "VNSI",
        "severity": 4,
        "probability": 2,
        "aircraft_registration": "9N-GHI",
        "flight_number": "FW-902",
        "occurrence_date": "2026-08-22",
    },
    {
        # VSR - Staff
        "title": "Tailwind Gust on Final Approach",
        "report_type": "voluntary",
        "narrative": "F/O Prashant Karki submitted a voluntary safety report "
        "on 18 August 2026 about a tailwind gust encountered during final "
        "approach to Runway 25 on flight FW-123. Aircraft temporarily exceeded "
        "approach speed by 20kts. Crew executed go-around and landed safely on "
        "second attempt. No injuries or damage.",
        "created_by": "F/O Prashant Karki",
        "created_by_email": "staff@fixedwing.test",
        "department": "Flight Operations",
        "occurrence_type": "Incident",
        "location": "VNKT",
        "severity": 2,
        "probability": 3,
        "aircraft_registration": "9N-JKL",
        "flight_number": "FW-123",
        "occurrence_date": "2026-08-18",
    },
]

# =============================================================================
# Report templates (Rotary-Wing)
# =============================================================================

ROTARY_WING_REPORTS: List[Dict[str, Any]] = [
    {
        # MOR - Part-145
        "title": "Tail Rotor Blade Crack - Helo RW-203",
        "report_type": "mandatory",
        "narrative": "Mr. Shiva Tamang (Part-145 Manager) submitted a "
        "mandatory occurrence report on 19 August 2026 regarding a crack "
        "discovered in the tail rotor blade of helicopter 9N-RWX during "
        "scheduled 100-hour inspection. The crack measured 2.5 inches from the "
        "root. Fleet-wide inspection ordered. Blade replaced and helicopter "
        "returned to service.",
        "created_by": "Mr. Shiva Tamang",
        "created_by_email": "145@rotarywing.test",
        "department": "Part-145",
        "occurrence_type": "Serious Incident",
        "location": "VNKT",
        "severity": 5,
        "probability": 1,
        "aircraft_registration": "9N-RWX",
        "flight_number": "RW-203",
        "occurrence_date": "2026-08-19",
    },
    {
        # MOR - CAMO
        "title": "Life-Limited Part Exceedance - Helo RW-210",
        "report_type": "mandatory",
        "narrative": "Mr. Kiran Gurung (CAMO Manager) submitted a mandatory "
        "occurrence report on 16 August 2026 regarding a life-limited part "
        "(main rotor gearbox) that exceeded its service life by 50 hours. The "
        "error was identified during records review. Component removed and "
        "sent for overhaul. Investigation found record-keeping discrepancy.",
        "created_by": "Mr. Kiran Gurung",
        "created_by_email": "camo@rotarywing.test",
        "department": "CAMO",
        "occurrence_type": "Incident",
        "location": "VNKT",
        "severity": 3,
        "probability": 2,
        "aircraft_registration": "9N-RWY",
        "occurrence_date": "2026-08-16",
    },
    {
        # MOR - Ops
        "title": "LTE Encounter at High-Altitude Helipad - RW-118",
        "report_type": "mandatory",
        "narrative": "Capt. Ram Koirala (Operations Manager) submitted a "
        "mandatory occurrence report on 21 August 2026 regarding a loss of "
        "tail rotor effectiveness (LTE) incident during approach to a "
        "high-altitude helipad (11,500ft AMSL). Helicopter experienced a 45° "
        "yaw due to sudden tailwind shift. Pilot recovered control and landed "
        "safely. Post-flight inspection revealed no damage.",
        "created_by": "Capt. Ram Koirala",
        "created_by_email": "ops@rotarywing.test",
        "department": "Flight Operations",
        "occurrence_type": "Serious Incident",
        "location": "High Altitude Helipad",
        "severity": 4,
        "probability": 2,
        "aircraft_registration": "9N-RWZ",
        "flight_number": "RW-118",
        "occurrence_date": "2026-08-21",
    },
    {
        # VSR - Staff
        "title": "Sudden Visibility Deterioration - Mountain Crossing",
        "report_type": "voluntary",
        "narrative": "F/O Bikram Malla submitted a voluntary safety report on "
        "17 August 2026 about a sudden visibility deterioration during a "
        "mountain crossing at 12,000ft. Visibility dropped from 8km to <1km "
        "due to unexpected valley fog. Pilot executed 180° turn and returned "
        "to base. Flight conducted under VFR.",
        "created_by": "F/O Bikram Malla",
        "created_by_email": "staff@rotarywing.test",
        "department": "Flight Operations",
        "occurrence_type": "Incident",
        "location": "Mountain Valley",
        "severity": 3,
        "probability": 3,
        "aircraft_registration": "9N-RWV",
        "flight_number": "RW-156",
        "occurrence_date": "2026-08-17",
    },
]

# =============================================================================
# Report templates (Demo Airport)
# =============================================================================

AIRPORT_REPORTS: List[Dict[str, Any]] = [
    {
        # MOR - Ops
        "title": "FOD on Runway 25 - Demo Airport",
        "report_type": "mandatory",
        "narrative": "Mr. Ramesh Adhikari (Airport Operations Manager) "
        "submitted a mandatory occurrence report on 23 August 2026 regarding "
        "foreign object debris (FOD) found on Runway 25. Debris included metal "
        "fragments and rubber deposits from recent construction work. Runway "
        "was closed for 45 minutes for inspection and cleanup. No aircraft "
        "damage reported.",
        "created_by": "Mr. Ramesh Adhikari",
        "created_by_email": "ops@demoairport.test",
        "department": "Airport Operations",
        "occurrence_type": "Incident",
        "location": "Runway 25",
        "severity": 3,
        "probability": 4,
        "occurrence_date": "2026-08-23",
    },
    {
        # VSR - Staff
        "title": "Apron Near-Miss - Ground Vehicle and Aircraft",
        "report_type": "voluntary",
        "narrative": "Mr. Purna Singh submitted a voluntary safety report on "
        "24 August 2026 about a near-miss incident on the apron involving a "
        "ground vehicle and a taxiing aircraft. Vehicle crossed the taxiway "
        "without clearance. ATC alerted the aircraft crew who stopped "
        "immediately. No collision occurred.",
        "created_by": "Mr. Purna Singh",
        "created_by_email": "staff@demoairport.test",
        "department": "Airport Operations",
        "occurrence_type": "Incident",
        "location": "Apron Area",
        "severity": 3,
        "probability": 2,
        "occurrence_date": "2026-08-24",
    },
]

# Aggregate keyed by tenant id (demostate has no reports).
REPORTS_BY_TENANT: Dict[str, List[Dict[str, Any]]] = {
    "fixedwing": FIXED_WING_REPORTS,
    "rotarywing": ROTARY_WING_REPORTS,
    "demoairport": AIRPORT_REPORTS,
}


class ReportSeeder(BaseSeeder):
    """Seed / unseed realistic VSR + MOR reports by operator type."""

    def __init__(
        self, tenant_ids: Optional[List[str]] = None, dry_run: bool = False
    ):
        super().__init__(tenant_ids=tenant_ids, dry_run=dry_run)

    # ------------------------------------------------------------------
    # PostgreSQL persistence helpers (async dispatched via bridge loop)
    # ------------------------------------------------------------------

    def _find_existing_report(
        self, tenant_id: str, narrative: str
    ) -> Optional[str]:
        """Return the id of an existing report with this narrative, else None."""
        tid = register_tenant(tenant_id)

        async def _query() -> Optional[str]:
            async with session_scope() as session:
                result = await session.scalar(
                    select(Report.id).where(
                        Report.tenant_id == tid,
                        Report.narrative == narrative,
                        Report.is_demo == demo_scope(),
                    )
                )
                return str(result) if result else None

        return run(_query())

    def _create_report(self, tenant_id: str, report_data: Dict) -> Optional[str]:
        """Create a single report in PostgreSQL. Skip if already exists."""
        title = report_data["title"]
        narrative = report_data["narrative"]

        if self.dry_run:
            self.log_info(f"[DRY RUN] Would create report: {title}")
            self.created_count += 1
            return "dry-run-id"

        existing = self._find_existing_report(tenant_id, narrative)
        if existing:
            self.skipped_count += 1
            self.log_info(f"Skipped existing report: {title}")
            return None

        reporter_email = report_data["created_by_email"]
        # Reporting user dict; nothing here is a "seeded by..." marker.
        reporter_user = {
            "uid": _uid_for(reporter_email),
            "email": reporter_email,
            "role": "USER",
            "tenant_id": tenant_id,
        }

        # Map template keys onto Report column names (severity/probability are
        # stored as severity_level/probability_level so risk is computed).
        payload = {
            "title": title,  # metadata only (Report has no title column)
            "narrative": narrative,
            "report_type": report_data["report_type"],
            "occurrence_type": report_data.get("occurrence_type"),
            "department": report_data.get("department", ""),
            "location": report_data.get("location", ""),
            "occurrence_date": report_data.get("occurrence_date"),
            "aircraft_registration": report_data.get("aircraft_registration"),
            "flight_number": report_data.get("flight_number"),
            "reporter_name": report_data["created_by"],
            "reporter_email": reporter_email,
            "severity_level": report_data.get("severity"),
            "probability_level": report_data.get("probability"),
            "status": "NEW",
        }

        try:
            service = ReportService(tenant_id=tenant_id)
            result = service.create_report(payload, reporter_user)
            self.created_count += 1
            self.log_info(f"Created report: {title}")
            return result.get("id")
        except Exception as e:
            self.log_error(f"Failed to create report {title}: {e}")
            return None

    def _get_reports_for_tenant(self, tenant_id: str) -> List[Dict]:
        return REPORTS_BY_TENANT.get(tenant_id, [])

    # ------------------------------------------------------------------
    # BaseSeeder interface
    # ------------------------------------------------------------------

    def seed(self) -> Dict[str, Any]:
        """Seed reports for all configured tenants."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        self.log_info("=" * 60)
        self.log_info("Starting ReportSeeder (Supabase/PostgreSQL)...")
        self.log_info("=" * 60)

        for tenant in self._get_tenant_ids():
            if not self._is_demo_tenant(tenant):
                self.log_warning(f"Skipping non-demo tenant: {tenant}")
                continue
            self.log_info(f"Seeding reports for tenant: {tenant}")
            reports = self._get_reports_for_tenant(tenant)
            self.log_info(f"  Found {len(reports)} report templates")
            for report in reports:
                self._create_report(tenant, report)

        self.log_info("=" * 60)
        self.log_info(
            f"ReportSeeder complete: created={self.created_count} "
            f"skipped={self.skipped_count} errors={len(self.errors)}"
        )
        self.log_info("=" * 60)

        return self.get_summary()

    def unseed(self) -> Dict[str, Any]:
        """Remove all reports created by this seeder from PostgreSQL."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        self.log_info("=" * 60)
        self.log_info("Starting ReportSeeder unseed...")
        self.log_info("=" * 60)

        for tenant in self._get_tenant_ids():
            if not self._is_demo_tenant(tenant):
                continue
            tid = register_tenant(tenant)
            seeded_narratives = [
                r["narrative"] for r in self._get_reports_for_tenant(tenant)
            ]
            if not seeded_narratives:
                continue

            if self.dry_run:
                self.log_info(
                    f"[DRY RUN] Would remove {len(seeded_narratives)} "
                    f"seeded reports for tenant: {tenant}"
                )
                continue

            async def _remove() -> int:
                async with session_scope() as session:
                    result = await session.execute(
                        delete(Report).where(
                            Report.tenant_id == tid,
                            Report.narrative.in_(seeded_narratives),
                            Report.is_demo == demo_scope(),
                        )
                    )
                    return result.rowcount or 0

            try:
                removed = run(_remove())
                self.created_count += removed
                self.log_info(
                    f"Removed {removed} seeded reports for tenant: {tenant}"
                )
            except Exception as e:
                self.log_error(
                    f"Failed to unseed reports for tenant {tenant}: {e}"
                )

        self.log_info(
            f"ReportSeeder unseed complete: removed={self.created_count}"
        )
        return self.get_summary()


if __name__ == "__main__":
    seed_mode = "seed"
    tenants: Optional[List[str]] = None
    dry_run = False

    args = sys.argv[1:]
    if args and args[0] in ("seed", "unseed"):
        seed_mode = args[0]
        args = args[1:]
    if "--dry-run" in args:
        dry_run = True
    if "--tenants" in args:
        idx = args.index("--tenants")
        if idx + 1 < len(args):
            tenants = [
                t.strip() for t in args[idx + 1].split(",") if t.strip()
            ]

    seeder = ReportSeeder(tenant_ids=tenants, dry_run=dry_run)
    result = seeder.seed() if seed_mode == "seed" else seeder.unseed()
    print(json.dumps(result, indent=2, default=str))
