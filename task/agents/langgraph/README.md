# langgraph τ-bench agent

**Multi-agent** τ-bench runner powered by LangGraph + LangChain.

Four logical agents arranged in a reasoning-controlled state graph:

```
┌────────┐    ┌──────────┐    ┌─────────────────┐    ┌───────────┐
│ ROUTER │───▶│ EXECUTOR │───▶│ COMPLETION GATE │───▶│ RESPONDER │
└────────┘    └──────────┘    └─────────────────┘    └───────────┘
     ▲              │                  │
     └──── loop ────┘                  └── bounded re-plan ──▶ ROUTER
```

Each node is wrapped in an explicit OpenInference ``AGENT`` span so the A2E
UI surfaces "Router → Executor → Responder" as separate agents within a
single task trace.

## Meta-reasoning control plane

Before execution, the task-core package builds a dataset-agnostic `CaseModel`
from the instruction and visible tool schemas. It estimates side-effect intent,
constraints, entities, tool ambiguity, risk, complexity, and a reasoning mode.
It never reads benchmark `expected_actions`.

When the router proposes termination, the completion gate checks observable
progress. A high-confidence state-changing request with only read/query calls,
or a failed mutation without recovery, receives one additional re-planning
pass. The bounded pass prevents infinite reflection loops and still permits a
well-evidenced refusal when an action is invalid, unsafe, or impossible.

## LLM provider

Uses ``langchain-openai`` and is OpenAI-compatible. Configure via env:

```bash
export OPENAI_API_KEY=...
export OPENAI_API_BASE=http://35.220.164.252:3888/v1/   # any OpenAI-compatible
export A2E_LANGGRAPH_MODEL=deepseek-v4-pro
```

Defaults fall back to ``OPENAI_BASE_URL`` / ``OPENAI_API_KEY`` and
``gpt-4o-mini``.

## Usage

```python
import asyncio
from ageneval.task.agents.langgraph import LangGraphTauAgent
from ageneval.task.datasets.tau_bench import load_tau_bench_tasks
from ageneval.task.core import ExperimentRunner, setup_instrumentation

provider = setup_instrumentation(
    project_name="tau-bench-langgraph",
    framework="langchain",
)
agent = LangGraphTauAgent(domain="retail")
dataset = load_tau_bench_tasks("retail", n=1)

with ExperimentRunner(dataset=dataset, agent=agent, tracer_provider=provider) as runner:
    for trace in asyncio.run(runner.run_all()):
        print(trace.task_id, trace.status, trace.turns, len(trace.tool_calls))
```
