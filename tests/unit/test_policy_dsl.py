"""Extended DSL and multi-level inheritance tests (PS-10.2)."""

from datetime import datetime, timezone

import pytest

from governance.policy_engine.evaluator import ConditionEvaluator, PolicyEvaluator
from governance.policy_engine.loader import PolicyLoader
from shared.models.context import DataClassification, GovernanceContext
from shared.models.policy import EnforcementAction


def _ctx(**kw):
    base = dict(agent_id="a1", session_id="s1", action_type="read", tool_name="db")
    base.update(kw)
    return GovernanceContext(**base)


@pytest.fixture
def ev():
    return ConditionEvaluator()


def test_not_operator(ev):
    cond = {"not": {"context.action_type": "read"}}
    assert ev.evaluate_condition(cond, _ctx(action_type="write")) is True
    assert ev.evaluate_condition(cond, _ctx(action_type="read")) is False


def test_nested_all_any_not(ev):
    cond = {
        "all": [
            {"context.action_type in": ["read", "write"]},
            {"any": [
                {"context.data_scope_size >": 100},
                {"not": {"context.session_data_classification ==": "public"}},
            ]},
        ]
    }
    ctx = _ctx(action_type="write", data_scope_size=5, session_data_classification=DataClassification.PHI)
    assert ev.evaluate_condition(cond, ctx) is True


def test_less_than_and_lte(ev):
    assert ev.evaluate_condition({"context.data_scope_size <": 10}, _ctx(data_scope_size=5)) is True
    assert ev.evaluate_condition({"context.data_scope_size <=": 5}, _ctx(data_scope_size=5)) is True
    assert ev.evaluate_condition({"context.data_scope_size <": 5}, _ctx(data_scope_size=5)) is False


def test_not_equal_and_not_in(ev):
    assert ev.evaluate_condition({"context.action_type !=": "read"}, _ctx(action_type="delete")) is True
    assert ev.evaluate_condition({"context.action_type not in": ["read", "list"]}, _ctx(action_type="delete")) is True
    assert ev.evaluate_condition({"context.action_type not in": ["read", "list"]}, _ctx(action_type="read")) is False


def test_contains(ev):
    ctx = _ctx(tool_name="db_delete")
    assert ev.evaluate_condition({"context.tool_name contains": "delete"}, ctx) is True
    assert ev.evaluate_condition({"context.tool_name contains": "email"}, ctx) is False


def test_tool_params_regex(ev):
    ctx = _ctx(
        tool_name="email_send",
        tool_params={"body": "Your password is expired"},
    )
    cond = {"context.tool_params.body": {"matches": "(?i)(password|ssn|credit.?card)"}}
    assert ev.evaluate_condition(cond, ctx) is True


def _policy(name, inherits=None, rules_yaml=""):
    doc = f"""
apiVersion: sentinelai.io/v1
kind: Policy
metadata:
  name: {name}
spec:
"""
    if inherits:
        doc += f"  inherits: {inherits}\n"
    doc += "  rules:\n" + (rules_yaml or "    []\n")
    return PolicyLoader.parse_yaml(doc)


def test_multi_level_inheritance():
    """grandparent → parent → child; unoverridden ancestor rules still apply."""
    grandparent = _policy(
        "gp",
        rules_yaml=(
            "    - name: allow-reads\n"
            "      priority: 10\n"
            "      when:\n"
            "        all:\n"
            "          - context.action_type: read\n"
            "      then:\n"
            "        action: allow\n"
        ),
    )
    parent = _policy(
        "parent",
        inherits="gp",
        rules_yaml=(
            "    - name: block-delete\n"
            "      priority: 200\n"
            "      when:\n"
            "        all:\n"
            "          - context.action_type: delete\n"
            "      then:\n"
            "        action: block\n"
        ),
    )
    child = _policy(
        "child",
        inherits="parent",
        rules_yaml=(
            "    - name: hitl-write\n"
            "      priority: 150\n"
            "      when:\n"
            "        all:\n"
            "          - context.action_type: write\n"
            "      then:\n"
            "        action: require_hitl\n"
        ),
    )

    pmap = {p.policy_id: p for p in (grandparent, parent, child)}
    evaluator = PolicyEvaluator()

    # child inherits the grandparent's block-delete (via parent) and its own rules.
    d_delete = evaluator.evaluate(_ctx(action_type="delete"), [child], policy_provider=pmap.get)
    assert d_delete.action == EnforcementAction.BLOCK

    d_write = evaluator.evaluate(_ctx(action_type="write"), [child], policy_provider=pmap.get)
    assert d_write.action == EnforcementAction.REQUIRE_HITL

    d_read = evaluator.evaluate(_ctx(action_type="read"), [child], policy_provider=pmap.get)
    assert d_read.action == EnforcementAction.ALLOW


def test_inheritance_cycle_is_safe():
    a = _policy("a", inherits="b", rules_yaml="    []\n")
    b = _policy("b", inherits="a", rules_yaml="    []\n")
    pmap = {"a": a, "b": b}
    # Must not infinite-loop.
    decision = PolicyEvaluator().evaluate(_ctx(), [a], policy_provider=pmap.get)
    assert decision.action == EnforcementAction.ALLOW
