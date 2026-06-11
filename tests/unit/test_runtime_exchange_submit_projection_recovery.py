from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.order_lifecycle_service import OrderLifecycleService
from src.application.position_projection_service import PositionProjectionService
from src.application.runtime_exchange_submit_projection_recovery_service import (
    RuntimeExchangeSubmitProjectionRecoveryRequest,
    RuntimeExchangeSubmitProjectionRecoveryService,
    RuntimeExchangeSubmitProjectionRecoveryStatus,
)
from src.domain.models import (
    Direction,
    Order,
    OrderPlacementResult,
    OrderRole,
    OrderStatus,
    OrderType,
    PositionInfo,
)


SYMBOL = "AVAX/USDT:USDT"
ENTRY_LOCAL_ID = "rtod-a194d1ef363c12c3df-entry"
SL_LOCAL_ID = "rtod-a194d1ef363c12c3df-sl"
ENTRY_EXCHANGE_ID = "39005273607"
SL_EXCHANGE_ID = "4000001547813056"


class _OrderRepository:
    def __init__(self, orders: list[Order]) -> None:
        self.orders = {order.id: order for order in orders}

    async def initialize(self) -> None:
        return None

    async def save(self, order: Order) -> None:
        self.orders[order.id] = order

    async def get_order(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)

    async def get_orders_by_signal(self, signal_id: str) -> list[Order]:
        return [order for order in self.orders.values() if order.signal_id == signal_id]

    async def get_orders_by_symbol(self, symbol: str) -> list[Order]:
        return [order for order in self.orders.values() if order.symbol == symbol]

    async def get_orders_by_status(self, status: OrderStatus) -> list[Order]:
        return [order for order in self.orders.values() if order.status == status]

    async def get_open_orders(self) -> list[Order]:
        return [
            order
            for order in self.orders.values()
            if order.status in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}
        ]


class _PositionRepository:
    def __init__(self) -> None:
        self.positions = {}

    async def save(self, position) -> None:
        self.positions[position.id] = position

    async def get(self, position_id: str):
        return self.positions.get(position_id)


class _Gateway:
    async def fetch_order(self, exchange_order_id: str, symbol: str):
        assert exchange_order_id == ENTRY_EXCHANGE_ID
        assert symbol == SYMBOL
        return OrderPlacementResult(
            order_id=ENTRY_EXCHANGE_ID,
            exchange_order_id=ENTRY_EXCHANGE_ID,
            symbol=SYMBOL,
            order_type=OrderType.MARKET,
            direction=Direction.SHORT,
            side="sell",
            amount=Decimal("1.0"),
            filled_qty=Decimal("1.0"),
            average_exec_price=Decimal("6.595"),
            price=Decimal("6.595"),
            reduce_only=False,
            status=OrderStatus.FILLED,
        )

    async def fetch_open_orders(self, symbol: str, params=None):
        assert symbol == SYMBOL
        assert params == {"stop": True}
        return [
            {
                "id": SL_EXCHANGE_ID,
                "clientOrderId": SL_LOCAL_ID,
                "symbol": SYMBOL,
                "status": "open",
                "type": "market",
                "side": "buy",
                "amount": 1.0,
                "filled": 0.0,
                "remaining": 1.0,
                "triggerPrice": 6.635,
                "stopPrice": 6.635,
                "reduceOnly": True,
            }
        ]

    async def fetch_positions(self, symbol=None):
        assert symbol == SYMBOL
        return [
            PositionInfo(
                symbol=SYMBOL,
                side="short",
                size=Decimal("1.0"),
                entry_price=Decimal("6.595"),
                mark_price=Decimal("6.588"),
                unrealized_pnl=Decimal("0.007"),
                leverage=1,
                margin_mode="cross",
            )
        ]


def _orders() -> list[Order]:
    created_at = 1781163965522
    semantic = {
        "runtime_instance_id": "strategy-runtime-95655873b76c",
        "trial_binding_id": "admission-binding-34757174b520",
        "strategy_family_id": "BTPC-001",
        "strategy_family_version_id": "BTPC-001-v0",
        "signal_evaluation_id": "signal-evaluation-adabffa08945",
        "order_candidate_id": "order-candidate-d0c432b4d869",
    }
    return [
        Order(
            id=ENTRY_LOCAL_ID,
            signal_id="signal-evaluation-adabffa08945",
            exchange_order_id=ENTRY_EXCHANGE_ID,
            symbol=SYMBOL,
            direction=Direction.SHORT,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.218954750000000000"),
            status=OrderStatus.SUBMITTED,
            created_at=created_at,
            updated_at=created_at,
            reduce_only=False,
            **semantic,
        ),
        Order(
            id=SL_LOCAL_ID,
            signal_id="signal-evaluation-adabffa08945",
            exchange_order_id=SL_EXCHANGE_ID,
            symbol=SYMBOL,
            direction=Direction.SHORT,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            trigger_price=Decimal("6.635"),
            requested_qty=Decimal("1.218954750000000000"),
            status=OrderStatus.SUBMITTED,
            created_at=created_at,
            updated_at=created_at,
            reduce_only=True,
            parent_order_id=ENTRY_LOCAL_ID,
            **semantic,
        ),
    ]


def _service(apply: bool = False):
    order_repo = _OrderRepository(_orders())
    position_repo = _PositionRepository()
    lifecycle = OrderLifecycleService(order_repo)
    service = RuntimeExchangeSubmitProjectionRecoveryService(
        gateway=_Gateway(),
        order_repository=order_repo,
        lifecycle=lifecycle,
        position_projection_service=PositionProjectionService(position_repo),
    )
    request = RuntimeExchangeSubmitProjectionRecoveryRequest(
        symbol=SYMBOL,
        entry_local_order_id=ENTRY_LOCAL_ID,
        entry_exchange_order_id=ENTRY_EXCHANGE_ID,
        protection_local_order_id=SL_LOCAL_ID,
        protection_exchange_order_id=SL_EXCHANGE_ID,
        apply=apply,
    )
    return service, request, order_repo, position_repo


@pytest.mark.asyncio
async def test_runtime_exchange_submit_projection_recovery_dry_run_does_not_mutate():
    service, request, order_repo, position_repo = _service(apply=False)

    result = await service.recover(request)

    assert result.status == RuntimeExchangeSubmitProjectionRecoveryStatus.DRY_RUN_READY
    assert result.blockers == []
    assert result.local_state_mutated is False
    assert order_repo.orders[ENTRY_LOCAL_ID].status == OrderStatus.SUBMITTED
    assert order_repo.orders[ENTRY_LOCAL_ID].requested_qty == Decimal(
        "1.218954750000000000"
    )
    assert position_repo.positions == {}


@pytest.mark.asyncio
async def test_runtime_exchange_submit_projection_recovery_applies_local_projection():
    service, request, order_repo, position_repo = _service(apply=True)

    result = await service.recover(request)

    assert result.status == RuntimeExchangeSubmitProjectionRecoveryStatus.APPLIED
    assert result.blockers == []
    assert result.local_state_mutated is True
    entry = order_repo.orders[ENTRY_LOCAL_ID]
    protection = order_repo.orders[SL_LOCAL_ID]
    assert entry.status == OrderStatus.FILLED
    assert entry.requested_qty == Decimal("1.0")
    assert entry.filled_qty == Decimal("1.0")
    assert entry.average_exec_price == Decimal("6.595")
    assert protection.status == OrderStatus.OPEN
    assert protection.requested_qty == Decimal("1.0")
    assert protection.trigger_price == Decimal("6.635")
    projected = position_repo.positions["pos_signal-evaluation-adabffa08945"]
    assert projected.symbol == SYMBOL
    assert projected.direction == Direction.SHORT
    assert projected.current_qty == Decimal("1.0")
    assert projected.entry_price == Decimal("6.595")
