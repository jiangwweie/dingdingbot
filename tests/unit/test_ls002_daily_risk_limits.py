from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.capital_protection import CapitalProtectionManager
from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.position_projection_service import PositionProjectionService
from src.domain.models import (
    CapitalProtectionConfig,
    Direction,
    Order,
    OrderRole,
    OrderStatus,
    OrderType,
    Position,
)


class _FakeAccountService:
    def __init__(self, balance: Decimal = Decimal("1000")) -> None:
        self._balance = balance

    async def get_balance(self) -> Decimal:
        return self._balance


class _FakeNotifier:
    async def send_alert(self, title: str, message: str) -> None:
        return None


class _FakeGateway:
    async def fetch_ticker_price(self, symbol: str) -> Decimal:
        return Decimal("100")

    async def get_market_info(self, symbol: str):
        return {
            "min_quantity": Decimal("0.001"),
            "quantity_precision": 3,
            "step_size": Decimal("0.001"),
        }


class _StubOrderLifecycle:
    def set_entry_partially_filled_callback(self, callback) -> None:
        self._on_entry_partially_filled = callback

    def set_entry_filled_callback(self, callback) -> None:
        self._on_entry_filled = callback

    def set_exit_progressed_callback(self, callback) -> None:
        self._on_exit_progressed = callback


class _InMemoryPositionRepository:
    def __init__(self) -> None:
        self._positions: dict[str, Position] = {}

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def save(self, position: Position) -> None:
        self._positions[position.id] = position.model_copy(deep=True)

    async def get(self, position_id: str) -> Position | None:
        position = self._positions.get(position_id)
        return position.model_copy(deep=True) if position is not None else None

    async def get_by_signal_id(self, signal_id: str):
        return [
            position.model_copy(deep=True)
            for position in self._positions.values()
            if position.signal_id == signal_id
        ]

    async def list_active(self, *, symbol: str | None = None, limit: int = 100):
        items = [
            position.model_copy(deep=True)
            for position in self._positions.values()
            if not position.is_closed and (symbol is None or position.symbol == symbol)
        ]
        return items[:limit]


def _build_capital_protection_config() -> CapitalProtectionConfig:
    config = CapitalProtectionConfig()
    config.daily["max_trade_count"] = 10
    config.daily["max_loss_amount"] = Decimal("100")
    return config


def _build_manager(config: CapitalProtectionConfig | None = None) -> CapitalProtectionManager:
    return CapitalProtectionManager(
        config=config or _build_capital_protection_config(),
        account_service=_FakeAccountService(),
        notifier=_FakeNotifier(),
        gateway=_FakeGateway(),
    )


def _build_exit_order(
    *,
    order_id: str,
    filled_qty: Decimal,
    exec_price: Decimal,
    role: OrderRole,
    signal_id: str = "sig-ls002",
) -> Order:
    return Order(
        id=order_id,
        signal_id=signal_id,
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=role,
        price=exec_price,
        requested_qty=filled_qty,
        filled_qty=filled_qty,
        average_exec_price=exec_price,
        status=OrderStatus.FILLED,
        created_at=1,
        updated_at=1,
        reduce_only=True,
        close_fee=Decimal("0"),
    )


def _build_open_position(signal_id: str = "sig-ls002") -> Position:
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
async def test_pre_order_check_resets_daily_stats_on_new_utc_day():
    manager = _build_manager()
    manager._daily_stats.trade_count = 3
    manager._daily_stats.realized_pnl = Decimal("-12")
    manager._daily_stats.last_reset_date = "2000-01-01"

    result = await manager.pre_order_check(
        symbol="ETH/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.1"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("99"),
    )

    stats = await manager.get_daily_stats()
    assert result.allowed is True
    assert stats.trade_count == 0
    assert stats.realized_pnl == Decimal("0")
    assert stats.last_reset_date != "2000-01-01"


@pytest.mark.asyncio
async def test_daily_trade_count_limit_rejects_new_orders():
    config = _build_capital_protection_config()
    config.daily["max_trade_count"] = 1
    manager = _build_manager(config)

    await manager.record_closed_trade()

    result = await manager.pre_order_check(
        symbol="ETH/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.1"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("99"),
    )

    assert result.allowed is False
    assert result.reason == "DAILY_TRADE_COUNT_LIMIT"


@pytest.mark.asyncio
async def test_daily_projected_realized_pnl_limit_rejects_new_orders():
    config = _build_capital_protection_config()
    config.daily["max_loss_amount"] = Decimal("10")
    manager = _build_manager(config)

    await manager.record_projected_realized_pnl_delta(Decimal("-10.5"))

    result = await manager.pre_order_check(
        symbol="ETH/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.1"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("99"),
    )

    assert result.allowed is False
    assert result.reason == "DAILY_LOSS_LIMIT"


@pytest.mark.asyncio
async def test_recording_stats_resets_on_new_utc_day():
    manager = _build_manager()
    manager._daily_stats.trade_count = 2
    manager._daily_stats.realized_pnl = Decimal("8")
    manager._daily_stats.last_reset_date = "2000-01-01"

    await manager.record_projected_realized_pnl_delta(Decimal("-3"))

    stats = await manager.get_daily_stats()
    assert stats.trade_count == 0
    assert stats.realized_pnl == Decimal("-3")
    assert stats.last_reset_date != "2000-01-01"


@pytest.mark.asyncio
async def test_single_trade_risk_behavior_is_unchanged():
    manager = _build_manager()

    result = await manager.pre_order_check(
        symbol="ETH/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("10"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("0"),
    )

    assert result.allowed is False
    assert result.reason == "SINGLE_TRADE_LOSS_LIMIT"


@pytest.mark.asyncio
async def test_exit_projection_updates_daily_pnl_and_trade_count_without_replay_duplicates():
    position_repo = _InMemoryPositionRepository()
    await position_repo.save(_build_open_position())

    manager = _build_manager()
    orchestrator = ExecutionOrchestrator(
        capital_protection=manager,
        order_lifecycle=_StubOrderLifecycle(),
        gateway=_FakeGateway(),
        position_projection_service=PositionProjectionService(position_repo),
    )

    partial_exit = _build_exit_order(
        order_id="tp1-order",
        filled_qty=Decimal("0.4"),
        exec_price=Decimal("110"),
        role=OrderRole.TP1,
    )

    await orchestrator._handle_exit_filled(partial_exit)

    stats = await manager.get_daily_stats()
    projected_position = await position_repo.get("pos_sig-ls002")
    assert stats.realized_pnl == Decimal("4.0")
    assert stats.trade_count == 0
    assert projected_position is not None
    assert projected_position.current_qty == Decimal("0.6")
    assert projected_position.is_closed is False

    await orchestrator._handle_exit_filled(partial_exit)

    replay_stats = await manager.get_daily_stats()
    assert replay_stats.realized_pnl == Decimal("4.0")
    assert replay_stats.trade_count == 0

    final_exit = _build_exit_order(
        order_id="tp2-order",
        filled_qty=Decimal("0.6"),
        exec_price=Decimal("120"),
        role=OrderRole.TP2,
    )

    await orchestrator._handle_exit_filled(final_exit)

    final_stats = await manager.get_daily_stats()
    closed_position = await position_repo.get("pos_sig-ls002")
    assert final_stats.realized_pnl == Decimal("16.0")
    assert final_stats.trade_count == 1
    assert closed_position is not None
    assert closed_position.current_qty == Decimal("0")
    assert closed_position.is_closed is True


@pytest.mark.asyncio
async def test_daily_stats_are_process_local_memory_state():
    manager = _build_manager()
    await manager.record_projected_realized_pnl_delta(Decimal("-2"))
    await manager.record_closed_trade()

    restarted_manager = _build_manager()
    restarted_stats = await restarted_manager.get_daily_stats()

    assert restarted_stats.realized_pnl == Decimal("0")
    assert restarted_stats.trade_count == 0
