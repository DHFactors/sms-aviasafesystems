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


def test_cors_preflight_beta_hosting_and_local_origins(client):
    """The beta web.app hosting origin and the local dev servers must pass the
    CORS preflight with the explicit App Check / tenant-routing header list."""
    from app.main import CANONICAL_ALLOWED_ORIGINS, _allowed_origins

    merged = _allowed_origins()
    for origin in CANONICAL_ALLOWED_ORIGINS:
        assert origin in merged

    for origin in (
        "https://aerosafety-sms-beta.web.app",
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
    resp = client.get("/health", headers={"Origin": "https://aerosafety-sms-beta.web.app"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "https://aerosafety-sms-beta.web.app"
    exposed = resp.headers.get("access-control-expose-headers") or ""
    for header in ("Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"):
        assert header.lower() in exposed.lower(), f"header {header} not exposed"
