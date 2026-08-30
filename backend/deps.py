"""Dependency injection container."""

from functools import lru_cache

from backend.services.copilot_service import PolicyCopilot
from backend.services.dashboard_service import DashboardService
from backend.services.intercept_service import InterceptService
from backend.services.policy_service import PolicyService
from backend.services.registry_service import RegistryService
from governance.compliance_engine.engine import ComplianceEngine
from governance.decision_engine.auditor import DecisionAuditor
from governance.graph_engine.service import GraphEngine
from governance.observability_pipeline.pipeline import ObservabilityPipeline
from governance.observability_pipeline.sla import GovernanceSLAMonitor
from governance.risk_engine.engine import RiskEngine
from governance.runtime_guardrails.simulator import GuardrailScenarioHarness
from shared.events.publisher import EventPublisher
from shared.storage.factory import get_repository


@lru_cache
def repo():
    return get_repository()


@lru_cache
def publisher():
    return EventPublisher(repo())


def registry_service() -> RegistryService:
    return RegistryService(repo())


def intercept_service() -> InterceptService:
    return InterceptService(repo())


def policy_service() -> PolicyService:
    return PolicyService(repo())


def copilot_service() -> PolicyCopilot:
    return PolicyCopilot()


def dashboard_service() -> DashboardService:
    return DashboardService(repo())


def graph_engine() -> GraphEngine:
    return GraphEngine(repo())


def decision_auditor() -> DecisionAuditor:
    return DecisionAuditor(repo())


def observability_pipeline() -> ObservabilityPipeline:
    return ObservabilityPipeline(repo(), publisher())


def sla_monitor() -> GovernanceSLAMonitor:
    return GovernanceSLAMonitor(repo(), publisher())


def guardrail_harness() -> GuardrailScenarioHarness:
    return GuardrailScenarioHarness(repo())


def risk_engine() -> RiskEngine:
    return RiskEngine(repo(), publisher())


def compliance_engine() -> ComplianceEngine:
    return ComplianceEngine(repo(), publisher())
