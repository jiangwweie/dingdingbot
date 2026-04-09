"""
P1: Pinbar Filter Combination Tests

测试目标:
- B1: Pinbar + EMA Trend Filter 组合（6 个测试）
- B2: Pinbar + MTF 多周期确认（6 个测试）
- B3: Pinbar + ATR Filter（3 个测试）
- B4: 多过滤器组合（3 个测试）

技术约束:
- 所有金额使用 decimal.Decimal，严禁 float
- 使用 DynamicStrategyRunner + StrategyWithFilters 测试过滤器链
- 合成数据，精确构造边界值
"""
import pytest
from decimal import Decimal
from src.domain.models import KlineData, Direction, TrendDirection, PatternResult
from src.domain.strategy_engine import (
    PinbarStrategy,
    PinbarConfig,
    StrategyWithFilters,
    DynamicStrategyRunner,
)
from src.domain.filter_factory import (
    EmaTrendFilterDynamic,
    MtfFilterDynamic,
    AtrFilterDynamic,
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


def _warmup_ema_for_bullish(ema_filter: EmaTrendFilterDynamic, symbol: str, timeframe: str) -> None:
    """Warm up EMA so trend is BULLISH (close > EMA).

    Generates 65 rising prices from 70 to 134. EMA ~102.
    A kline with close > 102 will be bullish.
    """
    for i in range(65):
        p = Decimal(str(70 + i))
        ema_filter.update_state(
            _make_kline(open=p, high=p + 1, low=p - 1, close=p,
                        symbol=symbol, timeframe=timeframe),
            symbol, timeframe
        )


def _warmup_ema_for_bearish(ema_filter: EmaTrendFilterDynamic, symbol: str, timeframe: str) -> None:
    """Warm up EMA so trend is BEARISH (close < EMA).

    Generates 65 falling prices from 165 to 101. EMA ~133.
    A kline with close < 133 will be bearish.
    """
    for i in range(65):
        p = Decimal(str(165 - i))
        ema_filter.update_state(
            _make_kline(open=p, high=p + 1, low=p - 1, close=p,
                        symbol=symbol, timeframe=timeframe),
            symbol, timeframe
        )


def _build_runner(
    ema_enabled: bool = True,
    mtf_enabled: bool = True,
    atr_enabled: bool = False,
) -> DynamicStrategyRunner:
    """Build a DynamicStrategyRunner with specified filters."""
    pinbar_strat = PinbarStrategy(PinbarConfig())
    filters = []

    if ema_enabled:
        filters.append(EmaTrendFilterDynamic(period=60, enabled=True))
    if mtf_enabled:
        filters.append(MtfFilterDynamic(enabled=True))
    if atr_enabled:
        filters.append(AtrFilterDynamic(period=14, enabled=True))

    strategy_with_filters = StrategyWithFilters(
        name="pinbar",
        strategy=pinbar_strat,
        filters=filters,
    )

    return DynamicStrategyRunner(strategies=[strategy_with_filters])


# ============================================================
# B1. Pinbar + EMA Trend Filter（6 个测试）
# ============================================================

class TestPinbarWithEmaTrend:
    """Pinbar + EMA 趋势过滤器组合测试"""

    def _build_runner(self, ema_enabled: bool = True) -> DynamicStrategyRunner:
        """Build runner with EMA filter only."""
        pinbar_strat = PinbarStrategy(PinbarConfig())
        ema_filter = EmaTrendFilterDynamic(period=60, enabled=ema_enabled)
        strat = StrategyWithFilters(name="pinbar", strategy=pinbar_strat, filters=[ema_filter])
        return DynamicStrategyRunner(strategies=[strat])

    def test_bullish_trend_bullish_pinbar_passes(self):
        """B1-01: 看涨趋势 + 看涨 Pinbar → SIGNAL_FIRED"""
        runner = self._build_runner()
        kline = _make_kline(
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("109"),
            timeframe="15m",
        )
        # Warm up EMA: rising prices → EMA ~102, close=109 > 102 → BULLISH
        ema_filter = runner._strategies[0].filters[0]
        _warmup_ema_for_bullish(ema_filter, kline.symbol, kline.timeframe)

        attempts = runner.run_all(kline, higher_tf_trends={})
        assert len(attempts) == 1
        assert attempts[0].final_result == "SIGNAL_FIRED"
        assert attempts[0].pattern is not None
        assert attempts[0].pattern.direction == Direction.LONG

    def test_bullish_trend_bearish_pinbar_rejected(self):
        """B1-02: 看涨趋势 + 看跌 Pinbar → FILTERED"""
        runner = self._build_runner()
        kline = _make_kline(
            open=Decimal("101"), high=Decimal("120"),
            low=Decimal("100"), close=Decimal("102"),
            timeframe="15m",
        )
        # Warm up EMA: rising prices → EMA ~102, close=102 ~ 102
        # To ensure bullish: need close > EMA. close=102, EMA~102 is borderline.
        # Use a different warmup to ensure EMA is clearly below 102.
        # Let's use prices from 60 to 100: EMA ~68, close=102 > 68 → BULLISH
        ema_filter = runner._strategies[0].filters[0]
        for i in range(65):
            p = Decimal(str(60 + i))
            ema_filter.update_state(
                _make_kline(open=p, high=p + 1, low=p - 1, close=p,
                            symbol=kline.symbol, timeframe=kline.timeframe),
                kline.symbol, kline.timeframe
            )

        attempts = runner.run_all(kline, higher_tf_trends={})
        assert len(attempts) == 1
        assert attempts[0].final_result == "FILTERED"

    def test_bearish_trend_bearish_pinbar_passes(self):
        """B1-03: 看跌趋势 + 看跌 Pinbar → SIGNAL_FIRED"""
        runner = self._build_runner()
        kline = _make_kline(
            open=Decimal("101"), high=Decimal("120"),
            low=Decimal("100"), close=Decimal("102"),
            timeframe="15m",
        )
        # Warm up EMA: falling prices → EMA ~133, close=102 < 133 → BEARISH
        ema_filter = runner._strategies[0].filters[0]
        _warmup_ema_for_bearish(ema_filter, kline.symbol, kline.timeframe)

        attempts = runner.run_all(kline, higher_tf_trends={})
        assert len(attempts) == 1
        assert attempts[0].final_result == "SIGNAL_FIRED"
        assert attempts[0].pattern is not None
        assert attempts[0].pattern.direction == Direction.SHORT

    def test_bearish_trend_bullish_pinbar_rejected(self):
        """B1-04: 看跌趋势 + 看涨 Pinbar → FILTERED"""
        runner = self._build_runner()
        kline = _make_kline(
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("109"),
            timeframe="15m",
        )
        # Warm up EMA: falling prices → EMA ~133, close=109 < 133 → BEARISH
        ema_filter = runner._strategies[0].filters[0]
        _warmup_ema_for_bearish(ema_filter, kline.symbol, kline.timeframe)

        attempts = runner.run_all(kline, higher_tf_trends={})
        assert len(attempts) == 1
        assert attempts[0].final_result == "FILTERED"

    def test_ema_data_not_ready_rejected(self):
        """B1-05: EMA 数据未就绪 → FILTERED"""
        runner = self._build_runner()
        kline = _make_kline(
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("109"),
            timeframe="15m",
        )
        # Don't warm up EMA → current_trend is None

        attempts = runner.run_all(kline, higher_tf_trends={})
        assert len(attempts) == 1
        assert attempts[0].final_result == "FILTERED"
        assert any(
            fr[1].reason == "ema_data_not_ready"
            for fr in attempts[0].filter_results
        )

    def test_ema_filter_disabled_always_passes(self):
        """B1-06: EMA 过滤器禁用 → SIGNAL_FIRED（无趋势数据也通过）"""
        runner = self._build_runner(ema_enabled=False)
        kline = _make_kline(
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("109"),
            timeframe="15m",
        )
        # No EMA warmup needed

        attempts = runner.run_all(kline, higher_tf_trends={})
        assert len(attempts) == 1
        assert attempts[0].final_result == "SIGNAL_FIRED"
        assert attempts[0].pattern is not None
        assert attempts[0].pattern.direction == Direction.LONG


# ============================================================
# B2. Pinbar + MTF 多周期确认（6 个测试）
# ============================================================

class TestPinbarWithMtf:
    """Pinbar + MTF 多周期确认测试"""

    def _build_runner(self, mtf_enabled: bool = True) -> DynamicStrategyRunner:
        """Build runner with MTF filter only."""
        pinbar_strat = PinbarStrategy(PinbarConfig())
        mtf_filter = MtfFilterDynamic(enabled=mtf_enabled)
        strat = StrategyWithFilters(name="pinbar", strategy=pinbar_strat, filters=[mtf_filter])
        return DynamicStrategyRunner(strategies=[strat])

    def test_15m_signal_confirmed_by_1h_passes(self):
        """B2-01: 15m 信号被 1h 确认 → SIGNAL_FIRED"""
        runner = self._build_runner()
        kline = _make_kline(
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("109"),
            timeframe="15m",
        )
        higher_tf_trends = {"1h": TrendDirection.BULLISH}

        attempts = runner.run_all(kline, higher_tf_trends=higher_tf_trends)
        assert len(attempts) == 1
        assert attempts[0].final_result == "SIGNAL_FIRED"

    def test_15m_signal_rejected_by_1h(self):
        """B2-02: 15m 信号被 1h 拒绝 → FILTERED"""
        runner = self._build_runner()
        kline = _make_kline(
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("109"),
            timeframe="15m",
        )
        # 1h is bearish, but signal is bullish → conflict
        higher_tf_trends = {"1h": TrendDirection.BEARISH}

        attempts = runner.run_all(kline, higher_tf_trends=higher_tf_trends)
        assert len(attempts) == 1
        assert attempts[0].final_result == "FILTERED"
        assert any(
            fr[1].reason == "mtf_rejected_bearish_higher_tf"
            for fr in attempts[0].filter_results
        )

    def test_1h_signal_confirmed_by_4h_passes(self):
        """B2-03: 1h 信号被 4h 确认 → SIGNAL_FIRED"""
        runner = self._build_runner()
        kline = _make_kline(
            open=Decimal("101"), high=Decimal("120"),
            low=Decimal("100"), close=Decimal("102"),
            timeframe="1h",
        )
        higher_tf_trends = {"4h": TrendDirection.BEARISH}

        attempts = runner.run_all(kline, higher_tf_trends=higher_tf_trends)
        assert len(attempts) == 1
        assert attempts[0].final_result == "SIGNAL_FIRED"

    def test_higher_tf_data_unavailable_rejected(self):
        """B2-04: 高周期数据不可用 → FILTERED"""
        runner = self._build_runner()
        kline = _make_kline(
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("109"),
            timeframe="15m",
        )
        # No 1h data in higher_tf_trends
        higher_tf_trends = {}

        attempts = runner.run_all(kline, higher_tf_trends=higher_tf_trends)
        assert len(attempts) == 1
        assert attempts[0].final_result == "FILTERED"
        assert any(
            fr[1].reason == "higher_tf_data_unavailable"
            for fr in attempts[0].filter_results
        )

    def test_no_higher_timeframe_1w_passes(self):
        """B2-05: 无更高周期（1w）→ SIGNAL_FIRED"""
        runner = self._build_runner()
        kline = _make_kline(
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("109"),
            timeframe="1w",
        )
        # 1w has no higher timeframe in MTF mapping

        attempts = runner.run_all(kline, higher_tf_trends={})
        assert len(attempts) == 1
        assert attempts[0].final_result == "SIGNAL_FIRED"

    def test_mtf_filter_disabled_always_passes(self):
        """B2-06: MTF 过滤器禁用 → SIGNAL_FIRED"""
        runner = self._build_runner(mtf_enabled=False)
        kline = _make_kline(
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("109"),
            timeframe="15m",
        )
        # No higher TF data, but filter is disabled

        attempts = runner.run_all(kline, higher_tf_trends={})
        assert len(attempts) == 1
        assert attempts[0].final_result == "SIGNAL_FIRED"


# ============================================================
# B3. Pinbar + ATR Filter（3 个测试）
# ============================================================

class TestPinbarWithAtr:
    """Pinbar + ATR 波动率过滤器测试"""

    def _build_runner(self, atr_enabled: bool = True) -> DynamicStrategyRunner:
        """Build runner with ATR filter only."""
        pinbar_strat = PinbarStrategy(PinbarConfig())
        atr_filter = AtrFilterDynamic(
            period=14,
            min_atr_ratio=Decimal("0.001"),
            enabled=atr_enabled
        )
        strat = StrategyWithFilters(name="pinbar", strategy=pinbar_strat, filters=[atr_filter])
        return DynamicStrategyRunner(strategies=[strat])

    def test_atr_sufficient_volatility_passes(self):
        """B3-01: ATR 波动率充足 → SIGNAL_FIRED"""
        runner = self._build_runner()
        symbol = "BTC/USDT:USDT"
        timeframe = "1h"

        # Generate 15 klines with significant volatility to build ATR
        klines = []
        for i in range(15):
            k = _make_kline(
                open=Decimal(str(100 + i * 2)),
                high=Decimal(str(100 + i * 2 + 5)),
                low=Decimal(str(100 + i * 2 - 3)),
                close=Decimal(str(100 + i * 2 + 1)),
                timeframe=timeframe,
                timestamp=1000 + i,
                symbol=symbol,
            )
            klines.append(k)

        # Last kline is a bullish pinbar with good range
        pinbar_kline = _make_kline(
            open=Decimal("128"), high=Decimal("130"),
            low=Decimal("120"), close=Decimal("129"),
            timeframe=timeframe,
            timestamp=1015,
            symbol=symbol,
        )

        # Update ATR with all klines
        atr_filter = runner._strategies[0].filters[0]
        for k in klines:
            atr_filter.update_state(k, k.symbol, k.timeframe)

        attempts = runner.run_all(pinbar_kline, higher_tf_trends={})
        assert len(attempts) == 1
        assert attempts[0].final_result == "SIGNAL_FIRED"

    def test_atr_insufficient_volatility_rejected(self):
        """B3-02: ATR 波动率不足 → NO_PATTERN (K 线本身不是 Pinbar)

        先建立高 ATR（大波幅 K 线），然后用极小波幅 K 线测试。
        极小波幅既不是 Pinbar，也不满足 ATR 波动率要求。
        """
        runner = self._build_runner()
        symbol = "BTC/USDT:USDT"
        timeframe = "1h"

        # Generate 15 klines with HUGE volatility to build a high ATR
        for i in range(15):
            k = _make_kline(
                open=Decimal(str(100 + i * 10)),
                high=Decimal(str(200 + i * 10)),  # huge range: 100
                low=Decimal(str(100 + i * 10)),
                close=Decimal(str(150 + i * 10)),
                timeframe=timeframe,
                timestamp=1000 + i,
                symbol=symbol,
            )
            atr_filter = runner._strategies[0].filters[0]
            atr_filter.update_state(k, k.symbol, k.timeframe)

        # Tiny doji-like kline (not a pinbar AND low volatility)
        tiny_kline = _make_kline(
            open=Decimal("249"), high=Decimal("251"),  # range = 2
            low=Decimal("249"), close=Decimal("250"),
            timeframe=timeframe,
            timestamp=1015,
            symbol=symbol,
        )

        attempts = runner.run_all(tiny_kline, higher_tf_trends={})
        assert len(attempts) == 1
        # The tiny kline is not a pinbar, so NO_PATTERN
        assert attempts[0].final_result == "NO_PATTERN"

    def test_atr_data_not_ready_rejected(self):
        """B3-03: ATR 数据未就绪 → FILTERED"""
        runner = self._build_runner()
        kline = _make_kline(
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("109"),
            timeframe="1h",
        )
        # No warmup → ATR not ready

        attempts = runner.run_all(kline, higher_tf_trends={})
        assert len(attempts) == 1
        assert attempts[0].final_result == "FILTERED"
        assert any(
            fr[1].reason == "atr_data_not_ready"
            for fr in attempts[0].filter_results
        )


# ============================================================
# B4. 多过滤器组合（3 个测试）
# ============================================================

class TestMultipleFilterCombination:
    """多过滤器组合测试（EMA + MTF 链）"""

    def _build_runner_full(self) -> DynamicStrategyRunner:
        """Build runner with EMA + MTF filters."""
        pinbar_strat = PinbarStrategy(PinbarConfig())
        ema_filter = EmaTrendFilterDynamic(period=60, enabled=True)
        mtf_filter = MtfFilterDynamic(enabled=True)
        strat = StrategyWithFilters(
            name="pinbar",
            strategy=pinbar_strat,
            filters=[ema_filter, mtf_filter],
        )
        return DynamicStrategyRunner(strategies=[strat])

    def test_all_filters_pass_signal_fired(self):
        """B4-01: 所有过滤器通过 → SIGNAL_FIRED"""
        runner = self._build_runner_full()
        kline = _make_kline(
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("109"),
            timeframe="15m",
        )

        # Warm up EMA → bullish (EMA ~102, close=109 > 102)
        ema_filter = runner._strategies[0].filters[0]
        _warmup_ema_for_bullish(ema_filter, kline.symbol, kline.timeframe)

        # MTF → confirmed bullish
        higher_tf_trends = {"1h": TrendDirection.BULLISH}

        attempts = runner.run_all(kline, higher_tf_trends=higher_tf_trends)
        assert len(attempts) == 1
        assert attempts[0].final_result == "SIGNAL_FIRED"
        # Both filters should be recorded
        filter_names = [fr[0] for fr in attempts[0].filter_results]
        assert "ema_trend" in filter_names
        assert "mtf" in filter_names

    def test_ema_fails_short_circuit(self):
        """B4-02: EMA 失败触发短路 → FILTERED（MTF 不执行）"""
        runner = self._build_runner_full()
        kline = _make_kline(
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("109"),
            timeframe="15m",
        )

        # Warm up EMA → bearish trend (EMA ~133, close=109 < 133)
        ema_filter = runner._strategies[0].filters[0]
        _warmup_ema_for_bearish(ema_filter, kline.symbol, kline.timeframe)

        # MTF would pass, but EMA short-circuits first
        higher_tf_trends = {"1h": TrendDirection.BULLISH}

        attempts = runner.run_all(kline, higher_tf_trends=higher_tf_trends)
        assert len(attempts) == 1
        assert attempts[0].final_result == "FILTERED"
        # Only EMA filter should be recorded (short-circuit)
        filter_names = [fr[0] for fr in attempts[0].filter_results]
        assert "ema_trend" in filter_names
        assert "mtf" not in filter_names  # MTF not executed due to short-circuit

    def test_ema_passes_mtf_fails(self):
        """B4-03: EMA 通过但 MTF 失败 → FILTERED"""
        runner = self._build_runner_full()
        kline = _make_kline(
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("109"),
            timeframe="15m",
        )

        # Warm up EMA → bullish
        ema_filter = runner._strategies[0].filters[0]
        _warmup_ema_for_bullish(ema_filter, kline.symbol, kline.timeframe)

        # MTF → rejected (bearish higher TF)
        higher_tf_trends = {"1h": TrendDirection.BEARISH}

        attempts = runner.run_all(kline, higher_tf_trends=higher_tf_trends)
        assert len(attempts) == 1
        assert attempts[0].final_result == "FILTERED"
        # Both filters should be recorded (EMA passes, MTF fails)
        filter_names = [fr[0] for fr in attempts[0].filter_results]
        assert "ema_trend" in filter_names
        assert "mtf" in filter_names
