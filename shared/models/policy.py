"""Policy domain models."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EnforcementAction(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REQUIRE_HITL = "require_hitl"
    WARN = "warn"
    AUDIT_ONLY = "audit_only"
    APPLY_POLICY = "apply_policy"
    SUSPEND_SESSION = "suspend_session"


class PolicyRule(BaseModel):
    name: str
    priority: int = 100
    when: dict[str, Any] | list[dict[str, Any]]
    then: dict[str, Any]


class Policy(BaseModel):
    policy_id: str
    name: str
    description: str = ""
    inherits: str | None = None
    rules: list[PolicyRule] = Field(default_factory=list)
    status: str = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PolicyVersion(BaseModel):
    policy_id: str
    version: str
    yaml_content: str
    content_hash: str
    created_by: str = "system"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MatchedRule(BaseModel):
    rule_name: str
    action: EnforcementAction
    reason: str = ""
    policy_id: str = ""
    policy_ref: str | None = None


class EnforcementDecision(BaseModel):
    action: EnforcementAction
    matched_rules: list[MatchedRule] = Field(default_factory=list)
    policy_version: str = "1.0.0"
    policy_ids: list[str] = Field(default_factory=list)
    reason: str = ""
    requires_hitl: bool = False
    ticket_id: str | None = None

    @property
    def is_blocked(self) -> bool:
        return self.action in {
            EnforcementAction.BLOCK,
            EnforcementAction.SUSPEND_SESSION,
        }
