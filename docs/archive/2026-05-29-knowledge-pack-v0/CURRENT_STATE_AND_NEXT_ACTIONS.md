> [!WARNING]
> **PARTIALLY SUPERSEDED**: This document remains useful as historical context, but current readiness and blockers are now tracked in:
> `docs/ops/knowledge-pack/CURRENT_READINESS_BLOCKERS.md`.
> Section 7 ("27 Alembic migrations") is stale; correct count is 21 tracked + 6 untracked.

---

# CURRENT_STATE_AND_NEXT_ACTIONS.md

Last updated: 2026-05-29
Status: research-only snapshot

---

## 1. 当前最近完成的事项

| ID | 事项 | 类型 | 结论 | 证据 | 复核 |
|---|---|---|---|---|---|
| DONE-001 | BRC-R5-003 Broad OHLCV-only Directional Smoke Screen | research | 3 个 trial candidate selected (MI-001 BNB/SOL long, VI-001 ETH long) | `reports/directional-opportunity-broad-smoke-20260529/` | 是：需要成本/基线补充 |
| DONE-002 | BRC-R5-002 Admission Gate Phase 1-17 | implementation | 元数据操作链完成 | `docs/ops/live-safe-v1-progress.md` 2026-05-27 | 是：端到端链路验证 |
| DONE-003 | BRC-R5-001E TF-001 Carrier Full-chain Smoke | implementation | 通过 | `docs/ops/live-safe-v1-progress.md` 2026-05-27 | 否 |
| DONE-004 | BRC-CONSOLE-V0 Owner Console v0 | implementation | 5 P0 pages 实现，浏览器验证通过 | `docs/ops/live-safe-v1-progress.md` 2026-05-26 | 否 |
| DONE-005 | BRC-R3 LangGraph LLM Operator Gateway | implementation | 实现 | `docs/ops/live-safe-v1-progress.md` 2026-05-26 | 否 |
| DONE-006 | PLC Phase 5E BTC/ETH Testnet Rehearsal | testnet | 通过 | `docs/ops/live-safe-v1-progress.md` 2026-05-25 | 否 |
| DONE-007 | Campaign State Machine (PLC-STATE-001-004) | implementation | 实现 | `docs/ops/live-safe-v1-progress.md` 2026-05-25 | 否 |

---

## 2. 当前正在确认的事项

| ID | 事项 | 为什么重要 | 当前进展 | 卡点 | 下一步 |
|---|---|---|---|---|---|
| CONF-001 | 3 个 trial candidate 补充成本/基线建模 | 决定是否值得继续深化 | broad smoke screen 完成，无成本建模 | Owner 需确认优先级 | cost/baseline research |
| CONF-002 | Strategy Family Registry PG 链路 | 决定策略族元数据是否可持久化 | migration 022 存在 | 未确认端到端验证 | read-only fact check |
| CONF-003 | Historical Research Sampling 端到端 | 决定研究采样能力是否可用 | service/repository 存在 | 未确认运行验证 | read-only fact check |
| CONF-004 | Admission Gate 端到端链路 | 决定 admission 是否可实际使用 | Phase 1-17 元数据完成 | signal-to-trade 转换未实现 | 取决于下一个 runtime phase |
| CONF-005 | Migration 022-027 状态 | 决定最新 schema 是否已应用 | 文件存在，untracked | 需确认 git/PG 状态 | read-only fact check |

---

## 3. 当前明确不能做的事

| ID | 事项 | 不能做的原因 | 安全边界 |
|---|---|---|---|
| FORBID-001 | 实盘交易 | ADR-0009 禁止，除非 Owner 单独明确授权 | 绝对禁止 |
| FORBID-002 | 使用真实资金下单 | 同上 | 绝对禁止 |
| FORBID-003 | 自动化策略执行 | 当前无 runtime-eligible strategy | 绝对禁止 |
| FORBID-004 | 修改 execution permission | Core file，Codex-owned | 需 Codex task card |
| FORBID-005 | 提现/transfer | 明确 out-of-scope | 绝对禁止 |
| FORBID-006 | 策略自提升 | ADR-0012 禁止 | 绝对禁止 |
| FORBID-007 | 绕过 Operation Layer | ADR-0012 禁止 | 绝对禁止 |
| FORBID-008 | 把 research-only 结果用于实盘 | research-runtime isolation | 永久规则 |
| FORBID-009 | 修改 API key / credentials | 安全风险 | 绝对禁止 |
| FORBID-010 | 自动化 symbol/side/leverage 扩展 | ADR-0012 禁止 | 绝对禁止 |

---

## 4. 当前下一步最合理动作

| 优先级 | 下一步 | 类型 | 目标 | 安全边界 |
|---|---|---|---|---|
| P0 | 3 个 trial candidate (MI-001 BNB/SOL, VI-001 ETH) 补充成本/滑点/资金费率建模 | research-only | 判断候选是否值得深化 | no execution, no trading |
| P0 | 3 个 trial candidate 做随机入场/持有基线对比 | research-only | 验证是否有 alpha vs beta | no execution |
| P1 | 验证 Strategy Family Registry PG 链路 | read-only fact check | 确认基础设施完整性 | no mutation |
| P1 | 验证 migration 022-027 是否已应用到 PG | read-only fact check | 确认 schema 状态 | no mutation |
| P1 | 验证 historical research sampling 端到端 | read-only fact check | 确认研究工具可用性 | no mutation |
| P2 | Owner 审查 3 个 trial candidate 事件样本 | owner review | 决定哪些值得下一步 | read-only |

---

## 5. 给 Codex 的下一步提示词

```text
## Task Context
Project: Bounded Risk Campaign Research System
Current stage: Opportunity Structure Discovery v0
Safety boundary: research-only, no execution, no trading, no real live

## Task
Continue broad screening follow-up. The latest broad OHLCV smoke screen
(BRC-R5-003) selected 3 trial candidates: MI-001 BNB long, MI-001 SOL long,
VI-001 ETH long. Evidence is intentionally incomplete (no cost/slippage/funding).

## Next Step
Design a cost/baseline enrichment plan for these 3 candidates. The plan should:
1. Add realistic cost model (slippage, funding rate, exchange fee)
2. Add random-entry + hold baseline comparison
3. Add rolling campaign ruin-rate estimate
4. Keep all work research-only / no PG persistence / no admission / no runtime

## Safety
- research-only
- no execution
- no trading
- no exchange API calls
- no PG mutation for runtime tables
- no strategy promotion
- read-only fact checks on infrastructure are OK

## Allowed files
- docs/ops/
- reports/
- scripts/
- src/application/backtester.py (read only)
- src/domain/ (read only)

## Forbidden files
- src/infrastructure/exchange_gateway.py
- src/application/execution_orchestrator.py
- src/application/order_lifecycle_service.py
- src/main.py
- migrations/ (unless explicitly approved)
```

---

## 6. 给 Claude 的下一步提示词

```text
## Task Context
Project knowledge pack is at docs/ops/knowledge-pack/
6 documents created: PROJECT_OVERVIEW, FACT_REGISTRY, MODULE_MAP,
STRATEGY_RESEARCH_HISTORY, CURRENT_STATE_AND_NEXT_ACTIONS, PROMPT_LIBRARY.

## Next Step
Incremental fact-check pass:
1. Verify Strategy Family Registry PG chain (migration 022 + repository)
2. Verify Historical Research Sampling PG chain (migration 024 + repository)
3. Verify Historical Signal Evaluation PG chain (migration 025 + repository)
4. Update FACT_REGISTRY.md with findings

## Safety
- read-only
- no code changes
- no PG mutation
- no exchange calls
- only read files and verify existence/structure
```

---

## 7. 给 ChatGPT 的交接摘要

```text
# Project Handoff Summary

## What is this project?
A crypto derivatives personal leveraged campaign research & governance system.
Currently NOT production-ready. All work is research-only.

## Current Stage
"Opportunity Structure Discovery v0" — broad OHLCV screening across 9 strategy
variants × 4 assets (BTC/ETH/SOL/BNB) × 2 sides. 3 trial candidates selected.

## Key Architecture
- Bounded Risk Campaign (BRC) framework: isolated risk capital → playbook →
  bounded attempts → hard risk envelope → profit-protect/loss-lock → evidence
- Binance testnet-first / production-blocked
- Domain-driven design (domain/application/infrastructure/interfaces)
- PostgreSQL persistence (27 Alembic migrations)
- Local Owner Console (FastAPI backend + Vite frontend)
- LangGraph LLM operator (advisory only, cannot execute trades)

## What Works
- BRC campaign lifecycle (testnet verified)
- Local console with TOTP auth
- Campaign state machine with PG persistence
- Global Kill Switch (fail-closed)
- Periodic reconciliation
- Backtester engine
- Broad OHLCV smoke screen

## What Doesn't Work Yet
- No production/live trading capability
- No runtime-eligible strategy candidate
- CPM-1 (ETH pullback) is PAUSED (OOS negative)
- Admission Gate Phase 1-17 are metadata-only (no signal-to-trade conversion)
- No cost/baseline enrichment for broad smoke candidates

## Critical Safety Rules
- Real live trading: PROHIBITED unless Owner explicitly authorizes
- LLM: advisory only, cannot write/trade/confirm
- Execution: protected by GKS, startup guard, campaign state, exposure caps
- Research-runtime isolation: permanent rule

## Read Order
1. docs/ops/knowledge-pack/PROJECT_OVERVIEW.md
2. docs/ops/knowledge-pack/CURRENT_STATE_AND_NEXT_ACTIONS.md
3. docs/ops/knowledge-pack/FACT_REGISTRY.md
4. docs/ops/knowledge-pack/MODULE_MAP.md
5. docs/ops/knowledge-pack/STRATEGY_RESEARCH_HISTORY.md
6. docs/ops/knowledge-pack/PROMPT_LIBRARY.md
```
