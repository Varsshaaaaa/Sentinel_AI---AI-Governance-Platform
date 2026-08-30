"""Governance SLA monitor tests (PS-4.2 bonus — auto-escalation)."""

from datetime import datetime, timedelta, timezone

import pytest

from governance.observability_pipeline.sla import GovernanceSLAMonitor
from governance.observability_pipeline.state_machine import GovernanceStateMachine
from shared.events.publisher import EventPublisher
from shared.models.events import EventType
from shared.models.governance import GovernanceStatus
from shared.storage.memory import MemoryRepository


@pytest.fixture
def repo():
    return MemoryRepository()


@pytest.fixture
def publisher(repo):
    return EventPublisher(repo)


def _put_under_review(repo, publisher, agent_id="agent-x", hours_ago=0.0):
    sm = GovernanceStateMachine(repo, publisher)
    sm.process_signal(agent_id, "drift_above_threshold")
    state = repo.get_governance_state(agent_id)
    state.since = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    repo.save_governance_state(state)
    return state


def test_no_action_before_reminder_window(repo, publisher):
    _put_under_review(repo, publisher, hours_ago=10)
    monitor = GovernanceSLAMonitor(repo, publisher, sla_hours=48)
    result = monitor.check_slas()
    assert result["reminders"] == []
    assert result["escalations"] == []


def test_reminder_fires_at_half_sla(repo, publisher):
    _put_under_review(repo, publisher, hours_ago=25)
    monitor = GovernanceSLAMonitor(repo, publisher, sla_hours=48)
    result = monitor.check_slas()
    assert len(result["reminders"]) == 1
    assert result["escalations"] == []
    state = repo.get_governance_state("agent-x")
    assert state.last_reminder_at is not None
    assert state.escalation_level == 0


def test_reminder_is_sent_only_once(repo, publisher):
    _put_under_review(repo, publisher, hours_ago=25)
    monitor = GovernanceSLAMonitor(repo, publisher, sla_hours=48)
    monitor.check_slas()
    result = monitor.check_slas()
    assert result["reminders"] == []


def test_escalation_fires_at_sla_breach(repo, publisher):
    _put_under_review(repo, publisher, hours_ago=49)
    monitor = GovernanceSLAMonitor(repo, publisher, sla_hours=48)
    result = monitor.check_slas()
    assert len(result["escalations"]) == 1
    esc = result["escalations"][0]
    assert esc["escalation_level"] == 1
    assert esc["escalated_to"] == "senior-reviewer"

    state = repo.get_governance_state("agent-x")
    assert state.status == GovernanceStatus.UNDER_REVIEW
    assert state.escalation_level == 1
    assert state.reviewer == "senior-reviewer"


def test_escalation_records_compliance_event(repo, publisher):
    _put_under_review(repo, publisher, hours_ago=49)
    GovernanceSLAMonitor(repo, publisher, sla_hours=48).check_slas()
    events = repo.list_events(agent_id="agent-x")
    compliance = [
        e
        for e in events
        if e.event_type == EventType.COMPLIANCE_CHANGED
        and e.payload.get("sla_event") == "escalation"
    ]
    assert len(compliance) == 1
    assert compliance[0].payload["compliance_event"] is True


def test_second_breach_escalates_to_next_tier(repo, publisher):
    _put_under_review(repo, publisher, hours_ago=49)
    monitor = GovernanceSLAMonitor(repo, publisher, sla_hours=48)
    monitor.check_slas()
    # Still under review, now push past the second SLA window (2 * 48h).
    state = repo.get_governance_state("agent-x")
    state.since = datetime.now(timezone.utc) - timedelta(hours=97)
    repo.save_governance_state(state)
    result = monitor.check_slas()
    assert result["escalations"][0]["escalation_level"] == 2
    assert result["escalations"][0]["escalated_to"] == "governance-lead"


def test_repeated_signal_does_not_reset_sla_clock(repo, publisher):
    """A re-triggered same-status signal must not reset the `since` clock."""
    state = _put_under_review(repo, publisher, hours_ago=40)
    original_since = state.since
    sm = GovernanceStateMachine(repo, publisher)
    sm.process_signal("agent-x", "drift_above_threshold")
    refreshed = repo.get_governance_state("agent-x")
    assert refreshed.since == original_since
    assert refreshed.status == GovernanceStatus.UNDER_REVIEW


def test_green_agents_are_ignored(repo, publisher):
    # Never signalled → default GREEN state isn't even persisted; ensure a
    # persisted green state is skipped.
    sm = GovernanceStateMachine(repo, publisher)
    sm.get_state("agent-green")  # persists a GREEN state
    monitor = GovernanceSLAMonitor(repo, publisher, sla_hours=48)
    result = monitor.check_slas()
    assert result["reminders"] == []
    assert result["escalations"] == []
