"""Read-only reconciliation for ambiguous ticket-bound exchange commands."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from src.application.action_time.exchange_command import (
    record_exchange_command_outcome,
)
from src.application.action_time.lifecycle_exchange_command_completion import (
    apply_completed_lifecycle_exchange_sources,
)
from src.application.action_time.netting_domain_hold import (
    resolve_netting_domain_hold_source,
    upsert_exchange_command_domain_hold,
)
from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandOutcomeClass,
    ExchangeCommandState,
)


VISIBILITY_WINDOW_MS = 30_000
AUTHORITY_BOUNDARY = (
    "ticket_bound_exchange_command_reconciliation; read-only lookup by "
    "persisted client_order_id; no submit, cancel, replace, profile, sizing, "
    "withdrawal, transfer, or file authority"
)


async def run_one_unknown_exchange_command_reconciliation(
    engine: sa.Engine,
    *,
    gateway: Any,
    now_ms: int,
) -> dict[str, Any]:
    """Short select -> transaction-free lookup -> short result projection."""

    with engine.begin() as conn:
        command = select_one_unknown_exchange_command(conn)
    if not command:
        return {
            "schema": "brc.ticket_bound_exchange_command_reconciliation_worker.v1",
            "status": "no_unknown_commands",
            "exchange_read_called": False,
            "exchange_write_called": False,
            "blockers": [],
        }
    identity_blockers = _gateway_identity_blockers(command, gateway)
    if identity_blockers:
        decision = {
            "status": "hard_stopped",
            "exchange_order_id": None,
            "blockers": identity_blockers,
        }
    else:
        decision = await lookup_unknown_exchange_command(
            command=command,
            gateway=gateway,
            now_ms=now_ms,
        )
    with engine.begin() as conn:
        applied = apply_unknown_exchange_command_decision(
            conn,
            command=command,
            decision=decision,
            now_ms=now_ms,
        )
    return {
        "schema": "brc.ticket_bound_exchange_command_reconciliation_worker.v1",
        **applied,
        "exchange_read_called": not identity_blockers,
        "exchange_write_called": False,
        "automatic_resubmit_called": False,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def select_one_unknown_exchange_command(
    conn: sa.engine.Connection,
) -> dict[str, Any]:
    table = sa.Table(
        "brc_ticket_bound_exchange_commands",
        sa.MetaData(),
        autoload_with=conn,
    )
    query = (
        sa.select(table)
        .where(table.c.command_state == "outcome_unknown")
        .order_by(table.c.updated_at_ms.asc())
        .limit(1)
    )
    if conn.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    row = conn.execute(query).mappings().first()
    return dict(row) if row else {}


async def lookup_unknown_exchange_command(
    *,
    command: dict[str, Any],
    gateway: Any,
    now_ms: int,
) -> dict[str, Any]:
    try:
        if str(command.get("command_kind") or "") == "cancel_order":
            orders = await gateway.fetch_all_open_orders(
                str(command["gateway_symbol"])
            )
            target = str(command.get("target_exchange_order_id") or "")
            still_open = any(
                str(_mapping(order).get("id") or _mapping(order).get("exchange_order_id") or "")
                == target
                for order in orders or []
            )
            exchange_order = None if still_open else {
                "exchange_order_id": target,
                "client_order_id": str(command.get("client_order_id") or ""),
                "symbol": str(command.get("gateway_symbol") or ""),
            }
        else:
            exchange_order = await gateway.find_order_by_client_id(
                str(command["client_order_id"]),
                str(command["gateway_symbol"]),
            )
    except Exception as exc:
        return {
            "status": "lookup_failed",
            "exchange_order_id": None,
            "blockers": [
                f"exchange_command_lookup_failed:{type(exc).__name__}"
            ],
        }
    if exchange_order is None:
        deadline = int(command.get("updated_at_ms") or now_ms) + VISIBILITY_WINDOW_MS
        if now_ms < deadline:
            return {
                "status": "pending_visibility",
                "exchange_order_id": None,
                "blockers": ["exchange_command_visibility_window_active"],
            }
        return {
            "status": "reconciled_absent",
            "exchange_order_id": None,
            "blockers": [],
        }
    exchange = _mapping(exchange_order)
    exchange_order_id = str(exchange.get("exchange_order_id") or "").strip()
    actual_client_id = str(exchange.get("client_order_id") or "").strip()
    actual_symbol = str(exchange.get("symbol") or "").strip()
    contradictory = (
        not exchange_order_id
        or (
            bool(actual_client_id)
            and actual_client_id != str(command["client_order_id"])
        )
        or (
            bool(actual_symbol)
            and actual_symbol != str(command["gateway_symbol"])
        )
    )
    if contradictory:
        return {
            "status": "hard_stopped",
            "exchange_order_id": exchange_order_id or None,
            "blockers": ["reconciled_exchange_identity_contradictory"],
        }
    return {
        "status": "reconciled_submitted",
        "exchange_order_id": exchange_order_id,
        "blockers": [],
    }


def apply_unknown_exchange_command_decision(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    decision: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    status = str(decision.get("status") or "")
    blockers = [str(item) for item in decision.get("blockers") or []]
    if status in {"lookup_failed", "pending_visibility"}:
        return {
            "status": status,
            "exchange_command_id": command.get("exchange_command_id"),
            "first_blocker": blockers[0] if blockers else None,
            "blockers": blockers,
        }
    target, outcome = {
        "reconciled_submitted": (
            ExchangeCommandState.RECONCILED_SUBMITTED,
            ExchangeCommandOutcomeClass.RECONCILED_EXCHANGE_TRUTH,
        ),
        "reconciled_absent": (
            ExchangeCommandState.RECONCILED_ABSENT,
            ExchangeCommandOutcomeClass.RECONCILED_ABSENCE,
        ),
        "hard_stopped": (
            ExchangeCommandState.HARD_STOPPED,
            ExchangeCommandOutcomeClass.CONTRADICTORY_TRUTH,
        ),
    }[status]
    recorded = record_exchange_command_outcome(
        conn,
        exchange_command_id=str(command["exchange_command_id"]),
        target_state=target,
        outcome_class=outcome,
        exchange_result={
            "exchange_order_id": decision.get("exchange_order_id"),
            "error_message": blockers[0] if blockers else None,
        },
        now_ms=now_ms,
    )
    if status == "hard_stopped":
        upsert_exchange_command_domain_hold(
            conn,
            command=recorded,
            blockers=blockers or ["exchange_command_hard_stopped"],
            now_ms=now_ms,
        )
    else:
        resolve_netting_domain_hold_source(
            conn,
            netting_domain_key=str(recorded.get("netting_domain_key") or ""),
            source_kind="exchange_command",
            source_id=str(recorded.get("exchange_command_id") or ""),
            resolution_source=f"exchange_command_{status}",
            now_ms=now_ms,
        )
        if status == "reconciled_submitted":
            apply_completed_lifecycle_exchange_sources(
                conn,
                now_ms=now_ms,
                source_command_id=str(recorded.get("source_command_id") or ""),
            )
    return {
        "status": status,
        "exchange_command_id": recorded.get("exchange_command_id"),
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
    }


def _gateway_identity_blockers(
    command: dict[str, Any],
    gateway: Any,
) -> list[str]:
    blockers: list[str] = []
    if str(getattr(gateway, "runtime_account_id", "") or "") != str(
        command.get("account_id") or ""
    ):
        blockers.append("exchange_command_gateway_account_mismatch")
    if str(getattr(gateway, "runtime_exchange_id", "") or "") != str(
        command.get("exchange_id") or ""
    ):
        blockers.append("exchange_command_gateway_exchange_mismatch")
    return blockers


async def reconcile_unknown_exchange_commands(
    conn: sa.engine.Connection,
    *,
    gateway: Any,
    now_ms: int,
    max_commands: int,
) -> dict[str, Any]:
    table = sa.Table(
        "brc_ticket_bound_exchange_commands",
        sa.MetaData(),
        autoload_with=conn,
    )
    rows = list(
        conn.execute(
            sa.select(table)
            .where(table.c.command_state == "outcome_unknown")
            .order_by(table.c.updated_at_ms.asc())
            .limit(max(0, max_commands))
        ).mappings()
    )
    counts = {
        "reconciled_submitted": 0,
        "reconciled_absent": 0,
        "pending_visibility": 0,
        "hard_stopped": 0,
        "lookup_failed": 0,
    }
    results: list[dict[str, Any]] = []
    for raw in rows:
        command = dict(raw)
        try:
            exchange_order = await gateway.find_order_by_client_id(
                str(command["client_order_id"]),
                str(command["gateway_symbol"]),
            )
        except Exception as exc:
            counts["lookup_failed"] += 1
            results.append(
                _item(
                    command,
                    status="lookup_failed",
                    blocker=f"exchange_command_lookup_failed:{type(exc).__name__}",
                )
            )
            continue

        if exchange_order is None:
            visibility_deadline_ms = (
                int(command.get("updated_at_ms") or now_ms)
                + VISIBILITY_WINDOW_MS
            )
            if now_ms < visibility_deadline_ms:
                counts["pending_visibility"] += 1
                results.append(
                    _item(
                        command,
                        status="pending_visibility",
                        blocker="exchange_command_visibility_window_active",
                    )
                )
                continue
            record_exchange_command_outcome(
                conn,
                exchange_command_id=str(command["exchange_command_id"]),
                target_state=ExchangeCommandState.RECONCILED_ABSENT,
                outcome_class=ExchangeCommandOutcomeClass.RECONCILED_ABSENCE,
                exchange_result={},
                now_ms=now_ms,
            )
            counts["reconciled_absent"] += 1
            results.append(
                _item(
                    command,
                    status="reconciled_absent",
                    blocker="new_ticket_and_official_gates_required_for_any_retry",
                )
            )
            continue

        exchange = _mapping(exchange_order)
        exchange_order_id = str(exchange.get("exchange_order_id") or "").strip()
        actual_client_id = str(exchange.get("client_order_id") or "").strip()
        actual_symbol = str(exchange.get("symbol") or "").strip()
        contradictory = (
            not exchange_order_id
            or (
                bool(actual_client_id)
                and actual_client_id != str(command["client_order_id"])
            )
            or (
                bool(actual_symbol)
                and actual_symbol != str(command["gateway_symbol"])
            )
        )
        if contradictory:
            record_exchange_command_outcome(
                conn,
                exchange_command_id=str(command["exchange_command_id"]),
                target_state=ExchangeCommandState.HARD_STOPPED,
                outcome_class=ExchangeCommandOutcomeClass.CONTRADICTORY_TRUTH,
                exchange_result={
                    "exchange_order_id": exchange_order_id or None,
                    "error_message": "reconciled_exchange_identity_contradictory",
                },
                now_ms=now_ms,
            )
            counts["hard_stopped"] += 1
            results.append(
                _item(
                    command,
                    status="hard_stopped",
                    blocker="reconciled_exchange_identity_contradictory",
                )
            )
            continue

        record_exchange_command_outcome(
            conn,
            exchange_command_id=str(command["exchange_command_id"]),
            target_state=ExchangeCommandState.RECONCILED_SUBMITTED,
            outcome_class=ExchangeCommandOutcomeClass.RECONCILED_EXCHANGE_TRUTH,
            exchange_result={"exchange_order_id": exchange_order_id},
            now_ms=now_ms,
        )
        counts["reconciled_submitted"] += 1
        results.append(_item(command, status="reconciled_submitted", blocker=""))

    blockers: list[str] = []
    if counts["hard_stopped"]:
        blockers.append("exchange_command_hard_stopped")
    if counts["lookup_failed"]:
        blockers.append("exchange_command_lookup_failed")
    if counts["pending_visibility"]:
        blockers.append("exchange_command_visibility_window_active")
    return {
        "schema": "brc.ticket_bound_exchange_command_reconciliation.v1",
        "status": "reconciliation_complete" if rows else "no_unknown_commands",
        "selected_count": len(rows),
        **counts,
        "results": results,
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "next_action": (
            "repair_or_continue_unknown_exchange_command_reconciliation"
            if blockers
            else "continue_ticket_bound_lifecycle_from_reconciled_truth"
        ),
        "exchange_read_called": bool(rows),
        "exchange_write_called": False,
        "automatic_resubmit_called": False,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}


def _item(
    command: dict[str, Any],
    *,
    status: str,
    blocker: str,
) -> dict[str, Any]:
    return {
        "exchange_command_id": command.get("exchange_command_id"),
        "client_order_id": command.get("client_order_id"),
        "status": status,
        "blockers": [blocker] if blocker else [],
    }
