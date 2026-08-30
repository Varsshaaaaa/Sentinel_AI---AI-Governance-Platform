"""External observability signal adapters (CloudWatch, OpenTelemetry)."""

from typing import Any


def map_cloudwatch_alarm(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Map a CloudWatch alarm notification (or direct JSON body) to an internal signal.

    Accepts either a flattened alarm body or SNS-wrapped Message JSON with keys:
    agent_id, signal_type, metric_value, alarm_state.
    """
    body = payload
    if "Message" in payload and isinstance(payload["Message"], str):
        import json

        try:
            body = json.loads(payload["Message"])
        except json.JSONDecodeError:
            body = payload

    agent_id = body.get("agent_id") or _dimension_value(body, "AgentId")
    signal_type = body.get("signal_type") or _dimension_value(body, "SignalType")
    if not agent_id or not signal_type:
        raise ValueError("CloudWatch alarm must include agent_id and signal_type")

    alarm_state = str(body.get("alarm_state") or body.get("NewStateValue") or "ALARM").upper()
    if alarm_state not in ("ALARM", "OK", "INSUFFICIENT_DATA"):
        alarm_state = "ALARM"

    return {
        "agent_id": agent_id,
        "signal_type": signal_type,
        "metric_value": body.get("metric_value") or body.get("Trigger", {}).get("Threshold"),
        "source": "cloudwatch",
        "alarm_state": alarm_state,
    }


def map_otel_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Map a minimal OpenTelemetry metrics export JSON to an internal governance signal.

    Expected shape:
    {
      "resource": {"attributes": {"agent.id": "<agent_id>"}},
      "scopeMetrics": [{
        "metrics": [{
          "name": "sentinelai.governance.signal",
          "gauge": {"dataPoints": [{
            "attributes": {"signal.type": "<signal_type>"},
            "asDouble": 1.0
          }]}
        }]
      }]
    }
    """
    resource_attrs = payload.get("resource", {}).get("attributes", {})
    agent_id = (
        resource_attrs.get("agent.id")
        or resource_attrs.get("service.name")
        or payload.get("agent_id")
    )
    signal_type = payload.get("signal_type")
    metric_value = payload.get("metric_value")

    for scope in payload.get("scopeMetrics", []):
        for metric in scope.get("metrics", []):
            if metric.get("name") != "sentinelai.governance.signal":
                continue
            gauge = metric.get("gauge") or metric.get("sum") or {}
            for point in gauge.get("dataPoints", []):
                attrs = point.get("attributes", {})
                signal_type = signal_type or attrs.get("signal.type")
                metric_value = metric_value if metric_value is not None else point.get("asDouble")

    if not agent_id or not signal_type:
        raise ValueError("OTel payload must include agent.id and signal.type")

    return {
        "agent_id": agent_id,
        "signal_type": signal_type,
        "metric_value": metric_value,
        "source": "otel",
    }


def _dimension_value(body: dict[str, Any], name: str) -> str | None:
    trigger = body.get("Trigger") or {}
    for dim in trigger.get("Dimensions", []):
        if dim.get("name") == name:
            return dim.get("value")
    return None
