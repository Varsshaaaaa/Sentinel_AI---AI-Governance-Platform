"""Seed demo agents, policies, and baselines."""

from pathlib import Path

from backend.deps import registry_service, policy_service, repo
from backend.services.intercept_service import InterceptService
from governance.behavior_engine.engine import BehaviorEngine
from shared.models.agent import AgentRegistration, ModelRef, RiskTier, ToolScope
from shared.models.context import DataClassification, GovernanceContext
from shared.models.tool import ToolInterceptRequest

POLICIES_DIR = Path(__file__).resolve().parents[2] / "governance" / "policies"
_seeded = False


def seed(force: bool = False) -> dict:
    global _seeded
    if _seeded and not force:
        return {"message": "Already seeded"}

    ps = policy_service()
    for yaml_file in POLICIES_DIR.glob("*.yaml"):
        content = yaml_file.read_text(encoding="utf-8")
        ps.deploy(content, created_by="seed")

    rs = registry_service()

    finance = rs.register(
        AgentRegistration(
            name="Finance Agent",
            owner="finance-team",
            team="Finance",
            purpose="Financial record management and reporting",
            framework="langgraph",
            risk_tier=RiskTier.HIGH,
            models=[ModelRef(name="gpt-4o", provider="openai")],
            tools=[
                ToolScope(name="db_query", allowed_operations=["read"]),
                ToolScope(name="db_delete", allowed_operations=["delete"]),
                ToolScope(name="report_generate", allowed_operations=["read"]),
                ToolScope(name="payment_process", allowed_operations=["write"]),
                ToolScope(name="identity_verify", allowed_operations=["read"]),
                ToolScope(name="record_read", allowed_operations=["read"]),
                ToolScope(name="record_update", allowed_operations=["write"]),
            ],
            datasets=["financial_records", "transactions", "data_warehouse"],
            policy_ids=["finance-agent-policy"],
        )
    )

    support = rs.register(
        AgentRegistration(
            name="Customer Support Agent",
            owner="support-team",
            team="Support",
            purpose="Customer inquiry handling and email responses",
            framework="openai_agents",
            risk_tier=RiskTier.MEDIUM,
            models=[ModelRef(name="gpt-4o-mini", provider="openai")],
            tools=[
                ToolScope(name="crm_read", allowed_operations=["read"]),
                ToolScope(name="email_send", allowed_operations=["read", "write"]),
            ],
            datasets=["customer_records"],
            policy_ids=["support-agent-policy"],
        )
    )

    hr = rs.register(
        AgentRegistration(
            name="HR Agent",
            owner="hr-team",
            team="Human Resources",
            purpose="Employee record management",
            framework="crewai",
            risk_tier=RiskTier.MEDIUM,
            models=[ModelRef(name="claude-3-5-sonnet", provider="anthropic")],
            tools=[
                ToolScope(name="hr_records", allowed_operations=["read", "write"]),
                ToolScope(name="benefits_lookup", allowed_operations=["read"]),
            ],
            datasets=["employee_records", "benefits", "data_warehouse"],
            policy_ids=["hr-agent-policy"],
        )
    )

    developer = rs.register(
        AgentRegistration(
            name="Developer Agent",
            owner="engineering-team",
            team="Engineering",
            purpose="Code assistance and CI/CD operations",
            framework="pydantic_ai",
            risk_tier=RiskTier.LOW,
            models=[ModelRef(name="gpt-4o-mini", provider="openai")],
            tools=[
                ToolScope(name="code_search", allowed_operations=["read"]),
                ToolScope(name="api_call", allowed_operations=["read", "write"]),
            ],
            datasets=["codebase"],
            policy_ids=["developer-agent-policy"],
        )
    )

    # Shadow / unmanaged agent: registered but with no governing policy.
    # Demonstrates the graph's orphan-detection surface (ungoverned agent
    # touching a sensitive data source with no owner-approved policy).
    rs.register(
        AgentRegistration(
            name="Marketing Insights Agent",
            owner="marketing-team",
            team="Marketing",
            purpose="Campaign analytics and customer segmentation",
            framework="langgraph",
            risk_tier=RiskTier.MEDIUM,
            models=[ModelRef(name="gpt-4o", provider="openai")],
            tools=[
                ToolScope(name="crm_read", allowed_operations=["read"]),
                ToolScope(name="analytics_query", allowed_operations=["read"]),
            ],
            datasets=["customer_records", "data_warehouse"],
            policy_ids=["marketing-agent-policy"],
        )
    )

    behavior = BehaviorEngine(repo())
    behavior.set_baseline(finance.agent_id, {"db_query": 50, "report_generate": 20})
    behavior.set_baseline(support.agent_id, {"crm_read": 80, "email_send": 30})
    behavior.set_baseline(hr.agent_id, {"hr_records": 40, "benefits_lookup": 15})
    behavior.set_baseline(developer.agent_id, {"code_search": 100, "api_call": 50})

    _run_demo_sessions(finance.agent_id, support.agent_id)

    _seeded = True
    return {
        "message": "Demo data seeded",
        "agents": {
            "finance": finance.agent_id,
            "support": support.agent_id,
            "hr": hr.agent_id,
            "developer": developer.agent_id,
        },
    }


def _run_demo_sessions(finance_id: str, support_id: str) -> None:
    """Create sample decision paths for replay demo."""
    intercept = InterceptService(repo())

    intercept.intercept(
        ToolInterceptRequest(
            context=GovernanceContext(
                agent_id=finance_id,
                session_id="demo-finance-session",
                user_id="user-finance-1",
                action_type="delete",
                tool_name="db_delete",
                tool_params={"table": "financial_records", "count": 500},
                data_scope_size=500,
            )
        )
    )

    intercept.intercept(
        ToolInterceptRequest(
            context=GovernanceContext(
                agent_id=support_id,
                session_id="demo-support-session",
                user_id="user-support-1",
                action_type="write",
                tool_name="email_send",
                tool_params={"to": "customer@gmail.com", "subject": "Re: Your inquiry"},
            )
        )
    )

    intercept.intercept(
        ToolInterceptRequest(
            context=GovernanceContext(
                agent_id=finance_id,
                session_id="demo-finance-allowed",
                user_id="user-finance-1",
                action_type="delete",
                tool_name="db_delete",
                tool_params={"table": "financial_records", "count": 5},
                data_scope_size=5,
            )
        )
    )


if __name__ == "__main__":
    result = seed(force=True)
    print(result)
