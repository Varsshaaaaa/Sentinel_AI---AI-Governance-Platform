"""SentinelAI Python SDK — governance adapter for any agent framework."""

from typing import Any

import httpx

from shared.models.context import DataClassification, GovernanceContext
from shared.models.tool import ToolInterceptRequest, ToolInterceptResponse


class SentinelAIClient:
    """Client for governing agent tool calls via SentinelAI runtime."""

    def __init__(self, base_url: str = "http://localhost:8080/v1", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def intercept(
        self,
        agent_id: str,
        session_id: str,
        tool_name: str,
        tool_params: dict[str, Any] | None = None,
        action_type: str = "read",
        user_id: str = "system",
        user_role: str = "user",
        data_scope_size: int = 0,
        session_data_classification: str = "internal",
        framework: str = "custom",
        shadow_mode: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> ToolInterceptResponse:
        context = GovernanceContext(
            agent_id=agent_id,
            session_id=session_id,
            tool_name=tool_name,
            tool_params=tool_params or {},
            action_type=action_type,
            user_id=user_id,
            user_role=user_role,
            data_scope_size=data_scope_size,
            session_data_classification=DataClassification(session_data_classification),
            framework=framework,
            metadata=metadata or {},
        )
        request = ToolInterceptRequest(context=context, shadow_mode=shadow_mode)
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/tool/intercept", json=request.model_dump(mode="json"))
            resp.raise_for_status()
            return ToolInterceptResponse(**resp.json())

    def register_agent(self, registration: dict) -> dict:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/agents/register", json=registration)
            resp.raise_for_status()
            return resp.json()

    def replay_session(self, session_id: str) -> dict:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(f"{self.base_url}/decision/replay/{session_id}")
            resp.raise_for_status()
            return resp.json()

    def governed_tool(
        self,
        agent_id: str,
        session_id: str,
        tool_name: str,
        action_type: str = "read",
        **kwargs: Any,
    ):
        """Decorator/factory for governed tool execution."""

        def decorator(func):
            def wrapper(*args, **func_kwargs):
                params = func_kwargs or {}
                result = self.intercept(
                    agent_id=agent_id,
                    session_id=session_id,
                    tool_name=tool_name,
                    tool_params=params,
                    action_type=action_type,
                )
                if result.disposition in ("block", "deny"):
                    raise PermissionError(f"Governance blocked: {result.reason}")
                if result.disposition == "require_hitl":
                    raise PermissionError(f"HITL required: ticket {result.ticket_id}")
                return func(*args, **func_kwargs)

            return wrapper

        return decorator
