"""
Configuration Management Package

This package provides a three-layer architecture for configuration management:

- Parser Layer (ConfigParser): YAML/JSON parsing and serialization
- Repository Layer (ConfigRepository): Data persistence and caching
- Service Layer (ConfigService): Business logic and validation

Usage:
    from src.application.config import ConfigParser, ConfigRepository, ConfigService
"""

from src.application.config.config_parser import ConfigParser
from src.application.config.models import (
    CoreConfig,
    UserConfig,
    RiskConfig,
    StrategyDefinition,
    TriggerConfig,
    FilterConfig,
)

__all__ = [
    "ConfigParser",
    "CoreConfig",
    "UserConfig",
    "RiskConfig",
    "StrategyDefinition",
    "TriggerConfig",
    "FilterConfig",
]
