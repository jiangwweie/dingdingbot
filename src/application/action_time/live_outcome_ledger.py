#!/usr/bin/env python3
"""Materialize ticket-bound Live Outcome Ledger rows from PG lifecycle truth."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import time
from typing import Any

import sqlalchemy as sa


AUTHORITY_BOUNDARY = (
    "ticket_bound_live_outcome_ledger; PG ticket/attempt/lifecycle/protection "
    "projection only; governance input only; no FinalGate, Operation Layer, "
    "exchange mutation, profile, sizing, withdrawal, transfer, or submit authority"
)

CLOSED_LIFECYCLE_STATUSES = {
    "budget_settled",
    "review_recorded",
    "lifecycle_closed",
}
RECOVERED_LIFECYCLE_STATUSES = {
    "reconciliation_matched",
    "runner_protected",
}
HARD_BLOCKED_LIFECYCLE_STATUSES = {
    "blocked",
    "entry_unknown",
    "entry_orphaned",
    "entry_partial_fill_unhandled",
    "protection_submit_failed",
    "runner_mutation_failed",
    "runner_reconciliation_mismatch",
    "position_closed_protection_live",
    "final_exit_unknown",
    "settlement_blocked",
    "review_blocked",
}
HARD_BLOCKED_ATTEMPT_STATUSES = {"submit_failed", "hard_stopped"}
DEFECT_STATUSES = HARD_BLOCKED_LIFECYCLE_STATUSES | {
    "protection_missing",
    "protection_degraded",
    "protection_reconciliation_mismatch",
    "exchange_orphan_detected",
}


def materialize_live_outcome_ledger(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    ticket_id = str(ticket_id or "").strip()
    if not ticket_id:
        return _result(
            "blocked",
            now_ms=now_ms,
            outcome={},
            blockers=["ticket_id_required"],
            next_action="provide_ticket_id",
        )

    ticket = _row_by_id(conn, "brc_action_time_tickets", "ticket_id", ticket_id)
    if not ticket:
        return _result(
            "blocked",
            now_ms=now_ms,
            outcome={},
            blockers=["action_time_ticket_missing"],
            next_action="repair_action_time_ticket",
        )

    attempt = _latest_real_attempt(conn, ticket_id)
    if not attempt:
        return _result(
            "not_applicable_no_real_submit",
            now_ms=now_ms,
            outcome={},
            blockers=[],
            next_action="continue_pre_submit_or_disabled_smoke_flow",
        )

    lifecycle = _row_by_id(conn, "brc_ticket_bound_order_lifecycle_runs", "ticket_id", ticket_id)
    if not lifecycle:
        return _result(
            "not_ready_lifecycle_missing",
            now_ms=now_ms,
            outcome={},
            blockers=["ticket_bound_lifecycle_missing"],
            next_action="materialize_ticket_bound_order_lifecycle",
        )

    exposure_episode_id = str(ticket.get("exposure_episode_id") or "").strip()
    episode_blockers = _live_outcome_episode_blockers(
        conn,
        ticket_id=ticket_id,
        expected_episode_id=exposure_episode_id,
    )
    if episode_blockers:
        return _result(
            "blocked_invalid_exposure_episode_lineage",
            now_ms=now_ms,
            outcome={},
            blockers=episode_blockers,
            next_action="repair_live_outcome_exposure_episode_lineage",
        )

    lifecycle_status = str(lifecycle.get("status") or "")
    attempt_status = str(attempt.get("status") or "")
    if lifecycle_status == "lifecycle_closed":
        lineage_blockers = _closed_lifecycle_lineage_blockers(
            conn,
            lifecycle=lifecycle,
            ticket_id=ticket_id,
        )
        if lineage_blockers:
            return _result(
                "blocked_invalid_lifecycle_lineage",
                now_ms=now_ms,
                outcome={},
                blockers=lineage_blockers,
                next_action="repair_lifecycle_closure_lineage",
            )
    outcome_type = _outcome_type(lifecycle_status, attempt_status)
    if not outcome_type:
        return _result(
            "not_ready_lifecycle_active",
            now_ms=now_ms,
            outcome={},
            blockers=[],
            next_action="continue_ticket_bound_lifecycle_monitoring",
        )

    protection_set = _row_by_id(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "ticket_id",
        ticket_id,
    )
    protection_orders = _protection_orders(conn, ticket_id)
    sl = _role_order(protection_orders, "SL")
    tp1 = _role_order(protection_orders, "TP1")
    runner_sl = _role_order(protection_orders, "RUNNER_SL")
    entry_fill = _lifecycle_fill_event(
        conn,
        lifecycle_run_id=str(lifecycle.get("lifecycle_run_id") or ""),
        event_type="entry_filled",
        payload_key="entry_fill",
    )
    tp1_fill = _lifecycle_fill_event(
        conn,
        lifecycle_run_id=str(lifecycle.get("lifecycle_run_id") or ""),
        event_type="tp1_filled",
        payload_key="fill",
    )
    final_fill = _lifecycle_fill_event(
        conn,
        lifecycle_run_id=str(lifecycle.get("lifecycle_run_id") or ""),
        event_type="final_exit_detected",
        payload_key="fill",
    )
    entry_price = _first_positive_decimal(
        entry_fill.get("fill_price"),
        lifecycle.get("entry_avg_price"),
    )
    entry_qty = _first_positive_decimal(
        entry_fill.get("fill_qty"),
        lifecycle.get("entry_filled_qty"),
    )
    entry_time_ms = _positive_int(
        entry_fill.get("fill_time_ms") or entry_fill.get("timestamp_ms")
    )
    stop_price = _decimal(sl.get("trigger_price"))
    risk_at_stop = (
        abs(entry_price - stop_price) * entry_qty
        if entry_price > 0 and stop_price > 0 and entry_qty > 0
        else None
    )
    initial_notional = entry_price * entry_qty if entry_price > 0 and entry_qty > 0 else None
    budget = _row_by_id(
        conn,
        "brc_budget_reservations",
        "budget_reservation_id",
        str(ticket.get("budget_reservation_id") or ""),
    )
    entry_slippage = _entry_slippage(
        side=str(ticket.get("side") or ""),
        reference_price=_positive_decimal(budget.get("entry_reference_price")),
        fill_price=entry_price if entry_price > 0 else None,
        fill_qty=entry_qty if entry_qty > 0 else None,
    )
    tp1_fill_price = _positive_decimal(tp1_fill.get("fill_price"))
    tp1_fill_qty = _positive_decimal(tp1_fill.get("fill_qty"))
    final_exit_price = _positive_decimal(final_fill.get("fill_price"))
    final_exit_qty = _positive_decimal(final_fill.get("fill_qty"))
    final_exit_time_ms = _positive_int(
        final_fill.get("fill_time_ms") or final_fill.get("timestamp_ms")
    )
    realized_pnl = _realized_pnl(
        side=str(ticket.get("side") or ""),
        entry_price=entry_price,
        entry_qty=entry_qty,
        exits=[
            (tp1_fill_price, tp1_fill_qty),
            (final_exit_price, final_exit_qty),
        ],
    )
    known_fill_fees = [entry_fill.get("fee")]
    if tp1_fill:
        known_fill_fees.append(tp1_fill.get("fee"))
    if final_fill:
        known_fill_fees.append(final_fill.get("fee"))
    fees = _compatible_fee_total(
        *known_fill_fees,
        require_all=True,
    )
    funding = _ticket_bound_funding_total(
        final_fill.get("funding_income"),
        ticket_id=ticket_id,
        symbol=str(ticket.get("symbol") or ""),
        entry_time_ms=entry_time_ms,
        final_exit_time_ms=final_exit_time_ms,
        funding_available=final_fill.get("funding_income_available"),
    )
    exit_slippage_parts = [
        _exit_slippage(
            side=str(ticket.get("side") or ""),
            reference_price=_positive_decimal(fill.get("reference_price")),
            fill_price=_positive_decimal(fill.get("fill_price")),
            fill_qty=_positive_decimal(fill.get("fill_qty")),
        )
        for fill in (tp1_fill, final_fill)
    ]
    known_exit_slippage = [item for item in exit_slippage_parts if item is not None]
    exit_slippage = (
        sum(known_exit_slippage, Decimal("0"))
        if known_exit_slippage
        else None
    )
    net_pnl = realized_pnl
    if net_pnl is not None and fees is not None:
        net_pnl -= fees
    if net_pnl is not None and funding is not None:
        net_pnl += funding
    r_multiple = (
        net_pnl / risk_at_stop
        if net_pnl is not None and risk_at_stop is not None and risk_at_stop > 0
        else None
    )
    lifecycle_defects = _lifecycle_defects(lifecycle)
    outcome = {
        "live_outcome_id": _stable_id("live_outcome", ticket_id),
        "ticket_id": ticket_id,
        "exposure_episode_id": exposure_episode_id,
        "protected_submit_attempt_id": str(attempt["protected_submit_attempt_id"]),
        "lifecycle_run_id": lifecycle.get("lifecycle_run_id"),
        "exit_protection_set_id": protection_set.get("exit_protection_set_id"),
        "strategy_group_id": str(ticket["strategy_group_id"]),
        "symbol": str(ticket["symbol"]),
        "side": str(ticket["side"]),
        "runtime_profile_id": str(ticket["runtime_profile_id"]),
        "policy_version_id": str(ticket.get("owner_policy_version") or "") or None,
        "strategy_version_id": str(ticket.get("strategy_group_version_id") or "") or None,
        "signal_event_id": str(ticket.get("signal_event_id") or "") or None,
        "signal_time_ms": ticket.get("event_time_ms"),
        "ticket_created_at_ms": int(ticket.get("created_at_ms") or now_ms),
        "entry_time_ms": entry_time_ms if entry_qty > 0 else None,
        "entry_price": entry_price if entry_price > 0 else None,
        "entry_qty": entry_qty if entry_qty > 0 else None,
        "stop_price": stop_price if stop_price > 0 else None,
        "tp1_price": _positive_decimal(tp1.get("price")),
        "tp1_qty": _positive_decimal(tp1.get("qty")),
        "risk_at_stop": risk_at_stop,
        "initial_notional": initial_notional,
        "leverage": _positive_decimal(ticket.get("leverage")),
        "sl_exchange_order_id": str(sl.get("exchange_order_id") or "") or None,
        "tp1_exchange_order_id": str(tp1.get("exchange_order_id") or "") or None,
        "tp1_fill_time_ms": tp1_fill.get("fill_time_ms"),
        "tp1_fill_price": tp1_fill_price,
        "runner_qty": _positive_decimal(protection_set.get("runner_qty")),
        "runner_sl_price": _positive_decimal(runner_sl.get("trigger_price")),
        "runner_sl_exchange_order_id": str(runner_sl.get("exchange_order_id") or "") or None,
        "final_exit_time_ms": final_exit_time_ms,
        "final_exit_price": final_exit_price,
        "flat_reconciled_at_ms": lifecycle.get("updated_at_ms") if lifecycle_status in CLOSED_LIFECYCLE_STATUSES else None,
        "fees": fees,
        "entry_slippage": entry_slippage,
        "exit_slippage": exit_slippage,
        "funding": funding,
        "realized_pnl": realized_pnl,
        "net_pnl": net_pnl,
        "unrealized_pnl": None,
        "mae": None,
        "mfe": None,
        "r_multiple": r_multiple,
        "stage_reached": lifecycle_status or attempt_status,
        "outcome_type": outcome_type,
        "status": "recorded",
        "first_blocker": lifecycle.get("first_blocker") if lifecycle_defects else None,
        "lifecycle_defects": lifecycle_defects,
        "review_decision": None,
        "review_reason_code": None,
        "reviewed_at_ms": None,
        "review_source": None,
        "source_refs": {
            "ticket_id": ticket_id,
            "protected_submit_attempt_id": str(attempt["protected_submit_attempt_id"]),
            "lifecycle_run_id": lifecycle.get("lifecycle_run_id"),
            "exit_protection_set_id": protection_set.get("exit_protection_set_id"),
            "funding_complete": funding is not None,
            "exit_slippage_complete": exit_slippage is not None,
            "leverage_source": "ticket_selected_leverage",
            "exchange_effective_leverage_known": False,
        },
        "authority_boundary": AUTHORITY_BOUNDARY,
        "created_at_ms": int(_existing_outcome(conn, ticket_id).get("created_at_ms") or now_ms),
        "updated_at_ms": now_ms,
    }
    _upsert_row(conn, "brc_live_outcome_ledger", "live_outcome_id", outcome)
    return _result(
        "recorded",
        now_ms=now_ms,
        outcome=outcome,
        blockers=[],
        next_action="use_live_outcome_for_governance_review_only",
    )


def _live_outcome_episode_blockers(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    expected_episode_id: str,
) -> list[str]:
    if not expected_episode_id:
        return ["live_outcome_exposure_episode_missing"]
    rows = conn.execute(
        sa.text(
            """
            SELECT exposure_episode_id
            FROM brc_ticket_bound_exchange_commands
            WHERE ticket_id = :ticket_id
            ORDER BY operation_submit_command_id, exchange_command_id
            """
        ),
        {"ticket_id": ticket_id},
    ).scalars().all()
    if not rows:
        return ["live_outcome_exchange_command_lineage_missing"]
    if any(str(row or "").strip() != expected_episode_id for row in rows):
        return ["live_outcome_exposure_episode_mismatch"]
    return []


def _latest_real_attempt(conn: sa.engine.Connection, ticket_id: str) -> dict[str, Any]:
    table = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    row = conn.execute(
        sa.select(table)
        .where(table.c.ticket_id == ticket_id)
        .where(table.c.submit_mode == "real_gateway_action")
        .where(table.c.exchange_write_called.is_(True))
        .order_by(table.c.updated_at_ms.desc(), table.c.created_at_ms.desc())
        .limit(1)
    ).mappings().first()
    return dict(row) if row else {}


def _outcome_type(lifecycle_status: str, attempt_status: str) -> str:
    if lifecycle_status in CLOSED_LIFECYCLE_STATUSES:
        return "lifecycle_closed"
    if lifecycle_status in RECOVERED_LIFECYCLE_STATUSES:
        return "recovered_outcome"
    if lifecycle_status in HARD_BLOCKED_LIFECYCLE_STATUSES:
        return "hard_blocked_outcome"
    if attempt_status in HARD_BLOCKED_ATTEMPT_STATUSES:
        return "hard_blocked_outcome"
    return ""


def _lifecycle_defects(lifecycle: dict[str, Any]) -> list[str]:
    defects = [
        str(item)
        for item in _json_list(lifecycle.get("blockers"))
        if str(item or "").strip()
    ]
    status = str(lifecycle.get("status") or "")
    if status in DEFECT_STATUSES:
        defects.insert(0, status)
    first = str(lifecycle.get("first_blocker") or "")
    if first:
        defects.insert(0, first)
    return _dedupe(defects)


def _protection_orders(conn: sa.engine.Connection, ticket_id: str) -> list[dict[str, Any]]:
    if not ticket_id:
        return []
    table = _table(conn, "brc_ticket_bound_exit_protection_orders")
    return [
        dict(row)
        for row in conn.execute(
            sa.select(table).where(table.c.ticket_id == ticket_id)
        ).mappings()
    ]


def _role_order(orders: list[dict[str, Any]], role: str) -> dict[str, Any]:
    for order in orders:
        if str(order.get("role") or "").upper() == role:
            return dict(order)
    return {}


def _existing_outcome(conn: sa.engine.Connection, ticket_id: str) -> dict[str, Any]:
    table = _table(conn, "brc_live_outcome_ledger")
    row = conn.execute(
        sa.select(table).where(table.c.ticket_id == ticket_id)
    ).mappings().first()
    return dict(row) if row else {}


def _lifecycle_fill_event(
    conn: sa.engine.Connection,
    *,
    lifecycle_run_id: str,
    event_type: str,
    payload_key: str,
) -> dict[str, Any]:
    if not lifecycle_run_id:
        return {}
    table = _table(conn, "brc_ticket_bound_lifecycle_events")
    rows = conn.execute(
        sa.select(table)
        .where(
            table.c.lifecycle_run_id == lifecycle_run_id,
            table.c.event_type == event_type,
        )
        .order_by(table.c.created_at_ms.desc())
    ).mappings()
    for row in rows:
        payload = _json_dict(row.get("event_payload"))
        fill = _json_dict(payload.get(payload_key))
        if fill and (
            _positive_decimal(fill.get("fill_price")) is not None
            or _positive_decimal(fill.get("fill_qty")) is not None
        ):
            return fill
    return {}


def _closed_lifecycle_lineage_blockers(
    conn: sa.engine.Connection,
    *,
    lifecycle: dict[str, Any],
    ticket_id: str,
) -> list[str]:
    blockers: list[str] = []
    closure = _row_by_id(
        conn,
        "brc_ticket_bound_post_submit_closures",
        "protected_submit_attempt_id",
        str(lifecycle.get("protected_submit_attempt_id") or ""),
    )
    if str(closure.get("status") or "") != "closed":
        blockers.append("live_outcome_closed_post_submit_closure_missing")
    table = _table(conn, "brc_ticket_bound_lifecycle_events")
    event_types = {
        str(row["event_type"])
        for row in conn.execute(
            sa.select(table.c.event_type).where(
                table.c.lifecycle_run_id == lifecycle.get("lifecycle_run_id"),
                table.c.ticket_id == ticket_id,
                table.c.protected_submit_attempt_id
                == lifecycle.get("protected_submit_attempt_id"),
            )
        ).mappings()
    }
    for event_type in (
        "final_exit_detected",
        "reconciliation_matched",
        "budget_settled",
        "review_recorded",
        "lifecycle_closed",
    ):
        if event_type not in event_types:
            blockers.append(f"live_outcome_lifecycle_event_missing:{event_type}")
    return blockers


def _realized_pnl(
    *,
    side: str,
    entry_price: Decimal,
    entry_qty: Decimal,
    exits: list[tuple[Decimal | None, Decimal | None]],
) -> Decimal | None:
    valid = [(price, qty) for price, qty in exits if price is not None and qty is not None]
    if entry_price <= 0 or entry_qty <= 0 or not valid:
        return None
    exited_qty = sum((qty for _, qty in valid), Decimal("0"))
    if exited_qty <= 0 or exited_qty > entry_qty:
        return None
    if exited_qty != entry_qty:
        return None
    multiplier = Decimal("1") if side == "long" else Decimal("-1")
    return sum(
        ((price - entry_price) * qty * multiplier for price, qty in valid),
        Decimal("0"),
    )


def _compatible_fee_total(
    *fees: Any,
    require_all: bool = False,
) -> Decimal | None:
    parsed: list[tuple[Decimal, str]] = []
    for fee in fees:
        if fee in (None, "", {}):
            if require_all:
                return None
            continue
        if isinstance(fee, dict):
            cost = _positive_or_zero_decimal(fee.get("cost"))
            currency = str(fee.get("currency") or "").upper()
        else:
            cost = _positive_or_zero_decimal(fee)
            currency = ""
        if cost is None:
            return None
        parsed.append((cost, currency))
    if not parsed:
        return None
    currencies = {currency for _, currency in parsed if currency}
    if len(currencies) > 1:
        return None
    return sum((cost for cost, _ in parsed), Decimal("0"))


def _entry_slippage(
    *,
    side: str,
    reference_price: Decimal | None,
    fill_price: Decimal | None,
    fill_qty: Decimal | None,
) -> Decimal | None:
    if not reference_price or not fill_price or not fill_qty:
        return None
    if side == "long":
        return (fill_price - reference_price) * fill_qty
    if side == "short":
        return (reference_price - fill_price) * fill_qty
    return None


def _exit_slippage(
    *,
    side: str,
    reference_price: Decimal | None,
    fill_price: Decimal | None,
    fill_qty: Decimal | None,
) -> Decimal | None:
    if not reference_price or not fill_price or not fill_qty:
        return None
    if side == "long":
        return (reference_price - fill_price) * fill_qty
    if side == "short":
        return (fill_price - reference_price) * fill_qty
    return None


def _ticket_bound_funding_total(
    rows: Any,
    *,
    ticket_id: str,
    symbol: str,
    entry_time_ms: int | None,
    final_exit_time_ms: int | None,
    funding_available: bool | None = None,
) -> Decimal | None:
    if not isinstance(rows, list):
        return None
    if not entry_time_ms or not final_exit_time_ms or final_exit_time_ms < entry_time_ms:
        return None
    if not rows:
        return Decimal("0") if funding_available is True else None
    by_id: dict[str, tuple[Decimal, int]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("ticket_id") or "") != ticket_id:
            continue
        if str(row.get("symbol") or "") != symbol:
            continue
        if str(row.get("income_type") or "").upper() != "FUNDING_FEE":
            continue
        if str(row.get("asset") or "").upper() != "USDT":
            continue
        if str(row.get("attribution_basis") or "") != (
            "single_active_position_exact_symbol_time_window"
        ):
            continue
        timestamp_ms = _positive_int(row.get("timestamp_ms"))
        amount = _decimal_optional(row.get("amount"))
        income_id = str(row.get("income_id") or "").strip()
        if (
            not income_id
            or timestamp_ms is None
            or amount is None
            or timestamp_ms < entry_time_ms
            or timestamp_ms > final_exit_time_ms
        ):
            continue
        value = (amount, timestamp_ms)
        existing = by_id.get(income_id)
        if existing is not None and existing != value:
            return None
        by_id[income_id] = value
    if not by_id:
        return None
    return sum((amount for amount, _ in by_id.values()), Decimal("0"))


def _row_by_id(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    id_value: str,
) -> dict[str, Any]:
    if not id_value:
        return {}
    table = _table(conn, table_name)
    row = conn.execute(sa.select(table).where(table.c[id_column] == id_value)).mappings().first()
    return dict(row) if row else {}


def _upsert_row(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    row: dict[str, Any],
) -> None:
    table = _table(conn, table_name)
    values = {
        column.name: row.get(column.name)
        for column in table.columns
        if column.name in row
    }
    existing = conn.execute(
        sa.select(table.c[id_column]).where(table.c[id_column] == values[id_column])
    ).first()
    if existing:
        conn.execute(
            table.update().where(table.c[id_column] == values[id_column]).values(**values)
        )
    else:
        conn.execute(table.insert().values(**values))


def _result(
    status: str,
    *,
    now_ms: int,
    outcome: dict[str, Any],
    blockers: list[str],
    next_action: str,
) -> dict[str, Any]:
    return {
        "schema": "brc.ticket_bound_live_outcome_ledger.v1",
        "status": status,
        "now_ms": now_ms,
        "ticket_id": outcome.get("ticket_id"),
        "live_outcome_id": outcome.get("live_outcome_id"),
        "outcome_type": outcome.get("outcome_type"),
        "stage_reached": outcome.get("stage_reached"),
        "first_blocker": blockers[0] if blockers else outcome.get("first_blocker"),
        "blockers": blockers,
        "next_action": next_action,
        "exchange_write_called": False,
        "finalgate_called": False,
        "operation_layer_called": False,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "runtime_budget_mutated": False,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "outcome": outcome,
    }


def _positive_decimal(value: Any) -> Decimal | None:
    parsed = _decimal(value)
    return parsed if parsed > 0 else None


def _positive_or_zero_decimal(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _first_positive_decimal(*values: Any) -> Decimal:
    for value in values:
        parsed = _positive_decimal(value)
        if parsed is not None:
            return parsed
    return Decimal("0")


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _decimal_optional(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _positive_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped[:1] == "[":
            loaded = json.loads(stripped)
            if isinstance(loaded, list):
                return [str(item) for item in loaded if str(item or "").strip()]
        return [stripped]
    return [str(value)]


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] == "{":
            loaded = json.loads(stripped)
            return dict(loaded) if isinstance(loaded, dict) else {}
    return {}


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)
