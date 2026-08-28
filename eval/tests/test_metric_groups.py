from core.metric_groups import METRIC_GROUPS, metrics_for_parts


def test_memory_is_an_independent_group() -> None:
    assert METRIC_GROUPS["memory"] == ("memory_retention",)
    assert metrics_for_parts(["memory"]) == ("memory_retention",)


def test_defaults_prefer_deterministic_metrics() -> None:
    llm_metrics = {"plan_grade", "correctness", "hallucination", "failure_transparency"}
    all_metrics = set(metrics_for_parts(["all"]))
    assert len(all_metrics & llm_metrics) == 4
    assert {"secret_exposure", "authorization_boundary", "prompt_injection_signals"} <= all_metrics
