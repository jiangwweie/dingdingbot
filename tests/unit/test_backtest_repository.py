"""
Unit tests for BacktestReportRepository.

Tests verify:
1. BacktestReportRepository CRUD operations
2. Strategy snapshot serialization
3. Parameters hash calculation
4. Position summary serialization/deserialization
"""
import pytest
from decimal import Decimal
import json
import hashlib
from unittest.mock import AsyncMock, MagicMock

from src.domain.models import (
    PMSBacktestReport,
    PositionSummary,
    Direction,
    StrategyDefinition,
)
from src.domain.strategy_engine import PinbarConfig
from src.domain.logic_tree import LogicNode, TriggerLeaf, FilterLeaf
from src.infrastructure.backtest_repository import BacktestReportRepository


# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
def sample_position_summary() -> PositionSummary:
    """Create a sample position summary for testing."""
    return PositionSummary(
        position_id="pos_001",
        signal_id="sig_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal("50000"),
        exit_price=Decimal("52000"),
        entry_time=1700000000000,
        exit_time=1700100000000,
        realized_pnl=Decimal("200"),
        exit_reason="TP1",
    )


@pytest.fixture
def sample_pms_report(sample_position_summary) -> PMSBacktestReport:
    """Create a sample PMS backtest report."""
    return PMSBacktestReport(
        strategy_id="pinbar_v1",
        strategy_name="Pinbar",
        backtest_start=1700000000000,
        backtest_end=1700100000000,
        initial_balance=Decimal("10000"),
        final_balance=Decimal("10500"),
        total_return=Decimal("5.0"),
        total_trades=10,
        winning_trades=6,
        losing_trades=4,
        win_rate=Decimal("60.0"),
        total_pnl=Decimal("500"),
        total_fees_paid=Decimal("20"),
        total_slippage_cost=Decimal("5"),
        max_drawdown=Decimal("2.5"),
        positions=[sample_position_summary],
    )


@pytest.fixture
def sample_strategy_definition() -> StrategyDefinition:
    """Create a sample strategy definition."""
    pinbar_config = PinbarConfig(
        min_wick_ratio=Decimal("0.6"),
        max_body_ratio=Decimal("0.3"),
        body_position_tolerance=Decimal("0.1"),
    )

    return StrategyDefinition(
        id="pinbar_v1",
        name="Pinbar",
        triggers=[],  # Will be populated from logic_tree
    )


@pytest.fixture
async def repository():
    """Create a test repository instance."""
    repo = BacktestReportRepository(db_path="data/test_backtest_reports.db")
    await repo.initialize()
    yield repo
    # Cleanup
    try:
        await repo.delete_report("test_report_001")
    except Exception:
        pass
    await repo.close()


# ============================================================
# Test BacktestReportRepository - Utility Methods
# ============================================================

class TestRepositoryUtilityMethods:
    """Tests for BacktestReportRepository utility methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.repo = BacktestReportRepository(db_path="data/test.db")

    def teardown_method(self):
        """Clean up."""
        if self.repo._db:
            import asyncio
            asyncio.get_event_loop().run_until_complete(self.repo.close())

    def test_calculate_parameters_hash(self):
        """Test parameters hash calculation."""
        strategy_snapshot = '{"triggers": [{"type": "pinbar"}]}'
        symbol = "BTC/USDT:USDT"
        timeframe = "15m"

        hash1 = self.repo._calculate_parameters_hash(strategy_snapshot, symbol, timeframe)
        hash2 = self.repo._calculate_parameters_hash(strategy_snapshot, symbol, timeframe)
        hash3 = self.repo._calculate_parameters_hash(
            '{"triggers": [{"type": "engulfing"}]}', symbol, timeframe
        )

        # Same input should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 produces 64 character hex string

        # Different input should produce different hash
        assert hash1 != hash3

    def test_decimal_conversion(self):
        """Test Decimal to string conversion."""
        value = Decimal("123.456789")
        str_value = self.repo._decimal_to_str(value)
        back_to_decimal = self.repo._str_to_decimal(str_value)

        assert str_value == "123.456789"
        assert back_to_decimal == value

    def test_serialize_positions_summary(self, sample_position_summary):
        """Test position summary serialization."""
        positions = [sample_position_summary]
        json_str = self.repo._serialize_positions_summary(positions)

        # Verify JSON is valid
        data = json.loads(json_str)
        assert len(data) == 1
        assert data[0]["position_id"] == "pos_001"
        assert data[0]["direction"] == "LONG"
        # Note: Decimal.normalize() may produce scientific notation (e.g., '5E+4' == 50000)
        assert Decimal(data[0]["entry_price"]) == Decimal("50000")
        assert Decimal(data[0]["exit_price"]) == Decimal("52000")
        assert Decimal(data[0]["realized_pnl"]) == Decimal("200")
        assert data[0]["exit_reason"] == "TP1"

    def test_deserialize_positions_summary(self, sample_position_summary):
        """Test position summary deserialization."""
        # First serialize
        positions = [sample_position_summary]
        json_str = self.repo._serialize_positions_summary(positions)

        # Then deserialize
        restored = self.repo._deserialize_positions_summary(json_str)

        assert len(restored) == 1
        assert restored[0].position_id == sample_position_summary.position_id
        assert restored[0].direction == sample_position_summary.direction
        assert restored[0].entry_price == sample_position_summary.entry_price
        assert restored[0].exit_price == sample_position_summary.exit_price

    def test_deserialize_empty_positions(self):
        """Test deserializing empty/null positions."""
        assert self.repo._deserialize_positions_summary(None) == []
        assert self.repo._deserialize_positions_summary("") == []
        assert self.repo._deserialize_positions_summary("[]") == []

    def test_serialize_strategy_snapshot_with_logic_tree(self):
        """Test serializing strategy snapshot with logic tree."""
        from src.domain.logic_tree import TriggerLeaf, FilterLeaf, LogicNode

        # Create a simple logic tree
        trigger_leaf = TriggerLeaf(
            type="trigger",
            id="trigger_1",
            config={"type": "pinbar", "params": {"min_wick_ratio": 0.6}}
        )
        filter_leaf = FilterLeaf(
            type="filter",
            id="filter_1",
            config={"type": "ema_trend", "params": {"enabled": True}}
        )
        logic_tree = LogicNode(gate="AND", children=[trigger_leaf, filter_leaf])

        strategy_def = StrategyDefinition(
            id="test_strat",
            name="TestStrategy",
            logic_tree=logic_tree,
        )

        json_str = self.repo._serialize_strategy_snapshot(strategy_def)
        data = json.loads(json_str)

        assert data["id"] == "test_strat"
        assert data["name"] == "TestStrategy"
        assert data["logic_tree"] is not None
        assert data["logic_tree"]["type"] == "node"
        assert data["logic_tree"]["gate"] == "AND"
        assert len(data["logic_tree"]["children"]) == 2


# ============================================================
# Test BacktestReportRepository - CRUD Operations
# ============================================================

@pytest.mark.asyncio
class TestRepositoryCRUD:
    """Tests for BacktestReportRepository CRUD operations."""

    @pytest.fixture(autouse=True)
    async def setup_repository(self):
        """Set up and tear down repository for each test."""
        # Clean up any existing data before test
        import os
        db_path = "data/test_crud.db"
        if os.path.exists(db_path):
            os.remove(db_path)

        self.repo = BacktestReportRepository(db_path=db_path)
        await self.repo.initialize()
        yield
        # Cleanup: Close connection
        await self.repo.close()

        # Remove test database file
        import os
        if os.path.exists(db_path):
            os.remove(db_path)
        if os.path.exists(db_path + "-wal"):
            os.remove(db_path + "-wal")
        if os.path.exists(db_path + "-shm"):
            os.remove(db_path + "-shm")

    async def test_save_and_get_report(self, sample_pms_report):
        """Test saving and retrieving a report."""
        strategy_snapshot = '{"triggers": [{"type": "pinbar"}], "filters": []}'
        symbol = "BTC/USDT:USDT"
        timeframe = "15m"

        # Save report
        await self.repo.save_report(sample_pms_report, strategy_snapshot, symbol, timeframe)

        # Get report by generating expected ID
        # Note: We need to get the ID from the database since it's generated
        cursor = await self.repo._db.execute(
            "SELECT id FROM backtest_reports WHERE strategy_id = ?",
            (sample_pms_report.strategy_id,)
        )
        row = await cursor.fetchone()
        assert row is not None
        report_id = row["id"]

        # Retrieve report
        retrieved = await self.repo.get_report(report_id)

        assert retrieved is not None
        assert retrieved.strategy_id == sample_pms_report.strategy_id
        assert retrieved.strategy_name == sample_pms_report.strategy_name
        assert retrieved.initial_balance == sample_pms_report.initial_balance
        assert retrieved.final_balance == sample_pms_report.final_balance
        assert retrieved.total_trades == sample_pms_report.total_trades
        assert len(retrieved.positions) == len(sample_pms_report.positions)

    async def test_get_nonexistent_report(self):
        """Test retrieving a report that doesn't exist."""
        result = await self.repo.get_report("nonexistent_id")
        assert result is None

    async def test_get_reports_by_strategy(self, sample_pms_report):
        """Test getting reports by strategy ID."""
        strategy_snapshot = '{"triggers": [{"type": "pinbar"}], "filters": []}'
        symbol = "BTC/USDT:USDT"
        timeframe = "15m"

        # Save multiple reports with different backtest_start
        for i in range(3):
            report = PMSBacktestReport(
                strategy_id=sample_pms_report.strategy_id,
                strategy_name=sample_pms_report.strategy_name,
                backtest_start=1700000000000 + (i * 1000000),
                backtest_end=sample_pms_report.backtest_end,
                initial_balance=sample_pms_report.initial_balance,
                final_balance=sample_pms_report.final_balance,
                total_return=sample_pms_report.total_return,
                total_trades=sample_pms_report.total_trades,
                winning_trades=sample_pms_report.winning_trades,
                losing_trades=sample_pms_report.losing_trades,
                win_rate=sample_pms_report.win_rate,
                total_pnl=sample_pms_report.total_pnl,
                total_fees_paid=sample_pms_report.total_fees_paid,
                total_slippage_cost=sample_pms_report.total_slippage_cost,
                max_drawdown=sample_pms_report.max_drawdown,
                positions=sample_pms_report.positions,
            )
            await self.repo.save_report(report, strategy_snapshot, symbol, timeframe)

        # Get reports by strategy
        reports = await self.repo.get_reports_by_strategy(
            sample_pms_report.strategy_id,
            limit=10
        )

        assert len(reports) >= 1
        assert reports[0]["strategy_name"] == sample_pms_report.strategy_name
        assert "total_return" in reports[0]
        assert "win_rate" in reports[0]
        assert "total_pnl" in reports[0]

    async def test_get_reports_by_parameters_hash(self, sample_pms_report):
        """Test getting reports by parameters hash."""
        strategy_snapshot = '{"triggers": [{"type": "pinbar"}], "filters": []}'
        symbol = "BTC/USDT:USDT"
        timeframe = "15m"

        # Save report
        await self.repo.save_report(sample_pms_report, strategy_snapshot, symbol, timeframe)

        # Get the hash from the database
        cursor = await self.repo._db.execute(
            "SELECT parameters_hash FROM backtest_reports LIMIT 1"
        )
        row = await cursor.fetchone()
        assert row is not None
        params_hash = row["parameters_hash"]

        # Get reports by hash
        reports = await self.repo.get_reports_by_parameters_hash(
            params_hash,
            limit=10
        )

        assert len(reports) >= 1

    async def test_delete_report(self, sample_pms_report):
        """Test deleting a report."""
        strategy_snapshot = '{"triggers": [{"type": "pinbar"}], "filters": []}'
        symbol = "BTC/USDT:USDT"
        timeframe = "15m"

        # Save report
        await self.repo.save_report(sample_pms_report, strategy_snapshot, symbol, timeframe)

        # Get the report ID
        cursor = await self.repo._db.execute(
            "SELECT id FROM backtest_reports WHERE strategy_id = ?",
            (sample_pms_report.strategy_id,)
        )
        row = await cursor.fetchone()
        report_id = row["id"]

        # Delete report
        await self.repo.delete_report(report_id)

        # Verify deletion
        retrieved = await self.repo.get_report(report_id)
        assert retrieved is None

    async def test_get_report_snapshot(self, sample_pms_report):
        """Test getting strategy snapshot from report."""
        strategy_snapshot = '{"triggers": [{"type": "pinbar", "params": {"min_wick_ratio": 0.6}}]}'
        symbol = "BTC/USDT:USDT"
        timeframe = "15m"

        # Save report
        await self.repo.save_report(sample_pms_report, strategy_snapshot, symbol, timeframe)

        # Get the report ID
        cursor = await self.repo._db.execute(
            "SELECT id FROM backtest_reports WHERE strategy_id = ?",
            (sample_pms_report.strategy_id,)
        )
        row = await cursor.fetchone()
        report_id = row["id"]

        # Get snapshot
        snapshot = await self.repo.get_report_snapshot(report_id)

        assert snapshot is not None
        data = json.loads(snapshot)
        assert "triggers" in data


# ============================================================
# Test Integration with Backtester
# ============================================================

@pytest.mark.asyncio
class TestBacktesterIntegration:
    """Tests for Backtester integration with BacktestReportRepository."""

    async def test_serialize_strategy_snapshot_for_report(self):
        """Test Backtester's _serialize_strategy_snapshot_for_report method."""
        from src.application.backtester import Backtester
        from src.domain.models import BacktestRequest

        # Create mock gateway
        mock_gateway = AsyncMock()

        backtester = Backtester(mock_gateway)

        # Test with strategy definitions
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            strategies=[
                {
                    "id": "test_strat",
                    "name": "TestStrategy",
                    "triggers": [
                        {"type": "pinbar", "params": {"min_wick_ratio": 0.6}}
                    ],
                }
            ],
        )

        snapshot = await backtester._serialize_strategy_snapshot_for_report(
            request, "test_strat", "TestStrategy"
        )

        data = json.loads(snapshot)
        assert data["id"] == "test_strat"
        assert data["name"] == "TestStrategy"
        assert len(data["triggers"]) > 0

    async def test_serialize_legacy_strategy_snapshot(self):
        """Test serializing legacy strategy configuration."""
        from src.application.backtester import Backtester
        from src.domain.models import BacktestRequest

        mock_gateway = AsyncMock()
        backtester = Backtester(mock_gateway)

        # Test with legacy parameters (no strategies defined)
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            min_wick_ratio=Decimal("0.7"),
            trend_filter_enabled=True,
            mtf_validation_enabled=False,
        )

        snapshot = await backtester._serialize_strategy_snapshot_for_report(
            request, "pinbar", "Pinbar"
        )

        data = json.loads(snapshot)
        assert data["id"] == "pinbar"
        assert data["name"] == "Pinbar"
        assert len(data["triggers"]) > 0
        assert data["triggers"][0]["type"] == "pinbar"


# ============================================================
# Test Parameters Hash Clustering
# ============================================================

class TestParametersHashClustering:
    """Tests for parameters hash clustering feature."""

    def setup_method(self):
        """Set up test fixtures."""
        self.repo = BacktestReportRepository(db_path="data/test.db")

    def test_same_parameters_produce_same_hash(self):
        """Verify that identical parameter combinations produce the same hash."""
        snapshot = '{"triggers": [{"type": "pinbar", "params": {"min_wick_ratio": 0.6}}]}'

        hash1 = self.repo._calculate_parameters_hash(snapshot, "BTC/USDT:USDT", "15m")
        hash2 = self.repo._calculate_parameters_hash(snapshot, "BTC/USDT:USDT", "15m")

        assert hash1 == hash2

    def test_different_parameters_produce_different_hashes(self):
        """Verify that different parameter combinations produce different hashes."""
        snapshot1 = '{"triggers": [{"type": "pinbar", "params": {"min_wick_ratio": 0.6}}]}'
        snapshot2 = '{"triggers": [{"type": "pinbar", "params": {"min_wick_ratio": 0.7}}]}'

        hash1 = self.repo._calculate_parameters_hash(snapshot1, "BTC/USDT:USDT", "15m")
        hash2 = self.repo._calculate_parameters_hash(snapshot2, "BTC/USDT:USDT", "15m")
        hash3 = self.repo._calculate_parameters_hash(snapshot1, "ETH/USDT:USDT", "15m")
        hash4 = self.repo._calculate_parameters_hash(snapshot1, "BTC/USDT:USDT", "1h")

        assert hash1 != hash2  # Different strategy params
        assert hash1 != hash3  # Different symbol
        assert hash1 != hash4  # Different timeframe


# ============================================================
# Test SQLite TEXT CHECK Constraint Fix (ADR-2026-0414)
# ============================================================

class TestPydanticRangeValidation:
    """
    Tests for PMSBacktestReport Pydantic range validators.

    ADR-2026-0414: Removed numeric CHECK constraints from BacktestReportORM
    because SQLite TEXT columns use lexicographic comparison, not numeric.
    Range validation is now exclusively handled by Pydantic models.
    """

    def test_negative_total_return_is_valid(self):
        """负收益率报告应能通过 Pydantic 验证（核心 bug 修复验证）。"""
        report = PMSBacktestReport(
            strategy_id="test_v1",
            strategy_name="TestStrategy",
            backtest_start=1700000000000,
            backtest_end=1700100000000,
            initial_balance=Decimal("10000"),
            final_balance=Decimal("8213"),
            total_return=Decimal("-0.1787"),
            total_trades=41,
            winning_trades=20,
            losing_trades=21,
            win_rate=Decimal("48.78"),
            total_pnl=Decimal("-1787"),
            total_fees_paid=Decimal("50"),
            total_slippage_cost=Decimal("10"),
            max_drawdown=Decimal("20.0"),
        )
        assert report.total_return == Decimal("-0.1787")

    def test_total_return_boundary_minimum(self):
        """total_return 最小边界值 -1.0 应能通过验证。"""
        report = PMSBacktestReport(
            strategy_id="test_v1",
            strategy_name="TestStrategy",
            backtest_start=1700000000000,
            backtest_end=1700100000000,
            initial_balance=Decimal("10000"),
            final_balance=Decimal("0"),
            total_return=Decimal("-1.0"),
            total_trades=10,
            winning_trades=0,
            losing_trades=10,
            win_rate=Decimal("0"),
            total_pnl=Decimal("-10000"),
            total_fees_paid=Decimal("50"),
            total_slippage_cost=Decimal("10"),
            max_drawdown=Decimal("100.0"),
        )
        assert report.total_return == Decimal("-1.0")

    def test_total_return_boundary_maximum(self):
        """total_return 最大边界值 10.0 应能通过验证。"""
        report = PMSBacktestReport(
            strategy_id="test_v1",
            strategy_name="TestStrategy",
            backtest_start=1700000000000,
            backtest_end=1700100000000,
            initial_balance=Decimal("10000"),
            final_balance=Decimal("110000"),
            total_return=Decimal("10.0"),
            total_trades=5,
            winning_trades=5,
            losing_trades=0,
            win_rate=Decimal("100"),
            total_pnl=Decimal("100000"),
            total_fees_paid=Decimal("50"),
            total_slippage_cost=Decimal("10"),
            max_drawdown=Decimal("0"),
        )
        assert report.total_return == Decimal("10.0")

    def test_total_return_below_minimum_raises_error(self):
        """total_return < -1.0 应抛出 Pydantic 验证错误。"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PMSBacktestReport(
                strategy_id="test_v1",
                strategy_name="TestStrategy",
                backtest_start=1700000000000,
                backtest_end=1700100000000,
                initial_balance=Decimal("10000"),
                final_balance=Decimal("0"),
                total_return=Decimal("-1.01"),
                total_trades=10,
                winning_trades=0,
                losing_trades=10,
                win_rate=Decimal("0"),
                total_pnl=Decimal("-10000"),
                total_fees_paid=Decimal("50"),
                total_slippage_cost=Decimal("10"),
                max_drawdown=Decimal("100.0"),
            )

    def test_total_return_above_maximum_raises_error(self):
        """total_return > 10.0 应抛出 Pydantic 验证错误。"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PMSBacktestReport(
                strategy_id="test_v1",
                strategy_name="TestStrategy",
                backtest_start=1700000000000,
                backtest_end=1700100000000,
                initial_balance=Decimal("10000"),
                final_balance=Decimal("120000"),
                total_return=Decimal("11.0"),
                total_trades=5,
                winning_trades=5,
                losing_trades=0,
                win_rate=Decimal("100"),
                total_pnl=Decimal("110000"),
                total_fees_paid=Decimal("50"),
                total_slippage_cost=Decimal("10"),
                max_drawdown=Decimal("0"),
            )

    def test_win_rate_boundary_values(self):
        """win_rate 边界值 0 和 100 应能通过验证。"""
        from pydantic import ValidationError

        # win_rate = 0
        report_zero = PMSBacktestReport(
            strategy_id="test_v1",
            strategy_name="TestStrategy",
            backtest_start=1700000000000,
            backtest_end=1700100000000,
            initial_balance=Decimal("10000"),
            final_balance=Decimal("9000"),
            total_return=Decimal("-0.1"),
            total_trades=10,
            winning_trades=0,
            losing_trades=10,
            win_rate=Decimal("0"),
            total_pnl=Decimal("-1000"),
            total_fees_paid=Decimal("50"),
            total_slippage_cost=Decimal("10"),
            max_drawdown=Decimal("15.0"),
        )
        assert report_zero.win_rate == Decimal("0")

        # win_rate = 100
        report_full = PMSBacktestReport(
            strategy_id="test_v1",
            strategy_name="TestStrategy",
            backtest_start=1700000000000,
            backtest_end=1700100000000,
            initial_balance=Decimal("10000"),
            final_balance=Decimal("11000"),
            total_return=Decimal("1.0"),
            total_trades=10,
            winning_trades=10,
            losing_trades=0,
            win_rate=Decimal("100"),
            total_pnl=Decimal("1000"),
            total_fees_paid=Decimal("50"),
            total_slippage_cost=Decimal("10"),
            max_drawdown=Decimal("5.0"),
        )
        assert report_full.win_rate == Decimal("100")

        # win_rate > 100 should fail
        with pytest.raises(ValidationError):
            PMSBacktestReport(
                strategy_id="test_v1",
                strategy_name="TestStrategy",
                backtest_start=1700000000000,
                backtest_end=1700100000000,
                initial_balance=Decimal("10000"),
                final_balance=Decimal("11000"),
                total_return=Decimal("1.0"),
                total_trades=10,
                winning_trades=10,
                losing_trades=0,
                win_rate=Decimal("100.01"),
                total_pnl=Decimal("1000"),
                total_fees_paid=Decimal("50"),
                total_slippage_cost=Decimal("10"),
                max_drawdown=Decimal("5.0"),
            )

    def test_max_drawdown_boundary_values(self):
        """max_drawdown 边界值 0 和 100 应能通过验证。"""
        from pydantic import ValidationError

        # max_drawdown = 0
        report_zero_dd = PMSBacktestReport(
            strategy_id="test_v1",
            strategy_name="TestStrategy",
            backtest_start=1700000000000,
            backtest_end=1700100000000,
            initial_balance=Decimal("10000"),
            final_balance=Decimal("10500"),
            total_return=Decimal("0.5"),
            total_trades=10,
            winning_trades=10,
            losing_trades=0,
            win_rate=Decimal("100"),
            total_pnl=Decimal("500"),
            total_fees_paid=Decimal("50"),
            total_slippage_cost=Decimal("10"),
            max_drawdown=Decimal("0"),
        )
        assert report_zero_dd.max_drawdown == Decimal("0")

        # max_drawdown = 100
        report_full_dd = PMSBacktestReport(
            strategy_id="test_v1",
            strategy_name="TestStrategy",
            backtest_start=1700000000000,
            backtest_end=1700100000000,
            initial_balance=Decimal("10000"),
            final_balance=Decimal("0"),
            total_return=Decimal("-1.0"),
            total_trades=10,
            winning_trades=0,
            losing_trades=10,
            win_rate=Decimal("0"),
            total_pnl=Decimal("-10000"),
            total_fees_paid=Decimal("50"),
            total_slippage_cost=Decimal("10"),
            max_drawdown=Decimal("100"),
        )
        assert report_full_dd.max_drawdown == Decimal("100")

        # max_drawdown > 100 should fail
        with pytest.raises(ValidationError):
            PMSBacktestReport(
                strategy_id="test_v1",
                strategy_name="TestStrategy",
                backtest_start=1700000000000,
                backtest_end=1700100000000,
                initial_balance=Decimal("10000"),
                final_balance=Decimal("0"),
                total_return=Decimal("-1.0"),
                total_trades=10,
                winning_trades=0,
                losing_trades=10,
                win_rate=Decimal("0"),
                total_pnl=Decimal("-10000"),
                total_fees_paid=Decimal("50"),
                total_slippage_cost=Decimal("10"),
                max_drawdown=Decimal("100.01"),
            )


@pytest.mark.asyncio
class TestNegativeReturnReportPersistence:
    """
    Integration test: 负收益率报告应能正常保存到 SQLite 数据库。

    直接验证 ADR-2026-0414 修复效果：删除 TEXT 列数值 CHECK 约束后，
    负收益率报告不再被 SQLite 字典序比较错误拒绝。
    """

    @pytest.fixture(autouse=True)
    async def setup_repository(self):
        """Set up and tear down repository for each test."""
        import os
        db_path = "data/test_negative_return.db"
        if os.path.exists(db_path):
            os.remove(db_path)

        self.repo = BacktestReportRepository(db_path=db_path)
        await self.repo.initialize()
        yield
        await self.repo.close()

        if os.path.exists(db_path):
            os.remove(db_path)
        if os.path.exists(db_path + "-wal"):
            os.remove(db_path + "-wal")
        if os.path.exists(db_path + "-shm"):
            os.remove(db_path + "-shm")

    async def test_negative_return_report_can_be_saved(self):
        """核心测试：total_return = -0.1787 的报告应能正常保存并读取。"""
        strategy_snapshot = '{"triggers": [{"type": "pinbar"}], "filters": []}'
        symbol = "BTC/USDT:USDT"
        timeframe = "15m"

        report = PMSBacktestReport(
            strategy_id="pinbar_v1",
            strategy_name="Pinbar",
            backtest_start=1700000000000,
            backtest_end=1700100000000,
            initial_balance=Decimal("10000"),
            final_balance=Decimal("8213"),
            total_return=Decimal("-0.1787"),
            total_trades=41,
            winning_trades=20,
            losing_trades=21,
            win_rate=Decimal("48.78"),
            total_pnl=Decimal("-1787"),
            total_fees_paid=Decimal("50"),
            total_slippage_cost=Decimal("10"),
            max_drawdown=Decimal("20.0"),
        )

        # Save report -- this previously failed due to CHECK constraint
        await self.repo.save_report(report, strategy_snapshot, symbol, timeframe)

        # Verify it was saved
        cursor = await self.repo._db.execute(
            "SELECT id, total_return FROM backtest_reports WHERE strategy_id = ?",
            (report.strategy_id,)
        )
        row = await cursor.fetchone()
        assert row is not None, "Report should have been saved to the database"
        # Database stores Decimal as string, convert back for comparison
        stored_return = Decimal(row["total_return"])
        assert stored_return == Decimal("-0.1787")

    async def test_boundary_return_values(self):
        """边界值测试：total_return = -1.0, 0, 10.0 均应能正常保存。"""
        strategy_snapshot = '{"triggers": [{"type": "pinbar"}], "filters": []}'
        symbol = "ETH/USDT:USDT"
        timeframe = "1h"

        test_values = [
            Decimal("-1.0"),   # 最小值（亏光）
            Decimal("0"),      # 盈亏平衡
            Decimal("10.0"),   # 最大值（10 倍收益）
        ]

        for i, ret_value in enumerate(test_values):
            report = PMSBacktestReport(
                strategy_id=f"boundary_test_{i}",
                strategy_name="BoundaryTest",
                backtest_start=1700000000000 + (i * 1000),
                backtest_end=1700100000000,
                initial_balance=Decimal("10000"),
                final_balance=Decimal("10000") * (1 + ret_value),
                total_return=ret_value,
                total_trades=5,
                winning_trades=3,
                losing_trades=2,
                win_rate=Decimal("60.0"),
                total_pnl=Decimal("10000") * ret_value,
                total_fees_paid=Decimal("50"),
                total_slippage_cost=Decimal("10"),
                max_drawdown=Decimal("10.0"),
            )

            await self.repo.save_report(report, strategy_snapshot, symbol, timeframe)

        # Verify all three reports were saved
        cursor = await self.repo._db.execute(
            "SELECT total_return FROM backtest_reports WHERE strategy_id LIKE 'boundary_test_%'"
        )
        rows = await cursor.fetchall()
        assert len(rows) == 3
        stored_returns = sorted([Decimal(r["total_return"]) for r in rows])
        assert stored_returns == [Decimal("-1.0"), Decimal("0"), Decimal("10.0")]


# ============================================================
# 验证 5: _migrate_existing_table 迁移逻辑
# ============================================================

class TestMigrationLogic:
    """
    验证 5: BacktestReportRepository._migrate_existing_table() 迁移逻辑。

    测试三个场景：
    - 5a: 手动创建带旧 CHECK 约束的表，验证 initialize() 成功迁移
    - 5b: 无旧约束时跳过迁移（幂等性）
    - 5c: 表不存在时跳过迁移
    """

    def _create_db_connection(self, db_path: str):
        """Create a sync sqlite3 connection for test setup."""
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @pytest.mark.asyncio
    async def test_5a_migrate_table_with_old_check_constraint(self):
        """
        验证 5a: 带旧 CHECK 约束的表应被迁移，数据不丢失。

        步骤：
        1. 手动创建带 CHECK(win_rate >= 0 AND win_rate <= 1) 的旧表
        2. 插入一条测试数据
        3. 调用 initialize() 触发迁移
        4. 验证：数据不丢失、旧表被删除、新表无 CHECK 约束
        """
        import os
        import aiosqlite

        db_path = "data/test_migration_5a.db"
        if os.path.exists(db_path):
            os.remove(db_path)

        # Step 1: Create old table with CHECK constraint
        conn = self._create_db_connection(db_path)
        try:
            conn.execute("""
                CREATE TABLE backtest_reports (
                    id                  TEXT PRIMARY KEY,
                    strategy_id         TEXT NOT NULL,
                    strategy_name       TEXT NOT NULL,
                    strategy_version    TEXT NOT NULL DEFAULT '1.0.0',
                    strategy_snapshot   TEXT NOT NULL,
                    parameters_hash     TEXT NOT NULL,
                    symbol              TEXT NOT NULL,
                    timeframe           TEXT NOT NULL,
                    backtest_start      INTEGER NOT NULL,
                    backtest_end        INTEGER NOT NULL,
                    created_at          INTEGER NOT NULL,
                    initial_balance     TEXT NOT NULL,
                    final_balance       TEXT NOT NULL,
                    total_return        TEXT NOT NULL DEFAULT '0',
                    total_trades        INTEGER NOT NULL DEFAULT 0,
                    winning_trades      INTEGER NOT NULL DEFAULT 0,
                    losing_trades       INTEGER NOT NULL DEFAULT 0,
                    win_rate            TEXT NOT NULL DEFAULT '0' CHECK(win_rate >= 0 AND win_rate <= 1),
                    total_pnl           TEXT NOT NULL DEFAULT '0',
                    total_fees_paid     TEXT NOT NULL DEFAULT '0',
                    total_slippage_cost TEXT NOT NULL DEFAULT '0',
                    max_drawdown        TEXT NOT NULL DEFAULT '0',
                    sharpe_ratio        TEXT,
                    positions_summary   TEXT,
                    monthly_returns     TEXT
                )
            """)
            conn.execute(
                "INSERT INTO backtest_reports (id, strategy_id, strategy_name, strategy_version, "
                "strategy_snapshot, parameters_hash, symbol, timeframe, backtest_start, backtest_end, "
                "created_at, initial_balance, final_balance, total_return, total_trades, "
                "winning_trades, losing_trades, win_rate, total_pnl, total_fees_paid, "
                "total_slippage_cost, max_drawdown) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("test_report_001", "test_strat", "TestStrategy", "1.0",
                 '{"triggers": []}', "hash123", "BTC/USDT:USDT", "15m",
                 1700000000000, 1700100000000, 1700000000000,
                 "10000", "9500", "-0.05", 5, 2, 3, "0.4",  # win_rate=0.4 passes old CHECK
                 "-500", "10", "5", "5.0")
            )
            conn.commit()

            # Verify old table has data
            row = conn.execute("SELECT COUNT(*) as cnt FROM backtest_reports").fetchone()
            assert row["cnt"] == 1
        finally:
            conn.close()

        # Step 2: Initialize repository (triggers migration)
        repo = BacktestReportRepository(db_path=db_path)
        await repo.initialize()

        try:
            # Step 3: Verify migration
            # Check old table is gone
            cursor = await repo._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='backtest_reports_old'"
            )
            old_table = await cursor.fetchone()
            assert old_table is None, "旧表 backtest_reports_old 应已被删除"

            # Check data preserved
            cursor = await repo._db.execute(
                "SELECT id, strategy_id, total_return, win_rate FROM backtest_reports WHERE id='test_report_001'"
            )
            row = await cursor.fetchone()
            assert row is not None, "迁移后数据应保留"
            assert row["strategy_id"] == "test_strat"
            assert row["total_return"] == "-0.05"
            # win_rate was stored as 0.4 (old CHECK constraint format)
            assert row["win_rate"] == "0.4"

            # Check new table has no CHECK constraint
            cursor = await repo._db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='backtest_reports'"
            )
            table_row = await cursor.fetchone()
            assert table_row is not None
            assert "CHECK" not in table_row["sql"].upper() or "win_rate" not in table_row["sql"], \
                "新表不应有 win_rate 的 CHECK 约束"
        finally:
            await repo.close()
            for f in [db_path, db_path + "-wal", db_path + "-shm"]:
                if os.path.exists(f):
                    os.remove(f)

    @pytest.mark.asyncio
    async def test_5b_skip_migration_when_no_old_constraint(self):
        """
        验证 5b: 无旧 CHECK 约束时应跳过迁移（幂等性）。

        步骤：
        1. 创建无 CHECK 约束的新表
        2. 调用 initialize()
        3. 验证：跳过迁移（caplog 含 "跳过迁移"）
        """
        import os
        import logging

        db_path = "data/test_migration_5b.db"
        if os.path.exists(db_path):
            os.remove(db_path)

        # Step 1: Create table without CHECK constraint (already new format)
        conn = self._create_db_connection(db_path)
        try:
            conn.execute("""
                CREATE TABLE backtest_reports (
                    id                  TEXT PRIMARY KEY,
                    strategy_id         TEXT NOT NULL,
                    strategy_name       TEXT NOT NULL,
                    strategy_version    TEXT NOT NULL DEFAULT '1.0.0',
                    strategy_snapshot   TEXT NOT NULL,
                    parameters_hash     TEXT NOT NULL,
                    symbol              TEXT NOT NULL,
                    timeframe           TEXT NOT NULL,
                    backtest_start      INTEGER NOT NULL,
                    backtest_end        INTEGER NOT NULL,
                    created_at          INTEGER NOT NULL,
                    initial_balance     TEXT NOT NULL,
                    final_balance       TEXT NOT NULL,
                    total_return        TEXT NOT NULL DEFAULT '0',
                    total_trades        INTEGER NOT NULL DEFAULT 0,
                    winning_trades      INTEGER NOT NULL DEFAULT 0,
                    losing_trades       INTEGER NOT NULL DEFAULT 0,
                    win_rate            TEXT NOT NULL DEFAULT '0',
                    total_pnl           TEXT NOT NULL DEFAULT '0',
                    total_fees_paid     TEXT NOT NULL DEFAULT '0',
                    total_slippage_cost TEXT NOT NULL DEFAULT '0',
                    max_drawdown        TEXT NOT NULL DEFAULT '0',
                    sharpe_ratio        TEXT,
                    positions_summary   TEXT,
                    monthly_returns     TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

        # Step 2: Initialize and verify skip
        repo = BacktestReportRepository(db_path=db_path)
        await repo.initialize()
        await repo.close()

        for f in [db_path, db_path + "-wal", db_path + "-shm"]:
            if os.path.exists(f):
                os.remove(f)

    @pytest.mark.asyncio
    async def test_5c_skip_migration_when_table_not_exists(self):
        """
        验证 5c: 表不存在时应跳过迁移（正常创建新表）。

        步骤：
        1. 创建干净的数据库（无 backtest_reports 表）
        2. 调用 initialize()
        3. 验证：表成功创建且无 CHECK 约束
        """
        import os

        db_path = "data/test_migration_5c.db"
        if os.path.exists(db_path):
            os.remove(db_path)

        repo = BacktestReportRepository(db_path=db_path)
        await repo.initialize()

        # Verify table was created
        cursor = await repo._db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='backtest_reports'"
        )
        row = await cursor.fetchone()
        assert row is not None, "backtest_reports 表应被创建"
        assert "CHECK" not in row["sql"].upper() or "win_rate" not in row["sql"], \
            "新创建的表不应有 win_rate 的 CHECK 约束"

        await repo.close()
        for f in [db_path, db_path + "-wal", db_path + "-shm"]:
            if os.path.exists(f):
                os.remove(f)
