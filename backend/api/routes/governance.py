"""Governance workflow routes (PS-4.2)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.deps import observability_pipeline, repo, sla_monitor
from governance.observability_pipeline.adapters import map_cloudwatch_alarm, map_otel_metrics

router = APIRouter()


class SignalIngestRequest(BaseModel):
    agent_id: str
    signal_type: str
    metric_value: float | None = None
    source: str = "observability"
    reviewer: str | None = None


class CloudWatchAlarmRequest(BaseModel):
    agent_id: str | None = None
    signal_type: str | None = None
    metric_value: float | None = None
    alarm_state: str = "ALARM"
    Trigger: dict | None = None
    NewStateValue: str | None = None
    Message: str | None = None


class OtelMetricsRequest(BaseModel):
    agent_id: str | None = None
    signal_type: str | None = None
    metric_value: float | None = None
    resource: dict = Field(default_factory=dict)
    scopeMetrics: list = Field(default_factory=list)


class HITLApprovalRequest(BaseModel):
    action: str  # approve | reject
    reviewer: str = "admin"
    reason: str = ""


@router.post("/observability/ingest")
def ingest_signal(request: SignalIngestRequest):
    try:
        result = observability_pipeline().ingest(request.model_dump())
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/observability/ingest/cloudwatch")
def ingest_cloudwatch_alarm(request: CloudWatchAlarmRequest):
    try:
        signal = map_cloudwatch_alarm(request.model_dump(exclude_none=True))
        if signal.get("alarm_state") != "ALARM":
            return {
                "skipped": True,
                "reason": "Alarm not in ALARM state",
                "alarm_state": signal.get("alarm_state"),
            }
        return observability_pipeline().ingest(signal)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/observability/ingest/otel")
def ingest_otel_metrics(request: OtelMetricsRequest):
    try:
        signal = map_otel_metrics(request.model_dump())
        return observability_pipeline().ingest(signal)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/governance/status/{agent_id}")
def governance_status(agent_id: str):
    return observability_pipeline().get_status(agent_id)


@router.get("/governance/action-log")
def governance_action_log(agent_id: str | None = None, limit: int = 50):
    return {"actions": observability_pipeline().list_action_log(agent_id, limit)}


@router.post("/governance/sla/check")
def governance_sla_check():
    """Run the governance SLA sweep (PS-4.2 bonus)."""
    return sla_monitor().check_slas()


@router.post("/admin/seed-demo")
def seed_demo_data(force: bool = False):
    """Re-deploy demo policies and upsert demo agents (idempotent by agent name)."""
    from backend.scripts.seed_demo import seed

    return seed(force=force)


@router.get("/timeline")
def governance_timeline(agent_id: str | None = None, limit: int = 100):
    events = repo().list_events(agent_id=agent_id, limit=limit)
    return {
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type.value,
                "agent_id": e.agent_id,
                "actor": e.actor,
                "timestamp": e.timestamp.isoformat(),
                "payload": e.payload,
            }
            for e in events
        ]
    }


@router.post("/hitl/{ticket_id}/approve")
def hitl_action(ticket_id: str, request: HITLApprovalRequest):
    ticket = repo().get_hitl_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="HITL ticket not found")

    status = "approved" if request.action == "approve" else "rejected"
    repo().update_hitl_ticket(
        ticket_id,
        {"status": status, "reviewer": request.reviewer, "reason": request.reason},
    )
    return {"ticket_id": ticket_id, "status": status, "message": f"HITL ticket {status}"}


@router.get("/hitl")
def list_hitl_tickets(status: str | None = None):
    return {"tickets": repo().list_hitl_tickets(status)}


@router.get("/violations")
def list_violations(agent_id: str | None = None):
    violations = repo().list_violations(agent_id=agent_id)
    return {
        "violations": [
            {
                "violation_id": v.violation_id,
                "agent_id": v.agent_id,
                "session_id": v.session_id,
                "rule_name": v.rule_name,
                "severity": v.severity.value,
                "source": v.source,
                "reason": v.reason,
                "timestamp": v.timestamp.isoformat(),
            }
            for v in sorted(violations, key=lambda x: x.timestamp, reverse=True)
        ]
    }
