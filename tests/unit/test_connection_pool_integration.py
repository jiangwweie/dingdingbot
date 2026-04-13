"""
集成测试：共享 DB 连接池改造验证

Verifies:
1. 所有 Repository 使用池化连接（同 db_path 共享同一连接）
2. 并发写入无 "database is locked" 异常
3. PRAGMA 设置正确（WAL, busy_timeout, synchronous）
4. 双模式初始化回归（lifespan 和 main.py 嵌入模式）
5. close() 不会关闭池化连接
"""
import asyncio
import os
import tempfile
import pytest
from decimal import Decimal

from src.infrastructure.connection_pool import (
    ConnectionPool,
    get_connection,
    close_all_connections,
)
from src.infrastructure.signal_repository import SignalRepository
from src.infrastructure.backtest_repository import BacktestReportRepository
from src.infrastructure.config_snapshot_repository import ConfigSnapshotRepository
from src.infrastructure.repositories.config_repositories import (
    StrategyConfigRepository,
    RiskConfigRepository,
    SystemConfigRepository,
    ConfigDatabaseManager,
)
from src.domain.models import SignalResult, Direction


@pytest.fixture
def temp_db_path():
    """Provide a temporary database file path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)
    # Also clean up WAL/SHM files
    for ext in ["-wal", "-shm"]:
        wal_path = path + ext
        if os.path.exists(wal_path):
            os.unlink(wal_path)


@pytest.fixture(autouse=True)
def reset_pool():
    """Reset connection pool before and after each test."""
    ConnectionPool._instance = None
    ConnectionPool._initialized = False
    yield
    ConnectionPool._instance = None
    ConnectionPool._initialized = False


class TestPoolConnectionSharing:
    """测试多个 Repository 共享同一池化连接"""

    @pytest.mark.asyncio
    async def test_multiple_repos_share_connection(self, temp_db_path):
        """不同 Repository 实例使用相同 db_path 应共享同一连接"""
        signal_repo = SignalRepository(db_path=temp_db_path)
        backtest_repo = BacktestReportRepository(db_path=temp_db_path)
        strategy_repo = StrategyConfigRepository(db_path=temp_db_path)

        await signal_repo.initialize()
        await backtest_repo.initialize()
        await strategy_repo.initialize()

        # 所有自行管理连接的 Repository 应使用池中的同一连接
        assert signal_repo._db is backtest_repo._db
        assert backtest_repo._db is strategy_repo._db

        await signal_repo.close()
        await backtest_repo.close()
        await strategy_repo.close()

    @pytest.mark.asyncio
    async def test_config_database_manager_uses_pool(self, temp_db_path):
        """ConfigDatabaseManager 创建的子仓库应使用池化连接"""
        manager = ConfigDatabaseManager(db_path=temp_db_path)
        await manager.initialize()

        # 子仓库应有连接
        assert manager.strategy_repo._db is not None
        assert manager.risk_repo._db is not None

        # 子仓库之间应共享连接（同一 db_path）
        assert manager.strategy_repo._db is manager.risk_repo._db

        await manager.close()


class TestConcurrentWrites:
    """测试并发写入无 locked 异常"""

    @pytest.mark.asyncio
    async def test_concurrent_writes_no_locked(self, temp_db_path):
        """多个 Repository 同时写入不应产生 database is locked"""
        # 初始化多个仓库
        signal_repo = SignalRepository(db_path=temp_db_path)
        strategy_repo = StrategyConfigRepository(db_path=temp_db_path)
        risk_repo = RiskConfigRepository(db_path=temp_db_path)

        await signal_repo.initialize()
        await strategy_repo.initialize()
        await risk_repo.initialize()

        errors = []

        async def write_signal(i: int):
            try:
                signal = SignalResult(
                    symbol="BTC/USDT:USDT",
                    timeframe="15m",
                    direction=Direction.LONG,
                    entry_price=Decimal("50000") + i,
                    suggested_stop_loss=Decimal("49000"),
                    suggested_position_size=Decimal("0.01"),
                    current_leverage=10,
                    tags=[],
                    risk_reward_info="",
                    strategy_name="test",
                    score=0.8,
                )
                await signal_repo.save_signal(signal, signal_id=f"test_{i}")
            except Exception as e:
                errors.append(f"signal write failed: {e}")

        async def write_strategy(i: int):
            try:
                await strategy_repo.create({
                    "name": f"Strategy {i}",
                    "trigger_config": {"type": "pinbar"},
                    "filter_configs": [],
                    "symbols": ["BTC/USDT:USDT"],
                    "timeframes": ["15m"],
                })
            except Exception as e:
                errors.append(f"strategy write failed: {e}")

        async def write_risk(i: int):
            try:
                await risk_repo.update({
                    "max_loss_percent": Decimal("0.01"),
                    "max_leverage": 10,
                })
            except Exception as e:
                errors.append(f"risk write failed: {e}")

        # 并发写入
        tasks = []
        for i in range(5):
            tasks.append(write_signal(i))
            tasks.append(write_strategy(i))
            tasks.append(write_risk(i))

        await asyncio.gather(*tasks)

        # 不应有任何写入失败
        assert not errors, f"Concurrent write failures: {errors}"

        await signal_repo.close()
        await strategy_repo.close()
        await risk_repo.close()


class TestPRAGMASettings:
    """测试 PRAGMA 设置正确性"""

    @pytest.mark.asyncio
    async def test_wal_mode_enabled(self, temp_db_path):
        """WAL 模式应已启用"""
        conn = await get_connection(temp_db_path)
        async with conn.execute("PRAGMA journal_mode") as cursor:
            row = await cursor.fetchone()
            assert row[0] == "wal", f"journal_mode is {row[0]}, expected 'wal'"

    @pytest.mark.asyncio
    async def test_busy_timeout_set(self, temp_db_path):
        """busy_timeout 应设置为 10000"""
        conn = await get_connection(temp_db_path)
        async with conn.execute("PRAGMA busy_timeout") as cursor:
            row = await cursor.fetchone()
            assert row[0] == 10000, f"busy_timeout is {row[0]}, expected 10000"

    @pytest.mark.asyncio
    async def test_synchronous_normal(self, temp_db_path):
        """synchronous 应设置为 NORMAL"""
        conn = await get_connection(temp_db_path)
        async with conn.execute("PRAGMA synchronous") as cursor:
            row = await cursor.fetchone()
            assert row[0] == 1, f"synchronous is {row[0]}, expected 1 (NORMAL)"


class TestCloseBehavior:
    """测试 close() 行为"""

    @pytest.mark.asyncio
    async def test_repo_close_does_not_close_pool_connection(self, temp_db_path):
        """Repository.close() 不应关闭池化连接"""
        repo = SignalRepository(db_path=temp_db_path)
        await repo.initialize()

        pool_conn = repo._db
        await repo.close()

        # 池化连接应仍然可用
        conn_after = await get_connection(temp_db_path)
        assert conn_after is pool_conn, "Pool connection was incorrectly closed"

    @pytest.mark.asyncio
    async def test_close_all_connections_works(self, temp_db_path):
        """close_all_connections() 应正确关闭所有连接"""
        await get_connection(temp_db_path)
        await close_all_connections()

        # 池应为空，获取新连接应创建新的
        pool = ConnectionPool.get_instance()
        assert temp_db_path not in pool._connections


class TestInitializationModes:
    """测试双模式初始化（lifespan 和 main.py 嵌入模式）"""

    @pytest.mark.asyncio
    async def test_repository_init_without_connection(self, temp_db_path):
        """不传 connection 参数时，Repository 应自动使用连接池"""
        repo = StrategyConfigRepository(db_path=temp_db_path)
        await repo.initialize()

        # 应有连接
        assert repo._db is not None

        # 验证连接来自连接池（同路径的另一个 Repo 共享同一连接）
        repo2 = RiskConfigRepository(db_path=temp_db_path)
        await repo2.initialize()
        assert repo._db is repo2._db

        await repo.close()
        await repo2.close()

    @pytest.mark.asyncio
    async def test_repository_init_with_injected_connection(self, temp_db_path):
        """传入注入的 connection 时，Repository 不应关闭该连接"""
        pool_conn = await get_connection(temp_db_path)
        repo = StrategyConfigRepository(db_path=temp_db_path, connection=pool_conn)
        await repo.initialize()

        assert repo._db is pool_conn
        await repo.close()

        # 注入的连接仍应在池中
        conn_from_pool = await get_connection(temp_db_path)
        assert conn_from_pool is pool_conn
