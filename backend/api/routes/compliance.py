"""Compliance routes."""

from fastapi import APIRouter

from backend.deps import compliance_engine

router = APIRouter()


@router.post("/compliance/check")
def check_compliance_all():
    return {"results": compliance_engine().check_all()}


@router.get("/compliance/{agent_id}")
def check_compliance(agent_id: str):
    return compliance_engine().check(agent_id)


@router.get("/compliance/{agent_id}/timeline")
def compliance_timeline(agent_id: str):
    return {"timeline": compliance_engine().timeline(agent_id)}
