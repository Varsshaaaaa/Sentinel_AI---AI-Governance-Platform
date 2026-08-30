"""Policy engine tests (PS-10.2)."""

from datetime import datetime, timezone

import pytest

from governance.policy_engine.evaluator import PolicyEvaluator
from governance.policy_engine.loader import PolicyLoader
from shared.models.context import DataClassification, GovernanceContext
from shared.models.policy import EnforcementAction, Policy, PolicyRule


@pytest.fixture
def base_policy():
    return PolicyLoader.parse_yaml("""
apiVersion: sentinelai.io/v1
kind: Policy
metadata:
  name: test-base
spec:
  rules:
    - name: allow-reads
      priority: 10
      when:
        all:
          - context.action_type: read
      then:
        action: allow
""")


@pytest.fixture
def finance_policy():
    return PolicyLoader.parse_yaml("""
apiVersion: sentinelai.io/v1
kind: Policy
metadata:
  name: test-finance
spec:
  inherits: test-base
  rules:
    - name: bulk-delete-block
      priority: 200
      when:
        all:
          - context.action_type: delete
          - context.data_scope_size >: 100
      then:
        action: block
        reason: "Bulk delete blocked"
    - name: after-hours-hitl
      priority: 100
      when:
        all:
          - context.timestamp.hour outside: [9, 18]
          - context.action_type in: [write, delete]
      then:
        action: require_hitl
    - name: violation-suspend
      priority: 400
      when:
        - context.previous_violations_in_session >=: 3
      then:
        action: suspend_session
""")


def test_bulk_delete_blocked(base_policy, finance_policy):
    ctx = GovernanceContext(
        agent_id="a1",
        session_id="s1",
        action_type="delete",
        tool_name="db_delete",
        data_scope_size=500,
    )
    decision = PolicyEvaluator().evaluate(ctx, [base_policy, finance_policy])
    assert decision.action == EnforcementAction.BLOCK


def test_small_delete_allowed(base_policy, finance_policy):
    ctx = GovernanceContext(
        agent_id="a1",
        session_id="s1",
        action_type="delete",
        tool_name="db_delete",
        data_scope_size=5,
        timestamp=datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc),
    )
    decision = PolicyEvaluator().evaluate(ctx, [base_policy, finance_policy])
    assert decision.action == EnforcementAction.ALLOW


def test_after_hours_hitl(base_policy, finance_policy):
    ctx = GovernanceContext(
        agent_id="a1",
        session_id="s1",
        action_type="write",
        tool_name="db_write",
        timestamp=datetime(2026, 1, 15, 22, 0, tzinfo=timezone.utc),
    )
    decision = PolicyEvaluator().evaluate(ctx, [base_policy, finance_policy])
    assert decision.action == EnforcementAction.REQUIRE_HITL


def test_business_hours_no_hitl(base_policy, finance_policy):
    ctx = GovernanceContext(
        agent_id="a1",
        session_id="s1",
        action_type="write",
        tool_name="db_write",
        timestamp=datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc),
        data_scope_size=5,
    )
    decision = PolicyEvaluator().evaluate(ctx, [base_policy, finance_policy])
    assert decision.action == EnforcementAction.ALLOW


def test_violation_suspend(base_policy, finance_policy):
    ctx = GovernanceContext(
        agent_id="a1",
        session_id="s1",
        action_type="read",
        tool_name="db_query",
        previous_violations_in_session=3,
    )
    decision = PolicyEvaluator().evaluate(ctx, [base_policy, finance_policy])
    assert decision.action == EnforcementAction.SUSPEND_SESSION


def test_policy_inheritance(base_policy, finance_policy):
    loader = PolicyLoader()
    merged = loader.merge_policies(base_policy, finance_policy)
    assert any(r.name == "allow-reads" for r in merged.rules)
    assert any(r.name == "bulk-delete-block" for r in merged.rules)
