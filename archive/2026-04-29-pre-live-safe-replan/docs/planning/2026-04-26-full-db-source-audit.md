# 全仓 DB 真源审计报告

> **审计日期**: 2026-04-26
> **审计范围**: 全系统持久化对象的真源归属、跨库链路、退役风险
> **约束**: 未改动任何主链代码，未运行完整测试，以代码为准
> **当前分支**: dev

> ⚠️ **状态说明 (2026-04-27)**：本报告编写时 signals 标记为"纯 SQLite / 无 PG 实现"，但此后 live signals + signal_take_profits 已通过 `HybridSignalRepository` + `PgSignalRepository` 迁移到 PG。P0-2（signals 跨库）和 P1-1（signals 无 PG 实现）风险已缓解。报告中关于 signals 位置和迁移状态的描述已过时，仅保留作历史参考。

---

## 0. 结论摘要

### 执行主线 PG 化进度

| 领域 | PG 化状态 | 说明 |
|------|----------|------|
| **orders** | ✅ 主链已 PG 化 | `main.py` Phase 4.2 硬编码 `create_runtime_order_repository()` → `PgOrderRepository` |
| **execution_intents** | ✅ 主链已 PG 化 | `CORE_EXECUTION_INTENT_BACKEND=postgres`，工厂返回 `PgExecutionIntentRepository` |
| **positions** | ✅ 主链已 PG 化 | `main.py` Phase 4.2 硬编码 `create_runtime_position_repository()` → `PgPositionRepository` |
| **execution_recovery_tasks** | ✅ 全量 PG | `PgExecutionRecoveryRepository`，无 SQLite 等价物 |
| **signals / signal_attempts** | ❌ 纯 SQLite | `SignalRepository` → `data/v3_dev.db`，无 PG 实现 |
| **config (全部)** | ❌ 纯 SQLite | 12+ config repo 全部 aiosqlite，无 PG 实现 |
| **backtest reports** | ❌ 纯 SQLite | `BacktestReportRepository` → `data/v3_dev.db` |
| **order_audit_logs** | ❌ 纯 SQLite | `OrderAuditLogRepository` → SQLAlchemy + SQLite |
| **reconciliation** | ❌ 纯 SQLite | `ReconciliationRepository` → `data/reconciliation.db`（独立文件） |
| **historical klines** | ❌ 纯 SQLite | `HistoricalDataRepository` → `data/v3_dev.db` |
| **runtime_profiles** | ❌ 纯 SQLite | `RuntimeProfileRepository` → `data/v3_dev.db` |

**一句话**: 执行主线 4 张表（orders, execution_intents, positions, execution_recovery_tasks）已 PG 化；其余 12+ 个 repository、30+ 张表仍纯 SQLite，无任何 PG 实现。

### 关键风险

- **P0-1**: 运行时执行链 orders 硬编码 PG，但 API 查询链 `_get_order_repo()` 走配置选择（默认 sqlite）→ 同一时刻可能读写不同库
- **P0-2**: PG schema 无版本化迁移管理（`metadata.create_all`），Alembic 仅管 SQLite
- **P0-3**: 3 个核心 PG repo（Order/Intent/Position）无单元测试
- **P0-4**: `get_pg_session_maker()` 引擎失败后 sessionmaker 永久损坏，无恢复机制
- **P0-5**: signals 表是执行主线的上游（信号→意图→订单），但仍是 SQLite → 跨库链路

---

## 1. 全量对象映射表

### 1.1 执行主线对象（已 PG 化）

| 对象 | 表名 | Repository | Service/API 消费者 | 真源库 | 过渡态? | 跨库? |
|------|------|-----------|-------------------|--------|---------|-------|
| **orders** | `orders` (PG) / `orders` (SQLite) | `PgOrderRepository` (主链) / `OrderRepository` (API fallback) | `ExecutionOrchestrator`, `OrderLifecycleService`, `PositionProjectionService`, `StartupReconciliationService`, `RuntimeOrdersReadModel`, `RuntimeOverviewReadModel` | **PG**（主链）/ SQLite（API fallback） | ⚠️ 双轨 | ⚠️ API 链可能读 SQLite |
| **execution_intents** | `execution_intents` (PG) | `PgExecutionIntentRepository` | `ExecutionOrchestrator`, `RuntimeExecutionIntentsReadModel`, `RuntimeOverviewReadModel` | **PG** | ✅ 已收口 | 无 |
| **positions** | `positions` (PG) | `PgPositionRepository` | `PositionProjectionService`, `RuntimePositionsReadModel`, `RuntimeOverviewReadModel` | **PG** | ✅ 已收口 | 无 |
| **execution_recovery_tasks** | `execution_recovery_tasks` (PG) | `PgExecutionRecoveryRepository` | `ExecutionOrchestrator`, `RuntimeHealthReadModel`, `StartupReconciliationService` | **PG** | ✅ 已收口 | 无 |

### 1.2 信号/研究对象（纯 SQLite）

| 对象 | 表名 | Repository | Service/API 消费者 | 真源库 | 过渡态? | 跨库? |
|------|------|-----------|-------------------|--------|---------|-------|
| **signals** | `signals` | `SignalRepository` | `SignalPipeline`, `SignalTracker`, `PerformanceTracker`, `RuntimeSignalsReadModel` | **SQLite** | ❌ 无 PG 实现 | ⚠️ 信号→意图跨库 |
| **signal_attempts** | `signal_attempts` | `SignalRepository` | `SignalPipeline`, `RuntimeAttemptsReadModel` | **SQLite** | ❌ 无 PG 实现 | ⚠️ 同上 |
| **signal_take_profits** | `signal_take_profits` | `SignalRepository` | `OrderLifecycleService` (via signal lookup) | **SQLite** | ❌ 无 PG 实现 | ⚠️ 同上 |

### 1.3 配置对象（纯 SQLite）

| 对象 | 表名 | Repository | Service/API 消费者 | 真源库 | 过渡态? | 跨库? |
|------|------|-----------|-------------------|--------|---------|-------|
| **strategies** | `strategies` | `StrategyConfigRepository` | `ConfigManager`, `api_v1_config.py` | **SQLite** | ❌ | 无 |
| **risk_configs** | `risk_configs` | `RiskConfigRepository` | `ConfigManager`, `api_v1_config.py` | **SQLite** | ❌ | 无 |
| **system_configs** | `system_configs` | `SystemConfigRepository` | `ConfigManager`, `api_v1_config.py` | **SQLite** | ❌ | 无 |
| **symbols** | `symbols` | `SymbolConfigRepository` | `ConfigManager`, `api_v1_config.py` | **SQLite** | ❌ | 无 |
| **notifications** | `notifications` | `NotificationConfigRepository` | `ConfigManager`, `api_v1_config.py` | **SQLite** | ❌ | 无 |
| **config_snapshots** | `config_snapshots` | `ConfigSnapshotRepository` | `ConfigSnapshotService`, `api_v1_config.py` | **SQLite** | ❌ | 无 |
| **config_history** | `config_history` | `ConfigHistoryRepository` | `api_v1_config.py` | **SQLite** | ❌ | 无 |
| **config_entries_v2** | `config_entries_v2` | `ConfigEntryRepository` | `ConfigManager`, `ConfigProfileService` | **SQLite** | ❌ | 无 |
| **config_profiles** | `config_profiles` | `ConfigProfileRepository` | `ConfigProfileService`, `api_profile_endpoints.py` | **SQLite** | ❌ | 无 |
| **exchange_configs** | `exchange_configs` | `ConfigRepository` (app层) | `ConfigManager` | **SQLite** | ❌ | 无 |
| **runtime_profiles** | `runtime_profiles` | `RuntimeProfileRepository` | `RuntimeConfigProvider`, `api_console_research.py` | **SQLite** | ❌ | 无 |

### 1.4 回测/归因对象（纯 SQLite）

| 对象 | 表名 | Repository | Service/API 消费者 | 真源库 | 过渡态? | 跨库? |
|------|------|-----------|-------------------|--------|---------|-------|
| **backtest_reports** | `backtest_reports` | `BacktestReportRepository` | `Backtester`, `api.py` | **SQLite** | ❌ | 无 |
| **position_close_events** | `position_close_events` | `BacktestReportRepository` | `Backtester` | **SQLite** | ❌ | 无 |
| **backtest_attributions** | `backtest_attributions` | `BacktestReportRepository` | `AttributionAnalyzer` | **SQLite** | ❌ | 无 |

### 1.5 审计/对账对象（纯 SQLite）

| 对象 | 表名 | Repository | Service/API 消费者 | 真源库 | 过渡态? | 跨库? |
|------|------|-----------|-------------------|--------|---------|-------|
| **order_audit_logs** | `order_audit_logs` | `OrderAuditLogRepository` | `OrderAuditLogger`, `api.py` | **SQLite** | ❌ | ⚠️ 审计 PG 订单但存 SQLite |
| **reconciliation_reports** | `reconciliation_reports` | `ReconciliationRepository` | `ReconciliationService` | **SQLite** (独立 DB) | ❌ | 无 |
| **reconciliation_details** | `reconciliation_details` | `ReconciliationRepository` | `ReconciliationService` | **SQLite** (独立 DB) | ❌ | 无 |

### 1.6 历史数据对象（纯 SQLite）

| 对象 | 表名 | Repository | Service/API 消费者 | 真源库 | 过渡态? | 跨库? |
|------|------|-----------|-------------------|--------|---------|-------|
| **klines** | `klines` | `HistoricalDataRepository` | `Backtester` | **SQLite** | ❌ | 无 |

---

## 2. 跨库链路分析

### 2.1 已确认的跨库链路

```
信号链路（跨库）:
  SignalPipeline → SignalRepository(SQLite) → signals 表
       ↓ signal_id
  ExecutionOrchestrator → PgExecutionIntentRepository(PG) → execution_intents 表
       ↓ intent_id
  OrderLifecycleService → PgOrderRepository(PG) → orders 表

问题: signal_id 从 SQLite 传入 PG，无外键约束，无一致性校验
```

```
审计链路（跨库）:
  OrderLifecycleService → PgOrderRepository(PG) → 写入 orders
       ↓ order_id
  OrderAuditLogger → OrderAuditLogRepository(SQLite) → order_audit_logs 表

问题: 审计的是 PG 订单，但审计日志存 SQLite，无法 JOIN 查询
```

```
对账链路（跨库）:
  StartupReconciliationService → OrderRepository(SQLite, fallback) → orders 表
       ↓ 同时
  StartupReconciliationService → PgExecutionRecoveryRepository(PG) → execution_recovery_tasks 表

问题: 对账同时读 SQLite orders 和 PG recovery_tasks，数据源不一致
```

### 2.2 API 查询链路的后端选择隐患

```
main.py Phase 4.2:
  _order_repo = create_runtime_order_repository()  → 始终 PgOrderRepository
  api.py _get_order_repo():
    if _order_repo is None:
      return create_order_repository()  → 按 CORE_ORDER_BACKEND 选择（默认 sqlite）
    return _order_repo  → 运行时是 PG

风险: 如果 _order_repo 被重置为 None（错误恢复场景），回退到 SQLite
```

---

## 3. 特别标清问题

### 3.1 执行主线对象仍不在 PG 真源上的

| 对象 | 说明 |
|------|------|
| **signals** | 执行主线的上游输入，signal_id 贯穿 intent→order，但 signals 表纯 SQLite |
| **signal_attempts** | 信号尝试记录，纯 SQLite |
| **order_audit_logs** | PG 订单的审计日志，但存 SQLite |

### 3.2 有 PG 实现但主链默认仍在 SQLite 的

| 对象 | 说明 |
|------|------|
| **orders (API 链)** | `CORE_ORDER_BACKEND` 默认 `sqlite`，`_get_order_repo()` fallback 走 SQLite |
| **positions (API 链)** | `CORE_POSITION_BACKEND` 默认 `sqlite`，但 `create_runtime_position_repository()` 硬编码 PG |

### 3.3 已进 PG 但周边仍依赖 SQLite 兼容路径的

| 对象 | 说明 |
|------|------|
| **orders** | `PgOrderRepository` 未覆盖 order tree/chain/batch-delete 等方法，这些查询仍走 SQLite `OrderRepository` |

### 3.4 仍直接 new SQLite repo 的 API/service/script

| 位置 | 说明 |
|------|------|
| `api.py` `_get_order_repo()` fallback | 调用 `create_order_repository()` 可能返回 SQLite |
| `startup_reconciliation_service.py` | 构造函数接收 `OrderRepository`（SQLite 类型标注） |
| `signal_pipeline.py` | 直接 import `SignalRepository`（SQLite） |
| `signal_tracker.py` | 直接 import `SignalRepository`（SQLite） |
| `order_audit_logger.py` | 直接 import `OrderAuditLogRepository`（SQLite） |
| `reconciliation.py` | 直接 import `ReconciliationRepository`（SQLite） |
| `reconciliation_lock.py` | 直接使用 `sqlite3` 同步连接 |
| `config_manager.py` | 直接 import 所有 config repositories（SQLite） |
| `backtester.py` | 直接 import `HistoricalDataRepository`（SQLite） |
| `scripts/` 目录 99 个脚本 | 全部硬编码 SQLite 路径 |

### 3.5 "看起来收口了，实际还跨库"的链路

| 链路 | 表象 | 实际 |
|------|------|------|
| **execution_intents** | 已收口到 PG | `signal_payload` JSONB 中的 signal_id 指向 SQLite signals 表，无引用完整性 |
| **positions** | 已收口到 PG | `signal_id` 字段指向 SQLite signals 表 |
| **orders** | 主链已 PG | API 查询链 fallback 仍可走 SQLite |
| **startup reconciliation** | 用 PG recovery repo | 同时读 SQLite orders 做比对 |

---

## 4. 风险矩阵

### P0 — 直接影响 Sim-1 观察可信度或执行主线一致性

| # | 问题 | 影响范围 | 文件 |
|---|------|---------|------|
| P0-1 | **orders API 链与执行链后端不一致**: 执行链硬编码 PG，API fallback 走配置选择（默认 sqlite） | Sim-1 控制台看到的订单可能与执行链写入的不一致 | `src/infrastructure/core_repository_factory.py`, `src/interfaces/api.py` |
| P0-2 | **signals 跨库**: signal_id 从 SQLite signals 表传入 PG execution_intents，无引用完整性 | 意图/订单关联到不存在的 signal 不会报错 | `src/application/execution_orchestrator.py` |
| P0-3 | **PG repo 无单元测试**: PgOrderRepository / PgPositionRepository / PgExecutionIntentRepository 无任何测试 | JSONB 序列化/反序列化 bug 不会被发现 | `tests/` 缺失 |
| P0-4 | **PG sessionmaker 无失败恢复**: `get_pg_session_maker()` 引擎失败后缓存损坏的 sessionmaker | PG 连接闪断后所有后续操作永久失败 | `src/infrastructure/database.py` |
| P0-5 | **PG schema 无版本化迁移**: `metadata.create_all()` 无法增量升级 | 后续加列/索引必须 drop+recreate，生产不可接受 | `src/infrastructure/database.py` |
| P0-6 | **order_audit_logs 跨库**: PG 订单的审计日志存 SQLite | 无法 JOIN 查询订单+审计，审计链路断裂 | `src/application/order_audit_logger.py` |
| P0-7 | **配置参数不一致**: pinbar 默认值在 3 个文件中有 3 种不同值，max_leverage 有 3 种不同值 | 回测结果不可复现，实盘与回测参数可能不同 | `config/user.yaml.example`, `backtest_config.py` |

### P1 — 阻碍后续 SQLite 退役

| # | 问题 | 影响范围 | 文件 |
|---|------|---------|------|
| P1-1 | **signals 无 PG 实现**: `SignalRepository` 是最大的 SQLite repo（4 张表），无任何 PG 迁移计划 | SQLite 退役最大障碍 | `src/infrastructure/signal_repository.py` |
| P1-2 | **config 全量 SQLite**: 12+ config repo、11 张表无 PG 实现 | 配置管理完全绑定 SQLite | `src/infrastructure/repositories/config_repositories.py`, `src/infrastructure/config_*.py` |
| P1-3 | **backtest SQLite**: backtest_reports / position_close_events / backtest_attributions 无 PG | 回测数据绑定 SQLite | `src/infrastructure/backtest_repository.py` |
| P1-4 | **historical klines SQLite**: 回测依赖的 K 线数据存 SQLite | 回测绑定 SQLite | `src/infrastructure/historical_data_repository.py` |
| P1-5 | **reconciliation 独立 DB**: `data/reconciliation.db` 是独立文件 | 对账数据与主库分离 | `src/infrastructure/reconciliation_repository.py` |
| P1-6 | **PgOrderRepository 方法不完整**: 缺少 order tree/chain/batch-delete 等方法 | 部分 API 查询仍需 SQLite fallback | `src/infrastructure/pg_order_repository.py` |
| P1-7 | **reconciliation_lock 直接用 sqlite3**: 同步 sqlite3 连接，不走连接池 | 无法迁移到 PG | `src/application/reconciliation_lock.py` |
| P1-8 | **ConfigRepository (app层) 自建连接**: 不走 connection pool，自建 aiosqlite 连接 + WAL PRAGMA | 迁移时需要特殊处理 | `src/application/config/config_repository.py` |

### P2 — 技术债或文档/脚本残留

| # | 问题 | 影响范围 |
|---|------|---------|
| P2-1 | `core.yaml.reference` 是死代码，文档与实际默认值不一致 | 开发者困惑 |
| P2-2 | `user.yaml.example` 有损坏的 YAML 语法（trigger_logic 段） | 新用户配置出错 |
| P2-3 | `config_backup_20260414_230534.yaml` 在项目根目录 | 安全/整洁 |
| P2-4 | scripts/ 目录 144 个脚本，99 个有 sys.path.insert hack | 维护成本 |
| P2-5 | scripts/ 中 44 个验证/诊断脚本混在工具脚本中 | 目录混乱 |
| P2-6 | scripts/README.md 严重过时 | 文档失效 |
| P2-7 | Alembic env.py 仅导入 SQLite Base.metadata，未管理 PG schema | 迁移管理不完整 |
| P2-8 | RuntimeOverviewReadModel 中 PG health 固定为 DEGRADED | 监控不准确 |

---

## 5. 退役顺序建议

### 5.1 可立即退役的 SQLite 路径

| 路径 | 理由 |
|------|------|
| **execution_intents SQLite fallback** | 当 `CORE_EXECUTION_INTENT_BACKEND=sqlite` 时返回 `None`，intent 回退到内存 dict。生产已用 PG，此路径仅测试用 |
| **positions SQLite fallback** | 当 `CORE_POSITION_BACKEND=sqlite` 时返回 `None`。同上 |
| **v3_orm.py 中的 OrderORM / PositionORM** | PG 版已有 `pg_models.py`，SQLite ORM 仅在 fallback 路径使用 |

### 5.2 暂缓退役的 SQLite 路径

| 路径 | 理由 | 前置条件 |
|------|------|---------|
| **OrderRepository (SQLite)** | API 查询链 fallback 仍依赖；PgOrderRepository 方法不完整（缺 tree/chain/batch-delete） | PgOrderRepository 补齐所有方法 + API 链统一走 PG |
| **SignalRepository** | 执行主线上游，但无 PG 实现 | 需新建 `PgSignalRepository` |
| **所有 config repositories** | 配置管理全量 SQLite | 需完整 PG 迁移方案 |
| **BacktestReportRepository** | 回测数据 | 需评估回测数据量和查询模式 |
| **HistoricalDataRepository** | K 线数据量大，迁移复杂 | 需评估是否用 ClickHouse/TimescaleDB |

### 5.3 当前必须保留的 SQLite 路径

| 路径 | 理由 |
|------|------|
| **reconciliation.db** | 独立数据库文件，对账是独立功能，与执行主线解耦 |
| **reconciliation_lock.py** | 同步 sqlite3 锁，轻量级，无迁移必要 |
| **scripts/ 中的分析脚本** | 临时分析工具，不进入生产链路 |
| **测试 fixtures** | 测试用 SQLite 数据库 |

### 5.4 推荐退役批次顺序

```
批次 0（立即）: 清理 execution_intents / positions 的 SQLite fallback 路径
  → 删除 CORE_EXECUTION_INTENT_BACKEND=sqlite 分支
  → 删除 CORE_POSITION_BACKEND=sqlite 分支
  → 风险: 低（生产已不用）

批次 1（Phase 5 完成前）: 统一 orders API 链到 PG
  → PgOrderRepository 补齐 tree/chain/batch-delete 方法
  → API 链 _get_order_repo() 统一走 PG
  → 删除 CORE_ORDER_BACKEND 配置项
  → 风险: 中（影响 API 查询）

批次 2（Phase 6）: signals 迁移到 PG
  → 新建 PgSignalRepository
  → 信号→意图跨库链路收口
  → 风险: 中（最大 SQLite repo，4 张表）

批次 3（Phase 7）: config 迁移到 PG
  → 12+ config repo 迁移
  → ConfigManager 改造
  → 风险: 高（配置是系统核心，影响面广）

批次 4（Phase 8）: backtest + historical data 迁移
  → 评估数据量，可能用 TimescaleDB
  → 风险: 低（不影响实盘）

批次 5（Phase 9）: 清理残留
  → 删除 v3_orm.py 中不再需要的 ORM
  → 删除 SQLite 连接池（如果不再需要）
  → 删除 alembic SQLite 迁移
  → 风险: 低
```

---

## 6. 当前执行主线 PG 化进度明细

### 已完成

| 步骤 | 说明 | 文件 |
|------|------|------|
| PG Schema 设计 | 4 张表完整 DDL + CHECK 约束 + 索引 | `db_scripts/2026-04-22-pg-core-baseline.sql` |
| PG ORM 模型 | `PGOrderORM`, `PGExecutionIntentORM`, `PGPositionORM`, `PGExecutionRecoveryTaskORM` | `src/infrastructure/pg_models.py` |
| PG Repository 实现 | 4 个 PG repo，实现 Protocol 接口 | `src/infrastructure/pg_*_repository.py` |
| Protocol 接口定义 | `OrderRepositoryPort`, `ExecutionIntentRepositoryPort`, `PositionRepositoryPort` | `src/infrastructure/repository_ports.py` |
| 工厂注入 | `core_repository_factory.py` 按配置选择 PG/SQLite | `src/infrastructure/core_repository_factory.py` |
| 双引擎架构 | SQLite + PG 独立引擎，独立 session maker | `src/infrastructure/database.py` |
| 启动集成 | `main.py` Phase 4.2 硬编码 PG 创建 | `src/main.py` |
| ReadModel 适配 | 4 个 readmodel 支持 PG 后端 | `src/application/readmodels/runtime_*.py` |
| PositionProjectionService | 基于 Protocol，与后端无关 | `src/application/position_projection_service.py` |
| 基础测试 | Recovery repo 测试 + 骨架测试 | `tests/unit/test_pg_*.py` |

### 未完成

| 步骤 | 说明 | 阻塞项 |
|------|------|--------|
| PG schema 版本化迁移 | Alembic 未管理 PG schema | P0-5 |
| PG repo 单元测试 | 3 个核心 repo 无测试 | P0-3 |
| API 链统一 PG | `_get_order_repo()` fallback 仍可能走 SQLite | P0-1 |
| signals PG 迁移 | 无 PG 实现 | P1-1 |
| config PG 迁移 | 无 PG 实现 | P1-2 |
| sessionmaker 失败恢复 | 引擎失败后永久损坏 | P0-4 |
| 审计日志 PG 化 | 跨库存储 | P0-6 |

---

## 7. 代码质量评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **执行主线 PG 化** | 🟢 7/10 | 4 张表已 PG 化，Protocol + 工厂模式设计良好 |
| **Schema 设计** | 🟢 8/10 | 约束完整，索引覆盖，JSONB 过渡合理 |
| **ORM 映射** | 🟢 7/10 | 双向映射完整，JSONB 序列化正确 |
| **连接管理** | 🟡 6/10 | 双引擎合理，但 sessionmaker 缺失败恢复 |
| **跨库一致性** | 🔴 3/10 | 信号→意图→订单跨库，审计跨库，对账跨库 |
| **测试覆盖** | 🔴 4/10 | PG repo 核心无测试 |
| **迁移管理** | 🔴 3/10 | PG 无版本化迁移 |
| **退役就绪度** | 🔴 3/10 | 仅 4/16+ 对象已 PG 化，退役路径不清晰 |

---

*审计完成。以上发现基于对 `src/infrastructure/`、`src/application/`、`src/interfaces/`、`src/domain/`、`config/`、`scripts/`、`db_scripts/`、`migrations/`、`tests/` 等全部相关文件的逐行审查。未运行完整测试。*
