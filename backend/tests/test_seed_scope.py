"""Seed scoping, survey-maturity, and CAAN regulator account invariants.

Locks the behaviour added for the beta verification run:

  * seed.runner.run(dry_run=True, tenant_ids=[...]) only counts the requested
    tenants; a full (unscoped) dry run counts the whole 11-provider set.
  * Every generated survey is a "completed" record with all four SMS pillars and
    a submitted_at inside the default 90-day assessment window (max 180 days),
    so the CAAN SMS-maturity overview has data.
  * The CAAN state-regulator account is a single smd@caanepal.gov.np identity
    and is always protected from automated unseed runs.
  * production_seed.SEED_OPERATORS matches the 11 active beta providers
    (CAAN oversight runs through the single `caan` regulator tenant).
"""

from datetime import datetime, timezone

from seed.config import (
    OPERATOR_PROFILES,
    CAAN_REGULATOR_ACCOUNT,
    PROTECTED_ADMIN_ACCOUNTS,
    ICAO_SMS_PILLARS,
    SEED_VERSION,
)
from seed.surveys import generate_survey_batch
from seed.generator import SeededRandom
from seed.runner import run


def test_dry_run_full_plan_counts():
    counts = run(dry_run=True)
    assert counts["tenants"] == len(OPERATOR_PROFILES) == 11
    assert counts["users"] == 0
    total_surveys = sum(p["survey_count"] for p in OPERATOR_PROFILES)
    assert counts["surveys"] == total_surveys
    assert counts["vsr_reports"] == sum(p["vsr_count"] for p in OPERATOR_PROFILES)
    assert counts["mor_reports"] == sum(p["mor_count"] for p in OPERATOR_PROFILES)
    from seed.hazard_can import estimate_counts
    hc = estimate_counts()
    assert counts["hazards"] == hc["hazards"]
    assert counts["cans"] == hc["cans"]
    assert counts["caps"] == hc["caps"]


def test_dry_run_scoped_to_tenant_ids():
    counts = run(dry_run=True, tenant_ids=["buddha-air", "ktm-mro"])
    assert counts["tenants"] == 2
    assert counts["tenant_ids"] == ["buddha-air", "ktm-mro"]
    expected_surveys = (
        sum(p["survey_count"] for p in OPERATOR_PROFILES if p["id"] in {"buddha-air", "ktm-mro"})
    )
    assert counts["surveys"] == expected_surveys
    assert counts["vsr_reports"] == sum(
        p["vsr_count"] for p in OPERATOR_PROFILES if p["id"] in {"buddha-air", "ktm-mro"}
    )
    assert counts["mor_reports"] == sum(
        p["mor_count"] for p in OPERATOR_PROFILES if p["id"] in {"buddha-air", "ktm-mro"}
    )


def test_dry_run_single_tenant_excludes_others():
    counts = run(dry_run=True, tenant_ids=["pokhara-aerodrome"])
    assert counts["tenants"] == 1
    pokhara = next(p for p in OPERATOR_PROFILES if p["id"] == "pokhara-aerodrome")
    assert counts["surveys"] == pokhara["survey_count"]
    assert counts["vsr_reports"] == pokhara["vsr_count"]
    assert counts["mor_reports"] == pokhara["mor_count"]


def test_generated_surveys_are_completed_with_all_pillars():
    for profile in OPERATOR_PROFILES:
        rng = SeededRandom(seed=10000)
        surveys = generate_survey_batch(rng, profile, 10000)
        assert len(surveys) == profile["survey_count"]
        assert 15 <= len(surveys) <= 25
        for s in surveys:
            assert s["status"] == "completed"
            assert s["seed_version"] == SEED_VERSION
            for pillar in ICAO_SMS_PILLARS:
                assert pillar in s, f"{pillar} missing from {profile['id']} survey"
            submitted = s["submitted_at"]
            if isinstance(submitted, datetime):
                age_days = (datetime.now(timezone.utc) - submitted).days
                assert 0 <= age_days <= 180


def test_survey_counts_per_provider_within_15_25():
    for p in OPERATOR_PROFILES:
        assert 15 <= p["survey_count"] <= 25, p["id"]


def test_caan_regulator_account_single_identity():
    assert CAAN_REGULATOR_ACCOUNT["uid"] == "smd-caan-001"
    assert CAAN_REGULATOR_ACCOUNT["email"] == "smd@caanepal.gov.np"
    assert CAAN_REGULATOR_ACCOUNT["role"] == "CAAN_SMD"
    assert CAAN_REGULATOR_ACCOUNT["tenant_id"] == "caan"


def test_caan_regulator_account_is_protected():
    acct = CAAN_REGULATOR_ACCOUNT
    assert acct["email"] in PROTECTED_ADMIN_ACCOUNTS["emails"]
    assert acct["uid"] in PROTECTED_ADMIN_ACCOUNTS["uids"]
    assert PROTECTED_ADMIN_ACCOUNTS["roles"] == {"SUPER_ADMIN"}


def test_production_seed_operators_match_active_providers():
    from app.services.production_seed import SEED_OPERATORS
    active = {p["id"] for p in OPERATOR_PROFILES}
    assert {o["id"] for o in SEED_OPERATORS} == active


class _FakeRef:
    def __init__(self, store, doc_id):
        self._store = store
        self._id = doc_id

    def set(self, data, merge=False):
        self._store[self._id] = {**self._store.get(self._id, {}), **data} if merge else dict(data)

    def get(self):
        return _FakeSnap(self._id, self._store.get(self._id) or {})


class _FakeSnap:
    def __init__(self, id, data):
        self.id = id
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data)


class _FakeColl:
    def __init__(self, store):
        self._store = store

    def document(self, doc_id):
        return _FakeRef(self._store, doc_id)


class _FakeDB:
    def __init__(self):
        self._stores = {"regulators": {}, "tenants": {}}

    def collection(self, name):
        return _FakeColl(self._stores[name])


def test_regulator_scoping_writes_caan_doc_and_tags_tenants():
    from seed.operators import create_regulator_scoping

    db = _FakeDB()
    result = create_regulator_scoping(db)
    active = sorted(p["id"] for p in OPERATOR_PROFILES)
    assert result["operator_tenant_ids"] == active
    reg = db._stores["regulators"]["caan"]
    assert reg["id"] == "caan"
    assert reg["type"] == "state_regulator"
    assert reg["operator_tenant_ids"] == active
    for tid in active + ["caan"]:
        assert db._stores["tenants"][tid]["regulator_id"] == "caan"
        assert db._stores["tenants"][tid]["country"] == "NP"
