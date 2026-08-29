from ageneval.task.core import AgentBinding, TaskInput
from ageneval.task.core.meta_reasoning import assess_progress, build_case_model


def _binding() -> AgentBinding:
    tools = [
        {"type": "function", "function": {"name": "get_order_details", "description": "Read order status"}},
        {"type": "function", "function": {"name": "cancel_pending_order", "description": "Cancel a pending order"}},
        {"type": "function", "function": {"name": "exchange_delivered_order_items", "description": "Exchange delivered items"}},
    ]
    return AgentBinding("test-retail", tools, lambda name, arguments, state: {}, lambda schemas: "test")


def test_case_model_detects_state_mutation_without_using_gold_actions() -> None:
    task = TaskInput("1", "Please cancel order #W123 after checking that it is pending.")
    case = build_case_model(task, _binding())
    assert case.requires_side_effect is True
    assert case.archetype == "state_mutation"
    assert "cancel_pending_order" in case.candidate_mutation_tools
    assert case.reasoning_mode in {"standard", "deep", "critical"}


def test_gold_action_does_not_leak_into_case_abstraction() -> None:
    task = TaskInput(
        "2",
        "What is the status of order #W123?",
        expected_actions=({"name": "cancel_pending_order"},),
    )
    case = build_case_model(task, _binding())
    assert case.requires_side_effect is False
    assert case.archetype == "information_or_qa"


def test_how_to_question_is_not_treated_as_mutation_request() -> None:
    case = build_case_model(TaskInput("howto", "Tell me how to cancel an order."), _binding())
    assert case.requires_side_effect is False


def test_query_only_trajectory_is_forced_to_replan_once() -> None:
    case = build_case_model(TaskInput("3", "Cancel order #W123."), _binding())
    calls = [{"name": "get_order_details", "arguments": {"order_id": "W123"}, "result": {"status": "pending"}}]
    assessment = assess_progress(case, calls, completion_checks=0, turns=1, max_turns=8)
    assert assessment.termination_ready is False
    assert assessment.reason == "required_side_effect_not_attempted"
    assert "cancel_pending_order" in assessment.feedback


def test_successful_mutation_allows_termination() -> None:
    case = build_case_model(TaskInput("4", "Cancel order #W123."), _binding())
    calls = [{"name": "cancel_pending_order", "arguments": {"order_id": "W123"}, "result": {"status": "cancelled"}}]
    assessment = assess_progress(case, calls, completion_checks=0, turns=1, max_turns=8)
    assert assessment.termination_ready is True
    assert assessment.diagnostic_sufficiency == 0.8


def test_failed_mutation_gets_recovery_pass_but_not_infinite_loop() -> None:
    case = build_case_model(TaskInput("5", "Cancel order #W123."), _binding())
    calls = [{"name": "cancel_pending_order", "arguments": {}, "result": {"error": "missing order_id"}}]
    first = assess_progress(case, calls, completion_checks=0, turns=1, max_turns=8)
    second = assess_progress(case, calls, completion_checks=1, turns=1, max_turns=8)
    assert first.termination_ready is False
    assert first.reason == "side_effect_attempt_failed"
    assert second.termination_ready is True


def test_multiple_explicit_entities_require_multiple_effects() -> None:
    case = build_case_model(TaskInput("6", "Cancel orders #W123 and #W456."), _binding())
    calls = [{"name": "cancel_pending_order", "arguments": {"order_id": "W123"}, "result": {"status": "cancelled"}}]
    assessment = assess_progress(case, calls, completion_checks=0, turns=1, max_turns=8)
    assert case.required_effect_count == 2
    assert assessment.termination_ready is False
    assert assessment.reason == "side_effect_partially_completed"
