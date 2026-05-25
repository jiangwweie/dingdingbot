from __future__ import annotations

from decimal import Decimal

from src.infrastructure.exchange_gateway import ExchangeGateway


class _RestExchange:
    def __init__(self, market):
        self.markets = {"BTC/USDT:USDT": market}

    def market(self, symbol):
        return self.markets[symbol]


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
