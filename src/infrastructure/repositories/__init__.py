"""
Configuration Management Repositories

This module provides 7 repository classes for managing configuration data:
- StrategyConfigRepository: Strategy configuration CRUD
- RiskConfigRepository: Risk configuration management
- SystemConfigRepository: System configuration management
- SymbolConfigRepository: Symbol pool configuration
- NotificationConfigRepository: Notification channel configuration
- ConfigSnapshotRepositoryExtended: Configuration snapshot management
- ConfigHistoryRepository: Configuration change history

Example usage:
    from src.infrastructure.repositories import ConfigDatabaseManager

    manager = ConfigDatabaseManager("data/v3_dev.db")
    await manager.initialize()

    # Access individual repositories
    strategy = manager.strategy_repo
    await strategy.create({...})
"""

from src.infrastructure.repositories.config_repositories import (
    # Exception classes
    ConfigNotFoundError,
    ConfigConflictError,
    ConfigValidationError,
    # Repository classes
    StrategyConfigRepository,
    RiskConfigRepository,
    SystemConfigRepository,
    SymbolConfigRepository,
    NotificationConfigRepository,
    ConfigSnapshotRepositoryExtended,
    ConfigHistoryRepository,
    # Manager class
    ConfigDatabaseManager,
)

__all__ = [
    # Exceptions
    "ConfigNotFoundError",
    "ConfigConflictError",
    "ConfigValidationError",
    # Repositories
    "StrategyConfigRepository",
    "RiskConfigRepository",
    "SystemConfigRepository",
    "SymbolConfigRepository",
    "NotificationConfigRepository",
    "ConfigSnapshotRepositoryExtended",
    "ConfigHistoryRepository",
    # Manager
    "ConfigDatabaseManager",
]
