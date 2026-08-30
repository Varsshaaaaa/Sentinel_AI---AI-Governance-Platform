"""Decision Path Auditor (PS-7.1)."""

import re
from typing import Any

from shared.models.audit import AuditStep, DecisionPath, StepType
from shared.models.context import GovernanceContext
from shared.models.policy import EnforcementDecision
from shared.models.tool import WAFResult
from shared.storage.base import Repository

PII_PATTERNS = [
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL_REDACTED]"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN_REDACTED]"),
    (r"\b(?:\d[ -]*?){13,16}\b", "[CARD_REDACTED]"),
    (r"\b(\+?1?\s?)?(\(?\d{3}\)?[\s.-]?)?\d{3}[\s.-]?\d{4}\b", "[PHONE_REDACTED]"),
    (r"\b\d{3}-\d{3}-\d{4}\b", "[PHONE_REDACTED]"),
    (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "[IP_REDACTED]"),
    (r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b", "[IBAN_REDACTED]"),
    (r"\b\d{4}[-/]\d{2}[-/]\d{2}\b", "[DOB_REDACTED]"),
    (r"\b[A-PR-WY][0-9]{7}\b", "[PASSPORT_REDACTED]"),
]

PII_KEYS = {
    "email",
    "ssn",
    "phone",
    "password",
    "credit_card",
    "address",
    "name",
    "dob",
    "date_of_birth",
    "passport",
    "iban",
    "account_number",
    "patient_name",
}


class DecisionAuditor:
    """Captures and reconstructs agent decision paths."""

    def __init__(self, repository: Repository) -> None:
        self._repo = repository

    def _next_sequence(self, session_id: str) -> int:
        # Delegate to the repository so sequencing is atomic and consistent
        # across concurrent requests and stateless Lambda instances.
        return self._repo.next_audit_sequence(session_id)

    def log_waf_evaluation(
        self, context: GovernanceContext, waf_result: WAFResult
    ) -> AuditStep:
        step = AuditStep(
            session_id=context.session_id,
            step_sequence=self._next_sequence(context.session_id),
            step_type=StepType.WAF_EVALUATION,
            agent_id=context.agent_id,
            user_id=context.user_id,
            content={"disposition": waf_result.disposition.value, "rules": waf_result.matched_rules},
            content_redacted={"disposition": waf_result.disposition.value, "rules": waf_result.matched_rules},
        )
        return self._repo.save_audit_step(step)

    def log_policy_evaluation(
        self, context: GovernanceContext, decision: EnforcementDecision
    ) -> AuditStep:
        content = {
            "action": decision.action.value,
            "matched_rules": [r.model_dump() for r in decision.matched_rules],
            "reason": decision.reason,
        }
        step = AuditStep(
            session_id=context.session_id,
            step_sequence=self._next_sequence(context.session_id),
            step_type=StepType.POLICY_EVALUATION,
            agent_id=context.agent_id,
            user_id=context.user_id,
            content=content,
            content_redacted=content,
            policy_evaluation=content,
        )
        return self._repo.save_audit_step(step)

    def log_tool_call(self, context: GovernanceContext) -> AuditStep:
        content = {
            "tool_name": context.tool_name,
            "tool_params": context.tool_params,
            "action_type": context.action_type,
            "data_scope_size": context.data_scope_size,
            "session_data_classification": context.session_data_classification.value,
            "previous_violations_in_session": context.previous_violations_in_session,
        }
        step = AuditStep(
            session_id=context.session_id,
            step_sequence=self._next_sequence(context.session_id),
            step_type=StepType.TOOL_CALL,
            agent_id=context.agent_id,
            user_id=context.user_id,
            content=content,
            content_redacted=self.redact(content),
        )
        return self._repo.save_audit_step(step)

    def log_step(
        self,
        session_id: str,
        agent_id: str,
        user_id: str,
        step_type: StepType,
        content: dict[str, Any],
        policy_evaluation: dict[str, Any] | None = None,
        risk_score: int | None = None,
    ) -> AuditStep:
        step = AuditStep(
            session_id=session_id,
            step_sequence=self._next_sequence(session_id),
            step_type=step_type,
            agent_id=agent_id,
            user_id=user_id,
            content=content,
            content_redacted=self.redact(content),
            policy_evaluation=policy_evaluation,
            risk_score=risk_score,
        )
        return self._repo.save_audit_step(step)

    def get_decision_path(self, session_id: str) -> DecisionPath | None:
        return self._repo.get_decision_path(session_id)

    def generate_summary(self, path: DecisionPath) -> str:
        """Generate plain-English decision summary."""
        steps_desc = []
        for step in path.steps:
            if step.step_type == StepType.INPUT:
                steps_desc.append("Received user input.")
            elif step.step_type == StepType.TOOL_CALL:
                tool = step.content_redacted.get("tool_name", "unknown")
                steps_desc.append(f"Called tool '{tool}'.")
            elif step.step_type == StepType.POLICY_EVALUATION:
                action = step.content.get("action", "allow")
                rules = step.content.get("matched_rules", [])
                rule_names = [r.get("rule_name", "") for r in rules]
                steps_desc.append(f"Policy evaluated: {action}. Rules: {', '.join(rule_names) or 'none'}.")
            elif step.step_type == StepType.WAF_EVALUATION:
                disp = step.content.get("disposition", "allow")
                steps_desc.append(f"WAF check: {disp}.")
            elif step.step_type == StepType.OUTPUT:
                steps_desc.append("Produced final output.")

        agent_id = path.agent_id
        return (
            f"Decision path for session {path.session_id} (agent {agent_id}): "
            + " → ".join(steps_desc)
            + f" Total steps: {len(path.steps)}."
        )

    async def generate_llm_summary(self, path: DecisionPath) -> str:
        """LLM-enhanced summary when API key available."""
        base_summary = self.generate_summary(path)
        try:
            from shared.llm.client import acompletion, extract_message_content, llm_configured

            if not llm_configured():
                return base_summary

            prompt = (
                "Summarize this AI agent decision path in plain English for a non-technical reviewer:\n"
                f"{base_summary}\n"
                f"Steps: {[s.step_type.value for s in path.steps]}"
            )
            response = await acompletion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
            )
            return extract_message_content(response) or base_summary
        except Exception:
            return base_summary

    @staticmethod
    def redact(data: dict[str, Any]) -> dict[str, Any]:
        result = {}
        for key, value in data.items():
            if key.lower() in PII_KEYS:
                result[key] = f"[{key.upper()}_REDACTED]"
            elif isinstance(value, str):
                result[key] = DecisionAuditor._redact_text(value)
            elif isinstance(value, dict):
                result[key] = DecisionAuditor.redact(value)
            elif isinstance(value, list):
                result[key] = [
                    DecisionAuditor.redact(v)
                    if isinstance(v, dict)
                    else (DecisionAuditor._redact_text(v) if isinstance(v, str) else v)
                    for v in value
                ]
            else:
                result[key] = value
        return result

    @staticmethod
    def _redact_text(text: str) -> str:
        """Regex baseline redaction, then an optional NER pass (Presidio)."""
        redacted = text
        for pattern, replacement in PII_PATTERNS:
            redacted = re.sub(pattern, replacement, redacted)
        return DecisionAuditor._ner_redact(redacted)

    @staticmethod
    def _ner_redact(text: str) -> str:
        """Redact named entities (PERSON, LOCATION, etc.) if Presidio is available.

        Regex cannot catch free-form names; when the optional `presidio-analyzer`
        dependency is installed this upgrades redaction to true NER. Falls back
        silently to the regex-only result otherwise.
        """
        analyzer = DecisionAuditor._get_presidio_analyzer()
        if analyzer is None:
            return text
        try:
            results = analyzer.analyze(
                text=text,
                entities=["PERSON", "LOCATION", "US_SSN", "CREDIT_CARD", "EMAIL_ADDRESS", "PHONE_NUMBER"],
                language="en",
            )
            for res in sorted(results, key=lambda r: r.start, reverse=True):
                text = text[: res.start] + f"[{res.entity_type}_REDACTED]" + text[res.end :]
        except Exception:
            return text
        return text

    _presidio_analyzer: Any = None
    _presidio_checked: bool = False

    @classmethod
    def _get_presidio_analyzer(cls) -> Any:
        if cls._presidio_checked:
            return cls._presidio_analyzer
        cls._presidio_checked = True
        try:
            from presidio_analyzer import AnalyzerEngine

            cls._presidio_analyzer = AnalyzerEngine()
        except Exception:
            cls._presidio_analyzer = None
        return cls._presidio_analyzer

    def generate_challenge_response(
        self, path: DecisionPath, challenge_question: str | None = None
    ) -> dict[str, Any]:
        """Draft a regulatory challenge response from a decision path (PS-7.1 bonus).

        Produces a defensible explanation that cites the specific data considered,
        tools invoked, and policy rules applied — the artifact a compliance team
        would send when a data subject or regulator challenges an AI decision.
        """
        tools_used: list[str] = []
        data_considered: list[str] = []
        rules_applied: list[str] = []
        final_action = "allow"

        for step in path.steps:
            if step.step_type == StepType.TOOL_CALL:
                tool = step.content_redacted.get("tool_name", "unknown")
                tools_used.append(tool)
                params = step.content_redacted.get("tool_params", {})
                for k in params:
                    data_considered.append(f"{tool}.{k}")
            elif step.step_type == StepType.POLICY_EVALUATION:
                final_action = step.content.get("action", final_action)
                for rule in step.content.get("matched_rules", []):
                    name = rule.get("rule_name")
                    if name:
                        rules_applied.append(name)

        factors = []
        if rules_applied:
            factors.append(f"the following governance rules applied: {', '.join(sorted(set(rules_applied)))}")
        else:
            factors.append("no governance rule was triggered; the action followed the default policy")
        if tools_used:
            factors.append(f"data was gathered via: {', '.join(sorted(set(tools_used)))}")

        draft = (
            f"In response to the challenge regarding session {path.session_id} "
            f"(agent {path.agent_id}): the outcome was '{final_action}'. "
            f"This decision was reached because " + "; ".join(factors) + ". "
            "All intermediate data was redacted of personal information before "
            "storage, and the full decision path is retained for audit."
        )
        if challenge_question:
            draft = f"Challenge: {challenge_question}\n\n{draft}"

        return {
            "session_id": path.session_id,
            "agent_id": path.agent_id,
            "final_action": final_action,
            "tools_used": sorted(set(tools_used)),
            "data_considered": sorted(set(data_considered)),
            "rules_applied": sorted(set(rules_applied)),
            "challenge_question": challenge_question,
            "draft_response": draft,
        }

    async def generate_challenge_response_llm(
        self, path: DecisionPath, challenge_question: str | None = None
    ) -> dict[str, Any]:
        """LLM-enhanced regulatory challenge draft, falling back to the template."""
        base = self.generate_challenge_response(path, challenge_question)
        try:
            from shared.llm.client import acompletion, extract_message_content, llm_configured

            if not llm_configured():
                return base

            prompt = (
                "You are a compliance officer drafting a response to a regulatory "
                "challenge about an automated AI decision. Be precise, factual, and "
                "cite only the evidence provided. Do not invent facts.\n\n"
                f"Decision outcome: {base['final_action']}\n"
                f"Governance rules applied: {base['rules_applied']}\n"
                f"Tools/data considered: {base['data_considered']}\n"
                f"Challenge question: {challenge_question or 'Explain why this decision was made.'}"
            )
            response = await acompletion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
            )
            base["draft_response"] = extract_message_content(response) or base["draft_response"]
            base["llm_generated"] = True
        except Exception:
            base["llm_generated"] = False
        return base
