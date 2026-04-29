"""Factory functions for creating config repositories with PG routing.

This module provides factory functions that automatically route to PG or SQLite
based on MIGRATE_ALL_STATE_TO_PG environment variable and explicit parameters.
"""

from typing import Optional

import aiosqlite


def _should_use_pg(db_path: str, connection: Optional[aiosqlite.Connection], use_pg: Optional[bool]) -> bool:
    if use_pg is not None:
        return use_pg
    if connection is not None or db_path != "data/v3_dev.db":
        return False
    from src.infrastructure.database import should_use_pg_for_default_repository

    return should_use_pg_for_default_repository()


def create_strategy_config_repository(
    db_path: str = "data/v3_dev.db",
    connection: Optional[aiosqlite.Connection] = None,
    use_pg: Optional[bool] = None,
):
    """
    Create StrategyConfigRepository with automatic PG routing.

    Args:
        db_path: SQLite database path (ignored if use_pg=True)
        connection: SQLite connection (ignored if use_pg=True)
        use_pg: Explicit PG flag (None → auto-detect based on env and params)

    Returns:
        PG or SQLite repository instance
    """
    if _should_use_pg(db_path, connection, use_pg):
        from src.infrastructure.pg_config_repositories import PgStrategyConfigRepository
        return PgStrategyConfigRepository()
    else:
        from src.infrastructure.repositories.config_repositories import StrategyConfigRepository
        return StrategyConfigRepository(db_path=db_path, connection=connection)


def create_risk_config_repository(
    db_path: str = "data/v3_dev.db",
    connection: Optional[aiosqlite.Connection] = None,
    use_pg: Optional[bool] = None,
):
    """Create RiskConfigRepository with automatic PG routing."""
    if _should_use_pg(db_path, connection, use_pg):
        from src.infrastructure.pg_config_repositories import PgRiskConfigRepository
        return PgRiskConfigRepository()
    else:
        from src.infrastructure.repositories.config_repositories import RiskConfigRepository
        return RiskConfigRepository(db_path=db_path, connection=connection)


def create_system_config_repository(
    db_path: str = "data/v3_dev.db",
    connection: Optional[aiosqlite.Connection] = None,
    use_pg: Optional[bool] = None,
):
    """Create SystemConfigRepository with automatic PG routing."""
    if _should_use_pg(db_path, connection, use_pg):
        from src.infrastructure.pg_config_repositories import PgSystemConfigRepository
        return PgSystemConfigRepository()
    else:
        from src.infrastructure.repositories.config_repositories import SystemConfigRepository
        return SystemConfigRepository(db_path=db_path, connection=connection)


def create_symbol_config_repository(
    db_path: str = "data/v3_dev.db",
    connection: Optional[aiosqlite.Connection] = None,
    use_pg: Optional[bool] = None,
):
    """Create SymbolConfigRepository with automatic PG routing."""
    if _should_use_pg(db_path, connection, use_pg):
        from src.infrastructure.pg_config_repositories import PgSymbolConfigRepository
        return PgSymbolConfigRepository()
    else:
        from src.infrastructure.repositories.config_repositories import SymbolConfigRepository
        return SymbolConfigRepository(db_path=db_path, connection=connection)


def create_notification_config_repository(
    db_path: str = "data/v3_dev.db",
    connection: Optional[aiosqlite.Connection] = None,
    use_pg: Optional[bool] = None,
):
    """Create NotificationConfigRepository with automatic PG routing."""
    if _should_use_pg(db_path, connection, use_pg):
        from src.infrastructure.pg_config_repositories import PgNotificationConfigRepository
        return PgNotificationConfigRepository()
    else:
        from src.infrastructure.repositories.config_repositories import NotificationConfigRepository
        return NotificationConfigRepository(db_path=db_path, connection=connection)


def create_config_snapshot_repository_extended(
    db_path: str = "data/v3_dev.db",
    connection: Optional[aiosqlite.Connection] = None,
    use_pg: Optional[bool] = None,
):
    """Create ConfigSnapshotRepositoryExtended with automatic PG routing."""
    if _should_use_pg(db_path, connection, use_pg):
        from src.infrastructure.pg_config_repositories import PgConfigSnapshotRepositoryExtended
        return PgConfigSnapshotRepositoryExtended()
    else:
        from src.infrastructure.repositories.config_repositories import ConfigSnapshotRepositoryExtended
        return ConfigSnapshotRepositoryExtended(db_path=db_path, connection=connection)


def create_config_history_repository(
    db_path: str = "data/v3_dev.db",
    connection: Optional[aiosqlite.Connection] = None,
    use_pg: Optional[bool] = None,
):
    """Create ConfigHistoryRepository with automatic PG routing."""
    if _should_use_pg(db_path, connection, use_pg):
        from src.infrastructure.pg_config_repositories import PgConfigHistoryRepository
        return PgConfigHistoryRepository()
    else:
        from src.infrastructure.repositories.config_repositories import ConfigHistoryRepository
        return ConfigHistoryRepository(db_path=db_path, connection=connection)
