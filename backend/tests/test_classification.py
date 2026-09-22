# ============================================================================
# P2-28 — data-classification labels (DP-1).
# ============================================================================

from app.services.data_governance import (
    CLASSIFICATION_INTERNAL,
    CLASSIFICATION_PROTECTED,
    CLASSIFICATION_PUBLIC,
    classification_header,
    classification_metadata,
    get_classification,
)


def test_report_classification_from_flag():
    assert get_classification("report", {"is_confidential": True}) == CLASSIFICATION_PROTECTED
    assert get_classification("report", {"is_confidential": False}) == CLASSIFICATION_INTERNAL
    assert get_classification("reports", {}) == CLASSIFICATION_INTERNAL


def test_survey_and_hazard_classification():
    assert get_classification("survey") == CLASSIFICATION_PROTECTED
    assert get_classification("hazard") == CLASSIFICATION_INTERNAL
    assert get_classification("cans") == CLASSIFICATION_INTERNAL


def test_aggregate_classification_is_public():
    assert get_classification("aggregate") == CLASSIFICATION_PUBLIC
    assert get_classification("state_aggregate") == CLASSIFICATION_PUBLIC


def test_classification_metadata_and_header():
    assert classification_metadata("hazard") == {"classification": CLASSIFICATION_INTERNAL}
    assert classification_header("aggregate")["X-Data-Classification"] == CLASSIFICATION_PUBLIC
