"""Application settings loaded from environment."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["local", "dev", "staging", "prod"] = "local"
    log_level: str = "INFO"
    api_prefix: str = "/v1"
    cors_origins: str = "http://localhost:5173,http://localhost:5174,http://localhost:3000"

    aws_region: str = "us-east-1"
    aws_account_id: str = ""
    dynamodb_table_prefix: str = "sentinelai"
    storage_backend: Literal["memory", "dynamodb"] = "memory"
    dynamodb_endpoint: str | None = None

    cognito_user_pool_id: str = ""
    cognito_client_id: str = ""

    eventbridge_bus_name: str = "sentinelai-governance"

    # AWS API Gateway WebSocket — WAF live dashboard (PS-5.1)
    waf_websocket_api_endpoint: str = ""
    waf_websocket_stage: str = "prod"

    litellm_model: str = "cerebras/gemma-4-31b"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    cerebras_api_key: str = ""
    cerebras_model: str = "cerebras/gemma-4-31b"
    cerebras_api_base: str = "https://api.cerebras.ai/v1"
    governance_api_url: str = "http://localhost:8080/v1"
    copilot_skip_templates: bool = False
    copilot_max_tokens: int = 1500

    slack_webhook_url: str = ""
    notification_email_from: str = "noreply@sentinelai.local"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60

    agent_credential_secret: str = "change-me-agent-signing-key"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def table_name(self, suffix: str) -> str:
        return f"{self.dynamodb_table_prefix}-{suffix}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """Clear cached settings (e.g. after Lambda env change in warm containers)."""
    get_settings.cache_clear()
    return get_settings()
