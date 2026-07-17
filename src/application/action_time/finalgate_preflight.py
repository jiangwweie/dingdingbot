#!/usr/bin/env python3
"""Run the PG ticket-bound action-time FinalGate preflight.

Input authority is exactly one ``ticket_id``. The script reads the complete
candidate identity and safety lineage from PG and updates only PG ticket
lifecycle state:

Action-Time Ticket
-> ticket event: created -> preflight_pending
-> ticket event: preflight_pending -> finalgate_ready/finalgate_rejected

It does not call Operation Layer, exchange write APIs, OrderLifecycle,
withdrawals, transfers, live profile mutation, or order sizing mutation.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import time
from decimal import Decimal, InvalidOperation
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
)
from src.application.action_time.capital_safety_guard import (  # noqa: E402
    current_scope_blockers,
)
from src.application.action_time.budget_stop_risk import (  # noqa: E402
    budget_stop_risk_blockers,
)
from src.application.action_time.action_time_ticket import (  # noqa: E402
    compute_action_time_ticket_hash,
)
from src.application.action_time.account_capacity_claim import (  # noqa: E402
    AccountCapacityClaimConflict,
    load_account_capacity_claim_by_invocation,
)
from src.application.action_time.instrument_risk_facts import (  # noqa: E402
    InstrumentRiskFactsError,
    load_instrument_risk_facts,
)
from src.domain.account_capacity_claim import (  # noqa: E402
    capacity_claim_hash,
    revalidate_capacity_totals,
)
from src.infrastructure.account_capacity_hot_path_repository import (  # noqa: E402
    load_live_exposure_rows,
)


PASSABLE_TICKET_STATUSES = {"created", "preflight_pending"}
ELIGIBLE_FINALGATE_TICKET_STATUSES = {
    "created",
    "preflight_pending",
    "finalgate_ready",
}
AUTHORITY_BOUNDARY = (
    "ticket_id_only_finalgate_preflight; no_operation_layer_no_exchange_write"
)
FORBIDDEN_EFFECTS = {
    "operation_layer_called": False,
    "exchange_write_called": False,
    "order_created": False,
    "order_lifecycle_called": False,
    "withdrawal_or_transfer_created": False,
    "live_profile_changed": False,
    "order_sizing_changed": False,
}


def materialize_action_time_finalgate_preflight(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    now_ms: int | None = None,
    control_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    ticket_id = str(ticket_id or "").strip()
    if not ticket_id:
        return _blocked(
            ["ticket_id_required"],
            now_ms=now_ms,
            ticket={},
            finalgate_pass_id=None,
        )
    if control_state is None:
        try:
            control_state = PgBackedRuntimeControlStateRepository(
                conn,
                now_ms=now_ms,
            ).read_action_time_control_state(ticket_id=ticket_id)
        except RuntimeControlStateRepositoryError as exc:
            return _blocked(
                [f"runtime_control_state_invalid:{exc}"],
                now_ms=now_ms,
                ticket={},
                finalgate_pass_id=None,
            )

    ticket = _ticket_by_id(control_state, ticket_id)
    if not ticket:
        return _blocked(
            ["action_time_ticket_missing"],
            now_ms=now_ms,
            ticket={"ticket_id": ticket_id},
            finalgate_pass_id=None,
        )
    if ticket.get("status") == "finalgate_ready":
        hash_blockers = _ticket_hash_blockers(ticket)
        if hash_blockers:
            return _blocked(
                hash_blockers,
                now_ms=now_ms,
                ticket=ticket,
                finalgate_pass_id=_latest_finalgate_pass_id(control_state, ticket_id),
            )
        return _result(
            "finalgate_already_ready",
            now_ms=now_ms,
            ticket=ticket,
            blockers=[],
            finalgate_pass_id=_latest_finalgate_pass_id(control_state, ticket_id),
            next_action="prepare_official_operation_layer_handoff",
        )
    if ticket.get("status") not in PASSABLE_TICKET_STATUSES:
        return _blocked(
            [f"ticket_status_not_finalgate_eligible:{ticket.get('status') or 'missing'}"],
            now_ms=now_ms,
            ticket=ticket,
            finalgate_pass_id=None,
        )

    blockers = _finalgate_blockers(
        conn,
        control_state,
        ticket=ticket,
        now_ms=now_ms,
    )
    if blockers:
        if ticket.get("status") == "created":
            _transition_ticket(
                conn,
                ticket=ticket,
                from_status="created",
                to_status="preflight_pending",
                reason="ticket_id_only_finalgate_preflight_started",
                now_ms=now_ms,
                finalgate_pass_id=None,
                blockers=[],
            )
            ticket = {**ticket, "status": "preflight_pending"}
        finalgate_pass_id = _finalgate_pass_id(ticket_id, now_ms)
        _transition_ticket(
            conn,
            ticket=ticket,
            from_status="preflight_pending",
            to_status="finalgate_rejected",
            reason="ticket_id_only_finalgate_preflight_blocked",
            now_ms=now_ms,
            finalgate_pass_id=finalgate_pass_id,
            blockers=blockers,
        )
        return _blocked(
            blockers,
            now_ms=now_ms,
            ticket={**ticket, "status": "finalgate_rejected"},
            finalgate_pass_id=finalgate_pass_id,
        )

    if ticket.get("status") == "created":
        _transition_ticket(
            conn,
            ticket=ticket,
            from_status="created",
            to_status="preflight_pending",
            reason="ticket_id_only_finalgate_preflight_started",
            now_ms=now_ms,
            finalgate_pass_id=None,
            blockers=[],
        )
        ticket = {**ticket, "status": "preflight_pending"}
    finalgate_pass_id = _finalgate_pass_id(ticket_id, now_ms)
    _transition_ticket(
        conn,
        ticket=ticket,
        from_status="preflight_pending",
        to_status="finalgate_ready",
        reason="ticket_id_only_finalgate_preflight_passed",
        now_ms=now_ms,
        finalgate_pass_id=finalgate_pass_id,
        blockers=[],
    )
    return _result(
        "finalgate_ready",
        now_ms=now_ms,
        ticket={**ticket, "status": "finalgate_ready"},
        blockers=[],
        finalgate_pass_id=finalgate_pass_id,
        next_action="prepare_official_operation_layer_handoff",
    )


def materialize_next_action_time_finalgate_preflight(
    conn: sa.engine.Connection,
    *,
    ticket_id: str = "",
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    ticket_id = str(ticket_id or "").strip()
    if ticket_id:
        return materialize_action_time_finalgate_preflight(
            conn,
            ticket_id=ticket_id,
            now_ms=now_ms,
        )
    try:
        control_state = PgBackedRuntimeControlStateRepository(
            conn,
            now_ms=now_ms,
        ).read_action_time_control_state()
    except RuntimeControlStateRepositoryError as exc:
        return _blocked(
            [f"runtime_control_state_invalid:{exc}"],
            now_ms=now_ms,
            ticket={},
            finalgate_pass_id=None,
        )
    tickets = [
        row
        for row in _control_state_rows(control_state.get("action_time_tickets"))
        if row.get("status") in ELIGIBLE_FINALGATE_TICKET_STATUSES
        and int(row.get("expires_at_ms") or 0) > now_ms
    ]
    if not tickets:
        return _result(
            "no_action_time_ticket",
            now_ms=now_ms,
            ticket={},
            blockers=[],
            finalgate_pass_id=None,
            next_action="continue_watcher_observation",
        )
    if len(tickets) > 1:
        return _blocked(
            ["multiple_eligible_action_time_tickets"],
            now_ms=now_ms,
            ticket={},
            finalgate_pass_id=None,
        )
    return materialize_action_time_finalgate_preflight(
        conn,
        ticket_id=str(tickets[0].get("ticket_id") or ""),
        now_ms=now_ms,
        control_state=control_state,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--ticket-id", default="")
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite or other SQLAlchemy URLs only for local unit tests.",
    )
    args = parser.parse_args(argv)
    if args.require_database_url and not args.database_url:
        print("ERROR: PG_DATABASE_URL is required for FinalGate preflight", file=sys.stderr)
        return 2
    if not args.database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if (
        not args.allow_non_postgres_for_test
        and not args.database_url.startswith(("postgresql://", "postgresql+psycopg://"))
    ):
        print("ERROR: FinalGate preflight requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(args.database_url)
    try:
        with engine.begin() as conn:
            report = materialize_next_action_time_finalgate_preflight(
                conn,
                ticket_id=args.ticket_id,
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
    return 0 if report["status"] in {
        "finalgate_ready",
        "finalgate_already_ready",
        "no_action_time_ticket",
    } else 1


def _finalgate_blockers(
    conn: sa.Connection,
    control_state: dict[str, Any],
    *,
    ticket: dict[str, Any],
    now_ms: int,
) -> list[str]:
    blockers: list[str] = []
    blockers.extend(
        current_scope_blockers(
            control_state,
            strategy_group_id=ticket.get("strategy_group_id"),
            symbol=ticket.get("symbol"),
            side=ticket.get("side"),
        )
    )
    if int(ticket.get("expires_at_ms") or 0) <= now_ms:
        blockers.append("ticket_expired")
    blockers.extend(_ticket_hash_blockers(ticket))

    lane = _row_by_id(
        control_state,
        "action_time_lane_inputs",
        "action_time_lane_input_id",
        ticket.get("action_time_lane_input_id"),
        blockers,
        "action_time_lane_missing",
    )
    signal = _row_by_id(
        control_state,
        "live_signal_events",
        "signal_event_id",
        ticket.get("signal_event_id"),
        blockers,
        "signal_event_missing",
    )
    runtime_scope = _row_by_id(
        control_state,
        "runtime_scope_bindings",
        "runtime_scope_binding_id",
        ticket.get("runtime_scope_binding_id"),
        blockers,
        "runtime_scope_binding_missing",
    )
    public_fact = _row_by_id(
        control_state,
        "runtime_fact_snapshots",
        "fact_snapshot_id",
        ticket.get("public_fact_snapshot_id"),
        blockers,
        "public_fact_snapshot_missing",
    )
    action_time_fact = _row_by_id(
        control_state,
        "runtime_fact_snapshots",
        "fact_snapshot_id",
        ticket.get("action_time_fact_snapshot_id"),
        blockers,
        "action_time_fact_snapshot_missing",
    )
    account_fact_surface, account_fact_id = _ticket_account_fact_pair(
        ticket,
        blockers=blockers,
    )
    account_safe_fact = _row_by_id(
        control_state,
        "runtime_fact_snapshots",
        "fact_snapshot_id",
        account_fact_id,
        blockers,
        f"{account_fact_surface}_fact_snapshot_missing",
    )
    account_mode_fact = _row_by_id(
        control_state,
        "runtime_fact_snapshots",
        "fact_snapshot_id",
        ticket.get("account_mode_snapshot_id"),
        blockers,
        "account_mode_snapshot_missing",
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
    event_spec = _row_by_id(
        control_state,
        "strategy_side_event_specs",
        "event_spec_id",
        ticket.get("event_spec_id"),
        blockers,
        "event_spec_missing",
    )

    for name, row in (
        ("lane", lane),
        ("signal", signal),
        ("runtime_scope", runtime_scope),
        ("public_fact", public_fact),
        ("action_time_fact", action_time_fact),
        ("account_fact", account_safe_fact),
        ("account_mode_fact", account_mode_fact),
        ("budget", budget),
        ("protection", protection),
        ("execution_policy", execution_policy),
        ("event_spec", event_spec),
    ):
        _assert_ticket_scope(blockers, ticket=ticket, row=row, label=name)

    if lane and lane.get("lane_scope") != "real_submit_candidate":
        blockers.append("lane_scope_not_real_submit_candidate")
    if lane and lane.get("status") not in {"ticket_created", "ticket_pending"}:
        blockers.append(f"lane_status_not_finalgate_eligible:{lane.get('status')}")
    if signal and signal.get("status") != "facts_validated":
        blockers.append(f"signal_event_status_not_validated:{signal.get('status')}")
    if signal and signal.get("freshness_state") != "fresh":
        blockers.append(f"signal_event_not_fresh:{signal.get('freshness_state')}")
    if signal and signal.get("source_kind") != "live_market":
        blockers.append(f"signal_event_not_live_market:{signal.get('source_kind') or 'missing'}")
    if signal and int(signal.get("expires_at_ms") or 0) <= now_ms:
        blockers.append("signal_event_expired")
    if signal and str(signal.get("event_spec_id") or "") != str(ticket.get("event_spec_id") or ""):
        blockers.append("signal_event_spec_mismatch")
    if signal and int(signal.get("event_time_ms") or 0) != int(ticket.get("event_time_ms") or 0):
        blockers.append("signal_event_time_mismatch:ticket")
    if signal and int(signal.get("trigger_candle_close_time_ms") or 0) != int(
        ticket.get("trigger_candle_close_time_ms") or 0
    ):
        blockers.append("signal_trigger_candle_close_time_mismatch:ticket")
    if signal and int(signal.get("event_time_ms") or 0) != int(
        signal.get("trigger_candle_close_time_ms") or 0
    ):
        blockers.append("signal_event_time_mismatch:trigger_candle_close_time_ms")
    if signal and int(signal.get("created_at_ms") or 0) == int(signal.get("event_time_ms") or 0):
        blockers.append("signal_generated_at_used_as_event_time")
    if runtime_scope:
        for flag in (
            "selected_strategygroup_scope",
            "symbol_side_scope_closed",
            "notional_leverage_scope_closed",
            "live_submit_allowed",
        ):
            if runtime_scope.get(flag) is not True:
                blockers.append(f"runtime_scope_not_closed:{flag}")
    for name, fact in (
        ("public_fact", public_fact),
        ("action_time_fact", action_time_fact),
        ("account_fact", account_safe_fact),
        ("account_mode_fact", account_mode_fact),
    ):
        _assert_fact_ready(blockers, name=name, fact=fact, now_ms=now_ms)
    account_values = _as_dict(account_safe_fact.get("fact_values"))
    if account_fact_surface == "account_safe":
        if account_values.get("account_safe") is not True:
            blockers.append("account_safe_fact_not_true")
        if account_values.get("open_orders_clear") is not True:
            blockers.append("open_orders_not_clear")
        if account_values.get("active_position_or_open_order_clear") is False:
            blockers.append("active_position_or_open_order_conflict")
    elif (
        account_values.get("schema_version") != "account_capacity_base.v1"
        or account_values.get("snapshot_complete") is not True
        or account_values.get("can_trade") is not True
    ):
        blockers.append("account_capacity_base_fact_not_safe")
    if budget and budget.get("ticket_id") != ticket.get("ticket_id"):
        blockers.append("budget_reservation_ticket_mismatch")
    if budget and budget.get("status") not in {"active", "consumed"}:
        blockers.append(f"budget_reservation_status_not_usable:{budget.get('status')}")
    if budget:
        blockers.extend(budget_stop_risk_blockers(budget))
    capacity_blockers, active_capacity_policy = account_capacity_current_blockers(
        conn,
        budget=budget,
        now_ms=now_ms,
    )
    blockers.extend(capacity_blockers)
    if active_capacity_policy and not capacity_blockers:
        if account_fact_surface != "account_capacity_base":
            blockers.append("account_capacity_fact_surface_required")
    if protection and int(protection.get("expires_at_ms") or 0) <= now_ms:
        blockers.append("protection_ref_expired")
    if execution_policy and execution_policy.get("status") != "current":
        blockers.append("execution_policy_not_current")
    if event_spec and event_spec.get("status") != "current":
        blockers.append("event_spec_not_current")
    if event_spec and event_spec.get("time_authority") != "trigger_candle_close_time_ms":
        blockers.append("unsupported_event_time_authority")
    if event_spec and str(
        f"{event_spec.get('event_spec_id')}:{event_spec.get('event_spec_version')}"
    ) != str(ticket.get("event_spec_version_id") or ""):
        blockers.append("event_spec_version_mismatch")
    return _dedupe(blockers)


_CAPACITY_REPLACED_LEGACY_BLOCKERS = {
    "account_safe_fact_not_satisfied",
    "account_safe_fact_not_fresh",
    "account_safe_fact_not_true",
    "open_orders_not_clear",
    "active_position_or_open_order_conflict",
}


def account_capacity_current_blockers(
    conn: sa.Connection,
    *,
    budget: dict[str, Any],
    now_ms: int,
) -> tuple[list[str], bool]:
    """Revalidate one immutable, already-counted claim by current semantics."""

    policy_version = str(budget.get("account_risk_policy_version") or "").strip()
    policy_event_id = str(budget.get("account_risk_policy_event_id") or "").strip()
    invocation_id = str(budget.get("action_time_invocation_id") or "").strip()
    ticket_id = str(budget.get("ticket_id") or "").strip()
    if not policy_version or budget.get("account_capacity_projection_version") is None:
        return [], False
    if not policy_event_id:
        return ["account_risk_policy_event_missing"], True
    if not invocation_id or not ticket_id:
        return ["account_capacity_claim_lineage_missing"], True

    try:
        claim = load_account_capacity_claim_by_invocation(
            conn,
            action_time_invocation_id=invocation_id,
        )
    except (AccountCapacityClaimConflict, TypeError, ValueError):
        return ["account_capacity_claim_invalid"], True
    if claim is None or claim.payload.ticket_id != ticket_id:
        return ["account_capacity_claim_missing"], True
    if (
        claim.capacity_claim_hash != capacity_claim_hash(claim.payload)
        or claim.capacity_claim_hash
        != str(budget.get("capacity_claim_hash") or "").strip()
    ):
        return ["account_capacity_claim_hash_mismatch"], True

    claim_count = int(
        conn.execute(
            sa.text(
                """
                SELECT count(*)
                FROM brc_budget_reservations
                WHERE account_id = :account_id
                  AND runtime_profile_id = :runtime_profile_id
                  AND ticket_id = :ticket_id
                  AND status IN ('active', 'consumed')
                """
            ),
            {
                "account_id": claim.payload.account_id,
                "runtime_profile_id": claim.payload.runtime_profile_id,
                "ticket_id": ticket_id,
            },
        ).scalar_one()
    )
    if claim_count == 0:
        return ["account_capacity_claim_not_counted"], True
    if claim_count != 1:
        return ["account_capacity_claim_count_mismatch"], True

    policy = conn.execute(
        sa.text(
            """
            SELECT risk_policy_version, activation_state, source_event_id,
                   max_concurrent_positions,
                   max_portfolio_open_risk_fraction,
                   max_cluster_open_risk_fraction,
                   max_portfolio_initial_margin_fraction
            FROM brc_account_risk_policy_current
            WHERE account_id = :account_id
              AND runtime_profile_id = :runtime_profile_id
            ORDER BY risk_policy_version
            LIMIT 2
            """
        ),
        {
            "account_id": claim.payload.account_id,
            "runtime_profile_id": claim.payload.runtime_profile_id,
        },
    ).mappings().one_or_none()
    if policy is None or str(policy.get("risk_policy_version") or "") != policy_version:
        return ["account_risk_policy_missing_or_changed"], True
    if str(policy.get("source_event_id") or "") != policy_event_id:
        return ["account_risk_policy_event_changed"], True
    if str(policy.get("activation_state") or "") != "active":
        return ["account_risk_policy_not_active"], True

    projection = conn.execute(
        sa.text(
            """
            SELECT projection_version, total_wallet_balance, available_balance,
                   portfolio_held_risk, unreflected_pending_margin,
                   exchange_total_initial_margin,
                   claimed_position_slots, valid_until_ms,
                   reconciliation_state, first_blocker
            FROM brc_account_budget_current
            WHERE account_id = :account_id
              AND runtime_profile_id = :runtime_profile_id
              AND risk_policy_version = :risk_policy_version
            ORDER BY account_budget_current_id
            LIMIT 2
            """
        ),
        {
            "account_id": claim.payload.account_id,
            "runtime_profile_id": claim.payload.runtime_profile_id,
            "risk_policy_version": policy_version,
        },
    ).mappings().one_or_none()
    if projection is None:
        return ["account_budget_current_missing"], True
    if int(projection.get("projection_version") or 0) != int(
        budget.get("account_capacity_projection_version") or 0
    ):
        return ["account_capacity_post_claim_projection_version_mismatch"], True
    if int(projection.get("valid_until_ms") or 0) <= now_ms:
        return ["account_budget_current_stale"], True

    max_positions = int(policy["max_concurrent_positions"])
    exposure_rows = load_live_exposure_rows(
        conn,
        account_id=claim.payload.account_id,
        max_concurrent_positions=max_positions,
    )
    if exposure_rows.overflow:
        return ["account_exposure_current_overflow"], True
    exposure_blockers = sorted(
        {str(row.first_blocker) for row in exposure_rows.rows if row.first_blocker}
    )
    if exposure_blockers:
        return exposure_blockers, True
    own_slot_count = sum(
        1
        for row in exposure_rows.rows
        if row.owner_ticket_id == ticket_id and row.position_slot_claimed
    )
    if own_slot_count == 0:
        return ["account_capacity_claim_slot_not_counted"], True
    if own_slot_count != 1:
        return ["account_capacity_claim_slot_count_mismatch"], True

    try:
        current_facts = load_instrument_risk_facts(
            conn,
            exchange_instrument_id=claim.payload.instrument.exchange_instrument_id,
            risk_policy_version=policy_version,
            planned_notional=claim.payload.target_notional,
            now_ms=now_ms,
        )
    except InstrumentRiskFactsError as exc:
        return [str(exc)], True
    if current_facts.identity != claim.payload.instrument:
        return ["account_capacity_claim_instrument_identity_changed"], True
    if (
        current_facts.cluster_snapshot.primary_risk_cluster_id
        != claim.payload.cluster_snapshot.primary_risk_cluster_id
    ):
        return ["account_capacity_primary_cluster_changed"], True
    rule_blockers = _current_rule_legality_blockers(
        claim=claim.payload,
        current_rule=current_facts.rule_snapshot,
    )
    if rule_blockers:
        return rule_blockers, True

    cluster_held_risk = _decimal(
        conn.execute(
            sa.text(
                """
                SELECT COALESCE(sum(held_risk), 0)
                FROM brc_account_exposure_current
                WHERE account_id = :account_id
                  AND primary_risk_cluster_id = :primary_risk_cluster_id
                  AND exposure_state NOT IN ('flat', 'closed')
                """
            ),
            {
                "account_id": claim.payload.account_id,
                "primary_risk_cluster_id": (
                    current_facts.cluster_snapshot.primary_risk_cluster_id
                ),
            },
        ).scalar_one()
    )
    wallet = _decimal(projection["total_wallet_balance"])
    blockers = revalidate_capacity_totals(
        current_portfolio_held_risk=_decimal(projection["portfolio_held_risk"]),
        current_primary_cluster_held_risk=cluster_held_risk,
        current_pending_margin=_decimal(projection["unreflected_pending_margin"]),
        current_claimed_position_slots=int(projection["claimed_position_slots"]),
        available_balance=_decimal(projection["available_balance"]),
        claim_risk=claim.payload.planned_stop_risk,
        claim_margin=claim.payload.reserved_margin,
        portfolio_limit=(
            wallet * _decimal(policy["max_portfolio_open_risk_fraction"])
        ),
        cluster_limit=(
            wallet * _decimal(policy["max_cluster_open_risk_fraction"])
        ),
        margin_limit=max(
            Decimal("0"),
            wallet * _decimal(policy["max_portfolio_initial_margin_fraction"])
            - _decimal(projection["exchange_total_initial_margin"]),
        ),
        max_concurrent_positions=max_positions,
    )
    return list(blockers), True


def _current_rule_legality_blockers(*, claim: Any, current_rule: Any) -> list[str]:
    quantities = (claim.intended_qty,)
    prices = (claim.entry_reference_price, claim.stop_price)
    if any(quantity % current_rule.quantity_step != 0 for quantity in quantities):
        return ["account_capacity_claim_quantity_rule_invalid"]
    if claim.intended_qty < current_rule.min_qty:
        return ["account_capacity_claim_quantity_rule_invalid"]
    if any(price % current_rule.price_tick != 0 for price in prices):
        return ["account_capacity_claim_price_rule_invalid"]
    notional = (
        claim.intended_qty
        * claim.entry_reference_price
        * current_rule.contract_multiplier
    )
    if notional < current_rule.min_notional:
        return ["account_capacity_claim_min_notional_invalid"]
    if (
        claim.selected_leverage
        > current_rule.exchange_max_leverage_for_claim_notional
    ):
        return ["account_capacity_claim_leverage_rule_invalid"]
    return []


def _decimal(value: object) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("account_capacity_decimal_invalid") from exc
    if not result.is_finite():
        raise ValueError("account_capacity_decimal_invalid")
    return result


def _ticket_hash_blockers(ticket: dict[str, Any]) -> list[str]:
    if not ticket.get("ticket_hash"):
        return ["ticket_hash_missing"]
    try:
        computed_hash = compute_action_time_ticket_hash(ticket)
    except ValueError:
        return ["ticket_hash_schema_unknown"]
    if computed_hash != ticket.get("ticket_hash"):
        return ["ticket_hash_mismatch"]
    return []


def _transition_ticket(
    conn: sa.engine.Connection,
    *,
    ticket: dict[str, Any],
    from_status: str,
    to_status: str,
    reason: str,
    now_ms: int,
    finalgate_pass_id: str | None,
    blockers: list[str],
) -> None:
    event_identity = (
        f"{ticket['ticket_id']}|{from_status}|{to_status}|{now_ms}"
    )
    event_id = f"ticket_event:{sha256(event_identity.encode('utf-8')).hexdigest()}"
    payload = {
        "finalgate_pass_id": finalgate_pass_id,
        "blockers": blockers,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }
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
        {
            "ticket_event_id": event_id,
            "ticket_id": ticket["ticket_id"],
            "action_time_lane_input_id": ticket["action_time_lane_input_id"],
            "from_status": from_status,
            "to_status": to_status,
            "transition_reason": reason,
            "trigger_ref": finalgate_pass_id,
            "writer": "materialize_action_time_finalgate_preflight",
            "event_payload": json.dumps(payload, sort_keys=True),
            "occurred_at_ms": now_ms,
            "created_at_ms": now_ms,
        },
    )
    conn.execute(
        text(
            """
            UPDATE brc_action_time_tickets
            SET status = :status
            WHERE ticket_id = :ticket_id
            """
        ),
        {"status": to_status, "ticket_id": ticket["ticket_id"]},
    )


def _ticket_by_id(control_state: dict[str, Any], ticket_id: str) -> dict[str, Any]:
    return next(
        (
            row
            for row in _control_state_rows(control_state.get("action_time_tickets"))
            if row.get("ticket_id") == ticket_id
        ),
        {},
    )


def _latest_finalgate_pass_id(control_state: dict[str, Any], ticket_id: str) -> str | None:
    events = [
        row
        for row in _control_state_rows(control_state.get("action_time_ticket_events"))
        if row.get("ticket_id") == ticket_id and row.get("to_status") == "finalgate_ready"
    ]
    if not events:
        return None
    event = sorted(events, key=lambda row: int(row.get("occurred_at_ms") or 0))[-1]
    payload = _as_dict(event.get("event_payload"))
    return str(payload.get("finalgate_pass_id") or "") or None


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
        (
            item
            for item in _control_state_rows(control_state.get(table_key))
            if item.get(id_key) == row_id
        ),
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


def _assert_fact_ready(
    blockers: list[str],
    *,
    name: str,
    fact: dict[str, Any],
    now_ms: int,
) -> None:
    if not fact:
        return
    if fact.get("computed") is not True:
        blockers.append(f"{name}_not_computed")
    if fact.get("satisfied") is not True:
        blockers.append(f"{name}_not_satisfied")
    if fact.get("freshness_state") != "fresh":
        blockers.append(f"{name}_not_fresh")
    if int(fact.get("valid_until_ms") or 0) <= now_ms:
        blockers.append(f"{name}_expired")


def _finalgate_pass_id(ticket_id: str, now_ms: int) -> str:
    return f"finalgate_pass:{ticket_id}:{now_ms}"


def _blocked(
    blockers: list[str],
    *,
    now_ms: int,
    ticket: dict[str, Any],
    finalgate_pass_id: str | None,
) -> dict[str, Any]:
    return _result(
        "blocked",
        now_ms=now_ms,
        ticket=ticket,
        blockers=_dedupe(blockers),
        finalgate_pass_id=finalgate_pass_id,
        next_action="repair_ticket_bound_finalgate_inputs",
    )


def _result(
    status: str,
    *,
    now_ms: int,
    ticket: dict[str, Any],
    blockers: list[str],
    finalgate_pass_id: str | None,
    next_action: str,
) -> dict[str, Any]:
    return {
        "schema": "brc.action_time_finalgate_preflight.v1",
        "status": status,
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "ticket_id": ticket.get("ticket_id"),
        "finalgate_pass_id": finalgate_pass_id,
        "action_time_lane_input_id": ticket.get("action_time_lane_input_id"),
        "strategy_group_id": ticket.get("strategy_group_id"),
        "symbol": ticket.get("symbol"),
        "side": ticket.get("side"),
        "blockers": blockers,
        "next_action": next_action,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "forbidden_effects": FORBIDDEN_EFFECTS,
        "created_at_ms": now_ms,
    }


def _control_state_rows(value: Any) -> list[dict[str, Any]]:
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


if __name__ == "__main__":
    raise SystemExit(main())
