"""HITL ticket matching helpers."""

import json
from typing import Any


def normalize_tool_params(params: dict[str, Any] | None) -> str:
    return json.dumps(params or {}, sort_keys=True, default=str)


def hitl_action_matches(
    ticket: dict[str, Any],
    session_id: str,
    tool_name: str,
    tool_params: dict[str, Any] | None = None,
) -> bool:
    if ticket.get("status") != "approved":
        return False
    if ticket.get("session_id") != session_id:
        return False
    if ticket.get("tool_name") != tool_name:
        return False
    ticket_params = ticket.get("tool_params")
    if normalize_tool_params(ticket_params) != normalize_tool_params(tool_params):
        return False
    return True
