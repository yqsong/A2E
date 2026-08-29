"""Dataset-agnostic case abstraction and conservative reasoning control.

This module never reads benchmark ground truth such as ``expected_actions``.
It derives a small control-plane model from the user instruction and the tools
visible to the agent, then uses observable trajectory evidence to decide
whether a proposed termination deserves one bounded re-planning pass.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from ageneval.task.core.binding import AgentBinding
from ageneval.task.core.dataset import TaskInput


_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_MUTATION_TERMS = frozenset({
    "add", "approve", "book", "buy", "cancel", "change", "create", "delete",
    "exchange", "modify", "move", "purchase", "refund", "remove",
    "replace", "reserve", "send", "set", "submit", "transfer", "update", "write",
})
_READ_TERMS = frozenset({
    "check", "find", "get", "inspect", "list", "lookup", "open", "read", "retrieve",
    "search", "show", "view",
})
_CONSTRAINT_TERMS = frozenset({
    "after", "before", "except", "if", "must", "only", "unless", "until", "without",
})
_RISK_TERMS = frozenset({"cancel", "delete", "purchase", "refund", "remove", "transfer"})
_INFORMATIONAL_REQUEST_RE = re.compile(
    r"\b(?:how\s+(?:do|can|should)\s+i|tell\s+me\s+how|explain\s+how|what\s+(?:is|are|happens))\b",
    re.IGNORECASE,
)


def _tokens(value: Any) -> set[str]:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(value or ""))
    return {token.casefold() for token in _TOKEN_RE.findall(text.replace("_", " ").replace("-", " "))}


def _tool_record(schema: Mapping[str, Any]) -> dict[str, str]:
    function = schema.get("function") if isinstance(schema.get("function"), Mapping) else schema
    return {
        "name": str(function.get("name") or schema.get("name") or ""),
        "description": str(function.get("description") or schema.get("description") or ""),
    }


def is_mutation_tool(value: Any) -> bool:
    if isinstance(value, Mapping):
        text = " ".join(str(value.get(key) or "") for key in ("name", "description"))
    else:
        text = str(value or "")
    tokens = _tokens(text)
    return bool(tokens & _MUTATION_TERMS) and not (
        tokens & _READ_TERMS and not tokens & (_MUTATION_TERMS - {"set"})
    )


def _result_failed(value: Any) -> bool:
    if isinstance(value, Mapping) and value.get("error"):
        return True
    text = json.dumps(value, ensure_ascii=False, default=str).casefold()
    return any(marker in text for marker in ("exception", "traceback", "timed out", '"error"'))


@dataclass(frozen=True)
class CaseModel:
    archetype: str
    requires_side_effect: bool
    mutation_intents: tuple[str, ...]
    candidate_mutation_tools: tuple[str, ...]
    required_effect_count: int
    constraint_count: int
    entity_count: int
    tool_ambiguity: float
    risk: float
    complexity: float
    reasoning_mode: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProgressAssessment:
    termination_ready: bool
    reason: str
    diagnostic_sufficiency: float
    missing_obligations: tuple[str, ...] = ()
    feedback: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_case_model(task: TaskInput, binding: AgentBinding) -> CaseModel:
    instruction_tokens = _tokens(task.instruction)
    mutation_intents = tuple(sorted(instruction_tokens & _MUTATION_TERMS))
    tools = [_tool_record(schema) for schema in binding.tool_schemas]
    mutation_tools = tuple(sorted(tool["name"] for tool in tools if tool["name"] and is_mutation_tool(tool)))
    informational_framing = bool(_INFORMATIONAL_REQUEST_RE.search(task.instruction))
    requires_side_effect = bool(mutation_intents and mutation_tools and not informational_framing)
    constraints = len(instruction_tokens & _CONSTRAINT_TERMS)
    entity_count = len(set(re.findall(r"#[A-Za-z0-9_-]+", task.instruction)))
    if not entity_count:
        entity_count = min(4, len(re.findall(r"\b(?:order|item|account|address|file|record)s?\b", task.instruction, re.I)))
    tool_ambiguity = min(1.0, max(0, len(mutation_tools) - 1) / 8)
    risk = min(1.0, 0.25 * len(instruction_tokens & _RISK_TERMS) + (0.2 if requires_side_effect else 0.0))
    complexity = min(
        1.0,
        0.12 * len(mutation_intents)
        + 0.10 * constraints
        + 0.08 * entity_count
        + 0.25 * tool_ambiguity
        + 0.25 * risk
        + (0.10 if len(task.instruction) > 500 else 0.0),
    )
    reasoning_mode = "critical" if risk >= 0.65 else "deep" if complexity >= 0.60 else "standard" if complexity >= 0.25 else "fast"
    return CaseModel(
        archetype="state_mutation" if requires_side_effect else "information_or_qa",
        requires_side_effect=requires_side_effect,
        mutation_intents=mutation_intents,
        candidate_mutation_tools=mutation_tools,
        required_effect_count=max(1, entity_count) if requires_side_effect else 0,
        constraint_count=constraints,
        entity_count=entity_count,
        tool_ambiguity=round(tool_ambiguity, 4),
        risk=round(risk, 4),
        complexity=round(complexity, 4),
        reasoning_mode=reasoning_mode,
    )


def assess_progress(
    case: CaseModel | Mapping[str, Any],
    tool_calls: Sequence[Mapping[str, Any]],
    *,
    completion_checks: int = 0,
    turns: int = 0,
    max_turns: int = 8,
) -> ProgressAssessment:
    case_dict = case.to_dict() if isinstance(case, CaseModel) else dict(case)
    mutation_calls = [call for call in tool_calls if is_mutation_tool(call)]
    successful_mutations = [call for call in mutation_calls if not _result_failed(call.get("result"))]
    information_gathered = any(not is_mutation_tool(call) for call in tool_calls)
    attempted = bool(mutation_calls)
    verified = bool(successful_mutations)
    sufficiency = min(1.0, 0.2 + 0.2 * information_gathered + 0.3 * attempted + 0.3 * verified)

    # One bounded recovery pass prevents infinite loops and avoids overriding a
    # legitimate refusal after the agent has reconsidered an impossible action.
    can_replan = completion_checks < 1 and turns < max_turns
    if case_dict.get("requires_side_effect") and not mutation_calls and can_replan:
        candidates = tuple(str(x) for x in case_dict.get("candidate_mutation_tools") or ())
        return ProgressAssessment(
            termination_ready=False,
            reason="required_side_effect_not_attempted",
            diagnostic_sufficiency=round(sufficiency, 4),
            missing_obligations=tuple(str(x) for x in case_dict.get("mutation_intents") or ("state_change",)),
            feedback=(
                "You are about to finish, but the request appears to require a state-changing action and "
                "the trajectory contains only information gathering. Re-check the user's requested outcome, "
                f"the latest tool results, and these candidate action tools: {', '.join(candidates) or '(none)'}. "
                "Either perform the necessary action, or clearly establish from evidence why it is invalid, "
                "unsafe, unauthorized, or impossible before finishing."
            ),
        )
    required_effect_count = int(case_dict.get("required_effect_count") or 1)
    if (
        case_dict.get("requires_side_effect")
        and successful_mutations
        and len(successful_mutations) < required_effect_count
        and can_replan
    ):
        remaining = required_effect_count - len(successful_mutations)
        return ProgressAssessment(
            termination_ready=False,
            reason="side_effect_partially_completed",
            diagnostic_sufficiency=round(sufficiency, 4),
            missing_obligations=(f"{remaining}_additional_state_change(s)",),
            feedback=(
                f"The request appears to cover {required_effect_count} explicit entities, but only "
                f"{len(successful_mutations)} successful state-changing action(s) are recorded. "
                "Reconcile each requested entity against the tool results, complete the remaining "
                "actions when valid, and verify the final state before finishing."
            ),
        )
    if attempted and not successful_mutations and can_replan:
        return ProgressAssessment(
            termination_ready=False,
            reason="side_effect_attempt_failed",
            diagnostic_sufficiency=round(sufficiency, 4),
            feedback=(
                "The requested state-changing action was attempted but no successful result is recorded. "
                "Diagnose the tool error, correct arguments or prerequisites, try a materially different "
                "recovery when available, and verify the resulting state before finishing."
            ),
        )
    return ProgressAssessment(True, "obligations_satisfied_or_bounded", round(sufficiency, 4))


__all__ = [
    "CaseModel",
    "ProgressAssessment",
    "assess_progress",
    "build_case_model",
    "is_mutation_tool",
]
