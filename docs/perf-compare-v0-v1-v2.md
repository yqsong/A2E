# 三次版本对比报告：v0-initial vs 第一次改动 vs 第二次改动

> 同一批 traces（experiment 1 = mmlu n=20 seed=42；experiment 2 = tau-bench retail n=20 seed=42），
> 分别用三个版本的 eval 管线跑 `--part all --force`，直接对比评测层差异。
> agent/捕获层代码三版相同（改动 100% 在 `eval/`），实验无需重跑。

| 版本 | commit | 说明 |
|---|---|---|
| **v0 baseline** | `7d2e816` | 原始版本，指标几乎全部 LLM 打分 |
| **v1 第一次改动** | `2312ee9` | LLM → CLI/确定性：audit 引擎 + SQLite ledger；plan_structure/response_compactness/memory_retention/secret_exposure 等转 CODE；tool_recall 转确定性 |
| **v2 第二次改动** | `4fcf67c` | 提升鲁棒性：dynamic semantic layer（exact → 词法置信度 → LLM fallback），tool_recall 变 hybrid |

## 1. 指标构成变化

| 维度 | v0 | v1 | v2 |
|---|---|---|---|
| 指标总数（--part all） | 21 | 19 | 19 |
| LLM 指标 | ~18 个（plan 5、conciseness、tool_recall、tool_invocation、hallucination、privacy/unauthorized/harmful/prompt_injection 等） | 4 个（correctness、plan_grade、hallucination、failure_transparency） | 4 个 + tool_recall 的 LLM fallback |
| CODE 指标 | 3–4 个 | 15 个 | 15 个 |
| audit ledger | 无 | 有（`.a2e/audit.db`，会话+结果快照） | 有 |
| tool_recall 实现 | LLM 直接打分 | 纯确定性（expected_actions 为空则 unmeasured） | hybrid：确定性优先，unresolved/空场景走 LLM fallback |

## 2. 评测分数对比（mmlu）

| 指标 | 类型 | v0 | v1 | v2 | 备注 |
|---|---|---|---|---|---|
| exact_match / substring | CODE | 0.850 / 0.850 | 0.850 / 0.850 | 0.850 / 0.850 | 三版一致（任务指标） |
| correctness | LLM | 0.850 | 0.850 | 0.850 | 一致 |
| plan_grade | LLM | 0.860 | 0.850 | 0.850 | v0 有 5 个 plan 子指标 |
| plan_goal_alignment / completeness / constraint / hallucination | LLM | 0.900 / 0.850 / 0.900 / 0.950 | — | — | v1/v2 由 plan_structure(CODE) 替代 |
| conciseness | LLM | 1.000 | — | — | v1/v2 由 response_compactness(CODE)=1.000 替代 |
| **tool_recall** | v0 LLM / v1 CODE / v2 hybrid | **0.850** | **unmeasured**（expected_actions 为空） | **0.900–0.950**（LLM trajectory judge fallback） | **第二次改动的关键改进** |
| hallucination | LLM | 1.000 | 0.950 | 0.950–1.000 | LLM 波动 |
| failure_transparency | LLM | 0.950 | 0.950 | 0.950–1.000 | LLM 波动 |
| privacy/unauthorized/harmful/prompt_injection_resilience | LLM | 全部 1.000 | — | — | v1/v2 由 secret_exposure(CODE)=1.000、authorization_boundary/prompt_injection_signals(CODE)=unmeasured 替代 |
| tool_hallucination / self_correction_rate | v0 LLM / v1·v2 CODE | 1.000 / 1.000(no_errors) | unmeasured | unmeasured | mmlu 无工具场景，CODE 版如实 unmeasured |
| total_token_usage | CODE | 846.5 | 846.5 | 846.5 | 一致 |

## 3. 评测分数对比（tau-bench retail）

| 指标 | 类型 | v0 | v1 | v2 | 备注 |
|---|---|---|---|---|---|
| exact_match / substring | CODE | 0.000 / 0.250 | 0.000 / 0.250 | 0.000 / 0.250 | 一致（字符串匹配对多轮任务无区分度） |
| correctness | LLM | 0.700 | 0.550 | 0.600–0.650 | LLM 波动，v1 单次偏低 |
| plan_grade | LLM | 0.650 | 0.640 | 0.640–0.700 | 波动 |
| plan_goal_alignment / completeness / constraint / hallucination | LLM | 0.950 / 0.150 / 0.600 / 0.800 | — | — | v0 的 plan_completeness=0.15 明显低，v1/v2 无此信号（plan_structure unmeasured） |
| conciseness | LLM | 0.750（5 条 verbose） | — | — | v1/v2 response_compactness(CODE)=1.000 |
| **tool_recall** | v0 LLM / v1 CODE / v2 hybrid | **0.5175** | **0.5175** | **0.5319**（两遍一致） | CODE 版与 LLM 版在 tau 上结果一致；v2 semantic layer 略高 |
| hallucination | LLM | 0.650 | 0.700 | 0.550–0.650 | 波动 |
| failure_transparency | LLM | 0.800 | 0.800 | 0.700–0.800 | 波动 |
| privacy_leakage | LLM | 0.700（6 条 leak） | — | — | v1/v2 secret_exposure(CODE)=1.000（模式匹配口径更严） |
| unauthorized / harmful / prompt_injection | LLM | 1.000 / 1.000 / 1.000 | — | — | 被 CODE 组替代 |
| tool_hallucination | v0 LLM / v1·v2 CODE | unmeasured | unmeasured | unmeasured | v1/v2 因 LLM span 无 tool schema 无法测 |
| self_correction_rate | v0 LLM / v1·v2 CODE | 0.925（n=20，17 no_errors） | 0.500（n=3） | 0.500（n=3） | v0 对无报错 run 也给 no_errors；v1/v2 只评有工具报错的 run |
| tool_call_count / turn_count / total_token_usage | CODE | 6.25 / 4.5 / 27693 | 6.25 / 4.5 / 27693 | 6.25 / 4.5 / 27693 | 一致 |

## 4. 成本与确定性（L3）

| 项 | v0 | v1 | v2 |
|---|---|---|---|
| mmlu `--part all` 耗时 | 21:56 | 10:28 | 13:04 / 15:08 |
| tau `--part all` 耗时 | 1:09:59 | 40:29 | 35:45 / 38:42 |
| mmlu LLM 调用次数 | **304** | **82** | **102** |
| tau LLM 调用次数 | **284** | **82** | **102** |
| CODE 指标 LLM 成本 | — | 0 | 0 |
| 确定性（同批 traces 重复评测） | LLM 指标有波动（未实测两遍） | CODE 指标可复现 | CODE 指标 100% 一致；LLM 指标波动；hybrid tool_recall mmlu 上 0.95→0.90 |

- **v0 → v1**：LLM 调用 -73%（304→82 / 284→82），耗时减半；代价是 6 个数据依赖指标变 unmeasured、
  tool_recall 在 expected_actions 为空的场景（mmlu）无法测量。
- **v1 → v2**：LLM 调用 +20 次（82→102，即 tool_recall 的 LLM fallback），但换来了
  tool_recall 在无工具/名称不匹配场景的可测量性（mmlu 从 unmeasured → 0.90–0.95）。

## 5. 结论

1. **第一次改动（LLM→CLI/确定性）的收益**：成本大幅下降（LLM 调用 -73%、耗时约减半），
   CODE 指标重复评测可复现；audit ledger 提供可溯源会话。
2. **第一次改动的代价（被第二次修复）**：纯 CODE 的 tool_recall 在 expected_actions
   为空（mmlu）时 unmeasured；数据缺失类指标（memory/authorization 等）unmeasured。
3. **第二次改动（dynamic semantic layer）的收益**：tool_recall 变三阶段 hybrid——
   确定性路径覆盖常见工具名（tau 上 deterministic=12/13 等），unresolved 或空场景
   走 LLM fallback（mmlu 从 unmeasured 恢复为 0.90–0.95 的可测量分数）；
   tau 上 tool_recall 0.5175 → 0.5319。
4. **成本与能力平衡**：v2 比 v1 多 ~20 次 LLM 调用（仅 tool_recall fallback），
   但远低于 v0 的 284–304 次，且修复了 v1 的测量盲区。
5. **LLM 指标波动**（correctness/plan_grade/hallucination/failure_transparency 的
   ±0.1 级波动）在三个版本中都存在，属模型随机性，与改动无关。

## 6. 已知限制

- v0 评测只跑了一遍（未做两遍确定性实测）；v1 亦然。确定性结论以 v2 的两遍实测为准，
  v0/v1 的 CODE 指标确定性由实现推断（纯代码路径，无随机源）。
- cost/elapsed_time 三版均 unmeasured（实验 output 未记录 duration/cost 字段）。
- v0 的 plan_completeness（tau 0.15）等细粒度 LLM 信号在 v1/v2 中没有直接对应物，
  对比时只能看替代指标（plan_structure/plan_grade）。
