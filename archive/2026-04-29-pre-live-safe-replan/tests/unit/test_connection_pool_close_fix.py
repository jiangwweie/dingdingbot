"""
Regression tests for the connection pool close fix.

Bug: Multiple repositories share a single aiosqlite connection from the pool
(one per db_path). When any repository's close() method was called, it would
call await self._db.close() on the shared connection, breaking all other
repositories using that connection.

Fix: Repository close() methods now only clear the local reference
(self._db = None) without closing the pool connection. Only
ConnectionPool.close_all() closes connections.

These 4 tests verify the fix works correctly and prevent regressions.
"""
import pytest

import src.infrastructure.connection_pool as pool_module
from src.infrastructure.connection_pool import (
    ConnectionPool,
    get_connection,
    close_all_connections,
)
from src.infrastructure.signal_repository import SignalRepository
from src.infrastructure.order_repository import OrderRepository
from src.infrastructure.backtest_repository import BacktestReportRepository


@pytest.fixture
def fresh_pool():
    """Reset the ConnectionPool singleton AND module-level _pool for test isolation."""
    ConnectionPool._instance = None
    pool_module._pool = ConnectionPool.get_instance()
    yield
    # Reset after test to avoid stale singleton
    ConnectionPool._instance = None
    pool_module._pool = ConnectionPool.get_instance()


@pytest.mark.asyncio
async def test_close_one_repo_doesnt_break_another(fresh_pool):
    """Closing one repo should not affect another repo sharing the same connection.

    Regression: Both repos with db_path=":memory:" get the SAME pool connection.
    The old close() called await self._db.close() which killed the shared connection,
    causing all other repos to fail on subsequent queries.
    """
    # Both repos will share the same connection from the pool
    repo1 = SignalRepository(db_path=":memory:")
    repo2 = OrderRepository(db_path=":memory:")
    await repo1.initialize()
    await repo2.initialize()

    # Verify they share the same pool connection
    assert repo1._db is repo2._db, "Both repos should share the same pool connection"

    # Close repo1 - this used to kill the shared connection
    await repo1.close()

    # repo1's local reference should be cleared
    assert repo1._db is None, "repo1._db should be None after close()"

    # repo2 should still be able to use the connection
    # This was the bug: repo1.close() called await self._db.close() on the shared connection
    result = await repo2._db.execute("SELECT 1")
    row = await result.fetchone()
    assert row[0] == 1, "repo2 should still have a working connection after repo1.close()"

    # Cleanup
    await repo2.close()
    await close_all_connections()


@pytest.mark.asyncio
async def test_sequential_close_pattern(fresh_pool):
    """Simulates the backtest API finally block pattern - closing multiple repos sequentially.

    Regression: The api.py finally block closes repos sequentially:
        await backtest_repo.close()
        await order_repo.close()
    The old code failed on the second close() because the first one
    killed the shared pool connection.
    """
    backtest_repo = BacktestReportRepository(db_path=":memory:")
    order_repo = OrderRepository(db_path=":memory:")
    await backtest_repo.initialize()
    await order_repo.initialize()

    # This is the exact pattern from api.py finally block that triggered the bug
    await backtest_repo.close()
    await order_repo.close()  # This used to fail because backtest_repo.close() killed the shared connection

    # Both repos should have cleared their local references
    assert backtest_repo._db is None, "backtest_repo._db should be None after close()"
    assert order_repo._db is None, "order_repo._db should be None after close()"

    # Pool connection should still be usable (new :memory: db will be created)
    pool_conn = await get_connection(":memory:")
    result = await pool_conn.execute("SELECT 1")
    row = await result.fetchone()
    assert row[0] == 1, "Pool connection should still be usable after all repos are closed"

    # Cleanup
    await close_all_connections()


@pytest.mark.asyncio
async def test_pool_close_all_after_repo_close():
    """ConnectionPool.close_all() should still properly close connections after repo.close().

    Regression: Verify that the pool still tracks connections after repos close,
    and that close_all() works correctly.

    Note: This test does NOT use fresh_pool fixture because repo.initialize()
    uses the module-level _pool, and get_instance() must return the same instance.
    """
    repo = SignalRepository(db_path=":memory:")
    await repo.initialize()

    # Use the same module-level _pool that repo.initialize() used
    pool = ConnectionPool.get_instance()

    # repo.close() should only clear local ref, not close the pool connection
    await repo.close()

    # Pool should still have the connection tracked
    assert ":memory:" in pool._connections, \
        "Pool should still track the connection after repo.close()"

    # close_all should work properly
    await close_all_connections()

    # Verify connections are cleared
    assert len(pool._connections) == 0, "close_all() should have cleared all connections"


@pytest.mark.asyncio
async def test_injected_connection_not_closed(fresh_pool):
    """A repo with an injected connection should not close it when repo.close() is called.

    Regression: When a connection is injected into a repo (for testing or
    lifespan-managed connections), the repo must not interfere with the
    injected connection lifecycle.
    """
    # Create a connection and inject it into the repo
    conn = await get_connection(":memory:")
    repo = SignalRepository(db_path=":memory:", connection=conn)
    await repo.initialize()

    # Close the repo
    await repo.close()

    # The injected connection should still be usable
    # (This was the original intended behavior - repos shouldn't close injected connections)
    result = await conn.execute("SELECT 1")
    row = await result.fetchone()
    assert row[0] == 1, "Injected connection should still work after repo.close()"

    # Cleanup
    await close_all_connections()
