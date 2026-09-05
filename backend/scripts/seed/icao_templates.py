# ============================================================================
# FILE: icao_templates.py
# PATH: backend/scripts/seed/icao_templates.py
# PURPOSE: ICAO Annex 19 / CAAN CAR-19 hazard templates used by the unified
#          seeder (unified_seeder.py) and tenant onboarding (onboarding_service).
#
#          Each template declares the full CAAN Chapter 2.1 hazard field set:
#              threat, taxonomy, source, top_event, consequence,
#              recommended_action, corrective_action_flag, srm_flag,
#              priority_date, status_date, remarks, function (area),
#              plus title / description and a default priority.
#          Templates are keyed by ICAO function code so the seeder can seed a
#          single functional area or the whole register.
# ============================================================================

from datetime import datetime, timezone

# The 14-field CAAN Chapter 2.1 hazard record keys written by the seeder.
CAAN_FIELD_KEYS = (
    "hazard_id", "function", "threat", "taxonomy", "source", "top_event",
    "consequence", "recommended_action", "corrective_action_flag", "srm_flag",
    "priority_date", "status_date", "remarks", "priority",
)

HAZARD_TEMPLATES = {
    "OPS": [
        {
            "title": "Unstabilised approach during mountainous terrain ops",
            "description": "Crew performed a continued unstabilised approach at a high-altitude STOL strip with terrain clearance reduced.",
            "threat": "Dual high workload: mountainous terrain navigation combined with late ATC re-routing.",
            "taxonomy": "Human",
            "source": "MOR",
            "top_event": "Loss of control or controlled flight into terrain during approach.",
            "consequence": "Catastrophic — hull loss with passenger and ground impact potential.",
            "recommended_action": "Re-brief stable-approach criteria and review approach minima for terrain.",
            "corrective_action_flag": True,
            "srm_flag": True,
            "priority": "H",
            "remarks": "Seeded from CAAN Chapter 2.1 high-risk approach template.",
        },
        {
            "title": "Runway incursion at uncontrolled aerodrome",
            "description": "Ground vehicle entered the runway during a live departure pattern.",
            "threat": "Non-radio-equipped vehicles operating at an uncontrolled airfield.",
            "taxonomy": "Organizational",
            "source": "Internal Audit",
            "top_event": "Runway collision between aircraft and ground vehicle.",
            "consequence": "Hazardous — wing/personnel strike with injury potential.",
            "recommended_action": "Mandatory radio-equipping of airside vehicles and re-briefing of ground marshals.",
            "corrective_action_flag": True,
            "srm_flag": False,
            "priority": "M",
            "remarks": "Seeded organizational runway-safety template.",
        },
    ],
    "MNT": [
        {
            "title": "Torque calibration drift on critical fasteners",
            "description": "Repeated out-of-tolerance torque readings on control-system fasteners during scheduled maintenance.",
            "threat": "Calibration drift in torque tools across the maintenance base.",
            "taxonomy": "Technical",
            "source": "Quality Audit",
            "top_event": "Insufficient fastener torque leading to in-flight control-surface failure.",
            "consequence": "Catastrophic — loss of control.",
            "recommended_action": "Increase torque-tool calibration frequency and quarantine suspect units.",
            "corrective_action_flag": True,
            "srm_flag": True,
            "priority": "H",
            "remarks": "Seeded engineering-control template.",
        },
        {
            "title": "Counterfeit / unapproved part in stores inventory",
            "description": "Documentation anomaly identified on a batch of stored brake assemblies.",
            "threat": "Unapproved-part intrusion into the maintenance supply chain.",
            "taxonomy": "Organizational",
            "source": "Quality Audit",
            "top_event": "Installation of a non-conforming part on an airworthy aircraft.",
            "consequence": "Hazardous — component failure with airborne consequences.",
            "recommended_action": "Quarantine batch, verify traceability, and reinforce vendor vetting.",
            "corrective_action_flag": True,
            "srm_flag": False,
            "priority": "M",
            "remarks": "Seeded supply-chain integrity template.",
        },
    ],
    "CAB": [
        {
            "title": "Cabin crew communication breakdown during evacuation drill",
            "description": "Inconsistent PA hand-over during a scheduled training evacuation scenario.",
            "threat": "Ambiguous PA script and inter-crew hand-over at the door stations.",
            "taxonomy": "Human",
            "source": "Safety Inspection",
            "top_event": "Delayed or garbled evacuation command on an actual emergency.",
            "consequence": "Hazardous — evacuation delay with increased exposure to fire/smoke.",
            "recommended_action": "Standardise the PA hand-over script and run joint crew CRM training.",
            "corrective_action_flag": True,
            "srm_flag": False,
            "priority": "M",
            "remarks": "Seeded cabin-safety template.",
        },
    ],
    "GHD": [
        {
            "title": "GPU positioning creates wingtip collision exposure",
            "description": "Ground power unit repeatedly marshalled within the shadow of the adjacent aircraft wingtip.",
            "threat": "Crowded apron layout with insufficient wingtip clearances.",
            "taxonomy": "Environmental",
            "source": "Safety Inspection",
            "top_event": "Wingtip / GPU collision during push-back.",
            "consequence": "Significant — aircraft skin damage and potential fuel leak.",
            "recommended_action": "Re-mark ground equipment stands and enforce spill-proof marshalling zones.",
            "corrective_action_flag": True,
            "srm_flag": True,
            "priority": "M",
            "remarks": "Seeded ground-handling / apron template.",
        },
    ],
    "ENG": [
        {
            "title": "Hydraulic system low-pressure indication on rotate",
            "description": "Transient low-pressure warning presented on the number-two hydraulic system during mast rotation.",
            "threat": "Wear on the hydraulic pump drive coupling.",
            "taxonomy": "Technical",
            "source": "VSR",
            "top_event": "Degraded flight-control authority in the hydraulic system.",
            "consequence": "Hazardous — reduced controllability.",
            "recommended_action": "Inspect and replace pump coupling on scheduled maintenance opportunity.",
            "corrective_action_flag": True,
            "srm_flag": False,
            "priority": "M",
            "remarks": "Seeded engineering template.",
        },
    ],
    "DSP": [
        {
            "title": "Dispatch hand-over omission during night crew change",
            "description": "Night dispatch shift hand-over omitted an active NOTAM and a fuel restriction.",
            "threat": "Fatigue and abbreviated hand-over checklists at the night desk.",
            "taxonomy": "Human",
            "source": "Internal Audit",
            "top_event": "Dispatch of a flight with unresolved operational restriction.",
            "consequence": "Hazardous — fuel-exhaustion or NOTAM-related diversion risk.",
            "recommended_action": "Enforce structured dispatch hand-over checklist and fatigue rostering.",
            "corrective_action_flag": True,
            "srm_flag": False,
            "priority": "M",
            "remarks": "Seeded dispatch/operations-control template.",
        },
    ],
    "SEC": [
        {
            "title": "Perimeter access control gap at maintenance apron",
            "description": "Non-staff drivers transiting the maintenance apron without badge verification.",
            "threat": "Unaccompanied vehicles on the apron via a weakly controlled gate.",
            "taxonomy": "Organizational",
            "source": "Safety Inspection",
            "top_event": "Unauthorised person or vehicle reaching an aircraft zone.",
            "consequence": "Significant — sabotage or FOD exposure.",
            "recommended_action": "Upgrade gate access control and reinforce security patrols.",
            "corrective_action_flag": True,
            "srm_flag": False,
            "priority": "M",
            "remarks": "Seeded aviation-security template.",
        },
    ],
    "MED": [
        {
            "title": "Rapid decompression oxygen availability at flight levels",
            "description": "Cabin oxygen mask servicing interval exceeds recommended shelf life on a batch of seats.",
            "threat": "Oxygen mask service-life expiry.",
            "taxonomy": "Technical",
            "source": "Quality Audit",
            "top_event": "Mask failure during rapid decompression descent.",
            "consequence": "Hazardous — crew/passenger incapacitation.",
            "recommended_action": "Immediate mask servicing and cabin-EMS compliance audit.",
            "corrective_action_flag": True,
            "srm_flag": False,
            "priority": "H",
            "remarks": "Seeded aeromedical template.",
        },
    ],
    "TRN": [
        {
            "title": "Simulator fidelity gap on terrain-authority training",
            "description": "Trainee instructors report visual terrain resolution below real-world context in the recurrent module.",
            "threat": "Reduced scenario fidelity limiting crew exposure realism.",
            "taxonomy": "Organizational",
            "source": "Internal Audit",
            "top_event": "Untrained/unprepared crew response to a terrain threat.",
            "consequence": "Hazardous — degraded crew performance in a real event.",
            "recommended_action": "Upgrade simulator visuals and add terrain-awareness drills.",
            "corrective_action_flag": False,
            "srm_flag": False,
            "priority": "L",
            "remarks": "Seeded training template.",
        },
    ],
    "ADM": [
        {
            "title": "Employee fatigue record-keeping gaps",
            "description": "Fatigue report workflow leaves duty-limit notifications incomplete for admin postholders.",
            "threat": "Incomplete duty-time tracking in the administrative workforce.",
            "taxonomy": "Organizational",
            "source": "Internal Audit",
            "top_event": "Fatigued administrative staff making scheduling errors.",
            "consequence": "Minor — documentation error with indirect safety effect.",
            "recommended_action": "Automate duty-time reminders and management oversight.",
            "corrective_action_flag": False,
            "srm_flag": False,
            "priority": "L",
            "remarks": "Seeded administration template.",
        },
    ],
    "ENV": [
        {
            "title": "Bird activity intensification on approach corridor",
            "description": "Monitoring recorded increased flocking on the northern approach during monsoon.",
            "threat": "Seasonal shift in bird activity across the approach corridor.",
            "taxonomy": "Environmental",
            "source": "VSR",
            "top_event": "Bird strike through the windscreen or into an engine.",
            "consequence": "Hazardous — engine or windshield impact.",
            "recommended_action": "Coordinate wildlife habitat management with the aerodrome.",
            "corrective_action_flag": True,
            "srm_flag": True,
            "priority": "M",
            "remarks": "Seeded environmental / wildlife template.",
        },
        {
            "title": "Standing water on runway during monsoon",
            "description": "Aquaplaning risk noted on the primary runway after heavy monsoon rain.",
            "threat": "Runway surface drainage failure during sustained rainfall.",
            "taxonomy": "Environmental",
            "source": "Flight Diversion",
            "top_event": "Hydroplaning and reduced braking capability on landing.",
            "consequence": "Hazardous — runway excursion.",
            "recommended_action": "Improve runway grooving/drainage and update aquaplaning SOPs.",
            "corrective_action_flag": True,
            "srm_flag": True,
            "priority": "M",
            "remarks": "Seeded monsoon-operations template.",
        },
    ],
    "HUM": [
        {
            "title": "Fatigue exposure on consecutive night duties",
            "description": "Crew routing logs show consecutive late-evening sectors exceeding fatigue thresholds.",
            "threat": "Roster design producing cumulative duty-time exposure.",
            "taxonomy": "Human",
            "source": "MOR",
            "top_event": "Crew fatigue leading to operational error.",
            "consequence": "Hazardous — error with airborne consequence.",
            "recommended_action": "Re-baseline fatiguerostering and activate fatigue SMS alerts.",
            "corrective_action_flag": True,
            "srm_flag": True,
            "priority": "H",
            "remarks": "Seeded human-factors template.",
        },
    ],
    "ORG": [
        {
            "title": "SMS documentation version control drift",
            "description": "Two competing revisions of the safety manual were found in circulation across departments.",
            "threat": "Distributed documentation with no central version control.",
            "taxonomy": "Organizational",
            "source": "Quality Audit",
            "top_event": "Crew and ground staff acting on an obsolete procedure.",
            "consequence": "Significant — procedural error with safety margin reduction.",
            "recommended_action": "Consolidate document control under the safety manager.",
            "corrective_action_flag": True,
            "srm_flag": False,
            "priority": "M",
            "remarks": "Seeded organizational-documentation template.",
        },
    ],
    "SAF": [
        {
            "title": "Cross-department hazard reporting latency",
            "description": "Voluntary reports from ramp staff routinely exceed the 72-hour submission window.",
            "threat": "Reporting channels not visible to frontline ramp staff.",
            "taxonomy": "Organizational",
            "source": "Safety Survey",
            "top_event": "Hazard feedback loop delayed, reducing prevention effectiveness.",
            "consequence": "Minor — bounded prevention delay.",
            "recommended_action": "Publicise reporting channels and recognise reporter participation.",
            "corrective_action_flag": False,
            "srm_flag": False,
            "priority": "L",
            "remarks": "Seeded safety-promotion template.",
        },
    ],
}

# Function codes guaranteed to have at least one template (seeder fallback).
FUNCTION_ORDER = sorted(HAZARD_TEMPLATES.keys())


def all_templates() -> list:
    """Flattened list of every template (deterministic order)."""
    return [t for fn in FUNCTION_ORDER for t in HAZARD_TEMPLATES[fn]]


def templates_for_function(function: str) -> list:
    """Return the templates for a function code, defaulting to GEN/OPS-safe set."""
    fn = (function or "OPS").upper()
    if fn in HAZARD_TEMPLATES:
        return HAZARD_TEMPLATES[fn]
    return HAZARD_TEMPLATES["OPS"]


def stamp_dates(template: dict, when: datetime = None) -> dict:
    """Return a template copy with priority_date / status_date stamped."""
    when = when or datetime.now(timezone.utc)
    doc = dict(template)
    doc["priority_date"] = when
    doc["status_date"] = when
    return doc