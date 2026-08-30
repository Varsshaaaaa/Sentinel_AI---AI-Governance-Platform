"""Decision audit and replay routes (PS-7.1)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.deps import decision_auditor
from shared.models.audit import StepType

router = APIRouter()


class AuditLogRequest(BaseModel):
    session_id: str
    agent_id: str
    user_id: str = "system"
    step_type: StepType
    content: dict


@router.post("/audit/log")
def log_audit_step(request: AuditLogRequest):
    step = decision_auditor().log_step(
        session_id=request.session_id,
        agent_id=request.agent_id,
        user_id=request.user_id,
        step_type=request.step_type,
        content=request.content,
    )
    return {"step": step}


@router.get("/decision/replay/{session_id}")
async def replay_decision(session_id: str):
    """Governance Replay — full decision timeline."""
    path = decision_auditor().get_decision_path(session_id)
    if not path:
        raise HTTPException(status_code=404, detail="Session not found")

    timeline = []
    for step in path.steps:
        timeline.append(
            {
                "sequence": step.step_sequence,
                "timestamp": step.timestamp.isoformat(),
                "step_type": step.step_type.value,
                "content": step.content_redacted,
                "policy_evaluation": step.policy_evaluation,
                "risk_score": step.risk_score,
            }
        )

    summary = decision_auditor().generate_summary(path)
    llm_summary = await decision_auditor().generate_llm_summary(path)

    return {
        "session_id": session_id,
        "agent_id": path.agent_id,
        "user_id": path.user_id,
        "started_at": path.started_at.isoformat() if path.started_at else None,
        "completed_at": path.completed_at.isoformat() if path.completed_at else None,
        "timeline": timeline,
        "summary": summary,
        "llm_summary": llm_summary,
        "step_count": len(timeline),
    }


@router.post("/decision/summary/{session_id}")
async def decision_summary(session_id: str):
    path = decision_auditor().get_decision_path(session_id)
    if not path:
        raise HTTPException(status_code=404, detail="Session not found")
    summary = await decision_auditor().generate_llm_summary(path)
    return {"session_id": session_id, "summary": summary}


class ChallengeRequest(BaseModel):
    question: str | None = None


@router.post("/decision/challenge/{session_id}")
async def decision_challenge(session_id: str, request: ChallengeRequest | None = None):
    """PS-7.1 bonus: draft a regulatory challenge response from the decision path."""
    path = decision_auditor().get_decision_path(session_id)
    if not path:
        raise HTTPException(status_code=404, detail="Session not found")
    question = request.question if request else None
    return await decision_auditor().generate_challenge_response_llm(path, question)
