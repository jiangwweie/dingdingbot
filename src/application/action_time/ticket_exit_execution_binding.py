"""Bind immutable, actual-fill-derived exit execution truth to one Ticket."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import json
from typing import Any, Literal

import sqlalchemy as sa

from src.application.action_time.ticket_exit_policy_binding import (
    initialize_ticket_exit_policy_projection,
)
from src.domain.ticket_exit_policy import (
    TicketExitExecutionSnapshot,
    TicketExitPolicySnapshot,
)


class TicketExitExecutionBindingError(ValueError):
    """Raised when immutable fill-derived exit truth cannot be proved."""


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
    if str(ticket.get("exit_policy_id") or "") == "legacy_unbound":
        raise TicketExitExecutionBindingError("legacy_exit_policy_has_no_execution_binding")
    payload = _mapping(ticket.get("exit_policy_snapshot"))
    try:
        policy = TicketExitPolicySnapshot.model_validate(payload)
    except Exception as exc:
        raise TicketExitExecutionBindingError(
            f"ticket_exit_policy_snapshot_invalid:{type(exc).__name__}"
        ) from exc
    if (
        str(ticket.get("exit_policy_id") or "") != policy.exit_policy_id
        or str(ticket.get("exit_policy_version") or "")
        != policy.exit_policy_version
        or str(ticket.get("exit_policy_hash") or "") != policy.payload_hash
    ):
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
