from __future__ import annotations

from decimal import Decimal

import ccxt
import pytest

from src.domain.ticket_bound_exchange_command import (
    ExchangeOrderLookupRequest,
    ExchangeOrderLookupStatus,
    ExchangeOrderLookupView,
)
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.domain.exceptions import ConnectionLostError, InvalidOrderError


class _RestExchange:
    def __init__(self, market):
        self.markets = {"BTC/USDT:USDT": market}
        self.fetch_my_trades_calls = []
        self.income_calls = []

    def market(self, symbol):
        return self.markets[symbol]

    async def fetch_my_trades(self, symbol, *, limit=50, params=None):
        self.fetch_my_trades_calls.append(
            {"symbol": symbol, "limit": limit, "params": params or {}}
        )
        return [{"id": "trade-1", "symbol": symbol}]

    async def fapiPrivateGetIncome(self, params):
        self.income_calls.append(dict(params))
        return [
            {
                "tranId": "income-1",
                "symbol": params["symbol"],
                "incomeType": "FUNDING_FEE",
                "income": "-0.12",
                "asset": "USDT",
                "time": params["startTime"] + 1,
            }
        ]


def _gateway_with_market(market):
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.rest_exchange = _RestExchange(market)
    return gateway


def test_get_min_notional_reads_limits_cost_min():
    gateway = _gateway_with_market({"limits": {"cost": {"min": "100"}}})

    assert gateway.get_min_notional("BTC/USDT:USDT") == Decimal("100")


def test_get_min_notional_reads_binance_min_notional_filter():
    gateway = _gateway_with_market(
        {
            "limits": {},
            "info": {
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                    {"filterType": "MIN_NOTIONAL", "notional": "100"},
                ]
            },
        }
    )

    assert gateway.get_min_notional("BTC/USDT:USDT") == Decimal("100")


def test_get_min_notional_reads_binance_notional_filter_min_notional():
    gateway = _gateway_with_market(
        {
            "limits": {},
            "info": {
                "filters": [
                    {"filterType": "NOTIONAL", "minNotional": "120"},
                ]
            },
        }
    )

    assert gateway.get_min_notional("BTC/USDT:USDT") == Decimal("120")


def test_get_min_notional_returns_none_when_markets_not_loaded():
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.rest_exchange = type("Rest", (), {"markets": None})()

    assert gateway.get_min_notional("BTC/USDT:USDT") is None


@pytest.mark.asyncio
async def test_fetch_my_trades_wrapper_calls_rest_exchange():
    rest = _RestExchange({"limits": {"cost": {"min": "100"}}})
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.rest_exchange = rest

    trades = await gateway.fetch_my_trades("BTC/USDT:USDT", limit=20)

    assert trades == [{"id": "trade-1", "symbol": "BTC/USDT:USDT"}]
    assert rest.fetch_my_trades_calls == [
        {"symbol": "BTC/USDT:USDT", "limit": 20, "params": {}}
    ]


@pytest.mark.asyncio
async def test_fetch_funding_income_uses_exact_binance_market_and_time_window():
    rest = _RestExchange(
        {"id": "BTCUSDT", "limits": {"cost": {"min": "100"}}}
    )
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.exchange_name = "binance"
    gateway.rest_exchange = rest

    rows = await gateway.fetch_funding_income(
        "BTC/USDT:USDT",
        start_time_ms=1000,
        end_time_ms=2000,
    )

    assert rows[0]["income"] == "-0.12"
    assert rest.income_calls == [
        {
            "symbol": "BTCUSDT",
            "incomeType": "FUNDING_FEE",
            "startTime": 1000,
            "endTime": 2000,
            "limit": 1000,
        }
    ]


@pytest.mark.asyncio
async def test_unclassified_create_order_exception_is_ambiguous_not_rejected():
    class _AmbiguousRest:
        async def create_order(self, **_kwargs):
            raise RuntimeError("connection closed after request write")

    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.exchange_name = "binance"
    gateway.rest_exchange = _AmbiguousRest()

    with pytest.raises(ConnectionLostError) as exc:
        await gateway.place_order(
            symbol="BTC/USDT:USDT",
            order_type="market",
            side="buy",
            amount=Decimal("0.001"),
            client_order_id="brc-test-ambiguous",
        )

    assert exc.value.error_code == "C-002"


@pytest.mark.asyncio
def _lookup_request(
    *,
    order_role: str,
    order_type: str,
    client_order_id: str,
) -> ExchangeOrderLookupRequest:
    return ExchangeOrderLookupRequest(
        exchange_id="binance_usdm",
        gateway_symbol="ETH/USDT:USDT",
        command_kind="place_order",
        order_role=order_role,
        order_type=order_type,
        client_order_id=client_order_id,
    )


@pytest.mark.asyncio
async def test_binance_conditional_client_lookup_uses_algo_order_endpoint():
    class _LookupRest:
        def __init__(self) -> None:
            self.algo_calls = []
            self.fetch_order_calls = []

        async def fapiPrivateGetAlgoOrder(self, params):
            self.algo_calls.append(dict(params))
            return {
                "algoId": "algo-1",
                "clientAlgoId": "brc-client-sl",
                "symbol": "ETHUSDT",
                "algoStatus": "NEW",
            }

        async def fetch_order(self, order_id, symbol, *, params):
            self.fetch_order_calls.append((order_id, symbol, params))
            raise AssertionError("conditional lookup must not use regular order view")

    rest = _LookupRest()
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.exchange_name = "binance"
    gateway.rest_exchange = rest

    result = await gateway.find_order_by_client_id(
        _lookup_request(
            order_role="SL",
            order_type="stop_market",
            client_order_id="brc-client-sl",
        ),
        observed_at_ms=10_000,
    )

    assert rest.algo_calls == [{"clientAlgoId": "brc-client-sl"}]
    assert rest.fetch_order_calls == []
    assert result.status == ExchangeOrderLookupStatus.FOUND
    assert result.lookup_view == ExchangeOrderLookupView.CONDITIONAL_ALGO_ORDER
    assert result.identity_kind == "clientAlgoId"
    assert result.exchange_order_id == "algo-1"
    assert result.gateway_symbol == "ETH/USDT:USDT"


@pytest.mark.asyncio
async def test_binance_regular_client_lookup_does_not_call_algo_endpoint():
    class _LookupRest:
        def __init__(self) -> None:
            self.algo_calls = []
            self.fetch_order_calls = []

        async def fapiPrivateGetAlgoOrder(self, params):
            self.algo_calls.append(dict(params))
            raise AssertionError("regular lookup must not use algo order view")

        async def fetch_order(self, order_id, symbol, *, params):
            self.fetch_order_calls.append((order_id, symbol, params))
            return {
                "id": "exchange-1",
                "symbol": symbol,
                "clientOrderId": "brc-client-1",
                "status": "open",
                "info": {},
            }

    rest = _LookupRest()
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.exchange_name = "binance"
    gateway.rest_exchange = rest

    result = await gateway.find_order_by_client_id(
        _lookup_request(
            order_role="ENTRY",
            order_type="market",
            client_order_id="brc-client-1",
        ),
        observed_at_ms=10_000,
    )

    assert rest.fetch_order_calls == [
        (
            None,
            "ETH/USDT:USDT",
            {"origClientOrderId": "brc-client-1"},
        )
    ]
    assert rest.algo_calls == []
    assert result.status == ExchangeOrderLookupStatus.FOUND
    assert result.lookup_view == ExchangeOrderLookupView.REGULAR_ORDER
    assert result.identity_kind == "origClientOrderId"
    assert result.exchange_order_id == "exchange-1"
    assert result.client_order_id == "brc-client-1"


@pytest.mark.asyncio
async def test_non_binance_lookup_preserves_regular_client_order_identity():
    class _LookupRest:
        def __init__(self) -> None:
            self.calls = []

        async def fetch_order(self, order_id, symbol, *, params):
            self.calls.append((order_id, symbol, params))
            return {
                "id": "exchange-1",
                "symbol": symbol,
                "clientOrderId": "brc-client-okx",
                "status": "open",
            }

    rest = _LookupRest()
    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.exchange_name = "okx"
    gateway.rest_exchange = rest
    request = ExchangeOrderLookupRequest(
        exchange_id="okx_swap",
        gateway_symbol="ETH/USDT:USDT",
        command_kind="place_order",
        order_role="SL",
        order_type="stop_market",
        client_order_id="brc-client-okx",
    )

    result = await gateway.find_order_by_client_id(request, observed_at_ms=10_000)

    assert rest.calls == [
        (None, "ETH/USDT:USDT", {"clientOrderId": "brc-client-okx"})
    ]
    assert result.lookup_view == ExchangeOrderLookupView.REGULAR_ORDER
    assert result.identity_kind == "clientOrderId"


@pytest.mark.asyncio
async def test_unsupported_binance_role_type_never_falls_back_to_regular_view():
    class _LookupRest:
        async def fetch_order(self, *_args, **_kwargs):
            raise AssertionError("unsupported lookup must fail before venue read")

        async def fapiPrivateGetAlgoOrder(self, _params):
            raise AssertionError("unsupported lookup must fail before venue read")

    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.exchange_name = "binance"
    gateway.rest_exchange = _LookupRest()

    with pytest.raises(InvalidOrderError, match="unsupported Binance"):
        await gateway.find_order_by_client_id(
            _lookup_request(
                order_role="SL",
                order_type="limit",
                client_order_id="brc-client-unsupported",
            ),
            observed_at_ms=10_000,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("order_role", "order_type", "expected_view", "expected_identity"),
    [
        ("ENTRY", "market", "regular_order", "origClientOrderId"),
        ("SL", "stop_market", "conditional_algo_order", "clientAlgoId"),
    ],
)
async def test_required_view_not_found_returns_typed_evidence(
    order_role: str,
    order_type: str,
    expected_view: str,
    expected_identity: str,
):
    class _LookupRest:
        async def fetch_order(self, _order_id, _symbol, *, params):
            raise ccxt.OrderNotFound(f"regular missing: {params}")

        async def fapiPrivateGetAlgoOrder(self, params):
            raise ccxt.OrderNotFound(f"conditional missing: {params}")

    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.exchange_name = "binance"
    gateway.rest_exchange = _LookupRest()

    result = await gateway.find_order_by_client_id(
        _lookup_request(
            order_role=order_role,
            order_type=order_type,
            client_order_id="brc-client-missing",
        ),
        observed_at_ms=10_000,
    )

    assert result.status == ExchangeOrderLookupStatus.NOT_FOUND
    assert result.lookup_view.value == expected_view
    assert result.identity_kind == expected_identity
    assert result.exchange_order_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("order_role", "order_type"),
    [("ENTRY", "market"), ("SL", "stop_market")],
)
async def test_required_view_malformed_response_never_becomes_not_found(
    order_role: str,
    order_type: str,
):
    class _LookupRest:
        async def fetch_order(self, _order_id, _symbol, *, params):
            return [params]

        async def fapiPrivateGetAlgoOrder(self, params):
            return [params]

    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.exchange_name = "binance"
    gateway.rest_exchange = _LookupRest()

    with pytest.raises(ConnectionLostError, match="non-structured"):
        await gateway.find_order_by_client_id(
            _lookup_request(
                order_role=order_role,
                order_type=order_type,
                client_order_id="brc-client-malformed",
            ),
            observed_at_ms=10_000,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("order_role", "order_type", "payload", "wrong_gateway_symbol"),
    [
        (
            "ENTRY",
            "market",
            {
                "id": "regular-1",
                "clientOrderId": "unexpected-client",
                "symbol": "BTC/USDT:USDT",
                "status": "open",
                "info": {},
            },
            "BTC/USDT:USDT",
        ),
        (
            "SL",
            "stop_market",
            {
                "algoId": "algo-1",
                "clientAlgoId": "unexpected-client",
                "symbol": "BTCUSDT",
                "algoStatus": "NEW",
            },
            "BTCUSDT",
        ),
    ],
)
async def test_required_view_preserves_wrong_returned_identity_for_hard_stop(
    order_role: str,
    order_type: str,
    payload: dict,
    wrong_gateway_symbol: str,
):
    class _LookupRest:
        async def fetch_order(self, _order_id, _symbol, *, params):
            return payload

        async def fapiPrivateGetAlgoOrder(self, params):
            return payload

    gateway = ExchangeGateway.__new__(ExchangeGateway)
    gateway.exchange_name = "binance"
    gateway.rest_exchange = _LookupRest()

    result = await gateway.find_order_by_client_id(
        _lookup_request(
            order_role=order_role,
            order_type=order_type,
            client_order_id="brc-client-expected",
        ),
        observed_at_ms=10_000,
    )

    assert result.status == ExchangeOrderLookupStatus.FOUND
    assert result.client_order_id == "unexpected-client"
    assert result.gateway_symbol == wrong_gateway_symbol
