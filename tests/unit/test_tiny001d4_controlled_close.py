from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.execution_orchestrator import ExecutionOrchestrator
from src.domain.exceptions import OrderNotFoundError
from src.domain.models import (
    Direction,
    Order,
    OrderCancelResult,
    OrderPlacementResult,
    OrderRole,
    OrderStatus,
    OrderType,
    Position,
)


SYMBOL = "ETH/USDT:USDT"


class _Lifecycle:
    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}

    def set_entry_partially_filled_callback(self, callback):
        self.entry_partial_cb = callback

    def set_entry_filled_callback(self, callback):
        self.entry_filled_cb = callback

    def set_exit_progressed_callback(self, callback):
        self.exit_progressed_cb = callback

    async def register_created_order(self, order: Order, metadata=None):
        order.status = OrderStatus.CREATED
        self.orders[order.id] = order
        return order

    async def submit_order(self, order_id: str, exchange_order_id=None):
        order = self.orders[order_id]
        order.exchange_order_id = exchange_order_id
        order.status = OrderStatus.SUBMITTED
        return order

    async def confirm_order(self, order_id: str, exchange_order_id=None):
        order = self.orders[order_id]
        if exchange_order_id:
            order.exchange_order_id = exchange_order_id
        order.status = OrderStatus.OPEN
        return order

    async def update_order_filled(self, order_id: str, filled_qty: Decimal, average_exec_price: Decimal):
        order = self.orders[order_id]
        order.filled_qty = filled_qty
        order.average_exec_price = average_exec_price
        order.status = OrderStatus.FILLED
        return order

    async def cancel_order(self, order_id: str, reason=None, oco_triggered=False):
        order = self.orders[order_id]
        order.status = OrderStatus.CANCELED
        order.exit_reason = reason
        return order

    async def reject_order(self, order_id: str, reason: str):
        order = self.orders[order_id]
        order.status = OrderStatus.REJECTED
        order.exit_reason = reason
        return order

    async def get_orders_by_signal(self, signal_id: str):
        return [order for order in self.orders.values() if order.signal_id == signal_id]


class _Gateway:
    def __init__(self) -> None:
        self.place_calls = []
        self.cancel_calls = []
        self.cancel_not_found_ids: set[str] = set()

    async def place_order(self, **kwargs):
        self.place_calls.append(kwargs)
        return OrderPlacementResult(
            order_id="exchange-generated",
            exchange_order_id="ex-close",
            symbol=kwargs["symbol"],
            order_type=OrderType.MARKET,
            direction=Direction.LONG,
            side=kwargs["side"],
            amount=kwargs["amount"],
            filled_qty=kwargs["amount"],
            average_exec_price=Decimal("2200"),
            reduce_only=kwargs["reduce_only"],
            client_order_id=kwargs["client_order_id"],
            status=OrderStatus.FILLED,
        )

    async def cancel_order(self, exchange_order_id: str, symbol: str):
        self.cancel_calls.append({"exchange_order_id": exchange_order_id, "symbol": symbol})
        if exchange_order_id in self.cancel_not_found_ids:
            raise OrderNotFoundError(f"订单不存在：{exchange_order_id}", "F-012")
        return OrderCancelResult(
            order_id=exchange_order_id,
            exchange_order_id=exchange_order_id,
            symbol=symbol,
            status=OrderStatus.CANCELED,
        )


class _PositionRepo:
    def __init__(self, position: Position) -> None:
        self.position = position
        self.saved: list[Position] = []

    async def get(self, position_id: str):
        return self.position if position_id == self.position.id else None

    async def save(self, position: Position) -> None:
        self.position = position
        self.saved.append(position)


def _position() -> Position:
    return Position(
        id="pos_sig-controlled",
        signal_id="sig-controlled",
        symbol=SYMBOL,
        direction=Direction.LONG,
        entry_price=Decimal("2100"),
        current_qty=Decimal("0.01"),
        opened_at=1,
    )


def _order(order_id: str, role: OrderRole, status: OrderStatus, exchange_order_id: str | None = None):
    return Order(
        id=order_id,
        signal_id="sig-controlled",
        exchange_order_id=exchange_order_id,
        symbol=SYMBOL,
        direction=Direction.LONG,
        order_type=OrderType.MARKET if role in {OrderRole.ENTRY, OrderRole.EXIT} else OrderType.LIMIT,
        order_role=role,
        requested_qty=Decimal("0.01"),
        filled_qty=Decimal("0.01") if status == OrderStatus.FILLED else Decimal("0"),
        average_exec_price=Decimal("2100") if status == OrderStatus.FILLED else None,
        status=status,
        created_at=1,
        updated_at=1,
        reduce_only=role != OrderRole.ENTRY,
        parent_order_id="entry" if role != OrderRole.ENTRY else None,
    )


@pytest.mark.asyncio
async def test_runtime_managed_controlled_close_projects_and_cancels_protection():
    from src.application.position_projection_service import PositionProjectionService

    position = _position()
    position_repo = _PositionRepo(position)
    lifecycle = _Lifecycle()
    lifecycle.orders["entry"] = _order("entry", OrderRole.ENTRY, OrderStatus.FILLED, "ex-entry")
    lifecycle.orders["sl"] = _order("sl", OrderRole.SL, OrderStatus.OPEN, "ex-sl")
    lifecycle.orders["tp"] = _order("tp", OrderRole.TP1, OrderStatus.OPEN, "ex-tp")
    gateway = _Gateway()
    capital = MagicMock()
    capital.record_exit_projection = AsyncMock()

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital,
        order_lifecycle=lifecycle,
        gateway=gateway,
        position_projection_service=PositionProjectionService(position_repo),
    )

    result = await orchestrator.execute_controlled_close(position=position)

    close_order = result["close_order"]
    assert close_order.order_role == OrderRole.EXIT
    assert close_order.status == OrderStatus.FILLED
    assert close_order.reduce_only is True
    assert gateway.place_calls == [
        {
            "symbol": SYMBOL,
            "order_type": "market",
            "side": "sell",
            "amount": Decimal("0.01"),
            "reduce_only": True,
            "client_order_id": close_order.id,
        }
    ]
    assert position_repo.position.is_closed is True
    assert position_repo.position.current_qty == Decimal("0")
    capital.record_exit_projection.assert_awaited_once()
    assert {call["exchange_order_id"] for call in gateway.cancel_calls} == {"ex-sl", "ex-tp"}
    assert lifecycle.orders["sl"].status == OrderStatus.CANCELED
    assert lifecycle.orders["tp"].status == OrderStatus.CANCELED


@pytest.mark.asyncio
async def test_controlled_close_records_custom_scope_metadata():
    from src.application.position_projection_service import PositionProjectionService

    position = _position()
    position_repo = _PositionRepo(position)
    lifecycle = _Lifecycle()
    lifecycle.orders["entry"] = _order("entry", OrderRole.ENTRY, OrderStatus.FILLED, "ex-entry")
    gateway = _Gateway()
    capital = MagicMock()
    capital.record_exit_projection = AsyncMock()

    observed_metadata = {}
    original_register = lifecycle.register_created_order

    async def register_created_order(order, metadata=None):
        observed_metadata.update(metadata or {})
        return await original_register(order, metadata=metadata)

    lifecycle.register_created_order = register_created_order
    orchestrator = ExecutionOrchestrator(
        capital_protection=capital,
        order_lifecycle=lifecycle,
        gateway=gateway,
        position_projection_service=PositionProjectionService(position_repo),
    )

    await orchestrator.execute_controlled_close(
        position=position,
        scope="runtime_owner_reduce_only_close",
    )

    assert observed_metadata["scope"] == "runtime_owner_reduce_only_close"


@pytest.mark.asyncio
async def test_controlled_close_terminalizes_protection_when_exchange_order_already_missing():
    from src.application.position_projection_service import PositionProjectionService

    position = _position()
    position_repo = _PositionRepo(position)
    lifecycle = _Lifecycle()
    lifecycle.orders["entry"] = _order("entry", OrderRole.ENTRY, OrderStatus.FILLED, "ex-entry")
    lifecycle.orders["sl"] = _order("sl", OrderRole.SL, OrderStatus.OPEN, "ex-sl")
    lifecycle.orders["tp"] = _order("tp", OrderRole.TP1, OrderStatus.OPEN, "ex-tp")
    gateway = _Gateway()
    gateway.cancel_not_found_ids = {"ex-tp"}
    capital = MagicMock()
    capital.record_exit_projection = AsyncMock()

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital,
        order_lifecycle=lifecycle,
        gateway=gateway,
        position_projection_service=PositionProjectionService(position_repo),
    )

    result = await orchestrator.execute_controlled_close(position=position)

    assert result["close_order"].status == OrderStatus.FILLED
    assert {call["exchange_order_id"] for call in gateway.cancel_calls} == {"ex-sl", "ex-tp"}
    assert lifecycle.orders["sl"].status == OrderStatus.CANCELED
    assert lifecycle.orders["tp"].status == OrderStatus.CANCELED


@pytest.fixture()
def _reset_close_guard():
    import src.interfaces.api_console_runtime as mod

    original = mod._CONTROLLED_CLOSE_EXECUTED
    mod._CONTROLLED_CLOSE_EXECUTED = False
    yield mod
    mod._CONTROLLED_CLOSE_EXECUTED = original


def _mock_request():
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = "testclient"
    req.body = AsyncMock(return_value=b"")
    return req


def _mock_api_module(*, active_positions):
    resolved = MagicMock()
    resolved.environment.exchange_testnet = True
    resolved.profile_name = "sim1_eth_runtime"
    provider = MagicMock()
    provider.resolved_config = resolved

    position_repo = MagicMock()
    position_repo.list_active = AsyncMock(return_value=active_positions)
    orchestrator = MagicMock()
    close_order = _order("exit-controlled", OrderRole.EXIT, OrderStatus.FILLED, "ex-close")
    orchestrator.execute_controlled_close = AsyncMock(
        return_value={"close_order": close_order, "terminalized_protection_orders": []}
    )
    api_mod = MagicMock()
    api_mod._runtime_config_provider = provider
    api_mod._position_repo = position_repo
    api_mod._execution_orchestrator = orchestrator
    api_mod._trace_service = None
    return api_mod, orchestrator


@pytest.mark.asyncio
async def test_controlled_close_endpoint_enforces_once_per_session(_reset_close_guard, monkeypatch):
    mod = _reset_close_guard
    mod._CONTROLLED_CLOSE_EXECUTED = True
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
    api_mod, _ = _mock_api_module(active_positions=[_position()])

    with patch.object(mod, "_load_api_module", return_value=api_mod):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await mod.execute_controlled_close(_mock_request())

    assert exc_info.value.status_code == 409
    assert "already executed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_controlled_close_endpoint_calls_orchestrator(_reset_close_guard, monkeypatch):
    mod = _reset_close_guard
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
    api_mod, orchestrator = _mock_api_module(active_positions=[_position()])

    with patch.object(mod, "_load_api_module", return_value=api_mod):
        response = await mod.execute_controlled_close(_mock_request())

    assert response.status == "FILLED"
    assert response.amount == Decimal("0.01")
    assert response.attempt_locked is True
    orchestrator.execute_controlled_close.assert_awaited_once()
