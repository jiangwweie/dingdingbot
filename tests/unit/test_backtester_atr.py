"""
Unit tests for Backtester ATR Filter Support (Scheme C - DynamicStrategyRunner)

Tests verify that:
1. Legacy parameters are converted to StrategyDefinition with ATR filter
2. DynamicStrategyRunner is used for all backtests
3. ATR filter correctly filters low-volatility candles in backtest
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.models import (
    KlineData,
    BacktestRequest,
    StrategyDefinition,
    TriggerConfig,
    FilterConfig,
)
from src.application.backtester import Backtester


# ============================================================
# Mock Exchange Gateway
# ============================================================
class MockExchangeGateway:
    """Mock exchange gateway for backtest testing"""

    def __init__(self):
        self.call_count = 0
        self.last_limit = 0

    async def fetch_historical_ohlcv(self, symbol, timeframe, limit=100):
        """Return mock K-line data"""
        self.call_count += 1
        self.last_limit = limit

        # Generate mock candle data with sufficient volatility
        klines = []
        base_price = Decimal("50000")

        for i in range(limit):
            timestamp = 1700000000000 + (i * 900 * 1000)  # 15-min bars
            price = base_price + Decimal(str(i)) * Decimal("10")

            klines.append(KlineData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=timestamp,
                open=price,
                high=price * Decimal("1.02"),  # 2% high wick
                low=price * Decimal("0.98"),   # 2% low wick
                close=price * Decimal("1.01"), # 1% close
                volume=Decimal("1000"),
                is_closed=True,
            ))

        return klines


# ============================================================
# Test 1: Legacy to StrategyDefinition Conversion
# ============================================================
class TestLegacyToStrategyDefinition:
    """Test conversion of legacy parameters to StrategyDefinition"""

    def test_convert_legacy_includes_ema_filter(self):
        """Test that EMA trend filter is included by default"""
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            limit=100,
            trend_filter_enabled=True,
            mtf_validation_enabled=True,
        )

        from src.application.backtester import Backtester
        backtester = Backtester.__new__(Backtester)
        strategy_def = backtester._convert_legacy_to_strategy_definition(request)

        # Check filters include EMA and MTF
        filter_types = [f.type for f in strategy_def.filters]
        assert "ema_trend" in filter_types, "EMA filter should be included"
        assert "mtf" in filter_types, "MTF filter should be included"

    def test_convert_legacy_includes_atr_filter_by_default(self):
        """Test that ATR filter is always included in legacy mode (production parity)"""
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            limit=100,
            trend_filter_enabled=True,
            mtf_validation_enabled=True,
        )

        from src.application.backtester import Backtester
        backtester = Backtester.__new__(Backtester)
        strategy_def = backtester._convert_legacy_to_strategy_definition(request)

        # Check filters include ATR
        filter_types = [f.type for f in strategy_def.filters]
        assert "atr" in filter_types, "ATR filter should be included by default for production parity"

        # Verify ATR params
        atr_filter = [f for f in strategy_def.filters if f.type == "atr"][0]
        assert atr_filter.enabled == True
        assert atr_filter.params.get('min_atr_ratio') == "0.005"  # 0.5%
        assert atr_filter.params.get('period') == 14

    def test_convert_legacy_pinbar_params(self):
        """Test that pinbar params are correctly converted"""
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            limit=100,
            min_wick_ratio=Decimal("0.7"),
            max_body_ratio=Decimal("0.25"),
            body_position_tolerance=Decimal("0.15"),
        )

        backtester = Backtester.__new__(Backtester)
        strategy_def = backtester._convert_legacy_to_strategy_definition(request)

        # Check trigger params
        trigger = strategy_def.triggers[0]
        assert trigger.type == "pinbar"
        assert trigger.params["min_wick_ratio"] == "0.7"
        assert trigger.params["max_body_ratio"] == "0.25"
        assert trigger.params["body_position_tolerance"] == "0.15"

    def test_convert_legacy_default_params(self):
        """Test that default pinbar params are used when not specified"""
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            limit=100,
        )

        backtester = Backtester.__new__(Backtester)
        strategy_def = backtester._convert_legacy_to_strategy_definition(request)

        trigger = strategy_def.triggers[0]
        assert trigger.params["min_wick_ratio"] == "0.6"
        assert trigger.params["max_body_ratio"] == "0.3"
        assert trigger.params["body_position_tolerance"] == "0.1"


# ============================================================
# Test 2: Build Runner from Request
# ============================================================
class TestBuildRunnerFromRequest:
    """Test _build_runner_from_request method"""

    def test_build_runner_from_legacy_params(self):
        """Test building runner from legacy parameters"""
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            limit=100,
        )

        backtester = Backtester.__new__(Backtester)
        runner = backtester._build_runner_from_request(request)

        # Should return DynamicStrategyRunner
        from src.domain.strategy_engine import DynamicStrategyRunner
        assert isinstance(runner, DynamicStrategyRunner)

    def test_build_runner_from_strategies_field(self):
        """Test building runner from strategies field"""
        strategy_def = {
            "id": "test",
            "name": "TestStrategy",
            "triggers": [{"type": "pinbar", "enabled": True}],
            "filters": [{"type": "ema_trend", "enabled": True}],
        }

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            limit=100,
            strategies=[strategy_def],
        )

        backtester = Backtester.__new__(Backtester)
        runner = backtester._build_runner_from_request(request)

        from src.domain.strategy_engine import DynamicStrategyRunner
        assert isinstance(runner, DynamicStrategyRunner)


# ============================================================
# Test 3: ATR Filter in Dynamic Strategy
# ============================================================
class TestAtrFilterInBacktest:
    """Test ATR filter functionality in backtest context"""

    def test_atr_filter_can_be_added_to_strategy(self):
        """Test that ATR filter can be added to backtest strategy"""
        strategy_def = StrategyDefinition(
            id="test_pinbar_atr",
            name="PinbarWithATR",
            triggers=[TriggerConfig(
                type="pinbar",
                enabled=True,
                params={"min_wick_ratio": "0.6"}
            )],
            filters=[
                FilterConfig(
                    type="ema_trend",
                    enabled=True,
                    params={"period": 60}
                ),
                FilterConfig(
                    type="atr",
                    enabled=True,
                    params={
                        "period": 14,
                        "min_atr_ratio": "0.5",
                        "min_absolute_range": "0.1"
                    }
                ),
                FilterConfig(
                    type="mtf",
                    enabled=True
                ),
            ],
        )

        from src.domain.strategy_engine import create_dynamic_runner
        runner = create_dynamic_runner([strategy_def])

        from src.domain.strategy_engine import DynamicStrategyRunner
        assert isinstance(runner, DynamicStrategyRunner)

        # Verify filters were created
        for strat in runner._strategies:
            filter_names = [f.name for f in strat.filters]
            assert "ema_trend" in filter_names
            assert "atr_volatility" in filter_names
            assert "mtf" in filter_names

    def test_atr_filter_rejects_low_volatility_candle(self):
        """Test that ATR filter rejects low-volatility (cross doji) candles"""
        from src.domain.strategy_engine import create_dynamic_runner
        from src.domain.filter_factory import AtrFilterDynamic
        from decimal import Decimal

        # Create ATR filter
        atr_filter = AtrFilterDynamic(
            period=14,
            min_atr_ratio=Decimal("0.5"),
            min_absolute_range=Decimal("0.1"),
            enabled=True
        )

        # Create low-volatility candle (cross doji)
        low_vol_kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1700000000000,
            open=Decimal("50000"),
            high=Decimal("50000.05"),  # Very small range
            low=Decimal("49999.95"),
            close=Decimal("50000"),
            volume=Decimal("100"),
            is_closed=True,
        )

        # Update state (need multiple candles for ATR)
        for i in range(20):
            kline = KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1700000000000 + (i * 900 * 1000),
                open=Decimal("50000") + Decimal(str(i)),
                high=Decimal("50000.05") + Decimal(str(i)),
                low=Decimal("49999.95") + Decimal(str(i)),
                close=Decimal("50000") + Decimal(str(i)),
                volume=Decimal("100"),
                is_closed=True,
            )
            atr_filter.update_state(kline, "BTC/USDT:USDT", "15m")

        # Create mock pattern
        from src.domain.models import PatternResult, Direction
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.8,
            details={},
        )

        # Create filter context
        from src.domain.filter_factory import FilterContext
        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="15m",
            kline=low_vol_kline
        )

        # Check - should reject due to low volatility
        event = atr_filter.check(pattern, context)
        assert event.passed is False, f"Expected ATR filter to reject low volatility candle, got: {event.reason}"


# ============================================================
# Test 4: Integration Test with Mock Gateway
# ============================================================
class TestBacktesterIntegration:
    """Integration tests for backtester with ATR filter"""

    @pytest.mark.asyncio
    async def test_backtest_fetches_klines(self):
        """Test that backtest fetches K-line data correctly"""
        gateway = MockExchangeGateway()
        backtester = Backtester(gateway)

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            limit=50,
        )

        # Just test the fetch method
        klines = await backtester._fetch_klines(request)

        assert len(klines) > 0
        assert gateway.call_count >= 1

    @pytest.mark.asyncio
    async def test_backtest_builds_runner(self):
        """Test that backtest builds runner correctly"""
        gateway = MockExchangeGateway()
        backtester = Backtester(gateway)

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            limit=50,
            trend_filter_enabled=True,
            mtf_validation_enabled=True,
        )

        runner = backtester._build_runner_from_request(request)

        from src.domain.strategy_engine import DynamicStrategyRunner
        assert isinstance(runner, DynamicStrategyRunner)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
