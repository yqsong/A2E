"""Metric applicability decisions made before scoring.

An inapplicable metric is not a failed metric and should not be sent to an LLM
to manufacture a score.  These decisions are intentionally conservative and
carry machine-readable reasons for later audit/calibration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ApplicabilityDecision:
    applicable: bool | None
    reason: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def tool_metric_applicability(
    output: Mapping[str, Any],
    expected: Mapping[str, Any],
    input_: Mapping[str, Any],
) -> ApplicabilityDecision:
    expected_actions = _as_mapping(expected).get("expected_actions") or []
    observed = output.get("tool_calls_full") or output.get("tool_calls") or []
    available = input_.get("available_tools") or input_.get("tools") or []
    metadata = _as_mapping(input_.get("metadata"))
    kind = str(
        input_.get("dataset_kind")
        or metadata.get("dataset_kind")
        or metadata.get("kind")
        or ""
    ).casefold()
    if expected_actions:
        return ApplicabilityDecision(True, "expected_actions_present", 1.0)
    if observed:
        return ApplicabilityDecision(True, "tool_calls_observed", 0.95)
    if available:
        return ApplicabilityDecision(None, "tools_available_but_necessity_unknown", 0.5)
    if kind in {"qa", "multiple_choice", "numeric"}:
        return ApplicabilityDecision(False, f"dataset_kind={kind}", 1.0)
    # With no reference, tool menu, or observed tool call, recall has no
    # denominator. This is not evidence of failure or success.
    return ApplicabilityDecision(False, "no_tool_contract_or_trajectory", 0.9)


__all__ = ["ApplicabilityDecision", "tool_metric_applicability"]
