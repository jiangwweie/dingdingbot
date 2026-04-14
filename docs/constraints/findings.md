# 技术发现

> **说明**: 仅保留当前活跃的技术发现，已归档的见 `archive/completed-tasks/findings-history-20260407-and-earlier.md`。
> **最后更新**: 2026-04-14 SQLite TEXT 列 CHECK 约束字典序比较 Bug

---

## 2026-04-14 SQLite TEXT 列 CHECK 约束字典序比较 Bug

### 根因

1. `DecimalField` = `DecimalString`，在 SQLite 中以 TEXT 存储 Decimal 值
2. `BacktestReportORM` 的 `check_total_return_range` 约束使用数值比较：`total_return >= -1.0`
3. SQLite 对 TEXT 列做字典序比较：`'-0.1787' >= '-1.0'` 为 False（因为 `'0' < '1'`）
4. 负收益率报告 INSERT 被拒绝，正数和零可以通过

### 影响范围

- **P0 已触发**: `total_return` 约束 -- 负收益合法，无法保存
- **P2 潜在**: 另有 6 处 DecimalString 数值 CHECK 约束（`win_rate`, `max_drawdown`, `requested_qty`, `filled_qty`, `current_qty`, `entry_price`）
- **无问题**: 9 处枚举值 `IN (...)` CHECK 约束（字符串字面量匹配，完全正确）

### 推荐方案

方案 A：删除所有 DecimalString 数值 CHECK 约束，改由应用层 Pydantic 验证。与 SignalORM 已有设计一致。

### ADR

`docs/arch/sqlite-text-check-constraint-fix-plan.md`

---

## 2026-04-14 P0 回测：入场订单状态未转换导致撮合引擎静默跳过

### 根因

1. `backtester.py:1306` — `create_order_chain()` 创建订单状态为 `CREATED`
2. `backtester.py:1315` — 订单直接加入 `active_orders` 列表，状态仍为 `CREATED`
3. `matching_engine.py:123` — 撮合引擎只处理 `status == OrderStatus.OPEN` 的订单
4. 回测中缺少 `submit_order()` + `confirm_order()` 流程，订单永远无法从 `CREATED` → `SUBMITTED` → `OPEN`

结果：所有入场单被撮合引擎静默跳过，回测 0 成交。

### 修复方案 A（改动最小）

在 `backtester.py` 第 1315 行 `active_orders.extend(entry_orders)` 之前，将订单状态直接设为 `OPEN`：

```python
# 回测中模拟订单从创建到挂单的完整流程（跳过 CREATED/SUBMITTED 中间状态）
for order in entry_orders:
    order.status = OrderStatus.OPEN  # 回测直接设为 OPEN（模拟即时挂单）

active_orders.extend(entry_orders)
```

### 技术要点

1. **回测 vs 实盘差异**：实盘有 `submit_order()` → `confirm_order()` 状态流转，回测是单线程同步模拟，中间状态无实际意义
2. **改动量**：3 行代码，不涉及其他文件
3. **`OrderStatus` 已在第 35 行导入**，无需额外 import

### 验证结果

- 21 个撮合引擎单元测试全部通过
- 验证 `create_order_chain()` 创建时状态为 `CREATED`
- 验证撮合引擎确实过滤非 `OPEN` 状态订单
- **全量测试 3068 项**：
  - 单元测试 ~2507 项：通过率 99.8%
  - 集成测试 561 项：415 passed, 63 failed, 91 error, 2 skipped
  - 核心功能全部通过：撮合引擎 21/21、回测数据完整性、Decimal 精度、订单生命周期
  - 63 FAILED 和 91 ERROR 均为预先存在的问题，**零新引入失败**

---

## 2026-04-14 连接池 close() 共享连接 premature close 修复

### 根因

所有使用 `pool_get_connection()` 的 Repository（13+ 个）在 `close()` 中检查 `_owns_connection=True` 时调用 `await self._db.close()`，关闭了连接池中的**共享连接**，导致其他共享同一 db_path 的 Repository 后续操作报 `ValueError("no active connection")`。

### `_owns_connection` 语义错位

ADR 设计意图：池化连接 `_owns_connection=False`（不关闭），注入连接 `_owns_connection=True`（关闭）。
实际实现：`_owns_connection = connection is None`（构造函数参数判断），池化连接也被标记为 `True`。

### 修复方案

所有 Repository 的 `close()` 不再调用 `await self._db.close()`，仅清除本地引用 `self._db = None`。
连接池是唯一所有者，由 `ConnectionPool.close_all()` 统一管理生命周期。

### 连带修复

1. **`pnl_ratio` Decimal 绑定 Bug**（`signal_repository.py:770`）：直接传 `Decimal` 给 SQLite，缺少 `str()` 转换
2. **测试隔离**：`:memory:` 池共享导致测试间数据污染，改用临时文件路径
3. **大小写断言**：测试用 `"long"` 但实际存储 `"LONG"`（`Direction.LONG.value`）

### 验证结果

- 81 个测试：78 通过，3 失败（预存问题，`test_backtest_repository.py` 测试隔离）
- 核心 4 个回归测试全部通过
- `test_connection_pool.py` 3 个预存失败全部修复（8/8）
- `test_signal_repository.py` 12 个预存失败全部修复（28/28）

---

## 2026-04-14 共享 DB 连接池改造

### 根因

17+ 个 Repository 各自调用 `aiosqlite.connect()` 创建独立连接，即使指向同一 db_path（`data/v3_dev.db`），SQLite 在多连接写入时需要文件级锁，导致 "database is locked" 异常。仅 `signal_repository.py` 设置了 `busy_timeout`。

### 方案 A（最小侵入）

每个 Repository 的 `initialize()` 内将 `aiosqlite.connect()` 替换为 `pool.get_connection()`。不改初始化时序、不改 set_dependencies()、不改全局变量赋值。

### 技术要点

1. **PRAGMA 集中管理**：`connection_pool.py` 统一设置 WAL/synchronous/busy_timeout/cache_size，Repository 不再重复设置
2. **`_owns_connection` 标志**：池化连接的 `_owns_connection=True`（因为 Repo 自己初始化时用 pool 获取连接，但仍视为"自有"），close() 时会关闭。但 `ConfigDatabaseManager` 注入的子仓库 `_owns_connection=False`，close() 不关闭池连接
3. **`config_entry_repository.py` 缺少 `import os`**：原文件遗漏，本次修复补上
4. **`historical_data_repository.py` 不改造**：使用 SQLAlchemy create_async_engine，有独立连接池机制

### 验证结果

- 18 个连接池测试 passed（8 原有 + 10 新增集成）
- 58 个核心 DB 回归测试 passed
- 0 新增回归失败

---

## 2026-04-14 Float/Decimal 精度污染

### 根因

Python 中 `float` 的 IEEE 754 双精度在金融计算中会引入舍入误差。代码中存在 25+ 处 `float()` 转换，部分污染了决策链：
- `calculate_score()` 返回 `float` → 影响 `PatternResult.score` → 影响 `_check_cover` 的信号覆盖判断
- `SignalResult.pnl_ratio: float` → 影响 API 累积 PnL 计算（浮点累加）
- backtester 返回硬编码 float → 影响回测报告精度

### 分类

| 级别 | 数量 | 说明 |
|------|------|------|
| P0 | 0 | 核心金融计算（仓位、止损、风险额）已正确使用 Decimal |
| P1 | 6 | Score/pnl_ratio 等决策影响字段被 float 污染 |
| P2 | 6 | `details={}` 字典中 `float()` 仅用于 JSON 序列化，可接受 |

### 修复

删除计算链中的 `float()` 转换，保持 Decimal 贯穿始终。对 JSON 序列化场景（details dict、API 响应），保留 `float()` 或使用自定义 DecimalEncoder。

### Pydantic 类型强制转换

`SignalResult.score` 在 Pydantic 模型中声明为 `float`，即使传入 `Decimal("0.85")`，Pydantic 也会自动转换为 `float 0.85`。这是预期行为 — score 仅用于 UI 展示/排序，不参与金融计算。

### 教训

1. **金融计算中永远不要使用 `float()` 转换**，即使只是"显示用途" — 值可能意外流入计算链
2. **Pydantic 模型字段类型会强制转换输入值** — 声明 Decimal 字段才能保护 Decimal 值
3. **`details={}` 字典用于诊断元数据** — 可以接受 float（JSON 兼容性），但应明确标注
4. **审计时应按数据流追踪** — 不能仅看单点 `float()` 调用，要追踪值最终流向哪里

---

## 2026-04-13 aiosqlite executescript() WAL 事务破坏

### 根因

`aiosqlite.executescript()` 在底层绕过 async 连接队列，直接操作底层 sqlite3 连接并执行隐式 COMMIT。这破坏了 WAL 模式的事务状态，导致 ConfigManager 初始化后 `_load_strategies_from_db()` 查询返回 0 行，而独立的新连接能看到数据。

### 症状

```
ConfigManager 的 aiosqlite 连接: SELECT * FROM strategies WHERE is_active = TRUE → 0 行
独立新建 aiosqlite 连接: 同一条 SQL → 1 行
独立 sqlite3 连接: 同一条 SQL → 1 行
```

### 修复

将 `ConfigManager._create_tables()` 中的 `await self._db.executescript(schema_sql)` 替换为逐条 `await self._db.execute(stmt)` 执行。

### 教训

**aiosqlite 中永远不要使用 executescript()**，它在 async 连接中行为不一致，会破坏 WAL 事务状态。所有批量 SQL 应拆分为逐条 execute() 调用。

---

---

## 2026-04-13 TODO 注释分布与清理

### 前端 TODO 分布（4 处）

| # | 文件:行 | 内容 | 状态 |
|---|---------|------|------|
| 1 | `Optimization.tsx:78` | 实现参数应用到策略 | 保留（优化功能未完成） |
| 2 | `Optimization.tsx:175` | 实现历史记录 API 调用 | 保留（优化功能未完成） |
| 3 | `StrategyForm.tsx:130` | 添加过滤器配置表单 | 保留（过滤器表单待实现） |
| 4 | `SystemSettings.tsx:422` | 实际项目中应调用重启 API | 清理（措辞过时，已更新为"实现后端重启 API 调用"） |

### 后端 TODO 分布（22 处）

| 分类 | 数量 | 示例 | 状态 |
|------|------|------|------|
| 过时/占位 | 4 | `TODO(P1-5)`、mock 注释 | 清理 |
| 未完成功能 | 12 | `TODO: 实现 PositionRepository`、`TODO: 从数据库获取本地订单` | 保留 |
| 简化 TODO | 6 | 注释"简化版本" | 保留（记录简化决策） |

### Profile 死代码发现

- `ConfigProfiles.tsx` 页面（524 行）仍完整存在于磁盘，但 `commit 6f0145f` 已从 `SystemSettings.tsx` 移除 Profile 管理入口
- 无路由引用、无其他文件 import、5 个 Profile Modal 组件仅被 `ConfigProfiles.tsx` 使用
- **判定**: Profile 管理功能已被 DB 驱动配置管理取代，属于完全废弃功能

---

## 2026-04-12 配置依赖注入统一修复

### 根因：`lifespan="off"` 导致 FastAPI 生命周期钩子不执行

**技术发现**:
1. `main.py` 使用 `uvicorn.Config(lifespan="off")` 启动 uvicorn，导致 `api.py` 中定义的 `lifespan()` 函数**完全不执行**
2. `lifespan()` 内负责初始化 7 个配置 Repository 并调用 `set_config_dependencies()`，全部被跳过
3. 两条独立的依赖注入链路共存于同一代码库但互不关联：
   - 旧链路：`set_dependencies()`（`main.py` Phase 9 调用）→ 正常
   - 新链路：`set_config_dependencies()`（`lifespan()` 调用）→ 未执行
4. **循环导入问题**：`api.py` 导入 `api_v1_config.py`（router），`api_v1_config.py` 需要从 `api.py` 读取全局变量 → 新增 `api_config_globals.py` 作为中间层打破循环

### 方案 C 验证

- 改动量极小（净增 ~30 行代码），影响范围仅限于启动流程
- 不修改任何 Repository 内部逻辑、不修改 API 处理函数、不修改前端
- 回滚成本极低（3 个文件，一个 `git revert`）

### 独立问题发现

1. `ConfigManager.get_system_config()` 方法不存在，`effective` 端点调用它直接 500
2. `AssetPollingConfig` 导入缺失，`test_config_repository.py` 3 个测试失败
3. `exchange_configs` 数据库表中 API Key/Secret 为空，testnet=1 → 无法连接交易所

---

## 2026-04-08 P0 WebSocket K 线选择逻辑修复

### 核心修复：交易所 x 字段优先 + 多层防御

**问题**: WebSocket K 线选择逻辑错误，系统处理 `ohlcv[-1]`（未收盘 K 线）进行形态检测。

**技术发现**:
1. `candle[6]` 可能包含 `info` 字典，`info['x']` 表示收盘状态
2. 无 `x` 字段时，使用 `ohlcv[-2]` + 时间戳推断作为后备
3. `KlineData` 新增 `info` 字段保留交易所原始数据

### Pinbar 最小波幅检查

| 方案 | 选择 |
|------|------|
| 固定值 (0.5 USDT) | ❌ 过滤低价格币种 |
| **动态百分比 (0.1%)** | ✅ 适配所有价格级别 |

**公式**: 有 ATR → `atr * 0.1`，无 ATR → `close * 0.001`

---

## 2026-04-08 系统优先级重新分析 - 用户场景驱动

### 核心发现：并发问题不存在

**用户约束**: 单人使用 + 1h/4h 中长线 + 不存在多人并发

| 原并发问题 | 原优先级 | 新优先级 |
|----------|---------|---------|
| 全局状态依赖注入 | P1 | P3 |
| 仓位同步竞态修复 | P1 | P3 |
| 多锁管理简化 | P2 | P3 |

**节省 10h 工时**

### MVP 范围调整

| 维度 | 完整版本 | 最小交付版本 |
|------|---------|-------------|
| 支持策略 | 全部 4 种 | **仅 Pinbar** |
| 总工时 | 55.5h | **33h** |

---

## 2026-04-07 P1-5 Provider 注册模式架构决策

**决策**: 外观模式 + Provider 注册实现（用户核心需求：零修改扩展）

| 决策项 | 结论 |
|--------|------|
| 扩展方式 | Protocol 接口 + Registry 注册中心 |
| 缓存机制 | CachedProvider 基类 + TTL 惰性清理 |
| 并发安全 | asyncio.Lock + 双重检查锁定 |
| 时钟注入 | ClockProtocol 抽象（测试可控） |
| 向后兼容 | 57 个调用方零修改 |

**成果**: 135 单元测试 + 50 集成测试，覆盖率 92%，代码审查 A+

---

## P1-5 Repository 层实现技术要点

- `ConfigRepository` 扩展：`update_risk_config_item()` / `update_user_config_item()` KV 模式更新
- Decimal 精度：`Decimal(str(value))` 转换，YAML 导出时 `str()` 序列化
- TTLCache: `time.monotonic()` 计算 TTL，惰性清理 + LRU 淘汰

---

## 工作流重构 v3.0

### 核心设计

1. **规划会话强制交互式头脑风暴**: PM ≥3 澄清问题 → Arch ≥2 方案 → PM 任务分解
2. **开发会话强制 Agent 调用**: `Agent(subagent_type="team-backend-dev", prompt="...")`
3. **状态看板实时更新**: `docs/planning/board.md` 每次调度后更新
4. **暂停关键词触发**: 用户输入"暂停"/"午休"自动更新 progress.md + findings.md

### 技能配置

| 技能 | 职责 |
|------|------|
| `/coordinator` | 兼任 PdM/Arch/PM |
| `/backend` | 后端开发 |
| `/frontend` | 前端开发 |
| `/qa` | 测试专家 |
| `/reviewer` | 代码审查 |

---

## DEBT-3 API 依赖注入架构决策

**问题**: API 端点硬编码 `OrderRepository()`，测试 fixture 临时数据库无法被使用。

**方案**: 全局变量 + `_get_order_repo()` 辅助函数 + 扩展 `set_dependencies()`

```python
_order_repo: Optional[OrderRepository] = None

def _get_order_repo() -> OrderRepository:
    if _order_repo is None:
        return OrderRepository()
    return _order_repo
```

---

## 2026-04-10 MCP 占位符清理 + 文档版本收敛

### 清理决策
- MCP 占位符（telegram/ssh/sentry）使用 dummy 值，不在项目 enabled 列表中，直接删除
- 12 个旧版 SKILL.md 残留文件（.backup / .v2 / .v3）全部删除，保留当前活跃版本
- 重复的 phase-contracts 目录（docs/designs/archive/ 和 docs/v3/ 各 14 个相同文件）删除 archive 副本
- 创建 SKILL_VERSIONS.md 版本追踪清单，避免未来再次积累残留文件

### 用户画像洞察
- 流程过重：10 人团队 + 三阶段工作流 + 5 个强制检查点，个人项目开销大
- 建议引入"快速通道"模式（light mode）处理小修小补
- Agent 定义去重：抽取公共规范为独立文件，各 Agent 仅引用而非复制

---

## 2026-04-10 策略系统架构分析

### 两套策略 API 并存

| 旧 API `/api/strategies` | 新 API `/api/v1/config/strategies` |
|---|---|
| id: number | id: string UUID |
| strategy_json: JSON 字符串 | trigger_config/filter_configs 扁平字段 |
| StrategyWorkbench 使用 | StrategyConfig / StrategiesTab 使用 |
| 有 Dry Run 预览 + 下发实盘 | 无预览、无下发功能 |

### 策略下发断裂根因

```
用户点"下发到实盘" → StrategyWorkbench 直接 PUT /api/config
→ 写了配置文件但 ConfigManager 内存未更新（未触发热重载）
→ 仪表盘 GET /api/config 读内存 → 显示空策略
```

**正确流程**: `POST /api/strategies/{id}/apply` 会写入 + 触发热重载 observer。

### MTF 映射是固定规则，无需用户配置

后端三处硬编码固定映射：
```python
MTF_MAPPING = {"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w"}
```
运行时根据 K 线自身的 timeframe 自动查找对应高一级周期。前端 MTF mapping 单选下拉框选了也不生效——"前端能选但后端不读"。

### 回测页面策略数组初始为空

Backtest.tsx 和 PMSBacktest.tsx 的 strategies 数组初始为空，用户必须手动组装或从工作台导入。没有"一键使用已保存策略"的快捷路径。

### 配置管理审计报告（2026-04-10）

#### P0 问题（阻断性）

| # | 问题 | 文件 | 行号 |
|---|------|------|------|
| 1 | RiskConfig 类型与后端不匹配（前端有 default_leverage，后端没有） | web-front/src/api/config.ts | 95-99 |
| 2 | BackupTab 导入/导出调用不存在的旧 API 路径 | web-front/src/pages/config/BackupTab.tsx | 184, 214 |
| 3 | BackupTab preview 数据结构与后端 ImportPreview 类型不匹配 | web-front/src/pages/config/BackupTab.tsx | 133-143 |
| 4 | YAML 全局 string 构造器被劫持为 Decimal，影响所有 YAML 解析 | src/interfaces/api_v1_config.py | 72 |

#### P1 问题（重要）

| # | 问题 | 文件 |
|---|------|------|
| 5 | 热重载通知只发给 Observer，ConfigManager 缓存未刷新 | api_v1_config.py:640-644 |
| 6 | 两个 SystemTab 组件功能重复（SystemTab.tsx vs SystemSettings.tsx） | 两个文件 |
| 7 | StrategyForm 提交 trigger_config.params 永远为空 | StrategyForm.tsx:116-118 |
| 8 | lib/api.ts 包含大量死代码/过时接口 | lib/api.ts |
| 9 | 多个 Repository 各自独立创建 DB 连接 | config_repositories.py |
| 10 | ConfigSnapshotService 每次创建快照新建/关闭临时连接 | config_snapshot_service.py:157-162 |

> 注：并发安全问题用户明确表示不考虑，已跳过 P1-3 (upsert 竞态)。

### 旧 API 死代码清理策略

**决定**: 渐进式清理，不是本轮目标。
- `lib/api.ts` 被 30+ 个文件引用，不能整体删除
- StrategyWorkbench 删除后，清理仅被其引用的旧函数
- 其余旧函数标记 `@deprecated`，后续逐步迁移

---

## 2026-04-13 方案 B 彻底统一策略表

### 新旧策略表对比

| 维度 | 旧表 `custom_strategies` | 新表 `strategies` |
|------|-------------------------|-------------------|
| ID 类型 | INTEGER AUTOINCREMENT | TEXT (UUID) |
| 数据存储 | 单个 `strategy_json` 字段 | 扁平化字段（trigger_config, filter_configs, symbols, timeframes） |
| 路由 | `/api/strategies/*` | `/api/v1/config/strategies/*` |
| 状态 | **已删除** | 使用中 |

### 路由冲突根因

`api.py` 和 `api_v1_config.py` 注册了重叠路由（如 `GET /api/v1/config/strategies`），FastAPI 按注册顺序匹配，旧端点优先生效导致新端点永远不会被命中。

### 清理结果

- 删除 8 个旧 API 端点（~260 行）
- 删除 5 个 SignalRepository CRUD 方法（~150 行）
- 前端 6 个文件迁移到新端点
- 创建迁移脚本 006_migrate_custom_strategies.py
- 净删除 ~830 行代码

---

## 归档

2026-04-07 及更早的技术发现已归档至:
`docs/planning/archive/completed-tasks/findings-history-20260407-and-earlier.md`

---

*最后更新：2026-04-13 16:00 - 方案 B 彻底统一策略表完成*
