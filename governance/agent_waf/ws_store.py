"""WebSocket connection registry for AWS API Gateway WAF live feed."""

from __future__ import annotations

from datetime import datetime, timezone

from shared.storage.factory import get_repository


def save_connection(connection_id: str, agent_id: str | None = None) -> None:
    repo = get_repository()
    repo.save_ws_connection(connection_id, agent_id or "all")


def delete_connection(connection_id: str) -> None:
    repo = get_repository()
    repo.delete_ws_connection(connection_id)


def list_connections(agent_id: str | None = None) -> list[str]:
    repo = get_repository()
    return repo.list_ws_connections(agent_id=agent_id)


def connection_payload(connection_id: str, agent_id: str | None = None) -> dict:
    return {
        "connection_id": connection_id,
        "agent_id": agent_id or "all",
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }
