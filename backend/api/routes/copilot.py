"""Policy Copilot routes."""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.deps import copilot_service, policy_service

router = APIRouter()


class CopilotRequest(BaseModel):
    description: str
    policy_name: str = "copilot-policy"


class CopilotDeployRequest(BaseModel):
    yaml_content: str
    approved_by: str = "admin"


@router.post("/copilot/generate-policy")
def generate_policy(request: CopilotRequest):
    result = copilot_service().generate(request.description, request.policy_name)
    return result


@router.post("/copilot/deploy-policy")
def deploy_copilot_policy(request: CopilotDeployRequest):
    """Deploy after human approval."""
    policy = policy_service().deploy(request.yaml_content, request.approved_by)
    return {"policy": policy, "message": "Policy deployed after human approval"}
