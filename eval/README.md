# Evaluation

A<sup>2</sup>E provides a unified evaluation pipeline for analyzing agent executions from
both process and outcome perspectives. After an experiment is completed,
collected trajectories can be evaluated across multiple dimensions of agent
behavior, including planning, tool usage, memory, correctness, efficiency, and
safety.

The evaluation workflow consists of two steps:

1. Start the A<sup>2</sup>E server to access stored experiment trajectories.
2. Run the evaluation pipeline on a selected experiment.

A<sup>2</sup>E supports:

- **Full evaluation**: run all available metrics for a comprehensive analysis.
- **Targeted evaluation**: evaluate specific aspects of agent behavior.

## Start A<sup>2</sup>E Server

Before running evaluations, start the server (same default endpoint as the root README):

```bash
# from repo root
bash scripts/start.sh                 # → http://localhost:6006
```

Or start the API only:

```bash
cd server
uv run a2e serve                     # → http://localhost:6006
```

The server exposes experiment data through:

```text
HTTP endpoint: http://localhost:6006
```

## Run All Evaluations

To evaluate an experiment across all supported metrics:

```bash
cd server

uv run python ../eval/scripts/run_eval.py \
  --base-url http://localhost:6006 \
  --experiment-id <experiment_id> \
  --part all
```

The `<experiment_id>` should correspond to an existing experiment stored in the
A<sup>2</sup>E database.

## Run Specific Evaluations

A<sup>2</sup>E supports evaluation across multiple dimensions of agent behavior:

| Metric | Description |
|--------|-------------|
| `plan` | Evaluates planning quality and decision-making behavior |
| `skill` | Measures agent execution capabilities |
| `memory` | Analyzes memory usage and context management |
| `tool` | Evaluates tool selection and tool execution behavior |
| `correct` | Measures final task completion correctness |
| `efficiency` | Analyzes execution efficiency and resource usage |
| `safety` | Evaluates safety-related behaviors |

For example, to evaluate only the planning capability:

```bash
cd server

uv run python ../eval/scripts/run_eval.py \
  --base-url http://localhost:6006 \
  --experiment-id <experiment_id> \
  --part plan
```

## Supported Evaluation Parts

The available evaluation modules are:

```text
plan
skill
memory
tool
correct
efficiency
safety
```

Each evaluation module operates on recorded agent trajectories and produces
metrics for analyzing agent behavior and comparing different agent systems.

## Deterministic audit architecture

The server already uses a local SQLite database by default (`a2e.db`) for
experiments, spans, task runs, and annotations. A2E now adds a separate local
audit provenance ledger at `.a2e/audit.db` (override with
`A2E_AUDIT_DB_PATH` or `--audit-db`). The ledger stores:

- versioned audit definitions and their SHA-256 digests;
- audit sessions linked to experiment and project identifiers;
- executor type and run configuration;
- evidence/result snapshots, status, errors, and timestamps;
- append-oriented audit lifecycle events.

The two databases have different responsibilities: `a2e.db` is the operational
trace store, while `audit.db` is the reproducibility and provenance ledger.

Audit definitions are JSON documents validated against
`audit/schemas/audit-definition-v1.schema.json`. Each definition selects one of
four adapters:

| Executor | Contract |
|---|---|
| `validator` | In-process deterministic Python validator registered by name |
| `script` | Executable script receives JSON on stdin and returns AuditResult JSON |
| `cli` | Explicit argv command, no shell, same stdin/stdout JSON contract |
| `llm` | Declared for compatibility, but disabled in the deterministic engine |

Initialize or inspect the ledger:

```bash
cd eval
python -m audit.cli --db .a2e/audit.db init
python -m audit.cli --db .a2e/audit.db list-runs
```

Run a versioned validator from a JSON definition:

```bash
python -m audit.cli --db .a2e/audit.db run \
  --definition audit/schemas/secret-exposure-v1.audit.json \
  --input evidence.json \
  --subject-id task-run-123
```

The default metric groups now prefer deterministic code metrics. Planning keeps
one LLM grade alongside a structural plan check; safety keeps only the two
high-level semantic judges (`hallucination` and `failure_transparency`) and uses
deterministic validators for secret exposure, authorization evidence, and prompt
injection signals. Memory is a real independent metric group. Missing evidence
returns `score=null, label=unmeasured`, never a synthetic passing score.
