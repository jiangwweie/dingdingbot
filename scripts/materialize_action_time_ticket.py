#!/usr/bin/env python3
"""Materialize one PG action-time lane into a formal Action-Time Ticket.

This script is intentionally narrow:

PG action-time lane
-> PG Action-Time Ticket
-> PG ticket-created event
-> lane status ticket_created

It does not call FinalGate, Operation Layer, exchange write APIs, order
lifecycle, withdrawals, transfers, live profile mutation, or order sizing
mutation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from decimal import Decimal, InvalidOperation
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


OPEN_REAL_LANE_STATUSES = {
    "opened",
    "facts_refreshing",
    "ticket_pending",
    "ticket_created",
}
ACTIVE_TICKET_STATUSES = {"created", "preflight_pending", "finalgate_ready"}
AUTHORITY_BOUNDARY = (
    "action_time_ticket_identity_only; no_finalgate_no_operation_layer_no_exchange_write"
)
TICKET_IDENTITY_HASH_FIELDS = (
    "ticket_id",
    "action_time_lane_input_id",
    "promotion_candidate_id",
    "signal_event_id",
    "event_spec_id",
    "event_spec_version_id",
    "candidate_scope_id",
    "runtime_scope_binding_id",
    "strategy_group_id",
    "strategy_group_version_id",
    "symbol",
    "exchange_instrument_id",
    "side",
    "event_id",
    "event_time_ms",
    "trigger_candle_close_time_ms",
    "runtime_profile_id",
    "public_fact_snapshot_id",
    "action_time_fact_snapshot_id",
    "account_safe_fact_snapshot_id",
    "account_mode_snapshot_id",
    "budget_reservation_id",
    "protection_ref_id",
    "execution_policy_id",
    "execution_policy_version",
    "owner_policy_version",
    "sizing_policy_version",
    "protection_policy_version",
    "target_notional",
    "leverage",
    "expires_at_ms",
    "authority_boundary",
    "created_under_versions_hash",
)
DECIMAL_HASH_FIELDS = {"target_notional", "leverage"}
INTEGER_HASH_FIELDS = {
    "event_time_ms",
    "trigger_candle_close_time_ms",
    "expires_at_ms",
}
FORBIDDEN_EFFECTS = {
    "finalgate_called": False,
    "operation_layer_called": False,
    "exchange_write_called": False,
    "order_created": False,
    "order_lifecycle_called": False,
    "withdrawal_or_transfer_created": False,
    "live_profile_changed": False,
    "order_sizing_changed": False,
}


class TicketMaterializationBlocked(RuntimeError):
    def __init__(self, blockers: list[str]) -> None:
        super().__init__(", ".join(blockers))
        self.blockers = blockers


def materialize_action_time_ticket(
    conn: sa.engine.Connection,
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    try:
        control_state = PgBackedRuntimeControlStateRepository(conn).read_control_state()
    except RuntimeControlStateRepositoryError as exc:
        return _blocked([f"runtime_control_state_invalid:{exc}"], now_ms=now_ms)

    lanes = _open_real_submit_lanes(control_state)
    if not lanes:
        return _result(
            "no_action_time_lane_input",
            now_ms=now_ms,
            blockers=[],
            next_action="continue_watcher_observation",
        )
    if len(lanes) > 1:
        return _blocked(["multiple_open_real_submit_lanes"], now_ms=now_ms)

    lane = lanes[0]
    lane_id = str(lane.get("action_time_lane_input_id") or "")
    existing_ticket = _active_ticket_for_lane(control_state, lane_id)
    if existing_ticket:
        return _result(
            "action_time_ticket_already_exists",
            now_ms=now_ms,
            ticket=existing_ticket,
            lane=lane,
            blockers=[],
            next_action="run_official_action_time_finalgate",
        )

    try:
        bundle = _build_ticket_bundle(control_state, lane=lane, now_ms=now_ms)
    except TicketMaterializationBlocked as exc:
        return _blocked(exc.blockers, now_ms=now_ms, lane=lane)

    _insert_ticket_bundle(conn, bundle)
    return _result(
        "action_time_ticket_created",
        now_ms=now_ms,
        ticket=bundle["ticket"],
        lane=lane,
        blockers=[],
        next_action="run_official_action_time_finalgate",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite or other SQLAlchemy URLs only for local unit tests.",
    )
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.require_database_url and not args.database_url:
        print("ERROR: PG_DATABASE_URL is required for Action-Time Ticket materializer", file=sys.stderr)
        return 2
    if not args.database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if (
        not args.allow_non_postgres_for_test
        and not args.database_url.startswith(("postgresql://", "postgresql+psycopg://"))
    ):
        print("ERROR: Action-Time Ticket materializer requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(args.database_url)
    try:
        with engine.begin() as conn:
            report = materialize_action_time_ticket(conn, now_ms=args.now_ms)
    except sa.exc.SQLAlchemyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
    else:
        print(report["status"])
    return 0 if report["status"] != "blocked" else 1


def _open_real_submit_lanes(control_state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in _rows(control_state.get("action_time_lane_inputs"))
        if row.get("lane_scope") == "real_submit_candidate"
        and row.get("status") in OPEN_REAL_LANE_STATUSES
    ]


def _active_ticket_for_lane(
    control_state: dict[str, Any],
    lane_id: str,
) -> dict[str, Any] | None:
    tickets = [
        row
        for row in _rows(control_state.get("action_time_tickets"))
        if row.get("action_time_lane_input_id") == lane_id
        and row.get("status") in ACTIVE_TICKET_STATUSES
    ]
    if not tickets:
        return None
    return sorted(tickets, key=lambda row: int(row.get("created_at_ms") or 0))[-1]


def _build_ticket_bundle(
    control_state: dict[str, Any],
    *,
    lane: dict[str, Any],
    now_ms: int,
) -> dict[str, dict[str, Any]]:
    blockers: list[str] = []
    lane_id = _required_text(lane, "action_time_lane_input_id", blockers)
    if lane.get("status") == "ticket_created":
        blockers.append("lane_marked_ticket_created_without_active_ticket")
    if not _required_text(lane, "candidate_authorization_ref", blockers):
        blockers.append("candidate_authorization_ref_missing")

    promotion = _one_by_id(
        control_state,
        "promotion_candidates",
        "promotion_candidate_id",
        str(lane.get("promotion_candidate_id") or ""),
        blockers,
        "promotion_candidate_missing",
    )
    signal = _one_by_id(
        control_state,
        "live_signal_events",
        "signal_event_id",
        str(lane.get("signal_event_id") or ""),
        blockers,
        "signal_event_missing",
    )
    runtime_scope = _one_by_id(
        control_state,
        "runtime_scope_bindings",
        "runtime_scope_binding_id",
        str(lane.get("runtime_scope_binding_id") or ""),
        blockers,
        "runtime_scope_binding_missing",
    )
    candidate = _one_by_id(
        control_state,
        "candidate_scope",
        "candidate_scope_id",
        str(runtime_scope.get("candidate_scope_id") or ""),
        blockers,
        "candidate_scope_missing",
    )
    event_binding = _matching_event_binding(
        control_state,
        candidate_scope_id=str(candidate.get("candidate_scope_id") or ""),
        blockers=blockers,
    )
    event_spec = _one_by_id(
        control_state,
        "strategy_side_event_specs",
        "event_spec_id",
        str(event_binding.get("event_spec_id") or signal.get("event_spec_id") or ""),
        blockers,
        "event_spec_missing",
    )
    policy = _one_by_id(
        control_state,
        "owner_policy_current",
        "policy_current_id",
        str(runtime_scope.get("policy_current_id") or candidate.get("policy_current_id") or ""),
        blockers,
        "owner_policy_current_missing",
    )
    public_fact = _one_by_id(
        control_state,
        "runtime_fact_snapshots",
        "fact_snapshot_id",
        str(lane.get("public_fact_snapshot_id") or ""),
        blockers,
        "public_fact_snapshot_missing",
    )
    action_time_fact = _one_by_id(
        control_state,
        "runtime_fact_snapshots",
        "fact_snapshot_id",
        str(lane.get("action_time_fact_snapshot_id") or ""),
        blockers,
        "action_time_fact_snapshot_missing",
    )
    account_safe_fact = _latest_fact(
        control_state,
        fact_surface="account_safe",
        lane=lane,
        blockers=blockers,
        missing_blocker="account_safe_fact_snapshot_missing",
    )
    account_mode_fact = _latest_fact(
        control_state,
        fact_surface="account_mode",
        lane=lane,
        blockers=blockers,
        missing_blocker="account_mode_snapshot_missing",
    )
    budget = _active_budget_reservation(
        control_state,
        lane_id=lane_id,
        blockers=blockers,
    )
    protection = _active_protection_ref(
        control_state,
        lane=lane,
        event_spec_id=str(event_spec.get("event_spec_id") or ""),
        now_ms=now_ms,
        blockers=blockers,
    )
    execution_policy = _current_execution_policy(
        control_state,
        lane=lane,
        event_spec_id=str(event_spec.get("event_spec_id") or ""),
        blockers=blockers,
    )
    exchange_instrument_id = _exchange_instrument_id(
        control_state,
        symbol=str(lane.get("symbol") or ""),
        blockers=blockers,
    )

    _validate_lineage(
        blockers,
        lane=lane,
        promotion=promotion,
        signal=signal,
        runtime_scope=runtime_scope,
        candidate=candidate,
        event_binding=event_binding,
        event_spec=event_spec,
        policy=policy,
        public_fact=public_fact,
        action_time_fact=action_time_fact,
        account_safe_fact=account_safe_fact,
        account_mode_fact=account_mode_fact,
        budget=budget,
        protection=protection,
        execution_policy=execution_policy,
        now_ms=now_ms,
    )

    required_fact_blockers = _required_fact_blockers(
        control_state,
        event_spec_id=str(event_spec.get("event_spec_id") or ""),
        action_time_fact=action_time_fact,
    )
    blockers.extend(required_fact_blockers)
    if blockers:
        raise TicketMaterializationBlocked(_dedupe(blockers))

    owner_policy_version = _owner_policy_version(control_state, policy)
    if not owner_policy_version:
        raise TicketMaterializationBlocked(["owner_policy_version_missing"])

    event_spec_version_id = (
        f"{event_spec['event_spec_id']}:{event_spec['event_spec_version']}"
    )
    sizing_policy_version = str(owner_policy_version)
    protection_policy_version = str(protection["protection_policy_version"])
    execution_policy_version = str(execution_policy["execution_policy_version"])
    expires_at_ms = min(
        int(lane["expires_at_ms"]),
        int(signal["expires_at_ms"]),
        int(budget["expires_at_ms"]),
        int(protection["expires_at_ms"]),
    )
    ticket_id = _stable_id("ticket", lane_id, str(signal["signal_event_id"]))
    created_under_versions_hash = _hash_payload(
        {
            "strategy_group_version_id": event_spec["strategy_group_version_id"],
            "event_spec_version_id": event_spec_version_id,
            "execution_policy_version": execution_policy_version,
            "owner_policy_version": owner_policy_version,
            "sizing_policy_version": sizing_policy_version,
            "protection_policy_version": protection_policy_version,
        }
    )
    ticket = {
        "ticket_id": ticket_id,
        "action_time_lane_input_id": lane_id,
        "promotion_candidate_id": lane["promotion_candidate_id"],
        "signal_event_id": signal["signal_event_id"],
        "event_spec_id": event_spec["event_spec_id"],
        "event_spec_version_id": event_spec_version_id,
        "candidate_scope_id": candidate["candidate_scope_id"],
        "runtime_scope_binding_id": runtime_scope["runtime_scope_binding_id"],
        "strategy_group_id": lane["strategy_group_id"],
        "strategy_group_version_id": event_spec["strategy_group_version_id"],
        "symbol": lane["symbol"],
        "exchange_instrument_id": exchange_instrument_id,
        "side": lane["side"],
        "event_id": event_spec["event_id"],
        "event_time_ms": signal["event_time_ms"],
        "trigger_candle_close_time_ms": signal["trigger_candle_close_time_ms"],
        "runtime_profile_id": lane["runtime_profile_id"],
        "public_fact_snapshot_id": public_fact["fact_snapshot_id"],
        "action_time_fact_snapshot_id": action_time_fact["fact_snapshot_id"],
        "account_safe_fact_snapshot_id": account_safe_fact["fact_snapshot_id"],
        "account_mode_snapshot_id": account_mode_fact["fact_snapshot_id"],
        "budget_reservation_id": budget["budget_reservation_id"],
        "protection_ref_id": protection["protection_ref_id"],
        "execution_policy_id": execution_policy["execution_policy_id"],
        "execution_policy_version": execution_policy_version,
        "owner_policy_version": owner_policy_version,
        "sizing_policy_version": sizing_policy_version,
        "protection_policy_version": protection_policy_version,
        "target_notional": str(budget["target_notional"]),
        "leverage": str(budget["leverage"]),
        "expires_at_ms": expires_at_ms,
        "status": "created",
        "authority_boundary": AUTHORITY_BOUNDARY,
        "created_under_versions_hash": created_under_versions_hash,
        "created_at_ms": now_ms,
    }
    ticket["ticket_hash"] = compute_action_time_ticket_hash(ticket)
    ticket_event = {
        "ticket_event_id": _stable_id("ticket_event", ticket_id, "created"),
        "ticket_id": ticket_id,
        "action_time_lane_input_id": lane_id,
        "from_status": None,
        "to_status": "created",
        "transition_reason": "pg_action_time_lane_materialized_to_ticket",
        "trigger_ref": lane.get("candidate_authorization_ref"),
        "writer": "materialize_action_time_ticket",
        "event_payload": {
            "signal_event_id": signal["signal_event_id"],
            "promotion_candidate_id": lane["promotion_candidate_id"],
            "authority_boundary": AUTHORITY_BOUNDARY,
        },
        "occurred_at_ms": now_ms,
        "created_at_ms": now_ms,
    }
    return {"ticket": ticket, "ticket_event": ticket_event, "budget": budget}


def _validate_lineage(blockers: list[str], **items: Any) -> None:
    lane = items["lane"]
    now_ms = items["now_ms"]
    comparable = (
        "strategy_group_id",
        "symbol",
        "side",
        "runtime_profile_id",
    )
    for item_name in ("promotion", "signal", "runtime_scope", "budget"):
        item = items[item_name]
        for key in comparable:
            if key in item and str(item.get(key) or "") != str(lane.get(key) or ""):
                blockers.append(f"{item_name}_mismatch:{key}")
    for item_name in ("candidate", "event_binding", "event_spec", "policy", "protection", "execution_policy"):
        item = items[item_name]
        for key in ("strategy_group_id", "side"):
            if key in item and str(item.get(key) or "") != str(lane.get(key) or ""):
                blockers.append(f"{item_name}_mismatch:{key}")
    if str(items["candidate"].get("symbol") or "") != str(lane.get("symbol") or ""):
        blockers.append("candidate_scope_mismatch:symbol")
    if str(items["event_binding"].get("event_spec_id") or "") != str(
        items["signal"].get("event_spec_id") or ""
    ):
        blockers.append("signal_event_mismatch:event_spec_id")
    if str(items["event_spec"].get("event_spec_id") or "") != str(
        items["execution_policy"].get("event_spec_id") or ""
    ):
        blockers.append("execution_policy_mismatch:event_spec_id")
    if items["promotion"].get("status") != "arbitration_won":
        blockers.append(f"promotion_candidate_not_arbitration_won:{items['promotion'].get('status') or 'missing'}")
    if items["promotion"].get("promotion_scope") != "live_submit_candidate":
        blockers.append(
            "promotion_scope_not_live_submit_candidate:"
            f"{items['promotion'].get('promotion_scope') or 'missing'}"
        )
    if str(lane.get("promotion_candidate_id") or "") != str(
        items["promotion"].get("promotion_candidate_id") or ""
    ):
        blockers.append("lane_mismatch:promotion_candidate_id")
    if str(lane.get("signal_event_id") or "") != str(
        items["signal"].get("signal_event_id") or ""
    ):
        blockers.append("lane_mismatch:signal_event_id")
    if str(items["promotion"].get("signal_event_id") or "") != str(
        items["signal"].get("signal_event_id") or ""
    ):
        blockers.append("promotion_candidate_mismatch:signal_event_id")
    if items["signal"].get("status") != "facts_validated":
        blockers.append(f"signal_event_not_facts_validated:{items['signal'].get('status') or 'missing'}")
    if items["signal"].get("freshness_state") != "fresh":
        blockers.append(f"signal_event_not_fresh:{items['signal'].get('freshness_state') or 'missing'}")
    if items["signal"].get("source_kind") != "live_market":
        blockers.append(f"signal_event_not_live_market:{items['signal'].get('source_kind') or 'missing'}")
    if int(items["signal"].get("expires_at_ms") or 0) <= now_ms:
        blockers.append("signal_event_expired")
    event_time_ms = int(items["signal"].get("event_time_ms") or 0)
    trigger_candle_close_time_ms = int(
        items["signal"].get("trigger_candle_close_time_ms") or 0
    )
    if event_time_ms <= 0:
        blockers.append("signal_event_time_missing")
    if trigger_candle_close_time_ms <= 0:
        blockers.append("signal_trigger_candle_close_time_missing")
    if event_time_ms != trigger_candle_close_time_ms:
        blockers.append("signal_event_time_mismatch:trigger_candle_close_time_ms")
    if int(items["signal"].get("created_at_ms") or 0) == event_time_ms:
        blockers.append("signal_generated_at_used_as_event_time")
    if items["runtime_scope"].get("status") != "active":
        blockers.append("runtime_scope_binding_not_active")
    for flag in (
        "selected_strategygroup_scope",
        "symbol_side_scope_closed",
        "notional_leverage_scope_closed",
        "live_submit_allowed",
    ):
        if items["runtime_scope"].get(flag) is not True:
            blockers.append(f"runtime_scope_not_closed:{flag}")
    if items["policy"].get("enabled_state") != "enabled":
        blockers.append("owner_policy_not_enabled")
    for fact_name in (
        "public_fact",
        "action_time_fact",
        "account_safe_fact",
        "account_mode_fact",
    ):
        fact = items[fact_name]
        if fact.get("computed") is not True:
            blockers.append(f"{fact_name}_not_computed")
        if fact.get("freshness_state") != "fresh":
            blockers.append(f"{fact_name}_not_fresh")
        if fact.get("satisfied") is not True:
            blockers.append(f"{fact_name}_not_satisfied")
        if int(fact.get("valid_until_ms") or 0) <= now_ms:
            blockers.append(f"{fact_name}_expired")
    if items["budget"].get("status") != "active":
        blockers.append("budget_reservation_not_active")
    if int(items["budget"].get("expires_at_ms") or 0) <= now_ms:
        blockers.append("budget_reservation_expired")
    if _decimal(items["budget"].get("target_notional")) <= 0:
        blockers.append("budget_reservation_target_notional_invalid")
    if _decimal(items["budget"].get("leverage")) <= 0:
        blockers.append("budget_reservation_leverage_invalid")
    if int(items["protection"].get("expires_at_ms") or 0) <= now_ms:
        blockers.append("protection_ref_expired")
    if items["execution_policy"].get("status") != "current":
        blockers.append("execution_policy_not_current")
    if items["event_spec"].get("status") != "current":
        blockers.append("event_spec_not_current")
    if items["event_spec"].get("time_authority") != "trigger_candle_close_time_ms":
        blockers.append("unsupported_event_time_authority")


def _required_fact_blockers(
    control_state: dict[str, Any],
    *,
    event_spec_id: str,
    action_time_fact: dict[str, Any],
) -> list[str]:
    fact_values = _as_dict(action_time_fact.get("fact_values"))
    blockers: list[str] = []
    for row in _rows(control_state.get("strategy_event_required_facts")):
        if row.get("event_spec_id") != event_spec_id:
            continue
        if row.get("status") != "current" or row.get("required_for_ticket") is not True:
            continue
        fact_key = str(row.get("fact_key") or "")
        satisfied = _fact_condition_satisfied(row, fact_values)
        if row.get("disable_on_match") is True:
            if _disable_fact_unknown(fact_key, fact_values):
                blockers.append(f"disable_fact_missing:{fact_key}")
                continue
            if satisfied:
                blockers.append(f"disable_fact_active:{fact_key}")
            continue
        if not satisfied:
            blockers.append(f"required_fact_not_satisfied:{fact_key}")
    return blockers


def _disable_fact_unknown(fact_key: str, fact_values: dict[str, Any]) -> bool:
    if fact_key not in fact_values:
        return True
    observed = fact_values.get(fact_key)
    if observed is None:
        return True
    if isinstance(observed, str) and observed.strip().lower() in {
        "",
        "unknown",
        "missing",
        "null",
    }:
        return True
    return False


def _fact_condition_satisfied(row: dict[str, Any], fact_values: dict[str, Any]) -> bool:
    fact_key = str(row.get("fact_key") or "")
    operator = str(row.get("operator") or "")
    observed = fact_values.get(fact_key)
    expected = row.get("expected_value")
    if operator == "exists":
        return observed is not None
    if operator == "not_exists":
        return observed is None
    if operator == "eq":
        return _normalized_scalar(observed) == _normalized_scalar(expected)
    if operator == "neq":
        return _normalized_scalar(observed) != _normalized_scalar(expected)
    if operator in {"gt", "gte", "lt", "lte"}:
        observed_dec = _decimal(observed)
        expected_dec = _decimal(expected)
        if operator == "gt":
            return observed_dec > expected_dec
        if operator == "gte":
            return observed_dec >= expected_dec
        if operator == "lt":
            return observed_dec < expected_dec
        return observed_dec <= expected_dec
    if operator == "in":
        return isinstance(expected, list) and observed in expected
    if operator == "not_in":
        return isinstance(expected, list) and observed not in expected
    if operator == "expr_ref":
        return observed is True
    return False


def _normalized_scalar(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    if text.lower() == "null":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _insert_ticket_bundle(
    conn: sa.engine.Connection,
    bundle: dict[str, dict[str, Any]],
) -> None:
    ticket = bundle["ticket"]
    event = bundle["ticket_event"]
    conn.execute(
        text(
            """
            INSERT INTO brc_action_time_tickets (
              ticket_id, action_time_lane_input_id, promotion_candidate_id,
              signal_event_id, event_spec_id, event_spec_version_id,
              candidate_scope_id, runtime_scope_binding_id, strategy_group_id,
              strategy_group_version_id, symbol, exchange_instrument_id, side,
              event_id, event_time_ms, trigger_candle_close_time_ms,
              runtime_profile_id, public_fact_snapshot_id,
              action_time_fact_snapshot_id, account_safe_fact_snapshot_id,
              account_mode_snapshot_id, budget_reservation_id, protection_ref_id,
              execution_policy_id, execution_policy_version, owner_policy_version,
              sizing_policy_version, protection_policy_version, target_notional,
              leverage, expires_at_ms, status, authority_boundary, ticket_hash,
              created_under_versions_hash, created_at_ms
            ) VALUES (
              :ticket_id, :action_time_lane_input_id, :promotion_candidate_id,
              :signal_event_id, :event_spec_id, :event_spec_version_id,
              :candidate_scope_id, :runtime_scope_binding_id, :strategy_group_id,
              :strategy_group_version_id, :symbol, :exchange_instrument_id, :side,
              :event_id, :event_time_ms, :trigger_candle_close_time_ms,
              :runtime_profile_id, :public_fact_snapshot_id,
              :action_time_fact_snapshot_id, :account_safe_fact_snapshot_id,
              :account_mode_snapshot_id, :budget_reservation_id, :protection_ref_id,
              :execution_policy_id, :execution_policy_version, :owner_policy_version,
              :sizing_policy_version, :protection_policy_version, :target_notional,
              :leverage, :expires_at_ms, :status, :authority_boundary, :ticket_hash,
              :created_under_versions_hash, :created_at_ms
            )
            """
        ),
        ticket,
    )
    conn.execute(
        text(
            """
            INSERT INTO brc_action_time_ticket_events (
              ticket_event_id, ticket_id, action_time_lane_input_id, from_status,
              to_status, transition_reason, trigger_ref, writer, event_payload,
              occurred_at_ms, created_at_ms
            ) VALUES (
              :ticket_event_id, :ticket_id, :action_time_lane_input_id, :from_status,
              :to_status, :transition_reason, :trigger_ref, :writer, :event_payload,
              :occurred_at_ms, :created_at_ms
            )
            """
        ),
        {**event, "event_payload": json.dumps(event["event_payload"], sort_keys=True)},
    )
    conn.execute(
        text(
            """
            UPDATE brc_action_time_lane_inputs
            SET status = 'ticket_created'
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {"lane_id": ticket["action_time_lane_input_id"]},
    )
    conn.execute(
        text(
            """
            UPDATE brc_budget_reservations
            SET ticket_id = :ticket_id,
                status = 'consumed'
            WHERE budget_reservation_id = :budget_reservation_id
            """
        ),
        {
            "ticket_id": ticket["ticket_id"],
            "budget_reservation_id": ticket["budget_reservation_id"],
        },
    )


def _matching_event_binding(
    control_state: dict[str, Any],
    *,
    candidate_scope_id: str,
    blockers: list[str],
) -> dict[str, Any]:
    matches = [
        row
        for row in _rows(control_state.get("candidate_scope_event_bindings"))
        if row.get("candidate_scope_id") == candidate_scope_id
        and row.get("status") == "active"
    ]
    if not matches:
        blockers.append("candidate_scope_event_binding_missing")
        return {}
    if len(matches) > 1:
        blockers.append("multiple_candidate_scope_event_bindings")
    return matches[0]


def _latest_fact(
    control_state: dict[str, Any],
    *,
    fact_surface: str,
    lane: dict[str, Any],
    blockers: list[str],
    missing_blocker: str,
) -> dict[str, Any]:
    rows = [
        row
        for row in _rows(control_state.get("runtime_fact_snapshots"))
        if row.get("fact_surface") == fact_surface
        and _optional_scope_matches(row, lane)
    ]
    if not rows:
        blockers.append(missing_blocker)
        return {}
    return sorted(rows, key=lambda row: int(row.get("observed_at_ms") or 0))[-1]


def _active_budget_reservation(
    control_state: dict[str, Any],
    *,
    lane_id: str,
    blockers: list[str],
) -> dict[str, Any]:
    rows = [
        row
        for row in _rows(control_state.get("budget_reservations"))
        if row.get("action_time_lane_input_id") == lane_id
        and row.get("status") == "active"
    ]
    if not rows:
        blockers.append("budget_reservation_missing")
        return {}
    if len(rows) > 1:
        blockers.append("multiple_active_budget_reservations")
    return rows[0]


def _active_protection_ref(
    control_state: dict[str, Any],
    *,
    lane: dict[str, Any],
    event_spec_id: str,
    now_ms: int,
    blockers: list[str],
) -> dict[str, Any]:
    rows = [
        row
        for row in _rows(control_state.get("protection_references"))
        if row.get("event_spec_id") == event_spec_id
        and row.get("strategy_group_id") == lane.get("strategy_group_id")
        and row.get("symbol") == lane.get("symbol")
        and row.get("side") == lane.get("side")
        and int(row.get("expires_at_ms") or 0) > now_ms
    ]
    if not rows:
        blockers.append("protection_ref_missing")
        return {}
    return sorted(rows, key=lambda row: int(row.get("expires_at_ms") or 0))[-1]


def _current_execution_policy(
    control_state: dict[str, Any],
    *,
    lane: dict[str, Any],
    event_spec_id: str,
    blockers: list[str],
) -> dict[str, Any]:
    rows = [
        row
        for row in _rows(control_state.get("execution_policies"))
        if row.get("runtime_profile_id") == lane.get("runtime_profile_id")
        and row.get("strategy_group_id") == lane.get("strategy_group_id")
        and row.get("event_spec_id") == event_spec_id
        and row.get("side") == lane.get("side")
        and row.get("status") == "current"
    ]
    if not rows:
        blockers.append("execution_policy_missing")
        return {}
    return rows[0]


def _exchange_instrument_id(
    control_state: dict[str, Any],
    *,
    symbol: str,
    blockers: list[str],
) -> str:
    mapping = next(
        (
            row
            for row in _rows(control_state.get("symbol_instrument_mappings"))
            if row.get("symbol") == symbol and row.get("status") == "active"
        ),
        {},
    )
    instrument_id = str(mapping.get("exchange_instrument_id") or "")
    instrument = next(
        (
            row
            for row in _rows(control_state.get("exchange_instruments"))
            if row.get("exchange_instrument_id") == instrument_id
            and row.get("status") == "active"
        ),
        {},
    )
    if not instrument_id or not instrument:
        blockers.append("exchange_instrument_mapping_missing")
    return instrument_id


def _owner_policy_version(
    control_state: dict[str, Any],
    policy: dict[str, Any],
) -> str:
    policy_event_ids = [str(item) for item in _list(policy.get("policy_event_ids"))]
    for policy_event_id in policy_event_ids:
        row = next(
            (
                item
                for item in _rows(control_state.get("owner_policy_events"))
                if item.get("policy_event_id") == policy_event_id
            ),
            {},
        )
        version = str(row.get("policy_version") or "")
        if version:
            return version
    return ""


def _one_by_id(
    control_state: dict[str, Any],
    table_key: str,
    id_key: str,
    row_id: str,
    blockers: list[str],
    missing_blocker: str,
) -> dict[str, Any]:
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


def _required_text(row: dict[str, Any], key: str, blockers: list[str]) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        blockers.append(f"{key}_missing")
    return value


def _optional_scope_matches(row: dict[str, Any], lane: dict[str, Any]) -> bool:
    for key in ("strategy_group_id", "symbol", "side", "runtime_profile_id"):
        value = row.get(key)
        if value is not None and str(value or "") != str(lane.get(key) or ""):
            return False
    return True


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


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("-1")


def compute_action_time_ticket_hash(ticket: dict[str, Any]) -> str:
    return _hash_payload(
        {
            field: _canonical_ticket_hash_value(field, ticket.get(field))
            for field in TICKET_IDENTITY_HASH_FIELDS
        }
    )


def _canonical_ticket_hash_value(field: str, value: Any) -> Any:
    if field in DECIMAL_HASH_FIELDS:
        return _canonical_decimal_string(value)
    if field in INTEGER_HASH_FIELDS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    return value


def _canonical_decimal_string(value: Any) -> str:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    if decimal_value == 0:
        return "0"
    return format(decimal_value.normalize(), "f")


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}:{hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()}"


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _blocked(
    blockers: list[str],
    *,
    now_ms: int,
    lane: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _result(
        "blocked",
        now_ms=now_ms,
        blockers=_dedupe(blockers),
        lane=lane or {},
        next_action="repair_pg_action_time_ticket_inputs",
    )


def _result(
    status: str,
    *,
    now_ms: int,
    blockers: list[str],
    next_action: str,
    lane: dict[str, Any] | None = None,
    ticket: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lane = lane or {}
    ticket = ticket or {}
    return {
        "schema": "brc.action_time_ticket_materialization.v1",
        "status": status,
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "action_time_lane_input_id": lane.get("action_time_lane_input_id"),
        "ticket_id": ticket.get("ticket_id"),
        "strategy_group_id": lane.get("strategy_group_id") or ticket.get("strategy_group_id"),
        "symbol": lane.get("symbol") or ticket.get("symbol"),
        "side": lane.get("side") or ticket.get("side"),
        "blockers": blockers,
        "next_action": next_action,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "forbidden_effects": FORBIDDEN_EFFECTS,
        "created_at_ms": now_ms,
    }


if __name__ == "__main__":
    raise SystemExit(main())
