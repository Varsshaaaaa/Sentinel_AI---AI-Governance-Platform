"""Guardrail scenario harness (PS-3.1).

Runs a sample agent through a batch of scenarios and reports which guardrail
outcome each one triggers (block / require_hitl / warn / audit_only / allow),
without mutating any state. This is the "simulation harness" the PS requires to
demonstrate that each of the outcome types fires on matching tool calls.
"""

from typing import Any

from governance.policy_engine.evaluator import PolicyEvaluator
from shared.models.context import DataClassification, GovernanceContext
from shared.models.policy import EnforcementAction, Policy
from shared.storage.base import Repository

# Map the enforcement action to the PS-3.1 disposition vocabulary.
_ACTION_TO_DISPOSITION = {
    EnforcementAction.BLOCK: "block",
    EnforcementAction.SUSPEND_SESSION: "block",
    EnforcementAction.REQUIRE_HITL: "require_hitl",
    EnforcementAction.APPLY_POLICY: "require_hitl",
    EnforcementAction.WARN: "warn",
    EnforcementAction.AUDIT_ONLY: "audit_only",
    EnforcementAction.ALLOW: "allow",
}

# PS-3.1's three canonical outcomes (log_and_allow == audit_only here).
REQUIRED_OUTCOMES = {"block", "require_hitl", "audit_only"}


class GuardrailScenarioHarness:
    """Evaluates scenarios against policy without side effects."""

    def __init__(self, repository: Repository) -> None:
        self._repo = repository
        self._evaluator = PolicyEvaluator()

    def run(
        self,
        scenarios: list[dict[str, Any]],
        policies: list[Policy] | None = None,
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        outcomes_seen: set[str] = set()

        for scenario in scenarios:
            ctx = self._to_context(scenario)
            pols = policies if policies is not None else self._load_policies(ctx.agent_id)
            decision = self._evaluator.evaluate(
                ctx, pols, policy_provider=self._repo.get_policy
            )
            disposition = _ACTION_TO_DISPOSITION.get(decision.action, "allow")
            outcomes_seen.add(disposition)
            results.append(
                {
                    "name": scenario.get("name", f"{ctx.tool_name}:{ctx.action_type}"),
                    "disposition": disposition,
                    "action": decision.action.value,
                    "matched_rules": [r.rule_name for r in decision.matched_rules],
                    "reason": decision.reason,
                    "risk_score": estimate_policy_risk(ctx, decision),
                    "expected": scenario.get("expected"),
                    "matched_expectation": (
                        scenario.get("expected") is None
                        or scenario.get("expected") == disposition
                    ),
                }
            )

        return {
            "total": len(results),
            "outcomes_covered": sorted(outcomes_seen),
            "covers_all_three_outcomes": REQUIRED_OUTCOMES.issubset(outcomes_seen),
            "expectations_met": all(r["matched_expectation"] for r in results),
            "results": results,
        }

    def _load_policies(self, agent_id: str) -> list[Policy]:
        agent = self._repo.get_agent(agent_id)
        if agent:
            loaded = [self._repo.get_policy(pid) for pid in agent.policy_ids]
            loaded = [p for p in loaded if p]
            if loaded:
                return loaded
        return self._repo.list_policies()

    def _to_context(self, scenario: dict[str, Any]) -> GovernanceContext:
        ctx_data = scenario.get("context", scenario)
        classification = ctx_data.get("session_data_classification", "internal")
        try:
            dc = DataClassification(classification)
        except ValueError:
            dc = DataClassification.INTERNAL
        return GovernanceContext(
            agent_id=ctx_data.get("agent_id", "sim-agent"),
            user_id=ctx_data.get("user_id", "sim-user"),
            session_id=ctx_data.get("session_id", "sim-session"),
            action_type=ctx_data.get("action_type", "read"),
            tool_name=ctx_data.get("tool_name", "unknown"),
            tool_params=ctx_data.get("tool_params", {}),
            data_scope_size=ctx_data.get("data_scope_size", 0),
            session_data_classification=dc,
            previous_violations_in_session=ctx_data.get("previous_violations_in_session", 0),
        )


def estimate_policy_risk(context: GovernanceContext, decision: Any) -> int:
    """Policy-derived risk score (0-100).

    Unlike a fixed heuristic, this is anchored to the enforcement decision that
    the policy engine actually produced, then adjusted by context sensitivity.
    """
    action_weight = {
        "block": 80,
        "suspend_session": 90,
        "require_hitl": 55,
        "apply_policy": 55,
        "warn": 30,
        "audit_only": 20,
        "allow": 5,
    }
    score = action_weight.get(getattr(decision.action, "value", "allow"), 5)

    # Each matched rule adds weight — more governance friction ⇒ higher risk.
    score += min(15, 5 * len(getattr(decision, "matched_rules", [])))

    if context.action_type in ("delete", "write"):
        score += 8
    if context.data_scope_size > 100:
        score += 10
    elif context.data_scope_size > 50:
        score += 5
    if context.session_data_classification.value in ("PHI", "PII", "confidential"):
        score += 10
    return min(100, score)
