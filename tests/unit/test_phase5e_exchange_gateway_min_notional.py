from __future__ import annotations

from decimal import Decimal

import pytest

from src.infrastructure.exchange_gateway import ExchangeGateway
from src.domain.exceptions import ConnectionLostError


class _RestExchange:
    def __init__(self, market):
        self.markets = {"BTC/USDT:USDT": market}
        self.fetch_my_trades_calls = []

    def market(self, symbol):
        return self.markets[symbol]

    async def fetch_my_trades(self, symbol, *, limit=50, params=None):
        self.fetch_my_trades_calls.append(
            {"symbol": symbol, "limit": limit, "params": params or {}}
        )
        return [{"id": "trade-1", "symbol": symbol}]


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
