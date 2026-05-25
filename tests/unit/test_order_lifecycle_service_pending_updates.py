from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.application.order_lifecycle_service import OrderLifecycleService
from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType


class _InMemoryOrderRepository:
    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}

    async def initialize(self) -> None:
        return None

    async def save(self, order: Order) -> None:
        self.orders[order.id] = order

    async def get_order_by_exchange_id(self, exchange_order_id: str):
        for order in self.orders.values():
            if order.exchange_order_id == exchange_order_id:
                return order
        return None

    async def get_orders_by_signal(self, signal_id: str):
        return [order for order in self.orders.values() if order.signal_id == signal_id]


def _order(
    *,
    order_id: str,
    exchange_order_id: str,
    status: OrderStatus,
    filled_qty: Decimal = Decimal("0"),
    role: OrderRole = OrderRole.TP1,
) -> Order:
    return Order(
        id=order_id,
        signal_id="sig-1",
        exchange_order_id=exchange_order_id,
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=role,
        requested_qty=Decimal("0.01"),
        filled_qty=filled_qty,
        average_exec_price=Decimal("2133"),
        status=status,
        created_at=1,
        updated_at=1,
        reduce_only=True,
    )


@pytest.mark.asyncio
async def test_exchange_update_before_local_order_is_buffered_and_replayed():
    repo = _InMemoryOrderRepository()
    service = OrderLifecycleService(
        repo,
        pending_update_retry_interval_seconds=0.01,
        pending_update_max_retries=10,
    )

    exchange_update = _order(
        order_id="exchange-order",
        exchange_order_id="ex-1",
        status=OrderStatus.FILLED,
        filled_qty=Decimal("0.01"),
    )

    await service.update_order_from_exchange(exchange_update)

    assert "ex-1" in service.list_pending_exchange_updates()

    local_order = _order(
        order_id="local-order",
        exchange_order_id="ex-1",
        status=OrderStatus.OPEN,
    )
    await repo.save(local_order)

    await asyncio.sleep(0.08)

    updated = await repo.get_order_by_exchange_id("ex-1")
    assert updated.status == OrderStatus.FILLED
    assert updated.filled_qty == Decimal("0.01")
    assert service.list_pending_exchange_updates() == {}
    await service.stop()


@pytest.mark.asyncio
async def test_external_close_hygiene_terminalizes_active_protection_orders_only():
    repo = _InMemoryOrderRepository()
    service = OrderLifecycleService(repo)
    await repo.save(
        _order(
            order_id="entry",
            exchange_order_id="ex-entry",
            status=OrderStatus.FILLED,
            filled_qty=Decimal("0.01"),
            role=OrderRole.ENTRY,
        )
    )
    await repo.save(
        _order(
            order_id="tp-open",
            exchange_order_id="ex-tp-open",
            status=OrderStatus.OPEN,
            role=OrderRole.TP1,
        )
    )
    await repo.save(
        _order(
            order_id="sl-partial",
            exchange_order_id="ex-sl-partial",
            status=OrderStatus.PARTIALLY_FILLED,
            filled_qty=Decimal("0.001"),
            role=OrderRole.SL,
        )
    )

    terminalized = await service.mark_stale_protection_orders_after_external_close(
        "sig-1",
        source="periodic",
        reason="POSITION_CLOSED_ON_EXCHANGE_NOT_PROJECTED",
        metadata={"test": True},
    )

    assert [order.id for order in terminalized] == ["tp-open", "sl-partial"]
    assert repo.orders["entry"].status == OrderStatus.FILLED
    assert repo.orders["tp-open"].status == OrderStatus.CANCELED
    assert repo.orders["tp-open"].exit_reason == "EXTERNAL_CLOSE_LOCAL_HYGIENE"
    assert repo.orders["sl-partial"].status == OrderStatus.CANCELED
    assert repo.orders["sl-partial"].exit_reason == "EXTERNAL_CLOSE_LOCAL_HYGIENE"


@pytest.mark.asyncio
async def test_pending_open_replay_after_local_filled_is_ignored():
    repo = _InMemoryOrderRepository()
    service = OrderLifecycleService(
        repo,
        pending_update_retry_interval_seconds=0.01,
        pending_update_max_retries=10,
    )
    await service.update_order_from_exchange(
        _order(
            order_id="exchange-order",
            exchange_order_id="ex-filled",
            status=OrderStatus.OPEN,
        )
    )
    await repo.save(
        _order(
            order_id="local-order",
            exchange_order_id="ex-filled",
            status=OrderStatus.FILLED,
            filled_qty=Decimal("0.01"),
        )
    )

    await asyncio.sleep(0.06)

    updated = await repo.get_order_by_exchange_id("ex-filled")
    assert updated.status == OrderStatus.FILLED
    assert updated.filled_qty == Decimal("0.01")
    assert service.list_pending_exchange_updates() == {}
    await service.stop()


@pytest.mark.asyncio
async def test_pending_partially_filled_replay_after_local_filled_is_ignored():
    repo = _InMemoryOrderRepository()
    service = OrderLifecycleService(
        repo,
        pending_update_retry_interval_seconds=0.01,
        pending_update_max_retries=10,
    )
    await service.update_order_from_exchange(
        _order(
            order_id="exchange-order",
            exchange_order_id="ex-partial",
            status=OrderStatus.PARTIALLY_FILLED,
            filled_qty=Decimal("0.005"),
        )
    )
    await repo.save(
        _order(
            order_id="local-order",
            exchange_order_id="ex-partial",
            status=OrderStatus.FILLED,
            filled_qty=Decimal("0.01"),
        )
    )

    await asyncio.sleep(0.06)

    updated = await repo.get_order_by_exchange_id("ex-partial")
    assert updated.status == OrderStatus.FILLED
    assert updated.filled_qty == Decimal("0.01")
    assert service.list_pending_exchange_updates() == {}
    await service.stop()


@pytest.mark.asyncio
async def test_duplicate_terminal_update_is_idempotent():
    repo = _InMemoryOrderRepository()
    service = OrderLifecycleService(repo)
    await repo.save(
        _order(
            order_id="local-order",
            exchange_order_id="ex-dup",
            status=OrderStatus.FILLED,
            filled_qty=Decimal("0.01"),
        )
    )

    updated = await service.update_order_from_exchange(
        _order(
            order_id="exchange-order",
            exchange_order_id="ex-dup",
            status=OrderStatus.FILLED,
            filled_qty=Decimal("0.01"),
        )
    )

    assert updated.status == OrderStatus.FILLED
    assert updated.filled_qty == Decimal("0.01")
    await service.stop()


@pytest.mark.asyncio
async def test_pending_filled_replay_after_local_open_is_applied():
    repo = _InMemoryOrderRepository()
    service = OrderLifecycleService(
        repo,
        pending_update_retry_interval_seconds=0.01,
        pending_update_max_retries=10,
    )
    await service.update_order_from_exchange(
        _order(
            order_id="exchange-order",
            exchange_order_id="ex-late-filled",
            status=OrderStatus.FILLED,
            filled_qty=Decimal("0.01"),
        )
    )
    await repo.save(
        _order(
            order_id="local-order",
            exchange_order_id="ex-late-filled",
            status=OrderStatus.OPEN,
        )
    )

    await asyncio.sleep(0.06)

    updated = await repo.get_order_by_exchange_id("ex-late-filled")
    assert updated.status == OrderStatus.FILLED
    assert updated.filled_qty == Decimal("0.01")
    assert service.list_pending_exchange_updates() == {}
    await service.stop()


@pytest.mark.asyncio
async def test_unresolved_pending_exchange_update_expires_without_crashing():
    repo = _InMemoryOrderRepository()
    service = OrderLifecycleService(
        repo,
        pending_update_retry_interval_seconds=0.01,
        pending_update_max_retries=2,
    )

    await service.update_order_from_exchange(
        _order(
            order_id="exchange-order",
            exchange_order_id="missing-ex",
            status=OrderStatus.OPEN,
        )
    )

    await asyncio.sleep(0.06)

    assert service.list_pending_exchange_updates() == {}
    await service.stop()


@pytest.mark.asyncio
async def test_pending_update_retry_task_cancelled_on_stop():
    repo = _InMemoryOrderRepository()
    service = OrderLifecycleService(
        repo,
        pending_update_retry_interval_seconds=10,
        pending_update_max_retries=10,
    )

    await service.update_order_from_exchange(
        _order(
            order_id="exchange-order",
            exchange_order_id="pending-ex",
            status=OrderStatus.OPEN,
        )
    )
    assert "pending-ex" in service.list_pending_exchange_updates()

    await service.stop()

    assert service.list_pending_exchange_updates() == {}
