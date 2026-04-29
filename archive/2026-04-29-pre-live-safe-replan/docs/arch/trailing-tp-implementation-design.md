# Trailing Take Profit (TTP) 实现设计文档

> **文档版本**: v1.0  
> **创建日期**: 2026-04-17  
> **状态**: 待实现  
> **前置 ADR**: [ADR-2026-04-16-Virtual-TTP.md](ADR-2026-04-16-Virtual-TTP.md)（已确认方案 B: 影子追踪模式）  
> **前置上下文**: [opus-context-trailing-tp.md](../planning/opus-context-trailing-tp.md)

---

## 1. 技术决策摘要

| 编号 | 决策项 | 结论 | 理由 |
|------|--------|------|------|
| D1 | Trailing TP 逻辑位置 | **方案 A: `DynamicRiskManager`** | `MockMatchingEngine` 仅回测使用，实盘无此组件；risk_manager 可回测/实盘共用 |
| D2 | TP2/TP3 是否支持 trailing | **通用支持所有 TP 级别** | `OrderRole` 已定义 TP1-TP5，不应硬编码；通过配置控制哪些级别启用 trailing |
| D3 | 事件记录机制 | **复用 `PositionCloseEvent`，新增 `event_category='tp_modified'`** | 避免新建模型类；利用现有 `close_price=None` 语义区分调价事件与成交事件 |
| D4 | 触发模式 | **回撤比例为核心，阶梯阈值为频控** | 与现有 Trailing SL 架构对称，pullback 决定目标价格，step 决定是否执行更新 |

---

## 2. 决策详细论证

### D1: 为什么选择 risk_manager 而非 matching_engine

**核心事实**：`MockMatchingEngine` 仅在 `backtester.py` 中导入（L40, L1180），实盘管线不存在撮合引擎——交易所完成撮合。

```
回测调用链 (backtester.py):
  ① matching_engine.match_orders_for_kline()   ← 模拟交易所
  ② handle_order_filled()                       ← ENTRY → 创建 TP/SL
  ③ risk_manager.evaluate_and_mutate()          ← 水位线 + Trailing SL + [新增] Trailing TP

实盘调用链:
  ① 交易所 WebSocket 推送成交/价格更新          ← 交易所负责撮合
  ② order_lifecycle_service 处理回调             ← 状态同步
  ③ risk_manager.evaluate_and_mutate()          ← 价格追踪 + 调单决策
  ④ exchange API modify_order()                 ← 执行改单
```

如果放在 matching_engine：回测可用，但实盘需要**重写一遍相同逻辑**。  
如果放在 risk_manager：**回测和实盘共用同一份计算代码**，仅执行层不同（内存变异 vs API 调用）。

### D2: 通用支持所有 TP 级别

当前 `OrderRole` 已定义 TP1-TP5：

```python
class OrderRole(str, Enum):
    TP1 = "TP1"   # 已实现撮合
    TP2 = "TP2"   # enum 已定义，撮合未实现
    TP3 = "TP3"   # enum 已定义，撮合未实现
    TP4 = "TP4"
    TP5 = "TP5"
```

设计原则：通过 `TrailingTPConfig.enabled_levels` 配置哪些级别启用 trailing，而非在代码中硬编码 `if order_role == OrderRole.TP1`。

典型用法示例：
- **保守策略**: 仅 TP1 trailing（`enabled_levels=["TP1"]`），TP2/TP3 固定限价
- **趋势策略**: TP1 固定，TP2/TP3 trailing（`enabled_levels=["TP2", "TP3"]`）
- **激进策略**: 全部 trailing（`enabled_levels=["TP1", "TP2", "TP3"]`）

### D3: 事件记录机制

`PositionCloseEvent` 现有字段设计已预留扩展能力：

```python
class PositionCloseEvent(FinancialModel):
    close_price: Optional[Decimal] = None   # sl_modified 时为 None
    close_qty: Optional[Decimal] = None     # sl_modified 时为 None
    close_pnl: Optional[Decimal] = None     # sl_modified 时为 None
    close_fee: Optional[Decimal] = None     # sl_modified 时为 None
    event_category: str                      # 现有: "exit"
```

文档注释已明确写了 "部分字段为 Optional：为 trailing stop 未来扩展预留 NULL 能力"。所以：

| 事件类型 | event_category | event_type | close_price | close_qty |
|----------|---------------|------------|-------------|-----------|
| TP1 成交 | `"exit"` | `"TP1"` | 实际成交价 | 实际成交量 |
| SL 成交 | `"exit"` | `"SL"` | 实际成交价 | 实际成交量 |
| TP 调价 | **`"tp_modified"`** | `"TP1"` / `"TP2"` | **None** | **None** |
| SL 调价 | `"sl_modified"` | `"SL"` | None | None |

`exit_reason` 字段记录调价详情，如 `"TRAILING_TP: 65000→66200 (watermark=67500)"`。

### D4: 触发模式 — 与现有 Trailing SL 完全对称

```python
# 现有 Trailing SL 逻辑 (risk_manager.py L156-208):
theoretical_trigger = watermark * (1 - trailing_percent)        # pullback 核心
min_required_price = current_trigger * (1 + step_threshold)     # step 频控
if theoretical_trigger >= min_required_price:
    sl_order.trigger_price = max(entry_price, theoretical_trigger)
```

Trailing TP 逻辑**完全镜像**：

```python
# Trailing TP 逻辑 (LONG 方向):
theoretical_tp = watermark * (1 - tp_trailing_percent)           # pullback 核心
min_required_tp = current_tp_price * (1 + tp_step_threshold)     # step 频控
if theoretical_tp >= min_required_tp:
    tp_order.price = max(original_tp_price, theoretical_tp)      # 保护底线
```

---

## 3. 数据模型变更

### 3.1 `RiskManagerConfig` 扩展

**文件**: `src/domain/models.py` (L1888-1901)

```python
class RiskManagerConfig(BaseModel):
    """
    动态风控管理器配置

    P2-1: 魔法数字配置化
    TTP: Trailing Take Profit 配置扩展
    """
    # ===== 现有字段（不变）=====
    trailing_percent: Decimal = Field(
        default=Decimal('0.02'),
        description="移动止损回撤容忍度 (默认 2%)"
    )
    step_threshold: Decimal = Field(
        default=Decimal('0.005'),
        description="阶梯阈值 (默认 0.5%)"
    )

    # ===== 新增字段: Trailing TP =====
    tp_trailing_enabled: bool = Field(
        default=False,
        description="是否启用 Trailing TP (默认关闭，需显式开启)"
    )
    tp_trailing_percent: Decimal = Field(
        default=Decimal('0.01'),
        description="TP 回撤容忍度 (默认 1%，比 SL 更敏感)"
    )
    tp_step_threshold: Decimal = Field(
        default=Decimal('0.003'),
        description="TP 阶梯阈值 (默认 0.3%，比 SL 更敏感)"
    )
    tp_trailing_enabled_levels: List[str] = Field(
        default_factory=lambda: ["TP1"],
        description="启用 trailing 的 TP 级别列表 (如 ['TP1', 'TP2'])"
    )
    tp_trailing_activation_rr: Decimal = Field(
        default=Decimal('0.5'),
        description="Trailing TP 激活阈值 (RR 倍数)：价格达到 TP 价格的 50% 时才开始追踪"
    )
```

**设计说明**:

1. **`tp_trailing_enabled`**: 默认关闭，回测和实盘都需要显式开启。避免意外改变现有行为。
2. **`tp_trailing_percent`**: 默认 1%，比 SL 的 2% 更小。原因：TP 追踪对回撤更敏感，过大会导致利润大幅吐回。
3. **`tp_step_threshold`**: 默认 0.3%，比 SL 的 0.5% 更小。原因：TP 调价频率可以更高（尤其回测场景无 API 限流）。
4. **`tp_trailing_enabled_levels`**: 控制粒度——哪些 TP 级别启用 trailing。
5. **`tp_trailing_activation_rr`**: 避免在价格刚突破入场价时就启动追踪，需要达到原始 TP 目标的一定比例才激活。

### 3.2 `Position` 模型扩展

**文件**: `src/domain/models.py` (L1094-1118)

```python
class Position(FinancialModel):
    # ===== 现有字段（不变）=====
    watermark_price: Optional[Decimal] = None

    # ===== 新增字段 =====
    tp_trailing_activated: bool = Field(
        default=False,
        description="Trailing TP 是否已激活 (价格达到激活阈值后标记为 True)"
    )
    original_tp_prices: Dict[str, Decimal] = Field(
        default_factory=dict,
        description="各 TP 级别的原始价格快照 (如 {'TP1': Decimal('65000')})"
    )
```

**设计说明**:

1. **`tp_trailing_activated`**: 一旦激活就不会再关闭（单向状态）。激活条件见第 4 节。
2. **`original_tp_prices`**: 在 TP 订单创建时记录原始价格。Trailing 逻辑确保新 TP 价格 ≥ 原始 TP 价格（LONG），保护利润底线。

### 3.3 `Order` 模型 — 无变更

现有 `Order.price` 字段（限价单挂单价格）直接用于 Trailing TP 调价，无需新增字段。

---

## 4. 核心方法设计

### 4.1 `DynamicRiskManager` 新增方法

**文件**: `src/domain/risk_manager.py`

#### 4.1.1 修改 `evaluate_and_mutate()` — 新增 Step 4

```python
def evaluate_and_mutate(
    self,
    kline: KlineData,
    position: Position,
    active_orders: List[Order],
) -> None:
    """
    每根 K 线撮合完成后调用此方法进行风控状态突变

    执行顺序:
        Step 1: 检查 TP1 是否成交 → Breakeven
        Step 2: 更新水位线
        Step 3: Trailing SL（原有）
        Step 4: Trailing TP（新增）  ← 新增

    T+1 时序声明:
        TP 价格修改在本 K 线撮合之后、下一根 K 线开始之前执行。
        matching_engine 在下一根 K 线使用修改后的 TP 价格进行撮合判定。
    """
    if position.is_closed or position.current_qty <= 0:
        return

    sl_order = self._find_order_by_role(active_orders, OrderRole.SL)
    if sl_order is None:
        return

    tp1_order = self._find_order_by_role(active_orders, OrderRole.TP1)

    # Step 1: Breakeven (不变)
    if tp1_order and tp1_order.status == OrderStatus.FILLED:
        self._apply_breakeven(position, sl_order)

    # Step 2: 更新水位线 (不变)
    self._update_watermark(kline, position)

    # Step 3: Trailing SL (不变)
    if sl_order.order_type == OrderType.TRAILING_STOP:
        self._apply_trailing_logic(position, sl_order)

    # Step 4: Trailing TP (新增)
    if self._config.tp_trailing_enabled:
        self._apply_trailing_tp(kline, position, active_orders)
```

#### 4.1.2 新增 `_apply_trailing_tp()`

```python
def _apply_trailing_tp(
    self,
    kline: KlineData,
    position: Position,
    active_orders: List[Order],
) -> List[PositionCloseEvent]:
    """
    对所有启用了 trailing 的活跃 TP 订单执行追踪调价

    激活条件 (必须同时满足):
        1. tp_trailing_enabled = True (全局配置)
        2. 该 TP 级别在 tp_trailing_enabled_levels 中
        3. 该 TP 订单状态为 OPEN
        4. position.watermark_price 已达到激活阈值
           (LONG: watermark >= entry + activation_rr * (tp_price - entry))
           (SHORT: watermark <= entry - activation_rr * (entry - tp_price))

    调价逻辑 (LONG 示例):
        theoretical_tp = watermark * (1 - tp_trailing_percent)
        min_required   = current_tp * (1 + tp_step_threshold)
        if theoretical_tp >= min_required:
            new_tp = max(original_tp_price, theoretical_tp)   # 保护底线
            tp_order.price = new_tp

    Args:
        kline: 当前 K 线数据
        position: 关联的仓位
        active_orders: 活跃订单列表

    Returns:
        List[PositionCloseEvent]: TP 调价事件列表 (event_category='tp_modified')

    副作用:
        - 更新 tp_order.price (满足条件时)
        - 设置 position.tp_trailing_activated = True (首次激活时)
        - 写入 position.original_tp_prices (首次遇到该 TP 时)
    """
    events = []

    if position.watermark_price is None:
        return events

    enabled_levels = set(self._config.tp_trailing_enabled_levels)

    for order in active_orders:
        # 仅处理活跃的 TP 订单
        if order.status != OrderStatus.OPEN:
            continue
        if order.signal_id != position.signal_id:
            continue
        if order.order_role.value not in enabled_levels:
            continue
        if order.price is None:
            continue

        # 记录原始 TP 价格 (仅首次)
        tp_level_key = order.order_role.value  # "TP1", "TP2", etc.
        if tp_level_key not in position.original_tp_prices:
            position.original_tp_prices[tp_level_key] = order.price

        original_tp = position.original_tp_prices[tp_level_key]

        # 检查激活条件
        if not self._check_tp_trailing_activation(position, original_tp):
            continue

        # 标记激活 (单向状态)
        if not position.tp_trailing_activated:
            position.tp_trailing_activated = True

        # 执行调价计算
        event = self._calculate_and_apply_tp_trailing(
            position, order, original_tp, kline.timestamp
        )
        if event:
            events.append(event)

    return events
```

#### 4.1.3 新增 `_check_tp_trailing_activation()`

```python
def _check_tp_trailing_activation(
    self,
    position: Position,
    original_tp_price: Decimal,
) -> bool:
    """
    检查 Trailing TP 激活条件

    激活阈值 = entry + activation_rr × (tp_price - entry)

    示例 (LONG, entry=60000, tp=66000, activation_rr=0.5):
        activation_price = 60000 + 0.5 × (66000 - 60000) = 63000
        当 watermark >= 63000 时激活

    Args:
        position: 仓位对象 (需要 watermark_price, entry_price, direction)
        original_tp_price: 原始 TP 价格

    Returns:
        True: 满足激活条件
    """
    if position.tp_trailing_activated:
        return True  # 已激活，无需再检查

    if position.watermark_price is None:
        return False

    activation_rr = self._config.tp_trailing_activation_rr

    if position.direction == Direction.LONG:
        price_range = original_tp_price - position.entry_price
        activation_price = position.entry_price + activation_rr * price_range
        return position.watermark_price >= activation_price
    else:
        price_range = position.entry_price - original_tp_price
        activation_price = position.entry_price - activation_rr * price_range
        return position.watermark_price <= activation_price
```

#### 4.1.4 新增 `_calculate_and_apply_tp_trailing()`

```python
def _calculate_and_apply_tp_trailing(
    self,
    position: Position,
    tp_order: Order,
    original_tp_price: Decimal,
    timestamp: int,
) -> Optional[PositionCloseEvent]:
    """
    对单个 TP 订单执行 trailing 调价

    LONG 方向:
        theoretical_tp = watermark × (1 - tp_trailing_percent)
        上移方向：theoretical_tp > current_tp_price
        阶梯判定：theoretical_tp >= current_tp × (1 + tp_step_threshold)
        底线保护：new_tp >= original_tp_price (不可低于原始 TP)

    SHORT 方向:
        theoretical_tp = watermark × (1 + tp_trailing_percent)
        下移方向：theoretical_tp < current_tp_price
        阶梯判定：theoretical_tp <= current_tp × (1 - tp_step_threshold)
        底线保护：new_tp <= original_tp_price (不可高于原始 TP)

    Args:
        position: 仓位对象
        tp_order: TP 订单
        original_tp_price: 原始 TP 价格（底线）
        timestamp: K 线时间戳 (用于事件记录)

    Returns:
        PositionCloseEvent: 调价事件 (event_category='tp_modified')
        None: 未满足调价条件
    """
    current_tp = tp_order.price
    watermark = position.watermark_price

    if position.direction == Direction.LONG:
        # LONG: TP 价格随水位线上移
        theoretical_tp = watermark * (Decimal('1') - self._config.tp_trailing_percent)

        # 阶梯判定：新价格必须高出当前价一定比例
        min_required = current_tp * (Decimal('1') + self._config.tp_step_threshold)

        if theoretical_tp >= min_required:
            # 底线保护：不低于原始 TP 价格
            new_tp = max(original_tp_price, theoretical_tp)
            old_tp = tp_order.price
            tp_order.price = new_tp

            # 生成调价事件
            return PositionCloseEvent(
                position_id=position.id,
                order_id=tp_order.id,
                event_type=tp_order.order_role.value,
                event_category='tp_modified',
                close_price=None,
                close_qty=None,
                close_pnl=None,
                close_fee=None,
                close_time=timestamp,
                exit_reason=f"TRAILING_TP: {old_tp}→{new_tp} (watermark={watermark})",
            )

    else:
        # SHORT: TP 价格随水位线下移
        theoretical_tp = watermark * (Decimal('1') + self._config.tp_trailing_percent)

        # 阶梯判定：新价格必须低于当前价一定比例
        min_required = current_tp * (Decimal('1') - self._config.tp_step_threshold)

        if theoretical_tp <= min_required:
            # 底线保护：不高于原始 TP 价格
            new_tp = min(original_tp_price, theoretical_tp)
            old_tp = tp_order.price
            tp_order.price = new_tp

            return PositionCloseEvent(
                position_id=position.id,
                order_id=tp_order.id,
                event_type=tp_order.order_role.value,
                event_category='tp_modified',
                close_price=None,
                close_qty=None,
                close_pnl=None,
                close_fee=None,
                close_time=timestamp,
                exit_reason=f"TRAILING_TP: {old_tp}→{new_tp} (watermark={watermark})",
            )

    return None
```

---

## 5. matching_engine 变更

### 5.1 支持所有 TP 级别的撮合

**文件**: `src/domain/matching_engine.py`

当前 matching_engine 仅处理 TP1（L161: `order.order_role == OrderRole.TP1`），需要扩展为支持所有 TP 级别。

```python
# 修改前 (L161):
elif order.order_type == OrderType.LIMIT and order.order_role == OrderRole.TP1:

# 修改后:
TP_ROLES = {OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5}

elif order.order_type == OrderType.LIMIT and order.order_role in TP_ROLES:
```

同时需要更新：

1. **`_sort_orders_by_priority()`** (L217-230): 将 TP2-TP5 加入优先级排序
2. **`_execute_fill()`** (L326): 将 TP2-TP5 加入平仓逻辑分支

```python
# 修改前 (L326):
elif order.order_role in [OrderRole.TP1, OrderRole.SL]:

# 修改后:
elif order.order_role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3,
                          OrderRole.TP4, OrderRole.TP5, OrderRole.SL]:
```

> **注意**: matching_engine 已经在 L326 处理了 TP1 和 SL 的平仓逻辑，
> 但 backtester.py L1444 已经包含了 TP2-TP5 的事件记录逻辑。
> 说明 TP2-TP5 的**撮合触发**尚未实现，但**事件记录已预埋**。

---

## 6. backtester 集成变更

### 6.1 变更点

**文件**: `src/application/backtester.py`

#### 修改 1: 初始化 RiskManagerConfig 增加 TTP 参数 (L1486-1491)

```python
# 修改前:
dynamic_risk_manager = DynamicRiskManager(
    config=RiskManagerConfig(
        trailing_percent=Decimal('0.02'),
        step_threshold=Decimal('0.005'),
    ),
)

# 修改后:
# 从 request 或 KV 配置读取 TTP 参数
tp_trailing_enabled = (
    kv_configs.get('tp_trailing_enabled') if kv_configs else False
) or False
tp_trailing_percent = (
    kv_configs.get('tp_trailing_percent') if kv_configs else None
) or Decimal('0.01')
tp_step_threshold = (
    kv_configs.get('tp_step_threshold') if kv_configs else None
) or Decimal('0.003')

dynamic_risk_manager = DynamicRiskManager(
    config=RiskManagerConfig(
        trailing_percent=Decimal('0.02'),
        step_threshold=Decimal('0.005'),
        tp_trailing_enabled=tp_trailing_enabled,
        tp_trailing_percent=tp_trailing_percent,
        tp_step_threshold=tp_step_threshold,
    ),
)
```

#### 修改 2: 收集 TP 调价事件 (L1492-1494)

```python
# 修改前:
for position in positions_map.values():
    if not position.is_closed and position.current_qty > 0:
        dynamic_risk_manager.evaluate_and_mutate(kline, position, active_orders)

# 修改后:
for position in positions_map.values():
    if not position.is_closed and position.current_qty > 0:
        dynamic_risk_manager.evaluate_and_mutate(kline, position, active_orders)

        # 收集 TP 调价事件 (新增)
        if dynamic_risk_manager._config.tp_trailing_enabled:
            tp_events = dynamic_risk_manager.get_last_tp_events()
            all_close_events.extend(tp_events)
```

> **注意**: `evaluate_and_mutate()` 内部调用 `_apply_trailing_tp()` 返回事件列表。
> 需要将 `_apply_trailing_tp()` 的返回值暂存，由新增的 `get_last_tp_events()` 方法暴露给外部。
> 或者直接修改 `evaluate_and_mutate()` 返回事件列表（破坏性更大、不推荐）。

**推荐方案**: 在 `DynamicRiskManager` 中新增实例变量 `_last_tp_events: List[PositionCloseEvent]`：

```python
class DynamicRiskManager:
    def __init__(self, config=None, ...):
        self._config = config or RiskManagerConfig()
        self._last_tp_events: List[PositionCloseEvent] = []   # 新增

    def evaluate_and_mutate(self, kline, position, active_orders):
        # ... 原有逻辑 ...

        # Step 4: Trailing TP
        if self._config.tp_trailing_enabled:
            self._last_tp_events = self._apply_trailing_tp(kline, position, active_orders)

    def get_last_tp_events(self) -> List[PositionCloseEvent]:
        """获取最近一次 evaluate_and_mutate() 产生的 TP 调价事件"""
        events = self._last_tp_events
        self._last_tp_events = []
        return events
```

#### 修改 3: original_tp_prices 初始化时机 (backtester.py, handle_order_filled 后)

TP 订单由 `order_manager._generate_tp_sl_orders()` 在 ENTRY 成交后动态生成。此时需要记录原始 TP 价格到 Position：

```python
# 在 backtester.py handle_order_filled() 之后:
for order in new_orders:
    if order.order_role in TP_ROLES and order.price:
        position = positions_map.get(order.signal_id)
        if position:
            position.original_tp_prices[order.order_role.value] = order.price
```

---

## 7. 实盘集成设计

### 7.1 实盘调用流程

```
WebSocket 价格推送 / K 线收盘事件
  └→ position_manager.on_kline_closed(kline)
       ├→ risk_manager.evaluate_and_mutate(kline, position, active_orders)
       │   ├→ _update_watermark()
       │   ├→ _apply_trailing_logic()     ← Trailing SL
       │   └→ _apply_trailing_tp()        ← Trailing TP (新增)
       │       └→ 修改内存中 tp_order.price
       │
       └→ if tp_order.price changed:
            └→ exchange_gateway.modify_order(
                  order_id=tp_order.exchange_order_id,
                  new_price=tp_order.price,
              )
```

### 7.2 Virtual TTP 模式 (ADR 已确认)

根据 ADR-2026-04-16，实盘采用**影子追踪模式**：

1. **交易所端**: 仅挂 SL 单（硬止损保底），**不挂 TP 限价单**
2. **本地端**: `DynamicRiskManager` 追踪水位线，计算虚拟 TP 触发价
3. **触发时**: 直接发送 MARKET 平仓单（Taker 费用，但避免撤单竞态）

这意味着实盘下 `_apply_trailing_tp()` 的行为略有不同：
- 回测模式: 修改 `tp_order.price`（限价单价格），matching_engine 在下一根 K 线判触发
- 实盘模式: 计算虚拟触发价，当价格回撤到触发价时，**直接发送市价平仓**

**实现建议**: 在 `evaluate_and_mutate()` 中新增返回值或回调机制，通知上层"TTP 触发平仓"：

```python
# 实盘模式下，risk_manager 新增触发检测:
def _check_ttp_market_exit(self, kline, position, tp_order):
    """
    实盘 Virtual TTP: 检测是否应该市价平仓

    条件: trailing_activated AND 当前价格回撤到 theoretical_tp 以下
    """
    if not position.tp_trailing_activated:
        return False

    theoretical_tp = ...  # 同 _calculate_and_apply_tp_trailing
    if position.direction == Direction.LONG:
        return kline.close <= theoretical_tp
    else:
        return kline.close >= theoretical_tp
```

> **注意**: 此方法仅用于实盘。回测中 matching_engine 负责判触发。

---

## 8. 完整文件变更清单

| 文件 | 变更类型 | 内容 |
|------|----------|------|
| `src/domain/models.py` | MODIFY | `RiskManagerConfig` 新增 5 个 TTP 字段；`Position` 新增 2 个字段 |
| `src/domain/risk_manager.py` | MODIFY | `evaluate_and_mutate()` 新增 Step 4；新增 3 个私有方法 + 1 个公开方法 |
| `src/domain/matching_engine.py` | MODIFY | TP1 硬编码 → 支持 TP1-TP5；优先级排序扩展 |
| `src/application/backtester.py` | MODIFY | RiskManagerConfig 初始化扩展；TP 调价事件收集；original_tp_prices 初始化 |
| `tests/test_trailing_tp.py` | NEW | 单元测试 |

---

## 9. 测试策略

### 9.1 单元测试 (test_trailing_tp.py)

```python
class TestTrailingTP:
    """Trailing TP 单元测试"""

    # ===== 基础功能 =====

    def test_tp_trailing_disabled_by_default(self):
        """默认关闭时，TP 价格不应改变"""

    def test_tp_trailing_activation_threshold(self):
        """价格未达到激活阈值时，不应启动追踪"""

    def test_tp_trailing_activation_long(self):
        """LONG: 水位线达到 activation_rr 后激活"""

    def test_tp_trailing_activation_short(self):
        """SHORT: 水位线达到 activation_rr 后激活"""

    # ===== 调价逻辑 =====

    def test_tp_price_moves_up_with_watermark_long(self):
        """LONG: 水位线上升 → TP 价格跟随上移"""

    def test_tp_price_moves_down_with_watermark_short(self):
        """SHORT: 水位线下降 → TP 价格跟随下移"""

    def test_tp_step_threshold_prevents_small_updates(self):
        """阶梯阈值：微小变动不触发更新"""

    def test_tp_floor_protection_long(self):
        """LONG: TP 价格不低于原始 TP 价格 (bottom line)"""

    def test_tp_floor_protection_short(self):
        """SHORT: TP 价格不高于原始 TP 价格"""

    # ===== 多级别 =====

    def test_only_enabled_levels_are_trailed(self):
        """仅 tp_trailing_enabled_levels 中的级别被追踪"""

    def test_tp2_tp3_trailing_independent(self):
        """TP2 和 TP3 独立追踪，互不影响"""

    # ===== 事件记录 =====

    def test_tp_modified_event_generated(self):
        """调价时生成 event_category='tp_modified' 事件"""

    def test_tp_modified_event_fields(self):
        """调价事件的 close_price/qty/pnl/fee 均为 None"""

    def test_no_event_when_no_update(self):
        """未达到调价条件时不生成事件"""

    # ===== T+1 时序 =====

    def test_tp_update_takes_effect_next_kline(self):
        """TP 调价在当前 K 线撮合后执行，下一根 K 线生效"""

    # ===== 边界条件 =====

    def test_tp_trailing_with_closed_position(self):
        """已平仓仓位不执行追踪"""

    def test_tp_trailing_watermark_none(self):
        """watermark 为 None 时跳过"""

    def test_tp_trailing_decimal_precision(self):
        """所有计算使用 Decimal，验证精度"""
```

### 9.2 集成测试 (回测路径)

```python
class TestTrailingTPBacktest:
    """Trailing TP 回测集成测试"""

    async def test_pms_backtest_with_trailing_tp_enabled(self):
        """
        端到端: 开启 TTP 的回测，验证:
        1. TP 价格确实随行情上移
        2. 最终 realized_pnl > 无 TTP 时的 pnl
        3. close_events 包含 tp_modified 事件
        """

    async def test_pms_backtest_trailing_tp_vs_fixed_tp(self):
        """
        对比测试: 同一组 K 线数据，对比开启/关闭 TTP 的收益差异
        """

    async def test_trailing_tp_with_multi_level_tp(self):
        """
        多级止盈 + TTP: TP1 固定，TP2 trailing
        验证两者独立运作，互不干扰
        """
```

### 9.3 验证命令

```bash
# 单元测试
pytest tests/test_trailing_tp.py -v

# 回测集成测试
pytest tests/test_trailing_tp.py::TestTrailingTPBacktest -v

# 验证现有测试不受影响 (回归测试)
pytest tests/ -v --tb=short
```

---

## 10. 实施顺序建议

```
Phase 1: 数据模型 (预计 1h)
  ├── models.py: RiskManagerConfig 扩展
  └── models.py: Position 扩展

Phase 2: 核心逻辑 (预计 3h)
  ├── risk_manager.py: _apply_trailing_tp()
  ├── risk_manager.py: _check_tp_trailing_activation()
  ├── risk_manager.py: _calculate_and_apply_tp_trailing()
  └── risk_manager.py: evaluate_and_mutate() Step 4

Phase 3: matching_engine 扩展 (预计 1h)
  ├── matching_engine.py: TP1 → TP1-TP5 撮合
  └── matching_engine.py: 优先级排序扩展

Phase 4: backtester 集成 (预计 2h)
  ├── backtester.py: RiskManagerConfig 初始化
  ├── backtester.py: TP 调价事件收集
  └── backtester.py: original_tp_prices 初始化

Phase 5: 单元测试 (预计 2h)
  └── tests/test_trailing_tp.py

Phase 6: 回测验证 (预计 1h)
  └── 运行完整回测，对比 TTP 开启/关闭的收益差异
```

---

## 附录 A: Trailing TP 计算示例

### LONG 方向完整流程

```
初始状态:
  entry_price = 60000
  original_tp = 66000 (1.5R)
  tp_trailing_percent = 0.01 (1%)
  tp_step_threshold = 0.003 (0.3%)
  activation_rr = 0.5

激活阈值:
  activation_price = 60000 + 0.5 × (66000 - 60000) = 63000

K 线 1: high=62000 → watermark=62000 → 未达激活阈值(< 63000), 跳过
K 线 2: high=64000 → watermark=64000 → 达到激活阈值(≥ 63000), 激活!
         theoretical_tp = 64000 × 0.99 = 63360
         min_required = 66000 × 1.003 = 66198
         63360 < 66198 → 不更新 (水位线虽已激活但 TP 仍远高于理论值)

K 线 3: high=68000 → watermark=68000
         theoretical_tp = 68000 × 0.99 = 67320
         min_required = 66000 × 1.003 = 66198
         67320 ≥ 66198 → 更新! TP: 66000 → 67320

K 线 4: high=70000 → watermark=70000
         theoretical_tp = 70000 × 0.99 = 69300
         min_required = 67320 × 1.003 = 67521.96
         69300 ≥ 67521.96 → 更新! TP: 67320 → 69300

K 线 5: high=69500 → watermark=70000 (不变，水位线只涨不跌)
         theoretical_tp = 70000 × 0.99 = 69300
         min_required = 69300 × 1.003 = 69507.9
         69300 < 69507.9 → 不更新 (未达阶梯阈值)

K 线 6: low=69200 → 价格触及 TP (69300)
         matching_engine 撮合成交，利润: (69300 - 60000) / 60000 = 15.5%
         对比固定 TP: (66000 - 60000) / 60000 = 10%
         TTP 额外捕获: +5.5%
```

### SHORT 方向完整流程

```
初始状态:
  entry_price = 60000
  original_tp = 54000 (1.5R)
  tp_trailing_percent = 0.01 (1%)

激活阈值:
  activation_price = 60000 - 0.5 × (60000 - 54000) = 57000

K 线 x: low=55000 → watermark=55000 → 达到激活阈值(≤ 57000), 激活!
         theoretical_tp = 55000 × 1.01 = 55550
         min_required = 54000 × 0.997 = 53838
         55550 > 53838 → 不更新 (SHORT 方向，TP 应该下移)

K 线 y: low=52000 → watermark=52000
         theoretical_tp = 52000 × 1.01 = 52520
         min_required = 54000 × 0.997 = 53838
         52520 ≤ 53838 → 更新! TP: 54000 → 52520
```
