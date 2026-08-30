"""Integration tests for PS-3.1 (Action Guardrails) and PS-4.2 (Observability Pipeline)."""

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.scripts.seed_demo import seed
from shared.storage.factory import get_repository


@pytest.fixture
def client():
    get_repository.cache_clear()
    from backend import deps

    deps.repo.cache_clear()
    deps.publisher.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded(client):
    return seed(force=True)


# --- PS-3.1 Action Guardrails ---


def test_internal_email_allowed(seeded, client):
    reg = client.post(
        "/v1/agents/register",
        json={
            "name": "Internal Email Test Agent",
            "owner": "test-team",
            "team": "Test",
            "purpose": "Validate internal email allow path",
            "framework": "custom",
            "risk_tier": "low",
            "tools": [{"name": "email_send", "allowed_operations": ["read", "write"]}],
            "policy_ids": ["support-agent-policy"],
        },
    )
    assert reg.status_code == 200
    agent_id = reg.json()["agent"]["agent_id"]
    resp = client.post(
        "/v1/tool/intercept",
        json={
            "context": {
                "agent_id": agent_id,
                "session_id": "internal-email-session",
                "action_type": "write",
                "tool_name": "email_send",
                "tool_params": {"to": "colleague@company.com", "subject": "Team sync notes"},
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["disposition"] == "allow"
    assert data.get("ticket_id") is None


def test_confidential_read_audit_only(seeded, client):
    developer_id = seeded["agents"]["developer"]
    resp = client.post(
        "/v1/tool/intercept",
        json={
            "context": {
                "agent_id": developer_id,
                "session_id": "audit-only-session",
                "action_type": "read",
                "tool_name": "code_search",
                "tool_params": {"query": "auth module"},
                "session_data_classification": "confidential",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["disposition"] == "audit_only"
    assert "Confidential read logged" in data["reason"]


def test_guardrail_dry_run_simulates_block(seeded, client):
    finance_id = seeded["agents"]["finance"]
    resp = client.post(
        "/v1/tool/intercept",
        json={
            "context": {
                "agent_id": finance_id,
                "session_id": "dry-run-block-session",
                "action_type": "delete",
                "tool_name": "db_delete",
                "tool_params": {"count": 500},
                "data_scope_size": 500,
            },
            "dry_run": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["disposition"] == "allow"
    assert data["metadata"]["dry_run"] is True
    assert data["metadata"]["would_disposition"] == "block"

    violations = client.get("/v1/violations", params={"agent_id": finance_id}).json()["violations"]
    dry_run_violations = [v for v in violations if v.get("session_id") == "dry-run-block-session"]
    assert dry_run_violations == []


def test_guardrail_dry_run_simulates_hitl(seeded, client):
    reg = client.post(
        "/v1/agents/register",
        json={
            "name": "Dry Run HITL Agent",
            "owner": "test-team",
            "team": "Test",
            "purpose": "Validate dry-run HITL simulation",
            "framework": "custom",
            "risk_tier": "low",
            "tools": [{"name": "email_send", "allowed_operations": ["read", "write"]}],
            "policy_ids": ["support-agent-policy"],
        },
    )
    agent_id = reg.json()["agent"]["agent_id"]
    resp = client.post(
        "/v1/tool/intercept",
        json={
            "context": {
                "agent_id": agent_id,
                "session_id": "dry-run-hitl-session",
                "action_type": "write",
                "tool_name": "email_send",
                "tool_params": {"to": "external@gmail.com"},
            },
            "dry_run": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["disposition"] == "allow"
    assert data["metadata"]["would_disposition"] == "require_hitl"

    tickets = client.get("/v1/hitl", params={"status": "pending"}).json()["tickets"]
    dry_run_tickets = [t for t in tickets if t.get("session_id") == "dry-run-hitl-session"]
    assert dry_run_tickets == []


# --- PS-4.2 Observability Pipeline ---


@pytest.mark.parametrize(
    "agent_key,signal_type,expected_status",
    [
        ("finance", "drift_above_threshold", "under_review"),
        ("support", "safety_violation", "suspended"),
        ("hr", "repeated_guardrail_blocks", "under_review"),
        ("developer", "anomaly_high", "under_review"),
        ("finance", "hitl_sla_breach", "under_review"),
    ],
)
def test_observability_signal_types(seeded, client, agent_key, signal_type, expected_status):
    agent_id = seeded["agents"][agent_key]
    resp = client.post(
        "/v1/observability/ingest",
        json={"agent_id": agent_id, "signal_type": signal_type, "metric_value": 0.91},
    )
    assert resp.status_code == 200
    assert resp.json()["governance_status"] == expected_status

    status = client.get(f"/v1/governance/status/{agent_id}").json()
    assert status["status"] == expected_status


def test_suspended_agent_intercept_blocked(seeded, client):
    finance_id = seeded["agents"]["finance"]
    client.post(
        "/v1/observability/ingest",
        json={"agent_id": finance_id, "signal_type": "safety_violation"},
    )
    resp = client.post(
        "/v1/tool/intercept",
        json={
            "context": {
                "agent_id": finance_id,
                "session_id": "governance-hold-session",
                "action_type": "read",
                "tool_name": "db_query",
                "tool_params": {"query": "SELECT 1"},
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["disposition"] == "block"
    assert data["metadata"]["governance_hold"] is True


def test_cloudwatch_adapter_ingest(seeded, client):
    hr_id = seeded["agents"]["hr"]
    resp = client.post(
        "/v1/observability/ingest/cloudwatch",
        json={
            "agent_id": hr_id,
            "signal_type": "anomaly_high",
            "metric_value": 0.88,
            "alarm_state": "ALARM",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["governance_status"] == "under_review"
    assert resp.json().get("signal_type") == "anomaly_high"


def test_otel_adapter_ingest(seeded, client):
    developer_id = seeded["agents"]["developer"]
    resp = client.post(
        "/v1/observability/ingest/otel",
        json={
            "resource": {"attributes": {"agent.id": developer_id}},
            "scopeMetrics": [
                {
                    "metrics": [
                        {
                            "name": "sentinelai.governance.signal",
                            "gauge": {
                                "dataPoints": [
                                    {
                                        "attributes": {"signal.type": "drift_above_threshold"},
                                        "asDouble": 1.0,
                                    }
                                ]
                            },
                        }
                    ]
                }
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["governance_status"] == "under_review"


def test_sla_auto_escalation_endpoint(seeded, client):
    """PS-4.2 bonus: under-review agent past SLA auto-escalates via the sweep."""
    from datetime import datetime, timedelta, timezone

    from backend import deps

    finance_id = seeded["agents"]["finance"]
    client.post(
        "/v1/observability/ingest",
        json={"agent_id": finance_id, "signal_type": "drift_above_threshold"},
    )

    # Backdate the review clock past the 48h SLA window.
    repository = deps.repo()
    state = repository.get_governance_state(finance_id)
    state.since = datetime.now(timezone.utc) - timedelta(hours=49)
    repository.save_governance_state(state)

    result = client.post("/v1/governance/sla/check").json()
    escalated_agents = [e["agent_id"] for e in result["escalations"]]
    assert finance_id in escalated_agents

    status = client.get(f"/v1/governance/status/{finance_id}").json()
    assert status["status"] == "under_review"
    assert status["reviewer"] == "senior-reviewer"

    action_log = client.get("/v1/governance/action-log", params={"agent_id": finance_id}).json()
    sla_events = [a for a in action_log["actions"] if a["payload"].get("sla_event") == "escalation"]
    assert len(sla_events) >= 1


def test_governance_timeline_and_action_log(seeded, client):
    finance_id = seeded["agents"]["finance"]
    client.post(
        "/v1/observability/ingest",
        json={"agent_id": finance_id, "signal_type": "drift_above_threshold"},
    )
    timeline = client.get("/v1/timeline", params={"agent_id": finance_id, "limit": 20}).json()
    assert len(timeline["events"]) >= 1

    action_log = client.get("/v1/governance/action-log", params={"agent_id": finance_id}).json()
    assert len(action_log["actions"]) >= 1
