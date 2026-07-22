from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.application.ports import VenueCommandRequest, VenueTruthRequest
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.infrastructure.venue_adapter import CcxtVenueAdapter
from src.trading_kernel.domain.venue_truth import VenueLookupStatus


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


class OrderNotFound(Exception):
    pass


class TruthExchange:
    def __init__(self, *, visible: bool) -> None:
        self.visible = visible
        self.calls: list[str] = []

    async def fetch_order(self, order_id, symbol, params):
        self.calls.append("order")
        if not self.visible:
            raise OrderNotFound("not visible")
        return {
            "id": "venue-order-1",
            "clientOrderId": params["origClientOrderId"],
            "symbol": symbol,
            "side": "buy",
            "amount": "0.001",
            "reduceOnly": False,
            "info": {"positionSide": "LONG"},
        }

    async def fetch_positions(self, symbols, params):
        self.calls.append("positions")
        return [{"symbol": symbols[0], "contracts": "0"}]

    async def fetch_my_trades(self, symbol, since, limit, params):
        self.calls.append("fills")
        return []

    async def fetch_open_orders(self, symbol, since, limit, params):
        self.calls.append(
            "conditional" if params.get("conditional") else "regular"
        )
        return []


class CancelTruthExchange(TruthExchange):
    def __init__(self, *, visible: bool, target_in_open: bool = False) -> None:
        super().__init__(visible=visible)
        self.order_lookup = None
        self.target_in_open = target_in_open

    async def fetch_order(self, order_id, symbol, params):
        self.calls.append("order")
        self.order_lookup = (order_id, symbol, params)
        if not self.visible:
            raise OrderNotFound("not visible")
        return {
            "id": order_id,
            "clientOrderId": "brc-original-stop",
            "symbol": symbol,
            "side": "sell",
            "amount": "0.001",
            "reduceOnly": True,
            "info": {"positionSide": "LONG"},
        }

    async def fetch_open_orders(self, symbol, since, limit, params):
        self.calls.append(
            "conditional" if params.get("conditional") else "regular"
        )
        if self.target_in_open and params.get("conditional"):
            return [
                {
                    "id": "stop-order-1",
                    "clientOrderId": "brc-original-stop",
                    "symbol": symbol,
                    "side": "sell",
                    "amount": "0.001",
                    "reduceOnly": True,
                    "info": {"positionSide": "LONG"},
                }
            ]
        return []

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


@pytest.mark.asyncio
async def test_ccxt_adapter_reads_complete_visible_command_truth() -> None:
    exchange = TruthExchange(visible=True)
    adapter = _cancel_adapter(exchange)

    truth = await adapter.lookup_command_truth(_truth_request())

    assert truth.lookup_status is VenueLookupStatus.VISIBLE
    assert truth.order is not None
    assert truth.order.exchange_order_id == "venue-order-1"
    assert truth.order.exchange_instrument_id == (
        "binance-usdm:BTCUSDT:perpetual"
    )
    assert truth.order.position_side == "long"
    assert truth.order.quantity == Decimal("0.001")
    assert exchange.calls == [
        "order",
        "positions",
        "fills",
        "regular",
        "conditional",
    ]


@pytest.mark.asyncio
async def test_ccxt_adapter_proves_absence_only_after_all_truth_surfaces() -> None:
    exchange = TruthExchange(visible=False)
    adapter = _cancel_adapter(exchange)

    truth = await adapter.lookup_command_truth(_truth_request())

    assert truth.lookup_status is VenueLookupStatus.ABSENT
    assert truth.order is None
    assert truth.position_quantity == 0
    assert truth.matching_fill_quantity == 0
    assert exchange.calls == [
        "order",
        "positions",
        "fills",
        "regular",
        "conditional",
    ]


@pytest.mark.asyncio
async def test_cancel_truth_looks_up_exact_target_order_not_cancel_command_identity() -> None:
    exchange = CancelTruthExchange(visible=True)
    adapter = _cancel_adapter(exchange)

    truth = await adapter.lookup_command_truth(_cancel_truth_request())

    assert truth.lookup_status is VenueLookupStatus.VISIBLE
    assert truth.order is not None
    assert truth.order.exchange_order_id == "stop-order-1"
    assert truth.order.venue_client_order_id == "brc-original-stop"
    assert exchange.order_lookup == (
        "stop-order-1",
        "BTC/USDT:USDT",
        {"positionSide": "LONG"},
    )


@pytest.mark.asyncio
async def test_cancel_truth_does_not_claim_absence_when_target_is_still_open() -> None:
    exchange = CancelTruthExchange(visible=False, target_in_open=True)
    adapter = _cancel_adapter(exchange)

    truth = await adapter.lookup_command_truth(_cancel_truth_request())

    assert truth.lookup_status is VenueLookupStatus.VISIBLE
    assert truth.order is not None
    assert truth.order.exchange_order_id == "stop-order-1"


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


def _truth_request() -> VenueTruthRequest:
    request = _request()
    return VenueTruthRequest(
        command_id=request.command_id,
        kind=request.kind,
        venue_id=request.venue_id,
        account_id=request.account_id,
        exchange_instrument_id=request.exchange_instrument_id,
        position_side=request.position_side,
        venue_client_order_id=request.venue_client_order_id,
        payload=request.payload,
        observed_at_ms=2_000,
    )


def _cancel_truth_request() -> VenueTruthRequest:
    request = _cancel_request()
    return VenueTruthRequest(
        command_id=request.command_id,
        kind=request.kind,
        venue_id=request.venue_id,
        account_id=request.account_id,
        exchange_instrument_id=request.exchange_instrument_id,
        position_side=request.position_side,
        venue_client_order_id=request.venue_client_order_id,
        payload=request.payload,
        observed_at_ms=2_000,
    )
