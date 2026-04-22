# PG 核心双轨迁移测试计划

> 日期：2026-04-22
> 范围：SQLite 保留、PG 新增实现、核心表先切 PG

---

## 一、测试目标

本轮测试不是验证“全系统已迁移到 PG”，而是验证：

1. SQLite 旧实现仍可保留运行
2. PG 新增实现可以承接核心表
3. 核心执行链可以切换到 PG 而不破坏现有语义
4. 迁移期间依赖注入边界清晰、不会误走错库

---

## 二、测试分层

### 2.1 设计阶段测试文档

当前先定义开发前测试用例，不执行耗时测试。

### 2.2 后续测试层级

1. 单元测试
   - PG 仓储方法
   - 接口/工厂选择逻辑
   - `ExecutionIntent` 持久化语义

2. 集成测试
   - PG schema 初始化
   - `OrderLifecycleService` + PG repo
   - `ExecutionOrchestrator` + PG intent repo

3. 保守冒烟验证
   - SQLite 旧链路未被破坏

---

## 三、开发前必须准备的测试集合

### A. 基础设施层：PG 基建

#### T-A1 `database.py` 可创建 PG async engine

验证：

- 从 `DATABASE_URL` 正常初始化
- sessionmaker 可创建 `AsyncSession`

#### T-A2 缺失 `DATABASE_URL` 时给出明确错误

验证：

- 启动配置异常可定位

#### T-A3 PG schema 初始化仅覆盖核心表

验证：

- 能初始化 `orders / execution_intents / positions`
- 不要求一次性初始化所有 SQLite 旧表

---

### B. 仓储接口层：依赖边界

#### T-B1 `OrderRepositoryPort` 的 SQLite 实现可继续工作

验证：

- 旧 `OrderRepository` 仍满足最小接口能力

#### T-B2 `OrderRepositoryPort` 的 PG 实现可替代 SQLite 实现

验证：

- `save/get/get_by_exchange_id/get_orders_by_signal` 等最小方法一致

#### T-B3 `ExecutionIntentRepositoryPort` 可持久化 strategy snapshot

验证：

- 保存后再读取，`strategy snapshot` 内容一致
- 不依赖 orchestrator 内存字典

#### T-B4 `PositionRepositoryPort` 可查询/保存核心仓位状态

验证：

- 创建/更新/查询可用

---

### C. 核心表：orders

#### T-C1 PG orders 表与当前核心字段兼容

验证字段至少包括：

- `id`
- `signal_id`
- `symbol`
- `direction`
- `order_type`
- `order_role`
- `price`
- `trigger_price`
- `requested_qty`
- `filled_qty`
- `average_exec_price`
- `status`
- `reduce_only`
- `parent_order_id`
- `oco_group_id`
- `exchange_order_id`
- `created_at`
- `updated_at`

#### T-C2 PG `save()` 保持 UPSERT 语义

验证：

- 首次写入成功
- 二次写入可更新状态与成交字段
- 不误覆盖关键字段

#### T-C3 `get_order_by_exchange_id()` 在 PG 下可用

验证：

- WebSocket / 对账依赖路径可继续工作

---

### D. 核心表：execution_intents

#### T-D1 可保存新建 intent

验证：

- `PENDING/BLOCKED/SUBMITTED/FAILED/...` 状态可持久化

#### T-D2 intent 读取后仍保有 strategy snapshot

验证：

- 读取出的 `tp_ratios / tp_targets / initial_stop_loss_rr` 不丢失

#### T-D3 `get_by_order_id()` 可用于 partial-fill 回调恢复上下文

验证：

- partial-fill 路径不再依赖纯内存查找

#### T-D4 `list_unfinished()` 能返回未完成 intents

验证：

- 为后续启动恢复打底

---

### E. 核心表：positions

#### T-E1 Position ORM/Repo 在 PG 下可正常保存与读取

#### T-E2 现有 `PositionManager` 的 PG 行锁路径可继续工作

验证：

- `with_for_update()` 路线不被当前迁移破坏

---

### F. 服务层切换

#### T-F1 `OrderLifecycleService` 能注入 PG order repo

验证：

- 创建订单
- 提交订单
- 更新状态

#### T-F2 `ExecutionOrchestrator` 能注入 PG intent repo

验证：

- `execute_signal()` 创建 intent 时落库
- 后续根据 `order_id` 找回 intent

#### T-F3 `StartupReconciliationService` 能基于 PG order repo 工作

验证：

- 最小查询路径不依赖 SQLite 特性

---

### G. 双轨并存

#### T-G1 SQLite 旧订单仓储不受 PG 新增实现影响

验证：

- 旧测试仍可跑
- 初始化时不强制要求 PG 替代 SQLite

#### T-G2 配置切换能明确选择核心链路使用 PG

验证：

- 核心服务拿到的是 PG 实现
- 未迁移模块仍可继续用 SQLite

#### T-G3 不会误发生“核心链路部分走 PG、部分走 SQLite”

验证：

- 同一条执行链依赖注入来源一致

---

## 四、建议测试文件拆分

建议新增或扩展以下测试文件：

1. `tests/unit/infrastructure/test_pg_order_repository.py`
2. `tests/unit/infrastructure/test_pg_execution_intent_repository.py`
3. `tests/unit/infrastructure/test_pg_position_repository.py`
4. `tests/unit/test_execution_orchestrator_pg_intent.py`
5. `tests/integration/test_pg_core_chain.py`
6. `tests/integration/test_dual_track_repository_binding.py`

---

## 五、验收标准

本轮开发开始前，先以本测试计划为准。

本轮骨架开发完成后，最低验收标准：

1. PG 核心 schema 可初始化
2. PG `orders` repo 最小 CRUD 可用
3. PG `execution_intents` repo 最小 CRUD 可用
4. `OrderLifecycleService` 与 `ExecutionOrchestrator` 已具备注入新实现的能力
5. SQLite 旧实现未被破坏

---

## 六、当前不进入测试执行的内容

按当前项目红线，本阶段不直接执行完整测试，仅先完成：

1. 测试设计
2. 用例清单
3. 后续开发的测试边界固定

待用户确认后，再进入测试执行阶段。
