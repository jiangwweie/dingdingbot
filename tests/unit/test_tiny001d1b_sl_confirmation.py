from __future__ import annotations

from decimal import Decimal

import ccxt
import pytest

from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.protection_health_monitor import PROTECTION_SL_NOT_CONFIRMED_ON_EXCHANGE
from src.domain.execution_intent import ExecutionIntent
from src.domain.models import (
    Direction,
    Order,
    OrderPlacementResult,
    OrderRole,
    OrderStatus,
    OrderStrategy,
    OrderType,
    SignalResult,
)
from src.infrastructure.exchange_gateway import ExchangeGateway


SYMBOL = "ETH/USDT:USDT"


class _Lifecycle:
    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}
        self.entry_partial_cb = None
        self.entry_filled_cb = None
        self.exit_progressed_cb = None
        self.rejected: list[tuple[str, str]] = []

    def set_entry_partially_filled_callback(self, callback):
        self.entry_partial_cb = callback

    def set_entry_filled_callback(self, callback):
        self.entry_filled_cb = callback

    def set_exit_progressed_callback(self, callback):
        self.exit_progressed_cb = callback

    async def register_created_order(self, order: Order, metadata=None):
        self.orders[order.id] = order

    async def submit_order(self, order_id: str, exchange_order_id: str):
        order = self.orders[order_id]
        order.exchange_order_id = exchange_order_id
        order.status = OrderStatus.SUBMITTED
        return order

    async def confirm_order(self, order_id: str):
        order = self.orders[order_id]
        order.status = OrderStatus.OPEN
        return order

    async def reject_order(self, order_id: str, reason: str):
        order = self.orders[order_id]
        order.status = OrderStatus.REJECTED
        self.rejected.append((order_id, reason))
        return order

    async def get_orders_by_signal(self, signal_id: str):
        return [order for order in self.orders.values() if order.signal_id == signal_id]


class _Gateway:
    def __init__(self, *, sl_confirmed: bool) -> None:
        self.sl_confirmed = sl_confirmed
        self.confirm_calls: list[dict] = []

    async def place_order(
        self,
        *,
        symbol,
        order_type,
        side,
        amount,
        price=None,
        trigger_price=None,
        reduce_only=False,
        client_order_id=None,
    ):
        role_id = "sl" if order_type == "stop_market" else "tp"
        return OrderPlacementResult(
            order_id=f"exchange-{role_id}",
            exchange_order_id=f"ex-{role_id}",
            symbol=symbol,
            order_type=OrderType.STOP_MARKET if order_type == "stop_market" else OrderType.LIMIT,
            direction=Direction.LONG,
            side=side,
            amount=amount,
            price=price,
            trigger_price=trigger_price,
            reduce_only=reduce_only,
            client_order_id=client_order_id,
            status=OrderStatus.OPEN,
        )

    async def confirm_order_exists(self, **kwargs):
        self.confirm_calls.append(kwargs)
        return self.sl_confirmed


def _entry_order() -> Order:
    return Order(
        id="entry",
        signal_id="sig-1",
        exchange_order_id="ex-entry",
        symbol=SYMBOL,
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.01"),
        filled_qty=Decimal("0.01"),
        average_exec_price=Decimal("2135"),
        status=OrderStatus.FILLED,
        created_at=1,
        updated_at=1,
    )


def _tp_order() -> Order:
    return Order(
        id="tp1",
        signal_id="sig-1",
        symbol=SYMBOL,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal("2156"),
        requested_qty=Decimal("0.005"),
        status=OrderStatus.CREATED,
        created_at=1,
        updated_at=1,
        reduce_only=True,
        parent_order_id="entry",
    )


def _sl_order() -> Order:
    return Order(
        id="sl1",
        signal_id="sig-1",
        symbol=SYMBOL,
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        trigger_price=Decimal("2114"),
        requested_qty=Decimal("0.01"),
        status=OrderStatus.CREATED,
        created_at=1,
        updated_at=1,
        reduce_only=True,
        parent_order_id="entry",
    )


def _intent() -> ExecutionIntent:
    signal = SignalResult(
        symbol=SYMBOL,
        timeframe="1h",
        direction=Direction.LONG,
        entry_price=Decimal("2135"),
        suggested_stop_loss=Decimal("2114"),
        suggested_position_size=Decimal("0.01"),
        current_leverage=1,
        risk_reward_info="test",
    )
    return ExecutionIntent(id="intent-1", signal_id="sig-1", signal=signal)


def _strategy() -> OrderStrategy:
    return OrderStrategy(
        id="strategy",
        name="test",
        tp_levels=1,
        tp_ratios=[Decimal("1")],
        tp_targets=[Decimal("1")],
        initial_stop_loss_rr=Decimal("-1"),
    )


@pytest.mark.asyncio
async def test_sl_confirmation_failure_fails_mount_and_blocks_symbol(monkeypatch):
    lifecycle = _Lifecycle()
    gateway = _Gateway(sl_confirmed=False)
    orchestrator = ExecutionOrchestrator(
        capital_protection=object(),
        order_lifecycle=lifecycle,
        gateway=gateway,
    )
    monkeypatch.setattr(
        "src.domain.order_manager.OrderManager._generate_tp_sl_orders",
        lambda self, filled_entry, positions_map, strategy, tp_targets=None: [_tp_order(), _sl_order()],
    )

    result = await orchestrator._mount_protection_orders(
        intent=_intent(),
        entry_order=_entry_order(),
        signal=_intent().signal,
        strategy=_strategy(),
    )

    assert result["success"] is False
    assert PROTECTION_SL_NOT_CONFIRMED_ON_EXCHANGE in result["error"]
    assert lifecycle.orders["sl1"].status == OrderStatus.REJECTED
    assert lifecycle.rejected == [("sl1", PROTECTION_SL_NOT_CONFIRMED_ON_EXCHANGE)]
    blocks = orchestrator.list_protection_health_blocks()
    assert blocks[SYMBOL]["reason_code"] == PROTECTION_SL_NOT_CONFIRMED_ON_EXCHANGE


@pytest.mark.asyncio
async def test_sl_confirmed_via_exchange_path_allows_mount(monkeypatch):
    lifecycle = _Lifecycle()
    gateway = _Gateway(sl_confirmed=True)
    orchestrator = ExecutionOrchestrator(
        capital_protection=object(),
        order_lifecycle=lifecycle,
        gateway=gateway,
    )
    monkeypatch.setattr(
        "src.domain.order_manager.OrderManager._generate_tp_sl_orders",
        lambda self, filled_entry, positions_map, strategy, tp_targets=None: [_tp_order(), _sl_order()],
    )

    result = await orchestrator._mount_protection_orders(
        intent=_intent(),
        entry_order=_entry_order(),
        signal=_intent().signal,
        strategy=_strategy(),
    )

    assert result["success"] is True
    assert result["sl_order"].id == "sl1"
    assert lifecycle.orders["sl1"].status == OrderStatus.OPEN
    assert gateway.confirm_calls[0]["exchange_order_id"] == "ex-sl"
    assert gateway.confirm_calls[0]["client_order_id"] == "sl1"
    assert orchestrator.list_protection_health_blocks() == {}


class _RestExchangeWithConditionalOpenOrders:
    def __init__(self) -> None:
        self.open_order_params: list[dict] = []

    async def fetch_order(self, exchange_order_id: str, symbol: str):
        raise RuntimeError("normal order endpoint cannot find conditional order")

    async def fetch_open_orders(self, symbol: str, params=None):
        params = params or {}
        self.open_order_params.append(params)
        if params.get("stop") is True:
            return [
                {
                    "id": "different-algo-id",
                    "clientOrderId": "sl-client-id",
                    "symbol": symbol,
                    "status": "open",
                    "info": {"algoId": "different-algo-id", "clientAlgoId": "sl-client-id"},
                }
            ]
        return []


class _RestExchangeFetchOrderConditionalFallback:
    def __init__(self) -> None:
        self.open_order_params: list[dict] = []

    async def fetch_order(self, exchange_order_id: str, symbol: str):
        raise ccxt.OrderNotFound("normal order endpoint cannot see conditional order")

    async def fetch_open_orders(self, symbol: str, params=None):
        params = params or {}
        self.open_order_params.append(params)
        if params.get("stop") is True:
            return [
                {
                    "id": "4000001555301974",
                    "clientOrderId": "sl-client-id",
                    "symbol": symbol,
                    "side": "sell",
                    "type": "market",
                    "status": "open",
                    "amount": "0.01",
                    "filled": "0",
                    "triggerPrice": "591.63",
                    "stopPrice": "591.63",
                    "reduceOnly": True,
                    "info": {
                        "algoId": "4000001555301974",
                        "clientAlgoId": "sl-client-id",
                        "orderType": "STOP_MARKET",
                        "side": "SELL",
                        "origQty": "0.01",
                        "executedQty": "0",
                        "triggerPrice": "591.63",
                        "stopPrice": "591.63",
                        "reduceOnly": True,
                    },
                }
            ]
        return []


@pytest.mark.asyncio
async def test_fetch_order_falls_back_to_conditional_open_stop_order():
    gateway = ExchangeGateway("binance", "key", "secret", testnet=True)
    rest = _RestExchangeFetchOrderConditionalFallback()
    gateway.rest_exchange = rest

    result = await gateway.fetch_order("4000001555301974", SYMBOL)

    assert result.exchange_order_id == "4000001555301974"
    assert result.status == OrderStatus.OPEN
    assert result.order_type == OrderType.STOP_MARKET
    assert result.side == "sell"
    assert result.reduce_only is True
    assert result.amount == Decimal("0.01")
    assert result.filled_qty == Decimal("0")
    assert result.trigger_price == Decimal("591.63")
    assert {"stop": True} in rest.open_order_params


@pytest.mark.asyncio
async def test_exchange_confirmation_matches_conditional_order_by_client_id():
    gateway = ExchangeGateway("binance", "key", "secret", testnet=True)
    rest = _RestExchangeWithConditionalOpenOrders()
    gateway.rest_exchange = rest
    gateway._order_confirmation_retry_delays = ()

    confirmed = await gateway.confirm_order_exists(
        exchange_order_id="unfetchable-id",
        symbol=SYMBOL,
        client_order_id="sl-client-id",
        order_type=OrderType.STOP_MARKET,
    )

    assert confirmed is True
    assert {"stop": True} in rest.open_order_params


class _RestExchangeWithDelayedConditionalOrder:
    def __init__(self) -> None:
        self.fetch_open_order_calls = 0

    async def fetch_order(self, exchange_order_id: str, symbol: str):
        raise RuntimeError("normal order endpoint cannot find conditional order yet")

    async def fetch_open_orders(self, symbol: str, params=None):
        self.fetch_open_order_calls += 1
        if self.fetch_open_order_calls < 2:
            return []
        return [
            {
                "id": "algo-1",
                "clientOrderId": "sl-client-id",
                "symbol": symbol,
                "side": "sell",
                "type": "STOP_MARKET",
                "status": "open",
                "info": {
                    "algoId": "algo-1",
                    "clientAlgoId": "sl-client-id",
                    "reduceOnly": True,
                    "stopPrice": "2114",
                },
            }
        ]


@pytest.mark.asyncio
async def test_exchange_confirmation_retries_bounded_open_order_fallback():
    gateway = ExchangeGateway("binance", "key", "secret", testnet=True)
    rest = _RestExchangeWithDelayedConditionalOrder()
    gateway.rest_exchange = rest
    gateway._order_confirmation_retry_delays = (0,)

    confirmed = await gateway.confirm_order_exists(
        exchange_order_id="unfetchable-id",
        symbol=SYMBOL,
        client_order_id="sl-client-id",
        order_type=OrderType.STOP_MARKET,
        side="sell",
        reduce_only=True,
        stop_price=Decimal("2114"),
        expected_type="STOP_MARKET",
    )

    assert confirmed is True
    assert rest.fetch_open_order_calls >= 2


class _RestExchangeShouldNotBeCalled:
    async def fetch_order(self, exchange_order_id: str, symbol: str):
        raise AssertionError("order-watch evidence should be checked before REST fetch_order")

    async def fetch_open_orders(self, symbol: str, params=None):
        raise AssertionError("order-watch evidence should be checked before REST fetch_open_orders")


@pytest.mark.asyncio
async def test_exchange_confirmation_accepts_recent_order_watch_evidence():
    gateway = ExchangeGateway("binance", "key", "secret", testnet=True)
    gateway.rest_exchange = _RestExchangeShouldNotBeCalled()
    await gateway._handle_order_update(
        {
            "id": "algo-1",
            "clientOrderId": "sl-client-id",
            "symbol": SYMBOL,
            "side": "sell",
            "type": "stop_market",
            "amount": "0.01",
            "filled": "0",
            "remaining": "0.01",
            "status": "open",
            "timestamp": 1,
            "reduceOnly": True,
            "info": {
                "algoId": "algo-1",
                "clientAlgoId": "sl-client-id",
                "reduceOnly": True,
                "stopPrice": "2114",
            },
        }
    )

    confirmed = await gateway.confirm_order_exists(
        exchange_order_id="unfetchable-id",
        symbol=SYMBOL,
        client_order_id="sl-client-id",
        order_type=OrderType.STOP_MARKET,
        side="sell",
        reduce_only=True,
        stop_price=Decimal("2114"),
        expected_type="STOP_MARKET",
    )

    assert confirmed is True


class _RestExchangeCancelConditionalFallback:
    def __init__(self) -> None:
        self.cancel_calls: list[tuple[str, str, dict | None]] = []
        self.fetch_open_order_params: list[dict] = []

    async def cancel_order(self, exchange_order_id: str, symbol: str, params=None):
        self.cancel_calls.append((exchange_order_id, symbol, params))
        if not params:
            raise ccxt.OrderNotFound("normal cancel cannot see conditional order")
        return {
            "id": exchange_order_id,
            "symbol": symbol,
            "status": None,
        }

    async def fetch_open_orders(self, symbol: str, params=None):
        params = params or {}
        self.fetch_open_order_params.append(params)
        if params.get("stop") is True:
            return [
                {
                    "id": "1000000085011119",
                    "symbol": symbol,
                    "side": "sell",
                    "type": "STOP_MARKET",
                    "status": "open",
                    "reduceOnly": True,
                    "info": {
                        "orderId": "1000000085011119",
                        "reduceOnly": True,
                        "stopPrice": "2085.38",
                    },
                }
            ]
        return []


@pytest.mark.asyncio
async def test_cancel_order_falls_back_to_conditional_stop_order_cancel():
    gateway = ExchangeGateway("binance", "key", "secret", testnet=True)
    rest = _RestExchangeCancelConditionalFallback()
    gateway.rest_exchange = rest

    result = await gateway.cancel_order("1000000085011119", SYMBOL)

    assert result.status == OrderStatus.CANCELED
    assert {"stop": True} in rest.fetch_open_order_params
    assert rest.cancel_calls == [
        ("1000000085011119", SYMBOL, None),
        ("1000000085011119", SYMBOL, {"stop": True}),
    ]
