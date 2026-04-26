# Runtime / Console 观测口径收口方案

> **审计日期**: 2026-04-26
> **审计范围**: 所有 runtime 观测面（API endpoints + readmodels + 前端契约）
> **约束**: 不修改 src/，仅审计 + 设计方案

---

## 一、当前观测面可信度结论

### 总体评估：**70/100 — 可用但有结构性风险**

| 维度 | 评分 | 说明 |
|------|------|------|
| **PG 主线数据源正确性** | 85/100 | Orders/Positions/Intents/Recovery 均通过 PG factory 创建，数据源正确 |
| **注入链路完整性** | 75/100 | main.py 嵌入模式注入完整；lifespan 独立模式有自建兜底 |
| **Console ReadModel 可信度** | 70/100 | 大部分读正确 repo，但 positions 口径混用（account_snapshot 优先于 PG） |
| **前端契约一致性** | 55/100 | 多处字段映射错误、类型不匹配、mock 数据残留 |
| **Fallback/空注入防御** | 65/100 | 部分 readmodel 有 None 检查，但部分返回空结果无告警 |

### 关键风险摘要

1. **Positions 口径混用**（P1）：`/api/v3/positions` 和 `/api/runtime/positions` 都优先读 `account_snapshot`（交易所实时），fallback 到 PG `position_repo`。当交易所不可用时返回空，但 PG 可能有数据。前端看到空仓位，但实际执行主链在 PG 中有活跃投影。
2. **Signals/Attempts 读 SQLite**（P2）：`/api/runtime/signals` 和 `/api/runtime/attempts` 读 `SignalRepository`（SQLite），这是正确的（信号是预执行实体，无 PG 路径），但前端可能误以为这是"执行态"数据。
3. **前端字段映射错误**（P2）：`getRuntimeOrders` adapter 把 `side` 映射为 `role`，语义错误；`getRuntimeOrders` 丢失 `type` 字段。
4. **PG 健康度永远 DEGRADED**（P3）：`RuntimeHealthReadModel` 和 `RuntimeOverviewReadModel` 的 `pg_health` 永远返回 `"DEGRADED"`，因为没有真实的 PG 连通性探针。

---

## 二、Endpoint / ReadModel 来源审计映射表

### 2.1 Console Runtime API（`/api/runtime/*`）

| Endpoint | ReadModel | 数据来源 | 注入点 | 可信度 | 问题 |
|----------|-----------|----------|--------|--------|------|
| `GET /api/runtime/overview` | `RuntimeOverviewReadModel` | runtime_config_provider + account_snapshot + exchange_gateway + execution_orchestrator + order_repo + position_repo + execution_intent_repo | `_load_api_module()` 直接读全局变量 | ✅ 高 | `pg_health` 永远 DEGRADED |
| `GET /api/runtime/portfolio` | `RuntimePortfolioReadModel` | account_snapshot + capital_protection + runtime_config_provider | 同上 | ✅ 高 | 无 PG fallback，account_snapshot 为空时全零 |
| `GET /api/runtime/health` | `RuntimeHealthReadModel` | runtime_config_provider + exchange_gateway + execution_orchestrator + execution_recovery_repo + startup_reconciliation_summary + account_snapshot | 同上 | ⚠️ 中 | pg_status 永远 DEGRADED；recovery_tasks 读 PG 正确 |
| `GET /api/runtime/positions` | `RuntimePositionsReadModel` | **account_snapshot 优先** → position_repo fallback | 同上 | ⚠️ 中 | 口径混用：交易所数据 vs PG 投影 |
| `GET /api/runtime/signals` | `RuntimeSignalsReadModel` | signal_repo (SQLite `SignalRepository`) | 同上 | ✅ 高 | 信号是预执行实体，SQLite 正确 |
| `GET /api/runtime/attempts` | `RuntimeAttemptsReadModel` | signal_repo (SQLite `SignalRepository`) | 同上 | ✅ 高 | 同上 |
| `GET /api/runtime/execution/orders` | `RuntimeOrdersReadModel` | order_repo (PG `PgOrderRepository`) | 同上 | ✅ 高 | 读 PG 正确 |
| `GET /api/runtime/execution/intents` | `RuntimeExecutionIntentsReadModel` | intent_repo (PG `PgExecutionIntentRepository`) | 同上 | ✅ 高 | 读 PG 正确 |

### 2.2 V3 API（`/api/v3/*`）

| Endpoint | 数据来源 | 注入点 | 可信度 | 问题 |
|----------|----------|--------|--------|------|
| `GET /api/v3/positions` | exchange_gateway.fetch_positions **优先** → position_repo.list_active fallback | `_get_exchange_gateway()` + `_get_position_repo()` | ⚠️ 中 | 交易所失败时 fallback PG，但 `is_closed=True` 直接返回空（不查 PG） |
| `GET /api/v3/positions/{id}` | position_repo.get() (PG) | `_get_position_repo()` | ✅ 高 | 直接读 PG |
| `GET /api/v3/orders` | order_repo.get_orders() (PG) | `_get_order_repo()` | ✅ 高 | 读 PG 正确 |
| `GET /api/v3/orders/tree` | order_repo.get_order_tree() | `_get_order_repo()` | ⚠️ 中 | PG 版本无 `get_order_tree()` 方法，可能 fallback 到 SQLite |
| `GET /api/v3/account/balance` | exchange_gateway.fetch_account_balance() | `_get_exchange_gateway()` | ✅ 高 | 实时交易所数据 |
| `GET /api/v3/account/snapshot` | exchange_gateway.get_account_snapshot() | `_get_exchange_gateway()` | ✅ 高 | 实时缓存数据 |

### 2.3 Legacy API（`/api/*`）

| Endpoint | 数据来源 | 注入点 | 可信度 | 问题 |
|----------|----------|--------|--------|------|
| `GET /api/health` | 纯时间戳 | 无依赖 | ✅ 高 | 无实际健康检查 |
| `GET /api/signals` | signal_repo (SQLite) | `_get_repository()` | ✅ 高 | 信号是预执行实体 |
| `GET /api/attempts` | signal_repo (SQLite) | `_get_repository()` | ✅ 高 | 同上 |
| `GET /api/account` | account_getter (内存缓存) | `_account_getter` | ⚠️ 中 | 依赖轮询更新，可能过期 |
| `GET /api/diagnostics` | signal_repo (SQLite) | `_get_repository()` | ✅ 高 | 诊断数据 |

### 2.4 Research API（`/api/research/*`）

| Endpoint | 数据来源 | 可信度 | 问题 |
|----------|----------|--------|------|
| `GET /api/research/candidates` | CandidateArtifactService (文件系统) | ✅ 高 | 只读文件扫描 |
| `GET /api/research/candidates/{name}` | CandidateArtifactService | ✅ 高 | 同上 |
| `GET /api/research/replay/{name}` | CandidateArtifactService | ✅ 高 | 同上 |

---

## 三、依赖注入链路审计

### 3.1 main.py 嵌入模式（生产路径）

```
main.py run_application()
  → create_runtime_order_repository()     → PgOrderRepository ✅
  → create_execution_intent_repository()  → PgExecutionIntentRepository ✅
  → create_runtime_position_repository()  → PgPositionRepository ✅
  → set_dependencies(order_repo=..., position_repo=..., ...)
  → set_v3_dependencies(execution_orchestrator=..., ...)
```

**结论**: 嵌入模式注入链路正确，所有核心 repo 均为 PG。

### 3.2 api.py lifespan 独立模式（开发/测试路径）

```
api.py lifespan()
  → create_runtime_order_repository()     → PgOrderRepository ✅
  → create_execution_intent_repository()  → PgExecutionIntentRepository ✅
  → create_runtime_position_repository()  → PgPositionRepository ✅
  → 自建 ExchangeGateway + ExecutionOrchestrator（如果 _exchange_gateway is None）
```

**结论**: 独立模式注入链路正确，但有自建兜底逻辑。

### 3.3 Console Runtime 路由注入

```
api_console_runtime.py
  → _load_api_module()  # 动态导入 api.py 模块
  → getattr(api_module, "_order_repo", None)     # 直接读全局变量
  → getattr(api_module, "_position_repo", None)
  → getattr(api_module, "_execution_intent_repo", None)
```

**结论**: Console 路由通过 `_load_api_module()` + `getattr` 读取全局变量，与 `set_dependencies()` 注入的变量一致。**但有一个风险**：如果 lifespan 先于 `set_dependencies()` 执行，全局变量可能尚未设置。

### 3.4 注入一致性检查

| 全局变量 | set_dependencies 设置 | lifespan 初始化 | Console 路由读取 | 一致？ |
|----------|----------------------|----------------|-----------------|--------|
| `_order_repo` | ✅ | ✅ | ✅ `_load_api_module()._order_repo` | ✅ |
| `_position_repo` | ✅ | ✅ | ✅ `_load_api_module()._position_repo` | ✅ |
| `_execution_intent_repo` | ✅ | ✅ | ✅ `_load_api_module()._execution_intent_repo` | ✅ |
| `_signal_repo` | ✅ (= `_repository`) | ✅ (= `_repository`) | ✅ `_load_api_module()._signal_repo` | ✅ |
| `_exchange_gateway` | ✅ | ✅ | ✅ `_load_api_module()._exchange_gateway` | ✅ |
| `_account_getter` | ✅ | ❌ lifespan 不设置 | ✅ `_load_api_module()._account_getter` | ⚠️ 独立模式为 None |
| `_runtime_config_provider` | ✅ | ✅ | ✅ `_load_api_module()._runtime_config_provider` | ✅ |
| `_execution_recovery_repo` | ✅ | ✅ | ✅ `_load_api_module()._execution_recovery_repo` | ✅ |

**发现**: `_account_getter` 在 lifespan 独立模式下不设置，导致 Console runtime 的 overview/portfolio/health/positions 在独立模式下 account_snapshot 永远为 None。

---

## 四、前端契约审计

### 4.1 前端 API 调用映射

| 前端页面 | 调用的 API | 前端类型 | 后端类型 | 匹配？ |
|----------|-----------|----------|----------|--------|
| Overview | `GET /api/runtime/overview` | `RuntimeOverview` | `RuntimeOverviewResponse` | ✅ |
| Portfolio | `GET /api/runtime/portfolio` | `PortfolioContext` | `RuntimePortfolioResponse` | ⚠️ 字段名差异 |
| Health | `GET /api/runtime/health` | `RuntimeHealth` | `RuntimeHealthResponse` | ✅ |
| Signals | `GET /api/runtime/signals` | `Signal[]` | `ConsoleSignalsResponse` | ✅ |
| Attempts | `GET /api/runtime/attempts` | `Attempt[]` | `ConsoleAttemptsResponse` | ✅ |
| Orders | `GET /api/runtime/execution/orders` | `Order[]` | `ConsoleOrdersResponse` | ❌ 字段映射错误 |
| Intents | `GET /api/runtime/execution/intents` | `ExecutionIntent[]` | `ConsoleExecutionIntentsResponse` | ⚠️ 部分字段缺失 |
| Config | `GET /api/runtime/config-snapshot` | `ConfigSnapshot` | `ConfigSnapshotResponse` | ⚠️ version 类型不匹配 |

### 4.2 关键契约问题

| # | 严重度 | 位置 | 问题 |
|---|--------|------|------|
| 1 | **HIGH** | `getRuntimeOrders` adapter | 后端 `side`+`type` 字段；前端期望 `role` (ENTRY/TP/SL)。adapter 把 BUY/SELL 映射为 role，语义错误 |
| 2 | **HIGH** | `getRuntimeOrders` adapter | 后端 `ConsoleOrderItem` 有 `type` 字段；前端 `Order` 类型缺少 `type`，订单类型（MARKET/LIMIT）被静默丢弃 |
| 3 | **HIGH** | CandidateDetail 页面 | 页面访问 `data.best_trial?.sharpe_ratio` 等字段，但 TypeScript 类型未声明，依赖 JS 运行时灵活性 |
| 4 | **MEDIUM** | Portfolio vs Positions | 后端有两个不同的 position 模型：`ConsolePositionItem`（有 margin/exposure）和 `PortfolioPositionItem`（有 pnl_percent）。前端只用 portfolio 版本 |
| 5 | **MEDIUM** | ConfigSnapshot | 后端 `identity.version` 是 `int`；前端期望 `string` |
| 6 | **LOW** | Events/Backtests/Compare 页面 | 这 3 个页面 import `mockApi` 而非 `api.ts`，始终显示硬编码 mock 数据 |

---

## 五、观测口径收口方案

### 方案 A：最小改动 — 保证观测可信（推荐）

**目标**: 在不改动执行主链的前提下，修复观测面的数据源可信度问题。

**改动层**: 仅 `src/interfaces/` + `src/application/readmodels/`

| 改动项 | 文件 | 改动内容 | 工作量 |
|--------|------|----------|--------|
| A1. Positions 口径统一 | `api_console_runtime.py` L82-91 | `RuntimePositionsReadModel.build()` 改为 **PG 优先**，account_snapshot 作为补充（unrealized_pnl/mark_price） | 2h |
| A2. Positions v3 口径统一 | `api.py` L5470-5516 | `list_positions()` 改为 **PG 优先**，交易所数据作为 mark_price/unrealized_pnl 补充 | 3h |
| A3. PG 健康度探针 | `runtime_health.py` L73-84 | 增加 `position_repo.list_active(limit=1)` 作为 PG 连通性弱探针，成功 → OK，失败 → DOWN | 1h |
| A4. Overview backend_summary 修正 | `runtime_overview.py` L82-92 | `backend_summary` 改为读取实际 repo class name，而非 config 默认值 | 0.5h |
| A5. Console 路由 account_getter 兜底 | `api_console_runtime.py` L36 | 独立模式下 `_account_getter` 为 None 时，尝试从 `_exchange_gateway.get_account_snapshot()` 获取 | 1h |
| A6. 前端 Orders adapter 修复 | `gemimi-web-front/src/api/adapters.ts` | `getRuntimeOrders` 的 `role` 映射改为读取后端 `order_role` 字段（如果后端有的话），或标记为 TODO | 1h |

**预期收益**:
- Positions 数据源从"交易所优先"改为"PG 优先"，与执行主链一致
- PG 健康度从"永远 DEGRADED"改为有真实探针
- 前端 Orders 语义错误修复

**风险**:
- A1/A2 改动 positions 数据源顺序，可能影响交易所实时数据的展示（unrealized_pnl 精度下降）
- A3 的弱探针有性能开销（每次 health 请求多一次 DB 查询）

**工作量**: 约 8.5h

---

### 方案 B：统一 Runtime Observability 口径

**目标**: 建立统一的 runtime observability 层，所有观测面读同一个 "truth source"。

**改动层**: `src/application/readmodels/` + `src/interfaces/` + 新增 `src/application/readmodels/runtime_truth_source.py`

| 改动项 | 文件 | 改动内容 | 工作量 |
|--------|------|----------|--------|
| B1. 新增 RuntimeTruthSource | 新建 `runtime_truth_source.py` | 统一的 runtime 真相源聚合器，封装 PG repos + exchange gateway + config provider | 4h |
| B2. 所有 ReadModel 改读 TruthSource | 所有 `runtime_*.py` | 每个 readmodel 的 `build()` 方法改为接收 `RuntimeTruthSource` 而非零散参数 | 6h |
| B3. Console 路由统一注入 | `api_console_runtime.py` | 所有路由改为注入 `RuntimeTruthSource` 实例 | 2h |
| B4. V3 API 统一读 PG | `api.py` v3 endpoints | positions/orders/intents 统一通过 TruthSource 读 PG | 3h |
| B5. 前端类型对齐 | `gemimi-web-front/src/api/` | 修复所有 adapter 的字段映射和类型定义 | 3h |
| B6. 新增 runtime observation 集成测试 | `tests/unit/` | 为所有 console runtime routes 添加 HTTP 集成测试 | 4h |

**预期收益**:
- 所有观测面读同一个真相源，消除口径不一致
- 新增集成测试覆盖，防止回归
- 前端类型完全对齐

**风险**:
- 改动面大，涉及 10+ 文件
- RuntimeTruthSource 是新抽象，需要验证与现有 lifespan/set_dependencies 的兼容性
- 可能与执行主链的并发改动冲突

**工作量**: 约 22h

---

## 六、推荐方案

### 推荐：**方案 A（最小改动）**

**理由**:

1. **当前阶段是 Sim-1 自然模拟盘**，执行主链刚上线，观测面的核心需求是"看起来对"而非"架构完美"。方案 A 的 6 个改动点直接修复了最严重的可信度问题。

2. **方案 B 的 ROI 不够**：22h 的改动量中，有 10h 是前端类型对齐和集成测试，这些在 Sim-1 阶段不是阻塞项。统一 TruthSource 是好的架构目标，但当前优先级低于"执行主链稳定运行"。

3. **避免与执行主链抢代码**：方案 A 只改 `interfaces/` 和 `readmodels/`，不动 `application/` 和 `infrastructure/` 的核心逻辑，符合"本窗口不与执行主链抢核心实现文件"的约束。

4. **方案 A 的改动可以渐进式实施**：A1-A6 每个都是独立的，可以按优先级逐个实施，不需要一次性全部完成。

**实施优先级**:
1. **A3**（PG 健康度探针）— 最小改动，最大感知收益
2. **A1**（Console positions 口径统一）— 修复最关键的口径混用
3. **A5**（account_getter 兜底）— 修复独立模式下的空注入
4. **A4**（backend_summary 修正）— 修复 overview 显示
5. **A2**（V3 positions 口径统一）— 与 A1 对齐
6. **A6**（前端 Orders adapter）— 修复语义错误

---

## 七、涉及文件清单

### 审计涉及的源文件

| 文件 | 角色 |
|------|------|
| `src/interfaces/api.py` | 主 API 模块，所有 endpoints + 依赖注入 |
| `src/interfaces/api_console_runtime.py` | Console runtime 路由 |
| `src/interfaces/api_console_research.py` | Console research 路由 |
| `src/interfaces/api_v1_config.py` | V1 config API |
| `src/interfaces/api_profile_endpoints.py` | Profile 管理 API |
| `src/main.py` | 启动入口，依赖注入 |
| `src/application/readmodels/runtime_overview.py` | Overview readmodel |
| `src/application/readmodels/runtime_portfolio.py` | Portfolio readmodel |
| `src/application/readmodels/runtime_health.py` | Health readmodel |
| `src/application/readmodels/runtime_positions.py` | Positions readmodel |
| `src/application/readmodels/runtime_signals.py` | Signals readmodel |
| `src/application/readmodels/runtime_attempts.py` | Attempts readmodel |
| `src/application/readmodels/runtime_orders.py` | Orders readmodel |
| `src/application/readmodels/runtime_execution_intents.py` | Execution intents readmodel |
| `src/application/readmodels/runtime_config_snapshot.py` | Config snapshot readmodel |
| `src/application/position_projection_service.py` | Position projection service |
| `src/infrastructure/core_repository_factory.py` | Repo factory |
| `src/infrastructure/pg_position_repository.py` | PG position repo |
| `src/infrastructure/pg_order_repository.py` | PG order repo |
| `src/infrastructure/pg_execution_intent_repository.py` | PG intent repo |
| `src/infrastructure/repository_ports.py` | Repo port interfaces |
| `src/infrastructure/database.py` | Backend settings |

### 方案 A 需要修改的文件

| 文件 | 改动 |
|------|------|
| `src/interfaces/api_console_runtime.py` | A1: positions 路由改为 PG 优先；A5: account_getter 兜底 |
| `src/application/readmodels/runtime_positions.py` | A1: build() 改为 PG 优先 |
| `src/application/readmodels/runtime_health.py` | A3: 增加 PG 连通性探针 |
| `src/application/readmodels/runtime_overview.py` | A4: backend_summary 修正 |
| `src/interfaces/api.py` | A2: list_positions() 改为 PG 优先 |
| `gemimi-web-front/src/api/adapters.ts` | A6: Orders adapter 修复 |

---

## 八、未运行测试说明

本次审计为纯代码审查，未运行任何测试。方案 A 实施后需要：
1. 运行 `pytest tests/unit/test_v3_positions_api.py -v` 验证 v3 positions
2. 运行 `pytest tests/unit/test_console_runtime_readmodels.py -v` 验证 readmodels
3. 运行 `pytest tests/unit/test_console_runtime_routes.py -v` 验证 console routes
4. 手动验证前端 Overview/Portfolio/Health 页面数据展示
