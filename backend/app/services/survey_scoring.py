"""Shared ICAO SMS survey scoring.

Single source of truth that turns raw survey answers into the pillar scores
(1-5) consumed by the airline and CAAN SMS maturity dashboards. The question ->
pillar grouping mirrors the master question contract
(public/portal/survey/default_q.js, v3.0.0) so scores computed here match the
questions employees are actually asked.
"""

from typing import Any, Dict, Optional

SURVEY_VERSION = "3.0.0"
SURVEY_VERSION_V4 = "4.0.0"

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


def validate_answers(answers: Dict[str, Any], version: str = None) -> Dict[str, str]:
    """Return {question_id: error} for every scored question that is missing
    or invalid. Optional free-text questions are ignored. `version` selects
    the question contract (auto-detected when omitted)."""
    universe = scored_universe(version or detect_survey_version(answers))
    errors: Dict[str, str] = {}
    for qid in universe:
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


# ============================================================================
# v4 SURVEY ENGINE — 31 questions, 12 ICAO SMS elements, proportional
# normalization (Chunk: Survey Scoring Engine).
#
#   Element score%  = (earned points / max possible for ANSWERED) × 100
#                     — elements with zero answered questions are skipped
#                       (None) and excluded from their pillar average.
#   Pillar score%   = average of the active element scores in that pillar.
#   Maturity %      = weighted composite across pillars: Policy 10 /
#                     SRM 40 / Assurance 30 / Promotion 20 (active weights
#                     renormalized so partial coverage never depresses).
#
# Legacy v3 submissions (23 questions) run through the same engine with the
# v3 question universe: elements whose v4-only questions are absent return
# None and simply drop out of the pillar averages — no artificial depression.
# ============================================================================

ELEMENT_QUESTIONS: Dict[str, list] = {
    "E1": ["q1_aware", "q2", "q3", "q4", "q5_spi"],
    "E2": ["q24_accountability", "q25_accountability_clear"],
    "E3": ["q26_key_personnel", "q27_key_personnel_access"],
    "E4": ["q6", "q7", "q8", "q9", "q10", "q11", "q12_risk_assess", "q13_action_inform"],
    "E5": ["q28_documentation", "q29_documentation_current"],
    "E6": ["q19_invest_outcome", "q20_corrective"],
    "E7": ["q14", "q15", "q16"],
    "E8": ["q16"],
    "E9": ["q30_moc_process", "q31_moc_risk"],
    "E10": ["q19_invest_outcome", "q20_corrective"],
    "E11": ["q17", "q18"],
    "E12": ["q21", "q22", "q23_peer"],
}

# Element → ICAO pillar (functional grouping by question content).
ELEMENT_PILLARS: Dict[str, str] = {
    "E1": "safety_policy",
    "E2": "safety_policy",
    "E3": "safety_policy",
    "E4": "safety_risk_management",
    "E5": "safety_policy",
    "E6": "safety_assurance",
    "E7": "safety_assurance",
    "E8": "safety_assurance",
    "E9": "safety_assurance",
    "E10": "safety_assurance",
    "E11": "safety_promotion",
    "E12": "safety_promotion",
}

PILLAR_WEIGHTS: Dict[str, int] = {
    "safety_policy": 10,
    "safety_risk_management": 40,
    "safety_assurance": 30,
    "safety_promotion": 20,
}

# Unique v4 question universe with its pillar assignment.
V4_QUESTION_PILLARS: Dict[str, str] = {}
for _eid, _qids in ELEMENT_QUESTIONS.items():
    for _q in _qids:
        V4_QUESTION_PILLARS.setdefault(_q, ELEMENT_PILLARS[_eid])

V4_ONLY_QUESTIONS = sorted(set(V4_QUESTION_PILLARS) - set(QUESTION_PILLARS))


def detect_survey_version(answers: Dict[str, Any]) -> str:
    """'4.0.0' when any v4-only question is answered, else the legacy '3.0.0'."""
    for qid in V4_ONLY_QUESTIONS:
        if answers.get(qid) is not None:
            return SURVEY_VERSION_V4
    return SURVEY_VERSION


def scored_universe(version: str) -> Dict[str, str]:
    """Question → pillar contract for a survey version."""
    return V4_QUESTION_PILLARS if version == SURVEY_VERSION_V4 else QUESTION_PILLARS


def compute_element_scores(
    answers: Dict[str, Any], version: str = None
) -> Dict[str, Optional[float]]:
    """Proportional element scores (0-100).

    score = Σ(normalized answers) / (5 × answered) × 100 — questions outside
    the version's universe are treated as unanswered; elements with no
    answered questions return None and are excluded from pillar averages.
    """
    ver = version or detect_survey_version(answers)
    universe = scored_universe(ver)
    result: Dict[str, Optional[float]] = {}
    for eid, qids in ELEMENT_QUESTIONS.items():
        vals = []
        for qid in qids:
            if qid not in universe:
                continue
            s = normalize_answer(qid, answers.get(qid))
            if s is not None:
                vals.append(s)
        result[eid] = round(sum(vals) / (5 * len(vals)) * 100, 1) if vals else None
    return result


def compute_pillar_percent_from_elements(
    element_scores: Dict[str, Optional[float]]
) -> Dict[str, Optional[float]]:
    """Average of the ACTIVE element scores per pillar (percent scale)."""
    buckets: Dict[str, list] = {p: [] for p in PILLARS}
    for eid, pct in element_scores.items():
        pillar = ELEMENT_PILLARS.get(eid)
        if pillar and pct is not None:
            buckets[pillar].append(pct)
    return {
        p: (round(sum(v) / len(v), 1) if v else None)
        for p, v in buckets.items()
    }


def compute_weighted_maturity_pct(
    pillar_percent: Dict[str, Optional[float]]
) -> Optional[float]:
    """Weighted composite (10/40/30/20) over pillars WITH scores, renormalized
    by the combined weight of active pillars."""
    total_weight = 0
    weighted = 0.0
    for pillar, weight in PILLAR_WEIGHTS.items():
        pct = pillar_percent.get(pillar)
        if pct is None:
            continue
        total_weight += weight
        weighted += pct * weight
    return round(weighted / total_weight, 1) if total_weight else None


def compute_survey_result(
    answers: Dict[str, Any], survey_version: str = None
) -> Dict[str, Any]:
    """Full scoring payload for a submission (v3 or v4).

    Both versions run through the same 12-element pipeline:
      * element_scores always populated — version-inapplicable elements return
        None (legacy v3: E2 / E3 / E5 / E9).
      * Pillar percent = average of ACTIVE element scores.
      * Maturity percent = weighted composite (Policy 10 / SRM 40 /
        Assurance 30 / Promotion 20) over pillars with scores; the 1-5
        maturity is `1 + pct/25`.
    """
    version = survey_version or detect_survey_version(answers)
    universe = scored_universe(version)

    question_scores = {
        qid: s for qid in universe
        if (s := normalize_answer(qid, answers.get(qid))) is not None
    }
    element_scores = compute_element_scores(answers, version)
    pillar_pct = compute_pillar_percent_from_elements(element_scores)
    overall_pct = compute_weighted_maturity_pct(pillar_pct)

    def _to5(pct):
        return round(1 + pct / 25, 2) if pct is not None else None

    pillar_scores = {p: _to5(pillar_pct[p]) for p in PILLARS}
    return {
        "version": version,
        "question_scores": question_scores,
        "element_scores": element_scores,
        "pillar_percent": pillar_pct,
        "pillar_scores": pillar_scores,
        "overall_score_pct": overall_pct,
        "overall_maturity": _to5(overall_pct),
    }
