"""
Test Configuration Version Tracking (R3.2).

Tests for configuration version number tracking to prevent
stale configuration references during hot-reload.
"""
import asyncio
import pytest
import tempfile
from pathlib import Path
from decimal import Decimal

import yaml

from src.application.config_manager import ConfigManager
from src.application.signal_pipeline import SignalPipeline
from src.application.config_manager import (
    SignalPipelineConfig,
    SignalQueueConfig,
)
from src.domain.models import (
    RiskConfig,
    KlineData,
)


class TestConfigVersionTracking:
    """Test configuration version tracking mechanism"""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory with test config files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Create core.yaml
            core_config = {
                "core_symbols": [
                    "BTC/USDT:USDT",
                    "ETH/USDT:USDT",
                ],
                "pinbar_defaults": {
                    "min_wick_ratio": "0.6",
                    "max_body_ratio": "0.3",
                    "body_position_tolerance": "0.1",
                },
                "ema": {"period": 60},
                "mtf_mapping": {"15m": "1h", "1h": "4h"},
                "warmup": {"history_bars": 100},
            }

            # Create user.yaml
            user_config = {
                "exchange": {
                    "name": "binance",
                    "api_key": "test_api_key",
                    "api_secret": "test_api_secret",
                    "testnet": True,
                },
                "timeframes": ["15m", "1h"],
                "active_strategies": [],
                "risk": {
                    "max_loss_percent": "0.01",
                    "max_leverage": 10,
                    "max_total_exposure": "0.8",
                },
                "notification": {
                    "channels": [
                        {"type": "feishu", "webhook_url": "https://example.com/webhook"}
                    ]
                },
            }

            with open(config_dir / "core.yaml", "w") as f:
                yaml.safe_dump(core_config, f)

            with open(config_dir / "user.yaml", "w") as f:
                yaml.safe_dump(user_config, f)

            yield str(config_dir)

    def test_config_version_initialization(self, temp_config_dir):
        """Test that config version starts at 0"""
        config_manager = ConfigManager(config_dir=temp_config_dir)
        config_manager.load_core_config()
        config_manager.load_user_config()

        assert config_manager.get_config_version() == 0

    @pytest.mark.asyncio
    async def test_config_version_increments_on_notify(self, temp_config_dir):
        """Test that config version increments when observers are notified"""
        config_manager = ConfigManager(config_dir=temp_config_dir)
        config_manager.load_core_config()
        config_manager.load_user_config()

        initial_version = config_manager.get_config_version()
        assert initial_version == 0

        # Add a dummy observer to ensure notification path is exercised
        notified = False
        async def dummy_observer():
            nonlocal notified
            notified = True
        config_manager.add_observer(dummy_observer)

        # Trigger observer notification
        await config_manager._notify_observers()

        new_version = config_manager.get_config_version()
        assert new_version == 1
        assert notified is True

        # Notify again
        await config_manager._notify_observers()

        final_version = config_manager.get_config_version()
        assert final_version == 2

    @pytest.mark.asyncio
    async def test_config_version_concurrent_notifications(self, temp_config_dir):
        """Test that concurrent notifications increment version correctly"""
        config_manager = ConfigManager(config_dir=temp_config_dir)
        config_manager.load_core_config()
        config_manager.load_user_config()

        initial_version = config_manager.get_config_version()
        assert initial_version == 0

        # Add a dummy observer
        async def dummy_observer():
            pass
        config_manager.add_observer(dummy_observer)

        # Fire multiple notifications concurrently
        await asyncio.gather(
            config_manager._notify_observers(),
            config_manager._notify_observers(),
            config_manager._notify_observers(),
        )

        final_version = config_manager.get_config_version()
        # Each notification should increment version
        assert final_version == 3


class TestSignalPipelineConfigVersion:
    """Test SignalPipeline configuration version tracking"""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory with test config files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            core_config = {
                "core_symbols": ["BTC/USDT:USDT"],
                "pinbar_defaults": {
                    "min_wick_ratio": "0.6",
                    "max_body_ratio": "0.3",
                    "body_position_tolerance": "0.1",
                },
                "ema": {"period": 60},
                "mtf_mapping": {"15m": "1h"},
                "warmup": {"history_bars": 100},
            }

            user_config = {
                "exchange": {
                    "name": "binance",
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": True,
                },
                "timeframes": ["15m"],
                "active_strategies": [],
                "risk": {
                    "max_loss_percent": "0.01",
                    "max_leverage": 10,
                    "max_total_exposure": "0.8",
                },
                "notification": {
                    "channels": [
                        {"type": "feishu", "webhook_url": "https://example.com/webhook"}
                    ]
                },
            }

            with open(config_dir / "core.yaml", "w") as f:
                yaml.safe_dump(core_config, f)

            with open(config_dir / "user.yaml", "w") as f:
                yaml.safe_dump(user_config, f)

            yield str(config_dir)

    def test_signal_pipeline_tracks_config_version(self, temp_config_dir):
        """Test that SignalPipeline initializes with config version"""
        config_manager = ConfigManager(config_dir=temp_config_dir)
        config_manager.load_core_config()
        config_manager.load_user_config()

        signal_config = SignalPipelineConfig(
            cooldown_seconds=14400,
            queue=SignalQueueConfig(),
        )
        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
        )

        pipeline = SignalPipeline(
            signal_config=signal_config,
            risk_config=risk_config,
            config_manager=config_manager,
        )

        # Pipeline should track the config version from ConfigManager
        assert pipeline._config_version == config_manager.get_config_version()

    @pytest.mark.asyncio
    async def test_signal_pipeline_refreshes_on_version_mismatch(self, temp_config_dir):
        """Test that SignalPipeline detects version mismatch in process_kline"""
        config_manager = ConfigManager(config_dir=temp_config_dir)
        config_manager.load_core_config()
        config_manager.load_user_config()

        # Add a dummy observer to ensure version increments on notify
        async def dummy_observer():
            pass
        config_manager.add_observer(dummy_observer)

        signal_config = SignalPipelineConfig(
            cooldown_seconds=14400,
            queue=SignalQueueConfig(),
        )
        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
        )

        # First, increment config version (simulating a prior config update)
        await config_manager._notify_observers()
        assert config_manager.get_config_version() == 1

        # Create pipeline AFTER config update
        # Note: Pipeline will initialize with version 1 (current version)
        pipeline = SignalPipeline(
            signal_config=signal_config,
            risk_config=risk_config,
            config_manager=config_manager,
        )

        # Pipeline should have synced to current version on init
        assert pipeline._config_version == 1

        # Now simulate another config update (without pipeline knowing)
        # We manually increment version without notifying observers
        async with config_manager._ensure_config_lock():
            config_manager._config_version += 1
        assert config_manager.get_config_version() == 2

        # Pipeline's tracked version is still old
        assert pipeline._config_version == 1

        # Create a K-line to trigger refresh
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1000000,
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50500"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        # Process K-line (this should detect version mismatch and refresh)
        await pipeline.process_kline(kline)

        # After refresh, pipeline version should match ConfigManager version
        assert pipeline._config_version == config_manager.get_config_version()
        assert pipeline._config_version == 2

    @pytest.mark.asyncio
    async def test_signal_pipeline_on_config_updated_updates_version(self, temp_config_dir):
        """Test that on_config_updated callback updates tracked version"""
        config_manager = ConfigManager(config_dir=temp_config_dir)
        config_manager.load_core_config()
        config_manager.load_user_config()

        signal_config = SignalPipelineConfig(
            cooldown_seconds=14400,
            queue=SignalQueueConfig(),
        )
        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
        )

        # Create pipeline without registering observer
        pipeline = SignalPipeline(
            signal_config=signal_config,
            risk_config=risk_config,
            config_manager=config_manager,
        )

        initial_version = pipeline._config_version

        # Manually increment ConfigManager version (simulating external config update)
        async with config_manager._ensure_config_lock():
            config_manager._config_version += 1

        # Call on_config_updated directly (simulating hot-reload)
        await pipeline.on_config_updated()

        # Version should be updated to match ConfigManager
        assert pipeline._config_version == config_manager.get_config_version()
        assert pipeline._config_version == initial_version + 1


class TestHotReloadConsistency:
    """Test hot-reload consistency with version tracking"""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory with test config files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            core_config = {
                "core_symbols": ["BTC/USDT:USDT"],
                "pinbar_defaults": {
                    "min_wick_ratio": "0.6",
                    "max_body_ratio": "0.3",
                    "body_position_tolerance": "0.1",
                },
                "ema": {"period": 60},
                "mtf_mapping": {"15m": "1h"},
                "warmup": {"history_bars": 100},
            }

            user_config = {
                "exchange": {
                    "name": "binance",
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "testnet": True,
                },
                "timeframes": ["15m"],
                "active_strategies": [],
                "risk": {
                    "max_loss_percent": "0.01",
                    "max_leverage": 10,
                    "max_total_exposure": "0.8",
                },
                "notification": {
                    "channels": [
                        {"type": "feishu", "webhook_url": "https://example.com/webhook"}
                    ]
                },
            }

            with open(config_dir / "core.yaml", "w") as f:
                yaml.safe_dump(core_config, f)

            with open(config_dir / "user.yaml", "w") as f:
                yaml.safe_dump(user_config, f)

            yield str(config_dir)

    @pytest.mark.asyncio
    async def test_config_lock_protects_version_increment(self, temp_config_dir):
        """Test that config lock protects version increment"""
        config_manager = ConfigManager(config_dir=temp_config_dir)
        config_manager.load_core_config()
        config_manager.load_user_config()

        # Ensure config lock is created
        lock = config_manager._ensure_config_lock()
        assert lock is not None

        # Add a dummy observer
        async def dummy_observer():
            pass
        config_manager.add_observer(dummy_observer)

        # Concurrent notifications should each increment version
        initial_version = config_manager.get_config_version()

        await asyncio.gather(
            *[config_manager._notify_observers() for _ in range(5)]
        )

        final_version = config_manager.get_config_version()
        assert final_version == initial_version + 5

    @pytest.mark.asyncio
    async def test_no_stale_reference_with_version_tracking(self, temp_config_dir):
        """Test that version tracking prevents stale configuration references"""
        config_manager = ConfigManager(config_dir=temp_config_dir)
        config_manager.load_core_config()
        config_manager.load_user_config()

        signal_config = SignalPipelineConfig(
            cooldown_seconds=14400,
            queue=SignalQueueConfig(),
        )
        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
        )

        pipeline = SignalPipeline(
            signal_config=signal_config,
            risk_config=risk_config,
            config_manager=config_manager,
        )

        # Store initial config values
        initial_max_loss = pipeline._risk_config.max_loss_percent
        initial_version = pipeline._config_version

        # Manually increment ConfigManager version (simulating external config update)
        async with config_manager._ensure_config_lock():
            config_manager._config_version += 1

        # Trigger hot-reload
        await pipeline.on_config_updated()

        # Config should be refreshed (version should match ConfigManager)
        assert pipeline._config_version == config_manager.get_config_version()
        assert pipeline._config_version == initial_version + 1

        # Verify risk config is still valid (not corrupted)
        assert pipeline._risk_config.max_loss_percent == initial_max_loss
