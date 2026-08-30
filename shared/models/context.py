"""Governance runtime context assembled at request time (PS-10.2)."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    PII = "PII"
    PHI = "PHI"


class GovernanceContext(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str = "system"
    user_role: str = "user"
    agent_id: str
    agent_role: str = "agent"
    session_id: str
    action_type: str
    tool_name: str
    tool_params: dict[str, Any] = Field(default_factory=dict)
    data_scope_size: int = 0
    session_data_classification: DataClassification = DataClassification.INTERNAL
    previous_violations_in_session: int = 0
    delegation_depth: int = 0
    framework: str = "custom"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def hour(self) -> int:
        return self.timestamp.hour

    @property
    def is_business_hours(self) -> bool:
        return 9 <= self.hour < 18

    def to_eval_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "timestamp.hour": self.hour,
            "user_id": self.user_id,
            "user_role": self.user_role,
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "session_id": self.session_id,
            "action_type": self.action_type,
            "tool_name": self.tool_name,
            "tool_params": self.tool_params,
            "data_scope_size": self.data_scope_size,
            "session_data_classification": self.session_data_classification.value,
            "previous_violations_in_session": self.previous_violations_in_session,
            "delegation_depth": self.delegation_depth,
            "framework": self.framework,
            "is_business_hours": self.is_business_hours,
        }
