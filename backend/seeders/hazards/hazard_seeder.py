# ============================================================================
# FILE: hazard_seeder.py
# PATH: backend/seeders/hazards/hazard_seeder.py
# PURPOSE: Seed / unseed realistic, operator-specific hazards using Supabase
#          (PostgreSQL) via SQLAlchemy models and the HazardService.
#
# Seeding:
#   * fixedwing    -> 10 airport/route-related flight ops hazards
#   * rotarywing   -> 10 mountain / helipad / HEMS / maintenance hazards
#   * demoairport  -> 6  ground / runway / apron airport hazards
#   * demostate    -> regulator tenant, seeds no hazards
#
# Every seeded row is written with source_id == "HAZARD-SEEDER" so unseed()
# can remove exactly the rows this seeder created (idempotent re-runs skip
# hazards whose title already exists for the tenant).
#
# Invocation (from backend/):
#   python -m seeders.hazards.hazard_seeder seed                    # all tenants
#   python -m seeders.hazards.hazard_seeder seed --tenants fixedwing
#   python -m seeders.hazards.hazard_seeder seed --dry-run
#   python -m seeders.hazards.hazard_seeder unseed
# ============================================================================

import json
import os
import sys
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select

from seeders import BaseSeeder
from app.db.ids import register_tenant
from app.db.isolation import demo_scope
from app.db.runner import run
from app.db.session import session_scope
from app.db.db_models import Hazard
from app.services.hazard_service import HazardService

# Marker used to identify rows created by this seeder (lets unseed() remove
# exactly the seeded rows without touching production/demo-authored hazards).
SEED_SOURCE_ID = "HAZARD-SEEDER"
SEEDER_EMAIL = "seeder@aviasafe.com"

# =============================================================================
# Fixed-Wing Hazards (10) - airport / route related flight operations
# =============================================================================

FIXED_WING_HAZARDS: List[Dict[str, Any]] = [
    # -------------------- APPROACH & LANDING --------------------
    {
        "title": "Unstabilized Approach Below 1,000ft AGL",
        "description": "Aircraft on ILS approach to Runway 25 with excessive "
        "airspeed (30+ kts above Vref), high drift angle (12°), and landing "
        "gear not deployed at 500ft AGL. Crew failed to execute go-around "
        "despite unstable approach criteria being met.",
        "taxonomy": "HUM",
        "priority": "H",
        "severity": 4,
        "probability": 3,
        "hfacs": ["AE102", "PE103", "SP001"],
        "department": "Flight Operations",
        "source": "Flight Data Monitoring",
        "occurrence_type": "Serious Incident",
    },
    {
        "title": "Runway Excursion During Wet Conditions",
        "description": "Aircraft landing on Runway 25 with standing water and "
        "reported braking action 'poor'. Auto-brake system failed to engage, "
        "and reverse thrust was delayed. Aircraft overshot the runway end by "
        "150ft before stopping.",
        "taxonomy": "ENV",
        "priority": "H",
        "severity": 5,
        "probability": 2,
        "hfacs": ["PE101", "AE201", "OP001"],
        "department": "Flight Operations",
        "source": "MOR Report",
        "occurrence_type": "Accident",
    },
    {
        "title": "Tailwind Landing Exceeding Aircraft Limitations",
        "description": "Crew accepted landing with 15kt tailwind component "
        "(exceeding aircraft limitation of 10kt). Aircraft floated for 60% of "
        "runway length before touchdown.",
        "taxonomy": "HUM",
        "priority": "M",
        "severity": 3,
        "probability": 2,
        "hfacs": ["AE201", "PC103", "SI001"],
        "department": "Flight Operations",
        "source": "Quality Audit",
        "occurrence_type": "Incident",
    },
    {
        "title": "Go-Around Decision Delay Due to Crew Pressure",
        "description": "Crew continued approach despite unstable parameters, "
        "citing operational pressure to land. Go-around was initiated at 200ft "
        "AGL, below the standard go-around decision height of 500ft.",
        "taxonomy": "HUM",
        "priority": "H",
        "severity": 4,
        "probability": 2,
        "hfacs": ["AE202", "PC104", "SP001"],
        "department": "Flight Operations",
        "source": "VSR Report",
        "occurrence_type": "Incident",
    },
    # -------------------- TAKEOFF & CLIMB --------------------
    {
        "title": "Bird Strike During Initial Climb",
        "description": "Multiple bird strikes on No. 2 engine during climb out "
        "at 500ft AGL. Engine vibration increased, N1 dropped to 65%. Crew "
        "declared emergency and returned to departure airport.",
        "taxonomy": "WLD",
        "priority": "M",
        "severity": 3,
        "probability": 4,
        "hfacs": ["PE201", "AE101"],
        "department": "Flight Operations",
        "source": "MOR Report",
        "occurrence_type": "Serious Incident",
    },
    {
        "title": "Rejected Takeoff Due to Engine Fire Warning",
        "description": "During takeoff roll, engine fire warning activated at "
        "80kts. Crew rejected takeoff, performed emergency braking, and "
        "evacuated aircraft via slides. No fire found on inspection.",
        "taxonomy": "TEC",
        "priority": "H",
        "severity": 5,
        "probability": 1,
        "hfacs": ["PC105", "AE101", "OP003"],
        "department": "Flight Operations",
        "source": "MOR Report",
        "occurrence_type": "Serious Incident",
    },
    # -------------------- CRUISE & SYSTEMS --------------------
    {
        "title": "Engine Oil Pressure Fluctuation in Cruise",
        "description": "Intermittent oil pressure fluctuations observed on "
        "No. 1 engine during cruise at FL350. Pressure dropped from 90psi to "
        "35psi for 8 seconds before recovering.",
        "taxonomy": "TEC",
        "priority": "M",
        "severity": 3,
        "probability": 2,
        "hfacs": ["PC105", "AE201"],
        "department": "Part-145",
        "source": "Flight Data Monitoring",
        "occurrence_type": "Incident",
    },
    {
        "title": "Cabin Pressurization Warning During Descent",
        "description": "Cabin altitude warning horn activated at FL280 during "
        "descent. Crew initiated emergency descent to 10,000ft and donned "
        "oxygen masks. Faulty outflow valve actuator found.",
        "taxonomy": "TEC",
        "priority": "H",
        "severity": 4,
        "probability": 1,
        "hfacs": ["PC105", "AE101", "OP003"],
        "department": "Part-145",
        "source": "MOR Report",
        "occurrence_type": "Serious Incident",
    },
    # -------------------- ATC & COMMUNICATION --------------------
    {
        "title": "Altitude Deviation Due to Miscommunication",
        "description": "Crew misheard ATC altitude clearance, climbing to FL310 "
        "instead of assigned FL290. TCAS RA triggered, and crew corrected "
        "within 30 seconds.",
        "taxonomy": "HUM",
        "priority": "M",
        "severity": 3,
        "probability": 2,
        "hfacs": ["AE201", "PC101", "SI001"],
        "department": "Flight Operations",
        "source": "ATC Report",
        "occurrence_type": "Incident",
    },
    {
        "title": "Route Deviation Due to FMS Programming Error",
        "description": "Crew entered incorrect waypoint in FMS, causing aircraft "
        "to deviate from assigned route by 12NM. ATC advised correction.",
        "taxonomy": "HUM",
        "priority": "L",
        "severity": 2,
        "probability": 2,
        "hfacs": ["AE203", "PC102", "SI002"],
        "department": "Flight Operations",
        "source": "Quality Audit",
        "occurrence_type": "Incident",
    },
]

# =============================================================================
# Rotary-Wing Hazards (10) - mountain / helipad / remote / maintenance
# =============================================================================

ROTARY_WING_HAZARDS: List[Dict[str, Any]] = [
    # -------------------- MOUNTAIN FLYING --------------------
    {
        "title": "Loss of Tail Rotor Effectiveness (LTE) in Mountain Winds",
        "description": "Helicopter on approach to high-altitude helipad "
        "(12,000ft AMSL) encountered sudden tailwind shift from 15kt to 25kt. "
        "Pilot experienced LTE requiring immediate recovery. Aircraft yawed "
        "40° before recovery.",
        "taxonomy": "ENV",
        "priority": "H",
        "severity": 5,
        "probability": 3,
        "hfacs": ["PE101", "AE104", "SP001"],
        "department": "Flight Operations",
        "source": "VSR Report",
        "occurrence_type": "Serious Incident",
    },
    {
        "title": "Settling With Power During High-Altitude Hover",
        "description": "Helicopter hovered at 11,500ft AMSL with high density "
        "altitude (+2,000ft). Settling with power developed, causing descent "
        "rate of 800ft/min. Pilot recovered with 10% power margin.",
        "taxonomy": "HUM",
        "priority": "H",
        "severity": 4,
        "probability": 2,
        "hfacs": ["AE102", "PE103", "SP002"],
        "department": "Flight Operations",
        "source": "Flight Data Monitoring",
        "occurrence_type": "Serious Incident",
    },
    {
        "title": "Weather Deterioration — Visibility Below VFR Minimums",
        "description": "Mountain flight encountered unexpected visibility drop "
        "from 5km to <1km due to valley fog. Pilot executed 180° turn and "
        "returned to base.",
        "taxonomy": "ENV",
        "priority": "M",
        "severity": 3,
        "probability": 3,
        "hfacs": ["PE101", "AE201"],
        "department": "Flight Operations",
        "source": "VSR Report",
        "occurrence_type": "Incident",
    },
    {
        "title": "Downdraft Encounter on Mountain Ridge Crossing",
        "description": "Helicopter crossing mountain ridge encountered severe "
        "downdraft of 1,200ft/min, causing altitude loss of 400ft. Pilot "
        "applied maximum power and recovered.",
        "taxonomy": "ENV",
        "priority": "H",
        "severity": 4,
        "probability": 2,
        "hfacs": ["PE101", "AE102", "SP001"],
        "department": "Flight Operations",
        "source": "Flight Data Monitoring",
        "occurrence_type": "Serious Incident",
    },
    # -------------------- HEMS / EMERGENCY OPERATIONS --------------------
    {
        "title": "Night HEMS Landing Zone — Obstruction Hazards",
        "description": "Night HEMS landing at accident site with unmarked power "
        "lines and uneven terrain. Crew identified hazards during final "
        "approach and executed go-around.",
        "taxonomy": "ENV",
        "priority": "H",
        "severity": 5,
        "probability": 2,
        "hfacs": ["PE101", "SP001", "OP002"],
        "department": "Flight Operations",
        "source": "Quality Audit",
        "occurrence_type": "Serious Incident",
    },
    {
        "title": "HEMS Landing Zone — Inadequate Ground Coordination",
        "description": "Ambulance crew positioned vehicle within 10m of landing "
        "zone without communication. Helicopter crew identified hazard during "
        "approach and repositioned.",
        "taxonomy": "HUM",
        "priority": "M",
        "severity": 3,
        "probability": 3,
        "hfacs": ["PC104", "AE201", "SI001"],
        "department": "Flight Operations",
        "source": "Safety Inspection",
        "occurrence_type": "Incident",
    },
    {
        "title": "Hoist Operation — Load Swing Hazard",
        "description": "SAR hoist operation in mountainous terrain experienced "
        "load swing due to gusting winds. Load struck the cabin door, causing "
        "minor damage.",
        "taxonomy": "ENV",
        "priority": "M",
        "severity": 3,
        "probability": 2,
        "hfacs": ["PE101", "AE102", "SP001"],
        "department": "Flight Operations",
        "source": "MOR Report",
        "occurrence_type": "Incident",
    },
    # -------------------- MAINTENANCE --------------------
    {
        "title": "Tail Rotor Blade Crack Discovery",
        "description": "During scheduled 100-hour inspection, maintenance crew "
        "discovered a 2-inch crack in one of the tail rotor blades near the "
        "root. Fleet-wide inspection ordered.",
        "taxonomy": "TEC",
        "priority": "H",
        "severity": 5,
        "probability": 1,
        "hfacs": ["PC105", "AE201", "OP001"],
        "department": "Part-145",
        "source": "Quality Audit",
        "occurrence_type": "Serious Incident",
    },
    {
        "title": "Engine Chip Light Activation",
        "description": "Engine chip light illuminated during cruise. Crew "
        "landed at nearest suitable location. Metal particles found in oil "
        "filter requiring engine overhaul.",
        "taxonomy": "TEC",
        "priority": "H",
        "severity": 4,
        "probability": 2,
        "hfacs": ["PC105", "AE101", "OP003"],
        "department": "Part-145",
        "source": "MOR Report",
        "occurrence_type": "Serious Incident",
    },
    {
        "title": "Vibration Monitoring System (VMS) Warning",
        "description": "VMS warning for main rotor track and balance "
        "exceedance. Investigation revealed worn elastomeric bearings which "
        "were replaced.",
        "taxonomy": "TEC",
        "priority": "M",
        "severity": 3,
        "probability": 2,
        "hfacs": ["PC105", "OP001"],
        "department": "Part-145",
        "source": "Flight Data Monitoring",
        "occurrence_type": "Incident",
    },
]

# =============================================================================
# Airport Hazards (6) - ground / runway / apron
# =============================================================================

AIRPORT_HAZARDS: List[Dict[str, Any]] = [
    # -------------------- RUNWAY SAFETY --------------------
    {
        "title": "Foreign Object Debris (FOD) on Runway 25",
        "description": "Multiple instances of FOD (metal fragments, rubber "
        "deposits, construction debris) reported on Runway 25. Recent runway "
        "resurfacing work identified as primary source.",
        "taxonomy": "ENV",
        "priority": "M",
        "severity": 3,
        "probability": 4,
        "hfacs": ["PE201", "OP001"],
        "department": "Airport Operations",
        "source": "Safety Inspection",
        "occurrence_type": "Incident",
    },
    {
        "title": "Wildlife Incursion — Bird Strike Risk",
        "description": "Increased bird activity around Runway 25, particularly "
        "during morning and evening hours. Species identified: pigeons, kites, "
        "and occasional eagles.",
        "taxonomy": "WLD",
        "priority": "M",
        "severity": 3,
        "probability": 3,
        "hfacs": ["PE201", "OP002"],
        "department": "Airport Operations",
        "source": "Wildlife Hazard Assessment",
        "occurrence_type": "Incident",
    },
    {
        "title": "Reduced Runway Friction — Rubber Deposits",
        "description": "Runway friction tests show readings below acceptable "
        "levels for wet conditions. Friction readings 20% below recommended "
        "minimum for landing.",
        "taxonomy": "TEC",
        "priority": "M",
        "severity": 3,
        "probability": 3,
        "hfacs": ["OP001", "OP003"],
        "department": "Airport Operations",
        "source": "Safety Inspection",
        "occurrence_type": "Incident",
    },
    # -------------------- GROUND VEHICLE SAFETY --------------------
    {
        "title": "Airside Vehicle Incursion — Active Taxiway",
        "description": "Ground vehicle entered active taxiway without "
        "clearance. Vehicle departed runway safety area and driver reportedly "
        "distracted by radio communication.",
        "taxonomy": "HUM",
        "priority": "H",
        "severity": 4,
        "probability": 2,
        "hfacs": ["AE201", "PC101", "SI001"],
        "department": "Airport Operations",
        "source": "ATC Report",
        "occurrence_type": "Serious Incident",
    },
    {
        "title": "Unauthorized Personnel in Airside Area",
        "description": "Construction worker bypassed security checkpoint and "
        "was found in airside operational area. Access badge revoked and "
        "security procedures reviewed.",
        "taxonomy": "HUM",
        "priority": "M",
        "severity": 3,
        "probability": 2,
        "hfacs": ["AE201", "PC103", "SI002"],
        "department": "Airport Operations",
        "source": "Safety Inspection",
        "occurrence_type": "Incident",
    },
    # -------------------- APRON OPERATIONS --------------------
    {
        "title": "Fuel Spill During Aircraft Refueling",
        "description": "Approximately 50 liters of jet fuel spilled during "
        "aircraft refueling due to disconnect mishap. Spill contained within "
        "10 minutes. Environmental team deployed.",
        "taxonomy": "ENV",
        "priority": "L",
        "severity": 2,
        "probability": 2,
        "hfacs": ["PC101", "AE201"],
        "department": "Airport Operations",
        "source": "Safety Inspection",
        "occurrence_type": "Incident",
    },
]


class HazardSeeder(BaseSeeder):
    """Seed realistic hazards based on operator type using Supabase."""

    def __init__(
        self, tenant_ids: Optional[List[str]] = None, dry_run: bool = False
    ):
        super().__init__(tenant_ids=tenant_ids, dry_run=dry_run)
        self.hfacs_codes = self._load_hfacs_codes()

    # ------------------------------------------------------------------
    # HFACS code loading
    # ------------------------------------------------------------------

    def _load_hfacs_codes(self) -> Dict[str, Dict]:
        """Load HFACS codes from the raw JSON array file, keyed by code."""
        hfacs_path = os.path.join(
            os.path.dirname(__file__),
            "../../../public/data/hfacs_nanocodes.json",
        )
        try:
            with open(hfacs_path, "r", encoding="utf-8-sig") as f:
                # The file begins with several "// ..." header comment lines and
                # is otherwise a plain JSON *array* (NOT wrapped in a
                # {"nanocodes": [...]} object), so strip comments before parsing.
                raw = "".join(
                    line for line in f if not line.lstrip().startswith("//")
                )
                data = json.loads(raw)
                items = (
                    data if isinstance(data, list) else data.get("nanocodes", [])
                )
                return {item["code"]: item for item in items}
        except Exception as e:
            self.log_warning(f"Could not load HFACS codes: {e}")
            return {}

    def _validate_hfacs(self, codes: List[str]) -> None:
        """Log a warning for any HFACS code not present in the lookup table."""
        for code in codes:
            if code not in self.hfacs_codes:
                self.log_warning(f"Unknown HFACS code in template: {code}")

    # ------------------------------------------------------------------
    # PostgreSQL persistence helpers (async dispatched via bridge loop)
    # ------------------------------------------------------------------

    def _find_existing_hazard(self, tenant_id: str, title: str) -> Optional[str]:
        """Return the id of an existing hazard with this title, else None."""
        tid = register_tenant(tenant_id)

        async def _query() -> Optional[str]:
            async with session_scope() as session:
                result = await session.scalar(
                    select(Hazard.id).where(
                        Hazard.tenant_id == tid,
                        Hazard.title == title,
                        Hazard.is_demo == demo_scope(),
                    )
                )
                return str(result) if result else None

        return run(_query())

    def _create_hazard(self, tenant_id: str, hazard_data: Dict) -> Optional[str]:
        """Create a single hazard in PostgreSQL. Skip if already exists."""
        title = hazard_data["title"]

        if self.dry_run:
            self.log_info(f"[DRY RUN] Would create hazard: {title}")
            self.created_count += 1
            return "dry-run-id"

        existing = self._find_existing_hazard(tenant_id, title)
        if existing:
            self.skipped_count += 1
            self.log_info(f"Skipped existing hazard: {title}")
            return None

        try:
            service = HazardService(tenant_id=tenant_id)
            seeder_user = {
                "uid": SEEDER_EMAIL,
                "email": SEEDER_EMAIL,
                "role": "SUPER_ADMIN",
                "tenant_id": tenant_id,
            }
            # source_id == SEED_SOURCE_ID tags the row so unseed() can remove
            # exactly the seeded hazards.
            result = service.create_hazard_v1(
                {
                    "title": title,
                    "description": hazard_data["description"],
                    "taxonomy": hazard_data["taxonomy"],
                    "priority": hazard_data["priority"],
                    "severity": hazard_data["severity"],
                    "probability": hazard_data["probability"],
                    "source": hazard_data.get("source", "Hazard Seeder"),
                    "source_id": SEED_SOURCE_ID,
                    "department": hazard_data.get("department", ""),
                    "occurrence_type": hazard_data.get(
                        "occurrence_type", "Incident"
                    ),
                    "hfacs_codes": hazard_data.get("hfacs", []),
                },
                seeder_user,
            )
            self.created_count += 1
            self.log_info(f"Created hazard: {title}")
            return result.get("id")
        except Exception as e:
            self.log_error(f"Failed to create hazard {title}: {e}")
            return None

    def _get_hazards_for_tenant(self, tenant_id: str) -> List[Dict]:
        """Return the hazard templates for a specific tenant type."""
        if tenant_id == "fixedwing":
            return FIXED_WING_HAZARDS
        elif tenant_id == "rotarywing":
            return ROTARY_WING_HAZARDS
        elif tenant_id == "demoairport":
            return AIRPORT_HAZARDS
        else:  # demostate (regulator) has no hazards
            return []

    # ------------------------------------------------------------------
    # BaseSeeder interface
    # ------------------------------------------------------------------

    def seed(self) -> Dict[str, Any]:
        """Seed hazards for all configured tenants."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        self.log_info("=" * 60)
        self.log_info("Starting HazardSeeder (Supabase/PostgreSQL)...")
        self.log_info("=" * 60)

        for tenant in self._get_tenant_ids():
            if not self._is_demo_tenant(tenant):
                self.log_warning(f"Skipping non-demo tenant: {tenant}")
                continue
            self.log_info(f"Seeding hazards for tenant: {tenant}")
            hazards = self._get_hazards_for_tenant(tenant)
            self.log_info(f"  Found {len(hazards)} hazard templates")
            for hazard in hazards:
                self._validate_hfacs(hazard.get("hfacs", []))
                self._create_hazard(tenant, hazard)

        self.log_info("=" * 60)
        self.log_info(
            f"HazardSeeder complete: created={self.created_count} "
            f"skipped={self.skipped_count} errors={len(self.errors)}"
        )
        self.log_info("=" * 60)

        return self.get_summary()

    def unseed(self) -> Dict[str, Any]:
        """Remove all hazards created by this seeder from PostgreSQL."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        self.log_info("=" * 60)
        self.log_info("Starting HazardSeeder unseed...")
        self.log_info("=" * 60)

        for tenant in self._get_tenant_ids():
            if not self._is_demo_tenant(tenant):
                continue
            tid = register_tenant(tenant)

            if self.dry_run:
                self.log_info(
                    f"[DRY RUN] Would remove seeded hazards for tenant: {tenant}"
                )
                continue

            async def _remove() -> int:
                async with session_scope() as session:
                    result = await session.execute(
                        delete(Hazard).where(
                            Hazard.tenant_id == tid,
                            Hazard.source_id == SEED_SOURCE_ID,
                            Hazard.is_demo == demo_scope(),
                        )
                    )
                    return result.rowcount or 0

            try:
                removed = run(_remove())
                self.created_count += removed
                self.log_info(
                    f"Removed {removed} seeded hazards for tenant: {tenant}"
                )
            except Exception as e:
                self.log_error(
                    f"Failed to unseed hazards for tenant {tenant}: {e}"
                )

        self.log_info(
            f"HazardSeeder unseed complete: removed={self.created_count}"
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

    seeder = HazardSeeder(tenant_ids=tenants, dry_run=dry_run)
    result = seeder.seed() if seed_mode == "seed" else seeder.unseed()
    print(json.dumps(result, indent=2, default=str))
