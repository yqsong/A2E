# tool_recall 三版失败案例分析（v0 vs v1 vs v2）

> 生成时间：2026-08-29 21:42
> 数据集：mmlu（exp 1, n=20）、tau-bench retail（exp 2, n=20），同一批 traces
> 指标：`tool_recall`（唯一三版实现不同的核心指标）
> 数据来源：`v0_tool_recall.json` / `v1_tool_recall.json` / `v2_tool_recall.json`（本目录，逐 run 明细）

## 1. 三版实现差异

| 版本 | commit | tool_recall 实现 | 失败模式 |
|---|---|---|---|
| v0 | `7d2e816` | 名称精确匹配；`expected_actions` 为空时走 LLM trajectory judge fallback | LLM fallback 判分不稳定 |
| v1 | `2312ee9` | 纯确定性 CODE；`expected_actions` 为空直接 unmeasured | 测量盲区（无法测量） |
| v2 | `4fcf67c` | hybrid：确定性匹配 → 词法相似度 → LLM fallback | fallback 处残留 LLM 不稳定 |

## 2. 案例一：v1 测量盲区（mmlu，expected_actions 为空）

mmlu 全部 20 个 run 的 `expected_actions` 为空，v1 的 CODE 实现全部 unmeasured；
v0/v2 均有 LLM fallback，但判分不稳定（同一场景可判相反）：

### run 22（纯数学问答，无需工具）

| 版本 | score | label | explanation |
|---|---|---|---|
| v0 | 1.0 | complete | expected_actions is empty; used LLM trajectory judge fallback. The task required only a direct mathematical answer, so no tool use was necessary, and the agent provided the correct answer. |
| v1 | null | unmeasured | expected_actions is empty; tool recall cannot be measured deterministically |
| v2 | 0.0 | missed | expected_actions is empty; used LLM trajectory judge fallback. The agent made no tool calls, so it did not inspect relevant files or run any verification commands required by the task. |

> 同一 run：v0 判 complete（1.0），v2 判 missed（0.0）——LLM fallback 不稳定。
> 整体上 mmlu 的 tool_recall：v0 = 0.85（第一轮）/ 0.95（重跑），v2 = 0.90 / 0.95，
> 波动均来自 LLM fallback；v1 恒为 unmeasured（20/20 盲区）。

## 3. 案例二：v0/v1 名称精确匹配漏判（tau-bench）

v0 与 v1 在 tau 上分数完全相同（0.5175），按工具名精确匹配 `called` vs `expected`；
v2 的 semantic 层（确定性 + LLM fallback）可补判部分"未解析的期望操作"。

| run | v0 | v1 | v2 | v2 explanation 关键片段 |
|---|---|---|---|---|
| 46 | 0.600 | 0.600 | 0.833 | deterministic=10/12; unresolved=2; llm_fallback=True |
| 55 | 0.600 | 0.600 | 0.750 | deterministic=9/12; unresolved=3; llm_fallback=True |
| 43 | 0.833 | 0.833 | 0.923 | deterministic=12/13; unresolved=1; llm_fallback=True |
| 48 | 0.750 | 0.750 | 0.833 | deterministic=5/6; unresolved=1; llm_fallback=True |

完整 explanation 见 JSON（run_id 46/55/43/48）。

## 4. 案例三：三版都判失败（agent 真实未执行关键操作）

6 条 run 三版全 0.0——agent 只做了信息查询、未执行关键修改/取消操作，
评测失败信号可靠（非误判）：

| run | 期望操作 | 三版 | v1 / v2 explanation 片段 |
|---|---|---|---|
| 41 | cancel_pending_order | 0.0 / 0.0 / 0.0 | v1: called=[...get_order_details...]; hit=[]; v2: deterministic=0/2; unresolved=2 → LLM 判定未执行取消 |
| 44 | exchange_delivered_order_items | 0.0 / 0.0 / 0.0 | v2: 只检索用户/订单/商品详情，未执行或语义覆盖换货 |
| 50 | modify_pending_order_items + modify_user_address | 0.0 / 0.0 / 0.0 | v2: 只获取信息，未执行要求的修改 |

完整 explanation 见 JSON（run_id 41/44/50）。

## 5. 结论

- v1 的失败是"测不了"（unmeasured 盲区）；v0 的失败是"测不准"（LLM 不稳定）；
- v2 是折中：确定性兜底 + 仅 unresolved 时用 LLM，补齐 v1 盲区，
  但 fallback 处仍继承 v0 的不稳定性（如 mmlu run 22）。
- tau 上 v2 语义补判使 tool_recall 从 0.5175 提升到 0.5319（两次一致）。
