"""Standalone FastAPI app for the Agent Chat Lambda."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import chat, health
from shared.config.settings import get_settings

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_chat_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="SentinelAI Agent Chat",
        description="Cerebras-powered governed agent chat for governance testing",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    prefix = settings.api_prefix
    app.include_router(health.router, tags=["Health"])
    app.include_router(chat.router, prefix=prefix, tags=["Agent Chat"])
    return app


app = create_chat_app()
