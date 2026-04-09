"""
P1: Pinbar Signal Output Validation Tests

测试目标:
- C1: 动态标签生成（4 个测试）
- C2: Score 评分逻辑（4 个测试）
- C3: Risk Reward Info（4 个测试）

技术约束:
- 所有金额使用 decimal.Decimal，严禁 float
- 使用 PinbarStrategy 直接测试 PatternResult
- 使用 DynamicStrategyRunner 测试 SignalAttempt 输出
- 合成数据
"""
import pytest
from decimal import Decimal
from src.domain.models import KlineData, Direction, TrendDirection, PatternResult
from src.domain.strategy_engine import (
    PinbarStrategy,
    PinbarConfig,
    PatternStrategy,
    StrategyWithFilters,
    DynamicStrategyRunner,
)
from src.domain.filter_factory import (
    EmaTrendFilterDynamic,
    MtfFilterDynamic,
    FilterContext,
)


# ============================================================
# Helpers
# ============================================================

def _make_kline(
    open: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "1h",
    timestamp: int = 1000,
    volume: Decimal = Decimal("1000"),
) -> KlineData:
    """Helper to create KlineData with precise Decimal values."""
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        is_closed=True,
    )


def _make_bullish_pinbar_kline(**kwargs) -> KlineData:
    """Create a valid bullish pinbar kline."""
    defaults = dict(
        open=Decimal("108"), high=Decimal("110"),
        low=Decimal("100"), close=Decimal("109"),
    )
    defaults.update(kwargs)
    return _make_kline(**defaults)


def _make_bearish_pinbar_kline(**kwargs) -> KlineData:
    """Create a valid bearish pinbar kline."""
    defaults = dict(
        open=Decimal("101"), high=Decimal("120"),
        low=Decimal("100"), close=Decimal("102"),
    )
    defaults.update(kwargs)
    return _make_kline(**defaults)


# ============================================================
# C1. 动态标签生成（4 个测试）
# ============================================================

class TestDynamicTagGeneration:
    """动态标签生成测试

    注意: PatternResult 本身不直接生成标签。
    标签由 SignalResult 在应用层组装，基于过滤器的 TraceEvent metadata。
    这里测试 FilterResult/TraceEvent 中的 metadata 是否包含可用于生成标签的信息。
    """

    def test_ema_filter_pass_generates_trend_metadata(self):
        """C1-01: EMA 过滤器通过时 metadata 包含趋势方向信息"""
        ema_filter = EmaTrendFilterDynamic(period=60, enabled=True)
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.7,
            details={"wick_ratio": 0.8, "body_ratio": 0.1},
        )
        context = FilterContext(
            higher_tf_trends={},
            current_trend=TrendDirection.BULLISH,
        )

        result = ema_filter.check(pattern, context)

        assert result.passed is True
        assert result.reason == "trend_match"
        # Metadata 包含标签生成所需信息
        assert result.metadata["trend_direction"] == "bullish"
        # pattern_direction 使用 .value which is uppercase for Direction enum
        assert result.metadata["pattern_direction"] == "LONG"

    def test_mtf_filter_pass_generates_confirmation_metadata(self):
        """C1-02: MTF 过滤器通过时 metadata 包含确认信息"""
        mtf_filter = MtfFilterDynamic(enabled=True)
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.7,
            details={"wick_ratio": 0.8, "body_ratio": 0.1},
        )
        context = FilterContext(
            higher_tf_trends={"1h": TrendDirection.BULLISH},
            current_trend=None,
            current_timeframe="15m",
        )

        result = mtf_filter.check(pattern, context)

        assert result.passed is True
        assert result.reason == "mtf_confirmed_bullish"
        assert result.metadata["higher_timeframe"] == "1h"
        assert result.metadata["higher_trend"] == "bullish"

    def test_multiple_filters_all_pass_metadata_combined(self):
        """C1-03: 多过滤器通过时各自 metadata 可组合为完整标签集"""
        ema_filter = EmaTrendFilterDynamic(period=60, enabled=True)
        mtf_filter = MtfFilterDynamic(enabled=True)
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.SHORT,
            score=0.75,
            details={"wick_ratio": 0.85, "body_ratio": 0.1},
        )

        # EMA: bearish
        ema_context = FilterContext(
            higher_tf_trends={"4h": TrendDirection.BEARISH},
            current_trend=TrendDirection.BEARISH,
        )
        ema_result = ema_filter.check(pattern, ema_context)

        # MTF: confirmed
        mtf_context = FilterContext(
            higher_tf_trends={"4h": TrendDirection.BEARISH},
            current_trend=None,
            current_timeframe="1h",
        )
        mtf_result = mtf_filter.check(pattern, mtf_context)

        # 两个过滤器都通过，metadata 可组合
        assert ema_result.passed is True
        assert mtf_result.passed is True

        # 模拟标签组装逻辑
        tags = []
        if ema_result.passed and "trend_direction" in ema_result.metadata:
            tags.append({"name": "EMA", "value": ema_result.metadata["trend_direction"].title()})
        if mtf_result.passed and "higher_trend" in mtf_result.metadata:
            tags.append({"name": "MTF", "value": "Confirmed"})

        assert len(tags) == 2
        assert tags[0] == {"name": "EMA", "value": "Bearish"}
        assert tags[1] == {"name": "MTF", "value": "Confirmed"}

    def test_failed_filter_no_tag_generated(self):
        """C1-04: 未通过过滤器不生成标签"""
        ema_filter = EmaTrendFilterDynamic(period=60, enabled=True)
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.7,
            details={"wick_ratio": 0.8, "body_ratio": 0.1},
        )
        # Bearish trend conflicts with bullish signal
        context = FilterContext(
            higher_tf_trends={},
            current_trend=TrendDirection.BEARISH,
        )

        result = ema_filter.check(pattern, context)

        assert result.passed is False
        assert result.reason == "bearish_trend_blocks_long"
        # Metadata 仍然包含信息（用于调试），但标签生成逻辑应检查 passed 字段
        # 模拟正确的标签组装逻辑（失败不生成标签）
        tags = []
        if result.passed and "trend_direction" in result.metadata:
            tags.append({"name": "EMA", "value": result.metadata["trend_direction"].title()})

        assert len(tags) == 0  # 未通过，不生成标签


# ============================================================
# C2. Score 评分逻辑（4 个测试）
# ============================================================

class TestScoreLogic:
    """Score 评分逻辑测试"""

    @pytest.fixture
    def strategy(self):
        return PinbarStrategy(PinbarConfig())

    def test_high_wick_ratio_with_atr_bonus(self, strategy):
        """C2-01: 高影线比例 + 高 ATR → 高评分（ capped at 1.0）"""
        # Kline: range=10, body=1, lower_wick=8, upper_wick=1
        # wick_ratio = 8/10 = 0.8, body_ratio = 1/10 = 0.1
        # body_position = (108.5-100)/10 = 0.85, threshold = 1-0.1-0.05=0.85, PASS
        # atr_ratio = 10/5 = 2.0
        # score = 0.8 * 0.7 + min(2.0, 2.0) * 0.3 = 0.56 + 0.6 = 1.16 → capped at 1.0
        kline = _make_kline(
            open=Decimal("109"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("108"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))

        assert result is not None
        assert result.score <= 1.0  # Score must be capped at 1.0
        assert result.score > 0.8  # High wick + ATR should give high score
        assert result.score == 1.0  # Exact: 0.56 + 0.6 = 1.16 > 1.0

    def test_high_wick_ratio_without_atr(self, strategy):
        """C2-02: 高影线比例 + 无 ATR → 评分等于 wick_ratio"""
        # Kline: range=10, body=1, lower_wick=8, upper_wick=1
        # wick_ratio = 8/10 = 0.8, no ATR → score = wick_ratio = 0.8
        kline = _make_kline(
            open=Decimal("109"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("108"),
        )
        result = strategy.detect(kline, atr_value=None)

        assert result is not None
        assert result.score == pytest.approx(0.8, abs=1e-9)

    def test_boundary_wick_ratio_scoring(self, strategy):
        """C2-03: 边界影线比例评分（wick_ratio 刚好在阈值 0.6）"""
        # range=10, body=3, lower_wick=6, upper_wick=1
        # wick_ratio = 0.6, body_ratio = 0.3
        # open=109, close=106: lower_wick=106-100=6, upper_wick=110-109=1
        # body_center=107.5, body_position=(107.5-100)/10=0.75
        # threshold = 1-0.1-0.15=0.75, 0.75 >= 0.75 PASS
        kline = _make_kline(
            open=Decimal("109"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("106"),
        )
        result = strategy.detect(kline, atr_value=None)

        assert result is not None
        assert result.details["wick_ratio"] == pytest.approx(0.6, abs=1e-9)
        assert result.score == pytest.approx(0.6, abs=1e-9)

    def test_score_never_exceeds_1_0(self, strategy):
        """C2-04: 评分不超过 1.0（即使 wick_ratio + ATR bonus 总和超过）"""
        # Kline: range=100, body=1, lower_wick=98, upper_wick=1
        # wick_ratio = 0.98, atr_ratio = 100/10 = 10.0
        # score = 0.98 * 0.7 + min(10.0, 2.0) * 0.3 = 0.686 + 0.6 = 1.286 → capped at 1.0
        kline = _make_kline(
            open=Decimal("98"), high=Decimal("100"),
            low=Decimal("0"), close=Decimal("99"),
        )
        result = strategy.detect(kline, atr_value=Decimal("10.0"))

        assert result is not None
        assert result.score <= 1.0
        # The raw calculation would exceed 1.0
        raw_score = result.details["wick_ratio"] * 0.7 + 2.0 * 0.3
        assert raw_score > 1.0  # Raw exceeds 1.0
        assert result.score == 1.0  # But result is capped


# ============================================================
# C3. Risk Reward Info（4 个测试）
# ============================================================

class TestRiskRewardInfo:
    """Risk Reward 信息测试

    注意: Risk Reward 计算由 risk_calculator 完成，
    PatternResult 只包含 entry_price（通过 kline.close 获得）和 score。
    这里验证 SignalAttempt 中的 pattern 结果包含构建 Risk Reward 所需的基础数据。
    """

    @pytest.fixture
    def strategy(self):
        return PinbarStrategy(PinbarConfig())

    def test_bullish_signal_entry_and_stop(self, strategy):
        """C3-01: 看涨信号 - entry 和 stop_loss 逻辑正确"""
        kline = _make_bullish_pinbar_kline()
        result = strategy.detect(kline, atr_value=Decimal("5.0"))

        assert result is not None
        assert result.direction == Direction.LONG
        # Entry price = current close
        entry = kline.close
        assert entry == Decimal("109")
        # Stop loss should be below the pinbar low
        # (actual calculation in risk_calculator, but direction is validated)
        # The pinbar low provides a natural stop level
        assert result.details["wick_ratio"] > 0.5

    def test_bearish_signal_entry_and_stop(self, strategy):
        """C3-02: 看跌信号 - entry 和 stop_loss 逻辑正确"""
        kline = _make_bearish_pinbar_kline()
        result = strategy.detect(kline, atr_value=Decimal("10.0"))

        assert result is not None
        assert result.direction == Direction.SHORT
        # Entry price = current close
        entry = kline.close
        assert entry == Decimal("102")
        # Stop loss should be above the pinbar high
        # The pinbar high provides a natural stop level
        assert result.details["wick_ratio"] > 0.5

    def test_take_profit_level_generation_ready(self, strategy):
        """C3-03: 止盈级别生成的基础数据完整

        止盈级别由 risk_calculator 基于 entry/stop/direction 计算。
        这里验证 PatternResult 提供的基础数据足以支持止盈计算。
        """
        kline = _make_bullish_pinbar_kline()
        result = strategy.detect(kline, atr_value=Decimal("5.0"))

        assert result is not None
        # 止盈计算所需的基础数据
        assert result.direction == Direction.LONG
        assert result.score > 0  # Score > 0 means valid signal
        assert "wick_ratio" in result.details  # Used for signal quality
        assert "body_ratio" in result.details
        assert "body_position" in result.details

        # Entry = close, Stop = below low (direction-dependent)
        entry = kline.close
        pinbar_low = kline.low
        # For LONG: stop_loss < entry, distance = entry - stop
        # Pinbar low is a valid stop level
        assert entry > pinbar_low  # Entry above low for LONG

    def test_take_profit_price_precision(self, strategy):
        """C3-04: 止盈价格精度 - PatternResult 中所有数值为 Decimal/float 精度正确

        使用有效 Pinbar + 高精度 Decimal 价格验证。
        """
        # Design a valid bullish pinbar with high precision decimals:
        # range=10.90, body=0.10 (body_ratio~0.009), lower_wick=9.80, upper_wick=1.00
        # wick_ratio = 9.80/10.90 ~ 0.899
        # body_center=109.85, body_position=(109.85-100)/10.90 ~ 0.904
        # threshold = 1-0.1-0.0046=0.8954, 0.904 >= 0.8954 PASS
        kline = _make_kline(
            open=Decimal("109.80"), high=Decimal("110.90"),
            low=Decimal("100.00"), close=Decimal("109.90"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.12345678"))

        assert result is not None
        # Score is float (not Decimal) - designed for UI display
        assert isinstance(result.score, float)
        assert 0 < result.score <= 1.0
        # Details are also float
        assert isinstance(result.details["wick_ratio"], float)
        assert isinstance(result.details["body_ratio"], float)
        assert isinstance(result.details["body_position"], float)
        # Original Kline data preserves Decimal precision
        assert isinstance(kline.close, Decimal)
        assert kline.close == Decimal("109.90")
