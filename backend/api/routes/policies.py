"""Policy management routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.deps import policy_service

router = APIRouter()


class PolicyDeployRequest(BaseModel):
    yaml_content: str
    created_by: str = "admin"


class PolicyEvaluateRequest(BaseModel):
    agent_id: str
    context: dict


class PolicySimulateRequest(BaseModel):
    yaml_content: str
    session_id: str | None = None


@router.post("/policy/deploy")
def deploy_policy(request: PolicyDeployRequest):
    try:
        policy = policy_service().deploy(request.yaml_content, request.created_by)
        return {"policy": policy, "message": "Policy deployed"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/policy")
def list_policies():
    return {"policies": policy_service().list_policies()}


@router.get("/policy/{policy_id}")
def get_policy(policy_id: str):
    policy = policy_service().get(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"policy": policy}


@router.post("/policy/evaluate")
def evaluate_policy(request: PolicyEvaluateRequest):
    result = policy_service().evaluate(request.context, request.agent_id)
    return {"decision": result}


@router.post("/policy/simulate")
def simulate_policy(request: PolicySimulateRequest):
    """Governance Sandbox — replay logs against proposed policy."""
    result = policy_service().simulate(request.yaml_content, request.session_id)
    return {"simulation": result}
