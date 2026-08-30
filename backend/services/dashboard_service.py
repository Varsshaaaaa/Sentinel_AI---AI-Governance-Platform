"""Dashboard aggregation service."""

from governance.compliance_engine.engine import ComplianceEngine
from governance.risk_engine.engine import RiskEngine
from shared.events.publisher import EventPublisher
from shared.storage.base import Repository


class DashboardService:
    def __init__(self, repository: Repository) -> None:
        publisher = EventPublisher(repository)
        self._repo = repository
        self._risk = RiskEngine(repository, publisher)
        self._compliance = ComplianceEngine(repository, publisher)

    def get_dashboard(self) -> dict:
        agents = self._repo.list_agents()
        violations = self._repo.list_violations()
        events = self._repo.list_events(limit=20)
        heatmap = self._risk.heatmap()
        compliance = self._compliance.check_all()

        return {
            "summary": {
                "total_agents": len(agents),
                "active_agents": sum(1 for a in agents if a.status.value == "active"),
                "suspended_agents": sum(1 for a in agents if a.status.value == "suspended"),
                "total_violations": len(violations),
                "violations_24h": len(violations),
                "avg_risk_score": (
                    sum(int(h["risk_score"]) for h in heatmap) / len(heatmap) if heatmap else 0
                ),
                "compliance_green": sum(1 for c in compliance if c["compliance_status"] == "green"),
                "compliance_amber": sum(1 for c in compliance if c["compliance_status"] == "amber"),
                "compliance_red": sum(1 for c in compliance if c["compliance_status"] == "red"),
                "pending_hitl": len(self._repo.list_hitl_tickets("pending")),
            },
            "risk_heatmap": heatmap,
            "compliance": compliance,
            "recent_events": [
                {
                    "event_type": e.event_type.value,
                    "agent_id": e.agent_id,
                    "timestamp": e.timestamp.isoformat(),
                    "payload": e.payload,
                }
                for e in events
            ],
            "recent_violations": [
                {
                    "violation_id": v.violation_id,
                    "agent_id": v.agent_id,
                    "rule_name": v.rule_name,
                    "severity": v.severity.value,
                    "reason": v.reason,
                    "timestamp": v.timestamp.isoformat(),
                }
                for v in sorted(violations, key=lambda x: x.timestamp, reverse=True)[:10]
            ],
        }
