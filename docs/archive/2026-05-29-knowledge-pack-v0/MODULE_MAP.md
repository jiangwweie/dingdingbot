> [!WARNING]
> **SUPERSEDED / PARTIALLY STALE**: This module map mixes tracked and untracked files.
> Current baseline: `docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md`.
> Untracked files must not be treated as integrated capabilities.
> See `docs/ops/knowledge-pack/TRUTH_REBUILD_PASS1.md` for specific stale claims.

---

# MODULE_MAP.md

Last updated: 2026-05-29
Status: research-only snapshot

---

## 1. 总览

| 模块 | 职责 | 当前状态 | 关键风险 | 是否已确认 |
|---|---|---|---|---|
| Domain Layer | 纯业务模型，无 I/O | 已实现 | 无直接 I/O 风险 | HIGH |
| Application Layer | 服务编排、业务流程 | 大部分已实现 | 部分端到端链路未验证 | MEDIUM-HIGH |
| Infrastructure Layer | PG 持久化、交易所连接、日志 | 已实现 | exchange_gateway 涉及 API key | HIGH |
| Interfaces Layer | API、认证、前端 | 已实现 | 本地版本，无 cloud hardening | HIGH |
| Frontend (BRC Console) | Owner 控制台 | 已实现 | 本地开发版本 | HIGH |

---

## 2. Data Layer

### 2.1 模块职责
历史 OHLCV 数据管理、K 线目录、数据导入工具。

### 2.2 关键文件路径
- `src/domain/historical_ohlcv.py`
- `src/infrastructure/pg_historical_ohlcv_catalog_repository.py`
- `src/infrastructure/pg_historical_data_repository.py`
- `src/infrastructure/historical_data_repository.py`
- `scripts/import_sqlite_klines_to_pg.py`
- `scripts/te005_import_pre2021_klines.py`
- Migration 023: `create_brc_historical_ohlcv_catalog`

### 2.3 核心类/函数
- 未确认具体类名，需代码核验

### 2.4 上游输入
- SQLite 历史 K 线数据
- 外部数据导入脚本

### 2.5 下游输出
- PG OHLCV catalog
- 回测引擎
- 研究采样服务

### 2.6 谁调用它
- `src/application/backtester.py`
- `src/application/historical_research_sampling_service.py`
- `scripts/` 下的多个研究脚本

### 2.7 它调用谁
- PG 数据库

### 2.8 是否只读
- Repository 层面：读写（导入时写入，查询时读取）
- 运行时：只读

### 2.9 是否可能触发外部 API
- 否（本地数据管理）

### 2.10 是否可能触发交易
- 否

### 2.11 是否依赖 API key
- 否

### 2.12 当前状态
- Migration 已存在，repository 已实现
- 数据导入脚本已存在
- 端到端验证状态：未确认

### 2.13 风险点
- 数据完整性（BNB 覆盖率未确认）
- 数据导入后是否经过质量检查

### 2.14 待确认事项
- PG OHLCV catalog 是否已填充 BTC/ETH/SOL/BNB 数据
- 数据质量检查是否已执行

---

## 3. PG Persistence Layer

### 3.1 模块职责
所有 PG 持久化逻辑：ORM 模型、Alembic migration、Repository 实现。

### 3.2 关键文件路径
- `src/infrastructure/pg_models.py` — 核心 ORM 模型（被修改中）
- `src/infrastructure/database.py` — 数据库连接
- `migrations/versions/` — 27 个 Alembic migration
- Repository 文件列表：
  - `pg_order_repository.py`, `pg_position_repository.py`, `pg_signal_repository.py`
  - `pg_brc_campaign_repository.py`, `pg_brc_admission_repository.py`
  - `pg_brc_operation_repository.py`, `pg_campaign_state_repository.py`
  - `pg_daily_risk_stats_repository.py`, `pg_execution_intent_repository.py`
  - `pg_global_kill_switch_repository.py`, `pg_reconciliation_repository.py`
  - `pg_reconciliation_read_model_repository.py`, `pg_config_entry_repository.py`
  - `pg_config_profile_repository.py`, `pg_config_snapshot_repository.py`
  - `pg_runtime_profile_repository.py`, `pg_research_repository.py`
  - `pg_backtest_repository.py`, `pg_execution_recovery_repository.py`
  - `pg_historical_ohlcv_catalog_repository.py`
  - `pg_historical_research_sampling_repository.py`
  - `pg_historical_signal_evaluation_repository.py`
  - `pg_strategy_family_registry_repository.py`

### 3.3 核心类/函数
- `PGCoreBase` — SQLAlchemy declarative base
- 各 Repository 类

### 3.4 上游输入
- Application Layer 各服务

### 3.5 下游输出
- PostgreSQL 数据库

### 3.6 调用关系
- 被 Application Layer 各服务调用
- 调用 PostgreSQL

### 3.7 是否只读
- 否。Repository 包含读写操作。
- Migration 是写操作。

### 3.8 是否可能触发外部 API
- 否（仅 PG）

### 3.9 是否可能触发交易
- 否

### 3.10 是否依赖 API key
- 依赖 PG 连接字符串（`.env` 中配置）

### 3.11 当前状态
- 27 个 migration 已存在
- 大部分 repository 已实现
- 部分新 migration（022-027）为 untracked 状态

### 3.12 风险点
- Migration 022-027 为 untracked，未确认是否已应用到 PG
- 旧 migration（002）曾有 clean-install 问题，已修复
- `alembic upgrade head` 在旧 schema 上可能遇到迁移顺序问题

### 3.13 待确认事项
- Migration 022-027 是否已加入 git
- 新 migration 是否已通过 `alembic upgrade head` 验证
- 当前 PG schema head revision 是什么

---

## 4. Strategy Research Layer

### 4.1 模块职责
策略方向研究、信号生成、回测执行、历史评估。

### 4.2 关键文件路径
- `src/domain/strategy_engine.py`
- `src/domain/strategies/engulfing_strategy.py`
- `src/domain/dca_strategy.py`
- `src/domain/indicators.py`
- `src/domain/strategy_family_registry.py`
- `src/domain/strategy_family_signal.py`
- `src/domain/historical_signal_evaluation.py`
- `src/domain/historical_research_sampling.py`
- `src/domain/directional_opportunity_pack.py`
- `src/application/backtester.py`
- `src/application/research_control_plane.py`
- `src/application/research_specs.py`
- `src/application/historical_research_sampling_service.py`
- `src/application/historical_signal_evaluation_service.py`
- `src/application/historical_signal_input_builder.py`
- `scripts/analyze_broad_directional_smoke.py`
- `scripts/research_directional_opportunity_smoke.py`
- `scripts/run_cpm_ro001_historical_experiment.py`
- `scripts/run_cpm_ro001_regime_split_experiment.py`

### 4.3 核心类/函数
- `Backtester` — 回测引擎
- `StrategyEngine` — 策略引擎
- `MatchingEngine` — 匹配引擎

### 4.4 上游输入
- OHLCV 数据（PG 或本地文件）
- 策略参数/配置
- 研究规范（ResearchSpecs）

### 4.5 下游输出
- 回测报告
- 历史评估结果
- 策略信号

### 4.6 调用关系
- 被 scripts/ 和 research API 调用
- 调用 Infrastructure Layer（数据读取）

### 4.7 是否只读
- 回测过程：只读（不修改 PG 运行时状态）
- 评估结果可能写入 PG

### 4.8 是否可能触发外部 API
- 否（纯本地计算）

### 4.9 是否可能触发交易
- 否（research-runtime isolation）

### 4.10 是否依赖 API key
- 否

### 4.11 当前状态
- 回测引擎已实现
- broad smoke screen 已执行
- 历史评估服务已实现
- 端到端验证状态：部分（broad smoke screen 已运行）

### 4.12 风险点
- research-runtime isolation 是永久安全规则
- 回测引擎不是完整交易模拟器（无 tick/orderbook）

### 4.13 待确认事项
- 历史评估服务端到端验证状态
- 研究采样服务端到端验证状态

---

## 5. Backtest / Evaluation Layer

### 5.1 模块职责
策略回测、样本外验证、压力测试、方向评估。

### 5.2 关键文件路径
- `src/application/backtester.py` — 主回测引擎
- `src/application/backtest_config.py` — 回测配置
- `src/domain/matching_engine.py` — 匹配引擎
- `src/infrastructure/pg_backtest_repository.py` — 回测结果持久化
- `scripts/run_cpm1_2021_oos.py`, `scripts/run_cpm1_2022_oos.py` — CPM-1 OOS 脚本
- `reports/` — 回测报告目录

### 5.3 当前状态
- 引擎已实现并多次使用
- CPM-1 OOS（2021/2022）已执行
- Direction A frozen diagnostic（ETH/BTC/SOL）已执行
- broad smoke screen（9 variants × 4 assets × 2 sides）已执行

### 5.4 风险点
- 回测成本模型的准确性（slippage=0 问题已修复，但其他成本建模需确认）
- 回测不等于实盘表现

---

## 6. BRC / Admission Layer

### 6.1 模块职责
Bounded Risk Campaign 治理、Admission Gate、操作层、LLM 工作流。

### 6.2 关键文件路径
- `src/domain/bounded_risk_campaign.py` — BRC 领域模型
- `src/domain/brc_admission.py` — Admission 领域模型
- `src/application/bounded_risk_campaign_service.py` — BRC 服务
- `src/application/brc_admission_service.py` — Admission 服务
- `src/application/brc_operation_layer.py` — 操作层
- `src/application/brc_operator_workflow.py` — LangGraph LLM 工作流
- `src/application/brc_admission_risk_capital.py` — 风险资本适配器
- `src/application/brc_live_read_only_detection_runner.py` — 实盘只读检测
- `src/infrastructure/pg_brc_campaign_repository.py`
- `src/infrastructure/pg_brc_admission_repository.py`
- `src/infrastructure/pg_brc_operation_repository.py`
- Migrations 012-021

### 6.3 是否只读
- BRC 服务：读写（创建 campaign、记录事件）
- Admission 服务：读写（记录 admission facts/decisions）
- Operation Layer：读写（记录操作日志、审查决策）
- LLM 工作流：读写（记录 intents/workflow runs）

### 6.4 是否可能触发外部 API
- BRC test endpoints 可能触发 Binance testnet（受控场景）
- LLM 工作流的 testnet intent 可能触发 Binance testnet

### 6.5 是否可能触发交易
- 受控 testnet ENTRY/CLOSE（需要 runtime control + test signal injection + testnet）
- 不涉及 real live

### 6.6 当前状态
- R0/R1 已实现并 testnet 验证
- R2 操作层已实现
- R3 LLM 工作流已实现
- R4 控制台已实现
- R5 Admission Phase 1-17 已实现（元数据操作）
- TF-001 carrier full-chain smoke 通过

---

## 7. Account Facts Layer

### 7.1 模块职责
账户事实读取、账户风险评估、账户对账。

### 7.2 关键文件路径
- `src/application/account_service.py`
- `src/application/account_risk_service.py`
- `src/application/reconciliation.py`
- `src/application/periodic_reconciliation.py`
- `src/application/startup_reconciliation_service.py`
- `src/infrastructure/exchange_gateway.py`（账户相关读取）

### 7.3 是否只读
- 账户事实读取：是（只读查询交易所 + PG）
- 账户风险评估：是（计算，不修改状态）
- 对账：是（只读比较交易所 vs PG 状态）

### 7.4 是否可能触发外部 API
- 是（查询 Binance testnet 账户状态）

### 7.5 是否可能触发交易
- 否

### 7.6 是否依赖 API key
- 是（Binance API key/secret）

### 7.7 当前状态
- Account risk service 已实现
- Reconciliation 已实现并 testnet 验证
- Account facts evidence metadata 已实现（BRC-R5-001C）

---

## 8. Exchange Service Layer

### 8.1 模块职责
交易所连接、订单管理、市场数据获取。

### 8.2 关键文件路径
- `src/infrastructure/exchange_gateway.py` [Codex-owned]

### 8.3 是否只读
- 否。可下单、取消订单、查询账户。

### 8.4 是否可能触发外部 API
- 是。通过 ccxt 连接 Binance（testnet/live）。

### 8.5 是否可能触发交易
- 是。受 GKS、startup guard、campaign state、exposure caps 保护。

### 8.6 是否依赖 API key
- 是（Binance API key/secret）

### 8.7 当前状态
- 已实现并多次 testnet 验证
- 受控 testnet 场景下运行

### 8.8 风险点
- **最高风险模块**。任何对 exchange_gateway 的修改必须极其谨慎。
- TESTNET/LIVE 环境切换由 `.env` 控制

---

## 9. Execution Layer

### 9.1 模块职责
执行编排、订单生命周期、仓位预测、资本保护。

### 9.2 关键文件路径
- `src/application/execution_orchestrator.py` [Codex-owned]
- `src/application/order_lifecycle_service.py` [Codex-owned]
- `src/application/position_projection_service.py` [Codex-owned]
- `src/application/capital_protection.py` [Codex-owned]
- `src/application/execution_permission.py`

### 9.3 是否只读
- 否。核心执行链路，可创建/提交/取消订单。

### 9.4 是否可能触发外部 API
- 间接通过 ExchangeGateway。

### 9.5 是否可能触发交易
- **是。这是最高风险区域。**

### 9.6 保护机制
- GKS (Global Kill Switch) — fail-closed
- Startup Trading Guard — 默认 blocked
- Campaign State — 默认 observe
- Account Risk Service — 可阻断新 entry
- Exposure Caps — 固定上限
- Daily Risk Stats — 日亏损/交易次数限制
- Once-per-session guard（受控 close）
- Controlled endpoint 要求 testnet + runtime control + test signal injection

### 9.7 当前状态
- 在 Binance testnet 受控场景下多次验证通过
- 不涉及 real live
- **Codex-owned — Claude 不可修改**

---

## 10. Reporting Layer

### 10.1 模块职责
研究报告生成、回测报告、证据包。

### 10.2 关键文件路径
- `reports/` 目录
- `src/application/research_artifacts.py`
- `docs/ops/` 中的研究报告

### 10.3 是否只读
- 是（只生成报告，不修改运行时状态）

### 10.4 当前状态
- 大量研究报告已生成

---

## 11. Scheduler / Worker / Automation Layer

### 11.1 模块职责
运行时任务调度、后台 worker。

### 11.2 关键文件路径
- `src/main.py` — 主入口，启动运行时任务
- `src/application/runtime_context.py` — 运行时上下文

### 11.3 当前状态
- 运行时任务包括：order-watch、periodic reconciliation、protection health monitor、external close monitor
- 进程本地运行，无独立 scheduler/daemon

### 11.4 风险点
- 进程重启后依赖 PG 恢复状态
- 无持久化断路器状态

---

## 12. Unknown / Unclassified Modules

以下模块在材料中出现，但归类不确定：

| 模块 | 路径 | 出现场景 | 待确认 |
|---|---|---|---|
| `src/domain/sol_high_convexity_candidates.py` | domain 层 | 新文件（untracked） | 职责和集成状态 |
| `src/domain/cpm_campaign_exposure_stress.py` | domain 层 | 新文件（untracked） | 与 CPM-1 关系 |
| `src/domain/cpm_campaign_replay.py` | domain 层 | 新文件（untracked） | 回测相关 |
| `src/domain/cpm_historical_evaluator.py` | domain 层 | 新文件（untracked） | 历史评估 |
| `src/domain/cpm_replay_cost_model.py` | domain 层 | 新文件（untracked） | 成本模型 |
| `src/domain/cpm_risk_capital_leverage_replay.py` | domain 层 | 新文件（untracked） | 杠杆回测 |
| `src/domain/forward_outcome_review.py` | domain 层 | 新文件（untracked） | 前瞻结果审查 |
| `src/infrastructure/strategy_signal_v2_observe_sink.py` | infra 层 | StrategySignalV2 观察写入 | 运行时集成状态 |
| `src/application/strategy_signal_v2_observe_writer.py` | app 层 | 同上 | 运行时集成状态 |
| `src/interfaces/operator_auth.py` | interfaces | 操作员认证 | 已确认实现 |
