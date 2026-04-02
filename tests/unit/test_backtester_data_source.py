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
