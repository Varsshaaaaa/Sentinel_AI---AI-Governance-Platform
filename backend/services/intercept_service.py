"""SentinelAI governance intercept pipeline."""

from governance.agent_waf.engine import AgentWAF
from governance.behavior_engine.engine import BehaviorEngine
from governance.compliance_engine.engine import ComplianceEngine
from governance.decision_engine.auditor import DecisionAuditor
from governance.graph_engine.service import GraphEngine
from governance.observability_pipeline.pipeline import ObservabilityPipeline
from governance.observability_pipeline.state_machine import GovernanceStateMachine
from governance.policy_engine.evaluator import PolicyEvaluator
from governance.risk_engine.engine import RiskEngine
from governance.runtime_guardrails.engine import ActionGuardrails
from shared.events.publisher import EventPublisher
from shared.models.agent import AgentStatus
from shared.models.context import GovernanceContext
from shared.models.events import EventType
from shared.models.policy import Policy
from shared.models.tool import ToolInterceptRequest, ToolInterceptResponse, WAFDisposition
from shared.storage.base import Repository


class InterceptService:
    """Orchestrates WAF → Policy → Guardrails → Audit pipeline."""

    def __init__(self, repository: Repository) -> None:
        self._repo = repository
        self._publisher = EventPublisher(repository)
        self._waf = AgentWAF(repository)
        self._policy_evaluator = PolicyEvaluator()
        self._guardrails = ActionGuardrails(repository)
        self._auditor = DecisionAuditor(repository)
        self._graph = GraphEngine(repository)
        self._behavior = BehaviorEngine(repository)
        self._risk = RiskEngine(repository, self._publisher)
        self._compliance = ComplianceEngine(repository, self._publisher)
        self._governance_sm = GovernanceStateMachine(repository, self._publisher)

    def intercept(self, request: ToolInterceptRequest) -> ToolInterceptResponse:
        ctx = request.context
        ctx.previous_violations_in_session = self._repo.get_session_violations(ctx.session_id)

        agent = self._repo.get_agent(ctx.agent_id)
        if agent and agent.status == AgentStatus.SUSPENDED:
            return ToolInterceptResponse(
                disposition="block",
                reason="Agent suspended — governance hold",
                metadata={"governance_hold": True},
            )

        if self._governance_sm.is_agent_governed_hold(ctx.agent_id):
            return ToolInterceptResponse(
                disposition="block",
                reason="Agent under governance suspension",
                metadata={"governance_hold": True},
            )

        self._auditor.log_tool_call(ctx)

        waf_result = self._waf.intercept(ctx, shadow_mode=request.shadow_mode, agent=agent)
        self._auditor.log_waf_evaluation(ctx, waf_result)
        # Record attempted tool usage in the governance graph (even if later blocked).
        self._graph.record_tool_call(ctx.agent_id, ctx.tool_name)

        if self._waf.is_probe_detected(ctx.session_id):
            self._publisher.emit(
                EventType.VIOLATION_DETECTED,
                agent_id=ctx.agent_id,
                payload={"source": "waf_probe_detection", "session_id": ctx.session_id},
            )

        dry_run_metadata: dict = {}
        waf_would_deny = waf_result.disposition == WAFDisposition.DENY and not request.shadow_mode
        if waf_would_deny and not request.dry_run:
            violation_id = self._record_waf_violation(ctx, waf_result.reason)
            self._publisher.emit(
                EventType.VIOLATION_DETECTED,
                agent_id=ctx.agent_id,
                payload={"source": "waf", "reason": waf_result.reason},
            )
            return ToolInterceptResponse(
                disposition="deny",
                waf_result=waf_result,
                reason=waf_result.reason,
                violation_id=violation_id,
            )
        if waf_would_deny and request.dry_run:
            dry_run_metadata.update(
                {
                    "dry_run": True,
                    "would_waf_disposition": "deny",
                    "would_waf_reason": waf_result.reason,
                }
            )

        policies = self._load_agent_policies(ctx.agent_id)
        policy_decision = self._policy_evaluator.evaluate(
            ctx, policies, policy_provider=self._repo.get_policy
        )
        self._auditor.log_policy_evaluation(ctx, policy_decision)

        disposition, decision, ticket_id, violation_id = self._guardrails.enforce(
            ctx, policy_decision, dry_run=request.dry_run
        )

        if policy_decision.matched_rules:
            self._publisher.emit(
                EventType.POLICY_MATCHED,
                agent_id=ctx.agent_id,
                payload={
                    "action": decision.action.value,
                    "rules": [r.rule_name for r in decision.matched_rules],
                },
            )

        if violation_id:
            self._publisher.emit(
                EventType.VIOLATION_DETECTED,
                agent_id=ctx.agent_id,
                payload={"violation_id": violation_id, "disposition": disposition},
            )

        enforced_disposition = disposition
        if request.dry_run and disposition in ("block", "deny", "require_hitl"):
            dry_run_metadata.update(
                {
                    "dry_run": True,
                    "would_disposition": disposition,
                    "would_reason": decision.reason,
                    "would_ticket_id": ticket_id,
                    "would_violation_id": violation_id,
                }
            )
            disposition = "allow"

        if not request.dry_run and enforced_disposition == "require_hitl":
            return ToolInterceptResponse(
                disposition="require_hitl",
                waf_result=waf_result,
                policy_decision=decision,
                reason=decision.reason,
                ticket_id=ticket_id,
            )

        if not request.dry_run and enforced_disposition in ("block", "deny"):
            return ToolInterceptResponse(
                disposition="block",
                waf_result=waf_result,
                policy_decision=decision,
                reason=decision.reason or "Blocked by policy",
                violation_id=violation_id,
                session_suspended=self._repo.is_session_suspended(ctx.session_id),
            )

        self._repo.record_tool_call(ctx.session_id, ctx.tool_name)
        self._behavior.record_action(ctx)
        anomaly = self._behavior.score_anomaly(ctx)
        self._risk.score_agent(ctx.agent_id, anomaly.get("anomaly_score", 0))

        if anomaly.get("is_anomalous"):
            self._governance_sm.process_signal(ctx.agent_id, "anomaly_high")

        self._publisher.emit(
            EventType.TOOL_CALLED,
            agent_id=ctx.agent_id,
            payload={
                "tool": ctx.tool_name,
                "disposition": disposition,
                "anomaly_score": anomaly.get("anomaly_score", 0),
            },
        )

        response_metadata = {"anomaly": anomaly}
        if dry_run_metadata:
            response_metadata.update(dry_run_metadata)
            if enforced_disposition != "allow":
                response_metadata["simulated_policy_action"] = decision.action.value

        return ToolInterceptResponse(
            disposition=disposition,
            waf_result=waf_result,
            policy_decision=decision,
            reason=decision.reason or "Allowed",
            ticket_id=ticket_id,
            metadata=response_metadata,
        )

    def _load_agent_policies(self, agent_id: str) -> list[Policy]:
        agent = self._repo.get_agent(agent_id)
        if not agent:
            return self._repo.list_policies()
        policies = []
        for pid in agent.policy_ids:
            p = self._repo.get_policy(pid)
            if p:
                policies.append(p)
        if not policies:
            policies = self._repo.list_policies()
        return policies

    def _record_waf_violation(self, ctx: GovernanceContext, reason: str) -> str:
        from shared.models.violation import Violation, ViolationSeverity

        v = Violation(
            agent_id=ctx.agent_id,
            session_id=ctx.session_id,
            rule_name="waf_deny",
            severity=ViolationSeverity.HIGH,
            source="agent_waf",
            reason=reason,
        )
        self._repo.save_violation(v)
        return v.violation_id
