"""Tests for Backtester config_manager explicit injection.

Verifies:
1. config_manager passed to constructor is used directly (no global singleton)
2. Fallback to ConfigManager.get_instance() when config_manager not provided
3. No global singleton pollution when config_manager is injected explicitly
4. config_manager=None behaves same as not providing it (falls back to get_instance)
5. Legacy mode never touches config_manager
6. legacy_fallback path emits a log containing "legacy_fallback"
7. Explicit injection does NOT emit legacy_fallback log
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.backtester import Backtester
from src.domain.models import KlineData, BacktestRequest, AccountSnapshot
from src.infrastructure.exchange_gateway import ExchangeGateway


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def sample_klines():
    return [
        KlineData(
            symbol="BTC/USDT:USDT", timeframe="15m",
            timestamp=1704067200000,
            open=Decimal("42000.00"), high=Decimal("42500.00"),
            low=Decimal("41800.00"), close=Decimal("42300.00"),
            volume=Decimal("1000.0"), is_closed=True,
        ),
        KlineData(
            symbol="BTC/USDT:USDT", timeframe="15m",
            timestamp=1704068100000,
            open=Decimal("42300.00"), high=Decimal("42800.00"),
            low=Decimal("42200.00"), close=Decimal("42600.00"),
            volume=Decimal("1200.0"), is_closed=True,
        ),
    ]


@pytest.fixture
def mock_gateway():
    gw = MagicMock(spec=ExchangeGateway)
    gw.fetch_historical_ohlcv = AsyncMock(return_value=[])
    return gw


# ============================================================
# 1. Explicit config_manager is used directly
# ============================================================


@pytest.mark.asyncio
async def test_explicit_config_manager_used_directly(mock_gateway, sample_klines):
    """config_manager passed to constructor is used, get_instance() is NOT called."""
    mock_cm = MagicMock()
    mock_cm.get_backtest_configs = AsyncMock(return_value={
        'slippage_rate': Decimal('0.002'),
    })

    backtester = Backtester(
        exchange_gateway=mock_gateway,
        config_manager=mock_cm,
    )

    request = BacktestRequest(symbol="BTC/USDT:USDT", timeframe="15m", mode="v3_pms")

    with patch.object(backtester, '_fetch_klines', AsyncMock(return_value=sample_klines)):
        with patch('src.application.config_manager.ConfigManager.get_instance') as mock_get_instance:
            try:
                await backtester.run_backtest(request)
            except Exception:
                pass

    # The explicitly provided config_manager should be used
    mock_cm.get_backtest_configs.assert_called_once()
    # get_instance() should NOT be called since we provided config_manager
    mock_get_instance.assert_not_called()


# ============================================================
# 2. Fallback to get_instance() when config_manager not provided
# ============================================================


@pytest.mark.asyncio
async def test_fallback_to_get_instance_when_not_provided(mock_gateway, sample_klines):
    """When config_manager not provided, falls back to ConfigManager.get_instance()."""
    mock_cm = MagicMock()
    mock_cm.get_backtest_configs = AsyncMock(return_value={})

    backtester = Backtester(exchange_gateway=mock_gateway)

    request = BacktestRequest(symbol="BTC/USDT:USDT", timeframe="15m", mode="v3_pms")

    with patch.object(backtester, '_fetch_klines', AsyncMock(return_value=sample_klines)):
        with patch('src.application.config_manager.ConfigManager.get_instance', return_value=mock_cm):
            try:
                await backtester.run_backtest(request)
            except Exception:
                pass

    # get_instance() fallback should be used
    mock_cm.get_backtest_configs.assert_called_once()


# ============================================================
# 3. No global singleton pollution with explicit injection
# ============================================================


@pytest.mark.asyncio
async def test_no_global_pollution_with_explicit_cm(mock_gateway, sample_klines):
    """When config_manager is injected, global singleton remains untouched."""
    mock_cm = MagicMock()
    mock_cm.get_backtest_configs = AsyncMock(return_value={})

    # Set a global singleton BEFORE running backtest
    from src.application.config_manager import ConfigManager
    original_instance = ConfigManager._instance
    sentinel = object()
    ConfigManager._instance = sentinel

    try:
        backtester = Backtester(
            exchange_gateway=mock_gateway,
            config_manager=mock_cm,
        )

        request = BacktestRequest(symbol="BTC/USDT:USDT", timeframe="15m", mode="v3_pms")

        with patch.object(backtester, '_fetch_klines', AsyncMock(return_value=sample_klines)):
            try:
                await backtester.run_backtest(request)
            except Exception:
                pass

        # Global singleton should be UNCHANGED — not replaced by our mock_cm
        assert ConfigManager._instance is sentinel
    finally:
        ConfigManager._instance = original_instance


# ============================================================
# 4. config_manager=None falls back to get_instance
# ============================================================


@pytest.mark.asyncio
async def test_config_manager_none_falls_back(mock_gateway, sample_klines):
    """config_manager=None behaves same as not providing it."""
    mock_cm = MagicMock()
    mock_cm.get_backtest_configs = AsyncMock(return_value={})

    backtester = Backtester(exchange_gateway=mock_gateway, config_manager=None)

    request = BacktestRequest(symbol="BTC/USDT:USDT", timeframe="15m", mode="v3_pms")

    with patch.object(backtester, '_fetch_klines', AsyncMock(return_value=sample_klines)):
        with patch('src.application.config_manager.ConfigManager.get_instance', return_value=mock_cm):
            try:
                await backtester.run_backtest(request)
            except Exception:
                pass

    mock_cm.get_backtest_configs.assert_called_once()


# ============================================================
# 5. Legacy mode never touches config_manager
# ============================================================


@pytest.mark.asyncio
async def test_legacy_mode_ignores_config_manager(mock_gateway, sample_klines):
    """v2_classic mode never calls config_manager.get_backtest_configs."""
    mock_cm = MagicMock()
    mock_cm.get_backtest_configs = AsyncMock(return_value={})

    backtester = Backtester(
        exchange_gateway=mock_gateway,
        config_manager=mock_cm,
    )

    request = BacktestRequest(symbol="BTC/USDT:USDT", timeframe="15m", mode="v2_classic")

    with patch.object(backtester, '_fetch_klines', AsyncMock(return_value=sample_klines)):
        try:
            await backtester.run_backtest(request)
        except Exception:
            pass

    mock_cm.get_backtest_configs.assert_not_called()


# ============================================================
# 6. legacy_fallback path logs "legacy_fallback"
# ============================================================


@pytest.mark.asyncio
async def test_fallback_logs_legacy_fallback(mock_gateway, sample_klines):
    """When config_manager not injected, fallback path logs 'legacy_fallback'."""
    mock_cm = MagicMock()
    mock_cm.get_backtest_configs = AsyncMock(return_value={})

    backtester = Backtester(exchange_gateway=mock_gateway)
    request = BacktestRequest(symbol="BTC/USDT:USDT", timeframe="15m", mode="v3_pms")

    with patch.object(backtester, '_fetch_klines', AsyncMock(return_value=sample_klines)):
        with patch('src.application.config_manager.ConfigManager.get_instance', return_value=mock_cm):
            with patch('src.application.backtester.logger') as mock_logger:
                try:
                    await backtester.run_backtest(request)
                except Exception:
                    pass

    # Verify legacy_fallback was logged
    info_calls = [str(call) for call in mock_logger.info.call_args_list]
    assert any("legacy_fallback" in c for c in info_calls), (
        f"Expected 'legacy_fallback' in logger.info calls, got: {info_calls}"
    )


# ============================================================
# 7. Explicit injection does NOT log legacy_fallback
# ============================================================


@pytest.mark.asyncio
async def test_explicit_injection_no_legacy_log(mock_gateway, sample_klines):
    """When config_manager is explicitly injected, no legacy_fallback log."""
    mock_cm = MagicMock()
    mock_cm.get_backtest_configs = AsyncMock(return_value={})

    backtester = Backtester(exchange_gateway=mock_gateway, config_manager=mock_cm)
    request = BacktestRequest(symbol="BTC/USDT:USDT", timeframe="15m", mode="v3_pms")

    with patch.object(backtester, '_fetch_klines', AsyncMock(return_value=sample_klines)):
        with patch('src.application.backtester.logger') as mock_logger:
            try:
                await backtester.run_backtest(request)
            except Exception:
                pass

    # Verify legacy_fallback was NOT logged
    info_calls = [str(call) for call in mock_logger.info.call_args_list]
    assert not any("legacy_fallback" in c for c in info_calls), (
        f"Did not expect 'legacy_fallback' in logger.info calls, got: {info_calls}"
    )
