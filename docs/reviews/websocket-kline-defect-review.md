# 架构审查报告 - WebSocket K 线处理与形态检测缺陷

> **审查日期**: 2026-04-07
> **审查人**: Architect
> **审查范围**: WebSocket K 线处理、形态检测逻辑
> **严重程度**: 🔴 **P0 - 严重缺陷**（影响信号质量）

---

## 一、问题概述

用户报告了历史版本中发现的 3 个关键问题，经架构审查确认，**当前系统存在全部 3 个问题**。

---

## 二、问题详细分析

### 🔴 问题 1: WebSocket 未正确过滤未收盘 K 线

**严重程度**: P0（严重）
**影响范围**: 信号误触发、形态误判

#### 代码位置

- `src/infrastructure/exchange_gateway.py:374-462` - WebSocket K 线订阅
- `src/infrastructure/exchange_gateway.py:439-462` - `_is_candle_closed()` 方法

#### 当前实现

```python
def _is_candle_closed(self, kline: KlineData, symbol: str, timeframe: str) -> bool:
    """
    Track if a candle has closed by detecting timestamp change.
    """
    key = f"{symbol}:{timeframe}"
    current_ts = kline.timestamp

    if key in self._candle_timestamps:
        if current_ts != self._candle_timestamps[key]:
            # Timestamp changed - previous candle is closed
            self._candle_timestamps[key] = current_ts
            return True
    else:
        self._candle_timestamps[key] = current_ts

    return False
```

#### 问题分析

1. **时间戳推断逻辑不可靠**：
   - 代码通过"时间戳变化"推断 K 线是否收盘
   - 但 WebSocket 实时推送的 K 线数据本身包含 `is_closed` 字段（交易所提供）
   - 当前代码**完全忽略**了交易所提供的 `is_closed` 字段

2. **`_parse_ohlcv()` 方法未设置 `is_closed`**：
   - 代码位置：`exchange_gateway.py:311-320`
   - 方法构造 `KlineData` 对象时，**没有设置** `is_closed` 字段
   - 使用的是模型默认值 `is_closed: bool = True`（models.py:94）
   - 这意味着所有通过 WebSocket 接收的 K 线都被标记为已收盘

3. **首次订阅时的问题**：
   - 首次订阅时，`_candle_timestamps[key]` 不存在，直接设置为当前时间戳并返回 `False`
   - 这意味着第一根 K 线**永远不会触发回调**（即使已收盘）
   - 但第二根 K 线的时间戳改变时，第一根 K 线才会被触发

4. **实时推送问题**：
   - WebSocket 实时推送未收盘的 K 线更新（每秒多次）
   - 但 `_is_candle_closed()` 在时间戳未改变时返回 `False`
   - 这意味着未收盘的 K 线**被正确过滤**（但不是通过 `is_closed` 字段）

#### 根本原因

**契约违反**：
- `KlineData` 模型定义 `is_closed: bool = True`（models.py:94）
- 但 WebSocket 推送的数据应该使用交易所提供的 `is_closed` 字段
- 当前实现**错误地假设所有 K 线都已收盘**

---

### 🔴 问题 2: `process_kline()` 缺少防御性检查

**严重程度**: P0（严重）
**影响范围**: 允许未收盘 K 线触发信号

#### 代码位置

- `src/application/signal_pipeline.py:455-560`

#### 当前实现

```python
async def process_kline(self, kline: KlineData) -> None:
    """
    Process a single closed K-line.

    Args:
        kline: Closed K-line data
    """
    try:
        # Ensure async primitives and flush worker are running (lazy init)
        self._ensure_flush_worker()

        # Ensure lock is available for this call
        lock = self._get_runner_lock()

        # Check pending signals for performance tracking
        if self._repository is not None:
            from src.application.performance_tracker import PerformanceTracker
            tracker = PerformanceTracker()
            await tracker.check_pending_signals(kline, self._repository)

        # Store in history
        self._store_kline(kline)

        # Run strategy engine with lock protection
        async with lock:
            attempts = self._run_strategy(kline)

        # ... (后续处理)
```

#### 问题分析

1. **缺少 `is_closed` 检查**：
   - 方法注释说"Process a single closed K-line"
   - 但代码中**没有验证** `kline.is_closed == True`
   - 如果 WebSocket 层传递了未收盘的 K 线，会被直接处理

2. **违反契约**：
   - 模型定义 `is_closed: bool = True`（默认值）
   - 但这个默认值**不代表所有 K 线都已收盘**
   - 应该在处理前强制验证契约

3. **缺少防御性编程**：
   - 用户历史问题描述："K6 刚开盘 3 秒就触发了信号"
   - 如果在 `process_kline()` 开头添加检查，可以完全避免此问题

#### 推荐修复

```python
async def process_kline(self, kline: KlineData) -> None:
    """
    Process a single closed K-line.

    Args:
        kline: Closed K-line data
    """
    # 🔴 P0 修复：验证 K 线是否已收盘
    if not kline.is_closed:
        logger.warning(
            f"Received unclosed K-line, ignoring: {kline.symbol} {kline.timeframe} "
            f"timestamp={kline.timestamp}"
        )
        return

    try:
        # ... (现有逻辑)
```

---

### 🔴 问题 3: Pinbar 检测缺少最小波幅检查

**严重程度**: P0（严重）
**影响范围**: 刚开盘的 K 线被误判为 Pinbar

#### 代码位置

- `src/domain/strategy_engine.py:184-276` - `PinbarStrategy.detect()` 方法

#### 当前实现

```python
def detect(self, kline: KlineData, atr_value: Optional[Decimal] = None) -> Optional[PatternResult]:
    cfg = self._config

    high = kline.high
    low = kline.low
    close = kline.close
    open_price = kline.open

    # Calculate candle range
    candle_range = high - low
    if candle_range == Decimal(0):
        return None  # 🔴 只检查了 candle_range == 0

    # Calculate body size
    body_size = abs(close - open_price)
    body_ratio = body_size / candle_range

    # Calculate upper and lower wicks
    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low

    # Determine dominant wick and calculate ratio
    dominant_wick = max(upper_wick, lower_wick)
    wick_ratio = dominant_wick / candle_range

    # Check if it meets Pinbar criteria
    is_pinbar = (
        wick_ratio >= cfg.min_wick_ratio
        and body_ratio <= cfg.max_body_ratio
    )

    # ... (后续逻辑)
```

#### 问题分析

1. **缺少最小波幅检查**：
   - 代码只检查 `candle_range == Decimal(0)`（完全无波动的 K 线）
   - 对于波幅极小的 K 线（如 `candle_range = 0.01 USDT`），仍会进行形态检测
   - 刚开盘的 K 线（价格≈开盘价）可能被误判为 Pinbar

2. **用户历史案例**：
   - "K6 刚开盘 3 秒就被误判为 Pinbar"
   - 如果开盘价 = 2098.28，最高 = 2098.30，最低 = 2098.27
   - `candle_range = 0.03 USDT`（> 0，会通过检查）
   - 可能满足 Pinbar 几何条件（长影线 + 小实体）

3. **误判原理**：
   - 刚开盘时，价格变化很小，但影线和实体比例可能恰好满足 Pinbar 条件
   - 例如：`wick_ratio = 0.67`（> 0.6），`body_ratio = 0.2`（< 0.3）
   - 这会被误判为 Pinbar，但实际上是开盘初期波动不足

#### 推荐修复

**方案 A: 使用 ATR 动态阈值（推荐）**

```python
def detect(self, kline: KlineData, atr_value: Optional[Decimal] = None) -> Optional[PatternResult]:
    cfg = self._config

    high = kline.high
    low = kline.low
    close = kline.close
    open_price = kline.open

    # Calculate candle range
    candle_range = high - low

    # 🔴 P0 修复：检查最小波幅（动态 ATR 阈值）
    min_required_range = Decimal("0.01") if atr_value is None else atr_value * Decimal("0.1")
    if candle_range < min_required_range:
        # 波幅太小，不检测形态（避免开盘初期误判）
        logger.debug(
            f"Skipping pinbar detection: candle_range={candle_range} < "
            f"min_required_range={min_required_range}"
        )
        return None

    if candle_range == Decimal(0):
        return None

    # ... (现有逻辑)
```

**方案 B: 固定阈值（简化版）**

```python
# 在 PinbarConfig 中添加参数
class PinbarConfig:
    def __init__(
        self,
        min_wick_ratio: Decimal = Decimal("0.6"),
        max_body_ratio: Decimal = Decimal("0.3"),
        body_position_tolerance: Decimal = Decimal("0.1"),
        min_candle_range: Decimal = Decimal("0.5"),  # 🔴 新增：最小波幅（USDT）
    ):
        self.min_wick_ratio = min_wick_ratio
        self.max_body_ratio = max_body_ratio
        self.body_position_tolerance = body_position_tolerance
        self.min_candle_range = min_candle_range  # 🔴 新增字段

# 在 detect() 方法中检查
candle_range = high - low
if candle_range < cfg.min_candle_range:
    logger.debug(f"Candle range too small: {candle_range} < {cfg.min_candle_range}")
    return None
```

---

## 三、问题影响评估

### 🔴 影响矩阵

| 问题 | 严重程度 | 影响范围 | 预期后果 | 发生概率 |
|------|---------|---------|---------|---------|
| **问题 1**: WebSocket 未正确过滤 | P0 | 高 | 未收盘 K 线触发信号 | 🔴 高（历史已发生） |
| **问题 2**: process_kline 缺少检查 | P0 | 高 | 问题 1 的下游放大 | 🔴 高（无防御层） |
| **问题 3**: 缺少最小波幅检查 | P0 | 中 | 开盘初期误判 Pinbar | 🟡 中（依赖市场条件） |

### 📊 影响场景

**场景 1: WebSocket 推送未收盘 K 线**
1. WebSocket 实时推送 K 线更新（每秒多次）
2. `_is_candle_closed()` 通过时间戳推断（可能不可靠）
3. 如果时间戳未改变，返回 `False`（正确过滤）
4. **但如果 `_parse_ohlcv()` 设置了错误的 `is_closed=True`**，下游无法防御

**场景 2: 首次订阅时的边界问题**
1. 首次订阅时，`_candle_timestamps[key]` 不存在
2. 直接设置为当前时间戳并返回 `False`
3. 第一根 K 线**永远不会触发回调**（即使已收盘）
4. 第二根 K 线时间戳改变时，第一根才被触发（**延迟触发**）

**场景 3: 开盘初期误判**
1. 新 K 线开盘，价格波动极小（如 `candle_range = 0.01 USDT`）
2. `_is_candle_closed()` 返回 `False`（时间戳未改变）
3. 但如果 WebSocket 推送了这根 K 线且 `is_closed` 错误
4. `process_kline()` 没有检查 `is_closed`
5. Pinbar 检测没有最小波幅检查，误判为 Pinbar

---

## 四、修复优先级

### 🔴 P0 级修复（立即修复）

| 修复项 | 预计工时 | 修复难度 | 风险 | 责任方 |
|--------|---------|---------|------|--------|
| 1. 修复 WebSocket `is_closed` 处理 | 1h | 低 | 低 | Backend Dev |
| 2. 添加 `process_kline()` 防御检查 | 0.5h | 低 | 无 | Backend Dev |
| 3. 添加 Pinbar 最小波幅检查 | 0.5h | 低 | 低 | Backend Dev |
| **总计** | **2h** | - | - | - |

---

## 五、修复方案详细设计

### 修复 1: WebSocket 正确处理 `is_closed`

**修改文件**: `src/infrastructure/exchange_gateway.py`

**修改点 1**: `_parse_ohlcv()` 方法增加 `is_closed` 参数

```python
def _parse_ohlcv(
    self,
    candle: List,
    symbol: str,
    timeframe: str,
    is_closed: bool = True,  # 🔴 新增参数
) -> Optional[KlineData]:
    """Parse OHLCV array from exchange into KlineData."""
    try:
        timestamp = int(candle[0])
        open_price = Decimal(str(candle[1]))
        high_price = Decimal(str(candle[2]))
        low_price = Decimal(str(candle[3]))
        close_price = Decimal(str(candle[4]))
        volume = Decimal(str(candle[5]))

        # ... (验证逻辑)

        return KlineData(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=timestamp,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            is_closed=is_closed,  # 🔴 使用参数值
        )

    except DataQualityWarning:
        raise
    except Exception as e:
        logger.warning(f"Failed to parse OHLCV candle: {e}")
        return None
```

**修改点 2**: WebSocket 订阅逻辑正确传递 `is_closed`

```python
async def _subscribe_single_ohlcv(
    self,
    symbol: str,
    timeframe: str,
    callback: Callable[[KlineData], Awaitable[None]],
    history_bars: int,
) -> None:
    reconnect_count = 0

    while self._ws_running:
        try:
            logger.info(f"Subscribing to {symbol} {timeframe}")

            while self._ws_running:
                # Watch OHLCV (this is a blocking call that receives updates)
                ohlcv = await self.ws_exchange.watch_ohlcv(symbol, timeframe)

                if not ohlcv:
                    continue

                # Get last candle (most recent)
                candle = ohlcv[-1]

                # 🔴 关键修复：从交易所数据中获取 is_closed 字段
                # CCXT watch_ohlcv 返回的 candle 格式：[ts, o, h, l, c, vol]
                # 但某些交易所返回扩展格式：[ts, o, h, l, c, vol, is_closed]
                # 需要检查交易所返回的数据是否包含 is_closed 字段

                # 方案 A: 如果交易所返回 is_closed 字段
                if len(candle) > 6:
                    is_closed = bool(candle[6])
                else:
                    # 方案 B: 使用时间戳推断（后备方案）
                    kline_temp = self._parse_ohlcv(candle, symbol, timeframe, is_closed=True)
                    if not kline_temp:
                        continue
                    is_closed = self._is_candle_closed(kline_temp, symbol, timeframe)

                kline = self._parse_ohlcv(candle, symbol, timeframe, is_closed=is_closed)

                if not kline:
                    continue

                # 🔴 仅触发已收盘 K 线的回调
                if kline.is_closed:
                    await callback(kline)

        except asyncio.CancelledError:
            # ... (异常处理)
```

---

### 修复 2: `process_kline()` 防御性检查

**修改文件**: `src/application/signal_pipeline.py`

```python
async def process_kline(self, kline: KlineData) -> None:
    """
    Process a single closed K-line.

    Args:
        kline: Closed K-line data

    Raises:
        ValueError: If kline.is_closed is False
    """
    # 🔴 P0 修复：验证 K 线是否已收盘
    if not kline.is_closed:
        logger.warning(
            f"[DEFENSE] Received unclosed K-line, ignoring: "
            f"{kline.symbol} {kline.timeframe} timestamp={kline.timestamp}"
        )
        return

    try:
        # Ensure async primitives and flush worker are running (lazy init)
        self._ensure_flush_worker()

        # ... (现有逻辑)
```

---

### 修复 3: Pinbar 最小波幅检查

**修改文件**: `src/domain/models.py` - 添加配置参数

```python
class PinbarParams(BaseModel):
    """Pinbar pattern detection parameters."""
    min_wick_ratio: Decimal = Field(
        default=Decimal("0.6"),
        ge=Decimal("0"),
        le=Decimal("1"),
        description="Minimum wick ratio (影线占全长的最低比例)"
    )
    max_body_ratio: Decimal = Field(
        default=Decimal("0.3"),
        ge=Decimal("0"),
        le=Decimal("1"),
        description="Maximum body ratio (实体占全长的最高比例)"
    )
    body_position_tolerance: Decimal = Field(
        default=Decimal("0.1"),
        ge=Decimal("0"),
        lt=Decimal("0.5"),
        description="Body position tolerance (实体位置容差)"
    )
    # 🔴 新增：最小波幅参数
    min_candle_range: Decimal = Field(
        default=Decimal("0.5"),
        ge=Decimal("0"),
        description="Minimum candle range for pattern detection (最小波幅，USDT)"
    )
```

**修改文件**: `src/domain/strategy_engine.py` - 实现检查逻辑

```python
def detect(self, kline: KlineData, atr_value: Optional[Decimal] = None) -> Optional[PatternResult]:
    cfg = self._config

    high = kline.high
    low = kline.low
    close = kline.close
    open_price = kline.open

    # Calculate candle range
    candle_range = high - low

    # 🔴 P0 修复：检查最小波幅（避免开盘初期误判）
    if candle_range < cfg.min_candle_range:
        logger.debug(
            f"[PINBAR_DEFENSE] Candle range too small: {candle_range} < "
            f"min_required={cfg.min_candle_range} - skipping detection"
        )
        return None

    if candle_range == Decimal(0):
        return None

    # ... (现有逻辑)
```

---

## 六、测试验证要求

### 单元测试

**测试文件**: `tests/unit/test_kline_closed_check.py`

```python
import pytest
from decimal import Decimal
from src.domain.models import KlineData
from src.application.signal_pipeline import SignalPipeline

@pytest.mark.asyncio
async def test_process_kline_rejects_unclosed_kline():
    """测试 process_kline 拒绝未收盘 K 线"""
    pipeline = SignalPipeline(...)

    # 构造未收盘 K 线
    unclosed_kline = KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        timestamp=1775526300000,
        open=Decimal("2098.00"),
        high=Decimal("2098.30"),
        low=Decimal("2097.90"),
        close=Decimal("2098.20"),
        volume=Decimal("100"),
        is_closed=False,  # 🔴 未收盘
    )

    # 期望：process_kline 应该拒绝并记录警告
    with pytest.raises(ValueError):
        await pipeline.process_kline(unclosed_kline)

@pytest.mark.asyncio
async def test_process_kline_accepts_closed_kline():
    """测试 process_kline 接受已收盘 K 线"""
    pipeline = SignalPipeline(...)

    # 构造已收盘 K 线
    closed_kline = KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        timestamp=1775526300000,
        open=Decimal("2098.00"),
        high=Decimal("2098.30"),
        low=Decimal("2097.90"),
        close=Decimal("2098.20"),
        volume=Decimal("100"),
        is_closed=True,  # ✅ 已收盘
    )

    # 期望：process_kline 应该正常处理
    await pipeline.process_kline(closed_kline)  # 不应抛出异常
```

**测试文件**: `tests/unit/test_pinbar_min_range.py`

```python
import pytest
from decimal import Decimal
from src.domain.models import KlineData
from src.domain.strategy_engine import PinbarStrategy, PinbarConfig

def test_pinbar_detection_rejects_small_range():
    """测试 Pinbar 检测拒绝波幅过小的 K 线"""
    config = PinbarConfig(
        min_wick_ratio=Decimal("0.6"),
        max_body_ratio=Decimal("0.3"),
        body_position_tolerance=Decimal("0.1"),
        min_candle_range=Decimal("0.5"),  # 最小波幅 0.5 USDT
    )
    strategy = PinbarStrategy(config)

    # 构造波幅过小的 K 线（刚开盘）
    small_range_kline = KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        timestamp=1775526300000,
        open=Decimal("2098.28"),
        high=Decimal("2098.30"),  # 仅 0.02 波幅
        low=Decimal("2098.28"),
        close=Decimal("2098.29"),
        volume=Decimal("10"),
        is_closed=True,
    )

    # 期望：detect 应该返回 None（波幅太小）
    result = strategy.detect(small_range_kline)
    assert result is None

def test_pinbar_detection_accepts_normal_range():
    """测试 Pinbar 检测接受正常波幅的 K 线"""
    config = PinbarConfig(min_candle_range=Decimal("0.5"))
    strategy = PinbarStrategy(config)

    # 构造正常波幅的 Pinbar
    normal_kline = KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        timestamp=1775526300000,
        open=Decimal("2098.00"),
        high=Decimal("2098.00"),
        low=Decimal("2095.00"),  # 长下影线
        close=Decimal("2097.80"),
        volume=Decimal("1000"),
        is_closed=True,
    )

    # 期望：detect 应该返回 PatternResult（检测到 Pinbar）
    result = strategy.detect(normal_kline)
    assert result is not None
    assert result.direction == Direction.LONG
```

---

## 七、验收标准

### 功能验收

- [ ] WebSocket 推送未收盘 K 线时，系统正确过滤（不触发信号）
- [ ] `process_kline()` 收到未收盘 K 线时，记录警告并返回
- [ ] Pinbar 检测拒绝波幅 < `min_candle_range` 的 K 线
- [ ] 所有单元测试通过

### 性能验收

- [ ] 修复不影响正常 K 线处理性能（延迟增加 < 5ms）
- [ ] 日志输出合理（避免过多警告刷屏）

### 回归测试

- [ ] 现有集成测试全部通过
- [ ] 回测系统无影响

---

## 八、风险评估

### 修复风险

| 风险项 | 风险等级 | 缓解措施 |
|--------|---------|---------|
| 修改 `_parse_ohlcv()` 影响现有代码 | 低 | 保留默认参数 `is_closed=True`（向后兼容） |
| 添加 `min_candle_range` 影响现有策略 | 中 | 提供合理的默认值（0.5 USDT）+ 可配置 |
| WebSocket `is_closed` 字段缺失 | 中 | 提供后备方案（时间戳推断） |

### 不修复风险

| 风险项 | 风险等级 | 后果 |
|--------|---------|------|
| 信号误触发 | 🔴 高 | 错误交易信号 → 资金损失 |
| 形态误判 | 🔴 高 | 策略信誉受损 |
| 用户信任度下降 | 🔴 高 | 系统不可靠 |

---

## 九、结论与建议

### 🔴 结论

**当前系统存在 3 个 P0 级严重缺陷**：

1. ✅ **WebSocket 未正确处理 `is_closed` 字段**
2. ✅ **`process_kline()` 缺少防御性检查**
3. ✅ **Pinbar 检测缺少最小波幅检查**

这 3 个问题相互叠加，导致：
- 未收盘 K 线可能触发信号
- 刚开盘的 K 线被误判为 Pinbar
- 系统信号质量严重下降

### 🎯 建议

**立即启动修复项目**（预计 2 小时）：

1. Backend Dev 修复 WebSocket `is_closed` 处理（1h）
2. Backend Dev 添加防御性检查（0.5h）
3. Backend Dev 添加最小波幅检查（0.5h）
4. QA Tester 验证修复（1h）

**总工时**: 3 小时（1 小时修复 + 1 小时测试 + 1 小时缓冲）

---

**审查人签字**: Architect
**审查日期**: 2026-04-07
**审查结论**: 🔴 **P0 级严重缺陷，立即修复**