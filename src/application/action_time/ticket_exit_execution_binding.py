"""Bind immutable, actual-fill-derived exit execution truth to one Ticket."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import json
from typing import Any, Literal

import sqlalchemy as sa

from src.application.action_time.ticket_exit_policy_binding import (
    initialize_ticket_exit_policy_projection,
    resolve_effective_ticket_exit_policy_binding,
)
from src.application.action_time.ticket_instrument_rule import (
    TicketInstrumentRuleError,
    resolve_ticket_instrument_rule,
)
from src.domain.ticket_exit_policy import (
    TicketExitExecutionSnapshot,
    TicketExitPolicySnapshot,
)


class TicketExitExecutionBindingError(ValueError):
    """Raised when immutable fill-derived exit truth cannot be proved."""


def recover_ticket_exit_execution_snapshot_from_exchange_truth(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    exchange_snapshot: dict[str, Any] | None,
    now_ms: int,
) -> dict[str, Any]:
    """Recover missing runner truth from durable Ticket state and exchange reads.

    This is a restart/deploy recovery boundary.  It may update only the current
    PG exit-policy projection and never calls an exchange gateway.
    """

    normalized_ticket_id = str(ticket_id or "").strip()
    base = {
        "ticket_id": normalized_ticket_id or None,
        "exchange_read_called": False,
        "exchange_write_called": False,
        "pg_projection_mutated": False,
    }
    if not normalized_ticket_id:
        return _recovery_blocked(base, "ticket_id_required")
    try:
        ticket = _required_row(
            conn,
            "brc_action_time_tickets",
            "ticket_id",
            normalized_ticket_id,
            "action_time_ticket_missing",
        )
        if not _mapping(ticket.get("exit_policy_snapshot")) or not str(
            ticket.get("exit_policy_hash") or ""
        ).strip():
            return {
                **base,
                "status": "execution_recovery_not_applicable",
                "first_blocker": None,
                "blockers": [],
            }
        capability = _optional_row(
            conn,
            "brc_runtime_capabilities_current",
            "capability_id",
            "ticket_exit_policy_v1",
        )
        if str((capability or {}).get("status") or "") != "enabled":
            return {
                **base,
                "status": "execution_recovery_capability_disabled",
                "first_blocker": None,
                "blockers": [],
            }

        projection = _optional_row(
            conn,
            "brc_ticket_exit_policy_current",
            "ticket_id",
            normalized_ticket_id,
        )
        existing_hash = str((projection or {}).get("exit_execution_hash") or "")
        existing_snapshot = _mapping(
            (projection or {}).get("exit_execution_snapshot")
        )
        if existing_hash:
            validated = TicketExitExecutionSnapshot.model_validate(existing_snapshot)
            if validated.payload_hash != existing_hash:
                raise TicketExitExecutionBindingError(
                    "ticket_exit_execution_projection_contradiction"
                )
            tp1_reprice_required = False
            snapshot = dict(exchange_snapshot or {})
            if snapshot:
                base["exchange_read_called"] = (
                    snapshot.get("exchange_read_called") is True
                )
                _require_snapshot_identity(ticket=ticket, snapshot=snapshot)
                instrument = _required_row(
                    conn,
                    "brc_exchange_instruments",
                    "exchange_instrument_id",
                    str(ticket.get("exchange_instrument_id") or ""),
                    "exchange_instrument_missing",
                )
                rule = resolve_ticket_instrument_rule(
                    instrument=instrument,
                    exchange_snapshot=snapshot,
                )
                tp1_reprice_required = _mark_tp1_reprice_if_required(
                    conn,
                    ticket_id=normalized_ticket_id,
                    execution=validated,
                    minimum_price_tick=rule.price_tick,
                    quantity_step=rule.quantity_step,
                    now_ms=int(now_ms),
                )
            return {
                **base,
                "status": "execution_binding_idempotent",
                "first_blocker": None,
                "blockers": [],
                "exit_execution_hash": existing_hash,
                "tp1_reprice_required": tp1_reprice_required,
            }

        snapshot = dict(exchange_snapshot or {})
        if not snapshot:
            raise TicketExitExecutionBindingError("exchange_snapshot_missing")
        base["exchange_read_called"] = snapshot.get("exchange_read_called") is True
        _require_snapshot_identity(ticket=ticket, snapshot=snapshot)

        lifecycle = _required_row(
            conn,
            "brc_ticket_bound_order_lifecycle_runs",
            "ticket_id",
            normalized_ticket_id,
            "ticket_order_lifecycle_missing",
        )
        if lifecycle.get("entry_fill_confirmed") not in {True, 1}:
            raise TicketExitExecutionBindingError("entry_fill_not_confirmed")
        entry_order_id = str(lifecycle.get("entry_exchange_order_id") or "").strip()
        if not entry_order_id:
            raise TicketExitExecutionBindingError("entry_exchange_order_id_missing")

        instrument = _required_row(
            conn,
            "brc_exchange_instruments",
            "exchange_instrument_id",
            str(ticket.get("exchange_instrument_id") or ""),
            "exchange_instrument_missing",
        )
        rule = resolve_ticket_instrument_rule(
            instrument=instrument,
            exchange_snapshot=snapshot,
        )
        entry_execution = _aggregate_entry_fills(
            snapshot.get("recent_fills"),
            entry_exchange_order_id=entry_order_id,
        )
        durable_qty = _required_decimal(
            lifecycle.get("entry_filled_qty"), "entry_filled_qty_missing"
        )
        durable_avg = _required_decimal(
            lifecycle.get("entry_avg_price"), "entry_avg_price_missing"
        )
        if entry_execution["qty"] != durable_qty:
            raise TicketExitExecutionBindingError(
                "entry_fill_quantity_contradicts_lifecycle"
            )
        if abs(entry_execution["avg_price"] - durable_avg) > rule.price_tick:
            raise TicketExitExecutionBindingError(
                "entry_fill_average_contradicts_lifecycle"
            )

        stop_order = _initial_stop_order(conn, normalized_ticket_id)
        initial_stop_price = _required_decimal(
            stop_order.get("trigger_price"), "initial_stop_price_missing"
        )
        commission_rate = _mapping(snapshot.get("commission_rate"))
        if str(commission_rate.get("symbol") or "") != str(ticket.get("symbol") or ""):
            raise TicketExitExecutionBindingError("commission_rate_symbol_mismatch")
        taker_rate = _required_decimal(
            commission_rate.get("taker_commission_rate"),
            "certified_exit_taker_fee_rate_missing",
            allow_zero=True,
        )
        market_rule = _mapping(snapshot.get("market_rule"))
        quote_asset = str(market_rule.get("quote_asset") or "").strip().upper()
        if not quote_asset:
            raise TicketExitExecutionBindingError("quote_asset_identity_missing")

        result = bind_ticket_exit_execution_snapshot(
            conn,
            ticket_id=normalized_ticket_id,
            side=str(ticket.get("side") or ""),
            entry_avg_fill_price=entry_execution["avg_price"],
            entry_filled_qty=entry_execution["qty"],
            initial_stop_price=initial_stop_price,
            minimum_price_tick=rule.price_tick,
            quantity_step=rule.quantity_step,
            entry_fee_amount=entry_execution["fee_amount"],
            entry_fee_asset=entry_execution["fee_asset"],
            quote_asset=quote_asset,
            fee_asset_quote_conversion_rate=(
                _optional_decimal(snapshot.get("fee_asset_quote_conversion_rate"))
            ),
            certified_exit_taker_fee_rate=taker_rate,
            now_ms=int(now_ms),
        )
        execution = TicketExitExecutionSnapshot.model_validate(result["snapshot"])
        tp1_reprice_required = _mark_tp1_reprice_if_required(
            conn,
            ticket_id=normalized_ticket_id,
            execution=execution,
            minimum_price_tick=rule.price_tick,
            quantity_step=rule.quantity_step,
            now_ms=int(now_ms),
        )
        return {
            **base,
            **result,
            "first_blocker": None,
            "blockers": [],
            "pg_projection_mutated": result.get("status") == "execution_bound",
            "tp1_reprice_required": tp1_reprice_required,
            "exchange_write_called": False,
        }
    except Exception as exc:
        if isinstance(exc, TicketExitExecutionBindingError):
            blocker = str(exc)
        elif isinstance(exc, TicketInstrumentRuleError):
            blocker = f"ticket_instrument_rule_invalid:{exc}"
        else:
            blocker = f"ticket_exit_execution_recovery_invalid:{type(exc).__name__}"
        return _recovery_blocked(base, blocker)


def build_ticket_exit_execution_snapshot(
    *,
    ticket_id: str,
    policy: TicketExitPolicySnapshot,
    side: Literal["long", "short"] | str,
    entry_avg_fill_price: Decimal,
    entry_filled_qty: Decimal,
    initial_stop_price: Decimal,
    minimum_price_tick: Decimal,
    quantity_step: Decimal,
    entry_fee_amount: Decimal | None,
    entry_fee_asset: str,
    quote_asset: str,
    fee_asset_quote_conversion_rate: Decimal | None,
    certified_exit_taker_fee_rate: Decimal,
) -> TicketExitExecutionSnapshot:
    """Resolve actual R, exact TP1, quantities, fee allocation, and slippage."""

    _require_decimal(
        entry_avg_fill_price,
        entry_filled_qty,
        initial_stop_price,
        minimum_price_tick,
        quantity_step,
        certified_exit_taker_fee_rate,
    )
    normalized_side = str(side or "").strip().lower()
    if normalized_side not in {"long", "short"}:
        raise TicketExitExecutionBindingError("exit_execution_side_invalid")
    if normalized_side != policy.side:
        raise TicketExitExecutionBindingError("exit_execution_policy_side_mismatch")
    if not str(ticket_id or "").strip():
        raise TicketExitExecutionBindingError("exit_execution_ticket_id_missing")
    if (
        entry_avg_fill_price <= 0
        or entry_filled_qty <= 0
        or initial_stop_price <= 0
        or minimum_price_tick <= 0
        or quantity_step <= 0
    ):
        raise TicketExitExecutionBindingError("exit_execution_fact_non_positive")
    if not Decimal("0") <= certified_exit_taker_fee_rate < Decimal("1"):
        raise TicketExitExecutionBindingError("exit_execution_taker_fee_rate_invalid")
    if normalized_side == "long" and initial_stop_price >= entry_avg_fill_price:
        raise TicketExitExecutionBindingError("exit_execution_long_stop_wrong_side")
    if normalized_side == "short" and initial_stop_price <= entry_avg_fill_price:
        raise TicketExitExecutionBindingError("exit_execution_short_stop_wrong_side")
    if not policy.take_profit_legs:
        raise TicketExitExecutionBindingError("exit_execution_tp1_policy_missing")
    tp1 = next((leg for leg in policy.take_profit_legs if leg.role == "TP1"), None)
    if tp1 is None:
        raise TicketExitExecutionBindingError("exit_execution_tp1_policy_missing")

    actual_r = abs(entry_avg_fill_price - initial_stop_price)
    if actual_r <= 0:
        raise TicketExitExecutionBindingError("exit_execution_actual_r_invalid")
    raw_tp1 = (
        entry_avg_fill_price + (tp1.reward_multiple * actual_r)
        if normalized_side == "long"
        else entry_avg_fill_price - (tp1.reward_multiple * actual_r)
    )
    if raw_tp1 <= 0:
        raise TicketExitExecutionBindingError("exit_execution_tp1_price_invalid")
    resolved_tp1_price = _round_to_step(
        raw_tp1,
        minimum_price_tick,
        rounding=ROUND_CEILING if normalized_side == "long" else ROUND_FLOOR,
    )
    resolved_tp1_target_qty = _round_to_step(
        entry_filled_qty * tp1.quantity_fraction,
        quantity_step,
        rounding=ROUND_FLOOR,
    )
    runner_target_qty = entry_filled_qty - resolved_tp1_target_qty
    if resolved_tp1_target_qty <= 0 or runner_target_qty < 0:
        raise TicketExitExecutionBindingError("exit_execution_quantity_invalid")

    total_entry_fee_quote = _entry_fee_in_quote(
        entry_fee_amount=entry_fee_amount,
        entry_fee_asset=entry_fee_asset,
        quote_asset=quote_asset,
        fee_asset_quote_conversion_rate=fee_asset_quote_conversion_rate,
    )
    allocated_runner_entry_fee = (
        total_entry_fee_quote * runner_target_qty / entry_filled_qty
    )
    floor_rule = policy.post_tp1_floor_rule
    slippage_buffer_quote = (
        Decimal(floor_rule.slippage_buffer_ticks)
        * minimum_price_tick
        * runner_target_qty
        if floor_rule is not None
        else Decimal("0")
    )
    try:
        return TicketExitExecutionSnapshot.with_canonical_hash(
            {
                "ticket_id": str(ticket_id),
                "exit_policy_id": policy.exit_policy_id,
                "exit_policy_version": policy.exit_policy_version,
                "entry_avg_fill_price": entry_avg_fill_price,
                "entry_filled_qty": entry_filled_qty,
                "initial_stop_price": initial_stop_price,
                "actual_r_per_unit": actual_r,
                "resolved_tp1_price": resolved_tp1_price,
                "resolved_tp1_target_qty": resolved_tp1_target_qty,
                "runner_target_qty": runner_target_qty,
                "entry_fee_quote": allocated_runner_entry_fee,
                "certified_exit_taker_fee_rate": certified_exit_taker_fee_rate,
                "slippage_buffer_quote": slippage_buffer_quote,
            }
        )
    except Exception as exc:
        raise TicketExitExecutionBindingError(
            f"exit_execution_snapshot_invalid:{type(exc).__name__}"
        ) from exc


def bind_ticket_exit_execution_snapshot(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    side: Literal["long", "short"] | str,
    entry_avg_fill_price: Decimal,
    entry_filled_qty: Decimal,
    initial_stop_price: Decimal,
    minimum_price_tick: Decimal,
    quantity_step: Decimal,
    entry_fee_amount: Decimal | None,
    entry_fee_asset: str,
    quote_asset: str,
    fee_asset_quote_conversion_rate: Decimal | None,
    certified_exit_taker_fee_rate: Decimal,
    now_ms: int,
) -> dict[str, Any]:
    """Persist one immutable execution snapshot, or prove an idempotent retry."""

    if not sa.inspect(conn).has_table("brc_action_time_tickets"):
        raise TicketExitExecutionBindingError("action_time_ticket_authority_missing")
    tickets = _table(conn, "brc_action_time_tickets")
    ticket_row = conn.execute(
        sa.select(tickets).where(tickets.c.ticket_id == str(ticket_id or ""))
    ).mappings().first()
    if ticket_row is None:
        raise TicketExitExecutionBindingError("action_time_ticket_missing")
    ticket = dict(ticket_row)
    try:
        binding = resolve_effective_ticket_exit_policy_binding(
            conn,
            ticket_id=str(ticket_id),
            now_ms=now_ms,
        )
        if binding.snapshot is None:
            raise TicketExitExecutionBindingError(
                "legacy_exit_policy_has_no_execution_binding"
            )
        policy = binding.snapshot
    except Exception as exc:
        if isinstance(exc, TicketExitExecutionBindingError):
            raise
        raise TicketExitExecutionBindingError(
            f"ticket_exit_policy_snapshot_invalid:{type(exc).__name__}"
        ) from exc
    if binding.exit_policy_hash != policy.payload_hash:
        raise TicketExitExecutionBindingError("ticket_exit_policy_identity_contradiction")

    snapshot = build_ticket_exit_execution_snapshot(
        ticket_id=str(ticket_id),
        policy=policy,
        side=side,
        entry_avg_fill_price=entry_avg_fill_price,
        entry_filled_qty=entry_filled_qty,
        initial_stop_price=initial_stop_price,
        minimum_price_tick=minimum_price_tick,
        quantity_step=quantity_step,
        entry_fee_amount=entry_fee_amount,
        entry_fee_asset=entry_fee_asset,
        quote_asset=quote_asset,
        fee_asset_quote_conversion_rate=fee_asset_quote_conversion_rate,
        certified_exit_taker_fee_rate=certified_exit_taker_fee_rate,
    )
    initialize_ticket_exit_policy_projection(conn, ticket=ticket, now_ms=now_ms)
    projection = _table(conn, "brc_ticket_exit_policy_current")
    current = conn.execute(
        sa.select(projection).where(projection.c.ticket_id == str(ticket_id))
    ).mappings().one()
    existing_hash = str(current.get("exit_execution_hash") or "")
    if existing_hash:
        if existing_hash != snapshot.payload_hash:
            raise TicketExitExecutionBindingError(
                "ticket_exit_execution_binding_contradiction"
            )
        return {
            "status": "execution_binding_idempotent",
            "ticket_id": str(ticket_id),
            "exit_execution_hash": existing_hash,
        }
    conn.execute(
        projection.update()
        .where(projection.c.ticket_id == str(ticket_id))
        .values(
            exit_execution_snapshot=snapshot.model_dump(mode="json"),
            exit_execution_hash=snapshot.payload_hash,
            actual_r_per_unit=snapshot.actual_r_per_unit,
            resolved_tp1_price=snapshot.resolved_tp1_price,
            resolved_tp1_target_qty=snapshot.resolved_tp1_target_qty,
            remaining_position_qty=snapshot.entry_filled_qty,
            state="execution_bound",
            first_blocker=None,
            updated_at_ms=int(now_ms),
        )
    )
    return {
        "status": "execution_bound",
        "ticket_id": str(ticket_id),
        "exit_execution_hash": snapshot.payload_hash,
        "snapshot": snapshot.model_dump(mode="json"),
    }


def _require_snapshot_identity(
    *, ticket: dict[str, Any], snapshot: dict[str, Any]
) -> None:
    expected = {
        "symbol": str(ticket.get("symbol") or ""),
        "exchange_instrument_id": str(ticket.get("exchange_instrument_id") or ""),
    }
    for key, value in expected.items():
        if not value or str(snapshot.get(key) or "") != value:
            raise TicketExitExecutionBindingError(f"exchange_snapshot_{key}_mismatch")
    if snapshot.get("exchange_write_called") is True:
        raise TicketExitExecutionBindingError("exchange_snapshot_write_boundary_invalid")


def _aggregate_entry_fills(
    value: Any,
    *,
    entry_exchange_order_id: str,
) -> dict[str, Any]:
    fills = [
        dict(item)
        for item in (value or [])
        if isinstance(item, dict)
        and str(item.get("exchange_order_id") or "") == entry_exchange_order_id
    ]
    if not fills:
        raise TicketExitExecutionBindingError("entry_exchange_fills_missing")
    total_qty = Decimal("0")
    total_notional = Decimal("0")
    total_fee = Decimal("0")
    fee_asset = ""
    for fill in fills:
        qty = _required_decimal(fill.get("qty"), "entry_fill_qty_invalid")
        price = _required_decimal(fill.get("price"), "entry_fill_price_invalid")
        fee = _mapping(fill.get("fee"))
        fee_amount = _required_decimal(
            fee.get("cost"), "entry_fee_amount_missing", allow_zero=True
        )
        current_fee_asset = str(fee.get("currency") or "").strip().upper()
        if not current_fee_asset:
            raise TicketExitExecutionBindingError("entry_fee_asset_identity_missing")
        if fee_asset and current_fee_asset != fee_asset:
            raise TicketExitExecutionBindingError("entry_fee_asset_not_unique")
        fee_asset = current_fee_asset
        total_qty += qty
        total_notional += qty * price
        total_fee += fee_amount
    if total_qty <= 0:
        raise TicketExitExecutionBindingError("entry_filled_qty_missing")
    return {
        "qty": total_qty,
        "avg_price": total_notional / total_qty,
        "fee_amount": total_fee,
        "fee_asset": fee_asset,
    }


def _initial_stop_order(
    conn: sa.engine.Connection, ticket_id: str
) -> dict[str, Any]:
    orders = _table(conn, "brc_ticket_bound_exit_protection_orders")
    order_by = []
    if "generation" in orders.c:
        order_by.append(orders.c.generation.asc())
    order_by.append(orders.c.created_at_ms.asc())
    row = conn.execute(
        sa.select(orders)
        .where(orders.c.ticket_id == ticket_id)
        .where(orders.c.role == "SL")
        .order_by(*order_by)
        .limit(1)
    ).mappings().first()
    if row is None:
        raise TicketExitExecutionBindingError("initial_stop_order_missing")
    return dict(row)


def _mark_tp1_reprice_if_required(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    execution: TicketExitExecutionSnapshot,
    minimum_price_tick: Decimal,
    quantity_step: Decimal,
    now_ms: int,
) -> bool:
    orders = _table(conn, "brc_ticket_bound_exit_protection_orders")
    rows = list(
        conn.execute(
            sa.select(orders)
            .where(orders.c.ticket_id == ticket_id)
            .where(orders.c.role == "TP1")
            .where(
                orders.c.status.in_(
                    ("planned", "submitted", "open", "partially_filled")
                )
            )
            .order_by(orders.c.generation.desc(), orders.c.updated_at_ms.desc())
        ).mappings()
    )
    if not rows:
        return False
    highest_generation = int(rows[0].get("generation") or 1)
    current = [
        row for row in rows if int(row.get("generation") or 1) == highest_generation
    ]
    if len(current) != 1:
        raise TicketExitExecutionBindingError("active_tp1_order_ambiguous")
    active = current[0]
    current_price = _required_decimal(active.get("price"), "active_tp1_price_missing")
    current_qty = _required_decimal(active.get("qty"), "active_tp1_qty_missing")
    mismatch = (
        abs(current_price - execution.resolved_tp1_price) > minimum_price_tick
        or abs(current_qty - execution.resolved_tp1_target_qty) > quantity_step
    )
    if not mismatch:
        return False
    projection = _table(conn, "brc_ticket_exit_policy_current")
    conn.execute(
        projection.update()
        .where(projection.c.ticket_id == ticket_id)
        .values(
            state="blocked_tp1_reprice_required",
            first_blocker="tp1_reprice_required",
            updated_at_ms=int(now_ms),
        )
    )
    return True


def _required_decimal(
    value: Any,
    blocker: str,
    *,
    allow_zero: bool = False,
) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise TicketExitExecutionBindingError(blocker) from exc
    if not result.is_finite() or result < 0 or (result == 0 and not allow_zero):
        raise TicketExitExecutionBindingError(blocker)
    return result


def _optional_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return _required_decimal(value, "fee_asset_quote_conversion_invalid")


def _required_row(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    id_value: str,
    blocker: str,
) -> dict[str, Any]:
    row = _optional_row(conn, table_name, id_column, id_value)
    if row is None:
        raise TicketExitExecutionBindingError(blocker)
    return row


def _optional_row(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    id_value: str,
) -> dict[str, Any] | None:
    if not sa.inspect(conn).has_table(table_name):
        return None
    table = _table(conn, table_name)
    row = conn.execute(
        sa.select(table).where(table.c[id_column] == id_value)
    ).mappings().first()
    return dict(row) if row is not None else None


def _recovery_blocked(base: dict[str, Any], blocker: str) -> dict[str, Any]:
    normalized = str(blocker or "ticket_exit_execution_recovery_unknown")
    return {
        **base,
        "status": "execution_recovery_blocked",
        "first_blocker": normalized,
        "blockers": [normalized],
        "exchange_write_called": False,
        "pg_projection_mutated": False,
    }


def _entry_fee_in_quote(
    *,
    entry_fee_amount: Decimal | None,
    entry_fee_asset: str,
    quote_asset: str,
    fee_asset_quote_conversion_rate: Decimal | None,
) -> Decimal:
    if entry_fee_amount is None or not isinstance(entry_fee_amount, Decimal):
        raise TicketExitExecutionBindingError("entry_fee_amount_missing")
    if entry_fee_amount < 0:
        raise TicketExitExecutionBindingError("entry_fee_amount_invalid")
    fee_asset = str(entry_fee_asset or "").strip().upper()
    quote = str(quote_asset or "").strip().upper()
    if not fee_asset or not quote:
        raise TicketExitExecutionBindingError("entry_fee_asset_identity_missing")
    if fee_asset == quote:
        return entry_fee_amount
    if (
        fee_asset_quote_conversion_rate is None
        or not isinstance(fee_asset_quote_conversion_rate, Decimal)
        or fee_asset_quote_conversion_rate <= 0
    ):
        raise TicketExitExecutionBindingError("entry_fee_quote_conversion_missing")
    return entry_fee_amount * fee_asset_quote_conversion_rate


def _round_to_step(value: Decimal, step: Decimal, *, rounding: str) -> Decimal:
    return (value / step).to_integral_value(rounding=rounding) * step


def _require_decimal(*values: Any) -> None:
    if any(not isinstance(value, Decimal) for value in values):
        raise TicketExitExecutionBindingError("exit_execution_financial_value_not_decimal")


def _mapping(value: Any) -> dict[str, Any]:
    while isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    return dict(value) if isinstance(value, dict) else {}


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)
