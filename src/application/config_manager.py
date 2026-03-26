"""
Configuration Manager - Load, validate, and merge core.yaml and user.yaml.
Handles API key permission validation at startup.
Supports hot-reload with atomic pointer swap and observer pattern.
"""
import asyncio
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Awaitable, Set
from decimal import Decimal
from enum import Enum

import yaml
from pydantic import BaseModel, Field, field_validator, ValidationError

from src.domain.exceptions import FatalStartupError
from src.infrastructure.logger import logger, register_secret, mask_secret
from src.domain.models import FilterConfig, StrategyDefinition, TriggerConfig


# ============================================================
# Pydantic Config Models
# ============================================================
class PinbarDefaults(BaseModel):
    min_wick_ratio: Decimal = Field(..., description="Minimum wick ratio")
    max_body_ratio: Decimal = Field(..., description="Maximum body ratio")
    body_position_tolerance: Decimal = Field(..., description="Body position tolerance")

    @field_validator('min_wick_ratio', 'max_body_ratio', 'body_position_tolerance')
    @classmethod
    def validate_decimal_range(cls, v):
        if v < 0 or v > 1:
            raise ValueError("Value must be between 0 and 1")
        return v


class EmaConfig(BaseModel):
    period: int = Field(..., ge=1, description="EMA period")


class MtfMapping(BaseModel):
    model_config = {'extra': 'allow'}


class WarmupConfig(BaseModel):
    history_bars: int = Field(..., ge=10, description="Number of historical bars to fetch")


class SignalPipelineConfig(BaseModel):
    cooldown_seconds: int = Field(default=14400, ge=60, description="Signal deduplication cooldown in seconds")


class CoreConfig(BaseModel):
    """Core system configuration (read-only)"""
    core_symbols: List[str] = Field(..., min_length=1, description="Core trading symbols")
    pinbar_defaults: PinbarDefaults
    ema: EmaConfig
    mtf_mapping: MtfMapping
    warmup: WarmupConfig
    signal_pipeline: SignalPipelineConfig = Field(default_factory=SignalPipelineConfig)


class ExchangeConfig(BaseModel):
    name: str = Field(..., description="Exchange name (ccxt id)")
    api_key: str = Field(..., description="API Key (read-only permission required)")
    api_secret: str = Field(..., description="API Secret")
    testnet: bool = Field(default=False, description="Use testnet")


class StrategyConfig(BaseModel):
    """
    Legacy strategy config (for backward compatibility).
    New systems should use active_strategies instead.
    """
    trend_filter_enabled: bool = Field(default=True, description="Enable EMA60 trend filter")
    mtf_validation_enabled: bool = Field(default=True, description="Enable MTF validation")


class RiskConfig(BaseModel):
    max_loss_percent: Decimal = Field(..., description="Max loss per trade as % of balance")
    max_leverage: int = Field(..., ge=1, le=125, description="Maximum leverage allowed")

    @field_validator('max_loss_percent')
    @classmethod
    def validate_loss_percent(cls, v):
        if v <= 0 or v > Decimal('1'):
            raise ValueError("Max loss percent must be between 0 and 1")
        return v


class AssetPollingConfig(BaseModel):
    interval_seconds: int = Field(default=60, ge=10, description="Asset polling interval")


class NotificationChannel(BaseModel):
    type: str = Field(..., description="Channel type: feishu or wecom")
    webhook_url: str = Field(..., description="Webhook URL")

    @field_validator('type')
    @classmethod
    def validate_channel_type(cls, v):
        if v not in ('feishu', 'wecom'):
            raise ValueError("Channel type must be 'feishu' or 'wecom'")
        return v


class NotificationConfig(BaseModel):
    channels: List[NotificationChannel] = Field(..., min_length=1, description="Notification channels")


class UserConfig(BaseModel):
    """User configuration (modifiable)"""
    exchange: ExchangeConfig
    user_symbols: List[str] = Field(default_factory=list, description="User-defined symbols")
    timeframes: List[str] = Field(..., min_length=1, description="Timeframes to monitor")
    # New dynamic rule engine config (Phase K)
    active_strategies: List[StrategyDefinition] = Field(
        default_factory=list,
        description="Active strategy definitions with attached filters"
    )
    # Legacy support - if active_strategies is empty, migrate from old strategy config
    strategy: Optional[StrategyConfig] = Field(default=None, description="Legacy strategy config (deprecated)")
    risk: RiskConfig
    asset_polling: AssetPollingConfig = Field(default_factory=AssetPollingConfig)
    notification: NotificationConfig

    model_config = {'protected_namespaces': ()}

    @field_validator('active_strategies', mode='after')
    @classmethod
    def migrate_legacy_strategy(cls, v: List[StrategyDefinition], info) -> List[StrategyDefinition]:
        """
        Migrate legacy strategy config to active_strategies if empty.
        This ensures backward compatibility with existing user.yaml files.
        """
        # Only migrate if active_strategies is empty and legacy strategy exists
        if len(v) == 0:
            ctx = info.context
            if ctx and 'strategy' in ctx:
                legacy = ctx['strategy']
                if legacy:
                    # Migrate to default pinbar strategy with EMA+MTF filters
                    filters = []
                    if legacy.trend_filter_enabled:
                        filters.append({"type": "ema", "period": 60, "enabled": True})
                    if legacy.mtf_validation_enabled:
                        filters.append({"type": "mtf", "enabled": True})

                    return [StrategyDefinition(
                        name="pinbar",
                        enabled=True,
                        trigger=TriggerConfig(type="pinbar", enabled=True, params={}),
                        filters=filters,
                        filter_logic="AND"
                    )]
        return v


# ============================================================
# Config Manager
# ============================================================
class ConfigManager:
    """
    Manages configuration loading, validation, and merging.
    Supports hot-reload with atomic pointer swap and observer pattern.
    """

    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize ConfigManager.

        Args:
            config_dir: Directory containing config files. Defaults to ./config
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            self.config_dir = Path(__file__).parent.parent.parent / 'config'

        self._core_config: Optional[CoreConfig] = None
        self._user_config: Optional[UserConfig] = None
        self._merged_symbols: List[str] = []

        # Hot-reload state
        self._observers: Set[Callable[[], Awaitable[None]]] = set()
        self._update_lock: Optional[asyncio.Lock] = None  # Lazily initialized

    def load_core_config(self) -> CoreConfig:
        """Load and validate core.yaml"""
        core_path = self.config_dir / 'core.yaml'

        if not core_path.exists():
            raise FatalStartupError(
                f"Core config file not found: {core_path}",
                "F-003"
            )

        try:
            with open(core_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            self._core_config = CoreConfig(**data)
            logger.info(f"Core configuration loaded from {core_path}")
            return self._core_config

        except ValidationError as e:
            raise FatalStartupError(
                f"Core config validation failed: {e}",
                "F-003"
            )
        except yaml.YAMLError as e:
            raise FatalStartupError(
                f"Core config YAML parse error: {e}",
                "F-003"
            )

    def load_user_config(self) -> UserConfig:
        """Load and validate user.yaml"""
        user_path = self.config_dir / 'user.yaml'

        if not user_path.exists():
            raise FatalStartupError(
                f"User config file not found: {user_path}",
                "F-003"
            )

        try:
            with open(user_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            # Extract legacy strategy config before validation
            legacy_strategy = data.get('strategy')

            self._user_config = UserConfig(**data)

            # Manual migration: if active_strategies is empty but legacy strategy exists
            if not self._user_config.active_strategies and legacy_strategy:
                self._user_config = self._migrate_legacy_strategy(legacy_strategy)

            # Register secrets for masking
            register_secret(self._user_config.exchange.api_key)
            register_secret(self._user_config.exchange.api_secret)
            for channel in self._user_config.notification.channels:
                register_secret(channel.webhook_url)

            logger.info(f"User configuration loaded from {user_path}")
            return self._user_config

        except ValidationError as e:
            raise FatalStartupError(
                f"User config validation failed: {e}",
                "F-003"
            )
        except yaml.YAMLError as e:
            raise FatalStartupError(
                f"User config YAML parse error: {e}",
                "F-003"
            )

    def _migrate_legacy_strategy(self, legacy_strategy: dict) -> UserConfig:
        """
        Migrate legacy strategy config to active_strategies format.

        Args:
            legacy_strategy: Dictionary with trend_filter_enabled and mtf_validation_enabled
        """
        # Build filter chain from legacy config
        filters = []
        if legacy_strategy.get('trend_filter_enabled', True):
            filters.append({"type": "ema", "period": 60, "enabled": True})
        if legacy_strategy.get('mtf_validation_enabled', True):
            filters.append({"type": "mtf", "enabled": True})

        # Create new active_strategies list
        active_strategies = [
            StrategyDefinition(
                name="pinbar",
                enabled=True,
                trigger=TriggerConfig(type="pinbar", enabled=True, params={}),
                filters=filters,
                filter_logic="AND"
            )
        ]

        # Update config with migrated strategies
        return self._user_config.model_copy(update={"active_strategies": active_strategies})

    def merge_symbols(self) -> List[str]:
        """
        Merge core_symbols and user_symbols with deduplication.
        core_symbols cannot be overridden or removed.

        Returns:
            Merged and deduplicated list of symbols
        """
        if not self._core_config:
            raise FatalStartupError("Core config not loaded", "F-003")
        if not self._user_config:
            raise FatalStartupError("User config not loaded", "F-003")

        # Use dict to maintain order while deduplicating
        # core_symbols come first (protected), then user_symbols
        merged = {}

        for symbol in self._core_config.core_symbols:
            merged[symbol] = True

        for symbol in self._user_config.user_symbols:
            if symbol not in merged:
                merged[symbol] = True

        self._merged_symbols = list(merged.keys())
        logger.info(f"Merged symbol list: {len(self._merged_symbols)} symbols")
        return self._merged_symbols

    async def check_api_key_permissions(self, exchange: Any) -> None:
        """
        API Key 读写权限探测已被强行跳过。
        用户需自行保证该 Key 仅拥有只读与合约权限，发生资产意外操作责任自负！

        Args:
            exchange: Initialized CCXT exchange instance
        """
        logger.warning(
            "API Key 读写权限探测已被强行跳过。"
            "用户需自行保证该 Key 仅拥有只读与合约权限，发生资产意外操作责任自负！"
        )
        return

    def print_startup_info(self) -> None:
        """
        Print all effective configuration parameters to console (with secrets masked).
        """
        if not self._core_config or not self._user_config:
            raise FatalStartupError("Configuration not fully loaded", "F-003")

        logger.info("=" * 60)
        logger.info("EFFECTIVE CONFIGURATION (Startup)")
        logger.info("=" * 60)

        # Exchange info (masked)
        exchange = self._user_config.exchange
        logger.info(f"Exchange: {exchange.name}")
        logger.info(f"API Key: {mask_secret(exchange.api_key)}")
        logger.info(f"Testnet: {exchange.testnet}")

        # Symbols
        logger.info(f"Monitoring {len(self._merged_symbols)} symbols:")
        for symbol in self._merged_symbols:
            logger.info(f"  - {symbol}")

        # Timeframes
        logger.info(f"Timeframes: {', '.join(self._user_config.timeframes)}")

        # Strategy settings - new dynamic rule engine
        active_strategies = self._user_config.active_strategies
        if active_strategies:
            logger.info(f"Active Strategies ({len(active_strategies)}):")
            for strat in active_strategies:
                status = "ENABLED" if getattr(strat, "trigger", None) and strat.trigger.enabled else "DISABLED"
                filter_names = ", ".join([f.type for f in strat.filters])
                logger.info(f"  - {strat.name}: {status} (filters: {filter_names or 'none'})")
        else:
            # Fallback to legacy display
            strategy = self._user_config.strategy
            if strategy:
                logger.info(f"Strategy Settings (legacy):")
                logger.info(f"  - Trend Filter (EMA60): {'ENABLED' if strategy.trend_filter_enabled else 'DISABLED'}")
                logger.info(f"  - MTF Validation: {'ENABLED' if strategy.mtf_validation_enabled else 'DISABLED'}")

        # Risk settings
        risk = self._user_config.risk
        logger.info(f"Risk Settings:")
        logger.info(f"  - Max Loss per Trade: {float(risk.max_loss_percent) * 100}%")
        logger.info(f"  - Max Leverage: {risk.max_leverage}x")

        # Notification channels
        logger.info(f"Notification Channels:")
        for channel in self._user_config.notification.channels:
            logger.info(f"  - {channel.type}: {mask_secret(channel.webhook_url)}")

        # Core settings
        ema = self._core_config.ema
        logger.info(f"Core Settings:")
        logger.info(f"  - EMA Period: {ema.period}")

        warmup = self._core_config.warmup
        logger.info(f"  - Warmup Bars: {warmup.history_bars}")

        signal_pipeline = self._core_config.signal_pipeline
        logger.info(f"  - Signal Cooldown: {signal_pipeline.cooldown_seconds}s")

        pinbar = self._core_config.pinbar_defaults
        logger.info(f"  - Pinbar Min Wick: {float(pinbar.min_wick_ratio)}")
        logger.info(f"  - Pinbar Max Body: {float(pinbar.max_body_ratio)}")
        logger.info(f"  - Pinbar Body Tolerance: {float(pinbar.body_position_tolerance)}")

        logger.info("=" * 60)

    @property
    def core_config(self) -> CoreConfig:
        """Get loaded core configuration"""
        if not self._core_config:
            raise FatalStartupError("Core config not loaded", "F-003")
        return self._core_config

    @property
    def user_config(self) -> UserConfig:
        """Get loaded user configuration"""
        if not self._user_config:
            raise FatalStartupError("User config not loaded", "F-003")
        return self._user_config

    @property
    def merged_symbols(self) -> List[str]:
        """Get merged symbol list"""
        if not self._merged_symbols:
            raise FatalStartupError("Symbols not merged", "F-003")
        return self._merged_symbols

    # ============================================================
    # Hot-Reload & Observer Pattern
    # ============================================================
    def _get_update_lock(self) -> asyncio.Lock:
        """Get or create the update lock for thread-safe config updates."""
        if self._update_lock is None:
            try:
                self._update_lock = asyncio.Lock()
            except RuntimeError:
                # No running event loop
                pass
        return self._update_lock

    def add_observer(self, callback: Callable[[], Awaitable[None]]) -> None:
        """
        Add an observer callback to be invoked when configuration is updated.

        Observers are called asynchronously after atomic config replacement.
        Use case: auto-reconnect exchange WebSocket on config change.

        Args:
            callback: Async function to call with no arguments
        """
        self._observers.add(callback)
        logger.info(f"Observer added. Total observers: {len(self._observers)}")

    def remove_observer(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Remove an observer callback."""
        self._observers.discard(callback)

    async def update_user_config(self, new_config_dict: Dict[str, Any]) -> UserConfig:
        """
        Hot-reload user configuration with atomic pointer swap.

        Flow:
        1. Validate incoming dict against Pydantic UserConfig model
        2. Deep copy to create new immutable model instance
        3. Atomically replace in-memory reference
        4. Notify all observers asynchronously
        5. Persist to user.yaml (background write)

        Args:
            new_config_dict: Partial or full user config dictionary

        Returns:
            The new validated UserConfig instance

        Raises:
            ValidationError: If config fails Pydantic validation
            FatalStartupError: If core config not loaded
        """
        if not self._core_config:
            raise FatalStartupError("Core config not loaded", "F-003")

        async with self._get_update_lock():
            # Step 1: Merge with existing config for partial updates
            existing_dict = self._user_config.model_dump() if self._user_config else {}
            merged_dict = self._deep_merge(existing_dict, new_config_dict)

            # Step 2: Validate against Pydantic model
            try:
                new_user_config = UserConfig(**merged_dict)
            except ValidationError as e:
                logger.error(f"Config validation failed: {e}")
                raise

            # Step 3: Atomic pointer swap (replace in-memory reference)
            old_config = self._user_config
            self._user_config = new_user_config

            # Register any new secrets for masking
            register_secret(new_user_config.exchange.api_key)
            register_secret(new_user_config.exchange.api_secret)
            for channel in new_user_config.notification.channels:
                register_secret(channel.webhook_url)

            # Step 4: Notify observers (async, non-blocking)
            await self._notify_observers()

            # Step 5: Persist to disk (fire-and-forget in production, but we await here for safety)
            await self._persist_user_config()

            logger.info("User configuration updated and persisted")
            return new_user_config

    def _deep_merge(self, base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep merge two dictionaries. Update values override base values.

        Args:
            base: Base dictionary
            update: Update dictionary (takes precedence)

        Returns:
            Merged dictionary
        """
        result = base.copy()
        for key, value in update.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    async def _notify_observers(self) -> None:
        """Notify all observers of config update (non-blocking)."""
        if not self._observers:
            return

        # Fire all observers concurrently
        results = await asyncio.gather(
            *[self._safe_observer_call(cb) for cb in self._observers],
            return_exceptions=True
        )

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Observer {i} failed: {result}")

    async def _safe_observer_call(self, callback: Callable[[], Awaitable[None]]) -> Any:
        """Safely call an observer, catching any exceptions."""
        try:
            return await callback()
        except Exception as e:
            logger.error(f"Observer callback raised: {e}")
            raise

    async def _persist_user_config(self) -> None:
        """Persist current user_config to user.yaml with yaml error handling."""
        user_path = self.config_dir / 'user.yaml'

        try:
            if not self._user_config:
                raise FatalStartupError("User config not loaded", "F-003")

            # Convert Pydantic model to dict
            # Use mode='json' to handle Decimal serialization properly
            config_dict = self._user_config.model_dump(mode='json')

            # Write to YAML file
            with open(user_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(
                    config_dict,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False
                )

            logger.info(f"User configuration persisted to {user_path}")

        except yaml.YAMLError as e:
            logger.error(f"YAML write error: {e}")
            # Revert to old config on write failure
            # In production, you might want a rollback strategy
            raise
        except Exception as e:
            logger.error(f"Config persist error: {e}")
            raise


# ============================================================
# Convenience function
# ============================================================
def load_all_configs(config_dir: Optional[str] = None) -> ConfigManager:
    """
    Load all configurations and return ConfigManager instance.

    Args:
        config_dir: Optional config directory path

    Returns:
        ConfigManager with all configs loaded and merged
    """
    manager = ConfigManager(config_dir)
    manager.load_core_config()
    manager.load_user_config()
    manager.merge_symbols()
    manager.print_startup_info()
    return manager
