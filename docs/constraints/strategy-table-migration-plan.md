# Strategy Table Migration Plan

> 日期: 2026-04-13
> 状态: 规划阶段
> 优先级: P0 (数据不一致 Bug)

---

## 1. 影响范围排查

### 1.1 旧表 `custom_strategies` 引用清单

**表定义**: `src/infrastructure/signal_repository.py` L233-L240

```sql
CREATE TABLE IF NOT EXISTS custom_strategies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    description   TEXT,
    strategy_json TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
)
```

| 文件 | 行号 | 方法/端点 | HTTP 路径 | 说明 |
|------|------|-----------|-----------|------|
| `src/interfaces/api.py` | L2652-L2671 | `list_strategy_templates()` | `GET /api/strategies/templates` | 回测沙箱策略模板列表 |
| `src/interfaces/api.py` | L2678-L2691 | `get_custom_strategies_v1()` | `GET /api/v1/config/strategies` | 前端配置别名路径 |
| `src/interfaces/api.py` | L2694-L2709 | `get_custom_strategies()` | `GET /api/strategies` | 旧版策略列表 |
| `src/interfaces/api.py` | L2712-L2740 | `get_custom_strategy()` | `GET /api/strategies/{strategy_id}` | **旧版**策略详情(参数 `int`) |
| `src/interfaces/api.py` | L2743-L2789 | `create_custom_strategy()` | `POST /api/strategies` | **旧版**创建(参数 `int`) |
| `src/interfaces/api.py` | L2792-L2843 | `update_custom_strategy()` | `PUT /api/strategies/{strategy_id}` | **旧版**更新(参数 `int`) |
| `src/interfaces/api.py` | L2846-L2869 | `delete_custom_strategy()` | `DELETE /api/strategies/{strategy_id}` | **旧版**删除(参数 `int`) |
| `src/interfaces/api.py` | L6687-L6704 | `list_config_strategies()` | `GET /api/config/strategies` | FE-01 配置导航 |
| `src/infrastructure/signal_repository.py` | L1529 | `get_all_custom_strategies()` | - | Repository 查询方法 |
| `src/infrastructure/signal_repository.py` | L1546 | `get_custom_strategy_by_id()` | - | Repository 按 ID 查询 |
| `src/infrastructure/signal_repository.py` | L1564 | `create_custom_strategy()` | - | Repository 创建方法 |
| `src/infrastructure/signal_repository.py` | L1594 | `update_custom_strategy()` | - | Repository 更新方法 |
| `src/infrastructure/signal_repository.py` | L1642 | `delete_custom_strategy()` | - | Repository 删除方法 |
| `tests/unit/test_strategy_apply.py` | L301 | 测试 mock | - | 测试中 mock 旧表方法 |

**总计**: 8 个 API 端点 + 5 个 Repository 方法 + 1 个测试文件

### 1.2 新表 `strategies` 引用清单

**表定义**: `src/infrastructure/repositories/config_repositories.py` L87-L100

```sql
CREATE TABLE IF NOT EXISTS strategies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    trigger_config TEXT NOT NULL,
    filter_configs TEXT NOT NULL,
    filter_logic TEXT DEFAULT 'AND',
    symbols TEXT NOT NULL,
    timeframes TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1
)
```

| 文件 | 行号 | 方法/端点 | HTTP 路径 | 说明 |
|------|------|-----------|-----------|------|
| `src/interfaces/api_v1_config.py` | L967-L995 | `get_strategies()` | `GET /api/v1/config/strategies` | **新版**策略列表 |
| `src/interfaces/api_v1_config.py` | L998-L1031 | `create_strategy()` | `POST /api/v1/config/strategies` | **新版**创建(需 admin) |
| `src/interfaces/api_v1_config.py` | L1034-L1046 | `get_strategy()` | `GET /api/v1/config/strategies/{strategy_id}` | **新版**详情(参数 `str`) |
| `src/interfaces/api_v1_config.py` | L1049-L1098 | `update_strategy()` | `PUT /api/v1/config/strategies/{strategy_id}` | **新版**更新(需 admin, 热重载) |
| `src/interfaces/api_v1_config.py` | L1101-L1137 | `delete_strategy()` | `DELETE /api/v1/config/strategies/{strategy_id}` | **新版**删除(需 admin) |
| `src/interfaces/api_v1_config.py` | L1140-L1176 | `toggle_strategy()` | `POST /api/v1/config/strategies/{id}/toggle` | **新版**启用/禁用 |
| `src/interfaces/api_v1_config.py` | L1600, L1838, L1991, L2358 | 导入导出/热重载 | - | 内部调用 `_strategy_repo` |
| `src/interfaces/api.py` | L3250 | `apply_strategy()` | `POST /api/strategies/{id}/apply` | **已使用新表** `get_by_id()` |
| `src/infrastructure/repositories/config_repositories.py` | L47-L352 | `StrategyConfigRepository` | - | 完整 CRUD + toggle + 分页 |

**总计**: 6 个 API 端点 + 1 个已修复端点 + 多个内部调用

### 1.3 路由冲突分析

存在 **URL 路由冲突**：

| 路径 | 旧端点 (api.py) | 新端点 (api_v1_config.py) | 冲突类型 |
|------|-----------------|--------------------------|---------|
| `GET /api/strategies` | `get_custom_strategies()` | - | 仅旧版 |
| `GET /api/v1/config/strategies` | `get_custom_strategies_v1()` | `get_strategies()` | **双重注册** |
| `GET /api/strategies/{strategy_id}` | `get_custom_strategy()` (int) | `get_strategy()` (str) | **参数类型冲突** |
| `POST /api/strategies` | `create_custom_strategy()` (int) | `create_strategy()` (str, admin) | **双重注册** |
| `PUT /api/strategies/{strategy_id}` | `update_custom_strategy()` (int) | `update_strategy()` (str, admin) | **参数类型冲突** |
| `DELETE /api/strategies/{strategy_id}` | `delete_custom_strategy()` (int) | `delete_strategy()` (str, admin) | **参数类型冲突** |

**注意**: FastAPI 按照注册顺序匹配路由。`api.py` 中注册的路由会优先于 `api_v1_config.py` 中的 router，因此旧端点实际生效。

### 1.4 初始化链路

```
src/main.py (startup)
  -> StrategyConfigRepository() -> initialize()    # 新表 strategies
  -> SignalRepository() -> initialize()            # 旧表 custom_strategies
  -> configure_config_globals(strategy_repo=...)    # 注入到 _config_globals
```

两个 Repository 使用 **同一个数据库文件** (`data/v3_dev.db`)，但各自管理独立的连接。

---

## 2. 数据模型对比

### 2.1 Schema 差异

| 字段 | 旧表 `custom_strategies` | 新表 `strategies` | 兼容性 |
|------|-------------------------|-------------------|--------|
| `id` | INTEGER AUTOINCREMENT | TEXT (UUID) | **不兼容** - 类型不同 |
| `name` | TEXT NOT NULL | TEXT NOT NULL | 兼容 |
| `description` | TEXT | TEXT | 兼容 |
| `strategy_json` | TEXT NOT NULL | - | **旧表独有** |
| `is_active` | - | BOOLEAN DEFAULT TRUE | **新表独有** |
| `trigger_config` | - | TEXT (JSON) | **新表独有** |
| `filter_configs` | - | TEXT (JSON) | **新表独有** |
| `filter_logic` | - | TEXT DEFAULT 'AND' | **新表独有** |
| `symbols` | - | TEXT (JSON) | **新表独有** |
| `timeframes` | - | TEXT (JSON) | **新表独有** |
| `created_at` | TEXT (ISO) | TIMESTAMP | 格式不同但可兼容 |
| `updated_at` | TEXT (ISO) | TIMESTAMP | 格式不同但可兼容 |
| `version` | - | INTEGER DEFAULT 1 | **新表独有** |

### 2.2 数据存储模型对比

**旧表模式 (SignalRepository)**:
- 将所有策略定义序列化为单个 `strategy_json` 字段（JSON 字符串）
- `strategy_json` 内部是 `StrategyDefinition` 的完整序列化
- ID 是 INTEGER 自增

**新表模式 (StrategyConfigRepository)**:
- 将策略拆分为多个结构化字段：`trigger_config`, `filter_configs`, `filter_logic`, `symbols`, `timeframes`
- 每个 JSON 字段独立序列化
- ID 是 TEXT (UUID)

### 2.3 核心不兼容点

1. **ID 类型不同**: 旧表 INTEGER vs 新表 TEXT(UUID)。前端如果硬编码了 ID 类型判断会出错。
2. **数据结构扁平化**: 旧表用 `strategy_json` 存整个 `StrategyDefinition`，新表将其拆散。从旧表读取的 `strategy_json` 需要解析后才能构建 `StrategyDefinition`。
3. **apply_strategy 的数据转换** (L3258-L3269): 新表的 `trigger_config` 和 `filter_configs` 是独立的 JSON 字段，需要在应用层映射到 `StrategyDefinition` 的 `triggers`/`filters` 或 `logic_tree`。
4. **字段映射风险**: 新表的 `trigger_config` 对应 StrategyDefinition 的 `trigger`（单数），而旧表 `strategy_json` 可能包含 `triggers`（复数）+ `trigger_logic`。

### 2.4 数据迁移映射（如需从旧表迁移到新表）

```
旧表 custom_strategies          ->  新表 strategies
─────────────────────────────────────────────────
id (int)                        ->  id (str): str(uuid4()) 生成新 UUID
name                            ->  name (同)
description                     ->  description (同)
strategy_json.name              ->  name (冗余)
strategy_json.triggers[0]       ->  trigger_config (取第一个)
strategy_json.filters           ->  filter_configs
strategy_json.filter_logic      ->  filter_logic
strategy_json.apply_to          ->  symbols + timeframes (需解析 "symbol:timeframe")
strategy_json.is_global         ->  (隐含，apply_to 为空则全局)
created_at                      ->  created_at
updated_at                      ->  updated_at
-                               ->  is_active = TRUE
-                               ->  version = 1
```

---

## 3. 修复方案设计

### 方案 A：最小改动 - 仅修复受影响的端点

#### 3.1.1 目标

保持旧表 CRUD 端点不变，确保 `apply_strategy` 和其他消费方使用新表数据。

#### 3.1.2 改动清单

| 文件 | 改动 | 行数 |
|------|------|------|
| `src/interfaces/api.py` | 无需改动 | 0 |
| `src/interfaces/api.py` | 修复路由冲突：将旧 CRUD 端点前缀改为 `/api/legacy/strategies/` | ~100 行 |
| `tests/unit/test_strategy_apply.py` | 更新 mock 从 `get_custom_strategy_by_id` 改为 `get_by_id` | ~10 行 |

**等等** -- 经代码审查，`apply_strategy` (L3250) **已经使用** `_config_globals._strategy_repo.get_by_id()`。这意味着 apply 端点已经被修复过，或者描述的是过去的状态。

实际未修复的问题是：

1. **`GET /api/strategies/{strategy_id}`** (L2712) - 仍使用旧表
2. **`POST /api/strategies`** (L2743) - 仍写入旧表
3. **`PUT /api/strategies/{strategy_id}`** (L2792) - 仍更新旧表
4. **`DELETE /api/strategies/{strategy_id}`** (L2846) - 仍删除旧表
5. **`GET /api/strategies`** (L2694) - 仍读旧表列表
6. **`GET /api/v1/config/strategies`** (L2678) - 与 v1 路由冲突
7. **`GET /api/config/strategies`** (L6687) - 仍读旧表
8. **`GET /api/strategies/templates`** (L2652) - 仍读旧表

#### 3.1.2 修正后的方案 A

将旧端点全部重定向/代理到新表：

| 文件 | 改动 | 说明 |
|------|------|------|
| `src/interfaces/api.py` L2652-2671 | 改为调用 `_config_globals._strategy_repo.get_list()` | templates 端点 |
| `src/interfaces/api.py` L2678-2691 | **删除**（与 v1 路由冲突，v1 端点已实现） | get_custom_strategies_v1 |
| `src/interfaces/api.py` L2694-2709 | 改为调用 `_config_globals._strategy_repo.get_list()` | get_custom_strategies |
| `src/interfaces/api.py` L2712-2740 | 改为调用 `_config_globals._strategy_repo.get_by_id()` | get_custom_strategy |
| `src/interfaces/api.py` L2743-2789 | 改为调用 `_config_globals._strategy_repo.create()` | create_custom_strategy |
| `src/interfaces/api.py` L2792-2843 | 改为调用 `_config_globals._strategy_repo.update()` | update_custom_strategy |
| `src/interfaces/api.py` L2846-2869 | 改为调用 `_config_globals._strategy_repo.delete()` | delete_custom_strategy |
| `src/interfaces/api.py` L6687-6704 | 改为调用 `_config_globals._strategy_repo.get_list()` | list_config_strategies |
| `src/interfaces/api.py` L2526-2537 | 更新请求模型适配新表格式 | StrategyCreateRequest/UpdateRequest |
| `tests/unit/test_strategy_apply.py` | 更新 mock | 适配新表格式 |

**风险评估**:
- 旧端点参数类型是 `int`，新表 ID 是 `str`(UUID)，需要改动 API 签名
- 旧请求体格式 (`strategy` 字段含 StrategyDefinition) 与新表格式 (`trigger_config`, `filter_configs` 等扁平字段) 不同
- 如果前端直接调用这些旧端点，会导致 Breaking Change

**回滚成本**: 低。只需恢复 api.py 中旧端点的原始实现即可。

**工作量估算**: 2-3 小时

### 方案 B：彻底统一 - 全面迁移到新表，废弃旧表

#### 3.2.1 目标

- 将所有策略 CRUD 操作统一走 `/api/v1/config/strategies` 路由
- 废弃 api.py 中的旧策略端点（保留 301 重定向或 410 Gone）
- 删除 SignalRepository 中的旧表 CRUD 方法
- 可选：创建数据迁移脚本将旧表数据导入新表
- 可选：删除 `custom_strategies` 表

#### 3.2.2 改动清单

| 文件 | 改动 | 说明 |
|------|------|------|
| `src/interfaces/api.py` | 删除 L2652-2869 所有旧策略端点 | ~220 行删除 |
| `src/interfaces/api.py` | 删除 L6687-6704 旧配置策略端点 | ~20 行删除 |
| `src/interfaces/api.py` | 删除 L2526-2537 旧请求模型 | ~12 行删除 |
| `src/interfaces/api.py` | 保留 `apply_strategy` 端点（已使用新表） | 无需改动 |
| `src/interfaces/api_v1_config.py` | 确认 `get_strategy` 端点参数类型兼容 | 可能需调整 |
| `src/infrastructure/signal_repository.py` | 删除 L231-245 旧表创建代码 | ~15 行删除 |
| `src/infrastructure/signal_repository.py` | 删除 L1525-1656 旧 CRUD 方法 | ~130 行删除 |
| `src/infrastructure/signal_repository.py` | 删除 `get_all_custom_strategies` 等方法的调用方引用 | - |
| `tests/unit/test_strategy_apply.py` | 更新测试逻辑 | 适配新表 |
| `migrations/versions/` | 新增迁移: 删除 custom_strategies 表 | 新文件 |
| `docs/` | 更新 ADR/架构文档 | 新文件 |

#### 3.2.3 数据迁移策略（可选但推荐）

```python
# 伪代码：migrations/versions/2026-04-13-XXX_migrate_custom_to_strategies.py
async def migrate():
    """将 custom_strategies 数据迁移到 strategies 表"""
    old_rows = await db.execute("SELECT * FROM custom_strategies")
    for row in old_rows:
        strategy_json = json.loads(row["strategy_json"])
        new_id = str(uuid.uuid4())

        # 解析 apply_to 提取 symbols 和 timeframes
        apply_to = strategy_json.get("apply_to", [])
        symbols = list(set(s.split(":")[0] + ":" + s.split(":")[1] if ":" in s else s for s in apply_to))
        timeframes = list(set(s.split(":")[-1] for s in apply_to if ":" in s))

        await db.execute("""
            INSERT INTO strategies (id, name, description, is_active, trigger_config,
                filter_configs, filter_logic, symbols, timeframes, created_at, updated_at, version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            new_id,
            row["name"],
            row["description"],
            True,
            json.dumps(strategy_json.get("triggers", [strategy_json.get("trigger", {})])[0] if strategy_json.get("triggers") else {}),
            json.dumps(strategy_json.get("filters", [])),
            strategy_json.get("filter_logic", "AND"),
            json.dumps(symbols),
            json.dumps(timeframes),
            row["created_at"],
            row["updated_at"],
            1
        ))

    await db.execute("DROP TABLE custom_strategies")
```

**风险评估**:
- 高：删除旧端点可能影响未知的前端调用方
- ID 类型从 int 变为 str，所有前端引用需要更新
- 旧表数据迁移存在信息丢失风险（StrategyDefinition 完整结构 vs 扁平字段）

**回滚成本**: 中等。需要保留旧表数据或迁移脚本可逆向执行。

**工作量估算**: 1-2 天（含测试 + 前端适配协调）

---

## 4. 推荐方案

### 推荐：方案 A（渐进式修复）

**理由**:

1. **风险最小**: 不删除任何代码，仅修改数据源。旧端点保留，前端不受影响。
2. **ID 类型问题**: 方案 B 需要全链路改 ID 类型（int -> str），影响范围大。方案 A 可以先做数据源切换，ID 问题后续统一处理。
3. **快速止血**: 核心 Bug（apply_strategy 找不到新策略）已经通过 apply 端点使用新表解决了。方案 A 进一步确保所有读端点也能读取新表数据。
4. **分步演进**: 方案 A 完成后，可以观察一段时间，确认所有流量都走新端点后再执行方案 B 的清理工作。

### 实施步骤

1. **Step 1**: 修改 `src/interfaces/api.py` 中 7 个旧端点的数据源，从 `_get_repository()` 改为 `_config_globals._strategy_repo`
2. **Step 2**: 处理 ID 类型差异（旧端点接收 `int`，新表使用 `str`）：在端点内做 `str(strategy_id)` 转换，或改为 `str` 类型参数
3. **Step 3**: 处理请求体格式差异：旧端点接收 `{"strategy": {...StrategyDefinition...}}`，新表接收扁平字段。在端点层做转换适配
4. **Step 4**: 更新 `tests/unit/test_strategy_apply.py` 测试
5. **Step 5**: 全量回归测试

### 远期规划

- Phase 2: 前端全面迁移到 `/api/v1/config/strategies` 新端点
- Phase 3: 删除 api.py 旧端点（方案 B 清理）
- Phase 4: 删除 `custom_strategies` 表及其 Repository 方法

---

## 附录

### A. 关键文件清单

| 文件 | 角色 |
|------|------|
| `/Users/jiangwei/Documents/final/src/interfaces/api.py` | 旧策略端点 + apply_strategy 端点 |
| `/Users/jiangwei/Documents/final/src/interfaces/api_v1_config.py` | 新策略 CRUD 端点 |
| `/Users/jiangwei/Documents/final/src/interfaces/api_config_globals.py` | 全局变量共享（strategy_repo 等） |
| `/Users/jiangwei/Documents/final/src/infrastructure/signal_repository.py` | SignalRepository + 旧表定义和 CRUD |
| `/Users/jiangwei/Documents/final/src/infrastructure/repositories/config_repositories.py` | StrategyConfigRepository + 新表定义和 CRUD |
| `/Users/jiangwei/Documents/final/src/main.py` | 初始化入口，注入 strategy_repo |
| `/Users/jiangwei/Documents/final/src/domain/models.py` | StrategyDefinition 模型定义 |
| `/Users/jiangwei/Documents/final/tests/unit/test_strategy_apply.py` | apply 端点测试 |

### B. 搜索索引

| 关键词 | 出现文件数 | 主要文件 |
|--------|-----------|---------|
| `custom_strategies` | 3 | signal_repository.py, api.py, test_strategy_apply.py |
| `get_custom_strategy` | 2 | api.py, signal_repository.py |
| `SignalRepository` | 30 | signal_repository.py, api.py 及多个测试 |
| `StrategyConfigRepository` | 2 | config_repositories.py, api.py |
| `strategy_repo` | 15 | api.py, api_v1_config.py, config_repositories.py 等 |
| `_config_globals` | 14 | api.py, api_v1_config.py, api_config_globals.py, main.py |
| `apply_strategy` | 3 | api.py, api_v1_config.py, test_strategy_apply.py |
