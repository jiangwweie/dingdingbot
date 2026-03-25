"""
Test Configuration Manager - Config loading, merging, and permission checks.
"""
import os
import tempfile
import pytest
from decimal import Decimal
from pathlib import Path

import yaml

from src.application.config_manager import ConfigManager, load_all_configs
from src.domain.exceptions import FatalStartupError


class TestConfigManager:
    """Test configuration loading and merging"""

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
                    "SOL/USDT:USDT",
                    "BNB/USDT:USDT",
                ],
                "pinbar_defaults": {
                    "min_wick_ratio": "0.6",
                    "max_body_ratio": "0.3",
                    "body_position_tolerance": "0.1",
                },
                "ema": {
                    "period": 60,
                },
                "mtf_mapping": {
                    "15m": "1h",
                    "1h": "4h",
                    "4h": "1d",
                    "1d": "1w",
                },
                "warmup": {
                    "history_bars": 100,
                },
            }

            with open(config_dir / "core.yaml", "w") as f:
                yaml.dump(core_config, f)

            # Create user.yaml
            user_config = {
                "exchange": {
                    "name": "binance",
                    "api_key": "test_api_key_12345",
                    "api_secret": "test_api_secret_67890",
                    "testnet": True,
                },
                "user_symbols": [
                    "XRP/USDT:USDT",
                    "DOGE/USDT:USDT",
                ],
                "timeframes": ["15m", "1h", "4h"],
                "strategy": {
                    "trend_filter_enabled": True,
                    "mtf_validation_enabled": True,
                },
                "risk": {
                    "max_loss_percent": "0.01",
                    "max_leverage": 10,
                },
                "asset_polling": {
                    "interval_seconds": 60,
                },
                "notification": {
                    "channels": [
                        {
                            "type": "feishu",
                            "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test123",
                        }
                    ],
                },
            }

            with open(config_dir / "user.yaml", "w") as f:
                yaml.dump(user_config, f)

            yield config_dir

    def test_load_core_config(self, temp_config_dir):
        """Test loading core configuration"""
        manager = ConfigManager(temp_config_dir)
        core = manager.load_core_config()

        assert core.core_symbols == [
            "BTC/USDT:USDT",
            "ETH/USDT:USDT",
            "SOL/USDT:USDT",
            "BNB/USDT:USDT",
        ]
        assert core.ema.period == 60
        assert core.warmup.history_bars == 100
        assert core.pinbar_defaults.min_wick_ratio == Decimal("0.6")

    def test_load_user_config(self, temp_config_dir):
        """Test loading user configuration"""
        manager = ConfigManager(temp_config_dir)
        user = manager.load_user_config()

        assert user.exchange.name == "binance"
        assert user.exchange.testnet is True
        assert user.timeframes == ["15m", "1h", "4h"]
        assert user.risk.max_loss_percent == Decimal("0.01")
        assert user.risk.max_leverage == 10

    def test_merge_symbols(self, temp_config_dir):
        """Test symbol merging with deduplication"""
        manager = ConfigManager(temp_config_dir)
        manager.load_core_config()
        manager.load_user_config()

        merged = manager.merge_symbols()

        # Core symbols must be included
        assert "BTC/USDT:USDT" in merged
        assert "ETH/USDT:USDT" in merged

        # User symbols must be included
        assert "XRP/USDT:USDT" in merged
        assert "DOGE/USDT:USDT" in merged

        # Core symbols should come first
        assert merged.index("BTC/USDT:USDT") < merged.index("XRP/USDT:USDT")

        # No duplicates
        assert len(merged) == len(set(merged))

    def test_merge_symbols_with_duplicate(self, temp_config_dir):
        """Test that duplicate user symbols are ignored"""
        # Add a duplicate symbol to user config
        with open(temp_config_dir / "user.yaml", "r") as f:
            user_config = yaml.safe_load(f)

        user_config["user_symbols"].append("BTC/USDT:USDT")  # Duplicate

        with open(temp_config_dir / "user.yaml", "w") as f:
            yaml.dump(user_config, f)

        manager = ConfigManager(temp_config_dir)
        manager.load_core_config()
        manager.load_user_config()

        merged = manager.merge_symbols()

        # Should only appear once
        assert merged.count("BTC/USDT:USDT") == 1

    def test_missing_core_config(self):
        """Test error when core.yaml is missing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConfigManager(tmpdir)

            with pytest.raises(FatalStartupError) as exc_info:
                manager.load_core_config()

            assert exc_info.value.error_code == "F-003"

    def test_missing_user_config(self):
        """Test error when user.yaml is missing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConfigManager(tmpdir)

            # Create empty core.yaml
            with open(Path(tmpdir) / "core.yaml", "w") as f:
                yaml.dump({"core_symbols": ["BTC/USDT:USDT"]}, f)

            with pytest.raises(FatalStartupError) as exc_info:
                manager.load_user_config()

            assert exc_info.value.error_code == "F-003"

    def test_invalid_core_config_schema(self, temp_config_dir):
        """Test error when core.yaml has invalid schema"""
        # Remove required field
        with open(temp_config_dir / "core.yaml", "w") as f:
            yaml.dump({"core_symbols": ["BTC/USDT:USDT"]}, f)  # Missing other required fields

        manager = ConfigManager(temp_config_dir)

        with pytest.raises(FatalStartupError) as exc_info:
            manager.load_core_config()

        assert exc_info.value.error_code == "F-003"

    def test_invalid_user_config_schema(self, temp_config_dir):
        """Test error when user.yaml has invalid schema"""
        # Remove required field
        with open(temp_config_dir / "user.yaml", "w") as f:
            yaml.dump({"exchange": {"name": "binance"}}, f)  # Missing api_key, api_secret

        manager = ConfigManager(temp_config_dir)
        manager.load_core_config()

        with pytest.raises(FatalStartupError) as exc_info:
            manager.load_user_config()

        assert exc_info.value.error_code == "F-003"

    def test_load_all_configs_convenience(self, temp_config_dir):
        """Test load_all_configs convenience function"""
        manager = load_all_configs(temp_config_dir)

        assert manager.core_config is not None
        assert manager.user_config is not None
        assert len(manager.merged_symbols) == 6  # 4 core + 2 user


class TestSecretMasking:
    """Test secret masking in config manager"""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory with test config files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Create minimal core.yaml
            with open(config_dir / "core.yaml", "w") as f:
                yaml.dump({
                    "core_symbols": ["BTC/USDT:USDT"],
                    "pinbar_defaults": {
                        "min_wick_ratio": "0.6",
                        "max_body_ratio": "0.3",
                        "body_position_tolerance": "0.1",
                    },
                    "ema": {"period": 60},
                    "mtf_mapping": {"15m": "1h"},
                    "warmup": {"history_bars": 100},
                }, f)

            # Create user.yaml
            with open(config_dir / "user.yaml", "w") as f:
                yaml.dump({
                    "exchange": {
                        "name": "binance",
                        "api_key": "sk_test_abcdefghijklmnop",
                        "api_secret": "secret_1234567890abcdef",
                        "testnet": True,
                    },
                    "user_symbols": [],
                    "timeframes": ["1h"],
                    "strategy": {
                        "trend_filter_enabled": True,
                        "mtf_validation_enabled": True,
                    },
                    "risk": {
                        "max_loss_percent": "0.01",
                        "max_leverage": 10,
                    },
                    "notification": {
                        "channels": [{
                            "type": "feishu",
                            "webhook_url": "https://hook.test/webhook/abc123",
                        }],
                    },
                }, f)

            yield config_dir

    def test_secrets_registered_on_load(self, temp_config_dir, caplog):
        """Test that secrets are registered for masking"""
        import logging
        logging.getLogger().setLevel(logging.INFO)

        manager = load_all_configs(temp_config_dir)

        # Config should load successfully
        assert manager.user_config.exchange.api_key == "sk_test_abcdefghijklmnop"
