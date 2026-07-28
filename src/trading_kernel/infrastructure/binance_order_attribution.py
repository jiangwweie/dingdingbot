"""Binance USD-M regular/algo order namespace resolution."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from decimal import Decimal
from typing import Protocol

from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)
from src.trading_kernel.domain.order_attribution import (
    OrderNamespace,
    ResolvedOrderIdentity,
    TicketOrderReference,
)


class BinanceAlgoOrderClient(Protocol):
    def fapiPrivateGetAlgoOrder(self, params: Mapping[str, object]) -> object: ...


_NOT_TRIGGERED_TERMINAL_STATUSES = {"CANCELED", "EXPIRED", "REJECTED"}


async def resolve_binance_order_identity(
    *,
    exchange: object,
    reference: TicketOrderReference,
    observed_at_ms: int,
) -> ResolvedOrderIdentity:
    """Resolve an accepted Binance order into the sole legal trade order id."""

    if reference.namespace is OrderNamespace.REGULAR:
        return ResolvedOrderIdentity(
            reference=reference,
            resolution_status="executable",
            actual_order_id=reference.submitted_exchange_order_id,
            resolved_at_ms=observed_at_ms,
        )

    lookup = getattr(exchange, "fapiPrivateGetAlgoOrder", None)
    if not callable(lookup):
        raise RuntimeError("Binance venue lacks exact algo order lookup")
    response = lookup({"algoId": reference.submitted_exchange_order_id})
    if inspect.isawaitable(response):
        response = await response
    if not isinstance(response, Mapping):
        raise RuntimeError("Binance algo order response is not a mapping")

    algo_id = str(response.get("algoId") or "").strip()
    if algo_id != reference.submitted_exchange_order_id:
        raise RuntimeError("Binance algoId differs from durable command identity")
    client_algo_id = str(response.get("clientAlgoId") or "").strip()
    if client_algo_id != reference.venue_client_order_id:
        raise RuntimeError("Binance clientAlgoId differs from durable command identity")
    expectation = reference.conditional_expectation
    if expectation is None:
        raise RuntimeError("conditional order lacks frozen command expectation")
    expected_symbol = parse_binance_usdm_instrument_id(
        expectation.exchange_instrument_id
    ).symbol
    _require_exact_algo_field(response, "symbol", expected_symbol)
    _require_exact_algo_field(response, "side", expectation.side.upper())
    _require_exact_algo_field(
        response,
        "positionSide",
        expectation.position_side.upper(),
    )
    _require_exact_algo_field(
        response,
        "type",
        expectation.order_type.upper(),
    )
    actual_order_id = str(response.get("actualOrderId") or "").strip() or None
    actual_quantity = _require_algo_quantity(response, "actualQty")
    if actual_order_id is not None:
        if actual_quantity != expectation.quantity:
            raise RuntimeError("Binance actualQty differs from frozen command quantity")
        return ResolvedOrderIdentity(
            reference=reference,
            resolution_status="executable",
            actual_order_id=actual_order_id,
            resolved_at_ms=observed_at_ms,
        )

    status = str(response.get("status") or "").strip().upper()
    if status not in _NOT_TRIGGERED_TERMINAL_STATUSES:
        raise RuntimeError("Binance algo order has no actual order identity yet")
    if actual_quantity != 0:
        raise RuntimeError("Binance untriggered algo actualQty must be zero")
    return ResolvedOrderIdentity(
        reference=reference,
        resolution_status="not_triggered",
        actual_order_id=None,
        resolved_at_ms=observed_at_ms,
    )


def _require_exact_algo_field(
    response: Mapping[str, object],
    field: str,
    expected: str,
) -> None:
    actual = str(response.get(field) or "").strip().upper()
    if actual != expected:
        raise RuntimeError(f"Binance {field} differs from frozen command identity")


def _require_algo_quantity(response: Mapping[str, object], field: str) -> Decimal:
    raw = response.get(field)
    if raw is None:
        raise RuntimeError(f"Binance {field} is unavailable")
    try:
        quantity = Decimal(str(raw))
    except Exception as exc:
        raise RuntimeError(f"Binance {field} is invalid") from exc
    if not quantity.is_finite() or quantity < 0:
        raise RuntimeError(f"Binance {field} must be finite and non-negative")
    return quantity
