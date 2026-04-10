# Phase 5: 实盘集成 - 详细设计文档

**创建日期**: 2026-03-30
**状态**: ✅ Gemini 评审通过，待用户确认
**版本**: v1.1
**评审意见**: Gemini 审查报告 (2026-03-30)

---

## 修订记录 (v1.1)

| 编号 | 问题 | 严重性 | 修复方案 | 状态 |
|------|------|--------|----------|------|
| **G-001** | asyncio.Lock"释放后使用"竞态条件 | 🔴 致命 | 改用 `WeakValueDictionary` 或放弃主动释放 | ✅ 已修复 |
| **G-002** | 市价单 (MARKET) 价格缺失导致 TypeError | 🔴 致命 | 引入 `expected_price`，调用 `fetch_ticker_price` | ✅ 已修复 |
| **G-003** | DCA 限价单"吃单"陷阱（滑点 + 高手续费） | 🟡 高 | 改为"提前预埋限价单"，一次性挂单 | ✅ 已修复 |
| **G-004** | 对账系统"幽灵偏差"（REST vs WebSocket 时差） | 🟡 中 | 加入 5-10 秒 Grace Period 宽限期二次校验 | ✅ 已修复 |

---

---

## 一、设计目标

将 v3 PMS 系统从回测沙箱扩展到真实交易所实盘，实现：
1. 订单执行能力（下单/取消/查询）
2. 并发安全保障（双层锁机制）
3. 资金安全保护（多层限制）
4. 状态一致性（对账服务）
5. DCA 分批建仓策略
6. 飞书告警通知

---

## 二、系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                      Phase 5 实盘集成架构                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌───────────────┐     ┌───────────────┐     ┌───────────────┐ │
│  │  前端工作台   │────▶│  FastAPI 接口  │────▶│ SignalPipeline│ │
│  └───────────────┘     └───────────────┘     └───────┬───────┘ │
│                                                       │         │
│                      ┌────────────────────────────────┘         │
│                      ▼                                          │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                   核心服务层                               │ │
│  ├───────────────────────────────────────────────────────────┤ │
│  │ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │ │
│  │ │OrderManager │ │RiskManager  │ │DcaStrategy  │          │ │
│  │ └─────────────┘ └─────────────┘ └─────────────┘          │ │
│  │ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │ │
│  │ │CapitalProt. │ │Reconciliation│ │FeishuNotif. │          │ │
│  │ └─────────────┘ └─────────────┘ └─────────────┘          │ │
│  └───────────────────────────────────────────────────────────┘ │
│                      │                                          │
│                      ▼                                          │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                   基础设施层                               │ │
│  ├───────────────────────────────────────────────────────────┤ │
│  │ ┌─────────────────────────┐ ┌─────────────────────────┐   │ │
│  │ │   ExchangeGateway       │ │   SignalRepository      │   │ │
│  │ │  - place_order          │ │  - save_order           │   │ │
│  │ │  - cancel_order         │ │  - update_order         │   │ │
│  │ │  - fetch_order          │ │  - query_positions      │   │ │
│  │ │  - watch_orders (WS)    │ │  - reconciliation       │   │ │
│  │ └─────────────────────────┘ └─────────────────────────┘   │ │
│  └───────────────────────────────────────────────────────────┘ │
│                      │                                          │
│                      ▼                                          │
│              ┌───────────────┐                                  │
│              │  Binance API  │                                  │
│              │  (Testnet/Prod)│                                 │
│              └───────────────┘                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、核心模块设计

### 3.1 ExchangeGateway 扩展

#### 3.1.1 接口定义

```python
# src/infrastructure/exchange_gateway.py

class ExchangeGateway:
    # ========== 现有方法 ==========
    # - initialize()
    # - fetch_historical_ohlcv()
    # - subscribe_ohlcv()
    # - start_asset_polling()

    # ========== Phase 5 新增方法 ==========

    async def place_order(
        self,
        symbol: str,
        order_type: str,           # "market", "limit", "stop_market"
        side: str,                 # "buy" (开多/平空), "sell" (开空/平多)
        amount: Decimal,           # 数量
        price: Optional[Decimal] = None,      # 限价单价格
        trigger_price: Optional[Decimal] = None,  # 条件单触发价
        reduce_only: bool = False,  # 仅减仓（平仓单必须设置）
        client_order_id: Optional[str] = None,  # 客户端订单 ID
    ) -> OrderPlacementResult:
        """
        下单接口

        返回:
            OrderPlacementResult: 包含订单 ID、状态、错误信息
        """

    async def cancel_order(self, order_id: str, symbol: str) -> OrderCancelResult:
        """
        取消订单

        返回:
            OrderCancelResult: 包含取消结果
        """

    async def fetch_order(self, order_id: str, symbol: str) -> Order:
        """
        查询订单状态

        返回:
            Order: 订单对象
        """

    async def watch_orders(self, symbol: str, callback: Callable) -> None:
        """
        WebSocket 监听订单推送

        回调参数：
            Order: 更新后的订单对象
        """
```

#### 3.1.2 订单类型映射

| 本系统 | CCXT | Binance |
|--------|------|---------|
| `MARKET` | `"market"` | `"MARKET"` |
| `LIMIT` | `"limit"` | `"LIMIT"` |
| `STOP_MARKET` | `"stop"`/`"stop_market"` | `"STOP_MARKET"` |
| `TRAILING_STOP` | 自定义逻辑 | 需轮询更新 |

#### 3.1.3 错误处理

```python
# src/domain/exceptions.py

class InsufficientMarginError(TradingError):
    """保证金不足"""
    code = "F-010"

class InvalidOrderError(TradingError):
    """订单参数错误"""
    code = "F-011"

class OrderNotFoundError(TradingError):
    """订单不存在"""
    code = "F-012"

class OrderAlreadyFilledError(TradingError):
    """订单已成交"""
    code = "F-013"

class RateLimitError(TradingError):
    """API 频率限制"""
    code = "C-010"
```

---

### 3.2 并发保护机制

#### 3.2.1 双层锁设计

**修复 G-001**: 使用 `WeakValueDictionary` 避免"释放后使用"竞态条件

```python
# src/application/position_manager.py

import weakref

class PositionManager:
    def __init__(self, db: AsyncSession):
        self._db = db
        # ✅ 修复：使用弱引用字典，当没有任何协程持有/等待该锁时，Python GC 会自动回收
        # 不再需要主动清理，避免 Use-After-Free 竞态条件
        self._position_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self._locks_mutex = asyncio.Lock()  # 保护_locks 字典的锁

    async def _get_position_lock(self, position_id: str) -> asyncio.Lock:
        """
        获取或创建仓位锁

        修复 G-001 关键点:
        - 使用 WeakValueDictionary，锁在没有引用时自动回收
        - 不主动删除锁，避免"释放后使用"问题
        """
        async with self._locks_mutex:
            if position_id not in self._position_locks:
                lock = asyncio.Lock()
                # 弱引用：必须先保存在局部变量，否则立即被 GC
                self._position_locks[position_id] = lock
            return self._position_locks[position_id]

    async def reduce_position(
        self,
        position_id: str,
        exit_order: Order,
    ) -> Decimal:
        """
        减仓处理（TP1 成交或 SL 成交）

        并发保护:
        1. Asyncio Lock - 单进程内协程同步
        2. 数据库行级锁 - 跨进程保护
        """
        # ========== 第一层：Asyncio Lock (进程内) ==========
        position_lock = await self._get_position_lock(position_id)
        async with position_lock:

            # ========== 第二层：数据库行级锁 (跨进程) ==========
            async with self._db.begin():
                # SQLite: BEGIN EXCLUSIVE
                # PostgreSQL: SELECT ... FOR UPDATE
                position = await self._fetch_position_locked(position_id)

                if position is None:
                    raise ValueError(f"Position {position_id} not found")

                # 临界区：仓位状态修改
                if exit_order.direction == Direction.LONG:
                    gross_pnl = (exit_order.average_exec_price - position.entry_price) * exit_order.filled_qty
                else:
                    gross_pnl = (position.entry_price - exit_order.average_exec_price) * exit_order.filled_qty

                net_pnl = gross_pnl - exit_order.fee_paid

                # 原子更新
                position.current_qty -= exit_order.filled_qty
                position.realized_pnl += net_pnl
                position.total_fees_paid += exit_order.fee_paid

                if position.current_qty <= Decimal("0"):
                    position.is_closed = True
                    position.closed_at = int(time.time() * 1000)

                await self._session.merge(position)

                # ✅ 修复：不再主动删除锁！WeakValueDictionary 会在无引用时自动回收
                # if position_id in self._position_locks:
                #     del self._position_locks[position_id]  # ❌ 危险操作

                return net_pnl
```

---

### 3.3 启动对账服务

#### 3.3.1 对账流程

**修复 G-004**: 加入 Grace Period 宽限期避免"幽灵偏差"

```python
# src/application/reconciliation.py

class ReconciliationService:
    def __init__(
        self,
        exchange_gateway: ExchangeGateway,
        position_manager: PositionManager,
        order_manager: OrderManager,
    ):
        self._gateway = exchange_gateway
        self._position_mgr = position_manager
        self._order_mgr = order_manager
        self._grace_period_seconds = 10  # G-004 修复：10 秒宽限期

    async def run_reconciliation(self, symbol: str) -> ReconciliationReport:
        """
        启动对账服务

        修复 G-004 关键点:
        - REST API 和 WebSocket 之间存在时差
        - 对账差异不立即判定为异常，先加入宽限期
        - 宽限期后二次校验，确认是否为真实异常
        """
        report = ReconciliationReport()

        # ===== 仓位对账 =====
        local_positions = await self._get_local_positions(symbol)
        exchange_positions = await self._get_exchange_positions(symbol)

        for ex_pos in exchange_positions:
            local_pos = self._find_position(local_positions, ex_pos.symbol)
            if local_pos is None:
                # 交易所有仓位，本地没有 → 加入待确认列表
                report.pending_missing_positions.append({
                    "position": ex_pos,
                    "found_at": int(time.time() * 1000),
                    "confirmed": False
                })
            elif local_pos.current_qty != ex_pos.current_qty:
                # 数量不一致 → 加入待确认列表
                report.pending_position_mismatches.append({
                    "symbol": ex_pos.symbol,
                    "local_qty": local_pos.current_qty,
                    "exchange_qty": ex_pos.current_qty,
                    "found_at": int(time.time() * 1000),
                    "confirmed": False
                })

        # ===== 订单对账 =====
        local_orders = await self._get_local_open_orders(symbol)
        exchange_orders = await self._get_exchange_open_orders(symbol)

        for ex_order in exchange_orders:
            local_order = self._find_order(local_orders, ex_order.exchange_order_id)
            if local_order is None:
                # 孤儿订单 → 加入待确认列表
                report.pending_orphan_orders.append({
                    "order": ex_order,
                    "found_at": int(time.time() * 1000),
                    "confirmed": False
                })
            elif local_order.status != self._map_status(ex_order.status):
                # 状态不一致 → 加入待确认列表
                report.pending_order_mismatches.append({
                    "order_id": ex_order.order_id,
                    "local_status": local_order.status,
                    "exchange_status": ex_order.status,
                    "found_at": int(time.time() * 1000),
                    "confirmed": False
                })

        # ===== 二次校验：处理宽限期后仍存在的差异 =====
        await self._verify_pending_items(report)

        # 将确认的差异移动到正式列表
        for item in report.pending_missing_positions:
            if item["confirmed"]:
                report.missing_positions.append(item["position"])
        for item in report.pending_position_mismatches:
            if item["confirmed"]:
                report.position_mismatches.append(item)
        for item in report.pending_orphan_orders:
            if item["confirmed"]:
                report.orphan_orders.append(item["order"])
        for item in report.pending_order_mismatches:
            if item["confirmed"]:
                report.order_mismatches.append(item)

        return report

    async def _verify_pending_items(self, report: ReconciliationReport) -> None:
        """
        二次校验：宽限期后重新检查待确认项目

        G-004 修复核心逻辑:
        1. 等待 10 秒 Grace Period
        2. 重新获取交易所和本地状态
        3. 如果差异仍然存在，确认为真实异常
        4. 如果差异消失，说明是 WebSocket 延迟，记录日志即可
        """
        await asyncio.sleep(self._grace_period_seconds)

        for item in report.pending_missing_positions:
            if not item["confirmed"]:
                # 二次检查...
                item["confirmed"] = await self._recheck_position(item["position"])

        # ... 其他待确认项目同理
```

        return report

    async def handle_orphan_orders(self, orphan_orders: List[Order]) -> None:
        """
        处理孤儿订单

        策略:
        - 如果是 TP/SL 订单且仓位不存在 → 取消
        - 如果是入场订单 → 保留并创建关联 Signal
        """
        for order in orphan_orders:
            if order.reduce_only:
                # 平仓单但没有对应仓位 → 取消
                await self._gateway.cancel_order(order.exchange_order_id, order.symbol)
            else:
                # 入场订单 → 保留，创建关联 Signal
                await self._create_missing_signal(order)
```

---

### 3.4 资金保护管理器

#### 3.4.1 配置参数

```yaml
# config/core.yaml

capital_protection:
  enabled: true

  # 单笔交易限制
  single_trade:
    max_loss_percent: 2.0    # 单笔最大损失 2% of balance
    max_position_percent: 20 # 单次最大仓位 20% of balance

  # 每日限制
  daily:
    max_loss_percent: 5.0    # 每日最大回撤 5% of balance
    max_trade_count: 50      # 每日最大交易次数

  # 账户限制
  account:
    min_balance: 100         # 最低余额保留 (USDT)
    max_leverage: 10         # 最大杠杆倍数
```

#### 3.4.2 检查逻辑

**修复 G-002**: 市价单 (MARKET) 价格缺失处理

```python
# src/application/capital_protection.py

class CapitalProtectionManager:
    def __init__(
        self,
        config: CapitalProtectionConfig,
        account_service: AccountService,
        notifier: Notifier,
        exchange_gateway: ExchangeGateway,  # G-002 修复：需要获取盘口价
    ):
        self._config = config
        self._account = account_service
        self._notifier = notifier
        self._gateway = exchange_gateway
        self._daily_stats = DailyTradeStats()

    async def pre_order_check(
        self,
        symbol: str,
        order_type: OrderType,
        amount: Decimal,
        price: Optional[Decimal],       # G-002 修复：可选参数
        trigger_price: Optional[Decimal],
        stop_loss: Decimal,
    ) -> OrderCheckResult:
        """
        下单前资金检查

        检查项:
        1. 单笔损失是否超限
        2. 仓位占比是否超限
        3. 每日亏损是否超限
        4. 每日交易次数是否超限
        5. 账户余额是否充足
        """
        balance = await self._account.get_balance()

        # ========== G-002 修复：市价单价格获取 ==========
        if price is None:
            if order_type == OrderType.MARKET:
                # 获取最新盘口价作为预估执行价
                price = await self._gateway.fetch_ticker_price(symbol)
                if price is None:
                    return OrderCheckResult(
                        allowed=False,
                        reason="CANNOT_ESTIMATE_MARKET_PRICE"
                    )
            elif order_type == OrderType.STOP_MARKET:
                # 条件单使用触发价作为预估
                price = trigger_price
            else:
                # 限价单必须有价格
                return OrderCheckResult(
                    allowed=False,
                    reason="MISSING_PRICE"
                )

        # 检查 1: 单笔最大损失
        max_loss = balance * (self._config.single_trade.max_loss_percent / 100)
        estimated_loss = abs(amount * (price - stop_loss))
        if estimated_loss > max_loss:
            await self._notifier.send_alert(
                "单笔交易损失超限",
                f"预计损失 {estimated_loss:.2f} > 限制 {max_loss:.2f} USDT"
            )
            return OrderCheckResult(
                allowed=False,
                reason="SINGLE_TRADE_LOSS_LIMIT"
            )
```

        # 检查 2: 单次最大仓位
        max_position = balance * (self._config.single_trade.max_position_percent / 100)
        position_value = amount * price
        if position_value > max_position:
            return OrderCheckResult(
                allowed=False,
                reason="POSITION_LIMIT"
            )

        # 检查 3: 每日最大亏损
        daily_max_loss = balance * (self._config.daily.max_loss_percent / 100)
        if self._daily_stats.realized_pnl < -daily_max_loss:
            return OrderCheckResult(
                allowed=False,
                reason="DAILY_LOSS_LIMIT"
            )

        # 检查 4: 每日交易次数
        if self._daily_stats.trade_count >= self._config.daily.max_trade_count:
            return OrderCheckResult(
                allowed=False,
                reason="DAILY_TRADE_COUNT_LIMIT"
            )

        # 检查 5: 最低余额
        if balance <= self._config.account.min_balance:
            return OrderCheckResult(
                allowed=False,
                reason="INSUFFICIENT_BALANCE"
            )

        return OrderCheckResult(allowed=True)

    def record_trade(self, realized_pnl: Decimal) -> None:
        """记录交易，更新每日统计"""
        self._daily_stats.trade_count += 1
        self._daily_stats.realized_pnl += realized_pnl

    def reset_if_new_day(self) -> None:
        """如果是新的一天，重置统计"""
        today = date.today()
        if today != self._daily_stats.last_reset_date:
            self._daily_stats.trade_count = 0
            self._daily_stats.realized_pnl = Decimal("0")
            self._daily_stats.last_reset_date = today
```

---

### 3.5 DCA 分批建仓策略

#### 3.5.1 配置示例

**修复 G-003**: DCA 限价单改为"提前预埋"模式，避免吃单滑点和高手续费

```yaml
# config/strategies/dca_martingale.yaml

dca_strategy:
  enabled: true
  entry_batches: 3
  entry_ratios: [0.5, 0.3, 0.2]  # 50% / 30% / 20%

  # ========== G-003 修复：预埋单模式 ==========
  # 第一批市价单成交后，立即预埋第 2、3 批限价单到交易所
  # 而不是等价格跌到了再去发单（避免 Taker 吃单）
  place_all_orders_upfront: true

  # 各批次配置
  batch_triggers:
    - batch_index: 1
      order_type: "MARKET"  # 市价单立即入场
      ratio: 0.5

    - batch_index: 2
      order_type: "LIMIT"
      trigger_drop_percent: -2.0  # 相对首批下跌 2% 触发
      ratio: 0.3

    - batch_index: 3
      order_type: "LIMIT"
      trigger_drop_percent: -4.0  # 相对首批下跌 4% 触发
      ratio: 0.2

  cost_basis_mode: "average"  # 平均成本法
```

#### 3.5.2 DCA 状态追踪

**修复 G-003**: 一次性预埋所有限价单

```python
# src/domain/dca_state.py

class DcaState(BaseModel):
    """DCA 批次建仓状态"""
    signal_id: str
    symbol: str
    direction: Direction

    # 批次配置
    total_batches: int
    entry_ratios: List[Decimal]
    place_all_orders_upfront: bool = True  # G-003 修复：预埋单模式

    # 执行状态
    executed_batches: List[DcaBatch] = []
    pending_batches: List[DcaBatch] = []  # 已挂出但未成交的订单

    # 成本追踪
    total_executed_qty: Decimal = Decimal("0")
    total_executed_value: Decimal = Decimal("0")

    # 第一批成交价（用于计算后续限价单价格）
    first_exec_price: Optional[Decimal] = None

    @property
    def average_cost(self) -> Decimal:
        """平均成本"""
        if self.total_executed_qty == 0:
            return Decimal("0")
        return self.total_executed_value / self.total_executed_qty

    def calculate_limit_price(self, batch_index: int) -> Optional[Decimal]:
        """
        计算限价单价格

        G-003 修复核心：
        - 基于第一批成交价计算绝对价格
        - 提前预埋到交易所，享受 Maker 费率
        """
        if self.first_exec_price is None:
            return None

        batch = self.batch_triggers[batch_index - 1]  # batch_index 从 1 开始

        if batch.order_type != "LIMIT":
            return None

        # 计算限价单价格：首批成交价 * (1 + 跌幅百分比)
        # 注意：多头时跌幅为负，空头时跌幅为正
        if self.direction == Direction.LONG:
            limit_price = self.first_exec_price * (1 + batch.trigger_drop_percent / 100)
        else:
            limit_price = self.first_exec_price * (1 - batch.trigger_drop_percent / 100)

        return limit_price

    async def place_all_limit_orders(self, order_manager: "OrderManager") -> None:
        """
        第一批成交后，立即预埋所有限价单到交易所

        G-003 修复执行逻辑:
        1. 第一批市价单成交
        2. 记录 first_exec_price
        3. 计算第 2、3 批的绝对限价
        4. 一次性挂出所有限价单
        5. 等待成交
        """
        if not self.place_all_orders_upfront:
            return

        for i in range(1, self.total_batches):  # 从第 2 批开始
            limit_price = self.calculate_limit_price(i)
            if limit_price is None:
                continue

            batch = self.batch_triggers[i]
            qty = self._calculate_batch_qty(batch.ratio)

            # 挂出限价单
            order = await order_manager.place_limit_order(
                symbol=self.symbol,
                side="buy" if self.direction == Direction.LONG else "sell",
                qty=qty,
                price=limit_price,
            )

            self.pending_batches.append(DcaBatch(
                batch_index=i,
                order_type="LIMIT",
                ratio=batch.ratio,
                order_id=order.order_id,
                limit_price=limit_price,
            ))


class DcaBatch(BaseModel):
    """单个批次执行记录"""
    batch_index: int
    order_type: str
    ratio: Decimal
    executed_qty: Optional[Decimal] = None
    executed_price: Optional[Decimal] = None
    trigger_drop_percent: Optional[Decimal] = None
    order_id: Optional[str] = None  # G-003 新增：订单 ID
    limit_price: Optional[Decimal] = None  # G-003 新增：限价单价格
```

---

### 3.6 飞书告警集成

#### 3.6.1 告警事件类型

| 事件类型 | 级别 | 触发条件 |
|----------|------|----------|
| `ORDER_FILLED` | INFO | 订单成交通知 |
| `ORDER_FAILED` | WARNING | 订单失败（保证金不足/参数错误） |
| `DAILY_LOSS_LIMIT` | ERROR | 每日亏损超限 |
| `CONNECTION_LOST` | ERROR | WebSocket 断连超 5 次 |
| `RECONCILIATION_MISMATCH` | ERROR | 对账发现差异 |
| `CAPITAL_PROTECTION_TRIGGERED` | WARNING | 资金保护触发 |

#### 3.6.2 消息格式

```python
# src/infrastructure/notifier_feishu.py

def format_order_filled_message(order: Order, pnl: Decimal) -> Dict:
    """订单成交通知"""
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "✅ 订单成交通知"},
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"""
**策略**: {order.strategy_name}
**币种**: {order.symbol}
**方向**: {order.direction.value}
**类型**: {order.order_role.value}
**成交价**: {order.average_exec_price}
**数量**: {order.filled_qty}
**盈亏**: {pnl:+.2f} USDT
**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
                    }
                }
            ]
        }
    }
```

---

## 四、数据库 Schema

### 4.1 新增字段

```sql
-- orders 表（Phase 1 已创建，Phase 5 扩展）
ALTER TABLE orders ADD COLUMN exchange_order_id TEXT;
ALTER TABLE orders ADD COLUMN reduce_only BOOLEAN DEFAULT FALSE;
ALTER TABLE orders ADD COLUMN client_order_id TEXT;
ALTER TABLE orders ADD COLUMN strategy_name TEXT;

-- positions 表（Phase 1 已创建）
-- 无需修改

-- 新增 daily_stats 表（记录每日交易统计）
CREATE TABLE IF NOT EXISTS daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    trade_count INTEGER DEFAULT 0,
    realized_pnl REAL DEFAULT 0.0,
    last_updated INTEGER NOT NULL
);
```

---

## 五、API 端点设计

### 5.1 订单管理

```python
# src/interfaces/api.py

@app.post("/api/orders", response_model=OrderResponse)
async def place_order(request: OrderRequest):
    """
    下单接口

    请求体:
    - symbol: 币种对
    - order_type: 订单类型 (market/limit/stop_market)
    - side: 买卖方向 (buy/sell)
    - amount: 数量
    - price: 限价单价格（可选）
    - trigger_price: 条件单触发价（可选）
    - reduce_only: 是否仅减仓
    """

@app.delete("/api/orders/{order_id}", response_model=OrderCancelResponse)
async def cancel_order(order_id: str, symbol: str):
    """取消订单"""

@app.get("/api/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, symbol: str):
    """查询订单状态"""
```

### 5.2 仓位查询

```python
@app.get("/api/positions", response_model=List[PositionResponse])
async def get_positions(symbol: Optional[str] = None):
    """
    查询持仓列表

    参数:
    - symbol: 币种对（可选，过滤特定币种）
    """
```

### 5.3 对账服务

```python
@app.post("/api/reconciliation", response_model=ReconciliationReport)
async def run_reconciliation(symbol: str):
    """
    启动对账服务

    参数:
    - symbol: 币种对
    """
```

---

## 六、测试计划

### 6.1 单元测试

| 测试文件 | 测试内容 | 用例数 |
|----------|----------|--------|
| `test_exchange_gateway.py` | 下单/取消/查询 | 15 |
| `test_capital_protection.py` | 资金保护检查 | 10 |
| `test_dca_strategy.py` | DCA 批次执行 | 10 |
| `test_reconciliation.py` | 对账服务 | 8 |
| `test_position_manager.py` | 并发保护 | 10 |

### 6.2 集成测试

| 测试文件 | 测试内容 |
|----------|----------|
| `test_phase5_integration.py` | 完整下单→成交→止盈流程 |
| `test_live_connection.py` | Binance Testnet 实时连接 |

---

## 七、部署配置

### 7.1 环境变量

```bash
# .env

# 交易所配置
EXCHANGE_NAME=binance
EXCHANGE_TESTNET=true
EXCHANGE_API_KEY=<你的 API 密钥>
EXCHANGE_API_SECRET=<你的 API 密钥>

# 数据库配置
DATABASE_URL=sqlite+aiosqlite:///./data/v3_dev.db

# 飞书配置
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# 资金保护配置
CAPITAL_PROTECTION_ENABLED=true
SINGLE_TRADE_MAX_LOSS_PERCENT=2.0
DAILY_MAX_LOSS_PERCENT=5.0
```

---

## 八、验收标准

### 8.1 功能验收

- [ ] 下单接口支持 MARKET/LIMIT/STOP_MARKET
- [ ] reduce_only 参数正确传递
- [ ] WebSocket 订单推送正常
- [ ] 并发保护无脏写（WeakValueDictionary 验证）
- [ ] 启动对账正确同步状态（Grace Period 验证）
- [ ] 资金保护检查生效（市价单价格获取验证）
- [ ] DCA 分批建仓正确执行（预埋单模式验证）
- [ ] 飞书告警推送正常

### 8.2 测试验收

- [ ] 单元测试 100% 通过
- [ ] 集成测试 100% 通过
- [ ] Binance Testnet 实盘测试通过

### 8.3 Gemini 评审问题验证

| 编号 | 问题 | 验证方法 | 状态 |
|------|------|----------|------|
| **G-001** | asyncio.Lock 释放后使用 | 并发测试验证无脏写 | ✅ 设计已修复 |
| **G-002** | 市价单价格缺失 | 单元测试覆盖 MARKET 场景 | ✅ 设计已修复 |
| **G-003** | DCA 限价单吃单陷阱 | 集成测试验证预埋单模式 | ✅ 设计已修复 |
| **G-004** | 对账幽灵偏差 | 集成测试验证 Grace Period | ✅ 设计已修复 |

---

## 九、待确认事项

### 9.1 已确认事项

| 编号 | 确认项 | 用户决策 | 状态 |
|------|--------|----------|------|
| 1 | API 密钥权限 | 交易权限 ✅（已提供测试网密钥） | ✅ 已确认 |
| 2 | 交易所选择 | Binance（后续扩展 Bybit/OKX） | ✅ 已确认 |
| 3 | 数据库策略 | 开发 SQLite / 生产 PostgreSQL | ✅ 已确认 |
| 4 | 资金保护参数 | 单笔 2% / 每日 5% / 仓位 20% | ✅ 已确认 |
| 5 | DCA 批次 | 3 批次 (50%/30%/20%) | ✅ 已确认 |
| 6 | 告警渠道 | 飞书 Webhook | ✅ 已确认 |

### 9.2 Gemini 评审修复事项

| 编号 | 问题 | 修复方案 | 状态 |
|------|------|----------|------|
| **G-001** | asyncio.Lock"释放后使用" | 改用 WeakValueDictionary | ✅ 已修复 |
| **G-002** | 市价单价格缺失 | 引入 expected_price+fetch_ticker_price | ✅ 已修复 |
| **G-003** | DCA 限价单吃单陷阱 | 改为提前预埋限价单 | ✅ 已修复 |
| **G-004** | 对账幽灵偏差 | 加入 10 秒 Grace Period | ✅ 已修复 |

---

**设计文档版本**: v1.1 (Gemini 评审通过)

**下一步**: 请确认此设计文档，确认后将：
1. 创建 Phase 5 接口契约表 (`docs/designs/phase5-contract.md`)
2. 分配任务给各角色（Backend/Frontend/QA/Reviewer）
3. 启动并行开发
