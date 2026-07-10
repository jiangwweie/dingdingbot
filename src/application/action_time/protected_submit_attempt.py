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
from src.application.action_time.capital_safety_guard import (  # noqa: E402
    current_scope_blockers,
)
from src.application.action_time.budget_stop_risk import (  # noqa: E402
    budget_stop_risk_blockers,
)
from src.application.action_time.lifecycle_safety_core import (  # noqa: E402
    classify_sequential_submit_result,
)
from src.application.action_time.exchange_command import (  # noqa: E402
    materialize_ticket_bound_exchange_commands,
)
from src.domain.ticket_bound_exchange_command import (  # noqa: E402
    deterministic_client_order_id,
)
from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
)


AUTHORITY_BOUNDARY = (
    "ticket_bound_protected_submit; "
    "requires_pg_runtime_safety_submit_allowed_and_official_operation_layer"
)
SUBMIT_MODE_DECISION_AUTHORITY_BOUNDARY = (
    "ticket_bound_submit_mode_decision; "
    "requires_owner_policy_runtime_scope_safety_gateway_and_deployment_arming"
)
SUBMIT_MODE_DISABLED_SMOKE = "disabled_smoke"
SUBMIT_MODE_REAL_GATEWAY_ACTION = "real_gateway_action"
SUBMIT_MODES = {SUBMIT_MODE_DISABLED_SMOKE, SUBMIT_MODE_REAL_GATEWAY_ACTION}
SUBMIT_MODE_DECISIONS = {
    "blocked",
    SUBMIT_MODE_DISABLED_SMOKE,
    SUBMIT_MODE_REAL_GATEWAY_ACTION,
}
PRODUCTION_SUBMIT_EXECUTION_POLICY_ARMED = "armed"
PRODUCTION_SUBMIT_EXECUTION_POLICIES = {
    "disabled",
    PRODUCTION_SUBMIT_EXECUTION_POLICY_ARMED,
}
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
    if existing and not _blocked_attempt_can_refresh(existing):
        return _result_from_existing(existing, now_ms=now_ms)

    graph = _select_graph(
        control_state,
        ticket_id=ticket_id,
        operation_submit_command_id=operation_submit_command_id,
    )
    blockers = list(graph["blockers"])
    blockers.extend(_graph_blockers(graph, now_ms=now_ms))
    submit_mode_decision = _current_submit_mode_decision(
        control_state,
        operation_submit_command_id=operation_submit_command_id,
        now_ms=now_ms,
    )
    if submit_mode == SUBMIT_MODE_REAL_GATEWAY_ACTION:
        blockers.extend(
            _real_submit_mode_decision_blockers(
                submit_mode_decision,
                ticket_id=ticket_id,
                operation_submit_command_id=operation_submit_command_id,
            )
        )
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
        submit_mode_decision_id=str(
            submit_mode_decision.get("submit_mode_decision_id") or ""
        ),
        official_operation_layer_submit_called=official_submit_called,
        exchange_write_called=False,
        order_created=False,
        order_lifecycle_called=False,
        now_ms=now_ms,
    )
    if existing:
        attempt["created_at_ms"] = int(existing.get("created_at_ms") or now_ms)
    _upsert_row(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        attempt,
    )
    if status == "submit_prepared":
        materialize_ticket_bound_exchange_commands(
            conn,
            attempt=attempt,
            now_ms=now_ms,
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
        extra={"submit_mode_decision": submit_mode_decision},
    )


def materialize_ticket_bound_submit_mode_decision(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    operation_submit_command_id: str,
    production_submit_execution_policy: str = "disabled",
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    ticket_id = str(ticket_id or "").strip()
    operation_submit_command_id = str(operation_submit_command_id or "").strip()
    production_submit_execution_policy = str(
        production_submit_execution_policy or ""
    ).strip()
    if production_submit_execution_policy not in PRODUCTION_SUBMIT_EXECUTION_POLICIES:
        production_submit_execution_policy = "disabled"
    if not ticket_id:
        return _submit_mode_decision_result(
            {},
            now_ms=now_ms,
            status="blocked",
            blockers=["ticket_id_required"],
            next_action="provide_ticket_id",
        )
    if not operation_submit_command_id:
        return _submit_mode_decision_result(
            {},
            now_ms=now_ms,
            status="blocked",
            blockers=["operation_submit_command_id_required"],
            next_action="provide_operation_submit_command_id",
        )
    try:
        control_state = PgBackedRuntimeControlStateRepository(conn).read_control_state()
    except RuntimeControlStateRepositoryError as exc:
        return _submit_mode_decision_result(
            {},
            now_ms=now_ms,
            status="blocked",
            blockers=[f"runtime_control_state_invalid:{exc}"],
            next_action="repair_pg_runtime_control_state",
        )

    graph = _select_graph(
        control_state,
        ticket_id=ticket_id,
        operation_submit_command_id=operation_submit_command_id,
    )
    blockers = list(graph["blockers"])
    blockers.extend(_graph_blockers(graph, now_ms=now_ms))
    blockers.extend(
        _submit_mode_authority_blockers(
            graph,
            production_submit_execution_policy=production_submit_execution_policy,
        )
    )
    blockers = _dedupe(blockers)
    decision = SUBMIT_MODE_REAL_GATEWAY_ACTION if not blockers else "blocked"
    first_blocker = blockers[0] if blockers else ""
    reason = (
        "production_live_submit_ready"
        if decision == SUBMIT_MODE_REAL_GATEWAY_ACTION
        else first_blocker or "submit_mode_decision_blocked"
    )
    row = _submit_mode_decision_row(
        graph,
        decision=decision,
        decision_reason=reason,
        first_blocker=first_blocker,
        blockers=blockers,
        production_submit_execution_policy=production_submit_execution_policy,
        now_ms=now_ms,
    )
    _upsert_row(
        conn,
        "brc_ticket_bound_submit_mode_decisions",
        "submit_mode_decision_id",
        row,
    )
    return _submit_mode_decision_result(
        row,
        now_ms=now_ms,
        status=decision,
        blockers=blockers,
        next_action=_submit_mode_decision_next_action(row),
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
    outcome_unknown = result_status in {
        "exchange_submit_outcome_unknown",
        "exchange_command_outcome_unknown",
    }
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
        else (
            "hard_stopped"
            if identity_blockers
            else (
                "submit_outcome_unknown"
                if outcome_unknown
                else ("submit_failed" if failed else "hard_stopped")
            )
        )
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
    lifecycle_classification = None
    if status == "submitted":
        _mark_ticket_submitted(conn, updated, now_ms=now_ms)
    elif not identity_blockers and not outcome_unknown:
        lifecycle_classification = classify_sequential_submit_result(
            attempt=updated,
            submit_result=submit_result,
            blockers=list(updated["blockers"]),
        )
        _materialize_submit_lifecycle_state(
            conn,
            attempt=updated,
            submit_result=submit_result,
            classification=lifecycle_classification,
            now_ms=now_ms,
        )
    return _result(
        status,
        now_ms=now_ms,
        blockers=list(updated["blockers"]),
        attempt=updated,
        next_action=(
            "run_post_submit_reconciliation_settlement_review"
            if status == "submitted"
            else (
                "repair_ticket_bound_submit_result_identity"
                if identity_blockers
                else "reconcile_unknown_exchange_command_before_any_new_submit"
                if outcome_unknown
                else lifecycle_classification.next_action
                if lifecycle_classification
                else "repair_ticket_bound_submit_result_identity"
            )
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
    runtime_scope = _row_by_id(
        control_state,
        "runtime_scope_bindings",
        "runtime_scope_binding_id",
        ticket.get("runtime_scope_binding_id") if ticket else "",
    )
    owner_policy = _row_by_id(
        control_state,
        "owner_policy_current",
        "policy_current_id",
        runtime_scope.get("policy_current_id") if runtime_scope else "",
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
    budget = _row_by_id(
        control_state,
        "budget_reservations",
        "budget_reservation_id",
        ticket.get("budget_reservation_id") if ticket else "",
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
    exchange_instrument = _row_by_id(
        control_state,
        "exchange_instruments",
        "exchange_instrument_id",
        ticket.get("exchange_instrument_id") if ticket else "",
    )
    return {
        "control_state": control_state,
        "blockers": blockers,
        "ticket": ticket,
        "handoff": handoff,
        "lane": lane,
        "runtime_scope": runtime_scope,
        "owner_policy": owner_policy,
        "runtime_safety": runtime_safety,
        "signal": signal,
        "protection": protection,
        "budget": budget,
        "execution_policy": execution_policy,
        "action_time_fact": action_time_fact,
        "exchange_instrument": exchange_instrument,
    }


def _graph_blockers(graph: dict[str, Any], *, now_ms: int) -> list[str]:
    blockers: list[str] = list(graph.get("blockers") or [])
    ticket = _as_dict(graph.get("ticket"))
    handoff = _as_dict(graph.get("handoff"))
    safety = _as_dict(graph.get("runtime_safety"))
    lane = _as_dict(graph.get("lane"))
    signal = _as_dict(graph.get("signal"))
    protection = _as_dict(graph.get("protection"))
    budget = _as_dict(graph.get("budget"))
    execution_policy = _as_dict(graph.get("execution_policy"))
    action_time_fact = _as_dict(graph.get("action_time_fact"))
    exchange_instrument = _as_dict(graph.get("exchange_instrument"))
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
    if not budget:
        blockers.append("budget_reservation_missing")
    if not execution_policy:
        blockers.append("execution_policy_missing")
    if not exchange_instrument:
        blockers.append("exchange_instrument_missing")
    elif str(exchange_instrument.get("status") or "") != "active":
        blockers.append("exchange_instrument_not_active")
    if blockers:
        return _dedupe(blockers)
    blockers.extend(
        current_scope_blockers(
            graph.get("control_state") or {},
            account_id=budget.get("account_id"),
            strategy_group_id=ticket.get("strategy_group_id"),
            symbol=ticket.get("symbol"),
            exchange_instrument_id=ticket.get("exchange_instrument_id"),
            side=ticket.get("side"),
        )
    )

    if ticket.get("status") != "finalgate_ready":
        blockers.append(f"ticket_status_not_finalgate_ready:{ticket.get('status')}")
    if int(ticket.get("expires_at_ms") or 0) <= now_ms:
        blockers.append("ticket_expired")
    if compute_action_time_ticket_hash(ticket) != ticket.get("ticket_hash"):
        blockers.append("ticket_hash_mismatch")
    if ticket.get("execution_eligible") is not True:
        blockers.append("execution_eligibility_missing_or_false")
    if ticket.get("signal_grade") not in {
        "trial_grade_signal",
        "production_grade_signal",
    }:
        blockers.append("execution_eligibility_signal_grade_invalid")
    if ticket.get("required_execution_mode") not in {
        "trial_live",
        "production_live",
    }:
        blockers.append("execution_eligibility_mode_invalid")
    for item_name, item in (
        ("lane", lane),
        ("signal", signal),
        ("runtime_safety", safety),
    ):
        for field in (
            "signal_grade",
            "required_execution_mode",
            "execution_eligible",
            "authority_source_ref",
        ):
            if item.get(field) != ticket.get(field):
                blockers.append(f"execution_eligibility_mismatch:{item_name}:{field}")
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
    if budget.get("ticket_id") != ticket.get("ticket_id"):
        blockers.append("budget_reservation_ticket_mismatch")
    if budget.get("status") != "consumed":
        blockers.append(f"budget_reservation_status_not_consumed:{budget.get('status')}")
    blockers.extend(budget_stop_risk_blockers(budget))
    if _tp1_price(action_time_fact=action_time_fact) <= 0:
        blockers.append("tp1_reference_missing")
    if execution_policy.get("status") != "current":
        blockers.append(f"execution_policy_not_current:{execution_policy.get('status')}")
    return _dedupe(blockers)


def _submit_mode_authority_blockers(
    graph: dict[str, Any],
    *,
    production_submit_execution_policy: str,
) -> list[str]:
    blockers: list[str] = []
    ticket = _as_dict(graph.get("ticket"))
    lane = _as_dict(graph.get("lane"))
    runtime_scope = _as_dict(graph.get("runtime_scope"))
    owner_policy = _as_dict(graph.get("owner_policy"))
    if not runtime_scope:
        blockers.append("runtime_scope_binding_missing")
    if not owner_policy:
        blockers.append("owner_policy_current_missing")
    if blockers:
        return blockers
    blockers.extend(
        current_scope_blockers(
            graph.get("control_state") or {},
            strategy_group_id=ticket.get("strategy_group_id"),
            symbol=ticket.get("symbol"),
            side=ticket.get("side"),
        )
    )
    if lane.get("lane_scope") != "real_submit_candidate":
        blockers.append(f"lane_scope_not_real_submit_candidate:{lane.get('lane_scope')}")
    if runtime_scope.get("status") != "active":
        blockers.append(f"runtime_scope_status_not_active:{runtime_scope.get('status')}")
    if runtime_scope.get("live_submit_allowed") is not True:
        blockers.append("runtime_scope_live_submit_not_allowed")
    for flag in (
        "selected_strategygroup_scope",
        "symbol_side_scope_closed",
        "notional_leverage_scope_closed",
    ):
        if runtime_scope.get(flag) is not True:
            blockers.append(f"runtime_scope_flag_false:{flag}")
    for key in ("strategy_group_id", "symbol", "side", "runtime_profile_id"):
        if str(runtime_scope.get(key) or "") != str(ticket.get(key) or ""):
            blockers.append(f"runtime_scope_ticket_mismatch:{key}")
    if owner_policy.get("enabled_state") != "enabled":
        blockers.append(f"owner_policy_not_enabled:{owner_policy.get('enabled_state')}")
    if str(owner_policy.get("live_submit_allowed") or "") not in {
        "scoped",
        "conditional_hard_gated",
    }:
        blockers.append(
            "owner_policy_live_submit_not_allowed:"
            f"{owner_policy.get('live_submit_allowed')}"
        )
    if production_submit_execution_policy != PRODUCTION_SUBMIT_EXECUTION_POLICY_ARMED:
        blockers.append("production_submit_execution_policy_not_armed")
    blockers.extend(_runtime_gateway_binding_env_blockers())
    return _dedupe(blockers)


def _runtime_gateway_binding_env_blockers() -> list[str]:
    expected = {
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "order_allowed",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
        "RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED": "true",
    }
    blockers: list[str] = []
    for key, expected_value in expected.items():
        actual = os.environ.get(key, "").strip().lower()
        if actual != expected_value:
            blockers.append(f"{key.lower()}_not_{expected_value}")
    return blockers


def _current_submit_mode_decision(
    control_state: dict[str, Any],
    *,
    operation_submit_command_id: str,
    now_ms: int,
) -> dict[str, Any]:
    operation_submit_command_id = str(operation_submit_command_id or "").strip()
    if not operation_submit_command_id:
        return {}
    rows = [
        row
        for row in _rows(control_state.get("ticket_bound_submit_mode_decisions"))
        if str(row.get("operation_submit_command_id") or "")
        == operation_submit_command_id
        and int(row.get("expires_at_ms") or 0) > now_ms
    ]
    if not rows:
        return {}
    return sorted(rows, key=lambda row: int(row.get("created_at_ms") or 0), reverse=True)[
        0
    ]


def _real_submit_mode_decision_blockers(
    decision: dict[str, Any],
    *,
    ticket_id: str,
    operation_submit_command_id: str,
) -> list[str]:
    if not decision:
        return ["submit_mode_decision_missing_for_real_gateway_action"]
    blockers: list[str] = []
    if decision.get("decision") != SUBMIT_MODE_REAL_GATEWAY_ACTION:
        blockers.append(f"submit_mode_decision_not_real:{decision.get('decision')}")
    if str(decision.get("ticket_id") or "") != str(ticket_id or ""):
        blockers.append("submit_mode_decision_ticket_mismatch")
    if str(decision.get("operation_submit_command_id") or "") != str(
        operation_submit_command_id or ""
    ):
        blockers.append("submit_mode_decision_command_mismatch")
    if decision.get("blockers"):
        blockers.append("submit_mode_decision_has_blockers")
    if decision.get("execution_eligible") is not True:
        blockers.append("submit_mode_decision_execution_eligibility_false")
    if decision.get("signal_grade") not in {
        "trial_grade_signal",
        "production_grade_signal",
    }:
        blockers.append("submit_mode_decision_signal_grade_invalid")
    if decision.get("required_execution_mode") not in {
        "trial_live",
        "production_live",
    }:
        blockers.append("submit_mode_decision_execution_mode_invalid")
    return _dedupe(blockers)


def _submit_mode_decision_row(
    graph: dict[str, Any],
    *,
    decision: str,
    decision_reason: str,
    first_blocker: str,
    blockers: list[str],
    production_submit_execution_policy: str,
    now_ms: int,
) -> dict[str, Any]:
    ticket = _as_dict(graph.get("ticket"))
    handoff = _as_dict(graph.get("handoff"))
    safety = _as_dict(graph.get("runtime_safety"))
    lane = _as_dict(graph.get("lane"))
    runtime_scope = _as_dict(graph.get("runtime_scope"))
    owner_policy = _as_dict(graph.get("owner_policy"))
    protection = _as_dict(graph.get("protection"))
    expires_at_ms = _min_positive_ms(
        [
            ticket.get("expires_at_ms"),
            safety.get("valid_until_ms"),
            protection.get("expires_at_ms"),
        ],
        default=now_ms + 300_000,
    )
    operation_submit_command_id = str(
        handoff.get("operation_submit_command_id")
        or ticket.get("operation_submit_command_id")
        or ""
    )
    return {
        "submit_mode_decision_id": _stable_id(
            "submit_mode_decision",
            operation_submit_command_id,
        ),
        "ticket_id": str(ticket.get("ticket_id") or handoff.get("ticket_id") or ""),
        "operation_layer_handoff_id": str(
            handoff.get("operation_layer_handoff_id") or ""
        ),
        "operation_submit_command_id": operation_submit_command_id,
        "runtime_safety_snapshot_id": str(
            safety.get("runtime_safety_snapshot_id") or ""
        ),
        "action_time_lane_input_id": str(
            ticket.get("action_time_lane_input_id")
            or lane.get("action_time_lane_input_id")
            or ""
        ),
        "runtime_scope_binding_id": str(
            runtime_scope.get("runtime_scope_binding_id") or ""
        ),
        "policy_current_id": str(owner_policy.get("policy_current_id") or ""),
        "strategy_group_id": str(
            ticket.get("strategy_group_id") or handoff.get("strategy_group_id") or ""
        ),
        "symbol": str(ticket.get("symbol") or handoff.get("symbol") or ""),
        "side": str(ticket.get("side") or handoff.get("side") or ""),
        "runtime_profile_id": str(
            ticket.get("runtime_profile_id") or handoff.get("runtime_profile_id") or ""
        ),
        "decision": decision,
        "decision_reason": decision_reason,
        "first_blocker": first_blocker,
        "blockers": blockers,
        "warnings": [],
        "evidence_refs": {
            "ticket_id": ticket.get("ticket_id"),
            "finalgate_pass_id": handoff.get("finalgate_pass_id"),
            "operation_layer_handoff_id": handoff.get("operation_layer_handoff_id"),
            "operation_submit_command_id": operation_submit_command_id,
            "runtime_safety_snapshot_id": safety.get("runtime_safety_snapshot_id"),
            "runtime_scope_binding_id": runtime_scope.get("runtime_scope_binding_id"),
            "policy_current_id": owner_policy.get("policy_current_id"),
            "protection_ref_id": ticket.get("protection_ref_id"),
        },
        "production_submit_execution_policy": production_submit_execution_policy,
        "gateway_binding_ready": not any(
            blocker.startswith("runtime_exchange")
            or blocker.startswith("trading_env_")
            or blocker.startswith("exchange_testnet_")
            or blocker.startswith("brc_execution_permission_max_")
            or blocker.startswith("runtime_control_api_")
            or blocker.startswith("runtime_test_signal_injection_")
            for blocker in blockers
        ),
        "authority_boundary": SUBMIT_MODE_DECISION_AUTHORITY_BOUNDARY,
        "created_at_ms": now_ms,
        "expires_at_ms": expires_at_ms,
        "updated_at_ms": now_ms,
        "signal_grade": ticket.get("signal_grade") or "invalid_signal",
        "required_execution_mode": ticket.get("required_execution_mode")
        or "observe_only",
        "execution_eligible": ticket.get("execution_eligible") is True,
        "authority_source_ref": ticket.get("authority_source_ref")
        or "submit-mode:missing-authority-source",
    }


def _submit_mode_decision_result(
    decision_row: dict[str, Any],
    *,
    now_ms: int,
    status: str,
    blockers: list[str],
    next_action: str,
) -> dict[str, Any]:
    return {
        "schema": "brc.ticket_bound_submit_mode_decision.v1",
        "status": status,
        "decision": decision_row.get("decision") or status,
        "submit_mode_decision_id": decision_row.get("submit_mode_decision_id"),
        "ticket_id": decision_row.get("ticket_id"),
        "operation_layer_handoff_id": decision_row.get("operation_layer_handoff_id"),
        "operation_submit_command_id": decision_row.get(
            "operation_submit_command_id"
        ),
        "runtime_safety_snapshot_id": decision_row.get("runtime_safety_snapshot_id"),
        "action_time_lane_input_id": decision_row.get("action_time_lane_input_id"),
        "runtime_scope_binding_id": decision_row.get("runtime_scope_binding_id"),
        "policy_current_id": decision_row.get("policy_current_id"),
        "strategy_group_id": decision_row.get("strategy_group_id"),
        "symbol": decision_row.get("symbol"),
        "side": decision_row.get("side"),
        "runtime_profile_id": decision_row.get("runtime_profile_id"),
        "decision_reason": decision_row.get("decision_reason") or (
            blockers[0] if blockers else status
        ),
        "first_blocker": decision_row.get("first_blocker") or (
            blockers[0] if blockers else ""
        ),
        "blockers": blockers,
        "warnings": decision_row.get("warnings") or [],
        "evidence_refs": decision_row.get("evidence_refs") or {},
        "production_submit_execution_policy": decision_row.get(
            "production_submit_execution_policy"
        ),
        "gateway_binding_ready": decision_row.get("gateway_binding_ready") is True,
        "next_action": next_action,
        "authority_boundary": decision_row.get(
            "authority_boundary",
            SUBMIT_MODE_DECISION_AUTHORITY_BOUNDARY,
        ),
        "observed_at_ms": now_ms,
    }


def _submit_mode_decision_next_action(decision: dict[str, Any]) -> str:
    value = str(decision.get("decision") or "")
    if value == SUBMIT_MODE_REAL_GATEWAY_ACTION:
        return "call_ticket_bound_real_gateway_submit"
    if value == SUBMIT_MODE_DISABLED_SMOKE:
        return "run_disabled_smoke_rehearsal"
    return "repair_ticket_bound_submit_mode_decision"


def _min_positive_ms(values: list[Any], *, default: int) -> int:
    positive: list[int] = []
    for value in values:
        try:
            parsed = int(value or 0)
        except (TypeError, ValueError):
            parsed = 0
        if parsed > 0:
            positive.append(parsed)
    return min(positive) if positive else default


def _submit_request(graph: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
    ticket = _as_dict(graph.get("ticket"))
    protection = _as_dict(graph.get("protection"))
    execution_policy = _as_dict(graph.get("execution_policy"))
    action_time_fact = _as_dict(graph.get("action_time_fact"))
    budget = _as_dict(graph.get("budget"))
    exchange_instrument = _as_dict(graph.get("exchange_instrument"))
    price = _execution_reference_price(
        action_time_fact=action_time_fact,
        protection=protection,
    )
    tp1_price = _tp1_price(action_time_fact=action_time_fact)
    target_notional = _decimal(ticket.get("target_notional"))
    if price <= 0 or target_notional <= 0 or tp1_price <= 0:
        return {}
    amount = target_notional / price
    tp1_amount = amount / Decimal("2")
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
    tp1_order_id = _stable_id(
        "ticket_tp1_order",
        str(ticket["ticket_id"]),
        str(graph["handoff"]["operation_submit_command_id"]),
    )
    symbol = str(exchange_instrument.get("exchange_symbol") or "")
    ticket_id = str(ticket["ticket_id"])
    operation_submit_command_id = str(
        graph["handoff"]["operation_submit_command_id"]
    )
    entry_order_type = _gateway_order_type(str(execution_policy.get("order_type") or "market"))
    protection_order_type = _gateway_order_type(
        str(protection.get("stop_order_type") or "stop_market")
    )
    return {
        "schema": "brc.ticket_bound_protected_submit_request.v1",
        "ticket_id": ticket.get("ticket_id"),
        "operation_submit_command_id": graph["handoff"].get("operation_submit_command_id"),
        "strategy_group_id": ticket.get("strategy_group_id"),
        "account_id": budget.get("account_id"),
        "symbol": ticket.get("symbol"),
        "exchange_symbol": symbol,
        "exchange_instrument_id": ticket.get("exchange_instrument_id"),
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
                "client_order_id": deterministic_client_order_id(
                    ticket_id,
                    operation_submit_command_id,
                    "ENTRY",
                    1,
                ),
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
                "client_order_id": deterministic_client_order_id(
                    ticket_id,
                    operation_submit_command_id,
                    "SL",
                    1,
                ),
            },
            {
                "local_order_id": tp1_order_id,
                "parent_order_id": entry_order_id,
                "order_role": "TP1",
                "symbol": symbol,
                "direction": direction,
                "gateway_order_type": "limit",
                "gateway_side": protection_side,
                "amount": str(tp1_amount),
                "price": str(tp1_price),
                "trigger_price": None,
                "reduce_only": True,
                "client_order_id": deterministic_client_order_id(
                    ticket_id,
                    operation_submit_command_id,
                    "TP1",
                    1,
                ),
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
    submit_mode_decision_id: str,
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
        "submit_mode_decision_id": submit_mode_decision_id,
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
        "signal_grade": ticket.get("signal_grade") or "invalid_signal",
        "required_execution_mode": ticket.get("required_execution_mode")
        or "observe_only",
        "execution_eligible": ticket.get("execution_eligible") is True,
        "authority_source_ref": ticket.get("authority_source_ref")
        or "protected-submit:missing-authority-source",
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
        blockers.extend(_submitted_order_semantic_blockers(attempt, submit_result))
        for key in ("exchange_write_called", "order_created", "order_lifecycle_called"):
            if submit_result.get(key) is not True:
                blockers.append(f"submit_result_required_effect_false:{key}")
    for key, expected in FORBIDDEN_EFFECTS.items():
        if submit_result.get(key) not in {expected, None, "", 0}:
            blockers.append(f"submit_result_forbidden_effect:{key}")
    return _dedupe(blockers)


def _submitted_order_semantic_blockers(
    attempt: dict[str, Any],
    submit_result: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    request_orders = [
        dict(order)
        for order in _as_dict(attempt.get("submit_request")).get("orders", [])
        if isinstance(order, dict)
    ]
    submitted_orders = [
        dict(order)
        for order in submit_result.get("submitted_orders", [])
        if isinstance(order, dict)
    ]
    for role in ("ENTRY", "SL", "TP1"):
        request_order = _order_by_role(request_orders, role)
        submitted_order = _order_by_role(submitted_orders, role)
        if not request_order or not submitted_order:
            continue
        if str(submitted_order.get("local_order_id") or "") != str(
            request_order.get("local_order_id") or ""
        ):
            blockers.append(f"submit_result_{role.lower()}_local_order_id_mismatch")
        if not str(submitted_order.get("exchange_order_id") or "").strip():
            blockers.append(f"submit_result_{role.lower()}_exchange_order_id_missing")
        if _decimal(submitted_order.get("amount") or request_order.get("amount")) <= 0:
            blockers.append(f"submit_result_{role.lower()}_amount_missing")
        if role == "ENTRY":
            if submitted_order.get("reduce_only") is not False:
                blockers.append("submit_result_entry_reduce_only_invalid")
            if _terminal_order_status(submitted_order):
                blockers.append("submit_result_entry_terminal_status")
        else:
            if submitted_order.get("reduce_only") is not True:
                blockers.append(f"submit_result_{role.lower()}_reduce_only_required")
            if _terminal_order_status(submitted_order):
                blockers.append(f"submit_result_{role.lower()}_terminal_status")
            if role == "SL" and _decimal(
                submitted_order.get("trigger_price") or request_order.get("trigger_price")
            ) <= 0:
                blockers.append("submit_result_sl_trigger_price_missing")
            if role == "TP1" and _decimal(
                submitted_order.get("price") or request_order.get("price")
            ) <= 0:
                blockers.append("submit_result_tp1_price_missing")
    return _dedupe(blockers)


def _terminal_order_status(order: dict[str, Any]) -> bool:
    status = str(order.get("status") or "").strip().lower()
    return status in {"canceled", "cancelled", "rejected", "expired", "failed"}


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
        "runtime_profile_id": attempt.get("runtime_profile_id"),
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


def _materialize_submit_lifecycle_state(
    conn: sa.engine.Connection,
    *,
    attempt: dict[str, Any],
    submit_result: dict[str, Any],
    classification: Any,
    now_ms: int,
) -> None:
    submitted_orders = [
        dict(order)
        for order in submit_result.get("submitted_orders", [])
        if isinstance(order, dict)
    ]
    entry_order = _order_by_role(submitted_orders, "ENTRY")
    row = {
        "lifecycle_run_id": _stable_id(
            "ticket_order_lifecycle",
            str(attempt["ticket_id"]),
        ),
        "ticket_id": str(attempt["ticket_id"]),
        "protected_submit_attempt_id": str(attempt["protected_submit_attempt_id"]),
        "strategy_group_id": str(attempt["strategy_group_id"]),
        "symbol": str(attempt["symbol"]),
        "side": str(attempt["side"]),
        "runtime_profile_id": str(attempt["runtime_profile_id"]),
        "status": classification.status,
        "entry_local_order_id": str(entry_order.get("local_order_id") or "") or None,
        "entry_exchange_order_id": str(entry_order.get("exchange_order_id") or "")
        or None,
        "entry_fill_confirmed": _entry_fully_filled(attempt, entry_order),
        "entry_filled_qty": (
            _decimal(entry_order.get("filled_qty"))
            if _decimal(entry_order.get("filled_qty")) > 0
            else None
        ),
        "entry_avg_price": (
            _decimal(entry_order.get("average_exec_price"))
            if _decimal(entry_order.get("average_exec_price")) > 0
            else None
        ),
        "exit_protection_set_id": None,
        "first_blocker": classification.first_blocker,
        "blockers": list(classification.blockers),
        "warnings": [],
        "authority_boundary": AUTHORITY_BOUNDARY,
        "created_at_ms": int(attempt.get("created_at_ms") or now_ms),
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        row,
    )
    event = {
        "lifecycle_event_id": _stable_id(
            "ticket_lifecycle_event",
            str(row["lifecycle_run_id"]),
            str(classification.event_type),
            str(now_ms),
        ),
        "lifecycle_run_id": str(row["lifecycle_run_id"]),
        "ticket_id": str(row["ticket_id"]),
        "protected_submit_attempt_id": str(row["protected_submit_attempt_id"]),
        "event_type": str(classification.event_type),
        "event_payload": {
            "submit_result_status": submit_result.get("status"),
            "lifecycle_status": classification.status,
            "blockers": list(classification.blockers),
            "next_action": classification.next_action,
        },
        "created_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_lifecycle_events",
        "lifecycle_event_id",
        event,
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


def _blocked_attempt_can_refresh(existing: dict[str, Any]) -> bool:
    if str(existing.get("status") or "") != "blocked":
        return False
    return not any(
        existing.get(key) in {True, 1}
        for key in (
            "exchange_write_called",
            "order_created",
            "order_lifecycle_called",
            "withdrawal_or_transfer_created",
            "live_profile_changed",
            "order_sizing_changed",
        )
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


def _tp1_price(*, action_time_fact: dict[str, Any]) -> Decimal:
    fact_values = _as_dict(action_time_fact.get("fact_values"))
    for key in (
        "take_profit_1",
        "tp1_price",
        "tp1_reference_price",
        "first_take_profit_price",
    ):
        if key in fact_values:
            value = _decimal(fact_values.get(key))
            if value > 0:
                return value
    return Decimal("0")


def _gateway_order_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"market", "limit", "stop_market"}:
        return normalized
    if normalized in {"stop-limit", "stop_limit"}:
        return "stop_limit"
    return "market"


def _order_by_role(orders: list[dict[str, Any]], role: str) -> dict[str, Any]:
    expected = role.upper()
    for order in orders:
        if str(order.get("order_role") or "").upper() == expected:
            return dict(order)
    return {}


def _entry_fully_filled(attempt: dict[str, Any], entry_order: dict[str, Any]) -> bool:
    if not entry_order:
        return False
    filled_qty = _decimal(entry_order.get("filled_qty"))
    request_order = _order_by_role(
        [
            dict(order)
            for order in _as_dict(attempt.get("submit_request")).get("orders", [])
            if isinstance(order, dict)
        ],
        "ENTRY",
    )
    requested_qty = _decimal(entry_order.get("amount") or request_order.get("amount"))
    avg_price = _decimal(entry_order.get("average_exec_price"))
    status = str(entry_order.get("status") or "").strip().lower()
    return (
        status == "filled"
        and filled_qty > 0
        and requested_qty > 0
        and filled_qty >= requested_qty
        and avg_price > 0
    )


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
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


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
        "submit_mode_decision_id": attempt.get("submit_mode_decision_id"),
        "strategy_group_id": attempt.get("strategy_group_id"),
        "runtime_profile_id": attempt.get("runtime_profile_id"),
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
        "authority_source_ref": attempt.get("authority_source_ref"),
        "observed_at_ms": now_ms,
    }
    if extra:
        payload.update(extra)
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
