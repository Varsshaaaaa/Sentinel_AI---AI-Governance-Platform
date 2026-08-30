"""DynamoDB repository implementation."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError

from shared.config.settings import get_settings
from shared.models.agent import Agent, AgentRegistration
from shared.models.audit import AuditStep, DecisionPath, StepType
from shared.models.events import GovernanceEvent, EventType
from shared.models.governance import GovernanceState, GovernanceStatus
from shared.models.graph import GraphEdge, GraphNode, EdgeType, NodeType
from shared.models.policy import Policy, PolicyRule, PolicyVersion
from shared.models.violation import Violation, ViolationSeverity
from governance.agent_waf.models import WAFDecisionRecord
from shared.models.tool import WAFDisposition, WAFRuleEvaluation
from shared.storage.base import Repository
from shared.storage.memory import MemoryRepository


def _serialize(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, Decimal):
        return obj
    if hasattr(obj, "value"):
        return obj.value
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    return obj


def _deserialize_datetime(val: str | None) -> datetime | None:
    if val is None:
        return None
    return datetime.fromisoformat(val.replace("Z", "+00:00"))


class DynamoDBRepository(Repository):
    """DynamoDB-backed repository with fallback to memory for session state."""

    def __init__(self) -> None:
        settings = get_settings()
        kwargs: dict[str, Any] = {"region_name": settings.aws_region}
        if settings.dynamodb_endpoint:
            kwargs["endpoint_url"] = settings.dynamodb_endpoint
        self._client = boto3.resource("dynamodb", **kwargs)
        self._prefix = settings.dynamodb_table_prefix
        self._session_store = MemoryRepository()

    def _table(self, name: str):
        return self._client.Table(f"{self._prefix}-{name}")

    def create_agent(self, registration: AgentRegistration) -> Agent:
        agent_id = f"agent-{uuid4().hex[:12]}"
        agent = Agent(agent_id=agent_id, **registration.model_dump())
        item = {"PK": f"AGENT#{agent_id}", "SK": "METADATA", **_serialize(agent.model_dump())}
        self._table("agents").put_item(Item=item)
        return agent

    def get_agent(self, agent_id: str) -> Agent | None:
        try:
            resp = self._table("agents").get_item(
                Key={"PK": f"AGENT#{agent_id}", "SK": "METADATA"}
            )
            item = resp.get("Item")
            if not item:
                return None
            data = {k: v for k, v in item.items() if k not in ("PK", "SK")}
            if data.get("created_at"):
                data["created_at"] = _deserialize_datetime(data["created_at"])
            if data.get("updated_at"):
                data["updated_at"] = _deserialize_datetime(data["updated_at"])
            if data.get("last_active_at"):
                data["last_active_at"] = _deserialize_datetime(data["last_active_at"])
            if data.get("credential_expires_at"):
                data["credential_expires_at"] = _deserialize_datetime(data["credential_expires_at"])
            return Agent(**data)
        except ClientError:
            return None

    def list_agents(self) -> list[Agent]:
        resp = self._table("agents").scan(
            FilterExpression="SK = :sk",
            ExpressionAttributeValues={":sk": "METADATA"},
        )
        agents = []
        for item in resp.get("Items", []):
            agent_id = item["PK"].replace("AGENT#", "")
            agent = self.get_agent(agent_id)
            if agent:
                agents.append(agent)
        return agents

    def update_agent(self, agent: Agent) -> Agent:
        agent.updated_at = datetime.now(timezone.utc)
        item = {
            "PK": f"AGENT#{agent.agent_id}",
            "SK": "METADATA",
            **_serialize(agent.model_dump()),
        }
        self._table("agents").put_item(Item=item)
        return agent

    def save_policy(self, policy: Policy, version: PolicyVersion) -> Policy:
        self._table("policies").put_item(
            Item={
                "PK": f"POLICY#{policy.policy_id}",
                "SK": "METADATA",
                **_serialize(policy.model_dump()),
            }
        )
        self._table("policies").put_item(
            Item={
                "PK": f"POLICY#{policy.policy_id}",
                "SK": f"VERSION#{version.version}",
                **_serialize(version.model_dump()),
            }
        )
        return policy

    def get_policy(self, policy_id: str) -> Policy | None:
        try:
            resp = self._table("policies").get_item(
                Key={"PK": f"POLICY#{policy_id}", "SK": "METADATA"}
            )
            item = resp.get("Item")
            if not item:
                return None
            data = {k: v for k, v in item.items() if k not in ("PK", "SK")}
            rules = [PolicyRule(**r) if isinstance(r, dict) else r for r in data.get("rules", [])]
            data["rules"] = rules
            for field in ("created_at", "updated_at"):
                if data.get(field):
                    data[field] = _deserialize_datetime(data[field])
            return Policy(**data)
        except ClientError:
            return None

    def list_policies(self) -> list[Policy]:
        resp = self._table("policies").scan(
            FilterExpression="SK = :sk",
            ExpressionAttributeValues={":sk": "METADATA"},
        )
        policies = []
        for item in resp.get("Items", []):
            policy_id = item["PK"].replace("POLICY#", "")
            policy = self.get_policy(policy_id)
            if policy:
                policies.append(policy)
        return policies

    def get_policy_version(self, policy_id: str, version: str) -> PolicyVersion | None:
        try:
            resp = self._table("policies").get_item(
                Key={"PK": f"POLICY#{policy_id}", "SK": f"VERSION#{version}"}
            )
            item = resp.get("Item")
            if not item:
                return None
            data = {k: v for k, v in item.items() if k not in ("PK", "SK")}
            if data.get("created_at"):
                data["created_at"] = _deserialize_datetime(data["created_at"])
            return PolicyVersion(**data)
        except ClientError:
            return None

    # Session-scoped state uses in-memory store (hot path, ephemeral)
    def increment_session_violations(self, session_id: str) -> int:
        return self._session_store.increment_session_violations(session_id)

    def get_session_violations(self, session_id: str) -> int:
        return self._session_store.get_session_violations(session_id)

    def is_session_suspended(self, session_id: str) -> bool:
        return self._session_store.is_session_suspended(session_id)

    def suspend_session(self, session_id: str) -> None:
        self._session_store.suspend_session(session_id)

    def record_tool_call(self, session_id: str, tool_name: str) -> list[str]:
        return self._session_store.record_tool_call(session_id, tool_name)

    def get_session_tool_calls(self, session_id: str) -> list[str]:
        return self._session_store.get_session_tool_calls(session_id)

    def increment_rate_counter(
        self, agent_id: str, tool_name: str, window_seconds: int = 60
    ) -> int:
        return self._session_store.increment_rate_counter(agent_id, tool_name, window_seconds)

    def save_violation(self, violation: Violation) -> Violation:
        self._table("violations").put_item(
            Item={
                "PK": f"VIOLATION#{violation.violation_id}",
                "SK": "METADATA",
                "GSI1PK": f"AGENT#{violation.agent_id}",
                "GSI1SK": violation.timestamp.isoformat(),
                **_serialize(violation.model_dump()),
            }
        )
        return violation

    def list_violations(self, agent_id: str | None = None) -> list[Violation]:
        if agent_id:
            resp = self._table("violations").query(
                IndexName="GSI1",
                KeyConditionExpression="GSI1PK = :pk",
                ExpressionAttributeValues={":pk": f"AGENT#{agent_id}"},
            )
        else:
            resp = self._table("violations").scan()
        violations = []
        for item in resp.get("Items", []):
            data = {k: v for k, v in item.items() if k not in ("PK", "SK", "GSI1PK", "GSI1SK")}
            if data.get("timestamp"):
                data["timestamp"] = _deserialize_datetime(data["timestamp"])
            violations.append(Violation(**data))
        return violations

    def next_audit_sequence(self, session_id: str) -> int:
        # Atomic per-session counter — safe across concurrent Lambda instances.
        resp = self._table("audit").update_item(
            Key={"PK": f"SESSION#{session_id}", "SK": "SEQCOUNTER"},
            UpdateExpression="ADD seq :one",
            ExpressionAttributeValues={":one": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(resp["Attributes"]["seq"])

    def save_audit_step(self, step: AuditStep) -> AuditStep:
        self._table("audit").put_item(
            Item={
                "PK": f"SESSION#{step.session_id}",
                "SK": f"STEP#{step.step_sequence:06d}",
                **_serialize(step.model_dump()),
            }
        )
        return step

    def get_decision_path(self, session_id: str) -> DecisionPath | None:
        resp = self._table("audit").query(
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": f"SESSION#{session_id}"},
        )
        items = resp.get("Items", [])
        if not items:
            return None
        steps = []
        for item in sorted(items, key=lambda x: x["SK"]):
            if not str(item.get("SK", "")).startswith("STEP#"):
                continue  # skip the SEQCOUNTER bookkeeping item
            data = {k: v for k, v in item.items() if k not in ("PK", "SK")}
            if data.get("timestamp"):
                data["timestamp"] = _deserialize_datetime(data["timestamp"])
            data["step_type"] = StepType(data["step_type"])
            steps.append(AuditStep(**data))
        return DecisionPath(
            session_id=session_id,
            agent_id=steps[0].agent_id,
            user_id=steps[0].user_id,
            steps=steps,
            started_at=steps[0].timestamp,
            completed_at=steps[-1].timestamp,
        )

    def list_decision_paths(
        self, user_id: str | None = None, agent_id: str | None = None
    ) -> list[DecisionPath]:
        return self._session_store.list_decision_paths(user_id, agent_id)

    def upsert_graph_node(self, node: GraphNode) -> GraphNode:
        self._table("graph").put_item(
            Item={
                "PK": f"NODE#{node.node_type.value}#{node.node_id}",
                "SK": "METADATA",
                "GSI1PK": f"TYPE#{node.node_type.value}",
                "GSI1SK": node.node_id,
                **_serialize(node.model_dump()),
            }
        )
        return node

    def upsert_graph_edge(self, edge: GraphEdge) -> GraphEdge:
        self._table("graph").put_item(
            Item={
                "PK": f"NODE#{edge.source_id}",
                "SK": f"EDGE#{edge.edge_type.value}#{edge.target_id}",
                "GSI2PK": f"TARGET#{edge.target_id}",
                "GSI2SK": edge.edge_type.value,
                **_serialize(edge.model_dump()),
            }
        )
        return edge

    def list_graph_nodes(self, node_type: str | None = None) -> list[GraphNode]:
        if node_type:
            resp = self._table("graph").query(
                IndexName="GSI1",
                KeyConditionExpression="GSI1PK = :pk",
                ExpressionAttributeValues={":pk": f"TYPE#{node_type}"},
            )
        else:
            resp = self._table("graph").scan(FilterExpression="SK = :sk", ExpressionAttributeValues={":sk": "METADATA"})
        nodes = []
        for item in resp.get("Items", []):
            data = {k: v for k, v in item.items() if k not in ("PK", "SK", "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK")}
            data["node_type"] = NodeType(data["node_type"])
            nodes.append(GraphNode(**data))
        return nodes

    def list_graph_edges(
        self, source_id: str | None = None, target_id: str | None = None
    ) -> list[GraphEdge]:
        if source_id:
            resp = self._table("graph").query(
                KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
                ExpressionAttributeValues={":pk": f"NODE#{source_id}", ":sk": "EDGE#"},
            )
        elif target_id:
            resp = self._table("graph").query(
                IndexName="GSI2",
                KeyConditionExpression="GSI2PK = :pk",
                ExpressionAttributeValues={":pk": f"TARGET#{target_id}"},
            )
        else:
            resp = self._table("graph").scan(FilterExpression="begins_with(SK, :sk)", ExpressionAttributeValues={":sk": "EDGE#"})
        edges = []
        for item in resp.get("Items", []):
            data = {k: v for k, v in item.items() if k not in ("PK", "SK", "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK")}
            data["edge_type"] = EdgeType(data["edge_type"])
            edges.append(GraphEdge(**data))
        return edges

    def get_governance_state(self, agent_id: str) -> GovernanceState | None:
        try:
            resp = self._table("governance").get_item(
                Key={"PK": f"AGENT#{agent_id}", "SK": "GOVSTATE"}
            )
            item = resp.get("Item")
            if not item:
                return None
            data = {k: v for k, v in item.items() if k not in ("PK", "SK", "GSI1PK", "GSI1SK")}
            for field in ("since", "updated_at", "last_reminder_at"):
                if data.get(field):
                    data[field] = _deserialize_datetime(data[field])
            data["status"] = GovernanceStatus(data["status"])
            return GovernanceState(**data)
        except ClientError:
            return None

    def save_governance_state(self, state: GovernanceState) -> GovernanceState:
        state.updated_at = datetime.now(timezone.utc)
        self._table("governance").put_item(
            Item={
                "PK": f"AGENT#{state.agent_id}",
                "SK": "GOVSTATE",
                "GSI1PK": f"GOVSTATUS#{state.status.value}",
                "GSI1SK": state.since.isoformat(),
                **_serialize(state.model_dump()),
            }
        )
        return state

    def list_governance_states(self, status: str | None = None) -> list[GovernanceState]:
        if status:
            resp = self._table("governance").query(
                IndexName="GSI1",
                KeyConditionExpression="GSI1PK = :pk",
                ExpressionAttributeValues={":pk": f"GOVSTATUS#{status}"},
            )
        else:
            resp = self._table("governance").scan(
                FilterExpression="SK = :sk",
                ExpressionAttributeValues={":sk": "GOVSTATE"},
            )
        states = []
        for item in resp.get("Items", []):
            data = {k: v for k, v in item.items() if k not in ("PK", "SK", "GSI1PK", "GSI1SK")}
            for field in ("since", "updated_at", "last_reminder_at"):
                if data.get(field):
                    data[field] = _deserialize_datetime(data[field])
            data["status"] = GovernanceStatus(data["status"])
            states.append(GovernanceState(**data))
        return states

    def save_event(self, event: GovernanceEvent) -> GovernanceEvent:
        self._table("events").put_item(
            Item={
                "PK": f"TENANT#{event.tenant_id}",
                "SK": f"EVENT#{event.timestamp.isoformat()}#{event.event_id}",
                "GSI1PK": f"AGENT#{event.agent_id}" if event.agent_id else "GLOBAL",
                "GSI1SK": event.timestamp.isoformat(),
                **_serialize(event.model_dump()),
            }
        )
        return event

    def list_events(self, agent_id: str | None = None, limit: int = 100) -> list[GovernanceEvent]:
        if agent_id:
            resp = self._table("events").query(
                IndexName="GSI1",
                KeyConditionExpression="GSI1PK = :pk",
                ExpressionAttributeValues={":pk": f"AGENT#{agent_id}"},
                ScanIndexForward=False,
                Limit=limit,
            )
        else:
            resp = self._table("events").scan(Limit=limit)
        events = []
        for item in resp.get("Items", []):
            data = {k: v for k, v in item.items() if k not in ("PK", "SK", "GSI1PK", "GSI1SK")}
            if data.get("timestamp"):
                data["timestamp"] = _deserialize_datetime(data["timestamp"])
            data["event_type"] = EventType(data["event_type"])
            events.append(GovernanceEvent(**data))
        return sorted(events, key=lambda e: e.timestamp, reverse=True)[:limit]

    def _hitl_ticket_item(self, ticket: dict[str, Any]) -> dict[str, Any]:
        ticket_id = ticket.get("ticket_id") or f"hitl-{uuid4().hex[:12]}"
        status = ticket.get("status", "pending")
        created_at = ticket.get("created_at") or datetime.now(timezone.utc).isoformat()
        ticket = {**ticket, "ticket_id": ticket_id, "status": status, "created_at": created_at}
        return {
            "PK": f"HITL#{ticket_id}",
            "SK": "METADATA",
            "GSI1PK": f"HITLSTATUS#{status}",
            "GSI1SK": created_at,
            **_serialize(ticket),
        }

    @staticmethod
    def _item_to_hitl_ticket(item: dict[str, Any]) -> dict[str, Any]:
        data = {k: v for k, v in item.items() if k not in ("PK", "SK", "GSI1PK", "GSI1SK")}
        if data.get("risk_score") is not None:
            data["risk_score"] = int(data["risk_score"])
        return data

    def create_hitl_ticket(self, ticket: dict[str, Any]) -> dict[str, Any]:
        item = self._hitl_ticket_item(ticket)
        self._table("governance").put_item(Item=item)
        return self._item_to_hitl_ticket(item)

    def get_hitl_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        try:
            resp = self._table("governance").get_item(
                Key={"PK": f"HITL#{ticket_id}", "SK": "METADATA"}
            )
            item = resp.get("Item")
            if not item:
                return self._session_store.get_hitl_ticket(ticket_id)
            return self._item_to_hitl_ticket(item)
        except ClientError:
            return self._session_store.get_hitl_ticket(ticket_id)

    def update_hitl_ticket(self, ticket_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        ticket = self.get_hitl_ticket(ticket_id)
        if not ticket:
            raise KeyError(f"HITL ticket not found: {ticket_id}")
        ticket.update(updates)
        return self.create_hitl_ticket(ticket)

    def list_hitl_tickets(self, status: str | None = None) -> list[dict[str, Any]]:
        try:
            if status:
                resp = self._table("governance").query(
                    IndexName="GSI1",
                    KeyConditionExpression="GSI1PK = :pk",
                    ExpressionAttributeValues={":pk": f"HITLSTATUS#{status}"},
                    ScanIndexForward=False,
                )
            else:
                resp = self._table("governance").scan(
                    FilterExpression="begins_with(PK, :pk)",
                    ExpressionAttributeValues={":pk": "HITL#"},
                )
            tickets = [self._item_to_hitl_ticket(item) for item in resp.get("Items", [])]
            if tickets:
                return sorted(tickets, key=lambda t: t.get("created_at", ""), reverse=True)
        except ClientError:
            pass
        return self._session_store.list_hitl_tickets(status)

    def find_approved_hitl_ticket(
        self,
        session_id: str,
        tool_name: str,
        tool_params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        from shared.storage.hitl import hitl_action_matches

        for ticket in self.list_hitl_tickets("approved"):
            if hitl_action_matches(ticket, session_id, tool_name, tool_params):
                return ticket
        return None

    def save_waf_record(self, record) -> object:
        ts = record.timestamp.isoformat()
        self._table("audit").put_item(
            Item={
                "PK": "WAF#RECORDS",
                "SK": f"{ts}#{record.record_id}",
                **_serialize(
                    {
                        "record_id": record.record_id,
                        "timestamp": record.timestamp,
                        "agent_id": record.agent_id,
                        "session_id": record.session_id,
                        "tool_name": record.tool_name,
                        "action_type": record.action_type,
                        "disposition": record.disposition.value,
                        "matched_rules": record.matched_rules,
                        "evaluations": [e.model_dump() for e in record.evaluations],
                        "reason": record.reason,
                        "params_sanitized": record.params_sanitized,
                        "shadow_mode": record.shadow_mode,
                        "latency_ms": record.latency_ms,
                    }
                ),
            }
        )
        # Keep in-process cache for rate-limit counters within the same invocation.
        return self._session_store.save_waf_record(record)

    def list_waf_records(self, agent_id: str | None = None, limit: int = 100) -> list:
        resp = self._table("audit").query(
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": "WAF#RECORDS"},
            ScanIndexForward=False,
            Limit=min(limit * 4, 500),
        )
        records: list[WAFDecisionRecord] = []
        for item in resp.get("Items", []):
            rec = self._item_to_waf_record(item)
            if agent_id and rec.agent_id != agent_id:
                continue
            records.append(rec)
            if len(records) >= limit:
                break
        return records

    @staticmethod
    def _item_to_waf_record(item: dict) -> WAFDecisionRecord:
        data = {k: v for k, v in item.items() if k not in ("PK", "SK")}
        if data.get("timestamp"):
            data["timestamp"] = _deserialize_datetime(data["timestamp"])
        data["disposition"] = WAFDisposition(data["disposition"])
        if data.get("latency_ms") is not None:
            data["latency_ms"] = float(data["latency_ms"])
        evals = data.get("evaluations") or []
        data["evaluations"] = [
            WAFRuleEvaluation(**e) if isinstance(e, dict) else e for e in evals
        ]
        return WAFDecisionRecord(**data)

    def increment_waf_scope_violations(self, session_id: str) -> int:
        return self._session_store.increment_waf_scope_violations(session_id)

    def get_waf_scope_violations(self, session_id: str) -> int:
        return self._session_store.get_waf_scope_violations(session_id)

    def save_ws_connection(self, connection_id: str, agent_id: str = "all") -> None:
        self._table("websocket").put_item(
            Item={
                "PK": f"CONN#{connection_id}",
                "SK": "META",
                "agent_id": agent_id,
                "connected_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def delete_ws_connection(self, connection_id: str) -> None:
        self._table("websocket").delete_item(
            Item={"PK": f"CONN#{connection_id}", "SK": "META"},
        )

    def list_ws_connections(self, agent_id: str | None = None) -> list[str]:
        resp = self._table("websocket").scan(
            FilterExpression="SK = :sk",
            ExpressionAttributeValues={":sk": "META"},
        )
        connection_ids: list[str] = []
        for item in resp.get("Items", []):
            subscribed = item.get("agent_id", "all")
            if agent_id is None or subscribed in (agent_id, "all"):
                pk = item["PK"]
                connection_ids.append(pk.replace("CONN#", "", 1))
        return connection_ids
