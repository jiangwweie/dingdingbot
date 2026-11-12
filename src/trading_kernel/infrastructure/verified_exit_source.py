"""Bounded GET-only exact accepted-order history and final flatness collection."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from decimal import Decimal

from src.trading_kernel.domain.aggregate import TradeAggregate
from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)
from src.trading_kernel.domain.order_attribution import (
    OrderNamespace,
    OrderRole,
    TicketOrderReference,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.readonly_closure import ClosureFill
from src.trading_kernel.domain.verified_exit_closure import (
    VerifiedClosureOrder,
    VerifiedExitClosureProof,
)
from src.trading_kernel.infrastructure.binance_management_observation import (
    parse_rest_order,
)
from src.trading_kernel.infrastructure.readonly_closure_source import ClosureReader


class VerifiedExitUnavailable(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


async def collect_verified_exit(
    reader: ClosureReader,
    *,
    aggregate: TradeAggregate,
    references: tuple[TicketOrderReference, ...],
    incident_ids: tuple[str, ...],
    clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
) -> VerifiedExitClosureProof:
    a = aggregate
    domain = a.identity.netting_domain
    if not 1 < len(references) <= 128:
        raise VerifiedExitUnavailable("closure_reference_bound")
    symbol = parse_binance_usdm_instrument_id(domain.exchange_instrument_id).symbol
    orders: list[VerifiedClosureOrder] = []
    entries: list[ClosureFill] = []
    exits: list[ClosureFill] = []
    all_trade_ids: dict[str, ClosureFill] = {}
    for ref in references:
        conditional = ref.namespace is OrderNamespace.CONDITIONAL
        raw = await reader.read(
            "algo_order" if conditional else "order",
            {"algoId": ref.submitted_exchange_order_id}
            if conditional
            else {"symbol": symbol, "orderId": ref.submitted_exchange_order_id},
        )
        if not isinstance(raw, dict):
            raise VerifiedExitUnavailable("closure_order_shape")
        now = clock_ms()
        evidence = parse_rest_order(
            raw,
            account_id=domain.account_id,
            conditional=conditional,
            received_at_ms=now,
            coverage_complete=True,
        )
        status = str(raw.get("algoStatus") if conditional else raw.get("status"))
        actual = str(raw.get("actualOrderId") or "").strip() if conditional else None
        actual = None if actual in {"", "0"} else actual
        quantity = (
            Decimal(str(raw.get("actualQty") or "0"))
            if conditional
            else Decimal(str(raw.get("executedQty") or "0"))
        )
        order = VerifiedClosureOrder.model_validate(
            {
                "reference": ref,
                "terms": evidence.terms,
                "status": status,
                "executed_quantity": quantity,
                "actual_order_id": actual,
                "updated_at_ms": int(raw["updateTime"]),
            }
        )
        if (
            order.terms.exchange_instrument_id != domain.exchange_instrument_id
            or order.terms.position_side != domain.position_side
        ):
            raise VerifiedExitUnavailable("closure_order_scope")
        oid = order.executable_id
        if quantity > 0:
            if oid is None:
                raise VerifiedExitUnavailable("closure_child_unavailable")
            if conditional:
                child = await reader.read("order", {"symbol": symbol, "orderId": oid})
                if (
                    not isinstance(child, dict)
                    or str(child.get("orderId")) != oid
                    or child.get("symbol") != symbol
                    or child.get("positionSide", "").lower() != domain.position_side
                    or child.get("side", "").lower() != order.terms.side
                    or child.get("clientOrderId") != ref.venue_client_order_id
                    or child.get("status") != "FILLED"
                    or Decimal(str(child.get("executedQty"))) != quantity
                ):
                    raise VerifiedExitUnavailable("closure_child_identity")
            rows = await reader.read(
                "trades",
                {
                    "symbol": symbol,
                    "orderId": oid,
                    "startTime": ref.command_created_at_ms,
                    "endTime": now,
                    "limit": 1000,
                },
            )
            if not isinstance(rows, list) or len(rows) >= 1000:
                raise VerifiedExitUnavailable("closure_fills_truncated")
            selected = []
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or str(row.get("orderId")) != oid
                    or row.get("symbol") != symbol
                    or str(row.get("positionSide", "")).lower() != domain.position_side
                    or str(row.get("side", "")).lower() != order.terms.side
                ):
                    raise VerifiedExitUnavailable("closure_fill_identity")
                fill = ClosureFill(
                    trade_id=str(row["id"]),
                    order_id=oid,
                    quantity=Decimal(row["qty"]),
                    price=Decimal(row["price"]),
                    occurred_at_ms=int(row["time"]),
                )
                old = all_trade_ids.get(fill.trade_id)
                if old is not None:
                    if old != fill:
                        raise VerifiedExitUnavailable(
                            "closure_duplicate_trade_conflict"
                        )
                    continue
                all_trade_ids[fill.trade_id] = fill
                selected.append(fill)
            (entries if ref.role is OrderRole.ENTRY else exits).extend(selected)
        orders.append(order)
    # Facts that establish current flatness are collected after historical I/O.
    positions, regular, conditional_orders, mode = await asyncio.gather(
        *(reader.read(name, {}) for name in ["positions", "orders", "algos", "mode"])
    )
    if mode != {"dualSidePosition": True}:
        raise VerifiedExitUnavailable("closure_account_mode")
    if (
        not isinstance(positions, list)
        or len(positions) > 2000
        or not isinstance(regular, list)
        or len(regular) >= 1000
        or not isinstance(conditional_orders, list)
        or len(conditional_orders) >= 1000
    ):
        raise VerifiedExitUnavailable("closure_current_incomplete")
    relevant = lambda row: (
        row.get("symbol") == symbol
        and str(row.get("positionSide", "")).lower() == domain.position_side
    )
    if any(
        Decimal(str(row["positionAmt"])) != 0
        for row in positions
        if row.get("symbol") == symbol
    ):
        raise VerifiedExitUnavailable("closure_position_nonzero")
    if any(relevant(row) for row in [*regular, *conditional_orders]):
        raise VerifiedExitUnavailable("closure_residual_orders")
    now = clock_ms()
    return VerifiedExitClosureProof(
        ticket_id=a.identity.ticket_id,
        domain=domain,
        expected_version=a.version,
        management_revision=a.management_revision,
        entry_quantity=a.ticket.quantity,
        orders=tuple(orders),
        entry_fills=tuple(entries),
        exit_fills=tuple(exits),
        snapshot=PositionSnapshot(
            netting_domain=domain,
            quantity=Decimal(0),
            average_entry_price=None,
            open_orders=(),
            orders_complete=True,
            observed_at_ms=now,
        ),
        incident_ids=incident_ids,
        observed_at_ms=now,
        valid_until_ms=now + 30_000,
    )
