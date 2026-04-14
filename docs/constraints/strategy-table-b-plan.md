# 方案 B：彻底统一策略表 - 详细执行方案

> 日期: 2026-04-13
> 状态: 已确认，待执行
> 优先级: P0

---

## 一、前端调用方清单

### 1.1 使用旧端点的文件（必须修改）

| # | 文件:行号 | 旧端点 | 请求体格式 | 新端点 | 转换方式 |
|---|-----------|--------|-----------|--------|---------|
| 1 | `web-front/src/lib/api.ts:602-614` `fetchStrategyTemplates()` | `GET /api/strategies/templates` | 无 | `GET /api/v1/config/strategies` (通过 `configApi.getStrategies()`) | 响应格式从 `{templates: [...]}` 变为 `axios response {data: Strategy[]}`。需改用 `configApi.getStrategies()` |
| 2 | `web-front/src/lib/api.ts:1030-1041` `fetchStrategyMetadata()` | `GET /api/strategies/meta` | 无 | **保留** `/api/strategies/meta` | 此端点不属于策略 CRUD，不在删除范围 |
| 3 | `web-front/src/lib/api.ts:1084-1097` `previewStrategy()` | `POST /api/strategies/preview` | `{logic_tree, symbol, timeframe}` | **保留** `/api/strategies/preview` | 此端点不属于策略 CRUD，不在删除范围 |
| 4 | `web-front/src/lib/api.ts:1103-1115` `applyStrategy()` | `POST /api/strategies/{id}/apply` | 无 | **保留** `/api/strategies/{id}/apply` | 此端点已使用新表，无需修改 |
| 5 | `web-front/src/lib/api.ts:1618-1630` `fetchStrategyParamTemplates()` | `GET /api/strategies/templates` | 无 | `GET /api/v1/config/strategies` | 与 #1 相同端点 |
| 6 | `web-front/src/lib/api.ts:1635-1651` `saveStrategyParamTemplate()` | `POST /api/strategies/templates` | `{name, description}` | `POST /api/v1/config/strategies` | 请求体格式完全不同，需用 `configApi.createStrategy()` |
| 7 | `web-front/src/lib/api.ts:1656-1668` `loadStrategyParamTemplate()` | `POST /api/strategies/templates/{id}/load` | 无 | 无直接替代 | 此端点实际不存在于后端（可能已废弃）|
| 8 | `web-front/src/lib/api.ts:1673-1685` `deleteStrategyParamTemplate()` | `DELETE /api/strategies/templates/{id}` | 无 | `DELETE /api/v1/config/strategies/{id}` | 改用 `configApi.deleteStrategy()` |
| 9 | `web-front/src/pages/Backtest.tsx:238` `handleImportTemplate()` | `GET /api/strategies/{id}` | 无 | `GET /api/v1/config/strategies/{id}` | 改用 `configApi.getStrategy(id)` |
| 10 | `web-front/src/pages/PMSBacktest.tsx:254` `handleImportTemplate()` | `GET /api/strategies/{id}` | 无 | `GET /api/v1/config/strategies/{id}` | 同上 |
| 11 | `web-front/src/components/StrategyTemplatePicker.tsx:7` | 接口定义 `id: number` | — | — | `id` 类型从 `number` 改为 `string` |

### 1.2 已使用新端点的文件（无需修改）

| 文件 | 说明 |
|------|------|
| `web-front/src/api/config.ts:387-478` `configApi` | 全部使用 `/api/v1/config/strategies` |
| `web-front/src/pages/config/StrategyConfig.tsx` | 全部通过 `configApi` 调用 |
| `web-front/src/pages/config/StrategiesTab.tsx` | 全部通过 `configApi` 调用 |

### 1.3 前端改动详细步骤

#### Step A: `web-front/src/lib/api.ts`

1. **删除** L602-614 `fetchStrategyTemplates()` — 改用 `configApi.getStrategies()`
2. **删除** L1618-1685 整套 strategy param template 函数 (`fetchStrategyParamTemplates`, `saveStrategyParamTemplate`, `loadStrategyParamTemplate`, `deleteStrategyParamTemplate`) — 这些是参数模板而非策略配置，如确实需要则需后端新增专用端点
3. **修改** L1103-1115 `applyStrategy()` — 无需修改（后端已使用新表）

#### Step B: `web-front/src/pages/Backtest.tsx`

1. **修改** L238 `fetch(\`/api/strategies/${templateStrategy.id}\`)` — 改为 `configApi.getStrategy(templateStrategy.id)`
2. 需额外导入 `configApi` from `../api/config`

#### Step C: `web-front/src/pages/PMSBacktest.tsx`

1. **修改** L254 `fetch(\`/api/strategies/${templateStrategy.id}\`)` — 改为 `configApi.getStrategy(templateStrategy.id)`
2. 需额外导入 `configApi` from `../api/config`

#### Step D: `web-front/src/components/StrategyTemplatePicker.tsx`

1. **修改** L7 `id: number` -> `id: string`

#### Step E: `web-front/src/components/strategy-params/StrategyParamPanel.tsx`

此组件使用的是 `/api/strategy/params` 系列端点（L1520-1601），与策略表 CRUD 无关，**无需修改**。但如果它调用了 `fetchStrategyParamTemplates` 等已删除的函数，需同步移除相关 UI。

#### Step F: 测试文件

1. `web-front/src/pages/config/__tests__/StrategiesTab.test.tsx:36-38` — mock 对象无需修改（继续使用 `configApi`）

---

## 二、后端改动清单

### 2.1 `src/interfaces/api.py` — 删除

| 删除范围 | 行号 | 说明 | 行数 |
|---------|------|------|------|
| 旧请求模型类 | L2526-2537 | `StrategyCreateRequest`, `StrategyUpdateRequest`（旧版） | 12 |
| 旧响应模型类 | L2540-2543 | `StrategyMetaResponse`（保留，被 meta 端点使用） | 0（保留） |
| GET `/api/strategies/templates` | L2652-2671 | `list_strategy_templates()` | 20 |
| GET `/api/v1/config/strategies` (旧) | L2678-2691 | `get_custom_strategies_v1()` — 与 v1 路由冲突 | 14 |
| GET `/api/strategies` | L2694-2709 | `get_custom_strategies()` | 16 |
| GET `/api/strategies/{strategy_id}` | L2712-2740 | `get_custom_strategy()` | 29 |
| POST `/api/strategies` | L2743-2789 | `create_custom_strategy()` | 47 |
| PUT `/api/strategies/{strategy_id}` | L2792-2843 | `update_custom_strategy()` | 52 |
| DELETE `/api/strategies/{strategy_id}` | L2846-2869 | `delete_custom_strategy()` | 24 |
| GET `/api/config/strategies` | L6633-6650 | `list_config_strategies()` | 18 |
| 旧请求模型类 | L2522-2523 | `from pydantic import BaseModel, Field` / `from typing import Optional` — **仅当这些 import 不被其他代码使用时才删除** | 0（大概率需要保留） |

**小计: ~232 行删除**

### 2.2 `src/interfaces/api.py` — 保留（不属于策略 CRUD）

| 保留范围 | 行号 | 说明 |
|---------|------|------|
| `get_strategy_metadata()` | L2546-2649 | `/api/strategies/meta` — 动态表单元数据，保留 |
| `preview_strategy()` | L2904-3211 | `/api/strategies/preview` — 热预览，保留 |
| `apply_strategy()` | L3217-3280 | `/api/strategies/{id}/apply` — 已使用新表，保留 |
| `StrategyPreviewRequest/Response` | L2875-2887 | preview 端点模型，保留 |
| `StrategyApplyRequest/Response` | L2890-2901 | apply 端点模型，保留 |

### 2.3 `src/infrastructure/signal_repository.py` — 删除

| 删除范围 | 行号 | 说明 | 行数 |
|---------|------|------|------|
| 表创建 DDL | L231-246 | `custom_strategies` 表 + 索引 | 16 |
| `get_all_custom_strategies()` | L1529-1544 | 查询方法 | 16 |
| `get_custom_strategy_by_id()` | L1546-1562 | 按 ID 查询 | 17 |
| `create_custom_strategy()` | L1564-1592 | 创建方法 | 29 |
| `update_custom_strategy()` | L1594-1640 | 更新方法 | 47 |
| `delete_custom_strategy()` | L1642-1656 | 删除方法 | 15 |
| 注释分隔行 | L1525-1527 | `# Custom Strategies CRUD Methods` 注释块 | 3 |

**小计: ~143 行删除**

### 2.4 `tests/unit/test_strategy_apply.py` — 修改

| 行号 | 改动 | 说明 |
|------|------|------|
| L291-306 | **删除** mock `get_custom_strategy_by_id` | 旧表 mock |
| L291-306 | **替换为** mock `_config_globals._strategy_repo.get_by_id` | 新表 mock，返回 UUID ID 格式 |
| L325 | `strategy_id=1` -> `strategy_id=str(uuid.uuid4())` | ID 类型从 int 改为 str |
| L329 | `response.strategy_id == 1` -> 断言 UUID 格式 | 响应断言适配 |

---

## 三、数据迁移脚本

新建文件: `migrations/versions/2026-04-13-006_migrate_custom_strategies.py`

```python
"""迁移 custom_strategies 到 strategies 表并删除旧表

Revision ID: 006
Revises: 005
Create Date: 2026-04-13

本迁移执行以下操作：
1. 从 custom_strategies 表读取所有策略
2. 解析 strategy_json 并映射到 strategies 表的扁平字段
3. 插入到 strategies 表（生成新 UUID）
4. 删除 custom_strategies 表
"""
from typing import Sequence, Union
import json
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 如果旧表不存在，直接跳过（全新部署）
    if 'custom_strategies' not in tables:
        print("custom_strategies 表不存在，跳过迁移")
        return

    # 确保新表存在
    if 'strategies' not in tables:
        raise RuntimeError("strategies 表不存在，请先执行创建 strategies 表的迁移")

    # 读取旧表数据
    result = conn.execute(sa.text("SELECT * FROM custom_strategies"))
    old_rows = result.fetchall()

    migrated_count = 0
    skipped_count = 0

    for row in old_rows:
        try:
            strategy_json = json.loads(row["strategy_json"])
            new_id = str(uuid.uuid4())

            # 解析 trigger_config
            trigger_config = {}
            triggers = strategy_json.get("triggers", [])
            if triggers:
                trigger_config = triggers[0] if isinstance(triggers, list) else triggers
            elif "trigger" in strategy_json:
                trigger_config = strategy_json["trigger"]

            # 解析 filter_configs
            filter_configs = strategy_json.get("filters", [])

            # 解析 filter_logic
            filter_logic = strategy_json.get("filter_logic", "AND")

            # 解析 symbols 和 timeframes
            symbols = []
            timeframes = []
            apply_to = strategy_json.get("apply_to", [])
            if apply_to:
                for scope in apply_to:
                    if ":" in scope:
                        parts = scope.split(":")
                        sym = ":".join(parts[:-1])  # 支持 BTC/USDT:USDT 这种带冒号的
                        tf = parts[-1]
                        if sym not in symbols:
                            symbols.append(sym)
                        if tf not in timeframes:
                            timeframes.append(tf)
                    else:
                        if scope not in symbols:
                            symbols.append(scope)

            # 如果无法解析出 symbols/timeframes，使用默认值
            if not symbols:
                symbols = strategy_json.get("symbols", ["*"])
            if not timeframes:
                timeframes = strategy_json.get("timeframes", ["*"])

            now = row.get("created_at", "")
            updated = row.get("updated_at", now)

            conn.execute(
                sa.text("""
                    INSERT INTO strategies
                    (id, name, description, is_active, trigger_config, filter_configs,
                     filter_logic, symbols, timeframes, created_at, updated_at, version)
                    VALUES
                    (:id, :name, :description, :is_active, :trigger_config, :filter_configs,
                     :filter_logic, :symbols, :timeframes, :created_at, :updated_at, :version)
                """),
                {
                    "id": new_id,
                    "name": row["name"],
                    "description": row.get("description"),
                    "is_active": True,
                    "trigger_config": json.dumps(trigger_config),
                    "filter_configs": json.dumps(filter_configs),
                    "filter_logic": filter_logic,
                    "symbols": json.dumps(symbols),
                    "timeframes": json.dumps(timeframes),
                    "created_at": now,
                    "updated_at": updated,
                    "version": 1,
                }
            )
            migrated_count += 1
            print(f"  已迁移策略: {row['name']} (旧ID={row['id']} -> 新ID={new_id})")

        except Exception as e:
            skipped_count += 1
            print(f"  跳过策略 {row.get('name', 'unknown')}: {e}")

    conn.commit()
    print(f"\n迁移完成: 成功 {migrated_count} 条, 跳过 {skipped_count} 条")

    # 删除旧表
    op.drop_table("custom_strategies")
    print("已删除 custom_strategies 表")


def downgrade() -> None:
    """
    降级操作：重建 custom_strategies 表
    注意：无法恢复已迁移的数据（UUID 无法逆向映射）
    此操作仅重建空表结构。
    """
    op.create_table(
        "custom_strategies",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("strategy_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )
    op.create_index(
        "idx_custom_strategies_name",
        "custom_strategies",
        ["name"],
    )
    print("已重建 custom_strategies 表（空表）")
    print("警告: 迁移到 strategies 表的数据无法自动回滚")
```

---

## 四、风险评估与缓解

### 风险 1: 前端 StrategyTemplatePicker 功能中断

**描述**: Backtest.tsx 和 PMSBacktest.tsx 的「从策略工作台导入」功能依赖 `GET /api/strategies/templates` 和 `GET /api/strategies/{id}` 端点。

**影响**: 回测沙箱无法导入预设策略模板。

**缓解措施**:
1. 修改 `Backtest.tsx:238` 和 `PMSBacktest.tsx:254`，改用 `configApi.getStrategy(id)`
2. 修改 `fetchStrategyTemplates()` 调用，改用 `configApi.getStrategies()` 并从 response 中提取模板列表
3. `StrategyTemplatePicker.tsx` 中 `id: number` 改为 `id: string`
4. `handleImportTemplate` 中的响应格式适配：新端点返回 `StrategyDetailResponse` 而非 `{strategy: {...}}`

### 风险 2: 策略参数模板功能丢失

**描述**: `web-front/src/lib/api.ts` 中有 `fetchStrategyParamTemplates`, `saveStrategyParamTemplate`, `loadStrategyParamTemplate`, `deleteStrategyParamTemplate` 四个函数，它们使用 `/api/strategies/templates` 端点。

**影响**: 如果这些函数有实际用户，删除后端端点后功能将中断。

**缓解措施**:
1. 确认这些函数是否被任何组件实际调用（全局搜索调用方）
2. 如确有用户在用，需在后端新增专用的 `/api/strategy/param-templates` 端点来替代
3. 如无人使用，可直接删除相关前端代码

### 风险 3: 数据迁移信息丢失

**描述**: 旧表 `strategy_json` 中的完整 `StrategyDefinition` 结构可能包含新表扁平字段无法完全覆盖的字段（如 `logic_tree`、自定义扩展字段等）。

**影响**: 迁移后策略行为可能发生微妙变化。

**缓解措施**:
1. 迁移前导出 `custom_strategies` 全表 JSON 备份
2. 迁移脚本中打印每条迁移的映射结果，便于审计
3. 对于包含 `logic_tree` 的旧策略，在 `description` 中添加标记 `"[migrated-from-logic-tree]"` 便于后续人工审查
4. 先在 staging 环境执行迁移，验证策略行为一致后再上生产

### 风险 4: 测试遗漏导致回归

**描述**: 删除大量代码后可能有隐式依赖的测试未更新。

**影响**: CI 测试通过但生产环境出现 404/500 错误。

**缓解措施**:
1. 执行全量 `pytest tests/` 确认无失败
2. 特别关注 `test_strategy_apply.py` 中的 mock 更新
3. 搜索代码库中对 `get_custom_strategy_by_id`、`get_all_custom_strategies` 等方法的引用

### 风险 5: 路由注册顺序影响

**描述**: `api.py` 和 `api_v1_config.py` 注册了重叠的路由路径（如 `/api/v1/config/strategies`）。FastAPI 按注册顺序匹配，先注册的优先。

**影响**: 如果旧端点先于新端点注册，新端点可能永远不会被命中。

**缓解措施**:
1. 删除 `api.py` 中的 `get_custom_strategies_v1()` (L2678-2691) 后，`/api/v1/config/strategies` 将完全由 `api_v1_config.py` 的 router 处理
2. 验证 `api.py` 中没有其他 `/api/v1/config/*` 前缀的端点

---

## 五、验证清单

### 5.1 后端验证

1. **启动验证**: `python -c "from src.interfaces.api import app; from src.interfaces.api_v1_config import router"` 确认无路由冲突错误

2. **端点存在性**:
   ```bash
   curl -s http://localhost:8000/api/strategies/templates | python -m json.tool   # 应 404
   curl -s http://localhost:8000/api/strategies | python -m json.tool             # 应 404
   curl -s http://localhost:8000/api/config/strategies | python -m json.tool      # 应 404
   curl -s http://localhost:8000/api/v1/config/strategies | python -m json.tool   # 应 200 + 策略列表
   ```

3. **保留端点正常**:
   ```bash
   curl -s http://localhost:8000/api/strategies/meta | python -m json.tool        # 应 200
   curl -s -X POST http://localhost:8000/api/strategies/preview -H "Content-Type: application/json" -d '{"logic_tree":{"gate":"AND","children":[]},"symbol":"BTC/USDT:USDT","timeframe":"15m"}'  # 应正常响应
   ```

4. **数据库验证**: 确认 `custom_strategies` 表已不存在
   ```sql
   SELECT name FROM sqlite_master WHERE type='table' AND name='custom_strategies';  -- 应返回空
   ```

5. **全量测试**: `pytest tests/ -v` 全部通过

### 5.2 前端验证

6. **策略配置页面**: 访问 `/config/strategies`，确认列表正常加载、创建/编辑/删除/切换策略均正常工作

7. **回测沙箱**: 在 Backtest 和 PMSBacktest 页面点击「从策略工作台导入」，确认能正常加载策略列表并导入

8. **Dry Run 预览**: 在策略配置页面点击「Dry Run 预览」，确认正常执行

---

## 六、执行顺序

1. **Step 1** (后端): 执行数据迁移脚本 `migrations/versions/2026-04-13-006_migrate_custom_strategies.py`
2. **Step 2** (后端): 删除 `api.py` 中的 8 个旧策略端点 + 旧模型类 (~232 行)
3. **Step 3** (后端): 删除 `signal_repository.py` 中的旧表定义和 CRUD 方法 (~143 行)
4. **Step 4** (后端): 更新 `tests/unit/test_strategy_apply.py` 测试
5. **Step 5** (前端): 修改 `lib/api.ts` 中的旧端点调用 (~80 行删除/修改)
6. **Step 6** (前端): 修改 `Backtest.tsx`, `PMSBacktest.tsx`, `StrategyTemplatePicker.tsx` 的调用
7. **Step 7**: 全量回归测试 (pytest + 前端 vitest)
8. **Step 8**: 手动验证验证清单中的 8 个步骤

---

## 七、工作量估算

| 步骤 | 预估时间 | 风险等级 |
|------|---------|---------|
| Step 1: 数据迁移 | 0.5h | 中 |
| Step 2: 删除 api.py 端点 | 0.5h | 低 |
| Step 3: 删除 signal_repository 方法 | 0.5h | 低 |
| Step 4: 更新测试 | 1h | 中 |
| Step 5: 前端 api.ts 改动 | 0.5h | 低 |
| Step 6: 前端页面改动 | 1h | 中 |
| Step 7: 全量回归 | 1h | 低 |
| Step 8: 手动验证 | 0.5h | 低 |
| **总计** | **~5.5 小时** | |
