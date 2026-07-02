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


def _build_entry_order(
    *,
    signal_id: str = "sig-tm002",
    filled_qty: Decimal = Decimal("1"),
    runtime_instance_id: str | None = "runtime-1",
    trial_binding_id: str | None = "trial-1",
    strategy_family_id: str | None = "family-1",
    strategy_family_version_id: str | None = "version-1",
    signal_evaluation_id: str | None = "signal-eval-1",
    order_candidate_id: str | None = "candidate-1",
) -> Order:
    return Order(
        id=f"entry-{signal_id}",
        signal_id=signal_id,
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.ENTRY,
        price=Decimal("100"),
        requested_qty=filled_qty,
        filled_qty=filled_qty,
        average_exec_price=Decimal("100"),
        status=OrderStatus.FILLED,
        created_at=1,
        updated_at=1,
        runtime_instance_id=runtime_instance_id,
        trial_binding_id=trial_binding_id,
        strategy_family_id=strategy_family_id,
        strategy_family_version_id=strategy_family_version_id,
        signal_evaluation_id=signal_evaluation_id,
        order_candidate_id=order_candidate_id,
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
async def test_project_entry_fill_propagates_runtime_semantic_ids():
    repository = _InMemoryPositionRepository()
    service = PositionProjectionService(repository)

    position = await service.project_entry_fill(_build_entry_order())

    assert position is not None
    assert position.runtime_instance_id == "runtime-1"
    assert position.trial_binding_id == "trial-1"
    assert position.strategy_family_id == "family-1"
    assert position.strategy_family_version_id == "version-1"
    assert position.signal_evaluation_id == "signal-eval-1"
    assert position.order_candidate_id == "candidate-1"
    assert position.semantic_ids.order_candidate_id == "candidate-1"


@pytest.mark.asyncio
async def test_project_entry_fill_preserves_existing_semantic_ids_when_entry_lacks_them():
    repository = _InMemoryPositionRepository()
    existing = _build_position()
    existing.runtime_instance_id = "runtime-existing"
    existing.trial_binding_id = "trial-existing"
    existing.strategy_family_id = "family-existing"
    existing.strategy_family_version_id = "version-existing"
    existing.signal_evaluation_id = "signal-eval-existing"
    existing.order_candidate_id = "candidate-existing"
    await repository.save(existing)
    service = PositionProjectionService(repository)

    position = await service.project_entry_fill(
        _build_entry_order(
            runtime_instance_id=None,
            trial_binding_id=None,
            strategy_family_id=None,
            strategy_family_version_id=None,
            signal_evaluation_id=None,
            order_candidate_id=None,
        )
    )

    assert position is not None
    assert position.runtime_instance_id == "runtime-existing"
    assert position.trial_binding_id == "trial-existing"
    assert position.strategy_family_id == "family-existing"
    assert position.strategy_family_version_id == "version-existing"
    assert position.signal_evaluation_id == "signal-eval-existing"
    assert position.order_candidate_id == "candidate-existing"


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
