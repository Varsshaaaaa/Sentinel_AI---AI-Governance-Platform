"""Governed agent chat — Cerebras LLM + tool intercept testing."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services.agent_chat_service import (
    list_chat_suggestions,
    llm_status,
    run_chat_turn,
)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    history: list[dict[str, str]] = Field(default_factory=list)
    active_agent: str | None = None
    agent_name: str | None = None
    api_url: str | None = None


@router.get("/chat/suggestions")
def chat_suggestions():
    return list_chat_suggestions()


@router.get("/chat/llm-status")
def chat_llm_status():
    return llm_status()


@router.post("/chat")
def chat_turn(request: ChatRequest):
    message = request.message.strip()
    if not message:
        return {"ok": False, "error": "message is required"}
    result = run_chat_turn(
        user_message=message,
        history=request.history,
        session_id=request.session_id,
        agent_name=request.agent_name,
        active_agent=request.active_agent,
        api_url=request.api_url,
    )
    return result
