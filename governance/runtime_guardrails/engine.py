"""Action Guardrails — pre-execution enforcement (PS-3.1)."""

from uuid import uuid4

from shared.models.context import GovernanceContext
from shared.models.policy import EnforcementAction, EnforcementDecision
from shared.models.violation import Violation, ViolationSeverity
from shared.storage.base import Repository


class ActionGuardrails:
    """Final enforcement layer for agent actions."""

    def __init__(self, repository: Repository) -> None:
        self._repo = repository

    def enforce(
        self,
        context: GovernanceContext,
        decision: EnforcementDecision,
        *,
        dry_run: bool = False,
    ) -> tuple[str, EnforcementDecision, str | None, str | None]:
        """
        Returns: (disposition, decision, ticket_id, violation_id)
        """
        if self._repo.is_session_suspended(context.session_id):
            return "block", decision, None, (
                None
                if dry_run
                else self._record_violation(
                    context, decision, "Session suspended due to repeated violations"
                )
            )

        action = decision.action

        if action == EnforcementAction.BLOCK:
            violation_id = (
                None
                if dry_run
                else self._record_violation(context, decision, decision.reason)
            )
            return "block", decision, None, violation_id

        if action == EnforcementAction.SUSPEND_SESSION:
            if not dry_run:
                self._repo.suspend_session(context.session_id)
            violation_id = (
                None
                if dry_run
                else self._record_violation(context, decision, "Session suspended by policy")
            )
            decision.action = EnforcementAction.BLOCK
            return "block", decision, None, violation_id

        if action == EnforcementAction.REQUIRE_HITL:
            if not dry_run:
                approved = self._repo.find_approved_hitl_ticket(
                    context.session_id,
                    context.tool_name,
                    context.tool_params,
                )
                if approved:
                    approved_id = approved.get("ticket_id")
                    decision.ticket_id = approved_id
                    decision.requires_hitl = False
                    decision.reason = (
                        f"Allowed — HITL ticket {approved_id} approved for this action"
                    )
                    return "allow", decision, approved_id, None

            ticket_id = None if dry_run else self._create_hitl_ticket(context, decision)
            decision.ticket_id = ticket_id
            decision.requires_hitl = True
            return "require_hitl", decision, ticket_id, None

        if action == EnforcementAction.WARN:
            if not dry_run:
                self._repo.increment_session_violations(context.session_id)
            return "warn", decision, None, None

        if action == EnforcementAction.AUDIT_ONLY:
            return "audit_only", decision, None, None

        return "allow", decision, None, None

    def _record_violation(
        self, context: GovernanceContext, decision: EnforcementDecision, reason: str
    ) -> str:
        rule_name = decision.matched_rules[0].rule_name if decision.matched_rules else "unknown"
        severity = ViolationSeverity.HIGH if decision.action == EnforcementAction.BLOCK else ViolationSeverity.MEDIUM
        violation = Violation(
            agent_id=context.agent_id,
            session_id=context.session_id,
            rule_name=rule_name,
            severity=severity,
            source="guardrails",
            reason=reason or decision.reason,
            details={"action": decision.action.value, "tool": context.tool_name},
        )
        self._repo.save_violation(violation)
        self._repo.increment_session_violations(context.session_id)
        return violation.violation_id

    def _create_hitl_ticket(
        self, context: GovernanceContext, decision: EnforcementDecision
    ) -> str:
        ticket_id = f"hitl-{uuid4().hex[:12]}"
        ticket = {
            "ticket_id": ticket_id,
            "agent_id": context.agent_id,
            "session_id": context.session_id,
            "user_id": context.user_id,
            "tool_name": context.tool_name,
            "tool_params": context.tool_params,
            "action_type": context.action_type,
            "reason": decision.reason,
            "matched_rules": [r.model_dump() for r in decision.matched_rules],
            "status": "pending",
            "risk_score": self._estimate_risk(context, decision),
        }
        self._repo.create_hitl_ticket(ticket)
        return ticket_id

    def _estimate_risk(self, context: GovernanceContext, decision: EnforcementDecision) -> int:
        # Policy-derived: anchored to the actual enforcement decision + matched
        # rules, then adjusted for context sensitivity (see simulator module).
        from governance.runtime_guardrails.simulator import estimate_policy_risk

        return estimate_policy_risk(context, decision)
