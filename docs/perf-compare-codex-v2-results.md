# 两次 codex 改动评测报告（mmlu + tau-bench）

> 评测对象：HEAD `4fcf67c`（含两次 codex 改动：
> `2312ee9` 确定性 audit 引擎 + audit CLI、`4fcf67c` hybrid semantic matching layer）
> 模型：`deepseek-v4-flash`（OpenAI 兼容端点 `https://api.deepseek.com/v1`）
> agent：`agno`；数据集：`mmlu`（n=20, seed=42）、`tau-bench`（retail, n=20, seed=42）
> 评测命令：`run_eval.py --part all`（19 个指标，共 21 项含任务自带 exact_match/substring）

## 1. L1 实验层（任务表现）

| 指标 | mmlu (exp 1) | tau-bench (exp 2) |
|---|---|---|
| exact_match | 17/20 = 0.850 | 0/20 = 0.000 |
| substring | 17/20 = 0.850 | 5/20 = 0.250 |
| task_succeeded | 19/20 = 0.950 | 20/20 = 1.000 |
| correctness（A2E LLM 判官） | 0.850（两遍一致） | 0.600 / 0.650（两遍波动） |

> tau-bench 的 exact_match=0 是任务自带字符串匹配对多轮工具任务不适用所致
> （无逐字标准答案）；其主指标应看 A2E 的 correctness / tool / safety 组。

## 2. L2 评测层（`--part all` 共 19 个指标）

### mmlu（exp 1）

| 指标 | 类型 | mean | 备注 |
|---|---|---|---|
| correctness | LLM | 0.850 | 17 correct / 3 incorrect |
| plan_grade | LLM | 0.850 | 17 perfect / 3 failed |
| hallucination | LLM | 0.950–1.000 | 两遍间波动 |
| failure_transparency | LLM | 0.950–1.000 | 两遍间波动 |
| tool_recall | hybrid | 0.900–0.950 | LLM fallback 引起波动 |
| exact_match / substring | CODE | 0.850 | 两遍完全一致 |
| secret_exposure | CODE | 1.000 | 无泄密 |
| response_compactness | CODE | 1.000 | 19/20（1 条 error 未评） |
| task_succeeded | CODE | 0.950 | 1 条 error |
| total_token_usage | CODE | 846.5 | 265–4544 |
| turn_count | CODE | 1.000 | 全部单轮（纯问答） |
| tool_call_count | CODE | 0.000 | 无工具调用（合理） |
| plan_structure | CODE | unmeasured | 无结构化 plan 字段 |
| memory_retention | CODE | unmeasured | 无 memory_facts 字段 |
| authorization_boundary | CODE | unmeasured | 无 allowed_actions 字段 |
| prompt_injection_signals | CODE | unmeasured | 无注入挑战字段 |
| tool_hallucination | CODE | unmeasured | 无 TOOL span |
| self_correction_rate | CODE | unmeasured | 无工具报错 |
| cost / elapsed_time | CODE | unmeasured | 实验 output 未记录 cost/duration 字段 |

### tau-bench retail（exp 2）

| 指标 | 类型 | mean | 备注 |
|---|---|---|---|
| correctness | LLM | 0.600 / 0.650 | 两遍波动（12/13 correct） |
| plan_grade | LLM | 0.700 / 0.640 | 两遍波动 |
| hallucination | LLM | 0.650 / 0.550 | 两遍波动 |
| failure_transparency | LLM | 0.700 / 0.800 | 两遍波动 |
| tool_recall | hybrid | 0.5319（两遍一致） | deterministic 平均覆盖 6–12/13，unresolved 走 LLM fallback |
| tool_call_count | CODE | 6.250 | 3–11 次/任务，13 high / 7 medium |
| turn_count | CODE | 4.500 | 3–6 轮 |
| total_token_usage | CODE | 27693.05 | 15015–45842 |
| response_compactness | CODE | 1.000 | |
| secret_exposure | CODE | 1.000 | 无泄密 |
| task_succeeded | CODE | 1.000 | |
| self_correction_rate | CODE | 0.500 | 仅 3 条有工具报错（n=3） |
| exact_match / substring | CODE | 0.000 / 0.250 | 任务自带字符串匹配 |
| cost / elapsed_time | CODE | unmeasured | 同 mmlu |
| plan_structure / memory_retention / authorization_boundary / prompt_injection_signals | CODE | unmeasured | 数据未提供对应字段 |
| tool_hallucination | CODE | unmeasured | LLM spans 中无 tool schema |

## 3. L3 成本与确定性

| 项 | mmlu | tau-bench |
|---|---|---|
| `--part all` 耗时（两次） | 13:04 / 15:08 | 35:45 / 38:42 |
| LLM API 调用（每次评测） | 102 次 | 102 次 |
| CODE 指标 LLM 成本 | 0 | 0 |

- 102 次 LLM 调用全部来自 4 个 LLM 指标（correctness、plan_grade、hallucination、
  failure_transparency；20 runs × 4 + 重试）；其余 15 个指标零 LLM 成本。
- 确定性对比（同批 traces 两次评测）：
  - **CODE 指标 100% 一致**：exact_match、substring、secret_exposure、
    response_compactness、total_token_usage、turn_count、tool_call_count、
    self_correction_rate、task_succeeded 两遍分数完全相同。
  - **LLM 指标有波动**：mmlu hallucination 1.000→0.950、failure_transparency
    0.950→1.000；tau correctness 0.600→0.650、hallucination 0.650→0.550、
    failure_transparency 0.700→0.800、plan_grade 0.700→0.640。
  - **hybrid 指标（tool_recall）偶发波动**：mmlu 上 0.950→0.900（unresolved 项
    走 LLM fallback 所致）；tau 上 0.5319 两次一致。
- audit ledger（第一次改动的产物）：`server/.a2e/audit.db` 记录了 4+ 次评测会话、
  1640 条结果快照、21 条 audit definition，评测会话语义与结果可溯源。

## 4. 两次 codex 改动验证结论

1. **第一次改动（LLM → CLI/确定性 CODE）**：19 个指标中 15 个已是纯 CODE
   确定性指标，`--part all` 的 LLM 调用从"多个指标每个 run 都调"收敛到仅
   4 个 LLM 指标共 ~102 次/评测（20 runs 含重试）；CODE 指标重复评测 100% 可复现；
   SQLite audit ledger 正常工作。
2. **第二次改动（dynamic semantic layer）**：`tool_recall` 三阶段生效——
   explanation 显示 `deterministic=12/13; unresolved=1; llm_fallback=True` 等，
   常见工具名走 exact/alias 确定性路径，未解决的才进 LLM fallback；低分 case
   （如"只查询未取消订单"）由 LLM 语义判定为未覆盖，给出 0.0–0.92 的区分度分数，
   而非全 0 或全 1。
3. **unmeasured 均为数据缺失**（README 设计行为：缺证据返回 score=null、
   label=unmeasured，不编造通过分）：mmu/tau 数据集未提供 allowed_actions、
   memory_facts、plan 等字段；实验 output 未记录 elapsed/cost 字段。

## 5. 已知限制

- `cost` / `elapsed_time` 恒为 unmeasured：run_experiment.py 的 output 未记录
  duration/cost 字段，评测读取不到（非评测 bug，属捕获层缺口）。
- `tool_hallucination` 在 tau-bench unmeasured：LLM spans 未携带 tool schema。
- tau-bench 的字符串匹配指标（exact_match/substring）无区分度，需以 A2E
  correctness / tool / safety 指标为主。
- deepseek-v4-flash 为推理模型（返回 reasoning_content），评测与实验均正常
  完成；LLM 指标分数波动属模型温度/推理随机性，与两次 codex 改动无关。
