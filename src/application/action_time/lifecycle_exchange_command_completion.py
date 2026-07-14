"""Apply fully resolved durable exchange commands to lifecycle plan state."""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa

from src.application.action_time.exit_protection_materializer import (
    materialize_ticket_bound_exit_protection_set,
)
from src.application.action_time.orphan_protection_cleanup_command import (
    apply_durable_orphan_cleanup_exchange_commands,
)
from src.application.action_time.protection_recovery_command import (
    apply_durable_protection_recovery_exchange_commands,
)
from src.application.action_time.runner_mutation_command import (
    record_ticket_bound_runner_mutation_result,
)
from src.application.action_time.runner_protection_adjuster import (
    materialize_ticket_bound_runner_protection_adjustment,
)


CONFIRMED = {"confirmed_submitted", "reconciled_submitted"}
UNRESOLVED = {"prepared", "dispatching"}
BLOCKED = {"confirmed_rejected", "outcome_unknown", "hard_stopped"}


def apply_completed_lifecycle_exchange_sources(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
    source_command_id: str | None = None,
) -> list[dict[str, Any]]:
    table = _table(conn, "brc_ticket_bound_exchange_commands")
    query = sa.select(table).where(
        table.c.command_source != "protected_submit"
    )
    if source_command_id:
        query = query.where(table.c.source_command_id == source_command_id)
    rows = [dict(row) for row in conn.execute(query).mappings()]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(
            (
                str(row.get("command_source") or ""),
                str(row.get("source_command_id") or ""),
            ),
            [],
        ).append(row)
    results: list[dict[str, Any]] = []
    for (source, source_id), commands in grouped.items():
        states = {str(row.get("command_state") or "") for row in commands}
        if states & UNRESOLVED:
            continue
        if states & BLOCKED:
            results.append(
                {
                    "status": "source_blocked",
                    "command_source": source,
                    "source_command_id": source_id,
                    "blockers": sorted(states & BLOCKED),
                }
            )
            continue
        if not states or not states <= CONFIRMED:
            continue
        if source == "protection_recovery":
            applied = apply_durable_protection_recovery_exchange_commands(
                conn,
                protection_recovery_command_id=source_id,
                exchange_commands=commands,
                now_ms=now_ms,
            )
            materialized = materialize_ticket_bound_exit_protection_set(
                conn,
                protected_submit_attempt_id=str(
                    applied.get("protected_submit_attempt_id") or ""
                ),
                now_ms=now_ms,
            )
            results.append(
                {
                    "status": "protection_recovery_applied",
                    "command_source": source,
                    "source_command_id": source_id,
                    "materialized_status": materialized.get("status"),
                    "blockers": list(materialized.get("blockers") or []),
                }
            )
            continue
        if source == "runner_mutation":
            source_row = _row_by_id(
                conn,
                "brc_ticket_bound_runner_mutation_commands",
                "runner_mutation_command_id",
                source_id,
            )
            placed = next(
                row for row in commands if row.get("command_kind") == "place_order"
            )
            canceled = next(
                row for row in commands if row.get("command_kind") == "cancel_order"
            )
            payload = {
                "runner_mutation_command_id": source_id,
                "exit_protection_set_id": source_row.get("exit_protection_set_id"),
                "ticket_id": source_row.get("ticket_id"),
                "old_sl_exchange_order_id": canceled.get(
                    "target_exchange_order_id"
                ),
                "old_sl_cancelled": True,
                "runner_sl_submitted": True,
                "runner_sl_exchange_order_id": placed.get("exchange_order_id"),
                "runner_sl_client_order_id": placed.get("client_order_id"),
                "runner_sl_local_order_id": placed.get("local_order_id"),
                "exchange_write_called": True,
                "withdrawal_or_transfer_created": False,
                "live_profile_changed": False,
                "order_sizing_changed": False,
                "blockers": [],
                "durable_exchange_command_authority": True,
            }
            record = record_ticket_bound_runner_mutation_result(
                conn,
                runner_mutation_command_id=source_id,
                result_payload=payload,
                now_ms=now_ms,
            )
            adjusted = materialize_ticket_bound_runner_protection_adjustment(
                conn,
                exit_protection_set_id=str(
                    source_row.get("exit_protection_set_id") or ""
                ),
                runner_sl_exchange_order_id=str(
                    placed.get("exchange_order_id") or ""
                ),
                runner_sl_local_order_id=str(placed.get("local_order_id") or ""),
                now_ms=now_ms,
            )
            results.append(
                {
                    "status": "runner_mutation_applied",
                    "command_source": source,
                    "source_command_id": source_id,
                    "record_status": record.get("status"),
                    "materialized_status": adjusted.get("status"),
                    "blockers": list(adjusted.get("blockers") or []),
                }
            )
            continue
        if source == "orphan_cleanup":
            applied = apply_durable_orphan_cleanup_exchange_commands(
                conn,
                orphan_protection_cleanup_command_id=source_id,
                exchange_commands=commands,
                now_ms=now_ms,
            )
            results.append(
                {
                    "status": "orphan_cleanup_applied",
                    "command_source": source,
                    "source_command_id": source_id,
                    "applied_status": applied.get("status"),
                    "blockers": [],
                }
            )
    return results


def apply_failed_lifecycle_exchange_source(
    conn: sa.engine.Connection,
    *,
    command_source: str,
    source_command_id: str,
    now_ms: int,
) -> dict[str, Any]:
    """Project a terminal durable-command failure back to its plan authority."""

    commands_table = _table(conn, "brc_ticket_bound_exchange_commands")
    commands = [
        dict(row)
        for row in conn.execute(
            sa.select(commands_table).where(
                commands_table.c.command_source == command_source,
                commands_table.c.source_command_id == source_command_id,
            )
        ).mappings()
    ]
    terminal = [
        row
        for row in commands
        if str(row.get("command_state") or "")
        in {"confirmed_rejected", "hard_stopped"}
    ]
    if not terminal:
        return {
            "status": "source_failure_not_terminal",
            "command_source": command_source,
            "source_command_id": source_command_id,
            "blockers": [],
        }
    blockers = _failed_command_blockers(terminal)
    if command_source == "runner_mutation":
        placed = next(
            (row for row in commands if row.get("command_kind") == "place_order"),
            {},
        )
        canceled = next(
            (row for row in commands if row.get("command_kind") == "cancel_order"),
            {},
        )
        payload = {
            "runner_mutation_command_id": source_command_id,
            "old_sl_exchange_order_id": canceled.get("target_exchange_order_id"),
            "old_sl_cancelled": str(canceled.get("command_state") or "")
            in CONFIRMED,
            "runner_sl_submitted": str(placed.get("command_state") or "")
            in CONFIRMED,
            "runner_sl_exchange_order_id": placed.get("exchange_order_id"),
            "runner_sl_client_order_id": placed.get("client_order_id"),
            "runner_sl_local_order_id": placed.get("local_order_id"),
            "exchange_write_called": any(
                int(row.get("execution_attempt_count") or 0) > 0
                for row in commands
            ),
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "blockers": blockers,
            "durable_exchange_command_authority": True,
        }
        record = record_ticket_bound_runner_mutation_result(
            conn,
            runner_mutation_command_id=source_command_id,
            result_payload=payload,
            now_ms=now_ms,
        )
        return {
            "status": "runner_mutation_failure_applied",
            "command_source": command_source,
            "source_command_id": source_command_id,
            "record_status": record.get("status"),
            "blockers": list(record.get("blockers") or blockers),
        }
    source_table, id_column = {
        "protection_recovery": (
            "brc_ticket_bound_protection_recovery_commands",
            "protection_recovery_command_id",
        ),
        "orphan_cleanup": (
            "brc_ticket_bound_orphan_protection_cleanup_commands",
            "orphan_protection_cleanup_command_id",
        ),
    }[command_source]
    table = _table(conn, source_table)
    conn.execute(
        table.update()
        .where(table.c[id_column] == source_command_id)
        .values(
            status="failed",
            first_blocker=blockers[0],
            blockers=blockers,
            result_payload={
                "durable_exchange_command_authority": True,
                "blockers": blockers,
            },
            updated_at_ms=now_ms,
        )
    )
    return {
        "status": f"{command_source}_failure_applied",
        "command_source": command_source,
        "source_command_id": source_command_id,
        "blockers": blockers,
    }


def _failed_command_blockers(commands: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for row in commands:
        message = str(row.get("exchange_error_message") or "").strip()
        code = str(row.get("exchange_error_code") or "").strip()
        if message:
            blockers.append(message)
        elif code:
            blockers.append(code)
        else:
            blockers.append(
                f"exchange_command_{str(row.get('command_state') or 'failed')}"
            )
    return list(dict.fromkeys(blockers))


def _row_by_id(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    id_value: str,
) -> dict[str, Any]:
    table = _table(conn, table_name)
    row = conn.execute(
        sa.select(table).where(table.c[id_column] == id_value)
    ).mappings().first()
    return dict(row) if row else {}


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)
