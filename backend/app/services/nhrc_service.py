# ============================================================================
# FILE: nhrc_service.py
# PATH: backend/app/services/nhrc_service.py
# PURPOSE: N-HRC (National High-Risk Category) mapping engine. Maps registered
#          hazards to Nepal's 7 NASP 2023-2025 National High-Risk Categories
#          and computes per-tenant and State-aggregated KPIs read from the
#          `hazards` PostgreSQL table.
#
#          The public API is synchronous (matching the legacy service facade
#          used by can_cap_service / hazard_service); DB work dispatches onto
#          the async engine through app.db.runner.run.
# ============================================================================

# ============================================================================
# Nepal NASP 2023-2025 N-HRC reference data (SEIs + contributing factors).
# Canonical source for the KPI payloads AND the Firestore reference docs that
# seeders/ssp/ssp_seeder.py persists into state/ssp/nhrcs/{code}.
# NOTE: content is an initial draft aligned to the published Nepal NASP
#       portfolios; validate against the official NASP 2023-2025 document.
# ============================================================================

NHRC_REFERENCE_DATA = [
    {
        "code": "CFIT",
        "name": "Controlled Flight Into Terrain",
        "contributing_factors": [
            "Critical terrain and rapidly deteriorating weather condition",
            "Violation of SOP",
            "Improper pilot response to stall warning",
            "Excess load on the front bench seat in the helicopters",
            "Loss of situational awareness of pilots",
            "Insufficient operational oversight from the organization",
            "Inadequate pre-flight planning and lack of consideration on individual load",
        ],
        "seis": [
            "Ensure aircraft are equipped with TAWS",
            "Promote wider use of TAWS",
            "Issue Safety Advisory on TAWS warning procedures",
            "Promote use of GPS-derived position data to feed TAWS",
            "Guidance for Operators on Training Programme on the use of GPWS",
            "Implement minimum safe altitude warning (MSAW) systems",
        ],
    },
    {
        "code": "LOC-I",
        "name": "Loss of Control - In Flight",
        "contributing_factors": [
            "Violation of SOP and stabilized approach criteria",
            "Inadequate upset prevention and recovery training (UPRT)",
            "Loss of situational awareness and spatial disorientation",
            "Inexperience in manual flight / over-reliance on automation",
            "Incorrect response to system or engine malfunction",
            "High terrain and mountainous operations increasing upset exposure",
        ],
        "seis": [
            "Introduce upset prevention and recovery training (UPRT) for pilots",
            "Promote SOP adherence for automation management and manual flying",
            "Enhance ATC radar and traffic information services in the valley",
            "Issue safety advisory on loss of control and stall warning response",
            "Monitor operator training programmes on spin/upset recovery",
        ],
    },
    {
        "code": "MAC",
        "name": "Mid Air Collision",
        "contributing_factors": [
            "High traffic volume and converging patterns around Kathmandu",
            "Inadequate ATC-aircrew coordination and communication",
            "TCAS/ACAS events or proximity reports not fully investigated",
            "Mixed IFR/VFR traffic within uncontrolled airspace",
            "Lack of adequate separation assurance outside controlled airspace",
        ],
        "seis": [
            "Enhance ATC coordination and hand-over procedures",
            "Promote mandatory TCAS event and near-miss reporting",
            "Develop safety bulletin on airborne conflict and traffic awareness",
            "Strengthen airspace surveillance and separation monitoring",
            "Encourage operator CRM training on traffic deconfliction",
        ],
    },
    {
        "code": "RE",
        "name": "Runway Excursion",
        "contributing_factors": [
            "Unstable approaches not terminated by go-around",
            "High-altitude / short runways with reduced performance margins",
            "Contaminated or waterlogged runway surface conditions",
            "Excessive speed, late touchdown or misjudged landing distance",
            "Inadequate rejected-takeoff and landing distance assessment",
            "Crosswind and gusty wind conditions at mountain aerodromes",
        ],
        "seis": [
            "Review runway friction and contamination reporting procedures",
            "Promote stabilized approach and go-around policy SOPs",
            "Issue guidance on landing distance and performance planning",
            "Enhance touchdown-zone and stopway management at aerodromes",
            "Monitor operator training on runway excursion prevention",
        ],
    },
    {
        "code": "RI",
        "name": "Runway Incursion",
        "contributing_factors": [
            "Vehicle or personnel entry onto the movement area without clearance",
            "Ambiguous ATC clearances and misunderstood instructions",
            "Inadequate ground movement signage and markings",
            "Runway crossing coordination failures",
            "Poor situational awareness of ground controllers and drivers",
        ],
        "seis": [
            "Implement runway incursion prevention procedures and signage upgrades",
            "Enhance surface movement surveillance and ground vehicle control",
            "Issue safety advisory on read-back / hear-back procedures",
            "Conduct runway safety team (RST) inspections and awareness campaigns",
            "Promote occurrence reporting for runway incursion precursors",
        ],
    },
    {
        "code": "ARC",
        "name": "Abnormal Runway Contact",
        "contributing_factors": [
            "Hard landings and tail strikes on short mountain runways",
            "Bounced, floated or off-centre touchdowns",
            "Helicopter skid/rotor contact during slope and confined-area operations",
            "Inadequate pilot technique and training for abnormal contacts",
            "Unfavourable windshear or turbulence near touchdown",
        ],
        "seis": [
            "Implement hard landing and abnormal contact event monitoring programmes",
            "Promote landing technique refresher training for high-altitude aerodromes",
            "Issue safety guidance on windshear and turbulence during approach",
            "Review helicopter slope-landing and confined-area operational procedures",
            "Encourage timely reporting of abnormal runway contact events",
        ],
    },
    {
        "code": "WS",
        "name": "Wildlife Strike",
        "contributing_factors": [
            "Bird and wildlife population activity around aerodromes",
            "Improper management of wildlife attractants (landfills, water bodies)",
            "Inadequate wildlife hazard management programme",
            "Lack of timely strike reporting and verification",
            "Open dumping and vegetation management gaps near runways",
        ],
        "seis": [
            "Develop and maintain aerodrome Wildlife Hazard Management Plans",
            "Strengthen bird strike reporting and data analysis",
            "Implement habitat and attractant management around movement areas",
            "Conduct regular wildlife patrols and dispersal operations",
            "Issue safety guidance on wildlife strike risk mitigations",
        ],
    },
]

NHRC_NAMES = {item["code"]: item["name"] for item in NHRC_REFERENCE_DATA}


import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from ..models.nhrc import NHRCCategory, NHRCMappingRule, NHRCKPI

logger = logging.getLogger(__name__)

# Nepal NASP 2023-2025 N-HRC Mapping Rules
NHRC_MAPPING_RULES = [
    NHRCMappingRule(
        nhrc=NHRCCategory.CFIT,
        taxonomies=["ENV", "HUM", "ORG"],
        keywords=["terrain", "approach", "stall", "warning", "ground proximity", "CFIT", "mountain"],
        priority_levels=["H", "M"],
        description="Controlled Flight Into Terrain - critical terrain and rapidly deteriorating weather"
    ),
    NHRCMappingRule(
        nhrc=NHRCCategory.LOCI,
        taxonomies=["TEC", "HUM", "ORG"],
        keywords=["control", "trim", "engine", "loss", "power", "stall", "spin", "LOC-I"],
        priority_levels=["H", "M"],
        description="Loss of Control In-Flight - SOP violation, inadequate training"
    ),
    NHRCMappingRule(
        nhrc=NHRCCategory.MAC,
        taxonomies=["HUM", "ORG"],
        keywords=["collision", "airborne", "TCAS", "traffic", "separation", "MAC"],
        priority_levels=["H"],
        description="Mid Air Collision - traffic volume and pattern, coordination"
    ),
    NHRCMappingRule(
        nhrc=NHRCCategory.RE,
        taxonomies=["ENV", "TEC", "HUM", "ORG"],
        keywords=["runway", "excursion", "overrun", "RE", "contaminated"],
        priority_levels=["H", "M"],
        description="Runway Excursion - situational awareness, SOP violation"
    ),
    NHRCMappingRule(
        nhrc=NHRCCategory.RI,
        taxonomies=["HUM", "ORG", "WLD"],
        keywords=["runway", "incursion", "vehicle", "unauthorized", "RI"],
        priority_levels=["H", "M"],
        description="Runway Incursion - situational awareness, communication"
    ),
    NHRCMappingRule(
        nhrc=NHRCCategory.ARC,
        taxonomies=["HUM", "TEC"],
        keywords=["hard landing", "tail strike", "bounced", "floated", "off-centre", "ARC"],
        priority_levels=["M"],
        description="Abnormal Runway Contact - hard landing, tail strike"
    ),
    NHRCMappingRule(
        nhrc=NHRCCategory.WS,
        taxonomies=["WLD", "ENV"],
        keywords=["bird", "wildlife", "strike", "animal", "fod", "WS"],
        priority_levels=["M", "L"],
        description="Wildlife Strike - wildlife control programme"
    ),
]

# Hazards in these terminal states are not "active".
_CLOSED_STATUSES = {"closed", "resolved", "complete", "completed"}

# Default per-category KPI order payloads are returned in (enum definition
# order = official NASP ordering).
_CATEGORY_ORDER = list(NHRCCategory)


class NHRCService:
    """Service for N-HRC mapping and KPI calculation."""

    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def map_hazard_to_nhrc(self, hazard: Dict[str, Any]) -> Optional[NHRCCategory]:
        """
        Map a single hazard to an N-HRC based on taxonomy, keywords, and priority.
        """
        taxonomy = (hazard.get("taxonomy") or "").strip().upper()
        title = hazard.get("title", "").lower()
        description = hazard.get("description", "").lower()
        priority = (hazard.get("priority") or "").strip().upper()

        for rule in NHRC_MAPPING_RULES:
            # Check taxonomy match
            if taxonomy not in rule.taxonomies:
                continue

            # Check priority match
            if priority not in rule.priority_levels:
                continue

            # Check keyword match
            text = title + " " + description
            for keyword in rule.keywords:
                if keyword.lower() in text:
                    return rule.nhrc

        return None

    # ------------------------------------------------------------------
    # KPI calculation (sync facade -> async engine via app.db.runner)
    # ------------------------------------------------------------------

    def calculate_nhrc_kpis(self, tenant_id: str) -> List[NHRCKPI]:
        """
        Calculate N-HRC KPIs for a specific tenant.
        """
        from app.db.runner import run

        tid_uuid = self._resolve_tenant_uuid(tenant_id)
        return run(self._calculate_kpis_async(tenant_id=tid_uuid))

    def calculate_state_nhrc_kpis(self) -> List[NHRCKPI]:
        """
        Calculate N-HRC KPIs for the State (aggregated across all operators).
        """
        from app.db.runner import run

        return run(self._calculate_kpis_async(tenant_id=None))

    # ------------------------------------------------------------------
    # NASP SEIs / contributing factors
    # ------------------------------------------------------------------

    def get_nhrc_seis(self, nhrc: NHRCCategory) -> List[str]:
        """
        Get the Safety Enhancement Initiatives (SEIs) for an N-HRC from NASP.
        """
        for ref in NHRC_REFERENCE_DATA:
            if ref["code"] == nhrc.value:
                return list(ref["seis"])
        return []

    def get_contributing_factors(self, nhrc: NHRCCategory) -> List[str]:
        """
        Get contributing factors for an N-HRC from NASP.
        """
        for ref in NHRC_REFERENCE_DATA:
            if ref["code"] == nhrc.value:
                return list(ref["contributing_factors"])
        return []

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_tenant_uuid(tenant_id: str) -> str:
        """Resolve a tenant slug or raw UUID string to the Postgres UUID."""
        from app.db.ids import tenant_uuid

        try:
            return str(uuid.UUID(str(tenant_id)))
        except (ValueError, AttributeError):
            return tenant_uuid(tenant_id)

    @staticmethod
    def _is_active(state: Optional[str], closed_at: Any) -> bool:
        return not (
            (state or "").strip().lower() in _CLOSED_STATUSES or closed_at is not None
        )

    @staticmethod
    def _hazard_to_dict(h) -> Dict[str, Any]:
        return {
            "taxonomy": h.taxonomy or "",
            "title": h.title or "",
            "description": h.description or "",
            "priority": h.priority or "",
            "risk_index": h.risk_index,
            "severity": h.severity,
            "probability": h.probability,
            "status": h.status or "",
            "closed_at": h.closed_at,
            "created_at": h.created_at or datetime.now(timezone.utc),
        }

    async def _calculate_kpis_async(
        self, tenant_id: Optional[str] = None
    ) -> List[NHRCKPI]:
        from app.db.db_models import Hazard
        from app.db.ids import tenant_uuid
        from app.db.session import session_scope

        async with session_scope() as session:
            stmt = select(Hazard)
            if tenant_id is not None:
                stmt = stmt.where(Hazard.tenant_id == tenant_id)
            else:
                # State view aggregates operator hazards only (regulator excluded).
                stmt = stmt.where(Hazard.tenant_id != tenant_uuid("demostate"))
            rows = (await session.scalars(stmt)).all()

        hazards = [self._hazard_to_dict(h) for h in rows]
        return self._compute_kpis(hazards)

    def _compute_kpis(self, hazards: List[Dict[str, Any]]) -> List[NHRCKPI]:
        now = datetime.now(timezone.utc)
        recent_cutoff = now - timedelta(days=30)
        prior_cutoff = now - timedelta(days=60)

        mapped: Dict[NHRCCategory, List[Dict[str, Any]]] = {c: [] for c in _CATEGORY_ORDER}
        for hazard in hazards:
            if not self._is_active(hazard.get("status"), hazard.get("closed_at")):
                continue
            category = self.map_hazard_to_nhrc(hazard)
            if category is not None:
                mapped[category].append(hazard)

        kpis: List[NHRCKPI] = []
        for category in _CATEGORY_ORDER:
            pool = mapped[category]
            risk_indices = [
                h["risk_index"]
                or (
                    (int(h["severity"] or 0) * int(h["probability"] or 0))
                    if h.get("severity") and h.get("probability")
                    else None
                )
                for h in pool
            ]
            risk_indices = [r for r in risk_indices if r]

            active = len(pool)
            avg_index = round(sum(risk_indices) / len(risk_indices), 1) if risk_indices else 0.0
            max_index = max(risk_indices) if risk_indices else 0

            recent = sum(1 for h in pool if h["created_at"] >= recent_cutoff)
            prior = sum(
                1
                for h in pool
                if prior_cutoff <= h["created_at"] < recent_cutoff
            )
            if recent > prior:
                trend = "increasing"
            elif recent < prior:
                trend = "decreasing"
            else:
                trend = "stable"

            kpis.append(
                NHRCKPI(
                    nhrc=category,
                    name=self._name_for(category),
                    active_hazards=active,
                    avg_risk_index=avg_index,
                    max_risk_index=max_index,
                    trend=trend,
                    status=self._status_for(max_index, avg_index, trend),
                    contributing_factors=self.get_contributing_factors(category),
                    seIs=self.get_nhrc_seis(category),
                )
            )
        return kpis

    @classmethod
    def _name_for(cls, category: NHRCCategory) -> str:
        return NHRC_NAMES.get(category.value, category.value)

    @classmethod
    def _status_for(cls, max_index: int, avg_index: float, trend: str) -> str:
        """Derive a dashboard status from risk exposure and near-term trend."""
        from app.services.risk_matrix import get_tolerability_tier

        if max_index <= 0:
            return "ok"
        if get_tolerability_tier(max_index) == "VERY HIGH":
            return "action"
        avg_tier = get_tolerability_tier(int(round(avg_index)))
        if avg_tier == "VERY HIGH":
            return "action"
        if avg_tier == "HIGH" or trend == "increasing":
            return "watch"
        return "ok"