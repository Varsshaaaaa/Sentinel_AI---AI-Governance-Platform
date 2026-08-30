"""SentinelAI FastAPI application."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import agents, audit, chat, compliance, copilot, dashboard, graph, governance, health, policies, risk, tools, waf
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
    settings = get_settings()
    if settings.environment == "local":
        try:
            from backend.scripts.seed_demo import seed
            seed(force=False)
        except Exception:
            pass
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="SentinelAI",
        description=(
            "Integrated AI Governance Platform implementing PS-1.3, PS-3.1, PS-4.2, "
            "PS-5.1, PS-7.1, and PS-10.2"
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
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
    app.include_router(agents.router, prefix=prefix, tags=["Agents"])
    app.include_router(tools.router, prefix=prefix, tags=["Tool Intercept"])
    app.include_router(waf.router, prefix=prefix, tags=["Agent WAF"])
    app.include_router(policies.router, prefix=prefix, tags=["Policies"])
    app.include_router(audit.router, prefix=prefix, tags=["Decision Audit"])
    app.include_router(graph.router, prefix=prefix, tags=["Governance Graph"])
    app.include_router(governance.router, prefix=prefix, tags=["Governance"])
    app.include_router(risk.router, prefix=prefix, tags=["Risk"])
    app.include_router(compliance.router, prefix=prefix, tags=["Compliance"])
    app.include_router(dashboard.router, prefix=prefix, tags=["Dashboard"])
    app.include_router(copilot.router, prefix=prefix, tags=["Policy Copilot"])
    app.include_router(chat.router, prefix=prefix, tags=["Agent Chat"])

    return app


app = create_app()
