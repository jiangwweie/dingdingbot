"""Raw USD-M user trades pass through the installed CCXT parser before the kernel."""

from copy import deepcopy
from decimal import Decimal

import ccxt
import pytest

from src.trading_kernel.application.runtime_facts import CompleteEntryFillsRequest
from src.trading_kernel.domain.commands import ExchangeCommandKind
from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.order_attribution import (
    OrderNamespace,
    OrderRole,
    TicketOrderReference,
)
from src.trading_kernel.infrastructure.venue_adapter import CcxtVenueAdapter

MARKET = {
    "id": "BTCUSDT", "symbol": "BTC/USDT:USDT", "base": "BTC", "quote": "USDT",
    "settle": "USDT", "type": "swap", "spot": False, "swap": True, "future": False,
    "option": False, "contract": True, "linear": True, "inverse": False,
    "contractSize": 1, "precision": {"amount": 0.001, "price": 0.1},
}
ORDER_ID = "9007199254740993"


def raw_trade(trade_id, quantity, price):
    return {
        "symbol": "BTCUSDT", "id": trade_id, "orderId": ORDER_ID, "side": "BUY",
        "price": price, "qty": quantity, "realizedPnl": "0", "marginAsset": "USDT",
        "quoteQty": str(Decimal(price) * Decimal(quantity)), "commission": "0.01",
        "commissionAsset": "BNB", "time": 1100, "positionSide": "LONG", "maker": False,
        "buyer": True,
    }


class ParsedExchange:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.parser = ccxt.binanceusdm()
        self.parser.set_markets([MARKET])

    async def fetch_my_trades(self, symbol, since, limit, params):
        self.calls.append((symbol, since, limit, params))
        return [self.parser.parse_trade(deepcopy(row), MARKET) for row in self.rows]


def request():
    return CompleteEntryFillsRequest(
        netting_domain=NettingDomain(
            venue_id="binance-usdm", account_id="manual", position_side="long",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        ),
        reference=TicketOrderReference(
            command_id="entry-command", command_kind=ExchangeCommandKind.ENTRY,
            role=OrderRole.ENTRY, namespace=OrderNamespace.REGULAR,
            venue_client_order_id="brc-exact-entry", submitted_exchange_order_id=ORDER_ID,
            command_created_at_ms=1000,
        ),
        expected_quantity=Decimal(".003"), observed_at_ms=2000,
    )


@pytest.mark.asyncio
async def test_multiple_raw_fills_freeze_exact_order_trade_ids_and_weighted_price():
    first = raw_trade(9007199254740995, ".001", "60000.1")
    second = raw_trade(9007199254740997, ".002", "60001.0")
    exchange = ParsedExchange([second, first, first])
    adapter = CcxtVenueAdapter(exchanges={("binance-usdm", "manual"): exchange}, clock_ms=lambda: 2000)
    facts = await adapter.read_complete_entry_fills(request())
    assert facts.exchange_order_id == ORDER_ID
    assert [f.trade_id for f in facts.fills] == ["9007199254740995", "9007199254740997"]
    assert facts.quantity == Decimal(".003") and facts.vwap == Decimal("60000.7")
    assert exchange.calls == [("BTC/USDT:USDT", None, 1000, {"orderId": ORDER_ID})]


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["order", "position_side", "time", "quantity", "duplicate"])
async def test_parsed_protocol_conflicts_never_become_complete_entry_proof(fault):
    rows = [raw_trade(1, ".003", "60000.1")]
    if fault == "order":
        rows[0]["orderId"] = "unrelated"
    elif fault == "position_side":
        rows[0]["positionSide"] = "SHORT"
    elif fault == "time":
        rows[0]["time"] = 999
    elif fault == "quantity":
        rows[0]["qty"] = ".002"
    else:
        changed = deepcopy(rows[0])
        changed["price"] = "60001.1"
        rows.append(changed)
    exchange = ParsedExchange(rows)
    adapter = CcxtVenueAdapter(exchanges={("binance-usdm", "manual"): exchange}, clock_ms=lambda: 2000)
    with pytest.raises(RuntimeError):
        await adapter.read_complete_entry_fills(request())
