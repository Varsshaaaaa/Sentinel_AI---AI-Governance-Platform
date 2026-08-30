"""Event publishing to EventBridge with local fallback."""

import json
import logging
from typing import Any
from uuid import uuid4

from shared.config.settings import get_settings
from shared.models.events import EventType, GovernanceEvent
from shared.storage.base import Repository

logger = logging.getLogger(__name__)


class EventPublisher:
    """Publishes governance events to EventBridge; persists locally in dev."""

    def __init__(self, repository: Repository) -> None:
        self._repo = repository
        self._settings = get_settings()
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3

            kwargs: dict[str, Any] = {"region_name": self._settings.aws_region}
            self._client = boto3.client("events", **kwargs)
        return self._client

    def publish(self, event: GovernanceEvent) -> GovernanceEvent:
        self._repo.save_event(event)
        if self._settings.environment == "local" and self._settings.storage_backend == "memory":
            logger.info("event_published", extra={"event_type": event.event_type.value, "agent_id": event.agent_id})
            return event
        try:
            self._get_client().put_events(
                Entries=[
                    {
                        "Source": "sentinelai.governance",
                        "DetailType": event.event_type.value,
                        "Detail": json.dumps(event.model_dump(), default=str),
                        "EventBusName": self._settings.eventbridge_bus_name,
                    }
                ]
            )
        except Exception as exc:
            logger.warning("eventbridge_publish_failed", extra={"error": str(exc)})
        return event

    def emit(
        self,
        event_type: EventType,
        agent_id: str | None = None,
        actor: str = "system",
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> GovernanceEvent:
        event = GovernanceEvent(
            event_type=event_type,
            agent_id=agent_id,
            actor=actor,
            payload=payload or {},
            correlation_id=correlation_id or str(uuid4()),
        )
        return self.publish(event)
