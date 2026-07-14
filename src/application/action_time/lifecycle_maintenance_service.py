#!/usr/bin/env python3
"""Production wiring runner for ticket-bound lifecycle maintenance.

The service consumes existing PG ticket/attempt/protection rows and invokes the
official ticket-bound maintenance modules. It does not create signals, tickets,
FinalGate passes, Operation Layer handoffs, profiles, sizing, or file artifacts.
Exchange mutation remains disabled unless the caller explicitly supplies both a
gateway and ``allow_exchange_mutation=True``.
"""

from __future__ import annotations

import time
from typing import Any

import sqlalchemy as sa

from src.application.action_time.exit_protection_materializer import (
    materialize_ticket_bound_exit_protection_set,
)
from src.application.action_time.orphan_protection_cleanup_command import (
    prepare_ticket_bound_orphan_protection_cleanup_command,
)
from src.application.action_time.lifecycle_exchange_command_materializer import (
    materialize_lifecycle_exchange_commands,
)
from src.application.action_time.protection_reconciler import (
    reconcile_ticket_bound_exit_protection_set,
)
from src.application.action_time.protection_recovery_command import (
    prepare_ticket_bound_protection_recovery_command,
)
from src.application.action_time.runner_mutation_command import (
    prepare_ticket_bound_runner_mutation_command,
)
from src.application.action_time.runner_protection_adjuster import (
    materialize_ticket_bound_runner_protection_adjustment,
)
from src.domain.ticket_exit_protection import (
    DEFAULT_REPLACEMENT_GRACE_MS,
    order_mapping_for_view,
    resolve_active_exit_protection_rows,
)


AUTHORITY_BOUNDARY = (
    "ticket_bound_lifecycle_maintenance_service; existing PG ticket-bound "
    "lifecycle rows only; optional official gateway mutation only when "
    "allow_exchange_mutation is true and a gateway is injected; no FinalGate, "
    "Operation Layer bypass, profile, sizing, withdrawal, transfer, file "
    "authority, signal creation, or ticket creation"
)

TERMINAL_ATTEMPT_STATUSES = {"blocked", "failed"}
MAINTAINABLE_PROTECTION_SET_STATUSES = {
    "submitted",
    "reconciled",
    "runner_mutation_pending",
    "runner_protected",
    "position_closed_protection_live",
}


async def run_ticket_bound_lifecycle_maintenance(
    conn: sa.engine.Connection,
    *,
    ticket_id: str = "",
    protected_submit_attempt_id: str = "",
    exit_protection_set_id: str = "",
    exchange_snapshot: dict[str, Any] | None = None,
    gateway: Any = None,
    allow_exchange_mutation: bool = False,
    max_actions: int = 16,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Run one bounded lifecycle maintenance pass.

    ``exchange_snapshot`` is optional and caller-provided. The service never
    fetches exchange state on its own, so production cadence can control cost
    and freshness explicitly.
    """

    now_ms = int(now_ms or time.time() * 1000)
    scope = {
        "ticket_id": str(ticket_id or "").strip(),
        "protected_submit_attempt_id": str(protected_submit_attempt_id or "").strip(),
        "exit_protection_set_id": str(exit_protection_set_id or "").strip(),
    }
    actions: list[dict[str, Any]] = []
    blockers: list[str] = []
    exchange_write_called = False
    exchange_read_called = False

    unknown_attempt_ids = _unknown_exchange_command_attempt_ids(
        conn,
        scope=scope,
        limit=max_actions,
    )
    if unknown_attempt_ids:
        blockers.append("exchange_command_reconciliation_worker_required")

    attempt_ids = _scoped_attempt_ids(conn, scope=scope)
    attempt_ids = [
        attempt_id
        for attempt_id in attempt_ids
        if attempt_id not in unknown_attempt_ids
    ]
    for attempt_id in attempt_ids:
        if len(actions) >= max_actions:
            blockers.append("lifecycle_maintenance_max_actions_reached")
            break
        result = materialize_ticket_bound_exit_protection_set(
            conn,
            protected_submit_attempt_id=attempt_id,
            now_ms=now_ms,
        )
        actions.append(_action("exit_protection_materialized", result))
        blockers.extend(_result_blockers(result))

        if str(result.get("status") or "") in {
            "protection_missing",
            "protection_degraded",
            "protection_submit_failed",
        }:
            recovery = prepare_ticket_bound_protection_recovery_command(
                conn,
                protected_submit_attempt_id=attempt_id,
                now_ms=now_ms + len(actions),
            )
            actions.append(_action("protection_recovery_prepared", recovery))
            blockers.extend(_result_blockers(recovery))
            command_id = str(recovery.get("protection_recovery_command_id") or "")
            if recovery.get("status") == "prepared" and command_id:
                durable = _materialize_durable_commands(
                    conn,
                    command_source="protection_recovery",
                    source_command_id=command_id,
                    now_ms=now_ms + len(actions),
                )
                actions.append(
                    _action("protection_recovery_exchange_commands_prepared", durable)
                )
                blockers.extend(_result_blockers(durable))

    protection_set_ids = _scoped_exit_protection_set_ids(conn, scope=scope)
    for set_id in protection_set_ids:
        if len(actions) >= max_actions:
            blockers.append("lifecycle_maintenance_max_actions_reached")
            break
        if exchange_snapshot:
            reconciled = reconcile_ticket_bound_exit_protection_set(
                conn,
                exit_protection_set_id=set_id,
                exchange_snapshot=exchange_snapshot,
                now_ms=now_ms + len(actions),
            )
            actions.append(_action("exit_protection_reconciled", reconciled))
            blockers.extend(_result_blockers(reconciled))
            if (
                str(reconciled.get("status") or "")
                in {"protection_missing", "protection_degraded", "protection_submit_failed"}
                and len(actions) < max_actions
            ):
                recovery = prepare_ticket_bound_protection_recovery_command(
                    conn,
                    protected_submit_attempt_id=_protection_set_attempt_id(conn, set_id),
                    now_ms=now_ms + len(actions),
                )
                actions.append(_action("protection_recovery_prepared", recovery))
                blockers.extend(_result_blockers(recovery))
                command_id = str(recovery.get("protection_recovery_command_id") or "")
                if recovery.get("status") == "prepared" and command_id:
                    durable = _materialize_durable_commands(
                        conn,
                        command_source="protection_recovery",
                        source_command_id=command_id,
                        now_ms=now_ms + len(actions),
                    )
                    actions.append(
                        _action(
                            "protection_recovery_exchange_commands_prepared",
                            durable,
                        )
                    )
                    blockers.extend(_result_blockers(durable))

        runner: dict[str, Any] = {}
        runner_command_id = ""
        if _runner_mutation_candidate(conn, set_id, now_ms=now_ms + len(actions)):
            runner = prepare_ticket_bound_runner_mutation_command(
                conn,
                exit_protection_set_id=set_id,
                now_ms=now_ms + len(actions),
            )
            if _should_record_action(runner):
                actions.append(_action("runner_mutation_prepared", runner))
                blockers.extend(_result_blockers(runner))
            runner_command_id = str(runner.get("runner_mutation_command_id") or "")
        if runner.get("status") == "prepared" and runner_command_id:
            durable = _materialize_durable_commands(
                conn,
                command_source="runner_mutation",
                source_command_id=runner_command_id,
                now_ms=now_ms + len(actions),
            )
            actions.append(
                _action("runner_mutation_exchange_commands_prepared", durable)
            )
            blockers.extend(_result_blockers(durable))

        cleanup: dict[str, Any] = {}
        cleanup_command_id = ""
        if _orphan_cleanup_candidate(conn, set_id):
            cleanup = prepare_ticket_bound_orphan_protection_cleanup_command(
                conn,
                exit_protection_set_id=set_id,
                now_ms=now_ms + len(actions),
            )
            if _should_record_action(cleanup):
                actions.append(_action("orphan_protection_cleanup_prepared", cleanup))
                blockers.extend(_result_blockers(cleanup))
            cleanup_command_id = str(cleanup.get("orphan_protection_cleanup_command_id") or "")
        if cleanup.get("status") == "prepared" and cleanup_command_id:
            durable = _materialize_durable_commands(
                conn,
                command_source="orphan_cleanup",
                source_command_id=cleanup_command_id,
                now_ms=now_ms + len(actions),
            )
            actions.append(
                _action("orphan_cleanup_exchange_commands_prepared", durable)
            )
            blockers.extend(_result_blockers(durable))

    blockers = _dedupe(
        _control_blockers(blockers)
        + _current_scope_blockers(conn, scope=scope, actions=actions)
    )
    return {
        "schema": "brc.ticket_bound_lifecycle_maintenance.v1",
        "status": "maintenance_blocked" if blockers else "maintenance_complete",
        "now_ms": now_ms,
        "scope": scope,
        "action_count": len(actions),
        "actions": actions,
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "next_action": _next_action(blockers),
        "allow_exchange_mutation": allow_exchange_mutation,
        "direct_exchange_mutation_enabled": False,
        "exchange_read_called": exchange_read_called,
        "exchange_write_called": exchange_write_called,
        "finalgate_called": False,
        "operation_layer_called": False,
        "order_created": exchange_write_called,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "runtime_budget_mutated": False,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def _materialize_durable_commands(
    conn: sa.engine.Connection,
    *,
    command_source: str,
    source_command_id: str,
    now_ms: int,
) -> dict[str, Any]:
    try:
        rows = materialize_lifecycle_exchange_commands(
            conn,
            command_source=command_source,  # type: ignore[arg-type]
            source_command_id=source_command_id,
            now_ms=now_ms,
        )
    except Exception as exc:
        blocker = f"lifecycle_exchange_command_materialization_failed:{type(exc).__name__}"
        return {
            "status": "blocked",
            "first_blocker": blocker,
            "blockers": [blocker, str(exc)],
            "exchange_write_called": False,
        }
    return {
        "status": "prepared",
        "exchange_command_count": len(rows),
        "exchange_command_ids": [
            str(row.get("exchange_command_id") or "") for row in rows
        ],
        "first_blocker": None,
        "blockers": [],
        "exchange_write_called": False,
    }


def _scoped_attempt_ids(
    conn: sa.engine.Connection,
    *,
    scope: dict[str, str],
) -> list[str]:
    table = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    query = sa.select(table.c.protected_submit_attempt_id, table.c.status)
    if scope["protected_submit_attempt_id"]:
        query = query.where(
            table.c.protected_submit_attempt_id == scope["protected_submit_attempt_id"]
        )
    elif scope["ticket_id"]:
        query = query.where(table.c.ticket_id == scope["ticket_id"])
    elif scope["exit_protection_set_id"]:
        return []
    else:
        query = query.where(~table.c.status.in_(TERMINAL_ATTEMPT_STATUSES))
    query = query.order_by(table.c.created_at_ms.desc()).limit(8)
    return [str(row["protected_submit_attempt_id"]) for row in conn.execute(query).mappings()]


def _unknown_exchange_command_attempt_ids(
    conn: sa.engine.Connection,
    *,
    scope: dict[str, str],
    limit: int,
) -> set[str]:
    if not sa.inspect(conn).has_table("brc_ticket_bound_exchange_commands"):
        return set()
    commands = _table(conn, "brc_ticket_bound_exchange_commands")
    query = sa.select(commands.c.protected_submit_attempt_id).where(
        commands.c.command_state == "outcome_unknown"
    )
    if scope["protected_submit_attempt_id"]:
        query = query.where(
            commands.c.protected_submit_attempt_id
            == scope["protected_submit_attempt_id"]
        )
    elif scope["ticket_id"]:
        query = query.where(commands.c.ticket_id == scope["ticket_id"])
    elif scope["exit_protection_set_id"]:
        return set()
    query = query.order_by(commands.c.updated_at_ms.asc()).limit(max(0, limit))
    return {
        str(row["protected_submit_attempt_id"])
        for row in conn.execute(query).mappings()
    }


def _scoped_exit_protection_set_ids(
    conn: sa.engine.Connection,
    *,
    scope: dict[str, str],
) -> list[str]:
    table = _table(conn, "brc_ticket_bound_exit_protection_sets")
    query = sa.select(table.c.exit_protection_set_id, table.c.status)
    if scope["exit_protection_set_id"]:
        query = query.where(
            table.c.exit_protection_set_id == scope["exit_protection_set_id"]
        )
    elif scope["protected_submit_attempt_id"]:
        query = query.where(
            table.c.protected_submit_attempt_id == scope["protected_submit_attempt_id"]
        )
    elif scope["ticket_id"]:
        query = query.where(table.c.ticket_id == scope["ticket_id"])
    else:
        query = query.where(table.c.status.in_(MAINTAINABLE_PROTECTION_SET_STATUSES))
    query = query.order_by(table.c.created_at_ms.desc()).limit(8)
    return [str(row["exit_protection_set_id"]) for row in conn.execute(query).mappings()]


def _runner_mutation_candidate(
    conn: sa.engine.Connection,
    set_id: str,
    *,
    now_ms: int,
) -> bool:
    protection_set = _row_by_id(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        set_id,
    )
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "ticket_id",
        str(protection_set.get("ticket_id") or ""),
    )
    orders = _orders_for_set(conn, set_id)
    tp1_resolution = resolve_active_exit_protection_rows(
        exit_protection_set_id=set_id,
        role="TP1",
        orders=orders,
        position_is_open=True,
        now_ms=now_ms,
        replacement_grace_ms=DEFAULT_REPLACEMENT_GRACE_MS,
    )
    runner_resolution = resolve_active_exit_protection_rows(
        exit_protection_set_id=set_id,
        role="RUNNER_SL",
        orders=orders,
        position_is_open=True,
        now_ms=now_ms,
        replacement_grace_ms=DEFAULT_REPLACEMENT_GRACE_MS,
    )
    if tp1_resolution.fails_closed or runner_resolution.fails_closed:
        return False
    tp1 = order_mapping_for_view(orders, tp1_resolution.lineage_leaf)
    runner = order_mapping_for_view(orders, runner_resolution.active_order)
    return (
        str(lifecycle.get("status") or "") == "runner_mutation_pending"
        or (
            str(tp1.get("status") or "").lower() == "filled"
            and not runner
            and str(protection_set.get("status") or "") in {
                "submitted",
                "reconciled",
                "runner_mutation_pending",
            }
        )
    )


def _orphan_cleanup_candidate(conn: sa.engine.Connection, set_id: str) -> bool:
    protection_set = _row_by_id(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        set_id,
    )
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "ticket_id",
        str(protection_set.get("ticket_id") or ""),
    )
    return (
        str(lifecycle.get("status") or "") == "position_closed_protection_live"
        and str(protection_set.get("status") or "") == "position_closed_protection_live"
    )


def _orders_for_set(conn: sa.engine.Connection, set_id: str) -> list[dict[str, Any]]:
    table = _table(conn, "brc_ticket_bound_exit_protection_orders")
    return [
        dict(row)
        for row in conn.execute(
            sa.select(table).where(table.c.exit_protection_set_id == set_id)
        ).mappings()
    ]


def _protection_set_attempt_id(conn: sa.engine.Connection, set_id: str) -> str:
    protection_set = _row_by_id(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        set_id,
    )
    return str(protection_set.get("protected_submit_attempt_id") or "")


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


def _action(action_type: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_type": action_type,
        "status": str(result.get("status") or "unknown"),
        "ticket_id": result.get("ticket_id"),
        "protected_submit_attempt_id": result.get("protected_submit_attempt_id"),
        "exit_protection_set_id": result.get("exit_protection_set_id"),
        "command_id": (
            result.get("protection_recovery_command_id")
            or result.get("runner_mutation_command_id")
            or result.get("orphan_protection_cleanup_command_id")
        ),
        "first_blocker": result.get("first_blocker"),
        "blockers": _result_blockers(result),
        "next_action": result.get("next_action"),
        "exchange_write_called": _result_exchange_write_called(result),
    }


def _control_blockers(blockers: list[str]) -> list[str]:
    prefixes = (
        "exchange_mutation_not_allowed",
        "exchange_command_reconciliation_worker_required",
        "gateway_required",
        "lifecycle_maintenance_max_actions_reached",
    )
    return [blocker for blocker in blockers if blocker.startswith(prefixes)]


def _current_scope_blockers(
    conn: sa.engine.Connection,
    *,
    scope: dict[str, str],
    actions: list[dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    lifecycle_table = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    query = sa.select(lifecycle_table)
    if scope["ticket_id"]:
        query = query.where(lifecycle_table.c.ticket_id == scope["ticket_id"])
    elif scope["protected_submit_attempt_id"]:
        query = query.where(
            lifecycle_table.c.protected_submit_attempt_id
            == scope["protected_submit_attempt_id"]
        )
    elif scope["exit_protection_set_id"]:
        query = query.where(
            lifecycle_table.c.exit_protection_set_id == scope["exit_protection_set_id"]
        )
    else:
        scoped_ticket_ids = {
            str(action.get("ticket_id") or "")
            for action in actions
            if action.get("ticket_id")
        }
        if scoped_ticket_ids:
            query = query.where(lifecycle_table.c.ticket_id.in_(scoped_ticket_ids))
        else:
            return []
    for row in conn.execute(query).mappings():
        lifecycle = dict(row)
        status = str(lifecycle.get("status") or "")
        if status in {
            "position_protected",
            "runner_protected",
            "reconciliation_matched",
            "budget_settled",
            "review_recorded",
            "lifecycle_closed",
        }:
            continue
        blockers.extend(_json_list(lifecycle.get("blockers")))
        first_blocker = str(lifecycle.get("first_blocker") or "").strip()
        if first_blocker:
            blockers.append(first_blocker)
    return _dedupe(blockers)


def _result_blockers(result: dict[str, Any]) -> list[str]:
    return [
        str(item)
        for item in (result.get("blockers") or [])
        if str(item or "").strip()
    ]


def _result_exchange_write_called(result: dict[str, Any]) -> bool:
    if result.get("exchange_write_called") is True:
        return True
    payload = result.get("result_payload")
    if isinstance(payload, dict) and payload.get("exchange_write_called") is True:
        return True
    command = result.get("command")
    if isinstance(command, dict):
        command_payload = command.get("result_payload")
        return (
            isinstance(command_payload, dict)
            and command_payload.get("exchange_write_called") is True
        )
    return False


def _should_record_action(result: dict[str, Any]) -> bool:
    status = str(result.get("status") or "")
    blockers = _result_blockers(result)
    return status not in {"blocked"} or bool(blockers)


def _next_action(blockers: list[str]) -> str:
    if not blockers:
        return "continue_ticket_bound_lifecycle_monitoring"
    if any(blocker.startswith("gateway_required") for blocker in blockers):
        return "provide_official_runtime_exchange_gateway"
    if any(blocker.startswith("exchange_mutation_not_allowed") for blocker in blockers):
        return "rerun_with_explicit_exchange_mutation_authority_when_safe"
    return "repair_ticket_bound_lifecycle_maintenance_blocker"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()]
    if isinstance(value, tuple):
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


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)
