"""Governance state models."""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class GovernanceStatus(str, Enum):
    GREEN = "green"
    UNDER_REVIEW = "under_review"
    SUSPENDED = "suspended"
    REMEDIATED = "remediated"


class GovernanceState(BaseModel):
    agent_id: str
    status: GovernanceStatus = GovernanceStatus.GREEN
    reviewer: str | None = None
    trigger_signal: str | None = None
    since: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str = ""
    # SLA escalation tracking (PS-4.2 bonus)
    escalation_level: int = 0
    last_reminder_at: datetime | None = None
