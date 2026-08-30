"""Cerebras-powered governed agent chat — LLM routes agents and intercepts every tool call."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Callable
from typing import Any

import httpx

from shared.config.settings import get_settings
from shared.llm.client import completion, extract_message_content, llm_configured, resolve_model
from shared.models.tool import ToolInterceptResponse

MAX_TOOL_ROUNDS = 6

_MOCK_DB: dict[str, list[dict]] = {
    "financial_records": [{"id": i, "amount": 100 * i} for i in range(1, 501)],
    "transactions": [{"id": i, "status": "posted"} for i in range(1, 51)],
    "customers": [{"id": f"c-{i}", "email": f"user{i}@example.com"} for i in range(1, 11)],
}


def _mock_db_query(table: str, limit: int = 10, **_: Any) -> dict:
    rows = _MOCK_DB.get(table, [])[:limit]
    return {"table": table, "rows": rows, "count": len(rows), "_tool_msg": f"read {len(rows)} row(s) from {table!r}"}


def _mock_db_delete(table: str, count: int = 1, **_: Any) -> dict:
    deleted = min(count, len(_MOCK_DB.get(table, [])))
    _MOCK_DB[table] = _MOCK_DB.get(table, [])[deleted:]
    return {
        "table": table,
        "deleted": deleted,
        "remaining": len(_MOCK_DB.get(table, [])),
        "_tool_msg": f"removed {deleted} row(s) from {table!r}",
    }


def _mock_identity_verify(customer_id: str = "cust-001", **_: Any) -> dict:
    return {"customer_id": customer_id, "verified": True, "_tool_msg": f"verified {customer_id!r}"}


def _mock_payment_process(amount: float, currency: str = "USD", **_: Any) -> dict:
    return {
        "amount": amount,
        "currency": currency,
        "status": "completed",
        "txn_id": uuid.uuid4().hex[:12],
        "_tool_msg": f"charged {currency} {amount:,.2f}",
    }


def _mock_email_send(to: str, subject: str, body: str, **_: Any) -> dict:
    return {
        "to": to,
        "subject": subject,
        "sent": True,
        "message_id": uuid.uuid4().hex[:12],
        "_tool_msg": f"sent to {to!r}",
    }


def _mock_crm_read(customer_id: str = "c-1001", **_: Any) -> dict:
    return {
        "customer_id": customer_id,
        "name": "Jane Doe",
        "tier": "gold",
        "_tool_msg": f"fetched customer {customer_id!r}",
    }


def _mock_hr_records(employee_id: str = "e-42", **_: Any) -> dict:
    return {
        "employee_id": employee_id,
        "name": "Alex Rivera",
        "department": "Engineering",
        "_tool_msg": f"read HR record {employee_id!r}",
    }


def _mock_benefits_lookup(plan: str = "health", **_: Any) -> dict:
    return {"plan": plan, "records": 120, "_tool_msg": f"benefits lookup for {plan!r}"}


def _mock_code_search(query: str = "auth", **_: Any) -> dict:
    return {"query": query, "matches": 3, "_tool_msg": f"code search {query!r}"}


def _mock_api_call(url: str, **_: Any) -> dict:
    return {"url": url, "status": 200, "_tool_msg": f"API call to {url!r}"}


MOCK_TOOLS: dict[str, Callable[..., dict]] = {
    "db_query": _mock_db_query,
    "db_delete": _mock_db_delete,
    "identity_verify": _mock_identity_verify,
    "payment_process": _mock_payment_process,
    "email_send": _mock_email_send,
    "crm_read": _mock_crm_read,
    "hr_records": _mock_hr_records,
    "benefits_lookup": _mock_benefits_lookup,
    "code_search": _mock_code_search,
    "api_call": _mock_api_call,
}


def resolve_governance_api_url(override: str | None = None) -> str:
    if override and override.strip():
        return override.strip().rstrip("/")
    env_url = os.environ.get("GOVERNANCE_API_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")
    return get_settings().governance_api_url.rstrip("/")


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
    framework: str = "agent_chat",
    **extra_context: Any,
) -> dict[str, Any]:
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
    ctx.update(extra_context)
    return {"context": ctx, "shadow_mode": False}


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
    target = f"{api_url.rstrip('/')}/tool/intercept"
    with httpx.Client(timeout=timeout, headers={"User-Agent": "SentinelAI-AgentChat/1.0"}) as client:
        resp = client.post(target, json=payload)
        resp.raise_for_status()
        return ToolInterceptResponse(**resp.json())


def ensure_demo_agents(api_url: str) -> dict[str, str]:
    api_url = api_url.rstrip("/")
    with httpx.Client(timeout=45.0, headers={"User-Agent": "SentinelAI-AgentChat/1.0"}) as client:
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


def llm_status() -> dict[str, Any]:
    configured = llm_configured()
    return {
        "configured": configured,
        "model": resolve_model() if configured else None,
    }

AGENT_PROFILES: dict[str, dict[str, Any]] = {
    "Finance Agent": {
        "team": "Finance",
        "purpose": "Financial records, payments, and reporting",
        "tools": [
            {
                "name": "db_query",
                "action_type": "read",
                "description": "Read rows from a table (params: table, limit, q for query text)",
            },
            {
                "name": "db_delete",
                "action_type": "delete",
                "description": "Delete records (params: table, count). Set data_scope_size to count.",
            },
            {
                "name": "identity_verify",
                "action_type": "read",
                "description": "Verify customer identity before payments (params: customer_id)",
            },
            {
                "name": "payment_process",
                "action_type": "write",
                "description": "Process a payment (params: amount, currency). Verify identity first for large amounts.",
            },
            {
                "name": "report_generate",
                "action_type": "read",
                "description": "Generate a financial report (params: report_type)",
            },
        ],
        "examples": [
            "Show me the latest transactions",
            "Verify customer cust-8842 and pay $150",
            "Generate a quarterly financial report",
        ],
    },
    "Customer Support Agent": {
        "team": "Support",
        "purpose": "Customer inquiries and email responses",
        "tools": [
            {
                "name": "crm_read",
                "action_type": "read",
                "description": "Read CRM record (params: customer_id)",
            },
            {
                "name": "email_send",
                "action_type": "write",
                "description": "Send email (params: to, subject, body). External domains may need approval.",
            },
        ],
        "examples": [
            "Look up customer c-1001",
            "Send an internal email to team@company.com",
        ],
    },
    "HR Agent": {
        "team": "Human Resources",
        "purpose": "Employee records and benefits",
        "tools": [
            {
                "name": "hr_records",
                "action_type": "read",
                "description": "Read employee record (params: employee_id)",
            },
            {
                "name": "benefits_lookup",
                "action_type": "read",
                "description": "Look up benefits plan (params: plan)",
            },
        ],
        "examples": [
            "Show employee e-42 record",
            "Look up health benefits",
        ],
    },
    "Developer Agent": {
        "team": "Engineering",
        "purpose": "Code search and external API calls",
        "tools": [
            {
                "name": "code_search",
                "action_type": "read",
                "description": "Search codebase (params: query)",
            },
            {
                "name": "api_call",
                "action_type": "write",
                "description": "Call external API (params: url, method)",
            },
        ],
        "examples": [
            "Search code for authentication middleware",
        ],
    },
}


# Prompts that should trigger block or deny from governance (see governed_agent_demo scenarios).
DENY_BLOCK_SUGGESTIONS: list[dict[str, str]] = [
    {
        "text": "Delete 500 financial records",
        "expected": "block",
        "reason": "Bulk delete exceeds 100 record limit",
    },
    {
        "text": "Process a $250 payment without verifying the customer",
        "expected": "deny",
        "reason": "WAF: payment_process requires identity_verify first",
    },
    {
        "text": "Query transactions with DROP TABLE users; --",
        "expected": "deny",
        "reason": "WAF blocks SQL injection in tool parameters",
    },
    {
        "text": "Email user@company.com that their password is expired",
        "expected": "block",
        "reason": "Policy blocks sensitive data patterns in email body",
    },
    {
        "text": "Charge $500 to customer cust-001 without identity verification",
        "expected": "deny",
        "reason": "WAF tool sequence: verify before payment",
    },
    {
        "text": "Delete 500 rows from the financial_records table",
        "expected": "block",
        "reason": "Mass delete blocked by finance policy",
    },
]

def _normalize_prompt(text: str) -> str:
    return " ".join(text.strip().split()).casefold()


# Exact sidebar prompts → deterministic tool payloads for governance testing.
GOVERNANCE_TEST_SCENARIOS: dict[str, dict[str, Any]] = {
    _normalize_prompt("Delete 500 financial records"): {
        "agent_name": "Finance Agent",
        "tool_name": "db_delete",
        "action_type": "delete",
        "params": {"table": "financial_records", "count": 500},
        "data_scope_size": 500,
    },
    _normalize_prompt("Process a $250 payment without verifying the customer"): {
        "agent_name": "Finance Agent",
        "tool_name": "payment_process",
        "action_type": "write",
        "params": {"amount": 250.0, "currency": "USD"},
        "data_scope_size": 250,
    },
    _normalize_prompt("Query transactions with DROP TABLE users; --"): {
        "agent_name": "Finance Agent",
        "tool_name": "db_query",
        "action_type": "read",
        "params": {"q": "DROP TABLE users; --", "table": "transactions"},
        "data_scope_size": 10,
    },
    _normalize_prompt("Email user@company.com that their password is expired"): {
        "agent_name": "Customer Support Agent",
        "tool_name": "email_send",
        "action_type": "write",
        "params": {
            "to": "user@company.com",
            "subject": "Security alert",
            "body": "Your password is expired — reset immediately.",
        },
        "data_scope_size": 0,
    },
    _normalize_prompt("Charge $500 to customer cust-001 without identity verification"): {
        "agent_name": "Finance Agent",
        "tool_name": "payment_process",
        "action_type": "write",
        "params": {"amount": 500.0, "currency": "USD", "customer_id": "cust-001"},
        "data_scope_size": 500,
    },
    _normalize_prompt("Delete 500 rows from the financial_records table"): {
        "agent_name": "Finance Agent",
        "tool_name": "db_delete",
        "action_type": "delete",
        "params": {"table": "financial_records", "count": 500},
        "data_scope_size": 500,
    },
    _normalize_prompt("Email customer@gmail.com about their ticket"): {
        "agent_name": "Customer Support Agent",
        "steps": [
            {
                "tool_name": "crm_read",
                "action_type": "read",
                "params": {"customer_id": "c-1001"},
                "data_scope_size": 1,
            },
            {
                "tool_name": "email_send",
                "action_type": "write",
                "params": {
                    "to": "customer@gmail.com",
                    "subject": "Your support request",
                    "body": "We received your ticket and will respond shortly.",
                },
                "data_scope_size": 0,
            },
        ],
    },
    _normalize_prompt("Process a $50,000 payment for customer cust-enterprise-01"): {
        "agent_name": "Finance Agent",
        "steps": [
            {
                "tool_name": "identity_verify",
                "action_type": "read",
                "params": {"customer_id": "cust-enterprise-01"},
                "data_scope_size": 0,
            },
            {
                "tool_name": "payment_process",
                "action_type": "write",
                "params": {"amount": 50000.0, "currency": "USD", "customer_id": "cust-enterprise-01"},
                "data_scope_size": 50000,
            },
        ],
    },
    _normalize_prompt("Call https://api.external.com/data"): {
        "agent_name": "Developer Agent",
        "tool_name": "api_call",
        "action_type": "write",
        "params": {"url": "https://api.external.com/data", "method": "GET"},
        "data_scope_size": 0,
    },
    _normalize_prompt("Access PHI medical records for employee e-99"): {
        "agent_name": "HR Agent",
        "tool_name": "hr_records",
        "action_type": "read",
        "params": {"employee_id": "e-99", "record_type": "medical"},
        "data_scope_size": 1,
        "session_data_classification": "PHI",
    },
    _normalize_prompt("Export all 800 CRM customer records"): {
        "agent_name": "Customer Support Agent",
        "tool_name": "crm_read",
        "action_type": "read",
        "params": {"segment": "all"},
        "data_scope_size": 800,
    },
}


def _match_governance_scenario(user_message: str) -> dict[str, Any] | None:
    return GOVERNANCE_TEST_SCENARIOS.get(_normalize_prompt(user_message))


def _enrich_tool_params(
    tool_name: str,
    params: dict[str, Any],
    user_message: str,
) -> dict[str, Any]:
    """Pass injection / user text into tool params so WAF can evaluate them."""
    merged = dict(params)
    if tool_name != "db_query":
        return merged
    if merged.get("q"):
        return merged
    injection = re.search(
        r"(DROP\s+TABLE\b[^;]*;?\s*--|UNION\s+SELECT\b[^;]*;?\s*--|;\s*DROP\b[^;]*)",
        user_message,
        re.IGNORECASE,
    )
    if injection:
        merged["q"] = injection.group(0).strip()
    elif "query" in user_message.casefold() or "transaction" in user_message.casefold():
        merged.setdefault("q", user_message.strip())
    return merged


def _reply_from_governance(
    *,
    disposition: str,
    tool_name: str,
    reason: str | None,
    ticket_id: str | None,
) -> str:
    if disposition in ("block", "deny"):
        return (
            f"Governance {disposition}: {reason or 'this action is not allowed'}. "
            f"The `{tool_name}` tool was not executed."
        )
    if disposition == "require_hitl":
        ticket = ticket_id or "pending"
        return (
            f"This action requires human approval before I can proceed. "
            f"Reason: {reason or 'policy requires HITL'}. "
            f"Approval ticket: {ticket}."
        )
    return f"The `{tool_name}` action was allowed by governance."


def _scenario_steps(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize a test scenario into ordered intercept steps."""
    if steps := scenario.get("steps"):
        return list(steps)
    return [
        {
            "tool_name": scenario["tool_name"],
            "action_type": scenario.get("action_type") or "read",
            "params": dict(scenario.get("params") or {}),
            "data_scope_size": int(scenario.get("data_scope_size") or 0),
            "session_data_classification": scenario.get("session_data_classification"),
        }
    ]


def _run_forced_governance_scenario(
    *,
    scenario: dict[str, Any],
    user_message: str,
    history: list[dict[str, str]],
    session_id: str,
    agent_id: str,
    agent_name: str,
    api_url: str,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run a sidebar test prompt through POST /tool/intercept with known payloads."""
    classification = str(scenario.get("session_data_classification") or "internal")
    steps = _scenario_steps(scenario)
    last_gov: ToolInterceptResponse | None = None
    last_tool_name = ""
    last_params: dict[str, Any] = {}
    reply = ""

    for step in steps:
        tool_name = str(step["tool_name"])
        action_type = str(step.get("action_type") or "read")
        params = dict(step.get("params") or {})
        data_scope_size = int(step.get("data_scope_size") or 0)
        step_classification = str(step.get("session_data_classification") or classification)

        events.append(
            {
                "kind": "tool_intent",
                "agent_name": agent_name,
                "tool_name": tool_name,
                "action_type": action_type,
                "params": params,
                "data_scope_size": data_scope_size,
                "forced_scenario": True,
            }
        )

        request_payload = build_intercept_payload(
            agent_id=agent_id,
            session_id=session_id,
            tool_name=tool_name,
            tool_params=params,
            action_type=action_type,
            data_scope_size=data_scope_size,
            session_data_classification=step_classification,
            framework="agent_demo_chat",
        )

        try:
            gov = call_governance_intercept(
                api_url,
                agent_id=agent_id,
                session_id=session_id,
                tool_name=tool_name,
                tool_params=params,
                action_type=action_type,
                data_scope_size=data_scope_size,
                session_data_classification=step_classification,
                framework="agent_demo_chat",
            )
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "error": f"Governance intercept failed: {exc}",
                "session_id": session_id,
                "events": events,
            }

        events.append(
            _governance_event(
                tool_name=tool_name,
                params=params,
                action_type=action_type,
                data_scope_size=data_scope_size,
                request=request_payload,
                response=gov,
            )
        )
        events[-1]["agent_name"] = agent_name

        last_gov = gov
        last_tool_name = tool_name
        last_params = params
        disp = gov.disposition

        if disp in ("block", "deny", "require_hitl"):
            reply = _reply_from_governance(
                disposition=disp,
                tool_name=tool_name,
                reason=gov.reason,
                ticket_id=gov.ticket_id,
            )
            break

        if disp in ("allow", "warn", "audit_only"):
            result = _mock_execute(tool_name, params)
            events.append({"kind": "executed", "tool_name": tool_name, "result": result})
            reply = result.get("message") or f"Executed {tool_name}."
            continue

        reply = f"Unknown governance disposition: {disp}"
        break

    if last_gov is None:
        reply = "No governance steps were executed."

    updated_history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": reply},
    ]
    return {
        "ok": True,
        "reply": reply,
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "events": events,
        "history": updated_history,
        "llm_model": "governance test scenario (deterministic)",
    }


# Prompts that should trigger require_hitl (shown separately — not executed until approved).
HITL_SUGGESTIONS: list[dict[str, str]] = [
    {
        "text": "Email customer@gmail.com about their ticket",
        "expected": "require_hitl",
        "reason": "External email requires human approval",
    },
    {
        "text": "Process a $50,000 payment for customer cust-enterprise-01",
        "expected": "require_hitl",
        "reason": "High-value payment requires finance approval",
    },
    {
        "text": "Call https://api.external.com/data",
        "expected": "require_hitl",
        "reason": "External API call requires engineering review",
    },
    {
        "text": "Access PHI medical records for employee e-99",
        "expected": "require_hitl",
        "reason": "PHI access requires HIPAA review",
    },
    {
        "text": "Export all 800 CRM customer records",
        "expected": "require_hitl",
        "reason": "Bulk CRM export requires supervisor approval",
    },
]


def list_chat_agents() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "team": profile["team"],
            "purpose": profile["purpose"],
            "tools": [t["name"] for t in profile["tools"]],
            "examples": profile["examples"],
        }
        for name, profile in AGENT_PROFILES.items()
    ]


def list_chat_suggestions() -> dict[str, Any]:
    """Example prompts for the chat sidebar — allow, deny/block, and HITL."""
    seen: set[str] = set()
    try_asking: list[str] = []
    for profile in AGENT_PROFILES.values():
        for example in profile.get("examples", []):
            if example not in seen:
                seen.add(example)
                try_asking.append(example)

    return {
        "try_asking": try_asking,
        "deny_block": DENY_BLOCK_SUGGESTIONS,
        "hitl": HITL_SUGGESTIONS,
    }


def _build_router_prompt() -> str:
    lines = []
    for name, profile in AGENT_PROFILES.items():
        tools = ", ".join(t["name"] for t in profile["tools"])
        lines.append(f"- {name} ({profile['team']}): {profile['purpose']}. Tools: {tools}")
    catalog = "\n".join(lines)
    return f"""You route user requests to the correct governed backend agent.

Agents:
{catalog}

Reply with ONLY valid JSON (one object, no markdown):
{{"agent_name":"<exact agent name from list above>","reason":"brief routing reason"}}

Rules:
- Pick the agent whose tools best match the user's intent.
- Payments, transactions, database, financial reports → Finance Agent
- Customer email, CRM → Customer Support Agent
- Employee records, benefits → HR Agent
- Code search, external APIs → Developer Agent
- If the conversation is a follow-up (count, customer ID, "yes"), keep the same agent as before unless the user clearly switched topics."""


def _route_agent_fallback(user_message: str, active_agent: str | None) -> str:
    text = user_message.lower()
    if active_agent and len(text.split()) <= 4:
        if text.isdigit() or text in {"yes", "no", "ok", "confirm", "y", "n"}:
            return active_agent

    rules: list[tuple[str, str]] = [
        (
            "Customer Support Agent",
            r"(send\s+.*\s*email|email\s+.+\@|\@[a-z0-9.-]+\.(com|net|org)|\bcrm\b|customer@gmail|password is expired|password.*expired)",
        ),
        ("HR Agent", r"\b(employee|benefits|hr record|phi|payroll|health plan|hipaa|medical record)\b"),
        (
            "Developer Agent",
            r"\b(code search|search code|github|external api|api_call|https?://api\.)",
        ),
        (
            "Finance Agent",
            r"\b(pay(ment)?|transaction|financial|invoice|db delete|delete \d+ record|verify.*customer|\$\d|drop table)",
        ),
    ]
    for agent_name, pattern in rules:
        if re.search(pattern, text, re.I):
            return agent_name
    return active_agent or "Finance Agent"


def _keyword_route(user_message: str) -> tuple[str, str] | None:
    """High-confidence keyword routing before calling the LLM."""
    text = user_message.lower()
    rules: list[tuple[str, str, str]] = [
        (
            "Customer Support Agent",
            r"(send\s+.*\s*email|email\s+.+\@|\@[a-z0-9.-]+\.(com|net|org)|\bcrm\b|customer@gmail|password is expired|export.*crm)",
            "customer email or CRM request",
        ),
        (
            "HR Agent",
            r"\b(employee|benefits|hr record|phi|payroll|health plan|hipaa|medical record)\b",
            "HR / benefits request",
        ),
        (
            "Developer Agent",
            r"\b(code search|search code|github|external api|https?://)",
            "developer / API request",
        ),
        (
            "Finance Agent",
            r"\b(payment|pay \$|transaction|financial record|delete \d+|verify.*customer|\$\d{2,}|drop table)",
            "finance / payment request",
        ),
    ]
    for agent_name, pattern, reason in rules:
        if re.search(pattern, text, re.I):
            return agent_name, reason
    return None


def route_agent(
    user_message: str,
    history: list[dict[str, str]] | None = None,
    active_agent: str | None = None,
) -> tuple[str, str]:
    """Pick which registered agent should handle this turn."""
    text = user_message.strip()
    if active_agent and active_agent in AGENT_PROFILES:
        if text.isdigit() or text.lower() in {"yes", "no", "ok", "confirm", "y", "n"}:
            return active_agent, "continuing prior conversation"

    keyword = _keyword_route(user_message)
    if keyword:
        return keyword

    messages: list[dict[str, str]] = [{"role": "system", "content": _build_router_prompt()}]
    if active_agent:
        messages.append(
            {
                "role": "system",
                "content": f"Active agent for this session so far: {active_agent}",
            }
        )
    for turn in (history or [])[-8:]:
        role = turn.get("role")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    try:
        response = completion(messages=messages, max_tokens=64, temperature=0.0)
        raw = extract_message_content(response)
        objs = _extract_json_objects(raw)
        for obj in objs:
            name = obj.get("agent_name")
            if name in AGENT_PROFILES:
                reason = str(obj.get("reason") or "routed by LLM").strip()
                return name, reason
    except Exception:
        pass

    chosen = _route_agent_fallback(user_message, active_agent)
    return chosen, "routed by keyword fallback"


def _build_system_prompt(agent_name: str) -> str:
    profile = AGENT_PROFILES[agent_name]
    tool_lines = "\n".join(
        f"- {t['name']} ({t['action_type']}): {t['description']}" for t in profile["tools"]
    )
    return f"""You are {agent_name}, a governed AI agent for {profile['team']}.
Purpose: {profile['purpose']}

Every tool call is checked by SentinelAI governance BEFORE execution. If blocked, explain why and suggest a compliant alternative.

Available tools:
{tool_lines}

RESPONSE FORMAT — reply with ONLY valid JSON (no markdown fences):

To answer without tools:
{{"type":"message","content":"your reply to the user"}}

To use a tool:
{{"type":"tool_call","tool_name":"...","action_type":"read|write|delete","params":{{}},"data_scope_size":0}}

Rules:
- Output exactly ONE JSON object per response — never concatenate multiple JSON objects.
- Use tools when the user asks you to perform an action (read data, send email, delete records, pay, etc.).
- Use the full conversation: if the user already gave a table name, count, customer ID, or said "yes", act immediately — do not ask again.
- Set data_scope_size to records affected (delete count) or payment amount in whole dollars (e.g. $10,000 → 10000).
- When the user asks to verify and pay, call identity_verify first, then payment_process in the next response after verification succeeds.
- After tool results are returned, respond with a {{"type":"message",...}} summarizing outcomes in plain language (never repeat raw JSON to the user).
- Be concise and professional."""


def _extract_json_objects(text: str) -> list[dict[str, Any]]:
    """Parse one or more JSON objects from LLM output (handles concatenated responses)."""
    text = (text or "").strip()
    if not text:
        return []

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()

    objects: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx] not in "{[":
            idx += 1
        if idx >= len(text):
            break
        try:
            obj, end = decoder.raw_decode(text, idx)
            if isinstance(obj, dict):
                objects.append(obj)
            idx = end
        except json.JSONDecodeError:
            idx += 1
    return objects


def _parse_llm_response(text: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Split LLM output into optional tool_call and message objects."""
    objects = _extract_json_objects(text)
    if not objects:
        return None, None

    tool_calls = [o for o in objects if o.get("type") == "tool_call"]
    messages = [o for o in objects if o.get("type") == "message"]

    if len(objects) == 1:
        obj = objects[0]
        if obj.get("type") == "tool_call":
            return obj, None
        if obj.get("type") == "message":
            return None, obj
        return None, None

    return (tool_calls[0] if tool_calls else None), (messages[-1] if messages else None)


def _plain_text_from_raw(raw: str) -> str:
    """Never show raw JSON blobs in the chat UI."""
    _tool, message = _parse_llm_response(raw)
    if message:
        content = str(message.get("content") or "").strip()
        if content:
            return content

    # Strip JSON object literals; keep any surrounding prose.
    stripped = raw
    for obj in _extract_json_objects(raw):
        try:
            stripped = stripped.replace(json.dumps(obj, separators=(",", ":")), "")
            stripped = stripped.replace(json.dumps(obj), "")
        except (TypeError, ValueError):
            pass
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if stripped and not stripped.startswith("{"):
        return stripped
    return "Done — see the governance trace for details."


def _summarize_from_events(events: list[dict[str, Any]]) -> str:
    """Build a user-facing reply when the LLM forgets to send a final message."""
    lines: list[str] = []
    for event in events:
        kind = event.get("kind")
        if kind == "executed":
            result = event.get("result") or {}
            msg = result.get("message") or event.get("tool_name", "tool")
            lines.append(f"✓ {msg}")
        elif kind == "governance":
            disp = event.get("disposition")
            tool = event.get("tool_name", "action")
            reason = event.get("reason") or disp
            if disp in ("block", "deny"):
                lines.append(f"✗ {tool} blocked: {reason}")
            elif disp == "require_hitl":
                ticket = event.get("ticket_id") or "pending"
                lines.append(f"⏸ {tool} needs approval (ticket {ticket}): {reason}")
            elif disp in ("allow", "warn", "audit_only"):
                lines.append(f"✓ {tool} allowed: {reason}")

    if not lines:
        return "I couldn't finish that request. Please try again."
    return "\n".join(lines)


def _extract_json(text: str) -> dict[str, Any] | None:
    """Legacy single-object parser — prefer _parse_llm_response."""
    tool, message = _parse_llm_response(text)
    return tool or message


def _mock_execute(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    fn = MOCK_TOOLS.get(tool_name)
    if fn is None:
        return {"tool": tool_name, "status": "mock_ok", "params": params}
    out = fn(**params)
    msg = out.pop("_tool_msg", tool_name)
    return {"tool": tool_name, "message": msg, "result": out}


def _governance_event(
    *,
    tool_name: str,
    params: dict[str, Any],
    action_type: str,
    data_scope_size: int,
    request: dict[str, Any],
    response: ToolInterceptResponse,
) -> dict[str, Any]:
    return {
        "kind": "governance",
        "tool_name": tool_name,
        "action_type": action_type,
        "params": params,
        "data_scope_size": data_scope_size,
        "disposition": response.disposition,
        "reason": response.reason,
        "ticket_id": response.ticket_id,
        "violation_id": response.violation_id,
        "request": request,
        "response": response.model_dump(),
    }


def run_chat_turn(
    *,
    user_message: str,
    history: list[dict[str, str]] | None = None,
    session_id: str | None = None,
    agent_name: str | None = None,
    active_agent: str | None = None,
    api_url: str | None = None,
) -> dict[str, Any]:
    """Process one user message: route agent → Cerebras → tool calls → governance intercept."""
    if not llm_configured():
        return {
            "ok": False,
            "error": "No LLM configured. Set CEREBRAS_API_KEY in the project .env file.",
        }

    api_url = resolve_governance_api_url(api_url)
    history = list(history or [])
    events: list[dict[str, Any]] = []
    events.append({"kind": "user", "content": user_message})

    if agent_name and agent_name in AGENT_PROFILES:
        chosen_agent = agent_name
        route_reason = "explicit"
    else:
        chosen_agent, route_reason = route_agent(user_message, history, active_agent)
        events.append(
            {
                "kind": "route",
                "agent_name": chosen_agent,
                "reason": route_reason,
            }
        )

    agent_name = chosen_agent
    if agent_name not in AGENT_PROFILES:
        return {"ok": False, "error": f"Unknown agent: {agent_name}"}

    try:
        agents = ensure_demo_agents(api_url)
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"Governance API unreachable: {exc}", "events": events}
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc), "events": events}

    agent_id = agents[agent_name]
    session_id = session_id or f"chat-{uuid.uuid4().hex[:12]}"

    scenario = _match_governance_scenario(user_message)
    if scenario:
        scenario_agent = scenario.get("agent_name")
        if scenario_agent and scenario_agent in AGENT_PROFILES:
            agent_name = scenario_agent
            agent_id = agents[agent_name]
            events.append(
                {
                    "kind": "route",
                    "agent_name": agent_name,
                    "reason": "governance test scenario",
                }
            )
        return _run_forced_governance_scenario(
            scenario=scenario,
            user_message=user_message,
            history=history,
            session_id=session_id,
            agent_id=agent_id,
            agent_name=agent_name,
            api_url=api_url,
            events=events,
        )

    messages: list[dict[str, str]] = [{"role": "system", "content": _build_system_prompt(agent_name)}]
    for turn in history[-20:]:
        role = turn.get("role")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    final_reply = ""
    pending_message: str | None = None
    tools_ran_this_turn = False
    updated_history = history + [{"role": "user", "content": user_message}]

    for round_idx in range(MAX_TOOL_ROUNDS):
        try:
            response = completion(messages=messages, max_tokens=350, temperature=0.15)
            raw = extract_message_content(response)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"LLM error: {exc}",
                "session_id": session_id,
                "events": events,
            }

        events.append({"kind": "llm", "round": round_idx + 1, "raw": raw})
        parsed_tool, parsed_message = _parse_llm_response(raw)

        if parsed_message and not parsed_tool:
            final_reply = str(parsed_message.get("content") or "").strip() or _plain_text_from_raw(raw)
            messages.append({"role": "assistant", "content": raw})
            updated_history.append({"role": "assistant", "content": final_reply})
            break

        if parsed_tool is None and parsed_message is None:
            final_reply = _plain_text_from_raw(raw)
            messages.append({"role": "assistant", "content": raw})
            updated_history.append({"role": "assistant", "content": final_reply})
            break

        if parsed_message:
            pending_message = str(parsed_message.get("content") or "").strip() or None

        parsed = parsed_tool
        if parsed is None:
            continue

        if parsed.get("type") != "tool_call":
            final_reply = _plain_text_from_raw(raw)
            messages.append({"role": "assistant", "content": raw})
            updated_history.append({"role": "assistant", "content": final_reply})
            break

        tool_name = str(parsed.get("tool_name") or "")
        action_type = str(parsed.get("action_type") or "read")
        params = parsed.get("params") if isinstance(parsed.get("params"), dict) else {}
        params = _enrich_tool_params(tool_name, params, user_message)
        data_scope_size = int(parsed.get("data_scope_size") or 0)

        # Infer data_scope_size when the LLM omits it.
        if data_scope_size <= 0:
            if tool_name == "payment_process" and "amount" in params:
                data_scope_size = int(float(params["amount"]))
            elif tool_name == "db_delete" and "count" in params:
                data_scope_size = int(params["count"])

        events.append(
            {
                "kind": "tool_intent",
                "agent_name": agent_name,
                "tool_name": tool_name,
                "action_type": action_type,
                "params": params,
                "data_scope_size": data_scope_size,
            }
        )

        request_payload = build_intercept_payload(
            agent_id=agent_id,
            session_id=session_id,
            tool_name=tool_name,
            tool_params=params,
            action_type=action_type,
            data_scope_size=data_scope_size,
            framework="agent_demo_chat",
        )

        try:
            gov = call_governance_intercept(
                api_url,
                agent_id=agent_id,
                session_id=session_id,
                tool_name=tool_name,
                tool_params=params,
                action_type=action_type,
                data_scope_size=data_scope_size,
                framework="agent_demo_chat",
            )
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "error": f"Governance intercept failed: {exc}",
                "session_id": session_id,
                "events": events,
            }

        events.append(
            _governance_event(
                tool_name=tool_name,
                params=params,
                action_type=action_type,
                data_scope_size=data_scope_size,
                request=request_payload,
                response=gov,
            )
        )
        events[-1]["agent_name"] = agent_name

        disp = gov.disposition
        if disp in ("block", "deny"):
            tools_ran_this_turn = True
            pending_message = None
            tool_note = (
                f"Governance {disp}: {gov.reason or 'blocked'}. "
                "The tool was NOT executed. Explain this to the user and suggest a compliant approach."
            )
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"[Tool blocked] {tool_note}"})
            continue

        if disp == "require_hitl":
            tools_ran_this_turn = True
            pending_message = None
            tool_note = (
                f"Governance require_hitl: {gov.reason or 'approval required'}. "
                f"Ticket {gov.ticket_id}. The tool was NOT executed until a human approves."
            )
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"[Tool pending HITL] {tool_note}"})
            final_reply = (
                f"This action requires human approval before I can proceed. "
                f"Reason: {gov.reason or 'policy requires HITL'}. "
                f"Approval ticket: {gov.ticket_id or 'pending'}."
            )
            updated_history.append({"role": "assistant", "content": final_reply})
            break

        if disp in ("allow", "warn", "audit_only"):
            tools_ran_this_turn = True
            result = _mock_execute(tool_name, params)
            events.append({"kind": "executed", "tool_name": tool_name, "result": result})
            tool_note = f"[Tool executed] {json.dumps(result, default=str)}"
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": tool_note})
            if pending_message:
                final_reply = pending_message
                pending_message = None
                updated_history.append({"role": "assistant", "content": final_reply})
                break
            continue

        tools_ran_this_turn = True
        pending_message = None
        tool_note = f"[Tool unknown disposition {disp!r}]"
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": tool_note})

    else:
        if pending_message:
            final_reply = pending_message
        elif tools_ran_this_turn:
            final_reply = _summarize_from_events(events)
        else:
            final_reply = "I reached the maximum number of tool steps for this turn."
        updated_history.append({"role": "assistant", "content": final_reply})

    if not final_reply:
        final_reply = _summarize_from_events(events) if tools_ran_this_turn else "I couldn't complete that request."
        if updated_history[-1]["role"] != "assistant":
            updated_history.append({"role": "assistant", "content": final_reply})
        elif updated_history[-1].get("content") != final_reply:
            updated_history[-1]["content"] = final_reply

    return {
        "ok": True,
        "reply": final_reply,
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "events": events,
        "history": updated_history,
        "llm_model": "cerebras (via LiteLLM)",
    }
