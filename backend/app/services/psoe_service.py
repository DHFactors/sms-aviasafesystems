# ============================================================================
# FILE: psoe_service.py
# PATH: backend/app/services/psoe_service.py
# PURPOSE: Template loading and scoring for the PSOE Audit & Surveillance
#          module. Loads the CAAN SMS Procedure Manual Appendix 10 checklist
#          and computes component / overall scores using the CAAN/ICAO
#          0-3 implementation scale with N/A excluded from the denominator.
# ============================================================================

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from app.models.psoe import PSOEAnswer, PSOETemplate

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "data" / "psoe_appendix10.json"
TEMPLATE_VERSION = "1.0.0"

# Default template used when the seed file cannot be loaded (defensive).
_DEFAULT_TEMPLATE: Dict[str, Any] = {
    "version": TEMPLATE_VERSION,
    "source": "CAAN SMS Procedure Manual - Appendix 10 (ICAO Annex 19 aligned)",
    "scoring_scale": {
        "0": "Not Implemented / Non-Compliant",
        "1": "Partially Implemented (Documented only)",
        "2": "Implemented & Operational",
        "3": "Fully Effective & Continuous Improvement",
        "NA": "Not Applicable (excluded from denominator)",
    },
    "components": [
        {"id": "component_1", "name": "Safety Policy & Objectives", "key": "safety_policy", "weight": 10, "questions": []},
        {"id": "component_2", "name": "Safety Risk Management", "key": "safety_risk_management", "weight": 40, "questions": []},
        {"id": "component_3", "name": "Safety Assurance", "key": "safety_assurance", "weight": 30, "questions": []},
        {"id": "component_4", "name": "Safety Promotion", "key": "safety_promotion", "weight": 20, "questions": []},
    ],
}

SCORE_LABELS: Dict[str, str] = {
    "0": "Not Implemented / Non-Compliant",
    "1": "Partially Implemented (Documented only)",
    "2": "Implemented & Operational",
    "3": "Fully Effective & Continuous Improvement",
    "NA": "Not Applicable (excluded from denominator)",
}

_LOADED_TEMPLATE: Optional[PSOETemplate] = None


def _raw_template() -> Dict[str, Any]:
    """Read the Appendix 10 seed file, falling back to the default shell."""
    try:
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("components"):
            return data
        logger.warning("PSOE template file has no components; using default shell")
        return _DEFAULT_TEMPLATE
    except FileNotFoundError:
        logger.warning(f"PSOE template file not found at {TEMPLATE_PATH}; using default shell")
        return _DEFAULT_TEMPLATE
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"PSOE template file unreadable: {e}; using default shell")
        return _DEFAULT_TEMPLATE


def load_template() -> PSOETemplate:
    """Load and validate the Appendix 10 template (cached after first call).

    The template is parsed through the Pydantic model so a malformed seed
    file fails loudly during development rather than at request time.
    """
    global _LOADED_TEMPLATE
    if _LOADED_TEMPLATE is not None:
        return _LOADED_TEMPLATE
    raw = _raw_template()
    # Stamp the owning component onto each question so consumers can group
    # answers without re-deriving it from the category.
    for comp in raw.get("components", []):
        for q in comp.get("questions", []):
            q.setdefault("component", comp.get("id"))
    _LOADED_TEMPLATE = PSOETemplate.model_validate(raw)
    return _LOADED_TEMPLATE


def reset_template_cache() -> None:
    """Drop the cached template (used by tests / reloads)."""
    global _LOADED_TEMPLATE
    _LOADED_TEMPLATE = None


def _is_applicable(answer: PSOEAnswer) -> bool:
    return not answer.is_na and answer.score is not None


def compute_component_scores(
    responses: List[PSOEAnswer], template: Optional[PSOETemplate] = None
) -> Dict[str, Dict[str, Any]]:
    """Compute per-component scores from a list of answers.

    For each component the applicable answers (non-N/A) are scored against
    their maximum (``max_score`` x question count) to give a percentage.
    N/A answers are excluded from the denominator entirely.
    """
    template = template or load_template()
    by_question = template.question_map()
    scores: Dict[str, Dict[str, Any]] = {}
    for comp in template.components:
        q_ids = {q.id for q in comp.questions}
        applicable = [a for a in responses if a.question_id in q_ids and _is_applicable(a)]
        total = sum(a.score or 0 for a in applicable)
        max_total = sum(by_question[qid].max_score for qid in q_ids if qid in by_question)
        max_total = min(max_total, 3 * len(applicable)) if applicable else 0
        pct = round((total / max_total * 100), 2) if applicable and max_total else 0.0
        scores[comp.id] = {
            "component": comp.id,
            "name": comp.name,
            "weight": comp.weight,
            "applicable_questions": len(applicable),
            "na_questions": sum(1 for a in responses if a.question_id in q_ids and not _is_applicable(a)),
            "score": total,
            "max_score": max_total,
            "score_pct": pct,
            "weighted_pct": round(pct * comp.weight / 100, 2),
        }
    return scores


def compute_overall(component_scores: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Combine per-component scores into an overall weighted percentage."""
    total_weight = sum(c["weight"] for c in component_scores.values()) or 100
    overall = round(
        sum(c["weighted_pct"] for c in component_scores.values()) / total_weight * 100, 2
    )
    return {
        "component_scores": component_scores,
        "overall_score_pct": overall,
        "overall_level": overall_level(overall),
    }


def overall_level(score_pct: float) -> str:
    """Map an overall percentage score to a CAAN/ICAO implementation level."""
    if score_pct >= 90:
        return "Fully Effective & Continuous Improvement"
    if score_pct >= 70:
        return "Implemented & Operational"
    if score_pct >= 40:
        return "Partially Implemented (Documented only)"
    return "Not Implemented / Non-Compliant"


def score_assessment(responses: List[PSOEAnswer]) -> Dict[str, Any]:
    """One-stop helper: compute component + overall scores for an assessment."""
    component_scores = compute_component_scores(responses)
    return compute_overall(component_scores)