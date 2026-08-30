"""Guardrail scenario harness tests (PS-3.1)."""

import pytest

from governance.runtime_guardrails.simulator import (
    GuardrailScenarioHarness,
    estimate_policy_risk,
)
from governance.policy_engine.evaluator import PolicyEvaluator
from governance.policy_engine.loader import PolicyLoader
from shared.models.context import GovernanceContext
from shared.storage.memory import MemoryRepository


@pytest.fixture
def policies():
    return [
        PolicyLoader.parse_yaml(
            """
apiVersion: sentinelai.io/v1
kind: Policy
metadata:
  name: guardrail-test
spec:
  rules:
    - name: bulk-delete-block
      priority: 300
      when:
        all:
          - context.action_type: delete
          - context.data_scope_size >: 100
      then:
        action: block
        reason: Bulk delete blocked
    - name: external-email-hitl
      priority: 200
      when:
        all:
          - context.tool_name: email_send
          - context.action_type: write
      then:
        action: require_hitl
        reason: External email needs review
    - name: confidential-audit
      priority: 100
      when:
        all:
          - context.session_data_classification: confidential
      then:
        action: audit_only
        reason: Confidential read logged
"""
        )
    ]


@pytest.fixture
def harness():
    return GuardrailScenarioHarness(MemoryRepository())


def test_harness_covers_all_three_outcomes(harness, policies):
    scenarios = [
        {"name": "bulk delete", "action_type": "delete", "tool_name": "db_delete", "data_scope_size": 500, "expected": "block"},
        {"name": "external email", "action_type": "write", "tool_name": "email_send", "expected": "require_hitl"},
        {"name": "confidential read", "action_type": "read", "tool_name": "reader", "session_data_classification": "confidential", "expected": "audit_only"},
        {"name": "small delete", "action_type": "delete", "tool_name": "db_delete", "data_scope_size": 5, "expected": "allow"},
    ]
    report = harness.run(scenarios, policies=policies)
    assert report["covers_all_three_outcomes"] is True
    assert report["expectations_met"] is True
    assert report["total"] == 4


def test_harness_flags_unmet_expectation(harness, policies):
    scenarios = [
        {"name": "small delete misexpected", "action_type": "delete", "tool_name": "db_delete", "data_scope_size": 5, "expected": "block"},
    ]
    report = harness.run(scenarios, policies=policies)
    assert report["expectations_met"] is False
    assert report["results"][0]["disposition"] == "allow"


def test_harness_has_no_side_effects(policies):
    repo = MemoryRepository()
    harness = GuardrailScenarioHarness(repo)
    harness.run(
        [{"action_type": "delete", "tool_name": "db_delete", "data_scope_size": 500}],
        policies=policies,
    )
    # Simulation must not create violations or suspend sessions.
    assert repo.list_violations() == []
    assert repo.is_session_suspended("sim-session") is False


def test_policy_derived_risk_orders_by_action(policies):
    evaluator = PolicyEvaluator()
    block_ctx = GovernanceContext(
        agent_id="a", session_id="s", action_type="delete", tool_name="db_delete", data_scope_size=500
    )
    allow_ctx = GovernanceContext(
        agent_id="a", session_id="s", action_type="read", tool_name="reader"
    )
    block_risk = estimate_policy_risk(block_ctx, evaluator.evaluate(block_ctx, policies))
    allow_risk = estimate_policy_risk(allow_ctx, evaluator.evaluate(allow_ctx, policies))
    assert block_risk > allow_risk
    assert 0 <= allow_risk <= 100 and 0 <= block_risk <= 100
