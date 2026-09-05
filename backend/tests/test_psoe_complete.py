# ============================================================================
# FILE: test_psoe_complete.py
# PATH: backend/tests/test_psoe_complete.py
# PURPOSE: Unit tests for the SUPABASE-backed PSOE scoring engine
#          (psoe_complete_service scoring helpers and response normalisation).
#          Pure-function tests only — no database session required.
# ============================================================================

from app.db.db_models import PsoeQuestion
from app.services.psoe_complete_service import (
    _level_name,
    _normalize_responses,
    _score,
)

COMPONENT_SIZES = {
    "Safety Management": 5,
    "Risk Management": 5,
    "Safety Assurance": 6,
    "Safety Promotion": 5,
}


def _question_bank() -> list:
    questions = []
    number = 1
    for component, size in COMPONENT_SIZES.items():
        for i in range(size):
            questions.append(
                PsoeQuestion(
                    component=component,
                    question_number=number,
                    question_text=f"{component} Q{number}",
                )
            )
            number += 1
    return questions


def _responses(mapping: dict) -> dict:
    return {str(n): {"response": value} for n, value in mapping.items()}


def test_all_compliant_scores_100_level5():
    responses = _responses({n: "Compliant" for n in range(1, 22)})
    component_scores, overall, level = _score(responses, _question_bank())
    for comp, scores in component_scores.items():
        assert scores["compliant"] == COMPONENT_SIZES[comp]
        assert scores["answered"] == COMPONENT_SIZES[comp]
        assert scores["percentage"] == 100.0
    assert overall == 100.0
    assert level == "Level 5 - World-Class"


def test_partial_scores_and_na_excluded_from_denominator():
    responses = {
        # Safety Management (5): 3 compliant, 1 non-compliant, 1 N/A -> 75%
        # Risk Management (5):   4 compliant, 1 non-compliant            -> 80%
        # Safety Assurance (6):  4 compliant, 1 non-compliant, 1 N/A    -> 80%
        # Safety Promotion (5):  5 compliant                            -> 100%
        1: "Compliant", 2: "Compliant", 3: "Compliant",
        4: "Non-Compliant", 5: "Not Applicable",
        6: "Compliant", 7: "Compliant", 8: "Compliant", 9: "Compliant",
        10: "Partially Compliant",
        11: "Compliant", 12: "Compliant", 13: "Compliant", 14: "Compliant",
        15: "Non-Compliant", 16: "Not Applicable",
        17: "Compliant", 18: "Compliant", 19: "Compliant",
        20: "Compliant", 21: "Compliant",
    }
    component_scores, overall, level = _score(responses, _question_bank())

    assert component_scores["Safety Management"]["percentage"] == 75.0
    assert component_scores["Risk Management"]["percentage"] == 80.0
    assert component_scores["Safety Assurance"]["percentage"] == 80.0
    assert component_scores["Safety Promotion"]["percentage"] == 100.0

    assert component_scores["Safety Management"]["answered"] == 4
    assert overall == round((75.0 + 80.0 + 80.0 + 100.0) / 4, 1) == 83.8
    assert level == "Level 5 - World-Class"


def test_empty_responses_score_zero_level1():
    component_scores, overall, level = _score({}, _question_bank())
    for comp, scores in component_scores.items():
        assert scores == {"compliant": 0, "answered": 0, "percentage": 0.0}
    assert overall == 0.0
    assert level == "Level 1 - Initial"


def test_level_thresholds():
    assert _level_name(0) == "Level 1 - Initial"
    assert _level_name(20) == "Level 1 - Initial"
    assert _level_name(21) == "Level 2 - Developing"
    assert _level_name(40) == "Level 2 - Developing"
    assert _level_name(41) == "Level 3 - Maturing"
    assert _level_name(60) == "Level 3 - Maturing"
    assert _level_name(61) == "Level 4 - Advanced"
    assert _level_name(80) == "Level 4 - Advanced"
    assert _level_name(81) == "Level 5 - World-Class"
    assert _level_name(100) == "Level 5 - World-Class"


def test_normalise_accepts_dict_and_list_forms():
    as_dict = _normalize_responses({"7": {"response": "Compliant", "evidence": "e1"}})
    assert as_dict == {"7": {"response": "Compliant", "evidence": "e1", "findings": ""}}

    as_list = _normalize_responses(
        [{"question_number": 7, "response": "Compliant", "evidence": "e1"}]
    )
    assert as_list["7"]["response"] == "Compliant"
    assert as_list["7"]["evidence"] == "e1"

    raw = _normalize_responses({"9": "Compliant"})
    assert raw["9"]["response"] == "Compliant"
    assert raw["9"]["evidence"] == ""

    answer_dict = _normalize_responses({7: {"response": "N/A", "findings": "f"}, 8: {}})
    assert answer_dict["7"]["findings"] == "f"
    assert answer_dict["8"]["response"] is None