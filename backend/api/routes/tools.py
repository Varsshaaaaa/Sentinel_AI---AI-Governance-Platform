"""Tool intercept routes — core governance pipeline."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.deps import guardrail_harness, intercept_service
from shared.models.tool import ToolInterceptRequest

router = APIRouter()


class GuardrailSimulationRequest(BaseModel):
    scenarios: list[dict] = Field(default_factory=list)


@router.post("/tool/intercept")
def intercept_tool(request: ToolInterceptRequest):
    """WAF → Policy Engine → Guardrails → Audit pipeline."""
    response = intercept_service().intercept(request)
    return response


@router.post("/guardrails/simulate")
def simulate_guardrails(request: GuardrailSimulationRequest):
    """PS-3.1 simulation harness: run scenarios and report each outcome."""
    return guardrail_harness().run(request.scenarios)
