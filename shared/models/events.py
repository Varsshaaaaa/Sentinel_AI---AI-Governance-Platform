"""Event models."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EventType(str, Enum):
    AGENT_REGISTERED = "AgentRegistered"
    TOOL_CALLED = "ToolCalled"
    POLICY_MATCHED = "PolicyMatched"
    VIOLATION_DETECTED = "ViolationDetected"
    RISK_UPDATED = "RiskUpdated"
    AGENT_SUSPENDED = "AgentSuspended"
    POLICY_UPDATED = "PolicyUpdated"
    DECISION_COMPLETED = "DecisionCompleted"
    COMPLIANCE_CHANGED = "ComplianceChanged"
    GOVERNANCE_STATUS_CHANGED = "GovernanceStatusChanged"


class GovernanceEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tenant_id: str = "default"
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str | None = None
    actor: str = "system"
    resource_type: str = ""
    resource_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = "1.0"
