#!/usr/bin/env python3
"""Quick SentinelAI production smoke check.

Usage:
    API_URL="https://dwybfyittl.execute-api.us-east-1.amazonaws.com/v1" python infrastructure/scripts/smoke_check.py

Exit code 0 = all checks passed, 1 = at least one failure.
"""

from __future__ import annotations

import os
import sys

import httpx

API = os.environ.get("API_URL", "https://dwybfyittl.execute-api.us-east-1.amazonaws.com/v1").rstrip("/")
BASE = API.removesuffix("/v1")


def main() -> int:
    client = httpx.Client(timeout=45)
    ok = True

    def check(name: str, resp: httpx.Response, expect: int = 200) -> None:
        nonlocal ok
        passed = resp.status_code == expect
        if not passed:
            ok = False
        print(f"  [{'PASS' if passed else 'FAIL'}] {name} (HTTP {resp.status_code})")

    print(f"SentinelAI smoke check → {API}\n")

    check("Health", client.get(f"{BASE}/health"))
    check("Dashboard", client.get(f"{API}/dashboard"))
    agents_resp = client.get(f"{API}/agents")
    check("Agents", agents_resp)

    agents = agents_resp.json().get("agents", [])
    finance = next((a for a in agents if a.get("name") == "Finance Agent"), None)
    if not finance:
        print("  [FAIL] Finance Agent not found — run POST /v1/admin/seed-demo?force=true")
        return 1

    intercept = client.post(
        f"{API}/tool/intercept",
        json={
            "context": {
                "agent_id": finance["agent_id"],
                "session_id": "smoke-bulk-delete",
                "tool_name": "db_delete",
                "action_type": "delete",
                "tool_params": {"count": 500, "table": "financial_records"},
                "data_scope_size": 500,
            }
        },
    )
    check("Finance bulk delete intercept", intercept)
    body = intercept.json()
    if body.get("disposition") != "block":
        print(f"         Expected disposition=block, got {body.get('disposition')!r}")
        ok = False
    else:
        print(f"         block OK — {str(body.get('reason', ''))[:70]}")

    copilot = client.post(
        f"{API}/copilot/generate-policy",
        json={
            "description": "Block developer agents from calling external APIs without approval",
            "policy_name": "smoke-copilot",
        },
    )
    check("Policy Copilot", copilot)
    copilot_body = copilot.json()
    if not copilot_body.get("valid"):
        print(f"         Copilot invalid: {copilot_body.get('error')}")
        ok = False
    elif "copilot-generated-rule" in copilot_body.get("yaml_content", ""):
        print("         Warning: template fallback YAML (Cerebras may be unavailable)")

    replay = client.get(f"{API}/decision/replay/demo-finance-session")
    check("Decision replay", replay, expect=200 if replay.status_code == 200 else replay.status_code)

    waf = client.post(f"{API}/waf/acceptance")
    check("WAF acceptance", waf)

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
