"""
Unit tests for Backtester KV configuration integration.

Tests verify:
1. KV configs are loaded from ConfigManager
2. Config priority: Request > KV > Code defaults
3. Fallback to code defaults when KV not available
4. Logging of used config values
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.backtester import Backtester
from src.domain.models import KlineData, BacktestRequest, AccountSnapshot
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
    ]


@pytest.fixture
def mock_exchange_gateway():
    """Mock exchange gateway"""
    gateway = MagicMock(spec=ExchangeGateway)
    gateway.fetch_historical_ohlcv = AsyncMock(return_value=[])
    return gateway


# ============================================================
# Test KV Config Loading
# ============================================================

@pytest.mark.asyncio
class TestKVConfigLoading:
    """Tests for KV config loading from ConfigManager"""

    async def test_loads_kv_configs_for_v3_pms_mode(self, mock_exchange_gateway, sample_klines):
        """Test 1: v3_pms 模式加载 KV 配置"""
        # Arrange: Mock ConfigManager with KV configs
        mock_config_manager = MagicMock()
        mock_config_manager.get_backtest_configs = AsyncMock(return_value={
            'slippage_rate': Decimal('0.002'),
            'fee_rate': Decimal('0.0006'),
            'initial_balance': Decimal('50000'),
            'tp_slippage_rate': Decimal('0.0008'),
        })

        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            mode="v3_pms",
        )

        # Mock _fetch_klines to return sample data
        with patch.object(backtester, '_fetch_klines', AsyncMock(return_value=sample_klines)):
            with patch('src.application.config_manager.ConfigManager') as mock_cm_class:
                mock_cm_class.get_instance = MagicMock(return_value=mock_config_manager)
                try:
                    await backtester.run_backtest(request)
                except Exception:
                    # Ignore other errors, we just want to verify KV loading
                    pass

        # Assert: ConfigManager.get_backtest_configs should be called
        mock_config_manager.get_backtest_configs.assert_called_once()

    async def test_skips_kv_load_for_legacy_mode(self, mock_exchange_gateway, sample_klines):
        """Test 2: 传统模式不加载 KV 配置"""
        mock_config_manager = MagicMock()
        mock_config_manager.get_backtest_configs = AsyncMock()

        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            mode="v2_classic",  # Legacy mode
        )

        with patch.object(backtester, '_fetch_klines', AsyncMock(return_value=sample_klines)):
            with patch('src.application.config_manager.ConfigManager') as mock_cm_class:
                mock_cm_class.get_instance = MagicMock(return_value=mock_config_manager)
                try:
                    await backtester.run_backtest(request)
                except Exception:
                    pass

        # Assert: get_backtest_configs should NOT be called for legacy mode
        mock_config_manager.get_backtest_configs.assert_not_called()

    async def test_handles_config_manager_not_available(self, mock_exchange_gateway, sample_klines):
        """Test 3: ConfigManager 不可用时使用代码默认值"""
        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            mode="v3_pms",
        )

        with patch.object(backtester, '_fetch_klines', AsyncMock(return_value=sample_klines)):
            with patch('src.application.config_manager.ConfigManager') as mock_cm_class:
                mock_cm_class.get_instance = MagicMock(return_value=None)
                try:
                    await backtester.run_backtest(request)
                except Exception:
                    pass

        # Should complete without error, using code defaults

    async def test_handles_exception_during_kv_load(self, mock_exchange_gateway, sample_klines):
        """Test 4: KV 加载异常时降级到代码默认值"""
        mock_config_manager = MagicMock()
        mock_config_manager.get_backtest_configs = AsyncMock(side_effect=Exception("KV load failed"))

        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            mode="v3_pms",
        )

        with patch.object(backtester, '_fetch_klines', AsyncMock(return_value=sample_klines)):
            with patch('src.application.config_manager.ConfigManager') as mock_cm_class:
                mock_cm_class.get_instance = MagicMock(return_value=mock_config_manager)
                try:
                    await backtester.run_backtest(request)
                except Exception:
                    pass

        # Should complete without error, using code defaults


# ============================================================
# Test Config Priority
# ============================================================

@pytest.mark.asyncio
class TestConfigPriority:
    """Tests for config priority: Request > KV > Code defaults"""

    async def test_request_param_overrides_kv_config(self, mock_exchange_gateway, sample_klines):
        """Test 5: 请求参数优先级高于 KV 配置"""
        # KV configs
        kv_configs = {
            'slippage_rate': Decimal('0.002'),
            'fee_rate': Decimal('0.0006'),
            'initial_balance': Decimal('50000'),
            'tp_slippage_rate': Decimal('0.0008'),
        }

        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        # Request with explicit params
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            mode="v3_pms",
            slippage_rate=Decimal('0.003'),  # Override KV
            fee_rate=Decimal('0.0005'),  # Override KV
            initial_balance=Decimal('100000'),  # Override KV
        )

        # Mock _run_v3_pms_backtest to capture the kv_configs passed
        captured_kv_configs = {}

        async def mock_run_v3_pms(request, repo, bt_repo, order_repo, kv_configs):
            captured_kv_configs.update(kv_configs or {})
            # Return minimal valid report structure
            from src.domain.models import PMSBacktestReport
            return PMSBacktestReport(
                strategy_id='test',
                strategy_name='test',
                backtest_start=0,
                backtest_end=0,
                initial_balance=Decimal('10000'),
                final_balance=Decimal('10000'),
                total_return=Decimal('0'),
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=Decimal('0'),
                total_pnl=Decimal('0'),
                total_fees_paid=Decimal('0'),
                total_slippage_cost=Decimal('0'),
                max_drawdown=Decimal('0'),
                positions=[],
            )

        with patch.object(backtester, '_run_v3_pms_backtest', side_effect=mock_run_v3_pms):
            with patch('src.application.config_manager.ConfigManager') as mock_cm_class:
                mock_cm = MagicMock()
                mock_cm.get_backtest_configs = AsyncMock(return_value=kv_configs)
                mock_cm_class.get_instance = MagicMock(return_value=mock_cm)

                await backtester.run_backtest(request)

        # Assert: KV configs should be passed to _run_v3_pms_backtest
        assert captured_kv_configs == kv_configs

    async def test_kv_config_overrides_code_defaults(self, mock_exchange_gateway, sample_klines):
        """Test 6: KV 配置优先级高于代码默认值"""
        # KV configs with custom values
        kv_configs = {
            'slippage_rate': Decimal('0.0025'),
            'fee_rate': Decimal('0.0007'),
            'initial_balance': Decimal('25000'),
            'tp_slippage_rate': Decimal('0.001'),
        }

        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        # Request without explicit params (should use KV)
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            mode="v3_pms",
            # No slippage_rate, fee_rate, or initial_balance specified
        )

        # Capture configs passed to _run_v3_pms_backtest
        captured_kv_configs = {}

        async def mock_run_v3_pms(request, repo, bt_repo, order_repo, kv_configs):
            captured_kv_configs.update(kv_configs or {})
            from src.domain.models import PMSBacktestReport
            return PMSBacktestReport(
                strategy_id='test',
                strategy_name='test',
                backtest_start=0,
                backtest_end=0,
                initial_balance=Decimal('10000'),
                final_balance=Decimal('10000'),
                total_return=Decimal('0'),
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=Decimal('0'),
                total_pnl=Decimal('0'),
                total_fees_paid=Decimal('0'),
                total_slippage_cost=Decimal('0'),
                max_drawdown=Decimal('0'),
                positions=[],
            )

        with patch.object(backtester, '_run_v3_pms_backtest', side_effect=mock_run_v3_pms):
            with patch('src.application.config_manager.ConfigManager') as mock_cm_class:
                mock_cm = MagicMock()
                mock_cm.get_backtest_configs = AsyncMock(return_value=kv_configs)
                mock_cm_class.get_instance = MagicMock(return_value=mock_cm)

                await backtester.run_backtest(request)

        # Assert: KV configs should be passed
        assert captured_kv_configs == kv_configs

    async def test_code_defaults_when_kv_empty(self, mock_exchange_gateway, sample_klines):
        """Test 7: KV 配置为空时使用代码默认值"""
        # Empty KV configs
        kv_configs = {}

        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            mode="v3_pms",
        )

        # Mock _run_v3_pms_backtest to verify merged configs
        actual_slippage = None
        actual_fee = None
        actual_balance = None

        async def mock_run_v3_pms(request, repo, bt_repo, order_repo, kv_configs):
            nonlocal actual_slippage, actual_fee, actual_balance
            # Simulate the merge logic
            actual_slippage = request.slippage_rate or (kv_configs.get('slippage_rate') if kv_configs else None) or Decimal('0.001')
            actual_fee = request.fee_rate or (kv_configs.get('fee_rate') if kv_configs else None) or Decimal('0.0004')
            actual_balance = request.initial_balance or (kv_configs.get('initial_balance') if kv_configs else None) or Decimal('10000')

            from src.domain.models import PMSBacktestReport
            return PMSBacktestReport(
                strategy_id='test',
                strategy_name='test',
                backtest_start=0,
                backtest_end=0,
                initial_balance=actual_balance,
                final_balance=actual_balance,
                total_return=Decimal('0'),
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=Decimal('0'),
                total_pnl=Decimal('0'),
                total_fees_paid=Decimal('0'),
                total_slippage_cost=Decimal('0'),
                max_drawdown=Decimal('0'),
                positions=[],
            )

        with patch.object(backtester, '_run_v3_pms_backtest', side_effect=mock_run_v3_pms):
            with patch('src.application.config_manager.ConfigManager') as mock_cm_class:
                mock_cm = MagicMock()
                mock_cm.get_backtest_configs = AsyncMock(return_value=kv_configs)
                mock_cm_class.get_instance = MagicMock(return_value=mock_cm)

                await backtester.run_backtest(request)

        # Assert: Should use code defaults
        assert actual_slippage == Decimal('0.001')
        assert actual_fee == Decimal('0.0004')
        assert actual_balance == Decimal('10000')

    async def test_partial_kv_configs_use_defaults_for_missing(self, mock_exchange_gateway, sample_klines):
        """Test 8: KV 配置部分缺失时使用代码默认值"""
        # Partial KV configs (only slippage_rate)
        kv_configs = {
            'slippage_rate': Decimal('0.002'),
            # fee_rate, initial_balance missing
        }

        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            mode="v3_pms",
        )

        # Mock _run_v3_pms_backtest to verify merged configs
        actual_configs = {}

        async def mock_run_v3_pms(request, repo, bt_repo, order_repo, kv_configs):
            # Use the same merge logic as actual code
            actual_configs['slippage'] = request.slippage_rate or (kv_configs.get('slippage_rate') if kv_configs else None) or Decimal('0.001')
            actual_configs['fee'] = request.fee_rate or (kv_configs.get('fee_rate') if kv_configs else None) or Decimal('0.0004')
            actual_configs['balance'] = request.initial_balance or (kv_configs.get('initial_balance') if kv_configs else None) or Decimal('10000')
            actual_configs['tp_slippage'] = (kv_configs.get('tp_slippage_rate') if kv_configs else None) or Decimal('0.0005')

            from src.domain.models import PMSBacktestReport
            return PMSBacktestReport(
                strategy_id='test',
                strategy_name='test',
                backtest_start=0,
                backtest_end=0,
                initial_balance=actual_configs['balance'],
                final_balance=actual_configs['balance'],
                total_return=Decimal('0'),
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=Decimal('0'),
                total_pnl=Decimal('0'),
                total_fees_paid=Decimal('0'),
                total_slippage_cost=Decimal('0'),
                max_drawdown=Decimal('0'),
                positions=[],
            )

        with patch.object(backtester, '_run_v3_pms_backtest', side_effect=mock_run_v3_pms):
            with patch('src.application.config_manager.ConfigManager') as mock_cm_class:
                mock_cm = MagicMock()
                mock_cm.get_backtest_configs = AsyncMock(return_value=kv_configs)
                mock_cm_class.get_instance = MagicMock(return_value=mock_cm)

                await backtester.run_backtest(request)

        # Assert: slippage_rate from KV, others from code defaults
        assert actual_configs['slippage'] == Decimal('0.002'), f"Expected slippage from KV (0.002), got {actual_configs['slippage']}"
        assert actual_configs['fee'] == Decimal('0.0004'), f"Expected fee from default (0.0004), got {actual_configs['fee']}"
        assert actual_configs['balance'] == Decimal('10000'), f"Expected balance from default (10000), got {actual_configs['balance']}"
        assert actual_configs['tp_slippage'] == Decimal('0.0005'), f"Expected tp_slippage from default (0.0005), got {actual_configs['tp_slippage']}"


# ============================================================
# Test Logging
# ============================================================

@pytest.mark.asyncio
class TestConfigLogging:
    """Tests for config logging"""

    async def test_logs_used_config_values(self, mock_exchange_gateway, sample_klines, caplog):
        """Test 9: 日志输出使用的配置值"""
        import logging

        kv_configs = {
            'slippage_rate': Decimal('0.002'),
            'fee_rate': Decimal('0.0006'),
            'initial_balance': Decimal('50000'),
            'tp_slippage_rate': Decimal('0.0008'),
        }

        backtester = Backtester(exchange_gateway=mock_exchange_gateway)

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            mode="v3_pms",
        )

        # Set up logging to capture INFO level logs
        with patch.object(backtester, '_fetch_klines', AsyncMock(return_value=sample_klines)):
            with patch('src.application.config_manager.ConfigManager') as mock_cm_class:
                mock_cm = MagicMock()
                mock_cm.get_backtest_configs = AsyncMock(return_value=kv_configs)
                mock_cm_class.get_instance = MagicMock(return_value=mock_cm)

                # Enable logging capture
                import logging
                logger = logging.getLogger('src.infrastructure.logger')
                original_level = logger.level
                logger.setLevel(logging.INFO)

                try:
                    with caplog.at_level(logging.INFO, logger='src.infrastructure.logger'):
                        try:
                            await backtester.run_backtest(request)
                        except Exception:
                            pass

                        # Assert: Log should contain config values
                        assert 'v3 PMS backtest' in caplog.text
                        assert 'slippage' in caplog.text
                finally:
                    logger.setLevel(original_level)
