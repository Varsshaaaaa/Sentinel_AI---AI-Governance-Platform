"""Agent WAF tests (PS-5.1)."""

import pytest

from governance.agent_waf.engine import AgentWAF
from shared.models.context import GovernanceContext
from shared.models.tool import WAFDisposition
from shared.storage.memory import MemoryRepository


@pytest.fixture
def waf():
    return AgentWAF(MemoryRepository())


def test_rate_limit(waf):
    ctx = GovernanceContext(
        agent_id="a1", session_id="s1", action_type="read", tool_name="db_query"
    )
    for _ in range(30):
        result = waf.intercept(ctx)
        assert result.disposition == WAFDisposition.ALLOW
    result = waf.intercept(ctx)
    assert result.disposition == WAFDisposition.DENY
    assert "rate_limit" in result.matched_rules[0]


def test_injection_blocked(waf):
    ctx = GovernanceContext(
        agent_id="a1",
        session_id="s1",
        action_type="read",
        tool_name="db_query",
        tool_params={"query": "SELECT * FROM users; DROP TABLE users;"},
    )
    result = waf.intercept(ctx)
    assert result.disposition == WAFDisposition.DENY


def test_data_scope_blocked(waf):
    ctx = GovernanceContext(
        agent_id="a1",
        session_id="s1",
        action_type="read",
        tool_name="crm_read",
        tool_params={"customer_id": "999"},
        metadata={"session_scope": {"customer_id": "123"}},
    )
    result = waf.intercept(ctx)
    assert result.disposition == WAFDisposition.DENY


def test_sequence_rule_blocked(waf):
    repo = MemoryRepository()
    waf = AgentWAF(repo)
    ctx = GovernanceContext(
        agent_id="a1",
        session_id="s1",
        action_type="write",
        tool_name="payment_process",
        tool_params={},
    )
    result = waf.intercept(ctx)
    assert result.disposition == WAFDisposition.DENY
    assert "sequence" in result.matched_rules[0]


def test_shadow_mode(waf):
    ctx = GovernanceContext(
        agent_id="a1",
        session_id="s1",
        action_type="read",
        tool_name="db_delete",
    )
    for _ in range(6):
        waf.intercept(ctx)
    result = waf.intercept(ctx, shadow_mode=True)
    assert result.disposition == WAFDisposition.SHADOW


def test_waf_stats(waf):
    ctx = GovernanceContext(
        agent_id="a1", session_id="s1", action_type="read", tool_name="db_query", tool_params={"q": "ok"}
    )
    waf.intercept(ctx)
    stats = waf.get_stats(agent_id="a1")
    assert stats.total_calls >= 1
    assert stats.allowed >= 1


def test_probe_detection(waf):
    ctx = GovernanceContext(
        agent_id="a1",
        session_id="probe-session",
        action_type="read",
        tool_name="crm_read",
        tool_params={"customer_id": "wrong"},
        metadata={"session_scope": {"customer_id": "123"}},
    )
    for _ in range(3):
        waf.intercept(ctx)
    assert waf.is_probe_detected("probe-session") is True


def test_sanitize_secrets(waf):
    ctx = GovernanceContext(
        agent_id="a1",
        session_id="s1",
        action_type="read",
        tool_name="db_query",
        tool_params={"password": "secret123", "query": "SELECT 1"},
    )
    waf.intercept(ctx)
    records = waf._repo.list_waf_records(agent_id="a1", limit=1)
    assert records[0].params_sanitized["password"] == "[REDACTED]"


def test_param_size_limit_blocked(waf):
    ctx = GovernanceContext(
        agent_id="a1",
        session_id="s1",
        action_type="write",
        tool_name="api_call",
        tool_params={"payload": "A" * 70000},
    )
    result = waf.intercept(ctx)
    assert result.disposition == WAFDisposition.DENY
    assert "size_limit" in result.matched_rules[0]


def test_sequence_allow_after_prerequisite():
    repo = MemoryRepository()
    waf = AgentWAF(repo)
    repo.record_tool_call("s-seq", "identity_verify")
    ctx = GovernanceContext(
        agent_id="a1", session_id="s-seq", action_type="write", tool_name="payment_process"
    )
    result = waf.intercept(ctx)
    assert result.disposition == WAFDisposition.ALLOW


def test_evaluation_trace_records_all_rules_up_to_trip(waf):
    ctx = GovernanceContext(
        agent_id="a1",
        session_id="s1",
        action_type="read",
        tool_name="db_query",
        tool_params={"query": "SELECT * FROM users; DROP TABLE users;--"},
    )
    result = waf.intercept(ctx)
    types = [e.rule_type for e in result.evaluations]
    assert "tool_scope" in types
    assert "rate_limit" in types
    assert "parameter_validation" in types
    tripped = [e for e in result.evaluations if not e.passed]
    assert len(tripped) == 1
    assert tripped[0].rule_type == "parameter_validation"


def test_allow_trace_all_rules_pass(waf):
    ctx = GovernanceContext(
        agent_id="a1",
        session_id="s1",
        action_type="read",
        tool_name="db_query",
        tool_params={"query": "list open tickets"},
    )
    result = waf.intercept(ctx)
    assert result.disposition == WAFDisposition.ALLOW
    assert all(e.passed for e in result.evaluations)
    assert len(result.evaluations) == 6


def test_stats_rule_type_breakdown(waf):
    ctx = GovernanceContext(
        agent_id="a1", session_id="s1", action_type="delete", tool_name="db_delete"
    )
    for _ in range(7):
        waf.intercept(ctx)
    stats = waf.get_stats(agent_id="a1")
    assert stats.by_rule_type.get("rate_limit", 0) >= 1
    assert stats.denied >= 1


def test_describe_config_defaults(waf):
    cfg = waf.describe_config()
    assert cfg.rate_window_seconds == 60
    assert "db_delete" in cfg.rate_limits
    assert cfg.injection_patterns
    assert cfg.sequence_rules.get("payment_process") == ["identity_verify"]


def test_acceptance_suite_all_pass():
    from governance.agent_waf.acceptance import WAFAcceptanceSuite

    report = WAFAcceptanceSuite().run()
    assert report["passed"] is True, [c for c in report["criteria"] if not c["passed"]]
    assert report["summary"]["failed"] == 0
    ids = {c["id"] for c in report["criteria"]}
    assert {
        "rate_limit",
        "parameter_blocklist",
        "param_size",
        "data_scope",
        "sequence_block",
        "sequence_allow",
        "legitimate_allow",
        "shadow_mode",
        "logging_completeness",
    } <= ids

