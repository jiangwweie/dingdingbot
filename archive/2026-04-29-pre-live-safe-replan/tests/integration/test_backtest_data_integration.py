"""
Integration tests for Backtest data flow.

Tests verify:
1. End-to-end data flow with real database
2. Data repository with real SQLite
3. Full backtest workflow integration
"""
import pytest
import asyncio
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.infrastructure.backtest_repository import BacktestReportRepository
from src.infrastructure.order_repository import OrderRepository
from src.infrastructure.signal_repository import SignalRepository
from src.domain.models import (
    KlineData, Order, OrderStatus, OrderType, OrderRole, Direction,
    PMSBacktestReport, PositionSummary,
)
from src.infrastructure.exchange_gateway import ExchangeGateway


# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
def sample_klines():
    """Sample K-line data for integration testing"""
    return [
        KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1704067200000,
            open=Decimal("42000.00"),
            high=Decimal("42500.00"),
            low=Decimal("41800.00"),
            close=Decimal("42300.00"),
            volume=Decimal("1000.0"),
            is_closed=True,
        ),
        KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1704068100000,
            open=Decimal("42300.00"),
            high=Decimal("42800.00"),
            low=Decimal("42200.00"),
            close=Decimal("42600.00"),
            volume=Decimal("1200.0"),
            is_closed=True,
        ),
        KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1704069000000,
            open=Decimal("42600.00"),
            high=Decimal("43000.00"),
            low=Decimal("42500.00"),
            close=Decimal("42900.00"),
            volume=Decimal("1500.0"),
            is_closed=True,
        ),
        KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1704067200000,
            open=Decimal("42000.00"),
            high=Decimal("43000.00"),
            low=Decimal("41800.00"),
            close=Decimal("42600.00"),
            volume=Decimal("5000.0"),
            is_closed=True,
        ),
    ]


@pytest.fixture
def sample_position_summary():
    """Sample position summary for testing"""
    return PositionSummary(
        position_id="pos_001",
        signal_id="sig_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal("42000"),
        exit_price=Decimal("42500"),
        entry_time=1704067200000,
        exit_time=1704070800000,
        realized_pnl=Decimal("50"),
        exit_reason="TP1",
    )


@pytest.fixture
def sample_backtest_report(sample_position_summary):
    """Sample backtest report for testing"""
    return PMSBacktestReport(
        strategy_id="pinbar_v1",
        strategy_name="Pinbar",
        backtest_start=1704067200000,
        backtest_end=1704070800000,
        initial_balance=Decimal("10000"),
        final_balance=Decimal("10050"),
        total_return=Decimal("0.5"),
        total_trades=1,
        winning_trades=1,
        losing_trades=0,
        win_rate=Decimal("100.0"),
        total_pnl=Decimal("50"),
        total_fees_paid=Decimal("1"),
        total_slippage_cost=Decimal("0.5"),
        max_drawdown=Decimal("0.1"),
        positions=[sample_position_summary],
    )


@pytest.fixture
def mock_exchange_gateway():
    """Mock exchange gateway for integration tests"""
    gateway = MagicMock(spec=ExchangeGateway)
    gateway.fetch_historical_ohlcv = AsyncMock(return_value=[])
    return gateway


# ============================================================
# Test End-to-End Data Flow
# ============================================================

@pytest.mark.asyncio
class TestEndToEndDataFlow:
    """Tests for end-to-end data flow"""

    async def test_end_to_end_data_flow(self, tmp_path):
        """Test 32: 端到端数据流"""
        # Arrange: Setup database path
        db_path = str(tmp_path / "test_e2e.db")

        # Create 15m-only sample klines
        klines_15m = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1704067200000,
                open=Decimal("42000.00"),
                high=Decimal("42500.00"),
                low=Decimal("41800.00"),
                close=Decimal("42300.00"),
                volume=Decimal("1000.0"),
                is_closed=True,
            ),
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1704068100000,
                open=Decimal("42300.00"),
                high=Decimal("42800.00"),
                low=Decimal("42200.00"),
                close=Decimal("42600.00"),
                volume=Decimal("1200.0"),
                is_closed=True,
            ),
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1704069000000,
                open=Decimal("42600.00"),
                high=Decimal("43000.00"),
                low=Decimal("42500.00"),
                close=Decimal("42900.00"),
                volume=Decimal("1500.0"),
                is_closed=True,
            ),
        ]

        # Create repository with mock gateway returning 15m klines
        mock_gateway = MagicMock(spec=ExchangeGateway)
        mock_gateway.fetch_historical_ohlcv = AsyncMock(return_value=klines_15m)

        repo = HistoricalDataRepository(db_path=db_path, exchange_gateway=mock_gateway)
        await repo.initialize()

        try:
            # Step 1: Save K-line data
            await repo._save_klines(klines_15m)

            # Step 2: Query K-line data with explicit limit to avoid fallback
            result = await repo.get_klines(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                limit=3,
            )

            # Assert: Data persisted correctly
            assert len(result) == 3  # 3 15m klines
            assert result[0].symbol == "BTC/USDT:USDT"
            assert result[0].timeframe == "15m"

            # Step 3: Count klines
            count = await repo.count_klines(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
            )
            assert count == 3

            # Step 4: Get time range
            min_ts, max_ts = await repo.get_kline_range(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
            )
            assert min_ts == 1704067200000
            assert max_ts == 1704069000000

        finally:
            await repo.close()

    async def test_data_repository_with_real_db(self, tmp_path, sample_klines):
        """Test 33: 真实数据库测试"""
        db_path = str(tmp_path / "test_real_db.db")

        # Create repository without gateway (pure local test)
        repo = HistoricalDataRepository(db_path=db_path, exchange_gateway=None)
        await repo.initialize()

        try:
            # Save data
            await repo._save_klines(sample_klines)

            # Verify database file exists
            assert os.path.exists(db_path)

            # Query data
            result = await repo.get_klines(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
            )

            assert len(result) == 3

            # Verify data integrity
            for original, saved in zip(sample_klines[:3], result):
                assert original.timestamp == saved.timestamp
                assert original.open == saved.open
                assert original.close == saved.close

        finally:
            await repo.close()


# ============================================================
# Test Backtest Report Repository Integration
# ============================================================

@pytest.mark.asyncio
class TestBacktestReportIntegration:
    """Tests for backtest report repository integration"""

    async def test_save_and_retrieve_backtest_report(self, tmp_path, sample_backtest_report):
        """Test: 保存和检索回测报告"""
        db_path = str(tmp_path / "test_backtest.db")

        repo = BacktestReportRepository(db_path=db_path)
        await repo.initialize()

        try:
            # Save report
            strategy_snapshot = '{"triggers": [{"type": "pinbar"}]}'
            await repo.save_report(
                sample_backtest_report,
                strategy_snapshot,
                "BTC/USDT:USDT",
                "15m",
            )

            # Get report by strategy
            reports = await repo.get_reports_by_strategy(
                strategy_id="pinbar_v1",
                limit=10,
            )

            assert len(reports) >= 1
            assert reports[0]["strategy_name"] == "Pinbar"

        finally:
            await repo.close()

    async def test_backtest_report_parameters_hash(self, tmp_path, sample_backtest_report):
        """Test: 回测报告参数哈希"""
        db_path = str(tmp_path / "test_hash.db")

        repo = BacktestReportRepository(db_path=db_path)
        await repo.initialize()

        try:
            # Save two reports with same parameters
            strategy_snapshot = '{"triggers": [{"type": "pinbar", "params": {"min_wick_ratio": 0.6}}]}'

            await repo.save_report(
                sample_backtest_report,
                strategy_snapshot,
                "BTC/USDT:USDT",
                "15m",
            )

            # Modify report slightly
            report2 = PMSBacktestReport(
                strategy_id="pinbar_v1",
                strategy_name="Pinbar",
                backtest_start=1704070800000,  # Different start time
                backtest_end=1704074400000,
                initial_balance=Decimal("10000"),
                final_balance=Decimal("10100"),
                total_return=Decimal("1.0"),
                total_trades=2,
                winning_trades=2,
                losing_trades=0,
                win_rate=Decimal("100.0"),
                total_pnl=Decimal("100"),
                total_fees_paid=Decimal("2"),
                total_slippage_cost=Decimal("1"),
                max_drawdown=Decimal("0.2"),
                positions=[],
            )

            await repo.save_report(
                report2,
                strategy_snapshot,  # Same parameters
                "BTC/USDT:USDT",
                "15m",
            )

            # Get reports by parameters hash
            params_hash = repo._calculate_parameters_hash(
                strategy_snapshot,
                "BTC/USDT:USDT",
                "15m",
            )

            reports = await repo.get_reports_by_parameters_hash(
                parameters_hash=params_hash,
                limit=10,
            )

            # Both reports should have same parameters hash
            assert len(reports) == 2

        finally:
            await repo.close()


# ============================================================
# Test Order Repository Integration
# ============================================================

@pytest.mark.asyncio
class TestOrderRepositoryIntegration:
    """Tests for order repository integration"""

    async def test_order_persistence(self, tmp_path):
        """Test: 订单持久化"""
        db_path = str(tmp_path / "test_orders.db")

        repo = OrderRepository(db_path=db_path)
        await repo.initialize()

        try:
            # Create order
            order = Order(
                id="order_test_001",
                signal_id="signal_001",
                symbol="BTC/USDT:USDT",
                direction=Direction.LONG,
                order_type=OrderType.MARKET,
                order_role=OrderRole.ENTRY,
                price=Decimal("42000.00"),
                trigger_price=None,
                requested_qty=Decimal("0.1"),
                filled_qty=Decimal("0.1"),
                average_exec_price=Decimal("42000.00"),
                status=OrderStatus.FILLED,
                reduce_only=False,
                parent_order_id=None,
                oco_group_id=None,
                exit_reason=None,
                exchange_order_id="exchange_001",
                filled_at=1704067200000,
                created_at=1704067200000,
                updated_at=1704067200000,
            )

            # Save order
            await repo.save(order)

            # Retrieve order
            retrieved = await repo.get_order("order_test_001")

            assert retrieved is not None
            assert retrieved.id == "order_test_001"
            assert retrieved.symbol == "BTC/USDT:USDT"
            assert retrieved.direction == Direction.LONG

        finally:
            await repo.close()

    async def test_order_query_by_signal(self, tmp_path):
        """Test: 按信号查询订单"""
        db_path = str(tmp_path / "test_order_query.db")

        repo = OrderRepository(db_path=db_path)
        await repo.initialize()

        try:
            # Create orders for different signals
            orders = [
                Order(
                    id=f"order_sig{i}_{j}",
                    signal_id=f"signal_{i}",
                    symbol="BTC/USDT:USDT",
                    direction=Direction.LONG,
                    order_type=OrderType.MARKET,
                    order_role=OrderRole.ENTRY,
                    price=Decimal("42000.00"),
                    trigger_price=None,
                    requested_qty=Decimal("0.1"),
                    filled_qty=Decimal("0.1"),
                    average_exec_price=Decimal("42000.00"),
                    status=OrderStatus.FILLED,
                    reduce_only=False,
                    parent_order_id=None,
                    oco_group_id=None,
                    exit_reason=None,
                    exchange_order_id=f"exchange_{i}_{j}",
                    filled_at=1704067200000 + j * 1000,
                    created_at=1704067200000 + j * 1000,
                    updated_at=1704067200000 + j * 1000,
                )
                for i in range(3)
                for j in range(2)
            ]

            # Save all orders
            for order in orders:
                await repo.save(order)

            # Query by signal
            result = await repo.get_orders_by_signal_ids(
                signal_ids=["signal_0", "signal_1"],
                page=1,
                page_size=10,
            )

            # Should return orders for signal_0 and signal_1 only
            assert result["total"] == 4

        finally:
            await repo.close()


# ============================================================
# Test Multi-Repository Integration
# ============================================================

@pytest.mark.asyncio
class TestMultiRepositoryIntegration:
    """Tests for multi-repository integration"""

    async def test_cross_repository_data_flow(self, tmp_path, sample_klines):
        """Test: 跨仓库数据流"""
        # Setup paths
        klines_db = str(tmp_path / "test_klines.db")
        orders_db = str(tmp_path / "test_orders.db")
        signals_db = str(tmp_path / "test_signals.db")
        backtest_db = str(tmp_path / "test_backtest.db")

        # Initialize repositories
        mock_gateway = MagicMock(spec=ExchangeGateway)
        mock_gateway.fetch_historical_ohlcv = AsyncMock(return_value=sample_klines)

        klines_repo = HistoricalDataRepository(db_path=klines_db, exchange_gateway=mock_gateway)
        orders_repo = OrderRepository(db_path=orders_db)
        signals_repo = SignalRepository(db_path=signals_db)
        backtest_repo = BacktestReportRepository(db_path=backtest_db)

        await klines_repo.initialize()
        await orders_repo.initialize()
        await signals_repo.initialize()
        await backtest_repo.initialize()

        try:
            # Step 1: Save K-line data
            await klines_repo._save_klines(sample_klines)

            # Step 2: Verify K-line data
            kline_count = await klines_repo.count_klines(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
            )
            assert kline_count == 3

            # Step 3: Save order
            order = Order(
                id="order_integration_001",
                signal_id="signal_integration_001",
                symbol="BTC/USDT:USDT",
                direction=Direction.LONG,
                order_type=OrderType.MARKET,
                order_role=OrderRole.ENTRY,
                price=Decimal("42000.00"),
                trigger_price=None,
                requested_qty=Decimal("0.1"),
                filled_qty=Decimal("0.1"),
                average_exec_price=Decimal("42000.00"),
                status=OrderStatus.FILLED,
                reduce_only=False,
                parent_order_id=None,
                oco_group_id=None,
                exit_reason=None,
                exchange_order_id="exchange_integration_001",
                filled_at=1704067200000,
                created_at=1704067200000,
                updated_at=1704067200000,
            )
            await orders_repo.save(order)

            # Step 4: Verify order
            retrieved_order = await orders_repo.get_order("order_integration_001")
            assert retrieved_order is not None
            assert retrieved_order.symbol == "BTC/USDT:USDT"

        finally:
            await klines_repo.close()
            await orders_repo.close()
            await signals_repo.close()
            await backtest_repo.close()


# ============================================================
# Test Concurrent Operations
# ============================================================

@pytest.mark.asyncio
class TestConcurrentOperations:
    """Tests for concurrent operations"""

    async def test_concurrent_kline_saves(self, tmp_path, sample_klines):
        """Test: 并发保存 K 线数据"""
        db_path = str(tmp_path / "test_concurrent.db")

        mock_gateway = MagicMock(spec=ExchangeGateway)
        mock_gateway.fetch_historical_ohlcv = AsyncMock(return_value=[])

        repo = HistoricalDataRepository(db_path=db_path, exchange_gateway=mock_gateway)
        await repo.initialize()

        try:
            # Concurrent saves
            await asyncio.gather(
                repo._save_klines(sample_klines),
                repo._save_klines(sample_klines),
                repo._save_klines(sample_klines),
            )

            # Verify no duplicates (idempotent)
            count = await repo.count_klines(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
            )
            assert count == 3

        finally:
            await repo.close()


# ============================================================
# Test Cleanup and Resource Management
# ============================================================

@pytest.mark.asyncio
class TestCleanupAndResourceManagement:
    """Tests for cleanup and resource management"""

    async def test_repository_close_cleanup(self, tmp_path):
        """Test: 仓库关闭清理"""
        db_path = str(tmp_path / "test_cleanup.db")

        repo = HistoricalDataRepository(db_path=db_path, exchange_gateway=None)
        await repo.initialize()

        # Close
        await repo.close()

        # Verify engine is disposed
        # Note: SQLAlchemy doesn't expose a direct 'disposed' property,
        # but we can verify by checking the repo can be re-initialized
        repo2 = HistoricalDataRepository(db_path=db_path, exchange_gateway=None)
        await repo2.initialize()
        await repo2.close()

    async def test_database_file_cleanup(self, tmp_path):
        """Test: 数据库文件清理"""
        db_path = str(tmp_path / "test_file_cleanup.db")

        repo = HistoricalDataRepository(db_path=db_path, exchange_gateway=None)
        await repo.initialize()
        await repo.close()

        # Database file should exist after close
        assert os.path.exists(db_path)

        # Manually cleanup
        os.remove(db_path)
        assert not os.path.exists(db_path)
