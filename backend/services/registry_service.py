"""Agent registry service."""

from datetime import datetime, timedelta, timezone

from governance.graph_engine.service import GraphEngine
from shared.events.publisher import EventPublisher
from shared.models.agent import Agent, AgentRegistration, AgentStatus
from shared.models.events import EventType
from shared.storage.base import Repository


class RegistryService:
    def __init__(self, repository: Repository) -> None:
        self._repo = repository
        self._publisher = EventPublisher(repository)
        self._graph = GraphEngine(repository)

    def register(self, registration: AgentRegistration) -> Agent:
        existing = next((a for a in self._repo.list_agents() if a.name == registration.name), None)
        if existing:
            agent = Agent(
                agent_id=existing.agent_id,
                created_at=existing.created_at,
                **registration.model_dump(),
            )
            agent.credential_expires_at = datetime.now(timezone.utc) + timedelta(days=90)
            self._repo.update_agent(agent)
            self._graph.ingest_agent(agent)
            return agent

        agent = self._repo.create_agent(registration)
        agent.credential_expires_at = datetime.now(timezone.utc) + timedelta(days=90)
        self._repo.update_agent(agent)
        self._graph.ingest_agent(agent)
        self._publisher.emit(
            EventType.AGENT_REGISTERED,
            agent_id=agent.agent_id,
            actor=registration.owner,
            payload={"name": agent.name, "framework": agent.framework},
        )
        return agent

    def get(self, agent_id: str) -> Agent | None:
        return self._repo.get_agent(agent_id)

    def list_agents(self) -> list[Agent]:
        return self._repo.list_agents()

    def suspend(self, agent_id: str, reason: str = "") -> Agent:
        agent = self._repo.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")
        agent.status = AgentStatus.SUSPENDED
        self._repo.update_agent(agent)
        self._publisher.emit(
            EventType.AGENT_SUSPENDED,
            agent_id=agent_id,
            payload={"reason": reason},
        )
        return agent

    def resume(self, agent_id: str) -> Agent:
        agent = self._repo.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")
        agent.status = AgentStatus.ACTIVE
        self._repo.update_agent(agent)
        return agent
