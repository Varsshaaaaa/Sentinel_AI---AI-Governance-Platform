"""Policy management service."""

from governance.graph_engine.service import GraphEngine
from governance.policy_engine.loader import PolicyLoader
from governance.policy_engine.simulator import PolicySimulator
from shared.events.publisher import EventPublisher
from shared.models.events import EventType
from shared.models.policy import Policy
from shared.storage.base import Repository


class PolicyService:
    def __init__(self, repository: Repository) -> None:
        self._repo = repository
        self._loader = PolicyLoader()
        self._simulator = PolicySimulator()
        self._graph = GraphEngine(repository)
        self._publisher = EventPublisher(repository)

    def deploy(self, yaml_content: str, created_by: str = "admin") -> Policy:
        policy = self._loader.parse_yaml(yaml_content)
        version = self._loader.create_version(yaml_content, created_by)
        self._repo.save_policy(policy, version)
        self._graph.ingest_policy(policy)
        self._publisher.emit(
            EventType.POLICY_UPDATED,
            payload={"policy_id": policy.policy_id, "version": version.version},
        )
        return policy

    def get(self, policy_id: str) -> Policy | None:
        return self._repo.get_policy(policy_id)

    def list_policies(self) -> list[Policy]:
        return self._repo.list_policies()

    def evaluate(self, context_dict: dict, agent_id: str) -> dict:
        from governance.policy_engine.evaluator import PolicyEvaluator
        from shared.models.context import DataClassification, GovernanceContext

        ctx = GovernanceContext(
            agent_id=agent_id,
            session_id=context_dict.get("session_id", "eval-session"),
            action_type=context_dict.get("action_type", "read"),
            tool_name=context_dict.get("tool_name", "unknown"),
            tool_params=context_dict.get("tool_params", {}),
            data_scope_size=context_dict.get("data_scope_size", 0),
            session_data_classification=DataClassification(
                context_dict.get("session_data_classification", "internal")
            ),
            previous_violations_in_session=context_dict.get("previous_violations_in_session", 0),
            user_role=context_dict.get("user_role", "user"),
        )
        agent = self._repo.get_agent(agent_id)
        policies = []
        if agent:
            for pid in agent.policy_ids:
                p = self._repo.get_policy(pid)
                if p:
                    policies.append(p)
        if not policies:
            policies = self._repo.list_policies()

        decision = PolicyEvaluator().evaluate(ctx, policies)
        return decision.model_dump()

    def simulate(self, yaml_content: str, session_id: str | None = None) -> dict:
        new_policy = self._loader.parse_yaml(yaml_content)
        old_policies = self._repo.list_policies()
        from governance.decision_engine.auditor import DecisionAuditor

        auditor = DecisionAuditor(self._repo)
        if session_id:
            path = auditor.get_decision_path(session_id)
            steps = path.steps if path else []
        else:
            steps = []
            for path in self._repo.list_decision_paths():
                steps.extend(path.steps)

        return self._simulator.simulate(steps, [new_policy], old_policies)
