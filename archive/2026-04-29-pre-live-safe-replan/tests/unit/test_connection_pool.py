"""
Tests for the global SQLite connection pool.

Verifies:
- Singleton pattern works correctly
- Connection sharing by db_path
- Backward compatibility (repos work without injected connection)
- Connection pool injection works
"""
import os
import pytest
import tempfile

import src.infrastructure.connection_pool as pool_module
from src.infrastructure.connection_pool import (
    ConnectionPool,
    get_connection,
    close_all_connections,
)
from src.infrastructure.repositories.config_repositories import (
    StrategyConfigRepository,
    RiskConfigRepository,
    ConfigDatabaseManager,
)


@pytest.fixture
def fresh_pool():
    """Provide a fresh ConnectionPool for each test."""
    ConnectionPool._instance = None
    pool_module._pool = ConnectionPool.get_instance()
    yield
    # Cleanup: reset singleton and module-level _pool
    ConnectionPool._instance = None
    pool_module._pool = ConnectionPool.get_instance()


@pytest.fixture
def temp_db_path():
    """Provide a temporary database file path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


class TestConnectionPoolSingleton:
    """Test ConnectionPool singleton behavior."""

    def test_get_instance_returns_same_instance(self, fresh_pool):
        """Multiple calls to get_instance return the same object."""
        instance1 = ConnectionPool.get_instance()
        instance2 = ConnectionPool.get_instance()
        assert instance1 is instance2

    def test_reset_instance(self, fresh_pool):
        """Resetting the instance creates a new object."""
        original = ConnectionPool.get_instance()
        ConnectionPool._instance = None
        new_instance = ConnectionPool.get_instance()
        assert original is not new_instance


class TestConnectionPoolConnectionSharing:
    """Test connection sharing by db_path."""

    @pytest.mark.asyncio
    async def test_same_path_returns_same_connection(self, fresh_pool, temp_db_path):
        """Connections for the same db_path are shared."""
        conn1 = await get_connection(temp_db_path)
        conn2 = await get_connection(temp_db_path)
        assert conn1 is conn2

    @pytest.mark.asyncio
    async def test_different_paths_return_different_connections(
        self, fresh_pool, tmp_path
    ):
        """Connections for different db_paths are separate."""
        path1 = str(tmp_path / "db1.db")
        path2 = str(tmp_path / "db2.db")

        conn1 = await get_connection(path1)
        conn2 = await get_connection(path2)
        assert conn1 is not conn2


class TestConnectionPoolBackwardCompatibility:
    """Test backward compatibility - repos work without injected connection."""

    @pytest.mark.asyncio
    async def test_repository_without_connection(self, temp_db_path):
        """Repository works when created without connection parameter."""
        repo = StrategyConfigRepository(db_path=temp_db_path)
        await repo.initialize()

        # Should work normally
        strategy_id = await repo.create({
            "name": "Test Strategy",
            "trigger_config": {"type": "pinbar"},
            "filter_configs": [],
            "symbols": ["BTC/USDT:USDT"],
            "timeframes": ["15m"],
        })
        assert strategy_id is not None

        strategy = await repo.get_by_id(strategy_id)
        assert strategy is not None
        assert strategy["name"] == "Test Strategy"

        await repo.close()

    @pytest.mark.asyncio
    async def test_repository_with_injected_connection(self, fresh_pool, temp_db_path):
        """Repository works when given an injected connection."""
        conn = await get_connection(temp_db_path)
        repo = StrategyConfigRepository(db_path=temp_db_path, connection=conn)
        await repo.initialize()

        strategy_id = await repo.create({
            "name": "Injected Strategy",
            "trigger_config": {"type": "pinbar"},
            "filter_configs": [],
            "symbols": ["BTC/USDT:USDT"],
            "timeframes": ["15m"],
        })
        assert strategy_id is not None

        strategy = await repo.get_by_id(strategy_id)
        assert strategy is not None

        # close() should NOT close the injected connection
        await repo.close()
        # Connection should still be usable (via pool)
        conn2 = await get_connection(temp_db_path)
        assert conn2 is conn  # Same connection from pool

    @pytest.mark.asyncio
    async def test_config_database_manager_uses_pool(self, fresh_pool, temp_db_path):
        """ConfigDatabaseManager uses the connection pool."""
        manager = ConfigDatabaseManager(db_path=temp_db_path)
        await manager.initialize()

        # All repos should be initialized
        assert manager.strategy_repo is not None
        assert manager.risk_repo is not None
        assert manager.system_repo is not None
        assert manager.symbol_repo is not None
        assert manager.notification_repo is not None
        assert manager.snapshot_repo is not None
        assert manager.history_repo is not None

        # Should be able to use the repos
        strategy_id = await manager.strategy_repo.create({
            "name": "Pool Strategy",
            "trigger_config": {"type": "pinbar"},
            "filter_configs": [],
            "symbols": ["BTC/USDT:USDT"],
            "timeframes": ["15m"],
        })
        assert strategy_id is not None

        strategy = await manager.strategy_repo.get_by_id(strategy_id)
        assert strategy["name"] == "Pool Strategy"

        await manager.close()
        await close_all_connections()


class TestConnectionPoolClose:
    """Test connection pool close behavior."""

    @pytest.mark.asyncio
    async def test_close_all_connections(self, fresh_pool, tmp_path):
        """close_all_connections closes all managed connections."""
        path = str(tmp_path / "test.db")
        await get_connection(path)

        await close_all_connections()

        # Getting connection again should create a new one
        conn = await get_connection(path)
        assert conn is not None
