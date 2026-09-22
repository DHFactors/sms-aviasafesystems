# ============================================================================
# FILE: data_governance.py
# PATH: backend/app/services/data_governance.py
# PURPOSE: Module C §5/§6 (DP-1, DP-7, SS-6) — data-classification labels and
#          Appendix-3 use-limitation statements for share / dispatch / export
#          outputs.
# ============================================================================

from __future__ import annotations

from typing import Any, Optional, Tuple

# Data-classification vocabulary (DP-1).
CLASSIFICATION_PUBLIC = "public"
CLASSIFICATION_INTERNAL = "internal"
CLASSIFICATION_CONFIDENTIAL = "confidential"
CLASSIFICATION_PROTECTED = "protected"

CLASSIFICATIONS = (
    CLASSIFICATION_PUBLIC,
    CLASSIFICATION_INTERNAL,
    CLASSIFICATION_CONFIDENTIAL,
    CLASSIFICATION_PROTECTED,
)

# Annex 19 Third Edition, Appendix 3 — use-limitation statement (DP-7 / SS-6).
USE_LIMITATION_STATEMENT = (
    "This safety data is provided for the purpose of maintaining or improving "
    "aviation safety only. It must not be used for disciplinary, civil, "
    "administrative, or criminal proceedings against employees, operational "
    "personnel, or organizations (Annex 19 Third Edition, Appendix 3)."
)

# Variant for protected / confidential data (Appendix 3 protection).
CONFIDENTIAL_USE_LIMITATION_STATEMENT = (
    USE_LIMITATION_STATEMENT
    + " This dataset is classified PROTECTED under Annex 19 Appendix 3; "
    "reporter identity must never be disclosed and the data must be "
    "de-identified before any onward use."
)

_PROTECTED_TYPES = {"survey", "surveys", "survey_response", "survey_responses",
                    "sms_maturity", "sms_maturity_assessment"}
_INTERNAL_TYPES = {"hazard", "hazards", "can", "cans", "cap", "caps", "report", "reports"}
_PUBLIC_TYPES = {"aggregate", "aggregates", "state_aggregate", "module_c_aggregate",
                 "industry_average", "benchmark"}


def get_classification(entity_type: str, entity: Optional[Any] = None) -> str:
    """Return the DP-1 classification for an entity/artifact.

    Rules (Module C §5):
      * reports      -> confidential flag ? "protected" : "internal"
      * surveys      -> "protected" (employee safety data)
      * hazards/CAN/CAP -> "internal"
      * aggregated/state data -> "public" (anonymized)
    """
    et = (entity_type or "").strip().lower()
    if et in _PROTECTED_TYPES:
        return CLASSIFICATION_PROTECTED
    if et in ("report", "reports"):
        flag = (entity.get("is_confidential") if isinstance(entity, dict)
                else getattr(entity, "is_confidential", False))
        return CLASSIFICATION_PROTECTED if flag else CLASSIFICATION_INTERNAL
    if et in _PUBLIC_TYPES:
        return CLASSIFICATION_PUBLIC
    if et in _INTERNAL_TYPES:
        return CLASSIFICATION_INTERNAL
    return CLASSIFICATION_INTERNAL


def classification_metadata(entity_type: str, entity: Optional[Any] = None) -> dict:
    return {"classification": get_classification(entity_type, entity)}


def classification_header(entity_type: str, entity: Optional[Any] = None) -> dict:
    """HTTP header pair for export responses carrying the classification."""
    return {"X-Data-Classification": get_classification(entity_type, entity)}


def limitation_statement(classification: str = CLASSIFICATION_INTERNAL) -> str:
    """Return the appropriate use-limitation statement text."""
    if classification in (CLASSIFICATION_PROTECTED, CLASSIFICATION_CONFIDENTIAL):
        return CONFIDENTIAL_USE_LIMITATION_STATEMENT
    return USE_LIMITATION_STATEMENT


def limitation_html(classification: str = CLASSIFICATION_INTERNAL) -> str:
    return f"<p><small><em>{limitation_statement(classification)}</em></small></p>"


def limitation_text(classification: str = CLASSIFICATION_INTERNAL) -> str:
    return f"\n\n{limitation_statement(classification)}"


def with_limitation(body: str, classification: str = CLASSIFICATION_INTERNAL,
                    *, html: bool = False) -> str:
    """Append the use-limitation statement to an email/PDF body."""
    if not body:
        return body
    return body + (limitation_html(classification) if html
                   else limitation_text(classification))
