"""Audit and decision path models."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StepType(str, Enum):
    INPUT = "input"
    CONTEXT_RETRIEVED = "context_retrieved"
    TOOL_CALL = "tool_call"
    TOOL_RESPONSE = "tool_response"
    POLICY_EVALUATION = "policy_evaluation"
    REASONING = "reasoning"
    OUTPUT = "output"
    WAF_EVALUATION = "waf_evaluation"


class AuditStep(BaseModel):
    session_id: str
    step_sequence: int
    step_type: StepType
    agent_id: str
    user_id: str = "system"
    content: dict[str, Any] = Field(default_factory=dict)
    content_redacted: dict[str, Any] = Field(default_factory=dict)
    policy_evaluation: dict[str, Any] | None = None
    risk_score: int | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DecisionPath(BaseModel):
    session_id: str
    agent_id: str
    user_id: str
    steps: list[AuditStep] = Field(default_factory=list)
    summary: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
