from typing import Optional, Dict, Any
from loguru import logger

from app.core.config import settings
from app.firebase import get_db, get_tenant_collection

RISK_MATRIX_DOC_PATH = "risk_matrix"

SEVERITY_LABELS_DEFAULT = {
    "1": "Negligible",
    "2": "Minor",
    "3": "Major",
    "4": "Hazardous",
    "5": "Catastrophic",
}

PROBABILITY_LABELS_DEFAULT = {
    "1": "Extremely Improbable",
    "2": "Improbable",
    "3": "Remote",
    "4": "Occasional",
    "5": "Frequent",
}

RISK_LEVEL_LABELS_DEFAULT = {
    "Low": "Low (Acceptable)",
    "High": "High (Tolerable)",
    "Very High": "Very High (Intolerable – Immediate Action)",
}

RISK_LEVEL_COLORS_DEFAULT = {
    "Low": "#4CAF50",
    "High": "#FF9800",
    "Very High": "#F44336",
}

# THRESHOLDS_DEFAULT keeps medium_max for backward compatibility with stored
# tenant configs, but classification is now 3-tier (low_max / high_max only):
#   <= low_max  -> LOW     (Acceptable, Level II, green)
#   <= high_max -> HIGH    (Tolerable,  Level III, amber/orange)
#   >  high_max -> VERY HIGH (Intolerable, Level IV, red)
THRESHOLDS_DEFAULT = {
    "low_max": 5,
    "medium_max": 9,
    "high_max": 15,
}

# CAAN CAR-19 aligned 3-tier tolerability classification. Legacy "Medium"/
# "Moderate" labels are folded into the HIGH tier (Level III).
TOLERABILITY_TIERS = {
    "LOW": {
        "level": "Level II",
        "label": "Low (Acceptable)",
        "color": "#4CAF50",
        "outcome": "Acceptable",
        "signoff": "Routine Monitoring",
    },
    "HIGH": {
        "level": "Level III",
        "label": "High (Tolerable)",
        "color": "#FF9800",
        "outcome": "Tolerable",
        "signoff": "Formal Mitigation & HOD Sign-off",
    },
    "VERY HIGH": {
        "level": "Level IV",
        "label": "Very High (Intolerable)",
        "color": "#F44336",
        "outcome": "Intolerable",
        "signoff": "Mandatory Cease / Accountable Executive Sign-off",
    },
}

TIER_TO_OUTCOME = {tier: cfg["outcome"] for tier, cfg in TOLERABILITY_TIERS.items()}


def _default_matrix_config() -> dict:
    return {
        "version": "1.0",
        "severity_labels": dict(SEVERITY_LABELS_DEFAULT),
        "probability_labels": dict(PROBABILITY_LABELS_DEFAULT),
        "thresholds": dict(THRESHOLDS_DEFAULT),
        "risk_level_labels": dict(RISK_LEVEL_LABELS_DEFAULT),
        "risk_level_colors": dict(RISK_LEVEL_COLORS_DEFAULT),
    }


def compute_risk_index(severity: int, probability: int) -> int:
    return severity * probability


def get_risk_level(risk_index: int, thresholds: Optional[dict] = None) -> str:
    if not thresholds:
        thresholds = THRESHOLDS_DEFAULT
    if risk_index <= thresholds["low_max"]:
        return "Low"
    elif risk_index <= thresholds["high_max"]:
        return "High"
    else:
        return "Very High"


def get_tolerability_tier(risk_index: int, thresholds: Optional[dict] = None) -> str:
    """Return the uppercase tolerability tier (LOW / HIGH / VERY HIGH) for a
    risk index under the CAAN CAR-19 3-tier scheme."""
    if not thresholds:
        thresholds = THRESHOLDS_DEFAULT
    if risk_index <= thresholds["low_max"]:
        return "LOW"
    elif risk_index <= thresholds["high_max"]:
        return "HIGH"
    else:
        return "VERY HIGH"


def normalize_tolerability(label: Optional[str]) -> str:
    """Normalise any legacy risk label/outcome into the 3-tier tolerance tier.

    Low / Acceptable -> LOW; Very High / Critical / Intolerable -> VERY HIGH;
    Medium / Moderate / High / Tolerable / unknown -> HIGH.
    """
    if not label:
        return "HIGH"
    norm = str(label).strip().upper()
    if norm in ("LOW", "ACCEPTABLE"):
        return "LOW"
    if norm in ("VERY HIGH", "CRITICAL", "INTOLERABLE", "SEVERE"):
        return "VERY HIGH"
    return "HIGH"


def classify_tolerability(risk_index: int, thresholds: Optional[dict] = None) -> dict:
    """Full 3-tier classification payload for a risk index."""
    tier = get_tolerability_tier(risk_index, thresholds)
    cfg = dict(TOLERABILITY_TIERS[tier])
    cfg["tier"] = tier
    cfg["risk_level"] = get_risk_level(risk_index, thresholds)
    cfg["risk_index"] = risk_index
    return cfg


def risk_outcome_by_index(risk_index: int, thresholds: Optional[dict] = None) -> str:
    """Outcome (Acceptable / Tolerable / Intolerable) from a risk index only."""
    return TIER_TO_OUTCOME[get_tolerability_tier(risk_index, thresholds)]


def get_risk_matrix_config(tenant_id: str) -> dict:
    try:
        doc_ref = (
            get_tenant_collection(tenant_id, settings.FIREBASE_COLLECTION_METADATA)
            .document(RISK_MATRIX_DOC_PATH)
        )
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
    except Exception as e:
        logger.warning(f"Failed to load risk matrix for {tenant_id}: {e}")

    return _default_matrix_config()


def set_risk_matrix_config(tenant_id: str, config: dict, updated_by: str) -> dict:
    from datetime import datetime, timezone

    base = get_risk_matrix_config(tenant_id)
    base.update(config)
    base["updated_by"] = updated_by
    base["updated_at"] = datetime.now(timezone.utc)

    doc_ref = (
        get_tenant_collection(tenant_id, settings.FIREBASE_COLLECTION_METADATA)
        .document(RISK_MATRIX_DOC_PATH)
    )
    doc_ref.set(base)
    return base


def get_thresholds(tenant_id: str) -> dict:
    """Return the effective risk-matrix thresholds for a tenant.

    Falls back to the platform defaults when no stored config exists, when the
    stored config carries no thresholds, or when the lookup fails.
    """
    try:
        config = get_risk_matrix_config(tenant_id)
    except Exception as e:
        logger.warning(f"Failed to load risk matrix for {tenant_id}: {e}")
        return dict(THRESHOLDS_DEFAULT)
    return config.get("thresholds") or dict(THRESHOLDS_DEFAULT)


def classify_risk(risk_index: int, thresholds: Optional[dict] = None) -> str:
    return get_risk_level(risk_index, thresholds)


def risk_outcome(severity: int, probability: int, thresholds: Optional[dict] = None) -> str:
    risk_index = compute_risk_index(severity, probability)
    return risk_outcome_by_index(risk_index, thresholds)
