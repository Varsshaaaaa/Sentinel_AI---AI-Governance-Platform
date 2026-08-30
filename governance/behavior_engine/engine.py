"""Behavioral intelligence engine."""

from collections import Counter
from typing import Any

from shared.models.context import GovernanceContext
from shared.storage.base import Repository


class BehaviorEngine:
    """Profiles agent behavior and detects anomalies."""

    def __init__(self, repository: Repository) -> None:
        self._repo = repository
        self._baselines: dict[str, dict[str, Any]] = {}

    def record_action(self, context: GovernanceContext) -> None:
        baseline = self._baselines.setdefault(
            context.agent_id,
            {"tool_counts": Counter(), "tool_sequences": [], "param_sizes": [], "models": Counter()},
        )
        baseline["tool_counts"][context.tool_name] += 1
        calls = self._repo.get_session_tool_calls(context.session_id)
        if len(calls) >= 2:
            baseline["tool_sequences"].append(tuple(calls[-2:]))
        baseline["param_sizes"].append(len(str(context.tool_params)))

    def score_anomaly(self, context: GovernanceContext) -> dict[str, Any]:
        baseline = self._baselines.get(context.agent_id)
        if not baseline or not baseline["tool_counts"]:
            return {"anomaly_score": 0, "flags": [], "is_anomalous": False}

        flags: list[str] = []
        score = 0

        known_tools = set(baseline["tool_counts"].keys())
        if context.tool_name not in known_tools:
            flags.append(f"unknown_tool:{context.tool_name}")
            score += 40

        avg_size = sum(baseline["param_sizes"]) / max(len(baseline["param_sizes"]), 1)
        current_size = len(str(context.tool_params))
        if current_size > avg_size * 3:
            flags.append("param_size_spike")
            score += 25

        if context.action_type == "delete" and baseline["tool_counts"].get("db_delete", 0) == 0:
            flags.append("first_delete_operation")
            score += 30

        calls = self._repo.get_session_tool_calls(context.session_id)
        if len(calls) >= 2:
            pair = (calls[-2], calls[-1]) if len(calls) >= 2 else tuple(calls)
            common_sequences = Counter(baseline["tool_sequences"])
            if pair not in common_sequences and common_sequences:
                flags.append("unusual_tool_sequence")
                score += 20

        return {
            "anomaly_score": min(100, score),
            "flags": flags,
            "is_anomalous": score >= 50,
        }

    def set_baseline(self, agent_id: str, tool_counts: dict[str, int]) -> None:
        self._baselines[agent_id] = {
            "tool_counts": Counter(tool_counts),
            "tool_sequences": [],
            "param_sizes": [100],
            "models": Counter(),
        }
