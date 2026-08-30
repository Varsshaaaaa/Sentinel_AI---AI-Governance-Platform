"""WAF live feed broadcast — AWS API Gateway WebSocket (production path)."""

from __future__ import annotations

import json
import logging
from typing import Any

from botocore.exceptions import ClientError

from governance.agent_waf.ws_store import delete_connection, list_connections
from shared.config.settings import get_settings

logger = logging.getLogger(__name__)


def _management_client():
    import boto3

    settings = get_settings()
    if not settings.waf_websocket_api_endpoint:
        return None
    return boto3.client(
        "apigatewaymanagementapi",
        endpoint_url=settings.waf_websocket_api_endpoint.rstrip("/"),
        region_name=settings.aws_region,
    )


def post_to_connection(connection_id: str, payload: dict[str, Any]) -> bool:
    client = _management_client()
    if client is None:
        return False
    try:
        client.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(payload, default=str).encode("utf-8"),
        )
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("GoneException", "410"):
            delete_connection(connection_id)
        else:
            logger.warning("WAF WebSocket post failed for %s: %s", connection_id, exc)
        return False


def broadcast_waf_record(record: dict[str, Any]) -> int:
    """Push a WAF record to all subscribed API Gateway WebSocket connections."""
    settings = get_settings()
    if not settings.waf_websocket_api_endpoint:
        return 0

    agent_id = record.get("agent_id")
    targets: set[str] = set()
    targets.update(list_connections(agent_id=None))
    if agent_id:
        targets.update(list_connections(agent_id=agent_id))

    delivered = 0
    for connection_id in targets:
        if post_to_connection(connection_id, record):
            delivered += 1
    return delivered


def notify_waf_record(record: dict[str, Any]) -> None:
    """Called from sync WAF intercept path after each decision is logged."""
    broadcast_waf_record(record)
