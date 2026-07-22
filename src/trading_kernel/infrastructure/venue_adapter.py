"""Typed CCXT translation at the sole trading-kernel venue boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
import inspect
from typing import Literal, Protocol

from pydantic import JsonValue

from src.trading_kernel.application.ports import VenueCommandRequest, VenueTruthRequest
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.domain.venue_truth import (
    VenueLookupStatus,
    VenueOrderTruth,
    VenueTruthSnapshot,
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

    def fetch_order(
        self,
        order_id: object,
        symbol: str,
        params: Mapping[str, object],
    ) -> object: ...

    def fetch_positions(
        self,
        symbols: list[str],
        params: Mapping[str, object],
    ) -> object: ...

    def fetch_my_trades(
        self,
        symbol: str,
        since: object,
        limit: int,
        params: Mapping[str, object],
    ) -> object: ...

    def fetch_open_orders(
        self,
        symbol: str,
        since: object,
        limit: int,
        params: Mapping[str, object],
    ) -> object: ...


_AUTHORITATIVE_REJECTION_TYPES = {
    "BadRequest",
    "InsufficientFunds",
    "InvalidOrder",
    "OperationRejected",
}
_ORDER_NOT_FOUND_TYPES = {"OrderNotFound"}


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

    async def lookup_command_truth(
        self,
        request: VenueTruthRequest,
    ) -> VenueTruthSnapshot:
        exchange, symbol = self._resolve_exchange_and_symbol(
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
        )
        order_response: object | None
        if isinstance(request.payload, CancelCommandPayload):
            lookup_order_id: object = request.payload.exchange_order_id
            lookup_params: Mapping[str, object] = {
                "positionSide": request.position_side.upper()
            }
        else:
            lookup_order_id = None
            lookup_params = {"origClientOrderId": request.venue_client_order_id}
        try:
            order_response = await _call_raw_exchange(
                exchange.fetch_order,
                lookup_order_id,
                symbol,
                lookup_params,
            )
        except Exception as exc:
            if type(exc).__name__ not in _ORDER_NOT_FOUND_TYPES:
                raise
            order_response = None

        positions = _require_list(
            await _call_raw_exchange(
                exchange.fetch_positions,
                [symbol],
                {"positionSide": request.position_side.upper()},
            ),
            name="positions",
        )
        fills = _require_list(
            await _call_raw_exchange(
                exchange.fetch_my_trades,
                symbol,
                None,
                100,
                {"clientOrderId": request.venue_client_order_id},
            ),
            name="fills",
        )
        regular_orders = _require_list(
            await _call_raw_exchange(
                exchange.fetch_open_orders,
                symbol,
                None,
                100,
                {"conditional": False},
            ),
            name="regular open orders",
        )
        conditional_orders = _require_list(
            await _call_raw_exchange(
                exchange.fetch_open_orders,
                symbol,
                None,
                100,
                {"conditional": True},
            ),
            name="conditional open orders",
        )
        if order_response is None and isinstance(
            request.payload,
            CancelCommandPayload,
        ):
            order_response = _find_order_by_exchange_id(
                (*regular_orders, *conditional_orders),
                exchange_order_id=request.payload.exchange_order_id,
            )
        order = (
            None
            if order_response is None
            else _parse_order_truth(
                order_response,
                request=request,
                expected_symbol=symbol,
            )
        )
        return VenueTruthSnapshot(
            lookup_status=(
                VenueLookupStatus.ABSENT
                if order is None
                else VenueLookupStatus.VISIBLE
            ),
            order=order,
            position_quantity=_position_quantity(positions, expected_symbol=symbol),
            matching_fill_quantity=_matching_fill_quantity(
                fills,
                venue_client_order_id=request.venue_client_order_id,
            ),
            regular_open_client_order_ids=_open_client_order_ids(regular_orders),
            conditional_open_client_order_ids=_open_client_order_ids(
                conditional_orders
            ),
            observed_at_ms=self._clock_ms(),
        )

    def _resolve_exchange_and_symbol(
        self,
        *,
        venue_id: str,
        account_id: str,
        exchange_instrument_id: str,
    ) -> tuple[_CcxtExchange, str]:
        exchange = self._exchanges.get((venue_id, account_id))
        if exchange is None:
            raise RuntimeError("venue/account adapter is not configured")
        symbol = self._venue_symbols.get((venue_id, exchange_instrument_id))
        if not symbol:
            raise RuntimeError("canonical instrument has no venue symbol mapping")
        return exchange, symbol


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


async def _call_raw_exchange(
    operation: Callable[..., object],
    *args: object,
) -> object:
    response = operation(*args)
    if inspect.isawaitable(response):
        return await response
    return response


def _require_list(value: object, *, name: str) -> list[object]:
    if not isinstance(value, list):
        raise RuntimeError(f"venue {name} response is not a list")
    return value


def _parse_order_truth(
    value: object,
    *,
    request: VenueTruthRequest,
    expected_symbol: str,
) -> VenueOrderTruth:
    if not isinstance(value, Mapping):
        raise RuntimeError("venue order truth response is not a mapping")
    info = value.get("info")
    raw_info = info if isinstance(info, Mapping) else {}
    raw_symbol = str(value.get("symbol") or "").strip()
    position_side = _position_side_literal(
        str(raw_info.get("positionSide") or "").strip().lower()
    )
    order_side = _order_side_literal(
        str(value.get("side") or "").strip().lower()
    )
    return VenueOrderTruth(
        exchange_order_id=str(value.get("id") or ""),
        venue_client_order_id=str(value.get("clientOrderId") or ""),
        exchange_instrument_id=(
            request.exchange_instrument_id
            if raw_symbol == expected_symbol
            else f"unmapped:{raw_symbol}"
        ),
        position_side=position_side,
        order_side=order_side,
        quantity=Decimal(str(value.get("amount") or "0")),
        reduce_only=bool(value.get("reduceOnly", False)),
    )


def _position_quantity(
    rows: list[object],
    *,
    expected_symbol: str,
) -> Decimal:
    total = Decimal("0")
    for value in rows:
        if not isinstance(value, Mapping):
            raise RuntimeError("venue position row is not a mapping")
        if str(value.get("symbol") or "") != expected_symbol:
            continue
        total += abs(Decimal(str(value.get("contracts") or "0")))
    return total


def _position_side_literal(value: str) -> Literal["long", "short"]:
    if value == "long":
        return "long"
    if value == "short":
        return "short"
    raise RuntimeError("venue order truth has invalid position side")


def _order_side_literal(value: str) -> Literal["buy", "sell"]:
    if value == "buy":
        return "buy"
    if value == "sell":
        return "sell"
    raise RuntimeError("venue order truth has invalid order side")


def _matching_fill_quantity(
    rows: list[object],
    *,
    venue_client_order_id: str,
) -> Decimal:
    total = Decimal("0")
    for value in rows:
        if not isinstance(value, Mapping):
            raise RuntimeError("venue fill row is not a mapping")
        info = value.get("info")
        raw_info = info if isinstance(info, Mapping) else {}
        client_id = str(
            value.get("clientOrderId")
            or raw_info.get("clientOrderId")
            or ""
        )
        if client_id == venue_client_order_id:
            total += abs(Decimal(str(value.get("amount") or "0")))
    return total


def _open_client_order_ids(rows: list[object]) -> tuple[str, ...]:
    identities: set[str] = set()
    for value in rows:
        if not isinstance(value, Mapping):
            raise RuntimeError("venue open-order row is not a mapping")
        identity = str(value.get("clientOrderId") or "").strip()
        if identity:
            identities.add(identity)
    return tuple(sorted(identities))


def _find_order_by_exchange_id(
    rows: tuple[object, ...],
    *,
    exchange_order_id: str,
) -> object | None:
    for value in rows:
        if not isinstance(value, Mapping):
            raise RuntimeError("venue open-order row is not a mapping")
        if str(value.get("id") or "").strip() == exchange_order_id:
            return value
    return None


def _safe_response_payload(response: Mapping[object, object]) -> dict[str, JsonValue]:
    return {
        key: value
        for key in ("status", "clientOrderId")
        if isinstance((value := response.get(key)), (str, int, float, bool))
    }
