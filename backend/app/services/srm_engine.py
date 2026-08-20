# ============================================================================
# FILE: srm_engine.py
# PATH: backend/app/services/srm_engine.py
# PURPOSE: CAAN CAR-19 Safety Risk Management (SRM) mathematical engine.
#
# Implements the algorithmic calculations defined in the CAAN SRM Procedure
# Manual (2026):
#   - 7-Impact Severity scoring (Weighted Score 0-65, letter A-E)
#   - Barrier Quality Value (BQV) -> Barrier Score Value (BSV) with the
#     Excellent..Ineffective robustness scale
#   - Probability classification from a (severity, barrier score) pair using
#     the severity-dependent Occurrence-Number-of-Barriers (ONB) bands
#   - Full Risk Profile evaluation (Existing vs Consolidated BSV) producing the
#     before/after risk index ("4D" -> "1D"), tolerability and the required
#     sign-off authority.
#
# AUTHOR: AviaSAFE Systems
# ============================================================================

from typing import Any, Dict, List, Sequence, Tuple


# ── Severity scoring (7 impacts, weighted) ──────────────────────────────────

SEVERITY_FACTORS = {
    "pax": 4,
    "worker": 3,
    "quality": 2,
    "asset": 1,
    "rep": 1,
    "sec": 1,
    "env": 1,
}

# [(lower, upper, letter, descriptor)]  — contiguous, covers 0..65.
SEVERITY_BANDS: List[Tuple[int, int, str, str]] = [
    (52, 65, "A", "Catastrophic"),
    (39, 51, "B", "Major"),
    (26, 38, "C", "Moderate"),
    (13, 25, "D", "Minor"),
    (0, 12, "E", "Insignificant"),
]

# ── Barrier Quality Value (BQV) -> Barrier Score Value (BSV) ────────────────

BQV_FACTORS = {
    "effectiveness": 3,
    "cost_benefit": 1,
    "practicality": 1,
    "acceptability": 1,
    "enforceability": 1,
    "durability": 1,
    "disinclination": 2,
}

# [(lower, upper, bsv, robustness)]
BQV_BANDS: List[Tuple[int, int, int, str]] = [
    (42, 50, 5, "Excellent"),
    (34, 41, 4, "Very Good"),
    (26, 33, 3, "Good"),
    (18, 25, 2, "Fair"),
    (10, 17, 1, "Poor"),
    (0, 9, 0, "Ineffective"),
]

# ── Probability bands (severity-dependent ONB / maximum) ────────────────────

PROBABILITY_DESCRIPTORS = {
    5: "Certain",
    4: "Likely",
    3: "Remote",
    2: "Improbable",
    1: "Extremely Improbable",
}

# {severity_letter: (onb, max_value, [(lo, hi, probability_value)])}
PROBABILITY_CONFIG: Dict[str, Tuple[int, int, List[Tuple[int, int, int]]]] = {
    "A": (8, 40, [(0, 7, 5), (8, 15, 4), (16, 23, 3), (24, 31, 2), (32, 40, 1)]),
    "B": (6, 30, [(0, 5, 5), (6, 11, 4), (12, 17, 3), (18, 23, 2), (24, 30, 1)]),
    "C": (4, 20, [(0, 3, 5), (4, 7, 4), (8, 11, 3), (12, 15, 2), (16, 20, 1)]),
    "D": (3, 15, [(0, 2, 5), (3, 5, 4), (6, 8, 3), (9, 11, 2), (12, 15, 1)]),
    "E": (2, 10, [(0, 1, 5), (2, 3, 4), (4, 5, 3), (6, 7, 2), (8, 10, 1)]),
}

# ── Risk tolerability matrix (probability_value x severity_letter) ───────────

TOLERABILITY_MATRIX: Dict[str, str] = {
    "5A": "Intolerable", "5B": "Intolerable", "5C": "Intolerable",
    "5D": "Tolerable", "5E": "Tolerable",
    "4A": "Intolerable", "4B": "Intolerable",
    "4C": "Tolerable", "4D": "Tolerable", "4E": "Tolerable",
    "3A": "Intolerable",
    "3B": "Tolerable", "3C": "Tolerable", "3D": "Tolerable",
    "3E": "Acceptable",
    "2A": "Tolerable", "2B": "Tolerable", "2C": "Tolerable",
    "2D": "Acceptable", "2E": "Acceptable",
    "1A": "Tolerable",
    "1B": "Acceptable", "1C": "Acceptable", "1D": "Acceptable", "1E": "Acceptable",
}

SIGNOFF_AUTHORITY = {
    "Intolerable": "Accountable Manager",
    "Tolerable": "Risk Owner / Functional Chief",
    "Acceptable": "Safety Manager / SAG Member",
}

# Map SRAM tolerability outcomes to the 3-tier CAAN CAR-19 tolerance tiers so
# the SRAM engine aligns with the operator risk matrix (Level II/III/IV).
TOLERABILITY_TO_TIER = {
    "Acceptable": "LOW",
    "Tolerable": "HIGH",
    "Intolerable": "VERY HIGH",
}

SEVERITY_LETTER_TO_NUMERIC = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1}


def tolerability_tier(tolerability: str) -> str:
    """Return the 3-tier tolerance tier for an SRAM tolerability outcome."""
    return TOLERABILITY_TO_TIER.get(tolerability, "HIGH")


def _lookup_band(value: int, bands: Sequence[Tuple[int, int, Any, Any]]) -> Tuple[Any, Any]:
    """Return (second_value, third_value) for the band containing `value`."""
    for lower, upper, primary, secondary in bands:
        if lower <= value <= upper:
            return primary, secondary
    # Fall back to the most severe band (callers clamp inputs first).
    return bands[0][2], bands[0][3]


def _tolerability(probability_value: int, severity_letter: str) -> str:
    return TOLERABILITY_MATRIX.get(
        f"{probability_value}{severity_letter}", "Acceptable"
    )


def calculate_severity(
    pax: int,
    worker: int,
    quality: int,
    asset: int,
    rep: int,
    sec: int,
    env: int,
) -> dict:
    """Weighted 7-impact severity score -> letter + descriptor.

    Weighted Score = (4*pax) + (3*worker) + (2*quality) + asset + rep + sec + env
    (Range 0-65). Mapping: >=52 A Catastrophic; 39-51 B Major; 26-38 C Moderate;
    13-25 D Minor; 0-12 E Insignificant.
    """
    score = (
        (4 * pax) + (3 * worker) + (2 * quality) + asset + rep + sec + env
    )
    letter, descriptor = _lookup_band(score, SEVERITY_BANDS)
    return {
        "total_score": score,
        "severity_letter": letter,
        "descriptor": descriptor,
    }


def calculate_bqv(
    effectiveness: int,
    cost_benefit: int,
    practicality: int,
    acceptability: int,
    enforceability: int,
    durability: int,
    disinclination: int,
) -> dict:
    """Barrier Quality Value (BQV) -> Barrier Score Value (BSV).

    Total BQV = (3*effectiveness) + cost_benefit + practicality + acceptability
    + enforceability + durability + (2*disinclination) (Range 10-50).
    BSV mapping: 42-50:5 Excellent; 34-41:4 Very Good; 26-33:3 Good; 18-25:2
    Fair; 10-17:1 Poor; 0-9:0 Ineffective.
    """
    bqv = (
        (3 * effectiveness)
        + cost_benefit
        + practicality
        + acceptability
        + enforceability
        + durability
        + (2 * disinclination)
    )
    bsv, robustness = _lookup_band(bqv, BQV_BANDS)
    return {"bqv": bqv, "bsv": bsv, "robustness": robustness}


def calculate_probability(severity: str, cbsv: int) -> dict:
    """Classify probability from a (severity letter, barrier score) pair.

    The consolidated barrier score value (cbsv) is banded against the
    severity-specific ONB table. Values above the severity maximum clamp to
    probability 1; values below zero clamp to probability 5.
    """
    sev = (severity or "E").upper()
    if sev not in PROBABILITY_CONFIG:
        sev = "E"
    _onb, max_value, bands = PROBABILITY_CONFIG[sev]
    value = max(0, min(int(cbsv or 0), max_value))
    probability_value = 5
    for lower, upper, pv in bands:
        if lower <= value <= upper:
            probability_value = pv
            break
    return {
        "probability_value": probability_value,
        "descriptor": PROBABILITY_DESCRIPTORS[probability_value],
    }


def _barrier_bsv(barrier: Any) -> int:
    """Extract a barrier's score value regardless of dict/model shape."""
    if barrier is None:
        return 0
    if isinstance(barrier, dict):
        return int(barrier.get("bsv") or 0)
    return int(getattr(barrier, "bsv", 0) or 0)


def evaluate_barrier(barrier: dict) -> dict:
    """Compute BQV/BSV for a single barrier carrying a quality assessment.

    Mutates and returns the barrier dict, always leaving it with a numeric
    `bsv` (computed from `quality` when present, otherwise the provided value).
    """
    barrier = dict(barrier or {})
    quality = barrier.get("quality")
    if isinstance(quality, dict):
        result = calculate_bqv(
            effectiveness=int(quality.get("effectiveness", 1)),
            cost_benefit=int(quality.get("cost_benefit", 1)),
            practicality=int(quality.get("practicality", 1)),
            acceptability=int(quality.get("acceptability", 1)),
            enforceability=int(quality.get("enforceability", 1)),
            durability=int(quality.get("durability", 1)),
            disinclination=int(quality.get("disinclination", 1)),
        )
        barrier["bqv"] = result["bqv"]
        barrier["bsv"] = result["bsv"]
        barrier["robustness"] = result["robustness"]
    else:
        barrier.setdefault("bqv", None)
        barrier["bsv"] = int(barrier.get("bsv") or 0)
    return barrier


def evaluate_barriers(
    ecb: Sequence[Any],
    erb: Sequence[Any],
    ncb: Sequence[Any],
    nrb: Sequence[Any],
) -> Dict[str, List[dict]]:
    """Normalise all four barrier sets, computing BQV/BSV where quality exists."""
    return {
        "ecb": [evaluate_barrier(b) for b in (ecb or [])],
        "erb": [evaluate_barrier(b) for b in (erb or [])],
        "ncb": [evaluate_barrier(b) for b in (ncb or [])],
        "nrb": [evaluate_barrier(b) for b in (nrb or [])],
    }


def evaluate_risk_profile(
    severity_data: dict,
    ecb_barriers: Sequence[Any],
    erb_barriers: Sequence[Any],
    ncb_barriers: Sequence[Any],
    nrb_barriers: Sequence[Any],
) -> dict:
    """Evaluate the before/after risk profile and required sign-off authority.

    Existing BSV = sum(ecb.bsv) + sum(erb.bsv)
    Consolidated BSV (CBSV) = Existing BSV + sum(ncb.bsv) + sum(nrb.bsv)

    Initial risk = band Existing BSV against the severity; resultant risk = band
    CBSV. Sign-off authority follows the resultant-risk tolerability:
      Intolerable -> Accountable Manager
      Tolerable   -> Risk Owner / Functional Chief
      Acceptable  -> Safety Manager / SAG Member
    """
    existing_bsv = sum(_barrier_bsv(b) for b in (ecb_barriers or [])) + sum(
        _barrier_bsv(b) for b in (erb_barriers or [])
    )
    consolidated_bsv = existing_bsv + sum(_barrier_bsv(b) for b in (ncb_barriers or [])) + sum(
        _barrier_bsv(b) for b in (nrb_barriers or [])
    )

    letter = ((severity_data or {}).get("severity_letter") or "E").upper()
    if letter not in PROBABILITY_CONFIG:
        letter = "E"

    initial = calculate_probability(letter, existing_bsv)
    resultant = calculate_probability(letter, consolidated_bsv)

    initial_tol = _tolerability(initial["probability_value"], letter)
    resultant_tol = _tolerability(resultant["probability_value"], letter)

    return {
        "existing_bsv": existing_bsv,
        "consolidated_bsv": consolidated_bsv,
        "severity_letter": letter,
        "tier": tolerability_tier(resultant_tol),
        "initial_risk": {
            "index": f'{initial["probability_value"]}{letter}',
            "probability_value": initial["probability_value"],
            "descriptor": initial["descriptor"],
            "tolerability": initial_tol,
            "tier": tolerability_tier(initial_tol),
        },
        "resultant_risk": {
            "index": f'{resultant["probability_value"]}{letter}',
            "probability_value": resultant["probability_value"],
            "descriptor": resultant["descriptor"],
            "tolerability": resultant_tol,
            "tier": tolerability_tier(resultant_tol),
        },
        "signoff": {
            "authority": SIGNOFF_AUTHORITY[resultant_tol],
            "initial_authority": SIGNOFF_AUTHORITY[initial_tol],
            "resultant_authority": SIGNOFF_AUTHORITY[resultant_tol],
        },
    }


def analyse(
    severity_inputs: dict,
    ecb_barriers: Sequence[Any] = (),
    erb_barriers: Sequence[Any] = (),
    ncb_barriers: Sequence[Any] = (),
    nrb_barriers: Sequence[Any] = (),
) -> dict:
    """Full SRM analysis: severity + barrier scoring + risk profile in one call."""
    severity = calculate_severity(
        pax=int(severity_inputs.get("pax") or 0),
        worker=int(severity_inputs.get("worker") or 0),
        quality=int(severity_inputs.get("quality") or 0),
        asset=int(severity_inputs.get("asset") or 0),
        rep=int(severity_inputs.get("rep") or 0),
        sec=int(severity_inputs.get("sec") or 0),
        env=int(severity_inputs.get("env") or 0),
    )
    barriers = evaluate_barriers(ecb_barriers, erb_barriers, ncb_barriers, nrb_barriers)
    risk_profile = evaluate_risk_profile(
        severity,
        barriers["ecb"],
        barriers["erb"],
        barriers["ncb"],
        barriers["nrb"],
    )
    return {
        "severity": severity,
        "barriers": barriers,
        "risk_profile": risk_profile,
    }