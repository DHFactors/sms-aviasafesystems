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
