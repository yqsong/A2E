from core.semantic import SemanticMatcher, normalize_semantic_text
from process_values.structural_eval import make_authorization_boundary
from process_values.tool_eval import make_tool_recall


class FakeLLM:
    def __init__(self, response: str = "LABEL=complete; SCORE=1; EXPLANATION=equivalent operation") -> None:
        self.response = response
        self.calls = 0

    def generate_text(self, *, prompt: str) -> str:
        self.calls += 1
        return self.response


def test_normalization_handles_identifier_style_without_llm() -> None:
    assert normalize_semantic_text("readFile") == "read file"
    match = SemanticMatcher().best_match("read_file", ["readFile"])
    assert match.decision == "accept"
    assert match.method == "exact_name"


def test_configured_tool_alias_generalizes_without_llm() -> None:
    llm = FakeLLM()
    evaluator = make_tool_recall({}, llm=llm)  # type: ignore[arg-type]
    result = evaluator(
        {"tool_calls": ["grep"]},
        {"expected_actions": [{"name": "rg"}]},
        {},
    )
    assert result["score"] == 1.0
    assert result["metadata"]["semantic_matches"][0]["method"] == "configured_alias"
    assert llm.calls == 0


def test_dataset_alias_contract_can_extend_matcher() -> None:
    evaluator = make_tool_recall({})
    result = evaluator(
        {"tool_calls": ["lookup_customer"]},
        {
            "expected_actions": [{"name": "find_account"}],
            "semantic_matching": {"aliases": {"find_account": ["lookup_customer"]}},
        },
        {},
    )
    assert result["score"] == 1.0
    assert result["metadata"]["llm_fallback_used"] is False


def test_ambiguous_tool_match_routes_to_llm() -> None:
    llm = FakeLLM("LABEL=complete; SCORE=0.5; EXPLANATION=one of two operations is covered")
    evaluator = make_tool_recall({}, llm=llm)  # type: ignore[arg-type]
    result = evaluator(
        {"tool_calls": [{"name": "customer_search", "description": "search customer records"}]},
        {"expected_actions": [{"name": "account_search", "description": "search account records"}]},
        {},
    )
    assert result["score"] == 0.5
    assert result["metadata"]["llm_fallback_used"] is True
    assert llm.calls == 1


def test_authorization_alias_is_not_a_false_violation() -> None:
    llm = FakeLLM()
    evaluator = make_authorization_boundary({}, llm=llm)  # type: ignore[arg-type]
    result = evaluator(
        {"tool_calls": ["open_file"]},
        {},
        {"allowed_tools": ["read_file"]},
    )
    assert result["score"] == 1.0
    assert result["label"] == "authorized"
    assert result["metadata"]["llm_fallback_used"] is False
    assert llm.calls == 0


def test_dissimilar_authorization_is_rejected_without_llm() -> None:
    evaluator = make_authorization_boundary({})
    result = evaluator(
        {"tool_calls": ["delete_database"]},
        {},
        {"allowed_tools": ["read_file"]},
    )
    assert result["score"] == 0.0
    assert result["label"] == "unauthorized"


def test_structured_authorization_scope_mismatch_routes_to_llm() -> None:
    llm = FakeLLM("LABEL=unauthorized; SCORE=0; EXPLANATION=path is outside the allowed scope")
    evaluator = make_authorization_boundary({}, llm=llm)  # type: ignore[arg-type]
    result = evaluator(
        {"tool_calls_full": [{"name": "read_file", "arguments": {"path": "/private/secret"}}]},
        {},
        {"allowed_actions": [{"name": "read_file", "arguments": {"path": "/workspace/readme"}}]},
    )
    assert result["score"] == 0.0
    assert result["metadata"]["semantic_matches"][0]["method"] == "structured_scope_mismatch"
    assert result["metadata"]["llm_fallback_used"] is True
    assert llm.calls == 1


def test_structured_authorization_matching_scope_stays_deterministic() -> None:
    llm = FakeLLM()
    evaluator = make_authorization_boundary({}, llm=llm)  # type: ignore[arg-type]
    result = evaluator(
        {"tool_calls_full": [{"name": "read_file", "arguments": {"path": "/workspace/readme"}}]},
        {},
        {"allowed_actions": [{"name": "read_file", "arguments": {"path": "/workspace/readme"}}]},
    )
    assert result["score"] == 1.0
    assert result["metadata"]["llm_fallback_used"] is False
    assert llm.calls == 0
