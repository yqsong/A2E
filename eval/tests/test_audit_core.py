from __future__ import annotations

import json
from pathlib import Path

from audit.engine import AuditEngine
from audit.ledger import AuditLedger
from audit.models import AuditDefinition
from audit.registry import AuditRegistry


RESULT_SCHEMA = {
    "type": "object",
    "required": ["audit_name", "audit_version", "status", "score", "label", "explanation", "evidence", "metadata", "error", "started_at", "ended_at"],
}


def definition(name: str, validator: str) -> AuditDefinition:
    return AuditDefinition(name, "1.0.0", name, "validator", {"name": validator},
                           {"type": "object"}, RESULT_SCHEMA)


def test_ledger_records_versioned_result(tmp_path: Path) -> None:
    ledger = AuditLedger(tmp_path / "audit.db")
    session = ledger.start_session(experiment_id="exp-1")
    item = definition("secrets", "secret_exposure")
    result = AuditEngine(ledger).execute(item, {"text": "safe"}, session_id=session, subject_id="run-1")
    ledger.finish_session(session)
    assert result.status == "pass"
    assert ledger.list_sessions()[0]["experiment_id"] == "exp-1"
    with ledger.connect() as db:
        row = db.execute("SELECT status, score FROM audit_results").fetchone()
    assert dict(row) == {"status": "pass", "score": 1.0}


def test_missing_measurement_is_not_a_pass() -> None:
    item = definition("memory", "memory_retention")
    result = AuditEngine().execute(item, {"required_facts": {}, "final_state": {}})
    assert result.status == "unmeasured"
    assert result.score is None


def test_cli_executor_uses_json_contract(tmp_path: Path) -> None:
    script = tmp_path / "validator.py"
    script.write_text(
        "import json,sys; json.load(sys.stdin); print(json.dumps({'status':'pass','score':1.0,'label':'ok','explanation':'ok'}))",
        encoding="utf-8",
    )
    item = AuditDefinition("external", "1.0.0", "external", "cli",
                           {"command": [__import__('sys').executable, str(script)]}, {"type": "object"}, RESULT_SCHEMA)
    assert AuditEngine().execute(item, {}).status == "pass"


def test_registry_loads_versioned_definition() -> None:
    path = Path(__file__).parents[1] / "audit" / "schemas" / "secret-exposure-v1.audit.json"
    registry = AuditRegistry()
    loaded = registry.load_file(path)
    assert loaded.definition_id == "secret_exposure@1.0.0"


def test_imported_server_results_are_normalized(tmp_path: Path) -> None:
    ledger = AuditLedger(tmp_path / "audit.db")
    session = ledger.start_session(experiment_id="exp-2")
    ledger.import_evaluation_snapshot(session, {"evaluation_runs": [{
        "name": "tool_call_count", "annotator_kind": "CODE", "experiment_run_id": "run-2",
        "result": {"score": 3.0, "label": "medium", "explanation": "3 calls"},
        "start_time": "2026-01-01T00:00:00Z", "end_time": "2026-01-01T00:00:01Z",
    }]})
    with ledger.connect() as db:
        row = db.execute("SELECT subject_id, label, score FROM audit_results").fetchone()
    assert dict(row) == {"subject_id": "run-2", "label": "medium", "score": 3.0}
