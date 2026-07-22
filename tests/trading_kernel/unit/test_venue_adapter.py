from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.application.ports import VenueCommandRequest
from src.trading_kernel.domain.commands import (
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.infrastructure.venue_adapter import CcxtVenueAdapter


class FakeAsyncExchange:
    def __init__(self) -> None:
        self.call = None

    async def create_order(self, symbol, order_type, side, amount, price, params):
        self.call = (symbol, order_type, side, amount, price, params)
        return {
            "id": "venue-order-1",
            "status": "open",
            "clientOrderId": params["newClientOrderId"],
        }


class InsufficientFunds(Exception):
    pass


class RejectingExchange:
    async def create_order(self, *args, **kwargs):
        raise InsufficientFunds("sensitive venue message")


class TimingOutExchange:
    async def create_order(self, *args, **kwargs):
        raise TimeoutError("network outcome unknown")


@pytest.mark.asyncio
async def test_ccxt_adapter_sends_explicit_hedge_side_and_client_identity() -> None:
    exchange = FakeAsyncExchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        venue_symbols={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "BTC/USDT:USDT"
        },
        clock_ms=lambda: 2_000,
    )

    result = await adapter.execute(_request())

    assert result.status is ExchangeCommandStatus.ACCEPTED
    assert result.exchange_order_id == "venue-order-1"
    assert exchange.call == (
        "BTC/USDT:USDT",
        "market",
        "buy",
        Decimal("0.001"),
        None,
        {
            "newClientOrderId": "brc-entry-1",
            "positionSide": "LONG",
        },
    )


@pytest.mark.asyncio
async def test_ccxt_adapter_classifies_only_authoritative_rejection() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): RejectingExchange()},
        venue_symbols={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "BTC/USDT:USDT"
        },
        clock_ms=lambda: 2_000,
    )

    result = await adapter.execute(_request())

    assert result.status is ExchangeCommandStatus.REJECTED
    assert result.reason == "venue_rejected:InsufficientFunds"
    assert "sensitive" not in result.reason


@pytest.mark.asyncio
async def test_ccxt_adapter_propagates_unknown_network_outcome() -> None:
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): TimingOutExchange()},
        venue_symbols={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "BTC/USDT:USDT"
        },
        clock_ms=lambda: 2_000,
    )

    with pytest.raises(TimeoutError):
        await adapter.execute(_request())


def _request() -> VenueCommandRequest:
    return VenueCommandRequest(
        command_id="command:entry-1",
        kind=ExchangeCommandKind.ENTRY,
        venue_id="binance-usdm",
        account_id="experiment-1",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        venue_client_order_id="brc-entry-1",
        payload=OrderCommandPayload(
            side="buy",
            quantity=Decimal("0.001"),
            order_type="market",
            reduce_only=False,
        ),
        deadline_at_ms=10_000,
    )
