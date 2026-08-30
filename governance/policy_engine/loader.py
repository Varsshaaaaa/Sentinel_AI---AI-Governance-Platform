"""Policy YAML loader and validator."""

import hashlib
from typing import Any

import yaml

from shared.models.policy import Policy, PolicyRule, PolicyVersion


class PolicyLoader:
    @staticmethod
    def parse_yaml(yaml_content: str) -> Policy:
        data = yaml.safe_load(yaml_content)
        if not data or "spec" not in data:
            raise ValueError("Invalid policy YAML: missing spec section")

        metadata = data.get("metadata", {})
        spec = data["spec"]
        rules = [PolicyRule(**rule) for rule in spec.get("rules", [])]

        return Policy(
            policy_id=metadata.get("name", "unnamed-policy"),
            name=metadata.get("name", "unnamed-policy"),
            description=metadata.get("description", ""),
            inherits=spec.get("inherits"),
            rules=rules,
        )

    @staticmethod
    def create_version(yaml_content: str, created_by: str = "system") -> PolicyVersion:
        content_hash = hashlib.sha256(yaml_content.encode()).hexdigest()
        policy = PolicyLoader.parse_yaml(yaml_content)
        return PolicyVersion(
            policy_id=policy.policy_id,
            version=content_hash[:8],
            yaml_content=yaml_content,
            content_hash=content_hash,
            created_by=created_by,
        )

    @staticmethod
    def merge_policies(base: Policy, child: Policy) -> Policy:
        """Policy inheritance: child overrides rules with same name."""
        merged_rules: dict[str, PolicyRule] = {r.name: r for r in base.rules}
        for rule in child.rules:
            merged_rules[rule.name] = rule
        sorted_rules = sorted(merged_rules.values(), key=lambda r: r.priority, reverse=True)
        return Policy(
            policy_id=child.policy_id,
            name=child.name,
            description=child.description,
            inherits=child.inherits,
            rules=sorted_rules,
        )

    @staticmethod
    def load_from_file(path: str) -> Policy:
        with open(path, encoding="utf-8") as f:
            return PolicyLoader.parse_yaml(f.read())
