# PG 执行主线真源闭环 — 验证资产设计

> **生成时间**: 2026-04-26
> **目的**: 为明日（2026-04-27）白天验证 PG 主线提供完整验证清单、测试矩阵、缺口分析和执行顺序
> **约束**: 本文档仅设计验证资产，不执行完整测试，不修改主线实现

---

## 一、验证结论摘要

### 当前状态判断

PG 执行主线代码骨架已落地（commit `c91e153` + `3f761bd`），覆盖以下链路：

| 链路 | 代码状态 | 测试状态 | 风险等级 |
|------|---------|---------|---------|
| ExecutionOrchestrator 核心流程 | ✅ 完整 | ⚠️ 单元测试充分，无 PG 集成 | 🟡 中 |
| OrderLifecycleService 状态机 | ✅ 完整 | ✅ 单元 + 集成（SQLite） | 🟢 低 |
| PositionProjectionService | ✅ 完整 | ⚠️ 单元测试充分，PG round-trip 被 skip | 🟡 中 |
| PgOrderRepository | ✅ 代码完整 | ❌ 无任何测试 | 🔴 高 |
| PgExecutionIntentRepository | ✅ 代码完整 | ❌ 无任何测试 | 🔴 高 |
| PgPositionRepository | ✅ 代码完整 | ❌ 唯一测试被 skip | 🔴 高 |
| PgExecutionRecoveryRepository | ✅ 代码完整 | ⚠️ 全部 mock，无真实 PG 验证 | 🔴 高 |
| Startup Reconciliation | ✅ 代码完整 | ⚠️ 全部 mock | 🟡 中 |
| Runtime Readonly API | ✅ 代码完整 | ⚠️ 全部 mock | 🟡 中 |
| Circuit Breaker + Recovery 联动 | ✅ 代码完整 | ⚠️ 全部 mock | 🟡 中 |

### 核心风险

1. **PG Repository 层零真实验证**：4 个 PG Repository 全部没有真实数据库测试，ORM 映射、JSONB 序列化/反序列化、CheckConstraint、Partial Index 均未验证
2. **PG ↔ Domain 双向映射未验证**：`_to_orm` / `_to_domain` 的 JSONB 打包（signal_payload, strategy_payload, position_payload）从未在真实 PG 上跑过
3. **Startup Reconciliation 仅 mock 验证**：启动时从 PG 恢复 circuit breaker 的链路，从未用真实数据验证
4. **Runtime API 的 PG 数据源路径未验证**：readmodel 查询 PG repo 的路径从未真实执行

---

## 二、PG 主线范围梳理

### 2.1 核心文件清单

#### 应用层
| 文件 | 核心职责 |
|------|---------|
| `src/application/execution_orchestrator.py` | 执行主编排：intent 创建→风控→下单→保护单→状态推进→recovery |
| `src/application/order_lifecycle_service.py` | 订单状态机：CREATED→SUBMITTED→OPEN→PARTIALLY_FILLED→FILLED/CANCELED/REJECTED |
| `src/application/position_projection_service.py` | 仓位投影：ENTRY fill→创建 Position，EXIT fill→更新 PnL/watermark/close |

#### 基础设施层（PG 仓储）
| 文件 | 核心职责 |
|------|---------|
| `src/infrastructure/pg_order_repository.py` | Order 的 PG CRUD，ORM 双向映射，status 部分更新 |
| `src/infrastructure/pg_execution_intent_repository.py` | ExecutionIntent 的 PG CRUD，JSONB signal/strategy payload |
| `src/infrastructure/pg_position_repository.py` | Position 的 PG CRUD，JSONB position_payload（watermark/projection metadata） |
| `src/infrastructure/pg_execution_recovery_repository.py` | Recovery Task 的 PG CRUD，dict 返回（非 domain model） |
| `src/infrastructure/pg_models.py` | ORM 模型定义：PGOrderORM, PGExecutionIntentORM, PGPositionORM, PGExecutionRecoveryTaskORM |
| `src/infrastructure/repository_ports.py` | Protocol 接口定义：OrderRepositoryPort, ExecutionIntentRepositoryPort, PositionRepositoryPort |

#### 运行时只读 API
| 文件 | 核心职责 |
|------|---------|
| `src/interfaces/api_console_runtime.py` | Runtime API 端点：overview, health, positions, execution/orders, execution/intents |
| `src/application/readmodels/runtime_health.py` | Health readmodel：breaker/recovery/PG status 聚合 |

#### 启动与对账
| 文件 | 核心职责 |
|------|---------|
| `src/main.py` | 启动入口，repo 注册，startup reconciliation 调用 |
| `src/interfaces/api.py` | `set_dependencies()` 注入链，`create_order_repository()` 工厂 |

---

## 三、验证矩阵

### 3.1 Orders 链路

| # | 验证项 | 涉及文件 | 测试层级 | 当前覆盖 | 缺口 |
|---|--------|---------|---------|---------|------|
| O-1 | Order CRUD (save/get/update) | pg_order_repository.py | PG 集成 | ❌ 无 | 需新建 |
| O-2 | save_batch 批量写入 | pg_order_repository.py | PG 集成 | ❌ 无 | 需新建 |
| O-3 | get_order_by_exchange_id 查询 | pg_order_repository.py | PG 集成 | ❌ 无 | 需新建 |
| O-4 | get_orders_by_signal 排序正确性 | pg_order_repository.py | PG 集成 | ❌ 无 | 需新建 |
| O-5 | get_open_orders 过滤 OPEN+PARTIALLY_FILLED | pg_order_repository.py | PG 集成 | ❌ 无 | 需新建 |
| O-6 | update_status 部分更新（不覆盖其他字段） | pg_order_repository.py | PG 集成 | ❌ 无 | 需新建 |
| O-7 | ORM ↔ Domain 双向映射（所有枚举字段） | pg_order_repository.py + pg_models.py | PG 集成 | ❌ 无 | 需新建 |
| O-8 | CheckConstraint 校验（direction, status 等） | pg_models.py | PG 集成 | ❌ 无 | 需新建 |
| O-9 | parent_order_id 外键 + OCO group | pg_order_repository.py | PG 集成 | ❌ 无 | 需新建 |
| O-10 | OrderLifecycleService 全生命周期 | order_lifecycle_service.py | 单元+集成 | ✅ SQLite 集成 | PG 切换验证 |
| O-11 | Order 状态机转换合法性 | order_lifecycle_service.py | 单元 | ✅ 充分 | — |
| O-12 | EXIT progressed callback (B.1-B.5) | order_lifecycle_service.py | 单元 | ✅ 充分 | — |

### 3.2 Execution Intents 链路

| # | 验证项 | 涉及文件 | 测试层级 | 当前覆盖 | 缺口 |
|---|--------|---------|---------|---------|------|
| I-1 | Intent CRUD (save/get/list) | pg_execution_intent_repository.py | PG 集成 | ❌ 无 | 需新建 |
| I-2 | get_by_signal_id 查询 | pg_execution_intent_repository.py | PG 集成 | ❌ 无 | 需新建 |
| I-3 | get_by_order_id 查询 | pg_execution_intent_repository.py | PG 集成 | ❌ 无 | 需新建 |
| I-4 | list_unfinished 过滤终态 | pg_execution_intent_repository.py | PG 集成 | ❌ 无 | 需新建 |
| I-5 | update_status 部分列更新 | pg_execution_intent_repository.py | PG 集成 | ❌ 无 | 需新建 |
| I-6 | JSONB signal_payload 序列化/反序列化 | pg_execution_intent_repository.py | PG 集成 | ❌ 无 | 需新建 |
| I-7 | JSONB strategy_payload 序列化/反序列化 | pg_execution_intent_repository.py | PG 集成 | ❌ 无 | 需新建 |
| I-8 | Partial unique index (order_id, exchange_order_id) | pg_models.py | PG 集成 | ❌ 无 | 需新建 |
| I-9 | Repo-first 语义（内存丢失后从 PG 恢复） | execution_orchestrator.py | 单元 | ✅ Fake repo | PG 真实验证 |
| I-10 | Intent 状态机转换（_can_transition_intent） | execution_orchestrator.py | 单元 | ✅ 充分 | — |

### 3.3 Positions 链路

| # | 验证项 | 涉及文件 | 测试层级 | 当前覆盖 | 缺口 |
|---|--------|---------|---------|---------|------|
| P-1 | Position save/get (ORM ↔ Domain) | pg_position_repository.py | PG 集成 | ❌ 被 skip | 需启用 |
| P-2 | list_active 过滤 is_closed=False | pg_position_repository.py | PG 集成 | ❌ 无 | 需新建 |
| P-3 | JSONB position_payload 完整打包/解包 | pg_position_repository.py | PG 集成 | ❌ 无 | 需新建 |
| P-4 | watermark_price 持久化 + 恢复 | pg_position_repository.py | PG 集成 | ❌ 无 | 需新建 |
| P-5 | projected_exit_fills 持久化 + 恢复 | pg_position_repository.py | PG 集成 | ❌ 无 | 需新建 |
| P-6 | projected_exit_fees 持久化 + 恢复 | pg_position_repository.py | PG 集成 | ❌ 无 | 需新建 |
| P-7 | save 时 existing ORM 字段保留（mark_price, leverage） | pg_position_repository.py | PG 集成 | ❌ 无 | 需新建 |
| P-8 | project_entry_fill 逻辑 | position_projection_service.py | 单元 | ✅ MagicMock repo | — |
| P-9 | project_exit_fill delta 幂等 | position_projection_service.py | 单元 | ✅ 充分 | — |
| P-10 | gross_pnl / watermark 计算 | position_projection_service.py | 单元 | ✅ 充分 | — |

### 3.4 Recovery Tasks 链路

| # | 验证项 | 涉及文件 | 测试层级 | 当前覆盖 | 缺口 |
|---|--------|---------|---------|---------|------|
| R-1 | create_task 插入 | pg_execution_recovery_repository.py | PG 集成 | ❌ 仅 mock | 需新建 |
| R-2 | list_active 时间窗口过滤 | pg_execution_recovery_repository.py | PG 集成 | ❌ 仅 mock | 需新建 |
| R-3 | list_blocking（不看 next_retry_at） | pg_execution_recovery_repository.py | PG 集成 | ❌ 仅 mock | 需新建 |
| R-4 | mark_resolved/retrying/failed 状态流转 | pg_execution_recovery_repository.py | PG 集成 | ❌ 仅 mock | 需新建 |
| R-5 | CheckConstraint recovery_type 限制 | pg_models.py | PG 集成 | ❌ 无 | 需新建 |
| R-6 | context_payload JSONB 序列化 | pg_execution_recovery_repository.py | PG 集成 | ❌ 无 | 需新建 |
| R-7 | Recovery task 创建（orchestrator 触发） | execution_orchestrator.py | 单元 | ✅ mock repo | — |
| R-8 | Circuit breaker 从 PG recovery 重建 | execution_orchestrator.py | 单元 | ✅ mock repo | PG 真实验证 |

### 3.5 Startup Reconciliation 链路

| # | 验证项 | 涉及文件 | 测试层级 | 当前覆盖 | 缺口 |
|---|--------|---------|---------|---------|------|
| S-1 | 启动时从 PG 加载 active recovery tasks | main.py + startup 逻辑 | 冒烟 | ⚠️ 仅 mock | 需真实验证 |
| S-2 | Circuit breaker 从 PG 恢复到内存 | execution_orchestrator.py | 单元 | ✅ mock | PG 真实验证 |
| S-3 | PG backend 选择逻辑（database.py） | database.py | 单元 | ✅ env mock | — |
| S-4 | validate_pg_core_configuration 校验 | database.py | 单元 | ✅ 充分 | — |
| S-5 | init_pg_core_db 表创建 | database.py + pg_models.py | 冒烟 | ❌ 无 | 需真实验证 |

### 3.6 Partial Fill / Order Status Transition 链路

| # | 验证项 | 涉及文件 | 测试层级 | 当前覆盖 | 缺口 |
|---|--------|---------|---------|---------|------|
| F-1 | 首次 partial fill → 增量保护 | execution_orchestrator.py | 单元 | ✅ 8 场景充分 | — |
| F-2 | 增量 delta 计算幂等 | execution_orchestrator.py | 单元 | ✅ 充分 | — |
| F-3 | 单 SL 约束（cancel 旧 + 创建新） | execution_orchestrator.py | 单元 | ✅ 4 场景 | — |
| F-4 | Cancel SL 失败 → circuit breaker + recovery | execution_orchestrator.py | 单元 | ✅ 充分 | — |
| F-5 | _apply_placed_order_status 5 种状态 | execution_orchestrator.py | 单元 | ✅ 充分 | — |
| F-6 | Intent 状态 only-forward 保护 | execution_orchestrator.py | 单元 | ✅ 充分 | — |
| F-7 | PARTIALLY_FILLED 不被 tail 覆盖 | execution_orchestrator.py | 单元 | ✅ 充分 | — |
| F-8 | 全链路：signal → intent → order → fill → protection → position | 端到端 | 冒烟 | ⚠️ 仅 mock | 需真实验证 |

### 3.7 Runtime Health / Overview / Execution Readonly 链路

| # | 验证项 | 涉及文件 | 测试层级 | 当前覆盖 | 缺口 |
|---|--------|---------|---------|---------|------|
| H-1 | /api/runtime/overview 数据聚合 | api_console_runtime.py | 单元 | ✅ mock | — |
| H-2 | /api/runtime/health PG status 报告 | runtime_health.py | 单元 | ✅ mock | — |
| H-3 | /api/runtime/positions fallback 到 position_repo | api_console_runtime.py | 单元 | ✅ mock | — |
| H-4 | /api/runtime/execution/orders 查询 PG repo | api_console_runtime.py | 单元 | ✅ mock | PG 真实验证 |
| H-5 | /api/runtime/execution/intents 查询 PG repo | api_console_runtime.py | 单元 | ✅ mock | PG 真实验证 |
| H-6 | Backend summary 正确识别 postgres backend | runtime_health.py | 单元 | ✅ 充分 | — |
| H-7 | Overview-health 一致性 | runtime_health.py | 单元 | ✅ 充分 | — |

---

## 四、测试层级设计

### 4.1 单元测试（已有，需确认通过）

**目标**: 验证业务逻辑正确性，不依赖真实 PG

**已覆盖且充分的**:
- ExecutionOrchestrator: partial fill 增量保护（8 场景）、状态机转换、circuit breaker、recovery task 创建
- OrderLifecycleService: 全生命周期状态转换、callback 触发、audit logging
- PositionProjectionService: entry/exit fill 投影、delta 幂等、PnL 计算、watermark
- Runtime readmodels: overview/health/positions 聚合逻辑

**执行方式**: `pytest tests/unit/ -v --tb=short`
**预计耗时**: 2-3 分钟
**是否需要用户确认**: 否（纯本地，无副作用）

### 4.2 PG 集成测试（需新建，待执行）

**目标**: 验证 PG Repository 层的真实 CRUD + ORM 映射 + JSONB 序列化

**需要新建的测试文件**:
1. `tests/integration/test_pg_order_repository.py` — O-1 ~ O-9
2. `tests/integration/test_pg_execution_intent_repository.py` — I-1 ~ I-8
3. `tests/integration/test_pg_position_repository.py` — P-1 ~ P-7（启用被 skip 的测试 + 扩展）
4. `tests/integration/test_pg_recovery_repository.py` — R-1 ~ R-6

**前置条件**:
- PG 容器运行（`docker-compose -f docker-compose.pg.yml up -d`）
- `PG_DATABASE_URL` 环境变量设置
- `init_pg_core_db()` 完成表创建

**执行方式**: `pytest tests/integration/test_pg_*.py -v --tb=long -m integration`
**预计耗时**: 5-10 分钟
**是否需要用户确认**: ⚠️ **是**（需要 PG 容器 + 数据库写入）

### 4.3 冒烟验证（需手动/半自动执行）

**目标**: 验证端到端链路在真实 PG 上的基本可用性

**冒烟清单**:

| # | 冒烟项 | 验证方式 | 验收标准 |
|---|--------|---------|---------|
| SM-1 | PG 表创建成功 | `init_pg_core_db()` 无异常 | 4 张表存在 |
| SM-2 | Order 写入→读出一致 | 手动 save + get | 字段完全匹配 |
| SM-3 | Intent JSONB 写入→读出一致 | 手动 save + get | signal_payload 可反序列化为 SignalResult |
| SM-4 | Position JSONB 写入→读出一致 | 手动 save + get | position_payload 包含 watermark/projection |
| SM-5 | Startup reconciliation 端到端 | 启动应用 → 插入 recovery task → 重启 → 检查 circuit breaker | breaker set 包含对应 symbol |
| SM-6 | Runtime API /execution/intents 返回 PG 数据 | curl /api/runtime/execution/intents | 返回真实 intent 列表 |
| SM-7 | Runtime API /execution/orders 返回 PG 数据 | curl /api/runtime/execution/orders | 返回真实 order 列表 |

**执行方式**: 手动或编写临时脚本
**预计耗时**: 15-30 分钟
**是否需要用户确认**: ⚠️ **是**（需要 PG 容器 + 可能影响运行中数据）

### 4.4 必须等用户确认后才执行的验证

| 验证项 | 原因 | 确认要点 |
|--------|------|---------|
| PG 集成测试全部 | 需要 PG 容器 + 数据库写入 | 确认 PG 容器可用 + 数据可清理 |
| Startup reconciliation 冒烟 | 需要重启应用 | 确认当前无活跃交易 |
| Runtime API 真实查询 | 需要应用运行中 | 确认不影响当前执行主线 |
| Circuit breaker 重建冒烟 | 可能阻塞 symbol | 确认不会误阻塞真实交易 |

### 4.5 现在只需要设计、不需要执行的验证

| 验证项 | 原因 | 优先级 |
|--------|------|--------|
| 并发写入 PG 的压力测试 | 当前单人单体应用，非紧急 | P2 |
| PG 连接池耗尽场景 | 生产环境才需要 | P2 |
| PG 主从切换场景 | 当前单实例 | P3 |
| 跨进程 recovery 一致性 | 需要多实例部署 | P3 |
| 超大 position_payload JSONB 性能 | 当前数据量不触发 | P3 |

---

## 五、验证缺口清单

### 5.1 已有测试覆盖（可信赖）

| 模块 | 覆盖度 | 信心 |
|------|--------|------|
| ExecutionOrchestrator 业务逻辑 | 高（16+ 场景） | 🟢 高 |
| OrderLifecycleService 状态机 | 高（20+ 场景） | 🟢 高 |
| PositionProjectionService 计算 | 高（30+ 场景） | 🟢 高 |
| Runtime readmodels 聚合 | 中（14+ 场景） | 🟢 高 |
| Circuit breaker 逻辑 | 中（4 场景） | 🟡 中（mock） |

### 5.2 代码改了但缺测试

| 文件 | 最近变更 | 缺口 |
|------|---------|------|
| `pg_order_repository.py` | 无直接测试 | **零覆盖** |
| `pg_execution_intent_repository.py` | 无直接测试 | **零覆盖** |
| `pg_position_repository.py` | commit `3f761bd` +161 行 | **唯一测试被 skip** |
| `pg_execution_recovery_repository.py` | commit `c91e153` 变更 | **全部 mock** |
| `database.py` init_pg_core_db | 无真实验证 | **零覆盖** |

### 5.3 有测试但不足以证明 PG 真源闭环

| 场景 | 为什么不够 |
|------|-----------|
| FakeExecutionIntentRepository 验证 repo-first | Fake 是内存 dict，不验证 PG JSONB 序列化、网络延迟、连接池行为 |
| SQLite OrderRepository 验证 lifecycle | SQLite 不支持 JSONB、CheckConstraint、Partial Index，PG 特有行为未覆盖 |
| MagicMock PG session 验证 recovery | 不验证真实 SQL 执行、事务提交、连接回收 |
| Mock position_repo 验证 projection | 不验证 PG position_payload JSONB 的打包/解包正确性 |

### 5.4 最容易出现"测试过了但观察面仍不可信"的地方

| 风险点 | 说明 |
|--------|------|
| **JSONB 反序列化失败静默吞错** | `_to_domain` 中 `SignalResult.model_validate(orm.signal_payload)` 如果 JSONB 损坏，可能抛异常或返回错误数据，但 mock 测试永远不触发 |
| **PG CheckConstraint 违反** | ORM 写入非法枚举值时，PG 会拒绝但 SQLAlchemy 可能只抛通用 IntegrityError，mock 测试不触发 |
| **list_active 排序 + 过滤** | position_repo.list_active 的 `is_closed=False` + `ORDER BY updated_at DESC` 在真实 PG 上的行为未验证 |
| **list_blocking vs list_active 语义差异** | recovery repo 的两个 list 方法在真实 PG 上的时间窗口过滤未验证 |
| **Startup reconciliation 时序** | 应用启动时 PG 连接是否就绪、表是否已创建、recovery tasks 是否已加载——这个时序在 mock 中被跳过 |
| **Runtime API 的 _load_api_module() 动态导入** | 运行时动态 import + 访问模块级单例，mock 测试不验证这个路径的真实行为 |

---

## 六、明日验证顺序（验证包）

### 建议执行顺序

```
Phase A: 基础设施就绪（10 min）
  ↓
Phase B: PG Repository 集成测试（30 min）
  ↓
Phase C: 端到端冒烟验证（20 min）
  ↓
Phase D: Runtime API 真实查询验证（10 min）
  ↓
Phase E: 异常场景验证（20 min）
```

### Phase A: 基础设施就绪

| 步骤 | 操作 | 目标 | 验收标准 | 风险 |
|------|------|------|---------|------|
| A-1 | `docker-compose -f docker-compose.pg.yml up -d` | PG 容器启动 | `pg_isready` 返回 OK | 端口 5432 被占用 |
| A-2 | 设置 `PG_DATABASE_URL` 环境变量 | 连接串就绪 | `psql $PG_DATABASE_URL -c '\dt'` 可连 | 密码/端口不匹配 |
| A-3 | 运行 `init_pg_core_db()` | 4 张表创建 | `\dt` 显示 orders, execution_intents, positions, execution_recovery_tasks | 表已存在（幂等） |
| A-4 | 运行 `pytest tests/unit/ -v --tb=short` | 单元测试基线 | 全部通过 | 无 |

**失败排查**: `database.py` → `pg_models.py` → `docker-compose.pg.yml` → `.env.local`

### Phase B: PG Repository 集成测试

| 步骤 | 操作 | 目标 | 验收标准 | 风险 |
|------|------|------|---------|------|
| B-1 | 运行 `test_pg_order_repository.py` | Order CRUD + ORM 映射 | 所有 save/get/update 查询正确 | ORM 字段映射遗漏 |
| B-2 | 运行 `test_pg_execution_intent_repository.py` | Intent CRUD + JSONB | signal_payload 反序列化为 SignalResult | JSONB 序列化不兼容 |
| B-3 | 运行 `test_pg_position_repository.py` | Position CRUD + JSONB | position_payload 完整打包/解包 | existing 字段保留逻辑 |
| B-4 | 运行 `test_pg_recovery_repository.py` | Recovery CRUD + 时间过滤 | list_active 时间窗口正确 | next_retry_at 比较逻辑 |

**失败排查**: `pg_models.py`（ORM 定义）→ 对应 `pg_*_repository.py`（映射逻辑）→ `pg_models.py`（CheckConstraint）

### Phase C: 端到端冒烟验证

| 步骤 | 操作 | 目标 | 验收标准 | 风险 |
|------|------|------|---------|------|
| C-1 | 手动构造 SignalResult → execute_signal | 完整链路走通 | Intent 状态到 SUBMITTED/COMPLETED，Order 写入 PG | Gateway 连接（可用 testnet） |
| C-2 | 模拟 partial fill → 检查保护单 | 增量保护在 PG 上正确 | SL/TP 订单写入 PG，requested_qty 覆盖全量 | Exchange API 限流 |
| C-3 | 检查 position projection | ENTRY fill 投影到 PG positions | position 记录存在，current_qty 正确 | — |
| C-4 | 检查 runtime API /execution/intents | PG 数据可查询 | 返回真实 intent 列表 | API 未启动 |

**失败排查**: `execution_orchestrator.py`（主链路）→ `order_lifecycle_service.py`（状态推进）→ `position_projection_service.py`（投影）

### Phase D: Runtime API 真实查询验证

| 步骤 | 操作 | 目标 | 验收标准 | 风险 |
|------|------|------|---------|------|
| D-1 | `curl localhost:8000/api/runtime/execution/orders` | Order 查询走 PG | 返回 Phase C 写入的 orders | repo 注入错误 |
| D-2 | `curl localhost:8000/api/runtime/execution/intents` | Intent 查询走 PG | 返回 Phase C 写入的 intents | — |
| D-3 | `curl localhost:8000/api/runtime/positions` | Position 查询走 PG | 返回 Phase C 投影的 positions | fallback 到 snapshot |
| D-4 | `curl localhost:8000/api/runtime/health` | Health 报告 PG 状态 | backend_summary 显示 postgres | — |

**失败排查**: `api_console_runtime.py`（readmodel 构建）→ `api.py`（repo 注入）→ `readmodels/runtime_health.py`（聚合逻辑）

### Phase E: 异常场景验证

| 步骤 | 操作 | 目标 | 验收标准 | 风险 |
|------|------|------|---------|------|
| E-1 | 插入 recovery task → 重启应用 → 检查 circuit breaker | Startup reconciliation | blocker symbol 被恢复 | 时序问题 |
| E-2 | 模拟 SL cancel 失败 → 检查 recovery task 创建 | Recovery 链路 | task 写入 PG，symbol 被 block | — |
| E-3 | 检查 PG 连接断开时的降级行为 | 容错 | 不 crash，合理错误信息 | — |

**失败排查**: `execution_orchestrator.py`（recovery 触发）→ `pg_execution_recovery_repository.py`（task 持久化）→ `main.py`（startup reconciliation）

---

## 七、关键文件路径速查

```
# 核心业务逻辑
src/application/execution_orchestrator.py
src/application/order_lifecycle_service.py
src/application/position_projection_service.py

# PG Repository 层
src/infrastructure/pg_order_repository.py
src/infrastructure/pg_execution_intent_repository.py
src/infrastructure/pg_position_repository.py
src/infrastructure/pg_execution_recovery_repository.py
src/infrastructure/pg_models.py
src/infrastructure/repository_ports.py

# Runtime API
src/interfaces/api_console_runtime.py
src/application/readmodels/runtime_health.py

# 启动与配置
src/main.py
src/interfaces/api.py
src/infrastructure/database.py

# 测试基础设施
docker-compose.pg.yml
.env.local
tests/unit/conftest.py

# 现有测试（参考）
tests/unit/test_execution_orchestrator_partial_fill.py
tests/unit/test_order_lifecycle_service.py
tests/unit/test_position_projection_service.py
tests/unit/test_pg_source_skeleton.py
tests/unit/test_console_runtime_readmodels.py
tests/unit/test_pg_execution_recovery_repository.py
tests/unit/test_execution_intent_repo_first.py
tests/unit/test_partial_fill_single_sl.py
tests/unit/test_sim_trading_readiness.py
tests/integration/test_order_lifecycle_e2e.py
```

---

## 八、附录：待新建测试文件清单

| 文件 | 覆盖矩阵编号 | 优先级 |
|------|-------------|--------|
| `tests/integration/test_pg_order_repository.py` | O-1 ~ O-9 | P0 |
| `tests/integration/test_pg_execution_intent_repository.py` | I-1 ~ I-8 | P0 |
| `tests/integration/test_pg_position_repository.py` | P-1 ~ P-7 | P0 |
| `tests/integration/test_pg_recovery_repository.py` | R-1 ~ R-6 | P0 |
| `tests/integration/test_pg_startup_reconciliation.py` | S-1, S-2, S-5 | P1 |
| `tests/smoke/test_pg_e2e_smoke.py` | SM-1 ~ SM-7 | P1 |

---

*本文档仅设计验证资产，未执行任何测试。所有"当前覆盖"评估基于代码审查和测试文件分析。*
