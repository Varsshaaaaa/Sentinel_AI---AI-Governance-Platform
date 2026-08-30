"""Observability signal classifier (PS-4.2)."""

from typing import Any

from governance.observability_pipeline.state_machine import GovernanceStateMachine
from shared.events.publisher import EventPublisher
from shared.models.events import EventType
from shared.storage.base import Repository


class ObservabilityPipeline:
    """Ingests observability signals and triggers governance workflows."""

    SIGNAL_TYPES = [
        "drift_above_threshold",
        "safety_violation",
        "repeated_guardrail_blocks",
        "anomaly_high",
        "hitl_sla_breach",
    ]

    def __init__(self, repository: Repository, publisher: EventPublisher) -> None:
        self._repo = repository
        self._publisher = publisher
        self._state_machine = GovernanceStateMachine(repository, publisher)

    def ingest(self, signal: dict[str, Any]) -> dict[str, Any]:
        signal_type = signal.get("signal_type", "")
        agent_id = signal.get("agent_id", "")
        if not agent_id:
            raise ValueError("agent_id is required")

        if signal_type not in self.SIGNAL_TYPES:
            raise ValueError(f"Unsupported signal type: {signal_type}. Supported: {self.SIGNAL_TYPES}")

        state = self._state_machine.process_signal(
            agent_id,
            signal_type,
            reviewer=signal.get("reviewer"),
        )

        self._publisher.emit(
            EventType.COMPLIANCE_CHANGED,
            agent_id=agent_id,
            payload={
                "signal_type": signal_type,
                "governance_status": state.status.value,
                "metric_value": signal.get("metric_value"),
                "source": signal.get("source", "observability"),
            },
        )

        return {
            "agent_id": agent_id,
            "signal_type": signal_type,
            "governance_status": state.status.value,
            "action_taken": state.trigger_signal,
            "reviewer": state.reviewer,
        }

    def get_status(self, agent_id: str) -> dict[str, Any]:
        state = self._state_machine.get_state(agent_id)
        return {
            "agent_id": agent_id,
            "status": state.status.value,
            "since": state.since.isoformat(),
            "trigger_signal": state.trigger_signal,
            "reviewer": state.reviewer,
        }

    def list_action_log(self, agent_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        events = self._repo.list_events(agent_id=agent_id, limit=limit)
        return [
            {
                "event_id": e.event_id,
                "event_type": e.event_type.value,
                "agent_id": e.agent_id,
                "timestamp": e.timestamp.isoformat(),
                "payload": e.payload,
            }
            for e in events
            if e.event_type
            in (EventType.GOVERNANCE_STATUS_CHANGED, EventType.COMPLIANCE_CHANGED, EventType.AGENT_SUSPENDED)
        ]
