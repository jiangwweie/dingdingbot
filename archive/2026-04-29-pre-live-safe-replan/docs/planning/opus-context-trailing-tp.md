# Trailing TP 架构设计请求

## 项目概况

盯盘狗 — 加密货币量化交易自动化系统（Python/FastAPI/asyncio），支持回测 + 实盘。
当前阶段：v3.0 Phase 5 实盘集成，已实现分批止盈（TP1 部分平仓），待实现止盈追踪。

## 当前已有的相关实现

### 1. Trailing Stop Loss（已有，可参考模式）

位置：`src/domain/risk_manager.py` 的 `_apply_trailing_logic()` 方法

核心逻辑：
- 基于 `position.watermark_price`（仓位持有期间最高/最低价）
- `theoretical_trigger = watermark * (1 - trailing_percent)` （LONG）
- 阶梯阈值防频繁更新：新止损价必须比当前价高出 `step_threshold` 才更新
- 保护损底线：LONG 止损价 ≥ entry_price，SHORT 止损价 ≤ entry_price
- 水位线在每根 K 线更新：`_update_watermark()`

### 2. 当前 TP1 处理（固定价格）

位置：`src/domain/matching_engine.py` 第 159-177 行

```python
elif order.order_type == OrderType.LIMIT and order.order_role == OrderRole.TP1:
    if order.direction == Direction.LONG and kline.high >= order.price:
        exec_price = order.price * (1 - tp_slippage_rate)
        self._execute_fill(order, exec_price, ...)
    elif order.direction == Direction.SHORT and kline.low <= order.price:
        exec_price = order.price * (1 + tp_slippage_rate)
        self._execute_fill(order, exec_price, ...)
```

TP1 是固定价格 LIMIT 单，K 线 high/low 触及即成交。

### 3. 数据模型

```python
class OrderRole(str, Enum):
    ENTRY = "ENTRY"
    TP1 = "TP1"    # 已实现
    TP2 = "TP2"    # enum 已定义，撮合未实现
    TP3 = "TP3"    # enum 已定义，撮合未实现
    SL = "SL"

class Position(FinancialModel):
    watermark_price: Optional[Decimal]  # 最高价(LONG)/最低价(SHORT)
    entry_price: Decimal
    direction: Direction  # LONG/SHORT
    current_qty: Decimal  # TP1 触发后会变小
    is_closed: bool

class TakeProfitLevel(BaseModel):
    id: str                    # "TP1", "TP2"
    position_ratio: Decimal    # 平仓比例，如 0.5
    risk_reward: Decimal       # 风险回报比，如 1.5, 3.0

class Order(FinancialModel):
    order_role: OrderRole
    order_type: OrderType      # LIMIT / MARKET
    price: Decimal             # 止盈价格（LIMIT 单）
    trigger_price: Optional[Decimal]  # 止损触发价
    signal_id: str
    direction: Direction
```

### 4. 关键约束

- 所有金额使用 `decimal.Decimal`（严禁 float）
- matching_engine 是同步方法（`def process_kline`），接收 `KlineData`
- 每根 K 线只在 `is_closed=True` 时触发策略计算
- 实盘和回测共用同一套 matching_engine
- 水位线更新在 risk_manager 中，matching_engine 中处理订单触发

## 需要设计的问题

### 核心问题：Trailing TP 如何实现？

用户需求：
1. TP 价格可跟随行情上移（LONG）/ 下移（SHORT）
2. 支持固定步长（step）和回撤比例（pullback）两种模式
3. 需要记录 TP 修改的事件日志（如 `event_category='tp_modified'`）
4. 需要考虑回测 vs 实盘的实现差异（如果有的话）

### 待决策项

1. **Trailing TP 逻辑放在哪里？**
   - 方案 A：放在 risk_manager（与 trailing SL 对称）
   - 方案 B：放在 matching_engine（与 TP1 处理就近）
   - 方案 C：新建 trailing_manager 模块

2. **Trailing TP 与 Trailing SL 的关系？**
   - 是否需要同时移动两者？
   - 是否有联动逻辑？

3. **TP2/TP3 是否也支持 trailing？**
   - 还是只对 TP1 做 trailing？

4. **回测中如何验证 trailing TP？**
   - 需要什么样的测试数据？
   - 与分批止盈（TP1/TP2/TP3）的交互？

5. **事件记录机制？**
   - 用现有的 PositionCloseEvent？
   - 还是新增 TP 修改事件类型？

## 技术栈

- Python 3.11+, Pydantic v2, asyncio
- 所有金融计算必须使用 decimal.Decimal
- FastAPI 后端
- 测试：pytest + pytest-asyncio

## 期望输出

请提供：
1. 架构方案（至少 2 个选项 + 推荐）
2. 核心接口/方法签名
3. 数据模型变更
4. 与现有 trailing SL 的关系
5. 测试策略
6. 实盘 vs 回测差异处理
