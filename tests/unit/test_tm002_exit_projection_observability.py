from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.position_projection_service import PositionProjectionService
from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType, Position


class _NoopOrderLifecycle:
    def set_entry_partially_filled_callback(self, callback) -> None:
        self.entry_partially_filled_callback = callback

    def set_entry_filled_callback(self, callback) -> None:
        self.entry_filled_callback = callback

    def set_exit_progressed_callback(self, callback) -> None:
        self.exit_progressed_callback = callback


class _FakeCapitalProtection:
    def __init__(self) -> None:
        self.exit_projection_calls: list[dict] = []

    async def record_exit_projection(self, **kwargs) -> None:
        self.exit_projection_calls.append(kwargs)


class _InMemoryPositionRepository:
    def __init__(self) -> None:
        self._positions: dict[str, Position] = {}

    async def save(self, position: Position) -> None:
        self._positions[position.id] = position.model_copy(deep=True)

    async def get(self, position_id: str) -> Position | None:
        position = self._positions.get(position_id)
        return position.model_copy(deep=True) if position is not None else None


def _build_exit_order(
    *,
    order_id: str = "exit-order",
    signal_id: str = "sig-tm002",
    filled_qty: Decimal = Decimal("0.5"),
    price: Decimal | None = Decimal("110"),
) -> Order:
    return Order(
        id=order_id,
        signal_id=signal_id,
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=price,
        requested_qty=filled_qty,
        filled_qty=filled_qty,
        average_exec_price=price,
        status=OrderStatus.FILLED,
        created_at=1,
        updated_at=1,
        reduce_only=True,
    )


def _build_position(signal_id: str = "sig-tm002") -> Position:
    return Position(
        id=f"pos_{signal_id}",
        signal_id=signal_id,
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal("100"),
        current_qty=Decimal("1"),
        watermark_price=Decimal("100"),
        realized_pnl=Decimal("0"),
        total_fees_paid=Decimal("0"),
        total_funding_paid=Decimal("0"),
        opened_at=1,
        closed_at=None,
        is_closed=False,
    )


@pytest.mark.asyncio
async def test_project_exit_fill_missing_local_position_is_observable_noop(caplog):
    service = PositionProjectionService(_InMemoryPositionRepository())

    result = await service.project_exit_fill(_build_exit_order())

    assert result is not None
    assert result.position is None
    assert result.delta_realized_pnl == Decimal("0")
    assert result.was_already_processed is True
    assert "Exit projection skipped: local position missing" in caplog.text


@pytest.mark.asyncio
async def test_project_exit_fill_invalid_exit_fill_is_observable_noop(caplog):
    repository = _InMemoryPositionRepository()
    await repository.save(_build_position())
    service = PositionProjectionService(repository)

    result = await service.project_exit_fill(
        _build_exit_order(filled_qty=Decimal("0"), price=None)
    )

    assert result is not None
    assert result.position is not None
    assert result.delta_realized_pnl == Decimal("0")
    assert result.was_already_processed is True
    assert "Exit projection skipped: invalid exit fill" in caplog.text


@pytest.mark.asyncio
async def test_orchestrator_missing_position_does_not_update_daily_stats_and_logs(caplog):
    capital_protection = _FakeCapitalProtection()
    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=_NoopOrderLifecycle(),
        gateway=object(),
        position_projection_service=PositionProjectionService(_InMemoryPositionRepository()),
    )

    await orchestrator._handle_exit_filled(_build_exit_order())

    assert capital_protection.exit_projection_calls == []
    assert "local position missing" in caplog.text
