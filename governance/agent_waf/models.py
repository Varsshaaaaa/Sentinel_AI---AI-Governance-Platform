"""Agent WAF models."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from shared.models.tool import WAFDisposition, WAFRuleEvaluation


class WAFRuleConfig(BaseModel):
    rate_limits: dict[str, int] = Field(default_factory=dict)
    rate_window_seconds: int = 60
    max_param_size: int = 65536
    param_blocklist: list[str] = Field(default_factory=list)
    allowed_datasets: list[str] = Field(default_factory=list)
    sequence_rules: dict[str, list[str]] = Field(default_factory=dict)
    enabled: bool = True


class WAFDecisionRecord(BaseModel):
    record_id: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent_id: str
    session_id: str
    tool_name: str
    action_type: str = ""
    disposition: WAFDisposition
    matched_rules: list[str] = Field(default_factory=list)
    evaluations: list[WAFRuleEvaluation] = Field(default_factory=list)
    reason: str = ""
    params_sanitized: dict[str, Any] = Field(default_factory=dict)
    shadow_mode: bool = False
    latency_ms: float = 0.0


class WAFStats(BaseModel):
    agent_id: str | None = None
    total_calls: int = 0
    allowed: int = 0
    denied: int = 0
    shadow_would_deny: int = 0
    by_tool: dict[str, int] = Field(default_factory=dict)
    by_rule_type: dict[str, int] = Field(default_factory=dict)
    avg_latency_ms: float = 0.0
    recent_blocks: list[WAFDecisionRecord] = Field(default_factory=list)


class WAFEffectiveConfig(BaseModel):
    """Human-readable view of the ruleset that will be enforced for an agent."""

    agent_id: str | None = None
    enabled: bool = True
    rate_window_seconds: int = 60
    rate_limits: dict[str, int] = Field(default_factory=dict)
    max_param_size: int = 65536
    injection_patterns: list[str] = Field(default_factory=list)
    param_blocklist: list[str] = Field(default_factory=list)
    allowed_datasets: list[str] = Field(default_factory=list)
    sequence_rules: dict[str, list[str]] = Field(default_factory=dict)
    allowed_tools: list[str] = Field(default_factory=list)
    source: str = "defaults"
