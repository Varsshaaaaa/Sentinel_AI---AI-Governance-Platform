"""Health check routes."""

from datetime import datetime, timezone

from fastapi import APIRouter

from shared.config.settings import get_settings

router = APIRouter()


@router.get("/health")
def health():
    settings = get_settings()
    return {
        "status": "healthy",
        "service": "sentinelai",
        "version": "1.0.0",
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
