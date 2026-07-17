#!/usr/bin/env python3
"""Materialize PG ticket-bound Runtime Safety State.

This is the non-executing L7 readiness bridge:

Action-Time Ticket + FinalGate pass + Operation Layer handoff
-> brc_runtime_safety_state_snapshots

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
from src.application.action_time.finalgate_preflight import (  # noqa: E402
    account_capacity_current_blockers,
)
from src.application.action_time.lifecycle_mutation_capability import (  # noqa: E402
    lifecycle_mutation_capability_decision,
)
from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
)


AUTHORITY_BOUNDARY = (
    "ticket_bound_runtime_safety_state; "
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
FACT_REF_KEYS = (
    "public_fact_snapshot_id",
    "action_time_fact_snapshot_id",
    "account_mode_snapshot_id",
)


def materialize_ticket_bound_runtime_safety_state(
    conn: sa.engine.Connection,
    *,
    ticket_id: str = "",
    operation_layer_handoff_id: str = "",
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    ticket_id = str(ticket_id or "").strip()
    operation_layer_handoff_id = str(operation_layer_handoff_id or "").strip()
    try:
        control_state = PgBackedRuntimeControlStateRepository(
            conn,
            now_ms=now_ms,
        ).read_action_time_control_state(
            ticket_id=ticket_id,
            operation_layer_handoff_id=operation_layer_handoff_id,
        )
    except RuntimeControlStateRepositoryError as exc:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=[f"runtime_control_state_invalid:{exc}"],
            snapshot={},
            next_action="repair_pg_runtime_control_state",
        )

    selection = _select_handoff(
        control_state,
        ticket_id=ticket_id,
        operation_layer_handoff_id=operation_layer_handoff_id,
        now_ms=now_ms,
    )
    if selection["blockers"]:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=selection["blockers"],
            snapshot={},
            next_action="repair_ticket_bound_operation_layer_handoff_selection",
        )
    handoff = selection["handoff"]
    if not handoff:
        return _result(
            "no_operation_layer_handoff",
            now_ms=now_ms,
            blockers=[],
            snapshot={},
            next_action="continue_watcher_observation",
        )

    ticket = _row_by_id(
        control_state,
        "action_time_tickets",
        "ticket_id",
        handoff.get("ticket_id"),
    )
    snapshot = _snapshot_row(
        conn,
        control_state,
        ticket=ticket,
        handoff=handoff,
        now_ms=now_ms,
    )
    capability = lifecycle_mutation_capability_decision(conn)
    if capability["blockers"]:
        snapshot["blockers"] = _dedupe(
            list(snapshot.get("blockers") or []) + list(capability["blockers"])
        )
        snapshot["submit_allowed"] = False
        snapshot["safety_state"] = "blocked_safety"
    snapshot["lifecycle_mutation_capability_ready"] = capability["enabled"]
    snapshot["lifecycle_mutation_capability_ref"] = (
        capability.get("capability", {}).get("certification_ref")
    )
    _upsert_row(
        conn,
        "brc_runtime_safety_state_snapshots",
        "runtime_safety_snapshot_id",
        snapshot,
    )
    _update_lane_runtime_safety_snapshot(conn, snapshot)
    return _result(
        "runtime_safety_state_ready"
        if snapshot["submit_allowed"] is True
        else "runtime_safety_state_blocked",
        now_ms=now_ms,
        blockers=list(snapshot["blockers"]),
        snapshot=snapshot,
        next_action=(
            "call_official_operation_layer_submit_after_action_time_recheck"
            if snapshot["submit_allowed"] is True
            else "repair_ticket_bound_runtime_safety_state"
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--ticket-id", default="")
    parser.add_argument("--operation-layer-handoff-id", default="")
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite or other SQLAlchemy URLs only for local unit tests.",
    )
    args = parser.parse_args(argv)
    if args.require_database_url and not args.database_url:
        print("ERROR: PG_DATABASE_URL is required for Runtime Safety State", file=sys.stderr)
        return 2
    if not args.database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if (
        not args.allow_non_postgres_for_test
        and not args.database_url.startswith(("postgresql://", "postgresql+psycopg://"))
    ):
        print("ERROR: Runtime Safety State materializer requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(args.database_url)
    try:
        with engine.begin() as conn:
            report = materialize_ticket_bound_runtime_safety_state(
                conn,
                ticket_id=args.ticket_id,
                operation_layer_handoff_id=args.operation_layer_handoff_id,
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


def _select_handoff(
    control_state: dict[str, Any],
    *,
    ticket_id: str,
    operation_layer_handoff_id: str,
    now_ms: int,
) -> dict[str, Any]:
    rows = [
        row
        for row in _rows(control_state.get("operation_layer_handoffs"))
        if row.get("status") == "handoff_ready"
    ]
    if ticket_id:
        rows = [row for row in rows if row.get("ticket_id") == ticket_id]
    if operation_layer_handoff_id:
        rows = [
            row
            for row in rows
            if row.get("operation_layer_handoff_id") == operation_layer_handoff_id
        ]
    if not ticket_id and not operation_layer_handoff_id:
        current_ticket_ids = {
            str(row.get("ticket_id") or "")
            for row in _rows(control_state.get("action_time_tickets"))
            if row.get("status") == "finalgate_ready"
            and int(row.get("expires_at_ms") or 0) > now_ms
        }
        rows = [
            row
            for row in rows
            if str(row.get("ticket_id") or "") in current_ticket_ids
        ]
    if len(rows) > 1:
        return {
            "handoff": {},
            "blockers": ["multiple_ready_operation_layer_handoffs"],
        }
    if not rows:
        return {"handoff": {}, "blockers": []}
    return {"handoff": rows[0], "blockers": []}


def _snapshot_row(
    conn: sa.Connection,
    control_state: dict[str, Any],
    *,
    ticket: dict[str, Any],
    handoff: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    blockers: list[str] = []
    if not ticket:
        blockers.append("action_time_ticket_missing")
    if ticket:
        blockers.extend(
            current_scope_blockers(
                control_state,
                strategy_group_id=ticket.get("strategy_group_id"),
                symbol=ticket.get("symbol"),
                side=ticket.get("side"),
            )
        )

    lane = _row_by_id(
        control_state,
        "action_time_lane_inputs",
        "action_time_lane_input_id",
        ticket.get("action_time_lane_input_id"),
    )
    runtime_scope = _row_by_id(
        control_state,
        "runtime_scope_bindings",
        "runtime_scope_binding_id",
        ticket.get("runtime_scope_binding_id"),
    )
    protection = _row_by_id(
        control_state,
        "protection_references",
        "protection_ref_id",
        ticket.get("protection_ref_id"),
    )
    budget = _row_by_id(
        control_state,
        "budget_reservations",
        "budget_reservation_id",
        ticket.get("budget_reservation_id"),
    )
    signal = _row_by_id(
        control_state,
        "live_signal_events",
        "signal_event_id",
        ticket.get("signal_event_id"),
    )
    account_fact_surface, account_fact_snapshot_id = _ticket_account_fact_pair(
        ticket,
        blockers=blockers,
    )
    facts = {
        key: _row_by_id(
            control_state,
            "runtime_fact_snapshots",
            "fact_snapshot_id",
            ticket.get(key),
        )
        for key in FACT_REF_KEYS
    }
    facts["account_capacity_fact_snapshot_id"] = _row_by_id(
        control_state,
        "runtime_fact_snapshots",
        "fact_snapshot_id",
        account_fact_snapshot_id,
    )

    blockers.extend(_ticket_blockers(control_state, ticket=ticket, now_ms=now_ms))
    blockers.extend(_handoff_blockers(ticket=ticket, handoff=handoff))
    blockers.extend(_finalgate_pass_blockers(control_state, ticket=ticket, handoff=handoff))
    blockers.extend(_scope_blockers(ticket=ticket, row=lane, label="lane"))
    blockers.extend(_scope_blockers(ticket=ticket, row=runtime_scope, label="runtime_scope"))
    blockers.extend(_scope_blockers(ticket=ticket, row=protection, label="protection"))
    blockers.extend(_scope_blockers(ticket=ticket, row=budget, label="budget"))
    blockers.extend(_scope_blockers(ticket=ticket, row=signal, label="signal"))
    blockers.extend(_lane_blockers(ticket=ticket, lane=lane))
    blockers.extend(_signal_blockers(ticket=ticket, signal=signal, now_ms=now_ms))
    for key, fact in facts.items():
        blockers.extend(_scope_blockers(ticket=ticket, row=fact, label=key))

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
    if budget and budget.get("status") != "consumed":
        blockers.append(f"budget_reservation_status_not_consumed:{budget.get('status') or 'missing'}")
    if budget:
        blockers.extend(budget_stop_risk_blockers(budget))
    capacity_blockers, active_capacity_policy = account_capacity_current_blockers(
        conn,
        budget=budget,
        now_ms=now_ms,
    )
    blockers.extend(capacity_blockers)
    if protection and int(protection.get("expires_at_ms") or 0) <= now_ms:
        blockers.append("protection_ref_expired")

    fact_blockers, facts_fresh, active_position_conflict = _fact_blockers(
        facts=facts,
        now_ms=now_ms,
    )
    if active_capacity_policy and not capacity_blockers and account_fact_surface != "account_capacity_base":
        fact_blockers.append("account_capacity_fact_surface_required")
        facts_fresh = False
        active_position_conflict = True
    blockers.extend(fact_blockers)
    trusted_fact_refs = _trusted_fact_refs(
        ticket=ticket,
        handoff=handoff,
        signal=signal,
        protection=protection,
        budget=budget,
        facts=facts,
        account_fact_surface=account_fact_surface,
    )
    trusted_fact_refs_complete = all(
        bool(trusted_fact_refs.get(key))
        for key in (
            "ticket_id",
            "ticket_hash",
            "finalgate_pass_id",
            "operation_layer_handoff_id",
            "operation_submit_command_id",
            "signal_event_id",
            "budget_reservation_id",
            "protection_ref_id",
            *FACT_REF_KEYS,
            "account_capacity_fact_surface",
            "account_capacity_fact_snapshot_id",
        )
    )
    if not trusted_fact_refs_complete:
        blockers.append("trusted_fact_refs_incomplete")

    finalgate_ready = (
        bool(ticket)
        and ticket.get("status") == "finalgate_ready"
        and bool(trusted_fact_refs.get("finalgate_pass_id"))
    )
    operation_layer_ready = (
        handoff.get("status") == "handoff_ready"
        and bool(handoff.get("operation_submit_command_id"))
    )
    protection_ready = bool(protection) and "protection_ref_expired" not in blockers
    submit_allowed = (
        finalgate_ready
        and operation_layer_ready
        and protection_ready
        and active_position_conflict is False
        and facts_fresh
        and trusted_fact_refs_complete
        and not blockers
    )
    valid_until_candidates = [
        int(ticket.get("expires_at_ms") or 0),
        int(protection.get("expires_at_ms") or 0),
        *[
            int(fact.get("valid_until_ms") or 0)
            for fact in facts.values()
            if fact
        ],
    ]
    valid_until_ms = min([value for value in valid_until_candidates if value > 0] or [now_ms])
    blockers = _dedupe(blockers)
    return {
        "runtime_safety_snapshot_id": _stable_id(
            "runtime_safety",
            str(handoff.get("operation_layer_handoff_id") or ""),
            str(ticket.get("ticket_id") or ""),
        ),
        "action_time_lane_input_id": ticket.get("action_time_lane_input_id"),
        "strategy_group_id": str(ticket.get("strategy_group_id") or handoff.get("strategy_group_id") or ""),
        "symbol": ticket.get("symbol") or handoff.get("symbol"),
        "side": ticket.get("side") or handoff.get("side"),
        "runtime_profile_id": ticket.get("runtime_profile_id") or handoff.get("runtime_profile_id"),
        "safety_state": "live_submit_ready" if submit_allowed else "blocked_safety",
        "submit_allowed": submit_allowed,
        "finalgate_ready": finalgate_ready,
        "operation_layer_ready": operation_layer_ready,
        "protection_ready": protection_ready,
        "active_position_conflict": active_position_conflict,
        "facts_fresh": facts_fresh,
        "trusted_fact_refs_complete": trusted_fact_refs_complete,
        "trusted_fact_refs_schema_version": "runtime_safety_trusted_refs.v2",
        "account_capacity_fact_surface": account_fact_surface,
        "account_capacity_fact_snapshot_id": account_fact_snapshot_id,
        "blockers": blockers,
        "trusted_fact_refs": trusted_fact_refs,
        "observed_at_ms": now_ms,
        "valid_until_ms": valid_until_ms,
        "created_at_ms": now_ms,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "signal_grade": ticket.get("signal_grade") or "invalid_signal",
        "required_execution_mode": ticket.get("required_execution_mode")
        or "observe_only",
        "execution_eligible": ticket.get("execution_eligible") is True,
        "authority_source_ref": ticket.get("authority_source_ref")
        or "runtime-safety:missing-authority-source",
    }


def _ticket_blockers(
    control_state: dict[str, Any],
    *,
    ticket: dict[str, Any],
    now_ms: int,
) -> list[str]:
    if not ticket:
        return []
    blockers: list[str] = []
    if ticket.get("status") != "finalgate_ready":
        blockers.append(f"ticket_status_not_finalgate_ready:{ticket.get('status') or 'missing'}")
    if int(ticket.get("expires_at_ms") or 0) <= now_ms:
        blockers.append("ticket_expired")
    if not ticket.get("ticket_hash"):
        blockers.append("ticket_hash_missing")
    elif compute_action_time_ticket_hash(ticket) != ticket.get("ticket_hash"):
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
    if not str(ticket.get("authority_source_ref") or "").strip():
        blockers.append("execution_eligibility_authority_source_missing")
    expected_pass_id = _latest_finalgate_pass_id(
        control_state,
        str(ticket.get("ticket_id") or ""),
    )
    if not expected_pass_id:
        blockers.append("finalgate_pass_id_missing")
    return blockers


def _handoff_blockers(*, ticket: dict[str, Any], handoff: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if handoff.get("ticket_id") != ticket.get("ticket_id"):
        blockers.append("operation_layer_handoff_ticket_mismatch")
    if handoff.get("status") != "handoff_ready":
        blockers.append(f"operation_layer_handoff_status_not_ready:{handoff.get('status') or 'missing'}")
    command_plan = _as_dict(handoff.get("command_plan"))
    for key in ("ticket_id", "finalgate_pass_id", "operation_submit_command_id"):
        if not command_plan.get(key):
            blockers.append(f"operation_layer_handoff_command_missing:{key}")
    if str(command_plan.get("ticket_id") or "") != str(ticket.get("ticket_id") or ""):
        blockers.append("operation_layer_handoff_command_ticket_mismatch")
    if str(command_plan.get("operation_submit_command_id") or "") != str(
        handoff.get("operation_submit_command_id") or ""
    ):
        blockers.append("operation_layer_handoff_command_submit_id_mismatch")
    if command_plan.get("kind") != "ticket_bound_operation_layer_handoff":
        blockers.append("operation_layer_handoff_command_kind_invalid")
    if command_plan.get("requires_ticket_bound_protected_submit") is not True:
        blockers.append("ticket_bound_protected_submit_requirement_missing")
    for key in ("places_order", "exchange_write_called", "order_lifecycle_called"):
        if command_plan.get(key) is not False:
            blockers.append(f"operation_layer_handoff_command_effect:{key}")
    if handoff.get("operation_layer_called") is not False:
        blockers.append("operation_layer_handoff_effect:operation_layer_called")
    if handoff.get("exchange_write_called") is not False:
        blockers.append("operation_layer_handoff_effect:exchange_write_called")
    if handoff.get("order_created") is not False:
        blockers.append("operation_layer_handoff_effect:order_created")
    if handoff.get("order_lifecycle_called") is not False:
        blockers.append("operation_layer_handoff_effect:order_lifecycle_called")
    return blockers


def _lane_blockers(*, ticket: dict[str, Any], lane: dict[str, Any]) -> list[str]:
    if not lane:
        return []
    blockers: list[str] = []
    if lane.get("lane_scope") != "real_submit_candidate":
        blockers.append(f"lane_scope_not_real_submit_candidate:{lane.get('lane_scope') or 'missing'}")
    if lane.get("status") not in {"ticket_pending", "ticket_created"}:
        blockers.append(f"lane_status_not_runtime_safety_eligible:{lane.get('status') or 'missing'}")
    if lane.get("execution_eligible") is not True:
        blockers.append("lane_execution_eligibility_missing_or_false")
    for field in (
        "signal_grade",
        "required_execution_mode",
        "execution_eligible",
        "authority_source_ref",
    ):
        if lane.get(field) != ticket.get(field):
            blockers.append(f"execution_eligibility_lane_ticket_mismatch:{field}")
    return blockers


def _signal_blockers(
    *,
    ticket: dict[str, Any],
    signal: dict[str, Any],
    now_ms: int,
) -> list[str]:
    if not ticket or not signal:
        return ["signal_event_missing"]
    blockers: list[str] = []
    if signal.get("status") != "facts_validated":
        blockers.append(f"signal_event_status_not_validated:{signal.get('status') or 'missing'}")
    if signal.get("freshness_state") != "fresh":
        blockers.append(f"signal_event_not_fresh:{signal.get('freshness_state') or 'missing'}")
    if signal.get("source_kind") != "live_market":
        blockers.append(f"signal_event_not_live_market:{signal.get('source_kind') or 'missing'}")
    if int(signal.get("expires_at_ms") or 0) <= now_ms:
        blockers.append("signal_event_expired")
    if str(signal.get("event_spec_id") or "") != str(ticket.get("event_spec_id") or ""):
        blockers.append("signal_event_spec_mismatch")
    if int(signal.get("event_time_ms") or 0) != int(ticket.get("event_time_ms") or 0):
        blockers.append("signal_event_time_mismatch:ticket")
    if int(signal.get("trigger_candle_close_time_ms") or 0) != int(
        ticket.get("trigger_candle_close_time_ms") or 0
    ):
        blockers.append("signal_trigger_candle_close_time_mismatch:ticket")
    if int(signal.get("event_time_ms") or 0) != int(
        signal.get("trigger_candle_close_time_ms") or 0
    ):
        blockers.append("signal_event_time_mismatch:trigger_candle_close_time_ms")
    if int(signal.get("created_at_ms") or 0) == int(signal.get("event_time_ms") or 0):
        blockers.append("signal_generated_at_used_as_event_time")
    for field in (
        "signal_grade",
        "required_execution_mode",
        "execution_eligible",
        "authority_source_ref",
    ):
        if signal.get(field) != ticket.get(field):
            blockers.append(f"execution_eligibility_signal_ticket_mismatch:{field}")
    if signal.get("execution_eligible") is not True:
        blockers.append("signal_execution_eligibility_missing_or_false")
    return blockers


def _finalgate_pass_blockers(
    control_state: dict[str, Any],
    *,
    ticket: dict[str, Any],
    handoff: dict[str, Any],
) -> list[str]:
    if not ticket:
        return []
    expected_pass_id = _latest_finalgate_pass_id(
        control_state,
        str(ticket.get("ticket_id") or ""),
    )
    if not expected_pass_id:
        return []
    command_plan = _as_dict(handoff.get("command_plan"))
    handoff_pass_id = str(handoff.get("finalgate_pass_id") or "")
    command_pass_id = str(command_plan.get("finalgate_pass_id") or "")
    blockers: list[str] = []
    if handoff_pass_id != expected_pass_id:
        blockers.append(
            "operation_layer_handoff_finalgate_pass_mismatch:"
            f"expected={expected_pass_id}:actual={handoff_pass_id or 'missing'}"
        )
    if command_pass_id != expected_pass_id:
        blockers.append(
            "operation_layer_handoff_command_finalgate_pass_mismatch:"
            f"expected={expected_pass_id}:actual={command_pass_id or 'missing'}"
        )
    if handoff_pass_id and command_pass_id and handoff_pass_id != command_pass_id:
        blockers.append("operation_layer_handoff_finalgate_pass_command_mismatch")
    return blockers


def _fact_blockers(
    *,
    facts: dict[str, dict[str, Any]],
    now_ms: int,
) -> tuple[list[str], bool, bool]:
    blockers: list[str] = []
    facts_fresh = True
    active_position_conflict = False
    for key, fact in facts.items():
        if not fact:
            blockers.append(f"{key}_missing")
            facts_fresh = False
            continue
        if fact.get("computed") is not True:
            blockers.append(f"{key}_not_computed")
        if fact.get("satisfied") is not True:
            blockers.append(f"{key}_not_satisfied")
        if fact.get("freshness_state") != "fresh":
            blockers.append(f"{key}_not_fresh")
            facts_fresh = False
        if int(fact.get("valid_until_ms") or 0) <= now_ms:
            blockers.append(f"{key}_expired")
            facts_fresh = False
    account_values = _as_dict(
        facts.get("account_capacity_fact_snapshot_id", {}).get("fact_values")
    )
    if account_values.get("schema_version") == "account_capacity_base.v1":
        if account_values.get("snapshot_complete") is not True or account_values.get("can_trade") is not True:
            blockers.append("account_capacity_base_fact_not_safe")
            active_position_conflict = True
    else:
        if account_values.get("account_safe") is not True:
            blockers.append("account_safe_fact_not_true")
        if account_values.get("open_orders_clear") is not True:
            blockers.append("open_orders_not_clear")
        if account_values.get("active_position_or_open_order_clear") is not True:
            active_position_conflict = True
            blockers.append("active_position_or_open_order_conflict")
    return blockers, facts_fresh and not blockers, active_position_conflict


_CAPACITY_REPLACED_RUNTIME_FACT_BLOCKERS = {
    "account_safe_fact_snapshot_id_not_satisfied",
    "account_safe_fact_snapshot_id_not_fresh",
    "account_safe_fact_not_true",
    "open_orders_not_clear",
    "active_position_or_open_order_conflict",
}


def _relax_legacy_account_position_fact_gate(
    *,
    facts: dict[str, dict[str, Any]],
    blockers: list[str],
    now_ms: int,
) -> tuple[list[str], bool, bool]:
    """Use the active account-budget claim, never a flat-account assumption."""

    account_safe = facts.get("account_safe_fact_snapshot_id", {})
    values = _as_dict(account_safe.get("fact_values"))
    if values.get("account_capacity_base_safe") is not True:
        return [*blockers, "account_capacity_base_fact_not_safe"], False, True
    remaining = [
        blocker
        for blocker in blockers
        if blocker not in _CAPACITY_REPLACED_RUNTIME_FACT_BLOCKERS
    ]
    facts_fresh = all(
        bool(fact)
        and fact.get("computed") is True
        and int(fact.get("valid_until_ms") or 0) > now_ms
        and (
            key == "account_safe_fact_snapshot_id"
            or (
                fact.get("satisfied") is True
                and fact.get("freshness_state") == "fresh"
            )
        )
        for key, fact in facts.items()
    )
    return remaining, facts_fresh and not remaining, False


def _scope_blockers(
    *,
    ticket: dict[str, Any],
    row: dict[str, Any],
    label: str,
) -> list[str]:
    if not row:
        return [f"{label}_missing"]
    blockers: list[str] = []
    for key in ("strategy_group_id", "symbol", "side", "runtime_profile_id"):
        if key in row and row.get(key) is not None and str(row.get(key) or "") != str(ticket.get(key) or ""):
            blockers.append(f"{label}_mismatch:{key}")
    return blockers


def _trusted_fact_refs(
    *,
    ticket: dict[str, Any],
    handoff: dict[str, Any],
    signal: dict[str, Any],
    protection: dict[str, Any],
    budget: dict[str, Any],
    facts: dict[str, dict[str, Any]],
    account_fact_surface: str,
) -> dict[str, Any]:
    finalgate_pass_id = _as_dict(handoff.get("command_plan")).get("finalgate_pass_id")
    return {
        "ticket_id": ticket.get("ticket_id"),
        "ticket_hash": ticket.get("ticket_hash"),
        "ticket_hash_schema_version": ticket.get("ticket_hash_schema_version"),
        "finalgate_pass_id": finalgate_pass_id or handoff.get("finalgate_pass_id"),
        "operation_layer_handoff_id": handoff.get("operation_layer_handoff_id"),
        "operation_submit_command_id": handoff.get("operation_submit_command_id"),
        "signal_event_id": signal.get("signal_event_id"),
        "budget_reservation_id": budget.get("budget_reservation_id"),
        "protection_ref_id": protection.get("protection_ref_id"),
        "account_capacity_fact_surface": account_fact_surface,
        "account_capacity_fact_snapshot_id": facts.get(
            "account_capacity_fact_snapshot_id", {}
        ).get("fact_snapshot_id"),
        **{
            key: facts.get(key, {}).get("fact_snapshot_id")
            for key in FACT_REF_KEYS
        },
    }


def _ticket_account_fact_pair(
    ticket: dict[str, Any],
    *,
    blockers: list[str],
) -> tuple[str, str]:
    legacy_fact_id = str(ticket.get("account_safe_fact_snapshot_id") or "").strip()
    capacity_fact_id = str(
        ticket.get("account_capacity_base_fact_snapshot_id") or ""
    ).strip()
    if bool(legacy_fact_id) == bool(capacity_fact_id):
        blockers.append("action_time_ticket_account_fact_pair_invalid")
        return "account_safe", ""
    return (
        ("account_capacity_base", capacity_fact_id)
        if capacity_fact_id
        else ("account_safe", legacy_fact_id)
    )


def _latest_finalgate_pass_id(control_state: dict[str, Any], ticket_id: str) -> str:
    events = [
        row
        for row in _rows(control_state.get("action_time_ticket_events"))
        if row.get("ticket_id") == ticket_id and row.get("to_status") == "finalgate_ready"
    ]
    if not events:
        return ""
    event = sorted(events, key=lambda row: int(row.get("occurred_at_ms") or 0))[-1]
    return str(_as_dict(event.get("event_payload")).get("finalgate_pass_id") or "")


def _row_by_id(
    control_state: dict[str, Any],
    table_key: str,
    id_key: str,
    row_id: Any,
) -> dict[str, Any]:
    row_id = str(row_id or "").strip()
    if not row_id:
        return {}
    return next(
        (
            row
            for row in _rows(control_state.get(table_key))
            if row.get(id_key) == row_id
        ),
        {},
    )


def _upsert_row(
    conn: sa.engine.Connection,
    table_name: str,
    pk_name: str,
    row: dict[str, Any],
) -> None:
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=conn)
    existing = conn.execute(
        sa.select(table.c[pk_name]).where(table.c[pk_name] == row[pk_name]).limit(1)
    ).scalar_one_or_none()
    values = {
        **row,
        "blockers": row["blockers"],
        "trusted_fact_refs": row["trusted_fact_refs"],
    }
    values = {
        column.name: values[column.name]
        for column in table.columns
        if column.name in values
    }
    if existing is None:
        conn.execute(table.insert().values(**values))
    else:
        conn.execute(table.update().where(table.c[pk_name] == row[pk_name]).values(**values))


def _update_lane_runtime_safety_snapshot(
    conn: sa.engine.Connection,
    snapshot: dict[str, Any],
) -> None:
    lane_id = str(snapshot.get("action_time_lane_input_id") or "").strip()
    snapshot_id = str(snapshot.get("runtime_safety_snapshot_id") or "").strip()
    if not lane_id or not snapshot_id:
        return
    metadata = sa.MetaData()
    table = sa.Table("brc_action_time_lane_inputs", metadata, autoload_with=conn)
    conn.execute(
        table.update()
        .where(table.c.action_time_lane_input_id == lane_id)
        .values(runtime_safety_snapshot_id=snapshot_id)
    )


def _result(
    status: str,
    *,
    now_ms: int,
    blockers: list[str],
    snapshot: dict[str, Any],
    next_action: str,
) -> dict[str, Any]:
    trusted_fact_refs = _as_dict(snapshot.get("trusted_fact_refs"))
    return {
        "schema": "brc.ticket_bound_runtime_safety_state.v1",
        "status": status,
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "runtime_safety_snapshot_id": snapshot.get("runtime_safety_snapshot_id"),
        "action_time_lane_input_id": snapshot.get("action_time_lane_input_id"),
        "ticket_id": trusted_fact_refs.get("ticket_id"),
        "finalgate_pass_id": trusted_fact_refs.get("finalgate_pass_id"),
        "operation_layer_handoff_id": trusted_fact_refs.get("operation_layer_handoff_id"),
        "operation_submit_command_id": trusted_fact_refs.get("operation_submit_command_id"),
        "strategy_group_id": snapshot.get("strategy_group_id"),
        "symbol": snapshot.get("symbol"),
        "side": snapshot.get("side"),
        "submit_allowed": snapshot.get("submit_allowed", False),
        "safety_state": snapshot.get("safety_state"),
        "lifecycle_mutation_capability_ready": snapshot.get(
            "lifecycle_mutation_capability_ready",
            False,
        ),
        "lifecycle_mutation_capability_ref": snapshot.get(
            "lifecycle_mutation_capability_ref"
        ),
        "blockers": _dedupe(blockers),
        "next_action": next_action,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "forbidden_effects": FORBIDDEN_EFFECTS,
        "created_at_ms": now_ms,
    }


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


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
        text = str(value or "")
        if text and text not in result:
            result.append(text)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
