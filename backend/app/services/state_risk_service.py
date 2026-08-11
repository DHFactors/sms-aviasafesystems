# ============================================================================
# FILE: state_risk_service.py
# PATH: backend/app/services/state_risk_service.py
# VERSION: 1.0.0
# DATE CREATED: 2026-08-04
# PURPOSE: State-level risk register service. Aggregates hazard/report risk
#          across all operator tenants, classifies by ICAO top-risk taxonomy,
#          and measures current industry risk against seeded SSP targets.
# AUTHOR: Ghanshyam Acharya
# CODE OWNER: AviaSafeSystems
# ============================================================================

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from loguru import logger

from app.firebase import get_db
from app.services.risk_matrix import compute_risk_index


STATE_COLLECTION = "state"
ICAO_REFERENCE_DOCUMENT = "icao_top_risks"
RISK_REGISTER_SUBCOLLECTION = "risk_register"

# ICAO-aligned top safety risk categories (state-level SSP register).
# Keys mirror the ADREP occurrence categories used across tenant reports.
# Default ssp_target is the baseline state risk-index target (1-25).
ICAO_TOP_RISK_CATEGORIES = [
    {"category": "LOCI", "name": "Loss of Control Inflight", "icao_reference": "ICAO Doc 9854 / SSP", "ssp_target": 12},
    {"category": "CFIT", "name": "Controlled Flight Into Terrain", "icao_reference": "ICAO Doc 9854 / SSP", "ssp_target": 10},
    {"category": "RE", "name": "Runway Excursion", "icao_reference": "ICAO Doc 9854 / SSP", "ssp_target": 12},
    {"category": "RI", "name": "Runway Incursion", "icao_reference": "ICAO Doc 9854 / SSP", "ssp_target": 9},
    {"category": "MAC", "name": "Airborne Conflict / Mid-Air Collision", "icao_reference": "ICAO Doc 9854 / SSP", "ssp_target": 8},
    {"category": "WX", "name": "Weather-Related", "icao_reference": "ICAO Doc 9854 / SSP", "ssp_target": 10},
    {"category": "ENG", "name": "Engine Failure / Power Loss", "icao_reference": "ICAO Doc 9854 / SSP", "ssp_target": 12},
    {"category": "SYS", "name": "System / Component Failure", "icao_reference": "ICAO Doc 9854 / SSP", "ssp_target": 12},
    {"category": "FIRE", "name": "Fire / Smoke", "icao_reference": "ICAO Doc 9854 / SSP", "ssp_target": 9},
    {"category": "BIRD", "name": "Wildlife Strike", "icao_reference": "ICAO Doc 9854 / SSP", "ssp_target": 8},
    {"category": "GCOL", "name": "Ground Collision", "icao_reference": "ICAO Doc 9854 / SSP", "ssp_target": 9},
    {"category": "CABIN", "name": "Cabin Safety", "icao_reference": "ICAO Doc 9854 / SSP", "ssp_target": 8},
    {"category": "ARC", "name": "Abnormal Runway Contact", "icao_reference": "ICAO Doc 9854 / SSP", "ssp_target": 10},
    {"category": "OTHER", "name": "Other / Unclassified", "icao_reference": "ICAO Doc 9854 / SSP", "ssp_target": 15},
]


def _risk_collection():
    return get_db().collection(STATE_COLLECTION).document("ssp").collection(RISK_REGISTER_SUBCOLLECTION)


def _icao_reference_doc(category: str) -> Optional[Dict[str, Any]]:
    try:
        doc = get_db().collection(STATE_COLLECTION).document(ICAO_REFERENCE_DOCUMENT).collection("categories").document(category).get()
        if doc.exists:
            data = doc.to_dict()
            data["category"] = category
            return data
    except Exception as e:
        logger.error(f"Failed to read ICAO reference for {category}: {e}")
    return None


class StateRiskService:
    """Aggregates tenant risk and maintains the state-level risk register."""

    def __init__(self, user: Optional[dict] = None):
        self.user = user or {}
        self.role = self.user.get("role", "USER")

    # ------------------------------------------------------------------
    # Public: read paths (CAAN_SMD / SUPER_ADMIN)
    # ------------------------------------------------------------------

    def list_register(self, year: Optional[int] = None, quarter: Optional[int] = None) -> List[Dict[str, Any]]:
        try:
            docs = _risk_collection().stream()
            rows = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                if year and data.get("year") != year:
                    continue
                if quarter and data.get("quarter") != quarter:
                    continue
                rows.append(data)
            return sorted(rows, key=lambda r: (r.get("year", 0), r.get("current_risk_index", 99) or 99))
        except Exception as e:
            logger.error(f"Failed to list state risk register: {e}")
            return []

    def get_register_entry(self, risk_id: str) -> Optional[Dict[str, Any]]:
        try:
            doc = _risk_collection().document(risk_id).get()
            if not doc.exists:
                return None
            data = doc.to_dict()
            data["id"] = doc.id
            return data
        except Exception as e:
            logger.error(f"Failed to get state risk register entry {risk_id}: {e}")
            return None

    # ------------------------------------------------------------------
    # Public: aggregation (drills tenant data up to state level)
    # ------------------------------------------------------------------

    def aggregate_state_risk(self, year: int, quarter: int, regulator_id: Optional[str] = None) -> Dict[str, Any]:
        """Aggregate all tenant hazards/reports by ICAO category and compute
        state current risk index per category.

        `regulator_id` scopes the aggregation to that State Regulator's
        operators (e.g. CAAN for Nepal). When omitted, every operator tenant is
        included (the whole-state state view).
        """
        hazards = self._cross_tenant_hazards()
        reports = self._cross_tenant_reports()

        if regulator_id:
            from app.services.regulator_service import operator_tenant_ids_for_regulator
            allowed = set(operator_tenant_ids_for_regulator(regulator_id))
            if allowed:
                hazards = [h for h in hazards if h.get("tenant_id") in allowed]
                reports = [r for r in reports if r.get("tenant_id") in allowed]

        category_totals: Dict[str, Dict[str, Any]] = {}
        for cat_def in ICAO_TOP_RISK_CATEGORIES:
            cat = cat_def["category"]
            ref = _icao_reference_doc(cat)
            category_totals[cat] = {
                "category": cat,
                "name": (ref or {}).get("name") or cat_def["name"],
                "icao_reference": (ref or {}).get("icao_reference") or cat_def["icao_reference"],
                "ssp_target": (ref or {}).get("ssp_target") or cat_def.get("ssp_target"),
                "count": 0,
                "high_risk_count": 0,
                "severity_sum": 0,
                "probability_sum": 0,
                "tenant_ids": set(),
            }

        for h in hazards:
            cat = self._classify(h)
            agg = category_totals.setdefault(cat, category_totals["OTHER"])
            agg["count"] += 1
            sev = h.get("severity_level") or h.get("severity")
            prob = h.get("probability_level") or h.get("probability")
            if isinstance(sev, int) and isinstance(prob, int):
                agg["severity_sum"] += sev
                agg["probability_sum"] += prob
            if h.get("risk_level") in ("High", "Very High", "Critical"):
                agg["high_risk_count"] += 1
            tid = h.get("tenant_id")
            if tid:
                agg["tenant_ids"].add(tid)

        for r in reports:
            cat = self._classify(r)
            agg = category_totals.setdefault(cat, category_totals["OTHER"])
            agg["count"] += 1
            sev = r.get("severity_level") or r.get("severity")
            prob = r.get("probability_level") or r.get("probability")
            if isinstance(sev, int) and isinstance(prob, int):
                agg["severity_sum"] += sev
                agg["probability_sum"] += prob
            if r.get("risk_level") in ("High", "Very High", "Critical"):
                agg["high_risk_count"] += 1
            tid = r.get("tenant_id")
            if tid:
                agg["tenant_ids"].add(tid)

        rows = []
        for cat, agg in category_totals.items():
            n = agg["count"]
            avg_sev = round(agg["severity_sum"] / n, 1) if n and agg["severity_sum"] else 1
            avg_prob = round(agg["probability_sum"] / n, 1) if n and agg["probability_sum"] else 1
            current_index = compute_risk_index(round(avg_sev), round(avg_prob)) if n else None
            rows.append({
                "icoc_category": cat,
                "name": agg["name"],
                "icao_reference": agg["icao_reference"],
                "ssp_target": agg["ssp_target"],
                "count": n,
                "high_risk_count": agg["high_risk_count"],
                "current_risk_index": current_index,
                "avg_severity": avg_sev,
                "avg_probability": avg_prob,
                "contributing_tenants": sorted(agg["tenant_ids"]),
                "year": year,
                "quarter": quarter,
            })

        rows = [r for r in rows if r["count"] > 0]
        rows.sort(key=lambda r: r["current_risk_index"] or 0, reverse=True)
        return {"year": year, "quarter": quarter, "risks": rows}

    def sync_register_from_aggregation(self, year: int, quarter: int, regulator_id: Optional[str] = None) -> Dict[str, Any]:
        """Persist the aggregated state risk into the state risk register,
        measuring actual values against seeded SSP targets where present.

        All register writes are committed in a single Firestore batch so the
        register is never observed partially updated (atomic consistency).
        Every entry records `aggregated_at` (UTC ISO) so consumers can detect
        how stale the register is relative to live tenant data.
        """
        agg = self.aggregate_state_risk(year, quarter, regulator_id=regulator_id)
        now = datetime.now(timezone.utc).isoformat()
        updated_by = self.user.get("uid", "system")
        collection = _risk_collection()
        batch = get_db().batch()

        for row in agg["risks"]:
            existing = self._find_entry(row["icoc_category"], year, quarter)
            data = {
                "icoc_category": row["icoc_category"],
                "name": row["name"],
                "icao_reference": row["icao_reference"],
                "current_risk_index": row["current_risk_index"],
                "contributing_tenants": row["contributing_tenants"],
                "actual_ssp_value": row["current_risk_index"],
                "count": row["count"],
                "high_risk_count": row["high_risk_count"],
                "avg_severity": row["avg_severity"],
                "avg_probability": row["avg_probability"],
                "tolerability": self._tolerability(row["current_risk_index"]),
                "trend": self._trend(existing, row["current_risk_index"]),
                "year": year,
                "quarter": quarter,
                "aggregated_at": now,
                "updated_at": now,
                "updated_by": updated_by,
            }
            if existing:
                data["ssp_target"] = existing.get("ssp_target") or row.get("ssp_target")
                data["risk_reduction_rate"] = existing.get("risk_reduction_rate")
                batch.update(collection.document(existing["id"]), data)
            else:
                data["ssp_target"] = row.get("ssp_target")
                data["risk_reduction_rate"] = None
                data["created_at"] = now
                batch.set(collection.document(f"{row['icoc_category']}-{year}Q{quarter}"), data)

        batch.commit()
        return {"year": year, "quarter": quarter, "synced": len(agg["risks"]), "aggregated_at": now}

    def update_ssp_target(self, risk_id: str, ssp_target: float, risk_reduction_rate: Optional[float] = None) -> Optional[Dict[str, Any]]:
        try:
            doc = _risk_collection().document(risk_id)
            if not doc.get().exists:
                return None
            patch: Dict[str, Any] = {
                "ssp_target": ssp_target,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": self.user.get("uid", "system"),
            }
            if risk_reduction_rate is not None:
                patch["risk_reduction_rate"] = risk_reduction_rate
            doc.update(patch)
            data = doc.get().to_dict()
            data["id"] = doc.id
            return data
        except Exception as e:
            logger.error(f"Failed to update SSP target for {risk_id}: {e}")
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cross_tenant_hazards(self) -> List[Dict[str, Any]]:
        try:
            docs = get_db().collection_group("hazards").get()
            return [d.to_dict() for d in docs]
        except Exception as e:
            logger.warning(f"Failed to aggregate hazards: {e}")
            return []

    def _cross_tenant_reports(self) -> List[Dict[str, Any]]:
        try:
            docs = get_db().collection_group("reports").get()
            return [d.to_dict() for d in docs]
        except Exception as e:
            logger.warning(f"Failed to aggregate reports: {e}")
            return []

    @staticmethod
    def _classify(doc: Dict[str, Any]) -> str:
        """Map a hazard/report to an ICAO top-risk category.

        Exact ADREP code matches win first (occurrence_category is already a
        code like LOCI/CFIT). Named labels are then matched explicitly so short
        codes (RI, RE, MAC) never match inside longer words (e.g. 'stRIke').
        """
        cat = (
            doc.get("occurrence_category")
            or doc.get("taxonomy")
            or doc.get("adrep_category")
            or doc.get("occurrence_type")
        )
        if not cat:
            return "OTHER"
        upper = cat.upper()

        # 1. Exact ADREP code match
        exact = ("LOCI", "CFIT", "RE", "RI", "MAC", "WX", "ENG", "SYS", "FIRE", "BIRD", "GCOL", "CABIN", "ARC")
        for code in exact:
            if upper == code:
                return code

        # 2. Named-label matches (ordered: most specific phrases first)
        label_groups = [
            ("LOCI", ("LOSS OF CONTROL", "LOC-I", "LOC I", "LOCI")),
            ("CFIT", ("TERRAIN", "CFIT")),
            ("RI", ("RUNWAY INCURSION",)),
            ("RE", ("RUNWAY EXCURSION",)),
            ("MAC", ("MID-AIR", "MIDAIR", "AIRBORNE CONFLICT")),
            ("BIRD", ("WILDLIFE", "BIRD STRIKE", "BIRD")),
            ("ENG", ("ENGINE", "POWER LOSS")),
            ("FIRE", ("FIRE", "SMOKE")),
            ("SYS", ("SYSTEM",)),
            ("WX", ("WEATHER", "WIND", "ICING")),
            ("GCOL", ("GROUND",)),
            ("CABIN", ("CABIN",)),
            ("ARC", ("ABNORMAL RUNWAY",)),
        ]
        for code, labels in label_groups:
            if any(label in upper for label in labels):
                return code

        return "OTHER"

    @staticmethod
    def _tolerability(risk_index: Optional[int]) -> str:
        if risk_index is None:
            return "Acceptable"
        if risk_index >= 16:
            return "Intolerable"
        if risk_index >= 9:
            return "Tolerable"
        return "Acceptable"

    @staticmethod
    def _trend(existing: Optional[Dict[str, Any]], current: Optional[int]) -> str:
        if not existing or existing.get("current_risk_index") is None or current is None:
            return "stable"
        prev = existing["current_risk_index"]
        if current > prev:
            return "deteriorating"
        if current < prev:
            return "improving"
        return "stable"

    def _find_entry(self, category: str, year: int, quarter: int) -> Optional[Dict[str, Any]]:
        try:
            doc = _risk_collection().document(f"{category}-{year}Q{quarter}").get()
            if not doc.exists:
                return None
            data = doc.to_dict()
            data["id"] = doc.id
            return data
        except Exception as e:
            logger.error(f"Failed to find entry {category}-{year}Q{quarter}: {e}")
            return None
