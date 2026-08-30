"""Agent WAF routes (PS-5.1)."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.deps import repo
from governance.agent_waf.acceptance import WAFAcceptanceSuite
from governance.agent_waf.engine import AgentWAF
from shared.models.context import GovernanceContext

router = APIRouter()


class WAFTestRequest(BaseModel):
    context: GovernanceContext
    shadow_mode: bool = False


@router.get("/waf/stats")
def waf_stats(agent_id: str | None = None, limit: int = 20):
    """WAF traffic and block statistics for dashboard."""
    waf = AgentWAF(repo())
    stats = waf.get_stats(agent_id=agent_id, limit=limit)
    return stats.model_dump()


@router.get("/waf/config")
def waf_config(agent_id: str | None = None):
    """Effective ruleset the WAF will enforce for an agent (transparent rule engine)."""
    waf = AgentWAF(repo())
    return waf.describe_config(agent_id=agent_id).model_dump()


@router.post("/waf/acceptance")
def waf_acceptance():
    """Run the PS-5.1 acceptance battery and return an evidenced pass/fail per criterion.

    Each criterion runs in an isolated in-memory repository, so this has no effect
    on live governance data.
    """
    return WAFAcceptanceSuite().run()


@router.post("/waf/test")
def waf_test(request: WAFTestRequest):
    """Fire a single crafted tool call through the live WAF engine.

    The decision is recorded to the live store so it appears on the real-time
    dashboard, and the full per-rule evaluation trace is returned for inspection.
    """
    waf = AgentWAF(repo())
    result = waf.intercept(request.context, shadow_mode=request.shadow_mode)
    return result.model_dump()


@router.get("/waf/records")
def waf_records(agent_id: str | None = None, limit: int = 50):
    records = repo().list_waf_records(agent_id=agent_id, limit=limit)
    return {
        "records": [
            {
                "record_id": r.record_id,
                "agent_id": r.agent_id,
                "session_id": r.session_id,
                "tool_name": r.tool_name,
                "action_type": r.action_type,
                "disposition": r.disposition.value,
                "matched_rules": r.matched_rules,
                "evaluations": [e.model_dump() for e in r.evaluations],
                "reason": r.reason,
                "params_sanitized": r.params_sanitized,
                "shadow_mode": r.shadow_mode,
                "latency_ms": r.latency_ms,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in records
        ]
    }
