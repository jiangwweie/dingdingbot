"""
Unit tests for Backtester data source switching.

Tests verify:
1. Backtester uses data repository when available
2. Fallback to gateway when repository not provided
3. Time range fetching
4. Timeframe parsing
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.backtester import Backtester
from src.domain.models import KlineData, BacktestRequest
from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.infrastructure.exchange_gateway import ExchangeGateway


# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
def sample_klines():
    """Sample K-line data for backtesting"""
    return [
        KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1704067200000,
            open=Decimal("42000.00"),
            high=Decimal("42500.00"),
            low=Decimal("41800.00"),
            close=Decimal("42300.00"),
            volume=Decimal("1000.0"),
            is_closed=True,
        ),
        KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1704068100000,
            open=Decimal("42300.00"),
            high=Decimal("42800.00"),
            low=Decimal("42200.00"),
            close=Decimal("42600.00"),
            volume=Decimal("1200.0"),
            is_closed=True,
        ),
        KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1704069000000,
            open=Decimal("42600.00"),
            high=Decimal("43000.00"),
            low=Decimal("42500.00"),
            close=Decimal("42900.00"),
            volume=Decimal("1500.0"),
            is_closed=True,
        ),
    ]


@pytest.fixture
def mock_exchange_gateway():
    """Mock exchange gateway"""
    gateway = MagicMock(spec=ExchangeGateway)
    gateway.fetch_historical_ohlcv = AsyncMock(return_value=[])
    return gateway


@pytest.fixture
def mock_data_repository():
    """Mock data repository"""
    repo = MagicMock(spec=HistoricalDataRepository)
    repo.get_klines = AsyncMock(return_value=[])
    repo.get_klines_aligned = AsyncMock(return_value=([], {}))
    return repo


# ============================================================
# Test Data Source Selection
# ============================================================

@pytest.mark.asyncio
class TestDataSourceSelection:
    """Tests for data source selection"""

    async def test_backtester_uses_data_repository(self, mock_exchange_gateway, mock_data_repository, sample_klines):
        """Test 16: 使用数据仓库获取数据"""
        # Arrange: Configure mock repository to return data
        mock_data_repository.get_klines = AsyncMock(return_value=sample_klines)

        backtester = Backtester(
            exchange_gateway=mock_exchange_gateway,
            data_repository=mock_data_repository,
        )

        # Create backtest request
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            limit=100,
        )

        # Mock _fetch_klines to test data source selection
        with patch.object(backtester, '_fetch_klines', wraps=backtester._fetch_klines) as mock_fetch:
            try:
                await backtester.run_backtest(request)
            except Exception:
                # Ignore other errors, we just want to verify data source was used
                pass

            # Assert: Repository should be called
            mock_data_repository.get_klines.assert_called()

    async def test_backtester_fallback_to_gateway(self, mock_exchange_gateway, sample_klines):
        """Test 17: 降级到网关"""
        # Arrange: No data repository, only gateway
        mock_exchange_gateway.fetch_historical_ohlcv = AsyncMock(return_value=sample_klines)

        backtester = Backtester(
            exchange_gateway=mock_exchange_gateway,
            data_repository=None,  # No repository
        )

        # Create backtest request
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            limit=100,
        )

        try:
            await backtester.run_backtest(request)
        except Exception:
            # Ignore other errors
            pass

        # Assert: Gateway should be called
        mock_exchange_gateway.fetch_historical_ohlcv.assert_called()


# ============================================================
# Test Time Range Fetching
# ============================================================

@pytest.mark.asyncio
class TestTimeRangeFetching:
    """Tests for time range fetching"""

    async def test_fetch_klines_with_time_range(self, mock_exchange_gateway, mock_data_repository):
        """Test 18: 按时间范围获取"""
        # Arrange: Setup mock data repository
        sample_klines = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1704067200000,
                open=Decimal("42000.00"),
                high=Decimal("42500.00"),
                low=Decimal("41800.00"),
                close=Decimal("42300.00"),
                volume=Decimal("1000.0"),
                is_closed=True,
            ),
        ]
        mock_data_repository.get_klines = AsyncMock(return_value=sample_klines)

        backtester = Backtester(
            exchange_gateway=mock_exchange_gateway,
            data_repository=mock_data_repository,
        )

        # Create request with time range
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            start_time=1704067200000,
            end_time=1704070800000,
            limit=100,
        )

        try:
            await backtester.run_backtest(request)
        except Exception:
            pass

        # Assert: Repository called with correct time range
        mock_data_repository.get_klines.assert_called()
        call_args = mock_data_repository.get_klines.call_args
        assert call_args.kwargs.get('start_time') == 1704067200000
        assert call_args.kwargs.get('end_time') == 1704070800000

    async def test_fetch_klines_default_limit(self, mock_exchange_gateway, mock_data_repository):
        """Test: 默认限制数量"""
        sample_klines = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1704067200000,
                open=Decimal("42000.00"),
                high=Decimal("42500.00"),
                low=Decimal("41800.00"),
                close=Decimal("42300.00"),
                volume=Decimal("1000.0"),
                is_closed=True,
            ),
        ]
        mock_data_repository.get_klines = AsyncMock(return_value=sample_klines)

        backtester = Backtester(
            exchange_gateway=mock_exchange_gateway,
            data_repository=mock_data_repository,
        )

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
        )

        try:
            await backtester.run_backtest(request)
        except Exception:
            pass

        # Assert: Default limit should be 100
        call_args = mock_data_repository.get_klines.call_args
        assert call_args.kwargs.get('limit') == 100


# ============================================================
# Test Timeframe Parsing
# ============================================================

@pytest.mark.asyncio
class TestTimeframeParsing:
    """Tests for timeframe parsing"""

    async def test_fetch_klines_parses_timeframe(self, mock_exchange_gateway, mock_data_repository):
        """Test 19: 解析时间周期"""
        sample_klines = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="1h",
                timestamp=1704067200000,
                open=Decimal("42000.00"),
                high=Decimal("42500.00"),
                low=Decimal("41800.00"),
                close=Decimal("42300.00"),
                volume=Decimal("1000.0"),
                is_closed=True,
            ),
        ]
        mock_data_repository.get_klines = AsyncMock(return_value=sample_klines)

        backtester = Backtester(
            exchange_gateway=mock_exchange_gateway,
            data_repository=mock_data_repository,
        )

        # Test different timeframes
        for tf in ["15m", "1h", "4h", "1d"]:
            request = BacktestRequest(
                symbol="BTC/USDT:USDT",
                timeframe=tf,
            )

            try:
                await backtester.run_backtest(request)
            except Exception:
                pass

            # Assert: Timeframe passed correctly
            call_args = mock_data_repository.get_klines.call_args
            assert call_args.kwargs.get('timeframe') == tf

    async def test_backtest_mtf_mapping(self, mock_exchange_gateway, mock_data_repository):
        """Test: MTF 映射正确"""
        # Arrange: Verify MTF_MAPPING in Backtester
        assert Backtester.MTF_MAPPING["15m"] == "1h"
        assert Backtester.MTF_MAPPING["1h"] == "4h"
        assert Backtester.MTF_MAPPING["4h"] == "1d"
        assert Backtester.MTF_MAPPING["1d"] == "1w"


# ============================================================
# Test Empty Data Handling
# ============================================================

@pytest.mark.asyncio
class TestEmptyDataHandling:
    """Tests for empty data handling"""

    async def test_backtest_empty_data_raises_error(self, mock_exchange_gateway, mock_data_repository):
        """Test: 空数据抛出错误"""
        # Arrange: Return empty data
        mock_data_repository.get_klines = AsyncMock(return_value=[])

        backtester = Backtester(
            exchange_gateway=mock_exchange_gateway,
            data_repository=mock_data_repository,
        )

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
        )

        # Act & Assert: Should raise ValueError
        with pytest.raises(ValueError, match="No K-line data fetched"):
            await backtester.run_backtest(request)


# ============================================================
# Test Legacy Mode
# ============================================================

@pytest.mark.asyncio
class TestLegacyMode:
    """Tests for legacy backtest mode"""

    async def test_backtest_legacy_mode(self, mock_exchange_gateway, mock_data_repository):
        """Test: 传统回测模式"""
        sample_klines = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1704067200000,
                open=Decimal("42000.00"),
                high=Decimal("42500.00"),
                low=Decimal("41800.00"),
                close=Decimal("42300.00"),
                volume=Decimal("1000.0"),
                is_closed=True,
            ),
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1704068100000,
                open=Decimal("42300.00"),
                high=Decimal("42800.00"),
                low=Decimal("42200.00"),
                close=Decimal("42600.00"),
                volume=Decimal("1200.0"),
                is_closed=True,
            ),
        ]
        mock_data_repository.get_klines = AsyncMock(return_value=sample_klines)

        backtester = Backtester(
            exchange_gateway=mock_exchange_gateway,
            data_repository=mock_data_repository,
        )

        # Legacy mode request
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            min_wick_ratio=Decimal("0.6"),
            trend_filter_enabled=True,
            mtf_validation_enabled=False,
        )

        try:
            report = await backtester.run_backtest(request)
        except Exception:
            pass

    async def test_backtest_v3_pms_mode(self, mock_exchange_gateway, mock_data_repository):
        """Test: v3 PMS 回测模式"""
        sample_klines = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1704067200000,
                open=Decimal("42000.00"),
                high=Decimal("42500.00"),
                low=Decimal("41800.00"),
                close=Decimal("42300.00"),
                volume=Decimal("1000.0"),
                is_closed=True,
            ),
        ]
        mock_data_repository.get_klines = AsyncMock(return_value=sample_klines)

        backtester = Backtester(
            exchange_gateway=mock_exchange_gateway,
            data_repository=mock_data_repository,
        )

        # v3 PMS mode request
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            mode="v3_pms",
            initial_balance=Decimal("10000"),
        )

        try:
            report = await backtester.run_backtest(request)
        except Exception:
            pass


# ============================================================
# Test Dynamic Strategy Mode
# ============================================================

@pytest.mark.asyncio
class TestDynamicStrategyMode:
    """Tests for dynamic strategy backtest mode"""

    async def test_backtest_dynamic_strategy(self, mock_exchange_gateway, mock_data_repository):
        """Test: 动态策略回测模式"""
        sample_klines = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1704067200000,
                open=Decimal("42000.00"),
                high=Decimal("42500.00"),
                low=Decimal("41800.00"),
                close=Decimal("42300.00"),
                volume=Decimal("1000.0"),
                is_closed=True,
            ),
        ]
        mock_data_repository.get_klines = AsyncMock(return_value=sample_klines)

        backtester = Backtester(
            exchange_gateway=mock_exchange_gateway,
            data_repository=mock_data_repository,
        )

        # Dynamic strategy mode request
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            strategies=[
                {
                    "id": "pinbar_v1",
                    "name": "Pinbar",
                    "triggers": [
                        {"type": "pinbar", "params": {"min_wick_ratio": 0.6}}
                    ],
                    "filters": [
                        {"type": "ema_trend", "params": {"enabled": True}}
                    ],
                }
            ],
        )

        try:
            report = await backtester.run_backtest(request)
        except Exception:
            pass


# ============================================================
# Test Repository Methods Directly
# ============================================================

@pytest.mark.asyncio
class TestBacktesterInternalMethods:
    """Tests for backtester internal methods"""

    async def test_build_strategy_config(self, mock_exchange_gateway):
        """Test: 构建策略配置"""
        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            min_wick_ratio=Decimal("0.7"),
            trend_filter_enabled=True,
            mtf_validation_enabled=False,
        )

        config = backtester._build_strategy_config(request)

        assert config.pinbar_config.min_wick_ratio == Decimal("0.7")
        assert config.trend_filter_enabled == True
        assert config.mtf_validation_enabled == False

    async def test_build_dynamic_runner(self, mock_exchange_gateway):
        """Test: 构建动态策略运行器"""
        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        strategies = [
            {
                "id": "test_strat",
                "name": "TestStrategy",
                "triggers": [
                    {"type": "pinbar", "params": {"min_wick_ratio": 0.6}}
                ],
            }
        ]

        runner = backtester._build_dynamic_runner(strategies)

        assert runner is not None


# ============================================================
# Task 5: _attempt_to_dict extension tests (BT-4 Attribution)
# ============================================================
class TestAttemptToDictExtension:
    """Tests for _attempt_to_dict BT-4 attribution fields."""

    def test_attempt_to_dict_includes_pnl_exit(self, mock_exchange_gateway):
        """
        Test: _attempt_to_dict 包含 pnl_ratio 和 exit_reason 字段

        验收标准：
        - 返回的字典包含 pnl_ratio 键
        - 返回的字典包含 exit_reason 键
        - filter_results 包含 metadata 字段
        """
        from src.application.backtester import Backtester
        from src.domain.models import SignalAttempt, PatternResult, FilterResult, Direction

        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        # Create a SignalAttempt with SIGNAL_FIRED result
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.85,
            details={"wick_ratio": 0.7},
        )

        filter_results = [
            ("ema_trend", FilterResult(passed=True, reason="trend_match", metadata={"trend": "bullish"})),
            ("mtf", FilterResult(passed=True, reason="mtf_confirmed", metadata={"higher_timeframe": "1h"})),
        ]

        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=pattern,
            filter_results=filter_results,
            final_result="SIGNAL_FIRED",
            kline_timestamp=1711785600000,
            _pnl_ratio=2.0,  # 2R gain
            _exit_reason="TAKE_PROFIT",
        )

        # Convert to dict
        result = backtester._attempt_to_dict(attempt)

        # Assertions - BT-4 attribution fields
        assert "pnl_ratio" in result
        assert "exit_reason" in result
        assert result["pnl_ratio"] == 2.0
        assert result["exit_reason"] == "TAKE_PROFIT"

        # Verify filter_results metadata is included
        assert len(result["filter_results"]) == 2
        assert "metadata" in result["filter_results"][0]
        assert result["filter_results"][0]["metadata"] == {"trend": "bullish"}

    def test_attempt_to_dict_no_pattern(self, mock_exchange_gateway):
        """
        Test: _attempt_to_dict for NO_PATTERN result

        预期：pnl_ratio 和 exit_reason 为 None
        """
        from src.application.backtester import Backtester
        from src.domain.models import SignalAttempt

        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=None,  # No pattern detected
            filter_results=[],
            final_result="NO_PATTERN",
            kline_timestamp=1711785600000,
        )

        result = backtester._attempt_to_dict(attempt)

        # Assertions
        assert result["final_result"] == "NO_PATTERN"
        assert result["pnl_ratio"] is None
        assert result["exit_reason"] is None
        assert result["pattern_score"] is None

    def test_attempt_to_dict_filtered_out(self, mock_exchange_gateway):
        """
        Test: _attempt_to_dict for FILTERED result

        预期：pnl_ratio 和 exit_reason 为 None
        """
        from src.application.backtester import Backtester
        from src.domain.models import SignalAttempt, PatternResult, FilterResult, Direction

        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.75,
            details={},
        )

        filter_results = [
            ("ema_trend", FilterResult(passed=False, reason="bearish_trend_blocks_long", metadata={})),
        ]

        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=pattern,
            filter_results=filter_results,
            final_result="FILTERED",
            kline_timestamp=1711785600000,
        )

        result = backtester._attempt_to_dict(attempt)

        # Assertions
        assert result["final_result"] == "FILTERED"
        assert result["pnl_ratio"] is None
        assert result["exit_reason"] is None
        assert len(result["filter_results"]) == 1
        assert result["filter_results"][0]["passed"] is False

    def test_attempt_to_dict_metadata_standardization(self, mock_exchange_gateway):
        """
        Test: filter_results metadata is standardized dict (never None)

        验收标准：
        - 所有 filter_results 的 metadata 字段都是 dict 类型
        - metadata 永远不会为 None
        """
        from src.application.backtester import Backtester
        from src.domain.models import SignalAttempt, PatternResult, FilterResult, Direction

        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.8,
            details={},
        )

        # Test with metadata=None (edge case - should be handled)
        filter_results = [
            ("ema_trend", FilterResult(passed=True, reason="trend_match", metadata=None)),
        ]

        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=pattern,
            filter_results=filter_results,
            final_result="SIGNAL_FIRED",
            kline_timestamp=1711785600000,
        )

        result = backtester._attempt_to_dict(attempt)

        # Metadata should be serialized (even if None in FilterResult)
        # Note: FilterResult.__post_init__ converts None to {}
        assert isinstance(result["filter_results"][0]["metadata"], dict)

    def test_attempt_to_dict_exit_reasons(self, mock_exchange_gateway):
        """
        Test: Various exit_reason values

        预期：exit_reason 可以是以下值之一:
        - "TAKE_PROFIT" (止盈出场)
        - "STOP_LOSS" (止损出场)
        - "TIME_EXIT" (时间出场)
        - None (未出场)
        """
        from src.application.backtester import Backtester
        from src.domain.models import SignalAttempt, PatternResult, Direction

        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.8,
            details={},
        )

        # Test different exit reasons
        exit_reasons = ["TAKE_PROFIT", "STOP_LOSS", "TIME_EXIT", None]

        for expected_reason in exit_reasons:
            attempt = SignalAttempt(
                strategy_name="pinbar",
                pattern=pattern,
                filter_results=[],
                final_result="SIGNAL_FIRED",
                kline_timestamp=1711785600000,
                _pnl_ratio=2.0 if expected_reason == "TAKE_PROFIT" else (-1.0 if expected_reason == "STOP_LOSS" else 0.0),
                _exit_reason=expected_reason,
            )

            result = backtester._attempt_to_dict(attempt)

            assert result["exit_reason"] == expected_reason
            if expected_reason == "TAKE_PROFIT":
                assert result["pnl_ratio"] == 2.0
            elif expected_reason == "STOP_LOSS":
                assert result["pnl_ratio"] == -1.0
            elif expected_reason == "TIME_EXIT":
                assert result["pnl_ratio"] == 0.0
