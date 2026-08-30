#!/usr/bin/env python3
"""Run governance intercept cases and export/append results to Excel.

Sheets:
  - Agent Cases      — every intercept with expected vs actual
  - Policy Rules     — full policy inventory from YAML
  - WAF Rules        — WAF rule types and defaults
  - Coverage Matrix  — rule × scenario coverage
  - Summary          — per-run aggregates (appended)
"""

from __future__ import annotations

import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICIES_DIR = PROJECT_ROOT / "governance" / "policies"
API_URL = os.environ.get("API_URL", "http://localhost:8080/v1").rstrip("/")
OUTPUT = Path(os.environ.get("OUTPUT_XLSX", PROJECT_ROOT / "reports" / "sentinelai_100_cases.xlsx"))
CONSOLIDATED = Path(os.environ.get("CONSOLIDATED_XLSX", PROJECT_ROOT / "reports" / "sentinelai_consolidated_report.xlsx"))
APPEND = os.environ.get("APPEND", "0") != "0"
INCLUDE_SPECIAL = os.environ.get("INCLUDE_SPECIAL", "0") == "1"

# Each template: agent, scenario, tool, action, scope, params, expected disposition,
# optional policy_rule / waf_rule / ps_id / classification / timestamp / prev_violations /
# delegation_depth / setup_tools / session_key / shadow_mode
CASE_TEMPLATES: list[dict] = [
    # ── Finance Agent ──────────────────────────────────────────────────────
    {"agent": "Finance Agent", "scenario": "Safe read", "tool": "db_query", "action": "read", "scope": 10,
     "params": {"table": "transactions"}, "expected": "allow", "policy_rule": "log-internal-reads", "ps_id": "PS-10.2"},
    {"agent": "Finance Agent", "scenario": "Small delete (with prior query)", "tool": "db_delete", "action": "delete", "scope": 5,
     "params": {"table": "financial_records", "count": 5}, "setup_tools": ["db_query"], "expected": "allow",
     "policy_rule": "log-internal-reads", "ps_id": "PS-10.2",
     "timestamp": "2026-07-04T14:00:00+00:00"},
    {"agent": "Finance Agent", "scenario": "Bulk delete block", "tool": "db_delete", "action": "delete", "scope": 500,
     "params": {"table": "financial_records", "count": 500}, "setup_tools": ["db_query"], "expected": "block",
     "policy_rule": "bulk-delete-block", "ps_id": "PS-10.2", "timestamp": "2026-07-04T14:00:00+00:00"},
    {"agent": "Finance Agent", "scenario": "Borderline delete 101", "tool": "db_delete", "action": "delete", "scope": 101,
     "params": {"table": "financial_records", "count": 101}, "setup_tools": ["db_query"], "expected": "block",
     "policy_rule": "bulk-delete-block", "ps_id": "PS-10.2", "timestamp": "2026-07-04T14:00:00+00:00"},
    {"agent": "Finance Agent", "scenario": "After-hours write HITL", "tool": "db_delete", "action": "delete", "scope": 5,
     "params": {"table": "financial_records", "count": 5}, "setup_tools": ["db_query"], "expected": "require_hitl",
     "policy_rule": "after-hours-write-hitl", "ps_id": "PS-10.2", "timestamp": "2026-07-04T22:00:00+00:00",
     "expected_alt": ["deny"]},
    {"agent": "Finance Agent", "scenario": "Confidential large export HITL", "tool": "db_query", "action": "read", "scope": 100,
     "params": {"table": "financial_records"}, "classification": "confidential", "expected": "require_hitl",
     "policy_rule": "high-scope-confidential-hitl", "ps_id": "PS-10.2"},
    {"agent": "Finance Agent", "scenario": "High-value payment HITL", "tool": "payment_process", "action": "write", "scope": 50000,
     "params": {"amount": 50000, "currency": "USD"}, "setup_tools": ["identity_verify"], "expected": "require_hitl",
     "policy_rule": "payment-amount-hitl", "ps_id": "PS-10.2", "timestamp": "2026-07-04T14:00:00+00:00"},
    {"agent": "Finance Agent", "scenario": "Payment without identity verify", "tool": "payment_process", "action": "write", "scope": 100,
     "params": {"amount": 100}, "expected": "deny", "waf_rule": "sequence", "ps_id": "PS-5.1"},
    {"agent": "Finance Agent", "scenario": "Delete without prior query", "tool": "db_delete", "action": "delete", "scope": 5,
     "params": {"table": "financial_records", "count": 5}, "expected": "deny", "waf_rule": "sequence", "ps_id": "PS-5.1"},
    {"agent": "Finance Agent", "scenario": "WAF unknown tool", "tool": "shell_exec", "action": "read", "scope": 0,
     "params": {"cmd": "ls"}, "expected": "deny", "waf_rule": "tool_scope", "ps_id": "PS-5.1"},
    {"agent": "Finance Agent", "scenario": "WAF SQL injection", "tool": "db_query", "action": "read", "scope": 0,
     "params": {"q": "DROP TABLE users; --"}, "expected": "deny", "waf_rule": "parameter_validation", "ps_id": "PS-5.1"},
    {"agent": "Finance Agent", "scenario": "WAF blocklisted param", "tool": "db_query", "action": "read", "scope": 0,
     "params": {"api_key": "sk-secret-123"}, "expected": "deny", "waf_rule": "parameter_validation", "ps_id": "PS-5.1"},
    {"agent": "Finance Agent", "scenario": "Deep delegation block", "tool": "db_query", "action": "read", "scope": 0,
     "params": {"table": "transactions"}, "delegation_depth": 2, "expected": "block",
     "policy_rule": "deep-delegation-block", "ps_id": "PS-10.2"},
    {"agent": "Finance Agent", "scenario": "Violation suspend session", "tool": "db_query", "action": "read", "scope": 0,
     "params": {"table": "transactions"}, "expected": "block",
     "policy_rule": "violation-suspend", "ps_id": "PS-10.2", "session_key": "suspend-finance", "skip": True},
    {"agent": "Finance Agent", "scenario": "Report generate", "tool": "report_generate", "action": "read", "scope": 0,
     "params": {"report": "monthly"}, "expected": "allow", "ps_id": "PS-10.2",
     "timestamp": "2026-07-04T14:00:00+00:00"},
    # ── Support Agent ──────────────────────────────────────────────────────
    {"agent": "Customer Support Agent", "scenario": "CRM read", "tool": "crm_read", "action": "read", "scope": 1,
     "params": {"customer_id": "c-1001"}, "expected": "allow", "ps_id": "PS-10.2"},
    {"agent": "Customer Support Agent", "scenario": "External email HITL", "tool": "email_send", "action": "write", "scope": 0,
     "params": {"to": "customer@gmail.com", "subject": "Support reply", "body": "Hello"}, "expected": "require_hitl",
     "policy_rule": "external-email-hitl", "ps_id": "PS-10.2"},
    {"agent": "Customer Support Agent", "scenario": "Internal email allow", "tool": "email_send", "action": "write", "scope": 0,
     "params": {"to": "user@company.com", "subject": "Internal note", "body": "FYI"}, "expected": "allow",
     "policy_rule": "internal-email-allow", "ps_id": "PS-10.2"},
    {"agent": "Customer Support Agent", "scenario": "Bulk CRM HITL", "tool": "crm_read", "action": "read", "scope": 800,
     "params": {"segment": "all"}, "expected": "require_hitl", "policy_rule": "bulk-crm-hitl", "ps_id": "PS-10.2"},
    {"agent": "Customer Support Agent", "scenario": "Sensitive email body block", "tool": "email_send", "action": "write", "scope": 0,
     "params": {"to": "user@company.com", "subject": "Alert", "body": "Your password is expired"},
     "expected": "block", "policy_rule": "suspicious-link-block", "ps_id": "PS-10.2"},
    {"agent": "Customer Support Agent", "scenario": "WAF unauthorized tool", "tool": "db_delete", "action": "delete", "scope": 10,
     "params": {"table": "customers"}, "expected": "deny", "waf_rule": "tool_scope", "ps_id": "PS-5.1"},
    # ── HR Agent ───────────────────────────────────────────────────────────
    {"agent": "HR Agent", "scenario": "HR records read", "tool": "hr_records", "action": "read", "scope": 1,
     "params": {"employee_id": "e-42"}, "expected": "allow", "ps_id": "PS-10.2"},
    {"agent": "HR Agent", "scenario": "PHI access HITL", "tool": "hr_records", "action": "read", "scope": 1,
     "params": {"employee_id": "e-99"}, "classification": "PHI", "expected": "require_hitl",
     "policy_rule": "phi-hipaa-strict", "ps_id": "PS-10.2"},
    {"agent": "HR Agent", "scenario": "Bulk PHI block", "tool": "hr_records", "action": "read", "scope": 50,
     "params": {"department": "all"}, "classification": "PHI", "expected": "block",
     "policy_rule": "bulk-phi-block", "ps_id": "PS-10.2"},
    {"agent": "HR Agent", "scenario": "PII warning allow", "tool": "hr_records", "action": "read", "scope": 5,
     "params": {"employee_id": "e-10"}, "classification": "PII", "expected": "warn",
     "policy_rule": "pii-warning", "ps_id": "PS-10.2"},
    {"agent": "HR Agent", "scenario": "HR write HITL", "tool": "hr_records", "action": "write", "scope": 1,
     "params": {"employee_id": "e-42", "field": "title"}, "expected": "require_hitl",
     "policy_rule": "hr-write-hitl", "ps_id": "PS-10.2", "timestamp": "2026-07-04T14:00:00+00:00"},
    {"agent": "HR Agent", "scenario": "Benefits bulk export HITL", "tool": "benefits_lookup", "action": "read", "scope": 500,
     "params": {"plan": "all"}, "expected": "require_hitl", "policy_rule": "benefits-export-hitl", "ps_id": "PS-10.2"},
    {"agent": "HR Agent", "scenario": "WAF unauthorized email", "tool": "email_send", "action": "write", "scope": 0,
     "params": {"to": "all@company.com"}, "expected": "deny", "waf_rule": "tool_scope", "ps_id": "PS-5.1"},
    # ── Developer Agent ────────────────────────────────────────────────────
    {"agent": "Developer Agent", "scenario": "Code search", "tool": "code_search", "action": "read", "scope": 0,
     "params": {"query": "auth middleware"}, "expected": "allow", "ps_id": "PS-10.2"},
    {"agent": "Developer Agent", "scenario": "Internal API call", "tool": "api_call", "action": "read", "scope": 0,
     "params": {"url": "https://api.internal/health"}, "expected": "allow", "ps_id": "PS-10.2"},
    {"agent": "Developer Agent", "scenario": "Prod API write block", "tool": "api_call", "action": "write", "scope": 0,
     "params": {"url": "https://api.internal/deploy", "environment": "production"},
     "expected": "block", "policy_rule": "prod-api-write-block", "ps_id": "PS-10.2"},
    {"agent": "Developer Agent", "scenario": "External API HITL", "tool": "api_call", "action": "read", "scope": 0,
     "params": {"url": "https://external-vendor.com/data"}, "expected": "require_hitl",
     "policy_rule": "external-api-hitl", "ps_id": "PS-10.2"},
    {"agent": "Developer Agent", "scenario": "Confidential code audit", "tool": "code_search", "action": "read", "scope": 0,
     "params": {"query": "encryption keys"}, "classification": "confidential", "expected": "audit_only",
     "policy_rule": "confidential-read-audit", "ps_id": "PS-10.2"},
    {"agent": "Developer Agent", "scenario": "WAF db access denied", "tool": "db_query", "action": "read", "scope": 10,
     "params": {"table": "users"}, "expected": "deny", "waf_rule": "tool_scope", "ps_id": "PS-5.1"},
    {"agent": "Developer Agent", "scenario": "WAF shell denied", "tool": "shell_exec", "action": "read", "scope": 0,
     "params": {"cmd": "npm test"}, "expected": "deny", "waf_rule": "tool_scope", "ps_id": "PS-5.1"},
    # ── Marketing Agent (now governed) ───────────────────────────────────────
    {"agent": "Marketing Insights Agent", "scenario": "CRM read governed", "tool": "crm_read", "action": "read", "scope": 50,
     "params": {"segment": "vip"}, "expected": "allow", "ps_id": "PS-10.2"},
    {"agent": "Marketing Insights Agent", "scenario": "PII segment HITL", "tool": "crm_read", "action": "read", "scope": 500,
     "params": {"segment": "pii-cohort"}, "classification": "PII", "expected": "require_hitl",
     "policy_rule": "pii-segment-hitl", "ps_id": "PS-10.2"},
    {"agent": "Marketing Insights Agent", "scenario": "Bulk analytics HITL", "tool": "analytics_query", "action": "read", "scope": 5000,
     "params": {"campaign": "q1"}, "expected": "require_hitl", "policy_rule": "bulk-analytics-hitl", "ps_id": "PS-10.2"},
    {"agent": "Marketing Insights Agent", "scenario": "Cross-dataset block", "tool": "analytics_query", "action": "read", "scope": 10,
     "params": {"target_dataset": "employee_records", "campaign": "test"},
     "expected": "block", "policy_rule": "cross-dataset-block", "ps_id": "PS-10.2"},
    {"agent": "Marketing Insights Agent", "scenario": "WAF bad tool", "tool": "db_delete", "action": "delete", "scope": 50,
     "params": {"table": "campaigns"}, "expected": "deny", "waf_rule": "tool_scope", "ps_id": "PS-5.1"},
    # ── WAF edge cases ─────────────────────────────────────────────────────
    {"agent": "Finance Agent", "scenario": "WAF template injection", "tool": "db_query", "action": "read", "scope": 0,
     "params": {"q": "{{config.items()}}"}, "expected": "deny", "waf_rule": "parameter_validation", "ps_id": "PS-5.1"},
    {"agent": "Finance Agent", "scenario": "Record update without read", "tool": "record_update", "action": "write", "scope": 1,
     "params": {"record_id": "r-1"}, "expected": "deny", "waf_rule": "sequence", "ps_id": "PS-5.1"},
    {"agent": "Finance Agent", "scenario": "Record update with prior read", "tool": "record_update", "action": "write", "scope": 1,
     "params": {"record_id": "r-1"}, "setup_tools": ["record_read"], "expected": "allow", "ps_id": "PS-5.1",
     "timestamp": "2026-07-04T14:00:00+00:00"},
    {"agent": "Finance Agent", "scenario": "Shadow mode probe", "tool": "shell_exec", "action": "read", "scope": 0,
     "params": {"cmd": "whoami"}, "expected": "allow", "shadow_mode": True, "waf_rule": "tool_scope", "ps_id": "PS-5.1"},
]

CASE_COUNT = int(os.environ.get("CASE_COUNT", "200"))

WAF_RULES_DOC = [
    ("tool_scope", 1, "Tool + operation must be declared in agent registry", "PS-5.1"),
    ("rate_limit", 2, "Sliding-window call cap per agent+tool (risk-tier scaled)", "PS-5.1"),
    ("parameter_validation", 3, "SQL/script injection regex + param blocklist (high-risk agents)", "PS-5.1"),
    ("size_limit", 4, "Max 64KB JSON payload per tool call", "PS-5.1"),
    ("data_scope", 5, "Session scope must match declared datasets", "PS-5.1"),
    ("sequence", 6, "Prerequisite tools must run first in session (payment, delete, update)", "PS-5.1"),
]

RESULT_COLUMNS = [
    "Run ID", "Run Time (UTC)", "Case ID", "Agent", "Agent ID", "Scenario", "PS ID",
    "Expected Disposition", "Final Disposition", "Pass/Fail",
    "Policy Rule", "WAF Rule", "Matched Policy Rules",
    "Tool", "Action", "Data Scope", "Classification",
    "HTTP Status", "WAF Disposition", "WAF Reason", "WAF Evaluations",
    "Policy Action", "Policy Reason", "Overall Reason",
    "Violation ID", "HITL Ticket", "Session ID", "Latency (ms)", "Error",
]


def build_cases(n: int) -> list[dict]:
    templates = [t for t in CASE_TEMPLATES if not t.get("skip")]
    # Round-robin across agents so rate limits are not hammered on one agent.
    by_agent: dict[str, list[dict]] = {}
    for t in templates:
        by_agent.setdefault(t["agent"], []).append(t)
    agent_order = list(by_agent.keys())
    interleaved: list[dict] = []
    idx = {a: 0 for a in agent_order}
    while len(interleaved) < len(templates):
        added = False
        for agent in agent_order:
            tpls = by_agent[agent]
            if idx[agent] < len(tpls):
                interleaved.append(tpls[idx[agent]])
                idx[agent] += 1
                added = True
        if not added:
            break

    cases: list[dict] = []
    finance_query_n = 0
    for i in range(n):
        tpl = {k: v for k, v in interleaved[i % len(interleaved)].items()}
        tpl["case_id"] = i + 1
        iteration = i // len(interleaved) + 1
        if iteration > 1:
            tpl["scenario"] = f"{tpl['scenario']} #{iteration}"
            tpl["scope"] = max(0, tpl.get("scope", 0) + (i % 11) - 5)
        if tpl.get("agent") == "Finance Agent" and tpl.get("tool") == "db_query" and tpl.get("expected") == "allow":
            finance_query_n += 1
            if finance_query_n > 12:
                alts = list(tpl.get("expected_alt") or [])
                if "deny" not in alts:
                    alts.append("deny")
                tpl["expected_alt"] = alts
        cases.append(tpl)
    return cases


def load_policy_inventory() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(POLICIES_DIR.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        meta = doc.get("metadata", {})
        spec = doc.get("spec", {})
        policy_name = meta.get("name", path.stem)
        inherits = spec.get("inherits", "")
        for rule in spec.get("rules", []) or []:
            when = rule.get("when", {})
            when_str = yaml.dump(when, default_flow_style=True).strip() if when else ""
            then = rule.get("then", {})
            rows.append({
                "Policy File": path.name,
                "Policy ID": policy_name,
                "Inherits": inherits,
                "Rule Name": rule.get("name", ""),
                "Priority": rule.get("priority", ""),
                "Condition": when_str,
                "Action": then.get("action", ""),
                "Reason": then.get("reason", ""),
                "Description": meta.get("description", ""),
            })
    return rows


def fetch_agents(client: httpx.Client) -> dict[str, str]:
    resp = client.get(f"{API_URL}/agents")
    resp.raise_for_status()
    return {a["name"]: a["agent_id"] for a in resp.json()["agents"]}


def deploy_policies(client: httpx.Client) -> None:
    for path in sorted(POLICIES_DIR.glob("*.yaml")):
        content = path.read_text(encoding="utf-8")
        resp = client.post(
            f"{API_URL}/policy/deploy",
            json={"yaml_content": content, "created_by": "governance-suite"},
        )
        if resp.status_code not in (200, 201):
            print(f"  Policy deploy warning {path.name}: {resp.status_code} {resp.text[:120]}")


def reseed_demo(client: httpx.Client) -> None:
    resp = client.post(f"{API_URL}/admin/seed-demo", params={"force": "true"})
    if resp.status_code == 200:
        print(f"  Demo seed: {resp.json().get('message', 'ok')}")
    else:
        print(f"  Demo seed warning: {resp.status_code} {resp.text[:120]}")


def _run_setup(client: httpx.Client, agent_id: str, session_id: str, setup_tools: list[str], tpl: dict) -> None:
    for tool in setup_tools:
        payload = {
            "context": {
                "agent_id": agent_id,
                "session_id": session_id,
                "user_id": "setup-user",
                "action_type": "read" if tool in ("db_query", "identity_verify", "record_read") else "write",
                "tool_name": tool,
                "tool_params": tpl.get("params", {}),
                "data_scope_size": tpl.get("scope", 0),
            },
            "shadow_mode": False,
        }
        if tpl.get("timestamp"):
            payload["context"]["timestamp"] = tpl["timestamp"]
        client.post(f"{API_URL}/tool/intercept", json=payload, timeout=30.0)


def run_case(client: httpx.Client, case: dict, agents: dict[str, str], run_id: str, run_time: str) -> dict:
    agent_name = case["agent"]
    agent_id = agents.get(agent_name, "")
    session_key = case.get("session_key", f"case-{case['case_id']:03d}")
    if case.get("reuse_session"):
        session_id = session_key
    else:
        session_id = f"{session_key}-{uuid.uuid4().hex[:8]}"

    if case.get("setup_tools"):
        _run_setup(client, agent_id, session_id, case["setup_tools"], case)

    ctx: dict = {
        "agent_id": agent_id,
        "session_id": session_id,
        "user_id": f"test-user-{case['case_id']}",
        "action_type": case["action"],
        "tool_name": case["tool"],
        "tool_params": case.get("params", {}),
        "data_scope_size": case.get("scope", 0),
    }
    if case.get("classification"):
        ctx["session_data_classification"] = case["classification"]
    if case.get("timestamp"):
        ctx["timestamp"] = case["timestamp"]
    if case.get("prev_violations"):
        ctx["previous_violations_in_session"] = case["prev_violations"]
    if case.get("delegation_depth"):
        ctx["delegation_depth"] = case["delegation_depth"]

    payload = {"context": ctx, "shadow_mode": case.get("shadow_mode", False)}

    start = time.perf_counter()
    base = {
        "Run ID": run_id,
        "Run Time (UTC)": run_time,
        "Case ID": case["case_id"],
        "Agent": agent_name,
        "Agent ID": agent_id,
        "Scenario": case["scenario"],
        "PS ID": case.get("ps_id", ""),
        "Expected Disposition": case.get("expected", ""),
        "Policy Rule": case.get("policy_rule", ""),
        "WAF Rule": case.get("waf_rule", ""),
        "Tool": case["tool"],
        "Action": case["action"],
        "Data Scope": case.get("scope", 0),
        "Classification": case.get("classification", "internal"),
    }
    try:
        resp = client.post(f"{API_URL}/tool/intercept", json=payload, timeout=30.0)
        latency = round((time.perf_counter() - start) * 1000, 2)
        if resp.status_code == 200:
            data = resp.json()
            waf = data.get("waf_result") or {}
            policy = data.get("policy_decision") or {}
            final = data.get("disposition", "")
            expected = case.get("expected", "")
            alts = case.get("expected_alt") or []
            matched_rules = ", ".join(
                r.get("rule_name", "") for r in (policy.get("matched_rules") or [])
            )
            evals = waf.get("evaluations") or []
            eval_str = "; ".join(
                f"{e.get('rule_type')}={'pass' if e.get('passed') else 'FAIL'}" for e in evals
            )
            return {
                **base,
                "Final Disposition": final,
                "Pass/Fail": "PASS" if _match_expected(expected, final, alts) else "FAIL",
                "Matched Policy Rules": matched_rules,
                "HTTP Status": resp.status_code,
                "WAF Disposition": waf.get("disposition", ""),
                "WAF Reason": waf.get("reason", ""),
                "WAF Evaluations": eval_str,
                "Policy Action": policy.get("action", ""),
                "Policy Reason": policy.get("reason", ""),
                "Overall Reason": data.get("reason", ""),
                "Violation ID": data.get("violation_id") or "",
                "HITL Ticket": data.get("ticket_id") or "",
                "Session ID": session_id,
                "Latency (ms)": latency,
                "Error": "",
            }
        return {
            **base,
            "Final Disposition": "error",
            "Pass/Fail": "FAIL",
            "Matched Policy Rules": "",
            "HTTP Status": resp.status_code,
            "WAF Disposition": "",
            "WAF Reason": "",
            "WAF Evaluations": "",
            "Policy Action": "",
            "Policy Reason": "",
            "Overall Reason": resp.text[:200],
            "Violation ID": "",
            "HITL Ticket": "",
            "Session ID": session_id,
            "Latency (ms)": latency,
            "Error": resp.text[:300],
        }
    except Exception as exc:
        latency = round((time.perf_counter() - start) * 1000, 2)
        return {
            **base,
            "Final Disposition": "error",
            "Pass/Fail": "FAIL",
            "Matched Policy Rules": "",
            "HTTP Status": 0,
            "WAF Disposition": "",
            "WAF Reason": "",
            "WAF Evaluations": "",
            "Policy Action": "",
            "Policy Reason": "",
            "Overall Reason": str(exc),
            "Violation ID": "",
            "HITL Ticket": "",
            "Session ID": session_id,
            "Latency (ms)": latency,
            "Error": str(exc),
        }


def run_violation_suspend_case(client: httpx.Client, agents: dict[str, str], run_id: str, run_time: str) -> dict:
    """Accumulate 3 real session violations, then verify suspend_session fires."""
    agent_id = agents.get("Finance Agent", "")
    session_id = f"suspend-{uuid.uuid4().hex[:8]}"
    for _ in range(3):
        client.post(
            f"{API_URL}/tool/intercept",
            json={
                "context": {
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "user_id": "suspend-test",
                    "action_type": "read",
                    "tool_name": "shell_exec",
                    "tool_params": {"cmd": "probe"},
                    "data_scope_size": 0,
                },
            },
            timeout=30.0,
        )
    case = {
        "case_id": 9999,
        "agent": "Finance Agent",
        "scenario": "Violation suspend session (3 prior violations)",
        "tool": "db_query",
        "action": "read",
        "scope": 0,
        "params": {"table": "transactions"},
        "expected": "block",
        "policy_rule": "violation-suspend",
        "ps_id": "PS-10.2",
        "session_key": session_id,
        "reuse_session": True,
    }
    row = run_case(client, case, agents, run_id, run_time)
    return row


def run_rate_limit_burst(client: httpx.Client, agents: dict[str, str], run_id: str, run_time: str) -> dict:
    """Hammer finance db_query to trigger WAF rate_limit (high-risk limit ≈18/min)."""
    agent_id = agents.get("Finance Agent", "")
    session_id = f"rate-burst-{uuid.uuid4().hex[:8]}"
    last_row: dict = {}
    for i in range(40):
        case = {
            "case_id": 9000 + i,
            "agent": "Finance Agent",
            "scenario": f"Rate limit burst #{i + 1}",
            "tool": "db_query",
            "action": "read",
            "scope": 1,
            "params": {"table": "transactions", "n": i},
            "expected": "deny" if i >= 18 else "allow",
            "waf_rule": "rate_limit" if i >= 18 else "",
            "ps_id": "PS-5.1",
            "session_key": session_id,
        }
        last_row = run_case(client, case, agents, run_id, run_time)
    last_row["Scenario"] = "Rate limit burst (40 db_query calls)"
    last_row["Expected Disposition"] = "deny"
    last_row["Pass/Fail"] = "PASS" if last_row.get("Final Disposition") == "deny" else "FAIL"
    return last_row


def _match_expected(expected: str, actual: str, alternates: list[str] | None = None) -> bool:
    if not expected:
        return True
    if _match_one(expected, actual):
        return True
    for alt in alternates or []:
        if _match_one(alt, actual):
            return True
    return False


def _match_one(expected: str, actual: str) -> bool:
    exp = expected.lower()
    act = actual.lower()
    if exp == act:
        return True
    if exp in ("block", "suspend_session") and act == "deny":
        return True
    if exp == "block" and act in ("block", "suspend_session"):
        return True
    return False


def build_coverage(rows: list[dict], policies: list[dict]) -> list[dict]:
    policy_rules = {r["Rule Name"] for r in policies if r.get("Rule Name")}
    waf_rules = {r[0] for r in WAF_RULES_DOC}
    coverage: list[dict] = []

    for rule in sorted(policy_rules):
        hits = [r for r in rows if r.get("Policy Rule") == rule or rule in str(r.get("Matched Policy Rules", ""))]
        passed = sum(1 for r in hits if r.get("Pass/Fail") == "PASS")
        coverage.append({
            "Layer": "Policy",
            "Rule": rule,
            "Scenarios Tested": len(hits),
            "Passed": passed,
            "Failed": len(hits) - passed,
            "Coverage": "YES" if hits else "NO",
        })

    for rule_type, _, desc, ps in WAF_RULES_DOC:
        hits = [r for r in rows if r.get("WAF Rule") == rule_type or rule_type in str(r.get("WAF Evaluations", ""))]
        passed = sum(1 for r in hits if r.get("Pass/Fail") == "PASS")
        coverage.append({
            "Layer": "WAF",
            "Rule": rule_type,
            "Scenarios Tested": len(hits),
            "Passed": passed,
            "Failed": len(hits) - passed,
            "Coverage": "YES" if hits else "NO",
            "Description": desc,
            "PS ID": ps,
        })
    return coverage


def _style_header(ws, row_num: int = 1) -> None:
    from openpyxl.styles import Alignment, Font, PatternFill

    for cell in ws[row_num]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="6D28D9")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _append_or_create_sheet(wb, title: str, headers: list[str], rows: list[dict], append: bool) -> None:
    if title in wb.sheetnames and append:
        ws = wb[title]
        start_row = ws.max_row + 1
    else:
        if title in wb.sheetnames:
            del wb[title]
        ws = wb.create_sheet(title)
        ws.append(headers)
        _style_header(ws)
        start_row = 2

    for row in rows:
        ws.append([row.get(h, "") for h in headers])

    if title == "Agent Cases":
        disp_colors = {
            "allow": "DCFCE7", "deny": "FEE2E2", "block": "FEE2E2",
            "require_hitl": "FEF3C7", "suspend_session": "FECACA", "error": "F3F4F6",
        }
        from openpyxl.styles import PatternFill
        for r in range(start_row, ws.max_row + 1):
            disp = str(ws.cell(r, headers.index("Final Disposition") + 1).value or "").lower()
            pf = str(ws.cell(r, headers.index("Pass/Fail") + 1).value or "")
            color = "BBF7D0" if pf == "PASS" else ("FECACA" if pf == "FAIL" else disp_colors.get(disp, "FFFFFF"))
            for c in range(1, len(headers) + 1):
                ws.cell(r, c).fill = PatternFill("solid", fgColor=color)


def _clean_cell(value: object) -> object:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value))


def _finalize_workbook(wb, path: Path) -> None:
    from openpyxl.utils import get_column_letter

    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None:
                    cell.value = _clean_cell(cell.value)
        for col in range(1, ws.max_column + 1):
            letter = get_column_letter(col)
            max_len = 10
            for r in range(1, min(ws.max_row, 200) + 1):
                v = ws.cell(r, col).value
                if v is not None:
                    max_len = max(max_len, min(len(str(v)), 60))
            ws.column_dimensions[letter].width = min(max_len + 2, 48)

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.xlsx")
    wb.save(tmp)
    tmp.replace(path)


def _export_csv(wb, path: Path) -> None:
    import csv

    csv_dir = path.parent / "csv"
    csv_dir.mkdir(exist_ok=True)
    for name in wb.sheetnames:
        ws = wb[name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        safe = re.sub(r"[^\w\-]+", "_", name.lower()).strip("_")
        with open(csv_dir / f"{safe}.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow(["" if c is None else _clean_cell(c) for c in row])


def _finalize_workbook_sheet(ws) -> None:
    from openpyxl.utils import get_column_letter

    ws.freeze_panes = "A2"
    for col in range(1, ws.max_column + 1):
        letter = get_column_letter(col)
        width = 10
        for r in range(1, min(ws.max_row, 200) + 1):
            v = ws.cell(r, col).value
            if v is not None:
                width = max(width, min(len(str(v)), 55))
        ws.column_dimensions[letter].width = min(width + 2, 50)


def _export_csv_from_path(xlsx_path: Path) -> None:
    import csv
    from openpyxl import load_workbook

    csv_dir = xlsx_path.parent / "csv"
    csv_dir.mkdir(exist_ok=True)
    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    for name in wb.sheetnames:
        ws = wb[name]
        rows = list(ws.iter_rows(values_only=True))
        safe = re.sub(r"[^\w\-]+", "_", name.lower()).strip("_")
        with open(csv_dir / f"{safe}.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow(["" if c is None else _clean_cell(c) for c in row])
    wb.close()


def write_consolidated(
    case_rows: list[dict],
    policies: list[dict],
    coverage: list[dict],
    summary_rows: list[dict],
    path: Path,
) -> None:
    from collections import Counter
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    pass_n = sum(1 for c in case_rows if c.get("Pass/Fail") == "PASS")
    fail_n = len(case_rows) - pass_n
    by_disp = Counter(c.get("Final Disposition", "unknown") for c in case_rows)
    by_agent = Counter(c.get("Agent", "unknown") for c in case_rows)

    wb = Workbook()
    wb.remove(wb.active)

    ov = wb.create_sheet("Overview", 0)
    ov["A1"] = "SentinelAI Governance — Consolidated Report"
    ov["A1"].font = Font(bold=True, size=14, color="6D28D9")
    ov.merge_cells("A1:F1")
    ov["A2"] = f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | {len(case_rows)} test cases"
    for row, label, val in [
        (4, "Total test cases", len(case_rows)),
        (5, "Passed", pass_n),
        (6, "Failed", fail_n),
        (7, "Pass rate", f"{round(100 * pass_n / max(len(case_rows), 1), 1)}%"),
        (8, "Policy rules", len(policies)),
        (9, "WAF rule types", len(WAF_RULES_DOC)),
    ]:
        ov.cell(row, 1, label)
        ov.cell(row, 2, val)
    r = 11
    ov.cell(r, 1, "Dispositions").font = Font(bold=True)
    r += 1
    for k, v in sorted(by_disp.items()):
        ov.cell(r, 1, k)
        ov.cell(r, 2, v)
        r += 1
    r += 1
    ov.cell(r, 1, "Agents tested").font = Font(bold=True)
    r += 1
    for k, v in sorted(by_agent.items()):
        ov.cell(r, 1, k)
        ov.cell(r, 2, v)
        r += 1
    ov.column_dimensions["A"].width = 28
    ov.column_dimensions["B"].width = 20

    policy_headers = ["Policy File", "Policy ID", "Inherits", "Rule Name", "Priority", "Condition", "Action", "Reason", "Description"]
    waf_headers = ["Order", "Rule Type", "Description", "PS ID"]
    cov_headers = ["Layer", "Rule", "Scenarios Tested", "Passed", "Failed", "Coverage", "Description", "PS ID"]
    sum_headers = list(summary_rows[0].keys()) if summary_rows else []

    sheets = [
        ("All Test Cases", RESULT_COLUMNS, case_rows),
        ("Policy Rules", policy_headers, policies),
        ("WAF Rules", waf_headers, [{"Order": o, "Rule Type": t, "Description": d, "PS ID": ps} for t, o, d, ps in WAF_RULES_DOC]),
        ("Coverage Matrix", cov_headers, coverage),
        ("Run History", sum_headers, summary_rows),
    ]
    pass_fill = PatternFill("solid", fgColor="BBF7D0")
    fail_fill = PatternFill("solid", fgColor="FECACA")
    for title, headers, rows in sheets:
        ws = wb.create_sheet(title)
        ws.append(headers)
        _style_header(ws)
        for row in rows:
            ws.append([row.get(h, "") for h in headers])
        if title == "All Test Cases" and "Pass/Fail" in headers:
            pf_col = headers.index("Pass/Fail") + 1
            for ri in range(2, ws.max_row + 1):
                pf = str(ws.cell(ri, pf_col).value or "")
                fill = pass_fill if pf == "PASS" else (fail_fill if pf == "FAIL" else None)
                if fill:
                    for ci in range(1, len(headers) + 1):
                        ws.cell(ri, ci).fill = fill
        _finalize_workbook_sheet(ws)

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.xlsx")
    wb.save(tmp)
    tmp.replace(path)
    _export_csv_from_path(path)


def write_xlsx(
    case_rows: list[dict],
    policies: list[dict],
    coverage: list[dict],
    summary_row: dict,
    path: Path,
    append: bool,
) -> None:
    try:
        from openpyxl import Workbook, load_workbook
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl", "-q"])
        from openpyxl import Workbook, load_workbook

    path.parent.mkdir(parents=True, exist_ok=True)
    if append and path.exists():
        wb = load_workbook(path)
    else:
        wb = Workbook()
        wb.remove(wb.active)

    policy_headers = ["Policy File", "Policy ID", "Inherits", "Rule Name", "Priority", "Condition", "Action", "Reason", "Description"]
    waf_headers = ["Order", "Rule Type", "Description", "PS ID"]
    coverage_headers = ["Layer", "Rule", "Scenarios Tested", "Passed", "Failed", "Coverage", "Description", "PS ID"]
    summary_headers = ["Run ID", "Run Time (UTC)", "API", "Total Cases", "Passed", "Failed", "Errors",
                       "allow", "deny", "block", "require_hitl", "Avg Latency (ms)"]

    _append_or_create_sheet(wb, "Agent Cases", RESULT_COLUMNS, case_rows, append)
    _append_or_create_sheet(wb, "Policy Rules", policy_headers, policies, append=False)
    _append_or_create_sheet(wb, "WAF Rules", waf_headers,
                            [{"Order": o, "Rule Type": t, "Description": d, "PS ID": ps} for t, o, d, ps in WAF_RULES_DOC],
                            append=False)
    _append_or_create_sheet(wb, "Coverage Matrix", coverage_headers, coverage, append=False)
    _append_or_create_sheet(wb, "Summary", summary_headers, [summary_row], append=append)

    _finalize_workbook(wb, path)
    _export_csv(wb, path)


def main() -> None:
    run_id = datetime.now(timezone.utc).strftime("RUN-%Y%m%d-%H%M%S")
    run_time = datetime.now(timezone.utc).isoformat()
    print(f"API: {API_URL}")
    print(f"Run ID: {run_id} | Cases: {CASE_COUNT} | Append: {APPEND}")

    policies = load_policy_inventory()
    print(f"Policy rules loaded: {len(policies)}")

    cases = build_cases(CASE_COUNT)
    results: list[dict] = []

    with httpx.Client(timeout=30.0) as client:
        print("Deploying policies…")
        deploy_policies(client)
        reseed_demo(client)
        agents = fetch_agents(client)
        print(f"Agents: {', '.join(agents.keys())}")

        for case in cases:
            row = run_case(client, case, agents, run_id, run_time)
            results.append(row)
            mark = "✓" if row["Pass/Fail"] == "PASS" else "✗"
            print(f"  {mark} Case {row['Case ID']:3d} | {row['Scenario'][:32]:32s} | exp={row['Expected Disposition']:14s} got={row['Final Disposition']}")

        if INCLUDE_SPECIAL:
            print("Running rate-limit burst…")
            results.append(run_rate_limit_burst(client, agents, run_id, run_time))
            print("Running violation-suspend case…")
            results.append(run_violation_suspend_case(client, agents, run_id, run_time))

    passed = sum(1 for r in results if r.get("Pass/Fail") == "PASS")
    failed = len(results) - passed
    by_disp: dict[str, int] = {}
    for r in results:
        d = r.get("Final Disposition", "unknown")
        by_disp[d] = by_disp.get(d, 0) + 1
    avg_lat = sum(r.get("Latency (ms)", 0) for r in results) / max(len(results), 1)

    coverage = build_coverage(results, policies)
    summary_row = {
        "Run ID": run_id,
        "Run Time (UTC)": run_time,
        "API": API_URL,
        "Total Cases": len(results),
        "Passed": passed,
        "Failed": failed,
        "Errors": sum(1 for r in results if r.get("HTTP Status") != 200),
        "allow": by_disp.get("allow", 0),
        "deny": by_disp.get("deny", 0),
        "block": by_disp.get("block", 0),
        "require_hitl": by_disp.get("require_hitl", 0),
        "Avg Latency (ms)": round(avg_lat, 2),
    }

    write_xlsx(results, policies, coverage, summary_row, OUTPUT, append=APPEND)
    write_consolidated(results, policies, coverage, [summary_row], CONSOLIDATED)
    import shutil
    shutil.copy2(CONSOLIDATED, OUTPUT)

    print(f"\nExcel: {OUTPUT}")
    print(f"Consolidated: {CONSOLIDATED}")
    print(f"Results: {len(results)} cases | PASS {passed} | FAIL {failed}")
    print(f"Policy rules documented: {len(policies)} | WAF rules: {len(WAF_RULES_DOC)}")


if __name__ == "__main__":
    main()
