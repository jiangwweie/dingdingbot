"""
ConfigParser - Configuration Parsing Layer

Responsibility:
- Dict conversion
- Decimal precision preservation
- Pydantic model validation

This is the lowest layer in the three-tier architecture:
    ConfigService → ConfigRepository → ConfigParser
"""
import logging
from decimal import Decimal
from typing import Dict
from src.application.config.models import (
    CoreConfig,
    UserConfig,
    RiskConfig,
)
from src.infrastructure.logger import mask_secret

logger = logging.getLogger(__name__)


# ============================================================
# ConfigParser Class
# ============================================================

class ConfigParser:
    """
    Configuration parser for in-memory dictionaries and Pydantic models.

    Responsibilities:
    - Decimal precision preservation
    - Pydantic model validation

    Usage:
        parser = ConfigParser()
        core_config = parser.parse_core_config(core_data)
    """

    def __init__(self):
        """Initialize ConfigParser with default settings."""
        self._logger = logging.getLogger(__name__)

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
