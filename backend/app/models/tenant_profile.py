"""Tenant Operational Profile model.

Describes each operator's operational footprint so the demo-data seeder can
generate realistic, tenant-consistent records (aircraft fleet, routes,
hazard domains). Profiles are stored in Firestore under
``tenants/{tenant_id}/metadata/profile`` (see seed/tenant_profiles.py).
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class OperationalScope(str, Enum):
    """Formal tenant classification governing flight operation scope and the
    department / postholder structures the tenant is permitted to hold.

    Airline classes are the only ones that operate flights (hold an AOC and
    maintain flight operations + CAMO). AMOs, aerodromes, ground-handling
    providers and CAAN directorates are non-flight service providers.

    ``departments`` lists the department codes each scope is permitted to
    hold (see :attr:`TenantOperationalProfile.applicable_departments`).
    """

    AIRLINE_FIXED_WING = "AIRLINE_FIXED_WING"
    AIRLINE_ROTARY = "AIRLINE_ROTARY"
    AMO = "AMO"
    AERODROME = "AERODROME"
    GROUND_HANDLING = "GROUND_HANDLING"
    REGULATOR = "REGULATOR"

    @property
    def operates_flights(self) -> bool:
        """True ONLY for fixed-wing / rotary airline operators that hold an
        AOC and physically operate flights."""
        return self in (OperationalScope.AIRLINE_FIXED_WING, OperationalScope.AIRLINE_ROTARY)

    @property
    def departments(self) -> List[str]:
        """Department codes applicable to this classification.

        * Airlines: flight_ops + camo + corporate safety + qa.
        * AMO: base/line maintenance (145) + qa + safety. NO flight ops / CAMO.
        * Aerodrome: airside ops + ARFF + safety/qa. NO flight ops / CAMO / 145.
        * Ground handling: ground ops + qa + safety.
        * Regulator (CAAN directorate): safety + SMD / FSSD / ASSD oversight
          directorates.
        """
        return {
            OperationalScope.AIRLINE_FIXED_WING: ["safety", "flight_ops", "camo", "qa"],
            OperationalScope.AIRLINE_ROTARY: ["safety", "flight_ops", "camo", "qa"],
            OperationalScope.AMO: ["safety", "maintenance_145", "qa"],
            OperationalScope.AERODROME: ["safety", "airside_ops", "arff"],
            OperationalScope.GROUND_HANDLING: ["safety", "ground_ops", "qa"],
            OperationalScope.REGULATOR: ["safety", "smd", "fssd", "assd"],
        }[self]


class TenantOperationalProfile(BaseModel):
    """Structured operational footprint for a single tenant.

    ``fleet`` holds the aircraft types for fixed/rotor-wing operators and the
    equipment inventory for AMO / aerodrome / ground-handling providers.
    ``authorized_destinations`` restricts every seeded departure, arrival and
    occurrence location to airports / STOL strips / LZs the tenant actually
    serves, so rotor-wing operators never receive fixed-wing routes and trunk
    jets never land at mountain STOL strips.
    """

    tenant_id: str = Field(..., description="Firestore tenant document id / slug")
    slug: str = Field(..., description="Readable slug (usually == tenant_id)")
    tenant_name: str = Field(..., description="Operator display name")
    email: str = Field(..., description="Operator safety / contact email")
    category: str = Field(
        ...,
        description=(
            "Operational category: Fixed-Wing | Rotor-Wing | Independent AMO | "
            "Certified Aerodrome | Ground Handling Services | CAAN Directorates"
        ),
    )
    operation_type: Optional[str] = Field(None, description="e.g. Scheduled / STOL / HEMS")
    fleet: List[str] = Field(..., description="Aircraft types or equipment inventory")
    base_hub: str = Field(..., description="Home airport / base / helipad")
    authorized_destinations: List[str] = Field(
        ..., description="Valid ICAO airports, STOL strips, LZs or operational zones"
    )
    hazard_domains: List[str] = Field(
        ..., description="Domain-specific safety risk categories applicable to this operator"
    )
    scope: OperationalScope = Field(
        ..., description="Formal tenant classification (drives flight scope + department applicability)"
    )
    operates_flights: Optional[bool] = Field(
        None,
        description="True ONLY for AOC-holding airlines (fixed-wing + rotary). AMO / "
        "aerodrome / ground-handling / regulator tenants never operate flights. "
        "Derived from ``scope``.",
    )
    applicable_departments: Optional[List[str]] = Field(
        None,
        description="Department codes the tenant's structure may hold, adapted to the "
        "operational classification (e.g. an AMO has maintenance_145 + qa but NO "
        "flight_ops / camo; an aerodrome has airside_ops + arff but NO camo / 145). "
        "Derived from ``scope``.",
    )

    @model_validator(mode="after")
    def _derive_classification_fields(self) -> "TenantOperationalProfile":
        """Derive flight scope + department applicability from the formal scope."""
        self.operates_flights = self.scope.operates_flights
        self.applicable_departments = list(self.scope.departments)
        return self