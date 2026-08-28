from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import AuditEngine
from .ledger import AuditLedger
from .registry import AuditRegistry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Versioned deterministic A2E audit runner")
    parser.add_argument("--db", default=".a2e/audit.db")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    run = sub.add_parser("run")
    run.add_argument("--definition", required=True)
    run.add_argument("--input", required=True, help="JSON file, or - for stdin")
    run.add_argument("--subject-id")
    listing = sub.add_parser("list-runs")
    listing.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    ledger = AuditLedger(args.db)
    if args.command == "init":
        print(ledger.path)
        return 0
    if args.command == "list-runs":
        print(json.dumps(ledger.list_sessions(args.limit), ensure_ascii=False, indent=2))
        return 0
    registry = AuditRegistry()
    definition = registry.load_file(args.definition)
    import sys
    text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
    payload = json.loads(text)
    session_id = ledger.start_session(source="audit-cli", config={"definition": definition.definition_id})
    result = AuditEngine(ledger).execute(definition, payload, session_id=session_id, subject_id=args.subject_id)
    ledger.finish_session(session_id, status="completed" if result.status != "error" else "failed", error=result.error)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status in {"pass", "unmeasured"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
