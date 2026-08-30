"""Violation models."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ViolationSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Violation(BaseModel):
    violation_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str
    session_id: str | None = None
    rule_name: str
    severity: ViolationSeverity = ViolationSeverity.MEDIUM
    source: str = "policy_engine"
    reason: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
