# ADR-2026-04-20-Trailing-Exit-Mechanism

## 标题

Trailing Exit（追踪退出）机制设计——从"上调 TP"改为"水位追踪平仓"

## 状态

提议（Proposed）

## 背景

### 问题诊断

当前 TTP（Trailing Take Profit）设计方向错误：

1. **原设计**：当 watermark > TP 价格时，上调 TP 订单价格
   - 触发条件：`watermark > tp_price`
   - 问题：54% 胜率策略下，大部分交易根本到不了 TP，TTP 永远不触发

2. **真实问题**：
   - 策略胜率 54%，但总 PnL 为负（-15723 USDT / 558 笔）
   - 说明实际盈亏比 < 1:1
   - 大部分赢单只吃到 TP1（1R），剩余仓位被 SL 打穿
   - 典型场景：价格涨到 +1.5R 后反转 → SL 打掉，最终亏 -1R

### 用户需求

把"价格涨到 X% 又跌回 SL 的亏损单"变成"锁定在水位高点附近平仓的盈利单"。

**典型场景对比**：

| 场景 | 当前（无 TTP） | 新 TTP（追踪平仓） |
|------|---------------|-------------------|
| 价格 +1.5R 后反转 | SL 打掉，亏 -1R | 水位 1.5R，trailing_exit ≈ +1.35R，小赢 |
| 价格 +0.5R 后反转 | SL 打掉，亏 -1R | 不激活（< 阈值），保持原 SL |
| 价格 +2.5R 直接到 TP2 | 正常赢 +2.5R | 正常赢 +2.5R（TTP 不干预） |

## 决策

重新设计 TTP 机制，从"上调 TP 订单"改为"水位追踪平仓"。

### 核心机制

#### 1. 激活条件（修复：基于 R 距离，不依赖 TP 级别）

**问题**：原设计硬编码 `tp1_price`，TP1 成交后激活阈值错误。

**修复方案**：激活阈值改为基于 watermark 已超过 entry 多少 R，不依赖具体 TP 级别：

```python
# 计算 SL 距离（R 的基准）
sl_distance = abs(position.entry_price - position.stop_loss_price)

# 激活阈值：entry + activation_rr × sl_distance
activation_threshold = position.entry_price + activation_rr × sl_distance
```

**激活条件**：
- LONG: `watermark >= activation_threshold`
- SHORT: `watermark <= activation_threshold`

**示例**：
- Entry: 50000, SL: 49500（1R = 500）
- Activation RR: 0.3
- Activation threshold: 50000 + 0.3 × 500 = 50150
- 效果：涨了 0.3R 就激活，与 TP1/TP2 是否成交无关

#### 2. 追踪退出价计算（新设计）

```python
if position.direction == Direction.LONG:
    trailing_exit_price = watermark × (1 - tp_trailing_percent)
else:  # SHORT
    trailing_exit_price = watermark × (1 + tp_trailing_percent)
```

#### 3. 平仓触发条件（新设计）

**每根 K 线收盘后检查**：

```python
if position.direction == Direction.LONG:
    # 本根 K 线最低价跌破追踪退出价 → 触发平仓
    if kline.low <= trailing_exit_price:
        trigger_trailing_exit(position, trailing_exit_price, kline.timestamp)
else:  # SHORT
    # 本根 K 线最高价涨破追踪退出价 → 触发平仓
    if kline.high >= trailing_exit_price:
        trigger_trailing_exit(position, trailing_exit_price, kline.timestamp)
```

#### 4. 平仓执行（新设计）

- **方式**：市价单平仓（立即执行）
- **仓位**：平掉所有剩余仓位（包括未成交的 TP 订单）
- **记录**：生成 `trailing_exit` 事件，记录平仓价格和原因

### 数据模型调整

#### Position 模型新增字段

```python
class Position(BaseModel):
    # 现有字段...

    # TTP 状态
    tp_trailing_activated: bool = False  # 是否已激活追踪
    trailing_exit_price: Optional[Decimal] = None  # 当前追踪退出价
    trailing_activation_time: Optional[int] = None  # 激活时间戳
```

#### CloseEvent 新增事件类型

```python
class CloseEvent(BaseModel):
    event_category: Literal[
        "tp_filled", "sl_filled", "manual_close", "trailing_exit", "trailing_activated"
    ]
    # trailing_exit: 追踪退出触发
    # trailing_activated: 追踪退出激活（水位达到阈值）
```

### 代码实现方案

#### 1. `risk_manager.py` 修改

**新增方法**（修复：传入 sl_price 参数）：

```python
def _check_trailing_activation(
    self,
    position: Position,
    sl_price: Decimal
) -> bool:
    """
    检查追踪退出激活条件

    Args:
        position: 当前仓位
        sl_price: 止损订单触发价（用于计算 R 距离）

    Returns:
        True 如果满足激活条件
    """
    if not position or not sl_price:
        return False

    # 计算 SL 距离（R 的基准）
    sl_distance = abs(position.entry_price - sl_price)

    # 激活阈值：entry + activation_rr × sl_distance
    activation_threshold = (
        position.entry_price +
        self._config.tp_trailing_activation_rr * sl_distance
    )

    # 检查 watermark 是否达到阈值
    if position.direction == Direction.LONG:
        return position.watermark_price >= activation_threshold
    else:  # SHORT
        return position.watermark_price <= activation_threshold
```

```python
def _apply_trailing_exit(
    self,
    kline: KlineData,
    position: Position,
    active_orders: List[Order]
) -> List[CloseEvent]:
    """
    应用追踪退出逻辑

    Returns:
        如果触发平仓，返回 CloseEvent 列表；否则返回空列表
    """
    events = []

    # 1. 检查是否启用追踪退出
    if not self._config.tp_trailing_enabled:
        return events

    # 2. 检查激活条件（修复：传入 sl_price）
    if not position.tp_trailing_activated:
        sl_order = self._find_order_by_role(active_orders, OrderRole.SL, position.signal_id)
        sl_price = sl_order.trigger_price if sl_order else None
        if sl_price and self._check_trailing_activation(position, sl_price):
            position.tp_trailing_activated = True
            position.trailing_activation_time = kline.timestamp
            # 记录激活事件（schema 见下方）
            events.append(self._create_trailing_activated_event(position, kline.timestamp))

    # 3. 如果已激活，更新追踪退出价
    if position.tp_trailing_activated:
        if position.direction == Direction.LONG:
            # LONG: watermark 上涨时更新追踪退出价
            new_trailing_exit = position.watermark_price * (1 - self._config.tp_trailing_percent)
            if new_trailing_exit > (position.trailing_exit_price or Decimal('0')):
                position.trailing_exit_price = new_trailing_exit
        else:  # SHORT
            # SHORT: watermark 下跌时更新追踪退出价
            new_trailing_exit = position.watermark_price * (1 + self._config.tp_trailing_percent)
            if position.trailing_exit_price is None or new_trailing_exit < position.trailing_exit_price:
                position.trailing_exit_price = new_trailing_exit

    # 4. 检查是否触发平仓
    if position.trailing_exit_price:
        if position.direction == Direction.LONG:
            if kline.low <= position.trailing_exit_price:
                # 触发平仓
                events.append(self._create_trailing_exit_event(
                    position,
                    position.trailing_exit_price,
                    kline.timestamp
                ))
        else:  # SHORT
            if kline.high >= position.trailing_exit_price:
                events.append(self._create_trailing_exit_event(
                    position,
                    position.trailing_exit_price,
                    kline.timestamp
                ))

    return events
```

**修改 `evaluate_and_mutate()`**：

```python
def evaluate_and_mutate(
    self,
    kline: KlineData,
    position: Position,
    active_orders: List[Order]
) -> List[CloseEvent]:
    """评估并执行风控逻辑"""
    events = []

    # 0. 如果仓位已关闭，直接返回（避免与 SL 竞争）
    if position.status == PositionStatus.CLOSED:
        return events

    # 1. 更新 watermark
    self._update_watermark(kline, position)

    # 2. 应用追踪退出（新增）
    trailing_events = self._apply_trailing_exit(kline, position, active_orders)
    events.extend(trailing_events)

    # 3. 如果追踪退出已触发，直接返回（不再执行其他逻辑）
    if trailing_events:
        return events

    # 4. 其他风控逻辑（止损、移动止损等）
    # ...

    return events
```

**关键时序说明**：

回测引擎每根 K 线的执行顺序：

1. **撮合阶段**（`matching_engine.match_orders_for_kline`）：
   - 检查 SL/TP 订单是否成交
   - 如果 SL 成交 → `position.status = CLOSED`

2. **风控评估阶段**（`risk_manager.evaluate_and_mutate`）：
   - 检查 `position.status == CLOSED` → 直接返回
   - 避免与已触发的 SL 竞争

**竞争场景处理**：

| 场景 | 撮合阶段 | 风控阶段 | 结果 |
|------|---------|---------|------|
| SL 和 Trailing Exit 同时满足 | SL 成交 | position 已关闭，跳过 | SL 优先（保守） |
| 仅 Trailing Exit 满足 | 无成交 | 触发平仓 | Trailing Exit 生效 |
| 仅 SL 满足 | SL 成交 | position 已关闭，跳过 | SL 正常触发 |

#### 2. `backtester.py` 修改

**在 K 线循环中调用追踪退出**：

```python
# 每根 K 线收盘后
if kline.is_closed:
    # 评估风控逻辑（包括追踪退出）
    events = risk_manager.evaluate_and_mutate(kline, position, active_orders)

    # 处理事件
    for event in events:
        if event.event_category == "trailing_exit":
            # 执行市价平仓
            await self._execute_trailing_exit(position, event, kline)
```

**新增平仓执行方法**（修复：传入 active_orders 参数，明确 SHORT 滑点公式）：

```python
async def _execute_trailing_exit(
    self,
    position: Position,
    event: CloseEvent,
    kline: KlineData,
    active_orders: List[Order]  # 修复：作为参数传入
) -> None:
    """执行追踪退出平仓"""
    # 1. 取消所有未成交订单
    for order in active_orders:
        if order.status == OrderStatus.OPEN:
            await self._cancel_order(order.id)

    # 2. 计算平仓价（保守：使用 trailing_exit_price ± slippage）
    # LONG: 卖出，滑点向下（成交价更低）
    # SHORT: 买回，滑点向上（成交价更高）
    if position.direction == Direction.LONG:
        exit_price = event.exit_price * (1 - self._config.trailing_slippage_rate)
    else:  # SHORT
        exit_price = event.exit_price * (1 + self._config.trailing_slippage_rate)

    # 3. 计算平仓 PnL
    if position.direction == Direction.LONG:
        pnl = (exit_price - position.entry_price) * position.current_qty
    else:  # SHORT
        pnl = (position.entry_price - exit_price) * position.current_qty

    # 4. 更新仓位状态
    position.status = PositionStatus.CLOSED
    position.close_price = exit_price
    position.close_time = kline.timestamp
    position.realized_pnl = pnl

    # 5. 记录事件
    self.close_events.append(event)
```

### 参数配置

#### 推荐参数（基于用户建议）

```python
tp_trailing_enabled = True
tp_trailing_percent = Decimal('0.015')  # 1.5% 回撤容忍度
tp_trailing_activation_rr = Decimal('0.3')  # 0.3R 激活阈值
tp_trailing_enabled_levels = ["TP1", "TP2", "TP3", "TP4", "TP5"]  # 明确列出所有级别
trailing_slippage_rate = Decimal('0.001')  # 0.1% 滑点（与 tp_slippage_rate 一致）
```

**参数说明**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `tp_trailing_enabled` | False | 是否启用追踪退出 |
| `tp_trailing_percent` | 0.015 | 回撤容忍度（1.5%） |
| `tp_trailing_activation_rr` | 0.3 | 激活阈值（0.3R） |
| `tp_trailing_enabled_levels` | ["TP1"~"TP5"] | 追踪级别（明确列出） |
| `trailing_slippage_rate` | 0.001 | 平仓滑点率（0.1%） |

**激活阈值计算示例**（修复：基于 SL 距离）：

- Entry: 50000, SL: 49500（sl_distance = 500）
- Activation RR: 0.3
- Activation threshold: 50000 + 0.3 × 500 = 50150
- 效果：涨了 0.3R 就激活，与 TP1/TP2 是否成交无关

**追踪退出价计算示例**：

- Watermark: 50750（+1.5R）
- Trailing percent: 1.5%
- Trailing exit: 50750 × (1 - 0.015) = 49988.75 ≈ +1.35R

### 测试策略

#### 单元测试

```python
# tests/unit/test_trailing_exit.py

def test_trailing_exit_activation():
    """测试激活条件"""
    # 价格达到 0.3R → 激活
    assert position.tp_trailing_activated == True

def test_trailing_exit_price_update():
    """测试追踪退出价更新"""
    # watermark 上涨 → trailing_exit_price 跟随上涨
    assert position.trailing_exit_price > old_trailing_exit_price

def test_trailing_exit_trigger():
    """测试平仓触发"""
    # K 线最低价跌破 trailing_exit_price → 触发平仓
    assert len(events) == 1
    assert events[0].event_category == "trailing_exit"

def test_trailing_exit_not_activated():
    """测试未激活场景"""
    # 价格未达到激活阈值 → 不激活
    assert position.tp_trailing_activated == False

def test_trailing_exit_partial_tp():
    """测试部分 TP 成交后追踪"""
    # TP1 成交后，剩余仓位继续追踪
    assert position.trailing_exit_price is not None
```

#### 集成测试

```python
# tests/integration/test_trailing_exit_backtest.py

async def test_trailing_exit_improves_pnl():
    """验证追踪退出提升收益"""
    # 对比实验：
    # - 实验 A: 追踪退出关闭
    # - 实验 B: 追踪退出开启
    # 预期：实验 B 的 PnL > 实验 A
```

### 风险评估

#### 优势

1. **降低回撤**：锁定水位高点附近的利润，避免"涨了又跌回 SL"
2. **提升盈亏比**：把潜在亏损单变成小盈利单
3. **适应性强**：54% 胜率策略下也能生效（不需要到 TP）

#### 劣势

1. **过早平仓**：可能错过大行情（价格继续涨到 TP2）
   - 缓解：调整 `tp_trailing_percent` 参数（如 2%）
2. **滑点风险**：市价平仓可能有滑点
   - 缓解：回测中使用 `trailing_slippage_rate` 参数保守估计
3. **SL 竞争**：同一根 K 线 SL 和 Trailing Exit 同时满足时，SL 优先（保守处理）

#### 兼容性

- **向后兼容**：不影响现有 TP/SL 订单逻辑
- **配置开关**：`tp_trailing_enabled` 控制启用/关闭
- **渐进式部署**：先回测验证，再实盘测试

## 替代方案

### 方案 A：保持原设计（上调 TP）

- **优点**：代码已实现，无需修改
- **缺点**：54% 胜率策略下永远不会触发
- **结论**：❌ 不采纳

### 方案 B：追踪退出（本方案）

- **优点**：适应 54% 胜率策略，提升盈亏比
- **缺点**：可能过早平仓，错过大行情
- **结论**：✅ 采纳

### 方案 C：混合模式（部分仓位追踪退出，部分仓位等 TP）

- **优点**：平衡锁定利润和抓住大行情
- **缺点**：逻辑复杂，参数多
- **结论**：⏸️ 暂缓，先验证方案 B

## 实施计划

### Phase 1: 数据模型扩展（0.5 天）

- [ ] Position 新增 3 个字段
- [ ] CloseEvent 新增 `trailing_exit` 类型
- [ ] 更新单元测试

### Phase 2: 核心逻辑实现（1 天）

- [ ] `_apply_trailing_exit()` 方法
- [ ] `_check_trailing_activation()` 方法（修复：传入 sl_price 参数）
- [ ] `_create_trailing_activated_event()` 方法（新增）
- [ ] `_create_trailing_exit_event()` 方法
- [ ] 单元测试（5+ 用例）

### Phase 3: backtester 集成（0.5 天）

- [ ] K 线循环调用追踪退出
- [ ] `_execute_trailing_exit()` 方法（修复：传入 active_orders 参数）
- [ ] 集成测试

### Phase 4: 回测验证（1 天）

- [ ] 3 年全量回测（BTC/ETH/SOL）
- [ ] 对比实验：追踪退出 on vs off
- [ ] 参数敏感性测试

### Phase 5: 文档更新（0.5 天）

- [ ] 更新 `trailing-tp-delivery-report.md`
- [ ] 更新 `progress.md`
- [ ] 提交代码审查

**总工时**：3.5 天

## 决策门

| 条件 | 行动 |
|------|------|
| 追踪退出 on 的 3 年 PnL > off（提升 > 10%） | ✅ 追踪退出有效，合并代码 |
| 追踪退出 on 的 3 年 PnL ≈ off（提升 < 5%） | ⚠️ 参数调优，重新测试 |
| 追踪退出 on 的 3 年 PnL < off | ❌ 追踪退出无效，转向信号质量优化 |

## 参考

- 原设计文档：`docs/arch/trailing-tp-implementation-design.md`
- 交付报告：`docs/delivery/trailing-tp-delivery-report.md`
- 用户诊断：会话记录（2026-04-20）

---

**作者**: Architect
**日期**: 2026-04-20
**状态**: 提议（等待用户审核）
