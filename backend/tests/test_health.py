def test_count_total_handles_all_sdk_shapes():
    """The Recent Reports endpoint must survive google-cloud-firestore version
    differences in the count() aggregation result (list-of-results vs. the
    nested [[AggregationResult]] shape returned by newer SDKs)."""
    from app.services.repository import ReportRepository

    class Agg:
        def __init__(self, value):
            self.value = value

    # Newer SDK shape: [[Aggregation(value=18)]]
    assert ReportRepository._count_total([[Agg(18)]]) == 18
    # Older SDK shape: [Aggregation(value=18)]
    assert ReportRepository._count_total([Agg(18)]) == 18
    # Empty result set
    assert ReportRepository._count_total([]) == 0
    assert ReportRepository._count_total(None) == 0
    # Zero count (non-nested and nested)
    assert ReportRepository._count_total([Agg(0)]) == 0
    assert ReportRepository._count_total([[Agg(0)]]) == 0


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "AviaSAFE SMS API"


def test_liveness_endpoint(client):
    resp = client.get("/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


def test_root_endpoint(client):
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert data["status"] == "operational"


def test_cors_allows_canonical_frontend_origins(client):
    """The beta/prod hosting sites and custom domain must always pass the CORS
    preflight regardless of a stale ALLOWED_ORIGINS environment variable."""
    from app.main import CANONICAL_ALLOWED_ORIGINS, _allowed_origins

    merged = _allowed_origins()
    for origin in CANONICAL_ALLOWED_ORIGINS:
        assert origin in merged

    for origin in CANONICAL_ALLOWED_ORIGINS:
        resp = client.options(
            "/api/v1/dashboard/airline/sms-maturity",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert resp.status_code == 200, f"preflight rejected for {origin}"
        assert resp.headers.get("access-control-allow-origin") == origin
        assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_preflight_hosting_and_local_origins(client):
    """The web.app hosting origin and the local dev servers must pass the
    CORS preflight with the explicit App Check / tenant-routing header list."""
    from app.main import CANONICAL_ALLOWED_ORIGINS, _allowed_origins

    merged = _allowed_origins()
    for origin in CANONICAL_ALLOWED_ORIGINS:
        assert origin in merged

    for origin in (
        "https://demo.aviasafesystems.com",
        "http://localhost:5000",
        "http://localhost:8000",
        "http://127.0.0.1:5500",
    ):
        resp = client.options(
            "/api/v1/auth/register-tenant",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type,x-firebase-appcheck,x-requested-with,accept,origin",
            },
        )
        assert resp.status_code == 200, f"preflight rejected for {origin}"
        assert resp.headers.get("access-control-allow-origin") == origin
        assert resp.headers.get("access-control-allow-credentials") == "true"
        allowed = (resp.headers.get("access-control-allow-headers") or "").lower()
        for header in ("x-firebase-appcheck", "x-requested-with", "x-tenant-id"):
            assert header in allowed, f"header {header} not allowed for {origin}"


def test_cors_exposes_rate_limit_headers(client):
    """The rate-limit / back-off headers must be readable from a cross-origin
    response so the SPA can honour Retry-After and the sliding-window counters."""
    resp = client.get("/health", headers={"Origin": "https://aerosafety-sms-prod.web.app"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "https://aerosafety-sms-prod.web.app"
    exposed = resp.headers.get("access-control-expose-headers") or ""
    for header in ("Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"):
        assert header.lower() in exposed.lower(), f"header {header} not exposed"


def test_repository_pushes_date_range_into_sql(monkeypatch):
    """get_all_in_range must push the date range into the SQL WHERE clause so
    tenant-scoped reads hit the (tenant_id, created_at) index instead of
    full-scanning then date-filtering in Python."""
    from datetime import datetime, timedelta, timezone
    from unittest.mock import patch

    from app.services.repository import ReportFilter, ReportRepository
    from app.db import db_models

    captured = {}

    def _fake_fetch_all(model, *, where=None, order_by=None, limit=None):
        captured["model"] = model
        captured["where"] = list(where or [])
        return []

    now = datetime.now(timezone.utc)
    date_from = now - timedelta(days=30)
    date_to = now
    with patch("app.services.repository.pg.fetch_all", _fake_fetch_all):
        repo = ReportRepository()
        repo.get_all_in_range(ReportFilter(tenant_id="sita-air", date_from=date_from, date_to=date_to))

    assert captured["model"] is db_models.Report
    rendered = " ".join(str(w) for w in captured["where"])
    # tenant scoping + lower bound + upper bound on the typed created_at column
    assert any(hasattr(w, "operator") and w.operator.__name__ == "ge" for w in captured["where"])
    assert any(hasattr(w, "operator") and w.operator.__name__ == "le" for w in captured["where"])
    assert "occurrence_date" in rendered or "created_at" in rendered


def test_repository_date_pushdown_respects_sort_column(monkeypatch):
    """Date predicates must follow sort_by: occurrence_date when requested,
    and stay out of the WHERE clause for non-date sort columns."""
    from datetime import datetime, timedelta, timezone
    from unittest.mock import patch

    from app.services.repository import ReportFilter, ReportRepository

    captured = {}

    def _fake_fetch_all(model, *, where=None, order_by=None, limit=None):
        captured["where"] = list(where or [])
        return []

    now = datetime.now(timezone.utc)
    with patch("app.services.repository.pg.fetch_all", _fake_fetch_all):
        repo = ReportRepository()
        repo.get_all_in_range(
            ReportFilter(tenant_id="sita-air", date_from=now - timedelta(days=7), sort_by="occurrence_date")
        )
        ops = [w.operator.__name__ for w in captured["where"] if hasattr(w, "operator")]
        assert "ge" in ops  # pushed on the occurrence_date column
        assert all("created_at" not in str(w) for w in captured["where"])

        # Non-date sort column -> no date predicate added (Python filter keeps it)
        captured["where"] = []
        repo.get_all_in_range(
            ReportFilter(tenant_id="sita-air", date_from=now - timedelta(days=7), sort_by="occurrence_type")
        )
        assert all(not hasattr(w, "operator") or w.operator.__name__ not in ("ge", "le") for w in captured["where"])
