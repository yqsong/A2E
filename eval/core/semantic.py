"""Deterministic semantic matching with explicit uncertainty boundaries.

The matcher deliberately handles only high-confidence lexical and configured
alias equivalence.  Callers can route ambiguous matches to an LLM while
keeping exact, reproducible decisions in code.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping, Sequence


_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)

DEFAULT_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("rg", "ripgrep", "grep", "search text", "search files"),
    ("read file", "view file", "open file", "get file"),
    ("apply patch", "edit file", "update file", "modify file"),
    ("exec command", "run command", "shell", "terminal", "bash"),
    ("web search", "search web", "internet search"),
)


def normalize_semantic_text(value: Any) -> str:
    """Normalize identifiers and natural-language labels without translating them."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _CAMEL_BOUNDARY.sub(" ", text).replace("_", " ").replace("-", " ")
    return " ".join(_TOKEN_RE.findall(text.casefold()))


def _tokens(value: Any) -> set[str]:
    return set(normalize_semantic_text(value).split())


@dataclass(frozen=True)
class SemanticCandidate:
    name: str
    description: str = ""

    @classmethod
    def from_value(cls, value: Any) -> "SemanticCandidate":
        if isinstance(value, Mapping):
            return cls(
                name=str(value.get("name") or value.get("action") or value.get("tool") or ""),
                description=str(value.get("description") or value.get("intent") or value.get("purpose") or ""),
            )
        return cls(name=str(value or ""))

    @property
    def text(self) -> str:
        return " ".join(part for part in (self.name, self.description) if part)


@dataclass(frozen=True)
class SemanticMatch:
    expected: str
    observed: str | None
    score: float
    method: str
    decision: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected": self.expected,
            "observed": self.observed,
            "score": self.score,
            "method": self.method,
            "decision": self.decision,
        }


class SemanticMatcher:
    """Match labels using exact, configured alias, and conservative lexical evidence."""

    def __init__(
        self,
        *,
        alias_groups: Iterable[Iterable[str]] = DEFAULT_ALIAS_GROUPS,
        accept_threshold: float = 0.82,
        ambiguous_threshold: float = 0.38,
    ) -> None:
        if not 0 <= ambiguous_threshold < accept_threshold <= 1:
            raise ValueError("semantic thresholds must satisfy 0 <= ambiguous < accept <= 1")
        self.accept_threshold = accept_threshold
        self.ambiguous_threshold = ambiguous_threshold
        self.aliases: dict[str, frozenset[str]] = {}
        for group in alias_groups:
            normalized = frozenset(filter(None, (normalize_semantic_text(item) for item in group)))
            for item in normalized:
                self.aliases[item] = normalized

    def pair_score(self, expected: SemanticCandidate, observed: SemanticCandidate) -> tuple[float, str]:
        expected_name = normalize_semantic_text(expected.name)
        observed_name = normalize_semantic_text(observed.name)
        if expected_name and expected_name == observed_name:
            return 1.0, "exact_name"
        if observed_name in self.aliases.get(expected_name, ()):
            return 0.95, "configured_alias"

        expected_tokens = _tokens(expected.text)
        observed_tokens = _tokens(observed.text)
        if not expected_tokens or not observed_tokens:
            return 0.0, "no_evidence"
        overlap = len(expected_tokens & observed_tokens) / len(expected_tokens | observed_tokens)
        containment = len(expected_tokens & observed_tokens) / min(len(expected_tokens), len(observed_tokens))
        sequence = SequenceMatcher(
            None, normalize_semantic_text(expected.text), normalize_semantic_text(observed.text)
        ).ratio()
        # Fuzzy similarity is capped below automatic acceptance unless token
        # overlap independently supplies strong evidence.
        score = max(overlap, 0.9 * containment, min(0.79, sequence))
        method = "token_overlap" if max(overlap, 0.9 * containment) >= min(0.79, sequence) else "fuzzy"
        return score, method

    def best_match(self, expected: Any, observed: Sequence[Any]) -> SemanticMatch:
        target = SemanticCandidate.from_value(expected)
        candidates = [SemanticCandidate.from_value(item) for item in observed]
        if not candidates:
            return SemanticMatch(target.name, None, 0.0, "no_candidates", "reject")
        ranked = [(self.pair_score(target, item), item) for item in candidates]
        ((score, method), winner) = max(ranked, key=lambda item: item[0][0])
        decision = (
            "accept" if score >= self.accept_threshold
            else "ambiguous" if score >= self.ambiguous_threshold
            else "reject"
        )
        return SemanticMatch(target.name, winner.name, round(score, 6), method, decision)


def alias_groups_from_config(value: Any) -> tuple[tuple[str, ...], ...]:
    """Accept either ``[[a,b]]`` or ``{canonical: [aliases]}`` dataset contracts."""
    groups: list[tuple[str, ...]] = list(DEFAULT_ALIAS_GROUPS)
    if isinstance(value, Mapping):
        for canonical, aliases in value.items():
            items = aliases if isinstance(aliases, Sequence) and not isinstance(aliases, str) else [aliases]
            groups.append(tuple([str(canonical), *(str(item) for item in items if item)]))
    elif isinstance(value, Sequence) and not isinstance(value, str):
        for group in value:
            if isinstance(group, Sequence) and not isinstance(group, str):
                groups.append(tuple(str(item) for item in group if item))
    return tuple(groups)
