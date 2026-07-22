from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.application.ports import VenueCommandRequest
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
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


class CancelExchange:
    def __init__(self) -> None:
        self.cancel_call = None

    async def create_order(self, *args, **kwargs):
        raise AssertionError("cancel must not create an order")

    async def cancel_order(self, order_id, symbol, params):
        self.cancel_call = (order_id, symbol, params)
        return {
            "id": order_id,
            "status": "canceled",
            "clientOrderId": "brc-stop-1",
        }


class RejectingCancelExchange:
    async def cancel_order(self, *args, **kwargs):
        raise InsufficientFunds("sensitive venue message")


class TimingOutCancelExchange:
    async def cancel_order(self, *args, **kwargs):
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


@pytest.mark.asyncio
async def test_ccxt_adapter_cancels_exact_exchange_order_without_creating_order() -> None:
    exchange = CancelExchange()
    adapter = _cancel_adapter(exchange)

    result = await adapter.execute(_cancel_request())

    assert result.status is ExchangeCommandStatus.ACCEPTED
    assert result.exchange_order_id == "stop-order-1"
    assert exchange.cancel_call == (
        "stop-order-1",
        "BTC/USDT:USDT",
        {"positionSide": "LONG"},
    )


@pytest.mark.asyncio
async def test_ccxt_adapter_classifies_authoritative_cancel_rejection() -> None:
    result = await _cancel_adapter(RejectingCancelExchange()).execute(
        _cancel_request()
    )

    assert result.status is ExchangeCommandStatus.REJECTED
    assert result.reason == "venue_rejected:InsufficientFunds"
    assert "sensitive" not in result.reason


@pytest.mark.asyncio
async def test_ccxt_adapter_propagates_unknown_cancel_outcome() -> None:
    with pytest.raises(TimeoutError):
        await _cancel_adapter(TimingOutCancelExchange()).execute(_cancel_request())


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


def _cancel_adapter(exchange) -> CcxtVenueAdapter:
    return CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        venue_symbols={
            (
                "binance-usdm",
                "binance-usdm:BTCUSDT:perpetual",
            ): "BTC/USDT:USDT"
        },
        clock_ms=lambda: 2_000,
    )


def _cancel_request() -> VenueCommandRequest:
    return VenueCommandRequest(
        command_id="command:cancel-stop-1",
        kind=ExchangeCommandKind.CANCEL_ORDER,
        venue_id="binance-usdm",
        account_id="experiment-1",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        venue_client_order_id="brc-cancel-stop-1",
        payload=CancelCommandPayload(exchange_order_id="stop-order-1"),
        deadline_at_ms=10_000,
    )
