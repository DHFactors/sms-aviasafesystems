# ============================================================================
# FILE: cap_seeder.py
# PATH: backend/seeders/cans_caps/cap_seeder.py
# PURPOSE: Seed / unseed realistic Corrective Action Plans (CAPs) using
#          Supabase (PostgreSQL) via the SQLAlchemy Cap model and
#          CanCapService, linking each CAP to an existing seeded CAN.
#
# Actor mapping:
#   * CAP submitter -> Department Manager (Part-145 / CAMO / Ops)
#   * CAP reviewer  -> Safety Manager (safety@*.com)
#
# Each CAP resolves its CAN via the Can.id uuid so it always links to a real
# seeded CAN. If the matching CAN is not present (e.g. CAN Seeder not run for
# this tenant), the CAP is skipped with a warning.
#
# Invocation (from backend/):
#   python -m seeders.cans_caps.cap_seeder seed                    # all tenants
#   python -m seeders.cans_caps.cap_seeder seed --tenants fixedwing
#   python -m seeders.cans_caps.cap_seeder seed --dry-run
#   python -m seeders.cans_caps.cap_seeder unseed
# ============================================================================

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select

from seeders import BaseSeeder
from app.db.ids import register_tenant
from app.db.isolation import demo_scope
from app.db.runner import run
from app.db.session import session_scope
from app.db.db_models import Can, Cap
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


# Department Manager submitter per tenant per department. The CAP payload's
# action_plan holds the realistic narrative (the Cap table has no separate
# description column), so the review/assignee mapping is by department.
SUBMITTERS: Dict[str, Dict[str, Dict[str, str]]] = {
    "fixedwing": {
        "Part-145": {"email": "145@fixedwing.com", "name": "Mr. Dipak Rai"},
        "CAMO": {"email": "camo@fixedwing.com", "name": "Mr. Suresh Ghale"},
        "Flight Operations": {"email": "ops@fixedwing.com", "name": "Capt. Sanjay Gurung"},
    },
    "rotarywing": {
        "Part-145": {"email": "145@rotarywing.com", "name": "Mr. Shiva Tamang"},
        "Flight Operations": {"email": "ops@rotarywing.com", "name": "Capt. Ram Koirala"},
    },
    "demoairport": {
        "Airport Operations": {"email": "ops@demoairport.com", "name": "Mr. Ramesh Adhikari"},
    },
}


# =============================================================================
# CAP templates (keyed by tenant id; demostate seeds no CAPs)
# =============================================================================

CAP_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "fixedwing": [
        {
            # CAP-26-001 -> CAN-26-001 (Engine System Investigation) -> Part-145
            "action_plan": "Mr. Dipak Rai (Part-145 Manager) submits this "
            "Corrective Action Plan in response to CAN-26-001. The plan "
            "includes full engine borescope inspection, oil analysis, and "
            "replacement of affected components on aircraft 9N-ABC.",
            "timeline": "Phase 1: Borescope inspection (7 days). Phase 2: Oil "
            "analysis (14 days). Phase 3: Component replacement (21 days).",
            "target_completion_offset_days": 30,
            "department": "Part-145",
            "rca_method": "bow_tie",
            "residual_severity": 2,
            "residual_probability": 2,
            "can_keywords": ["engine system investigation", "engine"],
        },
        {
            # CAP-26-002 -> CAN-26-002 (System Compliance Review) -> CAMO
            "action_plan": "Mr. Suresh Ghale (CAMO Manager) submits this "
            "Corrective Action Plan in response to CAN-26-002. The plan "
            "includes a full audit of AD compliance records for all fleet "
            "aircraft and implementation of corrective actions.",
            "timeline": "Phase 1: Records review (14 days). Phase 2: Gap "
            "analysis (21 days). Phase 3: Corrective implementation (30 "
            "days).",
            "target_completion_offset_days": 45,
            "department": "CAMO",
            "rca_method": "fishbone",
            "residual_severity": 2,
            "residual_probability": 1,
            "can_keywords": ["system compliance", "compliance"],
        },
        {
            # CAP-26-003 -> CAN-26-003 (Flight Operations Procedures Review) -> Ops
            "action_plan": "Capt. Sanjay Gurung (Operations Manager) submits "
            "this Corrective Action Plan in response to CAN-26-003. The plan "
            "includes review of approach procedures, crew training updates, "
            "and SOP revision for approach and landing.",
            "timeline": "Phase 1: SOP review (14 days). Phase 2: Crew training "
            "(28 days). Phase 3: SOP implementation (45 days).",
            "target_completion_offset_days": 60,
            "department": "Flight Operations",
            "rca_method": "bow_tie",
            "residual_severity": 2,
            "residual_probability": 2,
            "can_keywords": ["flight operations", "procedures review"],
        },
    ],
    "rotarywing": [
        {
            # CAP-26-004 -> CAN-26-004 (Tail Rotor Blade Inspection) -> Part-145
            "action_plan": "Mr. Shiva Tamang (Part-145 Manager) submits this "
            "Corrective Action Plan in response to CAN-26-004. The plan "
            "includes fleet-wide tail rotor blade inspections, crack detection "
            "procedures, and replacement protocols.",
            "timeline": "Phase 1: Inspection procedure development (7 days). "
            "Phase 2: Fleet inspection (21 days). Phase 3: Reporting and "
            "corrective action (30 days).",
            "target_completion_offset_days": 30,
            "department": "Part-145",
            "rca_method": "bow_tie",
            "residual_severity": 2,
            "residual_probability": 1,
            "can_keywords": ["tail rotor blade", "tail rotor"],
        },
        {
            # CAP-26-005 -> CAN-26-005 (LTE Training & Procedures) -> Ops
            "action_plan": "Capt. Ram Koirala (Operations Manager) submits "
            "this Corrective Action Plan in response to CAN-26-005. The plan "
            "includes LTE training curriculum review, refresher training for "
            "all pilots, and SOP updates for high-altitude operations.",
            "timeline": "Phase 1: Training material review (14 days). Phase 2: "
            "Pilot training (28 days). Phase 3: SOP updates (45 days).",
            "target_completion_offset_days": 45,
            "department": "Flight Operations",
            "rca_method": "fishbone",
            "residual_severity": 2,
            "residual_probability": 1,
            "can_keywords": ["lte training", "lte"],
        },
    ],
    "demoairport": [
        {
            # CAP-26-006 -> CAN-26-006 (Runway FOD Management) -> Airport Ops
            "action_plan": "Mr. Ramesh Adhikari (Airport Operations Manager) "
            "submits this Corrective Action Plan in response to CAN-26-006. "
            "The plan includes FOD prevention measures on Runway 25, daily FOD "
            "inspections, and reporting procedures.",
            "timeline": "Phase 1: FOD prevention implementation (7 days). "
            "Phase 2: Daily inspection procedures (14 days). Phase 3: "
            "Reporting and monitoring (21 days).",
            "target_completion_offset_days": 21,
            "department": "Airport Operations",
            "rca_method": "bow_tie",
            "residual_severity": 2,
            "residual_probability": 2,
            "can_keywords": ["fod", "runway", "management"],
        },
    ],
}


class CapSeeder(BaseSeeder):
    """Seed / unseed CAPs linked to existing seeded CANs."""

    def __init__(
        self, tenant_ids: Optional[List[str]] = None, dry_run: bool = False
    ):
        super().__init__(tenant_ids=tenant_ids, dry_run=dry_run)

    # ------------------------------------------------------------------
    # PostgreSQL persistence helpers (async dispatched via bridge loop)
    # ------------------------------------------------------------------

    def _find_can_for_keywords(
        self, tenant_id: str, keywords: List[str]
    ) -> Optional[Dict[str, str]]:
        """Return the id + reference of a seeded CAN matching any keyword for
        this tenant, else None."""
        tid = register_tenant(tenant_id)
        lowered = [k.lower() for k in keywords if k]

        async def _query() -> Optional[Dict[str, str]]:
            async with session_scope() as session:
                rows = (
                    await session.execute(
                        select(Can).where(
                            Can.tenant_id == tid,
                            Can.is_demo == demo_scope(),
                        )
                    )
                ).scalars().all()
                for c in rows:
                    title = (c.title or "").lower()
                    desc = (c.description or "").lower()
                    if any(k in title or k in desc for k in lowered):
                        return {
                            "id": str(c.id),
                            "can_reference": c.can_reference,
                            "issued_at": c.issued_at,
                        }
                return None

        return run(_query())

    def _cap_exists(self, tenant_id: str, action_plan: str) -> bool:
        """Return True if a CAP with this exact action_plan already exists for
        the tenant."""
        tid = register_tenant(tenant_id)

        async def _query() -> bool:
            async with session_scope() as session:
                row = await session.scalar(
                    select(Cap.id).where(
                        Cap.tenant_id == tid,
                        Cap.action_plan == action_plan,
                        Cap.is_demo == demo_scope(),
                    )
                )
                return row is not None

        return run(_query())

    def _submitted_by(self, tenant_id: str, department: str) -> Dict[str, str]:
        return SUBMITTERS.get(tenant_id, {}).get(
            department, {"email": "seeder@aviasafe.com", "name": "Department Manager"}
        )

    def _create_cap(self, tenant_id: str, cap_data: Dict) -> Optional[str]:
        """Create a single CAP linked to a seeded CAN. Skip if already exists
        or no matching CAN is found."""
        action_plan = cap_data["action_plan"]

        if self.dry_run:
            self.log_info(f"[DRY RUN] Would create CAP: {action_plan}")
            self.created_count += 1
            return "dry-run-id"

        if self._cap_exists(tenant_id, action_plan):
            self.skipped_count += 1
            self.log_info(f"Skipped existing CAP: {action_plan}")
            return None

        # Resolve the linked CAN so we never invent a CAN/hazard chain.
        can = self._find_can_for_keywords(
            tenant_id, cap_data.get("can_keywords", [])
        )
        if not can:
            self.log_warning(
                f"Skipping CAP with no matching seeded CAN: {action_plan}"
            )
            self.skipped_count += 1
            return None

        submitter = self._submitted_by(tenant_id, cap_data["department"])
        submitter_user = {
            "uid": _uid_for(submitter["email"]),
            "email": submitter["email"],
            "role": "DEPT_ADMIN",
            "tenant_id": tenant_id,
        }

        # Date the CAP relative to the linked CAN's issue date so the chain
        # Report -> CAN -> CAP is chronologically consistent (CAP never before
        # the CAN it responds to).
        can_issued_at = can.get("issued_at")
        if can_issued_at is None:
            can_issued_at = datetime.now(timezone.utc)
        else:
            can_issued_at = can_issued_at.replace(tzinfo=timezone.utc)
        offset_days = int(cap_data.get("target_completion_offset_days", 30))
        target_date = can_issued_at + timedelta(days=offset_days)
        submitted_at = can_issued_at + timedelta(days=random.randint(1, 7))

        payload = {
            "can_id": can["id"],
            "action_plan": action_plan,
            "timeline": cap_data["timeline"],
            "department": cap_data["department"],
            "rca_method": cap_data.get("rca_method", "bow_tie"),
            "residual_severity": cap_data["residual_severity"],
            "residual_probability": cap_data["residual_probability"],
            "target_completion_date": target_date,
            "submitted_at": submitted_at,
        }

        try:
            service = CanCapService(tenant_id=tenant_id)
            result = service.submit_cap(can["id"], payload, submitter_user)
            self.created_count += 1
            self.log_info(
                f"Created CAP: {action_plan} (linked to {can['can_reference']}, "
                f"submitted_at={submitted_at.isoformat()}, "
                f"target={target_date.date().isoformat()})"
            )
            return result.get("id")
        except Exception as e:
            self.log_error(f"Failed to create CAP {action_plan}: {e}")
            return None

    def _get_cap_templates(self, tenant_id: str) -> List[Dict]:
        return CAP_TEMPLATES.get(tenant_id, [])

    # ------------------------------------------------------------------
    # BaseSeeder interface
    # ------------------------------------------------------------------

    def seed(self) -> Dict[str, Any]:
        """Seed CAPs for all configured tenants."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        self.log_info("=" * 60)
        self.log_info("Starting CapSeeder (Supabase/PostgreSQL)...")
        self.log_info("=" * 60)

        for tenant in self._get_tenant_ids():
            if not self._is_demo_tenant(tenant):
                self.log_warning(f"Skipping non-demo tenant: {tenant}")
                continue
            self.log_info(f"Seeding CAPs for tenant: {tenant}")
            templates = self._get_cap_templates(tenant)
            self.log_info(f"  Found {len(templates)} CAP templates")
            for template in templates:
                self._create_cap(tenant, template)

        self.log_info("=" * 60)
        self.log_info(
            f"CapSeeder complete: created={self.created_count} "
            f"skipped={self.skipped_count} errors={len(self.errors)}"
        )
        self.log_info("=" * 60)

        return self.get_summary()

    def unseed(self) -> Dict[str, Any]:
        """Remove all CAPs created by this seeder from PostgreSQL."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        self.log_info("=" * 60)
        self.log_info("Starting CapSeeder unseed...")
        self.log_info("=" * 60)

        for tenant in self._get_tenant_ids():
            if not self._is_demo_tenant(tenant):
                continue
            tid = register_tenant(tenant)
            action_plans = [t["action_plan"] for t in self._get_cap_templates(tenant)]
            if not action_plans:
                continue

            if self.dry_run:
                self.log_info(
                    f"[DRY RUN] Would remove {len(action_plans)} seeded CAPs "
                    f"for tenant: {tenant}"
                )
                continue

            async def _remove() -> int:
                async with session_scope() as session:
                    result = await session.execute(
                        delete(Cap).where(
                            Cap.tenant_id == tid,
                            Cap.action_plan.in_(action_plans),
                            Cap.is_demo == demo_scope(),
                        )
                    )
                    return result.rowcount or 0

            try:
                removed = run(_remove())
                self.created_count += removed
                self.log_info(
                    f"Removed {removed} seeded CAPs for tenant: {tenant}"
                )
            except Exception as e:
                self.log_error(
                    f"Failed to unseed CAPs for tenant {tenant}: {e}"
                )

        self.log_info(f"CapSeeder unseed complete: removed={self.created_count}")
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

    seeder = CapSeeder(tenant_ids=tenants, dry_run=dry_run)
    result = seeder.seed() if seed_mode == "seed" else seeder.unseed()
    print(json.dumps(result, indent=2, default=str))
