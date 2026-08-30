"""Policy simulation against historical sessions (PS-10.2 bonus)."""

from typing import Any

from shared.models.audit import AuditStep
from shared.models.context import DataClassification, GovernanceContext
from shared.models.policy import EnforcementAction, Policy
from governance.policy_engine.evaluator import PolicyEvaluator


class SimulationResult:
    def __init__(self) -> None:
        self.total_actions: int = 0
        self.would_block: int = 0
        self.would_hitl: int = 0
        self.would_warn: int = 0
        self.unchanged: int = 0
        self.details: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_actions": self.total_actions,
            "would_block": self.would_block,
            "would_hitl": self.would_hitl,
            "would_warn": self.would_warn,
            "unchanged": self.unchanged,
            "false_positive_estimate": self.would_warn,
            "risk_improvement_score": min(100, self.would_block * 10 + self.would_hitl * 5),
            "details": self.details,
        }


class PolicySimulator:
    def __init__(self) -> None:
        self._evaluator = PolicyEvaluator()

    def simulate(
        self,
        steps: list[AuditStep],
        new_policies: list[Policy],
        old_policies: list[Policy] | None = None,
    ) -> dict[str, Any]:
        result = SimulationResult()
        old_evaluator = PolicyEvaluator()

        for step in steps:
            if step.step_type.value not in ("tool_call",):
                continue

            ctx = self._step_to_context(step)
            new_decision = self._evaluator.evaluate(ctx, new_policies)
            old_decision = (
                old_evaluator.evaluate(ctx, old_policies) if old_policies else None
            )

            result.total_actions += 1
            changed = old_decision is None or new_decision.action != old_decision.action

            if new_decision.action == EnforcementAction.BLOCK:
                result.would_block += 1
            elif new_decision.action == EnforcementAction.REQUIRE_HITL:
                result.would_hitl += 1
            elif new_decision.action in {EnforcementAction.WARN, EnforcementAction.AUDIT_ONLY}:
                result.would_warn += 1
            else:
                result.unchanged += 1

            if changed:
                result.details.append(
                    {
                        "session_id": step.session_id,
                        "step_sequence": step.step_sequence,
                        "tool": ctx.tool_name,
                        "new_action": new_decision.action.value,
                        "old_action": old_decision.action.value if old_decision else None,
                        "matched_rules": [r.rule_name for r in new_decision.matched_rules],
                    }
                )

        return result.to_dict()

    def _step_to_context(self, step: AuditStep) -> GovernanceContext:
        content = step.content
        classification = content.get("session_data_classification", "internal")
        try:
            dc = DataClassification(classification)
        except ValueError:
            dc = DataClassification.INTERNAL

        return GovernanceContext(
            agent_id=step.agent_id,
            user_id=step.user_id,
            session_id=step.session_id,
            action_type=content.get("action_type", "read"),
            tool_name=content.get("tool_name", "unknown"),
            tool_params=content.get("tool_params", {}),
            data_scope_size=content.get("data_scope_size", 0),
            session_data_classification=dc,
            previous_violations_in_session=content.get("previous_violations_in_session", 0),
        )
