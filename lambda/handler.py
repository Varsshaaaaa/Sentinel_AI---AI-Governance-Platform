"""AWS Lambda handler.

Serves the FastAPI app over API Gateway (HTTP) and also handles scheduled
EventBridge invocations for the governance SLA sweep (PS-4.2 bonus). EventBridge
scheduled events are not HTTP requests, so we detect them and run the SLA
monitor directly instead of routing through Mangum.
"""

from mangum import Mangum

from backend.api.main import app
from shared.config.settings import reload_settings

# Fresh settings on each cold start (Lambda env vars are fixed at init).
reload_settings()

_http_handler = Mangum(app, lifespan="auto")


def _is_scheduled_sla_event(event: dict) -> bool:
    if not isinstance(event, dict):
        return False
    detail_type = event.get("detail-type") or event.get("detailType")
    if detail_type == "Scheduled Event":
        return True
    return event.get("task") == "sla-check"


def handler(event, context):
    if _is_scheduled_sla_event(event):
        from backend.deps import sla_monitor

        return sla_monitor().check_slas()
    return _http_handler(event, context)
