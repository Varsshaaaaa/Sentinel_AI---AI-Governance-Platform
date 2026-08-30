"""Graph models."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    USER = "User"
    AGENT = "Agent"
    MODEL = "Model"
    TOOL = "Tool"
    DATASOURCE = "DataSource"
    POLICY = "Policy"
    SECRET = "Secret"
    CLOUD_RESOURCE = "CloudResource"
    DATASET = "Dataset"


class EdgeType(str, Enum):
    USES = "USES"
    OWNS = "OWNS"
    DEPLOYS = "DEPLOYS"
    CALLS = "CALLS"
    CONNECTED_TO = "CONNECTED_TO"
    HAS_POLICY = "HAS_POLICY"
    USES_MODEL = "USES_MODEL"


class GraphNode(BaseModel):
    node_id: str
    node_type: NodeType
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source_id: str
    target_id: str
    edge_type: EdgeType
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphQueryRequest(BaseModel):
    query_type: str
    agent_id: str | None = None
    model_id: str | None = None
    datasource_id: str | None = None
    tool_id: str | None = None
    policy_id: str | None = None


class GraphQueryResponse(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
