# ============================================================================
# FILE: psoe_seeder.py
# PATH: backend/seeders/psoe/psoe_seeder.py
# PURPOSE: Seed / unseed realistic PSOE Audit & Surveillance assessments
#          using the CAAN SMS Procedure Manual Appendix 10 checklist. PSOE
#          assessments are persisted to FIRESTORE in the top-level
#          ``psoe_assessments`` collection (each doc carries ``tenant_id``),
#          exactly matching app/routes/psoe.py.
#
# Scores are computed by the shared app.services.psoe_service.score_assessment
# helper using the real Appendix 10 template (app/data/psoe_appendix10.json),
# so the seeded component/overall scores match what the live API would return.
#
# One assessment is seeded per operator tenant (demostate, being a regulator,
# seeds none). Each assessment uses realistic Appendix 10 responses covering
# all 21 questions (SP-01..06, SRM-01..06, SA-01..05, SPROM-01..04).
#
# Invocation (from backend/):
#   python -m seeders.psoe.psoe_seeder seed
#   python -m seeders.psoe.psoe_seeder seed --tenants fixedwing
#   python -m seeders.psoe.psoe_seeder seed --dry-run
#   python -m seeders.psoe.psoe_seeder unseed
# ============================================================================

import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from seeders import BaseSeeder
from app.models.psoe import PSOEAnswer
from app.services.psoe_service import score_assessment, TEMPLATE_VERSION


# Auditor (CAAN_SMD style) per operator tenant, and the Safety Manager who owns
# the assessment within the operator.
AUDITORS: Dict[str, Dict[str, str]] = {
    "fixedwing": {"email": "smd@demostate.test", "name": "Mr. Prakash Adhikari"},
    "rotarywing": {"email": "smd@demostate.test", "name": "Mr. Prakash Adhikari"},
    "demoairport": {"email": "smd@demostate.test", "name": "Ms. Sunita Karki"},
}

OWNERS: Dict[str, Dict[str, str]] = {
    "fixedwing": {"email": "safety@fixedwing.test", "name": "Capt. Rajesh Thapa"},
    "rotarywing": {"email": "safety@rotarywing.test", "name": "Capt. Hari Pandey"},
    "demoairport": {"email": "safety@demoairport.test", "name": "Mr. Kumar Bhandari"},
}


# =============================================================================
# PSOE assessment templates (keyed by tenant id; demostate seeds none)
# Response scores use the 0-3 CAAN/ICAO implementation scale. An omitted entry
# is treated as Not Applicable (is_na=True, excluded from the denominator).
# =============================================================================

PSOE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "fixedwing": {
        "title": "PSOE Assessment: Fixed-Wing Operator Full SMS Surveillance",
        "department": "Safety",
        "scope": "Full SMS surveillance audit against CAAN Appendix 10",
        "responses": {
            # Component 1 - Safety Policy & Objectives
            "SP-01": 3, "SP-02": 3, "SP-03": 3, "SP-04": 2, "SP-05": 2, "SP-06": 3,
            # Component 2 - Safety Risk Management
            "SRM-01": 2, "SRM-02": 3, "SRM-03": 3, "SRM-04": 2, "SRM-05": 2, "SRM-06": 3,
            # Component 3 - Safety Assurance
            "SA-01": 2, "SA-02": 2, "SA-03": 3, "SA-04": 2, "SA-05": 2,
            # Component 4 - Safety Promotion
            "SPROM-01": 3, "SPROM-02": 3, "SPROM-03": 2, "SPROM-04": 2,
        },
        "notes": "Findings raised on SPI monitoring frequency and internal "
        "audit scheduling; a corrective action plan is being prepared.",
    },
    "rotarywing": {
        "title": "PSOE Assessment: Rotary-Wing Operator Full SMS Surveillance",
        "department": "Safety",
        "scope": "Full SMS surveillance audit against CAAN Appendix 10",
        "responses": {
            "SP-01": 3, "SP-02": 2, "SP-03": 3, "SP-04": 3, "SP-05": 2, "SP-06": 2,
            "SRM-01": 3, "SRM-02": 3, "SRM-03": 2, "SRM-04": 2, "SRM-05": 3, "SRM-06": 2,
            "SA-01": 2, "SA-02": 2, "SA-03": 2, "SA-04": 3, "SA-05": 2,
            "SPROM-01": 2, "SPROM-02": 3, "SPROM-03": 2, "SPROM-04": 3,
        },
        "notes": "High-altitude helicopter operations reviewed; LTE and "
        "weather-related risk management noted as areas for improvement.",
    },
    "demoairport": {
        "title": "PSOE Assessment: Demo Airport SMS Surveillance",
        "department": "Safety",
        "scope": "Airport SMS surveillance audit against CAAN Appendix 10",
        "responses": {
            "SP-01": 3, "SP-02": 3, "SP-03": 2, "SP-04": 2, "SP-05": 1, "SP-06": 2,
            "SRM-01": 2, "SRM-02": 2, "SRM-03": 2, "SRM-04": 2, "SRM-05": 2, "SRM-06": 1,
            "SA-01": 2, "SA-02": 1, "SA-03": 2, "SA-04": 1, "SA-05": 2,
            "SPROM-01": 2, "SPROM-02": 2, "SPROM-03": 2, "SPROM-04": 2,
        },
        "notes": "Emergency response plan coordination and FOD management "
        "identified as priority follow-up areas.",
    },
}


class PsoeSeeder(BaseSeeder):
    """Seed / unseed PSOE surveillance assessments in Firestore."""

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

    def _collection(self):
        return self.db.collection("psoe_assessments")

    def _assessment_exists(self, tenant_id: str, title: str) -> bool:
        """Return True if an assessment with this title already exists for the
        tenant."""
        for doc in self._collection().get():
            data = doc.to_dict() or {}
            if data.get("tenant_id") == tenant_id and data.get("title") == title:
                return True
        return False

    def _create_assessment(self, tenant_id: str, template: Dict[str, Any]) -> Optional[str]:
        title = template["title"]

        if self.dry_run:
            self.log_info(f"[DRY RUN] Would create PSOE assessment: {title}")
            self.created_count += 1
            return "dry-run-id"

        if self._assessment_exists(tenant_id, title):
            self.skipped_count += 1
            self.log_info(f"Skipped existing PSOE assessment: {title}")
            return None

        responses = [
            PSOEAnswer(
                question_id=qid,
                score=score,
                is_na=False,
            )
            for qid, score in template["responses"].items()
        ]

        scores = score_assessment(responses)
        now = datetime.now(timezone.utc)
        owner = OWNERS.get(
            tenant_id, {"email": "safety@aviasafe.com", "name": "Safety Manager"}
        )
        auditor = AUDITORS.get(
            tenant_id, {"email": "smd@demostate.test", "name": "Auditor"}
        )

        doc = {
            "tenant_id": tenant_id,
            "title": title,
            "status": "draft",
            "department": template.get("department"),
            "scope": template.get("scope"),
            "auditor_name": auditor["name"],
            "assessor_email": auditor["email"],
            "assessment_date": now,
            "template_version": TEMPLATE_VERSION,
            "responses": [r.model_dump() for r in responses],
            "component_scores": scores["component_scores"],
            "overall_score_pct": scores["overall_score_pct"],
            "overall_level": scores["overall_level"],
            "created_by": owner["email"],
            "created_by_uid": owner["email"],
            "created_at": now,
            "updated_at": now,
            "notes": template.get("notes"),
        }

        try:
            result = self._collection().add(doc)
            doc_id = result[1].id if isinstance(result, tuple) else result.id
            self._collection().document(doc_id).update({"id": doc_id})
            self.created_count += 1
            self.log_info(
                f"Created PSOE assessment: {title} "
                f"(score={scores['overall_score_pct']}%)"
            )
            return doc_id
        except Exception as e:
            self.log_error(f"Failed to create PSOE assessment {title}: {e}")
            return None

    def _get_template(self, tenant_id: str) -> Optional[Dict]:
        return PSOE_TEMPLATES.get(tenant_id)

    # ------------------------------------------------------------------
    # BaseSeeder interface
    # ------------------------------------------------------------------

    def seed(self) -> Dict[str, Any]:
        """Seed PSOE assessments for all configured operator tenants."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        self.log_info("=" * 60)
        self.log_info("Starting PsoeSeeder (Firestore)...")
        self.log_info("=" * 60)

        for tenant in self._get_tenant_ids():
            if not self._is_demo_tenant(tenant):
                self.log_warning(f"Skipping non-demo tenant: {tenant}")
                continue
            template = self._get_template(tenant)
            if not template:
                self.log_info(f"No PSOE template for tenant: {tenant}")
                continue
            self.log_info(f"Seeding PSOE assessment for tenant: {tenant}")
            self._create_assessment(tenant, template)

        self.log_info("=" * 60)
        self.log_info(
            f"PsoeSeeder complete: created={self.created_count} "
            f"skipped={self.skipped_count} errors={len(self.errors)}"
        )
        self.log_info("=" * 60)

        return self.get_summary()

    def unseed(self) -> Dict[str, Any]:
        """Remove all PSOE assessments created by this seeder from Firestore."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        self.log_info("=" * 60)
        self.log_info("Starting PsoeSeeder unseed...")
        self.log_info("=" * 60)

        titles = {t: tem["title"] for t, tem in PSOE_TEMPLATES.items()}

        if self.dry_run:
            self.log_info(
                f"[DRY RUN] Would remove {len(titles)} seeded PSOE assessments"
            )
            self.created_count = len(titles)
            return self.get_summary()

        removed = 0
        try:
            for doc in self._collection().get():
                data = doc.to_dict() or {}
                expected = titles.get(data.get("tenant_id"))
                if expected and data.get("title") == expected:
                    doc.reference.delete()
                    removed += 1
                    self.log_info(
                        f"Removed PSOE assessment: {data.get('title')}"
                    )
        except Exception as e:
            self.log_error(f"Failed to unseed PSOE assessments: {e}")
        self.created_count = removed

        self.log_info(f"PsoeSeeder unseed complete: removed={removed}")
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

    seeder = PsoeSeeder(tenant_ids=tenants, dry_run=dry_run)
    result = seeder.seed() if seed_mode == "seed" else seeder.unseed()
    print(json.dumps(result, indent=2, default=str))
