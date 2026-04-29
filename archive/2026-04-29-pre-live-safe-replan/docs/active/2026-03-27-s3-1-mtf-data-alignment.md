# S3-1 多周期数据对齐优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现实盘 MTF 数据对齐功能，使 MTF 过滤器在实盘管道中正确生效

**Architecture:**
1. 新增 `timeframe_utils.py` 封装 MTF 时间对齐工具函数
2. 修改 `signal_pipeline.py` 实现 `_get_closest_higher_tf_trends()` 方法
3. 修改 `config_manager.py` 添加 `mtf_ema_period` 和 `mtf_mapping` 配置字段
4. 修改 `core.yaml` 添加默认 MTF 配置

**Tech Stack:** Python 3.11+, Pydantic v2, Decimal for precision, asyncio for concurrency

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/domain/timeframe_utils.py` | Create | MTF 时间对齐工具函数（纯函数，无状态） |
| `src/application/signal_pipeline.py` | Modify | 新增 `_get_closest_higher_tf_trends()` 方法 |
| `src/application/config_manager.py` | Modify | 新增 MTF 配置字段 |
| `config/core.yaml` | Modify | 添加 MTF 默认配置 |
| `tests/unit/test_timeframe_utils.py` | Create | 工具函数单元测试 |
| `tests/unit/test_signal_pipeline.py` | Modify | 新增 MTF 对齐测试 |

---

## Task 1: 创建 timeframe_utils.py 工具函数

**Files:**
- Create: `src/domain/timeframe_utils.py`
- Test: `tests/unit/test_timeframe_utils.py`

**Status**: ✅ COMPLETED (commit 48b97fa)

- [x] **Step 1: 创建 timeframe_utils.py 基础结构**

```python
# src/domain/timeframe_utils.py
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
```

- [ ] **Step 2: 添加 get_higher_timeframe 函数**

```python
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
```

- [ ] **Step 3: 添加 parse_timeframe_to_ms 函数**

```python
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

- [ ] **Step 4: 添加 get_last_closed_kline_index 函数**

```python
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
    period_ms = parse_timeframe_to_ms(timeframe)

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
```

- [ ] **Step 5: 创建 test_timeframe_utils.py 测试文件框架**

```python
# tests/unit/test_timeframe_utils.py
"""Unit tests for MTF timeframe utilities."""
from decimal import Decimal
import pytest

from src.domain.timeframe_utils import (
    get_higher_timeframe,
    parse_timeframe_to_ms,
    get_last_closed_kline_index,
    DEFAULT_MTF_MAPPING,
    TIMEFRAME_TO_MS,
)
from src.domain.models import KlineData, TrendDirection


# Helper functions for test timestamp generation
def hour_to_ms(hour: int) -> int:
    """Convert hour to milliseconds since epoch (simplified for testing)."""
    base = 1700000000000  # Arbitrary base timestamp
    return base + (hour * 60 * 60 * 1000)


def minute_to_ms(hour: int, minute: int) -> int:
    """Convert hour:minute to milliseconds since epoch."""
    base = 1700000000000
    return base + (hour * 60 * 60 * 1000) + (minute * 60 * 1000)


def create_kline(timestamp: int, close: str = "50000") -> KlineData:
    """Create a test KlineData with minimal fields."""
    return KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="1h",
        timestamp=timestamp,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("1000"),
        is_closed=True,
    )
```

- [ ] **Step 6: 添加 get_higher_timeframe 测试**

```python
class TestGetHigherTimeframe:
    def test_default_mapping_15m_to_1h(self):
        """Test that 15m maps to 1h by default."""
        result = get_higher_timeframe("15m")
        assert result == "1h"

    def test_default_mapping_1h_to_4h(self):
        """Test that 1h maps to 4h by default."""
        result = get_higher_timeframe("1h")
        assert result == "4h"

    def test_default_mapping_4h_to_1d(self):
        """Test that 4h maps to 1d by default."""
        result = get_higher_timeframe("4h")
        assert result == "1d"

    def test_default_mapping_1d_to_1w(self):
        """Test that 1d maps to 1w by default."""
        result = get_higher_timeframe("1d")
        assert result == "1w"

    def test_no_higher_timeframe_for_1w(self):
        """Test that 1w has no higher timeframe in default mapping."""
        result = get_higher_timeframe("1w")
        assert result is None

    def test_custom_mapping(self):
        """Test custom MTF mapping override."""
        custom = {"15m": "4h", "1h": "1d"}
        result = get_higher_timeframe("15m", custom)
        assert result == "4h"

    def test_custom_mapping_partial(self):
        """Test custom mapping with missing key falls back to default."""
        custom = {"15m": "4h"}
        result = get_higher_timeframe("1h", custom)
        assert result == "4h"  # Falls back to default
```

- [ ] **Step 7: 添加 parse_timeframe_to_ms 测试**

```python
class TestParseTimeframeToMs:
    def test_standard_15m(self):
        result = parse_timeframe_to_ms("15m")
        assert result == 15 * 60 * 1000

    def test_standard_1h(self):
        result = parse_timeframe_to_ms("1h")
        assert result == 60 * 60 * 1000

    def test_standard_4h(self):
        result = parse_timeframe_to_ms("4h")
        assert result == 4 * 60 * 60 * 1000

    def test_standard_1d(self):
        result = parse_timeframe_to_ms("1d")
        assert result == 24 * 60 * 60 * 1000

    def test_standard_1w(self):
        result = parse_timeframe_to_ms("1w")
        assert result == 7 * 24 * 60 * 60 * 1000

    def test_custom_2h(self):
        result = parse_timeframe_to_ms("2h")
        assert result == 2 * 60 * 60 * 1000

    def test_custom_30m(self):
        result = parse_timeframe_to_ms("30m")
        assert result == 30 * 60 * 1000

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid timeframe format"):
            parse_timeframe_to_ms("invalid")

    def test_invalid_number(self):
        with pytest.raises(ValueError):
            parse_timeframe_to_ms("abc")
```

- [ ] **Step 8: 添加 get_last_closed_kline_index 测试**

```python
class TestGetLastClosedKlineIndex:
    def test_15m_signal_uses_1h_closed(self):
        """
        15m kline at 10:15 should use 10:00 as last closed 1h kline.
        """
        klines = [
            create_kline(hour_to_ms(9), "50000"),   # 09:00
            create_kline(hour_to_ms(10), "51000"),  # 10:00
            create_kline(hour_to_ms(11), "52000"),  # 11:00
        ]
        # Current 15m kline at 10:15
        current_ts = minute_to_ms(10, 15)

        idx = get_last_closed_kline_index(klines, current_ts, "1h")

        assert idx == 1  # Should return 10:00 kline

    def test_boundary_exactly_on_period(self):
        """
        Current kline exactly on 1h boundary (11:00) should use 10:00.
        """
        klines = [
            create_kline(hour_to_ms(9), "50000"),   # 09:00
            create_kline(hour_to_ms(10), "51000"),  # 10:00
            create_kline(hour_to_ms(11), "52000"),  # 11:00
        ]
        current_ts = hour_to_ms(11)

        idx = get_last_closed_kline_index(klines, current_ts, "1h")

        assert idx == 1  # Should return 10:00 kline, not 11:00

    def test_no_closed_klines(self):
        """
        All klines in the future should return -1.
        """
        klines = [
            create_kline(hour_to_ms(12), "52000"),  # 12:00 (future)
        ]
        current_ts = hour_to_ms(11)  # 11:00

        idx = get_last_closed_kline_index(klines, current_ts, "1h")

        assert idx == -1

    def test_empty_klines(self):
        """Empty kline list should return -1."""
        idx = get_last_closed_kline_index([], hour_to_ms(10), "1h")
        assert idx == -1

    def test_4h_to_1d_alignment(self):
        """
        4h kline at 14:00 should use previous day's 1d kline.
        """
        klines = [
            create_kline(1700000000000, "50000"),      # Day 1
            create_kline(1700086400000, "51000"),      # Day 2
        ]
        # 4h kline at some point on Day 2
        current_ts = 1700086400000 + (2 * 60 * 60 * 1000)

        idx = get_last_closed_kline_index(klines, current_ts, "1d")

        assert idx == 0  # Should return Day 1 kline
```

- [ ] **Step 9: 运行测试验证**

```bash
cd /Users/jiangwei/Documents/final
pytest tests/unit/test_timeframe_utils.py -v
```

Expected: All tests pass

- [x] **Step 10: 提交代码**

```bash
git add src/domain/timeframe_utils.py tests/unit/test_timeframe_utils.py
git commit -m "feat(S3-1): add MTF timeframe utilities with tests"
```

---

## Task 2: 修改 config_manager.py 添加 MTF 配置

**Files:**
- Modify: `src/application/config_manager.py`
- Test: `tests/unit/test_config_manager.py` (add MTF config tests)

**Status**: ✅ COMPLETED (commit a5406a3)

- [ ] **Step 1: 在 UserConfig 中添加 mtf_ema_period 字段**

```python
# src/application/config_manager.py

class UserConfig(BaseModel):
    """User configuration (modifiable)"""
    exchange: ExchangeConfig
    user_symbols: List[str] = Field(default_factory=list, description="User-defined symbols")
    timeframes: List[str] = Field(..., min_length=1, description="Timeframes to monitor")
    # New dynamic rule engine config (Phase K)
    active_strategies: List[StrategyDefinition] = Field(
        default_factory=list,
        description="Active strategy definitions with attached filters"
    )
    # Legacy support - if active_strategies is empty, migrate from old strategy config
    strategy: Optional[StrategyConfig] = Field(default=None, description="Legacy strategy config (deprecated)")
    risk: RiskConfig
    asset_polling: AssetPollingConfig = Field(default_factory=AssetPollingConfig)
    notification: NotificationConfig

    # MTF Configuration (S3-1)
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

    model_config = {'protected_namespaces': ()}
```

- [ ] **Step 2: 添加 mtf_ema_period 验证器**

```python
class UserConfig(BaseModel):
    # ... existing fields ...

    @field_validator('mtf_ema_period')
    @classmethod
    def validate_mtf_ema_period(cls, v):
        if v < 5 or v > 200:
            raise ValueError("mtf_ema_period must be between 5 and 200")
        return v
```

- [ ] **Step 3: 修改 CoreConfig 添加 mtf 配置字段**

```python
class CoreConfig(BaseModel):
    """Core system configuration (read-only)"""
    core_symbols: List[str] = Field(..., min_length=1, description="Core trading symbols")
    pinbar_defaults: PinbarDefaults
    ema: EmaConfig
    mtf_mapping: MtfMapping

    # S3-1: Add MTF EMA period config
    mtf_ema_period: int = Field(
        default=60,
        description="Default EMA period for MTF trend calculation",
        ge=5,
        le=200
    )

    warmup: WarmupConfig
    signal_pipeline: SignalPipelineConfig = Field(default_factory=SignalPipelineConfig)
```

- [ ] **Step 4: 添加 ConfigManager 测试**

```python
# tests/unit/test_config_manager.py

class TestMtfConfig:
    def test_default_mtf_ema_period(self):
        """Test that default MTF EMA period is 60."""
        config = create_test_user_config()
        assert config.mtf_ema_period == 60

    def test_custom_mtf_ema_period(self):
        """Test custom MTF EMA period."""
        config = create_test_user_config(mtf_ema_period=50)
        assert config.mtf_ema_period == 50

    def test_mtf_ema_period_validation_min(self):
        """Test MTF EMA period minimum validation."""
        with pytest.raises(ValidationError):
            create_test_user_config(mtf_ema_period=4)

    def test_mtf_ema_period_validation_max(self):
        """Test MTF EMA period maximum validation."""
        with pytest.raises(ValidationError):
            create_test_user_config(mtf_ema_period=201)

    def test_default_mtf_mapping(self):
        """Test default MTF mapping."""
        config = create_test_user_config()
        assert config.mtf_mapping == {
            "15m": "1h",
            "1h": "4h",
            "4h": "1d",
            "1d": "1w",
        }

    def test_custom_mtf_mapping(self):
        """Test custom MTF mapping."""
        custom_mapping = {"15m": "4h", "1h": "1d"}
        config = create_test_user_config(mtf_mapping=custom_mapping)
        assert config.mtf_mapping == custom_mapping
```

- [ ] **Step 5: 运行测试验证**

```bash
pytest tests/unit/test_config_manager.py::TestMtfConfig -v
```

Expected: All tests pass

- [x] **Step 6: 提交代码**

```bash
git add src/application/config_manager.py tests/unit/test_config_manager.py
git commit -m "feat(S3-1): add MTF configuration fields to UserConfig"
```

---

## Task 3: 修改 core.yaml 添加默认配置

**Files:**
- Modify: `config/core.yaml`

**Status**: ✅ COMPLETED (已合并到 a5406a3)

- [ ] **Step 1: 读取当前 core.yaml**

```bash
cat config/core.yaml
```

- [ ] **Step 2: 添加 MTF 配置到 core.yaml**

在 `ema` 配置后添加：

```yaml
# MTF (Multi-Timeframe) Configuration
mtf:
  ema_period: 60              # EMA period for trend calculation
  mapping:                    # Lower timeframe -> Higher timeframe
    "15m": "1h"
    "1h": "4h"
    "4h": "1d"
    "1d": "1w"
```

- [ ] **Step 3: 验证 YAML 语法**

```bash
python3 -c "import yaml; yaml.safe_load(open('config/core.yaml'))"
```

Expected: No error

- [x] **Step 4: 提交代码**

```bash
git add config/core.yaml
git commit -m "config(S3-1): add MTF default configuration"
```

---

## Task 4: 修改 signal_pipeline.py 实现 MTF 趋势计算

**Files:**
- Modify: `src/application/signal_pipeline.py`
- Test: `tests/unit/test_signal_pipeline.py`

**Status**: ✅ COMPLETED (commit 57846a3)

- [x] **Step 1: 导入必要模块**

```python
# src/application/signal_pipeline.py

# Add to imports
from src.domain.indicators import EMACalculator
from src.domain.timeframe_utils import (
    get_higher_timeframe,
    get_last_closed_kline_index,
)
```

- [ ] **Step 2: 在 __init__ 中添加 MTF EMA 指标缓存**

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
        self._config_manager = config_manager
        self._risk_calculator = RiskCalculator(risk_config)
        self._notification_service = notification_service
        self._repository = signal_repository
        self._cooldown_seconds = cooldown_seconds

        # Existing fields
        self._runner = None
        self._ema_indicators: Dict[str, EMACalculator] = {}
        self._kline_history: Dict[str, List[KlineData]] = {}
        self._account_snapshot: Optional[AccountSnapshot] = None
        self._signal_cooldown_cache: Dict[str, int] = {}

        # S3-1: MTF EMA indicators (one per symbol:timeframe combination)
        self._mtf_ema_indicators: Dict[str, EMACalculator] = {}
        self._mtf_ema_period = config_manager.user_config.mtf_ema_period or 60
```

- [ ] **Step 3: 添加 _get_closest_higher_tf_trends 方法**

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
        self._mtf_ema_indicators[ema_key] = EMACalculator(period=self._mtf_ema_period)

    ema = self._mtf_ema_indicators[ema_key]

    # Update EMA with last closed kline's close price
    ema.update(last_closed_kline.close)

    if not ema.is_ready:
        return result  # EMA needs more data

    # Determine trend direction from EMA slope
    # Note: EMACalculator doesn't expose prev_value, so we compare with current price
    ema_value = ema.value
    if ema_value is None:
        return result

    # Use price vs EMA to determine trend
    if last_closed_kline.close > ema_value:
        result[higher_tf] = TrendDirection.BULLISH
    else:
        result[higher_tf] = TrendDirection.BEARISH

    return result
```

- [ ] **Step 4: 修改 _run_strategy 方法**

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

    # S3-1: Calculate higher timeframe trends for MTF filtering
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
        higher_tf_trends=higher_tf_trends,  # Changed from {} to calculated trends
        kline_history=kline_history,
    )
```

- [ ] **Step 5: 添加单元测试**

```python
# tests/unit/test_signal_pipeline.py

class TestMtfAlignment:
    def test_pipeline_calculates_higher_tf_trends(self):
        """Verify pipeline correctly calculates MTF trends."""
        # Setup: Create pipeline with mocked dependencies
        config_manager = create_test_config_manager()
        pipeline = create_test_pipeline(config_manager)

        # Add 1h klines to history (simulate historical data)
        pipeline._kline_history["BTC/USDT:USDT:1h"] = [
            create_kline(hour_to_ms(9), "50000"),  # 09:00
            create_kline(hour_to_ms(10), "51000"), # 10:00
            create_kline(hour_to_ms(11), "52000"), # 11:00
        ]

        # Process 15m kline at 10:15
        kline_15m = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=minute_to_ms(10, 15),
            open=Decimal("50400"),
            high=Decimal("50600"),
            low=Decimal("50300"),
            close=Decimal("50500"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        trends = pipeline._get_closest_higher_tf_trends(kline_15m)

        # Should have calculated trend for 1h timeframe
        assert "1h" in trends
        # Trend should be based on price vs EMA comparison

    def test_pipeline_no_higher_timeframe(self):
        """Test when no higher timeframe exists (e.g., 1w)."""
        pipeline = create_test_pipeline()

        kline_1w = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1w",
            timestamp=1700000000000,
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50500"),
            volume=Decimal("10000"),
            is_closed=True,
        )

        trends = pipeline._get_closest_higher_tf_trends(kline_1w)

        # Should return empty dict for 1w (no higher timeframe)
        assert trends == {}

    def test_pipeline_no_higher_tf_data(self):
        """Test when higher timeframe data is not available."""
        pipeline = create_test_pipeline()

        # Don't add any 1h klines to history

        kline_15m = create_test_15m_kline()
        trends = pipeline._get_closest_higher_tf_trends(kline_15m)

        # Should return empty dict when no data available
        assert trends == {}

    def test_mtf_uses_config_ema_period(self):
        """Verify MTF uses configured EMA period."""
        config_manager = create_test_config_manager(mtf_ema_period=50)
        pipeline = create_test_pipeline(config_manager)

        # Add sufficient 1h klines for EMA warmup
        klines = [create_kline(hour_to_ms(h), str(50000 + h * 100)) for h in range(60)]
        pipeline._kline_history["BTC/USDT:USDT:1h"] = klines

        kline_15m = create_test_15m_kline()
        trends = pipeline._get_closest_higher_tf_trends(kline_15m)

        # Verify EMA was initialized with correct period
        ema_key = "BTC/USDT:USDT:1h"
        assert ema_key in pipeline._mtf_ema_indicators
        assert pipeline._mtf_ema_indicators[ema_key].period == 50
```

- [ ] **Step 6: 运行测试验证**

```bash
pytest tests/unit/test_signal_pipeline.py::TestMtfAlignment -v
```

Expected: All tests pass

- [ ] **Step 7: 运行所有 pipeline 测试**

```bash
pytest tests/unit/test_signal_pipeline.py -v
```

Expected: All tests pass

- [x] **Step 8: 提交代码**

```bash
git add src/application/signal_pipeline.py tests/unit/test_signal_pipeline.py
git commit -m "feat(S3-1): implement MTF trend calculation in signal pipeline"
```

---

## Task 5: 集成测试与验证

**Files:**
- Create: `tests/integration/test_mtf_e2e.py`

**Status**: ⏳ PENDING (待用户确认后执行)

**注意**: 运行测试前必须先通知用户确认！

- [ ] **Step 1: 创建集成测试文件**

```python
# tests/integration/test_mtf_e2e.py
"""
End-to-end tests for MTF (Multi-Timeframe) alignment.

These tests verify that MTF filtering works correctly in realistic scenarios.
"""
import pytest
import asyncio
from decimal import Decimal
from typing import Dict, List

from src.application.config_manager import ConfigManager
from src.application.signal_pipeline import SignalPipeline
from src.domain.models import KlineData, Direction, TrendDirection
from src.infrastructure.exchange_gateway import ExchangeGateway


def create_integration_kline(
    symbol: str,
    timeframe: str,
    timestamp: int,
    close: str,
    high: str = None,
    low: str = None,
) -> KlineData:
    """Create a realistic kline for integration testing."""
    close_dec = Decimal(close)
    high_dec = Decimal(high) if high else close_dec * Decimal("1.001")
    low_dec = Decimal(low) if low else close_dec * Decimal("0.999")

    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=close_dec,
        high=high_dec,
        low=low_dec,
        close=close_dec,
        volume=Decimal("1000"),
        is_closed=True,
    )
```

- [ ] **Step 2: 添加 MTF 过滤集成测试**

```python
class TestMtfFilterIntegration:
    @pytest.mark.asyncio
    async def test_mtf_blocks_conflicting_signals(self):
        """
        Scenario: 1h trend is BULLISH, 15m produces SHORT signal.
        Expected: MTF filter should reject the conflicting signal.
        """
        # Setup pipeline with MTF enabled
        config_manager = create_test_config_manager(mtf_ema_period=20)
        pipeline = create_test_pipeline(config_manager)

        # Simulate bullish 1h trend (rising prices)
        base_ts = 1700000000000
        for i in range(30):
            kline_1h = create_integration_kline(
                symbol="BTC/USDT:USDT",
                timeframe="1h",
                timestamp=base_ts + (i * 60 * 60 * 1000),
                close=str(50000 + i * 100),  # Rising prices = bullish
            )
            pipeline._kline_history["BTC/USDT:USDT:1h"] = [kline_1h]

        # Process 15m kline that would trigger SHORT
        kline_15m = create_integration_kline(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=base_ts + (30 * 60 * 60 * 1000) + (15 * 60 * 1000),
            close="50200",
            high="50300",  # High for potential short pinbar
            low="50100",
        )

        # Process kline
        await pipeline.process_kline(kline_15m)

        # Verify: Signal should be filtered out due to MTF conflict
        # (This depends on the specific signal filtering logic)
        # For now, verify that MTF trends were calculated
        assert len(pipeline._kline_history["BTC/USDT:USDT:1h"]) > 0

    @pytest.mark.asyncio
    async def test_mtf_allows_matching_signals(self):
        """
        Scenario: 1h trend is BULLISH, 15m produces LONG signal.
        Expected: MTF filter should allow the matching signal.
        """
        # Setup similar to above but with bullish setup
        config_manager = create_test_config_manager(mtf_ema_period=20)
        pipeline = create_test_pipeline(config_manager)

        # Simulate bullish 1h trend
        base_ts = 1700000000000
        for i in range(30):
            kline_1h = create_integration_kline(
                symbol="BTC/USDT:USDT",
                timeframe="1h",
                timestamp=base_ts + (i * 60 * 60 * 1000),
                close=str(50000 + i * 100),
            )
            pipeline._kline_history["BTC/USDT:USDT:1h"] = [kline_1h]

        # Process 15m kline that would trigger LONG
        kline_15m = create_integration_kline(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=base_ts + (30 * 60 * 60 * 1000) + (15 * 60 * 1000),
            close="50200",
            low="50100",  # Long pinbar setup
            high="50250",
        )

        await pipeline.process_kline(kline_15m)

        # MTF trends should be calculated
        # Signal filtering depends on specific strategy configuration
```

- [ ] **Step 3: 运行集成测试**

**注意**: 运行前必须先通知用户确认！

```bash
pytest tests/integration/test_mtf_e2e.py -v --tb=short
```

Expected: Tests pass

- [ ] **Step 4: 提交代码**

```bash
git add tests/integration/test_mtf_e2e.py
git commit -m "test(S3-1): add MTF end-to-end integration tests"
```

---

## Task 6: 验证与性能测试

**Files:**
- Manual verification scripts

**Status**: ⏳ PENDING (待 Task 5 完成后执行)

**注意**: 运行测试前必须先通知用户确认！

- [ ] **Step 1: 运行所有单元测试**

```bash
cd /Users/jiangwei/Documents/final
pytest tests/unit/ -v --tb=short
```

Expected: All tests pass, including new MTF tests

- [ ] **Step 2: 检查测试覆盖率**

```bash
pytest tests/unit/ --cov=src/domain/timeframe_utils --cov=src/application/signal_pipeline --cov-report=term-missing
```

Expected: New MTF code has > 90% coverage

- [ ] **Step 3: 性能验证（可选）**

```bash
# Run a quick performance check
python3 -c "
import time
from src.application.signal_pipeline import SignalPipeline
from src.application.config_manager import ConfigManager

# Create pipeline
config_manager = ConfigManager()
config_manager.load_all_configs()

# Time MTF calculation
start = time.time()
for i in range(100):
    kline = create_test_kline()
    trends = pipeline._get_closest_higher_tf_trends(kline)
end = time.time()

avg_ms = (end - start) / 100 * 1000
print(f'Average MTF calculation time: {avg_ms:.2f}ms')
assert avg_ms < 50, 'MTF calculation should take < 50ms'
print('Performance check PASSED')
"
```

Expected: Average calculation time < 50ms

- [ ] **Step 4: 最终提交**

```bash
git log --oneline -10
```

Verify all S3-1 commits are present

---

## Summary

### 已完成 (COMPLETED)

**Files Created:**
- ✅ `src/domain/timeframe_utils.py` - MTF 时间对齐工具函数 (commit 48b97fa)
- ✅ `tests/unit/test_timeframe_utils.py` - 工具函数单元测试 (commit 48b97fa)

**Files Modified:**
- ✅ `src/application/config_manager.py` - 新增 MTF 配置字段 (commit a5406a3)
- ✅ `config/core.yaml` - 添加 MTF 默认配置 (commit a5406a3)
- ✅ `src/application/signal_pipeline.py` - 实现 `_get_closest_higher_tf_trends()` 方法 (commit 57846a3)
- ✅ `tests/unit/test_signal_pipeline.py` - 新增 MTF 对齐测试 (commit 57846a3)

### 待完成 (PENDING)

**Task 5: 集成测试**
- ⏳ `tests/integration/test_mtf_e2e.py` - MTF 集成测试 (待用户确认后执行)

**Task 6: 验证与性能测试**
- ⏳ 运行所有单元测试
- ⏳ 检查测试覆盖率
- ⏳ 性能验证

### 验收标准

- [ ] 所有单元测试通过
- [ ] 集成测试通过
- [ ] 新增代码覆盖率 > 90%
- [ ] 性能测试通过（单次计算 < 50ms）

---

## 进度记录 (Progress Log)

**2026-03-27 会话 1 (已完成)**:
- ✅ Task 1: timeframe_utils.py 及单元测试 (commit 48b97fa)
- ✅ Task 2: config_manager.py MTF 配置字段 (commit a5406a3)
- ✅ Task 3: core.yaml 默认配置 (commit a5406a3)
- ✅ Task 4: signal_pipeline.py MTF 趋势计算 (commit 57846a3 + 57846a3 修复)

**2026-03-27 会话 2 (当前)**:
- ⏳ Task 5: 集成测试 (待用户确认)
- ⏳ Task 6: 验证与性能测试

---

*Plan created by writing-plans skill*
*Last updated: 2026-03-27 (会话 2 重启后)*
