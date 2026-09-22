# ============================================================================
# FILE: risk_calculator.py
# PATH: backend/app/services/risk_calculator.py
# PURPOSE: ICAO Annex 19 / Doc 9859 / CAAN Chapter 2.3 safety risk assessment
#          mathematics used by the SRAM module:
#
#            * 5x5 risk matrix (probability 1-5 x severity A-E)
#            * tolerability classification (Intolerable / Tolerable /
#              Acceptable) from the explicit cell grid (e.g. "4C")
#            * Barrier Strength Value (BSV) from 7 weighted elements
#
#          Pure functions - no I/O - so they are trivially unit testable.
# ============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Union

# ----------------------------------------------------------------------------
# Risk matrix vocabulary
# ----------------------------------------------------------------------------

SEVERITY_LETTERS: tuple = ("A", "B", "C", "D", "E")

# CAAN SRM Manual §2.3.6.4 — severity stored numerically (1-5). Letter labels
# A-E are a display convention rendered by the UI layer and never stored:
#   value | letter | descriptor
#    5    |   A    | Catastrophic
#    4    |   B    | Major / Hazardous
#    3    |   C    | Moderate / Major
#    2    |   D    | Minor
#    1    |   E    | Negligible / Insignificant
SEVERITY_TO_VALUE: Dict[str, int] = {
    "A": 5,  # Catastrophic
    "B": 4,  # Major / Hazardous
    "C": 3,  # Moderate / Major
    "D": 2,  # Minor
    "E": 1,  # Negligible / Insignificant
}

VALUE_TO_SEVERITY: Dict[int, str] = {v: k for k, v in SEVERITY_TO_VALUE.items()}

# CAAN audit reference: numeric severity -> letter and descriptor.
CAAN_SEVERITY_REFERENCE: Dict[int, Dict[str, str]] = {
    value: {"letter": VALUE_TO_SEVERITY[value], "descriptor": descriptor}
    for value, letter, descriptor in (
        (5, "A", "Catastrophic"),
        (4, "B", "Major / Hazardous"),
        (3, "C", "Moderate / Major"),
        (2, "D", "Minor"),
        (1, "E", "Negligible / Insignificant"),
    )
}

TOLERABILITY_INTOLERABLE = ("5A", "5B", "5C", "4A", "4B", "3A")
TOLERABILITY_TOLERABLE = (
    "5D", "5E", "4C", "4D", "4E", "3B", "3C", "3D", "2A", "2B", "2C", "1A"
)
TOLERABILITY_ACCEPTABLE = ("3E", "2D", "2E", "1B", "1C", "1D", "1E")

TOLERABILITY_COLORS = {
    "Intolerable": "red",
    "Tolerable": "yellow",
    "Acceptable": "green",
}

# ----------------------------------------------------------------------------
# Barrier Strength Value (BSV) weights - score each element 1-5
# ----------------------------------------------------------------------------

BSV_ELEMENT_WEIGHTS: Dict[str, int] = {
    "effectiveness": 3,
    "cost_benefit": 1,
    "practicality": 1,
    "acceptability": 1,
    "enforceability": 1,
    "durability": 1,
    "disinclination": 2,
}


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def normalize_severity(severity: Any) -> int:
    """Severity in letter (A-E) or numeric (1-5) form -> numeric value 1-5."""
    if isinstance(severity, int) and not isinstance(severity, bool):
        value = severity
    else:
        value = SEVERITY_TO_VALUE.get(str(severity).strip().upper())
        if value is None:
            raise ValueError(
                f"Severity must be a letter A-E or a value 1-5, got {severity!r}"
            )
    if not 1 <= value <= 5:
        raise ValueError(f"Severity must be between 1 and 5, got {severity!r}")
    return value


def normalize_probability(probability: Any) -> int:
    try:
        value = int(probability)
    except (TypeError, ValueError):
        raise ValueError(
            f"Probability must be an integer 1-5, got {probability!r}"
        )
    if not 1 <= value <= 5:
        raise ValueError(f"Probability must be between 1 and 5, got {value}")
    return value


def risk_index(probability: Any, severity: Any) -> str:
    """Build the risk index display string, e.g. '4C' (probability 4, severity C)."""
    prob = normalize_probability(probability)
    sev = normalize_severity(severity)
    return f"{prob}{VALUE_TO_SEVERITY[sev]}"


def severity_to_letter(severity: Any) -> str:
    """Numeric severity 1-5 -> display letter A-E (CAAN §2.3.6.4 mapping)."""
    return VALUE_TO_SEVERITY[normalize_severity(severity)]


def risk_index_to_display(severity: Any, probability: Any) -> str:
    """UI display form of the numeric risk index, e.g. severity 3, probability 4 -> '4C'."""
    return f"{normalize_probability(probability)}{severity_to_letter(severity)}"


def parse_risk_index(index: str) -> Dict[str, int]:
    """'4C' -> {'probability': 4, 'severity_value': 3, 'severity': 'C'}."""
    if not isinstance(index, str):
        raise ValueError(f"Risk index must be a string like '4C', got {index!r}")
    token = index.strip().upper()
    if len(token) != 2 or not token[0].isdigit() or token[1] not in SEVERITY_LETTERS:
        raise ValueError(f"Invalid risk index format {index!r} (expected e.g. '4C')")
    probability = int(token[0])
    severity = token[1]
    if not 1 <= probability <= 5:
        raise ValueError(f"Invalid probability in risk index {index!r}")
    return {
        "probability": probability,
        "severity": severity,
        "severity_value": SEVERITY_TO_VALUE[severity],
        "risk_index": token,
    }


# ----------------------------------------------------------------------------
# Core API
# ----------------------------------------------------------------------------

def get_risk_matrix(probability: Any, severity: Any) -> Dict[str, Any]:
    """Full risk matrix entry for a probability/severity pair.

    Returns numeric severity (1-5) and risk_index (severity × probability,
    1-25) per the corrected ICAO/CAAN numeric storage convention. Letter labels
    are available as ``severity_letter`` / ``risk_index_display`` for the UI
    layer (CAAN §2.3.6.4).
    """
    prob = normalize_probability(probability)
    sev_value = normalize_severity(severity)
    sev_letter = VALUE_TO_SEVERITY[sev_value]
    index_str = f"{prob}{sev_letter}"
    tolerability = get_tolerability(index_str)
    return {
        "probability": prob,
        "severity": sev_value,
        "severity_letter": sev_letter,
        "severity_value": sev_value,
        "risk_index": prob * sev_value,
        "risk_index_display": index_str,
        "tolerability": tolerability,
        "color": get_color(tolerability),
    }


def get_tolerability(risk_index: Union[str, int]) -> str:
    """Tolerability level for a risk matrix cell, e.g. '4C' -> 'Tolerable'.

    Numeric indices are rejected: classification runs on the display grid cell
    ('<probability><severity-letter>', e.g. '4C'). The SRAM register stores
    probability/severity numerically (1-5); convert to the display form with
    ``risk_index_to_display`` before calling.
    """
    if isinstance(risk_index, int) and not isinstance(risk_index, bool):
        raise ValueError(
            "SRAM risk indices are strings like '4C'; map legacy product "
            "indices to (probability, severity) before calling this"
        )
    token = parse_risk_index(risk_index)["risk_index"]
    if token in TOLERABILITY_INTOLERABLE:
        return "Intolerable"
    if token in TOLERABILITY_TOLERABLE:
        return "Tolerable"
    if token in TOLERABILITY_ACCEPTABLE:
        return "Acceptable"
    raise ValueError(f"Risk index {risk_index!r} does not map to any tolerability band")


def get_color(tolerability: str) -> str:
    """Conventional traffic-light colour for a tolerability level."""
    if not tolerability:
        raise ValueError("tolerability must not be empty")
    key = str(tolerability).strip().capitalize()
    if key == "Intolerable":
        return "red"
    if key == "Tolerable":
        return "yellow"
    if key == "Acceptable":
        return "green"
    if str(tolerability).strip().lower() in ("red", "yellow", "green"):
        return str(tolerability).strip().lower()
    raise ValueError(f"Unknown tolerability {tolerability!r}")


def build_risk_matrix() -> List[Dict[str, Any]]:
    """Materialise the full 5x5 matrix as probability-major rows of cells.

    Each cell carries numeric severity/risk_index (per the corrected storage
    contract) plus display-letter fields for the UI layer.
    """
    rows: List[Dict[str, Any]] = []
    for probability in range(1, 6):
        cells: List[Dict[str, Any]] = []
        for sev_value in range(1, 6):
            sev_letter = VALUE_TO_SEVERITY[sev_value]
            index_str = f"{probability}{sev_letter}"
            tolerability = get_tolerability(index_str)
            cells.append({
                "probability": probability,
                "severity": sev_value,
                "severity_letter": sev_letter,
                "severity_value": sev_value,
                "risk_index": probability * sev_value,
                "risk_index_display": index_str,
                "tolerability": tolerability,
                "color": get_color(tolerability),
            })
        rows.append({"probability": probability, "cells": cells})
    return rows


# ----------------------------------------------------------------------------
# Barrier Strength Value (BSV) — RETIRED (SN11 / P2-7)
# ----------------------------------------------------------------------------
# The continuous `calculate_bsv` model (weighted mean, 1 dp) was retired in
# Phase 2. The discrete CAAN Fig-b banded BSV from `srm_engine.calculate_bqv`
# is the single canonical BSV (0-5: Ineffective..Excellent). `BSV_ELEMENT_WEIGHTS`
# is retained as the canonical element-name/order registry used by sram_service.