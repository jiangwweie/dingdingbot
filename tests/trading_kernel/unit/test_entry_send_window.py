from __future__ import annotations

from decimal import Decimal
from urllib.parse import parse_qs

import ccxt
import pytest

from src.trading_kernel.application.ports import VenueCommandRequest, VenueTruthRequest
from src.trading_kernel.domain.commands import (
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.infrastructure.venue_adapter import CcxtVenueAdapter


class RecordingExchange:
    def __init__(self):
        self.calls = []

    async def create_order(self, *args):
        self.calls.append(args)
        return {"id": "order-1"}


def request():
    return VenueCommandRequest(
        command_id="entry-window",
        kind=ExchangeCommandKind.ENTRY,
        venue_id="binance-usdm",
        account_id="test",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        venue_client_order_id="entry-window",
        payload=OrderCommandPayload(
            side="buy",
            quantity=Decimal("0.001"),
            order_type="market",
            reduce_only=False,
        ),
        deadline_at_ms=20_000,
        entry_authorized_at_ms=2_000,
    )


@pytest.mark.asyncio
async def test_entry_freezes_signed_window_instead_of_refreshing_after_pause():
    exchange = RecordingExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "test"): exchange}, clock_ms=lambda: 3_000
    )
    result = await adapter.execute(request())
    assert result.status is ExchangeCommandStatus.ACCEPTED
    params = exchange.calls[0][-1]
    assert params["timestamp"] == 2_000
    assert params["recvWindow"] == 5_000
    # Exercise the installed CCXT signer; its current nonce must not extend authority.
    signer = ccxt.binance({"apiKey": "test", "secret": "test"})
    signer.nonce = lambda: 500_000
    signed = signer.sign("order", "fapiPrivate", "POST", params)
    body = parse_qs(signed["body"])
    assert body["timestamp"] == ["2000"]
    assert body["recvWindow"] == ["5000"]


@pytest.mark.asyncio
async def test_resumed_entry_after_window_expiry_makes_zero_order_calls():
    exchange = RecordingExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "test"): exchange}, clock_ms=lambda: 7_001
    )
    result = await adapter.execute(request())
    assert result.status is ExchangeCommandStatus.REJECTED
    assert result.reason == "entry_send_window_expired"
    assert exchange.calls == []


@pytest.mark.asyncio
async def test_missing_entry_authorization_cannot_silently_use_current_time():
    exchange = RecordingExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "test"): exchange}, clock_ms=lambda: 3_000
    )
    result = await adapter.execute(
        request().model_copy(update={"entry_authorized_at_ms": None})
    )
    assert result.status is ExchangeCommandStatus.REJECTED
    assert result.reason == "entry_send_authority_missing"
    assert exchange.calls == []


@pytest.mark.asyncio
async def test_visible_entry_can_be_observed_before_signing_window_closes():
    class ClockExchange(RecordingExchange):
        async def fapiPublicGetTime(self, params):
            self.calls.append(("server_clock", params))
            return {"serverTime": 7_000}

        async def fetch_order(self, *args):
            self.calls.append(("order_lookup",))
            return {
                "id": "order-1",
                "symbol": "BTC/USDT:USDT",
                "clientOrderId": "entry-window",
                "side": "buy",
                "amount": "0.001",
                "status": "open",
                "info": {"positionSide": "LONG", "reduceOnly": False},
            }

        async def fetch_positions(self, *args):
            return []

        async def fetch_open_orders(self, *args):
            return []

        async def fetch_my_trades(self, *args):
            return []

    exchange = ClockExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "test"): exchange}, clock_ms=lambda: 900_000
    )
    r = request()
    truth = VenueTruthRequest(
        **r.model_dump(exclude={"deadline_at_ms", "entry_authorized_at_ms"}),
        observed_at_ms=900_000,
        entry_window_expires_at_ms=7_000,
    )
    result = await adapter.lookup_command_truth(truth)
    assert result.lookup_status.value == "visible"
    assert result.exchange_observed_at_ms == 7_000
    assert exchange.calls == [("server_clock", {}), ("order_lookup",)]
