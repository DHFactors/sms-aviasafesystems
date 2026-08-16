"""Tenant Operational Profile Registry.

Maps every active OPERATOR_PROFILES tenant to an authentic operational
footprint (category, fleet, base hub, authorized destinations and hazard
domains) used to enforce seeder constraints:

* Fleet match        — seeded aircraft types only come from the tenant's fleet
* Location match     — seeded occurrences only reference authorized destinations
* Occurrence realism — occurrence types / hazard titles are drawn from the
  tenant's hazard domains (rotor-wing never gets fixed-wing content, trunk
  jets never land at mountain STOL strips, AMO / aerodrome providers get
  maintenance / apron exposure)

Profiles are stored in Firestore under ``tenants/{tenant_id}/profile``
(see ``write_tenant_profiles``). The registry is the single source of truth;
the demo seeder reads it via the ``get_*`` helpers below with graceful
fallbacks so pre-existing profiles still seed cleanly.
"""

from typing import List, Optional

from app.models.tenant_profile import TenantOperationalProfile
from seed.config import CREDENTIAL_EMAIL_DOMAINS, OPERATOR_PROFILES

CATEGORY_FIXED_WING = "Fixed-Wing"
CATEGORY_ROTOR_WING = "Rotor-Wing"
CATEGORY_AMO = "Independent AMO"
CATEGORY_AERODROME = "Certified Aerodrome"
CATEGORY_GROUND_HANDLING = "Ground Handling Services"
CATEGORY_CAAN = "CAAN Directorates"

# Firestore path: tenants/{tenant_id}/profile/{PROFILE_DOC_ID}
PROFILE_COLLECTION = "profile"
PROFILE_DOC_ID = "operational"


def _operator_email(tenant_id: str) -> str:
    domain = CREDENTIAL_EMAIL_DOMAINS.get(tenant_id, f"{tenant_id}.com")
    return f"safety@{domain}"


# Route short-code -> full airport display name (mirrors NEPAL_AIRPORTS).
_ROUTE_CODE_TO_AIRPORT = {
    "KTM": "Kathmandu (VNKT)",
    "VNKT": "Kathmandu (VNKT)",
    "PKR": "Pokhara (VNPK)",
    "VNPK": "Pokhara (VNPK)",
    "SDR": "Simara (VNSI)",
    "BWA": "Siddharthanagar (VNBW)",
    "JKR": "Janakpur (VNJP)",
    "BHR": "Bharatpur (VNBG)",
    "TPN": "Taplejung (VNTJ)",
    "DP": "Dolpa (VNDP)",
    "SIF": "Simikot (VNSK)",
    "LUA": "Lukla (VNLK)",
    "BJP": "Bhojpur (VNBJ)",
    "JMO": "Jomsom (VNJS)",
    "MUG": "Mugu (VNMU)",
    "JUM": "Jumla (VNJL)",
    "KEP": "Kangel Danda (VNDG)",
    "SYX": "Syangboche (VNSB)",
    "OGU": "Ongu / Everest Base Camp LZ",
    "EBO": "Everest Base Camp LZ",
    "IMK": "Ilam (VNDL)",
    "DPR": "Dolpa (VNDP)",
    "TPJ": "Taplejung (VNTJ)",
}

# Explicit profiles for the ten active OPERATOR_PROFILES tenants. Values follow
# each tenant's real aircraft_types / routes in seed/config.py so the registry
# stays consistent with the credential + operator metadata already seeded.
TENANT_OPERATIONAL_PROFILES = {
    "buddha-air": TenantOperationalProfile(
        tenant_id="buddha-air",
        slug="buddha-air",
        tenant_name="Buddha Air",
        email=_operator_email("buddha-air"),
        category=CATEGORY_FIXED_WING,
        operation_type="Scheduled domestic + regional",
        fleet=["Beechcraft 1900D", "ATR 42-320", "ATR 72-500"],
        base_hub="Kathmandu (VNKT)",
        authorized_destinations=[
            "Kathmandu (VNKT)", "Pokhara (VNPK)", "Simara (VNSI)",
            "Siddharthanagar (VNBW)", "Janakpur (VNJP)", "Bharatpur (VNBG)",
            "Taplejung (VNTJ)", "Dolpa (VNDP)",
        ],
        hazard_domains=[
            "Wake Turbulence", "Runway Incursion", "Wildlife & Bird Control",
            "Apron GSE", "De-icing Operations",
        ],
    ),
    "air-dynasty": TenantOperationalProfile(
        tenant_id="air-dynasty",
        slug="air-dynasty",
        tenant_name="Air Dynasty Heli Services",
        email=_operator_email("air-dynasty"),
        category=CATEGORY_ROTOR_WING,
        operation_type="HEMS / VIP / mountain LZ",
        fleet=["Airbus AS350 Écureuil", "Bell 407", "Bell 429 GlobalRanger", "Eurocopter EC135"],
        base_hub="Kathmandu (VNKT) Helipad",
        authorized_destinations=[
            "Kathmandu (VNKT)", "Everest Base Camp LZ", "Ongu / Everest Base Camp LZ",
            "Lukla (VNLK)", "Kangel Danda (VNDG)", "Pokhara (VNPK)", "Dolpa (VNDP)",
        ],
        hazard_domains=[
            "Density Altitude", "Sling Load Operations", "Tail Rotor Clearance",
            "Mountain Valley Clouding", "High-Altitude HEMS",
        ],
    ),
    "ktm-mro": TenantOperationalProfile(
        tenant_id="ktm-mro",
        slug="ktm-mro",
        tenant_name="Kathmandu MRO Services",
        email=_operator_email("ktm-mro"),
        category=CATEGORY_AMO,
        operation_type="Independent AMO (base + line)",
        fleet=["Engine Test Benches", "Avionics Calibration Rigs", "NDT Mobile Labs"],
        base_hub="TIA Hangar Complex, Kathmandu",
        authorized_destinations=[
            "Kathmandu (VNKT)", "Pokhara (VNPK)", "Nepalgunj (VNKG)",
        ],
        hazard_domains=[
            "Tool FOD", "Torque Calibration Drift", "Maintenance Human Factors (MEDA)",
            "Counterfeit / Unapproved Parts",
        ],
    ),
    "pokhara-aerodrome": TenantOperationalProfile(
        tenant_id="pokhara-aerodrome",
        slug="pokhara-aerodrome",
        tenant_name="Pokhara Regional Aerodrome",
        email=_operator_email("pokhara-aerodrome"),
        category=CATEGORY_AERODROME,
        operation_type="Certified aerodrome (Runway 05/23)",
        fleet=["ARFF Crash Tenders", "Runway Sweepers", "Friction Testers"],
        base_hub="Pokhara (VNPK)",
        authorized_destinations=[
            "Pokhara (VNPK)", "Kathmandu (VNKT)", "Bharatpur (VNBG)",
        ],
        hazard_domains=[
            "Runway Incursion", "Runway Excursion", "Wildlife & Bird Control",
            "Apron GSE", "Runway Rubber Deposition",
        ],
    ),
    "himalaya-ground-services": TenantOperationalProfile(
        tenant_id="himalaya-ground-services",
        slug="himalaya-ground-services",
        tenant_name="Himalaya Ground Handling",
        email=_operator_email("himalaya-ground-services"),
        category=CATEGORY_GROUND_HANDLING,
        operation_type="Ground handling / turnaround services",
        fleet=["Ground Power Units (GPU)", "Baggage Belt Loaders", "Pushback Tugs", "Passenger Stairs"],
        base_hub="Kathmandu (VNKT)",
        authorized_destinations=[
            "Kathmandu (VNKT)", "Pokhara (VNPK)", "Bharatpur (VNBG)",
        ],
        hazard_domains=[
            "Pushback Operations", "Baggage / GSE Collisions", "FOD on Apron", "Apron GSE",
        ],
    ),
    "yeti-airlines": TenantOperationalProfile(
        tenant_id="yeti-airlines",
        slug="yeti-airlines",
        tenant_name="Yeti Airlines",
        email=_operator_email("yeti-airlines"),
        category=CATEGORY_FIXED_WING,
        operation_type="Scheduled + STOL mountain",
        fleet=["ATR 72-500", "ATR 42-320", "de Havilland DHC-6 Twin Otter"],
        base_hub="Kathmandu (VNKT)",
        authorized_destinations=[
            "Kathmandu (VNKT)", "Pokhara (VNPK)", "Siddharthanagar (VNBW)",
            "Janakpur (VNJP)", "Dolpa (VNDP)", "Simikot (VNSK)",
            "Taplejung (VNTJ)", "Lukla (VNLK)",
        ],
        hazard_domains=[
            "Mountain Ridge Turbulence", "Wake Turbulence", "Short Runway Braking",
            "Micro-climate Fog",
        ],
    ),
    "summit-air": TenantOperationalProfile(
        tenant_id="summit-air",
        slug="summit-air",
        tenant_name="Summit Air",
        email=_operator_email("summit-air"),
        category=CATEGORY_FIXED_WING,
        operation_type="STOL / mountain cargo + passenger",
        fleet=["Dornier Do 228", "Let L-410 Turbolet", "de Havilland DHC-6 Twin Otter"],
        base_hub="Kathmandu (VNKT)",
        authorized_destinations=[
            "Kathmandu (VNKT)", "Simikot (VNSK)", "Dolpa (VNDP)", "Lukla (VNLK)",
            "Taplejung (VNTJ)", "Bhojpur (VNBJ)",
        ],
        hazard_domains=[
            "Box Canyon / Terrain Avoidance", "Density Altitude",
            "Short Runway Braking", "Mountain Ridge Turbulence",
        ],
    ),
    "sita-air": TenantOperationalProfile(
        tenant_id="sita-air",
        slug="sita-air",
        tenant_name="Sita Air",
        email=_operator_email("sita-air"),
        category=CATEGORY_FIXED_WING,
        operation_type="Scheduled + STOL mountain",
        fleet=["de Havilland DHC-6 Twin Otter", "Dornier Do 228"],
        base_hub="Kathmandu (VNKT)",
        authorized_destinations=[
            "Kathmandu (VNKT)", "Pokhara (VNPK)", "Simikot (VNSK)",
            "Dolpa (VNDP)", "Lukla (VNLK)", "Taplejung (VNTJ)",
        ],
        hazard_domains=[
            "Mountain Ridge Turbulence", "Short Runway Braking",
            "Wildlife & Bird Control", "FOD on Apron",
        ],
    ),
    "simrik-air": TenantOperationalProfile(
        tenant_id="simrik-air",
        slug="simrik-air",
        tenant_name="Simrik Air",
        email=_operator_email("simrik-air"),
        category=CATEGORY_ROTOR_WING,
        operation_type="VFR helicopter / mountain LZ",
        fleet=["Airbus AS350 Écureuil", "Bell 407"],
        base_hub="Pokhara (VNPK) Helipad",
        authorized_destinations=[
            "Pokhara (VNPK)", "Jomsom (VNJS)", "Kangel Danda (VNDG)",
            "Dolpa (VNDP)", "Syangboche (VNSB)", "Mugu (VNMU)",
        ],
        hazard_domains=[
            "Density Altitude", "Mountain Valley Clouding", "Sling Load Operations",
            "High-Altitude HEMS",
        ],
    ),
    "tara-air": TenantOperationalProfile(
        tenant_id="tara-air",
        slug="tara-air",
        tenant_name="Tara Air",
        email=_operator_email("tara-air"),
        category=CATEGORY_FIXED_WING,
        operation_type="STOL mountain scheduled",
        fleet=["de Havilland DHC-6 Twin Otter", "Dornier 228"],
        base_hub="Kathmandu (VNKT)",
        authorized_destinations=[
            "Kathmandu (VNKT)", "Lukla (VNLK)", "Ilam (VNDL)", "Jumla (VNJL)",
            "Dolpa (VNDP)", "Taplejung (VNTJ)", "Kangel Danda (VNDG)",
        ],
        hazard_domains=[
            "Box Canyon / Terrain Avoidance", "Micro-climate Fog",
            "Density Altitude", "Short Runway Braking",
        ],
    ),
}

# Optional additional demo tenants (reference profiles, not active in
# OPERATOR_PROFILES). Available for future activation via OPERATOR_PROFILES.
DEMO_REFERENCE_PROFILES = {
    "himalaya-airlines-demo": TenantOperationalProfile(
        tenant_id="himalaya-airlines-demo",
        slug="himalaya-airlines-demo",
        tenant_name="Himalaya Airlines (Demo)",
        email="safety@himalaya-airlines-demo.com",
        category=CATEGORY_FIXED_WING,
        operation_type="Scheduled international / trunk",
        fleet=["Airbus A319", "Airbus A320"],
        base_hub="Kathmandu (VNKT)",
        authorized_destinations=[
            "Kathmandu (VNKT)", "Bangkok (VTBS)", "Kuala Lumpur (WMKK)",
            "Doha (OTHH)", "Dubai (OMDB)",
        ],
        hazard_domains=[
            "Jet Wake Turbulence", "De-icing Operations",
            "High-Altitude Engine", "International Slot",
        ],
    ),
    "yeti-tara-demo": TenantOperationalProfile(
        tenant_id="yeti-tara-demo",
        slug="yeti-tara-demo",
        tenant_name="Yeti-Tara (Demo)",
        email="safety@yeti-tara-demo.com",
        category=CATEGORY_FIXED_WING,
        operation_type="Scheduled + STOL mountain",
        fleet=["ATR 72-500", "de Havilland DHC-6 Twin Otter 400"],
        base_hub="Kathmandu (VNKT) / Nepalgunj (VNKG)",
        authorized_destinations=[
            "Kathmandu (VNKT)", "Nepalgunj (VNKG)", "Lukla (VNLK)", "Jomsom (VNJS)",
        ],
        hazard_domains=[
            "Mountain Ridge Turbulence", "Box Canyon / Terrain Avoidance",
            "Micro-climate Fog", "Short Runway Braking",
        ],
    ),
    "air-dynasty-demo": TenantOperationalProfile(
        tenant_id="air-dynasty-demo",
        slug="air-dynasty-demo",
        tenant_name="Air Dynasty (Demo)",
        email="safety@air-dynasty-demo.com",
        category=CATEGORY_ROTOR_WING,
        operation_type="HEMS / high-altitude LZ",
        fleet=["Airbus H125", "Bell 407GXi"],
        base_hub="Kathmandu (VNKT) / Pokhara (VNPK) Helipad",
        authorized_destinations=[
            "Kathmandu (VNKT)", "Everest Base Camp LZ", "Gorakshep LZ",
            "Lukla (VNLK)", "Annapurna Base Camp LZ", "Langtang (VNLT)",
            "Manang (VNMA)", "Namche LZ",
        ],
        hazard_domains=[
            "Density Altitude", "Sling Load Operations", "Tail Rotor Clearance",
            "Mountain Valley Clouding",
        ],
    ),
    "nepal-aero-maintenance-demo": TenantOperationalProfile(
        tenant_id="nepal-aero-maintenance-demo",
        slug="nepal-aero-maintenance-demo",
        tenant_name="Nepal Aero Maintenance (Demo)",
        email="safety@nepal-aero-maintenance-demo.com",
        category=CATEGORY_AMO,
        operation_type="Independent AMO (TIA hangar)",
        fleet=["Engine Test Benches", "Avionics Calibration Rigs", "NDT Mobile Labs"],
        base_hub="TIA Hangar, Kathmandu",
        authorized_destinations=["Kathmandu (VNKT)"],
        hazard_domains=[
            "Tool FOD", "Torque Calibration Drift",
            "Maintenance Human Factors (MEDA)", "Counterfeit / Unapproved Parts",
        ],
    ),
    "tia-kathmandu-demo": TenantOperationalProfile(
        tenant_id="tia-kathmandu-demo",
        slug="tia-kathmandu-demo",
        tenant_name="TIA Kathmandu (Demo)",
        email="safety@tia-kathmandu-demo.com",
        category=CATEGORY_AERODROME,
        operation_type="Certified aerodrome (RWY 02/20)",
        fleet=["ARFF Crash Tenders", "Runway Sweepers", "Friction Testers"],
        base_hub="Kathmandu (VNKT)",
        authorized_destinations=[
            "Kathmandu (VNKT)", "Pokhara (VNPK)", "Bharatpur (VNBG)",
        ],
        hazard_domains=[
            "Runway Incursion", "Runway Excursion", "Wildlife & Bird Control",
            "Apron GSE", "Runway Rubber Deposition",
        ],
    ),
}

ALL_PROFILES = {**TENANT_OPERATIONAL_PROFILES, **DEMO_REFERENCE_PROFILES}


def get_profile(tenant_id: str) -> Optional[TenantOperationalProfile]:
    """Return the operational profile for a tenant, or None when unregistered."""
    return ALL_PROFILES.get(tenant_id)


def get_aircraft_fleet(tenant_id: str) -> List[str]:
    """Aircraft types / equipment inventory for the tenant (fleet match)."""
    profile = get_profile(tenant_id)
    if profile:
        return list(profile.fleet)
    # Fallback: derive from OPERATOR_PROFILES aircraft_types.
    for p in OPERATOR_PROFILES:
        if p["id"] == tenant_id:
            return list(p.get("aircraft_types") or [])
    return []


def get_authorized_destinations(tenant_id: str) -> List[str]:
    """Authorized airports / LZs / zones (location match)."""
    profile = get_profile(tenant_id)
    if profile:
        return list(profile.authorized_destinations)
    return []


def get_hazard_domains(tenant_id: str) -> List[str]:
    """Hazard domains applicable to the tenant (occurrence realism)."""
    profile = get_profile(tenant_id)
    if profile:
        return list(profile.hazard_domains)
    return []


def authorized_destinations_from_routes(routes: List[str]) -> List[str]:
    """Expand OPERATOR_PROFILES route short-codes into airport display names."""
    out = []
    for route in routes:
        for code in str(route).split("-"):
            name = _ROUTE_CODE_TO_AIRPORT.get(code)
            if name and name not in out:
                out.append(name)
    return out


# ---------------------------------------------------------------------------
# Occurrence realism: map each hazard domain to the VSR / MOR occurrence types
# and hazard titles that are plausible for that domain. Seeded docs draw from
# the tenant's domain pools (falling back to the generic pools when a tenant
# has no registered domains).
# ---------------------------------------------------------------------------

DOMAIN_TO_VSR_OCCURRENCE_TYPES = {
    "Wake Turbulence": ["Near Miss", "SOP Deviation", "CRM", "Communication"],
    "Runway Incursion": ["Near Miss", "SOP Deviation", "Communication"],
    "Runway Excursion": ["Near Miss", "SOP Deviation", "Communication"],
    "Wildlife & Bird Control": ["Bird Activity"],
    "Apron GSE": ["Ground Handling", "Ramp Safety"],
    "De-icing Operations": ["SOP Deviation", "Weather"],
    "Density Altitude": ["Weather", "Near Miss", "Human Factors"],
    "Sling Load Operations": ["Ramp Safety", "Ground Handling", "Near Miss"],
    "Tail Rotor Clearance": ["Ramp Safety", "Ground Handling", "Near Miss"],
    "Mountain Valley Clouding": ["Weather", "Near Miss", "Communication"],
    "High-Altitude HEMS": ["Weather", "Human Factors", "Near Miss"],
    "Tool FOD": ["FOD", "Maintenance Hazard"],
    "Torque Calibration Drift": ["Maintenance Hazard"],
    "Maintenance Human Factors (MEDA)": ["Maintenance Hazard", "Human Factors", "Fatigue"],
    "Counterfeit / Unapproved Parts": ["Maintenance Hazard", "SOP Deviation"],
    "Runway Rubber Deposition": ["FOD", "Ground Handling"],
    "Pushback Operations": ["Ground Handling", "Ramp Safety", "SOP Deviation"],
    "Baggage / GSE Collisions": ["Ground Handling", "Ramp Safety"],
    "FOD on Apron": ["FOD", "Ramp Safety"],
    "Mountain Ridge Turbulence": ["Weather", "Near Miss", "Human Factors"],
    "Box Canyon / Terrain Avoidance": ["Weather", "Near Miss", "SOP Deviation"],
    "Short Runway Braking": ["Weather", "Near Miss", "SOP Deviation"],
    "Micro-climate Fog": ["Weather", "Communication"],
    "Jet Wake Turbulence": ["Near Miss", "CRM", "Communication"],
    "High-Altitude Engine": ["Maintenance Hazard", "Near Miss"],
    "International Slot": ["Dispatch", "SOP Deviation"],
}

DOMAIN_TO_MOR_OCCURRENCE_TYPES = {
    "Wake Turbulence": ["Airborne Conflict", "Abnormal Runway Contact"],
    "Runway Incursion": ["Runway Incursion"],
    "Runway Excursion": ["Runway Excursion"],
    "Wildlife & Bird Control": ["Bird Strike"],
    "Apron GSE": ["Ground Collision"],
    "De-icing Operations": ["Weather Encounter"],
    "Density Altitude": ["Weather Encounter", "Abnormal Runway Contact"],
    "Sling Load Operations": ["Ground Collision"],
    "Tail Rotor Clearance": ["Ground Collision"],
    "Mountain Valley Clouding": ["Weather Encounter", "ATC Operational Incident"],
    "High-Altitude HEMS": ["Weather Encounter"],
    "Tool FOD": ["System/Component Failure"],
    "Torque Calibration Drift": ["System/Component Failure"],
    "Maintenance Human Factors (MEDA)": ["Procedural Deviation", "System/Component Failure"],
    "Counterfeit / Unapproved Parts": ["System/Component Failure"],
    "Runway Rubber Deposition": ["Abnormal Runway Contact"],
    "Pushback Operations": ["Ground Collision"],
    "Baggage / GSE Collisions": ["Ground Collision"],
    "FOD on Apron": ["Ground Collision", "System/Component Failure"],
    "Mountain Ridge Turbulence": ["Weather Encounter", "Airborne Conflict"],
    "Box Canyon / Terrain Avoidance": ["Weather Encounter", "Airborne Conflict"],
    "Short Runway Braking": ["Abnormal Runway Contact", "Runway Excursion"],
    "Micro-climate Fog": ["Weather Encounter", "ATC Operational Incident"],
    "Jet Wake Turbulence": ["Airborne Conflict"],
    "High-Altitude Engine": ["Powerplant Failure"],
    "International Slot": ["ATC Operational Incident", "Procedural Deviation"],
}

DOMAIN_TO_HAZARD_TITLES = {
    "Wake Turbulence": [
        "Wake turbulence encounter on short final",
        "Wake vortex reported during departure sequence",
        "Unexpected wake-induced roll on approach",
    ],
    "Runway Incursion": [
        "Vehicle entered runway without clearance",
        "Aircraft crossed hold short line during taxi",
        "Uncoordinated runway entry during reduced visibility",
    ],
    "Runway Excursion": [
        "Aircraft departed runway surface on landing roll",
        "Overrun risk on water-contaminated runway",
    ],
    "Wildlife & Bird Control": [
        "Recurrent bird activity on runway approach",
        "Large flock observed near departure threshold",
        "Bird strike risk during migratory season",
    ],
    "Apron GSE": [
        "Ground power unit positioned too close to wingtip",
        "Baggage cart collision on the apron",
        "Uncontrolled GSE movement near stand",
    ],
    "De-icing Operations": [
        "Insufficient de-icing coverage during cold weather",
        "De-icing fluid residue on critical surfaces",
        "Delayed de-icing causing frost accumulation",
    ],
    "Density Altitude": [
        "Reduced performance at high density altitude",
        "Marginal climb gradient at hot-and-high strip",
        "High-altitude performance margin concerns",
    ],
    "Sling Load Operations": [
        "Sling load oscillation during external lift",
        "Load release malfunction during longline ops",
        "Unstable underslung load on approach",
    ],
    "Tail Rotor Clearance": [
        "Tail rotor clearance compromise at congested LZ",
        "Obstacle proximity during confined-area landing",
    ],
    "Mountain Valley Clouding": [
        "Rapid valley clouding trapped VFR helicopter",
        "Deteriorating weather in mountain corridor",
    ],
    "High-Altitude HEMS": [
        "HEMS crew fatigue at high-altitude scene",
        "High-altitude medical evacuation performance margin",
    ],
    "Tool FOD": [
        "Tooling FOD left in engine bay after maintenance",
        "Uncontrolled tool control during line maintenance",
    ],
    "Torque Calibration Drift": [
        "Torque wrench calibration drift beyond tolerance",
        "Unverified torque application on critical fasteners",
    ],
    "Maintenance Human Factors (MEDA)": [
        "Maintenance documentation gaps for airworthy release",
        "Sign-off error under time pressure in hangar",
    ],
    "Counterfeit / Unapproved Parts": [
        "Suspected unapproved part in the supply chain",
        "Part traceability gap for rotable components",
    ],
    "Runway Rubber Deposition": [
        "Reduced braking action from rubber build-up",
        "Runway friction degradation from rubber deposition",
    ],
    "Pushback Operations": [
        "Pushback tug disconnect during towing",
        "Uncleared pushback into adjacent stand",
    ],
    "Baggage / GSE Collisions": [
        "Baggage cart striking aircraft fuselage",
        "GSE-to-GSE collision on the ramp",
    ],
    "FOD on Apron": [
        "Inadequate FOD control on the apron",
        "Foreign object debris near engine intake",
    ],
    "Mountain Ridge Turbulence": [
        "Obstacle clearance margin at mountain STOL strip",
        "Ridge turbulence during mountain circuit",
        "Downdraft encounter on leeward side of ridge",
    ],
    "Box Canyon / Terrain Avoidance": [
        "Box canyon terrain avoidance during approach",
        "Restricted escape route at confined mountain strip",
    ],
    "Short Runway Braking": [
        "Marginal braking on short mountain runway",
        "Wet short runway braking performance concern",
    ],
    "Micro-climate Fog": [
        "Sudden micro-climate fog closure of mountain strip",
        "Localized fog affecting short-field approach",
    ],
    "Jet Wake Turbulence": [
        "Jet wake turbulence encounter on final",
        "Wake turbulence from heavy traffic on approach",
    ],
    "High-Altitude Engine": [
        "High-altitude engine performance degradation",
        "Engine start difficulty at high elevation",
    ],
    "International Slot": [
        "International slot coordination error at hub",
        "Slot misalignment causing late pushback",
    ],
}


def _pooled(items: Optional[List[str]], fallback: List[str]) -> List[str]:
    """Return the domain-pooled items if any, else the generic fallback pool."""
    seen = []
    for item in items or []:
        if item and item not in seen:
            seen.append(item)
    return seen or list(fallback)


def vsr_occurrence_types_for_tenant(tenant_id: str, fallback: List[str]) -> List[str]:
    """VSR occurrence types plausible for the tenant's hazard domains."""
    domains = get_hazard_domains(tenant_id)
    mapped = []
    for domain in domains:
        mapped.extend(DOMAIN_TO_VSR_OCCURRENCE_TYPES.get(domain, []))
    return _pooled(mapped, fallback)


def mor_occurrence_types_for_tenant(tenant_id: str, fallback: List[str]) -> List[str]:
    """MOR occurrence types plausible for the tenant's hazard domains."""
    domains = get_hazard_domains(tenant_id)
    mapped = []
    for domain in domains:
        mapped.extend(DOMAIN_TO_MOR_OCCURRENCE_TYPES.get(domain, []))
    return _pooled(mapped, fallback)


def hazard_titles_for_tenant(tenant_id: str, fallback: List[str]) -> List[str]:
    """Hazard titles plausible for the tenant's hazard domains."""
    domains = get_hazard_domains(tenant_id)
    mapped = []
    for domain in domains:
        mapped.extend(DOMAIN_TO_HAZARD_TITLES.get(domain, []))
    return _pooled(mapped, fallback)


def write_tenant_profiles(db, tenant_ids: Optional[List[str]] = None) -> int:
    """Write each tenant's operational profile to ``tenants/{tenant_id}/profile``.

    Returns the number of profiles written. Non-registered tenants are skipped.
    """
    from app.core.config import settings

    ids = tenant_ids or list(TENANT_OPERATIONAL_PROFILES.keys())
    written = 0
    for tenant_id in ids:
        profile = get_profile(tenant_id)
        if profile is None:
            continue
        doc_ref = (
            db.collection(settings.FIREBASE_COLLECTION_TENANTS)
            .document(tenant_id)
            .collection(PROFILE_COLLECTION)
            .document(PROFILE_DOC_ID)
        )
        doc_ref.set(profile.model_dump())
        written += 1
    return written