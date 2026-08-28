from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Mapping

AuditStatus = Literal["pass", "fail", "unmeasured", "error"]
ExecutorKind = Literal["validator", "script", "cli", "llm"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return vars(value)
    return str(value)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


@dataclass(frozen=True)
class AuditDefinition:
    name: str
    version: str
    description: str
    executor: ExecutorKind
    executor_config: Mapping[str, Any]
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    tags: tuple[str, ...] = ()
    deprecated: bool = False

    @property
    def definition_id(self) -> str:
        return f"{self.name}@{self.version}"

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["tags"] = list(self.tags)
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AuditDefinition":
        required = {"name", "version", "description", "executor", "executor_config", "input_schema", "output_schema"}
        missing = sorted(required - set(value))
        if missing:
            raise ValueError(f"audit definition missing fields: {missing}")
        executor = str(value["executor"])
        if executor not in {"validator", "script", "cli", "llm"}:
            raise ValueError(f"unsupported executor: {executor}")
        return cls(
            name=str(value["name"]), version=str(value["version"]),
            description=str(value["description"]), executor=executor,  # type: ignore[arg-type]
            executor_config=dict(value["executor_config"]), input_schema=dict(value["input_schema"]),
            output_schema=dict(value["output_schema"]), tags=tuple(value.get("tags") or ()),
            deprecated=bool(value.get("deprecated", False)),
        )


@dataclass
class AuditResult:
    audit_name: str
    audit_version: str
    status: AuditStatus
    score: float | None
    label: str
    explanation: str
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    started_at: str = field(default_factory=utc_now)
    ended_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def unmeasured(cls, definition: AuditDefinition, explanation: str, **metadata: Any) -> "AuditResult":
        return cls(definition.name, definition.version, "unmeasured", None, "unmeasured", explanation, metadata=metadata)

    @classmethod
    def error_result(cls, definition: AuditDefinition, error: BaseException) -> "AuditResult":
        return cls(
            definition.name, definition.version, "error", None, "error",
            f"{type(error).__name__}: {error}"[:1000], error=f"{type(error).__name__}: {error}"[:2000],
        )
