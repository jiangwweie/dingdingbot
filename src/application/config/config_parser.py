"""
ConfigParser - Configuration Parsing Layer

Responsibility:
- YAML ↔ Dict conversion
- Decimal precision preservation
- Pydantic model validation

This is the lowest layer in the three-tier architecture:
    ConfigService → ConfigRepository → ConfigParser
"""
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import BaseModel

from src.application.config.models import (
    CoreConfig,
    UserConfig,
    RiskConfig,
)
from src.infrastructure.logger import mask_secret

logger = logging.getLogger(__name__)


# ============================================================
# Decimal Serialization Helpers (P1-1修复逻辑复用)
# ============================================================

def _decimal_representer(dumper, data) -> yaml.Node:
    """
    Represent Decimal as string to preserve precision during YAML serialization.

    Args:
        dumper: YAML dumper instance
        data: Decimal value to serialize

    Returns:
        YAML scalar node with string representation
    """
    return dumper.represent_scalar('tag:yaml.org,2002:str', str(data))


def _decimal_constructor(loader, node) -> Decimal:
    """
    Construct Decimal from string during YAML deserialization.

    Args:
        loader: YAML loader instance
        node: YAML scalar node

    Returns:
        Decimal value from string representation
    """
    value = loader.construct_scalar(node)
    return Decimal(value)


# Register Decimal representer and constructor for YAML
# Use custom !decimal tag to avoid hijacking all YAML string parsing.
# Only values explicitly marked as !decimal in YAML will be converted to Decimal.
yaml.add_representer(Decimal, _decimal_representer)
yaml.add_constructor('!decimal', _decimal_constructor)
# Also register on SafeLoader/SafeDumper for safe_dump/safe_load compatibility
yaml.add_representer(Decimal, _decimal_representer, Dumper=yaml.SafeDumper)
yaml.add_constructor('!decimal', _decimal_constructor, Loader=yaml.SafeLoader)


def _convert_decimals_to_str(obj: Any) -> Any:
    """
    Recursively convert all Decimal values in a dict/list to string for JSON/YAML serialization.
    Also converts Pydantic models to dicts.

    This preserves full precision without float conversion errors.

    Args:
        obj: Object to convert (dict, list, Decimal, or Pydantic model)

    Returns:
        Object with all Decimal values converted to strings and Pydantic models converted to dicts
    """
    if isinstance(obj, BaseModel):
        # Convert Pydantic model to dict recursively
        return _convert_decimals_to_str(obj.model_dump(mode='python'))
    elif isinstance(obj, Decimal):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: _convert_decimals_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals_to_str(item) for item in obj]
    return obj


# ============================================================
# ConfigParser Class
# ============================================================

class ConfigParser:
    """
    Configuration parser - responsible for YAML/JSON parsing and serialization.

    Responsibilities:
    - YAML ↔ Dict conversion
    - Decimal precision preservation
    - Pydantic model validation

    Usage:
        parser = ConfigParser()

        # Parse YAML file
        config_dir = Path('./config')
        core_data = parser.parse_yaml_file(config_dir / 'core.yaml')
        core_config = parser.parse_core_config(core_data)

        # Serialize to YAML
        yaml_str = parser.dump_to_yaml(core_config.model_dump())
    """

    def __init__(self):
        """Initialize ConfigParser with default settings."""
        self._logger = logging.getLogger(__name__)

    # ============================================================
    # Public API - File Operations
    # ============================================================

    def parse_yaml_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Parse YAML file to dictionary.

        Args:
            file_path: Path to YAML file

        Returns:
            Parsed dictionary

        Raises:
            FileNotFoundError: If file does not exist
            yaml.YAMLError: If YAML syntax is invalid
        """
        if not file_path.exists():
            raise FileNotFoundError(f"YAML file not found: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return data if data is not None else {}
        except yaml.YAMLError as e:
            self._logger.error(f"YAML parse error for {file_path}: {e}")
            raise

    def dump_to_yaml(self, data: Dict[str, Any]) -> str:
        """
        Serialize dictionary to YAML string with Decimal precision preservation.

        Args:
            data: Dictionary to serialize (may contain Decimal values)

        Returns:
            YAML string representation
        """
        # Convert Decimals to strings for proper serialization
        normalized_data = _convert_decimals_to_str(data)

        return yaml.dump(
            normalized_data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    # ============================================================
    # Public API - Model Parsing
    # ============================================================

    def parse_core_config(self, data: Dict[str, Any]) -> CoreConfig:
        """
        Parse core configuration from dictionary.

        Args:
            data: Dictionary containing core configuration

        Returns:
            Validated CoreConfig instance

        Raises:
            ValidationError: If configuration validation fails
        """
        try:
            return CoreConfig(**data)
        except Exception as e:
            self._logger.error(f"CoreConfig validation failed: {e}")
            raise

    def parse_user_config(self, data: Dict[str, Any]) -> UserConfig:
        """
        Parse user configuration from dictionary.

        Args:
            data: Dictionary containing user configuration

        Returns:
            Validated UserConfig instance

        Raises:
            ValidationError: If configuration validation fails
        """
        try:
            return UserConfig(**data)
        except Exception as e:
            self._logger.error(f"UserConfig validation failed: {e}")
            raise

    def parse_risk_config(self, data: Dict[str, Any]) -> RiskConfig:
        """
        Parse risk configuration from dictionary.

        Args:
            data: Dictionary containing risk configuration

        Returns:
            Validated RiskConfig instance

        Raises:
            ValidationError: If configuration validation fails
        """
        try:
            return RiskConfig(**data)
        except Exception as e:
            self._logger.error(f"RiskConfig validation failed: {e}")
            raise

    # ============================================================
    # Fallback Config Builders (迁移自 ConfigManager)
    # ============================================================

    def create_default_core_config(self) -> CoreConfig:
        """
        Create default core configuration.

        Used as fallback when YAML file is missing or corrupted.

        Returns:
            Default CoreConfig instance
        """
        from src.application.config.models import (
            PinbarDefaults,
            EmaConfig,
            MtfMapping,
            WarmupConfig,
            SignalPipelineConfig,
            AtrConfig,
        )

        return CoreConfig(
            core_symbols=["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"],
            pinbar_defaults=PinbarDefaults(
                min_wick_ratio=Decimal("0.6"),
                max_body_ratio=Decimal("0.3"),
                body_position_tolerance=Decimal("0.1"),
            ),
            ema=EmaConfig(period=60),
            mtf_mapping=MtfMapping(**{"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w"}),
            mtf_ema_period=60,
            warmup=WarmupConfig(history_bars=100),
            signal_pipeline=SignalPipelineConfig(cooldown_seconds=14400),
            atr=AtrConfig(enabled=True, period=14, min_ratio=Decimal("0.5")),
        )

    def create_default_user_config(self) -> UserConfig:
        """
        Create default user configuration.

        Used as fallback when YAML file is missing or corrupted.

        Returns:
            Default UserConfig instance
        """
        from src.application.config.models import (
            ExchangeConfig,
            RiskConfig,
            NotificationConfig,
            NotificationChannel,
        )

        return UserConfig(
            exchange=ExchangeConfig(
                name="binance",
                api_key="placeholder",
                api_secret="placeholder",
                testnet=True,
            ),
            timeframes=["15m", "1h"],
            risk=RiskConfig(
                max_loss_percent=Decimal("0.01"),
                max_leverage=10,
                max_total_exposure=Decimal("0.8"),
            ),
            notification=NotificationConfig(
                channels=[NotificationChannel(
                    type="feishu",
                    webhook_url="https://placeholder",
                )]
            ),
        )
