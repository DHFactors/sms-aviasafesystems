# ============================================================================
# P2-24 — CAAN read / share / escalation audit writers.
# ============================================================================

from app.services import caan_audit


def test_caan_audit_actions(monkeypatch):
    calls = []
    monkeypatch.setattr(caan_audit, "log_audit",
                        lambda **kw: calls.append(kw))
    user = {"role": "CAAN_SMD", "email": "smd@caan.gov.np"}

    caan_audit.log_caan_read(user, "industry_averages")
    caan_audit.log_caan_share(user, "benchmark", recipient="state-x")
    caan_audit.log_caan_escalated_read(user, tenant_id="air1", target_id="HZ-1")

    actions = [c["action"] for c in calls]
    assert actions == [
        "CAAN_READ_INDUSTRY_AVERAGES",
        "CAAN_SHARE_BENCHMARK",
        "CAAN_ESCALATED_READ",
    ]
    assert calls[0]["user"] == "smd@caan.gov.np"
    assert calls[1]["metadata"]["recipient"] == "state-x"
    assert calls[2]["tenant_id"] == "air1"
