#!/usr/bin/env python3
"""Materialize a PG ticket-bound Operation Layer handoff.

Input authority is ``ticket_id + finalgate_pass_id``. The script reads the
ticket lineage from PG and writes one non-executing Operation Layer handoff row.

It does not call Operation Layer submit, exchange write APIs, OrderLifecycle,
withdrawals, transfers, live profile mutation, or order sizing mutation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
)


DEFAULT_REPORT_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-signal-watcher")
DEFAULT_OUTPUT_JSON = DEFAULT_REPORT_DIR / "operation-layer-handoff.json"
AUTHORITY_BOUNDARY = (
    "ticket_id_finalgate_pass_operation_layer_handoff; "
    "no_operation_layer_submit_no_exchange_write"
)
FORBIDDEN_EFFECTS = {
    "operation_layer_submit_called": False,
    "exchange_write_called": False,
    "order_created": False,
    "order_lifecycle_called": False,
    "withdrawal_or_transfer_created": False,
    "live_profile_changed": False,
    "order_sizing_changed": False,
}


def materialize_action_time_operation_layer_handoff(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    finalgate_pass_id: str,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    ticket_id = str(ticket_id or "").strip()
    finalgate_pass_id = str(finalgate_pass_id or "").strip()
    if not ticket_id:
        return _blocked(["ticket_id_required"], now_ms=now_ms, ticket={})
    if not finalgate_pass_id:
        return _blocked(["finalgate_pass_id_required"], now_ms=now_ms, ticket={})
    try:
        control_state = PgBackedRuntimeControlStateRepository(conn).read_control_state()
    except RuntimeControlStateRepositoryError as exc:
        return _blocked([f"runtime_control_state_invalid:{exc}"], now_ms=now_ms, ticket={})

    ticket = _ticket_by_id(control_state, ticket_id)
    if not ticket:
        return _blocked(["action_time_ticket_missing"], now_ms=now_ms, ticket={"ticket_id": ticket_id})
    blockers = _handoff_blockers(
        control_state,
        ticket=ticket,
        finalgate_pass_id=finalgate_pass_id,
        now_ms=now_ms,
    )
    if blockers:
        return _blocked(blockers, now_ms=now_ms, ticket=ticket)

    existing = _existing_handoff(control_state, ticket_id, finalgate_pass_id)
    if existing:
        return _result(
            "operation_layer_handoff_already_exists",
            now_ms=now_ms,
            ticket=ticket,
            handoff=existing,
            blockers=[],
            next_action="prepare_ticket_bound_protected_submit",
        )

    handoff = _build_handoff(ticket, finalgate_pass_id=finalgate_pass_id, now_ms=now_ms)
    _insert_handoff(conn, handoff)
    return _result(
        "operation_layer_handoff_ready",
        now_ms=now_ms,
        ticket=ticket,
        handoff=handoff,
        blockers=[],
        next_action="prepare_ticket_bound_protected_submit",
    )


def materialize_next_action_time_operation_layer_handoff(
    conn: sa.engine.Connection,
    *,
    ticket_id: str = "",
    finalgate_pass_id: str = "",
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    ticket_id = str(ticket_id or "").strip()
    finalgate_pass_id = str(finalgate_pass_id or "").strip()
    if ticket_id or finalgate_pass_id:
        return materialize_action_time_operation_layer_handoff(
            conn,
            ticket_id=ticket_id,
            finalgate_pass_id=finalgate_pass_id,
            now_ms=now_ms,
        )
    try:
        control_state = PgBackedRuntimeControlStateRepository(conn).read_control_state()
    except RuntimeControlStateRepositoryError as exc:
        return _blocked([f"runtime_control_state_invalid:{exc}"], now_ms=now_ms, ticket={})
    tickets = [
        row
        for row in _rows(control_state.get("action_time_tickets"))
        if row.get("status") == "finalgate_ready"
    ]
    if not tickets:
        return _result(
            "no_finalgate_ready_ticket",
            now_ms=now_ms,
            ticket={},
            handoff={},
            blockers=[],
            next_action="continue_watcher_observation",
        )
    if len(tickets) > 1:
        return _blocked(["multiple_finalgate_ready_tickets"], now_ms=now_ms, ticket={})
    selected_ticket = tickets[0]
    selected_pass_id = _latest_finalgate_pass_id(
        control_state,
        str(selected_ticket.get("ticket_id") or ""),
    )
    if not selected_pass_id:
        return _blocked(
            ["finalgate_pass_id_missing"],
            now_ms=now_ms,
            ticket=selected_ticket,
        )
    return materialize_action_time_operation_layer_handoff(
        conn,
        ticket_id=str(selected_ticket.get("ticket_id") or ""),
        finalgate_pass_id=selected_pass_id,
        now_ms=now_ms,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--ticket-id", default="")
    parser.add_argument("--finalgate-pass-id", default="")
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite or other SQLAlchemy URLs only for local unit tests.",
    )
    args = parser.parse_args(argv)
    if args.require_database_url and not args.database_url:
        print("ERROR: PG_DATABASE_URL is required for Operation Layer handoff", file=sys.stderr)
        return 2
    if not args.database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if (
        not args.allow_non_postgres_for_test
        and not args.database_url.startswith(("postgresql://", "postgresql+psycopg://"))
    ):
        print("ERROR: Operation Layer handoff requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(args.database_url)
    try:
        with engine.begin() as conn:
            report = materialize_next_action_time_operation_layer_handoff(
                conn,
                ticket_id=args.ticket_id,
                finalgate_pass_id=args.finalgate_pass_id,
                now_ms=args.now_ms,
            )
    except sa.exc.SQLAlchemyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    _write_json(Path(args.output_json), report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
    else:
        print(report["status"])
    return 0 if report["status"] in {
        "operation_layer_handoff_ready",
        "operation_layer_handoff_already_exists",
        "no_finalgate_ready_ticket",
    } else 1


def _handoff_blockers(
    control_state: dict[str, Any],
    *,
    ticket: dict[str, Any],
    finalgate_pass_id: str,
    now_ms: int,
) -> list[str]:
    blockers: list[str] = []
    if ticket.get("status") != "finalgate_ready":
        blockers.append(f"ticket_status_not_finalgate_ready:{ticket.get('status') or 'missing'}")
    if int(ticket.get("expires_at_ms") or 0) <= now_ms:
        blockers.append("ticket_expired")
    expected_pass_id = _latest_finalgate_pass_id(
        control_state,
        str(ticket.get("ticket_id") or ""),
    )
    if not expected_pass_id:
        blockers.append("finalgate_pass_id_missing")
    elif expected_pass_id != finalgate_pass_id:
        blockers.append(
            "finalgate_pass_id_mismatch:"
            f"expected={expected_pass_id}:actual={finalgate_pass_id}"
        )
    blockers.extend(_ticket_lineage_blockers(control_state, ticket=ticket, now_ms=now_ms))
    return _dedupe(blockers)


def _ticket_lineage_blockers(
    control_state: dict[str, Any],
    *,
    ticket: dict[str, Any],
    now_ms: int,
) -> list[str]:
    blockers: list[str] = []
    runtime_scope = _row_by_id(
        control_state,
        "runtime_scope_bindings",
        "runtime_scope_binding_id",
        ticket.get("runtime_scope_binding_id"),
        blockers,
        "runtime_scope_binding_missing",
    )
    budget = _row_by_id(
        control_state,
        "budget_reservations",
        "budget_reservation_id",
        ticket.get("budget_reservation_id"),
        blockers,
        "budget_reservation_missing",
    )
    protection = _row_by_id(
        control_state,
        "protection_references",
        "protection_ref_id",
        ticket.get("protection_ref_id"),
        blockers,
        "protection_ref_missing",
    )
    execution_policy = _row_by_id(
        control_state,
        "execution_policies",
        "execution_policy_id",
        ticket.get("execution_policy_id"),
        blockers,
        "execution_policy_missing",
    )
    for label, row in (
        ("runtime_scope", runtime_scope),
        ("budget", budget),
        ("protection", protection),
        ("execution_policy", execution_policy),
    ):
        _assert_ticket_scope(blockers, ticket=ticket, row=row, label=label)
    if runtime_scope:
        for flag in (
            "selected_strategygroup_scope",
            "symbol_side_scope_closed",
            "notional_leverage_scope_closed",
            "live_submit_allowed",
        ):
            if runtime_scope.get(flag) is not True:
                blockers.append(f"runtime_scope_not_closed:{flag}")
    if budget and budget.get("ticket_id") != ticket.get("ticket_id"):
        blockers.append("budget_reservation_ticket_mismatch")
    if budget and budget.get("status") not in {"consumed"}:
        blockers.append(f"budget_reservation_status_not_consumed:{budget.get('status')}")
    if protection and int(protection.get("expires_at_ms") or 0) <= now_ms:
        blockers.append("protection_ref_expired")
    if execution_policy and execution_policy.get("status") != "current":
        blockers.append("execution_policy_not_current")
    return blockers


def _build_handoff(
    ticket: dict[str, Any],
    *,
    finalgate_pass_id: str,
    now_ms: int,
) -> dict[str, Any]:
    operation_submit_command_id = _stable_id(
        "operation_submit_command",
        str(ticket["ticket_id"]),
        finalgate_pass_id,
    )
    command_plan = {
        "kind": "ticket_bound_operation_layer_handoff",
        "status": "pending_ticket_bound_protected_submit_adapter",
        "ticket_id": ticket["ticket_id"],
        "finalgate_pass_id": finalgate_pass_id,
        "operation_submit_command_id": operation_submit_command_id,
        "strategy_group_id": ticket["strategy_group_id"],
        "symbol": ticket["symbol"],
        "side": ticket["side"],
        "runtime_profile_id": ticket["runtime_profile_id"],
        "target_notional": str(ticket["target_notional"]),
        "leverage": str(ticket["leverage"]),
        "requires_ticket_bound_protected_submit": True,
        "requires_finalgate_pass_id": True,
        "requires_operation_submit_command_id": True,
        "places_order": False,
        "exchange_write_called": False,
        "order_lifecycle_called": False,
        "non_authority_checkpoint": "prepare_ticket_bound_protected_submit",
    }
    return {
        "operation_layer_handoff_id": _stable_id(
            "operation_layer_handoff",
            str(ticket["ticket_id"]),
            finalgate_pass_id,
        ),
        "ticket_id": ticket["ticket_id"],
        "finalgate_pass_id": finalgate_pass_id,
        "operation_submit_command_id": operation_submit_command_id,
        "action_time_lane_input_id": ticket["action_time_lane_input_id"],
        "strategy_group_id": ticket["strategy_group_id"],
        "symbol": ticket["symbol"],
        "side": ticket["side"],
        "runtime_profile_id": ticket["runtime_profile_id"],
        "status": "handoff_ready",
        "blockers": [],
        "command_plan": command_plan,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "operation_layer_called": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }


def _insert_handoff(conn: sa.engine.Connection, handoff: dict[str, Any]) -> None:
    conn.execute(
        text(
            """
            INSERT INTO brc_operation_layer_handoffs (
              operation_layer_handoff_id, ticket_id, finalgate_pass_id,
              operation_submit_command_id, action_time_lane_input_id,
              strategy_group_id, symbol, side, runtime_profile_id, status,
              blockers, command_plan, authority_boundary, operation_layer_called,
              exchange_write_called, order_created, order_lifecycle_called,
              withdrawal_or_transfer_created, live_profile_changed,
              order_sizing_changed, created_at_ms, updated_at_ms
            ) VALUES (
              :operation_layer_handoff_id, :ticket_id, :finalgate_pass_id,
              :operation_submit_command_id, :action_time_lane_input_id,
              :strategy_group_id, :symbol, :side, :runtime_profile_id, :status,
              :blockers, :command_plan, :authority_boundary, :operation_layer_called,
              :exchange_write_called, :order_created, :order_lifecycle_called,
              :withdrawal_or_transfer_created, :live_profile_changed,
              :order_sizing_changed, :created_at_ms, :updated_at_ms
            )
            """
        ),
        {
            **handoff,
            "blockers": json.dumps(handoff["blockers"], sort_keys=True),
            "command_plan": json.dumps(handoff["command_plan"], sort_keys=True),
        },
    )


def _existing_handoff(
    control_state: dict[str, Any],
    ticket_id: str,
    finalgate_pass_id: str,
) -> dict[str, Any]:
    return next(
        (
            row
            for row in _rows(control_state.get("operation_layer_handoffs"))
            if row.get("ticket_id") == ticket_id
            and row.get("finalgate_pass_id") == finalgate_pass_id
            and row.get("status") == "handoff_ready"
        ),
        {},
    )


def _ticket_by_id(control_state: dict[str, Any], ticket_id: str) -> dict[str, Any]:
    return next(
        (
            row
            for row in _rows(control_state.get("action_time_tickets"))
            if row.get("ticket_id") == ticket_id
        ),
        {},
    )


def _latest_finalgate_pass_id(control_state: dict[str, Any], ticket_id: str) -> str | None:
    events = [
        row
        for row in _rows(control_state.get("action_time_ticket_events"))
        if row.get("ticket_id") == ticket_id and row.get("to_status") == "finalgate_ready"
    ]
    if not events:
        return None
    event = sorted(events, key=lambda row: int(row.get("occurred_at_ms") or 0))[-1]
    payload = _as_dict(event.get("event_payload"))
    return str(payload.get("finalgate_pass_id") or "") or None


def _row_by_id(
    control_state: dict[str, Any],
    table_key: str,
    id_key: str,
    row_id: Any,
    blockers: list[str],
    missing_blocker: str,
) -> dict[str, Any]:
    row_id = str(row_id or "").strip()
    if not row_id:
        blockers.append(missing_blocker)
        return {}
    row = next(
        (item for item in _rows(control_state.get(table_key)) if item.get(id_key) == row_id),
        {},
    )
    if not row:
        blockers.append(missing_blocker)
    return row


def _assert_ticket_scope(
    blockers: list[str],
    *,
    ticket: dict[str, Any],
    row: dict[str, Any],
    label: str,
) -> None:
    if not row:
        return
    for key in ("strategy_group_id", "symbol", "side", "runtime_profile_id"):
        if key in row and row.get(key) is not None and str(row.get(key) or "") != str(ticket.get(key) or ""):
            blockers.append(f"{label}_mismatch:{key}")


def _blocked(
    blockers: list[str],
    *,
    now_ms: int,
    ticket: dict[str, Any],
) -> dict[str, Any]:
    return _result(
        "blocked",
        now_ms=now_ms,
        ticket=ticket,
        handoff={},
        blockers=_dedupe(blockers),
        next_action="repair_ticket_bound_operation_layer_handoff_inputs",
    )


def _result(
    status: str,
    *,
    now_ms: int,
    ticket: dict[str, Any],
    handoff: dict[str, Any],
    blockers: list[str],
    next_action: str,
) -> dict[str, Any]:
    command_plan = _as_dict(handoff.get("command_plan"))
    return {
        "schema": "brc.action_time_operation_layer_handoff.v1",
        "status": status,
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "ticket_id": ticket.get("ticket_id"),
        "finalgate_pass_id": handoff.get("finalgate_pass_id"),
        "operation_layer_handoff_id": handoff.get("operation_layer_handoff_id"),
        "operation_submit_command_id": handoff.get("operation_submit_command_id"),
        "action_time_lane_input_id": ticket.get("action_time_lane_input_id"),
        "strategy_group_id": ticket.get("strategy_group_id"),
        "symbol": ticket.get("symbol"),
        "side": ticket.get("side"),
        "blockers": blockers,
        "command_plan": command_plan,
        "next_action": next_action,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "forbidden_effects": FORBIDDEN_EFFECTS,
        "created_at_ms": now_ms,
    }


def _rows(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return []
        return decoded if isinstance(decoded, list) else []
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
