from app.services.severity_service import (
    DEFAULT_SEVERITY_LEVEL,
    LEVEL_TO_LABEL,
    apply_auto_severity,
    severity_for_category,
    severity_label_for_category,
)


def test_critical_categories():
    for cat in ("CFIT", "LOCI", "MAC"):
        assert severity_for_category(cat) == 5
        assert severity_label_for_category(cat) == "Critical"


def test_high_categories():
    for cat in ("ENG", "SYS", "BIRD", "RE", "RI"):
        assert severity_for_category(cat) == 4
        assert severity_label_for_category(cat) == "High"


def test_medium_categories():
    for cat in ("WX", "GCOL", "OTHER", "FIRE", "CABIN", "ARC", "PRO"):
        assert severity_for_category(cat) == DEFAULT_SEVERITY_LEVEL
        assert severity_label_for_category(cat) == "Medium"


def test_case_insensitive_and_unknown_default_to_medium():
    assert severity_for_category("bird") == 4
    assert severity_for_category("UNRECOGNISED") == 3
    assert severity_for_category(None) == 3
    assert severity_for_category("") == 3


def test_level_to_label_matches_dashboard_vocabulary():
    assert LEVEL_TO_LABEL[5] == "Critical"
    assert LEVEL_TO_LABEL[4] == "High"
    assert LEVEL_TO_LABEL[3] == "Medium"
    assert LEVEL_TO_LABEL[2] == "Low"
    assert LEVEL_TO_LABEL[1] == "Low"


def test_apply_auto_severity_sets_level_and_label():
    payload = {"occurrence_category": "BIRD", "narrative": "struck by bird"}
    out = apply_auto_severity(payload)
    assert out["severity_level"] == 4
    assert out["severity"] == "High"


def test_apply_auto_severity_overrides_client_value():
    payload = {"occurrence_category": "WX", "severity_level": 1, "severity": "Low"}
    out = apply_auto_severity(payload)
    assert out["severity_level"] == 3
    assert out["severity"] == "Medium"


def test_apply_auto_severity_missing_category_defaults():
    payload = {"narrative": "no category chosen"}
    out = apply_auto_severity(payload)
    assert out["severity_level"] == 3
    assert out["severity"] == "Medium"