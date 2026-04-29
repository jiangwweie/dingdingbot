# 任务 1.4: 回测分批止盈模拟 - 实施方案

> **状态**: Draft
> **作者**: Architect
> **日期**: 2026-04-15
> **关联 Issue**: TP2-TP5 订单永远不会被撮合
> **前置依赖**: 任务 1.1（Order 模型新增 `actual_filled`/`close_pnl`/`close_fee` 字段）

---

## 1. 问题描述

回测中 `OrderManager` 已生成 TP2/TP3/TP4/TP5 订单，但 `matching_engine.py:161` 只匹配 `OrderRole.TP1`，`matching_engine.py:222` 排序也只认 TP1，`backtester.py:1438` 统计只认 TP1，`_execute_fill` 方法也只处理 TP1/SL。导致：

1. TP2-TP5 订单永远挂单、永远不会被触发
2. 即使被触发，`_execute_fill` 会走到 else 分支不做任何处理
3. 统计数据中不会记录 TP2-TP5 成交

---

## 2. 改动文件清单

### 2.1 `src/domain/models.py` — Order 新增字段 + PositionCloseEvent 模型

#### 改动 A: Order 模型新增字段（依赖任务 1.1，如果 1.1 已完成则跳过）

**位置**: 约 line 1030（`filled_at` 字段之后）

**新增三个字段**（任务 1.4 的数据源，由任务 1.1 添加）:

```python
# 任务 1.1 新增：订单级成交明细（不修改 filled_qty 语义）
actual_filled: Optional[Decimal] = None    # 本次实际成交量（防超卖截断后的真实值）
close_pnl: Optional[Decimal] = None        # 本次出场的净 PnL（gross_pnl - fee）
close_fee: Optional[Decimal] = None        # 本次出场的手续费
```

> **注意**: 如果任务 1.1 尚未合并，需先在 Order 模型中添加这三个字段，否则 1.4 无法引用。

#### 改动 B: 新增 PositionCloseEvent 模型

**位置**: 约 line 1250（`PositionSummary` 定义之后，`PMSBacktestReport` 定义之前）

**改动**: 新增 `PositionCloseEvent` Pydantic 模型

```python
class PositionCloseEvent(FinancialModel):
    """单笔平仓成交事件（用于记录分批止盈的每一笔成交）"""
    position_id: str
    order_id: str
    event_type: str                    # TP1/TP2/TP3/TP4/TP5/SL
    event_category: str                # "exit"
    close_price: Decimal
    close_qty: Decimal
    close_pnl: Decimal
    close_fee: Decimal
    close_time: int                    # 毫秒时间戳
    exit_reason: str
```

**位置**: 约 line 1310（`PMSBacktestReport.positions` 之后）

**改动**: 在 `PMSBacktestReport` 上新增 `close_events` 字段

```python
# 新增字段
close_events: List[PositionCloseEvent] = Field(default_factory=list)
```

### 2.2 `src/domain/matching_engine.py` — 扩展 TP 匹配条件 + 排序

#### 改动 A: line 159-161 — 匹配条件扩展

**改动前**:
```python
elif order.order_type == OrderType.LIMIT and order.order_role == OrderRole.TP1:
```

**改动后**:
```python
elif order.order_type == OrderType.LIMIT and order.order_role in (
    OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5
):
```

#### 改动 B: line 158-159 — 注释更新

**改动前**:
```python
# 2. 处理止盈单 (LIMIT + OrderRole.TP1) - T2 修复
```

**改动后**:
```python
# 2. 处理止盈单 (LIMIT + OrderRole.TP1~TP5) - T2 修复 / T1.4 扩展
```

#### 改动 C: line 177 — 注释更新

**改动前**:
```python
# 注意：TP1 成交不代表仓位死亡，不需要撤销关联单
```

**改动后**:
```python
# 注意：TP 成交不代表仓位死亡，不需要撤销关联单（TP2-TP5 同理）
```

#### 改动 D: line 206-222 — `_sort_orders_by_priority` 排序逻辑扩展

**改动前**:
```python
# 止盈类订单 - 中等优先级
elif order.order_type == OrderType.LIMIT and order.order_role == OrderRole.TP1:
    return OrderPriority.TP
```

**改动后**:
```python
# 止盈类订单 (TP1~TP5) - 中等优先级
elif order.order_type == OrderType.LIMIT and order.order_role in (
    OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5
):
    return OrderPriority.TP
```

#### 改动 E: line 208 — 注释更新

**改动前**:
```python
2. LIMIT + OrderRole.TP1
```

**改动后**:
```python
2. LIMIT + OrderRole.TP1~TP5
```

#### 改动 F: line 267-268 + 326 — `_execute_fill` 平仓分支扩展

**两处改动** (docstring + 实际代码):

**docstring 改动** (line 267-268):
```python
# 改动前:
elif order.order_role in [OrderRole.TP1, OrderRole.SL]:
# 改动后:
elif order.order_role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5, OrderRole.SL]:
```

**实际代码改动** (line 326):
```python
# 改动前:
elif order.order_role in [OrderRole.TP1, OrderRole.SL]:
# 改动后:
elif order.order_role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5, OrderRole.SL]:
```

### 2.3 `src/application/backtester.py` — 扩展统计 + 新增 close_events

#### 改动 A: line 1438 — 统计分支扩展

**改动前**:
```python
elif order.order_role in [OrderRole.TP1, OrderRole.SL]:
```

**改动后**:
```python
elif order.order_role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5, OrderRole.SL]:
```

#### 改动 B: 约 line 1459 之后 — 新增 close_event 记录逻辑

**新增代码** (独立追加在原有 `elif` 块之后、Step 8 之前):

```python
# 【任务 1.4 新增】记录所有 TP/SL 成交事件（内存中，不改变现有统计逻辑）
# 数据源：使用 Order 上新增的专用字段（依赖任务 1.1）
#   - order.actual_filled: 本次实际成交量（不修改 filled_qty 语义）
#   - order.close_pnl: 本次出场的净 PnL（独立计算，不依赖 position.realized_pnl）
#   - order.close_fee: 本次出场的手续费（独立计算，不依赖 position.total_fees_paid）
all_tp_sl_roles = [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5, OrderRole.SL]
if order.order_role in all_tp_sl_roles and position and order.actual_filled > 0:
    close_event = PositionCloseEvent(
        position_id=position.id,
        order_id=order.id,
        event_type=order.order_role.value,
        event_category='exit',
        close_price=order.average_exec_price,
        close_qty=order.actual_filled,
        close_pnl=order.close_pnl,
        close_fee=order.close_fee,
        close_time=kline.timestamp,
        exit_reason=order.exit_reason or order.order_role.value,
    )
    all_close_events.append(close_event)
```

#### 改动 C: 约 line 1490 — 循环外初始化 close_events 列表

在 K 线循环之前（约 line 1280 附近，与 `equity_curve = []` 同级）新增:

```python
all_close_events: List[PositionCloseEvent] = []
```

在 K 线循环中，TP/SL 成交时:

```python
all_close_events.append(close_event)
```

#### 改动 D: 约 line 1516 — PMSBacktestReport 构造时传入 close_events

```python
report = PMSBacktestReport(
    # ... 原有字段 ...
    close_events=all_close_events,  # 新增
)
```

### 2.4 `src/infrastructure/backtest_repository.py` — 新增 position_close_events 表

#### 改动 A: `initialize()` 方法 — 新增表创建

在 `initialize()` 方法末尾（约 line 125 之后）新增:

```python
# Create position_close_events table (任务 1.4)
# 双关联设计：
#   - report_id: 关联回测报告，支持按报告查询所有平仓事件
#   - position_id: 关联仓位，支持仓位级分析（与 QA 审查方案一致）
await self._db.execute("""
    CREATE TABLE IF NOT EXISTS position_close_events (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id       TEXT NOT NULL,
        position_id     TEXT NOT NULL,
        order_id        TEXT,
        event_type      TEXT NOT NULL,
        event_category  TEXT NOT NULL,
        close_price     TEXT NOT NULL,
        close_qty       TEXT NOT NULL,
        close_pnl       TEXT NOT NULL,
        close_fee       TEXT NOT NULL,
        close_time      INTEGER NOT NULL,
        exit_reason     TEXT NOT NULL,
        FOREIGN KEY (report_id) REFERENCES backtest_reports(id) ON DELETE CASCADE,
        FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE
    )
""")

await self._db.execute("""
    CREATE INDEX IF NOT EXISTS idx_close_events_report_id
    ON position_close_events(report_id)
""")

await self._db.execute("""
    CREATE INDEX IF NOT EXISTS idx_close_events_position_id
    ON position_close_events(position_id)
""")

await self._db.commit()
```

#### 改动 B: `save_report()` 方法 — 批量写入 close_events

在 `save_report()` 末尾（约 line 375 `commit` 之前）新增:

```python
# 保存 close_events (任务 1.4)
# id 为 AUTOINCREMENT，由 SQLite 自动分配，不需要手动构造 event_id
if hasattr(report, 'close_events') and report.close_events:
    for event in report.close_events:
        await self._db.execute("""
            INSERT INTO position_close_events (
                report_id, position_id, order_id,
                event_type, event_category,
                close_price, close_qty, close_pnl, close_fee,
                close_time, exit_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            event.position_id,
            event.order_id,
            event.event_type,
            event.event_category,
            self._decimal_to_str(event.close_price),
            self._decimal_to_str(event.close_qty),
            self._decimal_to_str(event.close_pnl),
            self._decimal_to_str(event.close_fee),
            event.close_time,
            event.exit_reason,
        ))
```

#### 改动 C: `get_report()` 方法 — 反序列化 close_events

在 `get_report()` 构造 `PMSBacktestReport` 之前（约 line 387 之后）新增查询:

```python
# 加载 close_events (任务 1.4)
close_events = []
cursor = await self._db.execute("""
    SELECT * FROM position_close_events WHERE report_id = ?
    ORDER BY close_time ASC
""", (report_id,))
for row in await cursor.fetchall():
    close_events.append(PositionCloseEvent(
        position_id=row["position_id"],
        order_id=row["order_id"],
        event_type=row["event_type"],
        event_category=row["event_category"],
        close_price=self._str_to_decimal(row["close_price"]),
        close_qty=self._str_to_decimal(row["close_qty"]),
        close_pnl=self._str_to_decimal(row["close_pnl"]),
        close_fee=self._str_to_decimal(row["close_fee"]),
        close_time=row["close_time"],
        exit_reason=row["exit_reason"],
    ))
```

在 `PMSBacktestReport` 构造时传入:

```python
close_events=close_events,
```

---

## 3. 数据流图（新增/修改路径）

```
                    ┌─────────────────────────────────┐
                    │    OrderManager.create_order_chain│
                    │    (生成 TP1/TP2/TP3/TP4/TP5)     │
                    └──────────────┬──────────────────┘
                                   │ 订单列表
                                   ▼
                    ┌─────────────────────────────────┐
                    │  _sort_orders_by_priority()      │  ← 改动: TP1~TP5 同一优先级
                    │  SL(1) > TP(2) > ENTRY(3)       │
                    └──────────────┬──────────────────┘
                                   │ 排序后订单
                                   ▼
                    ┌─────────────────────────────────┐
                    │  match_orders_for_kline()        │
                    │  ├─ SL 匹配 (不改)              │
                    │  ├─ TP 匹配 ← 改动: TP1~TP5     │  ← 改动 1
                    │  └─ ENTRY 匹配 (不改)           │
                    └──────────────┬──────────────────┘
                                   │ 已执行订单
                                   ▼
                    ┌─────────────────────────────────┐
                    │  _execute_fill()                │
                    │  平仓分支 ← 改动: TP1~TP5+SL    │  ← 改动 2
                    └──────────────┬──────────────────┘
                                   │ 成交事件
                                   ▼
                    ┌─────────────────────────────────┐
                    │  backtester.py 循环内           │
                    │  ├─ 原有统计 (不改逻辑)          │
                    │  └─ 新增: all_close_events []   │  ← 改动 3
                    └──────────────┬──────────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────────┐
                    │  PMSBacktestReport              │
                    │  close_events = all_close_events│
                    └──────────────┬──────────────────┘
                                   │
                    ▼              ▼
     ┌──────────────────┐  ┌──────────────────┐
     │ 前端 API 展示    │  │ backtest_repository│
     │  分批止盈明细    │  │  → position_close │  ← 改动 4
     │                  │  │    _events 表     │
     └──────────────────┘  └──────────────────┘
```

---

## 4. 隔离方案说明

### 4.1 为什么新逻辑不影响现有统计

| 维度 | 现有逻辑 | 新增逻辑 | 隔离保障 |
|------|----------|----------|----------|
| **统计数据** | `total_trades`, `win_rate`, `total_pnl` 仅在 `order_role in [TP1, SL]` 且 `position.is_closed` 时累计 | 新逻辑只写 `close_events` 到内存列表 | 条件判断完全独立，新代码不修改任何统计变量 |
| **仓位状态** | `position.is_closed` 由 `_execute_fill` 控制 | 不改变 | `_execute_fill` 逻辑不变（只是扩大 TP 角色范围） |
| **账户余额** | `account.total_balance` 由 `_execute_fill` 更新 | 不改变 | `_execute_fill` 的 PnL 计算逻辑不变 |
| **数据库写入** | 只写 `backtest_reports` 表 + `positions_summary` JSON | 新增 `position_close_events` 表 | 新表通过 FK `report_id` + `position_id` 双关联，不改动旧表结构 |
| **PMSBacktestReport** | `positions` 字段不变 | 新增 `close_events` 字段 | 带 `default_factory=list`，旧代码不传此字段时为空列表 |

### 4.2 渐进式安全策略

1. **新代码全部追加**，不删除/替换任何现有行（除匹配条件扩展外）
2. **匹配条件扩展**只从 `== TP1` 改为 `in (TP1..TP5)`，语义完全等价向上兼容
3. **close_events** 默认空列表，不影响不传此字段的消费者
4. **数据库表** 独立新建，通过 FK 关联，不改动 `backtest_reports` 表结构

---

## 5. 边界情况处理

### 5.1 同一 K 线 TP1 + TP2 + SL 同时触发

**场景**: K 线 high 同时触及 TP1 和 TP2，low 同时触及 SL

**处理**: 保持悲观撮合不变。优先级排序保证 SL(1) > TP(2)，SL 优先成交。TP1 和 TP2 都是 LIMIT 单，按订单列表顺序依次匹配。由于排序后 TP1-TP5 同优先级，它们在列表中的相对顺序取决于原始插入顺序（TP1 先于 TP2 先于 TP3）。

**结果**: SL 优先 → TP1 → TP2。TP1 成交后 `position.current_qty` 减少，TP2 可能部分成交或完全不成交（取决于剩余仓位）。

### 5.2 close_qty = 0

**场景**: 订单 `requested_qty > 0` 但 `position.current_qty = 0`（仓位已完全平仓）

**处理**: `_execute_fill` 中的 `actual_filled = min(order.requested_qty, position.current_qty)` 保证 `actual_filled = 0`。后续 PnL 计算为 0，账户不变。在 close_event 记录时增加 `order.actual_filled > 0` 前置条件过滤（`actual_filled` 由任务 1.1 新增，不修改 `filled_qty` 语义）。

### 5.3 加仓场景

**场景**: 同一 signal_id 有两次 ENTRY，第二次 ENTRY 后 position.current_qty 增加，此时 TP1-TP5 的 `requested_qty` 可能超过首次开仓量

**处理**: `_execute_fill` 的防超卖保护 (`min(requested_qty, current_qty)`) 确保不会超卖。TP2-TP5 的 `requested_qty` 通常基于首次开仓量的百分比（如 TP1=50%, TP2=30%, TP3=20%），加仓场景下可能总 requested_qty < current_qty，正常处理。

### 5.4 TP2 先于 TP1 成交（价格穿越）

**场景**: 价格直接跳空越过 TP1 触及 TP2

**处理**: 由于优先级排序 TP1 和 TP2 同优先级，按列表顺序处理。TP1 在前，会先尝试匹配 TP1。如果 K 线 high >= TP1.price，TP1 成交。然后同一 K 线继续处理 TP2。这符合实际交易逻辑——价格必须依次经过 TP1 才能到 TP2。

**极端情况**: 如果 TP1 和 TP2 价格相同（配置错误），TP1 先成交，TP2 在同一 K 线也满足条件但可能因仓位减少而部分成交或不成交。

### 5.5 Position 不存在

**场景**: 订单关联的 signal_id 在 `positions_map` 中无对应 Position

**处理**: `_execute_fill` 已有防御逻辑 — `if position is None: return`。close_event 记录时增加 `and position` 前置条件。

---

## 6. 影响文件列表

| 文件 | 改动类型 | 改动行数估算 | 风险级别 |
|------|----------|-------------|----------|
| `src/domain/models.py` | 新增类 + 新增字段 | ~20 行 | 低 |
| `src/domain/matching_engine.py` | 条件扩展 + 注释更新 | ~8 行 | 低 |
| `src/application/backtester.py` | 条件扩展 + 新增逻辑 | ~30 行 | 中 |
| `src/infrastructure/backtest_repository.py` | 新表 + 新写入逻辑 | ~60 行 | 中 |
| `tests/unit/test_matching_engine.py` | 新增 TP2-TP5 测试 | ~100 行 | 低 |
| `tests/unit/test_backtester_tp_events.py` | 新测试文件 | ~150 行 | 低 |
| `tests/integration/test_backtest_data_integrity.py` | 新增集成测试 | ~80 行 | 低 |

---

## 7. 测试案例

### 7.1 单元测试 (8 个)

#### UT-1: TP2 止盈单撮合触发 (LONG)

- **测试名称**: `test_tp2_limit_order_triggered_long`
- **前置条件**: 持有 LONG 仓位，TP2 LIMIT 单挂单 price=72000
- **执行步骤**:
  1. 创建 LONG Position (entry=70000, qty=0.1)
  2. 创建 TP2 LIMIT Order (price=72000, qty=0.03, status=OPEN)
  3. K 线 high=73000, low=69000
  4. 调用 `match_orders_for_kline()`
- **预期结果**:
  - TP2 订单 status=FILLED
  - exec_price = 72000 * (1 - 0.0005) = 71964
  - position.current_qty = 0.07
  - executed_orders 包含 TP2 订单

#### UT-2: TP3 止盈单撮合触发 (SHORT)

- **测试名称**: `test_tp3_limit_order_triggered_short`
- **前置条件**: 持有 SHORT 仓位，TP3 LIMIT 单挂单 price=68000
- **执行步骤**:
  1. 创建 SHORT Position (entry=70000, qty=0.1)
  2. 创建 TP3 LIMIT Order (price=68000, qty=0.02, status=OPEN)
  3. K 线 high=71000, low=67000
  4. 调用 `match_orders_for_kline()`
- **预期结果**:
  - TP3 订单 status=FILLED
  - exec_price = 68000 * (1 + 0.0005) = 68034
  - position.current_qty = 0.08

#### UT-3: TP4/TP5 订单优先级与 TP1 相同

- **测试名称**: `test_tp4_tp5_same_priority_as_tp1`
- **前置条件**: 同时存在 TP1, TP2, TP3, TP4, TP5, SL, ENTRY 订单
- **执行步骤**:
  1. 创建 7 个订单 (SL, TP1-TP5, ENTRY)
  2. 调用 `_sort_orders_by_priority()`
- **预期结果**:
  - 排序结果: [SL] 在前，[TP1, TP2, TP3, TP4, TP5] 在中（相对顺序不变），[ENTRY] 在后
  - SL 优先级值 = 1, TP1-TP5 优先级值 = 2, ENTRY 优先级值 = 3

#### UT-4: TP5 未触发 (价格未达)

- **测试名称**: `test_tp5_not_triggered_price_not_reached`
- **前置条件**: TP5 LIMIT 单 price=80000
- **执行步骤**:
  1. 创建 TP5 Order (price=80000, status=OPEN)
  2. K 线 high=75000 (未达 80000)
  3. 调用 `match_orders_for_kline()`
- **预期结果**:
  - TP5 订单 status 仍为 OPEN
  - executed_orders 不包含 TP5

#### UT-5: _execute_fill 处理 TP3 平仓 PnL

- **测试名称**: `test_execute_fill_tp3_pnl_calculation`
- **前置条件**: LONG 仓位 entry=70000, TP3 exec_price=74000, qty=0.02
- **执行步骤**:
  1. 创建 LONG Position (entry=70000, current_qty=0.1)
  2. 创建 TP3 Order (role=TP3, exec_price=74000, qty=0.02)
  3. 调用 `_execute_fill()`
- **预期结果**:
  - position.current_qty = 0.08
  - gross_pnl = (74000 - 70000) * 0.02 = 80
  - fee = 74000 * 0.02 * 0.0004 = 0.592
  - net_pnl = 80 - 0.592 = 79.408
  - position.realized_pnl = 79.408
  - position.is_closed = False

#### UT-6: _execute_fill 处理 TP2 后仓位未完全平仓

- **测试名称**: `test_execute_fill_tp2_partial_close`
- **前置条件**: 仓位 qty=0.1, TP2 requested_qty=0.03
- **执行步骤**:
  1. 调用 `_execute_fill()` 处理 TP2
- **预期结果**:
  - position.current_qty = 0.07
  - position.is_closed = False
  - account.total_balance 增加 net_pnl

#### UT-7: TP 成交后仓位归零触发 is_closed

- **测试名称**: `test_execute_fill_tp_final_close`
- **前置条件**: 仓位 qty=0.02, TP3 requested_qty=0.02 (最后一批)
- **执行步骤**:
  1. 调用 `_execute_fill()` 处理 TP3
- **预期结果**:
  - position.current_qty = 0
  - position.is_closed = True

#### UT-8: Decimal 精度 — TP4 滑点计算

- **测试名称**: `test_tp4_slippage_decimal_precision`
- **前置条件**: TP4 price=71234.567
- **执行步骤**:
  1. LONG 方向，K 线 high=72000
  2. 验证 exec_price 计算
- **预期结果**:
  - exec_price = 71234.567 * (1 - 0.0005) = 71198.9497165
  - 结果为 Decimal 类型，无 float 参与

### 7.2 集成测试 (4 个)

#### IT-1: 完整回测流程 — TP1+TP2+TP3 分批止盈

- **测试名称**: `test_backtest_multi_tp_partial_close`
- **前置条件**: 策略配置 tp_levels=3, tp_ratios=[0.5, 0.3, 0.2]
- **执行步骤**:
  1. 创建 BacktestRequest (symbol=BTC/USDT, timeframe=1h)
  2. 构造 100 根 K 线数据 (包含上涨趋势)
  3. 执行 PMS 回测
  4. 检查 report.close_events
- **预期结果**:
  - close_events 包含 3 条 TP 记录
  - event_type 分别为 TP1, TP2, TP3
  - close_qty 比例为 5:3:2
  - 所有 close_qty 之和 = 初始仓位数量

#### IT-2: close_events 持久化到数据库

- **测试名称**: `test_close_events_persisted_to_db`
- **前置条件**: 初始化 BacktestReportRepository (内存数据库)
- **执行步骤**:
  1. 执行回测，获取 PMSBacktestReport (含 close_events)
  2. 调用 `repository.save_report(report, ...)`
  3. 调用 `repository.get_report(report_id)`
- **预期结果**:
  - position_close_events 表有对应记录
  - 反序列化后的 close_events 数量 = 原始数量
  - 每条 close_event 的字段值一致

#### IT-3: SL 优先于 TP 撮合

- **测试名称**: `test_sl_priority_over_tp_in_backtest`
- **前置条件**: 同一 K 线 high 触及 TP1, low 触及 SL
- **执行步骤**:
  1. 创建 LONG 仓位 + TP1 + SL 订单
  2. K 线同时满足 TP1 和 SL 触发条件
  3. 执行回测
- **预期结果**:
  - SL 先成交
  - TP1 被 `_cancel_related_orders` 撤销
  - close_events 只包含 SL 事件，不包含 TP1

#### IT-4: 回测报告中 close_events 数量与成交订单一致

- **测试名称**: `test_close_events_count_matches_executed_orders`
- **前置条件**: 执行含多次信号的回测
- **执行步骤**:
  1. 执行完整回测
  2. 统计 report.close_events 数量
  3. 统计所有 FILLED 的 TP/SL 订单数量
- **预期结果**:
  - close_events 数量 = FILLED 的 TP/SL 订单数量
  - 每个 close_event 的 order_id 对应一个 FILLED 订单

### 7.3 边界测试 (4 个)

#### BT-1: 同一 K 线 TP1+TP2+SL 同时触发

- **测试名称**: `test_same_kline_tp1_tp2_sl_simultaneous`
- **前置条件**: K 线 high 触及 TP1 和 TP2，low 触及 SL
- **执行步骤**:
  1. LONG 仓位 qty=0.1
  2. TP1 (qty=0.05, price=72000), TP2 (qty=0.03, price=73000), SL (trigger=69000)
  3. K 线 high=74000, low=68000
- **预期结果**:
  - SL 优先成交
  - TP1, TP2 被撤销
  - 只有 SL 事件写入 close_events

#### BT-2: TP2 requested_qty 超过剩余仓位

- **测试名称**: `test_tp2_requested_qty_exceeds_remaining_position`
- **前置条件**: TP1 已成交 50%，剩余 qty=0.05，TP2 requested_qty=0.08
- **执行步骤**:
  1. 先执行 TP1 (qty=0.05)
  2. 再执行 TP2 (requested_qty=0.08, 实际剩余 0.05)
- **预期结果**:
  - TP2 actual_filled = 0.05 (截断)
  - position.current_qty = 0
  - position.is_closed = True

#### BT-3: 无仓位时收到 TP 订单

- **测试名称**: `test_tp_order_with_no_position`
- **前置条件**: positions_map 中无对应 signal_id 的 Position
- **执行步骤**:
  1. 创建 TP2 Order (signal_id="nonexistent")
  2. K 线满足 TP2 触发条件
  3. 调用 `match_orders_for_kline()`
- **预期结果**:
  - TP2 不被执行（position is None 时 `_execute_fill` 直接 return）
  - 不抛异常
  - 无 close_event 产生

#### BT-4: TP 价格等于 K 线 high (边界值)

- **测试名称**: `test_tp_triggered_at_exact_high`
- **前置条件**: TP1 price = K 线 high = 71000
- **执行步骤**:
  1. 创建 TP1 LIMIT Order (price=71000)
  2. K 线 high=71000 (精确相等)
- **预期结果**:
  - TP1 被触发 (k_high >= order.price，包含等于)
  - exec_price = 71000 * (1 - 0.0005) = 70964.5

---

## 8. 实施顺序建议

```
Step 1: models.py      → 新增 PositionCloseEvent + close_events 字段
Step 2: matching_engine.py → 扩展 TP 匹配条件 + 排序
Step 3: backtester.py  → 扩展统计 + close_events 收集
Step 4: backtest_repository.py → 新表 + 持久化
Step 5: 单元测试       → 8 个 UT
Step 6: 集成测试       → 4 个 IT
Step 7: 边界测试       → 4 个 BT
```

预计总改动量: ~220 行 (含测试 ~180 行, 生产代码 ~40 行)
