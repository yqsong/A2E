"""Metric groups used by the top-level evaluation runner."""

from __future__ import annotations

from collections.abc import Iterable

# Client-facing plan set: overall grade + four distinct failure modes.
# plan_correctness / reasoning_coherence remain in plan_eval.py (optional/manual).
PLAN_METRICS = ("plan_structure", "plan_grade")

SKILL_METRICS = ("response_compactness",)

# Memory is a real, independently measured group. Missing memory contracts produce
# an unmeasured result, never a synthetic pass.
MEMORY_METRICS = ("memory_retention",)

TOOL_METRICS = (
    "tool_hallucination",
    "tool_call_count",
    "self_correction_rate",
    "tool_recall",
)

CORRECT_METRICS = (
    "correctness",
    "task_succeeded",
)

EFFICIENCY_METRICS = (
    "total_token_usage",
    "cost",
    "turn_count",
    "elapsed_time",
)

SAFETY_METRICS = (
    "secret_exposure",
    "authorization_boundary",
    "prompt_injection_signals",
    "hallucination",
    "failure_transparency",
)

METRIC_GROUPS = {
    "plan": PLAN_METRICS,
    "skill": SKILL_METRICS,
    "memory": MEMORY_METRICS,
    "tool": TOOL_METRICS,
    "correct": CORRECT_METRICS,
    "efficiency": EFFICIENCY_METRICS,
    "safety": SAFETY_METRICS,
}

PART_ALIASES = {
    "all": "all",
    "plan": "plan",
    "plans": "plan",
    "skill": "skill",
    "skills": "skill",
    "memory": "memory",
    "mem": "memory",
    "tool": "tool",
    "tools": "tool",
    "correct": "correct",
    "correctness": "correct",
    "efficiency": "efficiency",
    "efficient": "efficiency",
    "safety": "safety",
    "safe": "safety",
    "safet": "safety",
}


def _dedupe(metrics: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for metric in metrics:
        if metric in seen:
            continue
        seen.add(metric)
        ordered.append(metric)
    return tuple(ordered)


def metrics_for_parts(parts: Iterable[str]) -> tuple[str, ...]:
    canonical_parts = [PART_ALIASES.get(part.strip().lower(), part.strip().lower()) for part in parts]
    if not canonical_parts or "all" in canonical_parts:
        return _dedupe(metric for group in METRIC_GROUPS.values() for metric in group)
    unknown = sorted({part for part in canonical_parts if part not in METRIC_GROUPS})
    if unknown:
        valid = ", ".join(["all", *METRIC_GROUPS])
        raise ValueError(f"Unsupported metric part(s): {unknown}. Supported parts: {valid}")
    return _dedupe(metric for part in canonical_parts for metric in METRIC_GROUPS[part])


ALL_METRICS = metrics_for_parts(("all",))
