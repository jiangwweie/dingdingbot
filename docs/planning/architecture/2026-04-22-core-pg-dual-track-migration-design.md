# 核心表先切 PG 的双轨迁移设计稿

> 日期：2026-04-22
> 场景：SQLite 保留可用，新增 PostgreSQL 实现；核心交易链路先切 PG，其他模块渐进迁移

---

## 一、背景与目标

当前系统已经存在两套明显不同的数据库技术路线：

1. **旧路线**
   - 以 `aiosqlite + 内联 SQL + Repository.initialize() 自动建表` 为主
   - 代表模块：`OrderRepository`、`SignalRepository`、配置类仓储

2. **新路线**
   - 以 `SQLAlchemy 2.0 async + ORM + AsyncSession` 为主
   - 代表模块：`v3_orm.py`、`PositionManager`

当前目标不是删除 SQLite，也不是一次性全库切换，而是：

**保持 SQLite 业务可用，同时新增 PostgreSQL 核心实现，并让核心交易链路优先切到 PG。**

本设计稿服务于以下现实约束：

- 低频、1h 级别、个人加密量化场景
- 当前最需要的是“可恢复、可审计、能逐步迁移”
- 不接受一次性推翻现有 SQLite 实现

---

## 二、迁移原则

### 2.1 双轨并行，不做一次性替换

- SQLite 旧实现保留
- PostgreSQL 以新增实现方式接入
- 同一条业务链路在同一阶段只认一个真源，不做复杂双写

### 2.2 核心表优先

第一阶段仅迁移以下核心表到 PG：

1. `orders`
2. `execution_intents`
3. `positions`

原因：

- `orders` 是当前执行链事实核心
- `execution_intents` 目前仍偏内存态，最适合借这次切 PG 正式落库
- `positions` 天然受益于 PG 行锁与 ORM 事务能力

### 2.3 旧模块先不动

以下内容暂时继续保留在 SQLite：

- `signals`
- `signal_attempts`
- `signal_take_profits`
- config / snapshot / history 类表
- backtest / optimization / historical data 相关表

### 2.4 不做的事情

本阶段明确不做：

1. 不删除 SQLite
2. 不做全量双写一致性
3. 不做所有表的统一 ORM 化
4. 不重构全部 Repository
5. 不顺手迁移前端 / API 契约

---

## 三、核心设计决策

### 3.1 数据库角色划分

#### SQLite

定位：

- 旧业务链路继续运行的存储后端
- 未迁移模块的事实来源
- 过渡期可运行兜底

#### PostgreSQL

定位：

- 新核心执行链路的事实来源
- `orders / execution_intents / positions` 的目标真源
- 后续恢复、并发保护、事务边界的基础底座

### 3.2 “新增实现”而不是“改写旧实现”

不直接把现有 `src/infrastructure/order_repository.py` 改造成 PG 版本，而是新增：

- `src/infrastructure/database.py`
- `src/infrastructure/pg_models.py` 或复用/拆分 `v3_orm.py`
- `src/infrastructure/pg_order_repository.py`
- `src/infrastructure/pg_execution_intent_repository.py`
- `src/infrastructure/pg_position_repository.py`

旧 SQLite 仓储保留原位：

- `src/infrastructure/order_repository.py`
- 其他 SQLite Repository

### 3.3 服务层改为面向接口/协议

核心服务不再强依赖 SQLite 具体类，而是依赖“最小能力接口”。

第一阶段需要完成接口抽象的服务：

1. `OrderLifecycleService`
2. `ExecutionOrchestrator`
3. `StartupReconciliationService`
4. `PositionManager`（如果要统一接入仓储）

### 3.4 切换策略

通过配置选择核心链路实际使用哪套实现，例如：

```env
CORE_ORDER_BACKEND=postgres
CORE_EXECUTION_INTENT_BACKEND=postgres
CORE_POSITION_BACKEND=postgres
```

过渡期允许：

- 核心执行链走 PG
- 旧查询/旧功能仍走 SQLite

不要求：

- 所有业务都在同一数据库

---

## 四、目标目录与组件划分

### 4.1 新增基础设施组件

建议新增：

```text
src/infrastructure/
├── database.py
├── repository_ports.py
├── pg_models.py
├── pg_order_repository.py
├── pg_execution_intent_repository.py
└── pg_position_repository.py
```

### 4.2 组件职责

#### `database.py`

职责：

- 创建 PG async engine
- 创建 async sessionmaker
- 统一读取 `DATABASE_URL`
- 不承接 SQLite 连接池职责

#### `repository_ports.py`

职责：

- 定义最小仓储协议/接口
- 限定服务层需要的方法边界

第一阶段至少需要：

- `OrderRepositoryPort`
- `ExecutionIntentRepositoryPort`
- `PositionRepositoryPort`

#### `pg_models.py`

职责：

- 承载 PG 核心表 ORM 定义
- 优先覆盖 `orders / execution_intents / positions`
- 若 `v3_orm.py` 可直接复用其中部分模型，可在此做拆分或重新导出

#### `pg_*_repository.py`

职责：

- 使用 SQLAlchemy async + ORM/SQL 表达式实现 PG 仓储
- 对外暴露与服务层约定一致的最小方法集

---

## 五、第一阶段接口边界

### 5.1 OrderRepositoryPort

第一阶段至少支持：

- `initialize()`
- `save(order)`
- `save_batch(orders)`
- `get_order(order_id)`
- `get_order_by_exchange_id(exchange_order_id)`
- `get_orders_by_signal(signal_id)`
- `get_orders_by_status(status, symbol=None)`
- `get_open_orders(symbol=None)`

说明：

- 只抽核心执行链实际依赖的方法
- 不先抽所有查询、树视图、批量删除等长尾方法

### 5.2 ExecutionIntentRepositoryPort

第一阶段新增并支持：

- `initialize()`
- `save(intent)`
- `get(intent_id)`
- `get_by_order_id(order_id)`
- `list_unfinished()`
- `update_status(intent_id, status, ...)`

说明：

- 该仓储是本轮迁移的关键新增点
- 用于替代 orchestrator 内存真源

### 5.3 PositionRepositoryPort

第一阶段建议至少支持：

- `initialize()`
- `get(position_id)`
- `save(position)`
- `get_by_signal_id(signal_id)`
- 行锁查询接口（若继续沿用 `PositionManager` 的 `AsyncSession`，可暂不独立抽全）

---

## 六、表级迁移边界

### 6.1 `orders`

状态：

- SQLite 版已存在并稳定运行
- 字段相对完整，可直接迁到 PG

建议：

- 在 PG 建立等价 schema
- 不在第一阶段变更业务字段语义

### 6.2 `execution_intents`

状态：

- 当前仍以内存存储为主
- 已经成为 partial-fill、保护单、恢复链的关键上下文

建议：

- 第一阶段直接作为新表落入 PG
- 保留 `strategy snapshot`
- 保留 `signal` 原始快照或最小必要字段

### 6.3 `positions`

状态：

- 代码层已有 SQLAlchemy/ORM 路线
- 是最接近 PG 思路的核心实体

建议：

- 与 `orders` 一起视为核心 PG 表
- 为后续行锁、状态恢复、仓位归因打底

---

## 七、实施顺序

### Phase A：设计与测试先行

本阶段输出：

1. 本设计稿
2. 测试用例设计文档

### Phase B：最小骨架

仅做：

1. `database.py`
2. `repository_ports.py`
3. PG 核心 ORM/schema
4. 空仓储骨架 + 最小初始化

### Phase C：核心链路接入

优先顺序：

1. `OrderLifecycleService` 接 `OrderRepositoryPort`
2. `ExecutionOrchestrator` 接 `ExecutionIntentRepositoryPort`
3. `StartupReconciliationService` 改走 PG order repo

### Phase D：启动/依赖注入切换

在应用初始化中增加：

- SQLite 旧 repo 初始化
- PG 核心 repo 初始化
- 核心链路绑定 PG 实现

---

## 八、风险与约束

### 8.1 最大风险

不是建表，而是：

- 服务层仍然写死依赖 SQLite 具体类
- 旧 repo 方法太多，抽象边界过宽
- 启动阶段依赖注入分散

### 8.2 风险控制策略

1. 接口只抽“当前主链实际用到”的最小方法
2. SQLite 旧实现不删不大改
3. PG 先只接核心链路
4. 不把“切 PG”与“执行链新功能”绑在一起

---

## 九、当前结论

本项目数据库迁移应采用：

**SQLite 保留可用 + 新增 PostgreSQL 核心实现 + 核心表先切 PG + 服务层逐步切换依赖注入**。

第一阶段真源划分：

- 核心执行链：PG
- 旧业务及未迁移模块：SQLite

下一步不是直接全量开发，而是：

1. 先按本设计稿补测试设计
2. 再写 PG 骨架
3. 再由执行开发补具体实现与测试
