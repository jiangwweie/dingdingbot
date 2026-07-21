from __future__ import annotations

from decimal import Decimal

import ccxt
import pytest

from src.domain.models import OrderStatus, OrderType
from src.domain.exceptions import InvalidOrderError
from src.domain.ticket_bound_exchange_command import ExchangeOrderLookupRequest
from src.infrastructure.exchange_gateway import ExchangeGateway


SYMBOL = "ETH/USDT:USDT"


class _CreateOrderRecorder:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create_order(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {"id": "exchange-order-1", "status": "open", "filled": "0"}


@pytest.mark.asyncio
async def test_limit_gtc_and_passive_gtx_send_explicit_ccxt_tif_contracts():
    rest = _CreateOrderRecorder()
    gateway = _gateway(rest)

    await gateway.place_order(
        symbol=SYMBOL,
        order_type="limit",
        side="sell",
        amount=Decimal("0.25"),
        price=Decimal("2100"),
        reduce_only=True,
        time_in_force="GTC",
        post_only=False,
    )
    await gateway.place_order(
        symbol=SYMBOL,
        order_type="limit",
        side="sell",
        amount=Decimal("0.25"),
        price=Decimal("2100"),
        reduce_only=True,
        time_in_force="GTX",
        post_only=True,
    )

    assert rest.calls[0]["params"]["timeInForce"] == "GTC"
    assert "postOnly" not in rest.calls[0]["params"]
    assert rest.calls[1]["params"]["timeInForce"] == "GTX"
    assert rest.calls[1]["params"]["postOnly"] is True
    assert all(call["type"] == "limit" for call in rest.calls)


@pytest.mark.asyncio
async def test_market_gtx_and_unsupported_post_only_fail_before_exchange_write():
    rest = _CreateOrderRecorder()
    gateway = _gateway(rest)

    with pytest.raises(InvalidOrderError):
        await gateway.place_order(
            symbol=SYMBOL,
            order_type="market",
            side="sell",
            amount=Decimal("0.25"),
            reduce_only=True,
            time_in_force="GTX",
            post_only=True,
        )
    unsupported = _gateway(rest, exchange_name="kraken")
    with pytest.raises(InvalidOrderError):
        await unsupported.place_order(
            symbol=SYMBOL,
            order_type="limit",
            side="sell",
            amount=Decimal("0.25"),
            price=Decimal("2100"),
            reduce_only=True,
            time_in_force="GTX",
            post_only=True,
        )

    assert rest.calls == []


def _gateway(rest_exchange, *, exchange_name: str = "binance") -> ExchangeGateway:
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.exchange_name = exchange_name
    gateway.rest_exchange = rest_exchange
    gateway._order_confirmation_retry_delays = ()
    gateway._recent_order_updates = {}
    gateway._recent_order_updates_by_symbol = {}
    return gateway


class _TwoOpenOrderViews:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def fetch_open_orders(self, symbol: str, params=None):
        normalized_params = dict(params or {})
        self.calls.append((symbol, normalized_params))
        if normalized_params == {}:
            return [
                {
                    "id": "normal-order-id",
                    "clientOrderId": "normal-client-id",
                    "symbol": symbol,
                    "status": "open",
                    "info": {"orderId": "normal-order-id"},
                },
                {
                    "id": "normal-visible-stop-id",
                    "clientOrderId": "shared-stop-client-id",
                    "symbol": symbol,
                    "type": "market",
                    "status": "open",
                    "info": {"orderId": "normal-visible-stop-id"},
                },
            ]
        if normalized_params == {"stop": True}:
            return [
                {
                    "id": "algo-visible-stop-id",
                    "clientOrderId": "shared-stop-client-id",
                    "symbol": symbol,
                    "type": "STOP_MARKET",
                    "status": "open",
                    "stopPrice": "1900",
                    "fees": [],
                    "info": {
                        "algoId": "algo-visible-stop-id",
                        "clientAlgoId": "shared-stop-client-id",
                        "orderType": "STOP_MARKET",
                        "stopPrice": "1900",
                    },
                },
                {
                    "id": "stop-only-id",
                    "clientOrderId": "stop-only-client-id",
                    "symbol": symbol,
                    "type": "STOP_MARKET",
                    "status": "open",
                    "stopPrice": "1800",
                    "info": {"algoId": "stop-only-id"},
                },
            ]
        raise AssertionError(f"unexpected open-order params: {normalized_params}")


@pytest.mark.asyncio
async def test_fetch_all_open_orders_merges_binance_normal_and_stop_views():
    rest = _TwoOpenOrderViews()
    gateway = _gateway(rest)

    orders = await gateway.fetch_all_open_orders(SYMBOL)

    assert rest.calls == [
        (SYMBOL, {}),
        (SYMBOL, {"stop": True}),
    ]
    assert [order["id"] for order in orders] == [
        "normal-order-id",
        "algo-visible-stop-id",
        "stop-only-id",
    ]
    merged_stop = orders[1]
    assert merged_stop["type"] == "STOP_MARKET"
    assert merged_stop["stopPrice"] == "1900"
    assert merged_stop["fees"] == []
    assert merged_stop["info"]["orderId"] == "normal-visible-stop-id"
    assert merged_stop["info"]["algoId"] == "algo-visible-stop-id"


class _SameExchangeIdAcrossViews:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def fetch_open_orders(self, symbol: str, params=None):
        normalized_params = dict(params or {})
        self.calls.append(normalized_params)
        if normalized_params == {}:
            return [{"id": "same-id", "symbol": symbol, "status": "open"}]
        if normalized_params == {"stop": True}:
            return [
                {
                    "id": "same-id",
                    "clientOrderId": "same-client-id",
                    "symbol": symbol,
                    "status": "open",
                    "stopPrice": "1900",
                }
            ]
        raise AssertionError(f"unexpected open-order params: {normalized_params}")


@pytest.mark.asyncio
async def test_fetch_all_open_orders_deduplicates_by_exchange_order_id():
    rest = _SameExchangeIdAcrossViews()
    gateway = _gateway(rest)

    orders = await gateway.fetch_all_open_orders(SYMBOL)

    assert len(orders) == 1
    assert orders[0]["id"] == "same-id"
    assert orders[0]["clientOrderId"] == "same-client-id"
    assert orders[0]["stopPrice"] == "1900"


class _FailingRequiredView:
    def __init__(self, failing_params: dict) -> None:
        self.failing_params = failing_params
        self.calls: list[dict] = []

    async def fetch_open_orders(self, symbol: str, params=None):
        normalized_params = dict(params or {})
        self.calls.append(normalized_params)
        if normalized_params == self.failing_params:
            raise RuntimeError(f"required view failed: {normalized_params}")
        return [{"id": "visible-order", "symbol": symbol, "status": "open"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_params", [{}, {"stop": True}])
async def test_fetch_all_open_orders_propagates_any_required_view_failure(
    failing_params: dict,
):
    gateway = _gateway(_FailingRequiredView(failing_params))

    with pytest.raises(RuntimeError, match="required view failed"):
        await gateway.fetch_all_open_orders(SYMBOL)


@pytest.mark.asyncio
async def test_fetch_all_open_orders_keeps_non_binance_normal_view_compatibility():
    rest = _FailingRequiredView({"stop": True})
    gateway = _gateway(rest, exchange_name="okx")

    orders = await gateway.fetch_all_open_orders(SYMBOL)

    assert [order["id"] for order in orders] == ["visible-order"]
    assert rest.calls == [{}]


class _ConditionalFallbackRest(_TwoOpenOrderViews):
    def __init__(self) -> None:
        super().__init__()
        self.cancel_calls: list[tuple[str, str, dict]] = []

    async def fetch_order(self, exchange_order_id: str, symbol: str):
        raise ccxt.OrderNotFound("regular order view cannot see algo order")

    async def cancel_order(self, exchange_order_id: str, symbol: str, params=None):
        normalized_params = dict(params or {})
        self.cancel_calls.append((exchange_order_id, symbol, normalized_params))
        if not normalized_params:
            raise ccxt.OrderNotFound("regular cancel cannot see algo order")
        return {
            "id": exchange_order_id,
            "symbol": symbol,
            "status": "canceled",
        }


@pytest.mark.asyncio
async def test_fetch_order_conditional_fallback_reuses_complete_open_order_read():
    rest = _ConditionalFallbackRest()
    gateway = _gateway(rest)

    result = await gateway.fetch_order("algo-visible-stop-id", SYMBOL)

    assert result.exchange_order_id == "algo-visible-stop-id"
    assert result.order_type == OrderType.STOP_MARKET
    assert rest.calls == [
        (SYMBOL, {}),
        (SYMBOL, {"stop": True}),
    ]


@pytest.mark.asyncio
async def test_order_confirmation_reuses_complete_open_order_read():
    rest = _ConditionalFallbackRest()
    gateway = _gateway(rest)

    confirmed = await gateway.confirm_order_exists(
        exchange_order_id="not-visible-to-fetch-order",
        client_order_id="shared-stop-client-id",
        symbol=SYMBOL,
        order_type=OrderType.STOP_MARKET,
        side=None,
        reduce_only=None,
        stop_price=Decimal("1900"),
        expected_type="STOP_MARKET",
    )

    assert confirmed is True
    assert rest.calls == [
        (SYMBOL, {}),
        (SYMBOL, {"stop": True}),
    ]


@pytest.mark.asyncio
async def test_cancel_conditional_fallback_reuses_complete_open_order_read():
    rest = _ConditionalFallbackRest()
    gateway = _gateway(rest)

    result = await gateway.cancel_order("algo-visible-stop-id", SYMBOL)

    assert result.status == OrderStatus.CANCELED
    assert rest.calls == [
        (SYMBOL, {}),
        (SYMBOL, {"stop": True}),
    ]
    assert rest.cancel_calls == [
        ("algo-visible-stop-id", SYMBOL, {}),
        ("algo-visible-stop-id", SYMBOL, {"stop": True}),
    ]


class _RegularLookupRest:
    def __init__(self, *, executed_qty: str, average_exec_price: str | None):
        self.executed_qty = executed_qty
        self.average_exec_price = average_exec_price

    async def fetch_order(self, _order_id, symbol, params=None):
        client_order_id = str((params or {}).get("origClientOrderId") or "")
        return {
            "id": "exchange-entry-lookup",
            "clientOrderId": client_order_id,
            "symbol": symbol,
            "status": "open",
            "filled": self.executed_qty,
            "average": self.average_exec_price,
            "info": {
                "orderId": "exchange-entry-lookup",
                "origClientOrderId": client_order_id,
                "symbol": "ETHUSDT",
                "executedQty": self.executed_qty,
                "avgPrice": self.average_exec_price,
            },
        }


def _entry_lookup_request() -> ExchangeOrderLookupRequest:
    return ExchangeOrderLookupRequest(
        exchange_id="binance_usdm",
        gateway_symbol=SYMBOL,
        command_kind="place_order",
        order_role="ENTRY",
        order_type="market",
        client_order_id="entry-lookup-client",
    )


@pytest.mark.asyncio
async def test_regular_lookup_normalizes_zero_fill_zero_average_to_no_fill_price():
    gateway = _gateway(
        _RegularLookupRest(
            executed_qty="0",
            average_exec_price="0.00000",
        )
    )

    result = await gateway.find_order_by_client_id(
        _entry_lookup_request(),
        observed_at_ms=1_720_000_000_000,
    )

    assert result.executed_qty == Decimal("0")
    assert result.average_exec_price is None


@pytest.mark.asyncio
@pytest.mark.parametrize("average_exec_price", ["0.00000", None])
async def test_regular_lookup_positive_fill_without_positive_average_fails_closed(
    average_exec_price,
):
    gateway = _gateway(
        _RegularLookupRest(
            executed_qty="0.01",
            average_exec_price=average_exec_price,
        )
    )

    with pytest.raises(ValueError):
        await gateway.find_order_by_client_id(
            _entry_lookup_request(),
            observed_at_ms=1_720_000_000_000,
        )
