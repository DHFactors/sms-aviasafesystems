# ============================================================================
# FILE: diversion_seeder.py
# PATH: backend/seeders/diversions/diversion_seeder.py
# PURPOSE: Seed / unseed realistic flight diversion records via the live
#          FlightDiversionService. Diversions are persisted to FIRESTORE in
#          the tenant-scoped ``flight_diversions`` collection (see
#          app/services/flight_diversion_service.py), matching how the app
#          actually reads/writes diversion data.
#
# Actor mapping: diversions are recorded by the Ops / Safety department
# manager (ops@*.test / safety@*.test), consistent with the CAN/CAP seeders.
#
# Each diversion is created through FlightDiversionService.create_diversion
# so generated references follow the service format DIV-{YYYY}-{seq:03d}.
# Seeded records are identified for unseed by their distinct description.
#
# Invocation (from backend/):
#   python -m seeders.diversions.diversion_seeder seed
#   python -m seeders.diversions.diversion_seeder seed --tenants fixedwing
#   python -m seeders.diversions.diversion_seeder seed --dry-run
#   python -m seeders.diversions.diversion_seeder unseed
# ============================================================================

import json
import sys
from typing import Any, Dict, List, Optional

from seeders import BaseSeeder
from seeders.utils.date_utils import get_random_date
from app.services.flight_diversion_service import FlightDiversionService


def _role_token_for_email(email: str) -> str:
    """Derive the role token from the email local part (e.g. 145 --> 145)."""
    return email.split("@")[0]


def _uid_for(email: str) -> str:
    """Deterministic uid, consistent with the tenant seeder's
    {role_token}-{tenant_id}-001 scheme."""
    token = _role_token_for_email(email)
    tenant = email.split("@")[1].split(".")[0]
    return f"{token}-{tenant}-001"


# Department Manager recorder per tenant (used for created_by).
RECORDERS: Dict[str, Dict[str, str]] = {
    "fixedwing": {"email": "ops@fixedwing.test", "name": "Capt. Sanjay Gurung"},
    "rotarywing": {"email": "ops@rotarywing.test", "name": "Capt. Ram Koirala"},
    "demoairport": {"email": "ops@demoairport.test", "name": "Mr. Ramesh Adhikari"},
}


# =============================================================================
# Diversion templates (keyed by tenant id; demostate seeds no diversions)
# =============================================================================

DIVERSION_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "fixedwing": [
        {
            "flight_number": "FW-421",
            "aircraft_registration": "9N-ABC",
            "sector_from": "VNKT",
            "sector_to": "VNSI",
            "diverted_to": "VNBG",
            "reason": "Weather",
            "reason_details": "Thunderstorm and severe wind shear reported "
            "on approach to Simara (VNSI); ATC advised diversion.",
            "captain": "Capt. Sanjay Gurung",
            "first_officer": "F/O Prashant Karki",
            "air_hostess": "Ms. Anju Shrestha",
            "description": "FW-421 (9N-ABC) from Kathmandu (VNKT) to Simara "
            "(VNSI) diverted to Bhairahawa (VNBG) due to thunderstorm and "
            "severe wind shear on approach.",
            "additional_fuel_cost": 1850.00,
            "passenger_impact": 42,
            "delay_minutes": 145,
            "remarks": "Passengers accommodated on alternate transport; "
            "no injuries reported.",
        },
        {
            "flight_number": "FW-208",
            "aircraft_registration": "9N-DEF",
            "sector_from": "VNKT",
            "sector_to": "VNBG",
            "diverted_to": "VNSI",
            "reason": "Technical",
            "reason_details": "Cabin pressurization warning during climb; "
            "crew actioned checklist and returned to lower altitude.",
            "captain": "Capt. Sanjay Gurung",
            "first_officer": "F/O Prashant Karki",
            "description": "FW-208 (9N-DEF) from Kathmandu (VNKT) to "
            "Bhairahawa (VNBG) diverted to Simara (VNSI) following a cabin "
            "pressurization warning during climb.",
            "additional_fuel_cost": 920.00,
            "passenger_impact": 38,
            "delay_minutes": 60,
            "remarks": "Returned to service after maintenance inspection.",
        },
        {
            "flight_number": "FW-312",
            "aircraft_registration": "9N-GHI",
            "sector_from": "VNSI",
            "sector_to": "VNKT",
            "diverted_to": "VNPK",
            "reason": "Medical",
            "reason_details": "Passenger reported severe chest pain; "
            "nearest suitable divert airfield selected.",
            "captain": "Capt. Sanjay Gurung",
            "first_officer": "F/O Prashant Karki",
            "description": "FW-312 (9N-GHI) from Simara (VNSI) to Kathmandu "
            "(VNKT) diverted to Pokhara (VNPK) for a medical emergency.",
            "additional_fuel_cost": 620.00,
            "passenger_impact": 1,
            "delay_minutes": 95,
            "remarks": "Emergency services met the aircraft; passenger "
            "transported to hospital.",
        },
    ],
    "rotarywing": [
        {
            "flight_number": "RW-115",
            "aircraft_registration": "9N-RWX",
            "sector_from": "VNKT",
            "sector_to": "VNJT",
            "diverted_to": "VNSB",
            "reason": "Weather",
            "reason_details": "Low cloud and reduced visibility at Jumla "
            "(VNJT); diverted to Simikot (VNSB).",
            "captain": "Capt. Ram Koirala",
            "first_officer": "F/O Bikram Malla",
            "description": "RW-115 (9N-RWX) from Kathmandu (VNKT) to Jumla "
            "(VNJT) diverted to Simikot (VNSB) due to low cloud at the "
            "destination.",
            "additional_fuel_cost": 480.00,
            "passenger_impact": 18,
            "delay_minutes": 110,
            "remarks": "Recovered to Jumla the following morning.",
        },
        {
            "flight_number": "RW-203",
            "aircraft_registration": "9N-RWL",
            "sector_from": "VNSI",
            "sector_to": "VNKT",
            "diverted_to": "VNPK",
            "reason": "Technical",
            "reason_details": "Main rotor chip detector advisory illuminated; "
            "precautionary diversion and landing.",
            "captain": "Capt. Ram Koirala",
            "first_officer": "F/O Bikram Malla",
            "description": "RW-203 (9N-RWL) from Simara (VNSI) to Kathmandu "
            "(VNKT) diverted to Pokhara (VNPK) following a main rotor chip "
            "detector advisory.",
            "additional_fuel_cost": 350.00,
            "passenger_impact": 15,
            "delay_minutes": 75,
            "remarks": "Placed out of service pending gearbox inspection.",
        },
    ],
    "demoairport": [
        {
            "flight_number": "AP-901",
            "aircraft_registration": "9N-ABC",
            "sector_from": "VNKT",
            "sector_to": "VNSI",
            "diverted_to": "VNBG",
            "reason": "Airport Closure",
            "reason_details": "Runway closed for FOD removal and repair at "
            "Simara (VNSI).",
            "captain": "Capt. Sanjay Gurung",
            "description": "AP-901 (9N-ABC) from Kathmandu (VNKT) to Simara "
            "(VNSI) diverted to Bhairahawa (VNBG) after runway closure for "
            "FOD removal at the destination.",
            "additional_fuel_cost": 1150.00,
            "passenger_impact": 39,
            "delay_minutes": 130,
            "remarks": "Runway reopened; flight operated the next morning.",
        },
        {
            "flight_number": "AP-905",
            "aircraft_registration": "9N-DEF",
            "sector_from": "VNSI",
            "sector_to": "VNKT",
            "diverted_to": "VNPK",
            "reason": "Operational",
            "reason_details": "Crew duty time approaching limit; diverted to "
            "nearest suitable airfield to comply with rest requirements.",
            "captain": "Capt. Sanjay Gurung",
            "description": "AP-905 (9N-DEF) from Simara (VNSI) to Kathmandu "
            "(VNKT) diverted to Pokhara (VNPK) to manage crew duty time.",
            "additional_fuel_cost": 540.00,
            "passenger_impact": 41,
            "delay_minutes": 88,
            "remarks": "Crew rested overnight; recovery to Kathmandu next day.",
        },
    ],
}


class DiversionSeeder(BaseSeeder):
    """Seed / unseed flight diversion records in Firestore."""

    def __init__(
        self, tenant_ids: Optional[List[str]] = None, dry_run: bool = False
    ):
        super().__init__(tenant_ids=tenant_ids, dry_run=dry_run)
        self._db = None

    @property
    def db(self):
        if self._db is None:
            from app.firebase import get_db
            self._db = get_db()
        return self._db

    def _collection(self, tenant_id: str):
        from app.firebase import get_tenant_collection
        return get_tenant_collection(tenant_id, "flight_diversions")

    def _diversion_exists(self, tenant_id: str, description: str) -> bool:
        """Return True if a diversion with this exact description already
        exists in the tenant's Firestore collection."""
        for doc in self._collection(tenant_id).stream():
            if doc.to_dict().get("description") == description:
                return True
        return False

    def _create_diversion(self, tenant_id: str, div_data: Dict) -> Optional[str]:
        description = div_data["description"]

        if self.dry_run:
            self.log_info(f"[DRY RUN] Would create diversion: {description}")
            self.created_count += 1
            return "dry-run-id"

        if self._diversion_exists(tenant_id, description):
            self.skipped_count += 1
            self.log_info(f"Skipped existing diversion: {description}")
            return None

        recorder = RECORDERS.get(
            tenant_id, {"email": "ops@aviasafe.com", "name": "Ops Manager"}
        )
        recorder_user = {
            "uid": _uid_for(recorder["email"]),
            "email": recorder["email"],
            "role": "DEPT_ADMIN",
            "tenant_id": tenant_id,
        }

        payload = {
            "date": get_random_date(start_days_ago=730, end_days_ago=7),
            "flight_number": div_data["flight_number"],
            "aircraft_registration": div_data["aircraft_registration"],
            "sector_from": div_data["sector_from"],
            "sector_to": div_data["sector_to"],
            "diverted_to": div_data["diverted_to"],
            "reason": div_data["reason"],
            "reason_details": div_data.get("reason_details"),
            "captain": div_data.get("captain"),
            "first_officer": div_data.get("first_officer"),
            "air_hostess": div_data.get("air_hostess"),
            "description": description,
            "additional_fuel_cost": div_data.get("additional_fuel_cost"),
            "passenger_impact": div_data.get("passenger_impact"),
            "delay_minutes": div_data.get("delay_minutes"),
            "remarks": div_data.get("remarks"),
        }

        try:
            service = FlightDiversionService(tenant_id=tenant_id)
            result = service.create_diversion(payload, recorder_user)
            self.created_count += 1
            self.log_info(
                f"Created diversion {result.get('diversion_id')}: "
                f"{description}"
            )
            return result.get("id")
        except Exception as e:
            self.log_error(f"Failed to create diversion {description}: {e}")
            return None

    def _get_templates(self, tenant_id: str) -> List[Dict]:
        return DIVERSION_TEMPLATES.get(tenant_id, [])

    # ------------------------------------------------------------------
    # BaseSeeder interface
    # ------------------------------------------------------------------

    def seed(self) -> Dict[str, Any]:
        """Seed diversions for all configured operator tenants."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        self.log_info("=" * 60)
        self.log_info("Starting DiversionSeeder (Firestore)...")
        self.log_info("=" * 60)

        for tenant in self._get_tenant_ids():
            if not self._is_demo_tenant(tenant):
                self.log_warning(f"Skipping non-demo tenant: {tenant}")
                continue
            templates = self._get_templates(tenant)
            if not templates:
                self.log_info(f"No diversion templates for tenant: {tenant}")
                continue
            self.log_info(f"Seeding diversions for tenant: {tenant}")
            for template in templates:
                self._create_diversion(tenant, template)

        self.log_info("=" * 60)
        self.log_info(
            f"DiversionSeeder complete: created={self.created_count} "
            f"skipped={self.skipped_count} errors={len(self.errors)}"
        )
        self.log_info("=" * 60)

        return self.get_summary()

    def unseed(self) -> Dict[str, Any]:
        """Remove all diversions created by this seeder from Firestore."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        self.log_info("=" * 60)
        self.log_info("Starting DiversionSeeder unseed...")
        self.log_info("=" * 60)

        for tenant in self._get_tenant_ids():
            if not self._is_demo_tenant(tenant):
                continue
            templates = self._get_templates(tenant)
            descriptions = [t["description"] for t in templates]
            if not descriptions:
                continue

            if self.dry_run:
                self.log_info(
                    f"[DRY RUN] Would remove {len(descriptions)} seeded "
                    f"diversions for tenant: {tenant}"
                )
                self.created_count += len(descriptions)
                continue

            removed = 0
            try:
                for doc in self._collection(tenant).stream():
                    data = doc.to_dict() or {}
                    if data.get("description") in descriptions:
                        doc.reference.delete()
                        removed += 1
                        self.log_info(
                            f"Removed diversion {data.get('diversion_id')} "
                            f"for tenant: {tenant}"
                        )
            except Exception as e:
                self.log_error(
                    f"Failed to unseed diversions for tenant {tenant}: {e}"
                )
            self.created_count += removed

        self.log_info(
            f"DiversionSeeder unseed complete: removed={self.created_count}"
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
            tenants = [t.strip() for t in args[idx + 1].split(",") if t.strip()]

    seeder = DiversionSeeder(tenant_ids=tenants, dry_run=dry_run)
    result = seeder.seed() if seed_mode == "seed" else seeder.unseed()
    print(json.dumps(result, indent=2, default=str))
