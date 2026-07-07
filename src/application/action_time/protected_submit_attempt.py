#!/usr/bin/env python3
"""Materialize PG ticket-bound protected submit attempts.

This is the L7 submit adapter boundary:

Action-Time Ticket + FinalGate pass + Operation Layer handoff
+ Runtime Safety State -> brc_ticket_bound_protected_submit_attempts

The disabled-smoke mode records a full ticket-bound submit attempt without
calling the exchange. The real mode only prepares a ticket-bound attempt here;
the API layer performs the official gateway call and then records the result
through ``record_ticket_bound_protected_submit_result``.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.application.action_time.action_time_ticket import (  # noqa: E402
    compute_action_time_ticket_hash,
)
from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
)


AUTHORITY_BOUNDARY = (
    "ticket_bound_protected_submit; "
    "requires_pg_runtime_safety_submit_allowed_and_official_operation_layer"
)
SUBMIT_MODE_DISABLED_SMOKE = "disabled_smoke"
SUBMIT_MODE_REAL_GATEWAY_ACTION = "real_gateway_action"
SUBMIT_MODES = {SUBMIT_MODE_DISABLED_SMOKE, SUBMIT_MODE_REAL_GATEWAY_ACTION}
FORBIDDEN_EFFECTS = {
    "withdrawal_or_transfer_created": False,
    "live_profile_changed": False,
    "order_sizing_changed": False,
}


def prepare_ticket_bound_protected_submit_attempt(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    operation_submit_command_id: str,
    submit_mode: str = SUBMIT_MODE_DISABLED_SMOKE,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    ticket_id = str(ticket_id or "").strip()
    operation_submit_command_id = str(operation_submit_command_id or "").strip()
    submit_mode = str(submit_mode or "").strip()
    if submit_mode not in SUBMIT_MODES:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=[f"invalid_submit_mode:{submit_mode or 'missing'}"],
            attempt={},
            next_action="repair_ticket_bound_submit_mode",
        )
    if not ticket_id:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=["ticket_id_required"],
            attempt={},
            next_action="provide_ticket_id",
        )
    if not operation_submit_command_id:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=["operation_submit_command_id_required"],
            attempt={},
            next_action="provide_operation_submit_command_id",
        )

    try:
        control_state = PgBackedRuntimeControlStateRepository(conn).read_control_state()
    except RuntimeControlStateRepositoryError as exc:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=[f"runtime_control_state_invalid:{exc}"],
            attempt={},
            next_action="repair_pg_runtime_control_state",
        )

    existing = _row_by_id(
        control_state,
        "ticket_bound_protected_submit_attempts",
        "operation_submit_command_id",
        operation_submit_command_id,
    )
    if existing:
        return _result_from_existing(existing, now_ms=now_ms)

    graph = _select_graph(
        control_state,
        ticket_id=ticket_id,
        operation_submit_command_id=operation_submit_command_id,
    )
    blockers = list(graph["blockers"])
    blockers.extend(_graph_blockers(graph, now_ms=now_ms))
    submit_request = _submit_request(graph, now_ms=now_ms) if not blockers else {}
    if not submit_request and not blockers:
        blockers.append("ticket_bound_submit_request_unavailable")

    status = "blocked"
    submit_allowed = False
    official_submit_called = False
    warnings: list[str] = []
    if not blockers:
        submit_allowed = True
        if submit_mode == SUBMIT_MODE_DISABLED_SMOKE:
            status = "disabled_smoke_passed"
            official_submit_called = True
            warnings.append("disabled_smoke_no_exchange_write")
        else:
            status = "submit_prepared"

    attempt = _attempt_row(
        graph,
        submit_mode=submit_mode,
        status=status,
        submit_allowed=submit_allowed,
        blockers=_dedupe(blockers),
        warnings=warnings,
        submit_request=submit_request,
        submit_result=_disabled_smoke_result(graph, submit_request)
        if status == "disabled_smoke_passed"
        else {},
        official_operation_layer_submit_called=official_submit_called,
        exchange_write_called=False,
        order_created=False,
        order_lifecycle_called=False,
        now_ms=now_ms,
    )
    _upsert_row(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        attempt,
    )
    return _result(
        status,
        now_ms=now_ms,
        blockers=list(attempt["blockers"]),
        attempt=attempt,
        next_action=(
            "call_ticket_bound_real_gateway_submit"
            if status == "submit_prepared"
            else (
                "continue_without_exchange_write"
                if status == "disabled_smoke_passed"
                else "repair_ticket_bound_protected_submit_attempt"
            )
        ),
    )


def materialize_next_ticket_bound_protected_submit_attempt(
    conn: sa.engine.Connection,
    *,
    ticket_id: str = "",
    operation_submit_command_id: str = "",
    submit_mode: str = SUBMIT_MODE_DISABLED_SMOKE,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    ticket_id = str(ticket_id or "").strip()
    operation_submit_command_id = str(operation_submit_command_id or "").strip()
    if ticket_id or operation_submit_command_id:
        return prepare_ticket_bound_protected_submit_attempt(
            conn,
            ticket_id=ticket_id,
            operation_submit_command_id=operation_submit_command_id,
            submit_mode=submit_mode,
            now_ms=now_ms,
        )

    try:
        control_state = PgBackedRuntimeControlStateRepository(conn).read_control_state()
    except RuntimeControlStateRepositoryError as exc:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=[f"runtime_control_state_invalid:{exc}"],
            attempt={},
            next_action="repair_pg_runtime_control_state",
        )

    selected = _select_next_handoff_for_protected_submit(
        control_state,
        now_ms=now_ms,
    )
    blockers = list(selected.get("blockers") or [])
    handoff = _as_dict(selected.get("handoff"))
    if blockers:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=blockers,
            attempt={},
            next_action="repair_ticket_bound_operation_layer_handoff_uniqueness",
        )
    if not handoff:
        return _result(
            "no_operation_layer_handoff_ready",
            now_ms=now_ms,
            blockers=[],
            attempt={},
            next_action="continue_watcher_observation",
        )
    return prepare_ticket_bound_protected_submit_attempt(
        conn,
        ticket_id=str(handoff.get("ticket_id") or ""),
        operation_submit_command_id=str(handoff.get("operation_submit_command_id") or ""),
        submit_mode=submit_mode,
        now_ms=now_ms,
    )


def record_ticket_bound_protected_submit_result(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
    submit_result: dict[str, Any],
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    attempt_id = str(protected_submit_attempt_id or "").strip()
    if not attempt_id:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=["protected_submit_attempt_id_required"],
            attempt={},
            next_action="provide_protected_submit_attempt_id",
        )
    table = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    attempt = conn.execute(
        sa.select(table).where(table.c.protected_submit_attempt_id == attempt_id)
    ).mappings().first()
    if attempt is None:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=["protected_submit_attempt_missing"],
            attempt={},
            next_action="repair_ticket_bound_protected_submit_attempt",
        )
    row = {key: _json_safe(value) for key, value in dict(attempt).items()}
    result_status = str(submit_result.get("status") or "")
    result_blockers = [
        str(item)
        for item in (submit_result.get("blockers") or [])
        if str(item).strip()
    ]
    identity_blockers = _result_identity_blockers(row, submit_result)
    blockers = _dedupe(result_blockers + identity_blockers)
    submitted = (
        not blockers
        and result_status == "exchange_submit_orders_submitted"
        and submit_result.get("exchange_write_called") is True
        and submit_result.get("order_lifecycle_called") is True
    )
    failed = (
        result_status.endswith("_failed")
        or bool(result_blockers)
        or (
            bool(result_status)
            and result_status != "exchange_submit_orders_submitted"
        )
    )
    status = (
        "submitted"
        if submitted
        else ("hard_stopped" if identity_blockers else ("submit_failed" if failed else "hard_stopped"))
    )
    updated = {
        **row,
        "status": status,
        "blockers": _dedupe(list(row.get("blockers") or []) + blockers),
        "submit_result": submit_result,
        "identity_evidence": _identity_evidence(row, submit_result, blockers),
        "official_operation_layer_submit_called": True,
        "exchange_write_called": bool(submit_result.get("exchange_write_called")),
        "order_created": bool(submit_result.get("order_created")),
        "order_lifecycle_called": bool(submit_result.get("order_lifecycle_called")),
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        updated,
    )
    if status == "submitted":
        _mark_ticket_submitted(conn, updated, now_ms=now_ms)
    return _result(
        status,
        now_ms=now_ms,
        blockers=list(updated["blockers"]),
        attempt=updated,
        next_action=(
            "run_post_submit_reconciliation_settlement_review"
            if status == "submitted"
            else "repair_ticket_bound_submit_result_identity"
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--ticket-id", default="")
    parser.add_argument("--operation-submit-command-id", default="")
    parser.add_argument("--submit-mode", default=SUBMIT_MODE_DISABLED_SMOKE)
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite or other SQLAlchemy URLs only for local unit tests.",
    )
    args = parser.parse_args(argv)
    if args.require_database_url and not args.database_url:
        print("ERROR: PG_DATABASE_URL is required for protected submit", file=sys.stderr)
        return 2
    if not args.database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if (
        not args.allow_non_postgres_for_test
        and not args.database_url.startswith(("postgresql://", "postgresql+psycopg://"))
    ):
        print("ERROR: protected submit requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(args.database_url)
    try:
        with engine.begin() as conn:
            report = materialize_next_ticket_bound_protected_submit_attempt(
                conn,
                ticket_id=args.ticket_id,
                operation_submit_command_id=args.operation_submit_command_id,
                submit_mode=args.submit_mode,
                now_ms=args.now_ms,
            )
    except sa.exc.SQLAlchemyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
    else:
        print(report["status"])
    return 1 if report["status"] == "blocked" else 0


def _select_next_handoff_for_protected_submit(
    control_state: dict[str, Any],
    *,
    now_ms: int,
) -> dict[str, Any]:
    existing_operation_submit_command_ids = {
        str(row.get("operation_submit_command_id") or "")
        for row in _rows(control_state.get("ticket_bound_protected_submit_attempts"))
        if row.get("operation_submit_command_id")
    }
    live_finalgate_ready_ticket_ids = {
        str(row.get("ticket_id") or "")
        for row in _rows(control_state.get("action_time_tickets"))
        if row.get("status") == "finalgate_ready"
        and int(row.get("expires_at_ms") or 0) > now_ms
    }
    ready_handoffs = [
        row
        for row in _rows(control_state.get("operation_layer_handoffs"))
        if row.get("status") == "handoff_ready"
        and row.get("operation_submit_command_id")
        and row.get("ticket_id")
        and str(row.get("ticket_id") or "") in live_finalgate_ready_ticket_ids
    ]
    unattempted = [
        row
        for row in ready_handoffs
        if str(row.get("operation_submit_command_id") or "")
        not in existing_operation_submit_command_ids
    ]
    candidates = unattempted or ready_handoffs
    if len(candidates) > 1:
        return {
            "handoff": {},
            "blockers": ["multiple_ready_operation_layer_handoffs_for_protected_submit"],
        }
    if not candidates:
        return {"handoff": {}, "blockers": []}
    return {"handoff": candidates[0], "blockers": []}


def _select_graph(
    control_state: dict[str, Any],
    *,
    ticket_id: str,
    operation_submit_command_id: str,
) -> dict[str, Any]:
    ticket = _row_by_id(control_state, "action_time_tickets", "ticket_id", ticket_id)
    handoffs = [
        row
        for row in _rows(control_state.get("operation_layer_handoffs"))
        if row.get("ticket_id") == ticket_id
        and row.get("operation_submit_command_id") == operation_submit_command_id
    ]
    blockers: list[str] = []
    if len(handoffs) > 1:
        blockers.append("multiple_operation_layer_handoffs_for_submit_command")
    handoff = handoffs[0] if len(handoffs) == 1 else {}
    lane = _row_by_id(
        control_state,
        "action_time_lane_inputs",
        "action_time_lane_input_id",
        ticket.get("action_time_lane_input_id") if ticket else "",
    )
    runtime_safety = _row_by_id(
        control_state,
        "runtime_safety_state",
        "runtime_safety_snapshot_id",
        lane.get("runtime_safety_snapshot_id") if lane else "",
    )
    signal = _row_by_id(
        control_state,
        "live_signal_events",
        "signal_event_id",
        ticket.get("signal_event_id") if ticket else "",
    )
    protection = _row_by_id(
        control_state,
        "protection_references",
        "protection_ref_id",
        ticket.get("protection_ref_id") if ticket else "",
    )
    execution_policy = _row_by_id(
        control_state,
        "execution_policies",
        "execution_policy_id",
        ticket.get("execution_policy_id") if ticket else "",
    )
    action_time_fact = _row_by_id(
        control_state,
        "runtime_fact_snapshots",
        "fact_snapshot_id",
        ticket.get("action_time_fact_snapshot_id") if ticket else "",
    )
    return {
        "blockers": blockers,
        "ticket": ticket,
        "handoff": handoff,
        "lane": lane,
        "runtime_safety": runtime_safety,
        "signal": signal,
        "protection": protection,
        "execution_policy": execution_policy,
        "action_time_fact": action_time_fact,
    }


def _graph_blockers(graph: dict[str, Any], *, now_ms: int) -> list[str]:
    blockers: list[str] = list(graph.get("blockers") or [])
    ticket = _as_dict(graph.get("ticket"))
    handoff = _as_dict(graph.get("handoff"))
    safety = _as_dict(graph.get("runtime_safety"))
    lane = _as_dict(graph.get("lane"))
    signal = _as_dict(graph.get("signal"))
    protection = _as_dict(graph.get("protection"))
    execution_policy = _as_dict(graph.get("execution_policy"))
    if not ticket:
        blockers.append("action_time_ticket_missing")
    if not handoff:
        blockers.append("operation_layer_handoff_missing")
    if not safety:
        blockers.append("runtime_safety_snapshot_missing")
    if not lane:
        blockers.append("action_time_lane_input_missing")
    if not signal:
        blockers.append("signal_event_missing")
    if not protection:
        blockers.append("protection_ref_missing")
    if not execution_policy:
        blockers.append("execution_policy_missing")
    if blockers:
        return _dedupe(blockers)

    if ticket.get("status") != "finalgate_ready":
        blockers.append(f"ticket_status_not_finalgate_ready:{ticket.get('status')}")
    if int(ticket.get("expires_at_ms") or 0) <= now_ms:
        blockers.append("ticket_expired")
    if compute_action_time_ticket_hash(ticket) != ticket.get("ticket_hash"):
        blockers.append("ticket_hash_mismatch")
    if handoff.get("status") != "handoff_ready":
        blockers.append(f"operation_layer_handoff_status_not_ready:{handoff.get('status')}")
    if safety.get("submit_allowed") is not True:
        blockers.append("runtime_safety_submit_allowed_false")
    if safety.get("safety_state") != "live_submit_ready":
        blockers.append(f"runtime_safety_state_not_ready:{safety.get('safety_state')}")
    if int(safety.get("valid_until_ms") or 0) <= now_ms:
        blockers.append("runtime_safety_snapshot_expired")
    if safety.get("blockers"):
        blockers.append("runtime_safety_snapshot_has_blockers")
    for flag in (
        "finalgate_ready",
        "operation_layer_ready",
        "protection_ready",
        "facts_fresh",
        "trusted_fact_refs_complete",
    ):
        if safety.get(flag) is not True:
            blockers.append(f"runtime_safety_flag_false:{flag}")
    if safety.get("active_position_conflict") is not False:
        blockers.append("runtime_safety_active_position_conflict")

    refs = _as_dict(safety.get("trusted_fact_refs"))
    expected = {
        "ticket_id": ticket.get("ticket_id"),
        "ticket_hash": ticket.get("ticket_hash"),
        "finalgate_pass_id": handoff.get("finalgate_pass_id"),
        "operation_layer_handoff_id": handoff.get("operation_layer_handoff_id"),
        "operation_submit_command_id": handoff.get("operation_submit_command_id"),
        "signal_event_id": ticket.get("signal_event_id"),
        "protection_ref_id": ticket.get("protection_ref_id"),
    }
    for key, expected_value in expected.items():
        if str(refs.get(key) or "") != str(expected_value or ""):
            blockers.append(f"runtime_safety_ref_mismatch:{key}")

    command_plan = _as_dict(handoff.get("command_plan"))
    if command_plan.get("kind") != "ticket_bound_operation_layer_handoff":
        blockers.append("operation_layer_handoff_command_kind_invalid")
    if command_plan.get("requires_ticket_bound_protected_submit") is not True:
        blockers.append("ticket_bound_protected_submit_requirement_missing")
    for key in ("ticket_id", "finalgate_pass_id", "operation_submit_command_id"):
        if str(command_plan.get(key) or "") != str(handoff.get(key) or ticket.get(key) or ""):
            blockers.append(f"operation_layer_handoff_command_mismatch:{key}")
    if signal.get("source_kind") != "live_market":
        blockers.append(f"signal_event_not_live_market:{signal.get('source_kind')}")
    if signal.get("status") != "facts_validated":
        blockers.append(f"signal_event_status_not_validated:{signal.get('status')}")
    if int(signal.get("created_at_ms") or 0) == int(signal.get("event_time_ms") or 0):
        blockers.append("signal_generated_at_used_as_event_time")
    if int(protection.get("expires_at_ms") or 0) <= now_ms:
        blockers.append("protection_ref_expired")
    if execution_policy.get("status") != "current":
        blockers.append(f"execution_policy_not_current:{execution_policy.get('status')}")
    return _dedupe(blockers)


def _submit_request(graph: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
    ticket = _as_dict(graph.get("ticket"))
    protection = _as_dict(graph.get("protection"))
    execution_policy = _as_dict(graph.get("execution_policy"))
    action_time_fact = _as_dict(graph.get("action_time_fact"))
    price = _execution_reference_price(
        action_time_fact=action_time_fact,
        protection=protection,
    )
    target_notional = _decimal(ticket.get("target_notional"))
    if price <= 0 or target_notional <= 0:
        return {}
    amount = target_notional / price
    direction = "LONG" if ticket.get("side") == "long" else "SHORT"
    entry_side = "buy" if direction == "LONG" else "sell"
    protection_side = "sell" if direction == "LONG" else "buy"
    entry_order_id = _stable_id(
        "ticket_entry_order",
        str(ticket["ticket_id"]),
        str(graph["handoff"]["operation_submit_command_id"]),
    )
    protection_order_id = _stable_id(
        "ticket_protection_order",
        str(ticket["ticket_id"]),
        str(graph["handoff"]["operation_submit_command_id"]),
    )
    symbol = str(ticket.get("exchange_instrument_id") or ticket.get("symbol") or "")
    entry_order_type = _gateway_order_type(str(execution_policy.get("order_type") or "market"))
    protection_order_type = _gateway_order_type(
        str(protection.get("stop_order_type") or "stop_market")
    )
    return {
        "schema": "brc.ticket_bound_protected_submit_request.v1",
        "ticket_id": ticket.get("ticket_id"),
        "operation_submit_command_id": graph["handoff"].get("operation_submit_command_id"),
        "strategy_group_id": ticket.get("strategy_group_id"),
        "symbol": ticket.get("symbol"),
        "exchange_symbol": symbol,
        "side": ticket.get("side"),
        "direction": direction,
        "target_notional": str(target_notional),
        "reference_price": str(price),
        "amount": str(amount),
        "created_at_ms": now_ms,
        "orders": [
            {
                "local_order_id": entry_order_id,
                "order_role": "ENTRY",
                "symbol": symbol,
                "direction": direction,
                "gateway_order_type": entry_order_type,
                "gateway_side": entry_side,
                "amount": str(amount),
                "price": None,
                "trigger_price": None,
                "reduce_only": False,
                "client_order_id": entry_order_id,
            },
            {
                "local_order_id": protection_order_id,
                "parent_order_id": entry_order_id,
                "order_role": "SL",
                "symbol": symbol,
                "direction": direction,
                "gateway_order_type": protection_order_type,
                "gateway_side": protection_side,
                "amount": str(amount),
                "price": None,
                "trigger_price": str(protection.get("reference_price")),
                "reduce_only": True,
                "client_order_id": protection_order_id,
            },
        ],
    }


def _attempt_row(
    graph: dict[str, Any],
    *,
    submit_mode: str,
    status: str,
    submit_allowed: bool,
    blockers: list[str],
    warnings: list[str],
    submit_request: dict[str, Any],
    submit_result: dict[str, Any],
    official_operation_layer_submit_called: bool,
    exchange_write_called: bool,
    order_created: bool,
    order_lifecycle_called: bool,
    now_ms: int,
) -> dict[str, Any]:
    ticket = _as_dict(graph.get("ticket"))
    handoff = _as_dict(graph.get("handoff"))
    safety = _as_dict(graph.get("runtime_safety"))
    lane = _as_dict(graph.get("lane"))
    return {
        "protected_submit_attempt_id": _stable_id(
            "protected_submit_attempt",
            str(handoff.get("operation_submit_command_id") or ""),
        ),
        "ticket_id": str(ticket.get("ticket_id") or handoff.get("ticket_id") or ""),
        "finalgate_pass_id": str(handoff.get("finalgate_pass_id") or ""),
        "operation_layer_handoff_id": str(handoff.get("operation_layer_handoff_id") or ""),
        "operation_submit_command_id": str(handoff.get("operation_submit_command_id") or ""),
        "runtime_safety_snapshot_id": str(safety.get("runtime_safety_snapshot_id") or ""),
        "action_time_lane_input_id": str(
            ticket.get("action_time_lane_input_id")
            or lane.get("action_time_lane_input_id")
            or ""
        ),
        "strategy_group_id": str(ticket.get("strategy_group_id") or handoff.get("strategy_group_id") or ""),
        "symbol": str(ticket.get("symbol") or handoff.get("symbol") or ""),
        "side": str(ticket.get("side") or handoff.get("side") or ""),
        "runtime_profile_id": str(ticket.get("runtime_profile_id") or handoff.get("runtime_profile_id") or ""),
        "submit_mode": submit_mode,
        "status": status,
        "submit_allowed": submit_allowed,
        "blockers": blockers,
        "warnings": warnings,
        "trusted_fact_refs": _as_dict(safety.get("trusted_fact_refs")),
        "submit_request": submit_request,
        "submit_result": submit_result,
        "identity_evidence": _identity_evidence(
            {
                "ticket_id": ticket.get("ticket_id"),
                "operation_submit_command_id": handoff.get("operation_submit_command_id"),
                "strategy_group_id": ticket.get("strategy_group_id"),
                "symbol": ticket.get("symbol"),
                "side": ticket.get("side"),
                "submit_request": submit_request,
            },
            submit_result,
            blockers,
        ),
        "official_operation_layer_submit_called": official_operation_layer_submit_called,
        "exchange_write_called": exchange_write_called,
        "order_created": order_created,
        "order_lifecycle_called": order_lifecycle_called,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }


def _disabled_smoke_result(
    graph: dict[str, Any],
    submit_request: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "brc.ticket_bound_protected_submit_result.v1",
        "status": "exchange_submit_execution_disabled",
        "ticket_id": _as_dict(graph.get("ticket")).get("ticket_id"),
        "operation_submit_command_id": _as_dict(graph.get("handoff")).get(
            "operation_submit_command_id"
        ),
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "submitted_orders": [],
        "submit_request_order_ids": [
            order.get("local_order_id")
            for order in submit_request.get("orders", [])
            if order.get("local_order_id")
        ],
    }


def _result_identity_blockers(
    attempt: dict[str, Any],
    submit_result: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    result_status = str(submit_result.get("status") or "")
    if attempt.get("status") != "submit_prepared":
        blockers.append(
            "protected_submit_attempt_status_not_submit_prepared:"
            f"{attempt.get('status')}"
        )
    if attempt.get("submit_mode") != SUBMIT_MODE_REAL_GATEWAY_ACTION:
        blockers.append(
            f"protected_submit_attempt_mode_not_real:{attempt.get('submit_mode')}"
        )
    if attempt.get("submit_allowed") is not True:
        blockers.append("protected_submit_attempt_submit_allowed_false")
    for key in (
        "ticket_id",
        "operation_submit_command_id",
        "strategy_group_id",
        "symbol",
        "side",
    ):
        actual = str(submit_result.get(key) or "")
        expected = str(attempt.get(key) or "")
        if not actual:
            blockers.append(f"submit_result_identity_missing:{key}")
        elif actual != expected:
            blockers.append(f"submit_result_identity_mismatch:{key}")
    request_order_ids = {
        str(order.get("local_order_id") or "")
        for order in _as_dict(attempt.get("submit_request")).get("orders", [])
        if order.get("local_order_id")
    }
    submitted_order_ids = {
        str(order.get("local_order_id") or "")
        for order in submit_result.get("submitted_orders", [])
        if order.get("local_order_id")
    }
    if result_status == "exchange_submit_orders_submitted":
        if not request_order_ids:
            blockers.append("submit_request_order_ids_missing")
        if not submitted_order_ids:
            blockers.append("submit_result_submitted_order_ids_missing")
        if not submitted_order_ids.issubset(request_order_ids):
            blockers.append("submit_result_order_id_not_in_ticket_request")
        if request_order_ids and submitted_order_ids != request_order_ids:
            blockers.append("submit_result_order_ids_incomplete")
        for key in ("exchange_write_called", "order_created", "order_lifecycle_called"):
            if submit_result.get(key) is not True:
                blockers.append(f"submit_result_required_effect_false:{key}")
    for key, expected in FORBIDDEN_EFFECTS.items():
        if submit_result.get(key) not in {expected, None, "", 0}:
            blockers.append(f"submit_result_forbidden_effect:{key}")
    return _dedupe(blockers)


def _identity_evidence(
    attempt: dict[str, Any],
    submit_result: dict[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    return {
        "schema": "brc.ticket_bound_submit_identity_evidence.v1",
        "ticket_id": attempt.get("ticket_id"),
        "operation_submit_command_id": attempt.get("operation_submit_command_id"),
        "strategy_group_id": attempt.get("strategy_group_id"),
        "symbol": attempt.get("symbol"),
        "side": attempt.get("side"),
        "submit_result_status": submit_result.get("status"),
        "submitted_order_ids": [
            order.get("local_order_id")
            for order in submit_result.get("submitted_orders", [])
            if order.get("local_order_id")
        ],
        "identity_blockers": blockers,
    }


def _mark_ticket_submitted(
    conn: sa.engine.Connection,
    attempt: dict[str, Any],
    *,
    now_ms: int,
) -> None:
    ticket_table = _table(conn, "brc_action_time_tickets")
    handoff_table = _table(conn, "brc_operation_layer_handoffs")
    conn.execute(
        ticket_table.update()
        .where(ticket_table.c.ticket_id == attempt["ticket_id"])
        .values(status="submitted")
    )
    conn.execute(
        handoff_table.update()
        .where(
            handoff_table.c.operation_layer_handoff_id
            == attempt["operation_layer_handoff_id"]
        )
        .values(status="submitted", updated_at_ms=now_ms)
    )
    event_table = _table(conn, "brc_action_time_ticket_events")
    event_id = _stable_id(
        "ticket_event",
        str(attempt["ticket_id"]),
        "submitted",
        str(attempt["protected_submit_attempt_id"]),
    )
    existing = conn.execute(
        sa.select(event_table.c.ticket_event_id).where(
            event_table.c.ticket_event_id == event_id
        )
    ).first()
    if existing:
        return
    conn.execute(
        event_table.insert().values(
            ticket_event_id=event_id,
            ticket_id=attempt["ticket_id"],
            action_time_lane_input_id=attempt["action_time_lane_input_id"],
            from_status="finalgate_ready",
            to_status="submitted",
            transition_reason="ticket_bound_protected_submit_completed",
            trigger_ref=attempt["protected_submit_attempt_id"],
            writer="ticket_bound_protected_submit_adapter",
            event_payload={
                "operation_submit_command_id": attempt["operation_submit_command_id"],
                "runtime_safety_snapshot_id": attempt["runtime_safety_snapshot_id"],
            },
            occurred_at_ms=now_ms,
            created_at_ms=now_ms,
        )
    )


def _result_from_existing(existing: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
    status = str(existing.get("status") or "")
    if status == "submit_prepared":
        blockers = [
            "protected_submit_attempt_already_prepared",
            "duplicate_submit_risk_requires_reconciliation",
        ]
        next_action = "reconcile_existing_submit_prepared_attempt_before_retry"
        result_status = "blocked"
    else:
        blockers = list(existing.get("blockers") or [])
        next_action = "use_existing_ticket_bound_protected_submit_attempt"
        result_status = status or "blocked"
    return _result(
        result_status,
        now_ms=now_ms,
        blockers=blockers,
        attempt=existing,
        next_action=next_action,
        extra={"idempotent_existing_attempt": True},
    )


def _execution_reference_price(
    *,
    action_time_fact: dict[str, Any],
    protection: dict[str, Any],
) -> Decimal:
    fact_values = _as_dict(action_time_fact.get("fact_values"))
    for key in (
        "last_price",
        "mark_price",
        "current_price",
        "close",
        "entry_price",
        "opening_range_low_reference",
    ):
        if key in fact_values:
            value = _decimal(fact_values.get(key))
            if value > 0:
                return value
    return _decimal(protection.get("reference_price"))


def _gateway_order_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"market", "limit", "stop_market"}:
        return normalized
    if normalized in {"stop-limit", "stop_limit"}:
        return "stop_limit"
    return "market"


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _row_by_id(
    control_state: dict[str, Any],
    table_key: str,
    id_key: str,
    id_value: Any,
) -> dict[str, Any]:
    expected = str(id_value or "")
    if not expected:
        return {}
    for row in _rows(control_state.get(table_key)):
        if str(row.get(id_key) or "") == expected:
            return dict(row)
    return {}


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _upsert_row(
    conn: sa.engine.Connection,
    table_name: str,
    pk_name: str,
    row: dict[str, Any],
) -> None:
    table = _table(conn, table_name)
    pk_value = row[pk_name]
    existing = conn.execute(
        sa.select(table.c[pk_name]).where(table.c[pk_name] == pk_value)
    ).first()
    if existing:
        conn.execute(
            table.update()
            .where(table.c[pk_name] == pk_value)
            .values(**{key: value for key, value in row.items() if key in table.c})
        )
        return
    conn.execute(table.insert().values(**{key: value for key, value in row.items() if key in table.c}))


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item)
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _result(
    status: str,
    *,
    now_ms: int,
    blockers: list[str],
    attempt: dict[str, Any],
    next_action: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": "brc.ticket_bound_protected_submit_attempt.v1",
        "status": status,
        "protected_submit_attempt_id": attempt.get("protected_submit_attempt_id"),
        "ticket_id": attempt.get("ticket_id"),
        "finalgate_pass_id": attempt.get("finalgate_pass_id"),
        "operation_layer_handoff_id": attempt.get("operation_layer_handoff_id"),
        "operation_submit_command_id": attempt.get("operation_submit_command_id"),
        "runtime_safety_snapshot_id": attempt.get("runtime_safety_snapshot_id"),
        "action_time_lane_input_id": attempt.get("action_time_lane_input_id"),
        "strategy_group_id": attempt.get("strategy_group_id"),
        "symbol": attempt.get("symbol"),
        "side": attempt.get("side"),
        "submit_mode": attempt.get("submit_mode"),
        "submit_allowed": attempt.get("submit_allowed", False),
        "blockers": blockers,
        "warnings": attempt.get("warnings", []),
        "submit_request": attempt.get("submit_request", {}),
        "submit_result": attempt.get("submit_result", {}),
        "identity_evidence": attempt.get("identity_evidence", {}),
        "official_operation_layer_submit_called": attempt.get(
            "official_operation_layer_submit_called",
            False,
        ),
        "exchange_write_called": attempt.get("exchange_write_called", False),
        "order_created": attempt.get("order_created", False),
        "order_lifecycle_called": attempt.get("order_lifecycle_called", False),
        "withdrawal_or_transfer_created": attempt.get(
            "withdrawal_or_transfer_created",
            False,
        ),
        "live_profile_changed": attempt.get("live_profile_changed", False),
        "order_sizing_changed": attempt.get("order_sizing_changed", False),
        "forbidden_effects": FORBIDDEN_EFFECTS,
        "next_action": next_action,
        "authority_boundary": attempt.get("authority_boundary", AUTHORITY_BOUNDARY),
        "observed_at_ms": now_ms,
    }
    if extra:
        payload.update(extra)
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
