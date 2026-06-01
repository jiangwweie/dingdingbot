# Current Position Rebuild

Date: 2026-05-29
Method: read-only, no code changes, no PG mutation, no exchange calls

2026-06-01 governance note: this document remains useful as a historical
position rebuild, but its research-only/read-only and blanket testnet Owner
authorization wording is superseded by `docs/ops/agent-current-brc-baseline.md`
and the 2026-06-01 amendment to ADR-0009. Use current tracked code, current
verified reports, and the agent baseline for execution/testnet behavior.

---

## 1. Owner 纠正

### 1.1 旧定位（已过期）

knowledge-pack `PROJECT_OVERVIEW.md` 原文：

> 当前是 AI-agent 辅助的低频加密衍生品个人杠杆 Campaign 研究与治理系统，处于 BRC Reset / Opportunity Structure Discovery v0

Owner 明确指出该定位**错误 / 未更新**。

### 1.2 新定位（2026-05-29 Owner 修正）

来源：`docs/ops/project-roadmap-v2.md` unstaged diff（2026-05-29 amendment）

> The project target is not a fully automated general strategy system at this stage. The active target is a fast trial-and-review research system for small risk-capital Campaigns.

推荐的研究漏斗：

```
wide admission → broad coarse screen → candidate → risk disclosure → Owner risk acceptance → bounded live trial or continued fine screen → review → promote / revise / park
```

硬边界：
- no uncontrolled capital risk
- no strategy self-elevation
- no bypass around Operation Layer

### 1.3 纠正要点

| 维度 | 旧定位 | 新定位 |
|---|---|---|
| 项目目标 | 通用策略研究与治理系统 | 小风险资本 Campaign 的快速试错-审查研究系统 |
| 阶段标签 | BRC Reset / Opportunity Structure Discovery v0 | 无正式阶段标签；当前实质为 "broad screen completed, 3 candidates pending cost enrichment" |
| 自动化程度 | 暗示系统级自动化能力 | 明确 NOT a fully automated general strategy system |
| 试验机制 | 未明确定义 | bounded live trial 需 Owner risk acceptance |

---

## 2. 当前仓库状态

### 2.1 Git 分支

- **Branch**: `codex/brc-owner-console-v0`
- **Main branch**: `main`

### 2.2 Git Status（2026-05-29）

**已跟踪文件修改（4 个，未暂存）**:
- `docs/ops/live-safe-v1-progress.md` (+23 行)
- `docs/ops/live-safe-v1-task-board.md` (+1 行)
- `docs/ops/project-roadmap-v2.md` (+31 行 — 含 Owner 2026-05-29 amendment)
- `src/infrastructure/pg_models.py` (+500 行 — 新 ORM 模型)

**Untracked 文件**: 60+ 文件，包括：
- 6 个 migration (022-027)
- 8 个 domain 文件
- 4 个 PG repository
- 5 个 application service
- 8 个 script
- 14 个 test 文件
- knowledge-pack 目录

### 2.3 最近 20 个 commit

```
559c95e docs(brc): record R5 admission and read-only state
860772e fix(brc): gate signal execution by permission
3e22b6a feat(brc): add live read-only detection runner
668acba feat(brc): add admission-backed runtime evidence chain
50cb1ba docs(brc): record tf001 full-chain validation stage
31075d1 test(brc): add tf001 carrier full-chain smoke
6d10165 feat(brc): add tf001 carrier playbook
785ef23 test(brc): add tf001 carrier decision review smoke
3eeef88 feat(brc): add owner console evidence hardening
769d902 feat(brc): harden owner console operation workbench
f47d5c0 feat(brc): add owner console operation workbench
ea26539 feat(brc): add owner console review dashboard
5585735 feat(brc): add owner console campaign overview
e583229 feat(brc): add owner console login gate
d96d2a4 docs(brc): record owner console v0 completion
6b7e8e2 feat(brc): add brc console v0 frontend
c10df95 feat(brc): add brc console v0 api layer
5e1f3c0 feat(brc): add langgraph operator workflow
fe33e45 feat(brc): add brc r3 operator layer
120a4c1 fix(brc): harden tf001 carrier pipeline
```

最近 20 个 commit 全部在 BRC 框架内（`brc` prefix），无任何生产部署 / live activation commit。

---

## 3. 定位候选

### 候选 A：快速试错-审查研究系统（推荐）

**来源**: 2026-05-29 Owner amendment in `project-roadmap-v2.md`
**置信度**: HIGH
**表述**: "a fast trial-and-review research system for small risk-capital Campaigns"
**证据强度**: Owner 直接声明，有明确的 diff 证据

### 候选 B：BRC 治理框架 + broad OHLCV 筛选完成 + 3 个未验证候选

**来源**: `reports/directional-opportunity-broad-smoke-20260529/` + `docs/ops/live-safe-v1-progress.md`
**置信度**: HIGH
**表述**: BRC governance framework with broad OHLCV screening phase completed, 3 unvalidated trial candidates selected (MI-001 BNB long, MI-001 SOL long, VI-001 ETH long)
**证据强度**: 代码 + 报告 + git history 均支持

### 候选 C：pre-trial 基础设施，存在已知 account_equity blocker

**来源**: `reports/directional-opportunity-broad-smoke-20260529/pg_trial_readiness_fact_check.md`
**置信度**: HIGH
**表述**: 试验准备阶段，已知阻断项为 account_equity 读取不可用
**证据强度**: fact check 报告明确标识 blocker

### 候选 D：Opportunity Structure Discovery v0（旧定位，已过期）

**来源**: knowledge-pack PROJECT_OVERVIEW.md
**置信度**: LOW（已被 Owner 否定）
**表述**: 处于 Opportunity Structure Discovery v0
**证据强度**: 旧文档，Owner 标记为错误

**结论**: 采用候选 A（Owner 原始表述），辅以候选 B 和 C 作为当前事实基线。

---

## 4. 阶段判断

### 4.1 当前实质阶段

基于代码、git history 和报告的客观判断：

**"BRC 治理框架已实现 + broad OHLCV 筛选已完成 + 3 个候选待成本/基线补充 + 试验准备存在已知 blocker"**

### 4.2 阶段分解

| 子阶段 | 状态 | 证据 |
|---|---|---|
| BRC 治理框架（campaign lifecycle + state machine + operation layer） | 已实现，testnet 验证通过 | commit history, task board |
| Owner Console v0（5 个 P0 页面） | 已实现 | commit `e583229`~`d96d2a4` |
| Admission Gate Phase 1-17 | 元数据操作完成 | commit `668acba`, progress log |
| TF-001 Carrier Full-chain Smoke | 通过 | commit `31075d1`, `50cb1ba` |
| Broad OHLCV Smoke Screen (BRC-R5-003) | 完成，3 候选选出 | `reports/directional-opportunity-broad-smoke-20260529/` |
| Cost/baseline enrichment for candidates | 未开始 | — |
| Trial readiness (account_equity, signal-to-intent) | 存在已知 blocker | `pg_trial_readiness_fact_check.md` |
| Signal-to-trade conversion | 未实现 | `execution_permission.py` 最高到 INTENT_RECORDING |

### 4.3 Owner 修正后的阶段定义

不再使用 "Opportunity Structure Discovery v0" 标签。当前可描述为：

> **BRC fast trial-and-review research system — broad screen phase completed, pre-trial enrichment pending**

---

## 5. 能力边界表

| 能力 | 是否具备 | 证据 | 备注 |
|---|---|---|---|
| 实盘交易 | **NO** | ADR-0009 禁止；无 live infrastructure wired | 绝对禁止 |
| testnet 交易 | **YES** | Binance testnet，受控 endpoint，多次验证 | 当前基线为 scoped verification + hard safety gates，不再 blanket Owner authorization |
| 自动化策略执行 | **NO** | `auto_within_budget_enabled=False`, `auto_execution_enabled=False`（hardcoded） | `bounded_risk_campaign_service.py` |
| signal-to-order 链路 | **NO** | 未实现 | — |
| signal-to-intent 链路 | **PARTIAL** | `brc_trial_trade_intents` 表存在，但最远状态为 `signal_evaluated_no_intent` | 无自动 signal→intent 转换 |
| account equity 读取 | **YES when cached** | cached `AccountSnapshot` 可映射 `wallet_equity` / `available_margin` | 缺失或 stale 时是 profile/preflight-scoped blocker |
| account balance 读取 (exchange) | **YES** | `AccountService.get_balance()` 调用 exchange gateway | 需 API key + testnet |
| account facts (positions/orders, PG) | **YES** | `_account_facts()` 有 local PG 路径 | positions 和 orders 有 dual path |
| BRC campaign lifecycle | **YES** | campaign state machine + PG persistence | testnet verified |
| Admission Gate metadata operations | **YES** | Phase 1-17 完成 | 元数据操作，无 runtime effect |
| Owner Console | **YES** | 5 个 P0 页面，浏览器验证 | 本地开发版本 |
| LangGraph LLM operator | **YES** | `brc_operator_workflow.py` | advisory only，不能执行交易 |
| Backtester engine | **YES** | `backtester.py`，多次使用 | research-only |
| Broad OHLCV screening | **YES** | BRC-R5-003 完成 | 9 variants × 4 assets × 2 sides |
| PG runtime state persistence | **YES** | 21 tracked migrations (001-021) | campaign/admission/operation tables |
| PG historical research tables | **PARTIAL** | ORM models in pg_models.py (unstaged), migrations 022-027 (untracked) | 未集成到 tracked codebase |
| Scheduler / daemon | **NO** (process-local only) | `src/main.py` 进程内调度 | 无独立 scheduler/daemon |
| GKS (Global Kill Switch) | **YES** | fail-closed 设计 | commit `bc7e2ad` |
| Periodic reconciliation | **YES** | testnet verified | — |
| Execution permission gating | **YES** | `execution_permission.py` | READ_ONLY / INTENT_RECORDING / EXECUTION_INTENT_ALLOWED / ORDER_CAPABLE |

---

## 6. 已过期结论表

| 来源 | 原结论 | 过期原因 | 当前事实 |
|---|---|---|---|
| PROJECT_OVERVIEW.md | "BRC Reset / Opportunity Structure Discovery v0" | Owner 2026-05-29 明确否定 | "fast trial-and-review research system for small risk-capital Campaigns" |
| PROJECT_OVERVIEW.md | "27 个 Alembic migration（001-027）" | 只有 001-021 是 git tracked | 21 tracked + 6 untracked |
| FACT_REGISTRY.md F-011 | "项目有 27 个 migration" | 同上 | 同上 |
| FACT_REGISTRY.md UF-001 | "Strategy Family Registry PG 链路待确认" | ORM 存在但 untracked，无 tracked 代码导入 | 未集成 |
| FACT_REGISTRY.md UF-002 | 暗示 "exchange + PG dual path" for account facts | `account_service.py` 只有 exchange 路径；PG dual path 仅限 positions/orders | account equity 为 not_available |
| MODULE_MAP.md Section 4-5 | 新 research/evaluation 模块集成状态 | 所有相关文件 untracked，无 tracked 代码导入 | 未集成 |
| CURRENT_STATE_AND_NEXT_ACTIONS.md CONF-002/003 | "待确认" | 确认结果：未集成 | 应改为 "未集成" |
| CURRENT_STATE_AND_NEXT_ACTIONS.md §7 | "27 Alembic migrations" | 同 F-011 | 21 tracked |
| knowledge-pack 整体 | 混合 tracked/untracked 文件作为项目能力 | untracked 文件在 git 层面不存在 | 所有 022-027 相关能力未集成 |

---

## 7. 新基线草稿

### 7.1 一句话定位

> Bounded Risk Campaign (BRC) 快速试错-审查研究系统，当前完成 broad OHLCV 筛选阶段，3 个候选待成本/基线补充，试验准备存在 account_equity 已知 blocker。

### 7.2 当前核心事实

1. **项目不是全自动策略系统** — Owner 2026-05-29 明确
2. **BRC 治理框架已实现** — campaign lifecycle, state machine, admission gate, operation layer, owner console, LLM operator
3. **实盘交易被绝对禁止** — ADR-0009，除非 Owner 单独授权
4. **testnet 交易能力已验证** — Binance testnet，受控场景，多次通过
5. **broad OHLCV 筛选已完成** — BRC-R5-003，9 variants × 4 assets × 2 sides，3 候选选出
6. **3 候选未做成本/基线补充** — 有意不完整：无 slippage/funding/baseline
7. **signal-to-trade 转换未实现** — 最远到 signal_evaluated_no_intent
8. **account_equity 读取不可用** — 已知试验准备 blocker
9. **auto_within_budget 和 auto_execution 永远为 False** — 硬编码
10. **022-027 migration + 相关模块未集成** — untracked，无 tracked 代码导入
11. **21 个 tracked migration 是当前可部署 schema** — 001-021
12. **无 production deployment 能力** — 本地运行，无 cloud/daemon

### 7.3 当前绝对禁止事项

| ID | 禁止事项 | 原因 |
|---|---|---|
| FORBID-001 | 实盘交易 | ADR-0009 |
| FORBID-002 | 使用真实资金下单 | ADR-0009 |
| FORBID-003 | 自动化策略执行 | 无 runtime-eligible strategy |
| FORBID-004 | 修改 execution permission | Codex-owned core file |
| FORBID-005 | 提现/transfer | out-of-scope |
| FORBID-006 | 策略自提升 | ADR-0012 |
| FORBID-007 | 绕过 Operation Layer | ADR-0012 |
| FORBID-008 | 把 research-only 结果用于实盘 | research-runtime isolation |
| FORBID-009 | 修改 API key / credentials | 安全风险 |
| FORBID-010 | 自动化 symbol/side/leverage 扩展 | ADR-0012 |

### 7.4 当前下一步

| 优先级 | 动作 | 类型 | 安全边界 |
|---|---|---|---|
| P0 | 3 个 trial candidate 补充成本/滑点/资金费率建模 | research-only | no execution, no trading |
| P0 | 3 个 trial candidate 做随机入场/持有基线对比 | research-only | no execution |
| P1 | 决定 022-027 和相关 untracked 文件是否应提交 | Owner decision | — |
| P1 | 解决 account_equity blocker（确定读取来源） | infrastructure | no execution |
| P1 | 决定 signal-to-intent conversion 是否在当前 scope | Owner decision | — |
| P2 | Owner 审查 3 个 trial candidate 事件样本 | owner review | read-only |

---

## 8. 下一轮建议

### 8.1 立即可做（read-only）

1. **更新 knowledge-pack 6 份文档**，反映 Owner 2026-05-29 修正和 tracked-only 事实
2. **读取 3 个 trial candidate 的报告**，为 Owner 审查准备摘要
3. **审查 account_equity blocker 的可选解法**（PG 路径 vs exchange 路径 vs mock 路径）

### 8.2 需要 Owner 决策

4. 是否将 022-027 + 相关文件提交到 git
5. 是否在当前 scope 解决 account_equity blocker
6. 是否在当前 scope 实现 signal-to-intent conversion
7. 是否接受 knowledge-pack 的 tracked-only 重写方向

### 8.3 不建议

- 不建议在未解决成本/基线补充前推进 trial
- 不建议在未确认 account_equity 来源前设计 trial execution
- 不建议使用 "Opportunity Structure Discovery v0" 标签
- 不建议将 untracked 文件视为已集成能力
