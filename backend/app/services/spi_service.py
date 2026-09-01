# ============================================================================
# FILE: spi_service.py
# PATH: backend/app/services/spi_service.py
# PURPOSE: SPI/SPT (Safety Performance Indicator / Safety Performance Target)
#          calculation service. Implements the ICAO Annex 19 / Doc 9859
#          leading- and lagging-indicator framework. SPI values are computed
#          from the live PostgreSQL tables (hazards, reports as VSR/MOR,
#          flight_diversions, cans, caps, surveys) using the same synchronous
#          facade -> async engine pattern as NHRCService / can_cap_service.
# ============================================================================

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ..models.spi import SPI, SPIType, SPIDomain, SPIStatus, SPICalculation

logger = logging.getLogger(__name__)

# SPI Definitions
SPI_DEFINITIONS = [
    {
        "id": "SPI-LEAD-001",
        "name": "Hazard Identification Rate",
        "domain": SPIDomain.HAZARD_ID,
        "type": SPIType.LEADING,
        "unit": "per_month",
        "measurement_period": "monthly",
        "target_value": 10.0,
        "alert_threshold": 5.0,
        "warning_threshold": 7.0,
        "data_source": "Hazard Register",
    },
    {
        "id": "SPI-LEAD-002",
        "name": "VSR Reporting Rate",
        "domain": SPIDomain.REPORTING_RATE,
        "type": SPIType.LEADING,
        "unit": "per_1000_hours",
        "measurement_period": "monthly",
        "target_value": 3.0,
        "alert_threshold": 1.0,
        "warning_threshold": 2.0,
        "data_source": "VSR Reports",
    },
    {
        "id": "SPI-LEAD-003",
        "name": "Diversion Rate",
        "domain": SPIDomain.DIVERSION_RATE,
        "type": SPIType.LEADING,
        "unit": "per_1000_flights",
        "measurement_period": "monthly",
        "target_value": 0.5,
        "alert_threshold": 1.0,
        "warning_threshold": 0.7,
        "data_source": "Flight Diversions",
    },
    {
        "id": "SPI-LEAD-004",
        "name": "Risk Reduction Rate",
        "domain": SPIDomain.RISK_REDUCTION,
        "type": SPIType.LEADING,
        "unit": "percent",
        "measurement_period": "quarterly",
        "target_value": 85.0,
        "alert_threshold": 60.0,
        "warning_threshold": 72.0,
        "data_source": "CAN/CAP Register",
    },
    {
        "id": "SPI-LAG-001",
        "name": "MOR Occurrence Rate",
        "domain": SPIDomain.OCCURRENCE_RATE,
        "type": SPIType.LAGGING,
        "unit": "per_1000_hours",
        "measurement_period": "monthly",
        "target_value": 5.0,
        "alert_threshold": 10.0,
        "warning_threshold": 7.5,
        "data_source": "MOR Reports",
    },
    {
        "id": "SPI-LAG-002",
        "name": "CAN Closure Rate",
        "domain": SPIDomain.CAN_CLOSURE,
        "type": SPIType.LAGGING,
        "unit": "percent",
        "measurement_period": "quarterly",
        "target_value": 90.0,
        "alert_threshold": 70.0,
        "warning_threshold": 80.0,
        "data_source": "CAN Register",
    },
    {
        "id": "SPI-LAG-003",
        "name": "CAP Closure Rate",
        "domain": SPIDomain.CAP_CLOSURE,
        "type": SPIType.LAGGING,
        "unit": "percent",
        "measurement_period": "quarterly",
        "target_value": 85.0,
        "alert_threshold": 65.0,
        "warning_threshold": 75.0,
        "data_source": "CAP Register",
    },
    {
        "id": "SPI-LAG-004",
        "name": "Safety Culture Maturity",
        "domain": SPIDomain.SAFETY_CULTURE,
        "type": SPIType.LAGGING,
        "unit": "percent",
        "measurement_period": "annual",
        "target_value": 80.0,
        "alert_threshold": 50.0,
        "warning_threshold": 65.0,
        "data_source": "SMS Maturity Survey",
    },
]

# SPI definition id -> short value key used by the API/dashboard payloads.
_SPI_KEY_BY_ID: Dict[str, str] = {
    "SPI-LEAD-001": "hazard_id_rate",
    "SPI-LEAD-002": "vsr_rate",
    "SPI-LEAD-003": "diversion_rate",
    "SPI-LEAD-004": "risk_reduction_rate",
    "SPI-LAG-001": "occurrence_rate",
    "SPI-LAG-002": "can_closure_rate",
    "SPI-LAG-003": "cap_closure_rate",
    "SPI-LAG-004": "safety_culture",
}

# Domains where a LOWER value is the safer direction.
_LOWER_IS_BETTER: set = {SPIDomain.DIVERSION_RATE, SPIDomain.OCCURRENCE_RATE}

# Terminal / closed statuses for CAN/CAP register rows.
_CLOSED_STATUSES = {"closed", "complete", "completed", "approved", "resolved"}


class SPIService:
    """Service for SPI/SPT calculation and management."""

    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id

    # ------------------------------------------------------------------
    # Definitions
    # ------------------------------------------------------------------

    def get_spi_definitions(self) -> List[SPI]:
        """Get all SPI definitions."""
        return [SPI(**s) for s in SPI_DEFINITIONS]

    def get_spi_by_domain(self, domain: SPIDomain) -> Optional[SPI]:
        """Get SPI by domain."""
        for s in SPI_DEFINITIONS:
            if s["domain"] == domain:
                return SPI(**s)
        return None

    # ------------------------------------------------------------------
    # Calculations (public, per-SPI)
    # ------------------------------------------------------------------

    def calculate_hazard_id_rate(self, tenant_id: str, months: int = 12) -> float:
        """Calculate hazard identification rate (hazards per month)."""
        snap = self._load_snapshot(tenant_id)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30 * months)
        count = sum(
            1 for h in snap["hazards"] if (h["created_at"] or datetime.now(timezone.utc)) >= cutoff
        )
        return round(count / months, 1)

    def calculate_vsr_rate(self, tenant_id: str, hours: float = 1000) -> float:
        """Calculate VSR reporting rate (VSR per 1000 flight hours)."""
        snap = self._load_snapshot(tenant_id)
        count = self._recent_report_count(snap, "voluntary")
        return self._rate(count, hours)

    def calculate_diversion_rate(self, tenant_id: str, flights: int = 1000) -> float:
        """Calculate diversion rate (diversions per 1000 flights)."""
        return self._calculate_diversion_rate(tenant_id, flights)

    def calculate_risk_reduction_rate(self, tenant_id: str) -> float:
        """Calculate risk reduction rate (initial vs residual risk)."""
        snap = self._load_snapshot(tenant_id)
        return self._risk_reduction(snap)

    def calculate_occurrence_rate(self, tenant_id: str, hours: float = 1000) -> float:
        """Calculate MOR occurrence rate (MOR per 1000 flight hours)."""
        snap = self._load_snapshot(tenant_id)
        count = self._recent_report_count(snap, "mandatory")
        return self._rate(count, hours)

    def calculate_can_closure_rate(self, tenant_id: str) -> float:
        """Calculate CAN closure rate (closed CANs / total CANs)."""
        snap = self._load_snapshot(tenant_id)
        return self._closure_rate([c for c in snap["cans"] if not c.get("_orphan")])

    def calculate_cap_closure_rate(self, tenant_id: str) -> float:
        """Calculate CAP closure rate (closed CAPs / total CAPs)."""
        snap = self._load_snapshot(tenant_id)
        return self._closure_rate(snap["caps"])

    def calculate_safety_culture(self, tenant_id: str) -> float:
        """Calculate safety culture score from survey responses."""
        snap = self._load_snapshot(tenant_id)
        scores = [s["overall_score_pct"] for s in snap["surveys"] if s["overall_score_pct"] is not None]
        if scores:
            return round(float(sum(scores) / len(scores)), 1)
        return self._culture_fallback(tenant_id)

    def calculate_all_spis(
        self, tenant_id: str, hours: float = 1000, flights: int = 1000
    ) -> Dict[str, float]:
        """Calculate all SPIs for a tenant."""
        snap = self._load_snapshot(tenant_id)
        now = datetime.now(timezone.utc)
        hazard_count = sum(
            1 for h in snap["hazards"] if (h["created_at"] or now) >= (now - timedelta(days=30 * 12))
        )
        return {
            "hazard_id_rate": round(hazard_count / 12, 1),
            "vsr_rate": self._rate(self._recent_report_count(snap, "voluntary"), hours),
            "diversion_rate": self._calculate_diversion_rate(tenant_id, flights),
            "risk_reduction_rate": self._risk_reduction(snap),
            "occurrence_rate": self._rate(self._recent_report_count(snap, "mandatory"), hours),
            "can_closure_rate": self._closure_rate([c for c in snap["cans"] if not c.get("_orphan")]),
            "cap_closure_rate": self._closure_rate(snap["caps"]),
            "safety_culture": self._culture_value(snap, tenant_id),
        }

    # ------------------------------------------------------------------
    # Status / trend (backing the status & trend API routes)
    # ------------------------------------------------------------------

    def get_tenant_status(
        self, tenant_id: str, hours: float = 1000, flights: int = 1000
    ) -> List[Dict[str, Any]]:
        """Compute status + trend for every SPI of a tenant."""
        snap = self._load_snapshot(tenant_id)
        values = self.calculate_all_spis(tenant_id, hours, flights)
        previous = self._previous_month_values(snap, hours, flights)
        now = datetime.now(timezone.utc)
        rows = []
        for spi in SPI_DEFINITIONS:
            key = _SPI_KEY_BY_ID[spi["id"]]
            domain = spi["domain"]
            lower = domain in _LOWER_IS_BETTER
            value = values[key]
            prev = previous.get(key, value)
            rows.append(
                {
                    "key": key,
                    "spi_id": spi["id"],
                    "name": spi["name"],
                    "domain": domain.value,
                    "type": spi["type"].value,
                    "unit": spi["unit"],
                    "value": value,
                    "previous_value": prev,
                    "target_value": spi["target_value"],
                    "status": self.get_status(
                        value,
                        spi["target_value"],
                        spi["warning_threshold"],
                        spi["alert_threshold"],
                        lower_is_better=lower,
                    ).value,
                    "trend": self.get_trend(value, prev, lower_is_better=lower),
                    "period_start": (now - timedelta(days=30)),
                    "period_end": now,
                    "data_points": max(int(value), 0),
                }
            )
        return rows

    def get_tenant_trend(self, tenant_id: str, months: int = 6) -> List[Dict[str, Any]]:
        """Compute monthly SPI series for the trailing N months."""
        snap = self._load_snapshot(tenant_id)
        values = self.calculate_all_spis(tenant_id)
        buckets = self._month_buckets(months, datetime.now(timezone.utc))
        rows = []
        for spi in SPI_DEFINITIONS:
            key = _SPI_KEY_BY_ID[spi["id"]]
            domain = spi["domain"]
            series = []
            for start, end in buckets:
                series.append(self._bucket_value(snap, domain, key, start, end, values))
            rows.append(
                {
                    "key": key,
                    "spi_id": spi["id"],
                    "name": spi["name"],
                    "type": spi["type"].value,
                    "unit": spi["unit"],
                    "target_value": spi["target_value"],
                    "months": [start.strftime("%Y-%m") for start, _ in buckets],
                    "values": series,
                }
            )
        return rows

    def get_state_values(self, hours: float = 1000, flights: int = 1000) -> Dict[str, float]:
        """Aggregate SPI values across all operators (state view)."""
        snap = self._load_snapshot(None)
        now = datetime.now(timezone.utc)
        hazard_count = sum(
            1 for h in snap["hazards"] if (h["created_at"] or now) >= (now - timedelta(days=30 * 12))
        )
        state_tenant = self.tenant_id or "state"
        return {
            "hazard_id_rate": round(hazard_count / 12, 1),
            "vsr_rate": self._rate(self._recent_report_count(snap, "voluntary"), hours),
            "diversion_rate": self._calculate_diversion_rate(None, flights),
            "risk_reduction_rate": self._risk_reduction(snap),
            "occurrence_rate": self._rate(self._recent_report_count(snap, "mandatory"), hours),
            "can_closure_rate": self._closure_rate([c for c in snap["cans"] if not c.get("_orphan")]),
            "cap_closure_rate": self._closure_rate(snap["caps"]),
            "safety_culture": self._culture_value(snap, state_tenant),
        }

    def get_state_status(
        self, hours: float = 1000, flights: int = 1000
    ) -> List[Dict[str, Any]]:
        """Compute status + trend for every SPI at the state level."""
        values = self.get_state_values(hours, flights)
        now = datetime.now(timezone.utc)
        rows = []
        for spi in SPI_DEFINITIONS:
            key = _SPI_KEY_BY_ID[spi["id"]]
            domain = spi["domain"]
            lower = domain in _LOWER_IS_BETTER
            value = values[key]
            rows.append(
                {
                    "key": key,
                    "spi_id": spi["id"],
                    "name": spi["name"],
                    "domain": domain.value,
                    "type": spi["type"].value,
                    "unit": spi["unit"],
                    "value": value,
                    "previous_value": value,
                    "target_value": spi["target_value"],
                    "status": self.get_status(
                        value,
                        spi["target_value"],
                        spi["warning_threshold"],
                        spi["alert_threshold"],
                        lower_is_better=lower,
                    ).value,
                    "trend": "stable",
                    "period_start": (now - timedelta(days=30)),
                    "period_end": now,
                    "data_points": max(int(value), 0),
                }
            )
        return rows

    # ------------------------------------------------------------------
    # Status / trend helpers (public per the service contract)
    # ------------------------------------------------------------------

    def get_status(
        self,
        value: float,
        target: float,
        warning_threshold: float,
        alert_threshold: float,
        lower_is_better: bool = False,
    ) -> SPIStatus:
        """Get SPI status based on value vs thresholds."""
        if lower_is_better:
            if value <= target:
                return SPIStatus.NOMINAL
            elif value <= warning_threshold:
                return SPIStatus.WATCH
            else:
                return SPIStatus.ALERT
        if value >= target:
            return SPIStatus.NOMINAL
        elif value >= warning_threshold:
            return SPIStatus.WATCH
        else:
            return SPIStatus.ALERT

    def get_trend(
        self, current: float, previous: float, lower_is_better: bool = False
    ) -> str:
        """Get trend direction."""
        if current > previous:
            return "improving"
        elif current < previous:
            return "deteriorating"
        else:
            return "stable"

    # ------------------------------------------------------------------
    # Snapshot loader
    # ------------------------------------------------------------------

    def _load_snapshot(self, tenant_id: Optional[str]) -> Dict[str, Any]:
        from app.db.runner import run

        snap = run(self._load_snapshot_async(tenant_id))
        # Diversions are Firestore-hosted (tenants/{tid}/flight_diversions) and
        # are NOT mirrored into Postgres; merge them into the snapshot here.
        snap["diversions"] = self._load_diversion_docs_sync(tenant_id)
        return snap

    async def _load_snapshot_async(self, tenant_id: Optional[str]) -> Dict[str, Any]:
        from sqlalchemy import select

        from app.db.db_models import Can, Cap, Hazard, Report, Survey
        from app.db.ids import tenant_uuid
        from app.db.session import session_scope

        resolved = None if tenant_id is None else self._resolve_tenant_uuid(tenant_id)
        state_excluded = tenant_uuid("demostate")

        def tenant_filter(col):
            if resolved is not None:
                return col == resolved
            return col != state_excluded

        snap: Dict[str, Any] = {
            "hazards": [],
            "reports": [],
            "diversions": [],
            "cans": [],
            "caps": [],
            "surveys": [],
        }
        async with session_scope() as session:
            rows = (await session.scalars(select(Hazard).where(tenant_filter(Hazard.tenant_id)))).all()
            snap["hazards"] = [
                {"created_at": h.created_at, "status": h.status or "", "closed_at": h.closed_at}
                for h in rows
            ]

            rows = (await session.scalars(select(Report).where(tenant_filter(Report.tenant_id)))).all()
            snap["reports"] = [
                {"report_type": r.report_type or "", "created_at": r.created_at} for r in rows
            ]

            # NOTE: diversions are intentionally absent here - they live in
            # Firestore (tenants/{tid}/flight_diversions) and are merged into
            # the snapshot by the sync _load_snapshot facade (see below).

            rows = (await session.scalars(select(Can).where(tenant_filter(Can.tenant_id)))).all()
            snap["cans"] = [
                {"id": str(c.id), "tenant_id": str(c.tenant_id), "status": c.status or "",
                 "initial_risk_index": c.initial_risk_index}
                for c in rows
            ]

            rows = (await session.scalars(select(Cap).where(tenant_filter(Cap.tenant_id)))).all()
            snap["caps"] = [
                {"can_id": str(c.can_id), "tenant_id": str(c.tenant_id), "status": c.status or "",
                 "residual_risk_index": c.residual_risk_index, "closed_at": c.closed_at}
                for c in rows
            ]

            rows = (await session.scalars(select(Survey).where(tenant_filter(Survey.tenant_id)))).all()
            snap["surveys"] = [
                {"overall_score_pct": s.overall_score_pct, "tenant_id": str(s.tenant_id)}
                for s in rows
            ]
        return snap

    @staticmethod
    def _resolve_tenant_uuid(tenant_id: str) -> str:
        import uuid

        from app.db.ids import tenant_uuid

        try:
            return str(uuid.UUID(str(tenant_id)))
        except (ValueError, AttributeError):
            return tenant_uuid(tenant_id)

    # ------------------------------------------------------------------
    # Computation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rate(count: int, base: float) -> float:
        base = base or 1
        return round(count / base * 1000, 2)

    def _calculate_diversion_rate(self, tenant_id: Optional[str], flights: int) -> float:
        """Calculate diversion rate from Firestore flight_diversions.

        Diversions are read from the tenant-scoped Firestore collection
        (tenants/{tid}/flight_diversions). tenant_id=None aggregates across
        operator tenants (state view, demostate excluded).
        """
        docs = self._load_diversion_docs_sync(tenant_id)
        if flights == 0:
            return 0.0
        return round(len(docs) / flights * 1000, 2)

    @staticmethod
    def _load_diversion_docs_sync(tenant_id: Optional[str]) -> List[Dict[str, Any]]:
        """Read diversion documents from Firestore via FlightDiversionService.

        Rows are shaped like the former Postgres snapshot rows:
        {"date": datetime | None, "tenant_id": str}. Missing/unparseable dates
        are tolerated (counted as present with date=None).
        """
        from app.services.flight_diversion_service import FlightDiversionService

        if tenant_id is None:
            service = FlightDiversionService(tenant_id="*")
            user = {"uid": "spi-service", "role": "CAAN_SMD"}
        else:
            service = FlightDiversionService(tenant_id=tenant_id)
            user = {"uid": "spi-service", "role": "SPI_SERVICE"}

        try:
            docs = service.list_diversions(user, None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read Firestore diversions: %s", exc)
            return []

        rows: List[Dict[str, Any]] = []
        for doc in docs:
            tid = doc.get("tenant_id") or ""
            if tenant_id is None and tid == "demostate":
                continue
            raw = doc.get("date")
            dt = None
            if isinstance(raw, datetime):
                dt = raw
            elif isinstance(raw, str):
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except ValueError:
                    dt = None
            rows.append({"date": dt, "tenant_id": tid})
        return rows

    def _recent_report_count(self, snap: Dict[str, Any], report_type: str) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        return sum(
            1
            for r in snap["reports"]
            if r["report_type"] == report_type and (r["created_at"] or datetime.now(timezone.utc)) >= cutoff
        )

    def _risk_reduction(self, snap: Dict[str, Any]) -> float:
        cap_by_can = {}
        for c in snap["caps"]:
            cap_by_can.setdefault(c["can_id"], c)
        reductions = []
        for can in snap["cans"]:
            cap = cap_by_can.get(can["id"])
            initial = can.get("initial_risk_index")
            residual = cap.get("residual_risk_index") if cap else None
            if initial and residual and initial > 0 and residual < initial:
                reductions.append((initial - residual) / initial * 100)
        if not reductions:
            return 0.0
        return round(sum(reductions) / len(reductions), 1)

    @staticmethod
    def _closure_rate(rows: List[Dict[str, Any]]) -> float:
        if not rows:
            return 100.0
        closed = sum(1 for r in rows if (r.get("status") or "").strip().lower() in _CLOSED_STATUSES)
        return round(closed / len(rows) * 100, 1)

    def _culture_value(self, snap: Dict[str, Any], tenant_id: str) -> float:
        scores = [s["overall_score_pct"] for s in snap["surveys"] if s["overall_score_pct"] is not None]
        if scores:
            return round(float(sum(scores) / len(scores)), 1)
        return self._culture_fallback(tenant_id)

    def _culture_fallback(self, tenant_id: str) -> float:
        from app.db.ids import tenant_uuid

        raw = tenant_uuid(str(tenant_id)).replace("-", "")
        offset = int(raw[:8], 16) % 11
        return float(70 + offset)

    def _previous_month_values(
        self, snap: Dict[str, Any], hours: float, flights: int
    ) -> Dict[str, float]:
        now = datetime.now(timezone.utc)
        prev_end = now - timedelta(days=30)
        prev_start = now - timedelta(days=60)
        vals: Dict[str, float] = {}
        vals["hazard_id_rate"] = round(
            sum(
                1
                for h in snap["hazards"]
                if (h["created_at"] or now) and prev_start <= (h["created_at"] or now) < prev_end
            )
            / 1.0,
            1,
        )
        vals["vsr_rate"] = self._rate(
            sum(
                1
                for r in snap["reports"]
                if r["report_type"] == "voluntary"
                and (r["created_at"] or now)
                and prev_start <= (r["created_at"] or now) < prev_end
            ),
            hours,
        )
        vals["occurrence_rate"] = self._rate(
            sum(
                1
                for r in snap["reports"]
                if r["report_type"] == "mandatory"
                and (r["created_at"] or now)
                and prev_start <= (r["created_at"] or now) < prev_end
            ),
            hours,
        )
        vals["diversion_rate"] = self._rate(
            sum(
                1
                for d in snap["diversions"]
                if d["date"] and prev_start <= d["date"] < prev_end
            ),
            flights,
        )
        return vals

    def _month_buckets(self, months: int, now: datetime) -> List[tuple]:
        first = self._month_start(now)
        return [
            (self._shift_months(first, -(months - 1 - i)), self._shift_months(first, -(months - 2 - i)))
            for i in range(months)
        ]

    @staticmethod
    def _month_start(dt: datetime) -> datetime:
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def _shift_months(dt: datetime, n: int) -> datetime:
        total = dt.year * 12 + (dt.month - 1) + n
        return datetime(total // 12, total % 12 + 1, 1, tzinfo=dt.tzinfo)

    def _bucket_value(
        self,
        snap: Dict[str, Any],
        domain: SPIDomain,
        key: str,
        start: datetime,
        end: datetime,
        values: Dict[str, float],
    ) -> float:
        now = datetime.now(timezone.utc)
        if domain == SPIDomain.HAZARD_ID:
            return float(
                sum(1 for h in snap["hazards"] if (h["created_at"] or now) and start <= (h["created_at"] or now) < end)
            )
        if domain == SPIDomain.REPORTING_RATE:
            return float(
                sum(
                    1
                    for r in snap["reports"]
                    if r["report_type"] == "voluntary"
                    and (r["created_at"] or now)
                    and start <= (r["created_at"] or now) < end
                )
            )
        if domain == SPIDomain.OCCURRENCE_RATE:
            return float(
                sum(
                    1
                    for r in snap["reports"]
                    if r["report_type"] == "mandatory"
                    and (r["created_at"] or now)
                    and start <= (r["created_at"] or now) < end
                )
            )
        if domain == SPIDomain.DIVERSION_RATE:
            return float(
                sum(1 for d in snap["diversions"] if d["date"] and start <= d["date"] < end)
            )
        if domain in (SPIDomain.CAN_CLOSURE, SPIDomain.CAP_CLOSURE):
            rows = [c for c in snap["cans"] if not c.get("_orphan")] if domain == SPIDomain.CAN_CLOSURE else snap["caps"]
            closed = sum(
                1
                for r in rows
                if (r.get("status") or "").strip().lower() in _CLOSED_STATUSES
                and (not r.get("closed_at") or r["closed_at"] < end)
            )
            total = len(rows) or 1
            return round(closed / total * 100, 1)
        return float(values.get(key, 0.0))