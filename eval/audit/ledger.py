from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Mapping

from .models import AuditDefinition, AuditResult, canonical_json, utc_now


DEFAULT_LEDGER = Path(os.getenv("A2E_AUDIT_DB_PATH", ".a2e/audit.db"))


class AuditLedger:
    """Append-oriented local SQLite ledger for audit provenance.

    The server's a2e.db remains the source of truth for spans and experiments.
    This ledger records schema versions, executor provenance, evidence snapshots
    and audit outputs so evaluations are reproducible and independently exportable.
    """

    def __init__(self, path: str | Path = DEFAULT_LEDGER) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit_definitions(
              definition_id TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL,
              digest TEXT NOT NULL, executor TEXT NOT NULL, definition_json TEXT NOT NULL,
              registered_at TEXT NOT NULL, UNIQUE(name, version)
            );
            CREATE TABLE IF NOT EXISTS audit_sessions(
              session_id TEXT PRIMARY KEY, experiment_id TEXT, project_name TEXT,
              source TEXT NOT NULL, status TEXT NOT NULL, config_json TEXT NOT NULL,
              started_at TEXT NOT NULL, ended_at TEXT, error TEXT
            );
            CREATE TABLE IF NOT EXISTS audit_results(
              result_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
              definition_id TEXT NOT NULL, subject_id TEXT, status TEXT NOT NULL,
              score REAL, label TEXT NOT NULL, explanation TEXT NOT NULL,
              evidence_json TEXT NOT NULL, metadata_json TEXT NOT NULL, error TEXT,
              started_at TEXT NOT NULL, ended_at TEXT NOT NULL,
              FOREIGN KEY(session_id) REFERENCES audit_sessions(session_id),
              FOREIGN KEY(definition_id) REFERENCES audit_definitions(definition_id)
            );
            CREATE INDEX IF NOT EXISTS ix_audit_results_session ON audit_results(session_id);
            CREATE INDEX IF NOT EXISTS ix_audit_results_subject ON audit_results(subject_id);
            CREATE TABLE IF NOT EXISTS audit_events(
              event_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
              event_type TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
              FOREIGN KEY(session_id) REFERENCES audit_sessions(session_id)
            );
            INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(1, CURRENT_TIMESTAMP);
            """)

    def register_definition(self, definition: AuditDefinition) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO audit_definitions VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(definition_id) DO UPDATE SET digest=excluded.digest,
                executor=excluded.executor, definition_json=excluded.definition_json""",
                (definition.definition_id, definition.name, definition.version, definition.digest,
                 definition.executor, canonical_json(definition.to_dict()), utc_now()),
            )

    def start_session(self, *, experiment_id: str | None = None, project_name: str | None = None,
                      source: str = "a2e-eval", config: Mapping[str, Any] | None = None) -> str:
        session_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO audit_sessions VALUES(?,?,?,?,?,?,?,?,?)", (
                session_id, experiment_id, project_name, source, "running", canonical_json(config or {}),
                utc_now(), None, None,
            ))
        return session_id

    def finish_session(self, session_id: str, *, status: str = "completed", error: str | None = None) -> None:
        with self.connect() as db:
            db.execute("UPDATE audit_sessions SET status=?, ended_at=?, error=? WHERE session_id=?",
                       (status, utc_now(), error, session_id))

    def add_event(self, session_id: str, event_type: str, payload: Mapping[str, Any]) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO audit_events(session_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",
                       (session_id, event_type, canonical_json(payload), utc_now()))

    def add_result(self, session_id: str, definition: AuditDefinition, result: AuditResult,
                   *, subject_id: str | None = None) -> str:
        self.register_definition(definition)
        result_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("""INSERT INTO audit_results VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                result_id, session_id, definition.definition_id, subject_id, result.status, result.score,
                result.label, result.explanation, canonical_json(result.evidence), canonical_json(result.metadata),
                result.error, result.started_at, result.ended_at,
            ))
        return result_id

    def import_evaluation_snapshot(self, session_id: str, evaluated: Mapping[str, Any]) -> None:
        """Persist both a lossless snapshot and normalized per-run audit results."""
        self.add_event(session_id, "evaluation_snapshot", {"evaluation": evaluated})
        output_schema = {
            "type": "object",
            "required": ["audit_name", "audit_version", "status", "score", "label", "explanation",
                         "evidence", "metadata", "error", "started_at", "ended_at"],
        }
        for item in evaluated.get("evaluation_runs", []):
            def read(name: str, default: Any = None) -> Any:
                return item.get(name, default) if isinstance(item, Mapping) else getattr(item, name, default)
            name = str(read("name") or "unnamed_evaluator")
            kind = str(read("annotator_kind") or "CODE").lower()
            executor = "llm" if kind == "llm" else "validator"
            definition = AuditDefinition(
                name=name, version="legacy-1", description="Imported A2E experiment evaluator",
                executor=executor, executor_config={"source": "evaluate_experiment", "annotator_kind": kind},
                input_schema={"type": "object"}, output_schema=output_schema, tags=("imported",),
            )
            raw_result = read("result") or {}
            result_map = dict(raw_result) if isinstance(raw_result, Mapping) else {}
            error = read("error")
            score = result_map.get("score")
            status = "error" if error else ("unmeasured" if score is None and not result_map.get("label") else "pass")
            result = AuditResult(
                name, definition.version, status, float(score) if score is not None else None,
                str(result_map.get("label") or status), str(result_map.get("explanation") or error or ""),
                evidence={"trace_id": read("trace_id")}, metadata={"annotator_kind": kind, **dict(read("metadata") or {})},
                error=str(error) if error else None,
                started_at=str(read("start_time") or utc_now()), ended_at=str(read("end_time") or utc_now()),
            )
            self.add_result(session_id, definition, result, subject_id=str(read("experiment_run_id") or "") or None)

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM audit_sessions ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
