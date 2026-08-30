"""Governance SLA monitor — auto-escalation for stale reviews (PS-4.2 bonus).

An agent that enters ``under_review`` must not sit there indefinitely. This
monitor is meant to be invoked on a schedule (EventBridge → Lambda every N
minutes, or ``POST /v1/governance/sla/check``). It scans every agent currently
``under_review`` and:

* at 50% of the SLA window, emits a one-time reminder;
* at 100% of the SLA window (default 48h), auto-escalates to the next reviewer
  tier and records a compliance event.

The clock is anchored to ``GovernanceState.since``, which the state machine
preserves across repeated same-status signals so the SLA cannot be reset by
re-triggering.
"""

from datetime import datetime, timezone
from typing import Any

from shared.events.publisher import EventPublisher
from shared.models.events import EventType
from shared.models.governance import GovernanceState, GovernanceStatus
from shared.storage.base import Repository

# Escalation ladder: each SLA breach bumps the review to the next tier.
REVIEWER_TIERS = ["l1-reviewer", "senior-reviewer", "governance-lead", "ciso"]


class GovernanceSLAMonitor:
    """Enforces time-bound SLAs on agents held in ``under_review``."""

    def __init__(
        self,
        repository: Repository,
        publisher: EventPublisher,
        sla_hours: float = 48.0,
        reminder_fraction: float = 0.5,
    ) -> None:
        self._repo = repository
        self._publisher = publisher
        self._sla_hours = sla_hours
        self._reminder_fraction = reminder_fraction

    def check_slas(self, now: datetime | None = None) -> dict[str, Any]:
        """Evaluate all under-review agents against their SLA.

        Returns a summary of reminders sent and escalations performed. Safe to
        call repeatedly — reminders and each escalation level fire at most once.
        """
        now = now or datetime.now(timezone.utc)
        reminded: list[dict[str, Any]] = []
        escalated: list[dict[str, Any]] = []

        for state in self._repo.list_governance_states(status=GovernanceStatus.UNDER_REVIEW.value):
            elapsed_hours = self._elapsed_hours(state, now)
            deadline_hours = self._sla_hours * (state.escalation_level + 1)

            if elapsed_hours >= deadline_hours:
                escalated.append(self._escalate(state, elapsed_hours, now))
            elif (
                elapsed_hours >= self._sla_hours * self._reminder_fraction
                and state.last_reminder_at is None
            ):
                reminded.append(self._remind(state, elapsed_hours, now))

        return {
            "checked_at": now.isoformat(),
            "sla_hours": self._sla_hours,
            "reminders": reminded,
            "escalations": escalated,
        }

    def _elapsed_hours(self, state: GovernanceState, now: datetime) -> float:
        since = state.since
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        return (now - since).total_seconds() / 3600.0

    def _remind(self, state: GovernanceState, elapsed_hours: float, now: datetime) -> dict[str, Any]:
        state.last_reminder_at = now
        self._repo.save_governance_state(state)
        self._publisher.emit(
            EventType.GOVERNANCE_STATUS_CHANGED,
            agent_id=state.agent_id,
            payload={
                "sla_event": "reminder",
                "elapsed_hours": round(elapsed_hours, 2),
                "sla_hours": self._sla_hours,
                "reviewer": state.reviewer,
                "message": f"Review pending {round(elapsed_hours, 1)}h — {self._sla_hours}h SLA half elapsed",
            },
        )
        return {
            "agent_id": state.agent_id,
            "elapsed_hours": round(elapsed_hours, 2),
            "reviewer": state.reviewer,
        }

    def _escalate(self, state: GovernanceState, elapsed_hours: float, now: datetime) -> dict[str, Any]:
        state.escalation_level += 1
        next_reviewer = REVIEWER_TIERS[min(state.escalation_level, len(REVIEWER_TIERS) - 1)]
        state.reviewer = next_reviewer
        state.notes = (
            f"SLA breach #{state.escalation_level}: exceeded "
            f"{self._sla_hours}h without action; escalated to {next_reviewer}"
        )
        self._repo.save_governance_state(state)

        # A breached governance SLA is itself a compliance event.
        self._publisher.emit(
            EventType.COMPLIANCE_CHANGED,
            agent_id=state.agent_id,
            payload={
                "sla_event": "escalation",
                "escalation_level": state.escalation_level,
                "elapsed_hours": round(elapsed_hours, 2),
                "sla_hours": self._sla_hours,
                "escalated_to": next_reviewer,
                "compliance_event": True,
                "message": (
                    f"HITL/governance SLA breached after {round(elapsed_hours, 1)}h — "
                    f"auto-escalated to {next_reviewer}"
                ),
            },
        )
        return {
            "agent_id": state.agent_id,
            "escalation_level": state.escalation_level,
            "elapsed_hours": round(elapsed_hours, 2),
            "escalated_to": next_reviewer,
        }
