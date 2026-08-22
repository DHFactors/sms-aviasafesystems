"""Chunk 9 — Survey Scoring Engine: 12 elements & proportional normalization.

Covers:
  * ELEMENT_QUESTIONS contract (31 unique questions, 12 elements)
  * Proportional normalization (earned / max-answered × 100)
  * Zero-answered elements are skipped (None) and excluded from pillars
  * Legacy v3 (23 questions): E2/E3/E5/E9 → None, no artificial depression
  * Weighted maturity composite (Policy 10 / SRM 40 / Assurance 30 / Promotion 20)
  * Version detection + explicit version handling
"""

from app.services import survey_scoring as sc


# ── Contract ────────────────────────────────────────────────────────────────

def test_element_questions_contract():
    assert len(sc.ELEMENT_QUESTIONS) == 12
    uniques = {q for qs in sc.ELEMENT_QUESTIONS.values() for q in qs}
    assert len(uniques) == 31
    # Every element maps to a valid pillar and every pillar is covered.
    for eid, pillar in sc.ELEMENT_PILLARS.items():
        assert eid in sc.ELEMENT_QUESTIONS
        assert pillar in sc.PILLARS
    covered = {sc.ELEMENT_PILLARS[e] for e in sc.ELEMENT_QUESTIONS}
    assert covered == set(sc.PILLARS)


def test_element_question_membership():
    eq = sc.ELEMENT_QUESTIONS
    assert eq["E1"] == ["q1_aware", "q2", "q3", "q4", "q5_spi"]
    assert eq["E2"] == ["q24_accountability", "q25_accountability_clear"]
    assert eq["E9"] == ["q30_moc_process", "q31_moc_risk"]
    # Shared questions across sibling elements.
    assert "q16" in eq["E7"] and "q16" in eq["E8"]
    assert "q19_invest_outcome" in eq["E6"] and "q19_invest_outcome" in eq["E10"]


def test_pillar_weights_match_appendix10():
    assert sc.PILLAR_WEIGHTS == {
        "safety_policy": 10,
        "safety_risk_management": 40,
        "safety_assurance": 30,
        "safety_promotion": 20,
    }


# ── Version detection ───────────────────────────────────────────────────────

V3_ANSWERS = {
    "q1_aware": True, "q2": 4, "q3": 4, "q4": 3, "q5_spi": 3,
    "q6": 4, "q7": 4, "q8": 3, "q9": 3, "q10": 4, "q11": 3, "q12_risk_assess": 3,
    "q13_action_inform": 2, "q14": 3, "q15": 3, "q16": 2,
    "q17": 4, "q18": 3, "q19_invest_outcome": 3, "q20_corrective": 3,
    "q21": 3, "q22": 4, "q23_peer": 3,
}


def test_version_detection():
    assert sc.detect_survey_version(V3_ANSWERS) == sc.SURVEY_VERSION
    v4 = dict(V3_ANSWERS, q24_accountability=4, q26_key_personnel=5, q28_documentation=3,
              q25_accountability_clear=4, q27_key_personnel_access=4,
              q29_documentation_current=3, q30_moc_process=3, q31_moc_risk=2)
    assert sc.detect_survey_version(v4) == sc.SURVEY_VERSION_V4


def test_explicit_version_wins():
    # A pure-v3 payload explicitly tagged v4 stays on the v4 contract.
    r = sc.compute_survey_result(dict(V3_ANSWERS), survey_version=sc.SURVEY_VERSION_V4)
    missing = [e for e, pct in r["element_scores"].items() if pct is None]
    assert set(missing) >= {"E2", "E3", "E5", "E9"}


# ── Proportional normalization ──────────────────────────────────────────────

def test_proportional_normalization_full_answered():
    # E1 answered: aware(→5) + 4 + 4 + 3 + 3 = 19 earned / max 25 = 76%.
    answers = {"q1_aware": True, "q2": 4, "q3": 4, "q4": 3, "q5_spi": 3,
               **{f"q{n}": 3 for n in range(6, 14)}}
    es = sc.compute_element_scores(answers, version=sc.SURVEY_VERSION_V4)
    assert es["E1"] == 76.0


def test_proportional_normalization_partial_skips_unanswered():
    # Only two of E1's questions answered: earned 8 / max 10 = 80%.
    answers = {"q1_aware": True, "q2": 3,
               **{f"q{n}": 3 for n in range(6, 14)}}
    es = sc.compute_element_scores(answers, version=sc.SURVEY_VERSION_V4)
    assert es["E1"] == 80.0


def test_zero_answered_element_is_none_and_excluded():
    answers = {"q24_accountability": 4, "q25_accountability_clear": 4}  # only E2
    es = sc.compute_element_scores(answers, version=sc.SURVEY_VERSION_V4)
    assert es["E2"] == 80.0   # (4+4) / (5×2) × 100
    for e in ("E1", "E4", "E7", "E12"):
        assert es[e] is None

    pillar_pct = sc.compute_pillar_percent_from_elements(es)
    assert pillar_pct["safety_policy"] == 80.0          # from E2 alone
    assert pillar_pct["safety_risk_management"] is None  # skipped element


def test_shared_question_counts_in_both_elements():
    answers = {"q14": 3, "q15": 3, "q16": 3, "q19_invest_outcome": 3, "q20_corrective": 3,
               **{f"q{n}": 3 for n in range(6, 14)}}
    es = sc.compute_element_scores(answers, version=sc.SURVEY_VERSION_V4)
    assert es["E7"] == 60.0   # q14,q15,q16
    assert es["E8"] == 60.0   # q16 alone
    assert es["E6"] == 60.0   # q19,q20
    assert es["E10"] == 60.0  # same pair


# ── Pillar aggregation & weighted maturity ──────────────────────────────────

def _v4_all_threes():
    """Every one of the 31 unique questions answered with 3 → all elements 60%."""
    answers = {}
    for qs in sc.ELEMENT_QUESTIONS.values():
        for q in qs:
            answers[q] = 3
    return answers


def test_weighted_maturity_all_threes_is_sixty_percent():
    result = sc.compute_survey_result(_v4_all_threes(), survey_version=sc.SURVEY_VERSION_V4)
    assert result["overall_score_pct"] == 60.0
    # 1-5 conversion: 1 + pct/25 → pct 60 ⇒ 3.4.
    assert result["pillar_scores"]["safety_policy"] == 3.4
    assert result["overall_maturity"] == 3.4


def test_weighted_renormalization_with_missing_pillar():
    # Only SRM elements answered → its weight carries everything (no depression).
    answers = {f"q{n}": 4 for n in range(6, 14)}
    es = sc.compute_element_scores(answers, version=sc.SURVEY_VERSION_V4)
    pillar_pct = sc.compute_pillar_percent_from_elements(es)
    assert pillar_pct["safety_risk_management"] == 80.0
    overall = sc.compute_weighted_maturity_pct(pillar_pct)
    assert overall == 80.0


def test_legacy_v3_no_artificial_depression():
    """v3 runs the element layer with the v3 universe: E2/E3/E5/E9 are None and
    pillars average only their active elements."""
    result = sc.compute_survey_result(dict(V3_ANSWERS))  # auto-detect → 3.0.0
    assert result["version"] == sc.SURVEY_VERSION

    for e in ("E2", "E3", "E5", "E9"):
        assert result["element_scores"][e] is None

    # safety_policy's only v3-active element is E1 → pillar equals E1 exactly.
    e1 = result["element_scores"]["E1"]
    assert result["pillar_percent"]["safety_policy"] == e1
    # Assurance averages its active elements (E6, E7, E8, E10).
    act = [result["element_scores"][e] for e in ("E6", "E7", "E8", "E10")
           if result["element_scores"][e] is not None]
    expected_assurance = round(sum(act) / len(act), 1)
    assert result["pillar_percent"]["safety_assurance"] == expected_assurance
    assert result["overall_score_pct"] == sc.compute_weighted_maturity_pct(
        result["pillar_percent"]
    )


def test_v4_weighted_composite_emphasizes_srm():
    answers = _v4_all_threes()
    # Perfect SRM: all eight SRM questions (incl. aliased ids) at 5.
    answers.update({
        "q6": 5, "q7": 5, "q8": 5, "q9": 5, "q10": 5,
        "q11": 5, "q12_risk_assess": 5, "q13_action_inform": 5,
    })
    result = sc.compute_survey_result(answers, survey_version=sc.SURVEY_VERSION_V4)
    # Policy/Promotion 60%, SRM 100%, Assurance 60%:
    # composite = .1*60 + .4*100 + .3*60 + .2*60 = 76 (> plain avg 70).
    assert result["element_scores"]["E4"] == 100.0
    assert result["overall_score_pct"] == 76.0


def test_validate_answers_version_aware():
    # v4 contract requires accountability questions.
    errs = sc.validate_answers({}, version=sc.SURVEY_VERSION_V4)
    assert errs.get("q24_accountability") == "required"
    # v3 contract does not know them.
    errs3 = sc.validate_answers({}, version=sc.SURVEY_VERSION)
    assert "q24_accountability" not in errs3 and "q6" in errs3
