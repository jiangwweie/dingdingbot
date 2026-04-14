# QA 审查报告：PositionSummary 一对多出场事件设计

## 审查概述

- **审查文件**：position-summary-close-event-implementation.md
- **关联 ADR**：position-summary-close-event-design.md
- **审查日期**：2026-04-15
- **审查人**：QA

---

## 问题清单

### P0 问题（必须修复）

| 编号 | 问题描述 | 影响 | 建议修复方案 |
|------|----------|------|-------------|
| P0-1 | **数据流图关键错误：`_execute_fill` 是 `match_orders_for_kline` 的内部方法，backtester 无法直接调用** | 设计文档的数据流图（Section 3.1）显示 backtester 直接调用 `_execute_fill` 并捕获返回值。但实际代码中（matching_engine.py line 150/175/194），`_execute_fill` 是 `match_orders_for_kline` 方法内部的私有方法，backtester 调用的是 `match_orders_for_kline`（backtester.py line 1381），而非 `_execute_fill` 本身。这意味着返回 tuple 的设计无法按文档描述的方式工作。 | 方案 A：让 `match_orders_for_kline` 返回 `tuple[List[Order], List[tuple[Decimal, Decimal]]]`，将每次 `_execute_fill` 的结果聚合后一并返回给 backtester。方案 B：不修改返回值，backtester 改为从 `executed` 订单列表中读取 `order.average_exec_price`，配合 `position.realized_pnl` 的差值来计算每次出场的 pnl。方案 C：给 Order 模型新增 `close_pnl` 和 `close_fee` 字段，`_execute_fill` 中将计算结果写入 order 对象，backtester 从 executed order 直接读取（推荐，改动最小且语义清晰）。 |
| P0-2 | **止损触发后关联订单被撤销，导致部分出场事件无法记录** | matching_engine.py line 161-163：SL 触发后会调用 `_cancel_related_orders` 撤销该 signal_id 的所有 OPEN 订单（包括 TP1）。被撤销的订单状态变为 CANCELED，永远不会进入 backtester 的 `executed` 列表（只有 FILLED 的订单才会被遍历）。因此，如果 SL 和 TP1 在同一根 K 线内，TP1 即使未触发也会被撤销——这是正确的；但如果 TP1 先在之前 K 线成交，SL 在当前 K 线触发，此时 TP1 事件已经正确记录，不受影响。然而设计文档 Section 5 提到"同一根 K 线多事件"场景未充分考虑：如果 SL 触发导致 TP1 被撤销，撤销本身是否需要记录为事件？ | 明确撤销场景的记录策略：(1) SL 触发撤销 TP1 时，撤销行为不需要记录为 close_event（因为 TP1 并未成交）；(2) 但需要在设计文档的边界情况表中补充"SL 触发后 TP 被撤销"的处理说明，避免开发时遗漏。 |
| P0-3 | **`close_pnl` 语义不一致：文档称"与 matching_engine net_pnl 语义一致"但未考虑手续费重复计算** | PositionCloseEvent 的 `close_pnl` 定义为 `gross_pnl - fee`。但 `matching_engine._execute_fill` 中（line 352）`net_pnl = gross_pnl - fee_paid` 已经扣除了手续费，同时 `position.realized_pnl += net_pnl` 也累计了这个净盈亏。如果前端对 `close_events` 求和得到总 pnl，同时对 `PositionSummary.realized_pnl` 也求和，两者应该一致。但设计文档 Section 7 技术债提到后续让 `realized_pnl` 改为计算属性从 `close_events` 派生，此时需要确认 `sum(e.close_pnl) == position.realized_pnl` 始终成立。当前代码中 `position.realized_pnl` 是在 `_execute_fill` 中累加的，而 `close_pnl` 也是同一个 `net_pnl`，所以一致性由同一计算保证——但设计文档需要明确声明这个不变量。 | 在设计文档中增加"不变量声明"章节：`sum(e.close_pnl for e in summary.close_events) == position.realized_pnl`（当仓位完全关闭时）。同时在 backtester 的统计逻辑中（line 1457 `total_pnl += position.realized_pnl`）需要确认不会与 close_events 的汇总产生重复计算。 |
| P0-4 | **backtester 第 1438 行条件从 `if position and position.is_closed` 改为 `if position` 后，部分平仓时 `position.realized_pnl` 尚未完全确定** | 新逻辑中每次 TP1/SL 成交时都创建事件。但 backtester line 1457 `total_pnl += position.realized_pnl` 只在 `is_closed` 时才执行（当前代码逻辑）。改为 `if position` 后，部分平仓也会进入该分支，此时 `position.realized_pnl` 只是部分实现的盈亏，计入 `total_pnl` 会导致重复累计（部分平仓时计入一次，完全平仓时又计入一次）。 | backtester 的统计逻辑需要拆分：(1) 部分平仓时：仅创建 close_event，不更新 `total_pnl`/`winning_trades`/`losing_trades`；(2) 完全平仓时（`is_closed=True`）：更新累计统计。需要在设计文档的 backtester 变更部分（Section 4.3）明确区分这两种情况下的统计处理。 |

### P1 问题（建议修复）

| 编号 | 问题描述 | 影响 | 建议修复方案 |
|------|----------|------|-------------|
| P1-1 | **`close_qty` 数据来源错误：设计文档使用 `order.filled_qty`，但部分平仓时 `order.filled_qty` 等于 `order.requested_qty`** | 设计文档 Section 4.3 新逻辑中 `close_qty=order.filled_qty`。但 `_execute_fill` 中（line 340）有防超卖保护 `actual_filled = min(order.requested_qty, position.current_qty)`。当 `requested_qty > current_qty` 时，实际成交数量小于 `order.filled_qty`。`PositionCloseEvent` 的 `close_qty` 应该等于 `actual_filled` 而非 `order.filled_qty`。 | `_execute_fill` 需要将 `actual_filled` 写入 order（如新增 `order.actual_filled_qty`）或返回值中，确保 backtester 使用实际成交数量而非请求数量。或者在 Order 模型中让 `filled_qty` 始终等于实际成交量（当前代码 line 271 `order.filled_qty = order.requested_qty` 没有考虑截断）。 |
| P1-2 | **Trailing stop 的 `original_sl_price` 和 `modified_sl_price` 填充时机未明确** | 设计文档定义了这两个可选字段用于 trailing stop 场景，但未说明：(1) 哪个环节负责填充这两个字段？(2) 每次 trailing stop 修改 SL 时，是产生一条新的 close_event 还是更新已有事件？(3) trailing stop 只是修改止损价，不是出场动作，不应该产生 close_event。 | 明确 trailing stop SL 修改的记录机制：trailing stop 修改 SL 不产生 close_event（因为仓位没有关闭），而是通过其他机制记录 SL 路径变更（例如在 Order 模型上记录 SL 修改历史，或在 Position 模型上维护 SL 历史列表）。`original_sl_price` 和 `modified_sl_price` 字段只在最终 SL 出场事件中使用，记录从哪个价格触发到哪个价格触发。 |
| P1-3 | **`close_fee` 计算基准不一致：入场单手续费 vs 平仓单手续费** | `_execute_fill` 中 `fee_paid = trade_value * self.fee_rate`，其中 `trade_value = exec_price * order.requested_qty`。入场单和平仓单都按此公式计算。但 `close_fee` 只在平仓事件中记录，入场单的 `fee_paid` 不会被记录到任何 close_event 中。如果用户想知道一笔仓位的总手续费成本，需要手动累加入场 fee + 所有出场 fee。 | 在 PositionSummary 中新增 `total_fees` 字段，或在前端展开明细时额外显示入场手续费。或者在第一个 close_event 中包含入场手续费信息。 |
| P1-4 | **前端 `close_events.length` 作为"出场次数"展示，但未考虑同一根 K 线内多次成交的排序** | 设计文档 Section 5 提到"同一根 K 线多事件：时间戳相同，按撮合顺序"。但前端展示时仅按 `close_events` 列表顺序排列，没有明确的排序保证。如果 backtester 追加事件的顺序与撮合引擎执行顺序不一致，前端展示的时间线会错乱。 | 在设计文档中明确：(1) close_events 必须按 `close_time` 升序排列，`close_time` 相同时按撮合引擎执行顺序排列；(2) 序列化/反序列化后仍保持顺序；(3) 前端展示前确保列表已排序。 |
| P1-5 | **`_str_to_decimal` 对 `None` 的处理在反序列化 `original_sl_price` 时可能出错** | 设计文档 Section 4.4 反序列化代码中 `self._str_to_decimal(event_data.get("original_sl_price"))`。当 JSON 中该字段为 `null` 时，`event_data.get()` 返回 `None`，`_str_to_decimal(None)` 返回 `None`（现有实现已处理）。但如果旧 JSON 中该字段不存在，`event_data.get("original_sl_price")` 返回 `None`（无默认值），同样是 `None`。此场景已有处理，但设计文档应明确确认。 | 在设计文档中显式声明：`event_data.get("original_sl_price")` 应使用 `event_data.get("original_sl_price")` 而非 `event_data["original_sl_price"]`，对旧数据兼容。同时补充 `exit_reason` 字段的类似处理（`event_data.get("exit_reason")`）。当前设计文档的代码示例已正确使用 `.get()`，但应在文字说明中确认。 |

### P2 问题（可选优化）

| 编号 | 问题描述 | 影响 | 建议修复方案 |
|------|----------|------|-------------|
| P2-1 | **ADR 文档（position-summary-close-event-design.md）中 `realized_pnl` 定义为 `@property` 计算属性，但实现文档中保留为普通字段** | ADR line 32-34 显示 `@property def realized_pnl(self) -> Decimal: return sum(...)`，但实现文档 Section 2.2 中 `realized_pnl` 仍是 `Decimal = Field(default=Decimal('0'))`。两个文档存在矛盾。 | 本期保留为普通字段（兼容），在技术债章节已提及后续改为计算属性。建议在 ADR 中补充说明：本期保留字段形式，下期迁移为计算属性。 |
| P2-2 | **前端 `EventTypeBadge` 颜色映射中 `TRAILING` 使用黄色，但回测中 trailing stop 出场事件的 `event_type` 是什么？** | 当前撮合引擎只有 `OrderRole.TP1` 和 `OrderRole.SL`，没有 TRAILING 角色。trailing stop 只是修改 SL 价格的机制，最终出场仍然是 SL 触发。前端定义了 TRAILING 颜色但目前没有对应数据。 | 明确 trailing stop 触发出场时 `event_type` 的值：(1) 如果仍是 "SL"，则前端 TRAILING 颜色暂时无用；(2) 如果需要在出场时区分"普通 SL"和"trailing SL"，需要新增 `event_type` 值或在 `exit_reason` 中区分。建议本期保留 "SL"，`exit_reason` 字段携带更多信息（如 "Trailing Stop 触发"）。 |
| P2-3 | **开发实施清单中测试工时 60min，但边界场景（直接 SL、TP1+SL、TP1 100%、TP1+TP2+SL、未平仓、同 K 线多事件、trailing stop、手动平仓、旧数据）至少需要 9 个测试用例** | 60min 覆盖所有单元测试可能不够充分，尤其是需要 mock 撮合引擎行为的场景。 | 建议将测试工时调整为 90min，并明确列出每个测试用例的优先级。 |
| P2-4 | **前端伪代码中 `EventRow` 使用 `key={idx}` 作为 React key** | 使用数组索引作为 React key 在列表顺序变化时会导致渲染问题。虽然 close_events 顺序理论上不变，但不符合最佳实践。 | 使用 `event.order_id` 或 `event.position_id + event.event_type + event.close_time` 作为 key。 |

---

## 边界情况检查

| 场景 | 是否覆盖 | 备注 |
|------|----------|------|
| 直接 SL 全平 | 已覆盖 | Section 5 边界情况表 |
| TP1 部分平 + SL 平剩余 | 已覆盖 | Section 5 边界情况表 |
| TP1 100% 全平 | 已覆盖 | Section 5 边界情况表 |
| TP1 部分平 + TP2 部分平 + SL 平剩余 | 已覆盖 | Section 5 边界情况表 |
| 仓位未平仓（回测期间未出场） | 已覆盖 | close_events = [] |
| 同一根 K 线多事件 | 部分覆盖 | 提到"按撮合顺序"但未明确排序保证机制 |
| trailing stop 修改 SL | 部分覆盖 | 定义了字段但未明确填充时机和记录机制 |
| 手动平仓 | 已覆盖（预留） | event_type = "MANUAL"，回测中暂无 |
| 旧回测报告（无 close_events 字段） | 已覆盖 | `.get("close_events", [])` 默认空列表 |
| **SL 触发后 TP 被撤销** | **未覆盖** | 需要在边界表中补充说明 |
| **close_qty = 0** | **未覆盖** | 设计文档 Section 5 边界检查提到 `close_qty > 0` 但未处理等于 0 的防御逻辑 |
| **close_pnl = 0**（成交价 = 入场价） | **未覆盖** | 前端 `isPositive` 辅助函数对 0 的展示需明确 |
| **超大数值展示** | **未覆盖** | 设计文档 Section 5 未提及极大值的格式化 |
| **加仓后部分平仓** | **未覆盖** | 如果同一 position 有多次入场（加仓），entry_price 会被覆盖（matching_engine.py line 298），close_events 的盈亏计算基于最新 entry_price，可能不准确 |

---

## 数据一致性专项检查

| 检查项 | 状态 | 说明 |
|--------|------|------|
| close_pnl = gross_pnl - fee 的计算一致性 | 需注意 | 计算在 `_execute_fill` 内部完成，close_pnl 直接使用 net_pnl，语义一致 |
| Decimal 精度保证 | 通过 | 所有金额字段使用 Decimal，序列化使用 `_decimal_to_str` |
| 累计值与事件列表汇总 | **存在风险** | P0-4 描述的 `total_pnl` 重复累计问题 |
| `sum(e.close_pnl) == position.realized_pnl` 不变量 | 需声明 | 当前由同一计算路径保证，但设计文档未显式声明 |

---

## 向后兼容性检查

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 旧 PositionSummary JSON 反序列化 | 通过 | `default_factory=list` + `.get("close_events", [])` |
| 前端旧版不读取 close_events | 通过 | `hasEvents` 空列表时不显示展开按钮 |
| 旧字段保留（exit_price/exit_time/realized_pnl/exit_reason） | 通过 | 设计明确保留所有旧字段 |
| 数据库 schema 变更 | 通过 | JSON 存储，无需 DB 迁移 |

---

## 审查结论

- **P0 问题数量**：4
- **P1 问题数量**：5
- **P2 问题数量**：4
- **是否通过审查**：**否**（P0 问题必须全部修复才能通过）

### 关键阻塞项

1. **P0-1 是最严重的结构性问题**：整个数据流图建立在错误的调用关系上。`_execute_fill` 是 `match_orders_for_kline` 的内部方法，backtester 无法直接调用。必须在编码开始前确定正确的数据传递方案（推荐方案 C：给 Order 模型新增 `close_pnl`/`close_fee` 字段）。

2. **P0-4 影响统计正确性**：如果部分平仓时也更新 `total_pnl`，会导致盈亏重复计算。必须明确区分部分平仓和完全平仓的统计逻辑。

3. **P0-3 影响数据可信度**：需要显式声明不变量，否则后续维护者无法确认 close_events 汇总与 realized_pnl 的一致性。

### 建议修复顺序

```
1. 先修复 P0-1（确定数据传递方案，修正数据流图）
2. 再修复 P0-4（拆分部分平仓 vs 完全平仓的统计逻辑）
3. 然后修复 P0-3（声明不变量）
4. P0-2 补充边界说明
5. P1 问题按需修复
6. P2 问题可后续优化
```
