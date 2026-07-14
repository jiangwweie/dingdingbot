from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.reconciliation import ReconciliationService
from src.application.protection_health_monitor import (
    PROTECTION_DATA_HYGIENE_LOCAL_SL_MISSING_ON_EXCHANGE,
    PROTECTION_EXCHANGE_POSITION_UNTRACKED,
    PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE,
    PROTECTION_MISSING_EXCHANGE_SL,
    PROTECTION_ORPHAN_REDUCE_ONLY_ORDER,
)
from src.domain.models import (
    Direction,
    Order,
    OrderRole,
    OrderResponse,
    OrderStatus,
    OrderType,
    PositionInfo,
)
from src.infrastructure.exchange_gateway import ExchangeGateway


SYMBOL = "ETH/USDT:USDT"


class _FakeRestExchange:
    def __init__(self) -> None:
        self.symbols: list[str] = []
        self.params: list[dict] = []

    async def fetch_open_orders(self, symbol: str, params=None):
        self.symbols.append(symbol)
        self.params.append(params or {})
        return [{"id": "ex-1", "symbol": symbol, "status": "open", "amount": "1"}]


class _MultiViewOpenOrderExchange:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def fetch_open_orders(self, symbol: str, params=None):
        params = params or {}
        self.calls.append((symbol, params))
        if params == {}:
            return [
                {
                    "id": "order-normal",
                    "clientOrderId": "client-normal",
                    "symbol": symbol,
                    "status": "open",
                },
                {
                    "id": "order-stop",
                    "clientOrderId": "client-stop",
                    "symbol": symbol,
                    "status": "open",
                },
            ]
        if params == {"stop": True}:
            return [
                {
                    "id": "order-stop",
                    "clientOrderId": "client-stop",
                    "symbol": symbol,
                    "status": "open",
                    "stopPrice": "90",
                }
            ]
        if params == {"type": "STOP_MARKET"}:
            return [
                {
                    "id": "algo-stop",
                    "clientOrderId": "client-stop",
                    "symbol": symbol,
                    "status": "open",
                    "triggerPrice": "90",
                }
            ]
        raise AssertionError(f"unexpected params: {params}")


class _FakeGateway:
    def __init__(
        self,
        *,
        positions: list[PositionInfo] | None = None,
        open_orders: list[dict] | None = None,
        fail_positions: bool = False,
        fail_open_orders: bool = False,
    ) -> None:
        self.positions = positions or []
        self.open_orders = open_orders or []
        self.fail_positions = fail_positions
        self.fail_open_orders = fail_open_orders
        self.fetch_open_order_params: list[dict] = []

    async def fetch_positions(self, symbol: str):
        if self.fail_positions:
            raise RuntimeError("positions unavailable")
        return [position for position in self.positions if position.symbol == symbol]

    async def fetch_open_orders(self, symbol: str, params=None):
        if self.fail_open_orders:
            raise RuntimeError("open orders unavailable")
        self.fetch_open_order_params.append(params or {})
        return [order for order in self.open_orders if order.get("symbol") == symbol]

    def get_account_snapshot(self):
        return None


class _FakePositionSource:
    def __init__(self, positions: list[PositionInfo] | None = None) -> None:
        self.positions = positions or []

    async def list_active(self, *, symbol: str | None = None, limit: int = 100):
        return [
            position
            for position in self.positions
            if symbol is None or position.symbol == symbol
        ][:limit]


class _FakeOrderRepository:
    def __init__(self, orders: list[Order] | None = None) -> None:
        self.orders = orders or []

    async def get_open_orders(self, symbol: str | None = None):
        return [
            order
            for order in self.orders
            if (symbol is None or order.symbol == symbol)
            and order.status in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}
        ]

    async def get_orders_by_status(self, status: OrderStatus, symbol: str | None = None):
        return [
            order
            for order in self.orders
            if order.status == status and (symbol is None or order.symbol == symbol)
        ]


class _ImportingOrderRepository(_FakeOrderRepository):
    def __init__(self) -> None:
        super().__init__([])
        self.imported_orders: list[OrderResponse] = []

    async def import_order(self, order: OrderResponse) -> None:
        self.imported_orders.append(order)


class _ConditionalOnlyGateway(_FakeGateway):
    async def fetch_open_orders(self, symbol: str, params=None):
        self.fetch_open_order_params.append(params or {})
        if params in ({"stop": True}, {"type": "STOP_MARKET"}):
            return [
                order
                for order in self.open_orders
                if order.get("symbol") == symbol and order.get("triggerPrice") is not None
            ]
        return [
            order
            for order in self.open_orders
            if order.get("symbol") == symbol and order.get("triggerPrice") is None
        ]


def _position(size: str = "1") -> PositionInfo:
    return PositionInfo(
        symbol=SYMBOL,
        side="long",
        size=Decimal(size),
        entry_price=Decimal("100"),
        unrealized_pnl=Decimal("0"),
        leverage=1,
    )


def _order(
    order_id: str,
    exchange_order_id: str,
    role: OrderRole,
    *,
    status: OrderStatus = OrderStatus.OPEN,
    qty: str = "1",
) -> Order:
    return Order(
        id=order_id,
        signal_id="sig-ls003a",
        exchange_order_id=exchange_order_id,
        symbol=SYMBOL,
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET if role == OrderRole.SL else OrderType.LIMIT,
        order_role=role,
        requested_qty=Decimal(qty),
        filled_qty=Decimal("0"),
        status=status,
        created_at=1,
        updated_at=1,
        reduce_only=role != OrderRole.ENTRY,
    )


def _exchange_order(
    order_id: str,
    *,
    amount: str = "1",
    reduce_only: bool = True,
    order_type: str = "limit",
    trigger_price: str | None = None,
):
    return {
        "id": order_id,
        "symbol": SYMBOL,
        "status": "open",
        "type": order_type,
        "side": "sell",
        "amount": amount,
        "filled": "0",
        "price": "120",
        **({"triggerPrice": trigger_price} if trigger_price is not None else {}),
        "reduceOnly": reduce_only,
        "timestamp": 1,
    }


def _exchange_sl(order_id: str = "ex-sl"):
    return _exchange_order(order_id, order_type="stop", trigger_price="90")


def _orphan_entry_order(order_id: str = "ex-entry") -> OrderResponse:
    return OrderResponse(
        order_id=order_id,
        exchange_order_id=order_id,
        symbol=SYMBOL,
        order_type=OrderType.LIMIT,
        direction=Direction.LONG,
        order_role=OrderRole.ENTRY,
        status=OrderStatus.OPEN,
        amount=Decimal("1"),
        filled_amount=Decimal("0"),
        price=Decimal("100"),
        reduce_only=False,
        created_at=1,
        updated_at=1,
    )


def _service(
    *,
    local_positions: list[PositionInfo] | None = None,
    exchange_positions: list[PositionInfo] | None = None,
    local_orders: list[Order] | None = None,
    exchange_orders: list[dict] | None = None,
    fail_positions: bool = False,
    fail_open_orders: bool = False,
) -> ReconciliationService:
    return ReconciliationService(
        gateway=_FakeGateway(
            positions=exchange_positions,
            open_orders=exchange_orders,
            fail_positions=fail_positions,
            fail_open_orders=fail_open_orders,
        ),
        position_mgr=_FakePositionSource(local_positions),
        order_repository=_FakeOrderRepository(local_orders),
    )


@pytest.mark.asyncio
async def test_fetch_open_orders_wrapper_calls_rest_exchange():
    gateway = object.__new__(ExchangeGateway)
    gateway.rest_exchange = _FakeRestExchange()

    orders = await gateway.fetch_open_orders(SYMBOL)

    assert gateway.rest_exchange.symbols == [SYMBOL]
    assert orders[0]["id"] == "ex-1"


@pytest.mark.asyncio
async def test_fetch_all_open_orders_merges_conditional_views_and_deduplicates():
    gateway = object.__new__(ExchangeGateway)
    gateway.exchange_name = "binance"
    gateway.rest_exchange = _MultiViewOpenOrderExchange()

    orders = await gateway.fetch_all_open_orders(SYMBOL)

    assert gateway.rest_exchange.calls == [
        (SYMBOL, {}),
        (SYMBOL, {"stop": True}),
    ]
    assert len(orders) == 2
    stop = next(order for order in orders if order["clientOrderId"] == "client-stop")
    assert stop.get("stopPrice") == "90" or stop.get("triggerPrice") == "90"


@pytest.mark.asyncio
async def test_get_local_open_orders_includes_submitted_orders():
    submitted_order = _order(
        "local-submitted",
        "ex-submitted",
        OrderRole.ENTRY,
        status=OrderStatus.SUBMITTED,
    )
    service = _service(local_orders=[submitted_order])

    orders = await service._get_local_open_orders(SYMBOL)

    assert [order.order_id for order in orders] == ["local-submitted"]
    assert orders[0].amount == Decimal("1")


@pytest.mark.asyncio
async def test_local_position_missing_on_exchange_is_severe():
    service = _service(local_positions=[_position()], exchange_positions=[])

    result = await service.build_read_model(SYMBOL)

    assert any(
        mismatch.mismatch_type == "local_position_missing_on_exchange"
        and mismatch.severity == "SEVERE"
        for mismatch in result.mismatches
    )


@pytest.mark.asyncio
async def test_exchange_position_missing_locally_is_severe():
    service = _service(local_positions=[], exchange_positions=[_position()])

    result = await service.build_read_model(SYMBOL)

    assert any(
        mismatch.mismatch_type == "exchange_position_missing_locally"
        and mismatch.severity == "SEVERE"
        for mismatch in result.mismatches
    )


@pytest.mark.asyncio
async def test_active_position_without_sl_reports_severe_protection_issue():
    service = _service(
        local_positions=[_position()],
        exchange_positions=[_position()],
        local_orders=[],
        exchange_orders=[],
    )

    result = await service.build_read_model(SYMBOL)

    assert any(
        mismatch.mismatch_type == "missing_any_protection"
        and mismatch.severity == "SEVERE"
        for mismatch in result.mismatches
    )


@pytest.mark.asyncio
async def test_active_position_with_sl_but_no_tp_reports_warning():
    service = _service(
        local_positions=[_position()],
        exchange_positions=[_position()],
        local_orders=[_order("local-sl", "ex-sl", OrderRole.SL)],
        exchange_orders=[_exchange_sl("ex-sl")],
    )

    result = await service.build_read_model(SYMBOL)

    assert any(
        mismatch.mismatch_type == "missing_tp_protection"
        and mismatch.severity == "WARNING"
        for mismatch in result.mismatches
    )


@pytest.mark.asyncio
async def test_local_open_order_missing_on_exchange_reports_warning():
    service = _service(
        local_orders=[_order("local-ghost", "ex-ghost", OrderRole.ENTRY)],
        exchange_orders=[],
    )

    result = await service.build_read_model(SYMBOL)

    assert any(
        mismatch.mismatch_type == "local_order_missing_on_exchange"
        and mismatch.severity == "WARNING"
        for mismatch in result.mismatches
    )


@pytest.mark.asyncio
async def test_exchange_open_order_missing_locally_reports_warning():
    service = _service(
        local_orders=[],
        exchange_orders=[_exchange_order("ex-orphan")],
    )

    result = await service.build_read_model(SYMBOL)

    assert any(
        mismatch.mismatch_type == "exchange_order_missing_locally"
        and mismatch.severity == "WARNING"
        for mismatch in result.mismatches
    )


@pytest.mark.asyncio
async def test_orphan_entry_order_without_import_contract_stays_import_pending():
    service = ReconciliationService(
        gateway=_FakeGateway(),
        order_repository=_FakeOrderRepository(),
    )

    imported, canceled = await service._process_orphan_orders(
        [_orphan_entry_order("ex-entry-pending")],
        SYMBOL,
    )

    assert canceled == []
    assert len(imported) == 1
    assert imported[0].order_id == "ex-entry-pending"
    assert imported[0].action_taken == "IMPORT_NOT_AVAILABLE"


@pytest.mark.asyncio
async def test_orphan_entry_order_uses_import_contract_when_available():
    order_repository = _ImportingOrderRepository()
    service = ReconciliationService(
        gateway=_FakeGateway(),
        order_repository=order_repository,
    )
    order = _orphan_entry_order("ex-entry-importable")

    imported, canceled = await service._process_orphan_orders([order], SYMBOL)

    assert canceled == []
    assert len(imported) == 1
    assert imported[0].action_taken == "IMPORTED_TO_DB"
    assert order_repository.imported_orders == [order]


@pytest.mark.asyncio
async def test_matching_state_has_no_mismatches():
    local_orders = [
        _order("local-sl", "ex-sl", OrderRole.SL),
        _order("local-tp", "ex-tp", OrderRole.TP1),
    ]
    service = _service(
        local_positions=[_position()],
        exchange_positions=[_position()],
        local_orders=local_orders,
        exchange_orders=[_exchange_sl("ex-sl"), _exchange_order("ex-tp")],
    )

    result = await service.build_read_model(SYMBOL)

    assert result.is_consistent
    assert result.mismatches == []


@pytest.mark.asyncio
async def test_conditional_stop_market_orders_are_included_in_read_model():
    gateway = _ConditionalOnlyGateway(
        positions=[_position()],
        open_orders=[_exchange_sl("ex-sl"), _exchange_order("ex-tp")],
    )
    service = ReconciliationService(
        gateway=gateway,
        position_mgr=_FakePositionSource([_position()]),
        order_repository=_FakeOrderRepository(
            [
                _order("local-sl", "ex-sl", OrderRole.SL),
                _order("local-tp", "ex-tp", OrderRole.TP1),
            ]
        ),
    )

    result = await service.build_read_model(SYMBOL)

    assert result.is_consistent
    assert result.mismatches == []
    assert {"stop": True} in gateway.fetch_open_order_params
    assert {"type": "STOP_MARKET"} in gateway.fetch_open_order_params


@pytest.mark.asyncio
async def test_local_and_exchange_position_without_exchange_native_sl_is_critical():
    service = _service(
        local_positions=[_position()],
        exchange_positions=[_position()],
        local_orders=[_order("local-tp", "ex-tp", OrderRole.TP1)],
        exchange_orders=[_exchange_order("ex-tp")],
    )

    result = await service.build_read_model(SYMBOL)

    mismatch = next(
        item
        for item in result.mismatches
        if item.metadata.get("protection_reason_code") == PROTECTION_MISSING_EXCHANGE_SL
    )
    assert mismatch.severity == "CRITICAL"
    assert mismatch.reason == PROTECTION_MISSING_EXCHANGE_SL


@pytest.mark.asyncio
async def test_exchange_position_without_local_position_is_critical_protection_issue():
    service = _service(local_positions=[], exchange_positions=[_position()])

    result = await service.build_read_model(SYMBOL)

    mismatch = next(
        item
        for item in result.mismatches
        if item.metadata.get("protection_reason_code") == PROTECTION_EXCHANGE_POSITION_UNTRACKED
    )
    assert mismatch.severity == "CRITICAL"
    assert mismatch.exchange_ref == SYMBOL


@pytest.mark.asyncio
async def test_local_sl_record_missing_on_exchange_is_critical():
    service = _service(
        local_positions=[_position()],
        exchange_positions=[_position()],
        local_orders=[_order("local-sl", "ex-missing-sl", OrderRole.SL)],
        exchange_orders=[],
    )

    result = await service.build_read_model(SYMBOL)

    mismatch = next(
        item
        for item in result.mismatches
        if item.metadata.get("protection_reason_code")
        == PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE
    )
    assert mismatch.severity == "CRITICAL"
    assert mismatch.local_ref == "local-sl"
    assert mismatch.exchange_ref == "ex-missing-sl"


@pytest.mark.asyncio
async def test_local_sl_record_missing_without_position_is_data_hygiene():
    service = _service(
        local_positions=[],
        exchange_positions=[],
        local_orders=[_order("local-sl", "ex-missing-sl", OrderRole.SL)],
        exchange_orders=[],
    )

    result = await service.build_read_model(SYMBOL)

    mismatch = next(
        item
        for item in result.mismatches
        if item.metadata.get("protection_reason_code")
        == PROTECTION_DATA_HYGIENE_LOCAL_SL_MISSING_ON_EXCHANGE
    )
    assert mismatch.severity == "HIGH"
    assert mismatch.local_ref == "local-sl"
    assert mismatch.metadata["has_local_position"] is False
    assert mismatch.metadata["has_exchange_position"] is False


@pytest.mark.asyncio
async def test_orphan_reduce_only_order_is_critical():
    service = _service(
        local_positions=[],
        exchange_positions=[],
        local_orders=[],
        exchange_orders=[_exchange_order("ex-orphan-tp")],
    )

    result = await service.build_read_model(SYMBOL)

    mismatch = next(
        item
        for item in result.mismatches
        if item.metadata.get("protection_reason_code") == PROTECTION_ORPHAN_REDUCE_ONLY_ORDER
    )
    assert mismatch.severity == "CRITICAL"
    assert mismatch.exchange_ref == "ex-orphan-tp"


@pytest.mark.asyncio
async def test_matching_position_and_exchange_native_sl_has_no_critical_protection_issue():
    service = _service(
        local_positions=[_position()],
        exchange_positions=[_position()],
        local_orders=[
            _order("local-sl", "ex-sl", OrderRole.SL),
            _order("local-tp", "ex-tp", OrderRole.TP1),
        ],
        exchange_orders=[_exchange_sl("ex-sl"), _exchange_order("ex-tp")],
    )

    result = await service.build_read_model(SYMBOL)

    assert not [
        item
        for item in result.mismatches
        if item.metadata.get("protection_reason_code")
    ]


@pytest.mark.asyncio
async def test_exchange_fetch_failure_returns_explainable_failure_result():
    service = _service(fail_open_orders=True)

    result = await service.build_read_model(SYMBOL)

    assert len(result.mismatches) == 1
    assert result.mismatches[0].mismatch_type == "exchange_state_fetch_failed"
    assert result.mismatches[0].severity == "SEVERE"
    assert "open orders unavailable" in result.mismatches[0].metadata["error"]
