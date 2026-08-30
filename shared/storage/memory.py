"""In-memory repository for local development and tests."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from shared.models.agent import Agent, AgentRegistration, AgentStatus
from shared.models.audit import AuditStep, DecisionPath
from shared.models.events import GovernanceEvent
from shared.models.governance import GovernanceState, GovernanceStatus
from shared.models.graph import GraphEdge, GraphNode
from shared.models.policy import Policy, PolicyVersion
from shared.models.violation import Violation
from shared.storage.base import Repository

try:
    from governance.agent_waf.models import WAFDecisionRecord
except ImportError:
    WAFDecisionRecord = None  # type: ignore


class MemoryRepository(Repository):
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._policies: dict[str, Policy] = {}
        self._policy_versions: dict[str, dict[str, PolicyVersion]] = {}
        self._session_violations: dict[str, int] = {}
        self._suspended_sessions: set[str] = set()
        self._session_tools: dict[str, list[str]] = {}
        # Sliding-window rate limiting: per key, a log of call epoch timestamps.
        self._rate_windows: dict[str, list[float]] = {}
        self._violations: list[Violation] = []
        self._audit_steps: dict[str, list[AuditStep]] = {}
        self._audit_sequences: dict[str, int] = {}
        self._graph_nodes: dict[str, GraphNode] = {}
        self._graph_edges: list[GraphEdge] = []
        self._governance_states: dict[str, GovernanceState] = {}
        self._events: list[GovernanceEvent] = []
        self._hitl_tickets: dict[str, dict[str, Any]] = {}
        self._waf_records: list = []
        self._waf_scope_violations: dict[str, int] = {}
        self._ws_connections: dict[str, str] = {}

    def create_agent(self, registration: AgentRegistration) -> Agent:
        agent_id = f"agent-{uuid4().hex[:12]}"
        agent = Agent(agent_id=agent_id, **registration.model_dump())
        self._agents[agent_id] = agent
        return agent

    def get_agent(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[Agent]:
        return list(self._agents.values())

    def update_agent(self, agent: Agent) -> Agent:
        agent.updated_at = datetime.now(timezone.utc)
        self._agents[agent.agent_id] = agent
        return agent

    def save_policy(self, policy: Policy, version: PolicyVersion) -> Policy:
        self._policies[policy.policy_id] = policy
        self._policy_versions.setdefault(policy.policy_id, {})[version.version] = version
        return policy

    def get_policy(self, policy_id: str) -> Policy | None:
        return self._policies.get(policy_id)

    def list_policies(self) -> list[Policy]:
        return list(self._policies.values())

    def get_policy_version(self, policy_id: str, version: str) -> PolicyVersion | None:
        return self._policy_versions.get(policy_id, {}).get(version)

    def increment_session_violations(self, session_id: str) -> int:
        self._session_violations[session_id] = self._session_violations.get(session_id, 0) + 1
        return self._session_violations[session_id]

    def get_session_violations(self, session_id: str) -> int:
        return self._session_violations.get(session_id, 0)

    def is_session_suspended(self, session_id: str) -> bool:
        return session_id in self._suspended_sessions

    def suspend_session(self, session_id: str) -> None:
        self._suspended_sessions.add(session_id)

    def record_tool_call(self, session_id: str, tool_name: str) -> list[str]:
        calls = self._session_tools.setdefault(session_id, [])
        calls.append(tool_name)
        return calls

    def get_session_tool_calls(self, session_id: str) -> list[str]:
        return self._session_tools.get(session_id, [])

    def increment_rate_counter(
        self, agent_id: str, tool_name: str, window_seconds: int = 60
    ) -> int:
        """True sliding-window counter.

        Records each call's timestamp and returns the number of calls within the
        trailing ``window_seconds``. Unlike a fixed window this does not reset in
        bulk at window boundaries, so a burst straddling the boundary is still
        counted correctly.
        """
        key = f"{agent_id}:{tool_name}"
        now = datetime.now(timezone.utc).timestamp()
        cutoff = now - window_seconds
        window = [ts for ts in self._rate_windows.get(key, []) if ts > cutoff]
        window.append(now)
        self._rate_windows[key] = window
        return len(window)

    def save_violation(self, violation: Violation) -> Violation:
        self._violations.append(violation)
        return violation

    def list_violations(self, agent_id: str | None = None) -> list[Violation]:
        if agent_id:
            return [v for v in self._violations if v.agent_id == agent_id]
        return list(self._violations)

    def next_audit_sequence(self, session_id: str) -> int:
        self._audit_sequences[session_id] = self._audit_sequences.get(session_id, 0) + 1
        return self._audit_sequences[session_id]

    def save_audit_step(self, step: AuditStep) -> AuditStep:
        self._audit_steps.setdefault(step.session_id, []).append(step)
        return step

    def get_decision_path(self, session_id: str) -> DecisionPath | None:
        steps = self._audit_steps.get(session_id, [])
        if not steps:
            return None
        steps_sorted = sorted(steps, key=lambda s: s.step_sequence)
        return DecisionPath(
            session_id=session_id,
            agent_id=steps_sorted[0].agent_id,
            user_id=steps_sorted[0].user_id,
            steps=steps_sorted,
            started_at=steps_sorted[0].timestamp,
            completed_at=steps_sorted[-1].timestamp,
        )

    def list_decision_paths(
        self, user_id: str | None = None, agent_id: str | None = None
    ) -> list[DecisionPath]:
        paths = []
        for session_id in self._audit_steps:
            path = self.get_decision_path(session_id)
            if path is None:
                continue
            if user_id and path.user_id != user_id:
                continue
            if agent_id and path.agent_id != agent_id:
                continue
            paths.append(path)
        return paths

    def upsert_graph_node(self, node: GraphNode) -> GraphNode:
        self._graph_nodes[node.node_id] = node
        return node

    def upsert_graph_edge(self, edge: GraphEdge) -> GraphEdge:
        for existing in self._graph_edges:
            if (
                existing.source_id == edge.source_id
                and existing.target_id == edge.target_id
                and existing.edge_type == edge.edge_type
            ):
                return existing
        self._graph_edges.append(edge)
        return edge

    def list_graph_nodes(self, node_type: str | None = None) -> list[GraphNode]:
        nodes = list(self._graph_nodes.values())
        if node_type:
            nodes = [n for n in nodes if n.node_type.value == node_type]
        return nodes

    def list_graph_edges(
        self, source_id: str | None = None, target_id: str | None = None
    ) -> list[GraphEdge]:
        edges = self._graph_edges
        if source_id:
            edges = [e for e in edges if e.source_id == source_id]
        if target_id:
            edges = [e for e in edges if e.target_id == target_id]
        return edges

    def get_governance_state(self, agent_id: str) -> GovernanceState | None:
        return self._governance_states.get(agent_id)

    def save_governance_state(self, state: GovernanceState) -> GovernanceState:
        state.updated_at = datetime.now(timezone.utc)
        self._governance_states[state.agent_id] = state
        return state

    def list_governance_states(self, status: str | None = None) -> list[GovernanceState]:
        states = list(self._governance_states.values())
        if status:
            states = [s for s in states if s.status.value == status]
        return states

    def save_event(self, event: GovernanceEvent) -> GovernanceEvent:
        self._events.append(event)
        return event

    def list_events(self, agent_id: str | None = None, limit: int = 100) -> list[GovernanceEvent]:
        events = self._events
        if agent_id:
            events = [e for e in events if e.agent_id == agent_id]
        events = sorted(events, key=lambda e: e.timestamp, reverse=True)
        return events[:limit]

    def create_hitl_ticket(self, ticket: dict[str, Any]) -> dict[str, Any]:
        ticket_id = ticket.get("ticket_id") or f"hitl-{uuid4().hex[:12]}"
        ticket["ticket_id"] = ticket_id
        ticket.setdefault("status", "pending")
        ticket.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        self._hitl_tickets[ticket_id] = ticket
        return ticket

    def get_hitl_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        return self._hitl_tickets.get(ticket_id)

    def update_hitl_ticket(self, ticket_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        ticket = self._hitl_tickets[ticket_id]
        ticket.update(updates)
        self._hitl_tickets[ticket_id] = ticket
        return ticket

    def list_hitl_tickets(self, status: str | None = None) -> list[dict[str, Any]]:
        tickets = list(self._hitl_tickets.values())
        if status:
            tickets = [t for t in tickets if t.get("status") == status]
        return tickets

    def find_approved_hitl_ticket(
        self,
        session_id: str,
        tool_name: str,
        tool_params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        from shared.storage.hitl import hitl_action_matches

        for ticket in self.list_hitl_tickets("approved"):
            if hitl_action_matches(ticket, session_id, tool_name, tool_params):
                return ticket
        return None

    def save_waf_record(self, record) -> object:
        self._waf_records.append(record)
        return record

    def list_waf_records(self, agent_id: str | None = None, limit: int = 100) -> list:
        records = self._waf_records
        if agent_id:
            records = [r for r in records if r.agent_id == agent_id]
        return sorted(records, key=lambda r: r.timestamp, reverse=True)[:limit]

    def increment_waf_scope_violations(self, session_id: str) -> int:
        self._waf_scope_violations[session_id] = self._waf_scope_violations.get(session_id, 0) + 1
        return self._waf_scope_violations[session_id]

    def get_waf_scope_violations(self, session_id: str) -> int:
        return self._waf_scope_violations.get(session_id, 0)

    def save_ws_connection(self, connection_id: str, agent_id: str = "all") -> None:
        self._ws_connections[connection_id] = agent_id

    def delete_ws_connection(self, connection_id: str) -> None:
        self._ws_connections.pop(connection_id, None)

    def list_ws_connections(self, agent_id: str | None = None) -> list[str]:
        if agent_id is None:
            return list(self._ws_connections.keys())
        return [
            connection_id
            for connection_id, subscribed_agent in self._ws_connections.items()
            if subscribed_agent in (agent_id, "all")
        ]

    def get_or_create_governance_state(self, agent_id: str) -> GovernanceState:
        if agent_id not in self._governance_states:
            self._governance_states[agent_id] = GovernanceState(
                agent_id=agent_id, status=GovernanceStatus.GREEN
            )
        return self._governance_states[agent_id]
