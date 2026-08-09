from app.services.metrics_service import MetricsService


def test_calculate_kpis_empty():
    result = MetricsService.calculate_kpis([])
    assert result["total_reports"] == 0
    assert result["open_reports"] == 0
    assert result["high_risk_reports"] == 0
    assert result["anonymous_percentage"] == 0.0


def test_calculate_kpis_with_data(sample_reports):
    result = MetricsService.calculate_kpis(sample_reports)
    assert result["total_reports"] == 2
    assert result["open_reports"] == 1
    assert result["closed_reports"] == 1
    assert result["high_risk_reports"] == 1
    assert result["anonymous_percentage"] == 50.0


def test_calculate_risk_distribution(sample_reports):
    result = MetricsService.calculate_risk_distribution(sample_reports)
    levels = {r["risk_level"]: r["count"] for r in result}
    assert levels.get("Low") == 1
    assert levels.get("High") == 1
    assert levels.get("Critical") == 0
    assert sum(r["count"] for r in result) == 2


def test_calculate_hazard_frequency(sample_reports):
    result = MetricsService.calculate_hazard_frequency(sample_reports)
    types = {r["occurrence_type"]: r["count"] for r in result}
    assert types.get("Bird Strike") == 1


def test_calculate_monthly_trends(sample_reports):
    result = MetricsService.calculate_monthly_trends(sample_reports)
    assert len(result) >= 1
    assert result[0]["total"] == 2


def test_calculate_ai_kpis(sample_reports):
    result = MetricsService.calculate_ai_kpis(sample_reports)
    assert result["ai_processed"] == 1
    assert result["ai_pending"] == 1


def test_calculate_org_kpis(sample_reports):
    result = MetricsService.calculate_org_kpis(sample_reports)
    assert result["active_reporters"] == 2
    assert result["corrective_actions_open"] == 1
    assert result["investigation_backlog"] == 1


def test_calculate_ssp_risk_trends_empty():
    result = MetricsService.calculate_ssp_risk_trends([])
    assert result["quarters"] == []
    assert len(result["series"]) == 5
    assert all(s["points"] == [] for s in result["series"])


def test_calculate_ssp_risk_trends_categories_and_scoring():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    reports = [
        {
            "occurrence_category": "MAC",
            "risk_index": 8,
            "created_at": now,
        },
        {
            "occurrence_category": "MAC",
            "risk_index": 12,
            "created_at": now,
        },
        {
            "occurrence_category": "BIRD",
            "risk_index": 4,
            "created_at": now,
        },
    ]
    result = MetricsService.calculate_ssp_risk_trends(reports)
    assert result["quarters"] == [f"{now.year}-Q{(now.month - 1) // 3 + 1}"]
    by_cat = {s["category"]: s for s in result["series"]}

    tech = by_cat["Technical"]["points"][0]
    assert tech["avg_risk_index"] == round(((8 + 12) / 2) * 4, 1)

    ext = by_cat["External"]["points"][0]
    assert ext["avg_risk_index"] == round(4 * 4, 1)

    assert by_cat["Operational"]["points"][0]["avg_risk_index"] is None


def test_calculate_ssp_risk_trends_ignores_no_risk_index():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    reports = [{"occurrence_category": "MAC", "created_at": now}]
    result = MetricsService.calculate_ssp_risk_trends(reports)
    assert result["quarters"] == [f"{now.year}-Q{(now.month - 1) // 3 + 1}"]
    for s in result["series"]:
        assert s["points"][0]["avg_risk_index"] is None


def test_calculate_ssp_risk_trends_skips_bad_dates():
    reports = [
        {"occurrence_category": "MAC", "risk_index": 8, "created_at": "not-a-date"},
        {"occurrence_category": "MAC", "risk_index": 8},
    ]
    result = MetricsService.calculate_ssp_risk_trends(reports)
    assert result["quarters"] == []
