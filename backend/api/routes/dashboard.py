"""Dashboard routes."""

from fastapi import APIRouter

from backend.deps import dashboard_service

router = APIRouter()


@router.get("/dashboard")
def get_dashboard():
    return dashboard_service().get_dashboard()
