"""PS-5.1 Agent WAF acceptance suite.

Runs a self-contained battery of adversarial scenarios that exercise every rule
type and proves each PS-5.1 success criterion (plus the shadow-mode bonus) on
demand. Every criterion executes against its own ephemeral in-memory repository,
so running the suite has no side effects on live governance data.

The output is deliberately structured (expected vs. actual disposition, matched
rules, and the full per-rule evaluation trace) so a reviewer can see each
success criterion fire with evidence rather than taking it on faith.
"""

from __future__ import annotations

from typing import Any, Callable

from governance.agent_waf.engine import AgentWAF
from shared.models.context import GovernanceContext, DataClassification
from shared.models.tool import WAFDisposition, WAFResult
from shared.storage.memory import MemoryRepository


def _evidence(result: WAFResult) -> dict[str, Any]:
    return {
        "disposition": result.disposition.value,
        "matched_rules": result.matched_rules,
        "reason": result.reason,
        "trace": [e.model_dump() for e in result.evaluations],
    }


class WAFAcceptanceSuite:
    """Executes the PS-5.1 success criteria as live, evidenced checks."""

    def run(self) -> dict[str, Any]:
        checks: list[Callable[[], dict[str, Any]]] = [
            self._c_rate_limit,
            self._c_parameter_blocklist,
            self._c_param_size,
            self._c_data_scope,
            self._c_sequence_block,
            self._c_sequence_allow,
            self._c_legitimate_allow,
            self._c_shadow_mode,
            self._c_logging_completeness,
        ]
        criteria = [check() for check in checks]
        passed = sum(1 for c in criteria if c["passed"])
        return {
            "suite": "PS-5.1 — The Agent WAF",
            "passed": passed == len(criteria),
            "summary": {"total": len(criteria), "passed": passed, "failed": len(criteria) - passed},
            "criteria": criteria,
        }

    # -- individual criteria -------------------------------------------------

    def _c_rate_limit(self) -> dict[str, Any]:
        waf = AgentWAF(MemoryRepository())
        ctx = GovernanceContext(
            agent_id="acc-agent", session_id="rate", action_type="read", tool_name="db_query"
        )
        results = [waf.intercept(ctx) for _ in range(31)]
        allowed = sum(1 for r in results[:30] if r.disposition == WAFDisposition.ALLOW)
        final = results[-1]
        passed = allowed == 30 and final.disposition == WAFDisposition.DENY
        return self._criterion(
            "rate_limit",
            "Rate limit fires correctly after N calls within the window",
            "First 30 db_query calls allowed (limit 30/min), the 31st blocked",
            expected="deny",
            actual=final.disposition.value,
            passed=passed,
            evidence={"allowed_before_block": allowed, **_evidence(final)},
        )

    def _c_parameter_blocklist(self) -> dict[str, Any]:
        waf = AgentWAF(MemoryRepository())
        ctx = GovernanceContext(
            agent_id="acc-agent",
            session_id="inj",
            action_type="read",
            tool_name="db_query",
            tool_params={"query": "SELECT * FROM users; DROP TABLE users;--"},
        )
        result = waf.intercept(ctx)
        passed = result.disposition == WAFDisposition.DENY
        return self._criterion(
            "parameter_blocklist",
            "Parameter blocklist catches a simulated injection attempt",
            "SQL-injection payload embedded in a tool parameter is rejected",
            expected="deny",
            actual=result.disposition.value,
            passed=passed,
            evidence=_evidence(result),
        )

    def _c_param_size(self) -> dict[str, Any]:
        waf = AgentWAF(MemoryRepository())
        ctx = GovernanceContext(
            agent_id="acc-agent",
            session_id="size",
            action_type="write",
            tool_name="api_call",
            tool_params={"payload": "A" * 70000},
        )
        result = waf.intercept(ctx)
        passed = result.disposition == WAFDisposition.DENY
        return self._criterion(
            "param_size",
            "Parameter size limit rejects oversized payloads",
            "A 70KB parameter exceeds the 64KB payload ceiling and is rejected",
            expected="deny",
            actual=result.disposition.value,
            passed=passed,
            evidence=_evidence(result),
        )

    def _c_data_scope(self) -> dict[str, Any]:
        waf = AgentWAF(MemoryRepository())
        ctx = GovernanceContext(
            agent_id="acc-agent",
            session_id="scope",
            action_type="read",
            tool_name="crm_read",
            tool_params={"customer_id": "999"},
            metadata={"session_scope": {"customer_id": "123"}},
        )
        result = waf.intercept(ctx)
        passed = result.disposition == WAFDisposition.DENY
        return self._criterion(
            "data_scope",
            "Out-of-scope data access is blocked",
            "Reading customer 999 while the session is scoped to customer 123 is rejected",
            expected="deny",
            actual=result.disposition.value,
            passed=passed,
            evidence=_evidence(result),
        )

    def _c_sequence_block(self) -> dict[str, Any]:
        waf = AgentWAF(MemoryRepository())
        ctx = GovernanceContext(
            agent_id="acc-agent",
            session_id="seq-bad",
            action_type="write",
            tool_name="payment_process",
        )
        result = waf.intercept(ctx)
        passed = result.disposition == WAFDisposition.DENY
        return self._criterion(
            "sequence_block",
            "Sequence rule blocks a tool called out of expected order",
            "payment_process is rejected because identity_verify was not called first",
            expected="deny",
            actual=result.disposition.value,
            passed=passed,
            evidence=_evidence(result),
        )

    def _c_sequence_allow(self) -> dict[str, Any]:
        repo = MemoryRepository()
        waf = AgentWAF(repo)
        # Prerequisite tool call recorded for the session first.
        repo.record_tool_call("seq-ok", "identity_verify")
        ctx = GovernanceContext(
            agent_id="acc-agent",
            session_id="seq-ok",
            action_type="write",
            tool_name="payment_process",
        )
        result = waf.intercept(ctx)
        passed = result.disposition == WAFDisposition.ALLOW
        return self._criterion(
            "sequence_allow",
            "Sequence rule permits a tool once its prerequisite ran (calibration)",
            "payment_process is allowed after identity_verify completed in the same session",
            expected="allow",
            actual=result.disposition.value,
            passed=passed,
            evidence=_evidence(result),
        )

    def _c_legitimate_allow(self) -> dict[str, Any]:
        waf = AgentWAF(MemoryRepository())
        ctx = GovernanceContext(
            agent_id="acc-agent",
            session_id="ok",
            action_type="read",
            tool_name="db_query",
            tool_params={"query": "find open tickets for the current user"},
        )
        result = waf.intercept(ctx)
        passed = result.disposition == WAFDisposition.ALLOW
        return self._criterion(
            "legitimate_allow",
            "A legitimate in-policy call passes through transparently",
            "A clean, in-scope read is forwarded and logged as allowed",
            expected="allow",
            actual=result.disposition.value,
            passed=passed,
            evidence=_evidence(result),
        )

    def _c_shadow_mode(self) -> dict[str, Any]:
        """Bonus: shadow mode logs what it *would* block without blocking."""
        waf = AgentWAF(MemoryRepository())
        ctx = GovernanceContext(
            agent_id="acc-agent", session_id="shadow", action_type="read", tool_name="db_query"
        )
        for _ in range(31):
            waf.intercept(ctx)
        result = waf.intercept(ctx, shadow_mode=True)
        passed = result.disposition == WAFDisposition.SHADOW
        return self._criterion(
            "shadow_mode",
            "Bonus: shadow mode records would-block events without enforcing",
            "A rate-limited call in shadow mode is logged as SHADOW, not denied",
            expected="shadow",
            actual=result.disposition.value,
            passed=passed,
            evidence=_evidence(result),
        )

    def _c_logging_completeness(self) -> dict[str, Any]:
        repo = MemoryRepository()
        waf = AgentWAF(repo)
        ctx = GovernanceContext(
            agent_id="acc-agent",
            session_id="log",
            action_type="read",
            tool_name="db_query",
            tool_params={"password": "hunter2", "query": "SELECT 1"},
            session_data_classification=DataClassification.CONFIDENTIAL,
        )
        waf.intercept(ctx)
        rec = repo.list_waf_records(agent_id="acc-agent", limit=1)[0]
        required = {
            "timestamp": bool(rec.timestamp),
            "agent_id": bool(rec.agent_id),
            "tool": bool(rec.tool_name),
            "params_sanitized": rec.params_sanitized.get("password") == "[REDACTED]",
            "rule_evaluation_outcome": len(rec.evaluations) > 0,
            "final_disposition": bool(rec.disposition),
        }
        passed = all(required.values())
        return self._criterion(
            "logging_completeness",
            "Every intercepted call is logged with the required fields",
            "Record carries timestamp, agent ID, tool, sanitised params, rule trace and disposition",
            expected="all fields present + secrets redacted",
            actual="present" if passed else "missing fields",
            passed=passed,
            evidence={"fields": required, "sanitized_params": rec.params_sanitized},
        )

    @staticmethod
    def _criterion(
        cid: str,
        ps_criterion: str,
        scenario: str,
        expected: str,
        actual: str,
        passed: bool,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": cid,
            "ps_criterion": ps_criterion,
            "scenario": scenario,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "evidence": evidence,
        }
