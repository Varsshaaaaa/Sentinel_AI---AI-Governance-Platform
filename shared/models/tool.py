"""Tool intercept models."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from shared.models.context import GovernanceContext
from shared.models.policy import EnforcementDecision


class WAFDisposition(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    SHADOW = "shadow"


class WAFRuleEvaluation(BaseModel):
    rule_type: str
    rule_id: str
    passed: bool
    detail: str = ""


class WAFResult(BaseModel):
    disposition: WAFDisposition
    matched_rules: list[str] = Field(default_factory=list)
    evaluations: list[WAFRuleEvaluation] = Field(default_factory=list)
    reason: str = ""


class ToolInterceptRequest(BaseModel):
    context: GovernanceContext
    shadow_mode: bool = False
    dry_run: bool = False


class ToolInterceptResponse(BaseModel):
    disposition: str
    waf_result: WAFResult | None = None
    policy_decision: EnforcementDecision | None = None
    reason: str = ""
    ticket_id: str | None = None
    violation_id: str | None = None
    session_suspended: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
