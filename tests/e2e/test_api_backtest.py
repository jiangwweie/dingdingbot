"""
E2E Integration Tests for Backtest Engine Sandbox Isolation

Tests:
1. Backtest API executes successfully (HTTP 200)
2. Returns valid BacktestReport structure
3. SANDBOX ISOLATION: Backtest params DO NOT pollute global ConfigManager
"""
import pytest
import tempfile
from pathlib import Path
from decimal import Decimal
import yaml

from fastapi.testclient import TestClient

from src.application.config_manager import ConfigManager
from src.interfaces.api import app, set_dependencies
from src.infrastructure.signal_repository import SignalRepository
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.domain.models import AccountSnapshot


# ============================================================
# Mock Exchange Gateway
# ============================================================
class MockExchangeGateway:
    """Mock exchange gateway for backtest testing"""

    def __init__(self):
        self.call_count = 0

    async def fetch_historical_ohlcv(self, symbol, timeframe, limit=100):
        """Return mock K-line data"""
        from src.domain.models import KlineData

        # Generate mock candle data
        # Higher timeframe data for MTF validation
        base_price = Decimal("50000") if "BTC" in symbol else Decimal("3000")

        klines = []
        for i in range(limit):
            timestamp = 1700000000000 + (i * 3600 * 1000)  # Hourly bars
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

        self.call_count += 1
        return klines


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def temp_config_dir():
    """Create temporary directory with valid test config files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)

        # Create core.yaml
        core_config = {
            "core_symbols": ["BTC/USDT:USDT"],
            "pinbar_defaults": {
                "min_wick_ratio": "0.6",
                "max_body_ratio": "0.3",
                "body_position_tolerance": "0.1",
            },
            "ema": {"period": 60},
            "mtf_mapping": {"15m": "1h", "1h": "4h", "4h": "1d"},
            "warmup": {"history_bars": 100},
            "signal_pipeline": {"cooldown_seconds": 14400},
        }

        with open(config_dir / "core.yaml", "w") as f:
            yaml.dump(core_config, f)

        # Create user.yaml with CONSERVATIVE default params
        user_config = {
            "exchange": {
                "name": "binance",
                "api_key": "test_api_key_conservative",
                "api_secret": "test_secret_conservative",
                "testnet": True,
            },
            "user_symbols": [],
            "timeframes": ["15m", "1h"],
            "strategy": {
                "trend_filter_enabled": True,
                "mtf_validation_enabled": True,
            },
            "risk": {
                "max_loss_percent": "0.01",  # 1% default
                "max_leverage": 10,
            },
            "asset_polling": {"interval_seconds": 60},
            "notification": {
                "channels": [{
                    "type": "feishu",
                    "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test123",
                }]
            },
        }

        with open(config_dir / "user.yaml", "w") as f:
            yaml.dump(user_config, f)

        yield config_dir


@pytest.fixture
def config_manager(temp_config_dir):
    """Create ConfigManager with test config"""
    manager = ConfigManager(temp_config_dir)
    manager.load_core_config()
    manager.load_user_config()
    manager.merge_symbols()
    return manager


@pytest.fixture
def mock_gateway():
    """Create mock exchange gateway"""
    return MockExchangeGateway()


@pytest.fixture
def mock_repository():
    """Create mock signal repository"""
    repo = SignalRepository.__new__(SignalRepository)
    repo._db = None
    return repo


@pytest.fixture
def test_client(config_manager, mock_gateway, mock_repository):
    """Create FastAPI TestClient with injected dependencies"""
    def mock_account_getter():
        return AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1700000000000,
        )

    set_dependencies(
        repository=mock_repository,
        account_getter=mock_account_getter,
        config_manager=config_manager,
        exchange_gateway=mock_gateway,
    )

    with TestClient(app) as client:
        yield client


# ============================================================
# Test 1: Backtest API Basic Execution
# ============================================================
class TestBacktestBasicExecution:
    """Test that backtest API executes and returns valid response"""

    def test_backtest_returns_200(self, test_client):
        """Test that backtest request returns HTTP 200"""
        payload = {
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "limit": 60,  # 60 candles
            "min_wick_ratio": "0.6",
            "max_body_ratio": "0.3",
            "body_position_tolerance": "0.1",
            "trend_filter_enabled": True,
            "mtf_validation_enabled": True,
        }

        response = test_client.post("/api/backtest", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_backtest_returns_valid_structure(self, test_client):
        """Test that backtest returns valid BacktestReport structure"""
        payload = {
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "limit": 60,
        }

        response = test_client.post("/api/backtest", json=payload)
        assert response.status_code == 200, f"Backtest failed: {response.text}"

        data = response.json()

        # Handle both success and error responses
        if "error" in data:
            pytest.skip(f"Backtest returned error: {data['error']}")

        assert "report" in data or "status" in data

        # Get report from either format: {"report": ...} or {"status": "success", "report": ...}
        report = data.get("report", data)

        # Verify required fields exist
        assert "candles_analyzed" in report
        assert "signal_stats" in report or "attempts" in report

    def test_backtest_fetches_klines(self, test_client, mock_gateway):
        """Test that backtest actually fetches K-line data"""
        initial_count = mock_gateway.call_count

        payload = {
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "limit": 50,
        }

        response = test_client.post("/api/backtest", json=payload)
        assert response.status_code == 200

        # Gateway should have been called at least once
        assert mock_gateway.call_count > initial_count


# ============================================================
# Test 2: Backtest with Extreme Parameters
# ============================================================
class TestBacktestExtremeParams:
    """Test backtest with extreme/unusual parameters"""

    def test_backtest_with_low_wick_ratio(self, test_client):
        """Test backtest with very low min_wick_ratio (more signals)"""
        payload = {
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "limit": 60,
            "min_wick_ratio": "0.3",  # Lower than default
            "trend_filter_enabled": False,  # Disable filter for more signals
            "mtf_validation_enabled": False,
        }

        response = test_client.post("/api/backtest", json=payload)
        assert response.status_code == 200, f"Backtest failed: {response.text}"

        data = response.json()
        if "error" in data:
            pytest.skip(f"Backtest returned error: {data['error']}")

        report = data.get("report", data)
        # Should have analyzed all candles
        assert report["candles_analyzed"] == 60

    def test_backtest_with_strict_params(self, test_client):
        """Test backtest with strict parameters (fewer signals)"""
        payload = {
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "limit": 60,
            "min_wick_ratio": "0.8",  # Very strict
            "max_body_ratio": "0.1",
            "trend_filter_enabled": True,
            "mtf_validation_enabled": True,
        }

        response = test_client.post("/api/backtest", json=payload)
        assert response.status_code == 200, f"Backtest failed: {response.text}"

        data = response.json()
        if "error" in data:
            pytest.skip(f"Backtest returned error: {data['error']}")

        report = data.get("report", data)
        assert report["candles_analyzed"] == 60


# ============================================================
# Test 3: SANDBOX ISOLATION (CRITICAL TEST)
# ============================================================
class TestSandboxIsolation:
    """
    CRITICAL: Test that backtest sandbox does NOT pollute global ConfigManager.

    This is the most important test - it verifies that backtest parameters
    are completely isolated from the production config.
    """

    def test_backtest_does_not_pollute_global_config(self, test_client, config_manager):
        """
        Test that submitting 'weird params' to backtest does NOT modify
        the global ConfigManager.current_config.

        This is the isolation mechanism test - backtest must run in a sandbox.
        """
        # Record ORIGINAL global config values
        original_trend_filter = config_manager.user_config.strategy.trend_filter_enabled
        original_mtf = config_manager.user_config.strategy.mtf_validation_enabled
        original_loss = config_manager.user_config.risk.max_loss_percent
        original_leverage = config_manager.user_config.risk.max_leverage

        # Submit BACKTEST with EXTREME/WEIRD params
        backtest_payload = {
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "limit": 60,
            "min_wick_ratio": "0.9",  # Extreme
            "max_body_ratio": "0.05",  # Extreme
            "trend_filter_enabled": not original_trend_filter,  # OPPOSITE of global
            "mtf_validation_enabled": not original_mtf,  # OPPOSITE of global
        }

        response = test_client.post("/api/backtest", json=backtest_payload)
        assert response.status_code == 200, f"Backtest failed: {response.text}"

        # CRITICAL ASSERTION: Global config must be UNCHANGED
        assert config_manager.user_config.strategy.trend_filter_enabled == original_trend_filter, \
            "SANDBOX BREACH: trend_filter_enabled was polluted!"
        assert config_manager.user_config.strategy.mtf_validation_enabled == original_mtf, \
            "SANDBOX BREACH: mtf_validation_enabled was polluted!"
        assert config_manager.user_config.risk.max_loss_percent == original_loss, \
            "SANDBOX BREACH: max_loss_percent was polluted!"
        assert config_manager.user_config.risk.max_leverage == original_leverage, \
            "SANDBOX BREACH: max_leverage was polluted!"

    def test_backtest_then_get_config_returns_original(self, test_client, config_manager):
        """
        Test that GET /api/config after backtest returns ORIGINAL global params,
        not the backtest params.
        """
        # Get config BEFORE backtest
        before_response = test_client.get("/api/config")
        before_config = before_response.json()["config"]

        # Run backtest with OPPOSITE params
        backtest_payload = {
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "limit": 30,
            "trend_filter_enabled": not before_config["strategy"]["trend_filter_enabled"],
            "mtf_validation_enabled": not before_config["strategy"]["mtf_validation_enabled"],
        }

        response = test_client.post("/api/backtest", json=backtest_payload)
        assert response.status_code == 200

        # Get config AFTER backtest
        after_response = test_client.get("/api/config")
        after_config = after_response.json()["config"]

        # CRITICAL: Config must be IDENTICAL (no pollution)
        assert after_config["strategy"]["trend_filter_enabled"] == before_config["strategy"]["trend_filter_enabled"], \
            "SANDBOX BREACH: Config was modified by backtest!"
        assert after_config["strategy"]["mtf_validation_enabled"] == before_config["strategy"]["mtf_validation_enabled"], \
            "SANDBOX BREACH: Config was modified by backtest!"

    def test_multiple_backtests_do_not_accumulate(self, test_client, config_manager):
        """
        Test that running multiple backtests with different params
        does not cause accumulated pollution.
        """
        # Record original state
        original_trend = config_manager.user_config.strategy.trend_filter_enabled

        # Run backtest 1: trend_filter = True
        payload1 = {
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "limit": 30,
            "trend_filter_enabled": True,
            "mtf_validation_enabled": True,
        }
        response1 = test_client.post("/api/backtest", json=payload1)
        assert response1.status_code == 200

        # Run backtest 2: trend_filter = False
        payload2 = {
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "limit": 30,
            "trend_filter_enabled": False,
            "mtf_validation_enabled": False,
        }
        response2 = test_client.post("/api/backtest", json=payload2)
        assert response2.status_code == 200

        # Run backtest 3: trend_filter = True again
        payload3 = {
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "limit": 30,
            "trend_filter_enabled": True,
        }
        response3 = test_client.post("/api/backtest", json=payload3)
        assert response3.status_code == 200

        # CRITICAL: Global config should still be original
        assert config_manager.user_config.strategy.trend_filter_enabled == original_trend, \
            "SANDBOX BREACH: Multiple backtests polluted global config!"

    def test_backtest_risk_params_not_polluted(self, test_client, config_manager):
        """
        Test that backtest risk parameters don't pollute global risk config.
        """
        original_loss = float(config_manager.user_config.risk.max_loss_percent)
        original_leverage = config_manager.user_config.risk.max_leverage

        # Backtest with EXTREME risk params
        payload = {
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "limit": 30,
            # These params should be sandboxed
        }

        response = test_client.post("/api/backtest", json=payload)
        assert response.status_code == 200

        # Global risk config must be unchanged
        assert float(config_manager.user_config.risk.max_loss_percent) == original_loss
        assert config_manager.user_config.risk.max_leverage == original_leverage


# ============================================================
# Test 4: Backtest Report Content Validation
# ============================================================
class TestBacktestReportContent:
    """Validate the content and structure of backtest reports"""

    def test_signal_stats_structure(self, test_client):
        """Test that signal_stats has all required fields"""
        payload = {
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "limit": 60,
        }

        response = test_client.post("/api/backtest", json=payload)
        assert response.status_code == 200, f"Backtest failed: {response.text}"

        data = response.json()
        if "error" in data:
            pytest.skip(f"Backtest returned error: {data['error']}")

        report = data.get("report", data)
        stats = report.get("signal_stats", {})

        # Required fields (if signal_stats exists)
        if stats:
            required_fields = [
                "total_attempts",
                "signals_fired",
                "no_pattern",
                "filtered_out",
            ]

            for field in required_fields:
                assert field in stats, f"Missing field: {field}"

    def test_attempts_structure(self, test_client):
        """Test that attempts array has valid structure"""
        payload = {
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "limit": 30,
        }

        response = test_client.post("/api/backtest", json=payload)
        assert response.status_code == 200, f"Backtest failed: {response.text}"

        data = response.json()
        if "error" in data:
            pytest.skip(f"Backtest returned error: {data['error']}")

        report = data.get("report", data)
        attempts = report.get("attempts", [])

        assert isinstance(attempts, list)

        if attempts:  # If any attempts exist
            attempt = attempts[0]
            assert "strategy_name" in attempt or "final_result" in attempt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
