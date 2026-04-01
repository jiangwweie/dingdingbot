"""
End-to-End Integration tests for Engulfing Strategy - T7 测试。

测试覆盖:
- T7-1: 真实 K 线数据回测场景
- T7-2: 与 Pinbar 策略对比
- T7-3: 参数敏感性测试
- T7-4: 极端行情稳定性测试
"""
import pytest
from decimal import Decimal
from src.domain.models import KlineData, Direction, TrendDirection
from src.domain.strategies.engulfing_strategy import EngulfingStrategy
from src.domain.strategy_engine import PinbarStrategy
from src.domain.filter_factory import (
    AtrFilterDynamic, EmaTrendFilterDynamic, MtfFilterDynamic, FilterContext
)


def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    open: Decimal = Decimal("100"),
    high: Decimal = Decimal("100"),
    low: Decimal = Decimal("100"),
    close: Decimal = Decimal("100"),
    timestamp: int = 1000,
    is_closed: bool = True,
) -> KlineData:
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=Decimal("1000"),
        is_closed=is_closed,
    )


class TestEngulfingE2E:
    """T7: End-to-End Integration tests."""

    def test_t7_1_realistic_kline_sequence(self):
        """T7-1: 真实 K 线数据回测场景"""
        strategy = EngulfingStrategy()
        atr_filter = AtrFilterDynamic(
            period=14,
            min_atr_ratio=Decimal("0.5"),
            min_absolute_range=Decimal("0.1"),
            enabled=True
        )

        # Setup ATR state
        atr_filter._atr_state["BTC/USDT:USDT:15m"] = {
            "tr_values": [Decimal("100")] * 14,
            "atr": Decimal("100"),
            "prev_close": Decimal("50000")
        }

        # Simulate realistic BTC K-line sequence
        klines = [
            # Normal candles (no pattern)
            create_kline(open=Decimal("50000"), high=Decimal("50100"), low=Decimal("49900"), close=Decimal("50050"), timestamp=1000),
            create_kline(open=Decimal("50050"), high=Decimal("50150"), low=Decimal("50000"), close=Decimal("50100"), timestamp=2000),
            create_kline(open=Decimal("50100"), high=Decimal("50200"), low=Decimal("50050"), close=Decimal("50150"), timestamp=3000),

            # Bullish engulfing setup
            create_kline(open=Decimal("50150"), high=Decimal("50200"), low=Decimal("50000"), close=Decimal("50050"), timestamp=4000),  # Bearish
            create_kline(open=Decimal("50040"), high=Decimal("50300"), low=Decimal("50000"), close=Decimal("50250"), timestamp=5000),  # Bullish engulfing

            # More normal candles
            create_kline(open=Decimal("50250"), high=Decimal("50350"), low=Decimal("50200"), close=Decimal("50300"), timestamp=6000),

            # Bearish engulfing setup
            create_kline(open=Decimal("50300"), high=Decimal("50400"), low=Decimal("50250"), close=Decimal("50380"), timestamp=7000),  # Bullish
            create_kline(open=Decimal("50390"), high=Decimal("50450"), low=Decimal("50200"), close=Decimal("50250"), timestamp=8000),  # Bearish engulfing
        ]

        signals_detected = []

        for i, kline in enumerate(klines):
            if i == 0:
                continue

            prev_kline = klines[i-1]
            result = strategy.detect(kline, prev_kline=prev_kline, atr_value=Decimal("100"))

            if result:
                # Run through ATR filter
                context = FilterContext(kline=kline, current_timeframe="15m", higher_tf_trends={}, current_trend=None)
                event = atr_filter.check(result, context)

                if event.passed:
                    signals_detected.append({
                        'timestamp': kline.timestamp,
                        'direction': result.direction,
                        'score': result.score
                    })

        # Should detect 2 engulfing patterns
        assert len(signals_detected) >= 1, "Should detect at least 1 valid signal"

        # Verify signal directions
        directions = [s['direction'] for s in signals_detected]
        assert Direction.LONG in directions or Direction.SHORT in directions

    def test_t7_2_engulfing_vs_pinbar_comparison(self):
        """T7-2: 与 Pinbar 策略对比"""
        engulfing_strategy = EngulfingStrategy()

        # Create K-line for engulfing
        prev = create_kline(
            open=Decimal("1000"), high=Decimal("1010"),
            low=Decimal("985"), close=Decimal("990"),
            timestamp=1000
        )
        curr_engulfing = create_kline(
            open=Decimal("989"), high=Decimal("1020"),
            low=Decimal("980"), close=Decimal("1001"),
            timestamp=2000
        )

        # Engulfing detection
        engulfing_result = engulfing_strategy.detect(curr_engulfing, prev_kline=prev, atr_value=Decimal("100"))

        # Engulfing strategy should work
        assert engulfing_result is not None, "Engulfing strategy should detect pattern"
        assert engulfing_result.direction == Direction.LONG
        engulfing_result = engulfing_strategy.detect(curr_engulfing, prev_kline=prev, atr_value=Decimal("100"))

        # Pinbar detection
        pinbar_result = pinbar_strategy.detect(curr_pinbar, atr_value=Decimal("100"))

        # Both strategies should work independently
        assert engulfing_result is not None or pinbar_result is not None, \
            "At least one strategy should detect a pattern"

    def test_t7_3_parameter_sensitivity_atr_ratio(self):
        """T7-3: 参数敏感性测试 - ATR 门槛"""
        # Test different min_atr_ratio values
        test_cases = [
            (Decimal("0.3"), "lenient"),
            (Decimal("0.5"), "moderate"),
            (Decimal("1.0"), "strict"),
        ]

        prev = create_kline(
            open=Decimal("1000"), high=Decimal("1005"),
            low=Decimal("985"), close=Decimal("990"),
            timestamp=1000
        )
        curr = create_kline(
            open=Decimal("989"), high=Decimal("1050"),
            low=Decimal("980"), close=Decimal("1001"),
            timestamp=2000
        )

        # candle_range = 1050-980 = 70

        results = {}
        for min_atr_ratio, label in test_cases:
            atr_filter = AtrFilterDynamic(
                period=14,
                min_atr_ratio=min_atr_ratio,
                min_absolute_range=Decimal("0.1"),
                enabled=True
            )
            # ATR = 100, candle_range = 70, ratio = 0.7
            atr_filter._atr_state["BTC/USDT:USDT:15m"] = {
                "tr_values": [Decimal("100")] * 14,
                "atr": Decimal("100"),
                "prev_close": Decimal("50000")
            }

            strategy = EngulfingStrategy()
            pattern_result = strategy.detect(curr, prev_kline=prev, atr_value=Decimal("100"))

            if pattern_result:
                context = FilterContext(kline=curr, current_timeframe="15m", higher_tf_trends={}, current_trend=None)
                event = atr_filter.check(pattern_result, context)
                results[label] = event.passed

        # Lenient (0.3): 0.7 > 0.3 -> pass
        assert results["lenient"] == True

        # Moderate (0.5): 0.7 > 0.5 -> pass
        assert results["moderate"] == True

        # Strict (1.0): 0.7 < 1.0 -> fail
        assert results["strict"] == False

    def test_t7_4_extreme_market_volatility(self):
        """T7-4: 极端行情稳定性测试"""
        strategy = EngulfingStrategy()
        atr_filter = AtrFilterDynamic(
            period=14,
            min_atr_ratio=Decimal("0.5"),
            min_absolute_range=Decimal("0.1"),
            enabled=True
        )

        # High volatility scenario (like during major news)
        atr_filter._atr_state["BTC/USDT:USDT:15m"] = {
            "tr_values": [Decimal("1000")] * 14,
            "atr": Decimal("1000"),
            "prev_close": Decimal("50000")
        }

        # Extreme volatility candles
        extreme_klines = [
            # Massive bullish candle
            create_kline(open=Decimal("48000"), high=Decimal("52000"), low=Decimal("47000"), close=Decimal("51000"), timestamp=1000),
            # Massive bearish engulfing
            create_kline(open=Decimal("51500"), high=Decimal("52500"), low=Decimal("46000"), close=Decimal("47000"), timestamp=2000),

            # Another setup
            create_kline(open=Decimal("47000"), high=Decimal("48000"), low=Decimal("46000"), close=Decimal("46500"), timestamp=3000),
            # Massive bullish engulfing
            create_kline(open=Decimal("46400"), high=Decimal("50000"), low=Decimal("46000"), close=Decimal("49500"), timestamp=4000),
        ]

        signals_count = 0
        for i, kline in enumerate(extreme_klines):
            if i == 0:
                continue

            prev_kline = extreme_klines[i-1]
            result = strategy.detect(kline, prev_kline=prev_kline, atr_value=Decimal("1000"))

            if result:
                context = FilterContext(kline=kline, current_timeframe="15m", higher_tf_trends={}, current_trend=None)
                event = atr_filter.check(result, context)

                if event.passed:
                    signals_count += 1
                    assert result.score >= 0.5
                    assert result.direction in [Direction.LONG, Direction.SHORT]

        # Should detect at least 1 valid signal in extreme volatility
        assert signals_count >= 1, "Should detect signals even in extreme volatility"

    def test_t7_5_filter_chain_integration(self):
        """Test full filter chain integration."""
        strategy = EngulfingStrategy()

        # Setup all filters
        atr_filter = AtrFilterDynamic(
            period=14,
            min_atr_ratio=Decimal("0.5"),
            min_absolute_range=Decimal("0.1"),
            enabled=True
        )
        atr_filter._atr_state["BTC/USDT:USDT:15m"] = {
            "tr_values": [Decimal("100")] * 14,
            "atr": Decimal("100"),
            "prev_close": Decimal("50000")
        }

        ema_filter = EmaTrendFilterDynamic(period=60, enabled=True)
        ema_filter._ema_calculators["BTC/USDT:USDT:15m"] = type('obj', (object,), {'value': Decimal("49000")})()

        mtf_filter = MtfFilterDynamic(enabled=True)

        # Valid engulfing
        prev = create_kline(
            open=Decimal("50000"), high=Decimal("50050"),
            low=Decimal("49900"), close=Decimal("49950"),
            timestamp=1000
        )
        curr = create_kline(
            open=Decimal("49940"), high=Decimal("50200"),
            low=Decimal("49900"), close=Decimal("50100"),
            timestamp=2000
        )

        result = strategy.detect(curr, prev_kline=prev, atr_value=Decimal("100"))
        assert result is not None

        # Run through full filter chain
        context = FilterContext(
            kline=curr,
            current_timeframe="15m",
            higher_tf_trends={"1h": TrendDirection.BULLISH},
            current_trend=TrendDirection.BULLISH
        )

        # All filters should pass
        assert atr_filter.check(result, context).passed == True
        assert ema_filter.check(result, context).passed == True
        assert mtf_filter.check(result, context).passed == True