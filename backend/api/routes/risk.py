"""Risk scoring routes."""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.deps import risk_engine

router = APIRouter()


class RiskScoreRequest(BaseModel):
    agent_id: str
    anomaly_score: int = 0


@router.post("/risk/score")
def score_risk(request: RiskScoreRequest):
    return risk_engine().score_agent(request.agent_id, request.anomaly_score)


@router.get("/risk/heatmap")
def risk_heatmap():
    return {"heatmap": risk_engine().heatmap()}
