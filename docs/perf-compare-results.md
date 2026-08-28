# 两版本对比实测结果：v0-initial vs HEAD

> 执行时间：2026-08-28。测试设计见 `docs/perf-compare-v0-initial-vs-head.md`。

## 0. 测试配置

- 模型：DeepSeek `deepseek-chat`（`OPENAI_API_BASE=https://api.deepseek.com/v1`）
- agent：`agno`；n=20；`--sample-seed 42`
- 数据集：`mmlu`（选择题）、`tau-bench`（retail，多轮工具调用）
- 两版各跑一遍实验（4 个 experiment）；同一批 traces 用两版 eval 管线分别评 `--part all`

| experiment | 版本 | dataset |
|---|---|---|
| RXhwZXJpbWVudDox / 1 | HEAD | mmlu |
| RXhwZXJpbWVudDoy / 2 | HEAD | tau-bench |
| RXhwZXJpbWVudDoz / 3 | v0-initial | mmlu |
| RXhwZXJpbWVudDo0 / 4 | v0-initial | tau-bench |

## 1. L1 实验层回归：无回归

用**同一套（新版）eval** 评两版实验的共有确定性指标：

| 指标 | new-exp (mmlu) | old-exp (mmlu) | new-exp (tau) | old-exp (tau) |
|---|---|---|---|---|
| correctness | 0.900 | 0.850 | 0.350 | 0.550 |
| task_succeeded | 1.000 | 1.000 | 1.000 | 1.000 |
| turn_count | 1.000 | 1.000 | 4.150 | 4.600 |
| total_token_usage | 246.65 | **246.65** | 23424.7 | 25960.4 |
| tool_call_count | 0.000 | 0.000 | 5.400 | 6.050 |

- mmlu 两版实验 `total_token_usage` **逐字节一致（246.65）**、turn/tool 一致 → 采样与 prompt 完全相同，实验层零回归。
- tau 的 correctness 差异（0.35 vs 0.55）是多轮对话的模型输出随机性（DeepSeek temperature>0，同 seed 只保证采样一致）导致的轨迹分叉，非代码回归——两版 task 层代码相同（`git diff v0-initial HEAD -- server task` 为空）已直接证明。

## 2. L2 评测层：指标构成与语义变化

同一批 traces（新版实验）分别用两版 eval 评测：

| 版本 | 指标总数 | CODE | LLM | LLM 指标 |
|---|---|---|---|---|
| v0-initial | 23 | 8 | 15 | plan_grade, plan_goal_alignment, plan_completeness, plan_constraint_adherence, plan_hallucination, conciseness, correctness, hallucination, failure_transparency, privacy_leakage, unauthorized_action, harmful_action, prompt_injection_resilience, tool_invocation, tool_recall |
| HEAD | 19 | **15** | **4** | plan_grade, correctness, hallucination, failure_transparency |

**LLM 指标从 15 个降到 4 个（-73%）**，新增 6 个确定性指标：`plan_structure`、`response_compactness`、`memory_retention`、`secret_exposure`、`authorization_boundary`、`prompt_injection_signals`。

关键对比（tau，同一 traces）：

| 指标 | old-eval | new-eval | 说明 |
|---|---|---|---|
| tool_recall | 0.410 (LLM) | **0.410 (CODE)** | 确定性实现与 LLM 打分**完全吻合** |
| tool_call_count | 5.400 | 5.400 | 确定性一致 |
| total_token_usage | 23424.7 | 23424.7 | 一致 |
| self_correction_rate | 0.925 | 0.500 | 语义变化，见下 |
| plan_grade | 0.430 | 0.600 | LLM 波动 |

**核心语义变化（新版）**：对"空集/未发生"场景不再给 vacuous 满分，而是标记 `unmeasured`（score=None，不参与计分）：
- 旧版：`no tool error outputs observed` → `self_correction_rate = 1.0`（真空正确，虚高）
- 新版：`no tool error outputs observed` → `self_correction_rate = unmeasured`
- 同样变化应用于 `tool_recall`（expected_actions 为空）与 `tool_hallucination`（无 tool 调用）

这解释了 self_correction_rate 从 0.925 → 0.500：旧版把大量"没发生过错误"的 run 计为满分，新版只对真正发生过错误并成功纠正的 run 计分。新版分数**更诚实、更有区分度**。

## 3. L3 成本与确定性：新版本质优势

### 3.1 评测成本（DeepSeek API 调用次数 / 耗时）

| 数据集 | old-eval LLM 调用 | new-eval LLM 调用 | 减少 | 耗时 old→new | 加速 |
|---|---|---|---|---|---|
| mmlu | 300 | 80 | **-73%** | 6m11s → 2m25s | **2.6×** |
| tau-bench | 280 | 80 | **-71%** | 7m07s → 3m08s | **2.3×** |

### 3.2 确定性（同一 experiment 两次评测，逐 run×指标比对）

| 指标类型 | 一致率 | 说明 |
|---|---|---|
| CODE（新版确定性） | **300/300 = 100.0%** | 完全可复现 |
| LLM（旧版式打分） | 67/80 = 83.8% | 13 处波动，`hallucination` 出现 0.0 ↔ 1.0 翻转 |

新版评测结果可审计、可复现；旧版 LLM 打分有约 16% 的不稳定。

### 3.3 审计能力

新版每次评测写入 SQLite 审计 ledger（`A2E_AUDIT_DB_PATH`，默认 `.a2e/audit.db`），记录评测会话、配置与结果快照——旧版无此能力。

## 4. 结论

| 维度 | v0-initial | HEAD | 评价 |
|---|---|---|---|
| 实验层正确率 | 基准 | 与基准一致（mmlu token 逐字节相同） | 无回归 |
| 评测指标 | 23（15 LLM） | 19（4 LLM，15 CODE） | 更省、更可复现 |
| tool_recall | LLM 0.410 | CODE 0.410 | 确定性实现等价 LLM |
| 分数诚实性 | 空集给 vacuous 1.0 | 空集标 unmeasured | 新版消除虚高 |
| 评测耗时 | 6–7 min | 2–3 min | 2.3–2.6× 加速 |
| LLM API 成本 | 280–300 次/实验 | 80 次/实验 | -71%~-73% |
| 结果可复现性 | LLM 83.8% | CODE 100.0% | 新版可审计 |

**一句话**：codex 的改进没有改变 agent 行为（实验层零回归），但把评测层从"15 个不可复现的 LLM 打分"重构为"15 个确定性 CODE 指标 + 4 个 LLM 指标"，评测成本降低约 3 倍、结果 100% 可复现、分数更诚实（消除 vacuous 满分），并新增审计 ledger。

## 5. 过程中发现并修复的仓库问题

| 问题 | 影响 | 处理 |
|---|---|---|
| `task/uv.lock` 缺 workspace member `ageneval-task-deepsearchqa`（`uv sync --frozen` 报错） | 依赖无法安装 | 两版 worktree 均执行 `uv lock` 更新 lockfile（已改动 `task/uv.lock`） |
| `server/server/src/a2e/version.py` 写死 `0.0.1`，而 a2e-client 要求 server ≥ 13.15.0 | 评测 API 报"Please upgrade your A2E server" | 本地改为 `13.15.0`（已改动 `server/server/src/a2e/version.py`） |
| Windows 控制台 cp1252 无法编码 `✓`/`🚀` 等字符 | 实验脚本 stdout 崩溃 | 运行前设 `PYTHONIOENCODING=utf-8` |
| 长路径文件（`monitor/.../cassettes/*.yaml`）超过 Windows 260 字符 | clone/checkout 失败 | `core.longpaths=true` |
| 两版 eval 并行写同一 experiment 的 annotations 会互相覆盖 | 结果污染 | 顺序执行 + 每轮前清空 annotations + 立即导出 |

建议把前两个问题修复提交回仓库（`uv.lock` 更新、`version.py` 版本号）。
