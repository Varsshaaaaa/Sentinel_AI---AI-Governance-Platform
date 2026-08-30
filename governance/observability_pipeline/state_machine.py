"""Governance state machine (PS-4.2)."""

from datetime import datetime, timezone

from shared.models.agent import AgentStatus
from shared.models.events import EventType
from shared.models.governance import GovernanceState, GovernanceStatus
from shared.storage.base import Repository
from shared.events.publisher import EventPublisher

VALID_TRANSITIONS: dict[GovernanceStatus, set[GovernanceStatus]] = {
    GovernanceStatus.GREEN: {GovernanceStatus.UNDER_REVIEW, GovernanceStatus.SUSPENDED},
    GovernanceStatus.UNDER_REVIEW: {GovernanceStatus.SUSPENDED, GovernanceStatus.REMEDIATED},
    GovernanceStatus.SUSPENDED: {GovernanceStatus.UNDER_REVIEW},
    GovernanceStatus.REMEDIATED: {GovernanceStatus.GREEN},
}


SIGNAL_ACTIONS: dict[str, tuple[GovernanceStatus, str]] = {
    "drift_above_threshold": (GovernanceStatus.UNDER_REVIEW, "Model drift detected — reassessment required"),
    "safety_violation": (GovernanceStatus.SUSPENDED, "Safety violation — agent suspended"),
    "repeated_guardrail_blocks": (GovernanceStatus.UNDER_REVIEW, "Escalated to compliance team"),
    "anomaly_high": (GovernanceStatus.UNDER_REVIEW, "Behavioral anomaly detected"),
    "hitl_sla_breach": (GovernanceStatus.UNDER_REVIEW, "HITL SLA breach — compliance event"),
    "guardrail_inactive": (GovernanceStatus.UNDER_REVIEW, "Guardrail may be inactive"),
    "manual_review_complete": (GovernanceStatus.REMEDIATED, "Manual review completed"),
    "approval_granted": (GovernanceStatus.GREEN, "Governance approval granted"),
}


class GovernanceStateMachine:
    def __init__(self, repository: Repository, publisher: EventPublisher) -> None:
        self._repo = repository
        self._publisher = publisher

    def get_state(self, agent_id: str) -> GovernanceState:
        state = self._repo.get_governance_state(agent_id)
        if state is None:
            state = GovernanceState(agent_id=agent_id, status=GovernanceStatus.GREEN)
            self._repo.save_governance_state(state)
        return state

    def transition(
        self,
        agent_id: str,
        target_status: GovernanceStatus,
        trigger_signal: str,
        reviewer: str | None = None,
    ) -> GovernanceState:
        current = self.get_state(agent_id)
        allowed = VALID_TRANSITIONS.get(current.status, set())
        is_self_signal = target_status == current.status
        if target_status not in allowed and not is_self_signal:
            raise ValueError(
                f"Invalid transition: {current.status.value} → {target_status.value}"
            )

        # A repeated signal that does not change status must NOT reset the SLA
        # clock (`since`) or the escalation state — otherwise an agent could
        # dodge SLA breach forever by re-triggering the same signal.
        state = GovernanceState(
            agent_id=agent_id,
            status=target_status,
            reviewer=reviewer if reviewer is not None else (current.reviewer if is_self_signal else None),
            trigger_signal=trigger_signal,
            since=current.since if is_self_signal else datetime.now(timezone.utc),
            escalation_level=current.escalation_level if is_self_signal else 0,
            last_reminder_at=current.last_reminder_at if is_self_signal else None,
        )
        self._repo.save_governance_state(state)

        if target_status == GovernanceStatus.SUSPENDED:
            agent = self._repo.get_agent(agent_id)
            if agent:
                from shared.models.agent import AgentStatus as AS

                agent.status = AS.SUSPENDED
                self._repo.update_agent(agent)
            self._publisher.emit(
                EventType.AGENT_SUSPENDED,
                agent_id=agent_id,
                payload={"trigger": trigger_signal},
            )

        self._publisher.emit(
            EventType.GOVERNANCE_STATUS_CHANGED,
            agent_id=agent_id,
            payload={
                "from_status": current.status.value,
                "to_status": target_status.value,
                "trigger_signal": trigger_signal,
            },
        )
        return state

    def process_signal(self, agent_id: str, signal_type: str, reviewer: str | None = None) -> GovernanceState:
        if signal_type not in SIGNAL_ACTIONS:
            raise ValueError(f"Unknown signal type: {signal_type}")

        target_status, message = SIGNAL_ACTIONS[signal_type]
        current = self.get_state(agent_id)

        if signal_type == "approval_granted" and current.status == GovernanceStatus.SUSPENDED:
            target_status = GovernanceStatus.UNDER_REVIEW

        try:
            return self.transition(agent_id, target_status, signal_type, reviewer)
        except ValueError:
            return current

    def is_agent_governed_hold(self, agent_id: str) -> bool:
        state = self.get_state(agent_id)
        return state.status == GovernanceStatus.SUSPENDED
