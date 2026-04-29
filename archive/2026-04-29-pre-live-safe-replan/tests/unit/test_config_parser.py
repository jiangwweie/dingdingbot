"""
ConfigParser Unit Tests

Tests for the ConfigParser class:
- YAML file parsing
- Decimal precision preservation (P1-1)
- Pydantic model validation
- Error handling
- Roundtrip serialization

Coverage target: >= 95%
"""
import os
import pytest
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any

import yaml

from src.application.config.config_parser import (
    ConfigParser,
    _decimal_representer,
    _decimal_constructor,
    _convert_decimals_to_str,
)
from src.application.config.models import (
    CoreConfig,
    UserConfig,
    RiskConfig,
    PinbarDefaults,
    EmaConfig,
    MtfMapping,
    WarmupConfig,
    SignalPipelineConfig,
    AtrConfig,
)


# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
def parser():
    """Create ConfigParser instance for testing."""
    return ConfigParser()


@pytest.fixture
def temp_yaml_file():
    """Create a temporary YAML file for testing."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    yield path
    if os.path.exists(path):
        os.close(fd)
        os.remove(path)


@pytest.fixture
def fixtures_dir() -> Path:
    """Get path to test fixtures directory."""
    return Path(__file__).parent.parent / "fixtures" / "config_parser"


@pytest.fixture
def sample_core_data() -> Dict[str, Any]:
    """Sample core configuration data."""
    return {
        "core_symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
        "pinbar_defaults": {
            "min_wick_ratio": "0.6",
            "max_body_ratio": "0.3",
            "body_position_tolerance": "0.1",
        },
        "ema": {"period": 60},
        "mtf_ema_period": 60,
        "mtf_mapping": {"15m": "1h", "1h": "4h"},
        "warmup": {"history_bars": 100},
        "signal_pipeline": {"cooldown_seconds": 14400},
        "atr": {"enabled": True, "period": 14, "min_ratio": "0.5"},
    }


@pytest.fixture
def sample_risk_data() -> Dict[str, Any]:
    """Sample risk configuration data."""
    return {
        "max_loss_percent": "0.01",
        "max_leverage": 20,
        "max_total_exposure": "0.9",
    }


@pytest.fixture
def decimal_test_values():
    """Decimal values for precision testing."""
    return [
        Decimal("0.01"),
        Decimal("0.12345678901234567890"),
        Decimal("0"),
        Decimal("-0.005"),
        Decimal("999999.999999"),
        Decimal("0.0075"),
    ]


# ============================================================
# YAML Parsing Tests
# ============================================================

class TestYamlParsing:
    """Tests for YAML file parsing functionality."""

    def test_parse_yaml_file_valid(self, parser, fixtures_dir):
        """Test parsing valid YAML file."""
        yaml_path = fixtures_dir / "core_valid.yaml"
        data = parser.parse_yaml_file(yaml_path)

        assert isinstance(data, dict)
        assert "core_symbols" in data
        assert len(data["core_symbols"]) == 4
        assert "BTC/USDT:USDT" in data["core_symbols"]

    def test_parse_yaml_file_not_found(self, parser):
        """Test FileNotFoundError when file does not exist."""
        non_existent_path = Path("/non/existent/path.yaml")

        with pytest.raises(FileNotFoundError) as exc_info:
            parser.parse_yaml_file(non_existent_path)

        assert "YAML file not found" in str(exc_info.value)

    def test_parse_yaml_file_invalid_syntax(self, parser, fixtures_dir):
        """Test YAML syntax error handling."""
        yaml_path = fixtures_dir / "invalid_syntax.yaml"

        with pytest.raises(yaml.YAMLError):
            parser.parse_yaml_file(yaml_path)

    def test_parse_yaml_file_empty(self, parser, fixtures_dir):
        """Test empty YAML file returns empty dict."""
        yaml_path = fixtures_dir / "empty.yaml"
        data = parser.parse_yaml_file(yaml_path)

        assert isinstance(data, dict)
        assert len(data) == 0

    def test_parse_yaml_file_with_unicode(self, parser, temp_yaml_file):
        """Test parsing YAML with Unicode content."""
        yaml_content = """
strategies:
  - name: 测试策略
    description: テスト戦略
    trigger:
      type: pinbar
      enabled: true
"""
        with open(temp_yaml_file, 'w', encoding='utf-8') as f:
            f.write(yaml_content)

        data = parser.parse_yaml_file(Path(temp_yaml_file))

        assert "strategies" in data
        assert data["strategies"][0]["name"] == "测试策略"


# ============================================================
# Decimal Precision Tests (P1-1 Core)
# ============================================================

class TestDecimalPrecision:
    """Tests for Decimal precision preservation (P1-1)."""

    def test_decimal_representer_preserves_precision(self, parser):
        """Test that Decimal representer preserves 20+ digit precision."""
        original = Decimal("0.12345678901234567890")

        # Create a dummy dumper for testing
        class DummyDumper:
            def represent_scalar(self, tag, value):
                return tag, value

        dumper = DummyDumper()
        tag, value = _decimal_representer(dumper, original)

        assert value == "0.12345678901234567890"

    def test_decimal_constructor_restores_precision(self, parser):
        """Test that Decimal constructor restores precision from string."""
        class DummyLoader:
            def construct_scalar(self, node):
                return node

        loader = DummyLoader()
        result = _decimal_constructor(loader, "0.12345678901234567890")

        assert isinstance(result, Decimal)
        assert result == Decimal("0.12345678901234567890")

    def test_decimal_in_complex_config(self, parser):
        """Test Decimal precision in complex nested configuration."""
        config = {
            "risk": {
                "max_loss_percent": Decimal("0.01"),
                "max_leverage": 20,
                "stop_loss_ratio": Decimal("1.5"),
            },
            "nested": {
                "values": [Decimal("0.001"), Decimal("0.002")],
                "deep": {
                    "precision": Decimal("0.123456789"),
                }
            }
        }

        yaml_str = parser.dump_to_yaml(config)
        loaded = yaml.safe_load(yaml_str)

        # Verify precision preserved as strings
        assert loaded["risk"]["max_loss_percent"] == "0.01"
        assert loaded["risk"]["stop_loss_ratio"] == "1.5"
        assert loaded["nested"]["values"][0] == "0.001"
        assert loaded["nested"]["values"][1] == "0.002"
        assert loaded["nested"]["deep"]["precision"] == "0.123456789"

    def test_decimal_zero_and_negative(self, parser):
        """Test Decimal handling for zero and negative values."""
        config = {
            "zero": Decimal("0"),
            "negative": Decimal("-0.005"),
        }

        yaml_str = parser.dump_to_yaml(config)
        loaded = yaml.safe_load(yaml_str)

        assert loaded["zero"] == "0"
        assert loaded["negative"] == "-0.005"

    def test_decimal_very_large_value(self, parser):
        """Test Decimal handling for very large values."""
        large_value = Decimal("999999999.999999999")
        config = {"large": large_value}

        yaml_str = parser.dump_to_yaml(config)
        loaded = yaml.safe_load(yaml_str)

        assert loaded["large"] == "999999999.999999999"

    def test_dump_to_yaml_with_decimal(self, parser):
        """Test YAML serialization with Decimal values."""
        data = {
            "risk": {
                "max_loss_percent": Decimal("0.0075"),
                "max_leverage": 15,
            }
        }

        yaml_str = parser.dump_to_yaml(data)

        # Verify Decimal is serialized as string
        assert "0.0075" in yaml_str
        assert "max_leverage: 15" in yaml_str

    def test_roundtrip_preserves_decimal_precision(self, parser, decimal_test_values):
        """Test roundtrip serialization preserves all Decimal precision."""
        for original in decimal_test_values:
            data = {"value": original}

            # Roundtrip
            yaml_str = parser.dump_to_yaml(data)
            loaded = yaml.safe_load(yaml_str)

            # Convert back to Decimal and verify
            assert Decimal(loaded["value"]) == original


# ============================================================
# Model Validation Tests
# ============================================================

class TestModelValidation:
    """Tests for Pydantic model validation."""

    def test_parse_core_config_valid(self, parser, sample_core_data):
        """Test parsing valid core configuration."""
        config = parser.parse_core_config(sample_core_data)

        assert isinstance(config, CoreConfig)
        assert len(config.core_symbols) == 2
        assert config.ema.period == 60
        assert config.mtf_ema_period == 60

    def test_parse_core_config_missing_field(self, parser):
        """Test core config validation fails with missing required field."""
        incomplete_data = {
            "core_symbols": ["BTC/USDT:USDT"],
            # Missing pinbar_defaults, ema, etc.
        }

        with pytest.raises(Exception) as exc_info:
            parser.parse_core_config(incomplete_data)

        assert "validation" in str(exc_info.value).lower() or "CoreConfig" in str(exc_info.value)

    def test_parse_core_config_invalid_value(self, parser):
        """Test core config validation fails with invalid value."""
        invalid_data = {
            "core_symbols": [],  # Empty list violates min_length
            "pinbar_defaults": {
                "min_wick_ratio": "0.6",
                "max_body_ratio": "0.3",
                "body_position_tolerance": "0.1",
            },
            "ema": {"period": 60},
            "mtf_ema_period": 60,
            "mtf_mapping": {},
            "warmup": {"history_bars": 100},
            "signal_pipeline": {"cooldown_seconds": 14400},
            "atr": {"enabled": True, "period": 14, "min_ratio": "0.5"},
        }

        with pytest.raises(Exception):
            parser.parse_core_config(invalid_data)

    def test_parse_user_config_valid(self, parser):
        """Test parsing valid user configuration."""
        user_data = {
            "exchange": {
                "name": "binance",
                "api_key": "test_key",
                "api_secret": "test_secret",
                "testnet": True,
            },
            "timeframes": ["15m", "1h"],
            "risk": {
                "max_loss_percent": "0.01",
                "max_leverage": 10,
            },
            "notification": {
                "channels": [
                    {
                        "type": "feishu",
                        "webhook_url": "https://test.webhook.com",
                    }
                ]
            },
        }

        config = parser.parse_user_config(user_data)

        assert isinstance(config, UserConfig)
        assert config.exchange.name == "binance"
        assert len(config.timeframes) == 2

    def test_parse_risk_config_valid(self, parser, sample_risk_data):
        """Test parsing valid risk configuration."""
        config = parser.parse_risk_config(sample_risk_data)

        assert isinstance(config, RiskConfig)
        assert config.max_loss_percent == Decimal("0.01")
        assert config.max_leverage == 20
        assert config.max_total_exposure == Decimal("0.9")

    def test_parse_risk_config_invalid_percent(self, parser):
        """Test risk config validation fails with invalid percent."""
        invalid_data = {
            "max_loss_percent": "invalid",
            "max_leverage": 10,
        }

        with pytest.raises(Exception):
            parser.parse_risk_config(invalid_data)

    def test_parse_risk_config_percent_validation(self, parser):
        """Test risk config percent values are validated correctly."""
        # Test with valid decimal string
        valid_data = {
            "max_loss_percent": "0.02",
            "max_leverage": 20,
        }
        config = parser.parse_risk_config(valid_data)
        assert config.max_loss_percent == Decimal("0.02")


# ============================================================
# Serialization Tests
# ============================================================

class TestSerialization:
    """Tests for YAML serialization."""

    def test_dump_to_yaml_basic(self, parser):
        """Test basic YAML serialization."""
        data = {
            "name": "test",
            "value": 123,
            "nested": {"key": "value"},
        }

        yaml_str = parser.dump_to_yaml(data)

        assert "name: test" in yaml_str
        assert "value: 123" in yaml_str
        assert "key: value" in yaml_str

    def test_dump_to_yaml_with_unicode(self, parser):
        """Test YAML serialization with Unicode content."""
        data = {
            "strategy_name": "测试策略",
            "description": "テスト戦略",
        }

        yaml_str = parser.dump_to_yaml(data)

        assert "测试策略" in yaml_str
        assert "テスト戦略" in yaml_str

    def test_roundtrip_yaml_serialization(self, parser):
        """Test roundtrip serialization (parse -> serialize -> parse)."""
        original = {
            "risk": {
                "max_loss_percent": "0.01",
                "max_leverage": 20,
            },
            "symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
        }

        # Roundtrip
        yaml_str = parser.dump_to_yaml(original)
        loaded = yaml.safe_load(yaml_str)

        assert loaded["risk"]["max_loss_percent"] == "0.01"
        assert loaded["risk"]["max_leverage"] == 20
        assert loaded["symbols"] == original["symbols"]

    def test_convert_decimals_to_str_recursive(self):
        """Test _convert_decimals_to_str handles nested structures."""
        data = {
            "level1": {
                "level2": {
                    "value": Decimal("0.123"),
                    "list": [Decimal("1.1"), Decimal("2.2")],
                },
                "direct": Decimal("3.3"),
            }
        }

        result = _convert_decimals_to_str(data)

        assert result["level1"]["level2"]["value"] == "0.123"
        assert result["level1"]["level2"]["list"] == ["1.1", "2.2"]
        assert result["level1"]["direct"] == "3.3"

    def test_convert_decimals_to_str_non_decimal_unchanged(self):
        """Test _convert_decimals_to_str leaves non-Decimals unchanged."""
        data = {
            "string": "hello",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "none": None,
        }

        result = _convert_decimals_to_str(data)

        assert result["string"] == "hello"
        assert result["int"] == 42
        assert result["float"] == 3.14
        assert result["bool"] is True
        assert result["none"] is None


# ============================================================
# Integration Tests
# ============================================================

class TestIntegration:
    """Integration tests for ConfigParser."""

    def test_create_default_core_config(self, parser):
        """Test default core config creation."""
        config = parser.create_default_core_config()

        assert isinstance(config, CoreConfig)
        assert len(config.core_symbols) == 4
        assert config.pinbar_defaults.min_wick_ratio == Decimal("0.6")

    def test_create_default_user_config(self, parser):
        """Test default user config creation."""
        config = parser.create_default_user_config()

        assert isinstance(config, UserConfig)
        assert config.risk.max_loss_percent == Decimal("0.01")
        assert len(config.notification.channels) == 1

    def test_full_config_workflow(self, parser, tmp_path):
        """Test complete configuration workflow: create -> save -> load."""
        # Create a test YAML file
        yaml_path = tmp_path / "test_config.yaml"
        test_data = {
            "core_symbols": ["BTC/USDT:USDT"],
            "pinbar_defaults": {
                "min_wick_ratio": "0.7",
                "max_body_ratio": "0.25",
                "body_position_tolerance": "0.15",
            },
            "ema": {"period": 55},
            "mtf_ema_period": 55,
            "mtf_mapping": {"15m": "1h"},
            "warmup": {"history_bars": 80},
            "signal_pipeline": {"cooldown_seconds": 7200},
            "atr": {"enabled": True, "period": 14, "min_ratio": "0.6"},
        }

        # Save to YAML
        yaml_str = parser.dump_to_yaml(test_data)
        with open(yaml_path, 'w', encoding='utf-8') as f:
            f.write(yaml_str)

        # Load and parse
        loaded_data = parser.parse_yaml_file(yaml_path)
        config = parser.parse_core_config(loaded_data)

        assert config.core_symbols == ["BTC/USDT:USDT"]
        assert config.ema.period == 55


# ============================================================
# Edge Cases
# ============================================================

class TestEdgeCases:
    """Edge case tests for ConfigParser."""

    def test_parse_yaml_file_none_content(self, parser, temp_yaml_file):
        """Test parsing YAML file with null content."""
        with open(temp_yaml_file, 'w') as f:
            f.write("null")

        data = parser.parse_yaml_file(Path(temp_yaml_file))
        assert isinstance(data, dict)
        assert len(data) == 0

    def test_dump_to_yaml_empty_dict(self, parser):
        """Test serializing empty dictionary."""
        yaml_str = parser.dump_to_yaml({})
        assert yaml_str.strip() == "" or yaml_str == "{}\n"

    def test_parse_core_config_with_decimal_strings(self, parser):
        """Test core config parsing accepts decimal strings."""
        data = {
            "core_symbols": ["BTC/USDT:USDT"],
            "pinbar_defaults": {
                "min_wick_ratio": "0.6",
                "max_body_ratio": "0.3",
                "body_position_tolerance": "0.1",
            },
            "ema": {"period": 60},
            "mtf_ema_period": 60,
            "mtf_mapping": {"15m": "1h"},
            "warmup": {"history_bars": 100},
            "signal_pipeline": {"cooldown_seconds": 14400},
            "atr": {"enabled": True, "period": 14, "min_ratio": "0.5"},
        }

        config = parser.parse_core_config(data)

        assert isinstance(config.pinbar_defaults.min_wick_ratio, Decimal)
        assert config.pinbar_defaults.min_wick_ratio == Decimal("0.6")

    def test_parse_risk_config_with_decimal_strings(self, parser):
        """Test risk config parsing accepts decimal strings."""
        data = {
            "max_loss_percent": "0.015",
            "max_leverage": 15,
            "max_total_exposure": "0.85",
        }

        config = parser.parse_risk_config(data)

        assert isinstance(config.max_loss_percent, Decimal)
        assert config.max_loss_percent == Decimal("0.015")
        assert isinstance(config.max_total_exposure, Decimal)
        assert config.max_total_exposure == Decimal("0.85")

    def test_parse_user_config_validation_error(self, parser):
        """Test parse_user_config raises on validation error."""
        invalid_data = {
            "exchange": {
                "name": "binance",
                # Missing required fields
            },
            "timeframes": [],  # Empty list violates min_length
        }

        with pytest.raises(Exception):
            parser.parse_user_config(invalid_data)

    def test_parse_risk_config_error_logging(self, parser, caplog):
        """Test that parse_risk_config logs errors on validation failure."""
        import logging
        parser._logger = logging.getLogger(__name__)

        invalid_data = {
            "max_loss_percent": "not_a_number",
            "max_leverage": 10,
        }

        with pytest.raises(Exception):
            parser.parse_risk_config(invalid_data)

        # Verify error was logged
        assert any("RiskConfig validation failed" in record.message for record in caplog.records)


# ============================================================
# Main entry point
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src/application/config/config_parser"])
