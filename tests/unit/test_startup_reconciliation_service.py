from decimal import Decimal

from src.application.startup_reconciliation_service import StartupReconciliationService
from src.domain.models import (
    Direction,
    Order,
    OrderPlacementResult,
    OrderRole,
    OrderStatus,
    OrderType,
)


def _local_order() -> Order:
    return Order(
        id="pg-tp-1",
        signal_id="sig-bnb-1",
        exchange_order_id="ex-tp-1",
        symbol="BNB/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal("600.62"),
        requested_qty=Decimal("0.01"),
        filled_qty=Decimal("0"),
        average_exec_price=None,
        status=OrderStatus.OPEN,
        created_at=1,
        updated_at=1,
        reduce_only=True,
    )


def _exchange_result(
    *,
    status: OrderStatus,
    amount: Decimal = Decimal("0.01"),
    filled_qty: Decimal | None,
    price: Decimal | None = Decimal("600.62"),
    average_exec_price: Decimal | None = None,
) -> OrderPlacementResult:
    return OrderPlacementResult(
        order_id="ex-tp-1",
        exchange_order_id="ex-tp-1",
        symbol="BNB/USDT:USDT",
        order_type=OrderType.LIMIT,
        direction=Direction.LONG,
        side="sell",
        amount=amount,
        price=price,
        filled_qty=filled_qty,
        average_exec_price=average_exec_price,
        reduce_only=True,
        status=status,
    )


def test_startup_reconciliation_open_order_keeps_filled_qty_zero():
    exchange_update = StartupReconciliationService._build_exchange_order_update(
        local_order=_local_order(),
        exchange_order_result=_exchange_result(
            status=OrderStatus.OPEN,
            filled_qty=Decimal("0"),
            average_exec_price=None,
        ),
        updated_at_ms=2,
    )

    assert exchange_update.requested_qty == Decimal("0.01")
    assert exchange_update.filled_qty == Decimal("0")
    assert exchange_update.average_exec_price is None
    assert exchange_update.status == OrderStatus.OPEN


def test_startup_reconciliation_open_order_without_filled_does_not_use_amount():
    exchange_update = StartupReconciliationService._build_exchange_order_update(
        local_order=_local_order(),
        exchange_order_result=_exchange_result(
            status=OrderStatus.OPEN,
            filled_qty=None,
            average_exec_price=None,
        ),
        updated_at_ms=2,
    )

    assert exchange_update.requested_qty == Decimal("0.01")
    assert exchange_update.filled_qty == Decimal("0")
    assert exchange_update.average_exec_price is None
    assert exchange_update.status == OrderStatus.OPEN


def test_startup_reconciliation_filled_order_uses_exchange_filled_and_average():
    exchange_update = StartupReconciliationService._build_exchange_order_update(
        local_order=_local_order(),
        exchange_order_result=_exchange_result(
            status=OrderStatus.FILLED,
            filled_qty=Decimal("0.01"),
            average_exec_price=Decimal("600.62"),
        ),
        updated_at_ms=2,
    )

    assert exchange_update.requested_qty == Decimal("0.01")
    assert exchange_update.filled_qty == Decimal("0.01")
    assert exchange_update.average_exec_price == Decimal("600.62")
    assert exchange_update.status == OrderStatus.FILLED
