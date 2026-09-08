# ==============================================================================
# File: backend/app/services/severity_service.py
# Description: Automatic severity assignment for VSR / MOR reports based on the
#              ICAO ADREP occurrence category selected by the reporter. The
#              reporter is no longer asked to self-rate severity — the system
#              derives it from the occurrence category before the report is
#              persisted, so dashboard KPIs and the risk matrix always have a
#              meaningful value.
# ==============================================================================

from typing import Dict, Optional

# ICAO ADREP occurrence category -> 1-5 ICAO severity level.
#
# The category codes are the application's ECCAIRS-aligned vocabulary defined in
# app/models/report.py (_OCCURRENCE_CATEGORIES):
#   ARC, MAC, BIRD, CABIN, CFIT, ENG, FIRE, GCOL, LOCI, PRO, RE, RI, SYS, WX, OTHER
#
# Mapping rationale (per user directive):
#   - Fatal / loss-of-control events        -> 5 Critical
#       CFIT, LOCI, MAC
#   - Powerplant/system failures & birdstrikes -> 4 High
#       ENG (covers SCF-PP/F-NI/FUEL), SYS (covers SCF-NP), BIRD, RE, RI
#   - Weather, ground collision, everything else -> 3 Medium
#       WX, GCOL, OTHER, FIRE, CABIN, ARC, PRO
_UNSET = object()


_SEVERITY_BY_ICAO: Dict[str, int] = {
    "CFIT": 5,
    "LOCI": 5,
    "MAC": 5,
    "ENG": 4,
    "SYS": 4,
    "BIRD": 4,
    "RE": 4,
    "RI": 4,
    "WX": 3,
    "GCOL": 3,
    "FIRE": 3,
    "CABIN": 3,
    "ARC": 3,
    "PRO": 3,
    "OTHER": 3,
}

# Default severity when the category is missing or unknown (ICAO-aligned "Major").
DEFAULT_SEVERITY_LEVEL = 3

# 1-5 ICAO level -> dashboard label. Mirrors the seeder mapping in
# admin_data_service._SEVERITY_STRING_BY_LEVEL so KPI/risk charts render.
LEVEL_TO_LABEL: Dict[int, str] = {
    1: "Low",
    2: "Low",
    3: "Medium",
    4: "High",
    5: "Critical",
}


def severity_for_category(category: Optional[str]) -> int:
    """Return the 1-5 ICAO severity level for an ICAO ADREP occurrence category."""
    if not category:
        return DEFAULT_SEVERITY_LEVEL
    return _SEVERITY_BY_ICAO.get(category.upper(), DEFAULT_SEVERITY_LEVEL)


def severity_label_for_category(category: Optional[str]) -> str:
    """Return the dashboard label for an ICAO ADREP occurrence category."""
    return LEVEL_TO_LABEL[severity_for_category(category)]


def apply_auto_severity(payload: dict) -> dict:
    """Assign severity_level + severity label to a report payload from its
    occurrence_category. Any value previously supplied by the client is
    overridden — reporter self-rating is intentionally not trusted."""
    category = payload.get("occurrence_category")
    level = severity_for_category(category)
    label = LEVEL_TO_LABEL[level]
    payload["severity_level"] = level
    payload["severity"] = label
    return payload