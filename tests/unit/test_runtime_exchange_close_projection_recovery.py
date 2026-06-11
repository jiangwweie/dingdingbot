from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.order_lifecycle_service import OrderLifecycleService
from src.application.position_projection_service import PositionProjectionService
from src.application.runtime_exchange_close_projection_recovery_service import (
    RuntimeExchangeCloseProjectionRecoveryService,
)
from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType, Position
from src.domain.runtime_exchange_close_projection_recovery import (
    RuntimeExchangeCloseProjectionRecoveryRequest,
    RuntimeExchangeCloseProjectionRecoveryStatus,
)


SYMBOL = "AVAX/USDT:USDT"


class _OrderRepo:
    def __init__(self, orders: list[Order]) -> None:
        self.orders = {order.id: order for order in orders}

    async def get_order(self, order_id: str):
        return self.orders.get(order_id)

    async def save(self, order: Order) -> None:
        self.orders[order.id] = order


class _PositionRepo:
    def __init__(self, positions: list[Position]) -> None:
        self.positions = {position.id: position for position in positions}

    async def get(self, position_id: str):
        return self.positions.get(position_id)

    async def save(self, position: Position) -> None:
        self.positions[position.id] = position

    async def list_active(self, *, symbol: str | None = None, limit: int = 100):
        return [
            position
            for position in self.positions.values()
            if not position.is_closed and (symbol is None or position.symbol == symbol)
        ][:limit]


class _TradeSource:
    def __init__(self, trades: list[dict]) -> None:
        self.trades = trades
        self.calls: list[tuple[str, int]] = []

    async def fetch_my_trades(self, symbol: str, limit: int = 50):
        self.calls.append((symbol, limit))
        return self.trades


def _sl_order() -> Order:
    return Order(
        id="rtod-a194d1ef363c12c3df-sl",
        signal_id="signal-evaluation-adabffa08945",
        exchange_order_id="4000001547813056",
        symbol=SYMBOL,
        direction=Direction.SHORT,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("1"),
        filled_qty=Decimal("0"),
        status=OrderStatus.OPEN,
        trigger_price=Decimal("6.635"),
        reduce_only=True,
        runtime_instance_id="strategy-runtime-95655873b76c",
        created_at=1781163965522,
        updated_at=1781166036946,
    )


def _position() -> Position:
    return Position(
        id="pos_signal-evaluation-adabffa08945",
        signal_id="signal-evaluation-adabffa08945",
        symbol=SYMBOL,
        direction=Direction.SHORT,
        entry_price=Decimal("6.595"),
        current_qty=Decimal("1"),
        watermark_price=Decimal("6.595"),
        realized_pnl=Decimal("0"),
        total_fees_paid=Decimal("0"),
        opened_at=1781166036000,
        is_closed=False,
        runtime_instance_id="strategy-runtime-95655873b76c",
    )


def _closing_trade(*, side: str = "buy") -> dict:
    return {
        "id": "1386754188",
        "timestamp": 1781166956564,
        "symbol": SYMBOL,
        "side": side,
        "price": Decimal("6.635"),
        "amount": Decimal("1"),
        "info": {"id": 1386754188, "side": side.upper(), "price": "6.6350"},
    }


def _service(order_repo: _OrderRepo, position_repo: _PositionRepo, trade_source: _TradeSource):
    return RuntimeExchangeCloseProjectionRecoveryService(
        exchange_trade_source=trade_source,
        order_repository=order_repo,
        position_repository=position_repo,
        order_lifecycle=OrderLifecycleService(order_repo),
        position_projection_service=PositionProjectionService(position_repo),
    )


def _request(*, apply: bool = False) -> RuntimeExchangeCloseProjectionRecoveryRequest:
    return RuntimeExchangeCloseProjectionRecoveryRequest(
        symbol=SYMBOL,
        exit_local_order_id="rtod-a194d1ef363c12c3df-sl",
        exit_exchange_order_id="4000001547813056",
        exit_trade_id="1386754188",
        apply=apply,
    )


@pytest.mark.asyncio
async def test_runtime_exchange_close_projection_recovery_dry_run_is_read_only():
    order = _sl_order()
    position = _position()
    order_repo = _OrderRepo([order])
    position_repo = _PositionRepo([position])
    trade_source = _TradeSource([_closing_trade()])

    result = await _service(order_repo, position_repo, trade_source).recover(
        _request(apply=False),
        now_ms=1781167000000,
    )

    assert result.status == RuntimeExchangeCloseProjectionRecoveryStatus.READY_TO_APPLY
    assert result.local_state_mutated is False
    assert result.order_status_changed is False
    assert result.position_projection_changed is False
    assert result.observed_trade_side == "buy"
    assert result.expected_close_side == "buy"
    assert result.local_position_qty_before == Decimal("1")
    assert order.status == OrderStatus.OPEN
    assert position.is_closed is False
    assert trade_source.calls == [(SYMBOL, 50)]


@pytest.mark.asyncio
async def test_runtime_exchange_close_projection_recovery_apply_marks_sl_and_position_closed():
    order = _sl_order()
    position = _position()
    order_repo = _OrderRepo([order])
    position_repo = _PositionRepo([position])
    trade_source = _TradeSource([_closing_trade()])

    result = await _service(order_repo, position_repo, trade_source).recover(
        _request(apply=True),
        now_ms=1781167000000,
    )

    updated_order = await order_repo.get_order(order.id)
    updated_position = await position_repo.get(position.id)
    assert result.status == RuntimeExchangeCloseProjectionRecoveryStatus.APPLIED
    assert result.local_state_mutated is True
    assert result.order_status_changed is True
    assert result.position_projection_changed is True
    assert result.exchange_write_called is False
    assert result.exchange_order_submitted is False
    assert result.exchange_order_cancelled is False
    assert result.withdrawal_instruction_created is False
    assert result.transfer_instruction_created is False
    assert result.local_position_qty_before == Decimal("1")
    assert result.local_position_qty_after == Decimal("0")
    assert result.realized_pnl_delta == Decimal("-0.040")
    assert result.realized_pnl_after == Decimal("-0.040")
    assert updated_order.status == OrderStatus.FILLED
    assert updated_order.filled_qty == Decimal("1")
    assert updated_order.average_exec_price == Decimal("6.635")
    assert updated_order.filled_at == 1781166956564
    assert updated_position.is_closed is True
    assert updated_position.current_qty == Decimal("0")
    assert updated_position.realized_pnl == Decimal("-0.040")


@pytest.mark.asyncio
async def test_runtime_exchange_close_projection_recovery_blocks_wrong_close_side():
    order_repo = _OrderRepo([_sl_order()])
    position_repo = _PositionRepo([_position()])
    trade_source = _TradeSource([_closing_trade(side="sell")])

    result = await _service(order_repo, position_repo, trade_source).recover(
        _request(apply=True),
        now_ms=1781167000000,
    )

    assert result.status == RuntimeExchangeCloseProjectionRecoveryStatus.BLOCKED
    assert "exchange_trade_close_side_mismatch" in result.blockers
    assert result.local_state_mutated is False
    assert (await order_repo.get_order("rtod-a194d1ef363c12c3df-sl")).status == OrderStatus.OPEN

