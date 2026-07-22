"""Typed CCXT translation at the sole trading-kernel venue boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import inspect
from typing import Protocol

from pydantic import JsonValue

from src.trading_kernel.application.ports import VenueCommandRequest
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
)


class _CcxtExchange(Protocol):
    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: object,
        price: object,
        params: Mapping[str, object],
    ) -> object: ...

    def cancel_order(
        self,
        order_id: str,
        symbol: str,
        params: Mapping[str, object],
    ) -> object: ...


_AUTHORITATIVE_REJECTION_TYPES = {
    "BadRequest",
    "InsufficientFunds",
    "InvalidOrder",
    "OperationRejected",
}


class CcxtVenueAdapter:
    def __init__(
        self,
        *,
        exchanges: Mapping[tuple[str, str], _CcxtExchange],
        venue_symbols: Mapping[tuple[str, str], str],
        clock_ms: Callable[[], int],
    ) -> None:
        self._exchanges = dict(exchanges)
        self._venue_symbols = dict(venue_symbols)
        self._clock_ms = clock_ms

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        exchange_key = (request.venue_id, request.account_id)
        exchange = self._exchanges.get(exchange_key)
        if exchange is None:
            raise RuntimeError("venue/account adapter is not configured")
        symbol_key = (request.venue_id, request.exchange_instrument_id)
        symbol = self._venue_symbols.get(symbol_key)
        if not symbol:
            raise RuntimeError("canonical instrument has no venue symbol mapping")

        params: dict[str, object] = {"positionSide": request.position_side.upper()}

        if isinstance(request.payload, CancelCommandPayload):
            response = await _call_exchange(
                exchange.cancel_order,
                request.payload.exchange_order_id,
                symbol,
                params,
                clock_ms=self._clock_ms,
            )
            if isinstance(response, ExchangeCommandResult):
                return response
            if not isinstance(response, Mapping):
                raise RuntimeError("venue cancel response is not a mapping")
            return ExchangeCommandResult(
                status=ExchangeCommandStatus.ACCEPTED,
                observed_at_ms=self._clock_ms(),
                exchange_order_id=request.payload.exchange_order_id,
                venue_payload=_safe_response_payload(response),
            )

        if not isinstance(request.payload, OrderCommandPayload):
            raise RuntimeError("unsupported venue command payload")

        params["newClientOrderId"] = request.venue_client_order_id
        if request.payload.reduce_only and request.venue_id != "binance-usdm":
            params["reduceOnly"] = True
        if request.payload.stop_price is not None:
            params["stopPrice"] = request.payload.stop_price

        response = await _call_exchange(
            exchange.create_order,
            symbol,
            request.payload.order_type,
            request.payload.side,
            request.payload.quantity,
            request.payload.limit_price,
            params,
            clock_ms=self._clock_ms,
        )
        if isinstance(response, ExchangeCommandResult):
            return response

        if not isinstance(response, Mapping):
            raise RuntimeError("venue response is not a mapping")
        exchange_order_id = str(response.get("id") or "").strip()
        if not exchange_order_id:
            raise RuntimeError("venue acceptance lacks exchange order identity")

        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=self._clock_ms(),
            exchange_order_id=exchange_order_id,
            venue_payload=_safe_response_payload(response),
        )


async def _call_exchange(
    operation: Callable[..., object],
    *args: object,
    clock_ms: Callable[[], int],
) -> object | ExchangeCommandResult:
    try:
        response = operation(*args)
        if inspect.isawaitable(response):
            response = await response
        return response
    except Exception as exc:
        error_type = type(exc).__name__
        if error_type in _AUTHORITATIVE_REJECTION_TYPES:
            return ExchangeCommandResult(
                status=ExchangeCommandStatus.REJECTED,
                observed_at_ms=clock_ms(),
                reason=f"venue_rejected:{error_type}",
            )
        raise


def _safe_response_payload(response: Mapping[object, object]) -> dict[str, JsonValue]:
    return {
        key: value
        for key in ("status", "clientOrderId")
        if isinstance((value := response.get(key)), (str, int, float, bool))
    }
