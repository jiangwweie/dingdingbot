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

from src.application.action_time.exchange_order_ownership import (
    classify_exchange_order_ownership,
)
from src.application.action_time.exchange_scope import (
    resolve_ticket_bound_exchange_scope,
)
from src.application.action_time.external_close_attribution import (
    attribute_exact_ticket_bound_external_close,
)
from src.application.action_time.netting_domain_hold import (
    resolve_netting_domain_hold_source,
    upsert_netting_domain_hold,
)
from src.application.action_time.lifecycle_safety_core import (
    classify_protection_reconciliation,
    lifecycle_decision_for_status,
    reduce_lifecycle_decision,
)
from src.domain.ticket_exit_protection import (
    DEFAULT_REPLACEMENT_GRACE_MS,
    order_mapping_for_view,
    resolve_active_exit_protection_rows,
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
    scope_resolution = resolve_ticket_bound_exchange_scope(
        conn,
        ticket_id=str(protection_set.get("ticket_id") or ""),
        now_ms=now_ms,
    )
    if scope_resolution.status != "resolved" or scope_resolution.scope is None:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=list(scope_resolution.blockers),
            protection_set=protection_set,
            lifecycle=lifecycle,
            next_action="repair_ticket_bound_exchange_scope",
    )
    exchange_scope = scope_resolution.scope
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
    raw_position = exchange_snapshot.get("position")
    position_snapshot_missing = not isinstance(raw_position, dict) or not raw_position
    position = dict(raw_position) if isinstance(raw_position, dict) else {}
    position_flat = False if position_snapshot_missing else _position_flat(position)
    position_is_open = not position_flat
    sl_resolution = resolve_active_exit_protection_rows(
        exit_protection_set_id=set_id,
        role="SL",
        orders=orders,
        position_is_open=position_is_open,
        now_ms=now_ms,
        replacement_grace_ms=DEFAULT_REPLACEMENT_GRACE_MS,
    )
    tp1_resolution = resolve_active_exit_protection_rows(
        exit_protection_set_id=set_id,
        role="TP1",
        orders=orders,
        position_is_open=position_is_open,
        now_ms=now_ms,
        replacement_grace_ms=DEFAULT_REPLACEMENT_GRACE_MS,
    )
    runner_resolution = resolve_active_exit_protection_rows(
        exit_protection_set_id=set_id,
        role="RUNNER_SL",
        orders=orders,
        position_is_open=position_is_open,
        now_ms=now_ms,
        replacement_grace_ms=DEFAULT_REPLACEMENT_GRACE_MS,
    )
    sl_order = order_mapping_for_view(
        orders, sl_resolution.active_order or sl_resolution.lineage_leaf
    )
    tp1_order = order_mapping_for_view(
        orders, tp1_resolution.active_order or tp1_resolution.lineage_leaf
    )
    runner_order = order_mapping_for_view(
        orders, runner_resolution.active_order or runner_resolution.lineage_leaf
    )
    resolution_blockers = [
        blocker
        for resolution in (sl_resolution, tp1_resolution, runner_resolution)
        if resolution.fails_closed
        for blocker in resolution.blockers
    ]
    ownership = classify_exchange_order_ownership(
        conn,
        current_scope=exchange_scope,
        open_orders=open_orders,
        now_ms=now_ms,
    )
    ownership_blockers = [
        str(item.blocker)
        for item in ownership
        if item.blocks_current_domain and item.blocker
    ]

    live_protection_orders = _live_protection_orders(open_orders, orders)
    tp1_filled = (
        str(tp1_order.get("status") or "").lower() == "filled"
        or _exchange_order_filled(tp1_order, recent_fills)
    )
    active_sl_order = runner_order if runner_order else sl_order
    if (
        position_flat
        and _exchange_order_filled(active_sl_order, recent_fills)
        and not live_protection_orders
        and not ownership_blockers
    ):
        return _apply_flat_final_exit_reconciliation(
            conn,
            protection_set=protection_set,
            lifecycle=lifecycle,
            orders=orders,
            final_order=active_sl_order,
            exchange_scope=exchange_scope,
            exchange_snapshot=exchange_snapshot,
            now_ms=now_ms,
        )
    conditional_lineage_error = str(
        exchange_snapshot.get("conditional_order_lineage_error") or ""
    ).strip()
    if position_flat and conditional_lineage_error:
        external_close = {}
        external_close_blockers = ["conditional_order_lineage_unavailable"]
    else:
        external_close, external_close_blockers = (
            attribute_exact_ticket_bound_external_close(
                conn,
                lifecycle=lifecycle,
                orders=orders,
                exchange_scope=exchange_scope,
                recent_fills=recent_fills,
                position=position,
            )
        )
    if (
        position_flat
        and external_close
        and not external_close_blockers
        and not live_protection_orders
        and not ownership_blockers
    ):
        return _apply_flat_external_close_reconciliation(
            conn,
            protection_set=protection_set,
            lifecycle=lifecycle,
            orders=orders,
            external_close=external_close,
            exchange_scope=exchange_scope,
            exchange_snapshot=exchange_snapshot,
            now_ms=now_ms,
        )
    ownership_blockers = _dedupe(ownership_blockers + external_close_blockers)
    classification = classify_protection_reconciliation(
        position_qty=position.get("qty") or position.get("position_qty"),
        has_valid_sl=_has_valid_exchange_protection(
            active_sl_order, open_orders, exchange_scope
        ),
        has_valid_tp1=tp1_filled or _has_valid_exchange_protection(
            tp1_order, open_orders, exchange_scope
        ),
        has_runner_sl=_has_valid_exchange_protection(
            runner_order, open_orders, exchange_scope
        ),
        tp1_filled=tp1_filled,
        position_flat=position_flat,
        live_protection_orders=live_protection_orders,
    )
    classification_blockers = (
        ["exchange_position_snapshot_missing"] if position_snapshot_missing else []
    ) + resolution_blockers + list(classification.blockers)

    blockers = _additional_blockers(
        orders=orders,
        open_orders=open_orders,
        recent_fills=recent_fills,
        position=position,
        tp1_filled=tp1_filled,
        active_sl_order=active_sl_order,
        old_sl_order=sl_order,
        tp1_order=tp1_order,
        runner_order=runner_order,
        classification_blockers=classification_blockers,
        ownership_blockers=ownership_blockers,
        exchange_scope=exchange_scope,
    )
    if blockers != classification_blockers:
        classification = classify_protection_reconciliation(
            position_qty=position.get("qty") or position.get("position_qty"),
            has_valid_sl=False
            if any(
                blocker in blockers
                for blocker in ("sl_exchange_order_missing", "runner_sl_exchange_order_missing")
            )
            else _has_valid_exchange_protection(
                active_sl_order, open_orders, exchange_scope
            ),
            has_valid_tp1=False
            if "tp1_exchange_order_missing" in blockers
            else tp1_filled or _has_valid_exchange_protection(
                tp1_order, open_orders, exchange_scope
            ),
            has_runner_sl=_has_valid_exchange_protection(
                runner_order, open_orders, exchange_scope
            ),
            tp1_filled=tp1_filled,
            position_flat=position_flat,
            live_protection_orders=live_protection_orders,
        )
        blockers = _dedupe(
            blockers
            + (
                ["exchange_position_snapshot_missing"]
                if position_snapshot_missing
                else []
            )
            + list(classification.blockers)
        )

    status = classification.status
    next_action = classification.next_action
    if "exchange_position_snapshot_missing" in blockers:
        status = "protection_reconciliation_mismatch"
        next_action = "refresh_exchange_position_snapshot"
    elif ownership_blockers:
        status = "exchange_orphan_detected"
        next_action = "freeze_new_submits_for_scope"
        upsert_netting_domain_hold(
            conn,
            account_id=exchange_scope.account_id,
            runtime_profile_id=exchange_scope.runtime_profile_id,
            exchange_id=exchange_scope.exchange_id,
            exchange_instrument_id=exchange_scope.exchange_instrument_id,
            position_mode=exchange_scope.position_mode,
            position_bucket=exchange_scope.position_bucket,
            netting_domain_key=exchange_scope.netting_domain_key,
            source_ticket_id=exchange_scope.ticket_id,
            strategy_group_id=exchange_scope.strategy_group_id,
            symbol=exchange_scope.canonical_symbol,
            side=exchange_scope.side,
            source_kind="exit_protection_reconciler",
            source_id=set_id,
            blockers=ownership_blockers,
            next_action="reconcile_global_exchange_order_ownership",
            authority_boundary=AUTHORITY_BOUNDARY,
            now_ms=now_ms,
        )
    elif "old_sl_still_live_after_runner_mutation" in blockers:
        status = "runner_reconciliation_mismatch"
        next_action = "cancel_old_sl_or_reconcile_runner_protection"
    elif any(blocker.endswith("_exchange_order_missing") for blocker in blockers):
        status = (
            "runner_reconciliation_mismatch"
            if any(blocker.startswith("runner_sl_") for blocker in blockers)
            else (
                "protection_degraded"
                if any(blocker.startswith("tp1_") for blocker in blockers)
                else "protection_reconciliation_mismatch"
            )
        )
        next_action = (
            "submit_missing_tp1"
            if status == "protection_degraded"
            else "run_exchange_protection_reconciler"
        )
    elif any(
        blocker.endswith("_side_mismatch")
        or blocker.endswith("_reduce_only_missing")
        or blocker.endswith("_reduce_intent_missing")
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
    lifecycle_decision = reduce_lifecycle_decision(
        current_status=str(lifecycle.get("status") or "") if lifecycle else None,
        target_status=success_status if not blockers else status,
        event_type="exit_protection_reconciled" if not blockers else None,
        blockers=blockers,
        next_action=(next_action if blockers else "continue_lifecycle_monitoring"),
    )
    first_blocker = lifecycle_decision.first_blocker
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
        "status": lifecycle_decision.status,
        "first_blocker": first_blocker,
        "blockers": list(lifecycle_decision.blockers),
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
            lifecycle_decision.event_type,
            {
                "blockers": blockers,
                "exchange_snapshot_ref": exchange_snapshot.get("snapshot_id"),
                "lifecycle_status": lifecycle_update["status"],
            },
            now_ms=now_ms,
        )
    if not blockers:
        resolve_netting_domain_hold_source(
            conn,
            netting_domain_key=exchange_scope.netting_domain_key,
            source_kind="exit_protection_reconciler",
            source_id=set_id,
            resolution_source="matched_exit_protection_reconciliation",
            now_ms=now_ms,
        )
    return _result(
        success_set_status if not blockers else status,
        now_ms=now_ms,
        blockers=blockers,
        protection_set=protection_update,
        lifecycle=lifecycle_update,
        next_action=lifecycle_decision.next_action,
        lifecycle_decision=lifecycle_decision,
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
    tp1_order: dict[str, Any],
    runner_order: dict[str, Any],
    classification_blockers: list[str],
    ownership_blockers: list[str],
    exchange_scope: Any,
) -> list[str]:
    blockers = list(classification_blockers) + list(ownership_blockers)
    for role, pg_order in (("SL", active_sl_order), ("TP1", tp1_order)):
        label = "runner_sl" if role == "SL" and pg_order == runner_order else role.lower()
        if role == "TP1" and _exchange_order_filled(pg_order, recent_fills):
            continue
        if not pg_order:
            continue
        exchange_order = _exchange_order_by_id(open_orders, pg_order)
        if not exchange_order:
            blockers.append(f"{label}_exchange_order_missing")
            continue
        if not _exchange_order_proves_reduce_intent(
            exchange_order,
            pg_order=pg_order,
            exchange_scope=exchange_scope,
        ):
            blockers.append(
                f"{label}_reduce_only_missing"
                if exchange_scope.position_mode == "one_way"
                else f"{label}_reduce_intent_missing"
            )
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
    return _dedupe(blockers)


def _apply_flat_final_exit_reconciliation(
    conn: sa.engine.Connection,
    *,
    protection_set: dict[str, Any],
    lifecycle: dict[str, Any],
    orders: list[dict[str, Any]],
    final_order: dict[str, Any],
    exchange_scope: Any,
    exchange_snapshot: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    order_table = _table(conn, "brc_ticket_bound_exit_protection_orders")
    for order in orders:
        if str(order.get("exit_protection_order_id") or "") == str(
            final_order.get("exit_protection_order_id") or ""
        ):
            continue
        if str(order.get("status") or "") in {
            "planned",
            "submitted",
            "open",
            "partially_filled",
            "cancel_pending",
            "replace_pending",
        }:
            conn.execute(
                order_table.update()
                .where(
                    order_table.c.exit_protection_order_id
                    == order["exit_protection_order_id"]
                )
                .values(status="cancelled", updated_at_ms=now_ms)
            )
    protection_update = {
        **protection_set,
        "status": "closed",
        "reconciled_with_exchange": True,
        "first_blocker": None,
        "blockers": [],
        "updated_at_ms": now_ms,
    }
    lifecycle_update = {
        **lifecycle,
        "status": "reconciliation_matched",
        "first_blocker": None,
        "blockers": [],
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        protection_update,
    )
    _upsert_row(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        lifecycle_update,
    )
    _insert_event(
        conn,
        lifecycle_update,
        "reconciliation_matched",
        {
            "final_exit_exchange_order_id": final_order.get("exchange_order_id"),
            "final_exit_role": final_order.get("role"),
            "final_position_flat_confirmed": True,
            "exchange_snapshot_ref": exchange_snapshot.get("snapshot_ref")
            or exchange_snapshot.get("snapshot_id"),
        },
        now_ms=now_ms,
    )
    resolve_netting_domain_hold_source(
        conn,
        netting_domain_key=exchange_scope.netting_domain_key,
        source_kind="exit_protection_reconciler",
        source_id=str(protection_set.get("exit_protection_set_id") or ""),
        resolution_source="flat_final_exit_reconciliation",
        now_ms=now_ms,
    )
    return _result(
        "reconciliation_matched",
        now_ms=now_ms,
        blockers=[],
        protection_set=protection_update,
        lifecycle=lifecycle_update,
        next_action="finalize_ticket_bound_lifecycle",
    )


def _apply_flat_external_close_reconciliation(
    conn: sa.engine.Connection,
    *,
    protection_set: dict[str, Any],
    lifecycle: dict[str, Any],
    orders: list[dict[str, Any]],
    external_close: dict[str, Any],
    exchange_scope: Any,
    exchange_snapshot: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    order_table = _table(conn, "brc_ticket_bound_exit_protection_orders")
    recent_fills = [
        dict(fill)
        for fill in exchange_snapshot.get("recent_fills", [])
        if isinstance(fill, dict)
    ]
    for order in orders:
        if str(order.get("status") or "") not in {
            "planned",
            "submitted",
            "open",
            "partially_filled",
            "cancel_pending",
            "replace_pending",
        }:
            continue
        status = "filled" if _exchange_order_filled(order, recent_fills) else "cancelled"
        conn.execute(
            order_table.update()
            .where(
                order_table.c.exit_protection_order_id
                == order["exit_protection_order_id"]
            )
            .values(status=status, updated_at_ms=now_ms)
        )
    protection_update = {
        **protection_set,
        "status": "closed",
        "reconciled_with_exchange": True,
        "first_blocker": None,
        "blockers": [],
        "updated_at_ms": now_ms,
    }
    lifecycle_update = {
        **lifecycle,
        "status": "reconciliation_matched",
        "first_blocker": None,
        "blockers": [],
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        protection_update,
    )
    _upsert_row(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        lifecycle_update,
    )
    _insert_event(
        conn,
        lifecycle_update,
        "final_exit_detected",
        {"fill": external_close},
        now_ms=now_ms,
    )
    _insert_event(
        conn,
        lifecycle_update,
        "reconciliation_matched",
        {
            "final_exit_exchange_order_id": external_close["exchange_order_id"],
            "final_exit_role": "EXTERNAL_CLOSE",
            "final_position_flat_confirmed": True,
            "external_close_attribution_basis": external_close["attribution_basis"],
            "exchange_snapshot_ref": exchange_snapshot.get("snapshot_ref")
            or exchange_snapshot.get("snapshot_id"),
        },
        now_ms=now_ms + 1,
    )
    resolve_netting_domain_hold_source(
        conn,
        netting_domain_key=exchange_scope.netting_domain_key,
        source_kind="exit_protection_reconciler",
        source_id=str(protection_set.get("exit_protection_set_id") or ""),
        resolution_source="flat_external_close_reconciliation",
        now_ms=now_ms,
    )
    return _result(
        "reconciliation_matched",
        now_ms=now_ms,
        blockers=[],
        protection_set=protection_update,
        lifecycle=lifecycle_update,
        next_action="finalize_ticket_bound_lifecycle",
    )


def _has_valid_exchange_protection(
    pg_order: dict[str, Any],
    open_orders: list[dict[str, Any]],
    exchange_scope: Any,
) -> bool:
    if not pg_order:
        return False
    exchange_order = _exchange_order_by_id(open_orders, pg_order)
    if not exchange_order:
        return False
    if not _exchange_order_proves_reduce_intent(
        exchange_order,
        pg_order=pg_order,
        exchange_scope=exchange_scope,
    ):
        return False
    if not _exchange_order_side_matches_pg(exchange_order, pg_order):
        return False
    return _decimal(exchange_order.get("qty") or exchange_order.get("amount")) > 0


def _exchange_order_proves_reduce_intent(
    exchange_order: dict[str, Any],
    *,
    pg_order: dict[str, Any],
    exchange_scope: Any,
) -> bool:
    if exchange_scope.position_mode == "one_way":
        return (
            exchange_order.get("reduce_only") is True
            or exchange_order.get("close_position") is True
        )
    return (
        str(exchange_order.get("position_side") or "").upper()
        == exchange_scope.position_side
        and _exchange_order_side_matches_pg(exchange_order, pg_order)
    )


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
    return any(
        expected
        in {
            str(fill.get("exchange_order_id") or ""),
            str(fill.get("parent_exchange_order_id") or ""),
        }
        for fill in recent_fills
    )


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
    identity_tail = str(now_ms)
    if event_type == "exit_protection_reconciled":
        identity_tail = _stable_id(
            "reconciliation_state",
            str(payload.get("lifecycle_status") or ""),
            json.dumps(
                payload.get("blockers") or [],
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    event = {
        "lifecycle_event_id": _stable_id(
            "ticket_lifecycle_event",
            str(lifecycle["lifecycle_run_id"]),
            event_type,
            identity_tail,
        ),
        "lifecycle_run_id": str(lifecycle["lifecycle_run_id"]),
        "ticket_id": str(lifecycle["ticket_id"]),
        "protected_submit_attempt_id": str(lifecycle["protected_submit_attempt_id"]),
        "event_type": event_type,
        "event_payload": payload,
        "created_at_ms": now_ms,
    }
    _upsert_row(conn, "brc_ticket_bound_lifecycle_events", "lifecycle_event_id", event)


def _upsert_scope_freeze(
    conn: sa.engine.Connection,
    *,
    protection_set: dict[str, Any],
    source_kind: str,
    source_id: str,
    blockers: list[str],
    now_ms: int,
) -> None:
    freeze_scope = {
        "strategy_group_id": str(protection_set["strategy_group_id"]),
        "symbol": str(protection_set["symbol"]),
        "side": str(protection_set["side"]),
    }
    row = {
        "scope_freeze_id": _stable_id(
            "ticket_scope_freeze",
            freeze_scope["strategy_group_id"],
            freeze_scope["symbol"],
            freeze_scope["side"],
            "active",
        ),
        **freeze_scope,
        "status": "active",
        "source_kind": source_kind,
        "source_id": source_id,
        "first_blocker": blockers[0],
        "blockers": blockers,
        "freeze_scope": freeze_scope,
        "next_action": "notify_owner_and_reconcile_unknown_exchange_order",
        "authority_boundary": AUTHORITY_BOUNDARY,
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }
    _upsert_row(conn, "brc_ticket_bound_scope_freezes", "scope_freeze_id", row)


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
    lifecycle_decision: Any | None = None,
) -> dict[str, Any]:
    decision = lifecycle_decision or lifecycle_decision_for_status(
        str(lifecycle.get("status") or "blocked"),
        blockers=blockers,
        next_action=next_action,
    )
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
        "lifecycle_decision": {
            "status": decision.status,
            "phase": decision.phase.value,
            "protection_state": decision.protection_state.value,
            "reconciliation_state": decision.reconciliation_state.value,
            "control_state": decision.control_state.value,
            "owner_state": decision.owner_state.value,
            "next_action": decision.next_action,
            "owner_action_required": decision.owner_action_required,
        },
        "authority_boundary": AUTHORITY_BOUNDARY,
        "protection_set": protection_set,
        "lifecycle": lifecycle,
    }


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


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
