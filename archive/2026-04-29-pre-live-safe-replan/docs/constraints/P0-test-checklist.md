# P0 WebSocket K 线选择逻辑修复 - 测试清单

> **文档类型**: 测试清单 (Test Checklist)  
> **关联 ADR**: [P0-websocket-kline-fix-design.md](./P0-websocket-kline-fix-design.md)  
> **创建日期**: 2026-04-08  
> **状态**: 待执行 (Pending Execution)  
> **覆盖率要求**: >85%

---

## 一、测试总览

### 1.1 测试类型分布

| 测试类型 | 用例数量 | 优先级 | 执行阶段 |
|----------|----------|--------|----------|
| 单元测试 | 12 | P0 | 开发阶段 |
| 集成测试 | 4 | P0 | 集成阶段 |
| 验收测试 | 3 | P0 | 验收阶段 |
| **总计** | **19** | - | - |

### 1.2 测试文件清单

| # | 测试文件 | 测试类型 | 关联修改 |
|---|----------|----------|----------|
| 1 | `tests/unit/test_exchange_gateway_websocket.py` | 单元测试 | `exchange_gateway.py` |
| 2 | `tests/unit/test_strategy_engine_pinbar.py` | 单元测试 | `strategy_engine.py` |
| 3 | `tests/unit/test_filter_factory_atr.py` | 单元测试 | `filter_factory.py` |
| 4 | `tests/integration/test_websocket_kline_selection.py` | 集成测试 | 端到端验证 |

---

## 二、单元测试用例

### 2.1 `test_exchange_gateway_websocket.py`

**测试文件路径**: `tests/unit/test_exchange_gateway_websocket.py`

---

#### 测试用例 1: `test_x_field_priority`

**测试目标**: 验证交易所 `x` 字段优先使用

**前置条件**:
- Mock WebSocket 返回包含 `x=true` 的 OHLCV 数据

**测试代码**:
```python
@pytest.mark.asyncio
async def test_x_field_priority():
    """验证当 x=true 时，ohlcv[-1] 被正确解析为已收盘 K 线"""
    # Arrange
    mock_ohlcv = [
        [1000, 100, 110, 90, 105, 1000, {"x": True}],  # 已收盘
    ]
    mock_ws_exchange = AsyncMock()
    mock_ws_exchange.watch_ohlcv = AsyncMock(return_value=mock_ohlcv)
    
    gateway = ExchangeGateway(...)
    gateway.ws_exchange = mock_ws_exchange
    
    received_klines = []
    async def callback(kline):
        received_klines.append(kline)
    
    # Act
    # 模拟单次推送
    await gateway._process_websocket_ohlcv(mock_ohlcv, callback, "BTC/USDT", "1h")
    
    # Assert
    assert len(received_klines) == 1
    assert received_klines[0].is_closed == True
    assert received_klines[0].info == {"x": True}
    assert received_klines[0].close == Decimal("105")
```

**验收标准**:
- [ ] K 线被正确推送给回调
- [ ] `is_closed=True`
- [ ] `info` 字段包含原始数据

---

#### 测试用例 2: `test_x_false_skip`

**测试目标**: 验证 `x=false` 时跳过未收盘 K 线

**前置条件**:
- Mock WebSocket 返回包含 `x=false` 的 OHLCV 数据

**测试代码**:
```python
@pytest.mark.asyncio
async def test_x_false_skip():
    """验证当 x=false 时，跳过未收盘 K 线"""
    # Arrange
    mock_ohlcv = [
        [1000, 100, 110, 90, 105, 1000, {"x": False}],  # 未收盘
    ]
    mock_ws_exchange = AsyncMock()
    mock_ws_exchange.watch_ohlcv = AsyncMock(return_value=mock_ohlcv)
    
    gateway = ExchangeGateway(...)
    gateway.ws_exchange = mock_ws_exchange
    
    received_klines = []
    async def callback(kline):
        received_klines.append(kline)
    
    # Act
    await gateway._process_websocket_ohlcv(mock_ohlcv, callback, "BTC/USDT", "1h")
    
    # Assert
    assert len(received_klines) == 0  # 不应推送未收盘 K 线
```

**验收标准**:
- [ ] 未收盘 K 线不被推送
- [ ] 无异常抛出

---

#### 测试用例 3: `test_timestamp_fallback`

**测试目标**: 验证时间戳后备机制

**前置条件**:
- Mock WebSocket 返回不包含 `x` 字段的 OHLCV 数据

**测试代码**:
```python
@pytest.mark.asyncio
async def test_timestamp_fallback():
    """验证无 x 字段时，使用时间戳推断机制"""
    # Arrange
    mock_ohlcv_prev = [
        [1000, 100, 110, 90, 105, 1000, {}],  # 前一根 K 线
        [2000, 105, 115, 95, 110, 1000, {}],  # 当前 K 线（时间戳变化）
    ]
    mock_ohlcv_same = [
        [1000, 100, 110, 90, 105, 1000, {}],  # 前一根 K 线
        [1000, 105, 115, 95, 110, 1000, {}],  # 当前 K 线（时间戳未变）
    ]
    
    gateway = ExchangeGateway(...)
    
    received_klines = []
    async def callback(kline):
        received_klines.append(kline)
    
    # Act & Assert
    # 第一次调用：时间戳未变化，不应推送
    await gateway._process_websocket_ohlcv(mock_ohlcv_same, callback, "BTC/USDT", "1h")
    assert len(received_klines) == 0
    
    # 第二次调用：时间戳变化，应推送前一根 K 线
    await gateway._process_websocket_ohlcv(mock_ohlcv_prev, callback, "BTC/USDT", "1h")
    assert len(received_klines) == 1
    assert received_klines[0].timestamp == 1000  # 前一根 K 线的时间戳
```

**验收标准**:
- [ ] 时间戳变化时推送前一根 K 线
- [ ] 时间戳未变化时不推送

---

#### 测试用例 4: `test_parse_ohlcv_with_x_field`

**测试目标**: 验证 `_parse_ohlcv()` 正确解析 `x` 字段

**测试代码**:
```python
def test_parse_ohlcv_with_x_field():
    """验证 _parse_ohlcv 正确解析 x 字段"""
    # Arrange
    gateway = ExchangeGateway(...)
    candle = [1000, 100, 110, 90, 105, 1000, {"x": True}]
    
    # Act
    kline = gateway._parse_ohlcv(candle, "BTC/USDT", "1h", {"x": True})
    
    # Assert
    assert kline.is_closed == True
    assert kline.info == {"x": True}
    assert kline.close == Decimal("105")
```

**验收标准**:
- [ ] `is_closed` 正确设置
- [ ] `info` 字段保留原始数据

---

#### 测试用例 5: `test_parse_ohlcv_without_x_field`

**测试目标**: 验证无 `x` 字段时的默认行为

**测试代码**:
```python
def test_parse_ohlcv_without_x_field():
    """验证无 x 字段时默认为已收盘"""
    # Arrange
    gateway = ExchangeGateway(...)
    candle = [1000, 100, 110, 90, 105, 1000]  # 无 info
    
    # Act
    kline = gateway._parse_ohlcv(candle, "BTC/USDT", "1h", None)
    
    # Assert
    assert kline.is_closed == True  # 默认假设已收盘
    assert kline.info is None
```

**验收标准**:
- [ ] 默认 `is_closed=True`
- [ ] 无异常抛出

---

### 2.2 `test_strategy_engine_pinbar.py`

**测试文件路径**: `tests/unit/test_strategy_engine_pinbar.py`

---

#### 测试用例 6: `test_pinbar_min_range_with_atr`

**测试目标**: 验证 ATR 10% 最小波幅检查

**前置条件**:
- ATR=50 USDT
- K 线波幅=4 USDT（小于 ATR 10%=5）

**测试代码**:
```python
def test_pinbar_min_range_with_atr():
    """验证 ATR 可用时，使用 ATR 10% 作为最小波幅"""
    # Arrange
    config = PinbarConfig()
    strategy = PinbarStrategy(config)
    
    kline = KlineData(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp=1000,
        open=Decimal("100"),
        high=Decimal("104"),  # 波幅 = 4
        low=Decimal("100"),
        close=Decimal("103"),
        volume=Decimal("1000"),
        is_closed=True,
    )
    atr_value = Decimal("50")  # ATR = 50
    
    # Act
    result = strategy.detect(kline, atr_value=atr_value)
    
    # Assert
    assert result is None  # 波幅 4 < 5 (50*0.1)，应被过滤
```

**验收标准**:
- [ ] 波幅 < ATR 10% 时返回 `None`
- [ ] 不被误判为 Pinbar

---

#### 测试用例 7: `test_pinbar_min_range_without_atr`

**测试目标**: 验证无 ATR 时使用固定后备值

**前置条件**:
- ATR 不可用
- K 线波幅=0.3 USDT（小于 0.5）

**测试代码**:
```python
def test_pinbar_min_range_without_atr():
    """验证无 ATR 时，使用 0.5 USDT 固定后备值"""
    # Arrange
    config = PinbarConfig()
    strategy = PinbarStrategy(config)
    
    kline = KlineData(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp=1000,
        open=Decimal("100"),
        high=Decimal("100.3"),  # 波幅 = 0.3
        low=Decimal("100"),
        close=Decimal("100.2"),
        volume=Decimal("1000"),
        is_closed=True,
    )
    
    # Act
    result = strategy.detect(kline, atr_value=None)
    
    # Assert
    assert result is None  # 波幅 0.3 < 0.5，应被过滤
```

**验收标准**:
- [ ] 波幅 < 0.5 USDT 时返回 `None`
- [ ] 无 ATR 时使用固定后备值

---

#### 测试用例 8: `test_pinbar_valid_with_sufficient_range`

**测试目标**: 验证有效 Pinbar 正常检测

**前置条件**:
- K 线波幅充足
- 符合 Pinbar 几何形态

**测试代码**:
```python
def test_pinbar_valid_with_sufficient_range():
    """验证波幅充足且形态符合时，正常检测 Pinbar"""
    # Arrange
    config = PinbarConfig()
    strategy = PinbarStrategy(config)
    
    # 有效 Pinbar：长下影线，body 在顶部
    kline = KlineData(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp=1000,
        open=Decimal("108"),
        high=Decimal("110"),
        low=Decimal("100"),  # 长下影线
        close=Decimal("109"),  # body 在顶部
        volume=Decimal("1000"),
        is_closed=True,
    )
    atr_value = Decimal("50")  # ATR = 50，min_range = 5
    
    # Act
    result = strategy.detect(kline, atr_value=atr_value)
    
    # Assert
    assert result is not None
    assert result.direction == Direction.LONG
    assert result.score > 0
```

**验收标准**:
- [ ] 有效 Pinbar 被正确检测
- [ ] 方向判断正确
- [ ] 评分合理

---

#### 测试用例 9: `test_pinbar_edge_case_zero_range`

**测试目标**: 验证零波幅 K 线处理

**测试代码**:
```python
def test_pinbar_edge_case_zero_range():
    """验证零波幅 K 线（high=low）被正确处理"""
    # Arrange
    config = PinbarConfig()
    strategy = PinbarStrategy(config)
    
    kline = KlineData(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp=1000,
        open=Decimal("100"),
        high=Decimal("100"),  # 零波幅
        low=Decimal("100"),
        close=Decimal("100"),
        volume=Decimal("1000"),
        is_closed=True,
    )
    
    # Act
    result = strategy.detect(kline, atr_value=Decimal("50"))
    
    # Assert
    assert result is None  # 零波幅应直接返回
```

**验收标准**:
- [ ] 零波幅 K 线返回 `None`
- [ ] 无异常抛出

---

### 2.3 `test_filter_factory_atr.py`

**测试文件路径**: `tests/unit/test_filter_factory_atr.py`

---

#### 测试用例 10: `test_atr_filter_default_disabled`

**测试目标**: 验证 ATR 过滤器默认不启用

**测试代码**:
```python
def test_atr_filter_default_disabled():
    """验证 AtrFilterDynamic 默认 enabled=False"""
    # Arrange & Act
    filter = AtrFilterDynamic()
    
    # Assert
    assert filter._enabled == False
    assert filter._min_atr_ratio == Decimal("0.001")
```

**验收标准**:
- [ ] `enabled=False` 默认值正确
- [ ] `min_atr_ratio=0.001` 保持当前值

---

#### 测试用例 11: `test_atr_filter_check_when_disabled`

**测试目标**: 验证禁用时过滤器自动通过

**测试代码**:
```python
def test_atr_filter_check_when_disabled():
    """验证 enabled=False 时，过滤器自动通过"""
    # Arrange
    filter = AtrFilterDynamic(enabled=False)
    
    kline = KlineData(...)
    pattern = PatternResult(...)
    context = FilterContext(kline=kline)
    
    # Act
    result = filter.check(pattern, context)
    
    # Assert
    assert result.passed == True
    assert result.reason == "filter_disabled"
```

**验收标准**:
- [ ] 禁用时自动通过
- [ ] `reason="filter_disabled"`

---

#### 测试用例 12: `test_atr_filter_manual_enable`

**测试目标**: 验证用户可手动启用

**测试代码**:
```python
def test_atr_filter_manual_enable():
    """验证用户可手动启用 ATR 过滤器"""
    # Arrange & Act
    filter = AtrFilterDynamic(enabled=True, min_atr_ratio=Decimal("0.02"))
    
    # Assert
    assert filter._enabled == True
    assert filter._min_atr_ratio == Decimal("0.02")
```

**验收标准**:
- [ ] 用户可自定义 `enabled=True`
- [ ] 用户可自定义 `min_atr_ratio`

---

## 三、集成测试用例

### 3.1 `test_websocket_kline_selection.py`

**测试文件路径**: `tests/integration/test_websocket_kline_selection.py`

---

#### 测试用例 13: `test_websocket_only_pushes_closed_klines`

**测试目标**: 验证 WebSocket 仅推送已收盘 K 线

**前置条件**:
- Mock WebSocket 推送多根 K 线（含未收盘和已收盘）

**测试代码**:
```python
@pytest.mark.asyncio
async def test_websocket_only_pushes_closed_klines():
    """集成测试：WebSocket 仅推送已收盘 K 线"""
    # Arrange
    mock_ohlcv_sequence = [
        # 第 1 次推送：x=false（未收盘）
        [[1000, 100, 110, 90, 105, 1000, {"x": False}]],
        # 第 2 次推送：x=true（已收盘）
        [[1000, 100, 110, 90, 105, 1000, {"x": True}]],
        # 第 3 次推送：x=false（下一根未收盘）
        [
            [1000, 100, 110, 90, 105, 1000, {"x": True}],
            [2000, 105, 115, 95, 110, 1000, {"x": False}],
        ],
    ]
    
    gateway = ExchangeGateway(...)
    received_klines = []
    
    async def mock_watch_ohlcv(symbol, timeframe):
        return mock_ohlcv_sequence.pop(0)
    
    gateway.ws_exchange = AsyncMock()
    gateway.ws_exchange.watch_ohlcv = AsyncMock(side_effect=mock_watch_ohlcv)
    
    async def callback(kline):
        received_klines.append(kline)
    
    # Act
    # 模拟 3 次推送
    for _ in range(3):
        ohlcv = await mock_watch_ohlcv("BTC/USDT", "1h")
        await gateway._process_websocket_ohlcv(ohlcv, callback, "BTC/USDT", "1h")
    
    # Assert
    assert len(received_klines) == 1  # 只推送 1 根已收盘 K 线
    assert received_klines[0].is_closed == True
```

**验收标准**:
- [ ] 只推送已收盘 K 线
- [ ] 未收盘 K 线被正确过滤

---

#### 测试用例 14: `test_pinbar_with_low_volatility`

**测试目标**: 验证低波动市场 Pinbar 过滤

**测试代码**:
```python
@pytest.mark.asyncio
async def test_pinbar_with_low_volatility():
    """集成测试：低波动市场 Pinbar 被过滤"""
    # Arrange
    config = PinbarConfig()
    strategy = PinbarStrategy(config)
    
    # 低波动 K 线（波幅极小）
    kline = KlineData(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp=1000,
        open=Decimal("100.01"),
        high=Decimal("100.02"),  # 波幅 = 0.01
        low=Decimal("100.00"),
        close=Decimal("100.01"),
        volume=Decimal("1000"),
        is_closed=True,
    )
    
    # Act
    result = strategy.detect(kline, atr_value=Decimal("50"))
    
    # Assert
    assert result is None  # 波幅 0.01 < 5 (50*0.1)，应被过滤
```

**验收标准**:
- [ ] 低波动 K 线不触发 Pinbar
- [ ] 防止开盘初期误判

---

#### 测试用例 15: `test_end_to_end_kline_flow`

**测试目标**: 验证端到端 K 线处理流程

**测试代码**:
```python
@pytest.mark.asyncio
async def test_end_to_end_kline_flow():
    """集成测试：端到端 K 线处理流程"""
    # Arrange
    # 1. WebSocket 推送已收盘 K 线
    mock_ohlcv = [[1000, 100, 110, 90, 105, 1000, {"x": True}]]
    
    # 2. 配置有效 Pinbar 形态
    kline = KlineData(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp=1000,
        open=Decimal("108"),
        high=Decimal("110"),
        low=Decimal("100"),
        close=Decimal("109"),
        volume=Decimal("1000"),
        is_closed=True,
    )
    
    # 3. 模拟完整流程
    gateway = ExchangeGateway(...)
    signals_fired = []
    
    # Act
    # 模拟 WebSocket -> Strategy -> Signal 流程
    # ...（详细实现略）
    
    # Assert
    # 验证信号正确触发
    assert len(signals_fired) == 1
```

**验收标准**:
- [ ] 完整流程无异常
- [ ] 信号正确触发

---

#### 测试用例 16: `test_concurrent_websocket_subscriptions`

**测试目标**: 验证多品种并发订阅

**测试代码**:
```python
@pytest.mark.asyncio
async def test_concurrent_websocket_subscriptions():
    """集成测试：多品种并发订阅"""
    # Arrange
    gateway = ExchangeGateway(...)
    received_klines = {"BTC/USDT": [], "ETH/USDT": []}
    
    async def callback(kline):
        received_klines[kline.symbol].append(kline)
    
    # Act
    # 并发订阅多个品种
    await asyncio.gather(
        gateway._subscribe_ohlcv_loop("BTC/USDT", "1h", callback),
        gateway._subscribe_ohlcv_loop("ETH/USDT", "1h", callback),
    )
    
    # Assert
    # 验证各品种独立处理
    assert len(received_klines["BTC/USDT"]) >= 0
    assert len(received_klines["ETH/USDT"]) >= 0
```

**验收标准**:
- [ ] 多品种并发无冲突
- [ ] 各品种独立处理

---

## 四、验收测试用例

### 4.1 验收标准

| # | 验收项 | 通过标准 | 状态 |
|---|--------|----------|------|
| 1 | 功能性 | 所有单元测试 100% 通过 | ⏳ 待执行 |
| 2 | 正确性 | WebSocket 仅推送已收盘 K 线 | ⏳ 待执行 |
| 3 | 性能 | 无显著性能回退 | ⏳ 待执行 |
| 4 | 覆盖率 | 修改代码行覆盖率 >85% | ⏳ 待执行 |

---

#### 测试用例 17: `test_coverage_requirement`

**测试目标**: 验证代码覆盖率

**执行方式**:
```bash
# 运行覆盖率测试
pytest --cov=src/infrastructure/exchange_gateway \
       --cov=src/domain/strategy_engine \
       --cov-report=html \
       tests/unit/test_exchange_gateway_websocket.py \
       tests/unit/test_strategy_engine_pinbar.py

# 检查覆盖率报告
# 要求：修改代码行覆盖率 >85%
```

**验收标准**:
- [ ] 总体覆盖率 >85%
- [ ] 关键函数覆盖率 100%

---

#### 测试用例 18: `test_regression_prevention`

**测试目标**: 验证无回归

**执行方式**:
```bash
# 运行所有现有测试
pytest tests/unit/ tests/integration/ -v

# 验证所有原有测试仍通过
```

**验收标准**:
- [ ] 所有原有测试通过
- [ ] 无功能回退

---

#### 测试用例 19: `test_logging_level`

**测试目标**: 验证日志级别为 DEBUG

**执行方式**:
```bash
# 运行测试并检查日志输出
pytest tests/unit/test_exchange_gateway_websocket.py -v -s

# 验证日志输出频率合理（不刷屏）
```

**验收标准**:
- [ ] 日志级别为 DEBUG
- [ ] 无 INFO/WARNING 级别刷屏

---

## 五、测试执行顺序

### 5.1 开发阶段

```
1. 单元测试 (12 个用例)
   ├── test_exchange_gateway_websocket.py (5 个用例)
   ├── test_strategy_engine_pinbar.py (4 个用例)
   └── test_filter_factory_atr.py (3 个用例)
```

### 5.2 集成阶段

```
2. 集成测试 (4 个用例)
   └── test_websocket_kline_selection.py (4 个用例)
```

### 5.3 验收阶段

```
3. 验收测试 (3 个用例)
   ├── 覆盖率验证
   ├── 回归测试
   └── 日志级别验证
```

---

## 六、测试环境要求

### 6.1 依赖安装

```bash
pip install pytest pytest-asyncio pytest-cov
```

### 6.2 测试配置

```ini
# pytest.ini
[pytest]
asyncio_mode = auto
addopts = -v --cov=src --cov-report=html
```

### 6.3 Mock 数据

- Mock OHLCV 数据格式
- Mock WebSocket 响应
- Mock ATR 值

---

## 七、问题记录

### 7.1 已知问题

| # | 问题描述 | 状态 | 解决方案 |
|---|----------|------|----------|
| 1 | - | - | - |

### 7.2 测试失败处理

1. **分析失败原因**
2. **修复代码或测试**
3. **重新执行测试**
4. **记录问题**

---

*文档版本: 1.0*  
*创建日期: 2026-04-08*  
*最后更新: 2026-04-08*
