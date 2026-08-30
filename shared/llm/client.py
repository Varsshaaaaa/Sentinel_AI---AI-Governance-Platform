"""LiteLLM client — OpenAI, Anthropic, and Cerebras via unified completion API."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from shared.config.settings import Settings, get_settings


@dataclass
class _LLMMessage:
    content: str | None = None
    reasoning_content: str | None = None


@dataclass
class _LLMChoice:
    message: _LLMMessage


@dataclass
class _LLMResponse:
    choices: list[_LLMChoice]


def llm_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(
        s.openai_api_key
        or s.anthropic_api_key
        or s.cerebras_api_key
        or os.environ.get("CEREBRAS_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
    )


def configure_litellm_env(settings: Settings | None = None) -> None:
    s = settings or get_settings()
    if s.openai_api_key or os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = s.openai_api_key or os.environ.get("OPENAI_API_KEY", "")
    if s.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = s.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    cerebras = s.cerebras_api_key or os.environ.get("CEREBRAS_API_KEY", "")
    if cerebras:
        os.environ["CEREBRAS_API_KEY"] = cerebras


def resolve_model(settings: Settings | None = None) -> str:
    """Pick the LiteLLM model id from settings and available API keys."""
    s = settings or get_settings()
    model = (s.litellm_model or "").strip()

    if model.startswith("cerebras/"):
        return model

    if s.cerebras_api_key and (not model or model in {"gpt-4o-mini", "gpt-4o"}):
        return s.cerebras_model

    if os.environ.get("CEREBRAS_API_KEY") and (not model or model in {"gpt-4o-mini", "gpt-4o"}):
        return s.cerebras_model

    if model and "/" not in model:
        if s.openai_api_key:
            return f"openai/{model}"
        if s.anthropic_api_key:
            return f"anthropic/{model}"

    return model or s.cerebras_model


def litellm_completion_kwargs(settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    configure_litellm_env(s)
    model = resolve_model(s)
    kwargs: dict[str, Any] = {"model": model}

    if model.startswith("cerebras/"):
        kwargs["api_base"] = s.cerebras_api_base
        kwargs["extra_headers"] = {"X-Cerebras-3rd-Party-Integration": "litellm"}

    return kwargs


def extract_message_content(response: Any) -> str:
    """Return assistant text from a LiteLLM response (handles reasoning models)."""
    message = response.choices[0].message
    content = getattr(message, "content", None) or ""
    if content:
        return content
    return getattr(message, "reasoning_content", None) or ""


def _cerebras_api_key(settings: Settings) -> str:
    return settings.cerebras_api_key or os.environ.get("CEREBRAS_API_KEY", "")


def _cerebras_http_completion(
    *,
    messages: list[dict[str, str]],
    max_tokens: int,
    settings: Settings,
    **extra: Any,
) -> _LLMResponse:
    """Direct Cerebras REST call — avoids LiteLLM/tiktoken (Lambda GLIBC safe)."""
    api_key = _cerebras_api_key(settings)
    if not api_key:
        raise RuntimeError("CEREBRAS_API_KEY not configured")

    model = resolve_model(settings).removeprefix("cerebras/")
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if "temperature" in extra:
        payload["temperature"] = extra["temperature"]

    req = urllib.request.Request(
        f"{settings.cerebras_api_base.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "SentinelAI-PolicyCopilot/1.0",
            "X-Cerebras-3rd-Party-Integration": "litellm",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Cerebras API error {exc.code}: {body}") from exc

    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    return _LLMResponse(
        choices=[
            _LLMChoice(
                message=_LLMMessage(
                    content=message.get("content"),
                    reasoning_content=message.get("reasoning_content"),
                )
            )
        ]
    )


def _use_cerebras_http(settings: Settings) -> bool:
    if not _cerebras_api_key(settings):
        return False
    if not resolve_model(settings).startswith("cerebras/"):
        return False
    # Lambda: avoid LiteLLM/tiktoken (GLIBC mismatch). Local dev: use LiteLLM.
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


def completion(*, messages: list[dict[str, str]], max_tokens: int = 800, **extra: Any) -> Any:
    settings = get_settings()
    if not llm_configured(settings):
        raise RuntimeError("No LLM API key configured")

    if _use_cerebras_http(settings):
        return _cerebras_http_completion(
            messages=messages,
            max_tokens=max_tokens,
            settings=settings,
            **extra,
        )

    import litellm

    kwargs = litellm_completion_kwargs(settings)
    kwargs.update(extra)
    return litellm.completion(messages=messages, max_tokens=max_tokens, **kwargs)


async def acompletion(*, messages: list[dict[str, str]], max_tokens: int = 800, **extra: Any) -> Any:
    settings = get_settings()
    if not llm_configured(settings):
        raise RuntimeError("No LLM API key configured")

    if _use_cerebras_http(settings):
        return await asyncio.to_thread(
            _cerebras_http_completion,
            messages=messages,
            max_tokens=max_tokens,
            settings=settings,
            **extra,
        )

    import litellm

    kwargs = litellm_completion_kwargs(settings)
    kwargs.update(extra)
    return await litellm.acompletion(messages=messages, max_tokens=max_tokens, **kwargs)
