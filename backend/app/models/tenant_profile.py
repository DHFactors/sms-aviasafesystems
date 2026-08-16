"""Tenant Operational Profile model.

Describes each operator's operational footprint so the demo-data seeder can
generate realistic, tenant-consistent records (aircraft fleet, routes,
hazard domains). Profiles are stored in Firestore under
``tenants/{tenant_id}/metadata/profile`` (see seed/tenant_profiles.py).
"""

from typing import List, Optional

from pydantic import BaseModel, Field


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