"""AWS API Gateway WebSocket handler for WAF live dashboard (PS-5.1)."""

from __future__ import annotations

import json
from typing import Any

from governance.agent_waf.broadcast import post_to_connection
from governance.agent_waf.engine import AgentWAF
from governance.agent_waf.ws_store import delete_connection, save_connection
from shared.storage.factory import get_repository


def _response(status_code: int = 200, body: dict | None = None) -> dict[str, Any]:
    return {"statusCode": status_code, "body": json.dumps(body or {"ok": True})}


def _query_param(event: dict, name: str) -> str | None:
    params = event.get("queryStringParameters") or {}
    return params.get(name)


def _send_recent_records(connection_id: str, agent_id: str | None) -> None:
    repo = get_repository()
    waf = AgentWAF(repo)
    records = repo.list_waf_records(agent_id=agent_id if agent_id and agent_id != "all" else None, limit=20)
    for record in reversed(records):
        post_to_connection(
            connection_id,
            {
                "record_id": record.record_id,
                "agent_id": record.agent_id,
                "session_id": record.session_id,
                "tool_name": record.tool_name,
                "disposition": record.disposition.value,
                "matched_rules": record.matched_rules,
                "reason": record.reason,
                "shadow_mode": record.shadow_mode,
                "latency_ms": record.latency_ms,
                "timestamp": record.timestamp.isoformat(),
            },
        )
    _ = waf  # ensure engine module loaded in Lambda package


def handler(event: dict, context: Any) -> dict[str, Any]:
    route = event.get("requestContext", {}).get("routeKey", "")
    connection_id = event.get("requestContext", {}).get("connectionId", "")

    if route == "$connect":
        if not connection_id:
            return _response(400, {"error": "missing connection id"})
        agent_id = _query_param(event, "agent_id") or "all"
        save_connection(connection_id, agent_id)
        _send_recent_records(connection_id, agent_id)
        return _response(200, {"connected": True, "agent_id": agent_id})

    if route == "$disconnect":
        if connection_id:
            delete_connection(connection_id)
        return _response(200, {"disconnected": True})

    if route == "$default":
        body = event.get("body") or "{}"
        try:
            message = json.loads(body)
        except json.JSONDecodeError:
            message = {"action": "ping"}
        if message.get("action") == "ping" and connection_id:
            post_to_connection(connection_id, {"type": "heartbeat"})
        return _response(200)

    return _response(404, {"error": f"unknown route: {route}"})
