# ============================================================================
# P2-21 — N-HRC auto-derivation (+ manual override wins).
# ============================================================================

from app.services.nhrc_derivation_service import (
    derive_nhrc_category,
    resolve_nhrc_category,
)


def test_derive_from_taxonomy_and_keywords():
    assert derive_nhrc_category(
        taxonomy="Environmental", occurrence_type="Bird Strike",
        title="bird strike on climb", priority="M") == "WS"
    assert derive_nhrc_category(
        taxonomy="Human", title="hard landing", description="floated",
        priority="M") == "ARC"


def test_derive_from_taxonomy_mappings_table():
    # Seeded taxonomy_mappings (P1-23) maps the ICAO/ADREP code CFIT -> CFIT.
    assert derive_nhrc_category(adrep_category="CFIT") == "CFIT"
    assert derive_nhrc_category(occurrence_type="LOC-I") == "LOC-I"


def test_undetermined_returns_none():
    assert derive_nhrc_category(taxonomy="Technical", title="x",
                                description="y", priority="H") is None


def test_manual_override_wins():
    # A provided value bypasses derivation entirely.
    assert resolve_nhrc_category("MAC", taxonomy="Environmental",
                                 occurrence_type="Bird Strike") == "MAC"
