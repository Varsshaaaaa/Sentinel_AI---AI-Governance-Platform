"""Integration tests for governance pipeline."""

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
    result = seed(force=True)
    return result


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_register_agent(client):
    resp = client.post(
        "/v1/agents/register",
        json={
            "name": "Test Agent",
            "owner": "test-team",
            "team": "Test",
            "purpose": "Testing",
            "framework": "custom",
            "risk_tier": "low",
        },
    )
    assert resp.status_code == 200
    assert "agent_id" in resp.json()["agent"]


def test_bulk_delete_blocked(seeded, client):
    finance_id = seeded["agents"]["finance"]
    session = "test-block-session"
    client.post(
        "/v1/tool/intercept",
        json={
            "context": {
                "agent_id": finance_id,
                "session_id": session,
                "action_type": "read",
                "tool_name": "db_query",
                "tool_params": {"table": "financial_records"},
                "data_scope_size": 10,
                "timestamp": "2026-01-15T14:00:00+00:00",
            },
        },
    )
    resp = client.post(
        "/v1/tool/intercept",
        json={
            "context": {
                "agent_id": finance_id,
                "session_id": session,
                "action_type": "delete",
                "tool_name": "db_delete",
                "tool_params": {"count": 500},
                "data_scope_size": 500,
                "timestamp": "2026-01-15T14:00:00+00:00",
            },
            "shadow_mode": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["disposition"] == "block"


def test_small_delete_allowed(seeded, client):
    finance_id = seeded["agents"]["finance"]
    session = "test-allow-session-2"
    client.post(
        "/v1/tool/intercept",
        json={
            "context": {
                "agent_id": finance_id,
                "session_id": session,
                "action_type": "read",
                "tool_name": "db_query",
                "tool_params": {"table": "financial_records"},
                "data_scope_size": 5,
                "timestamp": "2026-01-15T14:00:00+00:00",
            },
        },
    )
    resp = client.post(
        "/v1/tool/intercept",
        json={
            "context": {
                "agent_id": finance_id,
                "session_id": session,
                "action_type": "delete",
                "tool_name": "db_delete",
                "tool_params": {"count": 5},
                "data_scope_size": 5,
                "timestamp": "2026-01-15T14:00:00+00:00",
            },
        },
    )
    assert resp.status_code == 200
    assert resp.json()["disposition"] == "allow"


def test_external_email_hitl(seeded, client):
    support_id = seeded["agents"]["support"]
    resp = client.post(
        "/v1/tool/intercept",
        json={
            "context": {
                "agent_id": support_id,
                "session_id": "test-email-session",
                "action_type": "write",
                "tool_name": "email_send",
                "tool_params": {"to": "external@gmail.com"},
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["disposition"] == "require_hitl"
    assert data["ticket_id"] is not None


def test_hitl_approval_allows_retry_in_same_session(seeded, client):
    support_id = seeded["agents"]["support"]
    session_id = "test-hitl-retry-session"
    payload = {
        "context": {
            "agent_id": support_id,
            "session_id": session_id,
            "action_type": "write",
            "tool_name": "email_send",
            "tool_params": {"to": "external@gmail.com"},
        },
    }

    first = client.post("/v1/tool/intercept", json=payload).json()
    assert first["disposition"] == "require_hitl"
    ticket_id = first["ticket_id"]
    assert ticket_id

    approve = client.post(
        f"/v1/hitl/{ticket_id}/approve",
        json={"action": "approve", "reviewer": "test-reviewer"},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    second = client.post("/v1/tool/intercept", json=payload).json()
    assert second["disposition"] == "allow"
    assert second["ticket_id"] == ticket_id
    assert "approved" in (second.get("reason") or "").lower()


def test_decision_replay(seeded, client):
    resp = client.get("/v1/decision/replay/demo-finance-session")
    assert resp.status_code == 200
    data = resp.json()
    assert data["step_count"] > 0
    assert len(data["timeline"]) > 0


def test_graph_orphans(seeded, client):
    client.post(
        "/v1/agents/register",
        json={
            "name": "Orphan Agent",
            "owner": "test",
            "team": "Test",
            "purpose": "No policy",
            "framework": "custom",
            "policy_ids": [],
        },
    )
    resp = client.post("/v1/graph/query", json={"query_type": "orphans"})
    assert resp.status_code == 200
    assert resp.json()["metadata"]["orphan_count"] >= 1


def test_observability_pipeline(seeded, client):
    finance_id = seeded["agents"]["finance"]
    resp = client.post(
        "/v1/observability/ingest",
        json={"agent_id": finance_id, "signal_type": "safety_violation"},
    )
    assert resp.status_code == 200
    assert resp.json()["governance_status"] == "suspended"


def test_policy_copilot(client):
    resp = client.post(
        "/v1/copilot/generate-policy",
        json={
            "description": "Block any finance agent from deleting more than 100 records after business hours",
            "policy_name": "copilot-finance",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert "bulk-delete" in data["yaml_content"] or "after-hours" in data["yaml_content"]


def test_dashboard(seeded, client):
    resp = client.get("/v1/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["total_agents"] >= 4
    assert len(data["risk_heatmap"]) >= 4


def test_waf_records_after_intercept(seeded, client):
    finance_id = seeded["agents"]["finance"]
    client.post(
        "/v1/tool/intercept",
        json={
            "context": {
                "agent_id": finance_id,
                "session_id": "waf-log-session",
                "action_type": "read",
                "tool_name": "db_query",
                "tool_params": {"query": "SELECT 1"},
            },
        },
    )
    resp = client.get("/v1/waf/records", params={"agent_id": finance_id, "limit": 10})
    assert resp.status_code == 200
    records = resp.json()["records"]
    assert len(records) >= 1
    assert records[0]["tool_name"] == "db_query"


def test_waf_stats_after_intercept(seeded, client):
    finance_id = seeded["agents"]["finance"]
    resp = client.get("/v1/waf/stats", params={"agent_id": finance_id})
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total_calls"] >= 0
    assert "allowed" in stats
    assert "denied" in stats
