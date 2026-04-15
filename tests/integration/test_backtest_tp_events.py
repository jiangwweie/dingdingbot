"""
Integration tests for TP close events in backtest flow (Task 1.4).

Tests cover:
- IT-1: Full backtest multi-TP partial close (TP1+TP2+TP3)
- IT-2: close_events persisted to database
- IT-3: SL priority over TP in matching
- IT-4: close_events count matches executed TP/SL orders
"""
import pytest
import tempfile
import asyncio
from decimal import Decimal
from pathlib import Path

from src.domain.matching_engine import MockMatchingEngine
from src.domain.models import (
    KlineData,
    Order,
    Position,
    Account,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
    PositionCloseEvent,
    PMSBacktestReport,
)
from src.infrastructure.backtest_repository import BacktestReportRepository


# ============================================================
# Helper Functions
# ============================================================

def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "1h",
    timestamp: int = 1700000000000,
    open: Decimal = Decimal("50000"),
    high: Decimal = Decimal("51000"),
    low: Decimal = Decimal("49000"),
    close: Decimal = Decimal("50500"),
    volume: Decimal = Decimal("1000"),
) -> KlineData:
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        is_closed=True,
    )


# ============================================================
# IT-1: Full backtest multi-TP partial close
# ============================================================

class TestMultiTPIntegration:
    """IT-1: Multi-TP partial close integration with backtest flow."""

    def test_backtest_multi_tp_partial_close(self):
        """
        IT-1: 完整回测流程 TP1+TP2+TP3 分批止盈

        Simulates a backtest where a position is opened and then
        partially closed at three TP levels (50%, 30%, 20%).

        Verifies:
        - All three TP levels execute
        - close_qty proportions are correct (5:3:2)
        - Sum of close_qty equals initial position qty
        - All close_events have correct event_type
        """
        engine = MockMatchingEngine(
            slippage_rate=Decimal("0.001"),
            fee_rate=Decimal("0.0004"),
            tp_slippage_rate=Decimal("0.0005"),
        )

        signal_id = "sig_multi_tp"
        initial_qty = Decimal("0.1")
        position = Position(
            id=f"pos_{signal_id}",
            signal_id=signal_id,
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("50000"),
            current_qty=initial_qty,
            watermark_price=Decimal("50000"),
        )
        account = Account(account_id="test", total_balance=Decimal("10000"), frozen_margin=Decimal("0"))
        positions_map = {signal_id: position}

        # Create TP chain
        tp1 = Order(
            id="tp1", signal_id=signal_id, symbol="BTC/USDT:USDT",
            direction=Direction.LONG, order_type=OrderType.LIMIT, order_role=OrderRole.TP1,
            price=Decimal("52000"), requested_qty=Decimal("0.05"),
            status=OrderStatus.OPEN, created_at=1700000000000, updated_at=1700000000000,
        )
        tp2 = Order(
            id="tp2", signal_id=signal_id, symbol="BTC/USDT:USDT",
            direction=Direction.LONG, order_type=OrderType.LIMIT, order_role=OrderRole.TP2,
            price=Decimal("54000"), requested_qty=Decimal("0.03"),
            status=OrderStatus.OPEN, created_at=1700000000000, updated_at=1700000000000,
        )
        tp3 = Order(
            id="tp3", signal_id=signal_id, symbol="BTC/USDT:USDT",
            direction=Direction.LONG, order_type=OrderType.LIMIT, order_role=OrderRole.TP3,
            price=Decimal("56000"), requested_qty=Decimal("0.02"),
            status=OrderStatus.OPEN, created_at=1700000000000, updated_at=1700000000000,
        )

        all_close_events = []

        # Kline 1: Only TP1 triggers (high=53000 >= TP1=52000, but < TP2=54000)
        kline1 = create_kline(timestamp=1700000000000, high=Decimal("53000"), low=Decimal("49000"))
        exec1 = engine.match_orders_for_kline(kline1, [tp1, tp2, tp3], positions_map, account)

        # Collect close events (simulating backtester.py logic)
        for order in exec1:
            if order.order_role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5, OrderRole.SL] and order.actual_filled and order.actual_filled > 0:
                all_close_events.append(PositionCloseEvent(
                    position_id=position.id,
                    order_id=order.id,
                    event_type=order.order_role.value,
                    event_category="exit",
                    close_price=order.average_exec_price,
                    close_qty=order.actual_filled,
                    close_pnl=order.close_pnl,
                    close_fee=order.close_fee,
                    close_time=kline1.timestamp,
                    exit_reason=order.order_role.value,
                ))

        assert len(all_close_events) == 1
        assert all_close_events[0].event_type == "TP1"
        assert all_close_events[0].close_qty == Decimal("0.05")

        # Kline 2: TP2 and TP3 both trigger (high=57000)
        kline2 = create_kline(timestamp=1700003600000, high=Decimal("57000"), low=Decimal("49000"))
        exec2 = engine.match_orders_for_kline(kline2, [tp2, tp3], positions_map, account)

        for order in exec2:
            if order.order_role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5, OrderRole.SL] and order.actual_filled and order.actual_filled > 0:
                all_close_events.append(PositionCloseEvent(
                    position_id=position.id,
                    order_id=order.id,
                    event_type=order.order_role.value,
                    event_category="exit",
                    close_price=order.average_exec_price,
                    close_qty=order.actual_filled,
                    close_pnl=order.close_pnl,
                    close_fee=order.close_fee,
                    close_time=kline2.timestamp,
                    exit_reason=order.order_role.value,
                ))

        # Verify: 3 close events total
        assert len(all_close_events) == 3
        event_types = [e.event_type for e in all_close_events]
        assert "TP1" in event_types
        assert "TP2" in event_types
        assert "TP3" in event_types

        # Verify close_qty sum = initial qty
        total_close_qty = sum(e.close_qty for e in all_close_events)
        assert total_close_qty == initial_qty

        # Verify position closed
        assert position.is_closed == True
        assert position.current_qty == Decimal("0")

        # Verify invariant: sum(close_pnl) == realized_pnl
        total_close_pnl = sum(e.close_pnl for e in all_close_events)
        assert total_close_pnl == position.realized_pnl


# ============================================================
# IT-2: close_events persisted to database
# ============================================================

@pytest.mark.asyncio
class TestCloseEventsPersistence:
    """IT-2: close_events persistence to SQLite database."""

    @pytest.fixture(autouse=True)
    async def setup_repo(self):
        """Create temporary database for each test."""
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            self.db_path = str(Path(tmpdir) / "test_close_events.db")
            self.repo = BacktestReportRepository(db_path=self.db_path)
            await self.repo.initialize()
            yield
            await self.repo.close()
            # Cleanup handled by TemporaryDirectory

    async def test_close_events_persisted_to_db(self):
        """
        IT-2: close_events 持久化到数据库

        Steps:
        1. Create a PMSBacktestReport with close_events
        2. Save via repository
        3. Retrieve via get_report
        4. Verify close_events match
        """
        close_events = [
            PositionCloseEvent(
                position_id="pos_001",
                order_id="tp1_001",
                event_type="TP1",
                event_category="exit",
                close_price=Decimal("52000"),
                close_qty=Decimal("0.05"),
                close_pnl=Decimal("100"),
                close_fee=Decimal("1.04"),
                close_time=1700000000000,
                exit_reason="TP1",
            ),
            PositionCloseEvent(
                position_id="pos_001",
                order_id="tp2_001",
                event_type="TP2",
                event_category="exit",
                close_price=Decimal("54000"),
                close_qty=Decimal("0.03"),
                close_pnl=Decimal("120"),
                close_fee=Decimal("0.648"),
                close_time=1700003600000,
                exit_reason="TP2",
            ),
        ]

        report = PMSBacktestReport(
            strategy_id="pinbar_v1",
            strategy_name="Pinbar",
            backtest_start=1700000000000,
            backtest_end=1700010000000,
            initial_balance=Decimal("10000"),
            final_balance=Decimal("10220"),
            total_return=Decimal("0.022"),
            total_trades=1,
            winning_trades=1,
            losing_trades=0,
            win_rate=Decimal("100"),
            total_pnl=Decimal("220"),
            total_fees_paid=Decimal("1.688"),
            total_slippage_cost=Decimal("0.5"),
            max_drawdown=Decimal("0.5"),
            close_events=close_events,
        )

        strategy_snapshot = '{"triggers": [{"type": "pinbar"}], "filters": []}'
        symbol = "BTC/USDT:USDT"
        timeframe = "1h"

        # Save report
        await self.repo.save_report(report, strategy_snapshot, symbol, timeframe)

        # Verify close_events table has entries
        cursor = await self.repo._db.execute(
            "SELECT COUNT(*) as cnt FROM position_close_events"
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 2, "position_close_events table should have 2 rows"

        # Retrieve report
        cursor = await self.repo._db.execute(
            "SELECT id FROM backtest_reports WHERE strategy_id = ?",
            (report.strategy_id,)
        )
        report_row = await cursor.fetchone()
        assert report_row is not None
        report_id = report_row["id"]

        retrieved = await self.repo.get_report(report_id)

        # Verify close_events
        assert len(retrieved.close_events) == 2
        assert retrieved.close_events[0].event_type == "TP1"
        assert retrieved.close_events[0].close_qty == Decimal("0.05")
        assert retrieved.close_events[0].close_pnl == Decimal("100")
        assert retrieved.close_events[1].event_type == "TP2"
        assert retrieved.close_events[1].close_qty == Decimal("0.03")
        assert retrieved.close_events[1].close_pnl == Decimal("120")

        # Verify Decimal precision preserved
        for event in retrieved.close_events:
            assert isinstance(event.close_price, Decimal)
            assert isinstance(event.close_qty, Decimal)
            assert isinstance(event.close_pnl, Decimal)
            assert isinstance(event.close_fee, Decimal)

    async def test_close_events_empty_default(self):
        """
        Backward compatibility: report without close_events should work.

        Verifies: close_events defaults to empty list when not provided.
        """
        report = PMSBacktestReport(
            strategy_id="legacy_v1",
            strategy_name="Legacy",
            backtest_start=1700000000000,
            backtest_end=1700010000000,
            initial_balance=Decimal("10000"),
            final_balance=Decimal("10000"),
            total_return=Decimal("0"),
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=Decimal("0"),
            total_pnl=Decimal("0"),
            total_fees_paid=Decimal("0"),
            total_slippage_cost=Decimal("0"),
            max_drawdown=Decimal("0"),
            # close_events not provided, should default to []
        )

        strategy_snapshot = '{"triggers": [], "filters": []}'
        symbol = "ETH/USDT:USDT"
        timeframe = "1h"

        await self.repo.save_report(report, strategy_snapshot, symbol, timeframe)

        cursor = await self.repo._db.execute(
            "SELECT id FROM backtest_reports WHERE strategy_id = ?",
            (report.strategy_id,)
        )
        row = await cursor.fetchone()
        assert row is not None

        retrieved = await self.repo.get_report(row["id"])
        assert retrieved.close_events == []


# ============================================================
# IT-3: SL priority over TP
# ============================================================

class TestSLPriority:
    """IT-3: SL priority over TP in matching."""

    def test_sl_priority_over_tp(self):
        """
        IT-3: SL 优先于 TP 撮合

        When both SL and TP conditions are met on the same kline,
        SL should execute first and TP should be canceled.
        """
        engine = MockMatchingEngine(
            slippage_rate=Decimal("0.001"),
            fee_rate=Decimal("0.0004"),
            tp_slippage_rate=Decimal("0.0005"),
        )

        signal_id = "sl_priority"
        position = Position(
            id=f"pos_{signal_id}",
            signal_id=signal_id,
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("50000"),
            current_qty=Decimal("0.1"),
            watermark_price=Decimal("50000"),
        )
        account = Account(account_id="test", total_balance=Decimal("10000"), frozen_margin=Decimal("0"))
        positions_map = {signal_id: position}

        tp1 = Order(
            id="tp1", signal_id=signal_id, symbol="BTC/USDT:USDT",
            direction=Direction.LONG, order_type=OrderType.LIMIT, order_role=OrderRole.TP1,
            price=Decimal("52000"), requested_qty=Decimal("0.1"),
            status=OrderStatus.OPEN, created_at=1700000000000, updated_at=1700000000000,
        )
        sl = Order(
            id="sl", signal_id=signal_id, symbol="BTC/USDT:USDT",
            direction=Direction.LONG, order_type=OrderType.STOP_MARKET, order_role=OrderRole.SL,
            trigger_price=Decimal("49000"), requested_qty=Decimal("0.1"),
            status=OrderStatus.OPEN, created_at=1700000000000, updated_at=1700000000000,
        )

        # Kline with high >= TP1.price AND low <= SL.trigger_price
        kline = create_kline(high=Decimal("53000"), low=Decimal("48000"))

        all_orders = [tp1, sl]
        executed = engine.match_orders_for_kline(kline, all_orders, positions_map, account)

        # SL should execute
        assert sl.status == OrderStatus.FILLED
        # TP should be canceled
        assert tp1.status == OrderStatus.CANCELED
        # Only SL in executed list
        assert len(executed) == 1
        assert executed[0].order_role == OrderRole.SL
        # Position closed
        assert position.is_closed == True


# ============================================================
# IT-4: close_events count matches executed orders
# ============================================================

class TestCloseEventCountConsistency:
    """IT-4: close_events count matches executed TP/SL orders."""

    def test_close_events_count_matches_executed(self):
        """
        IT-4: 回测报告中 close_events 数量与成交订单一致

        Simulates multiple signals being processed, each generating
        TP/SL orders. Verifies that the count of close_events
        matches the count of FILLED TP/SL orders.
        """
        engine = MockMatchingEngine(
            slippage_rate=Decimal("0.001"),
            fee_rate=Decimal("0.0004"),
            tp_slippage_rate=Decimal("0.0005"),
        )

        all_close_events = []
        all_executed_tp_sl = []

        # Signal 1: LONG position, TP1 triggers
        sig1 = "sig_1"
        pos1 = Position(
            id=f"pos_{sig1}", signal_id=sig1, symbol="BTC/USDT:USDT",
            direction=Direction.LONG, entry_price=Decimal("50000"),
            current_qty=Decimal("0.1"), watermark_price=Decimal("50000"),
        )
        account1 = Account(account_id="test1", total_balance=Decimal("10000"), frozen_margin=Decimal("0"))
        positions_map1 = {sig1: pos1}

        tp1_1 = Order(
            id="tp1_1", signal_id=sig1, symbol="BTC/USDT:USDT",
            direction=Direction.LONG, order_type=OrderType.LIMIT, order_role=OrderRole.TP1,
            price=Decimal("52000"), requested_qty=Decimal("0.1"),
            status=OrderStatus.OPEN, created_at=1700000000000, updated_at=1700000000000,
        )
        sl1 = Order(
            id="sl1", signal_id=sig1, symbol="BTC/USDT:USDT",
            direction=Direction.LONG, order_type=OrderType.STOP_MARKET, order_role=OrderRole.SL,
            trigger_price=Decimal("48000"), requested_qty=Decimal("0.1"),
            status=OrderStatus.OPEN, created_at=1700000000000, updated_at=1700000000000,
        )

        kline1 = create_kline(timestamp=1700000000000, high=Decimal("53000"), low=Decimal("49000"))
        exec1 = engine.match_orders_for_kline(kline1, [tp1_1, sl1], positions_map1, account1)

        for order in exec1:
            if order.order_role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5, OrderRole.SL] and order.actual_filled and order.actual_filled > 0:
                all_close_events.append(PositionCloseEvent(
                    position_id=pos1.id, order_id=order.id, event_type=order.order_role.value,
                    event_category="exit", close_price=order.average_exec_price,
                    close_qty=order.actual_filled, close_pnl=order.close_pnl,
                    close_fee=order.close_fee, close_time=kline1.timestamp,
                    exit_reason=order.order_role.value,
                ))
                all_executed_tp_sl.append(order)

        # Signal 2: SHORT position, SL triggers
        sig2 = "sig_2"
        pos2 = Position(
            id=f"pos_{sig2}", signal_id=sig2, symbol="BTC/USDT:USDT",
            direction=Direction.SHORT, entry_price=Decimal("50000"),
            current_qty=Decimal("0.05"), watermark_price=Decimal("50000"),
        )
        account2 = Account(account_id="test2", total_balance=Decimal("5000"), frozen_margin=Decimal("0"))
        positions_map2 = {sig2: pos2}

        tp2_2 = Order(
            id="tp2_2", signal_id=sig2, symbol="BTC/USDT:USDT",
            direction=Direction.SHORT, order_type=OrderType.LIMIT, order_role=OrderRole.TP2,
            price=Decimal("48000"), requested_qty=Decimal("0.05"),
            status=OrderStatus.OPEN, created_at=1700003600000, updated_at=1700003600000,
        )
        sl2 = Order(
            id="sl2", signal_id=sig2, symbol="BTC/USDT:USDT",
            direction=Direction.SHORT, order_type=OrderType.STOP_MARKET, order_role=OrderRole.SL,
            trigger_price=Decimal("51000"), requested_qty=Decimal("0.05"),
            status=OrderStatus.OPEN, created_at=1700003600000, updated_at=1700003600000,
        )

        kline2 = create_kline(timestamp=1700003600000, high=Decimal("52000"), low=Decimal("47000"))
        exec2 = engine.match_orders_for_kline(kline2, [tp2_2, sl2], positions_map2, account2)

        for order in exec2:
            if order.order_role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5, OrderRole.SL] and order.actual_filled and order.actual_filled > 0:
                all_close_events.append(PositionCloseEvent(
                    position_id=pos2.id, order_id=order.id, event_type=order.order_role.value,
                    event_category="exit", close_price=order.average_exec_price,
                    close_qty=order.actual_filled, close_pnl=order.close_pnl,
                    close_fee=order.close_fee, close_time=kline2.timestamp,
                    exit_reason=order.order_role.value,
                ))
                all_executed_tp_sl.append(order)

        # Verify count matches
        assert len(all_close_events) == len(all_executed_tp_sl)

        # Verify each close_event has a matching order_id
        event_order_ids = {e.order_id for e in all_close_events}
        executed_order_ids = {o.id for o in all_executed_tp_sl}
        assert event_order_ids == executed_order_ids

        # Verify event types match
        for event in all_close_events:
            matching_order = next(o for o in all_executed_tp_sl if o.id == event.order_id)
            assert event.event_type == matching_order.order_role.value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
