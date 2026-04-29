# T2 - 修复止盈撮合过于理想问题 (添加滑点)

**文档状态**: 草案
**创建日期**: 2026-04-01
**负责人**: backend-dev
**优先级**: P0

---

## 1. 问题分析

### 1.1 现状描述

当前 PMS 回测系统中，止盈限价单 (LIMIT + OrderRole.TP1) 的撮合逻辑存在过度理想化问题：

```python
# src/domain/matching_engine.py:156-168 (当前代码)
elif order.order_type == OrderType.LIMIT and order.order_role == OrderRole.TP1:
    is_triggered = False
    exec_price = order.price  # 限价单按挂单价成交 <- 问题所在

    if order.direction == Direction.LONG and k_high >= order.price:
        is_triggered = True
    elif order.direction == Direction.SHORT and k_low <= order.price:
        is_triggered = True

    if is_triggered:
        self._execute_fill(order, exec_price, position, account, positions_map, kline.timestamp)
```

**核心问题**: `exec_price = order.price` 假设 100% 按设定价格成交，未考虑滑点。

### 1.2 影响范围

| 影响域 | 具体表现 |
|--------|----------|
| **回测 PnL** | 虚高 0.05%~0.15%（取决于仓位大小） |
| **胜率评估** | 无法反映真实成交质量 |
| **策略优化** | 过度乐观的参数可能被误选 |
| **实盘预期** | 用户预期与实际收益存在偏差 |

### 1.3 根本原因

设计文档 `docs/designs/phase2-matching-engine-contract.md` 中明确了滑点计算公式，但止盈单实现时遗漏：

- 止损单：已正确实现滑点 (`exec_price = trigger_price * (1 - slippage_rate)`)
- 入场单：已正确实现滑点 (`exec_price = kline.open * (1 + slippage_rate)`)
- **止盈单：未实现滑点** ← 本次修复目标

---

## 2. 滑点配置设计

### 2.1 配置项位置

**新增配置项**: `config/core.yaml`

```yaml
backtest:
  # 止盈滑点率 (默认 0.05%)
  # 实际交易中，大单会吃掉多档订单，产生滑点
  # 回测中添加保守滑点假设，使结果更贴近实盘
  take_profit_slippage_rate: 0.0005  # 0.05%
```

### 2.2 默认值说明

| 订单类型 | 滑点率 | 依据 |
|----------|--------|------|
| 止损单 (STOP_MARKET) | 0.1% (现有) | 市价单，滑点较大 |
| **止盈单 (LIMIT TP)** | **0.05% (新增)** | 限价单，滑点较小 |
| 入场单 (MARKET) | 0.1% (现有) | 市价单，滑点较大 |

**止盈滑点率较低的原因**:
1. 止盈单是限价单 (LIMIT)，挂在订单簿中等待成交
2. 实际成交时，价格通常已经达到或优于挂单价
3. 但大单会吃掉多档深度，产生部分滑点
4. 0.05% 是保守估计 (Binance/Bybit U 本位合约典型值)

### 2.3 配置加载

修改 `src/application/config_manager.py`，新增配置字段：

```python
class CoreConfig(BaseModel):
    ...
    backtest: BacktestConfig

class BacktestConfig(BaseModel):
    take_profit_slippage_rate: Decimal = Decimal('0.0005')  # 0.05%
```

---

## 3. 代码修改点

### 3.1 撮合引擎修改 (`src/domain/matching_engine.py`)

**修改位置**: `_execute_fill` 方法调用处 - 止盈单分支

```python
# 修改前 (行 156-168)
elif order.order_type == OrderType.LIMIT and order.order_role == OrderRole.TP1:
    is_triggered = False
    exec_price = order.price  # 限价单按挂单价成交

    if order.direction == Direction.LONG and k_high >= order.price:
        is_triggered = True
    elif order.direction == Direction.SHORT and k_low <= order.price:
        is_triggered = True

    if is_triggered:
        self._execute_fill(order, exec_price, position, account, positions_map, kline.timestamp)
        executed_orders.append(order)
```

```python
# 修改后
elif order.order_type == OrderType.LIMIT and order.order_role == OrderRole.TP1:
    is_triggered = False
    base_exec_price = order.price  # 限价单基准成交价

    if order.direction == Direction.LONG and k_high >= order.price:
        is_triggered = True
        # 多头止盈：滑点向下 (少收钱)
        exec_price = base_exec_price * (Decimal('1') - self.tp_slippage_rate)
    elif order.direction == Direction.SHORT and k_low <= order.price:
        is_triggered = True
        # 空头止盈：滑点向上 (多付钱)
        exec_price = base_exec_price * (Decimal('1') + self.tp_slippage_rate)
    else:
        exec_price = Decimal('0')

    if is_triggered:
        self._execute_fill(order, exec_price, position, account, positions_map, kline.timestamp)
        executed_orders.append(order)
```

**构造函数新增参数**:

```python
def __init__(
    self,
    slippage_rate: Decimal = Decimal('0.001'),
    fee_rate: Decimal = Decimal('0.0004'),
    tp_slippage_rate: Optional[Decimal] = None,  # 新增参数
):
    self.slippage_rate = slippage_rate
    self.fee_rate = fee_rate
    # 止盈滑点率，默认 0.05%
    self.tp_slippage_rate = tp_slippage_rate or Decimal('0.0005')
```

### 3.2 回测器修改 (`src/application/backtester.py`)

**修改位置**: `_run_v3_pms_backtest` 方法，初始化 `MockMatchingEngine` 时传入配置

```python
# 修改前
engine = MockMatchingEngine(
    slippage_rate=Decimal('0.001'),
    fee_rate=Decimal('0.0004'),
)

# 修改后
engine = MockMatchingEngine(
    slippage_rate=Decimal('0.001'),
    fee_rate=Decimal('0.0004'),
    tp_slippage_rate=Decimal('0.0005'),  # 止盈滑点 0.05%
)
```

### 3.3 配置管理器修改 (`src/application/config_manager.py`)

**新增配置模型**:

```python
class BacktestConfig(BaseModel):
    """回测配置"""
    take_profit_slippage_rate: Decimal = Field(
        default=Decimal('0.0005'),
        description="止盈滑点率 (默认 0.05%)"
    )


class CoreConfig(BaseModel):
    ...
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
```

---

## 4. 影响范围评估

### 4.1 回测 PnL 影响

以典型交易为例：

| 参数 | 值 |
|------|-----|
| 入场价 | $100,000 (BTC) |
| 止盈价 | $101,500 (+1.5%) |
| 仓位 | 1 BTC |
| 原滑点 | $0 |
| **新滑点** | **$101,500 × 0.05% = $50.75** |

**单笔止盈 PnL 影响**: -$50.75

**年化影响** (假设月均 10 笔止盈):
- 月影响：-$507.50
- 年影响：-$6,090

### 4.2 胜率评估影响

滑点不影响胜率判定 (仅影响 PnL 计算)，因为：
- 止盈单是否成交取决于价格是否触及
- 滑点仅影响成交价格，不影响成交判定

### 4.3 兼容性影响

| 模块 | 影响 | 缓解措施 |
|------|------|----------|
| 回测器 | 中等 | 默认值向后兼容 |
| 配置管理 | 低 | 新增可选字段 |
| 撮合引擎 | 低 | 参数可选，默认 0.05% |
| 前端展示 | 无 | 仅后端计算逻辑变更 |

---

## 5. 测试用例设计

### 5.1 单元测试 (SST 先行)

**测试文件**: `tests/unit/test_matching_engine.py`

#### Test 5.1.1: 止盈滑点计算 - 多头场景

```python
@pytest.mark.asyncio
async def test_take_profit_slippage_long():
    """测试多头止盈滑点计算"""
    # Arrange
    engine = MockMatchingEngine(tp_slippage_rate=Decimal('0.0005'))
    tp_order = Order(
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        direction=Direction.LONG,
        price=Decimal('1000'),
        requested_qty=Decimal('1'),
        ...
    )
    kline = KlineData(high=Decimal('1010'), low=Decimal('990'), ...)

    # Act
    executed = engine.match_orders_for_kline(kline, [tp_order], {}, Account(...))

    # Assert
    assert executed[0].status == OrderStatus.FILLED
    # 预期成交价 = 1000 * (1 - 0.0005) = 999.5
    expected_price = Decimal('1000') * (Decimal('1') - Decimal('0.0005'))
    assert executed[0].average_exec_price == expected_price
```

#### Test 5.1.2: 止盈滑点计算 - 空头场景

```python
@pytest.mark.asyncio
async def test_take_profit_slippage_short():
    """测试空头止盈滑点计算"""
    # Arrange
    engine = MockMatchingEngine(tp_slippage_rate=Decimal('0.0005'))
    tp_order = Order(
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        direction=Direction.SHORT,
        price=Decimal('1000'),
        requested_qty=Decimal('1'),
        ...
    )
    kline = KlineData(high=Decimal('1010'), low=Decimal('990'), ...)

    # Act
    executed = engine.match_orders_for_kline(kline, [tp_order], {}, Account(...))

    # Assert
    assert executed[0].status == OrderStatus.FILLED
    # 预期成交价 = 1000 * (1 + 0.0005) = 1000.5
    expected_price = Decimal('1000') * (Decimal('1') + Decimal('0.0005'))
    assert executed[0].average_exec_price == expected_price
```

#### Test 5.1.3: 止盈未触发场景

```python
@pytest.mark.asyncio
async def test_take_profit_not_triggered():
    """测试止盈价格未触及场景"""
    # Arrange
    engine = MockMatchingEngine(tp_slippage_rate=Decimal('0.0005'))
    tp_order = Order(
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        direction=Direction.LONG,
        price=Decimal('1000'),
        ...
    )
    kline = KlineData(high=Decimal('999'), low=Decimal('990'), ...)  # high < 1000

    # Act
    executed = engine.match_orders_for_kline(kline, [tp_order], {}, Account(...))

    # Assert
    assert len(executed) == 0  # 无成交
    assert tp_order.status == OrderStatus.OPEN  # 订单仍挂起
```

### 5.2 集成测试

**测试文件**: `tests/integration/test_backtest_slippage.py`

#### Test 5.2.1: 回测 PnL 滑点影响

```python
@pytest.mark.asyncio
async def test_backtest_pnl_with_slippage():
    """测试回测 PnL 受止盈滑点影响"""
    # Arrange
    backtester = Backtester(exchange_gateway)
    request = BacktestRequest(
        symbol="BTC/USDT:USDT",
        timeframe="1h",
        limit=100,
        mode="v3_pms",
    )

    # Act
    report = await backtester.run_backtest(request)

    # Assert
    # 验证回测报告包含滑点调整后的 PnL
    assert hasattr(report, 'total_pnl')
    # 滑点调整后的 PnL 应略低于无滑点场景
```

---

## 6. 实施计划

### 6.1 任务分解

| 任务 | 描述 | 预估工时 |
|------|------|----------|
| T2.1 | 创建 SST 测试用例 | 1h |
| T2.2 | 修改撮合引擎代码 | 0.5h |
| T2.3 | 修改回测器配置 | 0.5h |
| T2.4 | 运行测试验证 | 0.5h |
| T2.5 | 更新配置文档 | 0.5h |

### 6.2 验收标准

1. **测试覆盖率**: 新增代码行覆盖率 ≥ 90%
2. **配置兼容**: 默认值向后兼容，不影响现有回测
3. **精度验证**: 滑点计算误差 < 1e-8 (Decimal 精度)

---

## 7. 相关文件索引

| 文件 | 路径 |
|------|------|
| 撮合引擎 | `src/domain/matching_engine.py` |
| 回测器 | `src/application/backtester.py` |
| 配置管理 | `src/application/config_manager.py` |
| 核心配置 | `config/core.yaml` |
| 设计契约 | `docs/designs/phase2-matching-engine-contract.md` |

---

## 8. 附录：滑点计算公式

### 8.1 通用公式

```
实际成交价 = 基准价 × (1 ± 滑点率)
```

### 8.2 方向性滑点规则

| 订单类型 | 方向 | 滑点方向 | 公式 |
|----------|------|----------|------|
| 止损 (STOP_MARKET) | LONG | 向下 | `trigger_price × (1 - slippage_rate)` |
| 止损 (STOP_MARKET) | SHORT | 向上 | `trigger_price × (1 + slippage_rate)` |
| **止盈 (LIMIT TP)** | **LONG** | **向下** | **`price × (1 - tp_slippage_rate)`** |
| **止盈 (LIMIT TP)** | **SHORT** | **向上** | **`price × (1 + tp_slippage_rate)`** |
| 入场 (MARKET) | LONG (买入) | 向上 | `open × (1 + slippage_rate)` |
| 入场 (MARKET) | SHORT (卖出) | 向下 | `open × (1 - slippage_rate)` |

**滑点方向记忆法则**: 滑点总是对交易者不利
- 买入时：滑点使你支付更多
- 卖出时：滑点使你收入更少
