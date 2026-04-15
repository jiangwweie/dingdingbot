# 实现设计：PositionSummary 一对多出场事件列表

**文档类型**: 详细设计文档（实现级别）
**关联 ADR**: [PositionSummary 一对多出场事件设计](position-summary-close-event-design.md)
**创建日期**: 2026-04-14
**修订日期**: 2026-04-15
**状态**: 待评审

---

## 0. 方案变更记录（2026-04-15）

### 0.1 存储方案变更：JSON 嵌套 → 独立表

**原方案**：`close_events` 作为 JSON 嵌套在 `PositionSummary` 中，随回测报告整体序列化存储于 `backtest_reports` 表的 JSON 字段。

**新方案**：新建 `position_close_events` 独立数据库表，与 `positions` 表通过 `position_id` 外键关联。

**变更原因**：

| 维度 | JSON 嵌套方案的问题 | 独立表方案的优势 |
|------|---------------------|-----------------|
| **查询能力** | 无法按 event_type/close_time 独立查询 | 可建索引，支持高效查询 |
| **存储效率** | 每次回测报告整体存储，重复数据多 | 事件独立存储，按需关联 |
| **扩展性** | 新增事件类型需修改整个报告结构 | 新增行即可，表结构不变 |
| **归因追溯** | 需要反序列化整个报告才能分析单次出场 | 可直接 SQL 查询单条事件 |
| **Trailing Stop** | 修改历史无法独立记录 | 独立表天然支持事件日志模式 |
| **回测 vs 实盘** | JSON 格式只适用于回测 | 独立表可同时服务于回测和实盘 |

### 0.2 与订单状态机的关系明确

- **实盘路径**（OrderLifecycleService）：严格状态机 + 审计日志
- **回测路径**（matching_engine）：bypass 状态机（有意为之的性能优化）
- **close_events 表记录的是出场事实**（何时何价出了多少），不是订单状态变更
- 回测 bypass 状态机可接受，但出场事实必须有独立记录

### 0.3 隔离方案（不影响现有回测稳定性）

新逻辑与旧统计完全解耦：
- 现有逻辑一行不改（保持 is_closed 才统计）
- 新逻辑独立追加（只创建 close_event，不影响统计）
- 即使新逻辑有 bug，最坏情况是 close_events 为空，原有统计完全不受影响

---

## 1. 背景

### 1.1 问题描述

当前回测报告中的 `PositionSummary` 只有单一 `exit_price` 和累计 `realized_pnl`，导致部分平仓场景下出现数据矛盾：

- **矛盾现象**：`exit_price < entry_price` 但 `realized_pnl > 0`，看起来矛盾（因为 TP1 盈利 > SL 亏损）
- **归因缺失**：无法区分 TP1/SL 各自盈亏，无法回答"这笔仓位到底赚了多少、亏了多少"
- **路径丢失**：无法还原出场路径和时间序列，无法追溯父子订单关系
- **扩展死胡同**：固定字段方案（tp1_pnl/sl_pnl/tp1_exit_price/sl_exit_price）在加 TP2/TP3 时需要无限加字段

### 1.2 已批准的方案

采用**一对多事件列表（PositionCloseEvent）**，将每次出场记录为独立事件，支持任意级别止盈止损。
**存储方案**：独立数据库表 `position_close_events`，与 `positions` 表通过外键关联。

### 1.3 ADR 文档链接

- [docs/arch/position-summary-close-event-design.md](position-summary-close-event-design.md)

---

## 2. 模型设计

### 2.1 PositionCloseEvent 模型定义

```python
from decimal import Decimal
from typing import Optional
from pydantic import Field
from src.domain.models import FinancialModel


class PositionCloseEvent(FinancialModel):
    """单次出场事件记录

    每次 TP1/TP2/TP3/SL/TRAILING/MANUAL 平仓都会在 position_close_events 表中产生一条记录，
    用于精确归因和时间序列分析。

    设计考量:
    - close_pnl = gross_pnl - fee（与 matching_engine net_pnl 语义一致）
    - event_type 使用字符串（支持未来扩展，不限制枚举）
    - original_sl_price / modified_sl_price 用于追踪 trailing stop 路径
    - close_qty = actual_filled（实际成交量，非请求成交量）
    - 同时覆盖出场事件和 Trailing Stop 修改历史（event_category 区分）
    """
    position_id: str                    # 关联仓位 ID（FK → positions.id）
    order_id: Optional[str] = None      # 关联订单 ID（保留父子关系追溯）
    event_type: str                     # 出场类型：TP1/TP2/TP3/SL/TRAILING/MANUAL
    event_category: str = 'exit'        # 事件分类：exit / sl_modified / tp_modified
    close_price: Optional[Decimal] = None  # 实际成交价（sl_modified 时为 None）
    close_qty: Optional[Decimal] = None    # 平仓数量（sl_modified 时为 None）
    close_pnl: Optional[Decimal] = None    # 该次出场净盈亏（sl_modified 时为 None）
    close_fee: Optional[Decimal] = None    # 手续费（sl_modified 时为 None）
    close_time: int                     # 时间戳（毫秒）
    exit_reason: Optional[str] = None   # 平仓原因描述（如 "止损触发", "止盈1"）
    original_sl_price: Optional[Decimal] = None   # 原始止损价（trailing stop 场景用）
    modified_sl_price: Optional[Decimal] = None   # 修改后止损价（trailing stop 场景用）
```

**字段约束说明**:

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| position_id | str | 必填 | 关联仓位 ID |
| order_id | Optional[str] | 可选 | 关联订单 ID，保留订单级追溯 |
| event_type | str | 必填 | 字符串类型，支持未来扩展 |
| event_category | str | 必填，默认 'exit' | **事件分类**：exit（出场成交）/ sl_modified（止损修改）/ tp_modified（止盈修改） |
| close_price | Optional[Decimal] | 可选 | 实际成交价，**sl_modified 时为 NULL** |
| close_qty | Optional[Decimal] | 可选 | **实际平仓数量**，**sl_modified 时为 NULL** |
| close_pnl | Optional[Decimal] | 可选 | 净盈亏 = gross_pnl - fee，**sl_modified 时为 NULL** |
| close_fee | Optional[Decimal] | 可选 | 手续费，**sl_modified 时为 NULL** |
| close_time | int | 必填 | 毫秒时间戳 |
| exit_reason | Optional[str] | 可选 | 人类可读的平仓原因 |
| original_sl_price | Optional[Decimal] | 可选 | trailing stop 原始止损价 |
| modified_sl_price | Optional[Decimal] | 可选 | trailing stop 修改后止损价 |

**基类约束**:
- 继承 `FinancialModel`（`ConfigDict: arbitrary_types_allowed=True, extra="forbid"`）
- 所有金额使用 `Decimal`
- `extra="forbid"` 意味着不允许额外字段，保证序列化一致性

### 2.2 position_close_events 表 DDL（新增）

```sql
CREATE TABLE IF NOT EXISTS position_close_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id TEXT NOT NULL,
    order_id TEXT,
    event_type TEXT NOT NULL,                 -- TP1/TP2/TP3/TP4/TP5/SL/MANUAL
    event_category TEXT NOT NULL DEFAULT 'exit', -- exit / sl_modified / tp_modified
    close_price TEXT,                         -- NULL 允许（sl_modified 时无成交价）
    close_qty TEXT,                           -- NULL 允许（sl_modified 时无成交量）
    close_pnl TEXT,                           -- NULL 允许（sl_modified 时无盈亏）
    close_fee TEXT,                           -- NULL 允许（sl_modified 时无手续费）
    close_time INTEGER NOT NULL,
    exit_reason TEXT,
    original_sl_price TEXT,
    modified_sl_price TEXT,
    -- 【P0-1 修复】CHECK 约束：exit 事件必须有成交数据
    CHECK (event_category != 'exit' OR (
        close_price IS NOT NULL AND
        close_qty IS NOT NULL AND
        close_pnl IS NOT NULL AND
        close_fee IS NOT NULL
    )),
    FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_close_event_position_id ON position_close_events(position_id);
CREATE INDEX IF NOT EXISTS idx_close_event_type ON position_close_events(event_type);
CREATE INDEX IF NOT EXISTS idx_close_event_time ON position_close_events(close_time);
```

**设计说明**：
- `close_price`/`close_qty`/`close_pnl`/`close_fee` 使用 `TEXT` 类型（存储 Decimal 字符串，避免 SQLite 浮点精度问题）
- **【P0-1 修复】** `close_price`/`close_qty`/`close_pnl`/`close_fee` 改为**允许 NULL**，与 Pydantic `Optional[Decimal] = None` 一致
- 增加 **CHECK 约束**：`event_category='exit'` 时四个字段必须非 NULL，保证数据完整性
- `event_category` 用于区分出场成交（exit）和 Trailing Stop 修改历史（sl_modified）
- `ON DELETE CASCADE` 确保仓位删除时自动清理关联事件
- 三个索引覆盖常见查询模式：按仓位查询、按类型查询、按时间范围查询

### 2.3 PositionSummary 模型变更

在现有 `PositionSummary` 上新增字段：

```python
class PositionSummary(FinancialModel):
    """
    仓位摘要：用于 PMS 回测报告
    """
    position_id: str
    signal_id: str
    symbol: str
    direction: Direction
    entry_price: Decimal
    exit_price: Optional[Decimal] = None  # 平仓价（仅当仓位关闭时）
    entry_time: int              # 开仓时间戳 (ms)
    exit_time: Optional[int] = None  # 平仓时间戳 (ms)
    realized_pnl: Decimal = Field(default=Decimal('0'), description="已实现盈亏")
    exit_reason: Optional[str] = None  # 平仓原因 (TP1/SL/TRAILING)

    # ===== 新增字段 =====
    close_events: List[PositionCloseEvent] = Field(
        default_factory=list,
        description="出场事件列表（一对多，支持任意级别止盈止损）"
    )
```

**变更说明**:
- **仅新增一个字段** `close_events`，不修改任何现有字段
- `default_factory=list` 确保旧数据反序列化时默认为空列表 `[]`
- 保留 `exit_price`/`exit_time`/`realized_pnl`/`exit_reason` 保持向后兼容
- **向后兼容保证**：前端旧版不读取 `close_events` 时行为不变；新版读取旧数据时得到空列表

### 2.4 Order 模型变更（QA 审查修复 P0-4）

在现有 `Order` 模型上新增一个可选字段 `actual_filled`，用于回测场景中记录实际成交量。
同时新增 `close_pnl`/`close_fee` 用于传递出场盈亏数据：

```python
class Order(FinancialModel):
    # ... 现有字段不变 ...

    # 【新增 P0-4】实际成交量（_execute_fill 中写入，不修改 filled_qty 语义）
    actual_filled: Optional[Decimal] = None  # 实际成交量（防超卖保护截断后）

    # 【新增】回测出场盈亏字段（仅平仓单在 _execute_fill 中被填充）
    close_pnl: Optional[Decimal] = None    # 该笔平仓单的净盈亏（gross_pnl - fee）
    close_fee: Optional[Decimal] = None    # 该笔平仓单的手续费
```

**设计理由**（方案 A）：
- **方案 A（采用）**：新增 `order.actual_filled` 字段，不修改 `order.filled_qty` 语义
  - `filled_qty` 保持原有语义（请求成交量/订单级成交量）
  - `actual_filled` 表达"防超卖保护截断后的真实成交量"
  - 对其他模块零影响
- **方案 B（拒绝）**：直接修改 `order.filled_qty = actual_filled`
  - 改变了 `filled_qty` 原有语义，可能影响其他消费方
  - 风险不可控，需要全局审计所有 `filled_qty` 使用处
- 通过在 `Order` 对象上写入 PnL 数据，backtester 可从已执行的 `executed` 订单列表直接读取
- 无需修改 `_execute_fill` 的返回值签名，避免了影响其他潜在调用方的风险
- 语义清晰：`order.close_pnl` 明确表示"该笔订单对应的盈亏"

### 2.5 数据不变量（QA 审查修复 P0-3）

本节声明本设计中的核心数据不变量，用于保证数据一致性。

**不变量 1：close_pnl 汇总 == position.realized_pnl**

```
当仓位完全关闭（is_closed=True）时：
    sum(e.close_pnl for e in close_events where e.event_category='exit') == position.realized_pnl
```

**证明**：
- `position.realized_pnl` 在 `_execute_fill` 中通过 `position.realized_pnl += net_pnl` 累加
- `close_pnl` 直接从同一 `net_pnl` 值写入 `order.close_pnl`（同一个 `_execute_fill` 调用）
- `close_events` 在每次平仓单成交时从 `order.close_pnl` 读取
- 因此两者由**同一计算路径**保证相等

**不变量 2：close_qty 汇总 == 原始开仓数量**

```
当仓位完全关闭（is_closed=True）时：
    sum(e.close_qty for e in close_events where e.event_category='exit') == 原始开仓数量
```

**注意**：`close_qty` 使用 `order.actual_filled`（实际成交量），而非 `order.requested_qty`（请求成交量），因为 `_execute_fill` 中有防超卖保护 `actual_filled = min(order.requested_qty, position.current_qty)`（P0-4 修复）。

**不变量 3：close_fee 汇总 <= position.total_fees_paid**

```
position.total_fees_paid 包含入场费 + 所有出场费
    sum(e.close_fee for e in close_events where e.event_category='exit') <= position.total_fees_paid
```

入场手续费也计入 `position.total_fees_paid`，但不记录在任何 `close_event` 中。

**不变量 4（P0-3 修复）：本期不支持加仓，每个 close_event 的 entry_price 快照一致**

```
本期设计约束：
    - 本期（MVP）仅支持单向开仓 + 分批平仓场景
    - 不支持加仓（add_position）：同一个 position_id 下 entry_price 保持不变
    - 每个 close_event 对应的 entry_price 快照 = position.entry_price（开仓时确定）
    - close_pnl = (close_price - entry_price) * close_qty  # LONG
    - close_pnl = (entry_price - close_price) * close_qty  # SHORT
```

**加仓场景处理策略**：
- 如果后续需要支持加仓，需要引入加权平均成本（WAC）计算，每个 close_event 需要额外记录 `snapshot_entry_price` 字段
- 本期不实现加仓，`PositionSummary.entry_price` 即为该仓位所有 close_event 的统一入场价快照
- 测试时需验证：`close_events` 中所有 exit 事件的 PnL 计算都使用同一个 `position.entry_price`

---

## 3. 数据流设计

### 3.1 完整数据流图（独立表存储）

```
┌──────────────────────────────────────────────────────────────────────┐
│                        K 线驱动回测循环                               │
│  backtester.py: for kline in ohlcv_data                              │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Step 1: 策略信号检测                                                 │
│  backtester.py: 检测策略触发信号，生成 Order                           │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Step 2: 撮合引擎执行订单                                             │
│  matching_engine.match_orders_for_kline(...)                          │
│  → 遍历订单，对触发的订单调用 _execute_fill(order, exec_price, ...)   │
│                                                                      │
│  【关键变更点】_execute_fill 写入 order.close_pnl / order.close_fee:  │
│  - _execute_fill 返回类型不变（仍为 None）                              │
│  - 平仓单处理末尾新增:                                                 │
│      order.close_pnl = net_pnl                                       │
│      order.close_fee = fee_paid                                      │
│                                                                      │
│  PnL 计算逻辑（不变）:                                                  │
│    trade_value = exec_price * order.requested_qty                     │
│    fee_paid = trade_value * self.fee_rate                             │
│    actual_filled = min(order.requested_qty, position.current_qty)     │
│    gross_pnl = (exec_price - entry_price) * actual_filled  # LONG     │
│    net_pnl = gross_pnl - fee_paid                                     │
│    position.realized_pnl += net_pnl                                   │
│    # 【新增】写入订单对象                                               │
│    order.close_pnl = net_pnl                                          │
│    order.close_fee = fee_paid                                         │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       │ match_orders_for_kline 返回 executed Orders
                       │ （每个 executed order 上已写入 close_pnl/close_fee）
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Step 3: backtester 遍历 executed 订单，从 order 对象读取数据          │
│  backtester.py: for order in executed:                                │
│                                                                      │
│  if order.order_role in [TP1, SL]:                                    │
│      # 从 order 对象读取 PnL 数据（不再从返回值获取）                    │
│      pnl = order.close_pnl     # Decimal 或 None                      │
│      fee = order.close_fee     # Decimal 或 None                      │
│                                                                      │
│      if pnl is not None and pnl != 0:                                 │
│          event = PositionCloseEvent(                                  │
│              position_id=position.id,                                 │
│              order_id=order.id,                                       │
│              event_type=order.order_role.value,                       │
│              close_price=order.average_exec_price,                    │
│              close_qty=order.actual_filled,  # = actual_filled（P0-4 修复）│
│              close_pnl=order.close_pnl,  # 从 order 对象读取           │
│              close_fee=order.close_fee,  # 从 order 对象读取           │
│              close_time=kline.timestamp,                              │
│              exit_reason=order.exit_reason or order.order_role.value  │
│          )                                                            │
│          summary.close_events.append(event)                           │
│                                                                      │
│      # 【重要】完全平仓时才更新累计统计（修复 P0-4 重复计算问题）        │
│      if position.is_closed:                                           │
│          summary.exit_price = order.average_exec_price                │
│          summary.exit_time = kline.timestamp                          │
│          summary.realized_pnl = position.realized_pnl                 │
│          summary.exit_reason = order.exit_reason or order.order_role.value│
│          # 交易统计更新（仅完全平仓时）                                  │
│          total_trades += 1                                            │
│          if position.realized_pnl > 0:                                │
│              winning_trades += 1                                      │
│          else:                                                        │
│              losing_trades += 1                                       │
│          total_pnl += position.realized_pnl                           │
│          total_fees_paid += position.total_fees_paid                  │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Step 4: 写入独立表 position_close_events                              │
│  backtest_repository.create_close_events(events)                      │
│                                                                      │
│  INSERT INTO position_close_events                                    │
│      (position_id, order_id, event_type, event_category,              │
│       close_price, close_qty, close_pnl, close_fee,                   │
│       close_time, exit_reason, original_sl_price, modified_sl_price)  │
│  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)  -- 【P0-2 修复】全参数化，event_category 不再硬编码                     │
│                                                                      │
│  【隔离方案】此步骤为追加逻辑，不修改任何现有统计逻辑                    │
│  即使此步骤失败，Step 3 中的统计逻辑仍然正确执行                        │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Step 5: 查询时 JOIN 读取事件                                         │
│  backtest_repository.get_close_events_for_position(position_id)       │
│                                                                      │
│  SELECT * FROM position_close_events                                  │
│  WHERE position_id = ?                                                │
│  ORDER BY close_time ASC                                              │
│                                                                      │
│  返回 List[PositionCloseEvent]，填充到 PositionSummary.close_events   │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Step 6: 前端渲染                                                     │
│  BacktestReportDetailModal.tsx                                        │
│                                                                      │
│  - 仓位历史表格：对有多条 close_events 的仓位展开为子行                  │
│  - 子行展示：出场时间、类型、成交价、数量、盈亏、手续费                   │
│  - 向后兼容：旧数据无 close_events 时保持原单行展示                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 关键问题解答

**Q: 为什么不在 _execute_fill 中直接返回 tuple，而是写入 Order 对象？**

**A**: 三种方案对比：

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| A. `match_orders_for_kline` 返回聚合 tuple | 一次返回所有结果 | 改动大，需要修改公开 API 签名 | 低 |
| B. `_execute_fill` 返回 tuple | 纯函数式，无副作用 | 修改私有方法返回值影响所有调用方；backtester 无法直接调用 `_execute_fill`（它是 `match_orders_for_kline` 的内部方法） | 低 |
| **C. 写入 Order 对象字段**（采用） | **改动最小，不影响返回值签名；语义清晰** | 需要给 Order 模型新增字段 | **高** |

方案 C 是最佳选择，因为：
- `_execute_fill` 是 `match_orders_for_kline` 的内部方法，backtester 调用的是 `match_orders_for_kline`
- 方案 B 要求 backtester 能直接捕获 `_execute_fill` 返回值，但这与实际调用关系不符
- 方案 C 通过 Order 对象传递数据，backtester 从 `executed` 订单列表直接读取，与实际代码结构一致

**Q: partical fill 场景下 close_qty 用什么值？**

**A**: 使用 `order.actual_filled`（`_execute_fill` 中的 `min(order.requested_qty, position.current_qty)`），而非 `order.requested_qty`。实现方式：`_execute_fill` 中将 `order.actual_filled` 设为 `actual_filled` 的值（详见 4.2 节）。`order.filled_qty` 保持不变（P0-4 修复）。

**Q: 独立表方案下，如何保证与旧回测报告的兼容？**

**A**: 
- 旧回测报告仍在 `backtest_reports` 表中，无 `position_close_events` 记录
- 查询时如果独立表中无数据，返回空列表 `[]`
- `PositionSummary.close_events` 的 `default_factory=list` 保证旧数据反序列化时默认为空列表
- 新逻辑（写 close_events）与旧统计（is_closed 才统计）完全解耦，互不影响

**Q: close_events 表记录的是订单状态还是出场事实？**

**A**: close_events 表记录的是**出场事实**（何时何价出了多少），不是订单状态变更。
- 实盘路径（OrderLifecycleService）有严格状态机 + 审计日志
- 回测路径（matching_engine）bypass 状态机是有意为之的性能优化
- 即使回测 bypass 状态机，出场事实必须有独立记录，这就是 close_events 表的职责

---

## 4. 关键代码变更说明

### 4.1 src/domain/models.py

**文件位置**: `/Users/jiangwei/Documents/dingdingbot/src/domain/models.py`

**变更内容**:

1. **新增 PositionCloseEvent 类**（在 `PositionSummary` 定义之前，约 line 1235 之前）

```python
class PositionCloseEvent(FinancialModel):
    """单次出场事件记录

    每次 TP1/TP2/TP3/SL/TRAILING/MANUAL 平仓都会在 position_close_events 表中产生一条记录，
    用于精确归因和时间序列分析。
    """
    position_id: str                    # 关联仓位 ID
    order_id: Optional[str] = None      # 关联订单 ID
    event_type: str                     # TP1/TP2/TP3/SL/TRAILING/MANUAL
    event_category: str = 'exit'        # exit / sl_modified / tp_modified
    close_price: Optional[Decimal] = None  # 实际成交价（sl_modified 时为 None）
    close_qty: Optional[Decimal] = None    # 平仓数量（sl_modified 时为 None）
    close_pnl: Optional[Decimal] = None    # 该次出场净盈亏（sl_modified 时为 None）
    close_fee: Optional[Decimal] = None    # 手续费（sl_modified 时为 None）
    close_time: int                     # 时间戳（毫秒）
    exit_reason: Optional[str] = None   # 平仓原因描述
    original_sl_price: Optional[Decimal] = None
    modified_sl_price: Optional[Decimal] = None
```

2. **PositionSummary 新增字段**（约 line 1249 之后）

```python
class PositionSummary(FinancialModel):
    # ... 现有字段不变 ...

    close_events: List[PositionCloseEvent] = Field(
        default_factory=list,
        description="出场事件列表（一对多，支持任意级别止盈止损）"
    )
```

3. **Order 新增字段**（约 line 994 之后，`filled_at` 字段之后）

```python
class Order(FinancialModel):
    # ... 现有字段不变 ...

    # 【新增 P0-4】实际成交量（_execute_fill 中写入，不修改 filled_qty 语义）
    actual_filled: Optional[Decimal] = None  # 实际成交量（防超卖保护截断后）

    # 【新增】回测出场盈亏字段（仅平仓单在 _execute_fill 中被填充）
    close_pnl: Optional[Decimal] = None    # 该笔平仓单的净盈亏
    close_fee: Optional[Decimal] = None    # 该笔平仓单的手续费
```

**import 变更**: 无需新增 import（`List`, `Optional`, `Decimal`, `Field`, `FinancialModel` 已存在）

### 4.2 src/domain/matching_engine.py

**文件位置**: `/Users/jiangwei/Documents/dingdingbot/src/domain/matching_engine.py`

**变更内容**: `_execute_fill` 方法写入 PnL 数据到 Order 对象

**当前签名**（不变）:
```python
def _execute_fill(
    self,
    order: Order,
    exec_price: Decimal,
    position: Optional[Position],
    account: Account,
    positions_map: Dict[str, Position],
    timestamp: int,
) -> None:
```

**注意**：返回签名**不变**（仍为 `None`），避免影响其他调用方。

**关键变更点**：在平仓单处理逻辑中写入 PnL 到 order 对象

```python
elif order.order_role in [OrderRole.TP1, OrderRole.SL]:
    # ===== 平仓单：平仓逻辑 =====
    if position is None:
        # 理论上不应该发生，但做防御性处理
        return

    # 防超卖保护：截断成交数量
    actual_filled = min(order.requested_qty, position.current_qty)

    # 更新仓位数量
    position.current_qty -= actual_filled

    # 【关键修复 P0-4】将 actual_filled 写入 order.actual_filled（不修改 filled_qty 语义）
    # 这样 backtester 从 order.actual_filled 读取的就是真实成交量
    order.actual_filled = actual_filled

    # 计算盈亏
    if position.direction == Direction.LONG:
        gross_pnl = (exec_price - position.entry_price) * actual_filled
    else:
        gross_pnl = (position.entry_price - exec_price) * actual_filled

    net_pnl = gross_pnl - fee_paid

    # 更新 Position
    position.realized_pnl += net_pnl
    position.total_fees_paid += fee_paid

    # 【新增 P0-1】写入 PnL 到 order 对象，供 backtester 读取
    order.close_pnl = net_pnl
    order.close_fee = fee_paid

    # 检查是否完全平仓
    if position.current_qty <= Decimal('0'):
        position.is_closed = True

    # 盈亏计入账户
    account.total_balance += net_pnl
```

**入场单处理不变**：入场单不设置 `order.close_pnl`/`order.close_fee`（保持 `None`），因为入场单不是出场动作。

### 4.3 src/application/backtester.py

**文件位置**: `/Users/jiangwei/Documents/dingdingbot/src/application/backtester.py`

**变更内容**: 出场事件记录逻辑重构

**当前逻辑**（line 1438-1449）:
```python
elif order.order_role in [OrderRole.TP1, OrderRole.SL]:
    position = positions_map.get(order.signal_id)
    if position and position.is_closed:
        for summary in position_summaries:
            if summary.position_id == position.id:
                summary.exit_price = order.average_exec_price
                summary.exit_time = kline.timestamp
                summary.realized_pnl = position.realized_pnl
                summary.exit_reason = order.exit_reason or order.order_role.value
                break
```

**新逻辑**:
```python
elif order.order_role in [OrderRole.TP1, OrderRole.SL]:
    position = positions_map.get(order.signal_id)
    if position:
        # 找到对应的 PositionSummary
        for summary in position_summaries:
            if summary.position_id == position.id:
                # 【新增 P0-4】立即创建出场事件，从 order 对象读取 PnL 数据
                # 【P1-1 修复】防御性检查：actual_filled 必须 > 0
                if order.close_pnl is not None and order.actual_filled is not None:
                    if order.actual_filled <= Decimal('0'):
                        continue  # P1-1：跳过无效成交（零数量不应创建事件）

                    event = PositionCloseEvent(
                        position_id=position.id,
                        order_id=order.id,
                        event_type=order.order_role.value,  # "TP1" / "SL"
                        event_category='exit',
                        close_price=order.average_exec_price,
                        close_qty=order.actual_filled,       # = actual_filled（由 _execute_fill 写入，P0-4 修复）
                        close_pnl=order.close_pnl,           # 从 order 对象读取
                        close_fee=order.close_fee,           # 从 order 对象读取
                        close_time=kline.timestamp,
                        exit_reason=order.exit_reason or order.order_role.value,
                    )
                    summary.close_events.append(event)

                # 【保留 P0-4】向后兼容的累计值更新（仅在完全平仓时）
                # 交易统计（total_pnl/winning_trades/losing_trades）也仅在此分支更新
                if position.is_closed:
                    summary.exit_price = order.average_exec_price
                    summary.exit_time = kline.timestamp
                    summary.realized_pnl = position.realized_pnl
                    summary.exit_reason = order.exit_reason or order.order_role.value

                    # 【P0-4 修复】交易统计仅在此处更新，避免重复计算
                    total_trades += 1
                    if position.realized_pnl > 0:
                        winning_trades += 1
                    else:
                        losing_trades += 1
                    total_pnl += position.realized_pnl
                    total_fees_paid += position.total_fees_paid
                break
```

**关键变更点**:

1. **条件判断变化**：从 `if position and position.is_closed` 改为 `if position`
   - 原因：部分平仓时也要创建出场事件，不能等 `is_closed`

2. **事件创建**：每次 TP1/SL 成交时立即创建 `PositionCloseEvent`

3. **数据来源（P0-4 修复）**：
   - `close_pnl` 和 `close_fee` 从 `order.close_pnl`/`order.close_fee` 读取
   - `close_qty` 使用 `order.actual_filled`（`_execute_fill` 中写入，P0-4 修复，不修改 `filled_qty` 语义）
   - **【P1-1 修复】** 增加防御检查：`actual_filled <= 0` 时跳过事件创建
   - 其他字段从 `order` 和 `position` 对象获取

4. **统计逻辑（P0-4 修复）**：
   - **部分平仓时**：仅创建 `close_event`，**不更新** `total_pnl`/`winning_trades`/`losing_trades`
   - **完全平仓时**（`is_closed=True`）：更新 `summary.realized_pnl` + 交易统计
   - 这确保 `total_pnl` 不会被重复累加

### 4.4 src/infrastructure/backtest_repository.py

**文件位置**: `/Users/jiangwei/Documents/dingdingbot/src/infrastructure/backtest_repository.py`

**变更 0（P1-6 修复）**: 仓库初始化时启用 SQLite 外键约束

```python
class BacktestRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row

        # 【P1-6 修复】启用 SQLite 外键约束
        # SQLite 默认不启用外键检查，必须显式开启才能保证数据完整性
        self.db.execute("PRAGMA foreign_keys = ON")

        # 验证外键已启用
        result = self.db.execute("PRAGMA foreign_keys").fetchone()
        if result[0] != 1:
            raise RuntimeError("SQLite foreign_keys PRAGMA failed to enable")
```

**说明**：
- SQLite 默认 `foreign_keys = OFF`，`ON DELETE CASCADE` 不会生效
- 必须在每次连接时执行 `PRAGMA foreign_keys = ON`
- 增加验证检查确保 PRAGMA 生效成功

**变更 1**: 新增 `create_close_event` 方法（独立表写入）

```python
def create_close_event(self, event: PositionCloseEvent) -> int:
    """创建出场事件记录到独立表 position_close_events

    Args:
        event: PositionCloseEvent 对象

    Returns:
        新插入记录的 id
    """
    query = """
        INSERT INTO position_close_events
            (position_id, order_id, event_type, event_category,
             close_price, close_qty, close_pnl, close_fee,
             close_time, exit_reason, original_sl_price, modified_sl_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        event.position_id,
        event.order_id,
        event.event_type,
        event.event_category,
        self._decimal_to_str(event.close_price) if event.close_price else None,
        self._decimal_to_str(event.close_qty) if event.close_qty else None,
        self._decimal_to_str(event.close_pnl) if event.close_pnl else None,
        self._decimal_to_str(event.close_fee) if event.close_fee else None,
        event.close_time,
        event.exit_reason,
        self._decimal_to_str(event.original_sl_price) if event.original_sl_price else None,
        self._decimal_to_str(event.modified_sl_price) if event.modified_sl_price else None,
    )
    cursor = self.db.execute(query, params)
    return cursor.lastrowid
```

**变更 2**: 新增 `get_close_events_for_position` 方法（独立表查询）

```python
def get_close_events_for_position(self, position_id: str) -> List[PositionCloseEvent]:
    """查询指定仓位的所有出场事件

    Args:
        position_id: 仓位 ID

    Returns:
        按时间升序排列的出场事件列表
    """
    query = """
        SELECT * FROM position_close_events
        WHERE position_id = ?
        ORDER BY close_time ASC
    """
    cursor = self.db.execute(query, (position_id,))
    rows = cursor.fetchall()

    events = []
    for row in rows:
        events.append(PositionCloseEvent(
            position_id=row['position_id'],
            order_id=row['order_id'],
            event_type=row['event_type'],
            event_category=row['event_category'],
            close_price=self._str_to_decimal(row['close_price']),
            close_qty=self._str_to_decimal(row['close_qty']),
            close_pnl=self._str_to_decimal(row['close_pnl']),
            close_fee=self._str_to_decimal(row['close_fee']),
            close_time=row['close_time'],
            exit_reason=row['exit_reason'],
            original_sl_price=self._str_to_decimal(row['original_sl_price']),
            modified_sl_price=self._str_to_decimal(row['modified_sl_price']),
        ))
    return events
```

**变更 3**: 新增 `create_close_events_batch` 方法（批量写入）

```python
def create_close_events_batch(self, events: List[PositionCloseEvent]) -> None:
    """批量创建出场事件记录

    使用事务保证原子性。

    Args:
        events: PositionCloseEvent 对象列表
    """
    query = """
        INSERT INTO position_close_events
            (position_id, order_id, event_type, event_category,
             close_price, close_qty, close_pnl, close_fee,
             close_time, exit_reason, original_sl_price, modified_sl_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params_list = []
    for event in events:
        params_list.append((
            event.position_id,
            event.order_id,
            event.event_type,
            event.event_category,
            self._decimal_to_str(event.close_price) if event.close_price else None,
            self._decimal_to_str(event.close_qty) if event.close_qty else None,
            self._decimal_to_str(event.close_pnl) if event.close_pnl else None,
            self._decimal_to_str(event.close_fee) if event.close_fee else None,
            event.close_time,
            event.exit_reason,
            self._decimal_to_str(event.original_sl_price) if event.original_sl_price else None,
            self._decimal_to_str(event.modified_sl_price) if event.modified_sl_price else None,
        ))
    self.db.executemany(query, params_list)
```

### 4.5 web-front/src/lib/api.ts

**文件位置**: `/Users/jiangwei/Documents/dingdingbot/web-front/src/lib/api.ts`

**变更 1**: 新增 `PositionCloseEvent` 接口（在 `PositionSummary` 之前，约 line 506）

```typescript
/**
 * 单次出场事件记录
 * 对应后端 src/domain/models.py: PositionCloseEvent
 */
export interface PositionCloseEvent {
  /** 关联仓位 ID */
  position_id: string;
  /** 关联订单 ID */
  order_id: string | null;
  /** 出场类型：TP1/TP2/TP3/SL/TRAILING/MANUAL */
  event_type: string;
  /** 事件分类：exit / sl_modified / tp_modified */
  event_category: string;
  /** 实际成交价 (Decimal string, sl_modified 时为 null) */
  close_price: string | null;
  /** 平仓数量 (Decimal string, sl_modified 时为 null) */
  close_qty: string | null;
  /** 该次出场净盈亏 (Decimal string, sl_modified 时为 null) */
  close_pnl: string | null;
  /** 手续费 (Decimal string, sl_modified 时为 null) */
  close_fee: string | null;
  /** 时间戳 (ms) */
  close_time: number;
  /** 平仓原因描述 */
  exit_reason: string | null;
  /** 原始止损价 (Decimal string, trailing stop 场景用) */
  original_sl_price: string | null;
  /** 修改后止损价 (Decimal string, trailing stop 场景用) */
  modified_sl_price: string | null;
}
```

**变更 2**: `PositionSummary` 接口新增字段（约 line 527 之后）

```typescript
export interface PositionSummary {
  // ... 现有字段 ...
  exit_reason: string | null;

  /** 出场事件列表（一对多，支持任意级别止盈止损） */
  close_events: PositionCloseEvent[];
}
```

### 4.6 web-front/src/components/v3/backtest/BacktestReportDetailModal.tsx

**文件位置**: `/Users/jiangwei/Documents/dingdingbot/web-front/src/components/v3/backtest/BacktestReportDetailModal.tsx`

**变更内容**: 仓位历史表格改造

**设计目标**:
- 对有多个 `close_events` 的仓位，展开为子行展示
- 对无 `close_events` 的旧数据（空列表），保持原单行展示
- 子行展示：出场时间、类型、成交价、数量、盈亏、手续费

**表格结构示意**:

```
┌─────────────────────────────────────────────────────────────────────┐
│ 仓位历史                                                             │
├──────┬──────┬───────┬───────┬────────┬────────┬────────────────────┤
│ 交易对│ 方向 │ 入场价│ 出场价│ 已实现  │ 出场数 │ 操作               │
│      │      │       │       │ 盈亏    │        │                    │
├──────┼──────┼───────┼───────┼────────┼────────┼────────────────────┤
│ BTC/  │ LONG │ 50000 │ 51000 │ +150.00│ 2 次   │ [展开 ▼]           │
│ USDT  │      │       │       │        │        │                    │
│ ┌─────────────────────────────────────────────────────────────────┐│
│ │ 出场明细:                                                        ││
│ │ ┌────────┬──────┬────────┬────────┬────────┬────────┐          ││
│ │ │ 时间    │ 类型 │ 成交价  │ 数量    │ 盈亏    │ 手续费  │          ││
│ │ ├────────┼──────┼────────┼────────┼────────┼────────┤          ││
│ │ │ 04-01  │ TP1  │ 50800  │ 0.5 BTC│ +200.00│ 12.70  │          ││
│ │ │ 04-05  │ SL   │ 49500  │ 0.5 BTC│ -50.00 │ 12.38  │          ││
│ │ └────────┴──────┴────────┴────────┴────────┴────────┘          ││
│ └─────────────────────────────────────────────────────────────────┘│
├──────┼──────┼───────┼───────┼────────┼────────┼────────────────────┤
│ ETH/  │ SHORT│ 3000  │ 2900  │ +95.00 │ 1 次   │ [展开 ▼]           │
│ USDT  │      │       │       │        │        │                    │
│ ┌─────────────────────────────────────────────────────────────────┐│
│ │ 出场明细:                                                        ││
│ │ ┌────────┬──────┬────────┬────────┬────────┬────────┐          ││
│ │ │ 时间    │ 类型 │ 成交价  │ 数量    │ 盈亏    │ 手续费  │          ││
│ │ ├────────┼──────┼────────┼────────┼────────┼────────┤          ││
│ │ │ 04-03  │ TP1  │ 2900   │ 1.0 ETH│ +95.60 │ 14.64  │          ││
│ │ └────────┴──────┴────────┴────────┴────────┴────────┘          ││
│ └─────────────────────────────────────────────────────────────────┘│
└──────┴──────┴───────┴───────┴────────┴────────┴────────────────────┘
```

**伪代码实现**:

```tsx
import { useState } from 'react';
import { PositionSummary, PositionCloseEvent } from '@/lib/api';

function PositionHistoryTable({ positions }: { positions: PositionSummary[] }) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const toggleExpand = (positionId: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(positionId)) {
        next.delete(positionId);
      } else {
        next.add(positionId);
      }
      return next;
    });
  };

  return (
    <table>
      <thead>
        <tr>
          <th>交易对</th>
          <th>方向</th>
          <th>入场价</th>
          <th>出场价</th>
          <th>已实现盈亏</th>
          <th>出场次数</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((pos) => (
          <PositionRow
            key={pos.position_id}
            position={pos}
            isExpanded={expandedIds.has(pos.position_id)}
            onToggle={() => toggleExpand(pos.position_id)}
          />
        ))}
      </tbody>
    </table>
  );
}

function PositionRow({ position, isExpanded, onToggle }: {
  position: PositionSummary;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const hasEvents = position.close_events && position.close_events.length > 0;

  return (
    <>
      {/* 主行 */}
      <tr>
        <td>{position.symbol}</td>
        <td>{position.direction === 'LONG' ? '做多' : '做空'}</td>
        <td>{formatDecimal(position.entry_price)}</td>
        <td>{position.exit_price ? formatDecimal(position.exit_price) : '-'}</td>
        <td className={isPositive(position.realized_pnl) ? 'text-green' : 'text-red'}>
          {formatDecimal(position.realized_pnl)}
        </td>
        <td>{hasEvents ? position.close_events.length : '-'}</td>
        <td>
          {hasEvents && (
            <button onClick={onToggle}>
              {isExpanded ? '收起' : '展开'}
            </button>
          )}
        </td>
      </tr>

      {/* 子行：出场事件明细 */}
      {isExpanded && hasEvents && (
        <tr>
          <td colSpan={7}>
            <div className="event-detail-panel">
              <h4>出场明细</h4>
              <table>
                <thead>
                  <tr>
                    <th>出场时间</th>
                    <th>类型</th>
                    <th>成交价</th>
                    <th>数量</th>
                    <th>盈亏</th>
                    <th>手续费</th>
                  </tr>
                </thead>
                <tbody>
                  {/* P1-4 修复：使用 order_id 作为 key 而非数组索引 */}
                  {position.close_events.map((event) => (
                    <EventRow key={event.order_id} event={event} />
                  ))}
                </tbody>
              </table>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function EventRow({ event }: { event: PositionCloseEvent }) {
  return (
    <tr>
      <td>{formatTimestamp(event.close_time)}</td>
      <td>
        <EventTypeBadge type={event.event_type} />
      </td>
      <td>{formatDecimal(event.close_price)}</td>
      <td>{formatDecimal(event.close_qty)}</td>
      <td className={isPositive(event.close_pnl) ? 'text-green' : 'text-red'}>
        {formatDecimal(event.close_pnl)}
      </td>
      <td>{formatDecimal(event.close_fee)}</td>
    </tr>
  );
}

// 辅助组件：事件类型标签
function EventTypeBadge({ type }: { type: string }) {
  const colorMap: Record<string, string> = {
    TP1: 'bg-green', TP2: 'bg-green', TP3: 'bg-green',
    SL: 'bg-red',
    TRAILING: 'bg-yellow',
    MANUAL: 'bg-gray',
  };
  return <span className={`badge ${colorMap[type] || 'bg-gray'}`}>{type}</span>;
}
```

**向后兼容**：
- `hasEvents = position.close_events && position.close_events.length > 0`
- 旧数据 `close_events = []` 时，不显示展开按钮，保持原单行展示

---

## 5. 序列化/反序列化（独立表存储）

### 5.1 序列化：PositionSummary → 回测报告 JSON + 独立表 INSERT

**序列化流程**：

```python
def serialize_backtest_report(self, report: BacktestReport) -> int:
    """序列化回测报告

    分为三步：
    1. PositionSummary 序列化到 backtest_reports 表（close_events 序列化为 JSON 数组）
    2. 收集所有 close_events 到 all_close_events 列表（P1-5 修复）
    3. 批量写入独立表 position_close_events（双写，以 JSON 数据为准）

    Returns:
        报告 ID
    """
    # Step 1: 序列化 PositionSummary 到 backtest_reports 表
    positions_json = self._serialize_positions_summary(report.positions)
    cursor = self.db.execute(
        "INSERT INTO backtest_reports (..., position_summaries) VALUES (..., ?)",
        (positions_json, ...)
    )
    report_id = cursor.lastrowid

    # Step 2: 【P1-5 修复】收集所有 close_events 到 all_close_events 列表
    all_close_events: List[PositionCloseEvent] = []  # 初始化收集列表
    for pos in report.positions:
        for event in pos.close_events:
            all_close_events.append(event)  # 逐条追加

    # Step 3: 批量写入独立表（双写）
    # 【P1-4 修复】双写一致性降级策略：以 JSON 数据为准
    # 如果独立表写入失败，不抛出异常，保证 JSON 数据完整性
    # 读取时优先使用 JSON 数据，独立表作为补充查询
    if all_close_events:
        try:
            self.create_close_events_batch(all_close_events)
        except Exception:
            # P1-4：独立表写入失败时记录警告，不影响主流程
            # 降级策略：以 backtest_reports 表中的 JSON 数据为准
            logger.warning(
                f"position_close_events batch write failed for report_id={report_id}, "
                "falling back to JSON data as source of truth"
            )

    return report_id
```

**PositionSummary JSON 序列化**（与旧版兼容）：

```python
def _serialize_positions_summary(self, positions: List[PositionSummary]) -> str:
    data = []
    for pos in positions:
        pos_dict = {
            "position_id": pos.position_id,
            "signal_id": pos.signal_id,
            "symbol": pos.symbol,
            "direction": pos.direction.value,
            "entry_price": self._decimal_to_str(pos.entry_price),
            "exit_price": self._decimal_to_str(pos.exit_price) if pos.exit_price else None,
            "entry_time": pos.entry_time,
            "exit_time": pos.exit_time,
            "realized_pnl": self._decimal_to_str(pos.realized_pnl),
            "exit_reason": pos.exit_reason,
            # 【新增】close_events 嵌套列表（JSON 中保留，用于向前端返回完整数据）
            "close_events": [
                {
                    "position_id": e.position_id,
                    "order_id": e.order_id,
                    "event_type": e.event_type,
                    "event_category": e.event_category,
                    "close_price": self._decimal_to_str(e.close_price) if e.close_price else None,
                    "close_qty": self._decimal_to_str(e.close_qty) if e.close_qty else None,
                    "close_pnl": self._decimal_to_str(e.close_pnl) if e.close_pnl else None,
                    "close_fee": self._decimal_to_str(e.close_fee) if e.close_fee else None,
                    "close_time": e.close_time,
                    "exit_reason": e.exit_reason,
                    "original_sl_price": self._decimal_to_str(e.original_sl_price) if e.original_sl_price else None,
                    "modified_sl_price": self._decimal_to_str(e.modified_sl_price) if e.modified_sl_price else None,
                }
                for e in pos.close_events
            ],
        }
        data.append(pos_dict)
    return json.dumps(data, ensure_ascii=False)
```

### 5.2 反序列化：回测报告 JSON + 独立表 SELECT → PositionSummary

**反序列化流程**：

```python
def deserialize_backtest_report(self, report_id: int) -> BacktestReport:
    """反序列化回测报告

    分为三步：
    1. 从 backtest_reports 表读取 PositionSummary JSON（以 JSON 数据为准，P1-4 修复）
    2. 从独立表 position_close_events 读取出场事件（补充查询）
    3. 如果 JSON 中无 close_events 但独立表中有数据，以独立表补充
    """
    # Step 1: 读取报告
    cursor = self.db.execute(
        "SELECT * FROM backtest_reports WHERE id = ?", (report_id,)
    )
    row = cursor.fetchone()

    # Step 2: 反序列化 PositionSummary（从 JSON 读取，作为 SSOT）
    positions = self._deserialize_positions_summary(row['position_summaries'])

    # Step 3: 【P1-4 修复】从独立表补充 close_events（JSON 数据优先）
    for pos in positions:
        if not pos.close_events:
            # JSON 中无 close_events 时，从独立表补充
            events = self.get_close_events_for_position(pos.position_id)
            if events:
                pos.close_events = events

    return BacktestReport(...)
```

**PositionSummary JSON 反序列化**（向后兼容）：

```python
def _deserialize_positions_summary(self, json_str: Optional[str]) -> List[PositionSummary]:
    if not json_str:
        return []

    data = json.loads(json_str)
    positions = []
    for item in data:
        # 【新增】反序列化 close_events（从 JSON 中读取，作为 fallback）
        close_events = []
        for event_data in item.get("close_events", []):
            close_events.append(PositionCloseEvent(
                position_id=event_data["position_id"],
                order_id=event_data.get("order_id"),
                event_type=event_data["event_type"],
                event_category=event_data.get("event_category", 'exit'),
                close_price=self._str_to_decimal(event_data.get("close_price")),
                close_qty=self._str_to_decimal(event_data.get("close_qty")),
                close_pnl=self._str_to_decimal(event_data.get("close_pnl")),
                close_fee=self._str_to_decimal(event_data.get("close_fee")),
                close_time=event_data["close_time"],
                exit_reason=event_data.get("exit_reason"),
                original_sl_price=self._str_to_decimal(event_data.get("original_sl_price")),
                modified_sl_price=self._str_to_decimal(event_data.get("modified_sl_price")),
            ))

        positions.append(PositionSummary(
            position_id=item["position_id"],
            signal_id=item["signal_id"],
            symbol=item["symbol"],
            direction=Direction(item["direction"]),
            entry_price=self._str_to_decimal(item["entry_price"]),
            exit_price=self._str_to_decimal(item.get("exit_price")),
            entry_time=item["entry_time"],
            exit_time=item.get("exit_time"),
            realized_pnl=self._str_to_decimal(item["realized_pnl"]),
            exit_reason=item.get("exit_reason"),
            close_events=close_events,  # 【新增】
        ))
    return positions
```

**向后兼容保证**:
- `item.get("close_events", [])` 对旧数据（无此字段）默认返回空列表
- 旧回测报告反序列化后 `close_events = []`，前端展示不受影响
- 对 `original_sl_price`/`modified_sl_price`/`exit_reason` 使用 `.get()` 而非 `[]`，对旧数据兼容（P1-5 修复）
- **【P1-4 修复】** 以 JSON 数据为 SSOT，独立表作为补充查询：JSON 中有数据时直接使用，JSON 中无数据时从独立表补充

---

## 6. 设计理念对齐

本节说明 `position_close_events` 独立表如何补齐系统设计理念中的两个短板。

### 6.1 理念 2：Position 日志快照分离

**原有设计理念**：Position 是状态快照，记录当前仓位的最新状态（数量、方向、入场价等）。

**短板**：出场路径信息（何时何价出了多少）没有独立的日志层承载，只能依附于 Position 的单一字段（`exit_price`/`exit_time`/`exit_reason`），无法表达多段出场路径。

**补齐方案**：
- **Position 表** = 状态快照（保留现有逻辑不变）
- **position_close_events 表** = 日志层（记录每次出场事实）
- 两者通过 `position_id` 外键关联，Position 是"是什么"，close_events 是"发生了什么"

### 6.2 理念 3：归因友好

**原有设计理念**：每笔交易/事件必须有价格/数量/PnL/手续费/原因，可追溯。

**短板**：原有 `PositionSummary` 只有累计 `realized_pnl` 和单一 `exit_price`，无法回答"这笔仓位 TP1 赚了多少、SL 亏了多少"。

**补齐方案**：
- 每次出场（TP1/TP2/TP3/SL/MANUAL）都有独立的 `close_price`/`close_qty`/`close_pnl`/`close_fee`/`exit_reason`
- Trailing Stop 修改历史也可通过 `event_category='sl_modified'` 记录，保留 `original_sl_price`/`modified_sl_price`
- 归因分析可通过简单 SQL 完成：
  ```sql
  SELECT event_type, SUM(close_pnl) as total_pnl
  FROM position_close_events
  WHERE position_id = ?
  GROUP BY event_type
  ```

### 6.3 分批动态止盈覆盖

`position_close_events` 表同时覆盖两类场景：

| 场景 | event_category | close_price/qty/pnl/fee | 说明 |
|------|----------------|------------------------|------|
| **出场事件记录** | `exit` | 有值 | TP1/TP2/TP3/TP4/TP5/SL/MANUAL 成交记录 |
| **Trailing Stop 修改历史** | `sl_modified` | NULL | 记录止损价格变化路径，close_price/qty/pnl/fee 为 NULL |

这种设计使得一张表同时服务于出场成交日志和 Trailing Stop 变更日志两个用途，避免了多表冗余。

---

## 7. 边界情况处理

| 场景 | close_events 表现 | 说明 |
|------|------------------|------|
| 直接 SL 全平 | 仅 1 条 SL 事件 | 最简场景 |
| TP1 部分平 + SL 平剩余 | 2 条：TP1 + SL | 典型场景 |
| TP1 100% 全平 | 仅 1 条 TP1 事件 | TP1 比例 = 100% |
| TP1 部分平 + TP2 部分平 + SL 平剩余 | 3 条：TP1 + TP2 + SL | 多级别止盈场景 |
| 仓位未平仓 | 空列表 `[]` | 回测期间未出场 |
| 同一根 K 线多事件 | 时间戳相同，按撮合顺序排列 | 极端场景（如 TP1 和 SL 同根 K 线触发） |
| trailing stop 修改 SL | **产生 sl_modified 记录**（event_category='sl_modified'），close_price/close_pnl 为 NULL | 详见下方说明 |
| 手动平仓 | event_type = "MANUAL" | 回测中暂无此场景，预留 |
| 旧回测报告 | 反序列化默认空列表 `[]` | 向后兼容保证 |
| **SL 触发后 TP 被撤销** | **仅记录 SL 事件，被撤销的 TP 不产生 close_event** | 详见下方说明 |

### 7.1 SL 触发后 TP 被撤销场景说明（P0-2 修复）

在 `matching_engine.match_orders_for_kline` 中，当 SL 触发后会调用 `_cancel_related_orders` 撤销该 signal_id 的所有 OPEN 订单（包括 TP1）。

**处理策略**：
1. **SL 触发在同一根 K 线内**：SL 订单被成交（产生 1 条 close_event），TP1 订单被撤销（状态变为 CANCELED）。被撤销的 TP1 **不会进入** `executed` 列表，因此**不会产生 close_event**。这是正确的行为，因为 TP1 并未成交。
2. **TP1 已在之前 K 线成交，SL 在当前 K 线触发**：TP1 的 close_event 已在之前的 K 线中正确记录，SL 在当前 K 线触发时产生第 2 条 close_event。不受影响。
3. **TP1 和 SL 在同一根 K 线内，但 TP1 先成交**：由于撮合引擎按优先级排序（SL > TP），SL 会先于 TP1 判定。如果 SL 触发，则 TP1 被撤销。如果 SL 未触发但 TP1 触发，则 TP1 成交。两者不会在同一根 K 线内同时成交。

### 7.2 Trailing Stop 字段填充时机说明（P1-2 修复）

- **trailing stop 修改 SL 产生 sl_modified 记录**：`event_category='sl_modified'`，`close_price`/`close_qty`/`close_pnl`/`close_fee` 为 NULL，仅记录 `original_sl_price`/`modified_sl_price`。
- **填充时机**：在 `dynamic_risk_manager.evaluate_and_mutate` 中记录 SL 变化时同步创建 close_event。
- **最终 SL 出场**：当 SL 最终触发时，产生 `event_category='exit'` 的出场记录。

### 7.3 close_events 排序保证（P1-4 修复）

- `close_events` 列表必须按 `close_time` 升序排列
- `close_time` 相同时（同一根 K 线内多事件），按撮合引擎执行顺序排列
- `match_orders_for_kline` 按优先级（SL > TP > ENTRY）处理订单，因此 `executed` 列表的顺序即为撮合顺序
- backtester 按 `executed` 列表顺序遍历并追加到 `close_events`，自然保持正确顺序
- 序列化/反序列化后仍保持列表顺序（JSON 数组顺序保证）
- 独立表查询 `ORDER BY close_time ASC` 保证返回顺序
- 前端展示前无需额外排序，列表已按正确顺序排列

### 7.4 边界检查清单

- [x] `close_qty > 0`：每次出场数量必须为正（**P1-1 修复**：`actual_filled <= 0` 时 `continue` 跳过事件创建）
- [ ] `close_pnl` 可正可负（盈利/亏损），也可以为 0（成交价 = 入场价时）
- [ ] `close_fee >= 0`：手续费不能为负
- [ ] `close_time` 时间戳必须在回测时间范围内
- [ ] `close_events` 为空列表时，前端不显示展开按钮
- [ ] 同一 position 的 `close_events` 按时间排序
- [ ] `close_qty` 总和等于原始开仓数量（验证完整性：`sum(e.close_qty) == 原始开仓数量`）
- [ ] `sum(e.close_pnl for e in close_events where e.event_category='exit') == position.realized_pnl`（不变量验证）
- [ ] `close_pnl = 0` 时前端 `isPositive(0)` 应返回 false，展示为中性颜色或 0

---

## 8. 关联影响评估

| 模块 | 影响描述 | 风险等级 | 方案 |
|------|----------|----------|------|
| `src/domain/models.py` | 新增 PositionCloseEvent 模型 + PositionSummary.close_events 字段 + Order.actual_filled/close_pnl/close_fee 字段 | P0 | 核心变更 |
| `src/domain/matching_engine.py` | _execute_fill 写入 PnL 到 order 对象 + 写入 order.actual_filled（不修改 filled_qty 语义，P0-4 修复） | P0 | 写入 Order 字段，不改返回值 |
| `src/application/backtester.py` | 出场事件记录逻辑重构 + 统计逻辑拆分（部分平仓 vs 完全平仓） | P0 | 每次 TP1/SL 成交时创建事件，仅 is_closed 时更新统计 |
| `src/infrastructure/backtest_repository.py` | 新增独立表 CRUD 方法 + 序列化扩展 | P0 | INSERT/SELECT 独立表 + JSON 双写 |
| **数据库** | 新增 position_close_events 表 + 索引 | P0 | CREATE TABLE + CREATE INDEX |
| `web-front/src/lib/api.ts` | TS 接口新增 | P0 | 向后兼容 |
| `BacktestReportDetailModal.tsx` | 前端渲染逻辑改造 | P0 | 事件列表展开/折叠 |
| **测试** | 需覆盖所有边界场景 | P0 | 见测试计划 |

---

## 9. 技术债

### 9.1 已标记技术债（P2，本期不修复）

| 技术债 | 说明 | 优先级 | 备注 |
|--------|------|--------|------|
| realized_pnl 累计值冗余 | 当前 realized_pnl 仍为累计值，后续可考虑完全依赖 close_events 计算 | P2 | `sum(e.close_pnl for e in close_events where event_category='exit')` 可替代 |
| exit_price 单一字段 | 多事件场景下 exit_price 无明确语义，可逐步废弃 | P2 | 仅保留向后兼容 |
| exit_reason 单一字段 | 多事件场景下 exit_reason 无明确语义，可逐步废弃 | P2 | 信息已包含在 close_events 中 |
| exit_time 单一字段 | 多事件场景下 exit_time 无明确语义，可逐步废弃 | P2 | 信息已包含在 close_events 中 |
| 入场手续费未记录到 close_event | close_fee 仅记录出场手续费，入场 fee 未被记录 | P2 | 可在 PositionSummary 新增 total_fees 字段 |
| Trailing Stop 修改历史自动填充 | event_category='sl_modified' 记录需 dynamic_risk_manager 联动写入 | P2 | 本期预留字段，后续实现 |

### 9.2 QA 审查遗留 P2 问题（本期不修复，标注备查）

| 编号 | 问题 | 推荐方案 | 备注 |
|------|------|---------|------|
| P2-1 | close_events 表缺少唯一约束 | 添加 `UNIQUE(position_id, order_id, event_type, close_time)` 约束 | 防止重复插入同一订单的同一事件 |
| P2-2 | 缺少 close_time 范围约束 | 添加 CHECK(close_time > 0) 约束 | 防止零值/负值时间戳 |
| P2-3 | 前端 EventTypeBadge 硬编码颜色映射 | 改为配置驱动，支持动态事件类型 | 新增事件类型需修改前端 |
| P2-4 | close_events 表缺少 created_at 审计字段 | 新增 `created_at INTEGER` 记录写入时间 | 便于排查双写不一致问题 |

**迁移路径建议**:
1. 本期保留所有旧字段，确保向后兼容
2. 下期将 `realized_pnl` 改为计算属性（`@property`），从 close_events 派生
3. 再下期逐步废弃 `exit_price`/`exit_time`/`exit_reason` 单一字段

---

## 10. 开发实施清单

### 10.1 分步实施计划

| 步骤 | 内容 | 风险 |
|------|------|------|
| Step 1 | Order 新增 close_pnl/close_fee + _execute_fill 写值 | 仅新增字段赋值 |
| Step 2 | backtester 读取值创建 close_events 存入独立表 | 追加逻辑，不修改现有统计 |
| Step 3 | _generate_tp_sl_orders 增加 TP2/TP3 生成 | 新增订单，需验证触发逻辑 |

### 10.2 后端开发任务

| # | 任务 | 文件 | 预估工时 | 依赖 |
|---|------|------|----------|------|
| 1 | 新增 PositionCloseEvent 模型 | models.py | 10min | 无 |
| 2 | PositionSummary 新增 close_events 字段 | models.py | 5min | 1 |
| 3 | Order 新增 close_pnl/close_fee 字段 | models.py | 5min | 无 |
| 4 | _execute_fill 写入 PnL 到 order + 写入 order.actual_filled（P0-4 修复） | matching_engine.py | 20min | 3 |
| 5 | 创建 position_close_events 表 DDL | backtest_repository.py | 15min | 无 |
| 6 | 新增 create_close_event / create_close_events_batch 方法 | backtest_repository.py | 30min | 5 |
| 7 | 新增 get_close_events_for_position 方法 | backtest_repository.py | 20min | 5 |
| 8 | backtester 出场事件记录逻辑重构 + 统计拆分 + 写入独立表 | backtester.py | 45min | 4, 6 |
| 9 | 回测报告序列化/反序列化扩展（双写 + JOIN 查询） | backtest_repository.py | 30min | 7 |
| 10 | 单元测试 | tests/unit/ | 90min | 1-9 |

**总预估工时**: 约 5 小时

### 10.3 前端开发任务

| # | 任务 | 文件 | 预估工时 | 依赖 |
|---|------|------|----------|------|
| 1 | 新增 PositionCloseEvent 接口 | api.ts | 10min | 后端 2 |
| 2 | PositionSummary 接口新增字段 | api.ts | 5min | 1 |
| 3 | 仓位历史表格改造 | BacktestReportDetailModal.tsx | 60min | 2 |

**总预估工时**: 约 1.5 小时

---

## 11. 测试计划

### 11.1 单元测试

**models.py 测试**:
- [ ] PositionCloseEvent 所有必填字段校验
- [ ] PositionCloseEvent 可选字段 None 处理（close_price/close_qty/close_pnl/close_fee 在 sl_modified 时为 None）
- [ ] PositionCloseEvent event_category 默认值 'exit'
- [ ] PositionCloseEvent extra="forbid" 校验（额外字段抛异常）
- [ ] PositionSummary.close_events 默认空列表
- [ ] PositionSummary.close_events 多个事件追加
- [ ] Order.close_pnl/close_fee 默认 None
- [ ] Order.close_pnl/close_fee 可赋值 Decimal

**matching_engine.py 测试**:
- [ ] _execute_fill 入场单不设置 order.close_pnl（保持 None）
- [ ] _execute_fill 平仓单设置 order.close_pnl = net_pnl, order.close_fee = fee_paid
- [ ] _execute_fill 设置 order.actual_filled = actual_filled（防超卖保护截断后，P0-4 修复）
- [ ] _execute_fill 不修改 order.filled_qty 语义（P0-4 修复）
- [ ] _execute_fill position=None 直接 return（防御性处理）
- [ ] 不变量验证：`sum(event.close_pnl for event in close_events if event.event_category=='exit') == position.realized_pnl`

**backtest_repository.py 测试**:
- [ ] BacktestRepository 初始化时 PRAGMA foreign_keys = ON（P1-6 修复）
- [ ] PRAGMA foreign_keys 启用失败时抛出 RuntimeError
- [ ] create_close_event 正确 INSERT 到 position_close_events 表
- [ ] create_close_events_batch 批量 INSERT 正确
- [ ] get_close_events_for_position 正确 SELECT 并按 close_time 升序排列
- [ ] 序列化 close_events 嵌套列表到 JSON
- [ ] 反序列化有 close_events 的旧 JSON
- [ ] 反序列化无 close_events 的旧 JSON（默认空列表）
- [ ] 反序列化旧 JSON 时 original_sl_price 字段不存在也不报错
- [ ] 序列化/反序列化往返一致性
- [ ] 以 JSON 数据为 SSOT，独立表作为补充查询（P1-4 修复）
- [ ] 独立表写入失败时不抛出异常，记录 warning 日志（P1-4 修复）

**backtester.py 测试**:
- [ ] TP1 成交时创建 PositionCloseEvent 并写入独立表
- [ ] SL 成交时创建 PositionCloseEvent 并写入独立表
- [ ] actual_filled <= 0 时不创建 PositionCloseEvent（P1-1 修复）
- [ ] 多次部分平仓后 close_events 数量正确
- [ ] 部分平仓时不更新 total_pnl/winning_trades/losing_trades
- [ ] 完全平仓时更新 total_pnl/winning_trades/losing_trades
- [ ] 向后兼容：position.is_closed 时仍更新 exit_price/realized_pnl
- [ ] SL 触发后 TP 被撤销场景：仅 1 条 SL 事件，无 TP 事件
- [ ] 新逻辑失败时，原有统计逻辑不受影响

### 11.2 集成测试

- [ ] 运行完整回测，验证 close_events 数量与预期一致
- [ ] 验证 TP1 部分平 + SL 平剩余场景产生 2 条事件
- [ ] 验证直接 SL 全平场景产生 1 条事件
- [ ] 验证 SL 触发后 TP 被撤销场景仅产生 1 条 SL 事件
- [ ] 验证回测报告 API 返回 close_events 字段
- [ ] 验证前端正确渲染事件列表
- [ ] 验证 close_events 按时间顺序排列
- [ ] 验证 position_close_events 表索引查询性能
- [ ] 验证 order.actual_filled != order.requested_qty 时 close_qty 使用 actual_filled（P0-4 修复）
- [ ] 验证 event_category='exit' 时 close_price/close_qty/close_pnl/close_fee 非 NULL（P0-1 CHECK 约束）
- [ ] 验证 PRAGMA foreign_keys = ON 生效（P1-6 修复）

---

## 12. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Order 新增字段遗漏初始化为 None | 低 | P0 | Pydantic Optional 默认值保证 |
| _execute_fill 写入 order.close_pnl 被其他调用方误用 | 低 | P1 | 文档注明"仅回测场景使用" |
| 旧回测报告 JSON 反序列化失败 | 低 | P0 | `.get("close_events", [])` 默认空列表 |
| 前端旧版不识别 close_events 字段 | 低 | P1 | 字段可选 `close_events?: PositionCloseEvent[]` |
| 性能影响（序列化嵌套列表 + 双写） | 极低 | P2 | 单报告仓位数有限，无显著影响 |
| 部分平仓时 total_pnl 重复累加 | 无（已修复） | P0 | 仅在 `is_closed=True` 时更新统计 |
| 独立表写入失败影响原有统计 | 极低 | P0 | 新逻辑独立追加，即使失败原有统计不受影响 |
| 外键约束导致孤立数据 | 极低 | P1 | ON DELETE CASCADE 保证级联清理（P1-6: PRAGMA foreign_keys = ON） |

---

## 13. QA 审查修复记录

> **审查日期**: 2026-04-15
> **审查人**: QA 审查员
> **修复人**: 架构师

### P0 问题修复（必须修复）

| 编号 | 问题描述 | 修复方案 | 修复章节 | 状态 |
|------|---------|---------|---------|------|
| P0-1 | DDL NOT NULL 与 Pydantic Optional + sl_modified NULL 描述矛盾 | DDL 中 `close_price`/`close_qty`/`close_pnl`/`close_fee` 改为允许 NULL，增加 CHECK 约束保证 `event_category='exit'` 时非 NULL | 2.2 表 DDL | 已修复 |
| P0-2 | 数据流图硬编码 'exit' 与代码参数化不一致 | Step 4 INSERT 语句中 `event_category` 从硬编码 `'exit'` 改为参数化 `?` | 3.1 数据流图 | 已修复 |
| P0-3 | 加仓场景未声明约束 | 新增不变量 4，显式声明本期不支持加仓，每个 close_event 的 entry_price 快照一致 | 2.5 数据不变量 | 已修复 |
| P0-4 | `order.filled_qty` 语义变更影响未知 | 采用方案 A：新增 `order.actual_filled` 字段记录实际成交量，不修改 `filled_qty` 语义 | 2.4/4.1/4.2/4.3 | 已修复 |

### P1 问题修复（本期修复）

| 编号 | 问题描述 | 修复方案 | 修复章节 | 状态 |
|------|---------|---------|---------|------|
| P1-1 | 缺少 `close_qty > 0` 防御性检查 | 增加防御检查 `if order.actual_filled <= 0: continue` | 4.3 backtester.py | 已修复 |
| P1-4 | 双写一致性未保证 | 声明"以 JSON 数据为准"作为降级策略，独立表写入失败不抛异常 | 5.1/5.2 序列化/反序列化 | 已修复 |
| P1-5 | 事件收集逻辑不明确 | 补充 `all_close_events` 列表的初始化/追加/批量写入流程 | 5.1 序列化流程 | 已修复 |
| P1-6 | SQLite 外键需要 PRAGMA | 在 `BacktestRepository.__init__` 中增加 `PRAGMA foreign_keys = ON` 及验证 | 4.4 backtest_repository.py | 已修复 |

### P2 问题（标注备查，本期不修复）

| 编号 | 问题描述 | 推荐方案 | 处理 |
|------|---------|---------|------|
| P2-1 | close_events 表缺少唯一约束 | 添加 `UNIQUE(position_id, order_id, event_type, close_time)` | 技术债章节标注 |
| P2-2 | 缺少 close_time 范围约束 | 添加 CHECK(close_time > 0) 约束 | 技术债章节标注 |
| P2-3 | 前端 EventTypeBadge 硬编码颜色映射 | 改为配置驱动 | 技术债章节标注 |
| P2-4 | close_events 表缺少 created_at 审计字段 | 新增 `created_at INTEGER` 字段 | 技术债章节标注 |
