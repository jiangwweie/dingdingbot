#!/usr/bin/env python3
"""Reconcile ticket-bound protection PG rows against exchange truth snapshots.

The reconciler consumes already-fetched exchange/account facts. It never calls
the exchange, FinalGate, Operation Layer, OrderLifecycle, live profile, sizing,
withdrawal, or transfer paths.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import time
from typing import Any

import sqlalchemy as sa

from src.application.action_time.lifecycle_safety_core import (
    classify_protection_reconciliation,
)


AUTHORITY_BOUNDARY = (
    "ticket_bound_protection_reconciler; PG/exchange snapshot comparison only; "
    "no FinalGate, Operation Layer, exchange mutation, profile, sizing, "
    "withdrawal, or transfer authority"
)


def reconcile_ticket_bound_exit_protection_set(
    conn: sa.engine.Connection,
    *,
    exit_protection_set_id: str,
    exchange_snapshot: dict[str, Any],
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    set_id = str(exit_protection_set_id or "").strip()
    if not set_id:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=["exit_protection_set_id_required"],
            protection_set={},
            lifecycle={},
            next_action="provide_exit_protection_set_id",
        )
    protection_set = _row_by_id(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        set_id,
    )
    if not protection_set:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=["exit_protection_set_missing"],
            protection_set={},
            lifecycle={},
            next_action="repair_ticket_bound_exit_protection_set",
        )
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "ticket_id",
        str(protection_set.get("ticket_id") or ""),
    )
    orders = _orders_for_set(conn, set_id)
    sl_order = _role_order(orders, "SL")
    tp1_order = _role_order(orders, "TP1")
    runner_order = _role_order(orders, "RUNNER_SL")
    open_orders = [
        dict(order)
        for order in exchange_snapshot.get("open_orders", [])
        if isinstance(order, dict)
    ]
    recent_fills = [
        dict(fill)
        for fill in exchange_snapshot.get("recent_fills", [])
        if isinstance(fill, dict)
    ]
    position = dict(exchange_snapshot.get("position") or {})

    live_protection_orders = _live_protection_orders(open_orders, orders)
    tp1_filled = (
        str(tp1_order.get("status") or "").lower() == "filled"
        or _exchange_order_filled(tp1_order, recent_fills)
    )
    active_sl_order = runner_order if runner_order else sl_order
    classification = classify_protection_reconciliation(
        position_qty=position.get("qty") or position.get("position_qty"),
        has_valid_sl=_has_valid_exchange_protection(active_sl_order, open_orders),
        has_valid_tp1=tp1_filled or _has_valid_exchange_protection(tp1_order, open_orders),
        has_runner_sl=_has_valid_exchange_protection(runner_order, open_orders),
        tp1_filled=tp1_filled,
        position_flat=_position_flat(position),
        live_protection_orders=live_protection_orders,
    )

    blockers = _additional_blockers(
        orders=orders,
        open_orders=open_orders,
        recent_fills=recent_fills,
        position=position,
        tp1_filled=tp1_filled,
        active_sl_order=active_sl_order,
        old_sl_order=sl_order,
        runner_order=runner_order,
        classification_blockers=list(classification.blockers),
    )
    if blockers != list(classification.blockers):
        classification = classify_protection_reconciliation(
            position_qty=position.get("qty") or position.get("position_qty"),
            has_valid_sl=False
            if any(
                blocker in blockers
                for blocker in ("sl_exchange_order_missing", "runner_sl_exchange_order_missing")
            )
            else _has_valid_exchange_protection(active_sl_order, open_orders),
            has_valid_tp1=False
            if "tp1_exchange_order_missing" in blockers
            else tp1_filled or _has_valid_exchange_protection(tp1_order, open_orders),
            has_runner_sl=_has_valid_exchange_protection(runner_order, open_orders),
            tp1_filled=tp1_filled,
            position_flat=_position_flat(position),
            live_protection_orders=live_protection_orders,
        )
        blockers = _dedupe(blockers + list(classification.blockers))

    status = classification.status
    next_action = classification.next_action
    if any(blocker == "exchange_protection_order_not_linked_to_pg" for blocker in blockers):
        status = "tp1_or_sl_orphaned"
        next_action = "prove_or_cancel_orphan_protection_order"
    elif "old_sl_still_live_after_runner_mutation" in blockers:
        status = "runner_reconciliation_mismatch"
        next_action = "cancel_old_sl_or_reconcile_runner_protection"
    elif any(blocker.endswith("_exchange_order_missing") for blocker in blockers):
        status = (
            "runner_reconciliation_mismatch"
            if any(blocker.startswith("runner_sl_") for blocker in blockers)
            else "protection_reconciliation_mismatch"
        )
        next_action = "run_exchange_protection_reconciler"
    elif any(
        blocker.endswith("_side_mismatch")
        or blocker.endswith("_reduce_only_missing")
        or blocker.endswith("_qty_exceeds_position")
        for blocker in blockers
    ):
        status = (
            "runner_reconciliation_mismatch"
            if any(blocker.startswith("runner_sl_") for blocker in blockers)
            else "protection_reconciliation_mismatch"
        )
        next_action = "run_exchange_protection_reconciler"
    if blockers and status == "position_protected":
        status = "protection_reconciliation_mismatch"
        next_action = "run_exchange_protection_reconciler"
    success_status = "runner_protected" if runner_order else "position_protected"
    success_set_status = "runner_protected" if runner_order else "reconciled"
    first_blocker = blockers[0] if blockers else None
    protection_update = {
        **protection_set,
        "status": success_set_status if not blockers else status,
        "reconciled_with_exchange": not blockers,
        "first_blocker": first_blocker,
        "blockers": blockers,
        "updated_at_ms": now_ms,
    }
    lifecycle_update = {
        **lifecycle,
        "status": success_status if not blockers else status,
        "first_blocker": first_blocker,
        "blockers": blockers,
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        protection_update,
    )
    if lifecycle:
        _upsert_row(
            conn,
            "brc_ticket_bound_order_lifecycle_runs",
            "lifecycle_run_id",
            lifecycle_update,
        )
        _insert_event(
            conn,
            lifecycle_update,
            "exit_protection_reconciled"
            if not blockers
            else _event_type_for_status(status),
            {
                "blockers": blockers,
                "exchange_snapshot_ref": exchange_snapshot.get("snapshot_id"),
                "lifecycle_status": lifecycle_update["status"],
            },
            now_ms=now_ms,
        )
    return _result(
        success_set_status if not blockers else status,
        now_ms=now_ms,
        blockers=blockers,
        protection_set=protection_update,
        lifecycle=lifecycle_update,
        next_action=next_action if blockers else "continue_lifecycle_monitoring",
    )


def _additional_blockers(
    *,
    orders: list[dict[str, Any]],
    open_orders: list[dict[str, Any]],
    recent_fills: list[dict[str, Any]],
    position: dict[str, Any],
    tp1_filled: bool,
    active_sl_order: dict[str, Any],
    old_sl_order: dict[str, Any],
    runner_order: dict[str, Any],
    classification_blockers: list[str],
) -> list[str]:
    blockers = list(classification_blockers)
    linked_exchange_ids = {
        str(order.get("exchange_order_id") or "")
        for order in orders
        if order.get("exchange_order_id")
    }
    for role, pg_order in (("SL", active_sl_order), ("TP1", _role_order(orders, "TP1"))):
        label = "runner_sl" if role == "SL" and pg_order == runner_order else role.lower()
        if role == "TP1" and _exchange_order_filled(pg_order, recent_fills):
            continue
        if not pg_order:
            continue
        exchange_order = _exchange_order_by_id(open_orders, pg_order)
        if not exchange_order:
            blockers.append(f"{label}_exchange_order_missing")
            continue
        if exchange_order.get("reduce_only") is not True:
            blockers.append(f"{label}_reduce_only_missing")
        if not _exchange_order_side_matches_pg(exchange_order, pg_order):
            blockers.append(f"{label}_side_mismatch")
        if _exchange_order_qty_exceeds_position(
            exchange_order,
            position=position,
            role=role,
            tp1_filled=tp1_filled,
        ):
            blockers.append(f"{label}_qty_exceeds_position")
    if runner_order and _exchange_order_by_id(open_orders, old_sl_order):
        blockers.append("old_sl_still_live_after_runner_mutation")
    for exchange_order in open_orders:
        exchange_order_id = str(exchange_order.get("exchange_order_id") or "")
        if exchange_order.get("reduce_only") is True and exchange_order_id:
            if exchange_order_id not in linked_exchange_ids:
                blockers.append("exchange_protection_order_not_linked_to_pg")
    return _dedupe(blockers)


def _has_valid_exchange_protection(
    pg_order: dict[str, Any],
    open_orders: list[dict[str, Any]],
) -> bool:
    if not pg_order:
        return False
    exchange_order = _exchange_order_by_id(open_orders, pg_order)
    if not exchange_order:
        return False
    if exchange_order.get("reduce_only") is not True:
        return False
    if not _exchange_order_side_matches_pg(exchange_order, pg_order):
        return False
    return _decimal(exchange_order.get("qty") or exchange_order.get("amount")) > 0


def _exchange_order_side_matches_pg(
    exchange_order: dict[str, Any],
    pg_order: dict[str, Any],
) -> bool:
    expected = str(pg_order.get("side") or "").strip().lower()
    observed = str(exchange_order.get("side") or "").strip().lower()
    return bool(expected and observed and expected == observed)


def _exchange_order_qty_exceeds_position(
    exchange_order: dict[str, Any],
    *,
    position: dict[str, Any],
    role: str,
    tp1_filled: bool,
) -> bool:
    position_qty = abs(_decimal(position.get("qty") or position.get("position_qty")))
    if position_qty <= 0:
        return False
    order_qty = abs(_decimal(exchange_order.get("qty") or exchange_order.get("amount")))
    if order_qty <= 0:
        return False
    if role == "TP1":
        return order_qty > position_qty
    if role == "SL" and tp1_filled:
        return False
    return order_qty > position_qty


def _live_protection_orders(
    open_orders: list[dict[str, Any]],
    pg_orders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pg_exchange_ids = {
        str(order.get("exchange_order_id") or "")
        for order in pg_orders
        if order.get("exchange_order_id")
    }
    return [
        order
        for order in open_orders
        if order.get("reduce_only") is True
        or str(order.get("exchange_order_id") or "") in pg_exchange_ids
    ]


def _exchange_order_by_id(
    open_orders: list[dict[str, Any]],
    pg_order: dict[str, Any],
) -> dict[str, Any]:
    expected = str(pg_order.get("exchange_order_id") or "")
    if not expected:
        return {}
    for order in open_orders:
        if str(order.get("exchange_order_id") or "") == expected:
            return dict(order)
    return {}


def _exchange_order_filled(
    pg_order: dict[str, Any],
    recent_fills: list[dict[str, Any]],
) -> bool:
    expected = str(pg_order.get("exchange_order_id") or "")
    if not expected:
        return False
    return any(str(fill.get("exchange_order_id") or "") == expected for fill in recent_fills)


def _position_flat(position: dict[str, Any]) -> bool:
    if position.get("position_flat") is True:
        return True
    return _decimal(position.get("qty") or position.get("position_qty")) == 0


def _orders_for_set(
    conn: sa.engine.Connection,
    exit_protection_set_id: str,
) -> list[dict[str, Any]]:
    table = _table(conn, "brc_ticket_bound_exit_protection_orders")
    return [
        dict(row)
        for row in conn.execute(
            sa.select(table).where(
                table.c.exit_protection_set_id == exit_protection_set_id
            )
        ).mappings()
    ]


def _role_order(orders: list[dict[str, Any]], role: str) -> dict[str, Any]:
    for order in orders:
        if str(order.get("role") or "").upper() == role.upper():
            return dict(order)
    return {}


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


def _insert_event(
    conn: sa.engine.Connection,
    lifecycle: dict[str, Any],
    event_type: str,
    payload: dict[str, Any],
    *,
    now_ms: int,
) -> None:
    event = {
        "lifecycle_event_id": _stable_id(
            "ticket_lifecycle_event",
            str(lifecycle["lifecycle_run_id"]),
            event_type,
            str(now_ms),
        ),
        "lifecycle_run_id": str(lifecycle["lifecycle_run_id"]),
        "ticket_id": str(lifecycle["ticket_id"]),
        "protected_submit_attempt_id": str(lifecycle["protected_submit_attempt_id"]),
        "event_type": event_type,
        "event_payload": payload,
        "created_at_ms": now_ms,
    }
    _upsert_row(conn, "brc_ticket_bound_lifecycle_events", "lifecycle_event_id", event)


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


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _result(
    status: str,
    *,
    now_ms: int,
    blockers: list[str],
    protection_set: dict[str, Any],
    lifecycle: dict[str, Any],
    next_action: str,
) -> dict[str, Any]:
    return {
        "schema": "brc.ticket_bound_protection_reconciler.v1",
        "status": status,
        "now_ms": now_ms,
        "ticket_id": protection_set.get("ticket_id") or lifecycle.get("ticket_id"),
        "exit_protection_set_id": protection_set.get("exit_protection_set_id"),
        "lifecycle_run_id": lifecycle.get("lifecycle_run_id"),
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "next_action": next_action,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "protection_set": protection_set,
        "lifecycle": lifecycle,
    }


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _event_type_for_status(status: str) -> str:
    if status in {
        "protection_missing",
        "protection_reconciliation_mismatch",
        "tp1_or_sl_orphaned",
        "runner_mutation_pending",
        "runner_reconciliation_mismatch",
        "position_closed_protection_live",
    }:
        return status
    return "hard_stopped"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def dumps_json_safe(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True)
