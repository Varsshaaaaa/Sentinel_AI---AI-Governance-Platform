"""Policy rule condition evaluator."""

import re
from typing import Any

from shared.models.context import GovernanceContext
from shared.models.policy import (
    EnforcementAction,
    EnforcementDecision,
    MatchedRule,
    Policy,
)


class ConditionEvaluator:
    """Evaluates policy rule conditions against governance context."""

    def evaluate_condition(self, condition: dict[str, Any], ctx: GovernanceContext) -> bool:
        if "all" in condition:
            return all(self._eval_clause(c, ctx) for c in condition["all"])
        if "any" in condition:
            return any(self._eval_clause(c, ctx) for c in condition["any"])
        if "not" in condition:
            return not self._eval_clause(condition["not"], ctx)
        return self._eval_clause(condition, ctx)

    def _eval_clause(self, clause: Any, ctx: GovernanceContext) -> bool:
        if isinstance(clause, dict):
            if "all" in clause or "any" in clause or "not" in clause:
                return self.evaluate_condition(clause, ctx)
            if len(clause) == 1:
                key, value = next(iter(clause.items()))
                return self._eval_expression(key, value, ctx)
            return all(self._eval_clause({k: v}, ctx) for k, v in clause.items())
        if isinstance(clause, list):
            # A bare list of clauses is treated as an implicit `all`.
            return all(self._eval_clause(c, ctx) for c in clause)
        return bool(clause)

    def _eval_expression(self, key: str, value: Any, ctx: GovernanceContext) -> bool:
        ctx_dict = ctx.to_eval_dict()

        if key == "context.timestamp.hour outside":
            if isinstance(value, list) and len(value) == 2:
                start, end = value
                hour = ctx.hour
                if start <= end:
                    return not (start <= hour < end)
                return end <= hour < start
            return False

        if key == "context.is_business_hours":
            return ctx.is_business_hours == bool(value)

        if key == "context.tool_params.to_domain external":
            to_addr = str(ctx.tool_params.get("to", ctx.tool_params.get("recipient", "")))
            internal_domains = value if isinstance(value, list) else ["company.com", "internal.local"]
            domain = to_addr.split("@")[-1] if "@" in to_addr else ""
            return domain not in internal_domains and domain != ""

        if key.startswith("context.tool_params."):
            param_key = key.replace("context.tool_params.", "")
            param_val = str(ctx.tool_params.get(param_key, ""))
            if isinstance(value, dict) and "matches" in value:
                return bool(re.search(value["matches"], param_val, re.IGNORECASE))
            return param_val == str(value)

        if key.endswith(" not in"):
            field = key.replace(" not in", "").replace("context.", "")
            actual = self._get_field(field, ctx, ctx_dict)
            return actual not in value

        if key.endswith(" in"):
            field = key.replace(" in", "").replace("context.", "")
            actual = ctx_dict.get(field) or ctx_dict.get(f"context.{field}")
            if actual is None and field in ctx_dict:
                actual = ctx_dict[field]
            if field == "action_type":
                actual = ctx.action_type
            return actual in value

        if key.endswith(" contains"):
            field = key.replace(" contains", "").replace("context.", "")
            actual = self._get_field(field, ctx, ctx_dict)
            try:
                return value in actual
            except TypeError:
                return False

        if key.endswith(" =="):
            field = key.replace(" ==", "").replace("context.", "")
            actual = self._get_field(field, ctx, ctx_dict)
            return str(actual) == str(value)

        if key.endswith(" !="):
            field = key.replace(" !=", "").replace("context.", "")
            actual = self._get_field(field, ctx, ctx_dict)
            return str(actual) != str(value)

        if key.endswith(" >="):
            field = key.replace(" >=", "").replace("context.", "")
            actual = self._get_field(field, ctx, ctx_dict)
            return self._as_number(actual) >= self._as_number(value)

        if key.endswith(" <="):
            field = key.replace(" <=", "").replace("context.", "")
            actual = self._get_field(field, ctx, ctx_dict)
            return self._as_number(actual) <= self._as_number(value)

        if key.endswith(" >"):
            field = key.replace(" >", "").replace("context.", "")
            actual = self._get_field(field, ctx, ctx_dict)
            return self._as_number(actual) > self._as_number(value)

        if key.endswith(" <"):
            field = key.replace(" <", "").replace("context.", "")
            actual = self._get_field(field, ctx, ctx_dict)
            return self._as_number(actual) < self._as_number(value)

        # Plain equality: context.action_type: delete
        if key.startswith("context.") and not any(
            op in key for op in ("==", "!=", ">=", "<=", ">", "<", " in", " outside", " contains")
        ):
            field = key.replace("context.", "")
            actual = self._get_field(field, ctx, ctx_dict)
            return str(actual) == str(value)

        return False

    @staticmethod
    def _as_number(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _get_field(self, field: str, ctx: GovernanceContext, ctx_dict: dict) -> Any:
        mapping = {
            "session_data_classification": ctx.session_data_classification.value,
            "action_type": ctx.action_type,
            "data_scope_size": ctx.data_scope_size,
            "previous_violations_in_session": ctx.previous_violations_in_session,
            "delegation_depth": ctx.delegation_depth,
            "tool_name": ctx.tool_name,
            "user_role": ctx.user_role,
            "agent_role": ctx.agent_role,
        }
        return mapping.get(field, ctx_dict.get(field, ctx_dict.get(f"context.{field}")))


class PolicyEvaluator:
    """Evaluates policies against governance context (PS-10.2)."""

    def __init__(self) -> None:
        self._condition_evaluator = ConditionEvaluator()

    def evaluate(
        self,
        context: GovernanceContext,
        policies: list[Policy],
        policy_loader: Any | None = None,
        policy_provider: Any | None = None,
    ) -> EnforcementDecision:
        from governance.policy_engine.loader import PolicyLoader

        loader = policy_loader or PolicyLoader()
        resolved_policies = self._resolve_inheritance(policies, loader, policy_provider)
        all_rules = []
        for policy in resolved_policies:
            for rule in policy.rules:
                all_rules.append((policy.policy_id, rule))

        all_rules.sort(key=lambda x: x[1].priority, reverse=True)

        matched: list[MatchedRule] = []
        final_action = EnforcementAction.ALLOW
        policy_ref: str | None = None

        for policy_id, rule in all_rules:
            when = rule.when
            if not self._condition_evaluator.evaluate_condition(
                when if isinstance(when, dict) else {"all": when},
                context,
            ):
                continue

            action_str = rule.then.get("action", "allow")
            try:
                action = EnforcementAction(action_str)
            except ValueError:
                action = EnforcementAction.ALLOW

            matched.append(
                MatchedRule(
                    rule_name=rule.name,
                    action=action,
                    reason=rule.then.get("reason", ""),
                    policy_id=policy_id,
                    policy_ref=rule.then.get("policy_ref"),
                )
            )

            if action == EnforcementAction.APPLY_POLICY:
                policy_ref = rule.then.get("policy_ref")
                final_action = EnforcementAction.REQUIRE_HITL
            elif action in {
                EnforcementAction.BLOCK,
                EnforcementAction.SUSPEND_SESSION,
                EnforcementAction.REQUIRE_HITL,
            }:
                final_action = action
                break
            elif action in {EnforcementAction.WARN, EnforcementAction.AUDIT_ONLY}:
                if final_action == EnforcementAction.ALLOW:
                    final_action = action

        return EnforcementDecision(
            action=final_action,
            matched_rules=matched,
            policy_ids=[p.policy_id for p in resolved_policies],
            reason=matched[0].reason if matched else "No rules matched",
            requires_hitl=final_action == EnforcementAction.REQUIRE_HITL,
        )

    def _resolve_inheritance(
        self,
        policies: list[Policy],
        loader: Any,
        policy_provider: Any | None = None,
    ) -> list[Policy]:
        """Resolve full inheritance chains (base → mid → child).

        Ancestors are looked up first among the supplied policies, then via the
        optional ``policy_provider`` (e.g. ``repo.get_policy``) so a child can
        inherit from a base that wasn't explicitly attached to the agent.
        """
        policy_map = {p.policy_id: p for p in policies}
        return [
            self._resolve_one(policy, policy_map, loader, policy_provider, set())
            for policy in policies
        ]

    def _resolve_one(
        self,
        policy: Policy,
        policy_map: dict[str, Policy],
        loader: Any,
        policy_provider: Any | None,
        seen: set[str],
    ) -> Policy:
        if not policy.inherits or policy.policy_id in seen:
            return policy  # no parent, or cycle guard
        seen.add(policy.policy_id)

        base = policy_map.get(policy.inherits)
        if base is None and policy_provider is not None:
            base = policy_provider(policy.inherits)
        if base is None:
            return policy  # unresolved ancestor — apply child as-is

        resolved_base = self._resolve_one(base, policy_map, loader, policy_provider, seen)
        return loader.merge_policies(resolved_base, policy)
