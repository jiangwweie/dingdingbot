#!/usr/bin/env python3
"""Materialize PG fresh signals into promotion candidates and one action-time lane.

This script is the PG-only L4 -> L5 bridge:

live_signal_event + readiness + runtime scope + facts
-> promotion candidates
-> one real-submit action-time lane
-> lane-scoped budget reservation and protection reference

It does not call FinalGate, Operation Layer, exchange write APIs, order
lifecycle, withdrawals, transfers, live profile mutation, or order sizing
mutation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_daily_live_enablement_table import WIP_LANES  # noqa: E402
from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
)


DEFAULT_REPORT_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-signal-watcher")
DEFAULT_OUTPUT_JSON = DEFAULT_REPORT_DIR / "pg-promotion-action-time-lane-materialization.json"
OPEN_REAL_LANE_STATUSES = {
    "opened",
    "facts_refreshing",
    "ticket_pending",
    "ticket_created",
}
PROMOTION_AUTHORITY_BOUNDARY = (
    "pg_promotion_candidate_non_executing; "
    "no_finalgate_no_operation_layer_no_exchange_write"
)
LANE_AUTHORITY_BOUNDARY = (
    "pg_real_submit_candidate_identity_only; "
    "no_finalgate_no_operation_layer_no_exchange_write"
)
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


@dataclass(frozen=True)
class CandidateBundle:
    candidate: dict[str, Any]
    runtime_scope: dict[str, Any]
    policy: dict[str, Any]
    event_binding: dict[str, Any]
    event_spec: dict[str, Any]
    signal: dict[str, Any]
    readiness: dict[str, Any]
    public_fact: dict[str, Any]
    action_time_fact: dict[str, Any]
    account_safe_fact: dict[str, Any]
    account_mode_fact: dict[str, Any]
    coverage: dict[str, Any]
    owner_policy_version: str
    account_id: str
    blockers: tuple[str, ...]

    @property
    def key(self) -> tuple[str, str, str]:
        return _lane_key(self.candidate)

    @property
    def promotion_candidate_id(self) -> str:
        return _stable_id("promotion", str(self.signal["signal_event_id"]))

    @property
    def action_time_lane_input_id(self) -> str:
        return _stable_id("lane", str(self.signal["signal_event_id"]))

    @property
    def budget_reservation_id(self) -> str:
        return _stable_id("budget", self.action_time_lane_input_id)

    @property
    def protection_ref_id(self) -> str:
        return _stable_id(
            "protection",
            str(self.event_spec["event_spec_id"]),
            str(self.action_time_fact["fact_snapshot_id"]),
        )


def materialize_pg_promotion_action_time_lane(
    conn: sa.engine.Connection,
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    try:
        control_state = PgBackedRuntimeControlStateRepository(conn).read_control_state()
    except RuntimeControlStateRepositoryError as exc:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=[f"runtime_control_state_invalid:{exc}"],
            next_action="repair_pg_runtime_control_state",
        )

    open_lanes = _open_real_submit_lanes(control_state)
    if open_lanes:
        lane = sorted(open_lanes, key=lambda row: str(row.get("action_time_lane_input_id") or ""))[0]
        lane_expires_at_ms = int(lane.get("expires_at_ms") or 0)
        if lane_expires_at_ms <= now_ms:
            return _result(
                "open_action_time_lane_expired",
                now_ms=now_ms,
                action_time_lane_input_id=str(lane.get("action_time_lane_input_id") or ""),
                promotion_candidate_id=str(lane.get("promotion_candidate_id") or ""),
                signal_event_id=str(lane.get("signal_event_id") or ""),
                strategy_group_id=str(lane.get("strategy_group_id") or ""),
                symbol=str(lane.get("symbol") or ""),
                side=str(lane.get("side") or ""),
                blockers=["open_action_time_lane_expired_not_closed"],
                next_action="expire_or_close_pg_action_time_lane",
            )
        return _result(
            "action_time_lane_already_open",
            now_ms=now_ms,
            action_time_lane_input_id=str(lane.get("action_time_lane_input_id") or ""),
            promotion_candidate_id=str(lane.get("promotion_candidate_id") or ""),
            signal_event_id=str(lane.get("signal_event_id") or ""),
            strategy_group_id=str(lane.get("strategy_group_id") or ""),
            symbol=str(lane.get("symbol") or ""),
            side=str(lane.get("side") or ""),
            blockers=[],
            next_action="materialize_action_time_ticket",
        )

    bundles = _fresh_signal_bundles(control_state, now_ms=now_ms)
    if not bundles:
        return _result(
            "no_fresh_signal",
            now_ms=now_ms,
            blockers=[],
            next_action="continue_watcher_observation",
        )

    eligible = [bundle for bundle in bundles if not bundle.blockers]
    blocked = [bundle for bundle in bundles if bundle.blockers]
    selected = _select_winner(eligible)
    selected_id = selected.promotion_candidate_id if selected else ""

    promotion_rows: list[dict[str, Any]] = []
    for bundle in blocked:
        promotion_rows.append(
            _promotion_row(
                bundle,
                now_ms=now_ms,
                status="blocked",
                arbitration_rank=None,
                closed_at_ms=now_ms,
            )
        )
    for rank, bundle in enumerate(_ranked_candidates(eligible), start=1):
        promotion_rows.append(
            _promotion_row(
                bundle,
                now_ms=now_ms,
                status="arbitration_won"
                if bundle.promotion_candidate_id == selected_id
                else "arbitration_lost",
                arbitration_rank=rank,
                closed_at_ms=None
                if bundle.promotion_candidate_id == selected_id
                else now_ms,
            )
        )

    for row in promotion_rows:
        _upsert_row(conn, "brc_promotion_candidates", "promotion_candidate_id", row)

    if selected is None:
        return _result(
            "promotion_candidates_blocked",
            now_ms=now_ms,
            blockers=_dedupe(
                blocker
                for bundle in blocked
                for blocker in bundle.blockers
            ),
            promotion_candidate_count=len(promotion_rows),
            next_action="repair_first_blocked_fresh_signal_candidate",
            per_candidate_results=_candidate_results(bundles, selected=None),
        )

    lane = _lane_row(selected, now_ms=now_ms)
    budget = _budget_row(selected, now_ms=now_ms)
    protection = _protection_row(selected)
    _upsert_row(conn, "brc_action_time_lane_inputs", "action_time_lane_input_id", lane)
    _upsert_row(conn, "brc_budget_reservations", "budget_reservation_id", budget)
    _upsert_row(conn, "brc_protection_references", "protection_ref_id", protection)

    return _result(
        "promotion_action_time_lane_created",
        now_ms=now_ms,
        promotion_candidate_id=selected.promotion_candidate_id,
        action_time_lane_input_id=selected.action_time_lane_input_id,
        budget_reservation_id=selected.budget_reservation_id,
        protection_ref_id=selected.protection_ref_id,
        signal_event_id=str(selected.signal["signal_event_id"]),
        strategy_group_id=str(selected.candidate["strategy_group_id"]),
        symbol=str(selected.candidate["symbol"]),
        side=str(selected.candidate["side"]),
        blockers=[],
        promotion_candidate_count=len(promotion_rows),
        next_action="materialize_action_time_ticket",
        per_candidate_results=_candidate_results(bundles, selected=selected),
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
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.require_database_url and not args.database_url:
        print(
            "ERROR: PG_DATABASE_URL is required for PG promotion/action-time lane materializer",
            file=sys.stderr,
        )
        return 2
    if not args.database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if (
        not args.allow_non_postgres_for_test
        and not args.database_url.startswith(("postgresql://", "postgresql+psycopg://"))
    ):
        print("ERROR: PG promotion/action-time lane materializer requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(args.database_url)
    try:
        with engine.begin() as conn:
            report = materialize_pg_promotion_action_time_lane(conn, now_ms=args.now_ms)
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
    return 1 if report["status"] in {"blocked", "promotion_candidates_blocked"} else 0


def _fresh_signal_bundles(
    control_state: dict[str, Any],
    *,
    now_ms: int,
) -> list[CandidateBundle]:
    candidates = _active_candidate_rows(control_state)
    runtime_by_candidate = _active_by(control_state, "runtime_scope_bindings", "candidate_scope_id")
    policy_by_id = {
        str(row.get("policy_current_id") or ""): row
        for row in _rows(control_state.get("owner_policy_current"))
    }
    event_binding_by_candidate = _active_by(
        control_state,
        "candidate_scope_event_bindings",
        "candidate_scope_id",
    )
    event_by_id = {
        str(row.get("event_spec_id") or ""): row
        for row in _rows(control_state.get("strategy_side_event_specs"))
        if row.get("status") == "current"
    }
    readiness_by_lane = {
        _lane_key(row): row
        for row in _rows(control_state.get("pretrade_readiness_rows"))
    }
    coverage_by_lane = _current_coverage_by_lane(control_state)
    owner_policy_version_by_id = _owner_policy_version_by_id(control_state)

    bundles: list[CandidateBundle] = []
    for candidate in candidates:
        candidate_scope_id = str(candidate.get("candidate_scope_id") or "")
        event_binding = event_binding_by_candidate.get(candidate_scope_id, {})
        event_spec = event_by_id.get(str(event_binding.get("event_spec_id") or ""), {})
        signal = _fresh_signal_for_candidate(
            control_state,
            candidate=candidate,
            event_spec=event_spec,
            now_ms=now_ms,
        )
        if not signal:
            continue
        runtime_scope = runtime_by_candidate.get(candidate_scope_id, {})
        policy = policy_by_id.get(str(candidate.get("policy_current_id") or ""), {})
        readiness = readiness_by_lane.get(_lane_key(candidate), {})
        public_fact = _fact_by_id(
            control_state,
            str(signal.get("fact_snapshot_id") or ""),
        )
        action_time_fact = _latest_fact(
            control_state,
            candidate=candidate,
            runtime_profile_id=str(runtime_scope.get("runtime_profile_id") or ""),
            fact_surface="action_time",
        )
        account_safe_fact = _latest_fact(
            control_state,
            candidate=candidate,
            runtime_profile_id=str(runtime_scope.get("runtime_profile_id") or ""),
            fact_surface="account_safe",
            allow_global=True,
        )
        account_mode_fact = _latest_fact(
            control_state,
            candidate=candidate,
            runtime_profile_id=str(runtime_scope.get("runtime_profile_id") or ""),
            fact_surface="account_mode",
            allow_global=True,
        )
        coverage = coverage_by_lane.get(_lane_key(candidate), {})
        owner_policy_version = owner_policy_version_by_id.get(
            str(policy.get("policy_current_id") or ""),
            "",
        )
        account_id = _account_id(control_state, candidate)
        blockers = tuple(
            _candidate_blockers(
                control_state,
                now_ms=now_ms,
                candidate=candidate,
                runtime_scope=runtime_scope,
                policy=policy,
                event_binding=event_binding,
                event_spec=event_spec,
                signal=signal,
                readiness=readiness,
                public_fact=public_fact,
                action_time_fact=action_time_fact,
                account_safe_fact=account_safe_fact,
                account_mode_fact=account_mode_fact,
                coverage=coverage,
                owner_policy_version=owner_policy_version,
                account_id=account_id,
            )
        )
        bundles.append(
            CandidateBundle(
                candidate=candidate,
                runtime_scope=runtime_scope,
                policy=policy,
                event_binding=event_binding,
                event_spec=event_spec,
                signal=signal,
                readiness=readiness,
                public_fact=public_fact,
                action_time_fact=action_time_fact,
                account_safe_fact=account_safe_fact,
                account_mode_fact=account_mode_fact,
                coverage=coverage,
                owner_policy_version=owner_policy_version,
                account_id=account_id,
                blockers=blockers,
            )
        )
    return bundles


def _candidate_blockers(
    control_state: dict[str, Any],
    *,
    now_ms: int,
    candidate: dict[str, Any],
    runtime_scope: dict[str, Any],
    policy: dict[str, Any],
    event_binding: dict[str, Any],
    event_spec: dict[str, Any],
    signal: dict[str, Any],
    readiness: dict[str, Any],
    public_fact: dict[str, Any],
    action_time_fact: dict[str, Any],
    account_safe_fact: dict[str, Any],
    account_mode_fact: dict[str, Any],
    coverage: dict[str, Any],
    owner_policy_version: str,
    account_id: str,
) -> list[str]:
    blockers: list[str] = []
    _require_identity_match(blockers, candidate, runtime_scope, "runtime_scope")
    _require_identity_match(blockers, candidate, policy, "policy")
    _require_identity_match(blockers, candidate, event_binding, "event_binding")
    _require_identity_match(blockers, candidate, event_spec, "event_spec", keys=("strategy_group_id", "side"))
    _require_identity_match(blockers, candidate, signal, "signal")
    _require_identity_match(blockers, candidate, readiness, "readiness")
    _require_identity_match(blockers, candidate, public_fact, "public_fact")
    _require_identity_match(blockers, candidate, action_time_fact, "action_time_fact")

    if not event_binding:
        blockers.append("candidate_event_binding_missing")
    if not event_spec:
        blockers.append("event_spec_missing")
    if str(signal.get("event_spec_id") or "") != str(event_spec.get("event_spec_id") or ""):
        blockers.append("signal_event_spec_mismatch")
    if str(signal.get("candidate_scope_id") or "") != str(candidate.get("candidate_scope_id") or ""):
        blockers.append("signal_candidate_scope_mismatch")
    if signal.get("source_kind") != "live_market":
        blockers.append(f"signal_event_not_live_market:{signal.get('source_kind') or 'missing'}")
    if signal.get("status") != "facts_validated":
        blockers.append(f"signal_event_not_facts_validated:{signal.get('status') or 'missing'}")
    if signal.get("freshness_state") != "fresh":
        blockers.append(f"signal_event_not_fresh:{signal.get('freshness_state') or 'missing'}")
    if int(signal.get("expires_at_ms") or 0) <= now_ms:
        blockers.append("signal_event_expired")
    if int(signal.get("event_time_ms") or 0) <= 0:
        blockers.append("signal_event_time_missing")
    if int(signal.get("event_time_ms") or 0) != int(signal.get("trigger_candle_close_time_ms") or 0):
        blockers.append("signal_event_time_mismatch:trigger_candle_close_time_ms")
    if int(signal.get("created_at_ms") or 0) == int(signal.get("event_time_ms") or 0):
        blockers.append("signal_generated_at_used_as_event_time")

    if runtime_scope.get("status") != "active":
        blockers.append("runtime_scope_binding_not_active")
    for flag in (
        "selected_strategygroup_scope",
        "symbol_side_scope_closed",
        "notional_leverage_scope_closed",
        "live_submit_allowed",
    ):
        if runtime_scope.get(flag) is not True:
            blockers.append(f"runtime_scope_not_closed:{flag}")
    if policy.get("enabled_state") != "enabled":
        blockers.append("owner_policy_not_enabled")
    if policy.get("pretrade_candidate_allowed") is not True:
        blockers.append("owner_policy_blocks_pretrade")
    if policy.get("action_time_rehearsal_allowed") is not True:
        blockers.append("owner_policy_blocks_action_time")
    if policy.get("live_submit_allowed") not in {"scoped", "conditional_hard_gated"}:
        blockers.append("owner_policy_blocks_live_submit")
    if not owner_policy_version:
        blockers.append("owner_policy_version_missing")

    if candidate.get("scope_state") != "live_submit_allowed":
        blockers.append(f"candidate_scope_not_live_submit:{candidate.get('scope_state') or 'missing'}")
    if readiness.get("readiness_state") != "action_time_lane":
        blockers.append(
            f"readiness_not_action_time_lane:{readiness.get('readiness_state') or 'missing'}"
        )
    if readiness.get("public_facts_state") != "satisfied":
        blockers.append(f"public_facts_not_satisfied:{readiness.get('public_facts_state') or 'missing'}")
    if readiness.get("signal_lifecycle_status") != "facts_validated":
        blockers.append("readiness_signal_not_facts_validated")
    if readiness.get("signal_freshness_state") != "fresh":
        blockers.append("readiness_signal_not_fresh")
    if readiness.get("risk_state") != "acceptable":
        blockers.append(f"risk_state_not_acceptable:{readiness.get('risk_state') or 'missing'}")
    if readiness.get("scope_state") != "live_submit_allowed":
        blockers.append(f"readiness_scope_not_live_submit:{readiness.get('scope_state') or 'missing'}")
    if readiness.get("promotion_state") != "action_time_lane":
        blockers.append(f"readiness_promotion_not_action_time_lane:{readiness.get('promotion_state') or 'missing'}")
    if readiness.get("first_blocker_class") != "action_time_preflight_ready":
        blockers.append(
            f"readiness_not_action_time_preflight_ready:{readiness.get('first_blocker_class') or 'missing'}"
        )

    if coverage.get("coverage_state") != "covered":
        blockers.append(f"runtime_coverage_not_covered:{coverage.get('coverage_state') or 'missing'}")
    if coverage.get("liveness_state") not in {"healthy", "ok", "active"}:
        blockers.append(f"runtime_coverage_not_healthy:{coverage.get('liveness_state') or 'missing'}")
    if coverage.get("is_current") is not True:
        blockers.append("runtime_coverage_not_current")
    if int(coverage.get("valid_until_ms") or 0) <= now_ms:
        blockers.append("runtime_coverage_expired")

    _assert_fact_ready(blockers, "public_fact", public_fact, now_ms=now_ms)
    _assert_fact_ready(blockers, "action_time_fact", action_time_fact, now_ms=now_ms)
    _assert_fact_ready(blockers, "account_safe_fact", account_safe_fact, now_ms=now_ms)
    _assert_fact_ready(blockers, "account_mode_fact", account_mode_fact, now_ms=now_ms)
    account_values = _as_dict(account_safe_fact.get("fact_values"))
    if account_values.get("account_safe") is not True:
        blockers.append("account_safe_fact_not_true")
    if account_values.get("open_orders_clear") is not True:
        blockers.append("open_orders_not_clear")
    if account_values.get("active_position_or_open_order_clear") is False:
        blockers.append("active_position_or_open_order_conflict")

    blockers.extend(
        _required_fact_blockers(
            control_state,
            event_spec_id=str(event_spec.get("event_spec_id") or ""),
            fact_values=_as_dict(action_time_fact.get("fact_values")),
        )
    )
    protection_ref_type = str(event_spec.get("protection_ref_type") or "")
    if not protection_ref_type:
        blockers.append("protection_ref_type_missing")
    elif _decimal(_as_dict(action_time_fact.get("fact_values")).get(protection_ref_type)) <= 0:
        blockers.append(f"protection_reference_fact_missing:{protection_ref_type}")

    if _decimal(policy.get("max_notional")) <= 0:
        blockers.append("policy_max_notional_invalid")
    if _decimal(policy.get("leverage")) <= 0:
        blockers.append("policy_leverage_invalid")
    if account_id == "":
        blockers.append("account_id_missing")

    return _dedupe(blockers)


def _promotion_row(
    bundle: CandidateBundle,
    *,
    now_ms: int,
    status: str,
    arbitration_rank: int | None,
    closed_at_ms: int | None,
) -> dict[str, Any]:
    expires_at_ms = min(
        int(bundle.signal.get("expires_at_ms") or 0),
        int(bundle.public_fact.get("valid_until_ms") or 0),
        int(bundle.action_time_fact.get("valid_until_ms") or 0),
    )
    if expires_at_ms <= 0:
        expires_at_ms = int(bundle.signal.get("expires_at_ms") or now_ms)
    return {
        "promotion_candidate_id": bundle.promotion_candidate_id,
        "signal_event_id": str(bundle.signal["signal_event_id"]),
        "readiness_row_id": str(bundle.readiness.get("readiness_row_id") or ""),
        "strategy_group_id": str(bundle.candidate["strategy_group_id"]),
        "symbol": str(bundle.candidate["symbol"]),
        "side": str(bundle.candidate["side"]),
        "promotion_scope": "live_submit_candidate",
        "status": status,
        "scope_state": str(bundle.readiness.get("scope_state") or bundle.candidate.get("scope_state") or ""),
        "risk_state": str(bundle.readiness.get("risk_state") or ""),
        "facts_snapshot_id": str(bundle.public_fact.get("fact_snapshot_id") or ""),
        "blockers": list(bundle.blockers),
        "arbitration_rank": arbitration_rank,
        "created_at_ms": now_ms,
        "expires_at_ms": expires_at_ms,
        "closed_at_ms": closed_at_ms,
        "authority_boundary": PROMOTION_AUTHORITY_BOUNDARY,
    }


def _lane_row(bundle: CandidateBundle, *, now_ms: int) -> dict[str, Any]:
    expires_at_ms = min(
        int(bundle.signal["expires_at_ms"]),
        int(bundle.public_fact["valid_until_ms"]),
        int(bundle.action_time_fact["valid_until_ms"]),
        int(bundle.account_safe_fact["valid_until_ms"]),
        int(bundle.account_mode_fact["valid_until_ms"]),
    )
    return {
        "action_time_lane_input_id": bundle.action_time_lane_input_id,
        "promotion_candidate_id": bundle.promotion_candidate_id,
        "strategy_group_id": str(bundle.candidate["strategy_group_id"]),
        "symbol": str(bundle.candidate["symbol"]),
        "side": str(bundle.candidate["side"]),
        "runtime_profile_id": str(bundle.runtime_scope["runtime_profile_id"]),
        "lane_scope": "real_submit_candidate",
        "status": "ticket_pending",
        "signal_event_id": str(bundle.signal["signal_event_id"]),
        "public_fact_snapshot_id": str(bundle.public_fact["fact_snapshot_id"]),
        "action_time_fact_snapshot_id": str(bundle.action_time_fact["fact_snapshot_id"]),
        "runtime_scope_binding_id": str(bundle.runtime_scope["runtime_scope_binding_id"]),
        "candidate_authorization_ref": f"candidate_auth:{bundle.promotion_candidate_id}",
        "runtime_safety_snapshot_id": None,
        "first_blocker_class": "action_time_preflight_ready",
        "created_at_ms": now_ms,
        "expires_at_ms": expires_at_ms,
        "closed_at_ms": None,
        "authority_boundary": LANE_AUTHORITY_BOUNDARY,
    }


def _budget_row(bundle: CandidateBundle, *, now_ms: int) -> dict[str, Any]:
    target_notional = _decimal(bundle.policy.get("max_notional"))
    leverage = _decimal(bundle.policy.get("leverage"))
    reserved_margin = target_notional / leverage
    return {
        "budget_reservation_id": bundle.budget_reservation_id,
        "promotion_candidate_id": bundle.promotion_candidate_id,
        "action_time_lane_input_id": bundle.action_time_lane_input_id,
        "ticket_id": None,
        "signal_event_id": str(bundle.signal["signal_event_id"]),
        "event_spec_id": str(bundle.event_spec["event_spec_id"]),
        "runtime_profile_id": str(bundle.runtime_scope["runtime_profile_id"]),
        "account_id": bundle.account_id,
        "strategy_group_id": str(bundle.candidate["strategy_group_id"]),
        "symbol": str(bundle.candidate["symbol"]),
        "side": str(bundle.candidate["side"]),
        "target_notional": target_notional,
        "leverage": leverage,
        "reserved_margin": reserved_margin,
        "reserved_at_ms": now_ms,
        "expires_at_ms": min(
            int(bundle.signal["expires_at_ms"]),
            int(bundle.action_time_fact["valid_until_ms"]),
        ),
        "status": "active",
        "release_reason": None,
        "policy_version": bundle.owner_policy_version,
    }


def _protection_row(bundle: CandidateBundle) -> dict[str, Any]:
    fact_values = _as_dict(bundle.action_time_fact.get("fact_values"))
    reference_type = str(bundle.event_spec["protection_ref_type"])
    return {
        "protection_ref_id": bundle.protection_ref_id,
        "event_spec_id": str(bundle.event_spec["event_spec_id"]),
        "strategy_group_id": str(bundle.candidate["strategy_group_id"]),
        "symbol": str(bundle.candidate["symbol"]),
        "side": str(bundle.candidate["side"]),
        "reference_type": reference_type,
        "reference_price": _decimal(fact_values.get(reference_type)),
        "invalidation_condition": f"invalidate_if_price_crosses_{reference_type}",
        "stop_order_type": "stop_market",
        "stop_time_in_force": "GTC",
        "protection_policy_version": bundle.owner_policy_version,
        "source_fact_snapshot_id": str(bundle.action_time_fact["fact_snapshot_id"]),
        "expires_at_ms": int(bundle.action_time_fact["valid_until_ms"]),
    }


def _fresh_signal_for_candidate(
    control_state: dict[str, Any],
    *,
    candidate: dict[str, Any],
    event_spec: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    rows = []
    for row in _rows(control_state.get("live_signal_events")):
        if row.get("status") != "facts_validated":
            continue
        if row.get("freshness_state") != "fresh":
            continue
        if row.get("source_kind") != "live_market":
            continue
        if int(row.get("expires_at_ms") or 0) <= now_ms:
            continue
        if str(row.get("candidate_scope_id") or "") != str(candidate.get("candidate_scope_id") or ""):
            continue
        if str(row.get("event_spec_id") or "") != str(event_spec.get("event_spec_id") or ""):
            continue
        if _lane_key(row) != _lane_key(candidate):
            continue
        rows.append(row)
    if not rows:
        return {}
    return sorted(rows, key=lambda row: int(row.get("observed_at_ms") or 0))[-1]


def _open_real_submit_lanes(control_state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in _rows(control_state.get("action_time_lane_inputs"))
        if row.get("lane_scope") == "real_submit_candidate"
        and row.get("status") in OPEN_REAL_LANE_STATUSES
    ]


def _active_candidate_rows(control_state: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        [
            row
            for row in _rows(control_state.get("candidate_scope"))
            if row.get("status") == "active"
        ],
        key=_candidate_sort_key,
    )


def _active_by(
    control_state: dict[str, Any],
    table_key: str,
    key_name: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in _rows(control_state.get(table_key)):
        if row.get("status") != "active":
            continue
        key = str(row.get(key_name) or "")
        if key:
            result[key] = row
    return result


def _current_coverage_by_lane(control_state: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in _rows(control_state.get("watcher_runtime_coverage")):
        if row.get("is_current") is not True:
            continue
        result[_lane_key(row)] = row
    return result


def _fact_by_id(control_state: dict[str, Any], fact_snapshot_id: str) -> dict[str, Any]:
    if not fact_snapshot_id:
        return {}
    return next(
        (
            row
            for row in _rows(control_state.get("runtime_fact_snapshots"))
            if row.get("fact_snapshot_id") == fact_snapshot_id
        ),
        {},
    )


def _latest_fact(
    control_state: dict[str, Any],
    *,
    candidate: dict[str, Any],
    runtime_profile_id: str,
    fact_surface: str,
    allow_global: bool = False,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in _rows(control_state.get("runtime_fact_snapshots")):
        if row.get("fact_surface") != fact_surface:
            continue
        if not _fact_scope_matches(
            row,
            candidate=candidate,
            runtime_profile_id=runtime_profile_id,
            allow_global=allow_global,
        ):
            continue
        rows.append(row)
    if not rows:
        return {}
    return sorted(rows, key=lambda row: int(row.get("observed_at_ms") or 0))[-1]


def _fact_scope_matches(
    row: dict[str, Any],
    *,
    candidate: dict[str, Any],
    runtime_profile_id: str,
    allow_global: bool,
) -> bool:
    for key in ("strategy_group_id", "symbol", "side"):
        value = row.get(key)
        if value is None and allow_global:
            continue
        if value is not None and str(value or "") != str(candidate.get(key) or ""):
            return False
    value = row.get("runtime_profile_id")
    if value is None and allow_global:
        return True
    return str(value or "") == runtime_profile_id


def _owner_policy_version_by_id(control_state: dict[str, Any]) -> dict[str, str]:
    events = {
        str(row.get("policy_event_id") or ""): row
        for row in _rows(control_state.get("owner_policy_events"))
    }
    result: dict[str, str] = {}
    for policy in _rows(control_state.get("owner_policy_current")):
        policy_current_id = str(policy.get("policy_current_id") or "")
        for policy_event_id in _as_list(policy.get("policy_event_ids")):
            version = str(events.get(str(policy_event_id), {}).get("policy_version") or "")
            if version:
                result[policy_current_id] = version
                break
    return result


def _required_fact_blockers(
    control_state: dict[str, Any],
    *,
    event_spec_id: str,
    fact_values: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    for row in _rows(control_state.get("strategy_event_required_facts")):
        if row.get("event_spec_id") != event_spec_id:
            continue
        if row.get("status") != "current" or row.get("required_for_promotion") is not True:
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
    if isinstance(observed, str) and observed.strip().lower() in {"", "unknown", "missing"}:
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


def _assert_fact_ready(
    blockers: list[str],
    label: str,
    fact: dict[str, Any],
    *,
    now_ms: int,
) -> None:
    if not fact:
        blockers.append(f"{label}_snapshot_missing")
        return
    if fact.get("computed") is not True:
        blockers.append(f"{label}_not_computed")
    if fact.get("satisfied") is not True:
        blockers.append(f"{label}_not_satisfied")
    if fact.get("freshness_state") != "fresh":
        blockers.append(f"{label}_not_fresh")
    if int(fact.get("valid_until_ms") or 0) <= now_ms:
        blockers.append(f"{label}_expired")


def _require_identity_match(
    blockers: list[str],
    candidate: dict[str, Any],
    row: dict[str, Any],
    label: str,
    *,
    keys: tuple[str, ...] = ("strategy_group_id", "symbol", "side"),
) -> None:
    if not row:
        blockers.append(f"{label}_missing")
        return
    for key in keys:
        if key in row and str(row.get(key) or "") != str(candidate.get(key) or ""):
            blockers.append(f"{label}_mismatch:{key}")


def _select_winner(candidates: list[CandidateBundle]) -> CandidateBundle | None:
    ranked = _ranked_candidates(candidates)
    return ranked[0] if ranked else None


def _ranked_candidates(candidates: list[CandidateBundle]) -> list[CandidateBundle]:
    return sorted(candidates, key=_bundle_sort_key)


def _bundle_sort_key(bundle: CandidateBundle) -> tuple[int, int, int, str, str]:
    return (
        _strategy_priority(str(bundle.candidate.get("strategy_group_id") or "")),
        int(bundle.candidate.get("priority_rank") or 999),
        -int(bundle.signal.get("observed_at_ms") or 0),
        str(bundle.candidate.get("symbol") or ""),
        str(bundle.candidate.get("side") or ""),
    )


def _candidate_sort_key(row: dict[str, Any]) -> tuple[int, int, str, str]:
    return (
        _strategy_priority(str(row.get("strategy_group_id") or "")),
        int(row.get("priority_rank") or 999),
        str(row.get("symbol") or ""),
        str(row.get("side") or ""),
    )


def _strategy_priority(strategy_group_id: str) -> int:
    try:
        return list(WIP_LANES).index(strategy_group_id)
    except ValueError:
        return 999


def _account_id(control_state: dict[str, Any], candidate: dict[str, Any]) -> str:
    version_id = ""
    for group in _rows(control_state.get("strategy_groups")):
        if group.get("strategy_group_id") == candidate.get("strategy_group_id"):
            version_id = str(group.get("current_version_id") or "")
            break
    version = next(
        (
            row
            for row in _rows(control_state.get("strategy_group_versions"))
            if row.get("strategy_group_version_id") == version_id
        ),
        {},
    )
    return str(_as_dict(version.get("risk_envelope")).get("account_id") or "")


def _candidate_results(
    bundles: list[CandidateBundle],
    *,
    selected: CandidateBundle | None,
) -> list[dict[str, Any]]:
    selected_id = selected.promotion_candidate_id if selected else ""
    return [
        {
            "strategy_group_id": str(bundle.candidate.get("strategy_group_id") or ""),
            "symbol": str(bundle.candidate.get("symbol") or ""),
            "side": str(bundle.candidate.get("side") or ""),
            "signal_event_id": str(bundle.signal.get("signal_event_id") or ""),
            "promotion_candidate_id": bundle.promotion_candidate_id,
            "action_time_lane_input_id": bundle.action_time_lane_input_id
            if bundle.promotion_candidate_id == selected_id
            else "",
            "status": "selected"
            if bundle.promotion_candidate_id == selected_id
            else "blocked"
            if bundle.blockers
            else "arbitration_lost",
            "blockers": list(bundle.blockers),
        }
        for bundle in _ranked_candidates(bundles)
    ]


def _result(status: str, *, now_ms: int, blockers: list[str], next_action: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema": "brc.pg_promotion_action_time_lane_materialization.v1",
        "status": status,
        "generated_at_ms": now_ms,
        "blockers": blockers,
        "next_action": next_action,
        "forbidden_effects": FORBIDDEN_EFFECTS,
        "authority_boundary": (
            "pg_promotion_action_time_lane_materializer; "
            "no_finalgate_no_operation_layer_no_exchange_write"
        ),
        **extra,
    }


def _upsert_row(
    conn: sa.engine.Connection,
    table_name: str,
    pk_name: str,
    row: dict[str, Any],
) -> None:
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=conn)
    pk = table.c[pk_name]
    existing = conn.execute(
        sa.select(pk).where(pk == row[pk_name]).limit(1)
    ).scalar_one_or_none()
    if existing is None:
        conn.execute(table.insert().values(**row))
    else:
        conn.execute(table.update().where(pk == row[pk_name]).values(**row))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _lane_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("strategy_group_id") or ""),
        str(row.get("symbol") or ""),
        str(row.get("side") or ""),
    )


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    readable = ":".join(_safe_id_part(part) for part in parts if part)[:120]
    return f"{prefix}:{readable}:{digest}" if readable else f"{prefix}:{digest}"


def _safe_id_part(value: str) -> str:
    return (
        str(value)
        .replace("/", "_")
        .replace(":", "_")
        .replace(" ", "_")
        .replace("\\", "_")
    )


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("-1")


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "")
        if text and text not in result:
            result.append(text)
    return result


def _rows(value: Any) -> list[dict[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, dict)]


def _as_list(value: Any) -> list[Any]:
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


if __name__ == "__main__":
    raise SystemExit(main())
