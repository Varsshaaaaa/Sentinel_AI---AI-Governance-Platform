"""Decision Path Auditor tests (PS-7.1)."""

import pytest

from governance.decision_engine.auditor import DecisionAuditor
from shared.models.audit import StepType
from shared.storage.memory import MemoryRepository


@pytest.fixture
def repo():
    return MemoryRepository()


@pytest.fixture
def auditor(repo):
    return DecisionAuditor(repo)


def _three_step_path(auditor, repo, session_id="sess-1"):
    auditor.log_step(session_id, "agent-1", "user-1", StepType.INPUT, {"query": "loan status"})
    auditor.log_step(
        session_id,
        "agent-1",
        "user-1",
        StepType.TOOL_CALL,
        {"tool_name": "credit_api", "tool_params": {"customer_id": "c-9"}},
    )
    auditor.log_step(
        session_id,
        "agent-1",
        "user-1",
        StepType.POLICY_EVALUATION,
        {"action": "require_hitl", "matched_rules": [{"rule_name": "high-value-loan"}]},
    )
    return repo.get_decision_path(session_id)


def test_sequences_are_unique_across_separate_auditors(repo):
    """Regression: a new auditor per request must not reset the sequence."""
    a1 = DecisionAuditor(repo)
    a1.log_step("sess-x", "agent-1", "user-1", StepType.INPUT, {"q": 1})
    a2 = DecisionAuditor(repo)  # simulates a fresh Lambda instance
    a2.log_step("sess-x", "agent-1", "user-1", StepType.TOOL_CALL, {"tool_name": "t"})
    path = repo.get_decision_path("sess-x")
    sequences = [s.step_sequence for s in path.steps]
    assert sequences == [1, 2]
    assert len(set(sequences)) == 2


def test_three_step_path_reconstructed(auditor, repo):
    path = _three_step_path(auditor, repo)
    assert len(path.steps) == 3
    assert [s.step_type for s in path.steps] == [
        StepType.INPUT,
        StepType.TOOL_CALL,
        StepType.POLICY_EVALUATION,
    ]


def test_pii_redaction_covers_multiple_types():
    data = {
        "note": "Contact john@x.com or 555-123-4567, SSN 123-45-6789, IP 10.0.0.5",
        "name": "Jane Doe",
    }
    red = DecisionAuditor.redact(data)
    assert "john@x.com" not in red["note"]
    assert "123-45-6789" not in red["note"]
    assert "10.0.0.5" not in red["note"]
    assert red["name"] == "[NAME_REDACTED]"


def test_redaction_recurses_into_lists():
    data = {"items": [{"email": "a@b.com"}, "call 555-123-4567"]}
    red = DecisionAuditor.redact(data)
    assert red["items"][0]["email"] == "[EMAIL_REDACTED]"
    assert "555-123-4567" not in red["items"][1]


def test_challenge_response_cites_rules_and_tools(auditor, repo):
    path = _three_step_path(auditor, repo)
    result = auditor.generate_challenge_response(path, challenge_question="Why was I declined?")
    assert result["final_action"] == "require_hitl"
    assert "high-value-loan" in result["rules_applied"]
    assert "credit_api" in result["tools_used"]
    assert "high-value-loan" in result["draft_response"]
    assert result["challenge_question"] == "Why was I declined?"


def test_challenge_response_handles_no_rules(auditor, repo):
    auditor.log_step("sess-2", "agent-1", "user-1", StepType.TOOL_CALL, {"tool_name": "reader"})
    path = repo.get_decision_path("sess-2")
    result = auditor.generate_challenge_response(path)
    assert "default policy" in result["draft_response"]
