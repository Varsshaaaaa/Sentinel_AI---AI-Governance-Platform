#!/usr/bin/env python3
"""Real-world governed agent demo — mock tools + SentinelAI intercept.

Read the INTEGRATION section at the top first — it shows how to wire
SentinelAI into any agent. The rest of this file is demo scenarios.

CLI:
    python agent_demo/governed_agent_demo.py
    API_URL=http://localhost:8080/v1 python agent_demo/governed_agent_demo.py --scenario finance-bulk-delete

UI (browser agent simulator — real fetch to /tool/intercept):
    python agent_demo/server.py
    # open http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.models.tool import ToolInterceptResponse  # noqa: E402

# =============================================================================
# INTEGRATION — copy this pattern into your agent code
# =============================================================================
#
# Flow:
#   your_agent wants to run a tool
#        ↓
#   POST {SENTINELAI_API_URL}/tool/intercept   ← ask governance FIRST
#        ↓
#   allow / warn / audit_only  → run your real tool
#   block / deny               → stop, show reason to user
#   require_hitl               → pause, wait for human approval
#
# Alternative: use the SDK instead of raw HTTP (same endpoint under the hood):
#   from governance.adapters.client import SentinelAIClient
#   client = SentinelAIClient(SENTINELAI_API_URL)
#   result = client.intercept(agent_id=..., session_id=..., tool_name=..., ...)
# =============================================================================

# Production API (override for local dev: export API_URL=http://localhost:8080/v1)
SENTINELAI_API_URL = os.environ.get(
    "API_URL",
    "https://dwybfyittl.execute-api.us-east-1.amazonaws.com/v1",
).rstrip("/")

# Single governance entry point — every tool call goes here
INTERCEPT_PATH = "/tool/intercept"


def get_intercept_url(api_url: str | None = None) -> str:
    """Full URL for governance intercept."""
    return f"{(api_url or SENTINELAI_API_URL).rstrip('/')}{INTERCEPT_PATH}"


def build_intercept_payload(
    *,
    agent_id: str,
    session_id: str,
    tool_name: str,
    tool_params: dict[str, Any] | None = None,
    action_type: str = "read",
    data_scope_size: int = 0,
    session_data_classification: str = "internal",
    user_id: str = "demo-user",
    framework: str = "custom",
    shadow_mode: bool = False,
    timestamp: str | None = None,
    **extra_context: Any,
) -> dict[str, Any]:
    """Request body for POST /tool/intercept — fill context before each tool call."""
    ctx: dict[str, Any] = {
        "agent_id": agent_id,
        "session_id": session_id,
        "tool_name": tool_name,
        "action_type": action_type,
        "tool_params": tool_params or {},
        "data_scope_size": data_scope_size,
        "session_data_classification": session_data_classification,
        "user_id": user_id,
        "framework": framework,
    }
    if timestamp:
        ctx["timestamp"] = timestamp
    ctx.update(extra_context)
    return {"context": ctx, "shadow_mode": shadow_mode}


def call_governance_intercept(
    api_url: str,
    *,
    agent_id: str,
    session_id: str,
    tool_name: str,
    tool_params: dict[str, Any] | None = None,
    action_type: str = "read",
    data_scope_size: int = 0,
    session_data_classification: str = "internal",
    timeout: float = 45.0,
    **extra_context: Any,
) -> ToolInterceptResponse:
    """
    Ask SentinelAI before running a tool. Copy this into your agent.

    Example:
        result = call_governance_intercept(
            SENTINELAI_API_URL,
            agent_id="agent-finance-001",
            session_id="session-abc",
            tool_name="db_delete",
            action_type="delete",
            tool_params={"table": "financial_records", "count": 500},
            data_scope_size=500,
        )
        if result.disposition == "allow":
            run_real_db_delete(...)
    """
    payload = build_intercept_payload(
        agent_id=agent_id,
        session_id=session_id,
        tool_name=tool_name,
        tool_params=tool_params,
        action_type=action_type,
        data_scope_size=data_scope_size,
        session_data_classification=session_data_classification,
        **extra_context,
    )
    with httpx.Client(timeout=timeout, headers={"User-Agent": "SentinelAI-AgentDemo/1.0"}) as client:
        resp = client.post(get_intercept_url(api_url), json=payload)
        resp.raise_for_status()
        return ToolInterceptResponse(**resp.json())


def enforce_governance(result: ToolInterceptResponse) -> None:
    """
    Standard enforcement — call after intercept, before your real tool.

    Raises PermissionError if the tool must not run.
    """
    if result.disposition in ("block", "deny"):
        raise PermissionError(f"Governance blocked: {result.reason}")
    if result.disposition == "require_hitl":
        raise PermissionError(f"HITL required — ticket {result.ticket_id}")


def governed_tool_call(
    api_url: str,
    *,
    agent_id: str,
    session_id: str,
    tool_name: str,
    run_tool: Callable[[], Any],
    tool_params: dict[str, Any] | None = None,
    action_type: str = "read",
    data_scope_size: int = 0,
    **extra_context: Any,
) -> Any:
    """
    Minimal wrapper: intercept → enforce → run your function.

    Example:
        governed_tool_call(
            SENTINELAI_API_URL,
            agent_id=agent_id,
            session_id=session_id,
            tool_name="db_query",
            tool_params={"table": "transactions"},
            run_tool=lambda: my_db.query("transactions"),
        )
    """
    result = call_governance_intercept(
        api_url,
        agent_id=agent_id,
        session_id=session_id,
        tool_name=tool_name,
        tool_params=tool_params,
        action_type=action_type,
        data_scope_size=data_scope_size,
        **extra_context,
    )
    enforce_governance(result)
    return run_tool()


# Alias used by CLI / UI server
DEFAULT_API = SENTINELAI_API_URL

# =============================================================================
# DEMO — mock tools and test scenarios (below)
# =============================================================================

_MOCK_DB: dict[str, list[dict]] = {
    "financial_records": [{"id": i, "amount": 100 * i} for i in range(1, 501)],
    "transactions": [{"id": i, "status": "posted"} for i in range(1, 51)],
    "customers": [{"id": f"c-{i}", "email": f"user{i}@example.com"} for i in range(1, 11)],
}


def mock_db_query(table: str, limit: int = 10, **_: Any) -> dict:
    rows = _MOCK_DB.get(table, [])[:limit]
    return {"table": table, "rows": rows, "count": len(rows), "_tool_msg": f"read {len(rows)} row(s) from {table!r}"}


def mock_db_delete(table: str, count: int = 1, **_: Any) -> dict:
    deleted = min(count, len(_MOCK_DB.get(table, [])))
    _MOCK_DB[table] = _MOCK_DB.get(table, [])[deleted:]
    return {
        "table": table,
        "deleted": deleted,
        "remaining": len(_MOCK_DB.get(table, [])),
        "_tool_msg": f"removed {deleted} row(s) from {table!r}",
    }


def mock_identity_verify(customer_id: str = "cust-001", **_: Any) -> dict:
    return {"customer_id": customer_id, "verified": True, "_tool_msg": f"verified {customer_id!r}"}


def mock_payment_process(amount: float, currency: str = "USD", **_: Any) -> dict:
    return {
        "amount": amount,
        "currency": currency,
        "status": "completed",
        "txn_id": uuid.uuid4().hex[:12],
        "_tool_msg": f"charged {currency} {amount:,.2f}",
    }


def mock_email_send(to: str, subject: str, body: str, **_: Any) -> dict:
    return {
        "to": to,
        "subject": subject,
        "sent": True,
        "message_id": uuid.uuid4().hex[:12],
        "_tool_msg": f"sent to {to!r}",
    }


def mock_crm_read(customer_id: str = "c-1001", **_: Any) -> dict:
    return {
        "customer_id": customer_id,
        "name": "Jane Doe",
        "tier": "gold",
        "_tool_msg": f"fetched customer {customer_id!r}",
    }


def mock_hr_records(employee_id: str = "e-42", **_: Any) -> dict:
    return {
        "employee_id": employee_id,
        "name": "Alex Rivera",
        "department": "Engineering",
        "_tool_msg": f"read HR record {employee_id!r}",
    }


def mock_benefits_lookup(plan: str = "health", **_: Any) -> dict:
    return {"plan": plan, "records": 120, "_tool_msg": f"benefits lookup for {plan!r}"}


def mock_code_search(query: str = "auth", **_: Any) -> dict:
    return {"query": query, "matches": 3, "_tool_msg": f"code search {query!r}"}


def mock_api_call(url: str, **_: Any) -> dict:
    return {"url": url, "status": 200, "_tool_msg": f"API call to {url!r}"}


MOCK_TOOLS: dict[str, Callable[..., dict]] = {
    "db_query": mock_db_query,
    "db_delete": mock_db_delete,
    "identity_verify": mock_identity_verify,
    "payment_process": mock_payment_process,
    "email_send": mock_email_send,
    "crm_read": mock_crm_read,
    "hr_records": mock_hr_records,
    "benefits_lookup": mock_benefits_lookup,
    "code_search": mock_code_search,
    "api_call": mock_api_call,
}

SCENARIO_META: dict[str, dict[str, str]] = {
    "finance-safe-read": {
        "title": "Finance — safe read",
        "agent": "Finance Agent",
        "expected": "allow",
        "description": "Read transactions within normal scope.",
    },
    "finance-bulk-delete": {
        "title": "Finance — bulk delete 500 rows",
        "agent": "Finance Agent",
        "expected": "block",
        "description": "Policy blocks mass delete after prior query.",
    },
    "finance-payment-no-verify": {
        "title": "Finance — payment without verify",
        "agent": "Finance Agent",
        "expected": "deny",
        "description": "WAF sequence rule: payment requires identity_verify first.",
    },
    "finance-payment-with-verify": {
        "title": "Finance — payment after verify",
        "agent": "Finance Agent",
        "expected": "allow",
        "description": "Small payment after identity verification.",
    },
    "support-external-email": {
        "title": "Support — external email",
        "agent": "Customer Support Agent",
        "expected": "require_hitl",
        "description": "Email to gmail.com triggers human approval.",
    },
    "support-internal-email": {
        "title": "Support — internal email",
        "agent": "Customer Support Agent",
        "expected": "allow",
        "description": "Email to company domain is allowed.",
    },
    "waf-sql-injection": {
        "title": "Finance — SQL injection attempt",
        "agent": "Finance Agent",
        "expected": "deny",
        "description": "WAF blocks injection patterns in tool params.",
    },
    "finance-high-value-payment": {
        "title": "Finance — high-value payment HITL",
        "agent": "Finance Agent",
        "expected": "require_hitl",
        "description": "Payment over $10k requires human approval.",
    },
    "finance-after-hours-delete": {
        "title": "Finance — after-hours delete HITL",
        "agent": "Finance Agent",
        "expected": "require_hitl",
        "description": "Small delete outside business hours triggers HITL.",
    },
    "support-bulk-crm": {
        "title": "Support — bulk CRM export HITL",
        "agent": "Customer Support Agent",
        "expected": "require_hitl",
        "description": "Large CRM segment read requires human approval.",
    },
    "support-sensitive-email": {
        "title": "Support — sensitive email body block",
        "agent": "Customer Support Agent",
        "expected": "block",
        "description": "Policy blocks emails containing password/credential language.",
    },
    "hr-phi-access": {
        "title": "HR — PHI record access HITL",
        "agent": "HR Agent",
        "expected": "require_hitl",
        "description": "HIPAA PHI access requires human approval.",
    },
    "developer-external-api": {
        "title": "Developer — external API HITL",
        "agent": "Developer Agent",
        "expected": "require_hitl",
        "description": "Calls to external vendor APIs require approval.",
    },
}

# Declarative steps for the browser agent UI (same flows as SCENARIOS callables).
SCENARIO_STEPS: dict[str, list[dict[str, Any]]] = {
    "finance-safe-read": [
        {"tool_name": "db_query", "params": {"table": "transactions", "limit": 5}, "data_scope_size": 5},
    ],
    "finance-bulk-delete": [
        {"tool_name": "db_query", "params": {"table": "financial_records", "limit": 1}, "data_scope_size": 1},
        {
            "tool_name": "db_delete",
            "action_type": "delete",
            "params": {"table": "financial_records", "count": 500},
            "data_scope_size": 500,
            "timestamp": "2026-07-04T14:00:00+00:00",
        },
    ],
    "finance-payment-no-verify": [
        {
            "tool_name": "payment_process",
            "action_type": "write",
            "params": {"amount": 250.0, "currency": "USD"},
            "data_scope_size": 250,
        },
    ],
    "finance-payment-with-verify": [
        {"tool_name": "identity_verify", "params": {"customer_id": "cust-8842"}},
        {
            "tool_name": "payment_process",
            "action_type": "write",
            "params": {"amount": 150.0, "currency": "USD"},
            "data_scope_size": 150,
            "timestamp": "2026-07-04T14:00:00+00:00",
        },
    ],
    "support-external-email": [
        {"tool_name": "crm_read", "params": {"customer_id": "c-1001"}, "data_scope_size": 1},
        {
            "tool_name": "email_send",
            "action_type": "write",
            "params": {
                "to": "customer@gmail.com",
                "subject": "Your support request",
                "body": "We received your ticket and will respond shortly.",
            },
        },
    ],
    "support-internal-email": [
        {
            "tool_name": "email_send",
            "action_type": "write",
            "params": {
                "to": "manager@company.com",
                "subject": "Escalation note",
                "body": "Customer issue needs review.",
            },
        },
    ],
    "waf-sql-injection": [
        {"tool_name": "db_query", "params": {"q": "DROP TABLE users; --", "table": "transactions"}},
    ],
    "finance-high-value-payment": [
        {"tool_name": "identity_verify", "params": {"customer_id": "cust-enterprise-01"}},
        {
            "tool_name": "payment_process",
            "action_type": "write",
            "params": {"amount": 50000.0, "currency": "USD"},
            "data_scope_size": 50000,
            "timestamp": "2026-07-04T14:00:00+00:00",
        },
    ],
    "finance-after-hours-delete": [
        {"tool_name": "db_query", "params": {"table": "financial_records", "limit": 1}, "data_scope_size": 1},
        {
            "tool_name": "db_delete",
            "action_type": "delete",
            "params": {"table": "financial_records", "count": 5},
            "data_scope_size": 5,
            "timestamp": "2026-07-04T22:00:00+00:00",
        },
    ],
    "support-bulk-crm": [
        {"tool_name": "crm_read", "params": {"segment": "all"}, "data_scope_size": 800},
    ],
    "support-sensitive-email": [
        {
            "tool_name": "email_send",
            "action_type": "write",
            "params": {
                "to": "user@company.com",
                "subject": "Security alert",
                "body": "Your password is expired — reset immediately.",
            },
        },
    ],
    "hr-phi-access": [
        {
            "tool_name": "hr_records",
            "params": {"employee_id": "e-99"},
            "data_scope_size": 1,
            "classification": "PHI",
        },
    ],
    "developer-external-api": [
        {
            "tool_name": "api_call",
            "action_type": "read",
            "params": {"url": "https://external-vendor.com/data"},
        },
    ],
}


class GovernedAgent:
    """Agent that asks SentinelAI before every tool call."""

    def __init__(
        self,
        name: str,
        agent_id: str,
        api_url: str,
        session_id: str | None = None,
        *,
        collect_events: bool = True,
    ):
        self.name = name
        self.agent_id = agent_id
        self.api_url = api_url.rstrip("/")
        self.session_id = session_id or f"demo-{uuid.uuid4().hex[:10]}"
        self.executed: list[str] = []
        self.blocked: list[str] = []
        self.events: list[dict[str, Any]] = []
        self._collect_events = collect_events

    def close(self) -> None:
        pass

    def _emit(self, kind: str, message: str, **extra: Any) -> None:
        if self._collect_events:
            self.events.append({"kind": kind, "message": message, **extra})

    def intercept(
        self,
        tool_name: str,
        action_type: str = "read",
        tool_params: dict[str, Any] | None = None,
        data_scope_size: int = 0,
        session_data_classification: str = "internal",
        timestamp: str | None = None,
        **extra_context: Any,
    ) -> ToolInterceptResponse:
        return call_governance_intercept(
            self.api_url,
            agent_id=self.agent_id,
            session_id=self.session_id,
            tool_name=tool_name,
            tool_params=tool_params,
            action_type=action_type,
            data_scope_size=data_scope_size,
            session_data_classification=session_data_classification,
            framework="demo_script",
            user_id="demo-user",
            timestamp=timestamp,
            **extra_context,
        )

    def call_tool(
        self,
        tool_name: str,
        *,
        action_type: str = "read",
        params: dict[str, Any] | None = None,
        data_scope_size: int = 0,
        classification: str = "internal",
        timestamp: str | None = None,
        **extra_context: Any,
    ) -> dict[str, Any] | None:
        params = params or {}
        self._emit("request", f"Agent wants {tool_name}({params})", tool=tool_name, params=params)

        result = self.intercept(
            tool_name=tool_name,
            action_type=action_type,
            tool_params=params,
            data_scope_size=data_scope_size,
            session_data_classification=classification,
            timestamp=timestamp,
            **extra_context,
        )

        disp = result.disposition
        self._emit(
            "governance",
            result.reason or "no reason",
            disposition=disp,
            tool=tool_name,
            ticket_id=result.ticket_id,
            violation_id=result.violation_id,
        )

        if disp in ("block", "deny"):
            self.blocked.append(tool_name)
            self._emit(
                "stopped",
                "Governance stopped this tool — not executed (correct behavior)",
                tool=tool_name,
                disposition=disp,
            )
            return None

        if disp == "require_hitl":
            self.blocked.append(tool_name)
            self._emit(
                "hitl",
                f"Waiting for human approval — ticket {result.ticket_id} (correct behavior)",
                tool=tool_name,
                ticket_id=result.ticket_id,
                disposition=disp,
            )
            return None

        if disp in ("allow", "warn", "audit_only"):
            fn = MOCK_TOOLS.get(tool_name)
            if fn is None:
                self.executed.append(tool_name)
                self._emit("executed", f"No mock for {tool_name!r}", tool=tool_name)
                return {"tool": tool_name, "mock": True}

            out = fn(**params)
            tool_msg = out.pop("_tool_msg", tool_name)
            self.executed.append(tool_name)
            self._emit("executed", f"[TOOL] {tool_name} → {tool_msg}", tool=tool_name, result=out)
            return out

        self.blocked.append(tool_name)
        self._emit("blocked", f"Unknown disposition {disp!r}", tool=tool_name, disposition=disp)
        return None


def scenario_finance_safe_read(agent: GovernedAgent) -> None:
    agent.call_tool("db_query", params={"table": "transactions", "limit": 5}, data_scope_size=5)


def scenario_finance_bulk_delete(agent: GovernedAgent) -> None:
    agent.call_tool("db_query", params={"table": "financial_records", "limit": 1}, data_scope_size=1)
    agent.call_tool(
        "db_delete",
        action_type="delete",
        params={"table": "financial_records", "count": 500},
        data_scope_size=500,
        timestamp="2026-07-04T14:00:00+00:00",
    )


def scenario_finance_payment_without_verify(agent: GovernedAgent) -> None:
    agent.call_tool(
        "payment_process",
        action_type="write",
        params={"amount": 250.0, "currency": "USD"},
        data_scope_size=250,
    )


def scenario_finance_payment_with_verify(agent: GovernedAgent) -> None:
    agent.call_tool("identity_verify", params={"customer_id": "cust-8842"})
    agent.call_tool(
        "payment_process",
        action_type="write",
        params={"amount": 150.0, "currency": "USD"},
        data_scope_size=150,
        timestamp="2026-07-04T14:00:00+00:00",
    )


def scenario_support_external_email(agent: GovernedAgent) -> None:
    agent.call_tool("crm_read", params={"customer_id": "c-1001"}, data_scope_size=1)
    agent.call_tool(
        "email_send",
        action_type="write",
        params={
            "to": "customer@gmail.com",
            "subject": "Your support request",
            "body": "We received your ticket and will respond shortly.",
        },
    )


def scenario_support_internal_email(agent: GovernedAgent) -> None:
    agent.call_tool(
        "email_send",
        action_type="write",
        params={
            "to": "manager@company.com",
            "subject": "Escalation note",
            "body": "Customer issue needs review.",
        },
    )


def scenario_waf_sql_injection(agent: GovernedAgent) -> None:
    agent.call_tool(
        "db_query",
        params={"q": "DROP TABLE users; --", "table": "transactions"},
    )


def scenario_finance_high_value_payment(agent: GovernedAgent) -> None:
    agent.call_tool("identity_verify", params={"customer_id": "cust-enterprise-01"})
    agent.call_tool(
        "payment_process",
        action_type="write",
        params={"amount": 50000.0, "currency": "USD"},
        data_scope_size=50000,
        timestamp="2026-07-04T14:00:00+00:00",
    )


def scenario_finance_after_hours_delete(agent: GovernedAgent) -> None:
    agent.call_tool("db_query", params={"table": "financial_records", "limit": 1}, data_scope_size=1)
    agent.call_tool(
        "db_delete",
        action_type="delete",
        params={"table": "financial_records", "count": 5},
        data_scope_size=5,
        timestamp="2026-07-04T22:00:00+00:00",
    )


def scenario_support_bulk_crm(agent: GovernedAgent) -> None:
    agent.call_tool(
        "crm_read",
        params={"segment": "all"},
        data_scope_size=800,
    )


def scenario_support_sensitive_email(agent: GovernedAgent) -> None:
    agent.call_tool(
        "email_send",
        action_type="write",
        params={
            "to": "user@company.com",
            "subject": "Security alert",
            "body": "Your password is expired — reset immediately.",
        },
    )


def scenario_hr_phi_access(agent: GovernedAgent) -> None:
    agent.call_tool(
        "hr_records",
        params={"employee_id": "e-99"},
        data_scope_size=1,
        classification="PHI",
    )


def scenario_developer_external_api(agent: GovernedAgent) -> None:
    agent.call_tool(
        "api_call",
        action_type="read",
        params={"url": "https://external-vendor.com/data"},
    )


SCENARIOS: dict[str, Callable[[GovernedAgent], None]] = {
    "finance-safe-read": scenario_finance_safe_read,
    "finance-bulk-delete": scenario_finance_bulk_delete,
    "finance-payment-no-verify": scenario_finance_payment_without_verify,
    "finance-payment-with-verify": scenario_finance_payment_with_verify,
    "support-external-email": scenario_support_external_email,
    "support-internal-email": scenario_support_internal_email,
    "waf-sql-injection": scenario_waf_sql_injection,
    "finance-high-value-payment": scenario_finance_high_value_payment,
    "finance-after-hours-delete": scenario_finance_after_hours_delete,
    "support-bulk-crm": scenario_support_bulk_crm,
    "support-sensitive-email": scenario_support_sensitive_email,
    "hr-phi-access": scenario_hr_phi_access,
    "developer-external-api": scenario_developer_external_api,
}


def _http_error_detail(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        url = str(exc.request.url)
        body = (exc.response.text or "")[:240].strip()
        return f"{exc.response.status_code} {exc.response.reason_phrase} on {url}" + (f" — {body}" if body else "")
    return str(exc)


def check_api_connection(api_url: str) -> dict[str, Any]:
    """Quick connectivity check — GET /v1/agents (read-only)."""
    api_url = api_url.rstrip("/")
    try:
        with httpx.Client(timeout=30.0, headers={"User-Agent": "SentinelAI-AgentDemo/1.0"}) as client:
            resp = client.get(f"{api_url}/agents")
            resp.raise_for_status()
            agents = resp.json().get("agents", [])
            return {
                "ok": True,
                "api_url": api_url,
                "agent_count": len(agents),
                "agents": [a.get("name") for a in agents],
            }
    except httpx.HTTPError as exc:
        return {"ok": False, "api_url": api_url, "error": _http_error_detail(exc)}


def ensure_demo_agents(api_url: str) -> dict[str, str]:
    """Resolve demo agent IDs. Does not call admin seed (may 403 on production)."""
    api_url = api_url.rstrip("/")
    with httpx.Client(timeout=45.0, headers={"User-Agent": "SentinelAI-AgentDemo/1.0"}) as client:
        resp = client.get(f"{api_url}/agents")
        resp.raise_for_status()
        agents = {a["name"]: a["agent_id"] for a in resp.json().get("agents", [])}

    required = (
        "Finance Agent",
        "Customer Support Agent",
        "HR Agent",
        "Developer Agent",
    )
    missing = [name for name in required if name not in agents]
    if missing:
        raise RuntimeError(
            f"Demo agents not registered: {', '.join(missing)}. "
            f"Found: {', '.join(agents.keys()) or '(none)'}. "
            "Ask an admin to run POST /v1/admin/seed-demo on the API once."
        )
    return agents


def list_scenarios() -> list[dict[str, Any]]:
    return [
        {"key": key, **meta, "steps": SCENARIO_STEPS.get(key, [])}
        for key, meta in SCENARIO_META.items()
    ]


def run_scenarios(api_url: str, scenario_keys: list[str] | None = None) -> dict[str, Any]:
    """Run one or more scenarios; return structured result for UI/API."""
    api_url = api_url.rstrip("/")
    keys = scenario_keys or list(SCENARIOS.keys())
    started = datetime.now(timezone.utc).isoformat()

    try:
        agents = ensure_demo_agents(api_url)
    except httpx.HTTPError as exc:
        return {"ok": False, "error": _http_error_detail(exc), "api_url": api_url}
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc), "api_url": api_url}

    results: list[dict[str, Any]] = []
    sessions: dict[str, list[str]] = {}
    executed: dict[str, list[str]] = {}
    stopped: dict[str, list[str]] = {}

    for key in keys:
        if key not in SCENARIOS:
            results.append({"key": key, "ok": False, "error": "Unknown scenario"})
            continue

        meta = SCENARIO_META[key]
        agent_name = meta["agent"]
        agent = GovernedAgent(agent_name, agents[agent_name], api_url)

        try:
            SCENARIOS[key](agent)
            ok = True
            err = None
        except httpx.HTTPError as exc:
            ok = False
            err = _http_error_detail(exc)

        steps = list(agent.events)
        last_gov = next((e for e in reversed(steps) if e.get("kind") == "governance"), None)
        actual = last_gov.get("disposition") if last_gov else None

        sessions.setdefault(agent_name, []).append(agent.session_id)
        executed.setdefault(agent_name, []).extend(agent.executed)
        stopped.setdefault(agent_name, []).extend(agent.blocked)

        results.append(
            {
                "key": key,
                "ok": ok,
                "error": err,
                "title": meta["title"],
                "agent": meta["agent"],
                "expected": meta["expected"],
                "description": meta["description"],
                "actual": actual,
                "passed": ok and actual == meta["expected"],
                "session_id": agent.session_id,
                "steps": steps,
            }
        )
        agent.close()

    def _replay(agent_name: str) -> str | None:
        ids = sessions.get(agent_name)
        if not ids:
            return None
        return f"{api_url}/decision/replay/{ids[-1]}"

    return {
        "ok": True,
        "api_url": api_url,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": results,
        "summary": {
            "sessions": sessions,
            "finance_executed": executed.get("Finance Agent", []),
            "finance_stopped": stopped.get("Finance Agent", []),
            "support_executed": executed.get("Customer Support Agent", []),
            "support_stopped": stopped.get("Customer Support Agent", []),
            "hr_executed": executed.get("HR Agent", []),
            "hr_stopped": stopped.get("HR Agent", []),
            "developer_executed": executed.get("Developer Agent", []),
            "developer_stopped": stopped.get("Developer Agent", []),
            "replay_finance": _replay("Finance Agent"),
            "replay_support": _replay("Customer Support Agent"),
            "replay_hr": _replay("HR Agent"),
            "replay_developer": _replay("Developer Agent"),
            "passed_count": sum(1 for r in results if r.get("passed")),
            "total_count": len(results),
        },
    }


def _print_cli_result(result: dict[str, Any]) -> None:
    if not result.get("ok"):
        print(f"ERROR: {result.get('error')}")
        return

    print(f"API: {result['api_url']}")
    for sc in result["scenarios"]:
        print("\n" + "=" * 60)
        print(f"{sc['title']} (expected: {sc['expected']})")
        print("=" * 60)
        for step in sc.get("steps", []):
            prefix = {
                "request": "→",
                "governance": "←",
                "executed": "✓",
                "stopped": "✓",
                "blocked": "✓",
                "hitl": "✓",
            }.get(step["kind"], "·")
            msg = step["message"]
            if step["kind"] == "governance":
                msg = f"{step.get('disposition', '').upper()} — {msg}"
            print(f"  {prefix} {msg}")
        status = "PASS" if sc.get("passed") else "CHECK"
        print(f"  Result: {status} (actual={sc.get('actual')})")

    summary = result["summary"]
    passed = summary.get("passed_count", 0)
    total = summary.get("total_count", 0)
    print("\n" + "=" * 60)
    print(f"ALL SCENARIOS: {passed}/{total} PASSED")
    print("=" * 60)
    agent_summary = [
        ("Finance Agent", "finance_executed", "finance_stopped"),
        ("Customer Support Agent", "support_executed", "support_stopped"),
        ("HR Agent", "hr_executed", "hr_stopped"),
        ("Developer Agent", "developer_executed", "developer_stopped"),
    ]
    for agent_name, exec_key, stop_key in agent_summary:
        agent_sessions = summary.get("sessions", {}).get(agent_name, [])
        if not agent_sessions:
            continue
        print(f"{agent_name}: {len(agent_sessions)} session(s), latest {agent_sessions[-1]}")
        print(f"  tools executed:        {summary.get(exec_key) or '(none)'}")
        print(f"  stopped by governance: {summary.get(stop_key) or '(none)'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run governed agent tool-call demo")
    parser.add_argument("--api-url", default=SENTINELAI_API_URL)
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()) + ["all"],
        default="all",
    )
    args = parser.parse_args()
    keys = list(SCENARIOS.keys()) if args.scenario == "all" else [args.scenario]

    print("SentinelAI Governed Agent Demo")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")

    result = run_scenarios(args.api_url.rstrip("/"), keys)
    _print_cli_result(result)
    print("\nDone.")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
