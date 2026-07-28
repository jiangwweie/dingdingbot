"""Binance USD-M regular/algo order namespace resolution."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Protocol

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
    actual_order_id = str(response.get("actualOrderId") or "").strip() or None
    if actual_order_id is not None:
        return ResolvedOrderIdentity(
            reference=reference,
            resolution_status="executable",
            actual_order_id=actual_order_id,
            resolved_at_ms=observed_at_ms,
        )

    status = str(response.get("status") or "").strip().upper()
    if status not in _NOT_TRIGGERED_TERMINAL_STATUSES:
        raise RuntimeError("Binance algo order has no actual order identity yet")
    return ResolvedOrderIdentity(
        reference=reference,
        resolution_status="not_triggered",
        actual_order_id=None,
        resolved_at_ms=observed_at_ms,
    )
