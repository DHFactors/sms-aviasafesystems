# ============================================================================
# FILE: can_seeder.py
# PATH: backend/seeders/cans_caps/can_seeder.py
# PURPOSE: Seed / unseed realistic Corrective Action Notices (CANs) using
#          Supabase (PostgreSQL) via the SQLAlchemy Can model and
#          CanCapService, linking each CAN to an existing seeded hazard.
#
# Actor mapping:
#   * CAN issuer  -> Safety Manager (safety@*.com)
#   * CAN assignee-> Part-145 / CAMO / Ops depending on the hazard type
#
# Each CAN resolves its hazard via the Hazard.id uuid so it always links to a
# real seeded hazard (never auto-creating stub hazards). If the matching hazard
# is not present, the CAN is skipped with a warning instead.
#
# Invocation (from backend/):
#   python -m seeders.cans_caps.can_seeder seed                    # all tenants
#   python -m seeders.cans_caps.can_seeder seed --tenants fixedwing
#   python -m seeders.cans_caps.can_seeder seed --dry-run
#   python -m seeders.cans_caps.can_seeder unseed
# ============================================================================

import json
import sys
import random
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select

from seeders import BaseSeeder
from seeders.utils.date_utils import get_random_date
from app.db.ids import register_tenant
from app.db.isolation import demo_scope
from app.db.runner import run
from app.db.session import session_scope
from app.db.db_models import Can, Hazard
from app.services.can_cap_service import CanCapService


def _role_token_for_email(email: str) -> str:
    """Derive the role token from the email local part (e.g. 145 --> 145)."""
    return email.split("@")[0]


def _uid_for(email: str) -> str:
    """Deterministic uid, consistent with the tenant seeder's
    {role_token}-{tenant_id}-001 scheme."""
    token = _role_token_for_email(email)
    tenant = email.split("@")[1].split(".")[0]
    return f"{token}-{tenant}-001"


# Safety Manager issuer per tenant (used for issued_by / issued_by_uid).
ISSUERS: Dict[str, Dict[str, str]] = {
    "fixedwing": {"email": "safety@fixedwing.com", "name": "Capt. Rajesh Thapa"},
    "rotarywing": {"email": "safety@rotarywing.com", "name": "Capt. Hari Pandey"},
    "demoairport": {"email": "safety@demoairport.com", "name": "Mr. Kumar Bhandari"},
}

# =============================================================================
# CAN templates (keyed by tenant id; demostate seeds no CANs)
# =============================================================================

CAN_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "fixedwing": [
        {
            # CAN-26-001 -> Hazard: Engine Oil Pressure Fluctuation (TEC) -> Part-145
            "title": "CAN-26-001: Engine System Investigation Required",
            "description": "Following hazard identification by Safety Manager "
            "Capt. Rajesh Thapa regarding engine oil pressure fluctuations on "
            "aircraft 9N-ABC, this Corrective Action Notice is issued to the "
            "Part-145 department. Investigation required to determine root "
            "cause and implement corrective action.",
            "required_action": "Conduct full engine borescope inspection, oil "
            "analysis, and determine root cause of oil pressure fluctuations. "
            "Submit findings within 14 days.",
            "priority": "High",
            "initial_severity": 3,
            "initial_probability": 2,
            "assigned_to_name": "Mr. Dipak Rai",
            "assigned_to_email": "145@fixedwing.com",
            "department": "Part-145",
            "hazard_keywords": ["engine oil pressure", "oil pressure"],
        },
        {
            # CAN-26-002 -> Hazard: Cabin Pressurization Warning (TEC) -> Part-145
            "title": "CAN-26-002: System Compliance Review Required",
            "description": "Following hazard identification by Safety Manager "
            "Capt. Rajesh Thapa regarding cabin pressurization warning during "
            "descent on aircraft 9N-DEF, this Corrective Action Notice is "
            "issued to the CAMO department. Review system compliance and "
            "maintenance records.",
            "required_action": "Conduct full audit of cabin pressurization "
            "system maintenance records and AD compliance. Implement "
            "corrective action to prevent recurrence. Submit findings within "
            "30 days.",
            "priority": "High",
            "initial_severity": 3,
            "initial_probability": 2,
            "assigned_to_name": "Mr. Suresh Ghale",
            "assigned_to_email": "camo@fixedwing.com",
            "department": "CAMO",
            "hazard_keywords": ["cabin pressurization", "pressurization"],
        },
        {
            # CAN-26-003 -> Hazard: Unstabilized Approach (HUM) -> Ops
            "title": "CAN-26-003: Flight Operations Procedures Review",
            "description": "Following hazard identification by Safety Manager "
            "Capt. Rajesh Thapa regarding unstabilized approach incidents, "
            "this Corrective Action Notice is issued to the Flight Operations "
            "department. Review approach procedures and training.",
            "required_action": "Conduct flight operations procedures review, "
            "crew training, and update SOPs for approach and landing. Submit "
            "completion report within 45 days.",
            "priority": "High",
            "initial_severity": 4,
            "initial_probability": 3,
            "assigned_to_name": "Capt. Sanjay Gurung",
            "assigned_to_email": "ops@fixedwing.com",
            "department": "Flight Operations",
            "hazard_keywords": ["unstabilized approach", "unstable approach"],
        },
    ],
    "rotarywing": [
        {
            # CAN-26-004 -> Hazard: Tail Rotor Blade Crack (TEC) -> Part-145
            "title": "CAN-26-004: Tail Rotor Blade Inspection Required",
            "description": "Following hazard identification by Safety Manager "
            "Capt. Hari Pandey regarding tail rotor blade crack on helicopter "
            "9N-RWX, this Corrective Action Notice is issued to the Part-145 "
            "department. Fleet-wide tail rotor blade inspection required.",
            "required_action": "Conduct tail rotor blade inspections on all "
            "fleet helicopters. Report findings to Safety Department. "
            "Implement corrective action as required. Submit initial report "
            "within 14 days.",
            "priority": "High",
            "initial_severity": 5,
            "initial_probability": 1,
            "assigned_to_name": "Mr. Shiva Tamang",
            "assigned_to_email": "145@rotarywing.com",
            "department": "Part-145",
            "hazard_keywords": ["tail rotor blade", "tail rotor", "crack"],
        },
        {
            # CAN-26-005 -> Hazard: LTE (ENV) -> Ops
            "title": "CAN-26-005: LTE Training and Procedures Review",
            "description": "Following hazard identification by Safety Manager "
            "Capt. Hari Pandey regarding Loss of Tail Rotor Effectiveness "
            "incident at high-altitude helipad, this Corrective Action Notice "
            "is issued to the Flight Operations department. Review LTE "
            "procedures and training.",
            "required_action": "Review LTE training curriculum. Conduct "
            "refresher training for all helicopter pilots. Update SOPs for "
            "high-altitude operations. Submit completion report within 30 "
            "days.",
            "priority": "High",
            "initial_severity": 4,
            "initial_probability": 2,
            "assigned_to_name": "Capt. Ram Koirala",
            "assigned_to_email": "ops@rotarywing.com",
            "department": "Flight Operations",
            "hazard_keywords": ["tail rotor effectiveness", "lte"],
        },
    ],
    "demoairport": [
        {
            # CAN-26-006 -> Hazard: Runway FOD (ENV) -> Ops (airport)
            "title": "CAN-26-006: Runway FOD Management Required",
            "description": "Following hazard identification by Safety Manager "
            "Mr. Kumar Bhandari regarding FOD on Runway 25, this Corrective "
            "Action Notice is issued to the Airport Operations department. "
            "FOD management and prevention measures required.",
            "required_action": "Implement FOD prevention measures on Runway "
            "25. Conduct daily FOD inspections. Submit compliance report "
            "within 21 days.",
            "priority": "Medium",
            "initial_severity": 3,
            "initial_probability": 4,
            "assigned_to_name": "Mr. Ramesh Adhikari",
            "assigned_to_email": "ops@demoairport.com",
            "department": "Airport Operations",
            "hazard_keywords": ["foreign object", "fod", "debris"],
        },
    ],
}


class CanSeeder(BaseSeeder):
    """Seed / unseed CANs linked to existing seeded hazards."""

    def __init__(
        self, tenant_ids: Optional[List[str]] = None, dry_run: bool = False
    ):
        super().__init__(tenant_ids=tenant_ids, dry_run=dry_run)

    # ------------------------------------------------------------------
    # PostgreSQL persistence helpers (async dispatched via bridge loop)
    # ------------------------------------------------------------------

    def _find_hazard_for_keywords(
        self, tenant_id: str, keywords: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Return the id (uuid) and created_at of a seeded hazard matching any
        keyword, else None."""
        tid = register_tenant(tenant_id)
        lowered = [k.lower() for k in keywords if k]

        async def _query() -> Optional[Dict[str, Any]]:
            async with session_scope() as session:
                rows = (
                    await session.execute(
                        select(Hazard).where(
                            Hazard.tenant_id == tid,
                            Hazard.is_demo == demo_scope(),
                        )
                    )
                ).scalars().all()
                for h in rows:
                    title = (h.title or "").lower()
                    desc = (h.description or "").lower()
                    if any(k in title or k in desc for k in lowered):
                        return {
                            "id": str(h.id),
                            "created_at": h.created_at,
                        }
                return None

        return run(_query())

    def _can_exists(self, tenant_id: str, title: str) -> bool:
        """Return True if a CAN with this title already exists for the tenant."""
        tid = register_tenant(tenant_id)

        async def _query() -> bool:
            async with session_scope() as session:
                row = await session.scalar(
                    select(Can.id).where(
                        Can.tenant_id == tid,
                        Can.title == title,
                        Can.is_demo == demo_scope(),
                    )
                )
                return row is not None

        return run(_query())

    def _create_can(self, tenant_id: str, can_data: Dict) -> Optional[str]:
        """Create a single CAN linked to a seeded hazard. Skip if already
        exists or no matching hazard is found."""
        title = can_data["title"]

        if self.dry_run:
            self.log_info(f"[DRY RUN] Would create CAN: {title}")
            self.created_count += 1
            return "dry-run-id"

        if self._can_exists(tenant_id, title):
            self.skipped_count += 1
            self.log_info(f"Skipped existing CAN: {title}")
            return None

        # Resolve the linked hazard so we never create stub hazards.
        hazard = self._find_hazard_for_keywords(
            tenant_id, can_data.get("hazard_keywords", [])
        )
        if not hazard:
            self.log_warning(
                f"Skipping CAN with no matching seeded hazard: {title}"
            )
            self.skipped_count += 1
            return None
        hazard_id = hazard["id"]

        issuer = ISSUERS.get(
            tenant_id, {"email": "safety@aviasafe.com", "name": "Safety Manager"}
        )
        issuer_user = {
            "uid": _uid_for(issuer["email"]),
            "email": issuer["email"],
            "role": "AIRLINE_ADMIN",
            "tenant_id": tenant_id,
        }

        # Issue the CAN AFTER the linked hazard was created, so the chain
        # Hazard -> CAN is chronologically valid. Issued within 1-90 days of
        # the hazard being created, with a target 30-90 days after issuance.
        hazard_created = hazard.get("created_at") or get_random_date(
            start_days_ago=700, end_days_ago=30
        )
        if hasattr(hazard_created, "date"):
            can_base = hazard_created
            delta_days = random.randint(1, 90)
        else:
            can_base = get_random_date(start_days_ago=700, end_days_ago=30)
            delta_days = 0
        can_date = can_base + timedelta(days=delta_days)
        target_date = can_date + timedelta(days=random.randint(30, 90))

        # assigned_to holds the assignee email (used by notifications and
        # department resolution). The display name is kept in the template.
        payload = {
            "hazard_id": hazard_id,
            "title": title,
            "description": can_data["description"],
            "required_action": can_data["required_action"],
            "priority": can_data["priority"],
            "initial_severity": can_data["initial_severity"],
            "initial_probability": can_data["initial_probability"],
            "assigned_to": can_data["assigned_to_email"],
            "assigned_to_uid": _uid_for(can_data["assigned_to_email"]),
            "department": can_data["department"],
            "target_completion_date": target_date,
            "issued_at": can_date,
            "copies_to": None,
        }

        try:
            service = CanCapService(tenant_id=tenant_id)
            result = service.issue_can(payload, issuer_user)
            self.created_count += 1
            self.log_info(
                f"Created CAN: {title} (issued_at={can_date.isoformat()}, "
                f"target={target_date.date().isoformat()})"
            )
            return result.get("id")
        except Exception as e:
            self.log_error(f"Failed to create CAN {title}: {e}")
            return None

    def _get_can_templates(self, tenant_id: str) -> List[Dict]:
        return CAN_TEMPLATES.get(tenant_id, [])

    # ------------------------------------------------------------------
    # BaseSeeder interface
    # ------------------------------------------------------------------

    def seed(self) -> Dict[str, Any]:
        """Seed CANs for all configured tenants."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        self.log_info("=" * 60)
        self.log_info("Starting CanSeeder (Supabase/PostgreSQL)...")
        self.log_info("=" * 60)

        for tenant in self._get_tenant_ids():
            if not self._is_demo_tenant(tenant):
                self.log_warning(f"Skipping non-demo tenant: {tenant}")
                continue
            self.log_info(f"Seeding CANs for tenant: {tenant}")
            templates = self._get_can_templates(tenant)
            self.log_info(f"  Found {len(templates)} CAN templates")
            for template in templates:
                self._create_can(tenant, template)

        self.log_info("=" * 60)
        self.log_info(
            f"CanSeeder complete: created={self.created_count} "
            f"skipped={self.skipped_count} errors={len(self.errors)}"
        )
        self.log_info("=" * 60)

        return self.get_summary()

    def unseed(self) -> Dict[str, Any]:
        """Remove all CANs created by this seeder from PostgreSQL."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        self.log_info("=" * 60)
        self.log_info("Starting CanSeeder unseed...")
        self.log_info("=" * 60)

        for tenant in self._get_tenant_ids():
            if not self._is_demo_tenant(tenant):
                continue
            tid = register_tenant(tenant)
            titles = [t["title"] for t in self._get_can_templates(tenant)]
            if not titles:
                continue

            if self.dry_run:
                self.log_info(
                    f"[DRY RUN] Would remove {len(titles)} seeded CANs for "
                    f"tenant: {tenant}"
                )
                continue

            async def _remove() -> int:
                async with session_scope() as session:
                    result = await session.execute(
                        delete(Can).where(
                            Can.tenant_id == tid,
                            Can.title.in_(titles),
                            Can.is_demo == demo_scope(),
                        )
                    )
                    return result.rowcount or 0

            try:
                removed = run(_remove())
                self.created_count += removed
                self.log_info(
                    f"Removed {removed} seeded CANs for tenant: {tenant}"
                )
            except Exception as e:
                self.log_error(
                    f"Failed to unseed CANs for tenant {tenant}: {e}"
                )

        self.log_info(f"CanSeeder unseed complete: removed={self.created_count}")
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

    seeder = CanSeeder(tenant_ids=tenants, dry_run=dry_run)
    result = seeder.seed() if seed_mode == "seed" else seeder.unseed()
    print(json.dumps(result, indent=2, default=str))
