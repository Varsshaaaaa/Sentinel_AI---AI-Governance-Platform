"""Governance Graph Builder tests (PS-1.3)."""

import pytest

from governance.graph_engine.service import GraphEngine
from shared.models.agent import Agent, ModelRef, RiskTier, ToolScope
from shared.models.graph import GraphQueryRequest
from shared.storage.memory import MemoryRepository


@pytest.fixture
def repo():
    return MemoryRepository()


@pytest.fixture
def engine(repo):
    return GraphEngine(repo)


def _agent(agent_id="agent-1", tools=("db_query",), policies=("base",)):
    return Agent(
        agent_id=agent_id,
        name=agent_id,
        owner="alice",
        team="Data",
        purpose="test",
        framework="custom",
        risk_tier=RiskTier.MEDIUM,
        models=[ModelRef(name="gpt-4o", provider="openai")],
        tools=[ToolScope(name=t) for t in tools],
        datasets=["customers"],
        policy_ids=list(policies),
    )


def test_runtime_log_ingestion_creates_edges(engine, repo):
    engine.ingest_agent(_agent())
    result = engine.ingest_runtime_logs(
        [
            {"agent_id": "agent-1", "tool": "billing_api", "model": "claude-3", "datasource": "invoices"},
            {"agent_id": "agent-1", "tool": "billing_api"},
        ]
    )
    assert result["edges_created"] >= 3
    assert "billing_api" in result["tools_observed"]
    tools = engine.query(GraphQueryRequest(query_type="tools", agent_id="agent-1"))
    tool_labels = {n.label for n in tools.nodes if n.node_type.value == "Tool"}
    assert "billing_api" in tool_labels


def test_parse_runtime_log_text_jsonl_and_kv(engine):
    text = (
        '{"agent_id": "agent-1", "tool": "db_query"}\n'
        "agent_id=agent-1 tool=email_send model=gpt-4o\n"
        "\n"
    )
    entries = engine.parse_runtime_log_text(text)
    assert len(entries) == 2
    assert entries[0]["tool"] == "db_query"
    assert entries[1]["model"] == "gpt-4o"


def test_policy_document_yaml_ingestion(engine, repo):
    engine.ingest_agent(_agent(policies=()))  # orphan
    doc = """
policies:
  - id: pci-dss
    description: Card data handling
    agents: [agent-1]
"""
    result = engine.ingest_policy_document(doc)
    assert result["policies_created"] == 1
    assert result["links_created"] == 1
    orphans = engine.query(GraphQueryRequest(query_type="orphans"))
    assert "agent-1" not in {n.node_id for n in orphans.nodes}


def test_policy_document_freetext_ingestion(engine):
    engine.ingest_agent(_agent(agent_id="agent-7", policies=()))
    result = engine.ingest_policy_document("agent-7 -> hipaa")
    assert result["policies_created"] >= 1
    assert result["links_created"] >= 1


def test_config_change_diff(engine):
    engine.ingest_agent(_agent(tools=("db_query",)))
    before = engine.snapshot()
    engine.ingest_agent(_agent(tools=("db_query", "email_send")))
    diff = engine.diff(before)
    assert "tool-email_send" in diff["added_nodes"]
    assert any("tool-email_send" in edge for edge in diff["added_edges"])


def test_apply_agent_change_returns_diff(engine):
    engine.ingest_agent(_agent(tools=("db_query",)))
    result = engine.apply_agent_change(_agent(tools=("db_query", "s3_read")))
    assert "tool-s3_read" in result["diff"]["added_nodes"]


def test_orphan_query_still_correct_after_runtime_ingest(engine):
    engine.ingest_agent(_agent(agent_id="agent-orphan", policies=()))
    engine.ingest_runtime_logs([{"agent_id": "agent-orphan", "tool": "x"}])
    orphans = engine.query(GraphQueryRequest(query_type="orphans"))
    assert "agent-orphan" in {n.node_id for n in orphans.nodes}
