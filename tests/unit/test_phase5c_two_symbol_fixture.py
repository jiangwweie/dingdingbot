from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.application.readmodels.runtime_execution_intents import (
    RuntimeExecutionIntentsReadModel,
)
from src.application.readmodels.runtime_orders import RuntimeOrdersReadModel
from src.application.readmodels.runtime_portfolio import RuntimePortfolioReadModel
from src.application.readmodels.runtime_positions import RuntimePositionsReadModel
from src.application.reconciliation import ReconciliationService
from src.application.runtime_symbol_isolation_audit import (
    SymbolIsolationStatus,
    build_phase5c_symbol_isolation_audit,
)
from src.domain.execution_intent import ExecutionIntentStatus
from src.domain.models import (
    Direction,
    Order,
    OrderRole,
    OrderStatus,
    OrderType,
    PositionInfo,
)


ETH = "ETH/USDT:USDT"
BTC = "BTC/USDT:USDT"


class _Gateway:
    def __init__(self, *, positions=None, open_orders=None) -> None:
        self.positions = positions or []
        self.open_orders = open_orders or []
        self.position_symbols: list[str] = []
        self.open_order_symbols: list[str] = []

    async def fetch_positions(self, symbol: str):
        self.position_symbols.append(symbol)
        return [position for position in self.positions if position.symbol == symbol]

    async def fetch_open_orders(self, symbol: str, params=None):
        self.open_order_symbols.append(symbol)
        return [order for order in self.open_orders if order.get("symbol") == symbol]

    def get_account_snapshot(self):
        return None


class _PositionSource:
    def __init__(self, positions=None) -> None:
        self.positions = positions or []
        self.list_symbols: list[str | None] = []

    async def list_active(self, *, symbol: str | None = None, limit: int = 100):
        self.list_symbols.append(symbol)
        return [
            position
            for position in self.positions
            if symbol is None or position.symbol == symbol
        ][:limit]


class _OrderRepository:
    def __init__(self, orders=None) -> None:
        self.orders = orders or []
        self.symbol_calls: list[str | None] = []

    async def get_open_orders(self, symbol: str | None = None):
        self.symbol_calls.append(symbol)
        return [
            order
            for order in self.orders
            if (symbol is None or order.symbol == symbol)
            and order.status in {OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}
        ]

    async def get_orders_by_status(self, status: OrderStatus, symbol: str | None = None):
        self.symbol_calls.append(symbol)
        return [
            order
            for order in self.orders
            if order.status == status and (symbol is None or order.symbol == symbol)
        ]

    async def get_orders_by_symbol(self, symbol: str):
        self.symbol_calls.append(symbol)
        return [order for order in self.orders if order.symbol == symbol]


class _IntentRepository:
    def __init__(self, intents=None) -> None:
        self.intents = intents or []

    async def list_unfinished(self):
        return self.intents

    async def list(self, status=None):
        return [
            intent
            for intent in self.intents
            if status is None or intent.status == status
        ]


def _position_info(symbol: str, *, size: str = "1") -> PositionInfo:
    return PositionInfo(
        symbol=symbol,
        side="long",
        size=Decimal(size),
        entry_price=Decimal("100"),
        mark_price=Decimal("110"),
        unrealized_pnl=Decimal("10"),
        leverage=1,
        liquidation_price=Decimal("50"),
    )


def _stored_position(symbol: str, position_id: str):
    return SimpleNamespace(
        id=position_id,
        signal_id=f"sig-{position_id}",
        symbol=symbol,
        direction=Direction.LONG,
        entry_price=Decimal("100"),
        current_qty=Decimal("1"),
        watermark_price=Decimal("110"),
        unrealized_pnl=Decimal("10"),
        leverage=1,
        updated_at=1,
    )


def _order(symbol: str, order_id: str, exchange_order_id: str, role: OrderRole) -> Order:
    return Order(
        id=order_id,
        signal_id=f"sig-{order_id}",
        exchange_order_id=exchange_order_id,
        symbol=symbol,
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET if role == OrderRole.SL else OrderType.LIMIT,
        order_role=role,
        requested_qty=Decimal("1"),
        filled_qty=Decimal("0"),
        status=OrderStatus.OPEN,
        created_at=1,
        updated_at=1,
        reduce_only=role != OrderRole.ENTRY,
    )


def _exchange_order(symbol: str, order_id: str, *, stop: bool = False):
    return {
        "id": order_id,
        "symbol": symbol,
        "status": "open",
        "type": "stop" if stop else "limit",
        "side": "sell",
        "amount": "1",
        "filled": "0",
        "price": "120",
        "reduceOnly": True,
        "timestamp": 1,
        **({"triggerPrice": "90"} if stop else {}),
    }


def _intent(symbol: str, intent_id: str, status=ExecutionIntentStatus.PENDING):
    return SimpleNamespace(
        id=intent_id,
        symbol=symbol,
        signal_payload={
            "symbol": symbol,
            "direction": "LONG",
            "suggested_position_size": "1",
        },
        status=status,
        signal_id=f"sig-{intent_id}",
        created_at=1,
        updated_at=1,
    )


@pytest.mark.asyncio
async def test_reconciliation_build_read_model_keeps_btc_mismatches_out_of_eth_result():
    gateway = _Gateway(
        positions=[
            _position_info(ETH),
            _position_info(BTC),
        ],
        open_orders=[
            _exchange_order(ETH, "eth-sl", stop=True),
            _exchange_order(ETH, "eth-tp"),
            _exchange_order(BTC, "btc-orphan"),
        ],
    )
    service = ReconciliationService(
        gateway=gateway,
        position_mgr=_PositionSource([_position_info(ETH), _position_info(BTC)]),
        order_repository=_OrderRepository(
            [
                _order(ETH, "local-eth-sl", "eth-sl", OrderRole.SL),
                _order(ETH, "local-eth-tp", "eth-tp", OrderRole.TP1),
            ]
        ),
    )

    eth_result = await service.build_read_model(ETH)
    btc_result = await service.build_read_model(BTC)

    assert eth_result.is_consistent
    assert eth_result.mismatches == []
    assert all(symbol == ETH for symbol in gateway.position_symbols[:1])
    assert all(mismatch.symbol == BTC for mismatch in btc_result.mismatches)
    assert any(
        mismatch.mismatch_type == "local_order_missing_on_exchange"
        or mismatch.mismatch_type == "exchange_order_missing_locally"
        for mismatch in btc_result.mismatches
    )


@pytest.mark.asyncio
async def test_runtime_readmodels_filter_orders_intents_and_positions_by_symbol():
    orders = [_order(ETH, "eth-order", "ex-eth", OrderRole.ENTRY), _order(BTC, "btc-order", "ex-btc", OrderRole.ENTRY)]
    order_repo = _OrderRepository(orders)
    order_response = await RuntimeOrdersReadModel().build(
        order_repo=order_repo,
        symbol=ETH,
    )

    intent_response = await RuntimeExecutionIntentsReadModel().build(
        intent_repo=_IntentRepository([_intent(ETH, "eth-intent"), _intent(BTC, "btc-intent")]),
        symbol=ETH,
    )

    position_response = await RuntimePositionsReadModel().build(
        account_snapshot=None,
        position_repo=_PositionSource([
            _stored_position(ETH, "eth-position"),
            _stored_position(BTC, "btc-position"),
        ]),
        symbol=ETH,
    )

    assert [order.symbol for order in order_response.orders] == [ETH]
    assert [order.side for order in order_response.orders] == ["BUY"]
    assert [intent.symbol for intent in intent_response.intents] == [ETH]
    assert [intent.side for intent in intent_response.intents] == ["BUY"]
    assert [position.symbol for position in position_response.positions] == [ETH]
    assert order_repo.symbol_calls == [ETH]


@pytest.mark.asyncio
async def test_runtime_positions_do_not_resurrect_snapshot_only_position_when_pg_is_flat():
    stale_snapshot = SimpleNamespace(
        positions=[_position_info(BTC, size="0.002")],
    )

    response = await RuntimePositionsReadModel().build(
        account_snapshot=stale_snapshot,
        position_repo=_PositionSource([]),
        symbol=BTC,
    )

    assert response.positions == []


@pytest.mark.asyncio
async def test_runtime_portfolio_remains_account_level_for_two_symbols():
    account_snapshot = SimpleNamespace(
        total_balance=Decimal("1000"),
        available_balance=Decimal("900"),
        unrealized_pnl=Decimal("15"),
        positions=[_position_info(ETH), _position_info(BTC)],
    )

    response = await RuntimePortfolioReadModel().build(
        runtime_config_provider=None,
        capital_protection=None,
        account_snapshot=account_snapshot,
    )

    assert {position.symbol for position in response.positions} == {ETH, BTC}
    assert response.total_exposure == 200.0
    assert response.total_equity == 1015.0


def test_phase5c_symbol_isolation_audit_marks_synthetic_proof_passed():
    report = build_phase5c_symbol_isolation_audit()
    statuses = {check.check_id: check.status for check in report.checks}

    assert report.audit_version == "phase5c_two_symbol_fixture_audit_v1"
    assert statuses["P5C-SYM-003"] == SymbolIsolationStatus.PASS
    assert statuses["P5C-SYM-004"] == SymbolIsolationStatus.PASS
    assert statuses["P5C-SYM-005"] == SymbolIsolationStatus.BLOCKED
    assert report.verdict == (
        "two_symbol_synthetic_fixture_passed / "
        "multi_symbol_runtime_still_blocked"
    )
