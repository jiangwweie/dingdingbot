# S3-1 多周期数据对齐优化 - 设计文档

**创建日期**: 2026-03-27
**作者**: 盯盘狗开发团队
**状态**: 待实现
**优先级**: P1（重要但不紧急）

---

## 1. 背景与问题定义

### 1.1 核心问题

当前系统的 MTF（Multi-Timeframe）过滤器在实盘管道中**实际未生效**：

```python
# src/application/signal_pipeline.py:348-351
return self._runner.run_all(
    kline=kline,
    higher_tf_trends={},  # ❌ 空字典，MTF 过滤器无法进行趋势确认
    kline_history=kline_history,
)
```

### 1.2 影响范围

| 场景 | 当前行为 | 期望行为 |
|------|---------|---------|
| 15m Pinbar 多头信号 | MTF 过滤器跳过检查（无 1h 趋势数据） | 检查 1h EMA 趋势，确认是否为多头 |
| 1h 吞没空头信号 | MTF 过滤器跳过检查（无 4h 趋势数据） | 检查 4h EMA 趋势，确认是否为空头 |
| 回测环境 | ✅ 正确计算 MTF 趋势 | - |
| 实盘环境 | ❌ MTF 数据为空 | 与回测行为一致 |

### 1.3 根本原因

1. **实盘管道未构建 MTF 数据**：`signal_pipeline.py` 直接传入空字典
2. **回测/实盘逻辑不一致**：回测有 `_get_closest_higher_tf_trends()`，实盘没有
3. **MTF 配置不可自定义**：`MTF_MAPPING` 硬编码在多个文件中

---

## 2. 设计目标

### 2.1 功能目标

- [ ] 实盘管道正确计算并传入 `higher_tf_trends`
- [ ] 使用**已闭合**的高周期 K 线计算趋势（避免使用运行中 K 线）
- [ ] 支持 `mtf_ema_period` 配置（默认 60）
- [ ] 支持 `mtf_mapping` 自定义映射关系

### 2.2 非功能目标

- [ ] 回测/实盘 MTF 逻辑保持一致
- [ ] 新增单元测试覆盖率 > 90%
- [ ] 不影响现有策略执行性能（延迟增加 < 50ms）

---

## 3. 架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     用户配置 (user.yaml)                        │
│  mtf_ema_period: 60                                             │
│  mtf_mapping:                                                   │
│    "15m": "1h"                                                  │
│    "1h": "4h"                                                   │
│    "4h": "1d"                                                   │
│    "1d": "1w"                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              新增：src/domain/timeframe_utils.py                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ get_higher_timeframe()                                     │  │
│  │ get_last_closed_kline_index()                              │  │
│  │ calculate_ema_trend()                                      │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│         修改：src/application/signal_pipeline.py                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ _get_closest_higher_tf_trends(kline: KlineData)           │  │
│  │   - 从 _kline_history 中获取各周期 K 线                       │  │
│  │   - 调用 timeframe_utils 计算最后闭合 K 线的 EMA 趋势         │  │
│  │   - 返回 Dict[timeframe, TrendDirection]                  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 数据流

```
K-line WebSocket 推送
    ↓
signal_pipeline._on_kline_update()
    ↓
_store_kline(kline)  # 存入 _kline_history
    ↓
_run_strategy(kline)
    ↓
_get_closest_higher_tf_trends(kline)  # ← 新增
    ↓
_runner.run_all(kline, higher_tf_trends={...})  # ← 传入计算出的趋势
    ↓
MTFFilterDynamic.check() 使用 higher_tf_trends 进行趋势确认
```

---

## 4. 详细设计

### 4.1 新增文件：`src/domain/timeframe_utils.py`

```python
"""
Timeframe utilities for MTF (Multi-Timeframe) alignment.

Core responsibility: Ensure MTF filters use correctly aligned,
closed kline data for trend calculation.
"""
from typing import Dict, Optional, List
from decimal import Decimal

from .models import KlineData, TrendDirection


# MTF 映射默认值（可被用户配置覆盖）
DEFAULT_MTF_MAPPING = {
    "15m": "1h",
    "1h": "4h",
    "4h": "1d",
    "1d": "1w",
}

# 时间周期毫秒数映射
TIMEFRAME_TO_MS = {
    "1m": 60 * 1000,
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "30m": 30 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
    "1w": 7 * 24 * 60 * 60 * 1000,
}


def get_higher_timeframe(
    current_timeframe: str,
    mtf_mapping: Optional[Dict[str, str]] = None
) -> Optional[str]:
    """
    Get the higher timeframe for MTF analysis.

    Args:
        current_timeframe: Current kline timeframe (e.g., "15m")
        mtf_mapping: Custom MTF mapping (uses DEFAULT_MTF_MAPPING if None)

    Returns:
        Higher timeframe string, or None if no higher timeframe exists
    """
    mapping = mtf_mapping or DEFAULT_MTF_MAPPING
    return mapping.get(current_timeframe)


def get_last_closed_kline_index(
    klines: List[KlineData],
    current_timestamp: int,
    timeframe: str
) -> int:
    """
    Find the index of the last closed kline.

    A kline is considered "closed" if:
    1. Its timestamp is strictly less than current_timestamp
    2. It aligns with the timeframe period boundary

    Args:
        klines: List of klines (sorted by timestamp ascending)
        current_timestamp: Current kline's timestamp (milliseconds)
        timeframe: The timeframe of the klines being checked

    Returns:
        Index of last closed kline, or -1 if none found

    Example:
        current_timestamp = 10:15 (15m kline closes)
        timeframe = "1h"
        Returns index of 10:00 kline (last closed 1h kline)
    """
    period_ms = TIMEFRAME_TO_MS.get(timeframe)
    if period_ms is None:
        return -1

    # Calculate the start of current period
    current_period_start = (current_timestamp // period_ms) * period_ms

    # Last closed kline is the one before current period starts
    # We need to find the kline with timestamp < current_period_start
    # and closest to it

    last_closed_index = -1
    for i, kline in enumerate(klines):
        if kline.timestamp < current_period_start:
            last_closed_index = i
        else:
            break  # klines are sorted, no need to continue

    return last_closed_index


def parse_timeframe_to_ms(timeframe: str) -> int:
    """
    Parse timeframe string to milliseconds.

    Args:
        timeframe: Timeframe string (e.g., "15m", "1h", "4h")

    Returns:
        Milliseconds as integer

    Raises:
        ValueError: If timeframe format is invalid
    """
    if timeframe in TIMEFRAME_TO_MS:
        return TIMEFRAME_TO_MS[timeframe]

    # Try to parse custom timeframe (e.g., "2h", "30m")
    if timeframe.endswith('m'):
        minutes = int(timeframe[:-1])
        return minutes * 60 * 1000
    elif timeframe.endswith('h'):
        hours = int(timeframe[:-1])
        return hours * 60 * 60 * 1000
    elif timeframe.endswith('d'):
        days = int(timeframe[:-1])
        return days * 24 * 60 * 60 * 1000
    elif timeframe.endswith('w'):
        weeks = int(timeframe[:-1])
        return weeks * 7 * 24 * 60 * 60 * 1000

    raise ValueError(f"Invalid timeframe format: {timeframe}")
```

---

### 4.2 修改文件：`src/application/signal_pipeline.py`

#### 4.2.1 新增 MTF EMA 指标缓存

```python
class SignalPipeline:
    def __init__(
        self,
        config_manager: ConfigManager,
        risk_config: RiskConfig,
        notification_service: NotificationService,
        signal_repository: Optional[SignalRepository] = None,
        cooldown_seconds: int = 300,
    ):
        # ... existing init ...

        # MTF EMA indicators (one per symbol:timeframe combination)
        self._mtf_ema_indicators: Dict[str, EmaIndicator] = {}
        self._mtf_ema_period = config_manager.user_config.mtf_ema_period or 60
```

#### 4.2.2 新增方法：`_get_closest_higher_tf_trends()`

```python
def _get_closest_higher_tf_trends(self, kline: KlineData) -> Dict[str, TrendDirection]:
    """
    Calculate higher timeframe trends for MTF filtering.

    Uses the last CLOSED kline of each higher timeframe to ensure
    data consistency and avoid using incomplete running klines.

    Args:
        kline: Current kline that triggered a signal

    Returns:
        Dict mapping timeframe to TrendDirection
        e.g., {"1h": TrendDirection.BULLISH, "4h": TrendDirection.BEARISH}
    """
    from src.domain.timeframe_utils import (
        get_higher_timeframe,
        get_last_closed_kline_index,
    )

    result: Dict[str, TrendDirection] = {}
    current_tf = kline.timeframe

    # Get higher timeframe from config
    higher_tf = get_higher_timeframe(
        current_tf,
        self._config_manager.user_config.mtf_mapping
    )

    if higher_tf is None:
        return result  # No higher timeframe (e.g., 1w)

    # Fetch higher timeframe klines from history
    key = f"{kline.symbol}:{higher_tf}"
    higher_tf_klines = self._kline_history.get(key, [])

    if len(higher_tf_klines) == 0:
        return result  # No data available

    # Find last closed kline index
    last_closed_idx = get_last_closed_kline_index(
        higher_tf_klines,
        kline.timestamp,
        higher_tf
    )

    if last_closed_idx < 0:
        return result  # No closed kline found

    last_closed_kline = higher_tf_klines[last_closed_idx]

    # Get or create EMA indicator for this symbol:timeframe
    ema_key = f"{kline.symbol}:{higher_tf}"
    if ema_key not in self._mtf_ema_indicators:
        self._mtf_ema_indicators[ema_key] = EmaIndicator(period=self._mtf_ema_period)

    ema = self._mtf_ema_indicators[ema_key]

    # Update EMA with last closed kline's close price
    ema.update(last_closed_kline.close)

    if not ema.initialized:
        return result  # EMA needs more data

    # Determine trend direction from EMA slope
    if ema.value > ema.prev_value:
        result[higher_tf] = TrendDirection.BULLISH
    else:
        result[higher_tf] = TrendDirection.BEARISH

    return result
```

#### 4.2.3 修改 `_run_strategy()` 方法

```python
def _run_strategy(self, kline: KlineData) -> List[SignalAttempt]:
    """
    Run strategy engine on K-line.

    Args:
        kline: K-line data

    Returns:
        List[SignalAttempt] with full filtering chain results
    """
    # Get K-line history for strategies that need it (like Engulfing)
    key = f"{kline.symbol}:{kline.timeframe}"
    kline_history = self._kline_history.get(key, [])[:-1]  # Exclude current kline

    # Update runner state
    self._runner.update_state(kline)

    # Calculate higher timeframe trends for MTF filtering
    higher_tf_trends = self._get_closest_higher_tf_trends(kline)

    # Log MTF status for debugging
    if higher_tf_trends:
        logger.debug(
            f"MTF trends for {kline.symbol}:{kline.timeframe}: "
            f"{higher_tf_trends}"
        )

    # Run all strategies with MTF trends
    return self._runner.run_all(
        kline=kline,
        higher_tf_trends=higher_tf_trends,  # ← Changed from {} to calculated trends
        kline_history=kline_history,
    )
```

---

### 4.3 修改文件：`src/application/config_manager.py`

#### 4.3.1 新增配置字段

```python
class UserConfig(BaseModel):
    """User-specific configuration."""

    # ... existing fields ...

    mtf_ema_period: int = Field(
        default=60,
        description="EMA period for MTF trend calculation",
        ge=5,
        le=200
    )

    mtf_mapping: Dict[str, str] = Field(
        default_factory=lambda: {
            "15m": "1h",
            "1h": "4h",
            "4h": "1d",
            "1d": "1w",
        },
        description="MTF timeframe mapping: lower -> higher"
    )
```

---

### 4.4 配置文件：`config/core.yaml`

```yaml
# ... existing config ...

# MTF (Multi-Timeframe) Configuration
mtf:
  ema_period: 60              # EMA period for trend calculation
  mapping:                    # Lower timeframe -> Higher timeframe
    "15m": "1h"
    "1h": "4h"
    "4h": "1d"
    "1d": "1w"
```

---

## 5. 测试策略

### 5.1 单元测试

#### `tests/unit/test_timeframe_utils.py`

```python
class TestGetHigherTimeframe:
    def test_default_mapping_15m_to_1h(self):
        assert get_higher_timeframe("15m") == "1h"

    def test_custom_mapping(self):
        custom = {"15m": "4h"}
        assert get_higher_timeframe("15m", custom) == "4h"

    def test_no_higher_timeframe(self):
        # 1w has no higher timeframe in default mapping
        assert get_higher_timeframe("1w") is None


class TestGetLastClosedKlineIndex:
    def test_15m_signal_uses_1h_closed(self):
        # 1h klines: [09:00, 10:00, 11:00]
        # Current 15m kline: 10:15
        # Expected: index 1 (10:00 kline)
        klines = [
            KlineData(timestamp=hour_to_ms(9), close=Decimal("50000")),
            KlineData(timestamp=hour_to_ms(10), close=Decimal("51000")),
            KlineData(timestamp=hour_to_ms(11), close=Decimal("52000")),
        ]
        idx = get_last_closed_kline_index(klines, minute_to_ms(10, 15), "1h")
        assert idx == 1

    def test_boundary_exactly_on_period(self):
        # Current kline exactly on 1h boundary: 11:00
        # Expected: index 1 (10:00 kline, not 11:00)
        klines = [
            KlineData(timestamp=hour_to_ms(9), close=Decimal("50000")),
            KlineData(timestamp=hour_to_ms(10), close=Decimal("51000")),
            KlineData(timestamp=hour_to_ms(11), close=Decimal("52000")),
        ]
        idx = get_last_closed_kline_index(klines, hour_to_ms(11), "1h")
        assert idx == 1

    def test_no_closed_klines(self):
        # All klines are in the future
        klines = [
            KlineData(timestamp=hour_to_ms(12), close=Decimal("52000")),
        ]
        idx = get_last_closed_kline_index(klines, hour_to_ms(11), "1h")
        assert idx == -1


class TestParseTimeframeToMs:
    def test_standard_timeframes(self):
        assert parse_timeframe_to_ms("15m") == 15 * 60 * 1000
        assert parse_timeframe_to_ms("1h") == 60 * 60 * 1000
        assert parse_timeframe_to_ms("4h") == 4 * 60 * 60 * 1000

    def test_custom_timeframes(self):
        assert parse_timeframe_to_ms("2h") == 2 * 60 * 60 * 1000
        assert parse_timeframe_to_ms("30m") == 30 * 60 * 1000

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_timeframe_to_ms("invalid")
```

#### `tests/unit/test_signal_pipeline.py` (新增测试)

```python
class TestMtfAlignment:
    def test_pipeline_calculates_higher_tf_trends(self):
        """Verify pipeline correctly calculates MTF trends."""
        # Setup: Create pipeline with 15m + 1h kline history
        pipeline = create_test_pipeline()

        # Add 1h klines to history
        pipeline._kline_history["BTC/USDT:USDT:1h"] = [
            KlineData(timestamp=hour_to_ms(9), close=Decimal("50000")),
            KlineData(timestamp=hour_to_ms(10), close=Decimal("51000")),
            KlineData(timestamp=hour_to_ms(11), close=Decimal("52000")),
        ]

        # Process 15m kline at 10:15
        kline_15m = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=minute_to_ms(10, 15),
            close=Decimal("50500"),
        )

        trends = pipeline._get_closest_higher_tf_trends(kline_15m)

        # Should use 10:00 kline (not 11:00)
        assert "1h" in trends
        # Trend depends on EMA calculation from 10:00 kline

    def test_mtf_uses_config_ema_period(self):
        """Verify MTF uses configured EMA period."""
        config_manager = create_config_manager(mtf_ema_period=50)
        pipeline = SignalPipeline(config_manager=config_manager, ...)

        # EMA indicator should be initialized with period=50
        kline = create_test_kline()
        trends = pipeline._get_closest_higher_tf_trends(kline)

        ema_key = "BTC/USDT:USDT:1h"
        assert pipeline._mtf_ema_indicators[ema_key]._period == 50
```

### 5.2 集成测试

```python
# tests/integration/test_mtf_e2e.py
class TestMtfEndToEnd:
    async def test_mtf_filter_blocks_conflicting_signals(self):
        """
        Verify MTF filter blocks signals that conflict with higher TF trend.

        Scenario:
        - 1h trend is BULLISH (EMA going up)
        - 15m kline produces SHORT signal
        - MTF filter should REJECT this signal
        """
        # Setup exchange gateway with historical data
        gateway = await create_test_gateway()

        # Configure MTF-enabled strategy
        config = create_mtf_strategy_config()

        # Process klines
        pipeline = create_pipeline(config)

        # Simulate 15m short signal when 1h is bullish
        kline_15m = create_short_signal_kline()
        await pipeline.process_kline(kline_15m)

        # Verify signal was filtered out
        signals = pipeline.get_pending_signals()
        assert len(signals) == 0  # MTF rejected the signal
```

### 5.3 回测一致性测试

```python
# tests/backtest/test_alignment_consistency.py
def test_backtest_and_live_use_same_alignment():
    """
    Verify backtest and live modes use identical MTF alignment logic.
    """
    # Run backtest with MTF strategy
    backtest_results = run_backtest(mtf_enabled=True)

    # Run live simulation with same data
    live_results = run_live_simulation(mtf_enabled=True)

    # Signals should match (within acceptable tolerance)
    assert backtest_results.signals == live_results.signals
```

---

## 6. 风险与缓解

### 6.1 技术风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 时间戳边界条件遗漏 | 中 | 中 | 编写边界测试用例（整点、跨天、跨周） |
| 时区/夏令时问题 | 低 | 高 | 统一使用 UTC 毫秒时间戳 |
| 回测历史数据不精确 | 中 | 中 | 数据加载阶段做对齐校验 |

### 6.2 业务风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| MTF 过滤后信号数量减少 | 用户可能觉得信号变少 | 在通知中添加 MTF 状态标签，用户可理解过滤原因 |
| 配置迁移成本 | 老用户配置缺失 | 提供默认值，兼容旧配置格式 |

---

## 7. 验收标准

### 功能验收

- [ ] 实盘管道正确计算 `higher_tf_trends`（非空字典）
- [ ] MTF 过滤器使用已闭合 K 线数据
- [ ] 支持 `mtf_ema_period` 配置（默认 60）
- [ ] 支持 `mtf_mapping` 自定义映射

### 测试验收

- [ ] 单元测试覆盖率 > 90%
- [ ] 所有边界条件有测试覆盖
- [ ] 集成测试验证端到端流程

### 性能验收

- [ ] 单次 K 线处理延迟增加 < 50ms
- [ ] 内存占用增加 < 10MB

---

## 8. 实现顺序

```
1. 创建 timeframe_utils.py 及单元测试
2. 修改 config_manager.py 添加 MTF 配置字段
3. 修改 signal_pipeline.py 实现 _get_closest_higher_tf_trends()
4. 修改 core.yaml 添加默认配置
5. 编写集成测试
6. 性能测试验证
```

---

## 9. 相关文件索引

- `src/domain/timeframe_utils.py` - 新增
- `src/application/signal_pipeline.py` - 修改
- `src/application/config_manager.py` - 修改
- `config/core.yaml` - 修改
- `tests/unit/test_timeframe_utils.py` - 新增
- `tests/unit/test_signal_pipeline.py` - 修改

---

*本文档由 brainstorming 技能生成，待用户审查后进入实现阶段*
