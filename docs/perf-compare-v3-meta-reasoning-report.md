# v3 评测报告：adaptive meta-reasoning + metric applicability

> 版本：`ee021f5 feat(agent): add adaptive meta-reasoning control`
> 评测时间：2026-08-29
> 模型：`deepseek-v4-flash`；agent：`agno`；数据集：`mmlu`（n=20, seed=42）、
> `tau-bench`（retail, n=20, seed=42）

## 1. 本次改动性质（与前三次不同）

| 版本 | commit | 改动范围 | 说明 |
|---|---|---|---|
| v0 | `7d2e816` | eval/ 层 | baseline，指标几乎全 LLM |
| v1 | `2312ee9` | eval/ 层 | LLM → CLI/确定性 + audit ledger |
| v2 | `4fcf67c` | eval/ 层 | dynamic semantic layer（hybrid tool_recall） |
| **v3** | `ee021f5` | **agent/ + eval/ 层** | agent：`meta_reasoning.py`（终止前可追加一轮 bounded re-planning）；eval：`applicability.py`（指标适用性判定，不适用则不送 LLM） |

**关键影响**：v3 改了 agent 执行，因此必须重新跑实验生成新 traces
（mmlu → Experiment:3、tau-bench → Experiment:4，各 20 runs，seed=42）。
v0/v1/v2 在旧 traces（Experiment:1/2）上对比的是纯评测层差异；
v3 的对比 = agent 行为变化 + 评测层变化两层叠加。

## 2. L1 任务表现（agent 层效果：meta-reasoning）

| 指标 | v0-v2 批次（exp 1/2） | v3（exp 3/4） | 变化 |
|---|---|---|---|
| mmlu exact_match | 0.850 (17/20) | **0.900 (18/20)** | +0.05 |
| mmlu substring | 0.850 | 0.900 | +0.05 |
| mmlu task_succeeded | 0.950（1 error） | **1.000** | +0.05 |
| mmlu correctness（LLM 判） | 0.850 | **0.900** | +0.05 |
| mmlu total_token_usage | 846.5 | 942.7 | +11% |
| tau exact_match | 0.000 | 0.050 | +0.05 |
| tau substring | 0.250 | 0.200 | -0.05 |
| tau task_succeeded | 1.000 | **0.900（2 error）** | **-0.10** |
| tau correctness（LLM 判） | 0.60–0.65 | 0.60 | 持平 |
| tau turn_count | 4.50 | **1.20** | **-73%** |
| tau tool_call_count | 6.25 | 6.55 | +0.3 |
| tau total_token_usage | 27693 | **40395** | **+46%** |

> mmlu 上 agent 更好（多答对 1 题）；tau 上 meta-reasoning 将回合从 4.5 压到 1.2
> （-73%）、token 消耗 +46%，但任务完成率 1.0 → 0.9（2 条 error）、correctness 持平——
> re-planning 在 tau 这类多轮任务上成本高、收益不明显甚至略降。

## 3. L2 评测层：tool_recall 行为（本轮核心变化）

| 版本 | mmlu tool_recall | tau tool_recall |
|---|---|---|
| v0 | 0.85–0.95（LLM fallback，波动） | 0.5175 |
| v1 | unmeasured（盲区） | 0.5175 |
| v2 | 0.90–0.95（LLM fallback，波动） | 0.5319 |
| **v3** | **not_applicable（20/20，不送 LLM）** | **0.5774** |

- **mmlu**：v3 用 `tool_metric_applicability` 判定 `no_tool_contract_or_trajectory`，
  返回 **not_applicable**（score=None）+ 机器可读原因（`applicability` metadata）。
  对比 v2 的 LLM 硬打分（0.90–0.95 但两遍波动）、v1 的 unmeasured，
  v3 更诚实：不适用就不制造分数。
- **tau**：0.5774 为四版最高，含 `deterministic=1/1; unresolved=0; llm_fallback=False`
  满分 case；提升来自 agent 行为变化 + tool_recall prompt 调整
  （不再默认假设必须使用工具）。

## 4. L3 评测成本与确定性

| | v0 | v1 | v2 | v3 |
|---|---|---|---|---|
| mmlu `--part all` 耗时 | 21:56 | 10:28 | 13:04–15:08 | **5:53** |
| tau `--part all` 耗时 | 1:09:59 | 40:29 | 35:45–38:42 | 36:55 |
| mmlu LLM 调用次数 | 304 | 82 | 102 | **82** |
| tau LLM 调用次数 | 284 | 82 | 102 | **101** |

> mmlu 评测从 v2 的 13–15 分钟/102 次降到 **5:53/82 次**：applicability 免掉
> tool_recall 的 20 次 LLM fallback，且比 v1（同样 82 次但 unmeasured）信息量更大。
> tau 上 101 vs 102 基本持平（tau 的 tool_recall 仍有合理 fallback）。

## 5. 结论

1. **评测层（applicability）是明确改进**：mmlu tool_recall 从"LLM 波动打分"→
   "明确 not_applicable"，评测耗时 -60%、LLM 调用 -20 次、不制造分数；
   tau tool_recall 创四版新高 0.5774。
2. **agent 层（meta-reasoning）效果参半**：mmlu 正确率 +1 题；但 tau 上
   token +46%、turn -73%、task_succeeded 1.0→0.9——re-planning 的 token 成本
   在 tau 上未得到任务收益回报，建议关注/调优。
3. **turn_count 口径变化**：tau 上 4.5→1.2 是 agent 行为（单回合多工具调用）的
   真实变化，解读需与 tool_call_count（6.25→6.55）配套，避免误读为"任务更简单"。
4. **确定性**：v3 未跑两遍评测；由 v2 实测推断——CODE 指标可复现、LLM 指标
   （correctness/plan_grade/hallucination/failure_transparency）有 ±0.1 波动；
   v3 的 mmlu 评测不再含 tool_recall fallback，理论上更确定。

## 6. 已知限制

- v3 与 v0-v2 的 traces 不同（agent 层改动所致），L2 指标分数差异同时包含
  agent 行为与评测层两重因素，不能完全归因于评测层。
- cost/elapsed_time 仍 unmeasured（实验 output 未记录 duration/cost 字段）。
- tau 上 v3 出现 2 条 error（task_succeeded 0.90），建议检查是否为
  meta-reasoning re-planning 引入的回归。
