"""
Test SignalRepository - SQLite persistence for trading signals.
"""
import pytest
import asyncio
import json
import os
import tempfile
import uuid
from decimal import Decimal

import src.infrastructure.connection_pool as pool_module
from src.infrastructure.connection_pool import ConnectionPool, close_all_connections
from src.infrastructure.signal_repository import SignalRepository
from src.domain.models import SignalResult, Direction
from src.domain.strategy_engine import SignalAttempt, PatternResult, FilterResult


@pytest.fixture
async def repository():
    """Create an isolated repository for each test."""
    # Reset pool singleton to ensure fresh state
    ConnectionPool._instance = None
    pool_module._pool = ConnectionPool.get_instance()

    # Use unique temp file to prevent data bleeding between tests
    db_path = os.path.join(tempfile.gettempdir(), f"test_signal_repo_{uuid.uuid4().hex[:8]}.db")
    repo = SignalRepository(db_path)
    await repo.initialize()
    yield repo
    await repo.close()
    await close_all_connections()

    # Cleanup temp file
    if os.path.exists(db_path):
        os.unlink(db_path)

    # Reset pool to avoid stale state
    ConnectionPool._instance = None
    pool_module._pool = ConnectionPool.get_instance()


class TestSignalRepository:
    """Test SignalRepository basic operations."""

    @pytest.mark.asyncio
    async def test_initialize_creates_table(self, repository):
        """Test that initialize creates the signals table."""
        async with repository._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='signals'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row["name"] == "signals"

    @pytest.mark.asyncio
    async def test_save_and_query_signal(self, repository):
        """Test saving a signal and querying it back."""
        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            direction=Direction.LONG,
            entry_price=Decimal("35000.00"),
            suggested_stop_loss=Decimal("34500.00"),
            suggested_position_size=Decimal("1.5"),
            current_leverage=5,
            tags=[{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Confirmed"}],
            risk_reward_info="Risk 1% = 750 USDT",
        )

        await repository.save_signal(signal)
        result = await repository.get_signals(limit=10)

        signals = result["data"]
        assert len(signals) == 1
        assert result["total"] == 1
        saved = signals[0]
        assert saved["symbol"] == "BTC/USDT:USDT"
        assert saved["timeframe"] == "1h"
        assert saved["direction"] == "LONG"
        assert saved["entry_price"] == "35000.00"
        assert saved["stop_loss"] == "34500.00"
        assert saved["position_size"] == "1.5"
        assert saved["leverage"] == 5
        # Repository returns tags_json as the stored JSON string
        import json
        assert json.loads(saved["tags_json"]) == [{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Confirmed"}]
        assert saved["risk_info"] == "Risk 1% = 750 USDT"

    @pytest.mark.asyncio
    async def test_query_filter_by_symbol(self, repository):
        """Test filtering signals by symbol."""
        signal_btc = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            direction=Direction.LONG,
            entry_price=Decimal("35000.00"),
            suggested_stop_loss=Decimal("34500.00"),
            suggested_position_size=Decimal("1.5"),
            current_leverage=5,
            tags=[{"name": "EMA", "value": "Bullish"}],
            risk_reward_info="Risk 1% = 750 USDT",
        )

        signal_eth = SignalResult(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            direction=Direction.LONG,
            entry_price=Decimal("2200.00"),
            suggested_stop_loss=Decimal("2150.00"),
            suggested_position_size=Decimal("10.0"),
            current_leverage=3,
            tags=[{"name": "EMA", "value": "Bullish"}],
            risk_reward_info="Risk 1% = 500 USDT",
        )

        await repository.save_signal(signal_btc)
        await repository.save_signal(signal_eth)

        # Filter by BTC
        result = await repository.get_signals(limit=10, symbol="BTC/USDT:USDT")
        btc_signals = result["data"]
        assert len(btc_signals) == 1
        assert result["total"] == 1
        assert btc_signals[0]["symbol"] == "BTC/USDT:USDT"

        # Filter by ETH
        result = await repository.get_signals(limit=10, symbol="ETH/USDT:USDT")
        eth_signals = result["data"]
        assert len(eth_signals) == 1
        assert result["total"] == 1
        assert eth_signals[0]["symbol"] == "ETH/USDT:USDT"

    @pytest.mark.asyncio
    async def test_query_filter_by_direction(self, repository):
        """Test filtering signals by direction."""
        signal_long = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            direction=Direction.LONG,
            entry_price=Decimal("35000.00"),
            suggested_stop_loss=Decimal("34500.00"),
            suggested_position_size=Decimal("1.5"),
            current_leverage=5,
            tags=[{"name": "EMA", "value": "Bullish"}],
            risk_reward_info="Risk 1% = 750 USDT",
        )

        signal_short = SignalResult(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            direction=Direction.SHORT,
            entry_price=Decimal("2200.00"),
            suggested_stop_loss=Decimal("2250.00"),
            suggested_position_size=Decimal("10.0"),
            current_leverage=3,
            tags=[{"name": "EMA", "value": "Bearish"}],
            risk_reward_info="Risk 1% = 500 USDT",
        )

        await repository.save_signal(signal_long)
        await repository.save_signal(signal_short)

        # Filter by LONG
        result = await repository.get_signals(limit=10, direction="LONG")
        long_signals = result["data"]
        assert len(long_signals) == 1
        assert result["total"] == 1
        assert long_signals[0]["direction"] == "LONG"

        # Filter by SHORT
        result = await repository.get_signals(limit=10, direction="SHORT")
        short_signals = result["data"]
        assert len(short_signals) == 1
        assert result["total"] == 1
        assert short_signals[0]["direction"] == "SHORT"

    @pytest.mark.asyncio
    async def test_stats_counts_correctly(self, repository):
        """Test that stats returns correct counts."""
        # Save 2 LONG signals
        for i in range(2):
            signal_long = SignalResult(
                symbol="BTC/USDT:USDT",
                timeframe="1h",
                direction=Direction.LONG,
                entry_price=Decimal("35000.00"),
                suggested_stop_loss=Decimal("34500.00"),
                suggested_position_size=Decimal("1.5"),
                current_leverage=5,
                tags=[{"name": "EMA", "value": "Bullish"}],
                risk_reward_info=f"Risk 1% = {750 + i} USDT",
                status="PENDING",
                pnl_ratio=0.0,
            )
            await repository.save_signal(signal_long)

        # Save 1 SHORT signal
        signal_short = SignalResult(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            direction=Direction.SHORT,
            entry_price=Decimal("2200.00"),
            suggested_stop_loss=Decimal("2250.00"),
            suggested_position_size=Decimal("10.0"),
            current_leverage=3,
            tags=[{"name": "EMA", "value": "Bearish"}],
            risk_reward_info="Risk 1% = 500 USDT",
            status="PENDING",
            pnl_ratio=0.0,
        )
        await repository.save_signal(signal_short)

        stats = await repository.get_stats()

        assert stats["total"] == 3
        assert stats["long_count"] == 2
        assert stats["short_count"] == 1
        assert stats["won_count"] == 0
        assert stats["lost_count"] == 0
        assert stats["win_rate"] == 0.0
        # today count depends on current UTC date
        assert stats["today"] >= 0

    @pytest.mark.asyncio
    async def test_decimal_precision_preserved(self, repository):
        """Test that Decimal precision is preserved through string storage."""
        high_precision_signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("35000.12345678"),
            suggested_stop_loss=Decimal("34999.98765432"),
            suggested_position_size=Decimal("1.23456789"),
            current_leverage=5,
            tags=[{"name": "EMA", "value": "Bullish"}],
            risk_reward_info="Risk 1% = 123.456789 USDT",
        )

        await repository.save_signal(high_precision_signal)
        result = await repository.get_signals(limit=10)
        signals = result["data"]

        assert len(signals) == 1
        saved = signals[0]

        # Verify precision is preserved as strings
        assert saved["entry_price"] == "35000.12345678"
        assert saved["stop_loss"] == "34999.98765432"
        assert saved["position_size"] == "1.23456789"

        # Verify we can convert back to Decimal without precision loss
        entry_back = Decimal(saved["entry_price"])
        stop_back = Decimal(saved["stop_loss"])
        size_back = Decimal(saved["position_size"])

        assert entry_back == Decimal("35000.12345678")
        assert stop_back == Decimal("34999.98765432")
        assert size_back == Decimal("1.23456789")

    @pytest.mark.asyncio
    async def test_pagination_limit_offset(self, repository):
        """Test pagination with limit and offset."""
        # Save 5 signals
        for i in range(5):
            signal = SignalResult(
                symbol="BTC/USDT:USDT",
                timeframe="1h",
                direction=Direction.LONG,
                entry_price=Decimal(f"{35000 + i}"),
                suggested_stop_loss=Decimal(f"{34500 + i}"),
                suggested_position_size=Decimal("1.5"),
                current_leverage=5,
                tags=[{"name": "EMA", "value": "Bullish"}],
                risk_reward_info=f"Risk 1% = {750 + i} USDT",
            )
            await repository.save_signal(signal)

        # Get first 2 (limit=2, offset=0)
        result = await repository.get_signals(limit=2, offset=0)
        first_page = result["data"]
        assert len(first_page) == 2
        assert result["total"] == 5
        # Results are ordered by created_at DESC, so first page has highest entry_price
        assert first_page[0]["entry_price"] == "35004"
        assert first_page[1]["entry_price"] == "35003"

        # Get next 2 (limit=2, offset=2)
        result = await repository.get_signals(limit=2, offset=2)
        second_page = result["data"]
        assert len(second_page) == 2
        assert result["total"] == 5
        assert second_page[0]["entry_price"] == "35002"
        assert second_page[1]["entry_price"] == "35001"

        # Get last 1 (limit=2, offset=4)
        result = await repository.get_signals(limit=2, offset=4)
        third_page = result["data"]
        assert len(third_page) == 1
        assert result["total"] == 5
        assert third_page[0]["entry_price"] == "35000"


class TestSignalAttempts:
    """Test SignalRepository signal_attempts table operations."""

    @pytest.mark.asyncio
    async def test_save_attempt_no_pattern(self, repository):
        """Test saving a NO_PATTERN attempt."""
        # Create a SignalAttempt with no pattern detected
        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=None,
            filter_results=[],
            final_result="NO_PATTERN",
        )

        await repository.save_attempt(attempt, "BTC/USDT:USDT", "1h")

        # Verify it was saved correctly
        async with repository._db.execute(
            "SELECT * FROM signal_attempts WHERE symbol = ?", ("BTC/USDT:USDT",)
        ) as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 1
            row = dict(rows[0])
            assert row["strategy_name"] == "pinbar"
            assert row["symbol"] == "BTC/USDT:USDT"
            assert row["timeframe"] == "1h"
            assert row["direction"] is None
            assert row["pattern_score"] is None
            assert row["final_result"] == "NO_PATTERN"
            assert row["filter_stage"] is None
            assert row["filter_reason"] is None

    @pytest.mark.asyncio
    async def test_save_attempt_filtered(self, repository):
        """Test saving a FILTERED attempt with filter_stage and filter_reason."""
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.85,
            details={"wick_ratio": 0.7, "body_ratio": 0.2},
        )

        filter_results = [
            ("ema_trend", FilterResult(passed=True, reason="trend_match")),
            ("mtf_validation", FilterResult(passed=False, reason="bearish_trend_blocks_long")),
        ]

        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=pattern,
            filter_results=filter_results,
            final_result="FILTERED",
        )

        await repository.save_attempt(attempt, "ETH/USDT:USDT", "4h")

        # Verify it was saved correctly
        async with repository._db.execute(
            "SELECT * FROM signal_attempts WHERE symbol = ?", ("ETH/USDT:USDT",)
        ) as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 1
            row = dict(rows[0])
            assert row["strategy_name"] == "pinbar"
            assert row["symbol"] == "ETH/USDT:USDT"
            assert row["timeframe"] == "4h"
            assert row["direction"] == "LONG"
            assert row["pattern_score"] == 0.85
            assert row["final_result"] == "FILTERED"
            assert row["filter_stage"] == "mtf_validation"
            assert row["filter_reason"] == "bearish_trend_blocks_long"

    @pytest.mark.asyncio
    async def test_save_attempt_signal_fired(self, repository):
        """Test saving a SIGNAL_FIRED attempt with correct direction and score."""
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.SHORT,
            score=0.92,
            details={"wick_ratio": 0.8, "body_ratio": 0.15},
        )

        filter_results = [
            ("ema_trend", FilterResult(passed=True, reason="trend_match")),
            ("mtf_validation", FilterResult(passed=True, reason="confirmed")),
        ]

        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=pattern,
            filter_results=filter_results,
            final_result="SIGNAL_FIRED",
        )

        await repository.save_attempt(attempt, "SOL/USDT:USDT", "15m")

        # Verify it was saved correctly
        async with repository._db.execute(
            "SELECT * FROM signal_attempts WHERE symbol = ?", ("SOL/USDT:USDT",)
        ) as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 1
            row = dict(rows[0])
            assert row["strategy_name"] == "pinbar"
            assert row["symbol"] == "SOL/USDT:USDT"
            assert row["timeframe"] == "15m"
            assert row["direction"] == "SHORT"
            assert row["pattern_score"] == 0.92
            assert row["final_result"] == "SIGNAL_FIRED"
            assert row["filter_stage"] is None  # No filter failed
            assert row["filter_reason"] is None

    @pytest.mark.asyncio
    async def test_save_attempt_serializes_decimal_diagnostics(self, repository):
        """Signal attempt diagnostics may contain Decimal values from live strategy calculations."""
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=Decimal("0.875"),
            details={
                "wick_ratio": Decimal("0.72"),
                "body_ratio": Decimal("0.18"),
                "entry_price": Decimal("35000.25"),
            },
        )

        filter_results = [
            ("ema_trend", FilterResult(passed=True, reason="trend_match")),
        ]

        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=pattern,
            filter_results=filter_results,
            final_result="SIGNAL_FIRED",
        )

        await repository.save_attempt(attempt, "BTC/USDT:USDT", "15m")

        async with repository._db.execute(
            "SELECT pattern_score, details, trace_tree FROM signal_attempts WHERE symbol = ?",
            ("BTC/USDT:USDT",),
        ) as cursor:
            row = await cursor.fetchone()

        assert row["pattern_score"] == 0.875

        details = json.loads(row["details"])
        assert details["pattern"]["wick_ratio"] == "0.72"
        assert details["pattern"]["entry_price"] == "35000.25"

        trace_tree = json.loads(row["trace_tree"])
        trigger_node = trace_tree["children"][0]
        assert trigger_node["metadata"]["score"] == "0.875"
        assert trigger_node["metadata"]["details"]["body_ratio"] == "0.18"

    @pytest.mark.asyncio
    async def test_diagnostics_summary(self, repository):
        """Test that diagnostics returns correct summary statistics."""
        # Save different types of attempts
        for i in range(10):
            # NO_PATTERN
            attempt_no = SignalAttempt(
                strategy_name="pinbar",
                pattern=None,
                filter_results=[],
                final_result="NO_PATTERN",
            )
            await repository.save_attempt(attempt_no, "BTC/USDT:USDT", "1h")

        for i in range(5):
            # SIGNAL_FIRED
            pattern = PatternResult(
                strategy_name="pinbar",
                direction=Direction.LONG,
                score=0.9,
                details={},
            )
            attempt_fired = SignalAttempt(
                strategy_name="pinbar",
                pattern=pattern,
                filter_results=[("ema_trend", FilterResult(passed=True, reason="ok"))],
                final_result="SIGNAL_FIRED",
            )
            await repository.save_attempt(attempt_fired, "BTC/USDT:USDT", "1h")

        for i in range(3):
            # FILTERED
            pattern = PatternResult(
                strategy_name="pinbar",
                direction=Direction.SHORT,
                score=0.7,
                details={},
            )
            attempt_filtered = SignalAttempt(
                strategy_name="pinbar",
                pattern=pattern,
                filter_results=[("ema_trend", FilterResult(passed=False, reason="no_trend"))],
                final_result="FILTERED",
            )
            await repository.save_attempt(attempt_filtered, "BTC/USDT:USDT", "1h")

        diagnostics = await repository.get_diagnostics(hours=24)

        assert diagnostics["summary"]["total_klines"] == 18
        assert diagnostics["summary"]["no_pattern"] == 10
        assert diagnostics["summary"]["signal_fired"] == 5
        assert diagnostics["summary"]["filtered"] == 3
        assert len(diagnostics["recent_attempts"]) == 18  # Less than 20, so all returned

    @pytest.mark.asyncio
    async def test_diagnostics_filter_breakdown(self, repository):
        """Test that filter_breakdown correctly counts filter rejections."""
        # Save attempts filtered by different stages
        for i in range(3):
            pattern = PatternResult(
                strategy_name="pinbar",
                direction=Direction.LONG,
                score=0.8,
                details={},
            )
            attempt_ema = SignalAttempt(
                strategy_name="pinbar",
                pattern=pattern,
                filter_results=[("ema_trend", FilterResult(passed=False, reason="bearish"))],
                final_result="FILTERED",
            )
            await repository.save_attempt(attempt_ema, "BTC/USDT:USDT", "1h")

        for i in range(2):
            pattern = PatternResult(
                strategy_name="pinbar",
                direction=Direction.LONG,
                score=0.8,
                details={},
            )
            attempt_mtf = SignalAttempt(
                strategy_name="pinbar",
                pattern=pattern,
                filter_results=[
                    ("ema_trend", FilterResult(passed=True, reason="ok")),
                    ("mtf_validation", FilterResult(passed=False, reason="conflict")),
                ],
                final_result="FILTERED",
            )
            await repository.save_attempt(attempt_mtf, "BTC/USDT:USDT", "1h")

        diagnostics = await repository.get_diagnostics(hours=24)

        assert diagnostics["summary"]["filtered"] == 5
        assert diagnostics["summary"]["filter_breakdown"]["ema_trend"] == 3
        assert diagnostics["summary"]["filter_breakdown"]["mtf_validation"] == 2

    @pytest.mark.asyncio
    async def test_diagnostics_symbol_filter(self, repository):
        """Test diagnostics filtering by symbol."""
        # Save attempts for different symbols
        for symbol in ["BTC/USDT:USDT", "ETH/USDT:USDT"]:
            pattern = PatternResult(
                strategy_name="pinbar",
                direction=Direction.LONG,
                score=0.8,
                details={},
            )
            attempt = SignalAttempt(
                strategy_name="pinbar",
                pattern=pattern,
                filter_results=[("ema_trend", FilterResult(passed=True, reason="ok"))],
                final_result="SIGNAL_FIRED",
            )
            await repository.save_attempt(attempt, symbol, "1h")

        # Get diagnostics for BTC only
        btc_diagnostics = await repository.get_diagnostics(symbol="BTC/USDT:USDT", hours=24)
        assert btc_diagnostics["summary"]["total_klines"] == 1
        assert btc_diagnostics["summary"]["signal_fired"] == 1

        # Get diagnostics for all symbols
        all_diagnostics = await repository.get_diagnostics(hours=24)
        assert all_diagnostics["summary"]["total_klines"] == 2

    @pytest.mark.asyncio
    async def test_get_signals_returns_filtered_total(self, repository):
        """Test that get_signals returns filtered total, not overall total."""
        # Save signals for different symbols
        for i in range(5):
            signal_btc = SignalResult(
                symbol="BTC/USDT:USDT",
                timeframe="1h",
                direction=Direction.LONG,
                entry_price=Decimal("35000"),
                suggested_stop_loss=Decimal("34500"),
                suggested_position_size=Decimal("1.5"),
                current_leverage=5,
                tags=[{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Confirmed"}],
                risk_reward_info="Risk 1% = 750 USDT",
            )
            await repository.save_signal(signal_btc)

        for i in range(3):
            signal_eth = SignalResult(
                symbol="ETH/USDT:USDT",
                timeframe="1h",
                direction=Direction.SHORT,
                entry_price=Decimal("2200"),
                suggested_stop_loss=Decimal("2250"),
                suggested_position_size=Decimal("10"),
                current_leverage=3,
                tags=[{"name": "EMA", "value": "Bearish"}, {"name": "MTF", "value": "Confirmed"}],
                risk_reward_info="Risk 1% = 500 USDT",
            )
            await repository.save_signal(signal_eth)

        # Get filtered by BTC
        result_btc = await repository.get_signals(symbol="BTC/USDT:USDT", limit=10)
        assert result_btc["total"] == 5  # Filtered total, not 8
        assert len(result_btc["data"]) == 5

        # Get filtered by ETH
        result_eth = await repository.get_signals(symbol="ETH/USDT:USDT", limit=10)
        assert result_eth["total"] == 3  # Filtered total, not 8
        assert len(result_eth["data"]) == 3

        # Get filtered by direction
        result_long = await repository.get_signals(direction="LONG", limit=10)
        assert result_long["total"] == 5  # Only LONG signals
        assert len(result_long["data"]) == 5


class TestPerformanceTracking:
    """Test SignalRepository performance tracking operations."""

    @pytest.mark.asyncio
    async def test_get_pending_signals_returns_only_pending(self, repository):
        """Test that get_pending_signals returns only PENDING signals."""
        # Insert signals with different statuses manually
        await repository._db.execute(
            """
            INSERT INTO signals (created_at, symbol, timeframe, direction, entry_price, stop_loss, position_size, leverage, tags_json, risk_info, status, take_profit_1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-01T00:00:00Z", "BTC/USDT:USDT", "1h", "LONG", "40000", "39000", "1.0", "5", "[]", "Risk 1%", "PENDING", "42000")
        )
        await repository._db.execute(
            """
            INSERT INTO signals (created_at, symbol, timeframe, direction, entry_price, stop_loss, position_size, leverage, tags_json, risk_info, status, take_profit_1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-01T00:00:00Z", "BTC/USDT:USDT", "1h", "SHORT", "40000", "41000", "1.0", "5", "[]", "Risk 1%", "WON", "38000")
        )
        await repository._db.execute(
            """
            INSERT INTO signals (created_at, symbol, timeframe, direction, entry_price, stop_loss, position_size, leverage, tags_json, risk_info, status, take_profit_1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-01T00:00:00Z", "BTC/USDT:USDT", "1h", "LONG", "40000", "39000", "1.0", "5", "[]", "Risk 1%", "LOST", "42000")
        )
        await repository._db.commit()

        pending = await repository.get_pending_signals("BTC/USDT:USDT")

        assert len(pending) == 1
        assert pending[0]["direction"] == "LONG"
        assert pending[0]["entry_price"] == Decimal("40000")
        assert pending[0]["stop_loss"] == Decimal("39000")
        assert pending[0]["take_profit_1"] == Decimal("42000")

    @pytest.mark.asyncio
    async def test_get_pending_signals_empty(self, repository):
        """Test get_pending_signals when no pending signals."""
        pending = await repository.get_pending_signals("NONEXISTENT/USDT:USDT")
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_get_pending_signals_no_take_profit(self, repository):
        """Test get_pending_signals handles NULL take_profit_1."""
        # Insert signal without take_profit
        await repository._db.execute(
            """
            INSERT INTO signals (created_at, symbol, timeframe, direction, entry_price, stop_loss, position_size, leverage, tags_json, risk_info, status, take_profit_1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-01T00:00:00Z", "BTC/USDT:USDT", "1h", "LONG", "40000", "39000", "1.0", "5", "[]", "Risk 1%", "PENDING", None)
        )
        await repository._db.commit()

        pending = await repository.get_pending_signals("BTC/USDT:USDT")

        assert len(pending) == 1
        assert pending[0]["take_profit_1"] is None

    @pytest.mark.asyncio
    async def test_update_signal_status_won(self, repository):
        """Test updating signal status to WON."""
        # Insert a pending signal
        await repository._db.execute(
            """
            INSERT INTO signals (created_at, symbol, timeframe, direction, entry_price, stop_loss, position_size, leverage, tags_json, risk_info, status, take_profit_1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-01T00:00:00Z", "BTC/USDT:USDT", "1h", "LONG", "40000", "39000", "1.0", "5", "[]", "Risk 1%", "PENDING", "42000")
        )
        await repository._db.commit()

        # Update to WON
        pnl_ratio = Decimal("2.0")
        await repository.update_signal_status(1, "WON", pnl_ratio)

        # Verify update
        async with repository._db.execute("SELECT status, pnl_ratio, closed_at FROM signals WHERE id = 1") as cursor:
            row = await cursor.fetchone()
            assert row["status"] == "WON"
            assert row["pnl_ratio"] == "2.0"
            assert row["closed_at"] is not None

    @pytest.mark.asyncio
    async def test_update_signal_status_lost(self, repository):
        """Test updating signal status to LOST."""
        # Insert a pending signal
        await repository._db.execute(
            """
            INSERT INTO signals (created_at, symbol, timeframe, direction, entry_price, stop_loss, position_size, leverage, tags_json, risk_info, status, take_profit_1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-01T00:00:00Z", "BTC/USDT:USDT", "1h", "SHORT", "40000", "41000", "1.0", "5", "[]", "Risk 1%", "PENDING", "38000")
        )
        await repository._db.commit()

        # Update to LOST
        await repository.update_signal_status(1, "LOST", Decimal("-1.0"))

        # Verify update
        async with repository._db.execute("SELECT status, pnl_ratio FROM signals WHERE id = 1") as cursor:
            row = await cursor.fetchone()
            assert row["status"] == "LOST"
            assert row["pnl_ratio"] == "-1.0"

    @pytest.mark.asyncio
    async def test_update_signal_status_none_pnl(self, repository):
        """Test updating signal status with None pnl_ratio."""
        # Insert a pending signal
        await repository._db.execute(
            """
            INSERT INTO signals (created_at, symbol, timeframe, direction, entry_price, stop_loss, position_size, leverage, tags_json, risk_info, status, take_profit_1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-01T00:00:00Z", "BTC/USDT:USDT", "1h", "LONG", "40000", "39000", "1.0", "5", "[]", "Risk 1%", "PENDING", "42000")
        )
        await repository._db.commit()

        # Update with None pnl_ratio
        await repository.update_signal_status(1, "WON", None)

        # Verify pnl_ratio is NULL
        async with repository._db.execute("SELECT status, pnl_ratio FROM signals WHERE id = 1") as cursor:
            row = await cursor.fetchone()
            assert row["status"] == "WON"
            assert row["pnl_ratio"] is None

    @pytest.mark.asyncio
    async def test_stats_includes_won_lost_counts(self, repository):
        """Test that get_stats includes won_count and lost_count."""
        # Insert signals with different statuses
        await repository._db.execute(
            """
            INSERT INTO signals (created_at, symbol, timeframe, direction, entry_price, stop_loss, position_size, leverage, tags_json, risk_info, status, take_profit_1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-01T00:00:00Z", "BTC/USDT:USDT", "1h", "LONG", "40000", "39000", "1.0", "5", "[]", "Risk 1%", "WON", "42000")
        )
        await repository._db.execute(
            """
            INSERT INTO signals (created_at, symbol, timeframe, direction, entry_price, stop_loss, position_size, leverage, tags_json, risk_info, status, take_profit_1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-01T00:00:00Z", "BTC/USDT:USDT", "1h", "LONG", "40000", "39000", "1.0", "5", "[]", "Risk 1%", "WON", "42000")
        )
        await repository._db.execute(
            """
            INSERT INTO signals (created_at, symbol, timeframe, direction, entry_price, stop_loss, position_size, leverage, tags_json, risk_info, status, take_profit_1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-01T00:00:00Z", "BTC/USDT:USDT", "1h", "SHORT", "40000", "41000", "1.0", "5", "[]", "Risk 1%", "LOST", "38000")
        )
        await repository._db.execute(
            """
            INSERT INTO signals (created_at, symbol, timeframe, direction, entry_price, stop_loss, position_size, leverage, tags_json, risk_info, status, take_profit_1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-01T00:00:00Z", "BTC/USDT:USDT", "1h", "LONG", "40000", "39000", "1.0", "5", "[]", "Risk 1%", "PENDING", "42000")
        )
        await repository._db.commit()

        stats = await repository.get_stats()

        assert stats["won_count"] == 2
        assert stats["lost_count"] == 1
        assert stats["win_rate"] == 2 / 3  # 2 won out of 3 closed


class TestEvaluationSummaryAndTraceTree:
    """Test evaluation_summary and trace_tree generation."""

    @pytest.mark.asyncio
    async def test_save_attempt_generates_evaluation_summary(self, repository):
        """Test that save_attempt generates evaluation_summary field."""
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.85,
            details={"wick_ratio": 0.7, "body_ratio": 0.2},
        )

        filter_results = [
            ("ema_trend", FilterResult(passed=True, reason="trend_match")),
            ("mtf_validation", FilterResult(passed=True, reason="confirmed")),
        ]

        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=pattern,
            filter_results=filter_results,
            final_result="SIGNAL_FIRED",
        )

        await repository.save_attempt(attempt, "BTC/USDT:USDT", "1h")

        # Verify evaluation_summary is saved
        async with repository._db.execute(
            "SELECT evaluation_summary FROM signal_attempts WHERE symbol = ?", ("BTC/USDT:USDT",)
        ) as cursor:
            row = await cursor.fetchone()
            summary = row["evaluation_summary"]
            assert summary is not None
            assert "信号评估报告" in summary
            assert "币种：BTC/USDT:USDT" in summary
            assert "周期：1h" in summary
            assert "策略：pinbar" in summary
            assert "【评估结果】" in summary
            assert "信号触发" in summary
            assert "【形态检测】" in summary
            assert "【过滤器结果】" in summary
            assert "【最终结果】" in summary

    @pytest.mark.asyncio
    async def test_save_attempt_generates_trace_tree(self, repository):
        """Test that save_attempt generates trace_tree field."""
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.92,
            details={"wick_ratio": 0.8, "body_ratio": 0.15},
        )

        filter_results = [
            ("ema_trend", FilterResult(passed=True, reason="trend_match")),
            ("mtf_validation", FilterResult(passed=True, reason="confirmed")),
        ]

        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=pattern,
            filter_results=filter_results,
            final_result="SIGNAL_FIRED",
        )

        await repository.save_attempt(attempt, "ETH/USDT:USDT", "4h")

        # Verify trace_tree is saved
        async with repository._db.execute(
            "SELECT trace_tree FROM signal_attempts WHERE symbol = ?", ("ETH/USDT:USDT",)
        ) as cursor:
            row = await cursor.fetchone()
            trace_tree_json = row["trace_tree"]
            assert trace_tree_json is not None

            import json
            trace_tree = json.loads(trace_tree_json)

            # Verify root node structure
            assert "node_id" in trace_tree
            assert "node_type" in trace_tree
            assert trace_tree["node_type"] == "and_gate"
            assert "passed" in trace_tree
            assert trace_tree["passed"] is True  # SIGNAL_FIRED
            assert "reason" in trace_tree
            assert "metadata" in trace_tree
            assert "children" in trace_tree

            # Verify children nodes
            assert len(trace_tree["children"]) >= 2  # At least trigger + filters

            # First child should be trigger
            trigger_node = trace_tree["children"][0]
            assert trigger_node["node_type"] == "trigger"
            assert trigger_node["passed"] is True
            assert trigger_node["metadata"]["trigger_type"] == "pinbar"
            assert trigger_node["metadata"]["score"] == 0.92

            # Remaining children should be filters
            filter_nodes = trace_tree["children"][1:]
            assert len(filter_nodes) == 2
            assert filter_nodes[0]["node_type"] == "filter"
            assert filter_nodes[0]["passed"] is True
            assert filter_nodes[0]["metadata"]["filter_name"] == "ema_trend"

    @pytest.mark.asyncio
    async def test_save_attempt_no_pattern_generates_correct_summary(self, repository):
        """Test evaluation_summary for NO_PATTERN attempt."""
        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=None,
            filter_results=[],
            final_result="NO_PATTERN",
        )

        await repository.save_attempt(attempt, "SOL/USDT:USDT", "15m")

        # Verify evaluation_summary
        async with repository._db.execute(
            "SELECT evaluation_summary FROM signal_attempts WHERE symbol = ?", ("SOL/USDT:USDT",)
        ) as cursor:
            row = await cursor.fetchone()
            summary = row["evaluation_summary"]
            assert summary is not None
            assert "未检测到有效形态" in summary

        # Verify trace_tree
        async with repository._db.execute(
            "SELECT trace_tree FROM signal_attempts WHERE symbol = ?", ("SOL/USDT:USDT",)
        ) as cursor:
            row = await cursor.fetchone()
            trace_tree_json = row["trace_tree"]
            import json
            trace_tree = json.loads(trace_tree_json)

            # Root should not pass
            assert trace_tree["passed"] is False

            # Trigger node should not pass
            trigger_node = trace_tree["children"][0]
            assert trigger_node["node_type"] == "trigger"
            assert trigger_node["passed"] is False
            assert trigger_node["reason"] == "no_pattern_detected"

    @pytest.mark.asyncio
    async def test_save_attempt_filtered_generates_correct_summary(self, repository):
        """Test evaluation_summary for FILTERED attempt."""
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.SHORT,
            score=0.75,
            details={"wick_ratio": 0.65, "body_ratio": 0.25},
        )

        filter_results = [
            ("ema_trend", FilterResult(passed=True, reason="trend_match")),
            ("mtf_validation", FilterResult(passed=False, reason="bearish_trend_blocks_short")),
        ]

        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=pattern,
            filter_results=filter_results,
            final_result="FILTERED",
        )

        await repository.save_attempt(attempt, "BNB/USDT:USDT", "1h")

        # Verify evaluation_summary mentions the failed filter
        async with repository._db.execute(
            "SELECT evaluation_summary FROM signal_attempts WHERE symbol = ?", ("BNB/USDT:USDT",)
        ) as cursor:
            row = await cursor.fetchone()
            summary = row["evaluation_summary"]
            assert summary is not None
            assert "被过滤器" in summary
            assert "mtf_validation" in summary

        # Verify trace_tree
        async with repository._db.execute(
            "SELECT trace_tree FROM signal_attempts WHERE symbol = ?", ("BNB/USDT:USDT",)
        ) as cursor:
            row = await cursor.fetchone()
            trace_tree_json = row["trace_tree"]
            import json
            trace_tree = json.loads(trace_tree_json)

            # Root should not pass
            assert trace_tree["passed"] is False

            # Find the failed filter node
            filter_nodes = [n for n in trace_tree["children"] if n["node_type"] == "filter"]
            mtf_node = next(n for n in filter_nodes if n["metadata"]["filter_name"] == "mtf_validation")
            assert mtf_node["passed"] is False
            assert mtf_node["reason"] == "bearish_trend_blocks_short"
