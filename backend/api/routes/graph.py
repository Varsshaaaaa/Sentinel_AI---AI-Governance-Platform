"""Governance graph routes (PS-1.3)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.deps import graph_engine, repo
from shared.models.graph import GraphQueryRequest

router = APIRouter()


class RuntimeLogIngestRequest(BaseModel):
    logs: list[dict] = Field(default_factory=list)
    raw_text: str | None = None


class PolicyDocumentRequest(BaseModel):
    document: str


@router.post("/graph/query")
def query_graph(request: GraphQueryRequest):
    result = graph_engine().query(request)
    return result


@router.get("/graph/visualize")
def visualize_graph():
    result = graph_engine().query(GraphQueryRequest(query_type="full"))
    return result


@router.post("/graph/ingest/runtime-logs")
def ingest_runtime_logs(request: RuntimeLogIngestRequest):
    """PS-1.3 ingestion source 2: build the graph from runtime logs."""
    engine = graph_engine()
    logs = request.logs
    if request.raw_text:
        logs = logs + engine.parse_runtime_log_text(request.raw_text)
    return engine.ingest_runtime_logs(logs)


@router.post("/graph/ingest/policy-document")
def ingest_policy_document(request: PolicyDocumentRequest):
    """PS-1.3 ingestion source 3: build the graph from a policy document."""
    return graph_engine().ingest_policy_document(request.document)


@router.post("/graph/agents/{agent_id}/reingest")
def reingest_agent(agent_id: str):
    """Re-ingest an agent config and return the resulting graph diff."""
    agent = repo().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return graph_engine().apply_agent_change(agent)
