#!/usr/bin/env python3
"""Bounded scheduler runner for ticket-bound lifecycle maintenance."""

from __future__ import annotations

import time
from typing import Any

import sqlalchemy as sa

from src.application.action_time.exchange_snapshot_provider import (
    fetch_ticket_bound_attempt_exchange_snapshot,
    fetch_ticket_bound_exchange_snapshot,
)
from src.application.action_time.lifecycle_maintenance_service import (
    run_ticket_bound_lifecycle_maintenance,
)
from src.application.action_time.post_submit_reconciliation_tick import (
    materialize_ticket_bound_first_reconciliation_tick,
    materialize_ticket_bound_reconciliation_tick,
    select_ticket_bound_first_reconciliation_tick_scopes,
)


AUTHORITY_BOUNDARY = (
    "ticket_bound_lifecycle_maintenance_scheduler; PG-selected existing "
    "ticket-bound lifecycle scopes only; exchange reads only for selected open "
    "protection sets; optional exchange mutation delegated to maintenance "
    "service only when explicitly enabled; no signal, ticket, FinalGate, "
    "Operation Layer, profile, sizing, withdrawal, transfer, or file authority"
)

MAINTAINABLE_LIFECYCLE_STATUSES = {
    "position_protected",
    "tp1_filled",
    "runner_mutation_pending",
    "protection_missing",
    "protection_degraded",
    "protection_submit_failed",
    "protection_reconciliation_mismatch",
    "exchange_orphan_detected",
    "runner_mutation_failed",
    "runner_reconciliation_mismatch",
    "position_closed_protection_live",
}
SNAPSHOT_STATUSES = {
    "position_protected",
    "protection_degraded",
    "tp1_filled",
    "runner_mutation_pending",
    "protection_reconciliation_mismatch",
    "exchange_orphan_detected",
    "runner_reconciliation_mismatch",
    "position_closed_protection_live",
}


async def run_ticket_bound_lifecycle_maintenance_scheduler(
    conn: sa.engine.Connection,
    *,
    gateway: Any = None,
    allow_exchange_mutation: bool = False,
    fetch_exchange_snapshot: bool = True,
    max_lifecycle_scopes: int = 4,
    max_actions_per_scope: int = 16,
    snapshot_timeout_seconds: float = 8.0,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    first_tick_scopes = select_ticket_bound_first_reconciliation_tick_scopes(
        conn,
        max_scopes=max_lifecycle_scopes,
        now_ms=now_ms,
    )
    scopes = select_ticket_bound_lifecycle_maintenance_scopes(
        conn,
        max_lifecycle_scopes=max_lifecycle_scopes,
    )
    first_tick_attempt_ids = {
        str(scope.get("protected_submit_attempt_id") or "")
        for scope in first_tick_scopes
        if scope.get("protected_submit_attempt_id")
    }
    if first_tick_attempt_ids:
        scopes = [
            scope
            for scope in scopes
            if str(scope.get("protected_submit_attempt_id") or "")
            not in first_tick_attempt_ids
        ]
    if not first_tick_scopes and not scopes:
        return _result(
            "no_maintainable_lifecycle",
            now_ms=now_ms,
            scopes=[],
            runs=[],
            blockers=[],
            exchange_read_called=False,
            exchange_write_called=False,
        )

    runs: list[dict[str, Any]] = []
    blockers: list[str] = []
    exchange_read_called = False
    exchange_write_called = False
    for index, scope in enumerate(first_tick_scopes):
        snapshot_payload: dict[str, Any] = {}
        exchange_snapshot: dict[str, Any] | None = None
        if fetch_exchange_snapshot and gateway is not None:
            snapshot_payload = await fetch_ticket_bound_attempt_exchange_snapshot(
                conn,
                protected_submit_attempt_id=str(scope["protected_submit_attempt_id"]),
                gateway=gateway,
                timeout_seconds=snapshot_timeout_seconds,
                now_ms=now_ms + index,
            )
            exchange_read_called = (
                exchange_read_called or snapshot_payload.get("exchange_read_called") is True
            )
            if snapshot_payload.get("status") == "snapshot_ready":
                exchange_snapshot = dict(snapshot_payload.get("snapshot") or {})
            else:
                blockers.extend(_result_blockers(snapshot_payload))
        elif fetch_exchange_snapshot and gateway is None:
            blockers.append("exchange_snapshot_gateway_required")

        tick = materialize_ticket_bound_first_reconciliation_tick(
            conn,
            protected_submit_attempt_id=str(scope["protected_submit_attempt_id"]),
            exchange_snapshot=exchange_snapshot,
            now_ms=now_ms + index + 25,
        )
        blockers.extend(_result_blockers(tick))
        maintenance = await run_ticket_bound_lifecycle_maintenance(
            conn,
            ticket_id=str(scope.get("ticket_id") or ""),
            protected_submit_attempt_id=str(scope.get("protected_submit_attempt_id") or ""),
            exchange_snapshot=exchange_snapshot,
            gateway=gateway,
            allow_exchange_mutation=allow_exchange_mutation,
            max_actions=max_actions_per_scope,
            now_ms=now_ms + index + 100,
        )
        blockers.extend(_result_blockers(maintenance))
        exchange_write_called = (
            exchange_write_called or maintenance.get("exchange_write_called") is True
        )
        runs.append(
            {
                "scope": {**scope, "scheduler_scope_kind": "first_post_submit"},
                "snapshot": _summary(snapshot_payload),
                "first_tick": _summary(tick),
                "maintenance": _summary(maintenance),
                "actions": list(maintenance.get("actions") or []),
            }
        )

    for index, scope in enumerate(scopes):
        snapshot_payload: dict[str, Any] = {}
        exchange_snapshot: dict[str, Any] | None = None
        if (
            fetch_exchange_snapshot
            and gateway is not None
            and scope.get("exit_protection_set_id")
            and str(scope.get("lifecycle_status") or "") in SNAPSHOT_STATUSES
        ):
            snapshot_payload = await fetch_ticket_bound_exchange_snapshot(
                conn,
                exit_protection_set_id=str(scope["exit_protection_set_id"]),
                gateway=gateway,
                timeout_seconds=snapshot_timeout_seconds,
                now_ms=now_ms + index,
            )
            exchange_read_called = (
                exchange_read_called or snapshot_payload.get("exchange_read_called") is True
            )
            if snapshot_payload.get("status") == "snapshot_ready":
                exchange_snapshot = dict(snapshot_payload.get("snapshot") or {})
            else:
                blockers.extend(_result_blockers(snapshot_payload))
        elif (
            fetch_exchange_snapshot
            and scope.get("exit_protection_set_id")
            and str(scope.get("lifecycle_status") or "") in SNAPSHOT_STATUSES
            and gateway is None
        ):
            blockers.append("exchange_snapshot_gateway_required")

        scheduled_tick: dict[str, Any] = {}
        if exchange_snapshot and scope.get("protected_submit_attempt_id"):
            scheduled_tick = materialize_ticket_bound_reconciliation_tick(
                conn,
                protected_submit_attempt_id=str(scope["protected_submit_attempt_id"]),
                tick_kind="scheduled",
                exchange_snapshot=exchange_snapshot,
                now_ms=now_ms + index + 50,
            )
            blockers.extend(_result_blockers(scheduled_tick))

        maintenance = await run_ticket_bound_lifecycle_maintenance(
            conn,
            ticket_id=str(scope.get("ticket_id") or ""),
            protected_submit_attempt_id=str(scope.get("protected_submit_attempt_id") or ""),
            exit_protection_set_id=str(scope.get("exit_protection_set_id") or ""),
            exchange_snapshot=exchange_snapshot,
            gateway=gateway,
            allow_exchange_mutation=allow_exchange_mutation,
            max_actions=max_actions_per_scope,
            now_ms=now_ms + index + 100,
        )
        blockers.extend(_result_blockers(maintenance))
        exchange_write_called = (
            exchange_write_called or maintenance.get("exchange_write_called") is True
        )
        post_recovery_snapshot_payload: dict[str, Any] = {}
        recovery_check_tick: dict[str, Any] = {}
        if (
            fetch_exchange_snapshot
            and gateway is not None
            and scope.get("exit_protection_set_id")
            and scope.get("protected_submit_attempt_id")
            and _maintenance_executed_exchange_mutation(maintenance)
        ):
            post_recovery_snapshot_payload = await fetch_ticket_bound_exchange_snapshot(
                conn,
                exit_protection_set_id=str(scope["exit_protection_set_id"]),
                gateway=gateway,
                timeout_seconds=snapshot_timeout_seconds,
                now_ms=now_ms + index + 125,
            )
            exchange_read_called = (
                exchange_read_called
                or post_recovery_snapshot_payload.get("exchange_read_called") is True
            )
            if post_recovery_snapshot_payload.get("status") == "snapshot_ready":
                recovery_check_tick = materialize_ticket_bound_reconciliation_tick(
                    conn,
                    protected_submit_attempt_id=str(scope["protected_submit_attempt_id"]),
                    tick_kind="recovery_check",
                    exchange_snapshot=dict(post_recovery_snapshot_payload.get("snapshot") or {}),
                    now_ms=now_ms + index + 150,
                )
                blockers.extend(_result_blockers(recovery_check_tick))
            else:
                blockers.extend(_result_blockers(post_recovery_snapshot_payload))
        runs.append(
            {
                "scope": scope,
                "snapshot": _summary(snapshot_payload),
                "scheduled_tick": _summary(scheduled_tick),
                "maintenance": _summary(maintenance),
                "post_recovery_snapshot": _summary(post_recovery_snapshot_payload),
                "recovery_check_tick": _summary(recovery_check_tick),
                "actions": list(maintenance.get("actions") or []),
            }
        )

    refreshed_scopes = select_ticket_bound_lifecycle_maintenance_scopes(
        conn,
        max_lifecycle_scopes=max_lifecycle_scopes,
    )
    blockers = _dedupe(
        _current_lifecycle_blockers(conn, scopes=refreshed_scopes) + blockers
    )
    selected_scopes = [
        {**scope, "scheduler_scope_kind": "first_post_submit"}
        for scope in first_tick_scopes
    ] + scopes
    return _result(
        "scheduler_blocked" if blockers else "scheduler_complete",
        now_ms=now_ms,
        scopes=selected_scopes,
        runs=runs,
        blockers=blockers,
        exchange_read_called=exchange_read_called,
        exchange_write_called=exchange_write_called,
    )


def select_ticket_bound_lifecycle_maintenance_scopes(
    conn: sa.engine.Connection,
    *,
    max_lifecycle_scopes: int,
) -> list[dict[str, Any]]:
    lifecycle = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    query = (
        sa.select(lifecycle)
        .where(lifecycle.c.status.in_(MAINTAINABLE_LIFECYCLE_STATUSES))
        .order_by(lifecycle.c.updated_at_ms.asc(), lifecycle.c.created_at_ms.asc())
        .limit(max_lifecycle_scopes)
    )
    scopes: list[dict[str, Any]] = []
    for row in conn.execute(query).mappings():
        item = dict(row)
        scopes.append(
            {
                "ticket_id": str(item.get("ticket_id") or ""),
                "protected_submit_attempt_id": str(
                    item.get("protected_submit_attempt_id") or ""
                ),
                "exit_protection_set_id": str(item.get("exit_protection_set_id") or ""),
                "strategy_group_id": str(item.get("strategy_group_id") or ""),
                "symbol": str(item.get("symbol") or ""),
                "side": str(item.get("side") or ""),
                "lifecycle_status": str(item.get("status") or ""),
                "first_blocker": item.get("first_blocker"),
            }
        )
    return scopes


def lifecycle_maintenance_scopes_require_exchange_gateway(
    scopes: list[dict[str, Any]],
    *,
    allow_exchange_mutation: bool,
    fetch_exchange_snapshot: bool,
) -> bool:
    if not scopes:
        return False
    if any(scope.get("scheduler_scope_kind") == "first_post_submit" for scope in scopes):
        return bool(fetch_exchange_snapshot)
    if allow_exchange_mutation:
        return True
    return bool(
        fetch_exchange_snapshot
        and any(
            scope.get("exit_protection_set_id")
            and str(scope.get("lifecycle_status") or "") in SNAPSHOT_STATUSES
            for scope in scopes
        )
    )


def _current_lifecycle_blockers(
    conn: sa.engine.Connection,
    *,
    scopes: list[dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    if not scopes:
        return blockers
    lifecycle = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    ticket_ids = [scope["ticket_id"] for scope in scopes if scope.get("ticket_id")]
    if not ticket_ids:
        return blockers
    rows = conn.execute(
        sa.select(lifecycle).where(lifecycle.c.ticket_id.in_(ticket_ids))
    ).mappings()
    for row in rows:
        item = dict(row)
        status = str(item.get("status") or "")
        if status in {
            "position_protected",
            "runner_protected",
            "reconciliation_matched",
            "budget_settled",
            "review_recorded",
            "lifecycle_closed",
        }:
            continue
        first = str(item.get("first_blocker") or "").strip()
        if first:
            blockers.append(first)
        blockers.extend(_json_list(item.get("blockers")))
    return _dedupe(blockers)


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    return {
        "status": payload.get("status"),
        "ticket_id": payload.get("ticket_id"),
        "exit_protection_set_id": payload.get("exit_protection_set_id"),
        "first_blocker": payload.get("first_blocker"),
        "blockers": _result_blockers(payload),
        "exchange_read_called": payload.get("exchange_read_called") is True,
        "exchange_write_called": payload.get("exchange_write_called") is True,
    }


def _result(
    status: str,
    *,
    now_ms: int,
    scopes: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    blockers: list[str],
    exchange_read_called: bool,
    exchange_write_called: bool,
) -> dict[str, Any]:
    return {
        "schema": "brc.ticket_bound_lifecycle_maintenance_scheduler.v1",
        "status": status,
        "now_ms": now_ms,
        "selected_scope_count": len(scopes),
        "scopes": scopes,
        "runs": runs,
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "next_action": (
            "repair_ticket_bound_lifecycle_scheduler_blocker"
            if blockers
            else "continue_ticket_bound_lifecycle_monitoring"
        ),
        "exchange_read_called": exchange_read_called,
        "exchange_write_called": exchange_write_called,
        "finalgate_called": False,
        "operation_layer_called": False,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "runtime_budget_mutated": False,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def _result_blockers(result: dict[str, Any]) -> list[str]:
    return [
        str(item)
        for item in (result.get("blockers") or [])
        if str(item or "").strip()
    ]


def _maintenance_executed_exchange_mutation(result: dict[str, Any]) -> bool:
    if result.get("exchange_write_called") is True:
        return True
    return any(
        isinstance(action, dict) and action.get("exchange_write_called") is True
        for action in result.get("actions") or []
    )


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
            import json

            loaded = json.loads(stripped)
            if isinstance(loaded, list):
                return [str(item) for item in loaded if str(item or "").strip()]
        return [stripped]
    return [str(value)]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)
