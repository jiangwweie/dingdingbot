> [!WARNING]
> **SUPERSEDED**: This fact registry is historical and contains stale claims.
> Current fact registry: `docs/ops/knowledge-pack/CURRENT_FACT_REGISTRY.md`.
> Known stale claims: "27 Alembic migrations" should be "21 tracked + 6 untracked (022-027 not integrated)";
> UF-001/002/003/005/006 overstate integration status of untracked modules.

---

# FACT_REGISTRY.md

Last updated: 2026-05-29
Status: research-only snapshot

---

## 1. 说明

本文件只记录项目事实、待确认事实、已否定假设和风险边界。
事实必须有证据来源。没有证据的内容不能进入"已确认事实"。

置信度说明：
- HIGH：有代码、报告、运行结果或明确 commit 支持
- MEDIUM：有文档或 ADR 支持，但未经独立代码验证
- LOW：来自进度记录或对话，需要代码核验

---

## 2. 已确认事实

| ID | 事实 | 证据来源 | 相关文件 | 置信度 | 最近确认时间 |
|---|---|---|---|---|---|
| F-001 | 项目当前阶段为 BRC Reset / Opportunity Structure Discovery v0 | project-roadmap-v2.md | `docs/ops/project-roadmap-v2.md` | HIGH | 2026-05-29 |
| F-002 | 实盘交易（real live trading）被绝对禁止，除非 Owner 单独明确授权 | ADR-0009 | `docs/adr/0009-non-real-live-execution-authorization-boundary.md` | HIGH | 2026-05-25 |
| F-003 | 项目采用 testnet-first / production-blocked 运营姿态 | BRC-R4-004 | `docs/ops/brc-testnet-first-production-blocked-principle.md` | HIGH | 2026-05-26 |
| F-004 | BRC Campaign 在 Binance testnet 上完成受控 ETH+BTC 验证 | BRC-R0R1-001 进度记录 | `docs/ops/live-safe-v1-progress.md` 2026-05-25 | HIGH | 2026-05-25 |
| F-005 | CPM-1 在 2021 和 2022 OOS 均为 OOS_NEGATIVE，已暂停，晋升路径已停止 | CPM-OOS-FAILURE-CLASSIFY-001 | `docs/ops/crypto-pullback-module-v1-oos-failure-classification.md` | HIGH | 2026-05-06 |
| F-006 | Direction A 已归档为 POSITIVE_CROSS_ASSET_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME | DIRA-XA-003 | `docs/ops/direction-a-cross-asset-frozen-diagnostic-result.md` | HIGH | 2026-05 |
| F-007 | 当前无任何策略通过 SRR-002 标准，无 runtime-eligible 策略候选 | SRR-002 | `docs/ops/live-safe-v1-task-board.md` | HIGH | 2026-05-08 |
| F-008 | BRC Admission Gate Phase 1-17 已实现，均为元数据操作 | BRC-R5-002 | `docs/ops/live-safe-v1-progress.md` 2026-05-27 | HIGH | 2026-05-27 |
| F-009 | BRC 控制台 v0 已实现 5 个 P0 页面（Command Center, LLM Copilot, Strategy/Playbook, Risk&Account, Runtime Control） | BRC-CONSOLE-V0 | `docs/ops/live-safe-v1-task-board.md` | HIGH | 2026-05-26 |
| F-010 | 全局断路器 (GKS) 采用 fail-closed 设计 | BRC-AUDIT-001 | commit `bc7e2ad` | HIGH | 2026-05-26 |
| F-011 | 项目有 27 个 Alembic migration（001-027） | migrations/versions/ | `migrations/versions/` | HIGH | 2026-05-28 |
| F-012 | Campaign 状态机使用 table-driven 转换规则，支持 PG 持久化和回放证据 | PLC-STATE-001/002/003/004 | `src/application/campaign_state_service.py` | HIGH | 2026-05-25 |
| F-013 | LLM 工作流采用 LangGraph 架构，LLM 仅限 advisory，不能写/交易/确认 | BRC-R3-001 | `docs/ops/live-safe-v1-progress.md` 2026-05-26 | HIGH | 2026-05-26 |
| F-014 | Daily risk stats 使用 account-level scope（`runtime:default`），跨 profile 共享 | PLC Daily Risk Scope Decision | `docs/ops/live-safe-v1-progress.md` 2026-05-25 | HIGH | 2026-05-25 |
| F-015 | TF-001 Trend Following 是第一个 BRC carrier-validation playbook | STRAT-FAMILY-000 | `docs/ops/strategy-family-map-v0.md` | HIGH | 2026-05-26 |
| F-016 | BRC-R5-003 broad smoke screen 筛选出 3 个 trial candidate：MI-001 BNB long, MI-001 SOL long, VI-001 ETH long | BRC-R5-003 | `reports/directional-opportunity-broad-smoke-20260529/` | HIGH | 2026-05-29 |
| F-017 | broad smoke screen 结果有意不完整：无成本/滑点/资金费率/清算建模 | BRC-R5-003 进度记录 | `docs/ops/live-safe-v1-progress.md` 2026-05-29 | HIGH | 2026-05-29 |
| F-018 | Strategy Family Map 初始状态：TF-001 Intake, CPM-1 Conditional Candidate, VB-001 Reserve, MTF-001 Filter Candidate, ML/HFT Rejected | STRAT-FAMILY-000 | `docs/ops/strategy-family-map-v0.md` | HIGH | 2026-05-26 |
| F-019 | Withdrawal 是 Owner 外部行为，系统不建模 | PLC-SCOPE-001 | `docs/ops/live-safe-v1-progress.md` 2026-05-25 | HIGH | 2026-05-25 |
| F-020 | 操作员认证使用 username + PBKDF2 password + Google Authenticator TOTP + signed HttpOnly cookie | BRC-R4-001 | `docs/ops/live-safe-v1-progress.md` 2026-05-26 | HIGH | 2026-05-26 |

---

## 3. 待确认事实

| ID | 待确认事项 | 为什么重要 | 需要检查哪里 | 优先级 |
|---|---|---|---|---|
| UF-001 | Strategy Family Registry PG 链路是否端到端完整 | 决定策略族元数据是否可持久化和查询 | `src/infrastructure/pg_strategy_family_registry_repository.py`, migration 022 | HIGH |
| UF-002 | Account Facts 完整读取链路（exchange + PG 双路径）是否已验证 | 决定 BRC admission 的 account facts 依赖是否可靠 | `src/application/brc_admission_service.py`, `src/application/account_service.py` | HIGH |
| UF-003 | 历史 OHLCV 数据导入工具是否已运行并导入了 BTC/ETH/SOL/BNB 数据 | 决定 broad smoke screen 数据基础是否可靠 | `scripts/import_sqlite_klines_to_pg.py`, PG `ohlcv_catalog` | HIGH |
| UF-004 | BRC Admission Phase 1-17 的 signal-to-trade-intent 转换是否在任何层已有实现 | 决定 admission 链路是否接近可执行 | `src/domain/brc_admission.py`, `src/application/brc_admission_service.py` | MEDIUM |
| UF-005 | `src/application/historical_signal_evaluation_service.py` 是否已完成端到端验证 | 决定历史信号评估能力是否可用 | 该文件 + 对应 tests | MEDIUM |
| UF-006 | `src/application/historical_research_sampling_service.py` 是否已完成端到端验证 | 决定研究采样能力是否可用 | 该文件 + 对应 tests | MEDIUM |
| UF-007 | `src/infrastructure/pg_historical_signal_evaluation_repository.py` 是否已连接到实际 PG | 决定评估结果持久化是否可用 | 该文件 + migration 025 | MEDIUM |
| UF-008 | BRC Operator Console 的 CSRF/nonce/idempotency 保护是否已实现 | 安全审计记录为 deferred | `docs/ops/brc-pre-deploy-audit-backlog.md` | MEDIUM |
| UF-009 | Direction C (Volatility Contraction) 的 frozen threshold 规范是否已定义 | MTC-003 推荐 Level 3 升级但需要此规范 | `docs/ops/mtc-003-direction-c-volatility-contraction-inspect-v0.md` | LOW |
| UF-010 | BNB 历史 OHLCV 数据覆盖率是否达到 100% | broad smoke screen 包含 BNB，数据完整性影响结果可靠性 | PG `ohlcv_catalog` | MEDIUM |

---

## 4. 已否定假设

| ID | 曾经假设 | 当前结论 | 否定依据 | 后续影响 |
|---|---|---|---|---|
| NF-001 | CPM-1 (ETH Pinbar Pullback) 可作为小实盘候选 | 否定。2021/2022 OOS 均为 OOS_NEGATIVE | CPM-OOS-FAILURE-CLASSIFY-001 | CPM-1 暂停，晋升路径停止 |
| NF-002 | 项目应先证明稳定策略再构建执行平台 | 否定。改为 Bounded Risk Campaign 模型 | ADR-0012 | 产品模型根本转变 |
| NF-003 | 策略应该追求一个 universal strategy | 否定。改为 multiple bounded playbook candidates | strategy-family-map-v0 | 策略方向转变 |
| NF-004 | Direction D (Structured Pullback) 是一个独立方向 | 否定。417 trades, PF 0.985, REJECTED_FROZEN_BASELINE | MTC-006 | pullback-continuation 家族优先级降低 |
| NF-005 | Short-side 4h Breakdown Continuation 有效 | 否定。23 trades, 1 winner, PF 0.317, REJECTED | SSD-003 | short-side breakdown continuation 被拒绝 |
| NF-006 | VEI (Volatility Expansion/Impulse) 有独立 alpha | 否定。所有正 PnL 来自 Direction A echo | VEI-003 | VEI PAUSE_FRAGILE |
| NF-007 | LLM 可以自主执行交易 | 否定。LLM 仅限 advisory，不能写/交易/确认 | ADR-0009, BRC-R5-000 | LLM 角色明确为 assistant/advisor/investigator |

---

## 5. 历史上容易混淆的点

| ID | 容易混淆点 | 正确区分 | 证据 | 风险 |
|---|---|---|---|---|
| C-001 | BRC mock PnL vs 真实收益 | Mock PnL 是 BRC 业务状态证据，不等于真实交易结果 | BRC-R0R1-001 | 可能误判策略有效性 |
| C-002 | Playbook vs Strategy | Playbook 是人类选择的运营框架（可仅观察/纸面/自行判断）；Strategy Contract 是冻结的、验证的、可复现的规则集 | ADR-0012 | 可能混淆治理和执行边界 |
| C-003 | testnet 验证通过 vs production-ready | testnet 验证证明链路可运行，但不等于生产可用 | ADR-0009 | 可能高估系统成熟度 |
| C-004 | runtime_started vs strategy_active | runtime started 是元数据状态，不等于策略已激活 | BRC-R5-002 Phase 12 | 可能误判执行状态 |
| C-005 | carrier_ready vs order-capable | carrier_ready 是元数据，不是运行时启动，不是下单能力 | BRC-R5-002 Phase 7 | 可能误判执行能力 |
| C-006 | signal_evaluated vs trade intent | signal_evaluated_no_intent 不是 trade intent，不是 execution intent | BRC-R5-002 Phase 17 | 可能误判信号到交易的链路完整性 |
| C-007 | historical backtest evidence vs runtime candidate | 历史回测证据只在特定时间窗口/成本假设下有效 | SRR-002 | 可能将研究证据误读为生产就绪 |
| C-008 | 策略族状态 "Conditional Candidate" vs "runtime eligible" | CPM-1 是 Conditional Candidate，不是 runtime eligible | strategy-family-map-v0 | 可能重启已暂停的策略晋升 |

---

## 6. 高风险事实 / 安全边界

| ID | 涉及内容 | 是否只读 | API key | exchange | account | order/execution | 当前结论 | 证据 |
|---|---|---|---|---|---|---|---|---|
| R-001 | ExchangeGateway | 不确定 | 是（需要 Binance API key） | 是 | 是 | 是（可下单） | Codex-owned core file，testnet 受控场景下使用 | `src/infrastructure/exchange_gateway.py` |
| R-002 | ExecutionOrchestrator | 不确定 | 否（间接通过 gateway） | 间接 | 间接 | 是（可执行 ENTRY/EXIT） | Codex-owned core file，受 GKS/startup guard/campaign state 保护 | `src/application/execution_orchestrator.py` |
| R-003 | OrderLifecycleService | 不确定 | 否 | 间接 | 间接 | 是（管理订单状态） | Codex-owned core file | `src/application/order_lifecycle_service.py` |
| R-004 | CapitalProtection | 不确定 | 否 | 否 | 间接 | 间接（保护逻辑） | Codex-owned core file | `src/application/capital_protection.py` |
| R-005 | BRC test endpoints (`/api/runtime/test/brc/*`) | 否 | 否（testnet） | 是（testnet） | 是 | 是（受控 ENTRY/CLOSE） | 需要 `RUNTIME_CONTROL_API_ENABLED`, `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED`, testnet | `src/interfaces/api_console_runtime.py` |
| R-006 | Phase 5E controlled endpoints | 否 | 否（testnet） | 是（testnet） | 是 | 是（受控 ENTRY/CLOSE） | 需要 Phase 5E profile, testnet, once-per-session | `src/interfaces/api_console_runtime.py` |
| R-007 | BRC LLM workflow testnet intent | 否 | 否（testnet） | 是（testnet） | 间接 | 是（受控 testnet rehearsal） | LangGraph 工作流中存在受控 testnet 操作路径 | `src/application/brc_operator_workflow.py` |
| R-008 | `.env.local` 中的 API key/secret | 是（配置） | 是 | 间接 | 间接 | 否 | 本地开发便利，不入 git | `.env.local`（.gitignored） |
| R-009 | GKS (Global Kill Switch) | 是 | 否 | 否 | 否 | 否（阻止执行） | fail-closed 设计，审计写入失败为硬阻断 | `src/application/global_kill_switch.py` |
| R-010 | Startup Trading Guard | 是 | 否 | 否 | 否 | 否（阻止执行） | 默认 blocked，需手动 arm | `src/application/startup_trading_guard.py` |
| R-011 | Position Projection Service | 是（计算） | 否 | 否 | 间接 | 否（预测逻辑） | Codex-owned core file | `src/application/position_projection_service.py` |
| R-012 | Reconciliation | 是 | 否 | 是（只读查询） | 是（只读） | 否 | 周期对账，只读查询交易所状态 | `src/application/periodic_reconciliation.py` |
| R-013 | PG migration（001-027） | 否（写） | 否 | 否 | 否 | 否 | 数据库 schema 变更，需谨慎处理 | `migrations/versions/` |
| R-014 | BRC Admission 写操作 | 否 | 否 | 否 | 间接 | 否（元数据） | admission facts/decisions/bindings 写入 PG | `src/application/brc_admission_service.py` |
| R-015 | Campaign State 写操作 | 否 | 否 | 否 | 否 | 否（元数据） | campaign 状态转换写入 PG | `src/application/campaign_state_service.py` |
