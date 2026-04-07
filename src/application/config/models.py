"""
Configuration Data Models

This module re-exports Pydantic models used by the Parser layer.
Models are imported from their original locations to avoid duplication.

Parser Layer Models:
- CoreConfig: Core system configuration (read-only)
- UserConfig: User configuration (modifiable)
- RiskConfig: Risk management configuration
- StrategyDefinition: Strategy definition with triggers and filters
- TriggerConfig: Trigger configuration (from logic_tree)
- FilterConfig: Filter configuration (from logic_tree)

Supporting Models (for YAML parsing):
- PinbarDefaults, EmaConfig, MtfMapping, WarmupConfig
- SignalQueueConfig, SignalPipelineConfig, AtrConfig
- ExchangeConfig, StrategyConfig, AssetPollingConfig
- NotificationChannel, NotificationConfig
"""

# Import from domain layer (SSOT for domain models)
from src.domain.models import (
    RiskConfig,
    StrategyDefinition,
)

# Import from logic_tree for strategy definitions
from src.domain.logic_tree import (
    TriggerConfig,
    FilterConfig,
)

# Import from config_manager (original definition location)
# These are kept here for backward compatibility during P1-5 refactoring
# TODO(P1-5): Move these to domain/models.py after full refactoring
from src.application.config_manager import (
    PinbarDefaults,
    EmaConfig,
    MtfMapping,
    WarmupConfig,
    SignalQueueConfig,
    SignalPipelineConfig,
    AtrConfig,
    CoreConfig,
    ExchangeConfig,
    StrategyConfig,
    AssetPollingConfig,
    NotificationChannel,
    NotificationConfig,
    UserConfig,
)

__all__ = [
    # Core config models
    "CoreConfig",
    "UserConfig",
    "RiskConfig",
    # Strategy models
    "StrategyDefinition",
    "TriggerConfig",
    "FilterConfig",
    # Supporting models
    "PinbarDefaults",
    "EmaConfig",
    "MtfMapping",
    "WarmupConfig",
    "SignalQueueConfig",
    "SignalPipelineConfig",
    "AtrConfig",
    "ExchangeConfig",
    "StrategyConfig",
    "AssetPollingConfig",
    "NotificationChannel",
    "NotificationConfig",
]
