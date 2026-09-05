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

SEVERITY_TO_VALUE: Dict[str, int] = {
    "A": 1,  # Negligible
    "B": 2,  # Minor
    "C": 3,  # Major
    "D": 4,  # Hazardous
    "E": 5,  # Catastrophic
}

VALUE_TO_SEVERITY: Dict[int, str] = {v: k for k, v in SEVERITY_TO_VALUE.items()}

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

BSV_TOTAL_WEIGHT: int = sum(BSV_ELEMENT_WEIGHTS.values())  # 10


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
    """Build the risk index string, e.g. '4C' (probability 4, severity C)."""
    prob = normalize_probability(probability)
    sev = normalize_severity(severity)
    return f"{prob}{VALUE_TO_SEVERITY[sev]}"


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

    Returns the parsed cell with index string, tolerability and colour, e.g.
    probability 4, severity C -> '4C' / 'Tolerable' / 'yellow'.
    """
    prob = normalize_probability(probability)
    sev_value = normalize_severity(severity)
    sev_letter = VALUE_TO_SEVERITY[sev_value]
    index = f"{prob}{sev_letter}"
    tolerability = get_tolerability(index)
    return {
        "probability": prob,
        "severity": sev_letter,
        "severity_value": sev_value,
        "risk_index": index,
        "tolerability": tolerability,
        "color": get_color(tolerability),
    }


def get_tolerability(risk_index: Union[str, int]) -> str:
    """Tolerability level for a risk matrix cell, e.g. '4C' -> 'Tolerable'.

    Numeric indices are rejected: the SRAM register stores probability/severity
    pairs as strings (e.g. '4C') rather than legacy product indices. Convert
    legacy product indices to (probability, severity) before calling.
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
    """Materialise the full 5x5 matrix as probability-major rows of cells."""
    rows: List[Dict[str, Any]] = []
    for probability in range(1, 6):
        cells: List[Dict[str, Any]] = []
        for sev_value in range(1, 6):
            sev_letter = VALUE_TO_SEVERITY[sev_value]
            index = f"{probability}{sev_letter}"
            tolerability = get_tolerability(index)
            cells.append({
                "probability": probability,
                "severity": sev_letter,
                "severity_value": sev_value,
                "risk_index": index,
                "tolerability": tolerability,
                "color": get_color(tolerability),
            })
        rows.append({"probability": probability, "cells": cells})
    return rows


# ----------------------------------------------------------------------------
# Barrier Strength Value (BSV)
# ----------------------------------------------------------------------------

def calculate_bsv(barrier_scores: Any) -> Dict[str, Any]:
    """Barrier Strength Value on a 1-5 scale from the 7 element scores.

    ``barrier_scores`` is either a dict keyed by element name (only the 7
    BSW elements are read) or an iterable of 7 numeric scores in the
    documented order.

    Weighted total = sum(score * weight); BSV = clamp(total / 10, 1, 5),
    rounded to one decimal place.
    """
    if isinstance(barrier_scores, dict):
        scores: Dict[str, int] = {}
        for element, weight in BSV_ELEMENT_WEIGHTS.items():
            if element not in barrier_scores or barrier_scores.get(element) is None:
                raise ValueError(f"Missing barrier element score: {element}")
            score = barrier_scores[element]
            scores[element] = _validate_score(score, element)
    else:
        items = list(barrier_scores or [])
        if len(items) != len(BSV_ELEMENT_WEIGHTS):
            raise ValueError(
                f"Expected {len(BSV_ELEMENT_WEIGHTS)} barrier element scores, "
                f"got {len(items)}"
            )
        element_names = list(BSV_ELEMENT_WEIGHTS.keys())
        scores = {
            element_names[i]: _validate_score(items[i], element_names[i])
            for i in range(len(items))
        }

    weighted_total = sum(
        scores[element] * weight for element, weight in BSV_ELEMENT_WEIGHTS.items()
    )
    bsv = max(1.0, min(5.0, round(weighted_total / BSV_TOTAL_WEIGHT, 1)))
    return {
        "bsv": bsv,
        "weighted_total": weighted_total,
        "total_weight": BSV_TOTAL_WEIGHT,
        "max_bsv": 5,
        "correlation": _bsv_tier(bsv),
        "scores": scores,
    }


def _validate_score(value: Any, element: str) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{element} score must be an integer 1-5, got {value!r}")
    if not 1 <= score <= 5:
        raise ValueError(f"{element} score must be between 1 and 5, got {score}")
    return score


def _bsv_tier(bsv: float) -> str:
    if bsv >= 4.8:
        return "Strong"
    if bsv >= 4.0:
        return "Satisfactory"
    if bsv >= 3.0:
        return "Moderate"
    if bsv >= 2.0:
        return "Weak"
    return "Very Weak"