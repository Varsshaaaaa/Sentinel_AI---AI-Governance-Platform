"""Per-agent WAF configuration builder."""

from shared.models.agent import Agent
from governance.agent_waf.models import WAFRuleConfig

DEFAULT_RATE_LIMITS: dict[str, int] = {
    "db_query": 30,
    "db_delete": 5,
    "email_send": 10,
    "api_call": 60,
    "default": 30,
}

DEFAULT_SEQUENCE_RULES: dict[str, list[str]] = {
    "payment_process": ["identity_verify"],
    "record_update": ["record_read"],
    "db_delete": ["db_query"],
}

HIGH_RISK_PARAM_BLOCKLIST = ["password", "secret", "api_key", "token", "ssn", "credit_card"]


def build_waf_config(agent: Agent | None) -> WAFRuleConfig:
    """Build WAF config from agent registry metadata."""
    if agent is None:
        return WAFRuleConfig(
            rate_limits=dict(DEFAULT_RATE_LIMITS),
            sequence_rules=dict(DEFAULT_SEQUENCE_RULES),
        )

    rate_limits = dict(DEFAULT_RATE_LIMITS)
    allowed_datasets = list(agent.datasets)

    for tool in agent.tools:
        tool_limit = _rate_limit_for_risk(agent.risk_tier.value, tool.name)
        rate_limits[tool.name] = tool_limit
        allowed_datasets.extend(tool.data_scope.keys())

    return WAFRuleConfig(
        rate_limits=rate_limits,
        allowed_datasets=list(set(allowed_datasets)),
        sequence_rules=dict(DEFAULT_SEQUENCE_RULES),
        param_blocklist=list(HIGH_RISK_PARAM_BLOCKLIST) if agent.risk_tier.value in ("high", "critical") else [],
    )


def _rate_limit_for_risk(risk_tier: str, tool_name: str) -> int:
    base = DEFAULT_RATE_LIMITS.get(tool_name, DEFAULT_RATE_LIMITS["default"])
    multipliers = {"low": 1.5, "medium": 1.0, "high": 0.6, "critical": 0.4}
    return max(1, int(base * multipliers.get(risk_tier, 1.0)))
