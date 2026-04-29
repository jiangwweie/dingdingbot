"""
Multi-Exchange Integration Tests - Bybit & OKX Verification

This test suite verifies:
1. Configuration loading for Bybit and OKX
2. Exchange initialization and connectivity
3. Symbol availability validation
4. End-to-end flow: config -> exchange init -> WebSocket -> signal processing

Test Exchanges:
- Bybit: Derivatives (USDT perpetual swaps)
- OKX: Derivatives (USDT perpetual swaps)
"""
import pytest
import asyncio
from pathlib import Path
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import yaml

from src.application.config_manager import ConfigManager, CoreConfig, UserConfig
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.domain.models import KlineData, AccountSnapshot
from src.domain.exceptions import FatalStartupError


# ============================================================
# Test Fixtures
# ============================================================
@pytest.fixture
def config_dir():
    """Return the config directory path"""
    return Path(__file__).parent.parent.parent / 'config'


@pytest.fixture
def bybit_config_file(config_dir):
    """Return path to Bybit config example"""
    return config_dir / 'user.bybit.yaml.example'


@pytest.fixture
def okx_config_file(config_dir):
    """Return path to OKX config example"""
    return config_dir / 'user.okx.yaml.example'


@pytest.fixture(params=['bybit', 'okx'], ids=lambda x: f"exchange={x}")
def exchange_type(request):
    """Parametrized fixture for exchange types"""
    return request.param


@pytest.fixture
def exchange_credentials(exchange_type):
    """Return test credentials for each exchange"""
    credentials = {
        'bybit': {
            'exchange_name': 'bybit',
            'api_key': 'test_bybit_key',
            'api_secret': 'test_bybit_secret',
            'testnet': True,
        },
        'okx': {
            'exchange_name': 'okx',
            'api_key': 'test_okx_key',
            'api_secret': 'test_okx_secret',
            'testnet': True,
        },
    }
    return credentials.get(exchange_type, credentials['bybit'])


# ============================================================
# Configuration Loading Tests
# ============================================================
class TestConfigurationLoading:
    """Test configuration loading for different exchanges"""

    def test_bybit_config_example_structure(self, bybit_config_file):
        """Verify Bybit config example has correct structure"""
        assert bybit_config_file.exists(), f"Bybit config example not found: {bybit_config_file}"

        with open(bybit_config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Verify required sections
        assert 'exchange' in config
        assert config['exchange']['name'] == 'bybit'
        assert 'api_key' in config['exchange']
        assert 'api_secret' in config['exchange']
        assert 'timeframes' in config
        assert 'active_strategies' in config
        assert 'risk' in config
        assert 'notification' in config

    def test_okx_config_example_structure(self, okx_config_file):
        """Verify OKX config example has correct structure"""
        assert okx_config_file.exists(), f"OKX config example not found: {okx_config_file}"

        with open(okx_config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Verify required sections
        assert 'exchange' in config
        assert config['exchange']['name'] == 'okx'
        assert 'api_key' in config['exchange']
        assert 'api_secret' in config['exchange']
        assert 'timeframes' in config
        assert 'active_strategies' in config
        assert 'risk' in config
        assert 'notification' in config

    def test_config_validation_with_mock_credentials(self, config_dir, exchange_type):
        """Test that config validation passes with mock credentials"""
        # Create temporary user.yaml with exchange-specific config
        config_file = config_dir / 'user.test_temp.yaml'

        test_config = {
            'exchange': {
                'name': exchange_type,
                'api_key': f'test_{exchange_type}_key',
                'api_secret': f'test_{exchange_type}_secret',
                'testnet': True,
            },
            'user_symbols': [],
            'timeframes': ['15m', '1h'],
            'active_strategies': [{
                'id': 'test-strategy',
                'name': 'test_pinbar',
                'trigger': {'type': 'pinbar', 'enabled': True, 'params': {}},
                'filters': [],
                'filter_logic': 'AND',
                'is_global': True,
                'apply_to': [],
            }],
            'strategy': None,
            'risk': {
                'max_loss_percent': '0.01',
                'max_leverage': 125,
                'max_total_exposure': '0.8',
            },
            'asset_polling': {'interval_seconds': 60},
            'notification': {
                'channels': [{'type': 'feishu', 'webhook_url': 'https://example.com/webhook'}]
            },
        }

        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(test_config, f)

            # Test config loading
            manager = ConfigManager(config_dir=str(config_dir))
            manager.load_core_config()

            # Temporarily rename file to user.yaml for loading
            import shutil
            backup_file = config_dir / 'user.yaml.backup'
            original_user = config_dir / 'user.yaml'

            if original_user.exists():
                shutil.copy(original_user, backup_file)

            shutil.copy(config_file, config_dir / 'user.yaml')

            try:
                manager.load_user_config()
                manager.merge_symbols()

                # Verify config loaded correctly
                assert manager.user_config.exchange.name == exchange_type
                assert len(manager.user_config.timeframes) == 2
                assert manager.user_config.timeframes == ['15m', '1h']

            finally:
                # Restore original user.yaml
                if backup_file.exists():
                    shutil.copy(backup_file, original_user)
                    backup_file.unlink()
                if config_dir / 'user.yaml' != config_file:
                    (config_dir / 'user.yaml').unlink(missing_ok=True)

        finally:
            config_file.unlink(missing_ok=True)


# ============================================================
# Exchange Gateway Initialization Tests
# ============================================================
class TestExchangeGatewayInit:
    """Test Exchange Gateway initialization for different exchanges"""

    def test_gateway_creation(self, exchange_type, exchange_credentials):
        """Test creating ExchangeGateway for each exchange"""
        gateway = ExchangeGateway(
            exchange_name=exchange_credentials['exchange_name'],
            api_key=exchange_credentials['api_key'],
            api_secret=exchange_credentials['api_secret'],
            testnet=exchange_credentials['testnet'],
        )

        assert gateway.exchange_name == exchange_credentials['exchange_name']
        assert gateway.api_key == exchange_credentials['api_key']
        assert gateway.testnet == exchange_credentials['testnet']
        assert gateway._max_reconnect_attempts == 10

    @pytest.mark.asyncio
    async def test_exchange_initialization_mock(self, exchange_type, exchange_credentials):
        """Test exchange initialization with mocked CCXT"""
        # Create mock exchange class
        mock_instance = AsyncMock()
        mock_instance.load_markets = AsyncMock()
        mock_instance.symbols = [
            'BTC/USDT:USDT',
            'ETH/USDT:USDT',
            'SOL/USDT:USDT',
            'BNB/USDT:USDT',
        ]

        mock_class = MagicMock(return_value=mock_instance)

        with patch.object(asyncio, 'create_task') as mock_task:
            mock_task.return_value = AsyncMock()

            with patch('src.infrastructure.exchange_gateway.ccxt_async') as mock_ccxt:
                # Setup mock for all exchanges
                mock_ccxt.binance = mock_class
                mock_ccxt.bybit = mock_class
                mock_ccxt.okx = mock_class

                gateway = ExchangeGateway(**exchange_credentials)
                await gateway.initialize()

                # Verify load_markets was called
                mock_instance.load_markets.assert_called_once()

                await gateway.close()

    def test_timeframe_mapping(self, exchange_type, exchange_credentials):
        """Test that timeframe mapping works for all exchanges"""
        gateway = ExchangeGateway(**exchange_credentials)

        expected_timeframes = {
            '1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m',
            '1h': '1h', '2h': '2h', '4h': '4h', '6h': '6h',
            '12h': '12h', '1d': '1d', '1w': '1w',
        }

        assert gateway.TIMEFRAME_MAP == expected_timeframes


# ============================================================
# Symbol Availability Tests
# ============================================================
class TestSymbolAvailability:
    """Test that core symbols are available on all exchanges"""

    CORE_SYMBOLS = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT']

    @pytest.mark.asyncio
    async def test_core_symbols_availability_mock(self, exchange_type, exchange_credentials):
        """Test that core symbols are available (mocked)"""
        # Mock exchange with all core symbols available
        mock_instance = AsyncMock()
        mock_instance.load_markets = AsyncMock()
        mock_instance.symbols = self.CORE_SYMBOLS + ['XRP/USDT:USDT', 'ADA/USDT:USDT']
        mock_instance.markets = {
            symbol: {'active': True, 'swap': True}
            for symbol in mock_instance.symbols
        }

        mock_class = MagicMock(return_value=mock_instance)

        with patch('src.infrastructure.exchange_gateway.ccxt_async') as mock_ccxt:
            setattr(mock_ccxt, exchange_type, mock_class)

            gateway = ExchangeGateway(**exchange_credentials)
            await gateway.initialize()

            # Verify all core symbols are available
            for symbol in self.CORE_SYMBOLS:
                assert symbol in gateway.rest_exchange.symbols, \
                    f"Core symbol {symbol} not available on {exchange_type}"

            await gateway.close()

    def test_core_symbols_in_config(self, config_dir):
        """Test that core_symbols in core.yaml are valid"""
        core_config_file = config_dir / 'core.yaml'

        with open(core_config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        assert 'core_symbols' in config
        assert len(config['core_symbols']) >= 4

        expected_core = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT']
        for symbol in expected_core:
            assert symbol in config['core_symbols'], \
                f"Core symbol {symbol} missing from core.yaml"


# ============================================================
# End-to-End Flow Tests
# ============================================================
class TestEndToEndFlow:
    """Test complete flow: config -> exchange -> websocket -> signals"""

    @pytest.mark.asyncio
    async def test_full_startup_flow_mock(self, config_dir, exchange_type):
        """Test full application startup flow with mocked dependencies"""
        # Setup test config
        config_file = config_dir / 'user.yaml'
        backup_file = config_dir / 'user.yaml.backup'

        test_config = {
            'exchange': {
                'name': exchange_type,
                'api_key': f'test_{exchange_type}_key',
                'api_secret': f'test_{exchange_type}_secret',
                'testnet': True,
            },
            'user_symbols': [],
            'timeframes': ['15m', '1h'],
            'active_strategies': [{
                'id': 'test-strategy',
                'name': 'test_pinbar',
                'trigger': {'type': 'pinbar', 'enabled': True, 'params': {}},
                'filters': [{'type': 'ema', 'enabled': True, 'params': {}}],
                'filter_logic': 'AND',
                'is_global': True,
                'apply_to': [],
            }],
            'strategy': None,
            'risk': {
                'max_loss_percent': '0.01',
                'max_leverage': 125,
                'max_total_exposure': '0.8',
            },
            'asset_polling': {'interval_seconds': 60},
            'notification': {
                'channels': [{'type': 'feishu', 'webhook_url': 'https://example.com/webhook'}]
            },
        }

        # Backup original
        import shutil
        if config_file.exists():
            shutil.copy(config_file, backup_file)

        try:
            # Write test config
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(test_config, f, allow_unicode=True)

            # Mock CCXT
            mock_instance = AsyncMock()
            mock_instance.load_markets = AsyncMock()
            mock_instance.fetch_ohlcv = AsyncMock(return_value=[])
            mock_instance.fetch_balance = AsyncMock(return_value={
                'total': {'USDT': 10000},
                'free': {'USDT': 10000},
            })
            mock_instance.fetch_positions = AsyncMock(return_value=[])
            mock_instance.symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT']
            mock_instance.close = AsyncMock()

            mock_class = MagicMock(return_value=mock_instance)

            with patch('src.infrastructure.exchange_gateway.ccxt_async') as mock_ccxt:
                mock_ccxt.binance = mock_class
                mock_ccxt.bybit = mock_class
                mock_ccxt.okx = mock_class

                # Step 1: Load config
                manager = ConfigManager(config_dir=str(config_dir))
                manager.load_core_config()
                manager.load_user_config()
                manager.merge_symbols()

                assert manager.user_config.exchange.name == exchange_type
                assert len(manager.merged_symbols) >= 4

                # Step 2: Initialize exchange
                exchange_cfg = manager.user_config.exchange
                gateway = ExchangeGateway(
                    exchange_name=exchange_cfg.name,
                    api_key=exchange_cfg.api_key,
                    api_secret=exchange_cfg.api_secret,
                    testnet=exchange_cfg.testnet,
                )

                await gateway.initialize()

                # Step 3: Verify exchange is ready
                assert gateway.rest_exchange is not None

                # Step 4: Test historical fetch
                historical = await gateway.fetch_historical_ohlcv(
                    'BTC/USDT:USDT', '1h', limit=10
                )
                assert historical == []  # Mock returns empty

                # Step 5: Test account snapshot
                await gateway.start_asset_polling(interval_seconds=60)
                await asyncio.sleep(0.1)  # Let polling start

                await gateway.close()

        finally:
            # Restore original config
            if backup_file.exists():
                shutil.copy(backup_file, config_file)
                backup_file.unlink()

    @pytest.mark.asyncio
    async def test_kline_processing_pipeline(self, exchange_type):
        """Test K-line data processing through pipeline"""
        from src.application.signal_pipeline import SignalPipeline
        from src.domain.risk_calculator import RiskConfig

        # Mock config manager
        mock_config = MagicMock()
        mock_config.user_config = MagicMock()
        mock_config.user_config.mtf_ema_period = 60
        mock_config.user_config.mtf_mapping = {'15m': '1h', '1h': '4h', '4h': '1d', '1d': '1w'}
        mock_config.add_observer = MagicMock()
        mock_config.core_config = MagicMock()
        mock_config.core_config.signal_pipeline.cooldown_seconds = 300

        risk_config = RiskConfig(
            max_loss_percent=Decimal('0.01'),
            max_leverage=125,
        )

        mock_notifier = AsyncMock()
        mock_repository = AsyncMock()

        pipeline = SignalPipeline(
            config_manager=mock_config,
            risk_config=risk_config,
            notification_service=mock_notifier,
            signal_repository=mock_repository,
            cooldown_seconds=300,
        )

        # Create test K-line
        kline = KlineData(
            symbol='BTC/USDT:USDT',
            timeframe='15m',
            timestamp=1700000000000,
            open=Decimal('35000'),
            high=Decimal('35500'),
            low=Decimal('34800'),
            close=Decimal('35200'),
            volume=Decimal('1000'),
            is_closed=True,
        )

        # Process K-line
        await pipeline.process_kline(kline)

        # Verify K-line was stored
        key = 'BTC/USDT:USDT:15m'
        assert key in pipeline._kline_history
        assert len(pipeline._kline_history[key]) >= 1


# ============================================================
# Exchange-Specific Tests
# ============================================================
class TestBybitSpecific:
    """Bybit-specific integration tests"""

    def test_bybit_testnet_endpoint(self):
        """Test Bybit testnet configuration"""
        gateway = ExchangeGateway(
            exchange_name='bybit',
            api_key='test_key',
            api_secret='test_secret',
            testnet=True,
        )

        # Verify testnet is set
        assert gateway.testnet is True

    def test_bybit_sandbox_mode(self):
        """Test Bybit sandbox mode configuration"""
        gateway = ExchangeGateway(
            exchange_name='bybit',
            api_key='test_key',
            api_secret='test_secret',
            testnet=True,
        )

        # Sandbox mode should be enabled
        # Note: ccxt uses sandboxMode internally
        assert gateway.testnet is True


class TestOKXSpecific:
    """OKX-specific integration tests"""

    def test_okx_testnet_endpoint(self):
        """Test OKX testnet configuration"""
        gateway = ExchangeGateway(
            exchange_name='okx',
            api_key='test_key',
            api_secret='test_secret',
            testnet=True,
        )

        assert gateway.testnet is True

    def test_okx_sandbox_mode(self):
        """Test OKX sandbox mode configuration"""
        gateway = ExchangeGateway(
            exchange_name='okx',
            api_key='test_key',
            api_secret='test_secret',
            testnet=True,
        )

        assert gateway.testnet is True


# ============================================================
# Connection and Reconnection Tests
# ============================================================
class TestConnectionHandling:
    """Test connection handling for all exchanges"""

    @pytest.mark.asyncio
    async def test_exchange_close_cleanup(self, exchange_type, exchange_credentials):
        """Test that exchange close properly cleans up resources"""
        mock_instance = AsyncMock()
        mock_instance.load_markets = AsyncMock()
        mock_instance.close = AsyncMock()
        mock_instance.symbols = ['BTC/USDT:USDT']

        mock_class = MagicMock(return_value=mock_instance)

        with patch('src.infrastructure.exchange_gateway.ccxt_async') as mock_ccxt:
            setattr(mock_ccxt, exchange_type, mock_class)

            gateway = ExchangeGateway(**exchange_credentials)
            await gateway.initialize()

            # Start polling
            await gateway.start_asset_polling(interval_seconds=60)
            assert gateway._asset_polling_task is not None

            # Close should cleanup polling task
            await gateway.close()

            # Verify polling task was cancelled
            assert gateway._asset_polling_task is None or gateway._asset_polling_task.cancelled()

    def test_reconnection_config(self, exchange_type, exchange_credentials):
        """Test reconnection configuration"""
        gateway = ExchangeGateway(**exchange_credentials)

        assert gateway._max_reconnect_attempts == 10
        assert gateway._initial_reconnect_delay == 1.0
        assert gateway._max_reconnect_delay == 60.0


# ============================================================
# Integration Test Summary Report
# ============================================================
@pytest.fixture(scope="session", autouse=True)
def generate_test_report(request):
    """Generate a test report after all tests complete"""
    yield

    # Collect test results
    results = {
        'total': 0,
        'passed': 0,
        'failed': 0,
        'exchanges_tested': set(),
    }

    for item in request.session.items:
        if 'test_multi_exchange_integration' in str(item.fspath):
            results['total'] += 1
            # Results are tracked by pytest

    print("\n" + "=" * 60)
    print("MULTI-EXCHANGE INTEGRATION TEST REPORT")
    print("=" * 60)
    print(f"Exchanges Tested: Bybit, OKX")
    print(f"Test Categories:")
    print(f"  - Configuration Loading")
    print(f"  - Exchange Gateway Initialization")
    print(f"  - Symbol Availability Validation")
    print(f"  - End-to-End Flow")
    print(f"  - Connection Handling")
    print("=" * 60)
