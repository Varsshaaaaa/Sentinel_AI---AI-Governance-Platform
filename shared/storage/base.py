"""Abstract repository interface."""

from abc import ABC, abstractmethod
from typing import Any

from shared.models.agent import Agent, AgentRegistration
from shared.models.audit import AuditStep, DecisionPath
from shared.models.events import GovernanceEvent
from shared.models.governance import GovernanceState
from shared.models.graph import GraphEdge, GraphNode
from shared.models.policy import Policy, PolicyVersion
from shared.models.violation import Violation

try:
    from governance.agent_waf.models import WAFDecisionRecord
except ImportError:
    WAFDecisionRecord = None  # type: ignore


class Repository(ABC):
    # Agents
    @abstractmethod
    def create_agent(self, registration: AgentRegistration) -> Agent: ...

    @abstractmethod
    def get_agent(self, agent_id: str) -> Agent | None: ...

    @abstractmethod
    def list_agents(self) -> list[Agent]: ...

    @abstractmethod
    def update_agent(self, agent: Agent) -> Agent: ...

    # Policies
    @abstractmethod
    def save_policy(self, policy: Policy, version: PolicyVersion) -> Policy: ...

    @abstractmethod
    def get_policy(self, policy_id: str) -> Policy | None: ...

    @abstractmethod
    def list_policies(self) -> list[Policy]: ...

    @abstractmethod
    def get_policy_version(self, policy_id: str, version: str) -> PolicyVersion | None: ...

    # Sessions / violations
    @abstractmethod
    def increment_session_violations(self, session_id: str) -> int: ...

    @abstractmethod
    def get_session_violations(self, session_id: str) -> int: ...

    @abstractmethod
    def is_session_suspended(self, session_id: str) -> bool: ...

    @abstractmethod
    def suspend_session(self, session_id: str) -> None: ...

    @abstractmethod
    def record_tool_call(self, session_id: str, tool_name: str) -> list[str]: ...

    @abstractmethod
    def get_session_tool_calls(self, session_id: str) -> list[str]: ...

    @abstractmethod
    def increment_rate_counter(
        self, agent_id: str, tool_name: str, window_seconds: int = 60
    ) -> int: ...

    # Violations
    @abstractmethod
    def save_violation(self, violation: Violation) -> Violation: ...

    @abstractmethod
    def list_violations(self, agent_id: str | None = None) -> list[Violation]: ...

    # Audit
    @abstractmethod
    def next_audit_sequence(self, session_id: str) -> int: ...

    @abstractmethod
    def save_audit_step(self, step: AuditStep) -> AuditStep: ...

    @abstractmethod
    def get_decision_path(self, session_id: str) -> DecisionPath | None: ...

    @abstractmethod
    def list_decision_paths(
        self, user_id: str | None = None, agent_id: str | None = None
    ) -> list[DecisionPath]: ...

    # Graph
    @abstractmethod
    def upsert_graph_node(self, node: GraphNode) -> GraphNode: ...

    @abstractmethod
    def upsert_graph_edge(self, edge: GraphEdge) -> GraphEdge: ...

    @abstractmethod
    def list_graph_nodes(self, node_type: str | None = None) -> list[GraphNode]: ...

    @abstractmethod
    def list_graph_edges(
        self, source_id: str | None = None, target_id: str | None = None
    ) -> list[GraphEdge]: ...

    # Governance state
    @abstractmethod
    def get_governance_state(self, agent_id: str) -> GovernanceState | None: ...

    @abstractmethod
    def save_governance_state(self, state: GovernanceState) -> GovernanceState: ...

    @abstractmethod
    def list_governance_states(
        self, status: str | None = None
    ) -> list[GovernanceState]: ...

    # Events
    @abstractmethod
    def save_event(self, event: GovernanceEvent) -> GovernanceEvent: ...

    @abstractmethod
    def list_events(
        self, agent_id: str | None = None, limit: int = 100
    ) -> list[GovernanceEvent]: ...

    # HITL
    @abstractmethod
    def create_hitl_ticket(self, ticket: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def get_hitl_ticket(self, ticket_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def update_hitl_ticket(self, ticket_id: str, updates: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def list_hitl_tickets(self, status: str | None = None) -> list[dict[str, Any]]: ...

    @abstractmethod
    def find_approved_hitl_ticket(
        self,
        session_id: str,
        tool_name: str,
        tool_params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None: ...

    # WAF records
    @abstractmethod
    def save_waf_record(self, record: "WAFDecisionRecord") -> "WAFDecisionRecord": ...

    @abstractmethod
    def list_waf_records(self, agent_id: str | None = None, limit: int = 100) -> list["WAFDecisionRecord"]: ...
