#!/usr/bin/env python3
"""Materialize the first post-submit exchange-truth reconciliation tick."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import time
from typing import Any

import sqlalchemy as sa

from src.application.action_time.exchange_order_ownership import (
    classify_exchange_order_ownership,
    lifecycle_ownership_blockers_after_flat_position,
)
from src.application.action_time.exchange_scope import (
    resolve_ticket_bound_exchange_scope,
)
from src.application.action_time.lifecycle_safety_core import (
    reduce_lifecycle_decision,
)
from src.application.action_time.netting_domain_hold import (
    resolve_netting_domain_hold_source,
    upsert_netting_domain_hold,
)
from src.application.action_time.account_risk_reprojection import (
    reproject_account_risk_current,
)
from src.infrastructure.binance_usdm_account_risk_snapshot import (
    FullAccountRiskSnapshot,
)


AUTHORITY_BOUNDARY = (
    "ticket_bound_first_post_submit_reconciliation_tick; existing PG protected "
    "submit attempt plus optional official exchange read snapshot only; no "
    "FinalGate, Operation Layer, exchange mutation, profile, sizing, "
    "withdrawal, transfer, signal, ticket, or file authority"
)

VISIBILITY_GRACE_MS = 30_000
TERMINAL_ATTEMPT_STATUSES = {"blocked", "hard_stopped"}
FIRST_TICK_KIND = "first_post_submit"
SCHEDULED_TICK_KIND = "scheduled"
RECOVERY_CHECK_TICK_KIND = "recovery_check"
TICK_KINDS = {FIRST_TICK_KIND, SCHEDULED_TICK_KIND, RECOVERY_CHECK_TICK_KIND}


def select_ticket_bound_first_reconciliation_tick_scopes(
    conn: sa.engine.Connection,
    *,
    max_scopes: int,
    now_ms: int | None = None,
) -> list[dict[str, Any]]:
    now_ms = int(now_ms or time.time() * 1000)
    attempts = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    lifecycles = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    query = (
        sa.select(attempts)
        .select_from(
            attempts.outerjoin(
                lifecycles,
                lifecycles.c.ticket_id == attempts.c.ticket_id,
            )
        )
        .where(attempts.c.submit_mode == "real_gateway_action")
        .where(attempts.c.exchange_write_called.is_(True))
        .where(~attempts.c.status.in_(TERMINAL_ATTEMPT_STATUSES))
        .where(
            sa.or_(
                lifecycles.c.ticket_id.is_(None),
                lifecycles.c.status != "lifecycle_closed",
            )
        )
        .order_by(attempts.c.updated_at_ms.asc(), attempts.c.created_at_ms.asc())
        .limit(max(max_scopes * 4, max_scopes))
    )
    scopes: list[dict[str, Any]] = []
    for row in conn.execute(query).mappings():
        tick = _existing_tick(conn, str(row["protected_submit_attempt_id"]), FIRST_TICK_KIND)
        if tick and not _pending_tick_due(tick, now_ms=now_ms):
            continue
        scopes.append(
            {
                "ticket_id": str(row["ticket_id"]),
                "protected_submit_attempt_id": str(row["protected_submit_attempt_id"]),
                "strategy_group_id": str(row["strategy_group_id"]),
                "symbol": str(row["symbol"]),
                "side": str(row["side"]),
                "attempt_status": str(row["status"]),
                "existing_tick_status": str(tick.get("status") or ""),
            }
        )
        if len(scopes) >= max_scopes:
            break
    return scopes


def materialize_ticket_bound_first_reconciliation_tick(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
    exchange_snapshot: dict[str, Any] | None = None,
    account_risk_snapshot: FullAccountRiskSnapshot | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    return materialize_ticket_bound_reconciliation_tick(
        conn,
        protected_submit_attempt_id=protected_submit_attempt_id,
        tick_kind=FIRST_TICK_KIND,
        exchange_snapshot=exchange_snapshot,
        account_risk_snapshot=account_risk_snapshot,
        now_ms=now_ms,
    )


def materialize_ticket_bound_reconciliation_tick(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
    tick_kind: str,
    exchange_snapshot: dict[str, Any] | None = None,
    account_risk_snapshot: FullAccountRiskSnapshot | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    attempt_id = str(protected_submit_attempt_id or "").strip()
    tick_kind = str(tick_kind or "").strip()
    if tick_kind not in TICK_KINDS:
        return _result(
            "blocked",
            now_ms=now_ms,
            tick={},
            blockers=["reconciliation_tick_kind_invalid"],
            next_action="provide_supported_reconciliation_tick_kind",
        )
    if not attempt_id:
        return _result(
            "blocked",
            now_ms=now_ms,
            tick={},
            blockers=["protected_submit_attempt_id_required"],
            next_action="provide_protected_submit_attempt_id",
        )
    attempt = _row_by_id(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        attempt_id,
    )
    if not attempt:
        return _result(
            "blocked",
            now_ms=now_ms,
            tick={},
            blockers=["protected_submit_attempt_missing"],
            next_action="repair_ticket_bound_protected_submit_attempt",
        )
    if str(attempt.get("submit_mode") or "") != "real_gateway_action":
        return _result(
            "not_applicable_disabled_smoke",
            now_ms=now_ms,
            tick={},
            blockers=[],
            next_action="continue_without_exchange_truth_tick",
        )
    if attempt.get("exchange_write_called") is not True:
        return _result(
            "not_applicable_no_exchange_write",
            now_ms=now_ms,
            tick={},
            blockers=[],
            next_action="continue_submit_failure_handling",
        )
    scope_resolution = resolve_ticket_bound_exchange_scope(
        conn,
        ticket_id=str(attempt.get("ticket_id") or ""),
        now_ms=now_ms,
    )
    if scope_resolution.status != "resolved" or scope_resolution.scope is None:
        return _result(
            "blocked",
            now_ms=now_ms,
            tick={},
            blockers=list(scope_resolution.blockers),
            next_action="repair_ticket_bound_exchange_scope",
        )
    exchange_scope = scope_resolution.scope
    episode_blockers = _exchange_command_episode_blockers(
        conn,
        ticket_id=exchange_scope.ticket_id,
        expected_episode_id=exchange_scope.exposure_episode_id,
    )
    if episode_blockers:
        return _result(
            "blocked",
            now_ms=now_ms,
            tick={},
            blockers=episode_blockers,
            next_action="repair_exchange_command_exposure_episode_lineage",
        )

    existing = _existing_tick(conn, attempt_id, tick_kind)
    if tick_kind == FIRST_TICK_KIND and existing and not _pending_tick_due(existing, now_ms=now_ms):
        return _result(
            str(existing.get("status") or "matched"),
            now_ms=now_ms,
            tick=existing,
            blockers=_json_list(existing.get("blockers")),
            next_action=str(existing.get("next_action") or "continue_lifecycle_monitoring"),
            extra={"idempotent_existing_first_reconciliation_tick": True},
        )

    snapshot = dict(exchange_snapshot or {})
    submit_result = _as_dict(attempt.get("submit_result"))
    submitted_orders = [
        dict(order)
        for order in submit_result.get("submitted_orders", [])
        if isinstance(order, dict)
    ]
    submitted_orders = _current_exit_protection_orders(
        conn,
        protected_submit_attempt_id=attempt_id,
        submitted_orders=submitted_orders,
    )
    open_orders = [
        dict(order)
        for order in snapshot.get("open_orders", [])
        if isinstance(order, dict)
    ]
    recent_fills = [
        dict(fill)
        for fill in snapshot.get("recent_fills", [])
        if isinstance(fill, dict)
    ]
    position = snapshot.get("position") if isinstance(snapshot.get("position"), dict) else {}

    entry_order = _order_by_role(submitted_orders, "ENTRY")
    sl_order = _order_by_role(submitted_orders, "SL")
    tp1_order = _order_by_role(submitted_orders, "TP1")
    entry_state = _entry_state(entry_order, open_orders, recent_fills, position)
    sl_state = _protection_state(sl_order, open_orders, recent_fills)
    tp1_state = _protection_state(tp1_order, open_orders, recent_fills)
    position_state = _position_state(position)
    entry_execution = _entry_execution_truth(entry_order, recent_fills)
    if entry_execution:
        attempt = _conserve_entry_execution_truth(
            conn,
            attempt=attempt,
            entry_execution=entry_execution,
            now_ms=now_ms,
        )
    blockers: list[str] = []
    warnings: list[str] = []
    status = "matched"
    next_action = "continue_ticket_bound_lifecycle_monitoring"
    visibility_deadline_ms = int(attempt.get("updated_at_ms") or now_ms) + VISIBILITY_GRACE_MS

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
    external_manual_order_ids: list[str] = []
    if (
        position_state == "flat"
        and entry_state == "filled"
        and position.get("complete") is True
    ):
        ownership_blockers, external_manual_order_ids = (
            lifecycle_ownership_blockers_after_flat_position(
                ownership=ownership,
                open_orders=open_orders,
                current_scope=exchange_scope,
            )
        )
        if external_manual_order_ids:
            warnings.append("external_manual_reduce_only_orders_visible")
    if ownership_blockers:
        blockers.extend(ownership_blockers)
        status = "hard_stopped"
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
            source_kind=f"{tick_kind}_reconciliation_tick",
            source_id=_tick_id(attempt_id, tick_kind),
            blockers=blockers,
            next_action="reconcile_global_exchange_order_ownership",
            authority_boundary=AUTHORITY_BOUNDARY,
            now_ms=now_ms,
        )
    elif position_state == "open" and sl_state == "missing":
        blockers.append("sl_exchange_order_missing")
        status = "recovery_required"
        next_action = "submit_missing_sl"
        _update_lifecycle_if_present(
            conn,
            attempt=attempt,
            status="protection_missing",
            blockers=blockers,
            entry_execution=entry_execution,
            now_ms=now_ms,
        )
    elif position_state == "open" and sl_state == "open" and tp1_state == "missing":
        blockers.append("tp1_exchange_order_missing")
        status = "recovery_required"
        next_action = "submit_missing_tp1"
        _update_lifecycle_if_present(
            conn,
            attempt=attempt,
            status="protection_degraded",
            blockers=blockers,
            entry_execution=entry_execution,
            now_ms=now_ms,
        )
    elif not snapshot:
        blockers.append("exchange_snapshot_missing_for_first_tick")
        status = "pending_visibility"
        next_action = "collect_exchange_snapshot"
    elif entry_state in {"missing", "unknown"} and now_ms < visibility_deadline_ms:
        warnings.append("exchange_visibility_grace_active")
        status = "pending_visibility"
        next_action = "wait_for_exchange_visibility_or_refresh_snapshot"
    elif entry_state in {"missing", "unknown"}:
        blockers.append("entry_exchange_state_unknown")
        status = "mismatch"
        next_action = "query_by_client_order_id"
        _update_lifecycle_if_present(
            conn,
            attempt=attempt,
            status="entry_unknown",
            blockers=blockers,
            now_ms=now_ms,
        )
    elif status == "matched":
        resolve_netting_domain_hold_source(
            conn,
            netting_domain_key=exchange_scope.netting_domain_key,
            source_kind=f"{tick_kind}_reconciliation_tick",
            source_id=_tick_id(attempt_id, tick_kind),
            resolution_source="matched_post_submit_reconciliation_tick",
            now_ms=now_ms,
        )

    tick = {
        "reconciliation_tick_id": _tick_id(attempt_id, tick_kind),
        "ticket_id": str(attempt["ticket_id"]),
        "exposure_episode_id": exchange_scope.exposure_episode_id,
        "protected_submit_attempt_id": attempt_id,
        "tick_kind": tick_kind,
        "status": status,
        "strategy_group_id": str(attempt["strategy_group_id"]),
        "symbol": str(attempt["symbol"]),
        "side": str(attempt["side"]),
        "entry_state": entry_state,
        "sl_state": sl_state,
        "tp1_state": tp1_state,
        "position_state": position_state,
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "warnings": warnings,
        "next_action": next_action,
        "exchange_snapshot_ref": snapshot.get("snapshot_id"),
        "exchange_snapshot_summary": _snapshot_summary(snapshot),
        "visibility_deadline_ms": visibility_deadline_ms,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "created_at_ms": int(existing.get("created_at_ms") or now_ms),
        "updated_at_ms": now_ms,
    }
    _upsert_row(conn, "brc_ticket_bound_reconciliation_ticks", "reconciliation_tick_id", tick)
    account_risk_reprojection: dict[str, Any] = {}
    # Account Current is a projection of each complete fresh account snapshot,
    # not a side effect of lifecycle-state changes.  Lifecycle semantics still
    # control lifecycle audit/event mutation below.
    if account_risk_snapshot is not None:
        account_risk_reprojection = reproject_account_risk_current(
            conn,
            snapshot=account_risk_snapshot,
            runtime_profile_id=exchange_scope.runtime_profile_id,
            now_ms=now_ms,
        ).model_dump()
    return _result(
        status,
        now_ms=now_ms,
        tick=tick,
        blockers=blockers,
        next_action=next_action,
        extra={"account_risk_reprojection": account_risk_reprojection},
    )


def _exchange_command_episode_blockers(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    expected_episode_id: str,
) -> list[str]:
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
        return ["post_submit_exchange_command_lineage_missing"]
    if any(str(row or "").strip() != expected_episode_id for row in rows):
        return ["post_submit_exposure_episode_mismatch"]
    return []


def _entry_state(
    entry_order: dict[str, Any],
    open_orders: list[dict[str, Any]],
    recent_fills: list[dict[str, Any]],
    position: dict[str, Any],
) -> str:
    if not entry_order:
        return "missing"
    status = str(entry_order.get("status") or "").lower()
    if status in {"filled", "closed"} or _exchange_order_filled(entry_order, recent_fills):
        return "filled"
    if _decimal(entry_order.get("filled_qty")) > 0:
        return "filled"
    if _position_state(position) == "open":
        return "filled"
    if _exchange_order_by_id(open_orders, entry_order):
        return "accepted"
    if status in {"rejected", "failed", "canceled", "cancelled", "expired"}:
        return "rejected"
    return "unknown"


def _protection_state(
    order: dict[str, Any],
    open_orders: list[dict[str, Any]],
    recent_fills: list[dict[str, Any]],
) -> str:
    if not order or not str(order.get("exchange_order_id") or "").strip():
        return "missing"
    if _exchange_order_filled(order, recent_fills):
        return "filled"
    if _exchange_order_by_id(open_orders, order):
        return "open"
    return "missing"


def _position_state(position: dict[str, Any]) -> str:
    if not position:
        return "unknown"
    if position.get("position_flat") is True:
        return "flat"
    return "open" if _decimal(position.get("qty") or position.get("position_qty")) > 0 else "flat"


def _entry_execution_truth(
    entry_order: dict[str, Any],
    recent_fills: list[dict[str, Any]],
) -> dict[str, Any]:
    exchange_order_id = str(entry_order.get("exchange_order_id") or "").strip()
    if not exchange_order_id:
        return {}
    matching_fills = [
        fill
        for fill in recent_fills
        if str(fill.get("exchange_order_id") or "") == exchange_order_id
    ]
    if not matching_fills:
        return {}
    total_qty = Decimal("0")
    total_notional = Decimal("0")
    fill_time_ms: int | None = None
    fee: Any = None
    for fill in matching_fills:
        qty = _decimal(fill.get("qty"))
        price = _decimal(fill.get("price"))
        if qty <= 0 or price <= 0:
            return {}
        total_qty += qty
        total_notional += qty * price
        if fee is None and fill.get("fee") is not None:
            fee = fill.get("fee")
        timestamp_ms = _int_optional(fill.get("timestamp_ms"))
        if timestamp_ms is not None:
            fill_time_ms = max(fill_time_ms or timestamp_ms, timestamp_ms)
    return {
        "exchange_order_id": exchange_order_id,
        "filled_qty": str(total_qty),
        "average_exec_price": str(total_notional / total_qty),
        "fee": fee,
        "fill_time_ms": fill_time_ms,
    }


def _conserve_entry_execution_truth(
    conn: sa.engine.Connection,
    *,
    attempt: dict[str, Any],
    entry_execution: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    submit_result = _as_dict(attempt.get("submit_result"))
    submitted_orders = [
        dict(order)
        for order in submit_result.get("submitted_orders", [])
        if isinstance(order, dict)
    ]
    repaired = False
    for order in submitted_orders:
        if str(order.get("order_role") or "").upper() != "ENTRY":
            continue
        if str(order.get("exchange_order_id") or "") != str(
            entry_execution["exchange_order_id"]
        ):
            continue
        order.update(
            {
                "status": "FILLED",
                "filled_qty": entry_execution["filled_qty"],
                "average_exec_price": entry_execution["average_exec_price"],
                "fee": entry_execution.get("fee"),
                "fill_time_ms": entry_execution.get("fill_time_ms"),
            }
        )
        repaired = True
        break
    if not repaired:
        return attempt
    updated = {
        **attempt,
        "submit_result": {**submit_result, "submitted_orders": submitted_orders},
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        updated,
    )
    return updated


def _unknown_exchange_reduce_only_order(
    open_orders: list[dict[str, Any]],
    submitted_orders: list[dict[str, Any]],
) -> dict[str, Any]:
    submitted_exchange_ids = {
        str(order.get("exchange_order_id") or "")
        for order in submitted_orders
        if order.get("exchange_order_id")
    }
    for order in open_orders:
        exchange_order_id = str(order.get("exchange_order_id") or "")
        if order.get("reduce_only") is True and exchange_order_id:
            if exchange_order_id not in submitted_exchange_ids:
                return dict(order)
    return {}


def _update_lifecycle_if_present(
    conn: sa.engine.Connection,
    *,
    attempt: dict[str, Any],
    status: str,
    blockers: list[str],
    entry_execution: dict[str, Any] | None = None,
    now_ms: int,
) -> None:
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "ticket_id",
        str(attempt.get("ticket_id") or ""),
    )
    if not lifecycle:
        return
    decision = reduce_lifecycle_decision(
        current_status=str(lifecycle.get("status") or ""),
        target_status=status,
        blockers=blockers,
    )
    updated = {
        **lifecycle,
        "status": decision.status,
        "first_blocker": decision.first_blocker,
        "blockers": list(decision.blockers),
        "updated_at_ms": now_ms,
    }
    entry_execution = entry_execution or {}
    if entry_execution:
        updated.update(
            {
                "entry_exchange_order_id": entry_execution["exchange_order_id"],
                "entry_fill_confirmed": True,
                "entry_filled_qty": _decimal(entry_execution["filled_qty"]),
                "entry_avg_price": _decimal(
                    entry_execution["average_exec_price"]
                ),
            }
        )
    _upsert_row(conn, "brc_ticket_bound_order_lifecycle_runs", "lifecycle_run_id", updated)


def _upsert_scope_freeze(
    conn: sa.engine.Connection,
    *,
    attempt: dict[str, Any],
    source_kind: str,
    source_id: str,
    blockers: list[str],
    now_ms: int,
) -> None:
    freeze_scope = {
        "strategy_group_id": str(attempt["strategy_group_id"]),
        "symbol": str(attempt["symbol"]),
        "side": str(attempt["side"]),
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


def _snapshot_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    if not snapshot:
        return {}
    return {
        "snapshot_id": snapshot.get("snapshot_id"),
        "symbol": snapshot.get("symbol"),
        "open_order_count": len(snapshot.get("open_orders") or []),
        "recent_fill_count": len(snapshot.get("recent_fills") or []),
        "position_state": _position_state(
            snapshot.get("position") if isinstance(snapshot.get("position"), dict) else {}
        ),
        "account_exposure": (
            dict(snapshot.get("account_exposure"))
            if isinstance(snapshot.get("account_exposure"), dict)
            else {}
        ),
        "fetched_at_ms": snapshot.get("fetched_at_ms"),
    }


def _tick_semantics_changed(existing: dict[str, Any], tick: dict[str, Any]) -> bool:
    """Only lifecycle semantic transitions may trigger a capacity reprojection."""

    if not existing:
        return True
    keys = (
        "status",
        "entry_state",
        "sl_state",
        "tp1_state",
        "position_state",
        "first_blocker",
        "blockers",
    )
    return any(existing.get(key) != tick.get(key) for key in keys)


def _existing_tick(
    conn: sa.engine.Connection,
    attempt_id: str,
    tick_kind: str,
) -> dict[str, Any]:
    table = _table(conn, "brc_ticket_bound_reconciliation_ticks")
    row = conn.execute(
        sa.select(table)
        .where(table.c.protected_submit_attempt_id == attempt_id)
        .where(table.c.tick_kind == tick_kind)
    ).mappings().first()
    return dict(row) if row else {}


def _pending_tick_due(tick: dict[str, Any], *, now_ms: int) -> bool:
    return (
        str(tick.get("status") or "") == "pending_visibility"
        and int(tick.get("visibility_deadline_ms") or 0) <= now_ms
    )


def _order_by_role(orders: list[dict[str, Any]], role: str) -> dict[str, Any]:
    # Protection replacements are appended to the durable submit result.  A
    # scheduled reconciliation must compare the exchange snapshot with the
    # newest role lineage, not the original order that a later policy action
    # has already replaced.
    for order in reversed(orders):
        if str(order.get("order_role") or "").upper() == role:
            return dict(order)
    return {}


def _current_exit_protection_orders(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
    submitted_orders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prefer the current PG protection lineage over historical submit rows.

    Exit-policy reprices and recovery attempts append history to the protected
    submit result.  The exit-protection projection is the current authority for
    active SL/TP1 exchange IDs, so scheduled reconciliation must use it when
    it exists.
    """

    inspector = sa.inspect(conn)
    required_tables = {
        "brc_ticket_bound_exit_protection_sets",
        "brc_ticket_bound_exit_protection_orders",
    }
    if not all(inspector.has_table(table) for table in required_tables):
        return submitted_orders

    protection_sets = _table(conn, "brc_ticket_bound_exit_protection_sets")
    protection_orders = _table(conn, "brc_ticket_bound_exit_protection_orders")
    protection_set = conn.execute(
        sa.select(protection_sets.c.exit_protection_set_id)
        .where(
            protection_sets.c.protected_submit_attempt_id
            == str(protected_submit_attempt_id)
        )
        .order_by(protection_sets.c.updated_at_ms.desc())
        .limit(1)
    ).mappings().first()
    if not protection_set:
        return submitted_orders

    rows = conn.execute(
        sa.select(protection_orders)
        .where(
            protection_orders.c.exit_protection_set_id
            == str(protection_set["exit_protection_set_id"])
        )
        .where(protection_orders.c.role.in_(("SL", "TP1")))
        .where(protection_orders.c.status != "replaced")
        .order_by(
            protection_orders.c.role.asc(),
            protection_orders.c.generation.desc(),
            protection_orders.c.updated_at_ms.desc(),
        )
    ).mappings()
    current_by_role: dict[str, dict[str, Any]] = {}
    for row in rows:
        role = str(row.get("role") or "").upper()
        if role in current_by_role or not str(row.get("exchange_order_id") or "").strip():
            continue
        current_by_role[role] = {
            "order_role": role,
            "exchange_order_id": str(row["exchange_order_id"]),
            "status": str(row.get("status") or ""),
            "amount": row.get("qty"),
            "price": row.get("price"),
            "trigger_price": row.get("trigger_price"),
            "reduce_only": row.get("reduce_only"),
        }
    if not current_by_role:
        return submitted_orders
    historical = [
        order
        for order in submitted_orders
        if str(order.get("order_role") or "").upper() not in current_by_role
    ]
    return [*historical, *current_by_role.values()]


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
    tick: dict[str, Any],
    blockers: list[str],
    next_action: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "brc.ticket_bound_first_post_submit_reconciliation_tick.v1",
        "status": status,
        "now_ms": now_ms,
        "ticket_id": tick.get("ticket_id"),
        "protected_submit_attempt_id": tick.get("protected_submit_attempt_id"),
        "reconciliation_tick_id": tick.get("reconciliation_tick_id"),
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "next_action": next_action,
        "tick": tick,
        "exchange_read_called": False,
        "exchange_write_called": False,
        "finalgate_called": False,
        "operation_layer_called": False,
        "authority_boundary": AUTHORITY_BOUNDARY,
        **(extra or {}),
    }


def _tick_id(attempt_id: str, tick_kind: str = FIRST_TICK_KIND) -> str:
    return _stable_id("ticket_reconciliation_tick", attempt_id, tick_kind)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


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


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value[:1] == "{":
        loaded = json.loads(value)
        return dict(loaded) if isinstance(loaded, dict) else {}
    return {}


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _int_optional(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)
