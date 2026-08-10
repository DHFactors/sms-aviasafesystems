"""Shared ICAO SMS survey scoring.

Single source of truth that turns raw survey answers into the pillar scores
(1-5) consumed by the airline and CAAN SMS maturity dashboards. The question ->
pillar grouping mirrors the master question contract
(public/portal/survey/default_q.js, v3.0.0) so scores computed here match the
questions employees are actually asked.
"""

from typing import Any, Dict, Optional

SURVEY_VERSION = "3.0.0"

# The four ICAO Annex 19 SMS pillars, in the order used across the dashboards.
PILLARS = [
    "safety_policy",
    "safety_risk_management",
    "safety_assurance",
    "safety_promotion",
]

# Binary (aware/unaware) question: aware -> 5, unaware -> 1.
BINARY_QUESTIONS = {"q1_aware"}

# Optional free-text question; never scored.
OPTIONAL_QUESTIONS = {"q24_comments"}

# Question -> pillar mapping, mirroring the master contract grouping.
QUESTION_PILLARS: Dict[str, str] = {
    # Safety Policy & Objectives
    "q1_aware": "safety_policy",
    "q2": "safety_policy",
    "q3": "safety_policy",
    "q4": "safety_policy",
    "q5_spi": "safety_policy",
    # Safety Risk Management
    "q6": "safety_risk_management",
    "q7": "safety_risk_management",
    "q8": "safety_risk_management",
    "q9": "safety_risk_management",
    "q10": "safety_risk_management",
    "q11": "safety_risk_management",
    "q12_risk_assess": "safety_risk_management",
    "q13_action_inform": "safety_risk_management",
    # Safety Assurance
    "q14": "safety_assurance",
    "q15": "safety_assurance",
    "q16": "safety_assurance",
    "q19_invest_outcome": "safety_assurance",
    "q20_corrective": "safety_assurance",
    # Safety Promotion
    "q17": "safety_promotion",
    "q18": "safety_promotion",
    "q21": "safety_promotion",
    "q22": "safety_promotion",
    "q23_peer": "safety_promotion",
}


def normalize_answer(qid: str, value: Any) -> Optional[float]:
    """Normalize one raw answer to a 1-5 score, or None when invalid.

    Likert questions accept numeric 1-5. The binary question accepts either a
    boolean (true/false, as sent by the portal UI) or the numeric 1/5 form.
    """
    if qid in BINARY_QUESTIONS:
        if isinstance(value, bool):
            return 5.0 if value else 1.0
        if isinstance(value, int) and value in (1, 5):
            return float(value)
        if isinstance(value, float) and value in (1.0, 5.0):
            return float(value)
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if 1 <= value <= 5:
            return float(value)
    return None


def validate_answers(answers: Dict[str, Any]) -> Dict[str, str]:
    """Return {question_id: error} for every scored question that is missing
    or invalid. Optional free-text questions are ignored."""
    errors: Dict[str, str] = {}
    for qid in QUESTION_PILLARS:
        if qid not in answers or answers[qid] is None:
            errors[qid] = "required"
            continue
        if normalize_answer(qid, answers[qid]) is None:
            errors[qid] = "must be a 1-5 likert score (binary: true/false or 1/5)"
    return errors


def compute_question_scores(answers: Dict[str, Any]) -> Dict[str, float]:
    """Normalized per-question scores for all scored questions."""
    return {
        qid: score
        for qid in QUESTION_PILLARS
        if (score := normalize_answer(qid, answers.get(qid))) is not None
    }


def compute_pillar_scores(answers: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Compute the four ICAO pillar averages on the 1-5 scale."""
    buckets: Dict[str, list] = {p: [] for p in PILLARS}
    for qid, pillar in QUESTION_PILLARS.items():
        score = normalize_answer(qid, answers.get(qid))
        if score is not None:
            buckets[pillar].append(score)
    result: Dict[str, Optional[float]] = {}
    for pillar in PILLARS:
        vals = buckets[pillar]
        result[pillar] = round(sum(vals) / len(vals), 2) if vals else None
    return result


def compute_overall_maturity(
    pillar_scores: Dict[str, Optional[float]],
) -> Optional[float]:
    """Average of the pillar scores on the 1-5 scale. None when no pillar
    has a score."""
    vals = [v for v in pillar_scores.values() if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def compute_percentage_score(score: Optional[float]) -> Optional[float]:
    """Convert a 1-5 score to a percentage: ((score - 1) / 4) * 100."""
    if score is None:
        return None
    return round((score - 1) / 4 * 100, 1)
