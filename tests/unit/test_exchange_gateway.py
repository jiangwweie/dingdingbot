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
from src.domain.models import KlineData, OrderPlacementResult, OrderCancelResult, OrderStatus, OrderType
from src.domain.exceptions import FatalStartupError, DataQualityWarning, InsufficientMarginError, InvalidOrderError, OrderNotFoundError, OrderAlreadyFilledError, RateLimitError, ConnectionLostError


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


# ============================================================
# Phase 5: Order Management Tests
# ============================================================

class TestOrderPlacement:
    """Test place_order method"""

    @pytest.fixture
    def mock_exchange_class(self):
        """Create mock exchange class for order tests"""
        mock_class = MagicMock()
        mock_instance = AsyncMock()
        mock_instance.create_order = AsyncMock()
        mock_instance.fetch_order = AsyncMock()
        mock_instance.cancel_order = AsyncMock()
        mock_instance.fetch_ticker = AsyncMock()
        mock_instance.load_markets = AsyncMock()
        mock_instance.close = AsyncMock()
        mock_instance.symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
        mock_instance.options = {"defaultType": "swap"}
        mock_class.return_value = mock_instance
        return mock_class

    @pytest.fixture
    def gateway(self, exchange_name, exchange_credentials, mock_exchange_class):
        """Create gateway with mocked exchange for order tests"""
        with patch('src.infrastructure.exchange_gateway.ccxt_async') as mock_ccxt:
            mock_ccxt.binance = mock_exchange_class
            mock_ccxt.bybit = mock_exchange_class
            mock_ccxt.okx = mock_exchange_class

            gateway = ExchangeGateway(
                exchange_name=exchange_name,
                **exchange_credentials,
            )
            yield gateway

    @pytest.mark.asyncio
    async def test_place_market_order_success(self, gateway, mock_exchange_class):
        """Test placing a successful market order"""
        # Mock create_order response
        gateway.rest_exchange.create_order.return_value = {
            'id': '12345',
            'symbol': 'BTC/USDT:USDT',
            'type': 'market',
            'side': 'buy',
            'amount': 0.1,
            'status': 'open',
        }

        result = await gateway.place_order(
            symbol="BTC/USDT:USDT",
            order_type="market",
            side="buy",
            amount=Decimal("0.1"),
        )

        assert result.is_success is True
        assert result.exchange_order_id == '12345'
        assert result.symbol == "BTC/USDT:USDT"
        assert result.order_type == OrderType.MARKET
        assert result.amount == Decimal("0.1")
        assert result.reduce_only is False

    @pytest.mark.asyncio
    async def test_place_limit_order_success(self, gateway, mock_exchange_class):
        """Test placing a successful limit order"""
        gateway.rest_exchange.create_order.return_value = {
            'id': '12346',
            'symbol': 'BTC/USDT:USDT',
            'type': 'limit',
            'side': 'sell',
            'amount': 0.2,
            'price': 35000.0,
            'status': 'open',
        }

        result = await gateway.place_order(
            symbol="BTC/USDT:USDT",
            order_type="limit",
            side="sell",
            amount=Decimal("0.2"),
            price=Decimal("35000"),
        )

        assert result.is_success is True
        assert result.exchange_order_id == '12346'
        assert result.order_type == OrderType.LIMIT
        assert result.price == Decimal("35000")

    @pytest.mark.asyncio
    async def test_place_stop_market_order_success(self, gateway, mock_exchange_class):
        """Test placing a successful stop market order"""
        gateway.rest_exchange.create_order.return_value = {
            'id': '12347',
            'symbol': 'BTC/USDT:USDT',
            'type': 'stop',
            'side': 'buy',
            'amount': 0.1,
            'status': 'open',
        }

        result = await gateway.place_order(
            symbol="BTC/USDT:USDT",
            order_type="stop_market",
            side="buy",
            amount=Decimal("0.1"),
            trigger_price=Decimal("36000"),
        )

        assert result.is_success is True
        assert result.order_type == OrderType.STOP_MARKET
        assert result.trigger_price == Decimal("36000")

    @pytest.mark.asyncio
    async def test_place_order_with_reduce_only(self, gateway, mock_exchange_class):
        """Test placing order with reduce_only flag"""
        gateway.rest_exchange.create_order.return_value = {
            'id': '12348',
            'symbol': 'BTC/USDT:USDT',
            'type': 'market',
            'side': 'sell',
            'amount': 0.1,
            'status': 'open',
        }

        result = await gateway.place_order(
            symbol="BTC/USDT:USDT",
            order_type="market",
            side="sell",
            amount=Decimal("0.1"),
            reduce_only=True,
        )

        assert result.is_success is True
        assert result.reduce_only is True
        # Verify reduceOnly was passed to CCXT
        gateway.rest_exchange.create_order.assert_called_once()
        call_params = gateway.rest_exchange.create_order.call_args
        assert call_params[1]['params']['reduceOnly'] is True

    @pytest.mark.asyncio
    async def test_place_order_with_client_order_id(self, gateway, mock_exchange_class):
        """Test placing order with client order ID"""
        gateway.rest_exchange.create_order.return_value = {
            'id': '12349',
            'symbol': 'BTC/USDT:USDT',
            'type': 'market',
            'side': 'buy',
            'amount': 0.1,
            'status': 'open',
        }

        result = await gateway.place_order(
            symbol="BTC/USDT:USDT",
            order_type="market",
            side="buy",
            amount=Decimal("0.1"),
            client_order_id="my_custom_order_001",
        )

        assert result.is_success is True
        assert result.client_order_id == "my_custom_order_001"
        # Verify clientOrderId was passed to CCXT
        call_params = gateway.rest_exchange.create_order.call_args
        assert call_params[1]['params']['clientOrderId'] == "my_custom_order_001"

    @pytest.mark.asyncio
    async def test_place_limit_order_missing_price_raises_error(self, gateway, mock_exchange_class):
        """Test that LIMIT order without price raises InvalidOrderError"""
        with pytest.raises(InvalidOrderError) as exc_info:
            await gateway.place_order(
                symbol="BTC/USDT:USDT",
                order_type="limit",
                side="buy",
                amount=Decimal("0.1"),
            )
        assert exc_info.value.error_code == "F-011"

    @pytest.mark.asyncio
    async def test_place_stop_market_order_missing_trigger_price_raises_error(self, gateway, mock_exchange_class):
        """Test that STOP_MARKET order without trigger_price raises InvalidOrderError"""
        with pytest.raises(InvalidOrderError) as exc_info:
            await gateway.place_order(
                symbol="BTC/USDT:USDT",
                order_type="stop_market",
                side="buy",
                amount=Decimal("0.1"),
            )
        assert exc_info.value.error_code == "F-011"

    @pytest.mark.asyncio
    async def test_place_order_insufficient_margin_raises_error(self, gateway, mock_exchange_class):
        """Test that insufficient margin raises InsufficientMarginError"""
        import ccxt
        gateway.rest_exchange.create_order.side_effect = ccxt.InsufficientFunds("Insufficient funds")

        with pytest.raises(InsufficientMarginError) as exc_info:
            await gateway.place_order(
                symbol="BTC/USDT:USDT",
                order_type="market",
                side="buy",
                amount=Decimal("0.1"),
            )
        assert exc_info.value.error_code == "F-010"

    @pytest.mark.asyncio
    async def test_place_order_invalid_order_raises_error(self, gateway, mock_exchange_class):
        """Test that invalid order parameters raise InvalidOrderError"""
        import ccxt
        gateway.rest_exchange.create_order.side_effect = ccxt.InvalidOrder("Invalid price")

        with pytest.raises(InvalidOrderError) as exc_info:
            await gateway.place_order(
                symbol="BTC/USDT:USDT",
                order_type="limit",
                side="buy",
                amount=Decimal("0.1"),
                price=Decimal("35000"),
            )
        assert exc_info.value.error_code == "F-011"

    @pytest.mark.asyncio
    async def test_place_order_rate_limit_raises_error(self, gateway, mock_exchange_class):
        """Test that rate limit raises RateLimitError"""
        import ccxt
        gateway.rest_exchange.create_order.side_effect = ccxt.DDoSProtection("Rate limit exceeded")

        with pytest.raises(RateLimitError) as exc_info:
            await gateway.place_order(
                symbol="BTC/USDT:USDT",
                order_type="market",
                side="buy",
                amount=Decimal("0.1"),
            )
        assert exc_info.value.error_code == "C-010"


class TestOrderCancellation:
    """Test cancel_order method"""

    @pytest.fixture
    def mock_exchange_class(self):
        """Create mock exchange class for cancel tests"""
        mock_class = MagicMock()
        mock_instance = AsyncMock()
        mock_instance.cancel_order = AsyncMock()
        mock_instance.load_markets = AsyncMock()
        mock_instance.close = AsyncMock()
        mock_instance.options = {"defaultType": "swap"}
        mock_class.return_value = mock_instance
        return mock_class

    @pytest.fixture
    def gateway(self, exchange_name, exchange_credentials, mock_exchange_class):
        """Create gateway with mocked exchange for cancel tests"""
        with patch('src.infrastructure.exchange_gateway.ccxt_async') as mock_ccxt:
            mock_ccxt.binance = mock_exchange_class
            mock_ccxt.bybit = mock_exchange_class
            mock_ccxt.okx = mock_exchange_class

            gateway = ExchangeGateway(
                exchange_name=exchange_name,
                **exchange_credentials,
            )
            yield gateway

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, gateway, mock_exchange_class):
        """Test successful order cancellation"""
        gateway.rest_exchange.cancel_order.return_value = {
            'id': '12345',
            'symbol': 'BTC/USDT:USDT',
            'status': 'canceled',
        }

        result = await gateway.cancel_order("12345", "BTC/USDT:USDT")

        assert result.is_success is True
        assert result.order_id == "12345"
        assert result.status == OrderStatus.CANCELED

    @pytest.mark.asyncio
    async def test_cancel_order_not_found_raises_error(self, gateway, mock_exchange_class):
        """Test that canceling non-existent order raises OrderNotFoundError"""
        import ccxt
        gateway.rest_exchange.cancel_order.side_effect = ccxt.OrderNotFound("Order not found")

        with pytest.raises(OrderNotFoundError) as exc_info:
            await gateway.cancel_order("nonexistent", "BTC/USDT:USDT")
        assert exc_info.value.error_code == "F-012"

    @pytest.mark.asyncio
    async def test_cancel_order_already_filled_raises_error(self, gateway, mock_exchange_class):
        """Test that canceling filled order raises OrderAlreadyFilledError"""
        import ccxt
        gateway.rest_exchange.cancel_order.side_effect = ccxt.OrderNotFillable("Order already filled")

        with pytest.raises(OrderAlreadyFilledError) as exc_info:
            await gateway.cancel_order("filled_order", "BTC/USDT:USDT")
        assert exc_info.value.error_code == "F-013"


class TestFetchOrder:
    """Test fetch_order method"""

    @pytest.fixture
    def mock_exchange_class(self):
        """Create mock exchange class for fetch tests"""
        mock_class = MagicMock()
        mock_instance = AsyncMock()
        mock_instance.fetch_order = AsyncMock()
        mock_instance.load_markets = AsyncMock()
        mock_instance.close = AsyncMock()
        mock_instance.options = {"defaultType": "swap"}
        mock_class.return_value = mock_instance
        return mock_class

    @pytest.fixture
    def gateway(self, exchange_name, exchange_credentials, mock_exchange_class):
        """Create gateway with mocked exchange for fetch tests"""
        with patch('src.infrastructure.exchange_gateway.ccxt_async') as mock_ccxt:
            mock_ccxt.binance = mock_exchange_class
            mock_ccxt.bybit = mock_exchange_class
            mock_ccxt.okx = mock_exchange_class

            gateway = ExchangeGateway(
                exchange_name=exchange_name,
                **exchange_credentials,
            )
            yield gateway

    @pytest.mark.asyncio
    async def test_fetch_order_success(self, gateway, mock_exchange_class):
        """Test successful order fetch"""
        gateway.rest_exchange.fetch_order.return_value = {
            'id': '12345',
            'symbol': 'BTC/USDT:USDT',
            'type': 'limit',
            'side': 'buy',
            'amount': 0.1,
            'price': 35000.0,
            'average': 35000.0,
            'status': 'open',
        }

        result = await gateway.fetch_order("12345", "BTC/USDT:USDT")

        assert result.exchange_order_id == '12345'
        assert result.order_type == OrderType.LIMIT
        assert result.price == Decimal("35000.0")
        assert result.status == OrderStatus.OPEN

    @pytest.mark.asyncio
    async def test_fetch_order_not_found_raises_error(self, gateway, mock_exchange_class):
        """Test that fetching non-existent order raises OrderNotFoundError"""
        import ccxt
        gateway.rest_exchange.fetch_order.side_effect = ccxt.OrderNotFound("Order not found")

        with pytest.raises(OrderNotFoundError):
            await gateway.fetch_order("nonexistent", "BTC/USDT:USDT")


class TestFetchTickerPrice:
    """Test fetch_ticker_price method - G-002 fix verification"""

    @pytest.fixture
    def mock_exchange_class(self):
        """Create mock exchange class for ticker tests"""
        mock_class = MagicMock()
        mock_instance = AsyncMock()
        mock_instance.fetch_ticker = AsyncMock()
        mock_instance.load_markets = AsyncMock()
        mock_instance.close = AsyncMock()
        mock_instance.options = {"defaultType": "swap"}
        mock_class.return_value = mock_instance
        return mock_class

    @pytest.fixture
    def gateway(self, exchange_name, exchange_credentials, mock_exchange_class):
        """Create gateway with mocked exchange for ticker tests"""
        with patch('src.infrastructure.exchange_gateway.ccxt_async') as mock_ccxt:
            mock_ccxt.binance = mock_exchange_class
            mock_ccxt.bybit = mock_exchange_class
            mock_ccxt.okx = mock_exchange_class

            gateway = ExchangeGateway(
                exchange_name=exchange_name,
                **exchange_credentials,
            )
            yield gateway

    @pytest.mark.asyncio
    async def test_fetch_ticker_price_success(self, gateway, mock_exchange_class):
        """Test successful ticker price fetch"""
        gateway.rest_exchange.fetch_ticker.return_value = {
            'symbol': 'BTC/USDT:USDT',
            'last': 35000.0,
            'bid': 34999.0,
            'ask': 35001.0,
        }

        price = await gateway.fetch_ticker_price("BTC/USDT:USDT")

        assert price == Decimal("35000.0")

    @pytest.mark.asyncio
    async def test_fetch_ticker_price_uses_last(self, gateway, mock_exchange_class):
        """Test that fetch_ticker_price prefers 'last' price"""
        gateway.rest_exchange.fetch_ticker.return_value = {
            'symbol': 'BTC/USDT:USDT',
            'last': 35000.0,
            'close': 34900.0,
            'bid': 34999.0,
            'ask': 35001.0,
        }

        price = await gateway.fetch_ticker_price("BTC/USDT:USDT")

        assert price == Decimal("35000.0")  # Should use 'last'

    @pytest.mark.asyncio
    async def test_fetch_ticker_price_fallback_to_close(self, gateway, mock_exchange_class):
        """Test that fetch_ticker_price falls back to 'close' when 'last' unavailable"""
        gateway.rest_exchange.fetch_ticker.return_value = {
            'symbol': 'BTC/USDT:USDT',
            'close': 34900.0,
            'bid': 34999.0,
            'ask': 35001.0,
        }

        price = await gateway.fetch_ticker_price("BTC/USDT:USDT")

        assert price == Decimal("34900.0")

    @pytest.mark.asyncio
    async def test_fetch_ticker_price_fallback_to_bid(self, gateway, mock_exchange_class):
        """Test that fetch_ticker_price falls back to 'bid' when 'last' and 'close' unavailable"""
        gateway.rest_exchange.fetch_ticker.return_value = {
            'symbol': 'BTC/USDT:USDT',
            'bid': 34999.0,
            'ask': 35001.0,
        }

        price = await gateway.fetch_ticker_price("BTC/USDT:USDT")

        assert price == Decimal("34999.0")

    @pytest.mark.asyncio
    async def test_fetch_ticker_price_no_data_raises_error(self, gateway, mock_exchange_class):
        """Test that fetch_ticker_price raises error when no price data available"""
        gateway.rest_exchange.fetch_ticker.return_value = {
            'symbol': 'BTC/USDT:USDT',
        }

        with pytest.raises(ConnectionLostError) as exc_info:
            await gateway.fetch_ticker_price("BTC/USDT:USDT")

        assert exc_info.value.error_code == "C-001"

    @pytest.mark.asyncio
    async def test_fetch_ticker_price_network_error_raises_error(self, gateway, mock_exchange_class):
        """Test that network error raises ConnectionLostError"""
        import ccxt
        gateway.rest_exchange.fetch_ticker.side_effect = ccxt.NetworkError("Connection failed")

        with pytest.raises(ConnectionLostError) as exc_info:
            await gateway.fetch_ticker_price("BTC/USDT:USDT")

        assert exc_info.value.error_code == "C-001"


class TestOrderHelperMethods:
    """Test order helper methods"""

    @pytest.fixture
    def gateway(self, exchange_name, exchange_credentials):
        """Create gateway instance for testing"""
        return ExchangeGateway(
            exchange_name=exchange_name,
            **exchange_credentials,
        )

    def test_map_order_type_to_ccxt_market(self, gateway):
        """Test mapping market order type"""
        assert gateway._map_order_type_to_ccxt("market") == "market"

    def test_map_order_type_to_ccxt_limit(self, gateway):
        """Test mapping limit order type"""
        assert gateway._map_order_type_to_ccxt("limit") == "limit"

    def test_map_order_type_to_ccxt_stop_market(self, gateway):
        """Test mapping stop_market order type"""
        assert gateway._map_order_type_to_ccxt("stop_market") == "stop"

    def test_map_side_to_direction_buy_open(self, gateway):
        """Test mapping buy side to LONG for open position"""
        from src.domain.models import Direction
        result = gateway._map_side_to_direction("buy", reduce_only=False)
        assert result == Direction.LONG

    def test_map_side_to_direction_sell_open(self, gateway):
        """Test mapping sell side to SHORT for open position"""
        from src.domain.models import Direction
        result = gateway._map_side_to_direction("sell", reduce_only=False)
        assert result == Direction.SHORT

    def test_map_side_to_direction_buy_close(self, gateway):
        """Test mapping buy side to SHORT for close position (closing short)"""
        from src.domain.models import Direction
        result = gateway._map_side_to_direction("buy", reduce_only=True)
        assert result == Direction.SHORT

    def test_map_side_to_direction_sell_close(self, gateway):
        """Test mapping sell side to LONG for close position (closing long)"""
        from src.domain.models import Direction
        result = gateway._map_side_to_direction("sell", reduce_only=True)
        assert result == Direction.LONG

    def test_parse_order_status_open(self, gateway):
        """Test parsing 'open' status"""
        result = gateway._parse_order_status('open')
        assert result == OrderStatus.OPEN

    def test_parse_order_status_closed(self, gateway):
        """Test parsing 'closed' status"""
        result = gateway._parse_order_status('closed')
        assert result == OrderStatus.FILLED

    def test_parse_order_status_canceled(self, gateway):
        """Test parsing 'canceled' status"""
        result = gateway._parse_order_status('canceled')
        assert result == OrderStatus.CANCELED

    def test_parse_order_status_rejected(self, gateway):
        """Test parsing 'rejected' status"""
        result = gateway._parse_order_status('rejected')
        assert result == OrderStatus.REJECTED

    def test_parse_order_status_expired(self, gateway):
        """Test parsing 'expired' status"""
        result = gateway._parse_order_status('expired')
        assert result == OrderStatus.EXPIRED

    def test_parse_order_type_market(self, gateway):
        """Test parsing market order type"""
        result = gateway._parse_order_type('market')
        assert result == OrderType.MARKET

    def test_parse_order_type_limit(self, gateway):
        """Test parsing limit order type"""
        result = gateway._parse_order_type('limit')
        assert result == OrderType.LIMIT

    def test_parse_order_type_stop(self, gateway):
        """Test parsing 'stop' order type (CCXT format)"""
        result = gateway._parse_order_type('stop')
        assert result == OrderType.STOP_MARKET

    def test_parse_order_type_stop_market(self, gateway):
        """Test parsing 'stop_market' order type"""
        result = gateway._parse_order_type('stop_market')
        assert result == OrderType.STOP_MARKET


# ============================================================
# Test WebSocket Order Monitoring (G-002)
# ============================================================
class TestWatchOrders:
    """Test WebSocket order monitoring with G-002 dedup logic"""

    @pytest.fixture
    def gateway(self, exchange_name, exchange_credentials):
        """Create gateway instance for testing"""
        return ExchangeGateway(
            exchange_name=exchange_name,
            **exchange_credentials,
        )

    @pytest.mark.asyncio
    async def test_watch_orders_dedup_by_filled_qty(self, gateway):
        """
        G-002 修复：基于 filled_qty 去重，而非时间戳

        测试场景：同一订单在同一毫秒内多次推送 Partial Fill，
        只有 filled_qty 增加的推送才会被处理
        """
        # 模拟第一次订单更新（部分成交）
        raw_order_1 = {
            'id': 'test_order_001',
            'symbol': 'BTC/USDT:USDT',
            'status': 'open',
            'type': 'limit',
            'side': 'buy',
            'amount': 1.0,
            'filled': 0.5,
            'remaining': 0.5,
            'price': 35000.0,
            'average': 35000.0,
            'timestamp': 1700000000000,
        }

        # 模拟第二次订单更新（同一毫秒，filled_qty 相同）
        raw_order_2 = {
            'id': 'test_order_001',
            'symbol': 'BTC/USDT:USDT',
            'status': 'open',
            'type': 'limit',
            'side': 'buy',
            'amount': 1.0,
            'filled': 0.5,  # 相同的 filled_qty
            'remaining': 0.5,
            'price': 35000.0,
            'average': 35000.0,
            'timestamp': 1700000000000,  # 相同时间戳
        }

        # 第一次处理应该返回订单
        result_1 = await gateway._handle_order_update(raw_order_1)
        assert result_1 is not None
        assert result_1.filled_qty == Decimal('0.5')

        # 第二次处理应该返回 None（重复）
        result_2 = await gateway._handle_order_update(raw_order_2)
        assert result_2 is None

    @pytest.mark.asyncio
    async def test_watch_orders_partial_fill_increase(self, gateway):
        """
        测试部分成交增加时的正确处理

        场景：filled_qty 从 0.5 增加到 0.8，应该被处理
        """
        # 第一次：filled_qty = 0.5
        raw_order_1 = {
            'id': 'test_order_002',
            'symbol': 'BTC/USDT:USDT',
            'status': 'open',
            'type': 'limit',
            'side': 'buy',
            'amount': 1.0,
            'filled': 0.5,
            'remaining': 0.5,
            'price': 35000.0,
            'average': 35000.0,
            'timestamp': 1700000000000,
        }

        # 第二次：filled_qty = 0.8（增加）
        raw_order_2 = {
            'id': 'test_order_002',
            'symbol': 'BTC/USDT:USDT',
            'status': 'open',
            'type': 'limit',
            'side': 'buy',
            'amount': 1.0,
            'filled': 0.8,  # 增加了
            'remaining': 0.2,
            'price': 35000.0,
            'average': 35000.0,
            'timestamp': 1700000001000,
        }

        result_1 = await gateway._handle_order_update(raw_order_1)
        assert result_1 is not None
        assert result_1.filled_qty == Decimal('0.5')

        result_2 = await gateway._handle_order_update(raw_order_2)
        assert result_2 is not None  # 应该被处理
        assert result_2.filled_qty == Decimal('0.8')

    @pytest.mark.asyncio
    async def test_watch_orders_status_change_from_open_to_filled(self, gateway):
        """
        测试订单状态从 open 变为 filled 时的处理
        """
        # 第一次：open 状态
        raw_order_1 = {
            'id': 'test_order_003',
            'symbol': 'BTC/USDT:USDT',
            'status': 'open',
            'type': 'limit',
            'side': 'buy',
            'amount': 1.0,
            'filled': 0.0,
            'remaining': 1.0,
            'price': 35000.0,
            'timestamp': 1700000000000,
        }

        # 第二次：filled 状态
        raw_order_2 = {
            'id': 'test_order_003',
            'symbol': 'BTC/USDT:USDT',
            'status': 'closed',  # CCXT 使用 'closed' 表示已成交
            'type': 'limit',
            'side': 'buy',
            'amount': 1.0,
            'filled': 1.0,
            'remaining': 0.0,
            'price': 35000.0,
            'average': 35000.0,
            'timestamp': 1700000002000,
        }

        result_1 = await gateway._handle_order_update(raw_order_1)
        assert result_1 is not None
        assert result_1.status == OrderStatus.OPEN

        result_2 = await gateway._handle_order_update(raw_order_2)
        assert result_2 is not None
        assert result_2.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_watch_orders_partially_filled_status(self, gateway):
        """
        测试部分成交状态的正确识别
        """
        raw_order = {
            'id': 'test_order_004',
            'symbol': 'BTC/USDT:USDT',
            'status': 'open',  # CCXT 状态为 open
            'type': 'limit',
            'side': 'buy',
            'amount': 1.0,
            'filled': 0.3,  # 但有部分成交
            'remaining': 0.7,
            'price': 35000.0,
            'average': 35000.0,
            'timestamp': 1700000000000,
        }

        result = await gateway._handle_order_update(raw_order)
        assert result is not None
        # 应该识别为 PARTIALLY_FILLED
        assert result.status == OrderStatus.PARTIALLY_FILLED

    @pytest.mark.asyncio
    async def test_watch_orders_canceled_status(self, gateway):
        """
        测试取消订单状态的正确识别
        """
        raw_order = {
            'id': 'test_order_005',
            'symbol': 'BTC/USDT:USDT',
            'status': 'canceled',
            'type': 'limit',
            'side': 'buy',
            'amount': 1.0,
            'filled': 0.0,
            'remaining': 1.0,
            'price': 35000.0,
            'timestamp': 1700000000000,
        }

        result = await gateway._handle_order_update(raw_order)
        assert result is not None
        assert result.status == OrderStatus.CANCELED

    @pytest.mark.asyncio
    async def test_watch_orders_rejected_status(self, gateway):
        """
        测试被拒绝订单状态的正确识别
        """
        raw_order = {
            'id': 'test_order_006',
            'symbol': 'BTC/USDT:USDT',
            'status': 'rejected',
            'type': 'limit',
            'side': 'buy',
            'amount': 1.0,
            'filled': 0.0,
            'remaining': 1.0,
            'price': 35000.0,
            'timestamp': 1700000000000,
        }

        result = await gateway._handle_order_update(raw_order)
        assert result is not None
        assert result.status == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_watch_orders_decimal_precision(self, gateway):
        """
        测试金额计算的 Decimal 精度
        """
        raw_order = {
            'id': 'test_order_007',
            'symbol': 'BTC/USDT:USDT',
            'status': 'open',
            'type': 'limit',
            'side': 'buy',
            'amount': '1.12345678',  # 字符串形式的高精度数字
            'filled': '0.98765432',
            'remaining': '0.13580246',
            'price': '35123.45678901',
            'average': '35123.45678901',
            'timestamp': 1700000000000,
        }

        result = await gateway._handle_order_update(raw_order)
        assert result is not None
        # 验证 Decimal 精度
        assert result.requested_qty == Decimal('1.12345678')
        assert result.filled_qty == Decimal('0.98765432')
        assert result.price == Decimal('35123.45678901')
        assert isinstance(result.requested_qty, Decimal)
        assert isinstance(result.filled_qty, Decimal)
        assert isinstance(result.price, Decimal)

    @pytest.mark.asyncio
    async def test_watch_orders_clear_state(self, gateway):
        """
        测试清除订单本地状态
        """
        # 先处理一个订单
        raw_order = {
            'id': 'test_order_008',
            'symbol': 'BTC/USDT:USDT',
            'status': 'filled',
            'type': 'limit',
            'side': 'buy',
            'amount': 1.0,
            'filled': 1.0,
            'remaining': 0.0,
            'price': 35000.0,
            'average': 35000.0,
            'timestamp': 1700000000000,
        }

        result = await gateway._handle_order_update(raw_order)
        assert result is not None
        assert 'test_order_008' in gateway._order_local_state

        # 清除状态
        gateway.clear_order_state('test_order_008')
        assert 'test_order_008' not in gateway._order_local_state

    @pytest.mark.asyncio
    async def test_watch_orders_anomaly_filled_qty_decrease(self, gateway, caplog):
        """
        测试 filled_qty 减少的异常情况（应记录警告并跳过）

        G-002 修复逻辑：
        - 当 filled_qty 减少时，记录警告日志
        - 但由于这是异常情况，仍然跳过处理（返回 None）
        """
        import logging
        # 设置日志级别为 DEBUG 以捕获所有日志
        caplog.set_level(logging.DEBUG)

        # 第一次：filled_qty = 0.5
        raw_order_1 = {
            'id': 'test_order_009',
            'symbol': 'BTC/USDT:USDT',
            'status': 'open',
            'type': 'limit',
            'side': 'buy',
            'amount': 1.0,
            'filled': 0.5,
            'remaining': 0.5,
            'price': 35000.0,
            'timestamp': 1700000000000,
        }

        # 第二次：filled_qty = 0.3（异常减少）
        raw_order_2 = {
            'id': 'test_order_009',
            'symbol': 'BTC/USDT:USDT',
            'status': 'open',
            'type': 'limit',
            'side': 'buy',
            'amount': 1.0,
            'filled': 0.3,  # 异常减少
            'remaining': 0.7,
            'price': 35000.0,
            'timestamp': 1700000001000,
        }

        result_1 = await gateway._handle_order_update(raw_order_1)
        assert result_1 is not None

        result_2 = await gateway._handle_order_update(raw_order_2)
        # 由于 filled_qty 减少且状态未变，被判断为重复更新，返回 None
        assert result_2 is None

        # 检查是否记录了"重复更新"日志（因为 filled_qty 减少时，状态未变，先命中重复判断）
        # G-002 修复逻辑：filled_qty <= local_filled_qty and status == local_status → 跳过
        assert "重复更新" in caplog.text or "filled_qty" in caplog.text

    @pytest.mark.asyncio
    async def test_parse_order_status_with_filled_qty_partially(self, gateway):
        """
        测试 _parse_order_status_with_filled_qty 方法的部分成交识别
        """
        # open 状态 + 部分成交 = PARTIALLY_FILLED
        result = gateway._parse_order_status_with_filled_qty(
            'open',
            Decimal('0.5'),
            Decimal('1.0')
        )
        assert result == OrderStatus.PARTIALLY_FILLED

    @pytest.mark.asyncio
    async def test_parse_order_status_with_filled_qty_zero(self, gateway):
        """
        测试 _parse_order_status_with_filled_qty 方法的零成交识别
        """
        # open 状态 + 零成交 = OPEN
        result = gateway._parse_order_status_with_filled_qty(
            'open',
            Decimal('0'),
            Decimal('1.0')
        )
        assert result == OrderStatus.OPEN

    @pytest.mark.asyncio
    async def test_parse_order_status_with_filled_qty_full(self, gateway):
        """
        测试 _parse_order_status_with_filled_qty 方法的完全成交识别
        """
        # closed 状态 = FILLED
        result = gateway._parse_order_status_with_filled_qty(
            'closed',
            Decimal('1.0'),
            Decimal('1.0')
        )
        assert result == OrderStatus.FILLED
