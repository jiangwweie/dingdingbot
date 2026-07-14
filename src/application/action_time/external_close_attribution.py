"""Fail-closed attribution of exchange-side manual exits to one Ticket."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
from typing import Any

import sqlalchemy as sa


def attribute_exact_ticket_bound_external_close(
    conn: sa.engine.Connection,
    *,
    lifecycle: dict[str, Any],
    orders: list[dict[str, Any]],
    exchange_scope: Any,
    recent_fills: list[dict[str, Any]],
    position: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Return one external close only when identity, time, and quantity are exact."""

    if not lifecycle or lifecycle.get("entry_fill_confirmed") not in (True, 1):
        return {}, []
    if not _position_flat(position):
        return {}, []
    if not (
        position.get("complete") is True
        or str(position.get("truth_state") or "").lower() == "flat"
    ):
        return {}, []
    entry_qty = _decimal(lifecycle.get("entry_filled_qty"))
    entry_order_id = str(lifecycle.get("entry_exchange_order_id") or "").strip()
    if entry_qty <= 0 or not entry_order_id:
        return {}, []

    tracked_order_ids = {
        str(order.get("exchange_order_id") or "").strip()
        for order in orders
        if str(order.get("exchange_order_id") or "").strip()
    }
    tracked_exit_qty = Decimal("0")
    for fill in recent_fills:
        fill_order_id = str(fill.get("exchange_order_id") or "").strip()
        parent_order_id = str(
            fill.get("parent_exchange_order_id") or ""
        ).strip()
        matched_tracked_id = next(
            (
                order_id
                for order_id in (fill_order_id, parent_order_id)
                if order_id in tracked_order_ids
            ),
            "",
        )
        if not matched_tracked_id:
            continue
        tracked = next(
            (
                order
                for order in orders
                if str(order.get("exchange_order_id") or "").strip()
                == matched_tracked_id
            ),
            {},
        )
        if str(tracked.get("role") or "").upper() == "TP1":
            tracked_exit_qty += _decimal(fill.get("qty"))
    remaining_qty = entry_qty - tracked_exit_qty
    if remaining_qty <= 0:
        return {}, []

    expected_side = "sell" if exchange_scope.side == "long" else "buy"
    preliminary_candidates: list[dict[str, Any]] = []
    for fill in recent_fills:
        exchange_order_id = str(fill.get("exchange_order_id") or "").strip()
        parent_exchange_order_id = str(
            fill.get("parent_exchange_order_id") or ""
        ).strip()
        if not exchange_order_id or exchange_order_id == entry_order_id:
            continue
        if (
            exchange_order_id in tracked_order_ids
            or parent_exchange_order_id in tracked_order_ids
        ):
            continue
        if str(fill.get("side") or "").lower() != expected_side:
            continue
        if not _fill_symbol_matches_scope(fill, exchange_scope=exchange_scope):
            continue
        if not _fill_position_bucket_matches_scope(fill, exchange_scope=exchange_scope):
            continue
        if _decimal(fill.get("qty")) <= 0 or _decimal(fill.get("price")) <= 0:
            continue
        preliminary_candidates.append(fill)
    if not preliminary_candidates:
        return {}, []

    entry_fill_time_ms = _entry_fill_time_ms(
        conn,
        lifecycle=lifecycle,
        recent_fills=recent_fills,
    )
    if entry_fill_time_ms is None:
        return {}, ["external_close_entry_fill_time_missing"]
    candidates = [
        fill
        for fill in preliminary_candidates
        if (fill_time_ms := _int_optional(fill.get("timestamp_ms"))) is not None
        and fill_time_ms >= entry_fill_time_ms
    ]
    if not candidates:
        return {}, ["external_close_fill_time_invalid"]

    blockers: list[str] = []
    if len(
        {
            str(fill.get("exchange_order_id") or "").strip()
            for fill in candidates
        }
    ) != 1:
        blockers.append("external_close_fill_attribution_ambiguous")
    if _competing_open_ticket_ids(
        conn,
        lifecycle=lifecycle,
        exchange_scope=exchange_scope,
    ):
        blockers.append("external_close_ticket_scope_ambiguous")
    aggregated = _aggregate_external_close_fills(candidates)
    if _decimal(aggregated.get("fill_qty")) != remaining_qty:
        blockers.append("external_close_fill_qty_mismatch")
    if blockers:
        return {}, _dedupe(blockers)
    return {
        **aggregated,
        "role": "EXTERNAL_CLOSE",
        "attribution_basis": (
            "exact_account_instrument_position_bucket_entry_remainder_flat"
        ),
    }, []


def _entry_fill_time_ms(
    conn: sa.engine.Connection,
    *,
    lifecycle: dict[str, Any],
    recent_fills: list[dict[str, Any]],
) -> int | None:
    entry_order_id = str(lifecycle.get("entry_exchange_order_id") or "").strip()
    observed_times = [
        timestamp_ms
        for fill in recent_fills
        if str(fill.get("exchange_order_id") or "").strip() == entry_order_id
        if (timestamp_ms := _int_optional(fill.get("timestamp_ms"))) is not None
    ]
    if observed_times:
        return max(observed_times)
    attempt = _row_by_id(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        str(lifecycle.get("protected_submit_attempt_id") or ""),
    )
    submit_result = _mapping(attempt.get("submit_result"))
    for order in submit_result.get("submitted_orders", []):
        if not isinstance(order, dict):
            continue
        if str(order.get("order_role") or "").upper() != "ENTRY":
            continue
        return _int_optional(order.get("fill_time_ms") or order.get("timestamp_ms"))
    return None


def _fill_symbol_matches_scope(fill: dict[str, Any], *, exchange_scope: Any) -> bool:
    observed = _canonical_symbol(fill.get("symbol"))
    return observed in {
        _canonical_symbol(exchange_scope.canonical_symbol),
        _canonical_symbol(exchange_scope.exchange_symbol),
    }


def _fill_position_bucket_matches_scope(
    fill: dict[str, Any],
    *,
    exchange_scope: Any,
) -> bool:
    observed = str(fill.get("position_side") or "").upper()
    if exchange_scope.position_mode == "hedge":
        return observed == exchange_scope.position_side
    return observed in {"", "BOTH"}


def _competing_open_ticket_ids(
    conn: sa.engine.Connection,
    *,
    lifecycle: dict[str, Any],
    exchange_scope: Any,
) -> list[str]:
    lifecycles = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    tickets = _table(conn, "brc_action_time_tickets")
    budgets = _table(conn, "brc_budget_reservations")
    query = (
        sa.select(tickets.c.ticket_id)
        .select_from(
            lifecycles.join(tickets, lifecycles.c.ticket_id == tickets.c.ticket_id).join(
                budgets,
                tickets.c.budget_reservation_id == budgets.c.budget_reservation_id,
            )
        )
        .where(
            tickets.c.ticket_id != str(lifecycle.get("ticket_id") or ""),
            tickets.c.exchange_instrument_id == exchange_scope.exchange_instrument_id,
            budgets.c.account_id == exchange_scope.account_id,
            lifecycles.c.entry_fill_confirmed.is_(True),
            lifecycles.c.status != "lifecycle_closed",
        )
    )
    if exchange_scope.position_mode == "hedge":
        query = query.where(tickets.c.side == exchange_scope.side)
    return [str(row["ticket_id"]) for row in conn.execute(query).mappings()]


def _aggregate_external_close_fills(fills: list[dict[str, Any]]) -> dict[str, Any]:
    total_qty = Decimal("0")
    total_notional = Decimal("0")
    latest_time_ms: int | None = None
    fee_total = Decimal("0")
    fee_currency = ""
    fee_complete = True
    realized_pnl = Decimal("0")
    realized_pnl_complete = True
    for fill in fills:
        qty = _decimal(fill.get("qty"))
        price = _decimal(fill.get("price"))
        total_qty += qty
        total_notional += qty * price
        timestamp_ms = _int_optional(fill.get("timestamp_ms"))
        if timestamp_ms is not None:
            latest_time_ms = max(latest_time_ms or timestamp_ms, timestamp_ms)
        fee = fill.get("fee")
        if isinstance(fee, dict) and fee.get("cost") is not None:
            currency = str(fee.get("currency") or "").upper()
            if fee_currency and currency and currency != fee_currency:
                fee_complete = False
            fee_currency = fee_currency or currency
            fee_total += _decimal(fee.get("cost"))
        elif fee is not None:
            fee_total += _decimal(fee)
        else:
            fee_complete = False
        if fill.get("realized_pnl") is None:
            realized_pnl_complete = False
        else:
            realized_pnl += _decimal(fill.get("realized_pnl"))
    exchange_order_id = str(fills[0].get("exchange_order_id") or "") if fills else ""
    return {
        "exchange_order_id": exchange_order_id,
        "fill_qty": str(total_qty),
        "fill_price": str(total_notional / total_qty) if total_qty > 0 else "",
        "fill_time_ms": latest_time_ms,
        "fee": (
            {"cost": str(fee_total), "currency": fee_currency}
            if fee_complete
            else None
        ),
        "realized_pnl": str(realized_pnl) if realized_pnl_complete else None,
        "reference_price": None,
    }


def _position_flat(position: dict[str, Any]) -> bool:
    if position.get("position_flat") is True:
        return True
    return _decimal(position.get("qty") or position.get("position_qty")) == 0


def _row_by_id(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    id_value: str,
) -> dict[str, Any]:
    if not id_value:
        return {}
    table = _table(conn, table_name)
    row = conn.execute(
        sa.select(table).where(table.c[id_column] == id_value)
    ).mappings().first()
    return dict(row) if row else {}


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _canonical_symbol(value: Any) -> str:
    return str(value or "").upper().replace("/", "").split(":", 1)[0]


def _int_optional(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if str(item)))
