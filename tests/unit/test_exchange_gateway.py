"""
Test Exchange Gateway - REST warmup, WebSocket subscription, asset polling.
Uses aioresponses for mocking HTTP requests.
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.exchange_gateway import ExchangeGateway
from src.domain.models import KlineData
from src.domain.exceptions import FatalStartupError, DataQualityWarning


class TestExchangeGatewayInit:
    """Test ExchangeGateway initialization"""

    def test_init_with_params(self):
        """Test initialization with basic parameters"""
        gateway = ExchangeGateway(
            exchange_name="binance",
            api_key="test_key",
            api_secret="test_secret",
        )

        assert gateway.exchange_name == "binance"
        assert gateway.api_key == "test_key"
        assert gateway._max_reconnect_attempts == 10

    def test_init_default_options(self):
        """Test that default options include swap type"""
        gateway = ExchangeGateway(
            exchange_name="binance",
            api_key="test_key",
            api_secret="test_secret",
        )

        # REST exchange should have swap as default type
        assert gateway.rest_exchange.options.get("defaultType") == "swap"


class TestParseOhlcv:
    """Test OHLCV parsing and validation"""

    @pytest.fixture
    def gateway(self):
        """Create gateway instance for testing"""
        return ExchangeGateway(
            exchange_name="binance",
            api_key="test_key",
            api_secret="test_secret",
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

    # ============================================================
    # P0 修复：WebSocket K 线处理测试（x 字段优先逻辑）
    # ============================================================

    def test_parse_ohlcv_with_x_true(self, gateway):
        """测试 x=true 时 is_closed 设置为 True"""
        candle = [
            1700000000000,
            35000.0,
            35500.0,
            34800.0,
            35200.0,
            1000.5,
        ]
        raw_info = {'x': True}

        kline = gateway._parse_ohlcv(candle, "BTC/USDT:USDT", "1h", raw_info=raw_info)

        assert kline is not None
        assert kline.is_closed is True
        assert kline.info == raw_info

    def test_parse_ohlcv_with_x_false(self, gateway):
        """测试 x=false 时 is_closed 设置为 False"""
        candle = [
            1700000000000,
            35000.0,
            35500.0,
            34800.0,
            35200.0,
            1000.5,
        ]
        raw_info = {'x': False}

        kline = gateway._parse_ohlcv(candle, "BTC/USDT:USDT", "1h", raw_info=raw_info)

        assert kline is not None
        assert kline.is_closed is False
        assert kline.info == raw_info

    def test_parse_ohlcv_without_x(self, gateway):
        """测试无 x 字段时默认 is_closed=True"""
        candle = [
            1700000000000,
            35000.0,
            35500.0,
            34800.0,
            35200.0,
            1000.5,
        ]

        kline = gateway._parse_ohlcv(candle, "BTC/USDT:USDT", "1h", raw_info=None)

        assert kline is not None
        assert kline.is_closed is True
        assert kline.info is None


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
    def gateway(self, mock_exchange_class):
        """Create gateway with mocked exchange"""
        with patch('src.infrastructure.exchange_gateway.ccxt_async') as mock_ccxt:
            mock_ccxt.binance = mock_exchange_class
            gateway = ExchangeGateway(
                exchange_name="binance",
                api_key="test_key",
                api_secret="test_secret",
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
    def gateway(self):
        """Create gateway instance"""
        return ExchangeGateway(
            exchange_name="binance",
            api_key="test_key",
            api_secret="test_secret",
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

    # ============================================================
    # P0 修复：_get_closed_candle 测试（x 字段优先逻辑）
    # ============================================================

    def test_get_closed_candle_x_true(self, gateway):
        """测试 x=true 时返回 ohlcv[-1]（刚收盘的 K 线）"""
        # 准备 ohlcv 数据，最后一个 candle 带有 x=true
        ohlcv = [
            [1700000000000, 35000.0, 35500.0, 34800.0, 35200.0, 1000.0],
            [1700003600000, 35200.0, 35800.0, 35100.0, 35600.0, 1200.0],
        ]
        # 模拟 CCXT Pro 返回的数据格式（第 7 个元素是 x 字段）
        ohlcv[-1].append(True)  # x=true

        kline = gateway._get_closed_candle(ohlcv, "BTC/USDT:USDT", "1h")

        assert kline is not None
        assert kline.is_closed is True
        assert kline.timestamp == 1700003600000  # 返回的是 ohlcv[-1]

    def test_get_closed_candle_x_false(self, gateway):
        """测试 x=false 时返回 None（跳过未收盘 K 线）"""
        ohlcv = [
            [1700000000000, 35000.0, 35500.0, 34800.0, 35200.0, 1000.0],
            [1700003600000, 35200.0, 35800.0, 35100.0, 35600.0, 1200.0],
        ]
        # x=false 表示 K 线还未收盘
        ohlcv[-1].append(False)  # x=false

        kline = gateway._get_closed_candle(ohlcv, "BTC/USDT:USDT", "1h")

        assert kline is None  # 应该跳过未收盘的 K 线

    def test_get_closed_candle_timestamp_fallback(self, gateway):
        """测试无 x 字段时使用时间戳推断后备逻辑"""
        # 准备三根 K 线，模拟时间戳变化场景
        ohlcv = [
            [1700000000000, 35000.0, 35500.0, 34800.0, 35200.0, 1000.0],  # K 线 1
            [1700003600000, 35200.0, 35800.0, 35100.0, 35600.0, 1200.0],  # K 线 2
            [1700007200000, 35600.0, 36000.0, 35400.0, 35800.0, 1100.0],  # K 线 3（最新）
        ]
        # 不添加 x 字段，降级到时间戳推断

        # 第一次调用 - 记录最新时间戳但不返回（首次见到该 symbol:timeframe）
        kline1 = gateway._get_closed_candle(ohlcv, "BTC/USDT:USDT", "1h")
        assert kline1 is None  # 第一次见到，记录时间戳 1700007200000

        # 模拟新 K 线到来，时间戳变化
        ohlcv.append([1700010800000, 35800.0, 36200.0, 35600.0, 36000.0, 1300.0])  # K 线 4

        # 第二次调用 - 时间戳变化，应该返回 ohlcv[-2]（刚收盘的 K 线，即 K 线 3）
        kline2 = gateway._get_closed_candle(ohlcv, "BTC/USDT:USDT", "1h")

        assert kline2 is not None
        assert kline2.timestamp == 1700007200000  # 返回的是 ohlcv[-2]（K 线 3）
        assert kline2.is_closed is True


class TestReconnectionLogic:
    """Test WebSocket reconnection logic"""

    def test_reconnect_delay_calculation(self):
        """Test exponential backoff delay calculation"""
        gateway = ExchangeGateway(
            exchange_name="binance",
            api_key="test_key",
            api_secret="test_secret",
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
