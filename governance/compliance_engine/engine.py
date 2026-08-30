"""Compliance engine — runtime-to-compliance bridge."""

from datetime import datetime, timezone

from shared.models.events import EventType
from shared.models.governance import GovernanceStatus
from shared.events.publisher import EventPublisher
from shared.storage.base import Repository


class ComplianceEngine:
    def __init__(self, repository: Repository, publisher: EventPublisher) -> None:
        self._repo = repository
        self._publisher = publisher
        self._timeline: dict[str, list[dict]] = {}

    def check(self, agent_id: str) -> dict:
        agent = self._repo.get_agent(agent_id)
        if not agent:
            return {"agent_id": agent_id, "status": "unknown", "score": 0}

        gov = self._repo.get_governance_state(agent_id)
        violations = self._repo.list_violations(agent_id=agent_id)
        recent_violations = [
            v for v in violations
            if (datetime.now(timezone.utc) - v.timestamp).days <= 7
        ]

        status = "green"
        score = 100
        if gov and gov.status == GovernanceStatus.UNDER_REVIEW:
            status = "amber"
            score = 70
        elif gov and gov.status == GovernanceStatus.SUSPENDED:
            status = "red"
            score = 30
        elif len(recent_violations) >= 3:
            status = "amber"
            score = 60
        elif recent_violations:
            status = "amber"
            score = 80

        policies = [self._repo.get_policy(pid) for pid in agent.policy_ids]
        active_policies = [p for p in policies if p and p.status == "active"]

        result = {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "compliance_status": status,
            "compliance_score": score,
            "guardrails_active": len(active_policies) > 0,
            "policy_count": len(active_policies),
            "violation_count_7d": len(recent_violations),
            "governance_status": gov.status.value if gov else "green",
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }

        self._record_timeline(agent_id, status, result)
        return result

    def check_all(self) -> list[dict]:
        return [self.check(a.agent_id) for a in self._repo.list_agents()]

    def _record_timeline(self, agent_id: str, status: str, result: dict) -> None:
        entries = self._timeline.setdefault(agent_id, [])
        if entries and entries[-1]["status"] == status:
            return
        entry = {
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": result["compliance_score"],
            "trigger": result.get("governance_status", "runtime_check"),
        }
        entries.append(entry)
        self._publisher.emit(
            EventType.COMPLIANCE_CHANGED,
            agent_id=agent_id,
            payload=entry,
        )

    def timeline(self, agent_id: str | None = None, days: int = 7) -> list[dict]:
        if agent_id:
            return self._timeline.get(agent_id, [])
        all_entries = []
        for aid, entries in self._timeline.items():
            for e in entries:
                all_entries.append({"agent_id": aid, **e})
        return sorted(all_entries, key=lambda x: x["timestamp"], reverse=True)
