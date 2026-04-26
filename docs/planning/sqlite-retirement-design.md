# SQLite 退役专项设计

> **版本**: v1.0
> **日期**: 2026-04-26
> **作者**: PM (Claude Code)
> **状态**: 架构设计稿（未实施，未运行测试）
> **约束**: 本窗口仅做架构设计和迁移规划，不修改主线代码，不删除任何 SQLite 表/repo/脚本

---

## 0. 总体退役策略结论

### 核心判断

**推荐方案：方案 A（执行主线先退役，其余延后）**

当前阶段（Sim-1 观察期）应聚焦于**完成 Window 1 执行主线 PG 闭环**，而非全面退役 SQLite。理由：

1. **执行主线上仅剩 `signals` 表和 SQLite `orders` 回退路径**未切 PG，其余执行状态（execution_intents / recovery_tasks / positions）已在 PG
2. **`signals` 迁移属于 Window 2**，前置条件（执行主线 PG 稳定性验证、position projection 语义补全）尚未满足
3. **config / backtest / klines / reconciliation** 均不在执行热路径上，SQLite 完全能胜任，过早迁移只会增加 Sim-1 风险
4. **没有数据迁移工具**——当前 PG 表由应用运行时写入，历史 SQLite 数据未迁移。退役前必须先建迁移工具

### 一句话结论

> **现在做什么**：完成 Window 1 剩余工作（orders PG 全路径切换 + position projection 语义补全），为 Window 2 打基础。
> **现在不做什么**：不迁 signals、不迁 config、不迁 backtest、不迁 klines、不删任何 SQLite repo。

---

## 1. 退役范围模型

### 1.1 执行主线相关 SQLite 路径

| 对象 | 表 | Repo 类 | 当前状态 | 在执行主链上的角色 |
|------|-----|---------|----------|-------------------|
| **signals** | `signals` | `SignalRepository` | SQLite-only，无 PG 实现 | 信号生成是执行管线第一阶段；`SignalPipeline` 写入，`ExecutionOrchestrator` 读取 |
| **signal_take_profits** | `signal_take_profits` | `SignalRepository` (同 repo) | SQLite-only | 多级止盈追踪，执行链消费 |
| **SQLite orders 回退** | `orders` | `OrderRepository` (SQLite) | PG 已为主路径；SQLite 仍为 `create_order_repository()` 默认值 | API 端点和通用路径仍可能路由到 SQLite |
| **signal_attempts** | `signal_attempts` | `SignalRepository` (同 repo) | SQLite-only | 信号评估可观测性，非热路径但与 signals 同 repo |

**关键发现**：`SignalRepository` 是一个**巨型 repo**，同时管理 4 张表（signals / signal_attempts / signal_take_profits / config_snapshots）。退役 signals 意味着必须整体迁移这个 repo 或拆分它。

### 1.2 观察/只读/配置相关 SQLite 路径

| 对象 | 表 | Repo 类 | 当前状态 | 在执行主链上的角色 |
|------|-----|---------|----------|-------------------|
| **runtime_profiles** | `runtime_profiles` | `RuntimeProfileRepository` | SQLite-only | 启动时一次性读取，不在热路径上 |
| **config_snapshots** | `config_snapshots` | `ConfigSnapshotRepository` | SQLite-only | 配置版本控制，不在热路径上 |
| **config_entries** | `config_entries` / `config_entries_v2` | `ConfigEntryRepository` | SQLite-only | 策略参数 KV 存储，不在热路径上 |
| **config_profiles** | `config_profiles` | `ConfigProfileRepository` | SQLite-only | 配置 profile 管理，不在热路径上 |
| **reconciliation** | `reconciliation_reports` / `reconciliation_details` | `ReconciliationRepository` | SQLite-only（独立 DB 文件 `data/reconciliation.db`） | 仅启动时对账，不在热路径上 |
| **order_audit_logs** | `order_audit_logs` | `OrderAuditLogRepository` | PG（SQLAlchemy async） | 已在 PG，异步写入，不阻塞执行 |

### 1.3 研究/回测/历史相关 SQLite 路径

| 对象 | 表 | Repo 类 | 当前状态 | 在执行主链上的角色 |
|------|-----|---------|----------|-------------------|
| **backtest_reports** | `backtest_reports` | `BacktestReportRepository` | SQLite-only | 离线回测，不在执行路径上 |
| **position_close_events** | `position_close_events` | `BacktestReportRepository` (同 repo) | SQLite-only | 回测平仓事件 |
| **backtest_attributions** | `backtest_attributions` | `BacktestReportRepository` (同 repo) | SQLite-only | 回测归因分析 |
| **klines** | `klines` | `HistoricalDataRepository` | SQLite-only | 间接影响执行（喂给信号管线），但有 CCXT 回退 |
| **各 config 表** | `strategies` / `risk_configs` / `system_configs` / `exchange_configs` / `notification_configs` | `ConfigManager` (直接读 SQLite) | SQLite-only | YAML 配置的 DB 镜像，不在热路径上 |

---

## 2. 退役分批方案

### 第 1 批：可尽快退役（Window 1 收尾）

**目标**：消除执行主线上 SQLite 的最后一个回退路径

| 对象 | 具体内容 | 前置条件 | 风险点 | 回滚点 | 与 PG 主线的依赖 |
|------|---------|---------|--------|--------|-----------------|
| **SQLite orders 回退路径** | `OrderRepository` (SQLite) + `create_order_repository()` 的 sqlite 分支 + `CORE_ORDER_BACKEND=sqlite` 环境变量 | 1. `PgOrderRepository` 补全缺失方法（`get_order_tree` / `get_order_chain` / `delete_orders_batch` / `get_oco_group`）<br>2. API 端点全部切换到 PG factory<br>3. Sim-1 至少完成 1 次完整信号→下单→平仓周期 | API 端点路由到错误 repo；回退路径删除后 PG 不可用时无降级 | 恢复 `CORE_ORDER_BACKEND=sqlite` 环境变量 + 恢复 `create_order_repository()` 的 sqlite 分支 | PG `orders` 表必须稳定运行 |
| **reconciliation SQLite** | `ReconciliationRepository` + `data/reconciliation.db` | 1. PG 对账 repo 实现<br>2. 启动对账逻辑验证通过 | 对账是启动安全网，迁移失败可能导致脏数据不被发现 | 恢复 SQLite reconciliation repo + 独立 DB 文件 | 低依赖，可独立迁移 |

**预计工作量**：3-5 天（orders 补全 + API 切换 + 验证）

### 第 2 批：前置条件满足后退役（Window 2）

**目标**：退役信号/可观测性域的 SQLite

| 对象 | 具体内容 | 前置条件 | 风险点 | 回滚点 | 与 PG 主线的依赖 |
|------|---------|---------|--------|--------|-----------------|
| **signals 表** | `signals` 表 + `SignalRepository.save_signal()` / `get_signal_by_id()` / `get_pending_signals()` / `get_active_signal()` / `get_opposing_signal()` / `update_signal_status()` 等 | 1. Window 1 完成（orders/intents/recovery/positions 全在 PG 稳定运行）<br>2. Position projection 语义补全（fee / idempotency / out-of-order replay）<br>3. Sim-1 至少完成 1 次完整实盘验证<br>4. PG `signals` 表 DDL 设计 + ORM 实现 | 信号查询模式复杂（active signal lookup / opposing signal / superseded tracking）；跨库引用（PG orders.signal_id → SQLite signals） | 恢复 SQLite SignalRepository + 环境变量切换 | PG `orders.signal_id` 必须能逻辑引用 PG `signals.id`（消除跨库引用） |
| **signal_take_profits 表** | `signal_take_profits` 表 + 相关 CRUD 方法 | 同 signals | 与 signals 同 repo，必须一起迁移 | 同 signals | 同 signals |
| **signal_attempts 表** | `signal_attempts` 表 + `save_attempt()` / `get_attempts()` / `get_diagnostics()` | 同 signals（同 repo） | 可观测性数据，迁移失败不影响执行但影响诊断 | 同 signals | 低依赖 |

**预计工作量**：5-8 天（PG DDL + ORM + Repo 实现 + 查询适配 + 验证）

**SignalRepository 拆分建议**：当前 `SignalRepository` 管理 4 张表，建议迁移时拆分为：
- `PgSignalRepository`（signals + signal_take_profits）→ 执行相关
- `PgSignalAttemptRepository`（signal_attempts）→ 可观测性
- `config_snapshots` 归入 config 域（第 3 批）

### 第 3 批：当前不建议退役

| 对象 | 具体内容 | 不建议退役的原因 | 未来退役时机 |
|------|---------|-----------------|-------------|
| **runtime_profiles** | `runtime_profiles` 表 + `RuntimeProfileRepository` | 1. 启动时一次性读取，不在热路径上<br>2. 使用 `BEGIN IMMEDIATE` 保证事务安全，PG 迁移需重新设计并发控制<br>3. `sim1_eth_runtime` profile 已 seed 到 `data/v3_dev.db`，迁移需数据搬迁<br>4. 配置域明确留在 SQLite（Window 3） | Window 3（参数/策略配置域迁移） |
| **config 域全部** | `config_snapshots` / `config_entries` / `config_entries_v2` / `config_profiles` / `strategies` / `risk_configs` / `system_configs` 等 | 1. 配置域是独立域，不影响执行<br>2. `ConfigManager` 直接读 SQLite，迁移需重构整个配置加载链路<br>3. 配置热重载、快照回滚等机制依赖 SQLite 事务特性 | Window 3 |
| **backtest 域全部** | `backtest_reports` / `position_close_events` / `backtest_attributions` | 1. 纯离线分析数据<br>2. 数据量大（回测报告含大量 JSON payload）<br>3. 不影响任何执行/观测路径 | Window 4 |
| **klines** | `klines` 表 + `HistoricalDataRepository` | 1. 间接影响（喂给信号管线），但有 CCXT 实时回退<br>2. 数据量最大（历史 K 线），迁移成本最高<br>3. PG 时序数据方案需单独设计（TimescaleDB extension？） | Window 4 |
| **reconciliation** | `reconciliation_reports` / `reconciliation_details`（独立 DB） | 可以在第 1 批退役（见上），但如果 PG 对账 repo 实现复杂度高，可延后 | Window 2-3 |

---

## 3. 重点问题回答

### Q1: 哪些 SQLite 路径仍在执行主链上，必须优先处理？

**仅剩 2 个**：

1. **`signals` 表**（`SignalRepository`）— 信号生成是执行管线第一阶段。`SignalPipeline.process_kline()` 写入信号，`ExecutionOrchestrator` 读取信号并驱动下单。**但当前 `signals` 仍在 SQLite，而 `orders` / `execution_intents` / `positions` 已在 PG，形成了跨库引用**（PG `orders.signal_id` → SQLite `signals.id`）。这是当前架构最大的数据一致性风险。

2. **SQLite `orders` 回退路径** — `create_order_repository()` 默认返回 SQLite repo，API 端点可能路由到 SQLite。虽然运行时链路已硬编码 PG（`create_runtime_order_repository()`），但通用路径仍有 SQLite 回退。

### Q2: 哪些 SQLite 路径只是 research/config/history，不应该现在动？

- `backtest_reports` / `position_close_events` / `backtest_attributions` — 纯回测
- `klines` — 历史 K 线缓存
- `config_snapshots` / `config_entries` / `config_profiles` — 配置管理
- `strategies` / `risk_configs` / `system_configs` 等 config 表 — YAML 配置镜像
- `reconciliation_reports` / `reconciliation_details` — 启动对账（可选迁）

### Q3: runtime_profiles 现在是否应该迁 PG？

**不应该。** 原因：

1. **不在热路径**：`runtime_profiles` 仅在启动时由 `RuntimeConfigResolver` 读取一次，运行期间不频繁访问
2. **事务安全设计依赖 SQLite**：使用 `BEGIN IMMEDIATE` 保证 profile 切换的原子性，PG 需重新设计
3. **数据搬迁成本**：`sim1_eth_runtime` profile 已 seed 到 `data/v3_dev.db`，迁移需要数据搬迁脚本
4. **架构决策已锁定**：task_plan.md 明确 "config stays on SQLite short-term"，`runtime_profiles` 属于配置域
5. **迁移收益低**：即使迁到 PG，启动时仍需读取一次，性能无差异

### Q4: signals / attempts 是否适合现在迁 PG？

**不适合。** 原因：

1. **属于 Window 2**：已锁定的 4 窗口迁移计划明确 signals 在 Window 2
2. **前置条件未满足**：
   - orders / execution_intents / recovery_tasks / positions 尚未在 PG 完全稳定（Window 1 未完成）
   - Position projection 语义尚未补全（fee / idempotency / out-of-order replay）
   - Sim-1 尚未完成完整实盘验证
3. **查询模式复杂**：`get_active_signal()` / `get_opposing_signal()` / `update_superseded_by()` 等查询涉及复杂的状态机逻辑，迁移到 PG 需要仔细设计索引和查询计划
4. **跨库引用问题**：当前 PG `orders.signal_id` 引用 SQLite `signals.id`，迁移 signals 到 PG 后才能加真正的外键约束
5. **Repo 拆分成本**：`SignalRepository` 管理 4 张表，迁移时必须拆分，增加工作量

### Q5: config/backtest/historical 是否应晚于执行主线迁移？

**是的，必须晚于执行主线。** 理由：

1. **架构决策已锁定**：4 窗口迁移计划 = Window 1（执行主线）→ Window 2（信号/可观测性）→ Window 3（配置域）→ Window 4（回测/研究/历史）
2. **风险隔离**：执行主线是资金安全相关的，必须最先稳定；config/backtest 是辅助功能，SQLite 完全能胜任
3. **依赖关系**：config 域的迁移依赖执行主线稳定后才能验证配置变更的影响；backtest 域的迁移依赖 signals 域稳定后才能验证回测数据一致性
4. **数据量差异**：backtest 和 klines 数据量远大于执行数据，迁移成本最高，应最后处理

---

## 4. 两套架构方案

### 方案 A：执行主线先退役 SQLite，其余延后（推荐）

#### 范围

| 阶段 | 内容 | 涉及表 | 涉及 Repo |
|------|------|--------|-----------|
| **Window 1 收尾** | orders PG 全路径切换 | `orders` | `PgOrderRepository` 补全 + `OrderRepository` (SQLite) 标记废弃 |
| **Window 2** | 信号/可观测性域迁移 | `signals` / `signal_take_profits` / `signal_attempts` | 新建 `PgSignalRepository` + `PgSignalAttemptRepository` |
| **Window 3** | 配置域迁移（远期） | `runtime_profiles` / `config_*` / 各 config 表 | 新建 PG config repos |
| **Window 4** | 回测/研究/历史迁移（远期） | `backtest_*` / `klines` | 新建 PG backtest/klines repos |

#### 收益

- **风险最小**：每次只动一个域，失败影响范围可控
- **Sim-1 安全**：执行主线逐步闭环，不会反向冲击 Sim-1
- **可验证**：每个窗口完成后可以独立验证，再进入下一个
- **符合已有架构决策**：与 task_plan.md 锁定的 4 窗口计划完全一致

#### 风险

- **周期长**：4 个窗口可能需要 4-8 周
- **跨库引用持续存在**：Window 1-2 期间 PG `orders.signal_id` 仍引用 SQLite `signals.id`
- **双 repo 维护成本**：每个域迁移期间需要同时维护 SQLite 和 PG 两套 repo

#### 对 Sim-1 的影响

**极低**。Window 1 收尾只是把 API 端点的默认路由从 SQLite 改为 PG，运行时链路已经硬编码 PG。Window 2 及之后的窗口在 Sim-1 稳定后才启动。

#### 推荐理由

**强烈推荐。** 这是唯一与当前架构决策、代码现状、风险承受能力匹配的方案。核心论据：

1. 执行主线的 PG 闭环是资金安全的前提，必须最先完成
2. Sim-1 正在观察期，任何超出 Window 1 范围的变更都是不必要的风险
3. 4 窗口计划已经过架构师评审并锁定，不应在退役专项中推翻

---

### 方案 B：更激进的广域退役方案

#### 范围

| 阶段 | 内容 | 涉及表 | 涉及 Repo |
|------|------|--------|-----------|
| **Phase 1** | 执行主线 + 信号域同时迁移 | `orders` / `signals` / `signal_take_profits` / `signal_attempts` | `PgOrderRepository` 补全 + 新建 `PgSignalRepository` |
| **Phase 2** | 配置域迁移 | `runtime_profiles` / `config_*` / 各 config 表 | 新建 PG config repos |
| **Phase 3** | 回测/研究/历史迁移 | `backtest_*` / `klines` | 新建 PG backtest/klines repos |

#### 收益

- **总工期短**：3 个 Phase 可能只需 3-5 周
- **跨库引用更快消除**：Phase 1 完成后 orders 和 signals 都在 PG，可以加真正的外键
- **一步到位**：减少中间态的维护成本

#### 风险

- **高风险**：Phase 1 同时动 orders 和 signals，失败影响整个执行管线
- **Sim-1 冲击**：Phase 1 的范围超出当前 Window 1 的锁定计划，可能影响 Sim-1 观察
- **验证不足**：orders PG 路径尚未经过 Sim-1 完整验证，此时叠加 signals 迁移增加不确定性
- **Repo 拆分 + 迁移 + 验证并行**：`SignalRepository` 拆分、PG repo 实现、查询适配、数据搬迁同时进行，工作量集中
- **回滚复杂**：如果 Phase 1 的 signals 迁移失败，需要同时回滚 orders 和 signals，影响面大

#### 对 Sim-1 的影响

**中高**。Phase 1 同时动 orders（API 路由切换）和 signals（整个信号域迁移），如果出问题可能同时影响执行和信号两个环节。

#### 不推荐理由

1. **违反"一次只动一个变量"原则**：orders 和 signals 是两个独立域，应分别验证后再合并
2. **前置条件不满足**：orders PG 路径尚未在 Sim-1 完整验证，此时叠加 signals 迁移是跳跃式前进
3. **与已锁定的 4 窗口计划冲突**：推翻架构师评审结论需要充分理由，当前没有
4. **配置域和回测域不需要现在动**：SQLite 完全能胜任，过早迁移无收益

---

## 5. 明确推荐

### 推荐方案：方案 A（执行主线先退役，其余延后）

### 现在就应该做什么

1. **完成 Window 1 收尾**（最高优先级）：
   - 补全 `PgOrderRepository` 缺失方法（`get_order_tree` / `get_order_chain` / `delete_orders_batch` / `get_oco_group`）
   - API 端点全部切换到 PG factory（消除 `create_order_repository()` 的 sqlite 默认路由）
   - Position projection 语义补全（fee mapping / idempotency / out-of-order replay）
   - Sim-1 完整验证（信号→下单→平仓→对账全链路）

2. **为 Window 2 做准备**（低优先级，不阻塞 Window 1）：
   - 设计 PG `signals` 表 DDL（参考 `db_scripts/2026-04-22-pg-core-baseline.sql` 风格）
   - 评估 `SignalRepository` 拆分方案

### 现在不要做什么

- **不要迁 signals / signal_attempts / signal_take_profits** — 属于 Window 2，前置条件未满足
- **不要迁 runtime_profiles** — 配置域，SQLite 完全能胜任
- **不要迁 config 域任何表** — Window 3，远期
- **不要迁 backtest / klines** — Window 4，最远期
- **不要删除任何 SQLite repo 或表** — 退役不等于删除，先切流量再删代码
- **不要建数据迁移工具** — 当前 PG 表由应用运行时写入，历史数据搬迁是 Window 2+ 的事

### 明早如果要开"SQLite 退役实施窗口"，第一批任务

| 序号 | 任务 | 预计耗时 | 负责角色 | 依赖 |
|------|------|---------|---------|------|
| T1 | 补全 `PgOrderRepository`：实现 `get_order_tree()` / `get_order_chain()` / `delete_orders_batch()` / `get_oco_group()` | 1-2 天 | Backend | 无 |
| T2 | API 端点切换：`api.py` 中所有 `create_order_repository()` 调用改为 `create_runtime_order_repository()` 或显式 PG | 0.5 天 | Backend | T1 |
| T3 | 移除 `CORE_ORDER_BACKEND=sqlite` 环境变量默认值，改为 `postgres` | 0.5 天 | Backend | T2 |
| T4 | Position projection 语义补全：fee mapping（`close_fee` / `fee_paid`）+ 重复 fill 幂等 + 乱序 replay | 1-2 天 | Backend | 无 |
| T5 | Sim-1 完整验证：信号→下单→平仓→对账全链路 | 1 天 | QA | T1-T4 |
| T6 | 标记 SQLite `OrderRepository` 为 `@deprecated`，添加迁移就绪日志 | 0.5 天 | Backend | T5 |

**总预计**：4-6 天（Window 1 收尾）

---

## 附录 A：当前 PG/SQLite 存储矩阵

| 实体 | PG 表 | SQLite 表 | 运行时默认 | 通用默认 | 迁移状态 |
|------|-------|-----------|-----------|---------|---------|
| orders | `orders` | `orders` | **PG** (runtime factory) | SQLite (env var) | **PARTIAL** |
| execution_intents | `execution_intents` | 无 | **PG** | PG | **COMPLETE** |
| execution_recovery_tasks | `execution_recovery_tasks` | 无 | **PG** | N/A | **COMPLETE** |
| positions | `positions` | 无 | **PG** (runtime factory) | SQLite (env var) | **ACTIVE (transitional)** |
| order_audit_logs | `order_audit_logs` | 无 | **PG** | PG | **COMPLETE** |
| signals | 无 | `signals` | SQLite | SQLite | **NOT MIGRATED** |
| signal_take_profits | 无 | `signal_take_profits` | SQLite | SQLite | **NOT MIGRATED** |
| signal_attempts | 无 | `signal_attempts` | SQLite | SQLite | **NOT MIGRATED** |
| runtime_profiles | 无 | `runtime_profiles` | SQLite | SQLite | **NOT MIGRATED** |
| config_* | 无 | 多张 config 表 | SQLite | SQLite | **NOT MIGRATED** |
| backtest_* | 无 | 3 张 backtest 表 | SQLite | SQLite | **NOT MIGRATED** |
| klines | 无 | `klines` | SQLite | SQLite | **NOT MIGRATED** |
| reconciliation_* | 无 | 2 张 reconciliation 表 (独立 DB) | SQLite | SQLite | **NOT MIGRATED** |

## 附录 B：跨库引用风险图

```
当前状态（双库并存）:
┌─────────────────────────────────────────────────────┐
│  PostgreSQL                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ orders       │  │ exec_intents │  │ positions  │ │
│  │ .signal_id ──┼──┼──┐           │  │            │ │
│  └──────────────┘  │  │           │  └────────────┘ │
│                    │  │           │                  │
│  ┌─────────────────┼──┼───────────┤                  │
│  │ recovery_tasks  │  │           │                  │
│  └─────────────────┘  │           │                  │
└────────────────────────┼──────────┼──────────────────┘
                         │          │
                    跨库逻辑引用（无 FK 约束）
                         │          │
┌────────────────────────┼──────────┼──────────────────┐
│  SQLite (data/v3_dev.db)                             │
│  ┌─────────────────────▼──────────▼────────────────┐ │
│  │ signals                                         │ │
│  │ .id ← orders.signal_id 引用此字段               │ │
│  │ .id ← exec_intents.signal_id 引用此字段         │ │
│  └─────────────────────────────────────────────────┘ │
│  ┌──────────────────────┐  ┌───────────────────────┐ │
│  │ signal_take_profits  │  │ signal_attempts       │ │
│  └──────────────────────┘  └───────────────────────┘ │
└──────────────────────────────────────────────────────┘

Window 2 完成后（单库）:
┌─────────────────────────────────────────────────────┐
│  PostgreSQL                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ orders       │  │ exec_intents │  │ positions  │ │
│  │ .signal_id ──┼──┼──┐           │  │            │ │
│  └──────────────┘  │  │           │  └────────────┘ │
│  ┌─────────────────┼──┼───────────┤                  │
│  │ recovery_tasks  │  │           │                  │
│  └─────────────────┘  │           │                  │
│  ┌────────────────────▼───────────▼────────────────┐ │
│  │ signals (NEW)                                   │ │
│  │ .id ← orders.signal_id (FK 约束)               │ │
│  │ .id ← exec_intents.signal_id (FK 约束)         │ │
│  └─────────────────────────────────────────────────┘ │
│  ┌──────────────────────┐  ┌───────────────────────┐ │
│  │ signal_take_profits  │  │ signal_attempts       │ │
│  └──────────────────────┘  └───────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

## 附录 C：退役检查清单（每个 Window 完成前必须确认）

```markdown
## 数据完整性
- [ ] PG 表 DDL 已设计并 reviewed
- [ ] PG ORM 模型已实现
- [ ] PG Repo 已实现（CRUD + 关键查询）
- [ ] 数据搬迁脚本已编写（如需要）
- [ ] 数据搬迁脚本已在 staging 环境验证

## 代码切换
- [ ] 所有写入路径已切换到 PG
- [ ] 所有读取路径已切换到 PG
- [ ] SQLite repo 已标记 @deprecated
- [ ] 环境变量默认值已更新
- [ ] Factory 函数已更新

## 验证
- [ ] 单元测试全部通过
- [ ] 集成测试覆盖 PG 路径
- [ ] Sim-1 完整链路验证通过
- [ ] 回滚路径验证通过

## 安全
- [ ] 跨库引用已消除（如适用）
- [ ] FK 约束已添加（如适用）
- [ ] 索引已优化
- [ ] 敏感信息已脱敏

## 文档
- [ ] task_plan.md 已更新
- [ ] findings.md 已记录迁移决策
- [ ] progress.md 已更新进度
```

---

*本设计文档由 PM Agent 输出，未修改任何主线代码，未运行任何测试。所有结论基于代码静态分析和规划文档交叉验证。*
