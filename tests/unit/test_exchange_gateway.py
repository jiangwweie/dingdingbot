"""
Test Exchange Gateway - REST warmup, WebSocket subscription, asset polling.
Uses aioresponses for mocking HTTP requests.

Supports multi-exchange testing: binance, bybit, okx
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.exchange_gateway import ExchangeGateway
from src.domain.models import KlineData
from src.domain.exceptions import FatalStartupError, DataQualityWarning


# ============================================================
# Multi-Exchange Test Fixtures
# ============================================================
@pytest.fixture(params=["binance", "bybit", "okx"], ids=lambda x: f"exchange={x}")
def exchange_name(request):
    """Parametrized exchange name fixture"""
    return request.param


@pytest.fixture
def exchange_credentials():
    """Common test credentials for all exchanges"""
    return {
        "api_key": "test_key",
        "api_secret": "test_secret",
        "testnet": True,
    }


class TestExchangeGatewayInit:
    """Test ExchangeGateway initialization"""

    @pytest.fixture
    def gateway(self, exchange_name, exchange_credentials):
        """Create gateway instance for testing with parametrized exchange"""
        return ExchangeGateway(
            exchange_name=exchange_name,
            **exchange_credentials,
        )

    def test_init_with_params(self, gateway, exchange_name):
        """Test initialization with basic parameters"""
        assert gateway.exchange_name == exchange_name
        assert gateway.api_key == "test_key"
        assert gateway.testnet is True
        assert gateway._max_reconnect_attempts == 10

    def test_init_default_options(self, gateway):
        """Test that default options include swap type"""
        # REST exchange should have swap as default type
        assert gateway.rest_exchange.options.get("defaultType") == "swap"


class TestParseOhlcv:
    """Test OHLCV parsing and validation"""

    @pytest.fixture
    def gateway(self, exchange_name, exchange_credentials):
        """Create gateway instance for testing with parametrized exchange"""
        return ExchangeGateway(
            exchange_name=exchange_name,
            **exchange_credentials,
        )

    def test_parse_valid_ohlcv(self, gateway):
        """Test parsing valid OHLCV data"""
        candle = [
            1700000000000,  # timestamp
            35000.0,       # open
            35500.0,       # high
            34800.0,       # low
            35200.0,       # close
            1000.5,        # volume
        ]

        kline = gateway._parse_ohlcv(candle, "BTC/USDT:USDT", "1h")

        assert kline is not None
        assert kline.symbol == "BTC/USDT:USDT"
        assert kline.timeframe == "1h"
        assert kline.timestamp == 1700000000000
        assert kline.open == Decimal("35000.0")
        assert kline.high == Decimal("35500.0")
        assert kline.low == Decimal("34800.0")
        assert kline.close == Decimal("35200.0")
        assert kline.volume == Decimal("1000.5")
        assert kline.is_closed is True

    def test_parse_invalid_high_less_than_low(self, gateway):
        """Test rejection of invalid K-line where high < low"""
        candle = [
            1700000000000,
            35000.0,
            34000.0,  # high < low - invalid
            35500.0,
            35200.0,
            1000.0,
        ]

        with pytest.raises(DataQualityWarning) as exc_info:
            gateway._parse_ohlcv(candle, "BTC/USDT:USDT", "1h")

        assert exc_info.value.error_code == "W-001"

    def test_parse_invalid_high_below_open(self, gateway):
        """Test rejection of invalid K-line where high < open"""
        candle = [
            1700000000000,
            35000.0,
            34000.0,  # high < open - invalid
            33000.0,
            34500.0,
            1000.0,
        ]

        with pytest.raises(DataQualityWarning) as exc_info:
            gateway._parse_ohlcv(candle, "BTC/USDT:USDT", "1h")

        assert exc_info.value.error_code == "W-001"

    def test_parse_invalid_low_above_open(self, gateway):
        """Test rejection of invalid K-line where low > open"""
        candle = [
            1700000000000,
            35000.0,
            36000.0,
            35500.0,  # low > open - invalid
            35200.0,
            1000.0,
        ]

        with pytest.raises(DataQualityWarning) as exc_info:
            gateway._parse_ohlcv(candle, "BTC/USDT:USDT", "1h")

        assert exc_info.value.error_code == "W-001"

    def test_parse_malformed_candle(self, gateway):
        """Test handling of malformed candle data"""
        candle = [
            1700000000000,
            "invalid",  # Invalid price data
            35500.0,
            34800.0,
            35200.0,
            1000.0,
        ]

        result = gateway._parse_ohlcv(candle, "BTC/USDT:USDT", "1h")
        assert result is None  # Should return None for unparseable data


class TestFetchHistoricalOhlcv:
    """Test historical OHlcv fetching with mocking"""

    @pytest.fixture
    def mock_exchange_class(self):
        """Create mock exchange class"""
        mock_class = MagicMock()
        mock_instance = AsyncMock()
        mock_instance.fetch_ohlcv = AsyncMock()
        mock_instance.load_markets = AsyncMock()
        mock_instance.close = AsyncMock()
        mock_instance.symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
        mock_class.return_value = mock_instance
        return mock_class

    @pytest.fixture
    def gateway(self, exchange_name, exchange_credentials, mock_exchange_class):
        """Create gateway with mocked exchange (parametrized by exchange)"""
        with patch('src.infrastructure.exchange_gateway.ccxt_async') as mock_ccxt:
            # Setup mock for all exchanges
            mock_ccxt.binance = mock_exchange_class
            mock_ccxt.bybit = mock_exchange_class
            mock_ccxt.okx = mock_exchange_class

            gateway = ExchangeGateway(
                exchange_name=exchange_name,
                **exchange_credentials,
            )
            yield gateway

    @pytest.mark.asyncio
    async def test_fetch_historical_ohlcv(self, gateway, mock_exchange_class):
        """Test fetching historical OHLCV data"""
        # Setup mock response
        mock_data = [
            [1700000000000, 35000.0, 35500.0, 34800.0, 35200.0, 1000.0],
            [1700003600000, 35200.0, 35800.0, 35100.0, 35600.0, 1200.0],
            [1700007200000, 35600.0, 36000.0, 35400.0, 35800.0, 1100.0],
        ]
        gateway.rest_exchange.fetch_ohlcv.return_value = mock_data

        # Fetch data
        result = await gateway.fetch_historical_ohlcv(
            "BTC/USDT:USDT", "1h", limit=100
        )

        # Verify
        assert len(result) == 3
        assert all(isinstance(k, KlineData) for k in result)
        gateway.rest_exchange.fetch_ohlcv.assert_called_once_with(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            limit=100,
        )

    @pytest.mark.asyncio
    async def test_fetch_ohlcv_empty_response(self, gateway, mock_exchange_class):
        """Test handling of empty OHLCV response"""
        gateway.rest_exchange.fetch_ohlcv.return_value = []

        result = await gateway.fetch_historical_ohlcv(
            "BTC/USDT:USDT", "1h", limit=100
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_ohlcv_error(self, gateway, mock_exchange_class):
        """Test handling of fetch error"""
        gateway.rest_exchange.fetch_ohlcv.side_effect = Exception("Connection error")

        with pytest.raises(Exception):
            await gateway.fetch_historical_ohlcv("BTC/USDT:USDT", "1h")


class TestAssetPolling:
    """Test asset polling functionality"""

    @pytest.fixture
    def gateway(self, exchange_name, exchange_credentials):
        """Create gateway instance with parametrized exchange"""
        return ExchangeGateway(
            exchange_name=exchange_name,
            **exchange_credentials,
        )

    @pytest.mark.asyncio
    async def test_get_account_snapshot_initial(self, gateway):
        """Test that initial snapshot is None"""
        snapshot = gateway.get_account_snapshot()
        assert snapshot is None

    @pytest.mark.asyncio
    async def test_start_asset_polling_creates_task(self, gateway):
        """Test that start_asset_polling creates background task"""
        gateway._ws_running = True  # Mock running state

        await gateway.start_asset_polling(interval_seconds=60)

        assert gateway._asset_polling_task is not None
        assert not gateway._asset_polling_task.done()

        # Cleanup
        gateway._asset_polling_task.cancel()
        try:
            await gateway._asset_polling_task
        except asyncio.CancelledError:
            pass


class TestReconnectionLogic:
    """Test WebSocket reconnection logic"""

    def test_reconnect_delay_calculation(self, exchange_name, exchange_credentials):
        """Test exponential backoff delay calculation"""
        gateway = ExchangeGateway(
            exchange_name=exchange_name,
            **exchange_credentials,
        )

        # Initial delay
        gateway._reconnect_count = 1
        delay_1 = min(
            gateway._initial_reconnect_delay * (2 ** (gateway._reconnect_count - 1)),
            gateway._max_reconnect_delay,
        )
        assert delay_1 == 1.0

        # After 3 attempts
        gateway._reconnect_count = 3
        delay_3 = min(
            gateway._initial_reconnect_delay * (2 ** (gateway._reconnect_count - 1)),
            gateway._max_reconnect_delay,
        )
        assert delay_3 == 4.0

        # Should cap at max
        gateway._reconnect_count = 10
        delay_10 = min(
            gateway._initial_reconnect_delay * (2 ** (gateway._reconnect_count - 1)),
            gateway._max_reconnect_delay,
        )
        assert delay_10 == 60.0  # Capped at max_reconnect_delay


# ============================================================
# Additional Unit Tests for Previously Untested Methods
# ============================================================

class TestIsCandleClosed:
    """Test _is_candle_closed method - candle close detection"""

    @pytest.fixture
    def gateway(self, exchange_name, exchange_credentials):
        """Create gateway instance for testing"""
        return ExchangeGateway(
            exchange_name=exchange_name,
            **exchange_credentials,
        )

    def test_first_candle_not_closed(self, gateway):
        """Test that first candle for a symbol/timeframe is not marked as closed"""
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("35000"),
            high=Decimal("35500"),
            low=Decimal("34800"),
            close=Decimal("35200"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        result = gateway._is_candle_closed(kline, "BTC/USDT:USDT", "1h")
        assert result is False  # First candle, not closed

    def test_same_timestamp_not_closed(self, gateway):
        """Test that same timestamp means candle not yet closed"""
        # First candle
        kline1 = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("35000"),
            high=Decimal("35500"),
            low=Decimal("34800"),
            close=Decimal("35200"),
            volume=Decimal("1000"),
            is_closed=True,
        )
        gateway._is_candle_closed(kline1, "BTC/USDT:USDT", "1h")

        # Same timestamp
        kline2 = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,  # Same timestamp
            open=Decimal("35200"),
            high=Decimal("35600"),
            low=Decimal("35100"),
            close=Decimal("35400"),
            volume=Decimal("1100"),
            is_closed=True,
        )

        result = gateway._is_candle_closed(kline2, "BTC/USDT:USDT", "1h")
        assert result is False  # Still same candle, not closed

    def test_new_timestamp_candle_closed(self, gateway):
        """Test that new timestamp means previous candle closed"""
        # First candle
        kline1 = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("35000"),
            high=Decimal("35500"),
            low=Decimal("34800"),
            close=Decimal("35200"),
            volume=Decimal("1000"),
            is_closed=True,
        )
        gateway._is_candle_closed(kline1, "BTC/USDT:USDT", "1h")

        # New candle
        kline2 = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700003600000,  # +1 hour
            open=Decimal("35200"),
            high=Decimal("35600"),
            low=Decimal("35100"),
            close=Decimal("35400"),
            volume=Decimal("1100"),
            is_closed=True,
        )

        result = gateway._is_candle_closed(kline2, "BTC/USDT:USDT", "1h")
        assert result is True  # New candle, previous closed

    def test_multiple_symbols_independent(self, gateway):
        """Test that different symbols track independently"""
        # BTC first candle
        kline_btc1 = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("35000"),
            high=Decimal("35500"),
            low=Decimal("34800"),
            close=Decimal("35200"),
            volume=Decimal("1000"),
            is_closed=True,
        )
        gateway._is_candle_closed(kline_btc1, "BTC/USDT:USDT", "1h")

        # ETH new candle (should not affect BTC tracking)
        kline_eth1 = KlineData(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("2000"),
            high=Decimal("2050"),
            low=Decimal("1980"),
            close=Decimal("2020"),
            volume=Decimal("5000"),
            is_closed=True,
        )
        result_eth = gateway._is_candle_closed(kline_eth1, "ETH/USDT:USDT", "1h")
        assert result_eth is False  # First ETH candle

    def test_multiple_timeframes_independent(self, gateway):
        """Test that different timeframes track independently"""
        # 1h first candle
        kline_1h = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("35000"),
            high=Decimal("35500"),
            low=Decimal("34800"),
            close=Decimal("35200"),
            volume=Decimal("1000"),
            is_closed=True,
        )
        gateway._is_candle_closed(kline_1h, "BTC/USDT:USDT", "1h")

        # 4h candle (should not affect 1h tracking)
        kline_4h = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="4h",
            timestamp=1700000000000,
            open=Decimal("35000"),
            high=Decimal("35500"),
            low=Decimal("34800"),
            close=Decimal("35200"),
            volume=Decimal("1000"),
            is_closed=True,
        )
        result_4h = gateway._is_candle_closed(kline_4h, "BTC/USDT:USDT", "4h")
        assert result_4h is False  # First 4h candle


class TestParseWsBalance:
    """Test _parse_ws_balance method - WebSocket balance parsing"""

    @pytest.fixture
    def gateway(self, exchange_name, exchange_credentials):
        """Create gateway instance for testing"""
        return ExchangeGateway(
            exchange_name=exchange_name,
            **exchange_credentials,
        )

    def test_parse_balance_with_usdt(self, gateway):
        """Test parsing balance with USDT data"""
        balance = {
            "total": {"USDT": 10000.5},
            "free": {"USDT": 8000.25},
        }

        snapshot = gateway._parse_ws_balance(balance)

        assert snapshot.total_balance == Decimal("10000.5")
        assert snapshot.available_balance == Decimal("8000.25")
        assert snapshot.unrealized_pnl == Decimal("0")
        assert snapshot.positions == []
        assert isinstance(snapshot.timestamp, int)

    def test_parse_balance_empty(self, gateway):
        """Test parsing empty balance"""
        balance = {
            "total": {},
            "free": {},
        }

        snapshot = gateway._parse_ws_balance(balance)

        assert snapshot.total_balance == Decimal("0")
        assert snapshot.available_balance == Decimal("0")
        assert snapshot.unrealized_pnl == Decimal("0")
        assert snapshot.positions == []

    def test_parse_balance_missing_usdt(self, gateway):
        """Test parsing balance without USDT"""
        balance = {
            "total": {"BTC": 0.5, "ETH": 10},
            "free": {"BTC": 0.3, "ETH": 5},
        }

        snapshot = gateway._parse_ws_balance(balance)

        assert snapshot.total_balance == Decimal("0")
        assert snapshot.available_balance == Decimal("0")

    def test_parse_balance_partial(self, gateway):
        """Test parsing balance with only total or free"""
        # Only total
        balance_total = {"total": {"USDT": 10000}}
        snapshot_total = gateway._parse_ws_balance(balance_total)
        assert snapshot_total.total_balance == Decimal("10000")
        assert snapshot_total.available_balance == Decimal("0")

        # Only free
        balance_free = {"free": {"USDT": 8000}}
        snapshot_free = gateway._parse_ws_balance(balance_free)
        assert snapshot_free.total_balance == Decimal("0")
        assert snapshot_free.available_balance == Decimal("8000")
