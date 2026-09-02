# ============================================================================
# FILE: ssp_seeder.py
# PATH: backend/seeders/ssp/ssp_seeder.py
# PURPOSE: Seed / unseed the CAAN State Safety Programme (SSP) demonstration
#          data for the demostate regulator. Owned by the State Regulator, the
#          SSP data is written DIRECTLY to FIRESTORE in the top-level ``state``
#          collection (state/ssp/spis + state/ssp/risk_register), exactly
#          matching how app/services/state_risk_service.py reads the register.
#
# The seeder intentionally DOES NOT call StateRiskService.sync_register_from_
# aggregation, because that helper aggregates tenant hazards/reports from
# FIRESTORE collection groups which the hazard/report seeders write to
# PostgreSQL. Instead realistic register entries are written directly so the
# state risk register and SSP performance indicators render for the demo.
#
# Unseeding identifies the seeded docs by the ``is_demo`` marker plus the
# known spi ids / register entry ids written by this seeder.
#
# Invocation (from backend/):
#   python -m seeders.ssp.ssp_seeder seed                    # demostate
#   python -m seeders.ssp.ssp_seeder seed --tenants demostate
#   python -m seeders.ssp.ssp_seeder seed --dry-run
#   python -m seeders.ssp.ssp_seeder unseed
# ============================================================================

import json
import sys
from typing import Any, Dict, List, Optional

from seeders import BaseSeeder
from seeders.utils.date_utils import get_random_date
from app.services.state_risk_service import ICAO_TOP_RISK_CATEGORIES
from app.services.risk_matrix import (
    get_tolerability_tier,
    TOLERABILITY_TIERS,
)
from app.services.nhrc_service import NHRC_REFERENCE_DATA


# Single state regulator that owns the SSP (State Safety Programme).
REGULATOR_TENANT = "demostate"

# Operator tenants contributing to the state risk register.
_CONTRIBUTING_TENANTS = ["fixedwing", "rotarywing", "demoairport"]

# Immediate-period register to seed (current half of the year).
_REGISTER_YEAR = 2026
_REGISTER_QUARTER = 3

# Seeded register entries override per category: (actual_risk_index, count).
# Categories not listed here reuse their default ssp_target as the actual
# value with a small realistic count.
_REGISTER_ENTRIES: Dict[str, Dict[str, Any]] = {
    "LOCI": {"actual": 14, "count": 3, "high_risk_count": 2, "avg_severity": 3.3, "avg_probability": 3.0},
    "CFIT": {"actual": 11, "count": 2, "high_risk_count": 1, "avg_severity": 4.0, "avg_probability": 2.5},
    "RE": {"actual": 13, "count": 5, "high_risk_count": 3, "avg_severity": 3.4, "avg_probability": 2.8},
    "RI": {"actual": 8, "count": 4, "high_risk_count": 1, "avg_severity": 3.0, "avg_probability": 2.3},
    "MAC": {"actual": 7, "count": 2, "high_risk_count": 0, "avg_severity": 4.0, "avg_probability": 1.5},
    "WX": {"actual": 10, "count": 6, "high_risk_count": 2, "avg_severity": 2.8, "avg_probability": 2.8},
    "ENG": {"actual": 12, "count": 3, "high_risk_count": 2, "avg_severity": 3.7, "avg_probability": 2.3},
    "SYS": {"actual": 11, "count": 4, "high_risk_count": 2, "avg_severity": 3.5, "avg_probability": 2.3},
    "FIRE": {"actual": 9, "count": 2, "high_risk_count": 1, "avg_severity": 3.0, "avg_probability": 2.0},
    "BIRD": {"actual": 8, "count": 6, "high_risk_count": 1, "avg_severity": 2.7, "avg_probability": 2.8},
    "GCOL": {"actual": 9, "count": 3, "high_risk_count": 1, "avg_severity": 3.0, "avg_probability": 2.3},
    "CABIN": {"actual": 7, "count": 2, "high_risk_count": 0, "avg_severity": 3.0, "avg_probability": 2.0},
    "ARC": {"actual": 11, "count": 3, "high_risk_count": 1, "avg_severity": 3.7, "avg_probability": 2.7},
    "OTHER": {"actual": 12, "count": 4, "high_risk_count": 2, "avg_severity": 3.3, "avg_probability": 2.5},
}


# =============================================================================
# SPI templates (state-level SSP performance indicators)
# =============================================================================

SPI_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "hazard_identification_rate",
        "name": "Hazard Identification Rate",
        "domain": "hazard_id",
        "type": "leading",
        "target_value": 10.0,
        "alert_threshold": 5.0,
        "warning_threshold": 7.0,
        "unit": "per_month",
        "measurement_period": "monthly",
        "current_value": 8.5,
        "data_source": "Operator Hazard Register aggregation",
    },
    {
        "id": "hazard_closure_rate",
        "name": "Hazard Closure Rate",
        "domain": "hazard_closure",
        "type": "leading",
        "target_value": 90.0,
        "alert_threshold": 70.0,
        "warning_threshold": 80.0,
        "unit": "percent",
        "measurement_period": "quarterly",
        "current_value": 84.0,
        "data_source": "CAN/CAP closure tracking",
    },
    {
        "id": "can_cap_compliance_rate",
        "name": "CAN/CAP Compliance Rate",
        "domain": "can_cap_compliance",
        "type": "lagging",
        "target_value": 95.0,
        "alert_threshold": 75.0,
        "warning_threshold": 85.0,
        "unit": "percent",
        "measurement_period": "quarterly",
        "current_value": 88.0,
        "data_source": "Corrective action closure records",
    },
    {
        "id": "safety_reporting_rate",
        "name": "Safety Reporting Rate",
        "domain": "safety_reports",
        "type": "leading",
        "target_value": 20.0,
        "alert_threshold": 10.0,
        "warning_threshold": 15.0,
        "unit": "per_month",
        "measurement_period": "monthly",
        "current_value": 17.0,
        "data_source": "Voluntary/confidential reporting captures",
    },
    {
        "id": "runway_excursion_rate",
        "name": "Runway Excursion Rate",
        "domain": "runway_excursion",
        "type": "lagging",
        "target_value": 2.0,
        "alert_threshold": 5.0,
        "warning_threshold": 3.5,
        "unit": "per_100k_movements",
        "measurement_period": "annual",
        "current_value": 3.0,
        "data_source": "Occurrence reports / ADREP",
    },
    {
        "id": "loss_of_separation_rate",
        "name": "Loss of Separation Rate",
        "domain": "loss_of_separation",
        "type": "lagging",
        "target_value": 1.5,
        "alert_threshold": 4.0,
        "warning_threshold": 2.5,
        "unit": "per_100k_flights",
        "measurement_period": "annual",
        "current_value": 2.0,
        "data_source": "ATM safety investigations",
    },
    {
        "id": "bird_strike_rate",
        "name": "Wildlife Strike Rate",
        "domain": "bird_strike",
        "type": "lagging",
        "target_value": 3.0,
        "alert_threshold": 6.0,
        "warning_threshold": 4.5,
        "unit": "per_1000_movements",
        "measurement_period": "quarterly",
        "current_value": 4.2,
        "data_source": "Wildlife strike reports",
    },
    {
        "id": "serious_incident_rate",
        "name": "Serious Incident Rate",
        "domain": "serious_incident",
        "type": "lagging",
        "target_value": 0.5,
        "alert_threshold": 2.0,
        "warning_threshold": 1.0,
        "unit": "per_100k_flights",
        "measurement_period": "annual",
        "current_value": 0.8,
        "data_source": "ADREP serious incident records",
    },
]


class SspSeeder(BaseSeeder):
    """Seed / unseed the State Safety Programme demonstration data."""

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

    def _state_doc(self, sub: str):
        return self.db.collection("state").document("ssp").collection(sub)

    def _spi_collection(self):
        return self._state_doc("spis")

    def _register_collection(self):
        return self._state_doc("risk_register")

    def _nhrc_collection(self):
        return self._state_doc("nhrcs")

    # ------------------------------------------------------------------
    # SPI helpers
    # ------------------------------------------------------------------

    def _spi_exists(self, spi_id: str) -> bool:
        return self._spi_collection().document(spi_id).get().exists

    def _seed_spis(self) -> int:
        """Write the SPI documents. Returns count of new/updated SPIs."""
        created = 0
        now = get_random_date(start_days_ago=180, end_days_ago=30)
        for spi in SPI_TEMPLATES:
            spi_id = spi["id"]
            if self.dry_run:
                self.log_info(f"[DRY RUN] Would write SPI: {spi_id}")
                created += 1
                continue
            doc = {
                "id": spi_id,
                "name": spi["name"],
                "domain": spi["domain"],
                "type": spi["type"],
                "target_value": spi["target_value"],
                "alert_threshold": spi["alert_threshold"],
                "warning_threshold": spi["warning_threshold"],
                "unit": spi["unit"],
                "measurement_period": spi["measurement_period"],
                "current_value": spi["current_value"],
                "data_source": spi["data_source"],
                "is_demo": True,
                "seed_version": "3.0.0",
                "created_at": now,
                "updated_at": now,
            }
            if self._spi_exists(spi_id):
                self.log_info(f"Skipped existing SPI: {spi_id}")
                self.skipped_count += 1
                continue
            self._spi_collection().document(spi_id).set(doc)
            created += 1
            self.log_info(f"Created SPI: {spi_id}")
        return created

    # ------------------------------------------------------------------
    # State risk register helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _level_for(risk_index: int) -> str:
        tier = get_tolerability_tier(risk_index)
        return TOLERABILITY_TIERS[tier]["level"]

    @staticmethod
    def _tier(risk_index: int) -> str:
        return get_tolerability_tier(risk_index)

    def _register_entry_id(self, category: str) -> str:
        return f"{category}-{_REGISTER_YEAR}Q{_REGISTER_QUARTER}"

    def _seed_register_entries(self) -> int:
        """Write the state risk register entries directly (matching the shape
        StateRiskService.sync_register_from_aggregation writes)."""
        created = 0
        now = get_random_date(start_days_ago=365, end_days_ago=60)
        for cat_def in ICAO_TOP_RISK_CATEGORIES:
            cat = cat_def["category"]
            entry_id = self._register_entry_id(cat)
            override = _REGISTER_ENTRIES.get(cat, {})
            actual = override.get("actual", cat_def["ssp_target"])
            count = override.get("count", 1)
            high_risk = override.get("high_risk_count", 0)
            level_ii = max(0, count - high_risk)
            level_iii = high_risk if self._tier(actual) == "HIGH" else 0
            level_iv = high_risk if self._tier(actual) == "VERY HIGH" else 0

            doc = {
                "icoc_category": cat,
                "name": cat_def["name"],
                "icao_reference": cat_def["icao_reference"],
                "current_risk_index": actual,
                "contributing_tenants": list(_CONTRIBUTING_TENANTS),
                "actual_ssp_value": actual,
                "count": count,
                "high_risk_count": high_risk,
                "level_ii_count": level_ii,
                "level_iii_count": level_iii,
                "level_iv_count": level_iv,
                "avg_severity": override.get("avg_severity", 3.0),
                "avg_probability": override.get("avg_probability", 2.5),
                "tolerability": TOLERABILITY_TIERS[self._tier(actual)]["outcome"],
                "tolerability_tier": self._tier(actual),
                "level": self._level_for(actual),
                "trend": "stable",
                "year": _REGISTER_YEAR,
                "quarter": _REGISTER_QUARTER,
                "ssp_target": cat_def["ssp_target"],
                "risk_reduction_rate": 5.0,
                "is_demo": True,
                "seed_version": "3.0.0",
                "aggregated_at": now.isoformat(),
                "created_at": now,
                "updated_at": now,
                "updated_by": "demostate-seed",
            }

            if self.dry_run:
                self.log_info(f"[DRY RUN] Would write register entry: {entry_id}")
                created += 1
                continue

            ref = self._register_collection().document(entry_id)
            if ref.get().exists:
                self.log_info(f"Skipped existing register entry: {entry_id}")
                self.skipped_count += 1
                continue
            ref.set(doc)
            created += 1
            self.log_info(
                f"Created register entry: {entry_id} "
                f"(index={actual}, target={cat_def['ssp_target']})"
            )
        return created

    # ------------------------------------------------------------------
    # N-HRC (National High-Risk Category) reference data helpers
    # ------------------------------------------------------------------

    def _seed_nhrc_reference(self) -> int:
        """Persist the NASP 2023-2025 N-HRC reference data (SEIs +
        contributing factors) to Firestore under state/ssp/nhrcs/{code}."""
        created = 0
        now = get_random_date(start_days_ago=365, end_days_ago=60)
        for ref in NHRC_REFERENCE_DATA:
            code = ref["code"]
            if self.dry_run:
                self.log_info(f"[DRY RUN] Would write N-HRC reference: {code}")
                created += 1
                continue

            doc = {
                "code": code,
                "name": ref["name"],
                "contributing_factors": ref["contributing_factors"],
                "seis": ref["seis"],
                "is_demo": True,
                "seed_version": "3.0.0",
                "created_at": now,
                "updated_at": now,
            }

            ref_doc = self._nhrc_collection().document(code)
            if ref_doc.get().exists:
                self.log_info(f"Skipped existing N-HRC reference: {code}")
                self.skipped_count += 1
                continue
            ref_doc.set(doc)
            created += 1
            self.log_info(f"Created N-HRC reference: {code} ({ref['name']})")
        return created

    # ------------------------------------------------------------------
    # BaseSeeder interface
    # ------------------------------------------------------------------

    def _should_run(self) -> bool:
        """SSP is state-level and writes to the ``state`` collection; always
        run when invoked (not scoped to individual tenants)."""
        return True

    def seed(self) -> Dict[str, Any]:
        """Seed SPIs + risk register entries for the state regulator."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        self.log_info("=" * 60)
        self.log_info("Starting SspSeeder (Firestore / state.ssp)...")
        self.log_info("=" * 60)

        if not self._should_run():
            self.log_info(
                f"SSP is state-level; nothing to seed (target does not "
                f"include {REGULATOR_TENANT})"
            )
            return self.get_summary()

        self.created_count += self._seed_spis()
        self.created_count += self._seed_register_entries()
        self.created_count += self._seed_nhrc_reference()

        self.log_info("=" * 60)
        self.log_info(
            f"SspSeeder complete: created={self.created_count} "
            f"skipped={self.skipped_count} errors={len(self.errors)}"
        )
        self.log_info("=" * 60)

        return self.get_summary()

    def unseed(self) -> Dict[str, Any]:
        """Remove the SPIs and register entries created by this seeder."""
        self.created_count = 0
        self.skipped_count = 0
        self.errors = []

        self.log_info("=" * 60)
        self.log_info("Starting SspSeeder unseed...")
        self.log_info("=" * 60)

        if not self._should_run():
            self.log_info(f"Nothing to unseed (no {REGULATOR_TENANT} target)")
            return self.get_summary()

        spi_ids = [s["id"] for s in SPI_TEMPLATES]
        registry_ids = [
            self._register_entry_id(cd["category"])
            for cd in ICAO_TOP_RISK_CATEGORIES
        ]
        nhrc_codes = [r["code"] for r in NHRC_REFERENCE_DATA]

        if self.dry_run:
            self.log_info(
                f"[DRY RUN] Would remove {len(spi_ids)} SPIs, "
                f"{len(registry_ids)} register entries and "
                f"{len(nhrc_codes)} N-HRC reference docs"
            )
            self.created_count = len(spi_ids) + len(registry_ids) + len(nhrc_codes)
            return self.get_summary()

        removed = 0
        try:
            for spi_id in spi_ids:
                ref = self._spi_collection().document(spi_id)
                snap = ref.get()
                if snap.exists and (snap.to_dict() or {}).get("is_demo"):
                    ref.delete()
                    removed += 1
                    self.log_info(f"Removed SPI: {spi_id}")
        except Exception as e:
            self.log_error(f"Failed to unseed SPIs: {e}")

        try:
            for entry_id in registry_ids:
                ref = self._register_collection().document(entry_id)
                snap = ref.get()
                if snap.exists and (snap.to_dict() or {}).get("is_demo"):
                    ref.delete()
                    removed += 1
                    self.log_info(f"Removed register entry: {entry_id}")
        except Exception as e:
            self.log_error(f"Failed to unseed register entries: {e}")

        try:
            for code in nhrc_codes:
                ref = self._nhrc_collection().document(code)
                snap = ref.get()
                if snap.exists and (snap.to_dict() or {}).get("is_demo"):
                    ref.delete()
                    removed += 1
                    self.log_info(f"Removed N-HRC reference: {code}")
        except Exception as e:
            self.log_error(f"Failed to unseed N-HRC reference data: {e}")

        self.created_count = removed
        self.log_info(f"SspSeeder unseed complete: removed={removed}")
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

    seeder = SspSeeder(tenant_ids=tenants, dry_run=dry_run)
    result = seeder.seed() if seed_mode == "seed" else seeder.unseed()
    print(json.dumps(result, indent=2, default=str))