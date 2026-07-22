"""Typed CCXT translation at the sole trading-kernel venue boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import inspect
from typing import Protocol

from src.trading_kernel.application.ports import VenueCommandRequest
from src.trading_kernel.domain.commands import (
    ExchangeCommandResult,
    ExchangeCommandStatus,
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

        params: dict[str, object] = {
            "newClientOrderId": request.venue_client_order_id,
            "positionSide": request.position_side.upper(),
        }
        if request.payload.reduce_only and request.venue_id != "binance-usdm":
            params["reduceOnly"] = True
        if request.payload.stop_price is not None:
            params["stopPrice"] = request.payload.stop_price

        try:
            response = exchange.create_order(
                symbol,
                request.payload.order_type,
                request.payload.side,
                request.payload.quantity,
                request.payload.limit_price,
                params,
            )
            if inspect.isawaitable(response):
                response = await response
        except Exception as exc:
            error_type = type(exc).__name__
            if error_type in _AUTHORITATIVE_REJECTION_TYPES:
                return ExchangeCommandResult(
                    status=ExchangeCommandStatus.REJECTED,
                    observed_at_ms=self._clock_ms(),
                    reason=f"venue_rejected:{error_type}",
                )
            raise

        if not isinstance(response, Mapping):
            raise RuntimeError("venue response is not a mapping")
        exchange_order_id = str(response.get("id") or "").strip()
        if not exchange_order_id:
            raise RuntimeError("venue acceptance lacks exchange order identity")

        safe_payload = {
            key: value
            for key in ("status", "clientOrderId")
            if isinstance((value := response.get(key)), (str, int, float, bool))
        }
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=self._clock_ms(),
            exchange_order_id=exchange_order_id,
            venue_payload=safe_payload,
        )
