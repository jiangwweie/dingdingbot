"""
Unit tests for S6-2-3: Database Field Extensions.

Tests:
1. SignalStatus enum extensions (ACTIVE, SUPERSEDED)
2. SignalRepository new methods (update_signal_status, update_superseded_by, get_active_signal, get_opposing_signal)
3. Database schema migration (superseded_by, opposing_signal_id, opposing_signal_score columns)
"""
import pytest
import asyncio
from decimal import Decimal
from src.domain.models import SignalStatus, SignalResult, Direction
from src.infrastructure.signal_repository import SignalRepository


@pytest.fixture
async def repository():
    """Create a test repository instance."""
    repo = SignalRepository(db_path=":memory:")
    await repo.initialize()
    yield repo
    # Cleanup
    if repo._db:
        await repo._db.close()


class TestSignalStatusEnum:
    """Test SignalStatus enum extensions."""

    def test_active_status_exists(self):
        """Test that ACTIVE status exists."""
        assert hasattr(SignalStatus, "ACTIVE")
        assert SignalStatus.ACTIVE.value == "active"

    def test_superseded_status_exists(self):
        """Test that SUPERSEDED status exists."""
        assert hasattr(SignalStatus, "SUPERSEDED")
        assert SignalStatus.SUPERSEDED.value == "superseded"

    def test_all_statuses(self):
        """Test all signal statuses are available."""
        expected_statuses = {
            "GENERATED": "generated",
            "PENDING": "pending",
            "FILLED": "filled",
            "CANCELLED": "cancelled",
            "REJECTED": "rejected",
            "ACTIVE": "active",
            "SUPERSEDED": "superseded",
        }
        for name, value in expected_statuses.items():
            assert getattr(SignalStatus, name).value == value


class TestSignalRepositorySchema:
    """Test database schema migration."""

    @pytest.mark.asyncio
    async def test_new_columns_exist(self, repository):
        """Test that new columns are added to signals table."""
        # Get table info
        async with repository._db.execute("PRAGMA table_info(signals)") as cursor:
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

        # Check new columns
        assert "superseded_by" in column_names
        assert "opposing_signal_id" in column_names
        assert "opposing_signal_score" in column_names


class TestSignalRepositoryMethods:
    """Test new SignalRepository methods."""

    @pytest.mark.asyncio
    async def test_update_signal_status(self, repository):
        """Test updating signal status."""
        # Create a test signal with PENDING status (default)
        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("50000"),
            suggested_stop_loss=Decimal("49500"),
            suggested_position_size=Decimal("0.1"),
            current_leverage=10,
            tags=[],
            risk_reward_info="Risk 1% = 100 USDT",
        )

        signal_id = await repository.save_signal(signal, "test-signal-1", status="PENDING")

        # Update status to ACTIVE (uppercase) using new method
        await repository.update_signal_status_by_tracker_id(signal_id, "ACTIVE")

        # Verify - query by signal_id field
        async with repository._db.execute(
            "SELECT * FROM signals WHERE signal_id = ?", ("test-signal-1",)
        ) as cursor:
            result = await cursor.fetchone()

        assert result is not None
        assert result["status"] == "ACTIVE"

        # Update status to SUPERSEDED (uppercase)
        await repository.update_signal_status_by_tracker_id(signal_id, "SUPERSEDED")

        # Verify
        async with repository._db.execute(
            "SELECT * FROM signals WHERE signal_id = ?", ("test-signal-1",)
        ) as cursor:
            result = await cursor.fetchone()

        assert result is not None
        assert result["status"] == "SUPERSEDED"

    @pytest.mark.asyncio
    async def test_update_superseded_by(self, repository):
        """Test marking signal as superseded."""
        # Create two test signals
        signal1 = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("50000"),
            suggested_stop_loss=Decimal("49500"),
            suggested_position_size=Decimal("0.1"),
            current_leverage=10,
            tags=[],
            risk_reward_info="Risk 1% = 100 USDT",
            score=0.7,
        )

        signal2 = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("50100"),
            suggested_stop_loss=Decimal("49600"),
            suggested_position_size=Decimal("0.1"),
            current_leverage=10,
            tags=[],
            risk_reward_info="Risk 1% = 100 USDT",
            score=0.85,
        )

        signal_id1 = await repository.save_signal(signal1, "test-signal-1", status="active")
        signal_id2 = await repository.save_signal(signal2, "test-signal-2", status="active")

        # Mark signal1 as superseded by signal2
        await repository.update_superseded_by(signal_id1, signal_id2)

        # Verify signal1 is superseded
        result1 = await repository.get_signal_by_id(1)
        assert result1 is not None
        assert result1["status"] == "superseded"
        assert result1["superseded_by"] == signal_id2

        # Verify signal2 is still active
        result2 = await repository.get_signal_by_id(2)
        assert result2 is not None
        assert result2["status"] == "active"

    @pytest.mark.asyncio
    async def test_get_active_signal(self, repository):
        """Test getting active signal by dedup key."""
        # Create test signals
        signal1 = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("50000"),
            suggested_stop_loss=Decimal("49500"),
            suggested_position_size=Decimal("0.1"),
            current_leverage=10,
            tags=[],
            risk_reward_info="Risk 1% = 100 USDT",
            strategy_name="pinbar",
            score=0.7,
        )

        signal2 = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("50100"),
            suggested_stop_loss=Decimal("49600"),
            suggested_position_size=Decimal("0.1"),
            current_leverage=10,
            tags=[],
            risk_reward_info="Risk 1% = 100 USDT",
            strategy_name="pinbar",
            score=0.85,
        )

        # Create signals with same dedup key - use "ACTIVE" status (uppercase)
        await repository.save_signal(signal1, "test-signal-1", status="PENDING")
        await repository.save_signal(signal2, "test-signal-2", status="PENDING")

        # Update to ACTIVE status using new method
        await repository.update_signal_status_by_tracker_id("test-signal-1", "ACTIVE")
        await repository.update_signal_status_by_tracker_id("test-signal-2", "ACTIVE")

        # Get active signal by dedup key
        dedup_key = "BTC/USDT:USDT:15m:long:pinbar"
        active_signal = await repository.get_active_signal(dedup_key)

        # Should return the most recent active signal
        assert active_signal is not None, "Should find active signal"
        assert active_signal["symbol"] == "BTC/USDT:USDT"
        assert active_signal["timeframe"] == "15m"
        assert active_signal["direction"] == "long"
        assert active_signal["strategy_name"] == "pinbar"

    @pytest.mark.asyncio
    async def test_get_active_signal_returns_latest(self, repository):
        """Test that get_active_signal returns the latest active signal."""
        # Create two signals with different statuses
        signal1 = SignalResult(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            direction=Direction.SHORT,
            entry_price=Decimal("3000"),
            suggested_stop_loss=Decimal("3100"),
            suggested_position_size=Decimal("0.5"),
            current_leverage=5,
            tags=[],
            risk_reward_info="Risk 1% = 50 USDT",
            strategy_name="engulfing",
            score=0.75,
        )

        signal2 = SignalResult(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            direction=Direction.SHORT,
            entry_price=Decimal("3050"),
            suggested_stop_loss=Decimal("3150"),
            suggested_position_size=Decimal("0.5"),
            current_leverage=5,
            tags=[],
            risk_reward_info="Risk 1% = 50 USDT",
            strategy_name="engulfing",
            score=0.8,
        )

        await repository.save_signal(signal1, "test-signal-3", status="PENDING")
        await repository.save_signal(signal2, "test-signal-4", status="PENDING")

        # Update statuses using new method
        await repository.update_signal_status_by_tracker_id("test-signal-3", "SUPERSEDED")
        await repository.update_signal_status_by_tracker_id("test-signal-4", "ACTIVE")

        # Get active signal
        dedup_key = "ETH/USDT:USDT:1h:short:engulfing"
        active_signal = await repository.get_active_signal(dedup_key)

        # Should return signal2 (active), not signal1 (superseded)
        assert active_signal is not None, "Should find active signal"
        assert active_signal["signal_id"] == "test-signal-4"
        assert active_signal["status"] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_get_opposing_signal(self, repository):
        """Test getting opposing direction signal."""
        # Create LONG signal
        long_signal = SignalResult(
            symbol="SOL/USDT:USDT",
            timeframe="4h",
            direction=Direction.LONG,
            entry_price=Decimal("100"),
            suggested_stop_loss=Decimal("95"),
            suggested_position_size=Decimal("10"),
            current_leverage=3,
            tags=[],
            risk_reward_info="Risk 1% = 30 USDT",
            strategy_name="pinbar",
            score=0.8,
        )

        # Create SHORT signal
        short_signal = SignalResult(
            symbol="SOL/USDT:USDT",
            timeframe="4h",
            direction=Direction.SHORT,
            entry_price=Decimal("105"),
            suggested_stop_loss=Decimal("110"),
            suggested_position_size=Decimal("10"),
            current_leverage=3,
            tags=[],
            risk_reward_info="Risk 1% = 30 USDT",
            strategy_name="pinbar",
            score=0.75,
        )

        await repository.save_signal(long_signal, "test-long", status="active")
        await repository.save_signal(short_signal, "test-short", status="active")

        # Get opposing signal for LONG (should return SHORT)
        opposing = await repository.get_opposing_signal(
            "SOL/USDT:USDT", "4h", "long"
        )

        assert opposing is not None
        assert opposing["direction"] == "short"
        assert opposing["signal_id"] == "test-short"

        # Get opposing signal for SHORT (should return LONG)
        opposing = await repository.get_opposing_signal(
            "SOL/USDT:USDT", "4h", "short"
        )

        assert opposing is not None
        assert opposing["direction"] == "long"
        assert opposing["signal_id"] == "test-long"

    @pytest.mark.asyncio
    async def test_get_opposing_signal_none_when_no_opposing(self, repository):
        """Test that get_opposing_signal returns None when no opposing signal exists."""
        # Create only LONG signal
        long_signal = SignalResult(
            symbol="BNB/USDT:USDT",
            timeframe="1d",
            direction=Direction.LONG,
            entry_price=Decimal("300"),
            suggested_stop_loss=Decimal("280"),
            suggested_position_size=Decimal("1"),
            current_leverage=2,
            tags=[],
            risk_reward_info="Risk 1% = 20 USDT",
            strategy_name="pinbar",
            score=0.7,
        )

        await repository.save_signal(long_signal, "test-long-only", status="active")

        # Get opposing signal for LONG (should return None because no SHORT exists)
        opposing = await repository.get_opposing_signal(
            "BNB/USDT:USDT", "1d", "long"
        )

        # Should return None because there's no SHORT signal
        assert opposing is None, f"Should return None when no opposing signal exists, got: {opposing}"

    @pytest.mark.asyncio
    async def test_get_opposing_signal_excludes_superseded(self, repository):
        """Test that get_opposing_signal only returns ACTIVE signals."""
        # Create LONG signal (active)
        long_signal = SignalResult(
            symbol="XRP/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("0.5"),
            suggested_stop_loss=Decimal("0.48"),
            suggested_position_size=Decimal("1000"),
            current_leverage=5,
            tags=[],
            risk_reward_info="Risk 1% = 50 USDT",
            strategy_name="pinbar",
            score=0.7,
        )

        # Create SHORT signal (superseded)
        short_signal = SignalResult(
            symbol="XRP/USDT:USDT",
            timeframe="15m",
            direction=Direction.SHORT,
            entry_price=Decimal("0.52"),
            suggested_stop_loss=Decimal("0.54"),
            suggested_position_size=Decimal("1000"),
            current_leverage=5,
            tags=[],
            risk_reward_info="Risk 1% = 50 USDT",
            strategy_name="pinbar",
            score=0.6,
        )

        await repository.save_signal(long_signal, "test-long-active", status="active")
        await repository.save_signal(short_signal, "test-short-superseded", status="superseded")

        # Get opposing signal for LONG (should return None because SHORT is superseded)
        opposing = await repository.get_opposing_signal(
            "XRP/USDT:USDT", "15m", "long"
        )

        assert opposing is None


class TestIntegration:
    """Integration tests for signal covering workflow."""

    @pytest.mark.asyncio
    async def test_full_cover_workflow(self, repository):
        """Test the complete signal covering workflow."""
        # Step 1: Create initial signal (lower score)
        signal1 = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            direction=Direction.LONG,
            entry_price=Decimal("50000"),
            suggested_stop_loss=Decimal("49000"),
            suggested_position_size=Decimal("0.2"),
            current_leverage=10,
            tags=[{"name": "EMA", "value": "Bullish"}],
            risk_reward_info="Risk 1% = 200 USDT",
            strategy_name="pinbar",
            score=0.7,
        )

        signal_id1 = await repository.save_signal(signal1, "signal-1", status="PENDING")

        # Step 2: Create better signal (higher score)
        signal2 = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            direction=Direction.LONG,
            entry_price=Decimal("50200"),
            suggested_stop_loss=Decimal("49200"),
            suggested_position_size=Decimal("0.2"),
            current_leverage=10,
            tags=[{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Confirmed"}],
            risk_reward_info="Risk 1% = 200 USDT",
            strategy_name="pinbar",
            score=0.85,
        )

        signal_id2 = await repository.save_signal(signal2, "signal-2", status="PENDING")

        # Update both to ACTIVE first using new method
        await repository.update_signal_status_by_tracker_id(signal_id1, "ACTIVE")
        await repository.update_signal_status_by_tracker_id(signal_id2, "ACTIVE")

        # Step 3: Mark signal1 as superseded by signal2
        await repository.update_superseded_by(signal_id1, signal_id2)

        # Step 4: Verify signal1 is superseded
        async with repository._db.execute(
            "SELECT * FROM signals WHERE signal_id = ?", ("signal-1",)
        ) as cursor:
            result1 = await cursor.fetchone()

        assert result1 is not None
        assert result1["status"] == "superseded"  # update_superseded_by uses lowercase
        assert result1["superseded_by"] == signal_id2

        # Step 5: Verify signal2 is still active
        async with repository._db.execute(
            "SELECT * FROM signals WHERE signal_id = ?", ("signal-2",)
        ) as cursor:
            result2 = await cursor.fetchone()

        assert result2 is not None
        assert result2["status"] == "ACTIVE"

        # Step 6: Verify get_active_signal returns signal2
        dedup_key = "BTC/USDT:USDT:1h:long:pinbar"
        active = await repository.get_active_signal(dedup_key)
        assert active is not None, "Should find active signal"
        assert active["signal_id"] == signal_id2

        # Step 7: Verify get_opposing_signal works (should return None, no opposing signal)
        opposing = await repository.get_opposing_signal("BTC/USDT:USDT", "1h", "long")
        assert opposing is None  # No opposing SHORT signal
