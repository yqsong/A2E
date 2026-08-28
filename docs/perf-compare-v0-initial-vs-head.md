# 两版本性能对比测试方案：v0-initial vs HEAD

> 目的：用 repo 自带的 experiments（`task/examples/run_experiment.py`）对比
> 初始版本（`v0-initial` = `7d2e816`）与 codex 改进后版本（`HEAD` = `2312ee9`）
> 的性能差异，并给出可复现的执行步骤与判读标准。

## 1. 版本状态与差异分析

| 项 | 值 |
|---|---|
| 初始版本 | `v0-initial` → `7d2e816 fix(colab): repair double-https Colab links in README` |
| 改进版本 | `HEAD` → `2312ee9 feat(audit): add deterministic audit engine and local ledger` |
| 改动范围 | **100% 在 `eval/` 评测层**（`git diff --stat v0-initial HEAD -- server task` 为空） |

### 两版评测层差异（这是对比的真正焦点）

| 维度 | v0-initial（旧） | HEAD（新） |
|---|---|---|
| plan | `plan_grade` + `plan_goal_alignment` / `plan_completeness` / `plan_constraint_adherence` / `plan_hallucination`（LLM） | `plan_structure`（确定性 CODE）+ `plan_grade` |
| skill | `conciseness`（LLM） | `response_compactness`（CODE） |
| memory | 无独立组（旧别名并入 safety） | `memory_retention`（CODE，独立组） |
| tool_recall | LLM 打分（无 LLM 则报错） | CODE 确定性打分 |
| safety | `privacy_leakage` / `unauthorized_action` / `harmful_action` / `prompt_injection_resilience` | `secret_exposure` / `authorization_boundary` / `prompt_injection_signals` |
| 审计 | 无 | SQLite 审计 ledger（默认 `.a2e/audit.db`，可用 `--audit-db` / `A2E_AUDIT_DB_PATH` 覆盖） |

**核心结论**：两版在 agent 运行 / 实验捕获层代码完全相同，因此 agent 的
任务表现理论上无差异。对比的重点是**评测层**：确定性 CODE 指标 vs LLM 指标的
①成本（耗时 / LLM API 调用数）②确定性（重复评测分数是否可复现）③覆盖与区分度。

## 2. 测试设计（三层对比）

| 层 | 做什么 | 回答的问题 |
|---|---|---|
| **L1 实验层回归验证** | 两版各跑一遍实验（同 dataset / agent / seed），对比共有指标（correct、efficiency） | 改进版有没有引入实验层回归？ |
| **L2 评测层对比（核心）** | 同一批 traces 分别用两版 eval 管线打 `--part all`，对比新旧指标得分 | 新指标是否合理、稳定、可解释？ |
| **L3 成本与确定性** | 记录每版评测耗时、LLM 调用次数；同一 traces 重复评测看分数波动 | 新评测管线是否更快、更省、可复现？ |

### 2.1 测试矩阵

| dataset | agent | domain | n | seed | 说明 |
|---|---|---|---|---|---|
| `mmlu` | `agno` | — | 20 | 42 | 轻量选择题，验证正确率指标 |
| `tau-bench` | `agno` | `retail` | 20 | 42 | 多轮对话 + 工具调用，最能体现 tool / memory / safety 新指标 |

- 两版实验各跑一遍（L1），共 4 个实验。
- L2/L3 在任一批 traces 上执行（两版实验 traces 理论上一致，可用 L1 任一实验结果）。

## 3. 前置条件

```bash
# 1) 环境：Python 3.10+、uv（https://docs.astral.sh/uv/）
# 2) API key：在仓库根目录复制并填写 .env
cp .env.example .env   # 填 A2E_MODEL / OPENAI_API_KEY / OPENAI_API_BASE（或 ANTHROPIC_*）
# 3) 注意：旧版 tool_recall 与两版 plan_grade 需要 LLM，.env 必须配好模型
```

## 4. 执行步骤

### 4.0 建旧版 worktree（主目录保持 HEAD 新版，互不干扰）

```bash
cd <repo>/A2E
git worktree add ../A2E-v0 v0-initial   # repo config 已设 core.longpaths，长路径文件可正常检出
```

### 4.1 两个目录分别安装依赖 + 配 .env

```bash
# 新版（主目录）
cd <repo>/A2E/task && uv sync --frozen --all-packages --index-strategy unsafe-best-match
cd <repo>/A2E/eval && uv sync

# 旧版（worktree，注意 .env 被 gitignore，需单独复制）
cp <repo>/A2E/.env.example <repo>/A2E-v0/.env   # 填同样的 key
cd <repo>/A2E-v0/task && uv sync --frozen --all-packages --index-strategy unsafe-best-match
cd <repo>/A2E-v0/eval && uv sync
```

### 4.2 启动 server（只起一个，server 层两版零改动）

```bash
cd <repo>/A2E/server && uv sync && uv run a2e serve   # → http://localhost:6006
```

### 4.3 L1 实验层回归：两版各跑 2 个实验

```bash
# 新版
cd <repo>/A2E/task && set -a; . ../.env; set +a
uv run --frozen python examples/run_experiment.py --dataset mmlu     --agent agno --n 20 --sample-seed 42 --run-id v0cmp-new-mmlu
uv run --frozen python examples/run_experiment.py --dataset tau-bench --agent agno --domain retail --n 20 --sample-seed 42 --run-id v0cmp-new-tau

# 旧版
cd <repo>/A2E-v0/task && set -a; . ../.env; set +a
uv run --frozen python examples/run_experiment.py --dataset mmlu     --agent agno --n 20 --sample-seed 42 --run-id v0cmp-old-mmlu
uv run --frozen python examples/run_experiment.py --dataset tau-bench --agent agno --domain retail --n 20 --sample-seed 42 --run-id v0cmp-old-tau
```

每次运行结束从输出抓 experiment_id（供 L2 使用）：

```bash
uv run ... | tee /tmp/a2e_exp.log
grep -oP 'experiment_id:\s*\K.+' /tmp/a2e_exp.log | head -1
```

> 提示：run_id 只影响标识，experiment_id 由 server 生成；`--sample-seed 42`
> 保证两版采样同一批用例（task 层代码相同 → 同 seed 同用例）。

### 4.4 L2/L3 评测层对比：同一批 traces 双版评测

对**同一个** experiment_id（推荐用新版实验的 id），分别跑：

```bash
# 新版评测
cd <repo>/A2E/eval && uv run python scripts/run_eval.py --experiment-id <id> --part all

# 旧版评测（同一 experiment_id！）
cd <repo>/A2E-v0/eval && uv run python scripts/run_eval.py --experiment-id <id> --part all
```

重复跑 2 遍新版评测（或同一实验 id 多评一次）用于 L3 确定性对比：
新版 CODE 指标两次分数应**完全一致**；旧版 LLM 指标会有波动。

### 4.5 收集审计（仅新版）

```bash
cd <repo>/A2E && ls .a2e/audit.db   # 评测后应生成；记录评测会话与结果快照
```

## 5. 判读标准

### L1 实验层
- mmlu 的 `exact_match` / `substring` 两版分数差应 ≤ 1–2 条（模型输出随机性范围内）。
- 若差异显著（> 2 条），说明改进版引入了回归 → 需要进一步查。

### L2 评测层
- 新指标（`response_compactness`、`memory_retention`、`secret_exposure`、
  `authorization_boundary`、`prompt_injection_signals`、`plan_structure`、
  CODE 版 `tool_recall`）应给出 0–1 之间有区分度的分数，而不是全 0 或全 1。
- 对照旧指标（`conciseness`、`privacy_leakage`、`unauthorized_action` 等）看语义是否吻合。

### L3 成本与确定性
- 新版 `--part all` 的 LLM 调用次数应明显少于旧版（`tool_recall` 及 6 个新 CODE 指标零 LLM 成本；旧版 tool_recall + 多个 LLM 指标都要调模型）。
- 新版两次评测同批 traces 分数 100% 一致；旧版 LLM 指标有波动（记录每次差异）。

## 6. 对比报告模板

| 对比项 | v0-initial | HEAD | 结论 |
|---|---|---|---|
| mmlu exact_match（20 条） | ?/20 | ?/20 | 回归? |
| mmlu substring | ?/20 | ?/20 | |
| tau-bench exact_match | ?/20 | ?/20 | |
| tau-bench tool 指标（新旧各自） | ? | ? | 语义吻合? |
| --part all 耗时 | ?s | ?s | |
| --part all LLM 调用次数 | ? | ? | 省多少 |
| 同批 traces 重复评测分数一致性 | 波动 ±? | 100% | |

## 7. 注意事项与已知限制

1. **LLM 输出随机性**：`--sample-seed` 只保证采样一致，不保证模型输出一致
   （除非模型端点 temperature=0）。L1 分数差异需结合此背景解读。
2. **旧版 tool_recall 强依赖 LLM**：若 .env 未配模型，旧版 `--part all` 会报错——
   这是两版差异的一部分，可记录为"旧版配置要求更高"。
3. **长路径**：worktree 检出长路径文件依赖 `core.longpaths`（已写入 repo config，
   worktree 会继承）。
4. **.env 不进版本库**：worktree 需手动复制 .env。
5. **audit ledger 位置**：新版评测默认写 `<repo>/.a2e/audit.db`，可用
   `A2E_AUDIT_DB_PATH` 指定，避免污染 repo。
