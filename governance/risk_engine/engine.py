"""Risk scoring engine."""

from shared.models.agent import Agent
from shared.models.events import EventType
from shared.models.violation import ViolationSeverity
from shared.events.publisher import EventPublisher
from shared.storage.base import Repository


class RiskEngine:
    def __init__(self, repository: Repository, publisher: EventPublisher) -> None:
        self._repo = repository
        self._publisher = publisher
        self._scores: dict[str, int] = {}

    def score_agent(self, agent_id: str, anomaly_score: int = 0) -> dict[str, int | str]:
        agent = self._repo.get_agent(agent_id)
        base = agent.risk_score if agent else 44

        violations = self._repo.list_violations(agent_id=agent_id)
        violation_boost = min(30, len(violations) * 5)
        critical = sum(1 for v in violations if v.severity == ViolationSeverity.CRITICAL)
        critical_boost = critical * 10

        gov_state = self._repo.get_governance_state(agent_id)
        gov_boost = 0
        if gov_state:
            gov_boost = {"under_review": 10, "suspended": 20, "remediated": 5}.get(gov_state.status.value, 0)

        score = min(100, base + violation_boost + critical_boost + gov_boost + anomaly_score // 2)
        self._scores[agent_id] = score

        self._publisher.emit(
            EventType.RISK_UPDATED,
            agent_id=agent_id,
            payload={"score": score, "anomaly_score": anomaly_score},
        )

        return {
            "agent_id": agent_id,
            "risk_score": score,
            "factors": {
                "base": base,
                "violations": violation_boost,
                "critical_violations": critical_boost,
                "governance_status": gov_boost,
                "anomaly": anomaly_score // 2,
            },
        }

    def heatmap(self) -> list[dict[str, int | str]]:
        agents = self._repo.list_agents()
        result = []
        for agent in agents:
            if agent.agent_id in self._scores:
                score = self._scores[agent.agent_id]
            else:
                score = self.score_agent(agent.agent_id)["risk_score"]
            result.append(
                {
                    "agent_id": agent.agent_id,
                    "name": agent.name,
                    "risk_score": score,
                    "risk_tier": agent.risk_tier.value,
                    "status": agent.status.value,
                }
            )
        return sorted(result, key=lambda x: int(x["risk_score"]), reverse=True)
