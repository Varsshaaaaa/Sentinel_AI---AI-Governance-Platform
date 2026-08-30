"""Agent registry routes."""

from fastapi import APIRouter, HTTPException

from backend.deps import registry_service
from shared.models.agent import AgentRegistration

router = APIRouter()


@router.post("/agents/register")
def register_agent(registration: AgentRegistration):
    agent = registry_service().register(registration)
    return {"agent": agent, "message": "Agent registered successfully"}


@router.get("/agents")
def list_agents():
    agents = registry_service().list_agents()
    return {"agents": agents, "count": len(agents)}


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str):
    agent = registry_service().get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"agent": agent}


@router.post("/agents/{agent_id}/suspend")
def suspend_agent(agent_id: str, reason: str = ""):
    try:
        agent = registry_service().suspend(agent_id, reason)
        return {"agent": agent, "message": "Agent suspended"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/agents/{agent_id}/resume")
def resume_agent(agent_id: str):
    try:
        agent = registry_service().resume(agent_id)
        return {"agent": agent, "message": "Agent resumed"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
