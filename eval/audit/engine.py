from __future__ import annotations

import json
import shlex
import subprocess
from datetime import UTC, datetime
from typing import Any, Mapping

from .ledger import AuditLedger
from .models import AuditDefinition, AuditResult
from .schema import validate_schema
from .validators import get_validator


class AuditEngine:
    def __init__(self, ledger: AuditLedger | None = None) -> None:
        self.ledger = ledger

    def execute(self, definition: AuditDefinition, payload: Mapping[str, Any], *, session_id: str | None = None,
                subject_id: str | None = None) -> AuditResult:
        started = datetime.now(UTC).isoformat()
        try:
            validate_schema(payload, definition.input_schema)
            if definition.executor == "validator":
                config = dict(definition.executor_config)
                config["_definition"] = definition
                result = get_validator(str(config["name"]))(payload, config)
            elif definition.executor in {"script", "cli"}:
                result = self._execute_process(definition, payload)
            else:
                result = AuditResult.unmeasured(definition, "LLM executor is disabled in deterministic AuditEngine")
            result.started_at = started
            result.ended_at = datetime.now(UTC).isoformat()
            validate_schema(result.to_dict(), definition.output_schema)
        except Exception as exc:
            result = AuditResult.error_result(definition, exc)
            result.started_at = started
            result.ended_at = datetime.now(UTC).isoformat()
        if self.ledger and session_id:
            self.ledger.add_result(session_id, definition, result, subject_id=subject_id)
        return result

    def _execute_process(self, definition: AuditDefinition, payload: Mapping[str, Any]) -> AuditResult:
        config = definition.executor_config
        raw_command = config.get("command")
        if not raw_command:
            raise ValueError("script/cli executor requires command")
        command = list(raw_command) if isinstance(raw_command, list) else shlex.split(str(raw_command))
        completed = subprocess.run(
            command, input=json.dumps(payload, ensure_ascii=False), text=True, capture_output=True,
            timeout=float(config.get("timeout_seconds", 30)), shell=False, check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"executor exited {completed.returncode}: {completed.stderr[:1000]}")
        value = json.loads(completed.stdout)
        return AuditResult(
            definition.name, definition.version, value["status"], value.get("score"),
            str(value.get("label") or value["status"]), str(value.get("explanation") or ""),
            evidence=dict(value.get("evidence") or {}), metadata={"command": command},
        )
