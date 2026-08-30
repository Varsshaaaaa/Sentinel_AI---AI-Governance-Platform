"""Agent registry models."""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    UNDER_REVIEW = "under_review"
    DECOMMISSIONED = "decommissioned"


class ToolScope(BaseModel):
    name: str
    allowed_operations: list[str] = Field(default_factory=lambda: ["read"])
    data_scope: dict[str, str] = Field(default_factory=dict)


class ModelRef(BaseModel):
    name: str
    provider: str = "openai"
    version: str = "latest"


class AgentRegistration(BaseModel):
    name: str
    owner: str
    team: str
    purpose: str
    framework: str = "custom"
    risk_tier: RiskTier = RiskTier.MEDIUM
    models: list[ModelRef] = Field(default_factory=list)
    tools: list[ToolScope] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    policy_ids: list[str] = Field(default_factory=list)


class Agent(BaseModel):
    agent_id: str
    name: str
    owner: str
    team: str
    purpose: str
    framework: str
    risk_tier: RiskTier
    status: AgentStatus = AgentStatus.ACTIVE
    models: list[ModelRef] = Field(default_factory=list)
    tools: list[ToolScope] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    policy_ids: list[str] = Field(default_factory=list)
    credential_expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_active_at: datetime | None = None

    @property
    def risk_score(self) -> int:
        base = {"low": 15, "medium": 44, "high": 68, "critical": 92}
        score = base.get(self.risk_tier.value, 44)
        if self.status == AgentStatus.SUSPENDED:
            score = min(100, score + 10)
        return score
