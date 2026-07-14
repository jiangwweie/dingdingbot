#!/usr/bin/env python3
"""Build the PG-backed fresh-signal to action-time boundary view.

The artifact produced by this script is an export/diagnostic view. Production
runtime authority comes from PG control-state tables only.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Iterable

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import (  # noqa: E402
    non_executing_interaction,
    non_executing_safety_invariants,
)
from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
)


SCHEMA = "brc.strategy_fresh_signal_action_time_boundary.v1"
OPEN_REAL_LANE_STATUSES = {
    "opened",
    "facts_refreshing",
    "ticket_pending",
    "ticket_created",
}
ACTIVE_PROMOTION_STATUSES = {
    "eligible",
    "arbitration_pending",
    "arbitration_won",
}
ACTION_TIME_READY_BLOCKERS = {
    "market_wait_validated",
    "action_time_preflight_ready",
}
PG_SOURCE_TABLES = (
    "brc_live_signal_events",
    "brc_runtime_fact_snapshots",
    "brc_promotion_candidates",
    "brc_action_time_lane_inputs",
    "brc_action_time_tickets",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite/non-PG DSNs only in tests.",
    )
    parser.add_argument("--now-ms", type=int, default=None)
    args = parser.parse_args(argv)

    if args.require_database_url and not args.database_url:
        print(
            "ERROR: PG_DATABASE_URL is required for PG-backed action-time boundary",
            file=sys.stderr,
        )
        return 2
    if not args.database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if not args.database_url.startswith(
        ("postgresql://", "postgresql+psycopg://")
    ) and not args.allow_non_postgres_for_test:
        print(
            "ERROR: PG-backed action-time boundary requires PostgreSQL DSN",
            file=sys.stderr,
        )
        return 2

    engine = sa.create_engine(args.database_url)
    try:
        with engine.connect() as conn:
            repository = PgBackedRuntimeControlStateRepository(conn)
            artifact = build_strategy_fresh_signal_action_time_boundary(
                control_state=repository.read_control_state(),
                now_ms=args.now_ms,
            )
    except RuntimeControlStateRepositoryError as exc:
        print(f"ERROR: PG runtime control-state invalid: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    print(
        json.dumps(
            {
                "status": artifact["status"],
                "fresh_signal_present_count": artifact["summary"][
                    "fresh_signal_present_count"
                ],
                "would_enter_finalgate_if_private_facts_ready_count": artifact[
                    "summary"
                ]["would_enter_finalgate_if_private_facts_ready_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def build_strategy_fresh_signal_action_time_boundary(
    *,
    control_state: dict[str, Any],
    generated_at_utc: str | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Project PG current state into a non-authority action-time boundary view."""

    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    current_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    rows = [
        _row_from_lane_key(control_state, lane_key=lane_key, now_ms=current_ms)
        for lane_key in _lane_keys(control_state)
    ]
    return {
        "schema": SCHEMA,
        "scope": "fresh_signal_action_time_boundary_non_authority",
        "status": "strategy_fresh_signal_action_time_boundary_ready",
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "source_tables": list(PG_SOURCE_TABLES),
        "generated_at_utc": generated,
        "strategy_rows": rows,
        "summary": {
            "strategy_count": len(rows),
            "fresh_signal_present_count": sum(
                row["fresh_signal_present"] is True for row in rows
            ),
            "would_enter_finalgate_if_private_facts_ready_count": sum(
                row["would_enter_finalgate_if_private_facts_ready"] is True
                for row in rows
            ),
            "action_time_lane_input_count": sum(
                bool(row.get("action_time_lane_input_id")) for row in rows
            ),
            "live_submit_allowed_count": 0,
        },
        "checks": {
            "pg_source_required": True,
            "legacy_strategy_json_inputs_allowed": False,
            "required_facts_readiness_projected": True,
            "public_facts_refresh_projected": True,
            "private_action_time_facts_pending": any(
                row["fresh_signal_present"] is True
                and row["required_facts_readiness"][
                    "private_action_time_facts_ready"
                ]
                is not True
                for row in rows
            ),
            "candidate_evidence_shape_projected": True,
            "action_time_lane_projected": True,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "order_created": False,
            "live_submit_allowed": False,
        },
        "control_state_watermark": {
            "schema": str(control_state.get("schema") or ""),
            "source_mode": str(control_state.get("source_mode") or ""),
            "projection_target": str(control_state.get("projection_target") or ""),
            "table_counts": _as_dict(control_state.get("table_counts")),
        },
        "interaction": non_executing_interaction(
            "L4_pg_strategy_fresh_signal_action_time_boundary"
        ),
        "safety_invariants": non_executing_safety_invariants(
            tuple(), include_authority_mirrors=False
        ),
    }


def _row_from_lane_key(
    control_state: dict[str, Any],
    *,
    lane_key: tuple[str, str, str],
    now_ms: int,
) -> dict[str, Any]:
    readiness = _latest_by_key(
        control_state.get("pretrade_readiness_rows"),
        lane_key=lane_key,
        time_key="computed_at_ms",
    )
    signal = _latest_fresh_signal(control_state, lane_key=lane_key, now_ms=now_ms)
    promotion = _latest_promotion(control_state, lane_key=lane_key, now_ms=now_ms)
    lane = _latest_action_time_lane(control_state, lane_key=lane_key, now_ms=now_ms)
    public_fact = _public_fact(control_state, readiness=readiness, signal=signal, lane=lane)
    action_time_fact = _action_time_fact(control_state, lane_key=lane_key, lane=lane)
    account_safe_fact = _global_fact(control_state, fact_surface="account_safe")
    account_mode_fact = _global_fact(control_state, fact_surface="account_mode")
    strategy_group_id, symbol, side = lane_key

    fresh = bool(signal)
    action_time_lane_open = bool(lane)
    promotion_active = bool(promotion)
    public_ready = _fact_ready(public_fact, now_ms=now_ms) or (
        not fresh
        and not lane
        and not promotion
        and _readiness_public_ready(readiness, now_ms=now_ms)
    )
    action_time_fact_ready = _fact_ready(action_time_fact, now_ms=now_ms)
    account_safe_ready = _fact_ready(account_safe_fact, now_ms=now_ms)
    account_mode_ready = _fact_ready(account_mode_fact, now_ms=now_ms)
    private_ready = action_time_fact_ready and account_safe_ready and account_mode_ready
    account_values = _as_dict(account_safe_fact.get("fact_values"))
    active_clear = account_values.get("active_position_or_open_order_clear") is True
    balance_ready = (
        account_values.get("action_time_available_balance") is True
        or account_values.get("available_balance_ready") is True
        or account_values.get("account_safe") is True
    )
    candidate_shape = action_time_lane_open or promotion_active
    first_blocker = _first_blocker(
        readiness=readiness,
        promotion=promotion,
        lane=lane,
        signal=signal,
        public_ready=public_ready,
        private_ready=private_ready,
    )
    path_ready = (
        public_ready
        and first_blocker in ACTION_TIME_READY_BLOCKERS
        and (
            action_time_lane_open
            or promotion_active
            or str(readiness.get("readiness_state") or "")
            in {"market_wait_validated", "action_time_lane"}
        )
    )
    would_enter = fresh and candidate_shape and path_ready

    return _row(
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
        path_id=_path_id(readiness=readiness, signal=signal, lane=lane),
        fresh_signal_present=fresh,
        current_signal_state=_signal_state(signal=signal, readiness=readiness),
        public_facts_ready=public_ready,
        private_action_time_facts_ready=private_ready,
        active_position_or_open_order_clear=active_clear,
        action_time_available_balance=balance_ready,
        candidate_evidence_shape_ready=candidate_shape,
        dry_run_submit_rehearsal_ready=path_ready,
        would_enter_finalgate_if_private_facts_ready=would_enter,
        first_blocker=first_blocker,
        blocker_owner=_blocker_owner(first_blocker),
        signal_event_id=str(signal.get("signal_event_id") or ""),
        promotion_candidate_id=str(promotion.get("promotion_candidate_id") or ""),
        action_time_lane_input_id=str(lane.get("action_time_lane_input_id") or ""),
        runtime_profile_id=str(
            lane.get("runtime_profile_id")
            or readiness.get("runtime_profile_id")
            or ""
        ),
        source_refs=_source_refs(
            readiness=readiness,
            signal=signal,
            promotion=promotion,
            lane=lane,
            public_fact=public_fact,
            action_time_fact=action_time_fact,
            account_safe_fact=account_safe_fact,
            account_mode_fact=account_mode_fact,
        ),
    )


def _row(
    *,
    strategy_group_id: str,
    symbol: str,
    side: str,
    path_id: str,
    fresh_signal_present: bool,
    current_signal_state: str,
    public_facts_ready: bool,
    private_action_time_facts_ready: bool,
    active_position_or_open_order_clear: bool,
    action_time_available_balance: bool,
    candidate_evidence_shape_ready: bool,
    dry_run_submit_rehearsal_ready: bool,
    would_enter_finalgate_if_private_facts_ready: bool,
    first_blocker: str,
    blocker_owner: str,
    signal_event_id: str,
    promotion_candidate_id: str,
    action_time_lane_input_id: str,
    runtime_profile_id: str,
    source_refs: dict[str, str],
) -> dict[str, Any]:
    return {
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "side": side,
        "path_id": path_id,
        "signal_event_id": signal_event_id,
        "promotion_candidate_id": promotion_candidate_id,
        "action_time_lane_input_id": action_time_lane_input_id,
        "runtime_profile_id": runtime_profile_id,
        "fresh_signal_present": fresh_signal_present,
        "current_signal_state": current_signal_state,
        "required_facts_readiness": {
            "public_facts_ready": public_facts_ready,
            "private_action_time_facts_ready": private_action_time_facts_ready,
            "active_position_or_open_order_clear": (
                active_position_or_open_order_clear
            ),
            "action_time_available_balance": action_time_available_balance,
            "private_action_time_fact_keys_pending": []
            if private_action_time_facts_ready
            else [
                "action_time_fact_snapshot",
                "account_safe_fact_snapshot",
                "account_mode_fact_snapshot",
            ],
        },
        "candidate_evidence_shape_ready": candidate_evidence_shape_ready,
        "dry_run_submit_rehearsal_ready": dry_run_submit_rehearsal_ready,
        "action_time_path_ready": dry_run_submit_rehearsal_ready,
        "would_enter_finalgate_if_private_facts_ready": (
            would_enter_finalgate_if_private_facts_ready
        ),
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
        "order_created": False,
        "live_submit_allowed": False,
        "first_blocker": first_blocker,
        "blocker_owner": blocker_owner,
        "source_refs": source_refs,
        "next_action": _next_action(
            first_blocker=first_blocker,
            fresh_signal_present=fresh_signal_present,
            action_time_lane_input_id=action_time_lane_input_id,
        ),
        "post_action_expected_state": (
            "action_time_ticket_materialization_ready"
            if action_time_lane_input_id
            else "action_time_lane_materialization_ready"
            if would_enter_finalgate_if_private_facts_ready
            else "remain_non_authority_until_required_facts_close"
        ),
    }


def _lane_keys(control_state: dict[str, Any]) -> list[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for table_key in (
        "pretrade_readiness_rows",
        "live_signal_events",
        "promotion_candidates",
        "action_time_lane_inputs",
        "action_time_tickets",
    ):
        for row in _rows(control_state.get(table_key)):
            key = _lane_key(row)
            if all(key):
                keys.add(key)
    return sorted(keys, key=lambda key: (key[0], key[1], key[2]))


def _first_blocker(
    *,
    readiness: dict[str, Any],
    promotion: dict[str, Any],
    lane: dict[str, Any],
    signal: dict[str, Any],
    public_ready: bool,
    private_ready: bool,
) -> str:
    if not public_ready:
        return "watcher_tick_missing"
    lane_blocker = str(lane.get("first_blocker_class") or "")
    if lane_blocker:
        return lane_blocker
    blockers = _string_list(promotion.get("blockers"))
    if blockers:
        return blockers[0]
    readiness_blocker = str(readiness.get("first_blocker_class") or "")
    if readiness_blocker:
        return readiness_blocker
    if signal and not lane:
        return (
            "action_time_preflight_ready"
            if private_ready
            else "action_time_boundary_not_reproduced"
        )
    return "market_wait_validated"


def _latest_fresh_signal(
    control_state: dict[str, Any],
    *,
    lane_key: tuple[str, str, str],
    now_ms: int,
) -> dict[str, Any]:
    rows = []
    for row in _rows(control_state.get("live_signal_events")):
        if _lane_key(row) != lane_key:
            continue
        if row.get("source_kind") != "live_market":
            continue
        if row.get("status") != "facts_validated":
            continue
        if row.get("freshness_state") != "fresh":
            continue
        if int(row.get("expires_at_ms") or 0) <= now_ms:
            continue
        rows.append(row)
    return _latest(rows, time_key="observed_at_ms")


def _latest_promotion(
    control_state: dict[str, Any],
    *,
    lane_key: tuple[str, str, str],
    now_ms: int,
) -> dict[str, Any]:
    rows = []
    for row in _rows(control_state.get("promotion_candidates")):
        if _lane_key(row) != lane_key:
            continue
        if row.get("status") not in ACTIVE_PROMOTION_STATUSES:
            continue
        if int(row.get("expires_at_ms") or 0) <= now_ms:
            continue
        rows.append(row)
    return _latest(rows, time_key="created_at_ms")


def _latest_action_time_lane(
    control_state: dict[str, Any],
    *,
    lane_key: tuple[str, str, str],
    now_ms: int,
) -> dict[str, Any]:
    rows = []
    for row in _rows(control_state.get("action_time_lane_inputs")):
        if _lane_key(row) != lane_key:
            continue
        if row.get("lane_scope") != "real_submit_candidate":
            continue
        if row.get("status") not in OPEN_REAL_LANE_STATUSES:
            continue
        if int(row.get("expires_at_ms") or 0) <= now_ms:
            continue
        rows.append(row)
    return _latest(rows, time_key="created_at_ms")


def _public_fact(
    control_state: dict[str, Any],
    *,
    readiness: dict[str, Any],
    signal: dict[str, Any],
    lane: dict[str, Any],
) -> dict[str, Any]:
    for fact_id in (
        lane.get("public_fact_snapshot_id"),
        signal.get("fact_snapshot_id"),
        readiness.get("facts_snapshot_id"),
        readiness.get("fact_snapshot_id"),
    ):
        fact = _fact_by_id(control_state, str(fact_id or ""))
        if fact:
            return fact
    return {}


def _action_time_fact(
    control_state: dict[str, Any],
    *,
    lane_key: tuple[str, str, str],
    lane: dict[str, Any],
) -> dict[str, Any]:
    fact = _fact_by_id(control_state, str(lane.get("action_time_fact_snapshot_id") or ""))
    if fact:
        return fact
    return _latest_fact(control_state, lane_key=lane_key, fact_surface="action_time")


def _global_fact(control_state: dict[str, Any], *, fact_surface: str) -> dict[str, Any]:
    rows = [
        row
        for row in _rows(control_state.get("runtime_fact_snapshots"))
        if row.get("fact_surface") == fact_surface
        and not row.get("strategy_group_id")
        and not row.get("symbol")
        and not row.get("side")
    ]
    return _latest(rows, time_key="observed_at_ms")


def _latest_fact(
    control_state: dict[str, Any],
    *,
    lane_key: tuple[str, str, str],
    fact_surface: str,
) -> dict[str, Any]:
    rows = [
        row
        for row in _rows(control_state.get("runtime_fact_snapshots"))
        if row.get("fact_surface") == fact_surface and _lane_key(row) == lane_key
    ]
    return _latest(rows, time_key="observed_at_ms")


def _fact_by_id(control_state: dict[str, Any], fact_snapshot_id: str) -> dict[str, Any]:
    if not fact_snapshot_id:
        return {}
    for row in _rows(control_state.get("runtime_fact_snapshots")):
        if str(row.get("fact_snapshot_id") or "") == fact_snapshot_id:
            return row
    return {}


def _fact_ready(row: dict[str, Any], *, now_ms: int) -> bool:
    if not row:
        return False
    return (
        row.get("computed") is True
        and row.get("satisfied") is True
        and row.get("freshness_state") == "fresh"
        and int(row.get("valid_until_ms") or 0) > now_ms
    )


def _readiness_public_ready(readiness: dict[str, Any], *, now_ms: int) -> bool:
    if readiness.get("public_facts_state") != "satisfied":
        return False
    valid_until = readiness.get("valid_until_ms")
    return valid_until is None or int(valid_until or 0) > now_ms


def _latest_by_key(
    value: object,
    *,
    lane_key: tuple[str, str, str],
    time_key: str,
) -> dict[str, Any]:
    rows = [row for row in _rows(value) if _lane_key(row) == lane_key]
    return _latest(rows, time_key=time_key)


def _latest(rows: Iterable[dict[str, Any]], *, time_key: str) -> dict[str, Any]:
    materialized = list(rows)
    if not materialized:
        return {}
    return sorted(materialized, key=lambda row: int(row.get(time_key) or 0))[-1]


def _path_id(
    *,
    readiness: dict[str, Any],
    signal: dict[str, Any],
    lane: dict[str, Any],
) -> str:
    for value in (
        lane.get("candidate_authorization_ref"),
        signal.get("detector_key"),
        readiness.get("readiness_row_id"),
    ):
        text = str(value or "")
        if text:
            return text
    return "PG-ACTION-TIME-BOUNDARY"


def _signal_state(*, signal: dict[str, Any], readiness: dict[str, Any]) -> str:
    if signal:
        return "fresh_signal_present"
    lifecycle = str(readiness.get("signal_lifecycle_status") or "")
    freshness = str(readiness.get("signal_freshness_state") or "")
    if lifecycle and freshness:
        return f"{lifecycle}:{freshness}"
    if lifecycle:
        return lifecycle
    return "fresh_signal_absent"


def _blocker_owner(blocker: str) -> str:
    if blocker in {"computed_not_satisfied", "market_wait_validated"}:
        return "market"
    if blocker == "policy_scope_missing" or blocker.startswith("owner_policy_"):
        return "owner"
    if blocker in {"hard_safety_stop", "active_position_resolution"}:
        return "safety"
    return "runtime"


def _next_action(
    *,
    first_blocker: str,
    fresh_signal_present: bool,
    action_time_lane_input_id: str,
) -> str:
    if action_time_lane_input_id:
        return "materialize_or_refresh_action_time_ticket"
    if first_blocker == "watcher_tick_missing":
        return "refresh_or_repair_watcher_public_fact_input"
    if first_blocker == "computed_not_satisfied":
        return "continue_observation_until_required_facts_satisfy"
    if first_blocker == "market_wait_validated" and not fresh_signal_present:
        return "continue_watcher_observation_until_fresh_signal"
    if first_blocker == "action_time_preflight_ready":
        return "materialize_pg_promotion_action_time_lane"
    if fresh_signal_present:
        return "repair_or_materialize_pg_action_time_lane"
    return "repair_first_non_market_blocker"


def _source_refs(
    *,
    readiness: dict[str, Any],
    signal: dict[str, Any],
    promotion: dict[str, Any],
    lane: dict[str, Any],
    public_fact: dict[str, Any],
    action_time_fact: dict[str, Any],
    account_safe_fact: dict[str, Any],
    account_mode_fact: dict[str, Any],
) -> dict[str, str]:
    return {
        "readiness_row_id": str(readiness.get("readiness_row_id") or ""),
        "signal_event_id": str(signal.get("signal_event_id") or ""),
        "promotion_candidate_id": str(promotion.get("promotion_candidate_id") or ""),
        "action_time_lane_input_id": str(lane.get("action_time_lane_input_id") or ""),
        "public_fact_snapshot_id": str(public_fact.get("fact_snapshot_id") or ""),
        "action_time_fact_snapshot_id": str(
            action_time_fact.get("fact_snapshot_id") or ""
        ),
        "account_safe_fact_snapshot_id": str(
            account_safe_fact.get("fact_snapshot_id") or ""
        ),
        "account_mode_fact_snapshot_id": str(
            account_mode_fact.get("fact_snapshot_id") or ""
        ),
    }


def _lane_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("strategy_group_id") or ""),
        str(row.get("symbol") or ""),
        str(row.get("side") or ""),
    )


def _rows(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item)]
    return []


if __name__ == "__main__":
    raise SystemExit(main())
