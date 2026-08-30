"""Agent WAF — tool call firewall (PS-5.1)."""

import json
import re
import time
from typing import Any
from uuid import uuid4

from governance.agent_waf.config import build_waf_config
from governance.agent_waf.models import (
    WAFDecisionRecord,
    WAFEffectiveConfig,
    WAFRuleConfig,
    WAFStats,
)
from shared.models.context import GovernanceContext
from shared.models.tool import WAFDisposition, WAFResult, WAFRuleEvaluation
from shared.storage.base import Repository

INJECTION_PATTERNS = [
    r"(\bDROP\b|\bDELETE\b|\bINSERT\b|\bUPDATE\b|\bUNION\b|\bSELECT\b.*\bFROM\b)",
    r"(--|;|/\*|\*/|<script|javascript:)",
    r"(\$\{|\{\{|\}\})",
]

PROBE_VIOLATION_THRESHOLD = 3


class AgentWAF:
    """Policy-enforcing proxy for agent tool calls."""

    def __init__(self, repository: Repository) -> None:
        self._repo = repository

    def intercept(
        self,
        context: GovernanceContext,
        shadow_mode: bool = False,
        waf_rules: dict[str, Any] | None = None,
        agent: Any | None = None,
    ) -> WAFResult:
        start = time.perf_counter()
        config = self._resolve_config(context, waf_rules, agent)
        if not config.enabled:
            return WAFResult(disposition=WAFDisposition.ALLOW, matched_rules=[])

        rules_dict = config.model_dump()
        evaluations: list[WAFRuleEvaluation] = []

        # Rule 1 — tool scope: only tools (and operations) declared for the agent.
        tool_check = self._validate_allowed_tool(context, agent)
        evaluations.append(
            WAFRuleEvaluation(
                rule_type="tool_scope",
                rule_id=tool_check or "agent_tool_scope",
                passed=tool_check is None,
                detail=tool_check
                or f"{context.tool_name}:{context.action_type} within declared agent scope",
            )
        )
        if tool_check:
            return self._deny(context, [tool_check], "Tool not in agent scope", shadow_mode, evaluations, start)

        # Rule 2 — rate limit (sliding window).
        limit = config.rate_limits.get(context.tool_name, config.rate_limits.get("default", 30))
        count = self._repo.increment_rate_counter(
            context.agent_id, context.tool_name, config.rate_window_seconds
        )
        rate_id = f"rate_limit:{context.tool_name}:{limit}/{config.rate_window_seconds}s"
        over_rate = count > limit
        evaluations.append(
            WAFRuleEvaluation(
                rule_type="rate_limit",
                rule_id=rate_id,
                passed=not over_rate,
                detail=f"{count}/{limit} calls in trailing {config.rate_window_seconds}s window",
            )
        )
        if over_rate:
            return self._deny(
                context, [rate_id], f"Rate limit exceeded: {count}/{limit}", shadow_mode, evaluations, start
            )

        # Rule 3 — parameter validation (injection + blocklist).
        param_result = self._validate_parameters(context, config.param_blocklist)
        evaluations.append(
            WAFRuleEvaluation(
                rule_type="parameter_validation",
                rule_id=param_result or "parameter_validation",
                passed=param_result is None,
                detail=param_result or "no injection / blocklisted patterns in parameters",
            )
        )
        if param_result:
            return self._deny(
                context, [param_result], "Parameter validation failed", shadow_mode, evaluations, start
            )

        # Rule 4 — parameter size limit.
        params_size = len(json.dumps(context.tool_params, default=str))
        size_id = f"size_limit:{params_size}>{config.max_param_size}"
        over_size = params_size > config.max_param_size
        evaluations.append(
            WAFRuleEvaluation(
                rule_type="size_limit",
                rule_id="param_size_limit",
                passed=not over_size,
                detail=f"payload {params_size}B / max {config.max_param_size}B",
            )
        )
        if over_size:
            return self._deny(
                context, [size_id], "Parameter payload too large", shadow_mode, evaluations, start
            )

        # Rule 5 — data scope.
        scope_result = self._validate_data_scope(context, rules_dict)
        evaluations.append(
            WAFRuleEvaluation(
                rule_type="data_scope",
                rule_id=scope_result or "data_scope",
                passed=scope_result is None,
                detail=scope_result or "parameters within declared data scope",
            )
        )
        if scope_result:
            self._track_scope_violation(context.session_id)
            return self._deny(context, [scope_result], "Data scope violation", shadow_mode, evaluations, start)

        # Rule 6 — sequence / ordering.
        required_prior = config.sequence_rules.get(context.tool_name)
        seq_result = self._validate_sequence(context, config.sequence_rules)
        evaluations.append(
            WAFRuleEvaluation(
                rule_type="sequence",
                rule_id=seq_result or "sequence",
                passed=seq_result is None,
                detail=seq_result
                or (
                    f"prerequisite(s) {required_prior} satisfied this session"
                    if required_prior
                    else "no sequence prerequisites for this tool"
                ),
            )
        )
        if seq_result:
            return self._deny(context, [seq_result], "Tool sequence violation", shadow_mode, evaluations, start)

        result = WAFResult(disposition=WAFDisposition.ALLOW, matched_rules=[], evaluations=evaluations)
        self._record_decision(context, result, shadow_mode, start)
        return result

    def _deny(
        self,
        context: GovernanceContext,
        matched: list[str],
        reason: str,
        shadow_mode: bool,
        evaluations: list[WAFRuleEvaluation],
        start: float,
    ) -> WAFResult:
        result = self._result(WAFDisposition.DENY, matched, reason, shadow_mode)
        result.evaluations = evaluations
        self._record_decision(context, result, shadow_mode, start)
        return result

    def get_stats(self, agent_id: str | None = None, limit: int = 20) -> WAFStats:
        records = self._repo.list_waf_records(agent_id=agent_id, limit=1000)
        stats = WAFStats(agent_id=agent_id)
        total_latency = 0.0
        for rec in records:
            stats.total_calls += 1
            total_latency += rec.latency_ms
            stats.by_tool[rec.tool_name] = stats.by_tool.get(rec.tool_name, 0) + 1
            if rec.disposition == WAFDisposition.ALLOW:
                stats.allowed += 1
            elif rec.disposition == WAFDisposition.SHADOW:
                stats.shadow_would_deny += 1
            else:
                stats.denied += 1
            # Attribute each block to the rule type that tripped it.
            if rec.disposition in (WAFDisposition.DENY, WAFDisposition.SHADOW):
                tripped = next((e for e in rec.evaluations if not e.passed), None)
                key = tripped.rule_type if tripped else "unknown"
                stats.by_rule_type[key] = stats.by_rule_type.get(key, 0) + 1
        if stats.total_calls:
            stats.avg_latency_ms = round(total_latency / stats.total_calls, 3)
        blocks = [r for r in records if r.disposition in (WAFDisposition.DENY, WAFDisposition.SHADOW)]
        stats.recent_blocks = sorted(blocks, key=lambda r: r.timestamp, reverse=True)[:limit]
        return stats

    def describe_config(self, agent_id: str | None = None) -> WAFEffectiveConfig:
        """Return the effective ruleset that will be enforced for an agent.

        Makes the WAF a transparent, inspectable rule engine rather than a black box.
        """
        agent = self._repo.get_agent(agent_id) if agent_id else None
        config = build_waf_config(agent)
        allowed_tools = [t.name for t in agent.tools] if agent and agent.tools else []
        return WAFEffectiveConfig(
            agent_id=agent_id,
            enabled=config.enabled,
            rate_window_seconds=config.rate_window_seconds,
            rate_limits=config.rate_limits,
            max_param_size=config.max_param_size,
            injection_patterns=list(INJECTION_PATTERNS),
            param_blocklist=config.param_blocklist,
            allowed_datasets=config.allowed_datasets,
            sequence_rules=config.sequence_rules,
            allowed_tools=allowed_tools,
            source="agent_registry" if agent else "defaults",
        )

    def is_probe_detected(self, session_id: str) -> bool:
        if hasattr(self._repo, "get_waf_scope_violations"):
            return self._repo.get_waf_scope_violations(session_id) >= PROBE_VIOLATION_THRESHOLD
        return False

    def _resolve_config(
        self, context: GovernanceContext, waf_rules: dict[str, Any] | None, agent: Any | None
    ) -> WAFRuleConfig:
        if waf_rules:
            return WAFRuleConfig(**{**build_waf_config(agent).model_dump(), **waf_rules})
        if agent is None:
            agent = self._repo.get_agent(context.agent_id)
        return build_waf_config(agent)

    def _validate_allowed_tool(self, context: GovernanceContext, agent: Any | None) -> str | None:
        if agent is None:
            agent = self._repo.get_agent(context.agent_id)
        if agent is None or not agent.tools:
            return None
        allowed = {t.name for t in agent.tools}
        if context.tool_name not in allowed:
            return f"tool_not_allowed:{context.tool_name}"
        tool_scope = next((t for t in agent.tools if t.name == context.tool_name), None)
        if tool_scope and context.action_type not in tool_scope.allowed_operations:
            return f"operation_not_allowed:{context.action_type}"
        return None

    def _validate_parameters(self, context: GovernanceContext, blocklist: list[str]) -> str | None:
        extra = context.metadata.get("param_blocklist", [])
        for param_value in self._flatten_params(context.tool_params):
            str_val = str(param_value)
            for pattern in INJECTION_PATTERNS + blocklist + extra:
                if re.search(pattern, str_val, re.IGNORECASE):
                    return f"parameter_blocklist:{pattern[:30]}"
        return None

    def _validate_data_scope(self, context: GovernanceContext, rules: dict) -> str | None:
        session_scope = context.metadata.get("session_scope", {})
        for scope_key, expected_value in session_scope.items():
            actual = context.tool_params.get(scope_key)
            if actual is not None and str(actual) != str(expected_value):
                return f"data_scope:{scope_key}!={expected_value}"

        allowed_datasets = rules.get("allowed_datasets") or context.metadata.get("allowed_datasets")
        if allowed_datasets:
            dataset = context.tool_params.get("dataset") or context.tool_params.get("table")
            if dataset and dataset not in allowed_datasets:
                return f"data_scope:dataset:{dataset}"
        return None

    def _validate_sequence(self, context: GovernanceContext, sequence_rules: dict[str, list[str]]) -> str | None:
        required_prior = sequence_rules.get(context.tool_name)
        if not required_prior:
            return None
        prior_calls = self._repo.get_session_tool_calls(context.session_id)
        for required in required_prior:
            if required not in prior_calls:
                return f"sequence:{context.tool_name}_requires_{required}"
        return None

    def _track_scope_violation(self, session_id: str) -> None:
        if hasattr(self._repo, "increment_waf_scope_violations"):
            self._repo.increment_waf_scope_violations(session_id)

    def _record_decision(
        self,
        context: GovernanceContext,
        result: WAFResult,
        shadow_mode: bool,
        start: float,
    ) -> None:
        record = WAFDecisionRecord(
            record_id=f"waf-{uuid4().hex[:12]}",
            agent_id=context.agent_id,
            session_id=context.session_id,
            tool_name=context.tool_name,
            action_type=context.action_type,
            disposition=result.disposition,
            matched_rules=result.matched_rules,
            evaluations=result.evaluations,
            reason=result.reason,
            params_sanitized=self._sanitize_params(context.tool_params),
            shadow_mode=shadow_mode,
            latency_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        self._repo.save_waf_record(record)
        self._notify_live_feed(record)

    @staticmethod
    def _sanitize_params(params: dict) -> dict:
        sensitive_keys = {"password", "token", "secret", "api_key", "ssn", "credit_card"}
        sanitized = {}
        for key, value in params.items():
            if key.lower() in sensitive_keys:
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = AgentWAF._sanitize_params(value)
            else:
                sanitized[key] = value
        return sanitized

    def _flatten_params(self, params: dict) -> list[Any]:
        values = []
        for v in params.values():
            if isinstance(v, dict):
                values.extend(self._flatten_params(v))
            elif isinstance(v, list):
                values.extend(v)
            else:
                values.append(v)
        return values

    def _notify_live_feed(self, record: WAFDecisionRecord) -> None:
        try:
            from governance.agent_waf.broadcast import notify_waf_record

            notify_waf_record(
                {
                    "record_id": record.record_id,
                    "agent_id": record.agent_id,
                    "session_id": record.session_id,
                    "tool_name": record.tool_name,
                    "action_type": record.action_type,
                    "disposition": record.disposition.value,
                    "matched_rules": record.matched_rules,
                    "evaluations": [e.model_dump() for e in record.evaluations],
                    "reason": record.reason,
                    "shadow_mode": record.shadow_mode,
                    "latency_ms": record.latency_ms,
                    "timestamp": record.timestamp.isoformat(),
                }
            )
        except Exception:
            pass

    def _result(
        self, disposition: WAFDisposition, rules: list[str], reason: str, shadow_mode: bool
    ) -> WAFResult:
        if shadow_mode:
            return WAFResult(
                disposition=WAFDisposition.SHADOW,
                matched_rules=rules,
                reason=f"[SHADOW] Would deny: {reason}",
            )
        return WAFResult(disposition=disposition, matched_rules=rules, reason=reason)
