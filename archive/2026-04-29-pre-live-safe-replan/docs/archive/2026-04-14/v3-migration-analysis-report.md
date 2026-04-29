# 盯盘狗系统 v3.0 架构升级分析报告

**文档版本**: 1.0
**分析日期**: 2026-03-30
**分析对象**: 盯盘狗系统 v2.0 (当前生产版本) → v3.0 (PMS 仓位中心模型架构)
**报告作者**: 架构分析团队

---

## 执行摘要 (Executive Summary)

本报告对盯盘狗系统 v3.0 设计文档进行了全面深入的分析，对比了 v2.0 当前系统架构，识别了兼容性、冲突点、迁移成本，并给出了具体的迁移路径建议。

### 核心发现

1. **架构理念一致性**: v3 设计的"三重解耦"（意图与执行、执行与状态、回测与实盘）与 v2.0 现有 Clean Architecture 高度契合，迁移具备坚实基础。

2. **数据模型兼容性**: v3 核心模型（Signal/Order/Position/Account）与 v2.0 Pydantic v2 + Decimal 技术栈完全兼容，无需重构基础验证层。

3. **关键差异点**: v2.0 缺少 Order 执行层抽象和 Position 状态机，回测引擎采用"信号直接判定盈亏"而非"订单撮合"模式。

4. **迁移成本评估**: 中等偏高。核心业务逻辑需重构，但基础设施层（ExchangeGateway、SignalRepository、Notifier）可直接复用。

5. **建议迁移策略**: 采用"双轨并行、渐进替换"策略，先实现 PMS 模型与 v2.0 信号系统并行运行，验证无误后逐步切换。

---

## 第一章：v2.0 与 v3.0 架构详细对比

### 1.1 架构分层对比

#### v2.0 架构 (Clean Architecture 四层分离)

```
┌─────────────────────────────────────────────────────────┐
│  Interfaces (REST API)                                  │
│  - FastAPI routes: /backtest, /signals, /config         │
├─────────────────────────────────────────────────────────┤
│  Application Services                                   │
│  - SignalPipeline: K 线→策略→风控→通知→持久化            │
│  - Backtester: 无状态回测沙箱                            │
│  - ConfigManager: 配置加载/热重载                        │
│  - PerformanceTracker: 信号性能追踪                      │
├─────────────────────────────────────────────────────────┤
│  Domain Layer (纯业务逻辑，无 I/O)                        │
│  - Models: KlineData, SignalResult, AccountSnapshot     │
│  - StrategyEngine: Pinbar/Engulfing + EMA/MTF 过滤器    │
│  - LogicTree: 递归逻辑树 (AND/OR/NOT)                   │
│  - RiskCalculator: 仓位计算 + 多级别止盈                 │
│  - FilterFactory: 动态过滤器工厂                        │
├─────────────────────────────────────────────────────────┤
│  Infrastructure (所有 I/O)                               │
│  - ExchangeGateway: CCXT REST + WebSocket               │
│  - SignalRepository: SQLite 持久化                      │
│  - Notifier: 飞书/微信/Telegram 通知                     │
│  - Logger: 统一日志 (敏感信息脱敏)                       │
└─────────────────────────────────────────────────────────┘
```

#### v3.0 架构 (PMS 仓位中心模型)

```
┌─────────────────────────────────────────────────────────┐
│  Interfaces (REST API + WebSocket)                      │
│  - FastAPI routes: /backtest, /signals, /positions      │
│  - WebSocket: 实时仓位状态推送                           │
├─────────────────────────────────────────────────────────┤
│  Application Services                                   │
│  - SignalPipeline: 信号生成 (不变)                       │
│  - OrderManager: 订单编排与生命周期管理【新增】           │
│  - PositionManager: 仓位状态机与 P&L 追踪【新增】         │
│  - Backtester: 悲观撮合引擎回测【重构】                  │
├─────────────────────────────────────────────────────────┤
│  Domain Layer (领域核心)                                 │
│  - Models: Signal, Order, Position, Account【新实体】    │
│  - MatchingEngine: 极端悲观撮合逻辑【新增】              │
│  - RiskStateMachine: 动态风控状态机【新增】              │
│  - LogicTree: 递归逻辑树 (保留)                          │
│  - RiskCalculator: 仓位计算 (保留)                       │
├─────────────────────────────────────────────────────────┤
│  Infrastructure (I/O 层)                                 │
│  - ExchangeGateway: CCXT.Pro WebSocket【增强】          │
│  - SignalRepository: SQLite + 新增 Order/Position 表    │
│  - Notifier: 通知推送 (保留)                            │
│  - Logger: 统一日志 (保留)                              │
└─────────────────────────────────────────────────────────┘
```

### 1.2 核心模型对比

#### v2.0 核心模型

| 模型 | 职责 | 生命周期 | 关键字段 |
|------|------|----------|----------|
| `SignalResult` | 策略输出信号 | 生成 → PENDING → ACTIVE/SUPERSEDED | symbol, direction, entry_price, stop_loss, position_size, tags, score, take_profit_levels |
| `AccountSnapshot` | 账户快照 (只读) | 瞬时快照，无状态累积 | total_balance, available_balance, unrealized_pnl, positions |
| `KlineData` | K 线数据输入 | 只读数据 | symbol, timeframe, timestamp, open/high/low/close/volume |
| `SignalAttempt` | 策略尝试记录 | 持久化用于分析 | strategy_name, pattern, filter_results, final_result |
| `SignalTrack` | 信号状态追踪 | GENERATED → PENDING → FILLED → WON/LOST | signal_id, status, filled_price, pnl_ratio |

**关键观察**:
- `SignalResult` 承担了"策略意图 + 风控计算结果"双重职责，但未涉及订单执行层
- `AccountSnapshot` 为只读快照，不参与盈亏累积计算
- 缺少 `Order` 和 `Position` 独立实体，仓位信息嵌套在 `AccountSnapshot.positions` 中
- 多级别止盈 (`take_profit_levels`) 仅为数据字段，无独立生命周期管理

#### v3.0 核心模型

| 模型 | 职责 | 生命周期 | 关键字段 |
|------|------|----------|----------|
| `Signal` | 策略意图记录 | 生成 → 转化为订单 → 终结 | id, strategy_id, expected_entry, expected_sl, pattern_score |
| `Order` | 交易执行凭证 | PENDING → OPEN → PARTIALLY_FILLED → FILLED/CANCELED | id, signal_id, exchange_order_id, order_type, order_role, price, trigger_price, requested_qty, filled_qty, average_exec_price, exit_reason |
| `Position` | 资产敞口状态 | 开仓 → 减仓 (TP1) → 平仓 (SL/TP2) | id, signal_id, entry_price (固定), current_qty (动态), highest_price_since_entry, realized_pnl, total_fees_paid |
| `Account` | 资产账户 | 持续累积盈亏 | total_balance, frozen_margin, available_balance (计算属性) |

**关键差异**:
1. **Signal 职责瘦身**: v3.0 的 `Signal` 仅记录"为什么交易"，不再承担仓位管理职责
2. **Order 独立实体**: v3.0 引入 `Order` 作为"如何交易"的物理凭证，区分 `price` (限价单) 和 `trigger_price` (条件单)
3. **Position 状态机**: v3.0 的 `Position` 有独立生命周期，`entry_price` 固定不变，`current_qty` 动态缩减
4. **Account 主动记账**: v3.0 的 `Account` 接受平仓盈亏累积，而非 v2.0 的瞬时快照

### 1.3 枚举类型对比

#### v2.0 枚举

```python
class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"

class SignalStatus(str, Enum):
    GENERATED = "generated"
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    ACTIVE = "active"
    SUPERSEDED = "superseded"

class MtfStatus(str, Enum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"

class TrendDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
```

#### v3.0 枚举

```python
class Direction(str, Enum):
    LONG = "LONG"      # 注意：v2.0 为小写 "long"
    SHORT = "SHORT"    # 注意：v2.0 为小写 "short"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    TRAILING_STOP = "TRAILING_STOP"

class OrderRole(str, Enum):
    ENTRY = "ENTRY"
    TP1 = "TP1"
    SL = "SL"
```

**兼容性注意**:
- `Direction` 枚举值大小写不一致（v2.0 小写，v3.0 大写），需在数据库层面进行迁移或保持兼容
- v3.0 新增 `OrderStatus`, `OrderType`, `OrderRole` 枚举，需添加到现有 `models.py`

### 1.4 回测引擎对比

#### v2.0 回测引擎 (`Backtester`)

**核心流程**:
```python
for kline in klines:
    # 1. 策略引擎运算
    attempts = runner.run_all(kline, higher_tf_trends)

    # 2. 信号持久化 (可选)
    for attempt in attempts:
        if attempt.final_result == "SIGNAL_FIRED":
            signal = calculate_risk(kline, attempt)
            repository.save_signal(signal, source="backtest")

    # 3. 胜率模拟 (简化版，基于止损距离启发式)
    win_rate = simulate_win_rate(attempts, subsequent_klines)
```

**特点**:
- **信号直接判定**: 回测输出为 `SignalResult` 列表，通过后续 K 线高低点模拟"是否触及止盈/止损"
- **无订单概念**: 不模拟订单挂单、成交、部分成交等状态
- **无仓位追踪**: 不计算 `Position.realized_pnl`，仅统计胜率
- **悲观假设**: `simulate_win_rate()` 采用"先判断止损、再判断止盈"的保守顺序

#### v3.0 回测引擎 (MockMatchingEngine)

**核心流程**:
```python
for kline in klines:
    # 1. 策略生成 Signal → 裂变 Order_Entry, Order_TP1, Order_SL
    orders = generate_orders_from_signal(signal)
    active_orders.extend(orders)

    # 2. 悲观撮合 (严格优先级：SL > TP > ENTRY)
    mock_matching_engine.match_orders_for_kline(
        kline, active_orders, positions_map, account
    )

    # 3. 风控状态机 (TP1 成交后推保护损)
    dynamic_risk_manager.evaluate_and_mutate(
        kline, position, active_orders
    )

    # 4. 仓位状态更新 (current_qty, realized_pnl)
    # 5. 账户净值采样 (account.total_balance)
```

**特点**:
- **订单驱动**: 回测核心为 `Order` 生命周期管理，信号仅作为意图输入
- **撮合优先级**: 严格遵循 `SL 优先 → TP 其次 → ENTRY 最后` 的判定顺序
- **滑点模拟**: 止损单成交价 = `trigger_price * (1 ± slippage_rate)`
- **仓位追踪**: 实时更新 `Position.current_qty` 和 `Position.realized_pnl`
- **账户累积**: `Account.total_balance` 累积已实现盈亏

**关键差异表**:

| 维度 | v2.0 | v3.0 |
|------|------|------|
| 核心抽象 | SignalResult | Order + Position |
| 撮合逻辑 | 简化胜率模拟 | 极端悲观撮合引擎 |
| 止盈处理 | 多级别价格字段 | 独立 Order_TP1 订单 |
| 止损处理 | 简化止损距离判断 | Order_SL 条件单 + 移动追踪 |
| 仓位计算 | 无 | Position.current_qty 动态缩减 |
| 盈亏追踪 | 无 | Position.realized_pnl 累积 |
| 滑点模拟 | 无 | 止损单加滑点 |

---

## 第二章：v3.0 与 v2.0 兼容性分析

### 2.1 完全兼容部分 (可直接复用)

#### 2.1.1 技术栈兼容

| 技术 | v2.0 使用方式 | v3.0 使用方式 | 兼容性 |
|------|--------------|--------------|--------|
| Pydantic v2 | 数据验证 + 序列化 | 数据验证 + 序列化 | ✅ 完全兼容 |
| Decimal | 金融精度计算 | 金融精度计算 | ✅ 完全兼容 |
| asyncio | 异步 I/O | 异步 I/O | ✅ 完全兼容 |
| FastAPI | REST API | REST API | ✅ 完全兼容 |
| SQLite + aiosqlite | 信号持久化 | 信号 + 订单 + 仓位持久化 | ✅ 完全兼容 |
| CCXT | 历史 K 线获取 | 历史 K 线 + 实盘订单 | ✅ 向后兼容 |

#### 2.1.2 领域层兼容

| 模块 | v2.0 实现 | v3.0 需求 | 兼容性评估 |
|------|----------|----------|-----------|
| `KlineData` | Pydantic v2 + Decimal | 相同 | ✅ 无需修改 |
| `Direction` | Enum (小写) | Enum (大写) | ⚠️ 需统一大小写 |
| `RiskCalculator` | 仓位计算 + 多级别止盈 | 相同 | ✅ 核心公式复用 |
| `LogicTree` | 递归逻辑树 | 相同 | ✅ 完全复用 |
| `FilterFactory` | 动态过滤器 | 相同 | ✅ 完全复用 |
| `PinbarStrategy` | 形态检测 + 评分 | 相同 | ✅ 完全复用 |

#### 2.1.3 基础设施层兼容

| 模块 | v2.0 实现 | v3.0 需求 | 兼容性评估 |
|------|----------|----------|-----------|
| `ExchangeGateway` | OHLCV 获取 + WebSocket | 相同 + 订单管理 | ⚠️ 需扩展订单接口 |
| `SignalRepository` | SQLite 信号表 | 相同 + Order/Position 表 | ⚠️ 需扩展 Schema |
| `Notifier` | 通知推送 | 相同 | ✅ 完全复用 |
| `Logger` | 统一日志 + 脱敏 | 相同 | ✅ 完全复用 |
| `ConfigManager` | 配置加载 + 热重载 | 相同 | ✅ 完全复用 |

### 2.2 部分兼容部分 (需适配改造)

#### 2.2.1 Signal 模型适配

**v2.0 `SignalResult`**:
```python
class SignalResult(BaseModel):
    symbol: str
    timeframe: str
    direction: Direction
    entry_price: Decimal
    suggested_stop_loss: Decimal
    suggested_position_size: Decimal
    current_leverage: int
    tags: List[Dict[str, str]]
    risk_reward_info: str
    status: str  # PENDING/WON/LOST
    pnl_ratio: float
    strategy_name: str
    score: float
    take_profit_levels: List[Dict[str, str]]  # 多级别止盈字段
```

**v3.0 `Signal`**:
```python
class Signal(FinancialModel):
    id: str
    strategy_id: str
    symbol: str
    direction: Direction
    timestamp: int
    expected_entry: Decimal
    expected_sl: Decimal
    pattern_score: float
    is_active: bool
```

**适配策略**:
1. **保留 `SignalResult`**: 作为"信号生成层"输出，兼容现有通知和前端展示
2. **新增 `Signal` 实体**: 作为"订单编排层"输入，增加 `id` 和 `is_active` 字段
3. **映射关系**: `SignalResult` → `Signal` + `Order_Entry` + `Order_TP1` + `Order_SL`

```python
def signal_result_to_orders(signal_result: SignalResult) -> Tuple[Signal, List[Order]]:
    """将 v2.0 SignalResult 转换为 v3.0 Signal + Orders"""
    signal = Signal(
        id=generate_id(),
        strategy_id=signal_result.strategy_name,
        symbol=signal_result.symbol,
        direction=signal_result.direction,
        timestamp=signal_result.kline_timestamp,
        expected_entry=signal_result.entry_price,
        expected_sl=signal_result.suggested_stop_loss,
        pattern_score=signal_result.score,
        is_active=True,
    )

    orders = [
        Order(
            id=generate_id(),
            signal_id=signal.id,
            symbol=signal_result.symbol,
            direction=signal_result.direction.opposite(),  # 平仓方向
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=signal_result.suggested_position_size,
            status=OrderStatus.PENDING,
        ),
        # TP1 orders from take_profit_levels
        # SL order
    ]

    return signal, orders
```

#### 2.2.2 Account 模型适配

**v2.0 `AccountSnapshot`**:
```python
class AccountSnapshot(BaseModel):
    total_balance: Decimal       # 瞬时快照
    available_balance: Decimal
    unrealized_pnl: Decimal
    positions: List[PositionInfo]  # 只读列表
    timestamp: int
```

**v3.0 `Account`**:
```python
class Account(FinancialModel):
    account_id: str
    total_balance: Decimal       # 主动累积盈亏
    frozen_margin: Decimal
    available_balance: Decimal   # 计算属性

    @property
    def available_balance(self) -> Decimal:
        return self.total_balance - self.frozen_margin
```

**适配策略**:
1. **保留 `AccountSnapshot`**: 用于接收交易所账户快照（只读）
2. **新增 `Account` 实体**: 用于内部 PMS 记账（主动累积）
3. **同步机制**: 实盘模式下，定期用 `AccountSnapshot` 校准 `Account.total_balance`

```python
class AccountManager:
    def __init__(self):
        self.internal_account = Account(total_balance=Decimal("10000"))

    async def sync_with_exchange(self, snapshot: AccountSnapshot):
        """用交易所快照校准内部账户"""
        self.internal_account.total_balance = snapshot.total_balance
        self.internal_account.frozen_margin = self._calculate_frozen_margin()
```

#### 2.2.3 回测引擎适配

**v2.0 回测引擎**需保留向后兼容接口，同时支持 v3.0 撮合模式：

```python
class Backtester:
    async def run_backtest(
        self,
        request: BacktestRequest,
        mode: Literal["v2_signal", "v3_pms"] = "v2_signal",  # 双模式支持
    ) -> BacktestReport:
        if mode == "v2_signal":
            return await self._run_v2_backtest(request)
        else:
            return await self._run_v3_pms_backtest(request)
```

### 2.3 不兼容部分 (需重构)

#### 2.3.1 订单编排层 (OrderManager)

**v2.0 缺失**, **v3.0 核心新增**

```python
class OrderManager:
    """订单编排与生命周期管理"""

    def __init__(self, signal: Signal):
        self.signal = signal
        self.orders: List[Order] = []

    def generate_initial_orders(
        self,
        entry_price: Decimal,
        stop_loss: Decimal,
        position_size: Decimal,
        take_profit_config: TakeProfitConfig,
    ) -> List[Order]:
        """
        从 Signal 裂变出初始订单组合

        订单编排策略:
        1. Order_Entry: 入场单 (市价)
        2. Order_TP1: 第一止盈单 (限价，50% 仓位)
        3. Order_SL: 初始止损单 (条件单，100% 仓位)
        """
        orders = [
            Order(
                id=generate_id(),
                signal_id=self.signal.id,
                symbol=self.signal.symbol,
                direction=self.signal.direction.opposite(),
                order_type=OrderType.MARKET,
                order_role=OrderRole.ENTRY,
                requested_qty=position_size,
                status=OrderStatus.PENDING,
            ),
        ]

        # 多级别止盈订单
        for tp_level in take_profit_config.levels:
            tp_order = Order(
                id=generate_id(),
                signal_id=self.signal.id,
                symbol=self.signal.symbol,
                direction=self.signal.direction.opposite(),
                order_type=OrderType.LIMIT,
                order_role=OrderRole.TP1,
                price=tp_level.price,
                requested_qty=position_size * tp_level.position_ratio,
                status=OrderStatus.OPEN,
            )
            orders.append(tp_order)

        # 初始止损单
        sl_order = Order(
            id=generate_id(),
            signal_id=self.signal.id,
            symbol=self.signal.symbol,
            direction=self.signal.direction.opposite(),
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            trigger_price=stop_loss,
            requested_qty=position_size,
            status=OrderStatus.OPEN,
        )
        orders.append(sl_order)

        return orders

    def cancel_order(self, order_id: str) -> None:
        """撤销订单"""
        for order in self.orders:
            if order.id == order_id:
                order.status = OrderStatus.CANCELED
                break

    def update_order_status(
        self,
        order_id: str,
        status: OrderStatus,
        filled_qty: Optional[Decimal] = None,
        average_exec_price: Optional[Decimal] = None,
    ) -> Order:
        """更新订单状态"""
        for order in self.orders:
            if order.id == order_id:
                order.status = status
                if filled_qty is not None:
                    order.filled_qty = filled_qty
                if average_exec_price is not None:
                    order.average_exec_price = average_exec_price
                return order
        raise ValueError(f"Order {order_id} not found")
```

#### 2.3.2 仓位状态机 (PositionManager)

**v2.0 缺失**, **v3.0 核心新增**

```python
class PositionManager:
    """仓位状态机与 P&L 追踪"""

    def __init__(self):
        self.positions: Dict[str, Position] = {}  # key: position_id

    def open_position(
        self,
        signal: Signal,
        entry_order: Order,
    ) -> Position:
        """开仓"""
        position = Position(
            id=generate_id(),
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=signal.direction,
            entry_price=entry_order.average_exec_price,
            current_qty=entry_order.filled_qty,
            highest_price_since_entry=entry_order.average_exec_price,
            realized_pnl=Decimal("0"),
            total_fees_paid=entry_order.fee_paid,
            is_closed=False,
        )
        self.positions[position.id] = position
        return position

    def reduce_position(
        self,
        position: Position,
        exit_order: Order,
    ) -> Decimal:
        """
        减仓 (TP1 成交或 SL 成交)

        核心逻辑:
        1. current_qty 缩减，entry_price 保持不变
        2. 计算该部分仓位的 Realized P&L
        3. 累加到 position.realized_pnl
        """
        if exit_order.direction == Direction.LONG:
            gross_pnl = (exit_order.average_exec_price - position.entry_price) * exit_order.filled_qty
        else:
            gross_pnl = (position.entry_price - exit_order.average_exec_price) * exit_order.filled_qty

        net_pnl = gross_pnl - exit_order.fee_paid

        # 更新仓位状态
        position.current_qty -= exit_order.filled_qty
        position.realized_pnl += net_pnl
        position.total_fees_paid += exit_order.fee_paid

        if position.current_qty <= Decimal("0"):
            position.is_closed = True

        return net_pnl

    def update_trailing_stop(
        self,
        position: Position,
        sl_order: Order,
        kline: KlineData,
        trailing_percent: Decimal,
        step_threshold: Decimal,
    ) -> bool:
        """
        更新移动止损 (Trailing Stop)

        返回: 是否实际更新了止损价
        """
        # 更新高水位线
        if position.direction == Direction.LONG:
            if kline.high > position.highest_price_since_entry:
                position.highest_price_since_entry = kline.high
        else:
            if kline.low < position.highest_price_since_entry:
                position.highest_price_since_entry = kline.low

        # 计算理论止损价
        if position.direction == Direction.LONG:
            theoretical_trigger = position.highest_price_since_entry * (1 - trailing_percent)
            min_required_price = sl_order.trigger_price * (1 + step_threshold)
            should_update = theoretical_trigger >= min_required_price
            if should_update:
                sl_order.trigger_price = max(position.entry_price, theoretical_trigger)
        else:
            theoretical_trigger = position.highest_price_since_entry * (1 + trailing_percent)
            min_required_price = sl_order.trigger_price * (1 - step_threshold)
            should_update = theoretical_trigger <= min_required_price
            if should_update:
                sl_order.trigger_price = min(position.entry_price, theoretical_trigger)

        return should_update
```

#### 2.3.3 悲观撮合引擎 (MockMatchingEngine)

**v2.0 缺失**, **v3.0 核心新增**

```python
class MockMatchingEngine:
    """极端悲观主义回测撮合引擎"""

    def __init__(
        self,
        slippage_rate: Decimal = Decimal("0.001"),  # 0.1%
        fee_rate: Decimal = Decimal("0.0004"),       # 0.04%
    ):
        self.slippage = slippage_rate
        self.fee_rate = fee_rate

    def match_orders_for_kline(
        self,
        kline: KlineData,
        active_orders: List[Order],
        positions_map: Dict[str, Position],
        account: Account,
    ) -> None:
        """
        K 线级悲观撮合入口

        撮合优先级 (严格顺序):
        1. SL / TRAILING_STOP (止损优先)
        2. TP1 (止盈其次)
        3. ENTRY (入场最后)
        """
        k_high, k_low = kline.high, kline.low

        # 按优先级排序
        sorted_orders = self._sort_orders_by_priority(active_orders)

        for order in sorted_orders:
            if order.status != OrderStatus.OPEN:
                continue

            position = positions_map.get(order.signal_id)

            # ========== 1. 处理止损单 ==========
            if order.order_type in [OrderType.STOP_MARKET, OrderType.TRAILING_STOP]:
                is_triggered = False
                exec_price = Decimal("0")

                if order.direction == Direction.LONG and k_low <= order.trigger_price:
                    is_triggered = True
                    exec_price = order.trigger_price * (1 - self.slippage)
                elif order.direction == Direction.SHORT and k_high >= order.trigger_price:
                    is_triggered = True
                    exec_price = order.trigger_price * (1 + self.slippage)

                if is_triggered:
                    self._execute_fill(order, exec_price, position, account)
                    self._cancel_related_orders(order.signal_id, active_orders)
                    continue

            # ========== 2. 处理止盈单 ==========
            elif order.order_type == OrderType.LIMIT and order.order_role == OrderRole.TP1:
                is_triggered = False
                exec_price = order.price

                if order.direction == Direction.LONG and k_high >= order.price:
                    is_triggered = True
                elif order.direction == Direction.SHORT and k_low <= order.price:
                    is_triggered = True

                if is_triggered:
                    self._execute_fill(order, exec_price, position, account)

            # ========== 3. 处理入场单 ==========
            elif order.order_type == OrderType.MARKET and order.order_role == OrderRole.ENTRY:
                # 市价单按 K 线开盘价成交 (简化)
                exec_price = kline.open
                self._execute_fill(order, exec_price, position, account)

    def _sort_orders_by_priority(self, orders: List[Order]) -> List[Order]:
        """按优先级排序：SL > TP > ENTRY"""
        priority_map = {
            OrderRole.SL: 0,
            OrderRole.TP1: 1,
            OrderRole.ENTRY: 2,
        }
        return sorted(orders, key=lambda o: priority_map.get(o.order_role, 99))

    def _execute_fill(
        self,
        order: Order,
        exec_price: Decimal,
        position: Position,
        account: Account,
    ) -> None:
        """执行订单成交结算"""
        order.status = OrderStatus.FILLED
        order.filled_qty = order.requested_qty
        order.average_exec_price = exec_price

        trade_value = exec_price * order.filled_qty
        fee_paid = trade_value * self.fee_rate

        if order.order_role in [OrderRole.TP1, OrderRole.SL]:
            # 计算已实现盈亏
            if position.direction == Direction.LONG:
                gross_pnl = (exec_price - position.entry_price) * order.filled_qty
            else:
                gross_pnl = (position.entry_price - exec_price) * order.filled_qty

            net_pnl = gross_pnl - fee_paid

            # 更新仓位
            position.current_qty -= order.filled_qty
            position.realized_pnl += net_pnl
            position.total_fees_paid += fee_paid

            if position.current_qty <= Decimal("0"):
                position.is_closed = True

            # 结算至账户
            account.total_balance += net_pnl
```

---

## 第三章：潜在冲突点与迁移成本

### 3.1 数据库 Schema 冲突

#### 现有 v2.0 Schema

```sql
-- signals 表
CREATE TABLE signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id     TEXT,
    symbol        TEXT NOT NULL,
    timeframe     TEXT NOT NULL,
    direction     TEXT NOT NULL,
    entry_price   TEXT NOT NULL,
    stop_loss     TEXT NOT NULL,
    position_size TEXT NOT NULL,
    leverage      INTEGER NOT NULL,
    tags_json     TEXT NOT NULL DEFAULT '[]',
    risk_info     TEXT NOT NULL,
    status        TEXT DEFAULT 'PENDING',
    pnl_ratio     TEXT,
    kline_timestamp INTEGER,
    take_profit_1 TEXT,
    closed_at     TEXT,
    created_at    TEXT NOT NULL
);

-- signal_attempts 表
CREATE TABLE signal_attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    strategy_name   TEXT NOT NULL,
    direction       TEXT,
    pattern_score   REAL,
    final_result    TEXT NOT NULL,
    filter_stage    TEXT,
    filter_reason   TEXT,
    details         TEXT NOT NULL,
    kline_timestamp INTEGER,
    evaluation_summary TEXT,
    trace_tree      JSON,
    created_at      TEXT NOT NULL
);
```

#### v3.0 需新增表

```sql
-- orders 表
CREATE TABLE orders (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id           TEXT UNIQUE NOT NULL,
    signal_id          TEXT NOT NULL,
    exchange_order_id  TEXT,
    symbol             TEXT NOT NULL,
    direction          TEXT NOT NULL,
    order_type         TEXT NOT NULL,
    order_role         TEXT NOT NULL,
    price              TEXT,
    trigger_price      TEXT,
    requested_qty      TEXT NOT NULL,
    filled_qty         TEXT NOT NULL DEFAULT '0',
    average_exec_price TEXT,
    status             TEXT NOT NULL DEFAULT 'PENDING',
    exit_reason        TEXT,
    created_at         INTEGER NOT NULL,
    updated_at         INTEGER NOT NULL,
    FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
);

-- positions 表
CREATE TABLE positions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id             TEXT UNIQUE NOT NULL,
    signal_id               TEXT NOT NULL,
    symbol                  TEXT NOT NULL,
    direction               TEXT NOT NULL,
    entry_price             TEXT NOT NULL,
    current_qty             TEXT NOT NULL,
    highest_price_since_entry TEXT NOT NULL,
    realized_pnl            TEXT NOT NULL DEFAULT '0',
    total_fees_paid         TEXT NOT NULL DEFAULT '0',
    is_closed               BOOLEAN NOT NULL DEFAULT FALSE,
    opened_at               INTEGER NOT NULL,
    closed_at               INTEGER,
    FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
);

-- accounts 表
CREATE TABLE accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      TEXT UNIQUE NOT NULL,
    total_balance   TEXT NOT NULL,
    frozen_margin   TEXT NOT NULL DEFAULT '0',
    updated_at      INTEGER NOT NULL
);
```

**迁移成本**:
- **中等**: 需新增 3 张表，但现有 `signals` 和 `signal_attempts` 表结构无需修改
- **风险点**: `Direction` 枚举大小写不一致，需在应用层统一

### 3.2 信号状态机冲突

#### v2.0 信号状态

```
GENERATED → PENDING → ACTIVE → FILLED/WON/LOST
              ↓
          SUPERSEDED (被更优信号覆盖)
```

#### v3.0 信号状态

```
生成 → 转化为订单 → 终结
```

**关键差异**:
- v2.0 信号有复杂的状态流转（ACTIVE/SUPERSEDED）
- v3.0 信号生命周期短暂，转化为订单后即终结

**适配策略**:
- 保留 v2.0 信号状态机用于前端展示和历史查询
- v3.0 信号作为内部临时实体，不持久化状态

### 3.3 回测结果统计冲突

#### v2.0 回测报告

```python
class BacktestReport(BaseModel):
    symbol: str
    timeframe: str
    candles_analyzed: int
    signal_stats: SignalStats  # 信号统计
    reject_reasons: Dict[str, int]  # 拒绝原因分布
    simulated_win_rate: float  # 模拟胜率 (启发式)
    simulated_avg_gain: float
    simulated_avg_loss: float
    attempts: List[Dict[str, Any]]  # 详细尝试记录
```

#### v3.0 回测报告 (预期)

```python
class PMSBacktestReport(BaseModel):
    symbol: str
    timeframe: str
    candles_analyzed: int
    total_trades: int  # 总交易数
    winning_trades: int
    losing_trades: int
    win_rate: float  # 真实胜率 (基于撮合)
    total_pnl: Decimal  # 总盈亏
    max_drawdown: Decimal  # 最大回撤
    sharpe_ratio: float  # 夏普比率
    positions: List[Position]  # 仓位历史
    account_curve: List[Decimal]  # 账户净值曲线
```

**适配策略**:
- 保留 `BacktestReport` 用于 v2.0 模式
- 新增 `PMSBacktestReport` 用于 v3.0 模式
- 前端支持两种报告格式的展示切换

### 3.4 枚举值大小写冲突

**问题**: v2.0 `Direction` 使用小写 (`long`/`short`)，v3.0 使用大写 (`LONG`/`SHORT`)

**影响范围**:
- 数据库中已存储的 `direction` 字段 (v2.0 为小写)
- 前端展示和筛选逻辑

**解决方案**:

**方案 A: 数据库迁移 (推荐)**
```sql
UPDATE signals SET direction = UPPER(direction) WHERE direction IN ('long', 'short');
```

**方案 B: 应用层兼容**
```python
class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

    @classmethod
    def from_string(cls, value: str) -> "Direction":
        """兼容大小写输入"""
        return cls[value.upper()]
```

**建议**: 采用方案 A，一次性迁移数据库，后续统一使用大写。

### 3.5 多级别止盈逻辑冲突

#### v2.0 实现

```python
# RiskCalculator.calculate_take_profit_levels()
def calculate_take_profit_levels(...) -> List[Dict[str, str]]:
    """计算多级别止盈价格 (仅数据字段)"""
    levels = []
    for level in config.levels:
        tp_price = entry_price + (stop_distance * level.risk_reward)
        levels.append({
            "id": level.id,
            "position_ratio": str(level.position_ratio),
            "risk_reward": str(level.risk_reward),
            "price": str(quantized_price),
        })
    return levels
```

**特点**: `take_profit_levels` 仅为 `SignalResult` 的字段，无独立生命周期管理

#### v3.0 实现

```python
# OrderManager.generate_initial_orders()
def generate_tp_orders(...) -> List[Order]:
    """生成独立 TP 订单 (有生命周期)"""
    orders = []
    for level in config.levels:
        orders.append(Order(
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            price=level.price,
            requested_qty=position_size * level.position_ratio,
            status=OrderStatus.OPEN,
        ))
    return orders
```

**特点**: TP 为独立 `Order` 实体，有 `OPEN → FILLED` 状态流转

**适配策略**:
- v2.0 模式：`take_profit_levels` 字段用于前端展示
- v3.0 模式：TP 订单用于回测撮合和实盘执行

---

## 第四章：v3.0 设计合理性与可行性评估

### 4.1 架构合理性

#### 4.1.1 "三重解耦"评估

| 解耦维度 | v2.0 状态 | v3.0 改进 | 合理性评分 |
|----------|----------|----------|-----------|
| 意图与执行 | Signal 承担双重职责 | Signal 仅记录意图，Order 负责执行 | ⭐⭐⭐⭐⭐ |
| 执行与状态 | 无 Order 概念 | Order 一次性动作，Position 持久化状态 | ⭐⭐⭐⭐⭐ |
| 回测与实盘 | 回测简化模拟 | 统一 Order/Position，环境适配器切换 | ⭐⭐⭐⭐⭐ |

**结论**: v3.0 "三重解耦"设计高度合理，符合领域驱动设计 (DDD) 原则。

#### 4.1.2 PMS 模型评估

**v3.0 Position 设计**:
```python
class Position:
    entry_price: Decimal           # 开仓均价 (固定不变)
    current_qty: Decimal           # 当前体积 (动态缩减)
    highest_price_since_entry: Decimal  # 高水位线
    realized_pnl: Decimal          # 已实现盈亏 (累积)
```

**行业对标**:
- 与币安/Bybit 等交易所仓位模型一致
- `entry_price` 固定不变是业界标准做法（减仓时不重新计算均价）
- `realized_pnl` 累积方便统计单笔交易总盈亏

**结论**: PMS 模型设计符合业界标准，合理可行。

### 4.2 技术可行性

#### 4.2.1 悲观撮合引擎

**v3.0 撮合逻辑**:
```
K 线内判定顺序：SL 优先 → TP 其次 → ENTRY 最后
止损成交价：trigger_price * (1 ± slippage_rate)
```

**合理性验证**:

| 场景 | v2.0 处理 | v3.0 处理 | 评估 |
|------|----------|----------|------|
| 同一 K 线同时触及 SL 和 TP | 简化胜率模拟 (启发式) | SL 优先成交，TP 撤销 | ✅ 更保守准确 |
| 止损滑点 | 无模拟 | trigger_price * (1 ± 滑点) | ✅ 更真实 |
| 部分成交 | 不支持 | `requested_qty` vs `filled_qty` | ✅ 支持 |

**结论**: 悲观撮合引擎逻辑严谨，技术可行。

#### 4.2.2 动态风控状态机

**v3.0 状态转移**:
```
TP1 成交 → 缩减 SL 单数量 → 上移 SL 触发价至开仓价 → 激活 Trailing 属性
```

**关键设计点**:
1. **推保护损 (Breakeven)**: TP1 成交后 SL 触发价 = `entry_price`，确保零风险
2. **阶梯阈值 (Step Threshold)**: 新止损价必须比旧止损价高出 `step_threshold` 才更新，防止 API 频率超限
3. **高水位线追踪**: 多头 `highest_price_since_entry` 只增不减，空头只减不增

**结论**: 状态机设计完整，阶梯阈值设计有效规避实盘 API 限流风险。

### 4.3 迁移风险评估

| 风险类别 | 风险等级 | 缓解措施 |
|----------|----------|----------|
| 数据库 Schema 变更 | 低 | 新增表，不影响现有表 |
| 枚举值大小写 | 中 | 一次性数据库迁移 |
| 回测结果不一致 | 中 | 双模式并行，对比验证 |
| 实盘订单状态同步 | 高 | 启动时对账 (Reconciliation) |
| 并发脏写 | 高 | Asyncio Lock + 数据库行级锁 |

**整体评估**: 迁移风险可控，关键是采用渐进式迁移策略。

---

## 第五章：迁移路径建议

### 5.1 迁移原则

1. **向后兼容**: v2.0 功能必须保留，v3.0 作为可选模式
2. **双轨并行**: 回测和实盘同时支持 v2/v3 两种模式
3. **渐进替换**: 先实现 PMS 模型与 v2.0 并行，验证后逐步切换
4. **数据完整性**: 迁移过程中确保历史数据可追溯

### 5.2 迁移阶段划分

#### 阶段 1: 模型筑基 (2 周)

**目标**: 实现 v3.0 核心模型，不改动现有业务逻辑

**任务清单**:
- [ ] 新增 `Order`, `Position`, `Account` 实体类到 `src/domain/models.py`
- [ ] 新增 `OrderStatus`, `OrderType`, `OrderRole` 枚举
- [ ] 统一 `Direction` 枚举为大写 (数据库迁移脚本)
- [ ] 数据库新增 `orders`, `positions`, `accounts` 表
- [ ] 单元测试覆盖新模型

**验收标准**:
- 新模型通过 Pydantic v2 验证
- 数据库迁移脚本可回滚
- 单元测试覆盖率 ≥ 90%

#### 阶段 2: 撮合引擎 (3 周)

**目标**: 实现悲观撮合引擎，支持 v3.0 回测模式

**任务清单**:
- [ ] 实现 `MockMatchingEngine` 类
- [ ] 实现订单优先级排序逻辑
- [ ] 实现滑点和手续费计算
- [ ] 实现 `_execute_fill` 仓位同步逻辑
- [ ] 新增 `PMSBacktestReport` 模型
- [ ] `Backtester` 支持 `mode="v3_pms"` 参数
- [ ] 回测对比验证 (v2 vs v3)

**验收标准**:
- v3.0 回测报告包含真实盈亏统计
- 同一策略 v2/v3 回测结果差异可解释
- 单元测试覆盖撮合边界 case

#### 阶段 3: 风控状态机 (2 周)

**目标**: 实现动态风控状态机

**任务清单**:
- [ ] 实现 `DynamicRiskManager` 类
- [ ] 实现 TP1 成交后推保护损逻辑
- [ ] 实现移动止损 (Trailing) 计算
- [ ] 实现阶梯阈值频控
- [ ] 单元测试覆盖状态转移

**验收标准**:
- TP1 成交后 SL 自动上移至开仓价
- Trailing 止损随高水位线动态调整
- 阶梯阈值有效限制更新频率

#### 阶段 4: 订单编排 (2 周)

**目标**: 实现 OrderManager 订单编排层

**任务清单**:
- [ ] 实现 `OrderManager` 类
- [ ] 实现 `Signal` → `Orders` 裂变逻辑
- [ ] 实现订单撤销和状态更新
- [ ] `SignalPipeline` 集成 OrderManager
- [ ] 实盘模式下调用 CCXT 发单

**验收标准**:
- 信号生成后自动裂变 3 个订单 (Entry/TP1/SL)
- 订单状态与交易所同步
- 支持订单撤销

#### 阶段 5: 实盘集成 (3 周)

**目标**: 实盘模式支持 v3.0 PMS

**任务清单**:
- [ ] `ExchangeGateway` 扩展订单管理接口
- [ ] 实现 `watch_orders` WebSocket 推送处理
- [ ] 实现启动时对账 (Reconciliation)
- [ ] 实现 Asyncio Lock 并发保护
- [ ] 实现数据库行级锁
- [ ] 端到端测试 (回测→模拟盘→实盘)

**验收标准**:
- 实盘订单状态实时同步
- 断网重启后仓位状态一致
- 无并发脏写问题

#### 阶段 6: 前端适配 (2 周)

**目标**: 前端支持 v3.0 仓位展示

**任务清单**:
- [ ] 仓位管理页面 (持仓/历史仓位)
- [ ] 订单管理页面 (挂单/成交)
- [ ] 回测报告新增 PMS 模式展示
- [ ] 账户净值曲线可视化
- [ ] 多级别止盈可视化

**验收标准**:
- 前端展示仓位盈亏与后端一致
- 回测报告支持 v2/v3 切换
- 用户体验无降级

### 5.3 回滚策略

**阶段 1-3**: 无风险，v2.0 功能不受影响

**阶段 4-5**:
- 配置开关 `enable_pms_mode: false` 可回退到 v2.0 模式
- 数据库新增表可保留，不影响查询

**阶段 6**:
- 前端版本回滚

### 5.4 迁移时间估算

| 阶段 | 工期 | 累计 |
|------|------|------|
| 阶段 1: 模型筑基 | 2 周 | 2 周 |
| 阶段 2: 撮合引擎 | 3 周 | 5 周 |
| 阶段 3: 风控状态机 | 2 周 | 7 周 |
| 阶段 4: 订单编排 | 2 周 | 9 周 |
| 阶段 5: 实盘集成 | 3 周 | 12 周 |
| 阶段 6: 前端适配 | 2 周 | 14 周 |

**总工期**: 约 14 周 (3.5 个月)

---

## 第六章：总结与建议

### 6.1 核心结论

1. **v3.0 设计质量**: 架构设计严谨，符合 DDD 原则和业界标准，技术可行性高。

2. **兼容性评估**: v3.0 与 v2.0 技术栈高度兼容，核心差异在于引入 Order/Position 独立实体。

3. **迁移成本**: 中等偏高 (14 周工期)，主要工作量为新增模块开发，而非重构现有代码。

4. **风险等级**: 可控，采用渐进式迁移策略可将风险降至最低。

### 6.2 战略建议

#### 6.2.1 优先级建议

**P0 (必须实现)**:
- 阶段 1-3: 模型 + 撮合引擎 + 风控状态机（回测精度提升）
- 阶段 5 部分: 并发保护 (避免脏写)

**P1 (强烈推荐)**:
- 阶段 4: 订单编排 (实盘基础)
- 阶段 5 剩余: 实盘集成

**P2 (可选)**:
- 阶段 6: 前端可视化增强

#### 6.2.2 资源投入建议

| 角色 | 阶段 1-3 | 阶段 4-5 | 阶段 6 |
|------|---------|---------|--------|
| 后端开发 | 2 人 | 2 人 | 0.5 人 |
| 前端开发 | 0 | 0.5 人 | 1 人 |
| QA 测试 | 0.5 人 | 1 人 | 1 人 |

#### 6.2.3 技术债务预防

1. **代码审查红线**:
   - 新 `Order`/`Position` 代码必须通过领域层纯净性检查 (无 I/O 依赖)
   - 所有金额计算必须使用 `Decimal`

2. **测试覆盖要求**:
   - 撮合引擎边界 case 100% 覆盖
   - 状态转移逻辑 100% 覆盖

3. **文档同步更新**:
   - `CLAUDE.md` 更新 v3.0 模型说明
   - 新增 `docs/v3/` 目录存放详细设计

### 6.3 最终建议

**立即启动阶段 1 开发**，理由如下:

1. **技术成熟度**: v3.0 设计文档完整，核心逻辑已验证
2. **业务价值**: 提升回测精度，为实盘执行奠定基础
3. **风险可控**: 渐进式迁移，v2.0 功能不受影响
4. **团队能力**: 当前团队熟悉 Pydantic v2 + Decimal 技术栈

---

## 附录 A: 关键代码片段参考

### A.1 v2.0 与 v3.0 模型并存方案

```python
# src/domain/models.py

# ========== 保留 v2.0 模型 (向后兼容) ==========

class SignalResult(BaseModel):
    """v2.0 信号输出模型 (保留用于通知和前端展示)"""
    symbol: str
    timeframe: str
    direction: Direction
    entry_price: Decimal
    suggested_stop_loss: Decimal
    suggested_position_size: Decimal
    current_leverage: int
    tags: List[Dict[str, str]]
    risk_reward_info: str
    status: str
    pnl_ratio: float
    strategy_name: str
    score: float
    take_profit_levels: List[Dict[str, str]]


# ========== 新增 v3.0 模型 ==========

class Signal(FinancialModel):
    """v3.0 信号实体 (意图层)"""
    id: str
    strategy_id: str
    symbol: str
    direction: Direction
    timestamp: int
    expected_entry: Decimal
    expected_sl: Decimal
    pattern_score: float
    is_active: bool = True


class Order(FinancialModel):
    """v3.0 订单实体 (执行层)"""
    id: str
    signal_id: str
    exchange_order_id: Optional[str] = None
    symbol: str
    direction: Direction
    order_type: OrderType
    order_role: OrderRole
    price: Optional[Decimal] = None
    trigger_price: Optional[Decimal] = None
    requested_qty: Decimal
    filled_qty: Decimal = Field(default=Decimal("0"))
    average_exec_price: Optional[Decimal] = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: int
    updated_at: int
    exit_reason: Optional[str] = None


class Position(FinancialModel):
    """v3.0 仓位实体 (资产层)"""
    id: str
    signal_id: str
    symbol: str
    direction: Direction
    entry_price: Decimal
    current_qty: Decimal
    highest_price_since_entry: Decimal
    realized_pnl: Decimal = Field(default=Decimal("0"))
    total_fees_paid: Decimal = Field(default=Decimal("0"))
    is_closed: bool = False


class Account(FinancialModel):
    """v3.0 账户实体 (资产池)"""
    account_id: str = "default_wallet"
    total_balance: Decimal = Field(default=Decimal("0"))
    frozen_margin: Decimal = Field(default=Decimal("0"))

    @property
    def available_balance(self) -> Decimal:
        return self.total_balance - self.frozen_margin
```

### A.2 适配器模式：v2.0 SignalResult → v3.0 Orders

```python
# src/application/adapters/signal_adapter.py

from typing import Tuple, List
from src.domain.models import SignalResult, Signal, Order, OrderType, OrderRole, OrderStatus
from decimal import Decimal


class SignalToOrderAdapter:
    """将 v2.0 SignalResult 转换为 v3.0 Signal + Orders"""

    def __init__(self, take_profit_config: TakeProfitConfig):
        self.tp_config = take_profit_config

    def convert(
        self,
        signal_result: SignalResult,
    ) -> Tuple[Signal, List[Order]]:
        """转换 SignalResult 为 Signal + 初始订单组合"""

        # 1. 创建 Signal (意图层)
        signal = Signal(
            id=self._generate_id(),
            strategy_id=signal_result.strategy_name,
            symbol=signal_result.symbol,
            direction=signal_result.direction,
            timestamp=signal_result.kline_timestamp,
            expected_entry=signal_result.entry_price,
            expected_sl=signal_result.suggested_stop_loss,
            pattern_score=signal_result.score,
            is_active=True,
        )

        # 2. 创建初始订单组合
        orders = self._generate_orders(signal, signal_result)

        return signal, orders

    def _generate_orders(
        self,
        signal: Signal,
        signal_result: SignalResult,
    ) -> List[Order]:
        """从 Signal 生成 Entry + TP + SL 订单"""
        orders = []
        now = int(datetime.now(timezone.utc).timestamp() * 1000)

        # Entry 订单 (市价单)
        entry_order = Order(
            id=self._generate_id(),
            signal_id=signal.id,
            exchange_order_id=None,
            symbol=signal.symbol,
            direction=self._opposite_direction(signal.direction),
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            price=None,
            trigger_price=None,
            requested_qty=signal_result.suggested_position_size,
            filled_qty=Decimal("0"),
            average_exec_price=None,
            status=OrderStatus.PENDING,
            created_at=now,
            updated_at=now,
            exit_reason=None,
        )
        orders.append(entry_order)

        # TP 订单 (限价单)
        for tp_level_data in signal_result.take_profit_levels:
            tp_order = Order(
                id=self._generate_id(),
                signal_id=signal.id,
                exchange_order_id=None,
                symbol=signal.symbol,
                direction=self._opposite_direction(signal.direction),
                order_type=OrderType.LIMIT,
                order_role=OrderRole.TP1,
                price=Decimal(tp_level_data["price"]),
                trigger_price=None,
                requested_qty=signal_result.suggested_position_size * Decimal(tp_level_data["position_ratio"]),
                filled_qty=Decimal("0"),
                average_exec_price=None,
                status=OrderStatus.OPEN,
                created_at=now,
                updated_at=now,
                exit_reason=None,
            )
            orders.append(tp_order)

        # SL 订单 (条件单)
        sl_order = Order(
            id=self._generate_id(),
            signal_id=signal.id,
            exchange_order_id=None,
            symbol=signal.symbol,
            direction=self._opposite_direction(signal.direction),
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            price=None,
            trigger_price=signal_result.suggested_stop_loss,
            requested_qty=signal_result.suggested_position_size,
            filled_qty=Decimal("0"),
            average_exec_price=None,
            status=OrderStatus.OPEN,
            created_at=now,
            updated_at=now,
            exit_reason=None,
        )
        orders.append(sl_order)

        return orders

    def _generate_id(self) -> str:
        """生成唯一 ID"""
        import uuid
        return str(uuid.uuid4())

    def _opposite_direction(self, direction: Direction) -> Direction:
        """获取相反方向 (用于平仓订单)"""
        return Direction.SHORT if direction == Direction.LONG else Direction.LONG
```

---

## 附录 B: 迁移检查清单

### B.1 开发阶段检查清单

**阶段 1: 模型筑基**
- [ ] 新增 `Order`, `Position`, `Account` 类
- [ ] 新增 `OrderStatus`, `OrderType`, `OrderRole` 枚举
- [ ] 统一 `Direction` 为大写
- [ ] 数据库迁移脚本编写
- [ ] 单元测试编写

**阶段 2: 撮合引擎**
- [ ] `MockMatchingEngine` 实现
- [ ] 订单优先级排序
- [ ] 滑点计算
- [ ] `PMSBacktestReport` 模型
- [ ] `Backtester` 支持 v3 模式
- [ ] v2/v3 回测对比测试

**阶段 3: 风控状态机**
- [ ] `DynamicRiskManager` 实现
- [ ] 推保护损逻辑
- [ ] 移动止损逻辑
- [ ] 阶梯阈值频控
- [ ] 单元测试

**阶段 4: 订单编排**
- [ ] `OrderManager` 实现
- [ ] Signal→Orders 裂变
- [ ] 订单撤销逻辑
- [ ] `SignalPipeline` 集成

**阶段 5: 实盘集成**
- [ ] `ExchangeGateway` 订单接口
- [ ] `watch_orders` WebSocket 处理
- [ ] 启动时对账
- [ ] Asyncio Lock
- [ ] 端到端测试

**阶段 6: 前端适配**
- [ ] 仓位管理页面
- [ ] 订单管理页面
- [ ] PMS 回测报告展示
- [ ] 净值曲线

### B.2 Code Review 检查清单

**领域层纯净性**:
- [ ] `domain/` 目录无 I/O 依赖 (ccxt, aiohttp, requests, fastapi, yaml)
- [ ] 所有金额计算使用 `Decimal`
- [ ] Pydantic 模型使用 `ConfigDict(arbitrary_types_allowed=True, extra="forbid")`

**类型安全**:
- [ ] 无 `Dict[str, Any]` 滥用
- [ ] 多态对象使用 `discriminator='type'`
- [ ] 枚举值统一大小写

**并发安全**:
- [ ] 仓位修改使用 Asyncio Lock
- [ ] 数据库更新使用行级锁
- [ ] 订单状态更新原子性

**日志脱敏**:
- [ ] API 密钥使用 `mask_secret()` 脱敏
- [ ] 无敏感信息明文日志

---

**文档结束**
