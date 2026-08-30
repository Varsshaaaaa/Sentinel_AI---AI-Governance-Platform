"""HITL approval satisfies subsequent intercept in the same session."""

from governance.policy_engine.evaluator import PolicyEvaluator
from governance.policy_engine.loader import PolicyLoader
from governance.runtime_guardrails.engine import ActionGuardrails
from shared.models.context import GovernanceContext
from shared.models.policy import EnforcementAction
from shared.storage.memory import MemoryRepository


def test_approved_hitl_ticket_allows_same_action_retry():
    repo = MemoryRepository()
    guardrails = ActionGuardrails(repo)
    policies = [
        PolicyLoader.parse_yaml(
            """
apiVersion: sentinelai.io/v1
kind: Policy
metadata:
  name: hitl-retry-test
spec:
  rules:
    - name: external-email-hitl
      priority: 200
      when:
        all:
          - context.tool_name: email_send
          - context.action_type: write
      then:
        action: require_hitl
        reason: External email needs review
"""
        )
    ]
    evaluator = PolicyEvaluator()
    ctx = GovernanceContext(
        agent_id="agent-support",
        session_id="session-hitl-retry",
        action_type="write",
        tool_name="email_send",
        tool_params={"to": "external@gmail.com", "subject": "Hello"},
    )

    decision = evaluator.evaluate(ctx, policies)
    assert decision.action == EnforcementAction.REQUIRE_HITL

    first = guardrails.enforce(ctx, decision)
    assert first[0] == "require_hitl"
    ticket_id = first[2]
    assert ticket_id

    repo.update_hitl_ticket(ticket_id, {"status": "approved", "reviewer": "admin"})

    second = guardrails.enforce(ctx, decision)
    assert second[0] == "allow"
    assert second[2] == ticket_id
    assert "approved" in (second[1].reason or "").lower()


def test_rejected_hitl_ticket_does_not_allow_retry():
    repo = MemoryRepository()
    guardrails = ActionGuardrails(repo)
    policies = [
        PolicyLoader.parse_yaml(
            """
apiVersion: sentinelai.io/v1
kind: Policy
metadata:
  name: hitl-reject-test
spec:
  rules:
    - name: external-email-hitl
      priority: 200
      when:
        context.tool_name: email_send
      then:
        action: require_hitl
        reason: External email needs review
"""
        )
    ]
    evaluator = PolicyEvaluator()
    ctx = GovernanceContext(
        agent_id="agent-support",
        session_id="session-hitl-reject",
        action_type="write",
        tool_name="email_send",
        tool_params={"to": "external@gmail.com"},
    )
    decision = evaluator.evaluate(ctx, policies)

    first = guardrails.enforce(ctx, decision)
    ticket_id = first[2]
    repo.update_hitl_ticket(ticket_id, {"status": "rejected", "reviewer": "admin"})

    second = guardrails.enforce(ctx, decision)
    assert second[0] == "require_hitl"
    assert second[2] != ticket_id
