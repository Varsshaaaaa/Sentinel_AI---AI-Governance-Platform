"""Governance Graph Builder (PS-1.3)."""

import re
from collections import deque
from typing import Any

import yaml

from shared.models.agent import Agent
from shared.models.graph import (
    EdgeType,
    GraphEdge,
    GraphNode,
    GraphQueryRequest,
    GraphQueryResponse,
    NodeType,
)
from shared.models.policy import Policy
from shared.storage.base import Repository


class GraphEngine:
    """Builds and queries the governance graph."""

    def __init__(self, repository: Repository) -> None:
        self._repo = repository

    def ingest_agent(self, agent: Agent) -> None:
        agent_node = GraphNode(
            node_id=agent.agent_id,
            node_type=NodeType.AGENT,
            label=agent.name,
            properties={
                "framework": agent.framework,
                "risk_tier": agent.risk_tier.value,
                "status": agent.status.value,
                "owner": agent.owner,
            },
        )
        self._repo.upsert_graph_node(agent_node)

        owner_node = GraphNode(
            node_id=f"user-{agent.owner}",
            node_type=NodeType.USER,
            label=agent.owner,
            properties={"team": agent.team},
        )
        self._repo.upsert_graph_node(owner_node)
        self._repo.upsert_graph_edge(
            GraphEdge(source_id=f"user-{agent.owner}", target_id=agent.agent_id, edge_type=EdgeType.OWNS)
        )

        for model in agent.models:
            model_id = f"model-{model.name}"
            self._repo.upsert_graph_node(
                GraphNode(
                    node_id=model_id,
                    node_type=NodeType.MODEL,
                    label=model.name,
                    properties={"provider": model.provider, "version": model.version},
                )
            )
            self._repo.upsert_graph_edge(
                GraphEdge(source_id=agent.agent_id, target_id=model_id, edge_type=EdgeType.USES_MODEL)
            )

        for tool in agent.tools:
            tool_id = f"tool-{tool.name}"
            self._repo.upsert_graph_node(
                GraphNode(
                    node_id=tool_id,
                    node_type=NodeType.TOOL,
                    label=tool.name,
                    properties={"operations": tool.allowed_operations},
                )
            )
            self._repo.upsert_graph_edge(
                GraphEdge(source_id=agent.agent_id, target_id=tool_id, edge_type=EdgeType.USES)
            )

        for dataset in agent.datasets:
            ds_id = f"datasource-{dataset}"
            self._repo.upsert_graph_node(
                GraphNode(node_id=ds_id, node_type=NodeType.DATASOURCE, label=dataset, properties={})
            )
            self._repo.upsert_graph_edge(
                GraphEdge(source_id=agent.agent_id, target_id=ds_id, edge_type=EdgeType.CONNECTED_TO)
            )

        for policy_id in agent.policy_ids:
            self._link_policy(agent.agent_id, policy_id)

    def ingest_policy(self, policy: Policy) -> None:
        self._repo.upsert_graph_node(
            GraphNode(
                node_id=f"policy-{policy.policy_id}",
                node_type=NodeType.POLICY,
                label=policy.name,
                properties={"inherits": policy.inherits, "rule_count": len(policy.rules)},
            )
        )

    def link_agent_policy(self, agent_id: str, policy_id: str) -> None:
        self._link_policy(agent_id, policy_id)

    def record_tool_call(self, agent_id: str, tool_name: str) -> None:
        tool_id = f"tool-{tool_name}"
        if not any(n.node_id == tool_id for n in self._repo.list_graph_nodes()):
            self._repo.upsert_graph_node(
                GraphNode(node_id=tool_id, node_type=NodeType.TOOL, label=tool_name, properties={})
            )
        self._repo.upsert_graph_edge(
            GraphEdge(source_id=agent_id, target_id=tool_id, edge_type=EdgeType.CALLS)
        )

    def _link_policy(self, agent_id: str, policy_id: str) -> None:
        self._repo.upsert_graph_edge(
            GraphEdge(
                source_id=agent_id,
                target_id=f"policy-{policy_id}",
                edge_type=EdgeType.HAS_POLICY,
            )
        )

    # --- Ingestion source 2: runtime logs from a sample agent run (PS-1.3) ---

    def ingest_runtime_logs(self, logs: list[dict[str, Any]]) -> dict[str, Any]:
        """Build graph edges from raw runtime log entries.

        Each entry is a structured event captured during an agent run, e.g.::

            {"agent_id": "agent-1", "tool": "db_query", "model": "gpt-4o",
             "datasource": "customers"}

        This is the "runtime logs" ingestion source the PS requires, distinct
        from config-time ingestion — it records what the agent *actually* did.
        """
        edges_created = 0
        tools_seen: set[str] = set()
        for entry in logs:
            agent_id = entry.get("agent_id") or entry.get("agent")
            if not agent_id:
                continue

            tool = entry.get("tool") or entry.get("tool_name")
            if tool:
                self.record_tool_call(agent_id, tool)
                tools_seen.add(tool)
                edges_created += 1

            model = entry.get("model")
            if model:
                model_id = f"model-{model}"
                self._repo.upsert_graph_node(
                    GraphNode(node_id=model_id, node_type=NodeType.MODEL, label=model, properties={})
                )
                self._repo.upsert_graph_edge(
                    GraphEdge(source_id=agent_id, target_id=model_id, edge_type=EdgeType.USES_MODEL)
                )
                edges_created += 1

            datasource = entry.get("datasource") or entry.get("data_source")
            if datasource:
                ds_id = f"datasource-{datasource}"
                self._repo.upsert_graph_node(
                    GraphNode(node_id=ds_id, node_type=NodeType.DATASOURCE, label=datasource, properties={})
                )
                self._repo.upsert_graph_edge(
                    GraphEdge(source_id=agent_id, target_id=ds_id, edge_type=EdgeType.CONNECTED_TO)
                )
                edges_created += 1

        return {
            "log_entries": len(logs),
            "edges_created": edges_created,
            "tools_observed": sorted(tools_seen),
        }

    def parse_runtime_log_text(self, text: str) -> list[dict[str, Any]]:
        """Parse a raw runtime log blob into structured entries.

        Supports JSON-lines and a simple ``key=value`` line format so a real
        agent log file can be dropped in directly.
        """
        import json

        entries: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("{"):
                try:
                    entries.append(json.loads(line))
                    continue
                except json.JSONDecodeError:
                    pass
            kv = dict(re.findall(r"(\w+)=([^\s]+)", line))
            if kv:
                entries.append(kv)
        return entries

    # --- Ingestion source 3: a manually authored policy document (PS-1.3) ---

    def ingest_policy_document(self, document: str) -> dict[str, Any]:
        """Parse a hand-written policy document and wire it into the graph.

        Accepts either a YAML mapping::

            policies:
              - id: pci-dss
                agents: [agent-1, agent-2]

        or free text containing lines like ``agent-1 -> pci-dss`` /
        ``policy pci-dss applies to agent-1``.
        """
        policies_created = 0
        links_created = 0

        parsed = None
        try:
            parsed = yaml.safe_load(document)
        except yaml.YAMLError:
            parsed = None

        pairs: list[tuple[str, str]] = []
        if isinstance(parsed, dict) and "policies" in parsed:
            for entry in parsed.get("policies", []) or []:
                pid = str(entry.get("id") or entry.get("name") or "").strip()
                if not pid:
                    continue
                self._repo.upsert_graph_node(
                    GraphNode(
                        node_id=f"policy-{pid}",
                        node_type=NodeType.POLICY,
                        label=pid,
                        properties={"source": "document", "description": entry.get("description", "")},
                    )
                )
                policies_created += 1
                for agent_id in entry.get("agents", []) or []:
                    pairs.append((str(agent_id), pid))
        else:
            # Free-text extraction.
            for match in re.finditer(
                r"(agent[\w-]+)\s*(?:->|=>|:|applies to|has policy)?\s*(?:policy\s+)?([\w-]+)",
                document,
                re.IGNORECASE,
            ):
                agent_id, pid = match.group(1), match.group(2)
                if agent_id.lower() != pid.lower():
                    self._repo.upsert_graph_node(
                        GraphNode(
                            node_id=f"policy-{pid}",
                            node_type=NodeType.POLICY,
                            label=pid,
                            properties={"source": "document"},
                        )
                    )
                    policies_created += 1
                    pairs.append((agent_id, pid))

        for agent_id, pid in pairs:
            self._link_policy(agent_id, pid)
            links_created += 1

        return {"policies_created": policies_created, "links_created": links_created}

    # --- Config-change diff (PS-1.3: graph updates on config change) ---

    def snapshot(self) -> dict[str, set]:
        """Capture the current node/edge keys for later diffing."""
        nodes = {n.node_id for n in self._repo.list_graph_nodes()}
        edges = {
            (e.source_id, e.target_id, e.edge_type.value)
            for e in self._repo.list_graph_edges()
        }
        return {"nodes": nodes, "edges": edges}

    def diff(self, before: dict[str, set]) -> dict[str, Any]:
        """Diff the current graph against a prior :meth:`snapshot`."""
        after = self.snapshot()
        return {
            "added_nodes": sorted(after["nodes"] - before["nodes"]),
            "removed_nodes": sorted(before["nodes"] - after["nodes"]),
            "added_edges": [list(e) for e in sorted(after["edges"] - before["edges"])],
            "removed_edges": [list(e) for e in sorted(before["edges"] - after["edges"])],
        }

    def apply_agent_change(self, agent: Agent) -> dict[str, Any]:
        """Re-ingest a changed agent config and return what changed in the graph."""
        before = self.snapshot()
        self.ingest_agent(agent)
        return {"agent_id": agent.agent_id, "diff": self.diff(before)}

    def query(self, request: GraphQueryRequest) -> GraphQueryResponse:
        qt = request.query_type

        if qt == "tools":
            return self._tools_for_agent(request.agent_id)
        if qt == "agents_by_model":
            return self._agents_by_model(request.model_id)
        if qt == "agents_by_datasource":
            return self._agents_by_datasource(request.datasource_id)
        if qt == "orphans":
            return self._orphan_agents()
        if qt == "blast_radius":
            return self._blast_radius(request.tool_id)
        if qt == "full":
            return GraphQueryResponse(
                nodes=self._repo.list_graph_nodes(),
                edges=self._repo.list_graph_edges(),
            )

        return GraphQueryResponse(nodes=[], edges=[], metadata={"error": f"Unknown query type: {qt}"})

    def _tools_for_agent(self, agent_id: str | None) -> GraphQueryResponse:
        if not agent_id:
            return GraphQueryResponse(nodes=[], edges=[])
        edges = [
            e
            for e in self._repo.list_graph_edges(source_id=agent_id)
            if e.edge_type in (EdgeType.USES, EdgeType.CALLS)
        ]
        tool_ids = {e.target_id for e in edges}
        nodes = [n for n in self._repo.list_graph_nodes() if n.node_id in tool_ids]
        agent_nodes = [n for n in self._repo.list_graph_nodes() if n.node_id == agent_id]
        return GraphQueryResponse(nodes=agent_nodes + nodes, edges=edges)

    def _agents_by_model(self, model_id: str | None) -> GraphQueryResponse:
        if not model_id:
            return GraphQueryResponse(nodes=[], edges=[])
        mid = model_id if model_id.startswith("model-") else f"model-{model_id}"
        edges = self._repo.list_graph_edges(target_id=mid)
        agent_ids = {e.source_id for e in edges if e.edge_type == EdgeType.USES_MODEL}
        nodes = [n for n in self._repo.list_graph_nodes() if n.node_id in agent_ids or n.node_id == mid]
        return GraphQueryResponse(nodes=nodes, edges=edges)

    def _agents_by_datasource(self, datasource_id: str | None) -> GraphQueryResponse:
        if not datasource_id:
            return GraphQueryResponse(nodes=[], edges=[])
        ds_id = datasource_id if datasource_id.startswith("datasource-") else f"datasource-{datasource_id}"
        edges = self._repo.list_graph_edges(target_id=ds_id)
        agent_ids = {e.source_id for e in edges}
        nodes = [n for n in self._repo.list_graph_nodes() if n.node_id in agent_ids or n.node_id == ds_id]
        return GraphQueryResponse(nodes=nodes, edges=edges)

    def _orphan_agents(self) -> GraphQueryResponse:
        agents = [n for n in self._repo.list_graph_nodes(NodeType.AGENT.value)]
        orphans = []
        orphan_edges = []
        for agent in agents:
            policy_edges = [
                e
                for e in self._repo.list_graph_edges(source_id=agent.node_id)
                if e.edge_type == EdgeType.HAS_POLICY
            ]
            if not policy_edges:
                orphans.append(agent)
        return GraphQueryResponse(
            nodes=orphans,
            edges=orphan_edges,
            metadata={"orphan_count": len(orphans)},
        )

    def _blast_radius(self, tool_id: str | None) -> GraphQueryResponse:
        if not tool_id:
            return GraphQueryResponse(nodes=[], edges=[])
        tid = tool_id if tool_id.startswith("tool-") else f"tool-{tool_id}"
        visited_nodes: set[str] = {tid}
        visited_edges: list[GraphEdge] = []
        queue: deque[str] = deque([tid])

        while queue:
            current = queue.popleft()
            inbound = self._repo.list_graph_edges(target_id=current)
            for edge in inbound:
                visited_edges.append(edge)
                if edge.source_id not in visited_nodes:
                    visited_nodes.add(edge.source_id)
                    queue.append(edge.source_id)

        nodes = [n for n in self._repo.list_graph_nodes() if n.node_id in visited_nodes]
        return GraphQueryResponse(
            nodes=nodes,
            edges=visited_edges,
            metadata={"blast_radius_size": len(nodes)},
        )
