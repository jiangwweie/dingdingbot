#!/usr/bin/env python3
"""Build the five StrategyGroup live-candidate pool PG-backed export."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
    is_current_action_time_lane,
    is_current_fact_snapshot,
    is_current_live_signal,
    is_current_pretrade_readiness,
    is_current_watcher_coverage,
)

from src.infrastructure.sync_pg_dsn import (  # noqa: E402
    is_sync_postgres_dsn,
    normalize_sync_postgres_dsn,
)

from src.application.readmodels.daily_live_enablement_table import (  # noqa: E402
    AUTHORITY_BOUNDARY as DAILY_AUTHORITY_BOUNDARY,
    CONTRACT_BLOCKER_CLASSES,
    WIP_LANES,
)
from src.application.action_time.process_outcome_relevance import (  # noqa: E402
    process_outcome_has_current_blocking_authority,
)
from src.application.action_time.capability_certification import (  # noqa: E402
    ActionTimeCapabilityTruth,
    current_action_time_capability_truth_by_lane,
    current_runtime_head,
)


SCHEMA = "brc.strategy_live_candidate_pool.v1"
OWNER_AUTHORIZATION_SCHEMA = "brc.owner_pretrade_runtime_authorization.v0"
AUTHORITY_BOUNDARY = (
    "live_candidate_pool_is_read_model; "
    "no_finalgate_no_operation_layer_no_exchange_write_no_live_profile_or_sizing_change"
)
EVENT_EXECUTION_CAPABILITY_NOT_CERTIFIED = (
    "event_execution_capability_not_certified"
)
CANDIDATE_POSITIONING = {
    "MPG-001": "selective leader continuation long candidate",
    "CPM-RO-001": "reclaim / pullback recovery long candidate",
    "MI-001": "relative strength / cross-asset candidate",
    "SOR-001": "session / flow confirmation candidate",
    "BRF2-001": "conditional failed-rebound short candidate",
}
PLACEHOLDER_SYMBOLS = {
    "strategy_scope",
    "brf2_research_supported_symbols_only",
}
PRIMARY_SYMBOLS = {
    "CPM-RO-001": "ETHUSDT",
    "MPG-001": "OPUSDT",
    "MI-001": "AVAXUSDT",
    "SOR-001": "ETHUSDT",
    "BRF2-001": "BTCUSDT",
}
FRESH_SIGNAL_TIMESTAMP_KEYS = (
    "event_time_utc",
    "fresh_signal_time_utc",
    "latest_candle_close_time_utc",
)
RESIDUAL_DEPLOY_BLOCKERS = {
    "artifact_missing",
    "schema_invalid",
    "detector_not_attached",
    "watcher_tick_missing",
    "scope_not_attached",
    "replay_live_rule_mismatch",
    EVENT_EXECUTION_CAPABILITY_NOT_CERTIFIED,
    "action_time_boundary_not_reproduced",
    "action_time_preflight_ready",
    "policy_scope_missing",
    "runtime_profile_scope_missing",
    "active_position_resolution",
    "hard_safety_stop",
}
ACTION_TIME_BLOCKED_STATUSES = {
    "blocked_public_facts",
    "blocked_action_time_rehearsal",
}
ACTION_TIME_SCOPE_STATES = {
    "live_submit_allowed",
    "conditional_action_time_rehearsal_allowed",
}
ACTION_TIME_INPUT_BLOCKERS = {
    EVENT_EXECUTION_CAPABILITY_NOT_CERTIFIED,
    "action_time_boundary_not_reproduced",
    "active_position_resolution",
    "artifact_missing",
    "detector_not_attached",
    "watcher_tick_missing",
    "scope_not_attached",
    "policy_scope_missing",
    "runtime_profile_scope_missing",
    "hard_safety_stop",
    "replay_live_rule_mismatch",
}
ACTION_TIME_CURRENT_ONLY_BLOCKERS = {
    "action_time_boundary_not_reproduced",
    "action_time_preflight_ready",
    "private_action_time_facts_required",
}
P0_P1_ITEMS = (
    ("P0", "five_strategy_candidate_pool_control_surface"),
    ("P0", "mpg_watcher_closure"),
    ("P0", "sor_watcher_closure"),
    ("P0", "mi_scope_closure"),
    ("P0", "cpm_computed_refresh"),
    ("P0", "brf2_conditionalization"),
    ("P0", "no_authority_leakage"),
    ("P1", "candidate_pool_validator"),
    ("P1", "output_whitelist_gate"),
    ("P1", "no_stale_facts"),
    ("P1", "review_report"),
    ("P1", "postdeploy_validation_script"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("PG_DATABASE_URL", ""),
        help=(
            "PostgreSQL DSN for the DB-backed production current source. "
            "Defaults to PG_DATABASE_URL."
        ),
    )
    parser.add_argument(
        "--require-database-url",
        action="store_true",
        help="Require an explicit database URL; retained for command consistency.",
    )
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite/non-PG DSNs only in tests.",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print(
            "ERROR: PG_DATABASE_URL is required for DB-backed candidate pool",
            file=sys.stderr,
        )
        return 2

    database_url = normalize_sync_postgres_dsn(args.database_url)
    if not is_sync_postgres_dsn(database_url) and not args.allow_non_postgres_for_test:
        print(
            "ERROR: DB-backed candidate pool requires PostgreSQL DSN",
            file=sys.stderr,
        )
        return 2
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            repository = PgBackedRuntimeControlStateRepository(conn)
            artifact = build_strategy_live_candidate_pool_from_control_state(
                repository.read_monitor_control_state(),
            )
    finally:
        engine.dispose()
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "candidate_count": artifact["summary"]["candidate_count"],
                "p0_cleared": artifact["summary"]["p0_cleared"],
                "p1_cleared_or_waived": artifact["summary"][
                    "p1_cleared_or_waived"
                ],
                "deploy_ready": artifact["summary"]["deploy_ready"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def build_strategy_live_candidate_pool_from_control_state(
    control_state: dict[str, Any],
    *,
    generated_at_utc: str | None = None,
    suppress_persistent_action_time_outcomes: bool = False,
) -> dict[str, Any]:
    """Build Candidate Pool from DB-backed runtime control state.

    This is the production-current read path. It converts PG current rows into
    the builder's internal projection inputs and does not call FinalGate,
    Operation Layer, or exchange-write surfaces.
    """

    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    inputs = _candidate_pool_inputs_from_control_state(
        control_state,
        generated_at_utc=generated,
        suppress_persistent_action_time_outcomes=(
            suppress_persistent_action_time_outcomes
        ),
    )
    artifact = build_strategy_live_candidate_pool(
        daily_table=inputs["daily_table"],
        tradeability=inputs["tradeability"],
        replay_live_parity=inputs["replay_live_parity"],
        action_time_boundary=inputs["action_time_boundary"],
        single_lane_task_packet=inputs["single_lane_task_packet"],
        runtime_active_monitor=inputs["runtime_active_monitor"],
        owner_pretrade_authorization=inputs["owner_pretrade_authorization"],
        generated_at_utc=generated,
    )
    artifact["source_mode"] = "db_backed"
    artifact["projection_target"] = "production_current"
    artifact["control_state_watermark"] = {
        "schema": str(control_state.get("schema") or ""),
        "table_counts": _as_dict(control_state.get("table_counts")),
    }
    artifact["source_validation"] = {
        **_as_dict(artifact.get("source_validation")),
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "legacy_file_authority": False,
    }
    return artifact


def build_strategy_live_candidate_pool_inputs_from_control_state(
    control_state: dict[str, Any],
    *,
    generated_at_utc: str | None = None,
    suppress_persistent_action_time_outcomes: bool = False,
) -> dict[str, dict[str, Any]]:
    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    return _candidate_pool_inputs_from_control_state(
        control_state,
        generated_at_utc=generated,
        suppress_persistent_action_time_outcomes=(
            suppress_persistent_action_time_outcomes
        ),
    )


def _candidate_pool_inputs_from_control_state(
    control_state: dict[str, Any],
    *,
    generated_at_utc: str,
    suppress_persistent_action_time_outcomes: bool = False,
) -> dict[str, dict[str, Any]]:
    if control_state.get("source_mode") != "db_backed":
        raise ValueError("Candidate Pool production path requires DB-backed state")
    candidate_rows = _active_candidate_scope_rows(control_state)
    if not candidate_rows:
        raise ValueError("PG control state has no active candidate scope rows")
    invalid_candidate_ids = [
        str(row.get("candidate_scope_id") or "missing")
        for row in candidate_rows
        if not str(row.get("exchange_instrument_id") or "").strip()
        or not str(row.get("timeframe") or "").strip()
    ]
    if invalid_candidate_ids:
        raise ValueError(
            "PG control state has schema-invalid exact candidate identity: "
            + ", ".join(sorted(invalid_candidate_ids))
        )
    missing_strategy_groups = set(WIP_LANES) - {
        str(row.get("strategy_group_id") or "") for row in candidate_rows
    }
    if missing_strategy_groups:
        raise ValueError(
            "PG control state missing active candidate scope for: "
            + ", ".join(sorted(missing_strategy_groups))
        )
    extra_strategy_groups = {
        str(row.get("strategy_group_id") or "")
        for row in candidate_rows
        if str(row.get("strategy_group_id") or "") not in set(WIP_LANES)
    }
    if extra_strategy_groups:
        raise ValueError(
            "PG control state has active candidate scope outside WIP replacement audit: "
            + ", ".join(sorted(extra_strategy_groups))
        )

    event_by_id = {
        str(row.get("event_spec_id") or ""): row
        for row in _dict_rows(control_state.get("strategy_side_event_specs"))
        if row.get("status") == "current"
    }
    extra_event_strategy_groups = {
        str(row.get("strategy_group_id") or "")
        for row in event_by_id.values()
        if str(row.get("strategy_group_id") or "") not in set(WIP_LANES)
    }
    if extra_event_strategy_groups:
        raise ValueError(
            "PG control state has current event spec outside WIP replacement audit: "
            + ", ".join(sorted(extra_event_strategy_groups))
        )
    binding_by_candidate = _active_scope_event_binding_by_candidate(control_state)
    event_spec_by_candidate = {
        candidate_scope_id: event_by_id.get(
            str(binding.get("event_spec_id") or ""),
            {},
        )
        for candidate_scope_id, binding in binding_by_candidate.items()
    }
    runtime_by_candidate = _active_runtime_scope_by_candidate(control_state)
    policy_by_id = {
        str(row.get("policy_current_id") or ""): row
        for row in _dict_rows(control_state.get("owner_policy_current"))
    }
    strategy_groups = _strategy_group_rows(control_state)
    readiness_by_lane = _current_pretrade_readiness_by_lane(
        control_state,
        suppress_persistent_action_time_outcomes=(
            suppress_persistent_action_time_outcomes
        ),
    )
    public_fact_by_lane = _current_fact_snapshot_by_lane(
        control_state,
        fact_surface="pretrade_public",
    )
    fact_by_lane = _current_fact_snapshot_by_lane(
        control_state,
        fact_surface="pretrade_strategy",
    )
    action_time_fact_by_lane = _current_fact_snapshot_by_lane(
        control_state,
        fact_surface="action_time",
    )
    account_safe_fact = _current_global_fact_snapshot(
        control_state,
        fact_surface="account_safe",
    )
    account_safe_fact_by_lane = _current_fact_snapshot_by_lane(
        control_state,
        fact_surface="account_safe",
    )
    signal_by_lane = _fresh_signal_by_lane(control_state)
    action_lane_by_lane = _open_action_time_lane_by_lane(control_state)
    coverage_by_lane = _current_watcher_coverage_by_lane(control_state)
    for row in candidate_rows:
        candidate_scope_id = str(row.get("candidate_scope_id") or "")
        if not candidate_scope_id:
            raise ValueError("PG candidate scope row missing candidate_scope_id")
        policy_current_id = str(row.get("policy_current_id") or "")
        if not policy_current_id:
            raise ValueError(f"{candidate_scope_id} missing PG owner policy ref")
        if candidate_scope_id not in binding_by_candidate:
            raise ValueError(f"{candidate_scope_id} has no active PG event binding")
        if candidate_scope_id not in runtime_by_candidate:
            raise ValueError(f"{candidate_scope_id} has no active PG runtime scope")
        if policy_current_id not in policy_by_id:
            raise ValueError(f"{candidate_scope_id} has no PG owner policy")
        _require_pg_policy_runtime_scope(
            candidate=row,
            runtime_scope=runtime_by_candidate[candidate_scope_id],
            policy=policy_by_id[policy_current_id],
        )

    capability_truth_by_lane = current_action_time_capability_truth_by_lane(
        control_state,
        current_runtime_head=current_runtime_head(control_state),
    )
    _apply_action_time_capability_truth(
        readiness_by_lane,
        capability_truth_by_lane=capability_truth_by_lane,
        fact_by_lane=fact_by_lane,
    )

    return {
        "daily_table": _pg_daily_table_projection(
            generated_at_utc=generated_at_utc,
            candidate_rows=candidate_rows,
            strategy_groups=strategy_groups,
            readiness_by_lane=readiness_by_lane,
            fact_by_lane=fact_by_lane,
            binding_by_candidate=binding_by_candidate,
            runtime_by_candidate=runtime_by_candidate,
            signal_by_lane=signal_by_lane,
            event_spec_by_candidate=event_spec_by_candidate,
        ),
        "tradeability": _pg_tradeability_projection(
            candidate_rows=candidate_rows,
            strategy_groups=strategy_groups,
            policy_by_id=policy_by_id,
            runtime_by_candidate=runtime_by_candidate,
            readiness_by_lane=readiness_by_lane,
            fact_by_lane=fact_by_lane,
            signal_by_lane=signal_by_lane,
            event_spec_by_candidate=event_spec_by_candidate,
        ),
        "replay_live_parity": _pg_replay_live_parity_projection(
            candidate_rows=candidate_rows,
            readiness_by_lane=readiness_by_lane,
            fact_by_lane=fact_by_lane,
            signal_by_lane=signal_by_lane,
            event_spec_by_candidate=event_spec_by_candidate,
        ),
        "action_time_boundary": _pg_action_time_boundary_projection(
            generated_at_utc=generated_at_utc,
            now_ms=_control_state_now_ms(control_state),
            candidate_rows=candidate_rows,
            binding_by_candidate=binding_by_candidate,
            event_by_id=event_by_id,
            readiness_by_lane=readiness_by_lane,
            public_fact_by_lane=public_fact_by_lane,
            action_time_fact_by_lane=action_time_fact_by_lane,
            account_safe_fact=account_safe_fact,
            account_safe_fact_by_lane=account_safe_fact_by_lane,
            signal_by_lane=signal_by_lane,
            action_lane_by_lane=action_lane_by_lane,
            capability_truth_by_lane=capability_truth_by_lane,
        ),
        "single_lane_task_packet": _pg_single_lane_packet_projection(
            action_lane_by_lane=action_lane_by_lane,
        ),
        "runtime_active_monitor": _pg_runtime_active_monitor_projection(
            candidate_rows=candidate_rows,
            runtime_by_candidate=runtime_by_candidate,
            policy_by_id=policy_by_id,
            coverage_by_lane=coverage_by_lane,
        ),
        "owner_pretrade_authorization": _pg_owner_pretrade_authorization_projection(
            candidate_rows=candidate_rows,
            runtime_by_candidate=runtime_by_candidate,
            policy_by_id=policy_by_id,
        ),
    }


def _active_candidate_scope_rows(control_state: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        [
            row
            for row in _dict_rows(control_state.get("candidate_scope"))
            if row.get("status") == "active"
        ],
        key=lambda row: (
            _strategy_priority(str(row.get("strategy_group_id") or "")),
            int(row.get("priority_rank") or 999),
            str(row.get("symbol") or ""),
            str(row.get("side") or ""),
        ),
    )


def _strategy_group_rows(control_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("strategy_group_id") or ""): row
        for row in _dict_rows(control_state.get("strategy_groups"))
        if row.get("status") == "active"
    }


def _active_scope_event_binding_by_candidate(
    control_state: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    bindings: dict[str, dict[str, Any]] = {}
    for row in _dict_rows(control_state.get("candidate_scope_event_bindings")):
        if row.get("status") != "active":
            continue
        candidate_scope_id = str(row.get("candidate_scope_id") or "")
        if candidate_scope_id in bindings:
            raise ValueError(f"multiple active event bindings for {candidate_scope_id}")
        bindings[candidate_scope_id] = row
    return bindings


def _active_runtime_scope_by_candidate(
    control_state: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    bindings: dict[str, dict[str, Any]] = {}
    for row in _dict_rows(control_state.get("runtime_scope_bindings")):
        if row.get("status") != "active":
            continue
        candidate_scope_id = str(row.get("candidate_scope_id") or "")
        if candidate_scope_id in bindings:
            raise ValueError(f"multiple active runtime scope bindings for {candidate_scope_id}")
        bindings[candidate_scope_id] = row
    return bindings


def _positive_decimal(value: Any) -> bool:
    try:
        return Decimal(str(value)) > 0
    except Exception:
        return False


def _require_pg_policy_runtime_scope(
    *,
    candidate: dict[str, Any],
    runtime_scope: dict[str, Any],
    policy: dict[str, Any],
) -> None:
    candidate_scope_id = str(candidate.get("candidate_scope_id") or "unknown_candidate")
    for key in ("strategy_group_id", "symbol", "side", "policy_current_id"):
        if str(runtime_scope.get(key) or "") != str(candidate.get(key) or ""):
            raise ValueError(f"{candidate_scope_id} PG runtime scope mismatches {key}")
    for key in ("strategy_group_id", "symbol", "side"):
        if str(policy.get(key) or "") != str(candidate.get(key) or ""):
            raise ValueError(f"{candidate_scope_id} PG owner policy mismatches {key}")
    if runtime_scope.get("selected_strategygroup_scope") is not True:
        raise ValueError(f"{candidate_scope_id} PG runtime scope missing selected StrategyGroup")
    if runtime_scope.get("symbol_side_scope_closed") is not True:
        raise ValueError(f"{candidate_scope_id} PG runtime scope missing symbol/side closure")
    if runtime_scope.get("notional_leverage_scope_closed") is not True:
        raise ValueError(f"{candidate_scope_id} PG runtime scope missing notional/leverage closure")
    if runtime_scope.get("live_submit_allowed") is not True:
        raise ValueError(f"{candidate_scope_id} PG runtime scope blocks live submit")
    if str(runtime_scope.get("runtime_profile_id") or "") != str(
        policy.get("runtime_profile_id") or ""
    ):
        raise ValueError(f"{candidate_scope_id} PG runtime profile mismatches owner policy")
    if policy.get("enabled_state") != "enabled":
        raise ValueError(f"{candidate_scope_id} PG owner policy is not enabled")
    if policy.get("pretrade_candidate_allowed") is not True:
        raise ValueError(f"{candidate_scope_id} PG owner policy blocks pretrade")
    if policy.get("action_time_rehearsal_allowed") is not True:
        raise ValueError(f"{candidate_scope_id} PG owner policy blocks action-time rehearsal")
    if policy.get("live_submit_allowed") not in {"scoped", "conditional_hard_gated"}:
        raise ValueError(f"{candidate_scope_id} PG owner policy blocks live submit")
    if not _positive_decimal(policy.get("max_notional")) or not _positive_decimal(
        policy.get("leverage")
    ):
        raise ValueError(f"{candidate_scope_id} PG owner policy missing notional/leverage")


def _current_pretrade_readiness_by_lane(
    control_state: dict[str, Any],
    *,
    suppress_persistent_action_time_outcomes: bool = False,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    now_ms = _control_state_now_ms(control_state)
    readiness = {
        _lane_key(row): row
        for row in _dict_rows(control_state.get("pretrade_readiness_rows"))
        if is_current_pretrade_readiness(row, now_ms)
    }
    if suppress_persistent_action_time_outcomes:
        return readiness
    unresolved_outcomes = _unresolved_action_time_sequence_outcomes(control_state)
    for key, outcome in unresolved_outcomes.items():
        strategy_group_id, symbol, side = key
        current = readiness.get(key, {})
        readiness[key] = {
            **current,
            "strategy_group_id": strategy_group_id,
            "symbol": symbol,
            "side": side,
            "readiness_state": "blocked",
            "signal_lifecycle_status": "engineering_blocked",
            "signal_freshness_state": "absent",
            "promotion_state": "blocked",
            "first_blocker_class": "action_time_boundary_not_reproduced",
            "first_blocker_detail": str(outcome.get("first_blocker") or ""),
            "next_action": "repair_non_executing_action_time_rehearsal_path",
            "persistent_engineering_blocker": True,
            "process_outcome_id": str(outcome.get("process_outcome_id") or ""),
            "process_outcome_updated_at_ms": int(outcome.get("updated_at_ms") or 0),
        }
    return readiness


def _unresolved_action_time_sequence_outcomes(
    control_state: dict[str, Any],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    latest_by_lane: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in _dict_rows(control_state.get("runtime_process_outcomes")):
        if row.get("process_name") not in {
            "action_time_ticket_sequence",
            "action_time_ticket_sequence_batch",
            "action_time_refresh_sequence",
        }:
            continue
        scope_parts = str(row.get("scope_key") or "").split(":")
        if len(scope_parts) != 4 or scope_parts[0] != "lane":
            continue
        key = (scope_parts[1], scope_parts[2], scope_parts[3])
        current = latest_by_lane.get(key)
        row_order = (
            int(row.get("updated_at_ms") or 0),
            str(row.get("process_outcome_id") or ""),
        )
        current_order = (
            (
                int(current.get("updated_at_ms") or 0),
                str(current.get("process_outcome_id") or ""),
            )
            if current is not None
            else (-1, "")
        )
        if row_order >= current_order:
            latest_by_lane[key] = row
    return {
        key: row
        for key, row in latest_by_lane.items()
        if process_outcome_has_current_blocking_authority(control_state, row)
    }


def _current_fact_snapshot_by_lane(
    control_state: dict[str, Any],
    *,
    fact_surface: str,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    now_ms = _control_state_now_ms(control_state)
    snapshots: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in _dict_rows(control_state.get("runtime_fact_snapshots")):
        if row.get("fact_surface") != fact_surface:
            continue
        if not is_current_fact_snapshot(row, now_ms):
            continue
        key = _lane_key(row)
        if not all(key):
            continue
        current = snapshots.get(key)
        if current is None or int(row.get("observed_at_ms") or 0) >= int(
            current.get("observed_at_ms") or 0
        ):
            snapshots[key] = row
    return snapshots


def _current_global_fact_snapshot(
    control_state: dict[str, Any],
    *,
    fact_surface: str,
) -> dict[str, Any]:
    now_ms = _control_state_now_ms(control_state)
    rows = [
        row
        for row in _dict_rows(control_state.get("runtime_fact_snapshots"))
        if row.get("fact_surface") == fact_surface
        and row.get("strategy_group_id") is None
        and row.get("symbol") is None
        and row.get("side") is None
        and is_current_fact_snapshot(row, now_ms)
    ]
    if not rows:
        return {}
    return sorted(rows, key=lambda row: int(row.get("observed_at_ms") or 0))[-1]


def _fresh_signal_by_lane(
    control_state: dict[str, Any],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    now_ms = _control_state_now_ms(control_state)
    signals: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in _dict_rows(control_state.get("live_signal_events")):
        if not is_current_live_signal(row, now_ms):
            continue
        key = _lane_key(row)
        current = signals.get(key)
        if current is None or int(row.get("observed_at_ms") or 0) >= int(
            current.get("observed_at_ms") or 0
        ):
            signals[key] = row
    return signals


def _control_state_now_ms(control_state: dict[str, Any]) -> int:
    try:
        value = int(control_state.get("read_now_ms") or 0)
    except (TypeError, ValueError):
        value = 0
    if value > 0:
        return value
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _open_action_time_lane_by_lane(
    control_state: dict[str, Any],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    now_ms = _control_state_now_ms(control_state)
    lanes: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in _dict_rows(control_state.get("action_time_lane_inputs")):
        if not is_current_action_time_lane(row, now_ms):
            continue
        key = _lane_key(row)
        if key in lanes:
            raise ValueError("multiple open real-submit action-time lanes in PG state")
        lanes[key] = row
    return lanes


def _current_watcher_coverage_by_lane(
    control_state: dict[str, Any],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    now_ms = _control_state_now_ms(control_state)
    coverage: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in _dict_rows(control_state.get("watcher_runtime_coverage")):
        if not is_current_watcher_coverage(row, now_ms):
            continue
        key = _lane_key(row)
        coverage[key] = row
    return coverage


def _pg_daily_table_projection(
    *,
    generated_at_utc: str,
    candidate_rows: list[dict[str, Any]],
    strategy_groups: dict[str, dict[str, Any]],
    readiness_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    fact_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    binding_by_candidate: dict[str, dict[str, Any]],
    runtime_by_candidate: dict[str, dict[str, Any]],
    signal_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    event_spec_by_candidate: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for rank, strategy_group_id in enumerate(WIP_LANES, start=1):
        group_candidates = [
            row
            for row in candidate_rows
            if row.get("strategy_group_id") == strategy_group_id
        ]
        selected = _pg_strategy_summary_candidate(
            group_candidates,
            readiness_by_lane=readiness_by_lane,
            fact_by_lane=fact_by_lane,
            signal_by_lane=signal_by_lane,
            event_spec_by_candidate=event_spec_by_candidate,
        )
        candidate_scope_id = str(selected.get("candidate_scope_id") or "")
        first_blocker = _pg_candidate_first_blocker(
            selected,
            readiness_by_lane=readiness_by_lane,
            fact_by_lane=fact_by_lane,
            runtime_scope=runtime_by_candidate.get(candidate_scope_id, {}),
            signal_by_lane=signal_by_lane,
            event_spec=event_spec_by_candidate.get(candidate_scope_id, {}),
        )
        rows.append(
            {
                "strategy_group_id": strategy_group_id,
                "symbol": str(selected.get("symbol") or ""),
                "side": str(selected.get("side") or ""),
                "stage": str(
                    _as_dict(strategy_groups.get(strategy_group_id)).get(
                        "tradeability_stage"
                    )
                    or "armed_observation"
                ),
                "chain_position": "pg_runtime_control_state",
                "first_blocker": first_blocker,
                "first_blocker_detail": str(
                    selected.get("first_blocker_detail")
                    or ""
                ),
                "first_blocker_evidence": _pg_candidate_evidence_ref(
                    selected,
                    first_blocker=first_blocker,
                    binding=binding_by_candidate.get(candidate_scope_id, {}),
                ),
                "owner_action_required": "no",
                "next_engineering_action": _pg_next_action(first_blocker),
                "stop_condition": _symbol_stop_condition(first_blocker),
                "closest_to_live_rank": rank,
                "authority_boundary": DAILY_AUTHORITY_BOUNDARY,
            }
        )
    return {
        "schema": "brc.daily_live_enablement_table.v1",
        "status": "daily_live_enablement_table_ready",
        "source_validation": {
            "valid": True,
            "source_mode": "db_backed",
            "legacy_file_authority": False,
        },
        "generated_at_utc": generated_at_utc,
        "rows": rows,
    }


def _pg_tradeability_projection(
    *,
    candidate_rows: list[dict[str, Any]],
    strategy_groups: dict[str, dict[str, Any]],
    policy_by_id: dict[str, dict[str, Any]],
    runtime_by_candidate: dict[str, dict[str, Any]],
    readiness_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    fact_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    signal_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    event_spec_by_candidate: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    decision_rows: list[dict[str, Any]] = []
    for strategy_group_id in WIP_LANES:
        group_candidates = [
            row
            for row in candidate_rows
            if row.get("strategy_group_id") == strategy_group_id
        ]
        selected = _pg_strategy_summary_candidate(
            group_candidates,
            readiness_by_lane=readiness_by_lane,
            fact_by_lane=fact_by_lane,
            signal_by_lane=signal_by_lane,
            event_spec_by_candidate=event_spec_by_candidate,
        )
        candidate_scope_id = str(selected.get("candidate_scope_id") or "")
        runtime_scope = runtime_by_candidate.get(candidate_scope_id, {})
        first_blocker = _pg_candidate_first_blocker(
            selected,
            readiness_by_lane=readiness_by_lane,
            fact_by_lane=fact_by_lane,
            runtime_scope=runtime_scope,
            signal_by_lane=signal_by_lane,
            event_spec=event_spec_by_candidate.get(candidate_scope_id, {}),
        )
        policies = [
            policy_by_id.get(str(row.get("policy_current_id") or ""), {})
            for row in group_candidates
        ]
        live_symbols = sorted(
            {
                str(row.get("symbol") or "")
                for row in group_candidates
                if row.get("scope_state") == "live_submit_allowed"
                or runtime_by_candidate.get(str(row.get("candidate_scope_id") or ""), {}).get(
                    "live_submit_allowed"
                )
                is True
            }
        )
        decision_rows.append(
            {
                "strategy_group_id": strategy_group_id,
                "stage": str(
                    _as_dict(strategy_groups.get(strategy_group_id)).get(
                        "tradeability_stage"
                    )
                    or "armed_observation"
                ),
                "can_trade_now": False,
                "first_blocker": first_blocker,
                "first_blocker_detail": str(
                    selected.get("first_blocker_detail")
                    or ""
                ),
                "blocker_owner": _blocker_owner(first_blocker),
                "policy_scope": {
                    "live_submit_symbols": live_symbols,
                    "runtime_profile_ids": sorted(
                        {
                            str(policy.get("runtime_profile_id") or "")
                            for policy in policies
                            if str(policy.get("runtime_profile_id") or "")
                        }
                    ),
                },
            }
        )
    return {
        "schema": "brc.strategygroup_tradeability_decision.v1",
        "status": "tradeability_decision_ready",
        "decision_rows": decision_rows,
    }


def _pg_replay_live_parity_projection(
    *,
    candidate_rows: list[dict[str, Any]],
    readiness_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    fact_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    signal_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    event_spec_by_candidate: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        key = _lane_key(candidate)
        readiness = readiness_by_lane.get(key, {})
        facts = fact_by_lane.get(key, {})
        signal = signal_by_lane.get(key, {})
        detector_fact = (
            facts if str(facts.get("fact_surface") or "") == "pretrade_strategy" else {}
        )
        computed = bool(
            _is_true(detector_fact.get("computed"))
        )
        satisfied = (
            _is_true(detector_fact.get("satisfied"))
        )
        failed_facts = [
            str(item)
            for item in (
                readiness.get("computed_not_satisfied")
                or detector_fact.get("failed_facts")
                or []
            )
            if str(item or "")
        ]
        blocker_class = _event_spec_execution_eligibility_blocker(
            event_spec_by_candidate.get(
                str(candidate.get("candidate_scope_id") or ""),
                {},
            )
        ) or _pg_replay_live_blocker_class(
            readiness=readiness,
            facts=detector_fact,
            signal=signal,
            computed=computed,
            satisfied=satisfied,
            failed_facts=failed_facts,
        )
        rows.append(
            {
                "strategy_group_id": str(candidate.get("strategy_group_id") or ""),
                "symbol": str(candidate.get("symbol") or ""),
                "side": str(candidate.get("side") or ""),
                "blocker_class": blocker_class,
                "first_blocker_detail": str(
                    readiness.get("first_blocker_detail") or ""
                ),
                "persistent_engineering_blocker": (
                    readiness.get("persistent_engineering_blocker") is True
                ),
                "detector_attached": computed,
                "watcher_tick_present": readiness.get("watcher_state") == "fresh",
                "computed": computed,
                "fresh_signal_present": bool(signal),
                "event_time_utc": _ms_to_iso(_signal_event_time_ms(signal)),
                "failed_facts": failed_facts,
                "next_action": _pg_next_action(blocker_class),
                "evidence_source": "pg_runtime_control_state:pretrade_strategy_detector_fact",
            }
        )
    return {
        "schema": "brc.replay_live_parity_audit.v1",
        "status": "replay_live_parity_audit_ready",
        "per_symbol_mismatch_table": rows,
    }


def _pg_replay_live_blocker_class(
    *,
    readiness: dict[str, Any],
    facts: dict[str, Any],
    signal: dict[str, Any],
    computed: bool,
    satisfied: bool,
    failed_facts: list[str],
) -> str:
    readiness_blocker = str(readiness.get("first_blocker_class") or "")
    fact_blocker = str(facts.get("blocker_class") or "")
    current_signal_present = bool(signal)
    if readiness_blocker == "market_wait_validated" and not facts:
        return "detector_not_attached"
    if readiness_blocker and (
        readiness.get("persistent_engineering_blocker") is True
        or current_signal_present
        or readiness_blocker not in ACTION_TIME_CURRENT_ONLY_BLOCKERS
    ):
        return readiness_blocker
    if fact_blocker and (
        current_signal_present
        or fact_blocker not in ACTION_TIME_CURRENT_ONLY_BLOCKERS
    ):
        return fact_blocker
    if computed and satisfied:
        return "market_wait_validated"
    if computed and failed_facts:
        return "computed_not_satisfied"
    return "detector_not_attached"


def _pg_action_time_boundary_projection(
    *,
    generated_at_utc: str,
    now_ms: int,
    candidate_rows: list[dict[str, Any]],
    binding_by_candidate: dict[str, dict[str, Any]],
    event_by_id: dict[str, dict[str, Any]],
    readiness_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    public_fact_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    action_time_fact_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    account_safe_fact: dict[str, Any],
    account_safe_fact_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    signal_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    action_lane_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    capability_truth_by_lane: dict[
        tuple[str, str, str], ActionTimeCapabilityTruth
    ],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        key = _lane_key(candidate)
        candidate_scope_id = str(candidate.get("candidate_scope_id") or "")
        binding = binding_by_candidate.get(candidate_scope_id, {})
        event = event_by_id.get(str(binding.get("event_spec_id") or ""), {})
        readiness = readiness_by_lane.get(key, {})
        public_fact = public_fact_by_lane.get(key, {})
        action_time_fact = action_time_fact_by_lane.get(key, {})
        lane_account_safe_fact = account_safe_fact_by_lane.get(key, {})
        signal = signal_by_lane.get(key, {})
        action_lane = action_lane_by_lane.get(key, {})
        capability_truth = capability_truth_by_lane[key]
        fresh_signal_present = bool(signal)
        public_facts_ready = (
            readiness.get("public_facts_state") == "satisfied"
            or _is_true(public_fact.get("satisfied"))
        )
        private_action_time_facts_ready = (
            bool(action_lane.get("action_time_fact_snapshot_id"))
            or _fact_snapshot_ready(action_time_fact, now_ms=now_ms)
        )
        account_values = _as_dict(
            (account_safe_fact or lane_account_safe_fact).get("fact_values")
        )
        active_position_or_open_order_clear = (
            _is_true(account_values.get("active_position_or_open_order_clear"))
        )
        action_time_available_balance = (
            _is_true(account_values.get("action_time_available_balance"))
        )
        path_ready = bool(action_lane) or (
            fresh_signal_present
            and public_facts_ready
            and private_action_time_facts_ready
            and active_position_or_open_order_clear
            and action_time_available_balance
        )
        first_blocker = str(
            action_lane.get("first_blocker_class")
            or readiness.get("first_blocker_class")
            or ("action_time_preflight_ready" if path_ready else "")
            or f"fresh_{str(event.get('event_id') or 'signal').lower()}_absent"
        )
        rows.append(
            {
                "strategy_group_id": str(candidate.get("strategy_group_id") or ""),
                "symbol": str(candidate.get("symbol") or ""),
                "side": str(candidate.get("side") or ""),
                "event_id": str(event.get("event_id") or ""),
                "fresh_signal_present": fresh_signal_present,
                "event_time_utc": _ms_to_iso(_signal_event_time_ms(signal)),
                "fresh_signal_time_utc": _ms_to_iso(_signal_event_time_ms(signal)),
                "latest_candle_close_time_utc": _ms_to_iso(
                    _signal_trigger_candle_close_time_ms(signal)
                ),
                "action_time_path_ready": path_ready,
                "action_time_capability_certified": capability_truth.certified,
                "action_time_capability_reason": capability_truth.reason,
                "action_time_capability_source_watermark": (
                    capability_truth.identity.source_watermark
                    if capability_truth.identity is not None
                    else ""
                ),
                "action_time_capability_runtime_head": (
                    capability_truth.certified_runtime_head
                ),
                "first_blocker": first_blocker,
                "first_blocker_detail": str(
                    readiness.get("first_blocker_detail") or ""
                ),
                "next_action": _pg_next_action(first_blocker),
                "required_facts_readiness": {
                    "public_facts_ready": public_facts_ready,
                    "private_action_time_facts_ready": private_action_time_facts_ready,
                    "action_time_fact_snapshot_id": str(
                        action_lane.get("action_time_fact_snapshot_id")
                        or action_time_fact.get("fact_snapshot_id")
                        or ""
                    ),
                    "active_position_or_open_order_clear": (
                        active_position_or_open_order_clear
                    ),
                    "action_time_available_balance": action_time_available_balance,
                },
            }
        )
    return {
        "schema": "brc.strategy_fresh_signal_action_time_boundary.v1",
        "status": "strategy_fresh_signal_action_time_boundary_ready",
        "generated_at_utc": generated_at_utc,
        "strategy_rows": rows,
    }


def _apply_action_time_capability_truth(
    readiness_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    *,
    capability_truth_by_lane: dict[
        tuple[str, str, str], ActionTimeCapabilityTruth
    ],
    fact_by_lane: dict[tuple[str, str, str], dict[str, Any]],
) -> None:
    for lane_key, truth in capability_truth_by_lane.items():
        readiness = readiness_by_lane.get(lane_key)
        if truth.certified:
            continue
        if readiness and str(
            readiness.get("first_blocker_class") or ""
        ) != "market_wait_validated":
            continue
        facts = fact_by_lane.get(lane_key, {})
        if facts and facts.get("satisfied") is not True:
            continue
        readiness_by_lane[lane_key] = {
            **(readiness or {}),
            "strategy_group_id": lane_key[0],
            "symbol": lane_key[1],
            "side": lane_key[2],
            "readiness_state": "blocked",
            "promotion_state": "blocked",
            "first_blocker_class": "action_time_boundary_not_reproduced",
            "first_blocker_detail": (
                "release-bound Action-Time capability certification is not current: "
                + truth.reason
            ),
            "next_action": "certify_current_release_action_time_capability",
            "persistent_engineering_blocker": True,
            "action_time_capability": truth.model_dump(mode="json"),
        }


def _pg_single_lane_packet_projection(
    *,
    action_lane_by_lane: dict[tuple[str, str, str], dict[str, Any]],
) -> dict[str, Any]:
    if not action_lane_by_lane:
        return {
            "schema": "brc.single_lane_task_packet.v1",
            "status": "single_lane_task_packet_not_applicable_market_wait",
            "task_id": "OBSERVE-PG-CURRENT-CANDIDATE-POOL",
            "active_lane": {},
            "first_blocker": "market_wait_validated",
        }
    lane = sorted(
        action_lane_by_lane.values(),
        key=lambda row: (
            _strategy_priority(str(row.get("strategy_group_id") or "")),
            str(row.get("symbol") or ""),
            str(row.get("side") or ""),
        ),
    )[0]
    return {
        "schema": "brc.single_lane_task_packet.v1",
        "status": "single_lane_task_packet_ready",
        "task_id": f"PG-{lane.get('action_time_lane_input_id')}",
        "active_lane": {
            "strategy_group_id": str(lane.get("strategy_group_id") or ""),
            "symbol": str(lane.get("symbol") or ""),
            "side": str(lane.get("side") or ""),
            "stage": "action_time",
        },
        "first_blocker": str(lane.get("first_blocker_class") or "action_time_preflight_ready"),
    }


def _pg_runtime_active_monitor_projection(
    *,
    candidate_rows: list[dict[str, Any]],
    runtime_by_candidate: dict[str, dict[str, Any]],
    policy_by_id: dict[str, dict[str, Any]],
    coverage_by_lane: dict[tuple[str, str, str], dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        candidate_scope_id = str(candidate.get("candidate_scope_id") or "")
        runtime_scope = runtime_by_candidate.get(candidate_scope_id, {})
        policy = policy_by_id.get(str(candidate.get("policy_current_id") or ""), {})
        coverage = coverage_by_lane.get(_lane_key(candidate), {})
        coverage_state = str(coverage.get("coverage_state") or "")
        liveness_state = str(coverage.get("liveness_state") or "")
        # ``active`` remains valid only for historical/current rows written
        # before the typed observation-result field existed.  The current
        # watcher now writes an explicit failed/degraded liveness value on a
        # technical observation failure, so this compatibility state can no
        # longer hide an actual failed cycle.
        active = coverage_state == "covered" and liveness_state in {
            "healthy",
            "ok",
            "active",
        }
        technical_observation_failure = (
            coverage_state == "covered" and liveness_state in {"failed", "degraded"}
        )
        blocker_class = (
            "none"
            if active
            else "watcher_tick_missing"
            if technical_observation_failure
            else "runtime_profile_scope_missing"
        )
        rows.append(
            {
                "strategy_group_id": str(candidate.get("strategy_group_id") or ""),
                "symbol": str(candidate.get("symbol") or ""),
                "side": str(candidate.get("side") or ""),
                "expected_side": str(candidate.get("side") or ""),
                "state": "active_watcher_scope"
                if active
                else "runtime_observation_failed"
                if technical_observation_failure
                else "runtime_profile_scope_missing",
                "blocker_class": blocker_class,
                "liveness_state": liveness_state or "missing",
                "active_runtime_instance_ids": [
                    str(runtime_scope.get("runtime_scope_binding_id") or "")
                ]
                if active
                else [],
                "selected_runtime_instance_ids": [
                    str(runtime_scope.get("runtime_scope_binding_id") or "")
                ]
                if active
                else [],
                "matched_runtime_sides": [str(candidate.get("side") or "")]
                if active
                else [],
                "side_mismatch_runtime_instance_ids": [],
                "runtime_profile": {
                    "runtime_profile_id": str(
                        runtime_scope.get("runtime_profile_id")
                        or policy.get("runtime_profile_id")
                        or ""
                    ),
                    "target_notional_usdt": str(policy.get("max_notional") or ""),
                    "max_notional": str(policy.get("max_notional") or ""),
                    "leverage": str(policy.get("leverage") or ""),
                },
                "next_action": "continue_pretrade_observation"
                if active
                else "repair_runtime_observation_cycle_api"
                if technical_observation_failure
                else "bind_or_start_pretrade_runtime_for_candidate_symbol",
                "authority_boundary": AUTHORITY_BOUNDARY,
            }
        )
    active_matched = sum(1 for row in rows if row["state"] == "active_watcher_scope")
    coverage = {
        "status": "complete"
        if rows and active_matched == len(rows)
        else "incomplete",
        "expected_row_count": len(rows),
        "active_matched_row_count": active_matched,
        "missing_row_count": len(rows) - active_matched,
        "rows": rows,
    }
    return {
        "candidate_universe_coverage": coverage,
        "latest_summary": {"candidate_universe_coverage": coverage},
    }


def _pg_owner_pretrade_authorization_projection(
    *,
    candidate_rows: list[dict[str, Any]],
    runtime_by_candidate: dict[str, dict[str, Any]],
    policy_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    strategy_groups: dict[str, dict[str, Any]] = {}
    common_required_gates = [
        "fresh_signal",
        "required_facts",
        "server_runtime_coverage",
        "action_time_facts",
        "finalgate",
        "operation_layer",
        "protection",
        "reconciliation",
    ]
    for strategy_group_id in WIP_LANES:
        group_candidates = [
            row
            for row in candidate_rows
            if row.get("strategy_group_id") == strategy_group_id
        ]
        policies = [
            policy_by_id.get(str(row.get("policy_current_id") or ""), {})
            for row in group_candidates
        ]
        runtime_scopes = [
            runtime_by_candidate.get(str(row.get("candidate_scope_id") or ""), {})
            for row in group_candidates
        ]
        conditional_gates = sorted(
            {
                str(gate)
                for runtime_scope in runtime_scopes
                for gate in runtime_scope.get("conditional_hard_gates") or []
                if str(gate or "")
            }
        )
        strategy_groups[strategy_group_id] = {
            "pretrade_candidate_allowed": all(
                policy.get("pretrade_candidate_allowed") is True
                for policy in policies
            )
            and bool(policies),
            "action_time_rehearsal_allowed": all(
                policy.get("action_time_rehearsal_allowed") is True
                for policy in policies
            )
            and bool(policies),
            "candidate_symbols": _pg_group_symbols(group_candidates),
            "side_scope": sorted(
                {
                    str(row.get("side") or "")
                    for row in group_candidates
                    if str(row.get("side") or "")
                }
            ),
            "live_submit_allowed": "conditional_hard_gated"
            if conditional_gates
            else "scoped",
            "conditional_hard_gates": conditional_gates,
            "real_submit_required_gates": common_required_gates
            + conditional_gates
            + ["action_time_ticket"],
        }
    return {
        "schema": OWNER_AUTHORIZATION_SCHEMA,
        "status": "owner_pretrade_runtime_authorization_recorded",
        "scope": "pg_runtime_control_state_current",
        "recorded_at": "",
        "source": "pg_runtime_control_state",
        "pretrade_candidate_allowed": True,
        "action_time_rehearsal_allowed": True,
        "v0_single_action_time_lane": True,
        "v0_single_real_submit_intent": True,
        "strategy_groups": strategy_groups,
        "authority_boundary": (
            "owner_policy_scope_only; no_exchange_write_bypass; "
            "no_finalgate_bypass; no_operation_layer_bypass"
        ),
    }


def _pg_strategy_summary_candidate(
    candidates: list[dict[str, Any]],
    *,
    readiness_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    fact_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    signal_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    event_spec_by_candidate: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not candidates:
        return {}
    return sorted(
        candidates,
        key=lambda row: (
            _pg_blocker_rank(
                _pg_candidate_first_blocker(
                    row,
                    readiness_by_lane=readiness_by_lane,
                    fact_by_lane=fact_by_lane,
                    runtime_scope={},
                    signal_by_lane=signal_by_lane,
                    event_spec=event_spec_by_candidate.get(
                        str(row.get("candidate_scope_id") or ""),
                        {},
                    ),
                )
            ),
            int(row.get("priority_rank") or 999),
            str(row.get("symbol") or ""),
            str(row.get("side") or ""),
        ),
    )[0]


def _pg_candidate_first_blocker(
    candidate: dict[str, Any],
    *,
    readiness_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    fact_by_lane: dict[tuple[str, str, str], dict[str, Any]],
    runtime_scope: dict[str, Any],
    signal_by_lane: dict[tuple[str, str, str], dict[str, Any]] | None = None,
    event_spec: dict[str, Any] | None = None,
) -> str:
    key = _lane_key(candidate)
    event_spec = event_spec or {}
    event_spec_blocker = _event_spec_execution_eligibility_blocker(event_spec)
    if event_spec_blocker:
        return event_spec_blocker
    signal = (signal_by_lane or {}).get(key, {})
    if signal and signal.get("execution_eligible") is not True:
        return EVENT_EXECUTION_CAPABILITY_NOT_CERTIFIED
    readiness = readiness_by_lane.get(key, {})
    if readiness.get("first_blocker_class"):
        if (
            str(readiness.get("first_blocker_class")) == "market_wait_validated"
            and not facts
        ):
            return "detector_not_attached"
        return str(readiness["first_blocker_class"])
    facts = fact_by_lane.get(key, {})
    if facts and str(facts.get("fact_surface") or "") != "pretrade_strategy":
        return "detector_not_attached"
    if facts:
        if facts.get("computed") is not True:
            return "artifact_missing"
        if facts.get("satisfied") is True:
            return "market_wait_validated"
        return str(facts.get("blocker_class") or "computed_not_satisfied")
    if runtime_scope and runtime_scope.get("live_submit_allowed") is not True:
        return "runtime_profile_scope_missing"
    return "detector_not_attached"


def _event_spec_execution_eligibility_blocker(
    event_spec: dict[str, Any],
) -> str:
    if "execution_eligibility_enabled" not in event_spec:
        return ""
    if (
        event_spec.get("execution_eligibility_enabled") is not True
        or event_spec.get("declared_signal_grade")
        not in {"trial_grade_signal", "production_grade_signal"}
        or event_spec.get("declared_required_execution_mode")
        not in {"trial_live", "production_live"}
    ):
        return EVENT_EXECUTION_CAPABILITY_NOT_CERTIFIED
    return ""


def _pg_candidate_evidence_ref(
    candidate: dict[str, Any],
    *,
    first_blocker: str,
    binding: dict[str, Any],
) -> str:
    return (
        "pg_runtime_control_state:"
        f"{candidate.get('candidate_scope_id')} "
        f"event_binding={binding.get('binding_id', '')} "
        f"first_blocker={first_blocker}"
    )


def _pg_next_action(first_blocker: str) -> str:
    return {
        "detector_not_attached": "attach_detector_for_candidate_symbol",
        "watcher_tick_missing": "refresh_readonly_watcher_for_candidate_symbol",
        "artifact_missing": "produce_per_symbol_readiness_evidence",
        "computed_not_satisfied": "continue_observation_with_failed_fact_matrix",
        "market_wait_validated": "continue_watcher_observation_until_fresh_signal",
        "runtime_profile_scope_missing": "bind_or_start_pretrade_runtime_for_candidate_symbol",
        EVENT_EXECUTION_CAPABILITY_NOT_CERTIFIED: (
            "certify_event_execution_capability_or_keep_observe_only"
        ),
        "action_time_boundary_not_reproduced": "repair_non_executing_action_time_rehearsal_path",
        "action_time_preflight_ready": "prepare_non_executing_finalgate_preflight_input",
        "active_position_resolution": "resolve_active_position_or_open_order_conflict",
        "hard_safety_stop": "resolve_hard_safety_stop",
    }.get(first_blocker, "reclassify_symbol_blocker")


def _pg_blocker_rank(first_blocker: str) -> int:
    return {
        "action_time_preflight_ready": 0,
        "market_wait_validated": 1,
        "computed_not_satisfied": 2,
        "watcher_tick_missing": 3,
        "detector_not_attached": 4,
        "runtime_profile_scope_missing": 5,
        EVENT_EXECUTION_CAPABILITY_NOT_CERTIFIED: 6,
        "artifact_missing": 6,
    }.get(first_blocker, 9)


def _pg_group_symbols(candidates: list[dict[str, Any]]) -> list[str]:
    ranked = sorted(
        candidates,
        key=lambda row: (int(row.get("priority_rank") or 999), str(row.get("symbol") or "")),
    )
    result: list[str] = []
    for row in ranked:
        symbol = str(row.get("symbol") or "")
        if symbol and symbol not in result:
            result.append(symbol)
    return result


def _lane_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("strategy_group_id") or ""),
        str(row.get("symbol") or ""),
        str(row.get("side") or ""),
    )


def _ms_to_iso(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).isoformat()


def _signal_event_time_ms(signal: dict[str, Any]) -> Any:
    return signal.get("event_time_ms") or signal.get("observed_at_ms")


def _signal_trigger_candle_close_time_ms(signal: dict[str, Any]) -> Any:
    return signal.get("trigger_candle_close_time_ms") or _signal_event_time_ms(signal)


def _fact_snapshot_ready(row: dict[str, Any], *, now_ms: int) -> bool:
    return (
        bool(row)
        and _is_true(row.get("computed"))
        and _is_true(row.get("satisfied"))
        and row.get("freshness_state") == "fresh"
        and int(row.get("valid_until_ms") or 0) > now_ms
    )


def _is_true(value: Any) -> bool:
    if value is True:
        return True
    if value in {1, "1"}:
        return True
    if isinstance(value, str) and value.strip().lower() == "true":
        return True
    return False


def build_strategy_live_candidate_pool(
    *,
    daily_table: dict[str, Any],
    tradeability: dict[str, Any],
    replay_live_parity: dict[str, Any],
    action_time_boundary: dict[str, Any],
    single_lane_task_packet: dict[str, Any],
    sor_detector: dict[str, Any] | None = None,
    mi_trial_admission: dict[str, Any] | None = None,
    brf2_runtime_signal_facts: dict[str, Any] | None = None,
    runtime_active_monitor: dict[str, Any] | None = None,
    owner_pretrade_authorization: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    runtime_active_monitor = runtime_active_monitor or {}
    owner_pretrade_authorization = owner_pretrade_authorization or {}
    generated = (
        generated_at_utc
        or str(daily_table.get("generated_at_utc") or "")
        or datetime.now(timezone.utc).isoformat()
    )
    action_time_boundary = {
        **action_time_boundary,
        "generated_at_utc": str(action_time_boundary.get("generated_at_utc") or generated),
    }
    source_validation = _source_validation(
        daily_table=daily_table,
        tradeability=tradeability,
        replay_live_parity=replay_live_parity,
        action_time_boundary=action_time_boundary,
        single_lane_task_packet=single_lane_task_packet,
    )
    daily_rows = {
        str(row.get("strategy_group_id") or ""): row
        for row in _dict_rows(daily_table.get("rows"))
    }
    tradeability_rows = {
        str(row.get("strategy_group_id") or ""): row
        for row in _dict_rows(tradeability.get("decision_rows"))
    }
    candidate_rows = [
        _candidate_row(
            strategy_group_id=strategy_group_id,
            daily_row=daily_rows.get(strategy_group_id, {}),
            tradeability_row=tradeability_rows.get(strategy_group_id, {}),
            action_row=_action_time_row(
                action_time_boundary=action_time_boundary,
                strategy_group_id=strategy_group_id,
                symbol=str(
                    daily_rows.get(strategy_group_id, {}).get("symbol") or ""
                ),
            ),
        )
        for strategy_group_id in WIP_LANES
    ]
    symbol_readiness_rows = _symbol_readiness_rows(
        candidate_rows=candidate_rows,
        daily_rows=daily_rows,
        replay_live_parity=replay_live_parity,
        action_time_boundary=action_time_boundary,
        sor_detector=sor_detector or {},
        mi_trial_admission=mi_trial_admission or {},
        brf2_runtime_signal_facts=brf2_runtime_signal_facts or {},
        tradeability_rows=tradeability_rows,
        runtime_active_monitor=runtime_active_monitor,
        owner_pretrade_authorization=owner_pretrade_authorization,
    )
    candidate_rows = _sync_candidate_rows_with_symbol_readiness(
        candidate_rows,
        symbol_readiness_rows,
    )
    promotion_candidates = [
        row
        for row in symbol_readiness_rows
        if row["promotion_state"] == "promotion_candidate"
    ]
    eligible_action_time_rows = [
        row
        for row in symbol_readiness_rows
        if row["promotion_state"] == "action_time_lane"
    ]
    selected_action_time_row = _select_action_time_row(eligible_action_time_rows)
    action_time_lane_inputs = (
        [_action_time_lane_input(selected_action_time_row)]
        if selected_action_time_row
        else []
    )
    arbitration = _arbitration(
        promotion_candidates=promotion_candidates,
        eligible_action_time_rows=eligible_action_time_rows,
        selected_action_time_row=selected_action_time_row,
    )
    no_trade_audit = _no_trade_audit(
        symbol_readiness_rows=symbol_readiness_rows,
        action_time_lane_inputs=action_time_lane_inputs,
        arbitration=arbitration,
    )
    p0_p1_review = _p0_p1_review(candidate_rows, source_validation)
    p0_cleared = all(
        row["status"] == "cleared"
        for row in p0_p1_review
        if row["priority"] == "P0"
    )
    p1_cleared_or_waived = all(
        row["status"] in {"cleared", "waived", "waived_with_reason"}
        for row in p0_p1_review
        if row["priority"] == "P1"
    )
    deploy_ready = (
        p0_cleared
        and p1_cleared_or_waived
        and not _residual_deploy_blockers(candidate_rows)
    )
    return {
        "schema": SCHEMA,
        "scope": "five_strategy_live_candidate_pool_non_authority",
        "status": (
            "strategy_live_candidate_pool_ready"
            if source_validation["valid"]
            else "strategy_live_candidate_pool_source_invalid"
        ),
        "generated_at_utc": generated,
        "source_validation": source_validation,
        "pretrade_runtime": {
            "name": "Multi-Strategy Multi-Symbol Pre-Trade Runtime V0",
            "principle": (
                "wide_observation_medium_candidate_narrow_action_time_"
                "single_intent_submit"
            ),
            "active_strategy_groups": list(WIP_LANES),
            "candidate_symbols_per_strategy_group": {
                strategy_group_id: len(
                    {
                        row["symbol"]
                        for row in symbol_readiness_rows
                        if row["strategy_group_id"] == strategy_group_id
                    }
                )
                for strategy_group_id in WIP_LANES
            },
            "candidate_lanes_per_strategy_group": {
                strategy_group_id: len(
                    [
                        row
                        for row in symbol_readiness_rows
                        if row["strategy_group_id"] == strategy_group_id
                    ]
                )
                for strategy_group_id in WIP_LANES
            },
            "owner_authorization": _owner_authorization_summary(
                owner_pretrade_authorization
            ),
        },
        "candidate_universe": _candidate_universe(symbol_readiness_rows),
        "candidate_lane_universe": _candidate_lane_universe(symbol_readiness_rows),
        "server_runtime_coverage": _runtime_coverage(runtime_active_monitor),
        "candidate_rows": candidate_rows,
        "symbol_readiness_rows": symbol_readiness_rows,
        "promotion_candidates": promotion_candidates,
        "action_time_lane_inputs": action_time_lane_inputs,
        "arbitration": arbitration,
        "no_trade_audit": no_trade_audit,
        "p0_p1_review": p0_p1_review,
        "summary": {
            "candidate_count": len(candidate_rows),
            "symbol_readiness_count": len(symbol_readiness_rows),
            "fresh_candidate_count": len(promotion_candidates),
            "action_time_lane_input_count": len(action_time_lane_inputs),
            "top_action_time_candidate": arbitration["selected_action_time_candidate"],
            "wip_lane_count": len(WIP_LANES),
            "p0_cleared": p0_cleared,
            "p1_cleared_or_waived": p1_cleared_or_waived,
            "deploy_ready": deploy_ready,
            "non_authority": True,
        },
        "checks": {
            "source_validation_passed": source_validation["valid"],
            "five_wip_candidates_present": {
                row["strategy_group_id"] for row in candidate_rows
            }
            == set(WIP_LANES),
            "all_rows_have_required_candidate_fields": all(
                _candidate_row_complete(row) for row in candidate_rows
            ),
            "each_strategy_has_multiple_candidate_symbols": all(
                count >= 2
                for count in {
                    row["strategy_group_id"]: len(
                        [
                            candidate
                            for candidate in symbol_readiness_rows
                            if candidate["strategy_group_id"]
                            == row["strategy_group_id"]
                        ]
                    )
                    for row in candidate_rows
                }.values()
            ),
            "readonly_signal_cannot_order": all(
                row["scope_state"] != "readonly_only"
                for row in action_time_lane_inputs
            ),
            "single_real_submit_candidate": len(action_time_lane_inputs) <= 1
            and len(_dict_rows(arbitration.get("deferred_action_time_candidates")))
            == max(len(eligible_action_time_rows) - 1, 0),
            "p0_cleared": p0_cleared,
            "p1_cleared_or_waived": p1_cleared_or_waived,
            "deploy_ready": deploy_ready,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "order_created": False,
        },
        "authority_boundary": AUTHORITY_BOUNDARY,
        "safety_invariants": {
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "order_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
        },
    }


def _action_time_row(
    *,
    action_time_boundary: dict[str, Any],
    strategy_group_id: str,
    symbol: str,
) -> dict[str, Any]:
    fallback: dict[str, Any] = {}
    for row in _dict_rows(action_time_boundary.get("strategy_rows")):
        if str(row.get("strategy_group_id") or "") != strategy_group_id:
            continue
        if symbol and str(row.get("symbol") or "") == symbol:
            return row
        if not fallback:
            fallback = row
    return fallback


def _symbol_readiness_rows(
    *,
    candidate_rows: list[dict[str, Any]],
    daily_rows: dict[str, dict[str, Any]],
    replay_live_parity: dict[str, Any],
    action_time_boundary: dict[str, Any],
    sor_detector: dict[str, Any],
    mi_trial_admission: dict[str, Any],
    brf2_runtime_signal_facts: dict[str, Any],
    tradeability_rows: dict[str, dict[str, Any]],
    runtime_active_monitor: dict[str, Any],
    owner_pretrade_authorization: dict[str, Any],
) -> list[dict[str, Any]]:
    parity_rows = _dict_rows(replay_live_parity.get("per_symbol_mismatch_table"))
    sor_facts = _sor_detector_symbol_facts(sor_detector)
    mi_facts = _mi_trial_admission_symbol_facts(
        mi_trial_admission,
        owner_pretrade_authorization=owner_pretrade_authorization,
    )
    brf2_facts = _brf2_runtime_signal_symbol_facts(
        brf2_runtime_signal_facts,
        owner_pretrade_authorization=owner_pretrade_authorization,
    )
    action_rows = _dict_rows(action_time_boundary.get("strategy_rows"))
    runtime_coverage_rows = _dict_rows(
        _runtime_coverage(runtime_active_monitor).get("rows")
    )
    result: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        strategy_group_id = str(candidate.get("strategy_group_id") or "")
        daily_row = daily_rows.get(strategy_group_id, {})
        candidate_sides = _candidate_side_scope(
            strategy_group_id,
            owner_pretrade_authorization,
        )
        symbols = _candidate_symbols(
            strategy_group_id=strategy_group_id,
            selected_symbol=str(candidate.get("selected_symbol") or ""),
            parity_rows=parity_rows,
            action_rows=action_rows,
            owner_pretrade_authorization=owner_pretrade_authorization,
        )
        for symbol in symbols:
            for candidate_side in candidate_sides:
                parity_row = _matching_symbol_row(
                    parity_rows,
                    strategy_group_id,
                    symbol,
                    candidate_side,
                )
                if strategy_group_id == "SOR-001":
                    parity_row = _merge_symbol_fact_row(
                        parity_row,
                        sor_facts.get(symbol, {}),
                    )
                if strategy_group_id == "MI-001":
                    parity_row = _merge_symbol_fact_row(
                        parity_row,
                        mi_facts.get(symbol, {}),
                    )
                if strategy_group_id == "BRF2-001":
                    parity_row = _merge_symbol_fact_row(
                        parity_row,
                        brf2_facts.get(symbol, {}),
                    )
                action_row = _matching_symbol_row(
                    action_rows,
                    strategy_group_id,
                    symbol,
                    candidate_side,
                )
                action_row = {
                    **action_row,
                    "_artifact_generated_at_utc": str(
                        action_time_boundary.get("generated_at_utc") or ""
                    ),
                }
                runtime_coverage_row = _matching_symbol_row(
                    runtime_coverage_rows,
                    strategy_group_id,
                    symbol,
                    candidate_side,
                    allow_side_mismatch=True,
                ) or _missing_runtime_coverage_row(
                    strategy_group_id, symbol, candidate_side
                )
                runtime_coverage_row = _normalize_runtime_coverage_row(
                    runtime_coverage_row,
                    strategy_group_id,
                    symbol,
                    candidate_side,
                )
                result.append(
                    _symbol_readiness_row(
                        strategy_group_id=strategy_group_id,
                        symbol=symbol,
                        side=candidate_side,
                        candidate=candidate,
                        daily_row=daily_row,
                        tradeability_row=tradeability_rows.get(strategy_group_id, {}),
                        parity_row=parity_row,
                        action_row=action_row,
                        runtime_coverage_row=runtime_coverage_row,
                        owner_pretrade_authorization=owner_pretrade_authorization,
                    )
                )
    return result


def _merge_symbol_fact_row(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    if not override:
        return base
    merged = dict(base)
    merged.update(override)
    return merged


def _sor_detector_symbol_facts(detector: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if detector.get("status") != "sor_session_detector_facts_ready":
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in _dict_rows(detector.get("symbol_detector_rows")):
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        missing = [
            str(item)
            for item in row.get("missing_required_trigger_facts") or []
            if str(item or "")
        ]
        candle_tick_present = bool(row.get("latest_candle_close_time_utc")) and (
            "opening_range_available" not in missing
        )
        public_facts_ready = row.get("public_facts_ready") is True
        watcher_tick_present = public_facts_ready and candle_tick_present
        rows[symbol] = {
            "blocker_class": (
                "computed_not_satisfied"
                if watcher_tick_present and missing
                else "market_wait_validated"
                if watcher_tick_present
                else "watcher_tick_missing"
            ),
            "detector_attached": True,
            "watcher_tick_present": watcher_tick_present,
            "computed": watcher_tick_present,
            "fresh_signal_present": row.get("fresh_session_range_signal") is True,
            "latest_candle_close_time_utc": str(
                row.get("latest_candle_close_time_utc") or ""
            ),
            "failed_facts": missing if watcher_tick_present else [],
            "next_action": (
                "continue_observation_with_failed_fact_matrix"
                if watcher_tick_present
                else "refresh_or_repair_watcher_public_fact_input"
            ),
        }
    return rows


def _mi_trial_admission_symbol_facts(
    admission: dict[str, Any],
    *,
    owner_pretrade_authorization: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if admission.get("status") != "mi_trial_admission_decision_ready":
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in _dict_rows(admission.get("symbol_evidence")):
        symbol = str(row.get("symbol") or "")
        if not _symbol_authorized(
            "MI-001",
            symbol,
            owner_pretrade_authorization,
        ):
            continue
        failed = _mi_failed_facts(row)
        rows[symbol] = {
            "blocker_class": (
                "computed_not_satisfied" if failed else "market_wait_validated"
            ),
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "fresh_signal_present": False,
            "failed_facts": failed,
            "next_action": (
                "continue_observation_with_failed_fact_matrix"
                if failed
                else "continue_watcher_observation_until_fresh_signal"
            ),
            "evidence_source": "mi_trial_admission_decision:symbol_evidence",
        }
    return rows


def _mi_failed_facts(row: dict[str, Any]) -> list[str]:
    failed: list[str] = []
    if row.get("strategy_scope_supported") is not True:
        failed.append("strategy_scope_supported")
    if row.get("public_facts_ready") is not True:
        failed.append("public_facts_ready")
    liquidity = _as_dict(row.get("liquidity"))
    for key in ("spread_ok", "min_notional_ok", "qty_step_ok"):
        if liquidity.get(key) is not True:
            failed.append(key)
    if row.get("funding_not_extreme") is not True:
        failed.append("funding_not_extreme")
    if str(row.get("strategy_fit") or "") == "not_supported_by_strategy_scope":
        failed.append("strategy_fit")
    return sorted(set(failed))


def _brf2_runtime_signal_symbol_facts(
    facts_artifact: dict[str, Any],
    *,
    owner_pretrade_authorization: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    status = str(facts_artifact.get("status") or "")
    if not status:
        return {}
    symbols = _authorization_candidate_symbols(
        owner_pretrade_authorization,
        "BRF2-001",
    )
    if not symbols:
        return {}
    if status == "brf2_runtime_signal_facts_missing_watcher_input":
        return {
            symbol: {
                "blocker_class": "watcher_tick_missing",
                "detector_attached": True,
                "watcher_tick_present": False,
                "computed": False,
                "fresh_signal_present": False,
                "failed_facts": [],
                "next_action": "attach_brf2_watcher_fact_input_producer",
                "evidence_source": "brf2_runtime_signal_facts:missing_watcher_input",
            }
            for symbol in symbols
        }
    if status != "brf2_runtime_signal_facts_ready":
        return {}
    per_symbol_rows = _dict_rows(facts_artifact.get("per_symbol_facts"))
    if per_symbol_rows:
        rows: dict[str, dict[str, Any]] = {}
        for row in per_symbol_rows:
            symbol = _normalize_symbol(row.get("symbol"))
            if not _symbol_authorized(
                "BRF2-001",
                symbol,
                owner_pretrade_authorization,
            ):
                continue
            failed = _brf2_failed_facts(_as_dict(row.get("facts")))
            watcher_tick_present = row.get("watcher_tick_present") is True
            computed = row.get("fact_input_present") is True and watcher_tick_present
            rows[symbol] = {
                "blocker_class": (
                    "computed_not_satisfied" if failed else "market_wait_validated"
                ),
                "detector_attached": True,
                "watcher_tick_present": watcher_tick_present,
                "computed": computed,
                "fresh_signal_present": row.get("fresh_signal_present") is True,
                "fresh_signal_time_utc": str(
                    row.get("fresh_signal_time_utc")
                    or row.get("event_time_utc")
                    or row.get("latest_candle_close_time_utc")
                    or ""
                ),
                "failed_facts": failed if computed else [],
                "next_action": (
                    "continue_observation_with_failed_fact_matrix"
                    if failed
                    else "continue_watcher_observation_until_fresh_signal"
                ),
                "evidence_source": "brf2_runtime_signal_facts:per_symbol_facts",
            }
        for symbol in symbols:
            rows.setdefault(
                symbol,
                {
                    "blocker_class": "watcher_tick_missing",
                    "detector_attached": True,
                    "watcher_tick_present": False,
                    "computed": False,
                    "fresh_signal_present": False,
                    "failed_facts": [],
                    "next_action": "attach_brf2_watcher_fact_input_producer",
                    "evidence_source": "brf2_runtime_signal_facts:missing_symbol_fact_input",
                },
            )
        return rows
    observed_symbol = _normalize_symbol(
        _as_dict(facts_artifact.get("signal_context")).get("symbol")
        or _as_dict(facts_artifact.get("source_signal_context")).get("symbol")
    )
    observed_symbol_authorized = _symbol_authorized(
        "BRF2-001",
        observed_symbol,
        owner_pretrade_authorization,
    )
    failed = _brf2_failed_facts(_as_dict(facts_artifact.get("facts")))
    rows: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        if not observed_symbol_authorized or symbol != observed_symbol:
            rows[symbol] = {
                "blocker_class": "watcher_tick_missing",
                "detector_attached": True,
                "watcher_tick_present": False,
                "computed": False,
                "fresh_signal_present": False,
                "failed_facts": [],
                "next_action": "attach_brf2_watcher_fact_input_producer",
                "evidence_source": "brf2_runtime_signal_facts:missing_symbol_fact_input",
            }
            continue
        rows[symbol] = {
            "blocker_class": (
                "computed_not_satisfied" if failed else "market_wait_validated"
            ),
            "detector_attached": True,
            "watcher_tick_present": facts_artifact.get("watcher_tick_present") is True,
            "computed": facts_artifact.get("fact_input_present") is True,
            "fresh_signal_present": False,
            "failed_facts": failed,
            "next_action": (
                "continue_observation_with_failed_fact_matrix"
                if failed
                else "continue_watcher_observation_until_fresh_signal"
            ),
            "evidence_source": "brf2_runtime_signal_facts:facts",
        }
    return rows


def _brf2_failed_facts(facts: dict[str, Any]) -> list[str]:
    if not facts:
        return ["brf2_runtime_signal_facts"]
    failed: list[str] = []
    accepted = {
        "closed_1h_ohlcv": {"fresh", "present", "ready"},
        "closed_5m_ohlcv": {"fresh", "present", "ready"},
        "rally_context": {"bear_or_weak_reclaim", "ready", "weak_rally"},
        "rally_failure_trigger_state": {"active", "confirmed", "ready"},
        "short_squeeze_risk_state": {"clear", "clear_or_bounded"},
        "strong_reclaim_disable_state": {"clear", "false", "inactive"},
        "liquidity_downshift_state": {"clear", "false", "inactive"},
        "spread_liquidity_state": {"acceptable", "normal", "ready"},
    }
    disable_active = {
        "short_squeeze_risk_state": {"bounded", "red", "unbounded", "unknown"},
        "strong_reclaim_disable_state": {"active", "true"},
        "rally_extension_invalidates_failure_state": {"active", "true"},
        "liquidity_downshift_state": {"active", "true"},
        "spread_liquidity_state": {"missing", "wide_spread", "thin_volume", "unknown"},
    }
    for fact_key, accepted_statuses in accepted.items():
        status = str(_as_dict(facts.get(fact_key)).get("status") or "").lower()
        if status not in accepted_statuses:
            failed.append(fact_key)
    for fact_key, active_statuses in disable_active.items():
        status = str(_as_dict(facts.get(fact_key)).get("status") or "").lower()
        if status in active_statuses:
            failed.append(fact_key)
    return sorted(set(failed))


def _normalize_symbol(value: Any) -> str:
    symbol = str(value or "").upper()
    if not symbol:
        return ""
    symbol = symbol.split(":", 1)[0].replace("/", "")
    return symbol


def _candidate_symbols(
    *,
    strategy_group_id: str,
    selected_symbol: str,
    parity_rows: list[dict[str, Any]],
    action_rows: list[dict[str, Any]],
    owner_pretrade_authorization: dict[str, Any] | None = None,
) -> list[str]:
    symbols: list[str] = []
    authorized_symbols = _authorization_candidate_symbols(
        owner_pretrade_authorization or {},
        strategy_group_id,
    )
    for symbol in authorized_symbols:
        symbols.append(symbol)
    for symbol in (
        selected_symbol,
        *(
            str(row.get("symbol") or "")
            for row in parity_rows
            if str(row.get("strategy_group_id") or "") == strategy_group_id
        ),
        *(
            str(row.get("symbol") or "")
            for row in action_rows
            if str(row.get("strategy_group_id") or "") == strategy_group_id
        ),
    ):
        if _symbol_authorized(
            strategy_group_id,
            symbol,
            owner_pretrade_authorization,
        ):
            symbols.append(symbol)
    return sorted(set(symbols), key=lambda symbol: (_symbol_role(strategy_group_id, symbol), symbol))


def _symbol_authorized(
    strategy_group_id: str,
    symbol: str,
    authorization: dict[str, Any] | None = None,
) -> bool:
    if not symbol or symbol in PLACEHOLDER_SYMBOLS:
        return False
    authorized = set(_authorization_candidate_symbols(authorization or {}, strategy_group_id))
    return symbol in authorized


def _authorization_candidate_symbols(
    authorization: dict[str, Any],
    strategy_group_id: str,
) -> tuple[str, ...]:
    row = _as_dict(_as_dict(authorization.get("strategy_groups")).get(strategy_group_id))
    symbols = [
        str(item).strip().upper()
        for item in row.get("candidate_symbols") or []
        if str(item or "").strip()
    ]
    result: list[str] = []
    for symbol in symbols:
        if symbol not in PLACEHOLDER_SYMBOLS and symbol not in result:
            result.append(symbol)
    return tuple(result)


def _candidate_side_scope(
    strategy_group_id: str,
    authorization: dict[str, Any],
) -> tuple[str, ...]:
    row = _as_dict(_as_dict(authorization.get("strategy_groups")).get(strategy_group_id))
    sides = [
        str(item).strip().lower()
        for item in row.get("side_scope") or []
        if str(item or "").strip()
    ]
    allowed: list[str] = []
    for side in sides:
        if side in {"long", "short"} and side not in allowed:
            allowed.append(side)
    return tuple(allowed)


def _owner_authorization_summary(
    authorization: dict[str, Any],
) -> dict[str, Any]:
    valid = _owner_authorization_valid(authorization)
    strategy_groups = _as_dict(authorization.get("strategy_groups"))
    return {
        "schema": str(authorization.get("schema") or ""),
        "status": str(authorization.get("status") or ""),
        "valid": valid,
        "pretrade_candidate_allowed": authorization.get(
            "pretrade_candidate_allowed"
        )
        is True,
        "action_time_rehearsal_allowed": authorization.get(
            "action_time_rehearsal_allowed"
        )
        is True,
        "v0_single_action_time_lane": authorization.get(
            "v0_single_action_time_lane"
        )
        is True,
        "v0_single_real_submit_intent": authorization.get(
            "v0_single_real_submit_intent"
        )
        is True,
        "scoped_live_submit_strategy_groups": sorted(
            strategy_group_id
            for strategy_group_id in WIP_LANES
            if _as_dict(strategy_groups.get(strategy_group_id)).get(
                "live_submit_allowed"
            )
            == "scoped"
        ),
        "conditional_hard_gated_strategy_groups": sorted(
            strategy_group_id
            for strategy_group_id in WIP_LANES
            if _as_dict(strategy_groups.get(strategy_group_id)).get(
                "live_submit_allowed"
            )
            == "conditional_hard_gated"
        ),
        "strategy_group_scopes": {
            strategy_group_id: {
                "candidate_symbols": sorted(
                    str(item)
                    for item in _as_dict(
                        strategy_groups.get(strategy_group_id)
                    ).get("candidate_symbols")
                    or []
                    if str(item or "")
                ),
                "side_scope": sorted(
                    str(item)
                    for item in _as_dict(
                        strategy_groups.get(strategy_group_id)
                    ).get("side_scope")
                    or []
                    if str(item or "")
                ),
                "live_submit_allowed": str(
                    _as_dict(strategy_groups.get(strategy_group_id)).get(
                        "live_submit_allowed"
                    )
                    or ""
                ),
            }
            for strategy_group_id in WIP_LANES
        },
        "authority_boundary": str(authorization.get("authority_boundary") or ""),
    }


def _owner_authorization_valid(authorization: dict[str, Any]) -> bool:
    if authorization.get("schema") != OWNER_AUTHORIZATION_SCHEMA:
        return False
    if authorization.get("status") != "owner_pretrade_runtime_authorization_recorded":
        return False
    if authorization.get("pretrade_candidate_allowed") is not True:
        return False
    if authorization.get("action_time_rehearsal_allowed") is not True:
        return False
    if authorization.get("v0_single_action_time_lane") is not True:
        return False
    if authorization.get("v0_single_real_submit_intent") is not True:
        return False
    strategy_groups = _as_dict(authorization.get("strategy_groups"))
    for strategy_group_id in WIP_LANES:
        row = _as_dict(strategy_groups.get(strategy_group_id))
        if row.get("pretrade_candidate_allowed") is not True:
            return False
        if row.get("action_time_rehearsal_allowed") is not True:
            return False
        symbols = set(_authorization_candidate_symbols(authorization, strategy_group_id))
        if not symbols:
            return False
        sides = {
            str(item)
            for item in row.get("side_scope") or []
            if str(item or "")
        }
        if not sides or not sides.issubset({"long", "short"}):
            return False
        if str(row.get("live_submit_allowed") or "") not in {
            "scoped",
            "conditional_hard_gated",
        }:
            return False
    return True


def _symbol_owner_authorization(
    authorization: dict[str, Any],
    strategy_group_id: str,
    symbol: str,
    side: str,
) -> dict[str, Any]:
    if not _owner_authorization_valid(authorization):
        return {
            "pretrade_candidate_allowed": False,
            "action_time_rehearsal_allowed": False,
            "live_submit_allowed": "none",
            "real_submit_required_gates": [],
            "candidate_symbols": [],
            "side_scope": [],
            "authority_boundary": "owner_pretrade_authorization_missing_or_invalid",
        }
    strategy_groups = _as_dict(authorization.get("strategy_groups"))
    row = _as_dict(strategy_groups.get(strategy_group_id))
    symbols = {str(item) for item in row.get("candidate_symbols") or []}
    sides = {str(item) for item in row.get("side_scope") or []}
    symbol_allowed = symbol in symbols and _symbol_authorized(
        strategy_group_id,
        symbol,
        authorization,
    )
    side_allowed = side in sides
    return {
        "pretrade_candidate_allowed": bool(
            symbol_allowed
            and side_allowed
            and row.get("pretrade_candidate_allowed") is True
        ),
        "action_time_rehearsal_allowed": bool(
            symbol_allowed
            and side_allowed
            and row.get("action_time_rehearsal_allowed") is True
        ),
        "live_submit_allowed": (
            str(row.get("live_submit_allowed") or "none")
            if symbol_allowed and side_allowed
            else "none"
        ),
        "real_submit_required_gates": [
            str(item) for item in row.get("real_submit_required_gates") or []
        ]
        if symbol_allowed and side_allowed
        else [],
        "candidate_symbols": sorted(symbols),
        "side_scope": sorted(sides),
        "authority_boundary": str(authorization.get("authority_boundary") or ""),
    }


def _matching_symbol_row(
    rows: list[dict[str, Any]],
    strategy_group_id: str,
    symbol: str,
    side: str | None = None,
    allow_side_mismatch: bool = False,
) -> dict[str, Any]:
    side_mismatch_fallback: dict[str, Any] = {}
    side_neutral_fallback: dict[str, Any] = {}
    for row in rows:
        if (
            str(row.get("strategy_group_id") or "") == strategy_group_id
            and str(row.get("symbol") or "") == symbol
        ):
            row_side = str(row.get("side") or row.get("expected_side") or "")
            if side is None:
                return row
            if row_side == side:
                return row
            if not row_side and not side_neutral_fallback:
                side_neutral_fallback = row
            if allow_side_mismatch and row_side and not side_mismatch_fallback:
                side_mismatch_fallback = row
    if side_neutral_fallback:
        return side_neutral_fallback
    if side_mismatch_fallback:
        return side_mismatch_fallback
    return {}


def _runtime_coverage_side_mismatch(row: dict[str, Any], side: str) -> bool:
    coverage_side = str(row.get("side") or row.get("expected_side") or "")
    return bool(coverage_side and side and coverage_side != side)


def _missing_runtime_coverage_row(
    strategy_group_id: str, symbol: str, side: str
) -> dict[str, Any]:
    return {
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "side": side,
        "expected_side": side,
        "state": "runtime_profile_scope_missing",
        "blocker_class": "runtime_profile_scope_missing",
        "active_runtime_instance_ids": [],
        "selected_runtime_instance_ids": [],
        "matched_runtime_sides": [],
        "side_mismatch_runtime_instance_ids": [],
        "next_action": "bind_or_start_pretrade_runtime_for_candidate_symbol",
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def _normalize_runtime_coverage_row(
    row: dict[str, Any], strategy_group_id: str, symbol: str, side: str
) -> dict[str, Any]:
    normalized = dict(row)
    normalized.setdefault("strategy_group_id", strategy_group_id)
    normalized.setdefault("symbol", symbol)
    normalized.setdefault("side", side)
    normalized.setdefault("expected_side", side)
    normalized.setdefault("state", "runtime_profile_scope_missing")
    normalized.setdefault("blocker_class", "runtime_profile_scope_missing")
    normalized.setdefault("active_runtime_instance_ids", [])
    normalized.setdefault("selected_runtime_instance_ids", [])
    normalized.setdefault("matched_runtime_sides", [])
    normalized.setdefault("side_mismatch_runtime_instance_ids", [])
    if _runtime_coverage_side_mismatch(normalized, side):
        mismatched_side = str(
            normalized.get("side") or normalized.get("expected_side") or ""
        )
        matched_runtime_sides = list(normalized.get("matched_runtime_sides") or [])
        if mismatched_side and mismatched_side not in matched_runtime_sides:
            matched_runtime_sides.append(mismatched_side)
        normalized["matched_runtime_sides"] = sorted(
            str(item) for item in matched_runtime_sides if str(item or "")
        )
        normalized["side"] = side
        normalized["expected_side"] = side
        normalized["state"] = "runtime_profile_scope_missing"
        normalized["blocker_class"] = "runtime_profile_scope_missing"
        normalized["selected_runtime_instance_ids"] = []
        normalized["next_action"] = "bind_or_repair_runtime_profile_scope_side"
    normalized.setdefault(
        "next_action",
        "bind_or_start_pretrade_runtime_for_candidate_symbol",
    )
    normalized.setdefault("authority_boundary", AUTHORITY_BOUNDARY)
    return normalized


def _symbol_readiness_row(
    *,
    strategy_group_id: str,
    symbol: str,
    side: str,
    candidate: dict[str, Any],
    daily_row: dict[str, Any],
    tradeability_row: dict[str, Any],
    parity_row: dict[str, Any],
    action_row: dict[str, Any],
    runtime_coverage_row: dict[str, Any],
    owner_pretrade_authorization: dict[str, Any],
) -> dict[str, Any]:
    candidate_side = str(side or "")
    runtime_active = _server_runtime_scope_ready(
        runtime_coverage_row,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=candidate_side,
    )
    detector_ready = parity_row.get("detector_attached") is True
    watcher_present = (
        parity_row.get("watcher_tick_present") is True
        if parity_row
        else runtime_active
    )
    computed = parity_row.get("computed") is True
    failed_facts = [
        str(item)
        for item in parity_row.get("failed_facts", [])
        if isinstance(item, str)
    ]
    public_facts_state = _public_facts_state(
        parity_row=parity_row,
        computed=computed,
        failed_facts=failed_facts,
    )
    strategy_signal_fact_side_scope = _strategy_signal_fact_side_scope(
        strategy_group_id,
        owner_pretrade_authorization,
    )
    strategy_signal_fact_side_supported = _strategy_signal_fact_side_supported(
        strategy_group_id,
        candidate_side,
        owner_pretrade_authorization,
    )
    fresh_signal_timestamp_utc = _fresh_signal_timestamp(action_row, parity_row)
    fresh_signal_timestamp_source = _fresh_signal_timestamp_source(
        action_row,
        parity_row,
    )
    signal_state = _signal_state(action_row, parity_row)
    scope_state = _scope_state(
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=candidate_side,
        candidate=candidate,
        daily_row=daily_row,
        tradeability_row=tradeability_row,
        owner_pretrade_authorization=owner_pretrade_authorization,
    )
    owner_authorization = _symbol_owner_authorization(
        owner_pretrade_authorization,
        strategy_group_id,
        symbol,
        candidate_side,
    )
    risk_state = _risk_state(parity_row)
    runtime_profile_ready = _runtime_profile_ready(runtime_coverage_row)
    action_time_scope_missing = (
        scope_state in ACTION_TIME_SCOPE_STATES
        and public_facts_state["state"] == "satisfied"
        and not runtime_active
    )
    first_blocker = _symbol_first_blocker(
        candidate=candidate,
        action_row=action_row,
        parity_row=parity_row,
        detector_ready=detector_ready,
        watcher_present=watcher_present,
        public_facts_state=public_facts_state,
        signal_state=signal_state,
        scope_state=scope_state,
        risk_state=risk_state,
        runtime_scope_missing=action_time_scope_missing,
    )
    if str(daily_row.get("first_blocker") or "") == EVENT_EXECUTION_CAPABILITY_NOT_CERTIFIED:
        first_blocker = EVENT_EXECUTION_CAPABILITY_NOT_CERTIFIED
    if first_blocker == "action_time_preflight_ready" and not runtime_profile_ready:
        first_blocker = "runtime_profile_scope_missing"
    if (
        first_blocker == "action_time_preflight_ready"
        and not strategy_signal_fact_side_supported
    ):
        first_blocker = "runtime_profile_scope_missing"
    promotion_state = _promotion_state(
        public_facts_state=public_facts_state,
        signal_state=signal_state,
        scope_state=scope_state,
        risk_state=risk_state,
        first_blocker=first_blocker,
        runtime_scope_missing=action_time_scope_missing,
    )
    return {
        "strategy_group_id": strategy_group_id,
        "symbol_or_basket": symbol,
        "symbol": symbol,
        "asset_class": "crypto_perpetual",
        "side": candidate_side,
        "candidate_role": _candidate_role(strategy_group_id, symbol),
        "observation_scope": (
            "active_observation" if watcher_present else "readonly"
        ),
        "detector_state": "ready" if detector_ready else "missing",
        "watcher_state": "fresh" if watcher_present else "missing",
        "public_facts_state": public_facts_state,
        "signal_state": signal_state,
        "fresh_signal_timestamp_utc": fresh_signal_timestamp_utc,
        "fresh_signal_timestamp_source": fresh_signal_timestamp_source,
        "risk_state": risk_state,
        "scope_state": scope_state,
        "owner_authorization": owner_authorization,
        "promotion_state": promotion_state,
        "first_blocker": first_blocker,
        "first_blocker_detail": str(
            parity_row.get("first_blocker_detail")
            or action_row.get("first_blocker_detail")
            or ""
        ),
        "next_action": _symbol_next_action(first_blocker, candidate, action_row),
        "stop_condition": _symbol_stop_condition(first_blocker),
        "evidence_ref": _symbol_evidence_ref(
            strategy_group_id=strategy_group_id,
            symbol=symbol,
            first_blocker=first_blocker,
            parity_row=parity_row,
            action_row=action_row,
            runtime_coverage_row=runtime_coverage_row,
        ),
        "action_time": _action_time_readiness(action_row),
        "server_runtime_coverage": runtime_coverage_row or {},
        "strategy_signal_fact_side_scope": list(strategy_signal_fact_side_scope),
        "strategy_signal_fact_side_supported": strategy_signal_fact_side_supported,
        "lane_fingerprint": _lane_fingerprint(
            strategy_group_id=strategy_group_id,
            symbol=symbol,
            side=candidate_side,
            signal_state=signal_state,
            fresh_signal_timestamp_utc=fresh_signal_timestamp_utc,
        ),
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def _public_facts_state(
    *, parity_row: dict[str, Any], computed: bool, failed_facts: list[str]
) -> dict[str, Any]:
    if not parity_row:
        return {
            "state": "missing",
            "missing": ["per_symbol_replay_live_parity_row"],
            "computed_not_satisfied": [],
            "satisfied": [],
        }
    if not computed:
        return {
            "state": "missing",
            "missing": ["computed_public_facts"],
            "computed_not_satisfied": [],
            "satisfied": [],
        }
    if failed_facts:
        return {
            "state": "computed_not_satisfied",
            "missing": [],
            "computed_not_satisfied": failed_facts,
            "satisfied": [],
        }
    return {
        "state": "satisfied",
        "missing": [],
        "computed_not_satisfied": [],
        "satisfied": ["strategy_public_fact_matrix"],
    }


def _signal_state(action_row: dict[str, Any], parity_row: dict[str, Any] | None = None) -> str:
    if _fresh_signal_present(action_row, parity_row):
        if _fresh_signal_timestamp(action_row, _as_dict(parity_row)):
            return "fresh"
        return "invalidated"
    if _as_dict(parity_row).get("fresh_signal_present") is True:
        return "invalidated"
    if action_row.get("fresh_signal_present") is True:
        return "invalidated"
    if action_row.get("fresh_signal_present") is False:
        return "absent"
    if _as_dict(parity_row).get("fresh_signal_present") is False:
        return "absent"
    if _as_dict(parity_row).get("blocker_class") == "market_wait_validated":
        return "absent"
    if _as_dict(parity_row).get("blocker_class") == "computed_not_satisfied":
        return "absent"
    blocker = str(action_row.get("first_blocker") or "")
    if not action_row:
        return "absent"
    if "stale" in blocker:
        return "stale"
    if blocker.startswith("fresh_") and blocker.endswith("_absent"):
        return "absent"
    return "absent"


def _fresh_signal_present(
    action_row: dict[str, Any],
    parity_row: dict[str, Any] | None = None,
) -> bool:
    if _as_dict(parity_row).get("fresh_signal_present") is True:
        return True
    return action_row.get("fresh_signal_present") is True


def _scope_state(
    *,
    strategy_group_id: str,
    symbol: str,
    side: str,
    candidate: dict[str, Any],
    daily_row: dict[str, Any],
    tradeability_row: dict[str, Any],
    owner_pretrade_authorization: dict[str, Any],
) -> str:
    owner_authorization = _symbol_owner_authorization(
        owner_pretrade_authorization,
        strategy_group_id,
        symbol,
        side,
    )
    if (
        owner_authorization.get("pretrade_candidate_allowed") is True
        and owner_authorization.get("action_time_rehearsal_allowed") is True
        and owner_authorization.get("live_submit_allowed") == "scoped"
    ):
        return "live_submit_allowed"
    if (
        owner_authorization.get("pretrade_candidate_allowed") is True
        and owner_authorization.get("action_time_rehearsal_allowed") is True
        and owner_authorization.get("live_submit_allowed")
        == "conditional_hard_gated"
    ):
        return "conditional_action_time_rehearsal_allowed"
    return "readonly_only"


def _risk_state(parity_row: dict[str, Any]) -> str:
    failed = {
        str(item)
        for item in parity_row.get("failed_facts", [])
        if isinstance(item, str)
    }
    if failed & {"funding_not_extreme", "spread_ok", "liquidity_ok", "squeeze_disable"}:
        return "warning"
    return "acceptable"


def _symbol_first_blocker(
    *,
    candidate: dict[str, Any],
    action_row: dict[str, Any],
    parity_row: dict[str, Any],
    detector_ready: bool,
    watcher_present: bool,
    public_facts_state: dict[str, Any],
    signal_state: str,
    scope_state: str,
    risk_state: str,
    runtime_scope_missing: bool = False,
) -> str:
    if runtime_scope_missing:
        return "runtime_profile_scope_missing"
    if not detector_ready:
        return "detector_not_attached"
    if public_facts_state["state"] == "computed_not_satisfied":
        return "computed_not_satisfied"
    if not watcher_present:
        return "watcher_tick_missing"
    if public_facts_state["state"] == "missing":
        return "artifact_missing"
    if risk_state == "disable":
        return "hard_safety_stop"
    if signal_state == "fresh" and scope_state == "readonly_only":
        return "scope_not_attached"
    if signal_state == "fresh" and scope_state in ACTION_TIME_SCOPE_STATES:
        return _fresh_action_time_blocker(action_row)
    if signal_state == "fresh":
        return "runtime_profile_scope_missing"
    return str(parity_row.get("blocker_class") or candidate.get("first_blocker") or "computed_not_satisfied")


def _fresh_action_time_blocker(action_row: dict[str, Any]) -> str:
    readiness = _as_dict(action_row.get("required_facts_readiness"))
    if action_row.get("action_time_path_ready") is not True:
        return "action_time_boundary_not_reproduced"
    if readiness.get("public_facts_ready") is not True:
        return "action_time_boundary_not_reproduced"
    if readiness.get("private_action_time_facts_ready") is not True:
        return "action_time_boundary_not_reproduced"
    if readiness.get("active_position_or_open_order_clear") is not True:
        return "active_position_resolution"
    if readiness.get("action_time_available_balance") is not True:
        return "action_time_boundary_not_reproduced"
    return "action_time_preflight_ready"


def _promotion_state(
    *,
    public_facts_state: dict[str, Any],
    signal_state: str,
    scope_state: str,
    risk_state: str,
    first_blocker: str,
    runtime_scope_missing: bool = False,
) -> str:
    if runtime_scope_missing:
        return "idle"
    if signal_state != "fresh" or public_facts_state["state"] != "satisfied":
        return "idle"
    if risk_state == "disable":
        return "blocked"
    if scope_state in ACTION_TIME_SCOPE_STATES:
        if first_blocker in ACTION_TIME_INPUT_BLOCKERS:
            return "idle"
        return "action_time_lane"
    return "promotion_candidate"


def _symbol_next_action(
    first_blocker: str,
    candidate: dict[str, Any],
    action_row: dict[str, Any] | None = None,
) -> str:
    action_next = str(_as_dict(action_row).get("next_action") or "")
    if (
        first_blocker == "action_time_preflight_ready"
        and _action_time_private_facts_ready(_as_dict(action_row))
    ):
        return "prepare_non_executing_finalgate_preflight_input"
    if (
        first_blocker == "action_time_boundary_not_reproduced"
        and action_next
        and action_next != "wait_for_fresh_signal_then_refresh_private_action_time_facts"
    ):
        return action_next
    if (
        first_blocker == "market_wait_validated"
        and action_next
        and action_next != "wait_for_fresh_signal_then_refresh_private_action_time_facts"
    ):
        return action_next
    return {
        "detector_not_attached": "attach_detector_for_candidate_symbol",
        "watcher_tick_missing": "refresh_readonly_watcher_for_candidate_symbol",
        "artifact_missing": "produce_per_symbol_readiness_evidence",
        "computed_not_satisfied": "continue_observation_with_failed_fact_matrix",
        "scope_not_attached": "produce_scoped_live_observation_or_scope_proposal",
        "runtime_profile_scope_missing": (
            "bind_or_start_pretrade_runtime_for_candidate_symbol"
        ),
        EVENT_EXECUTION_CAPABILITY_NOT_CERTIFIED: (
            "certify_event_execution_capability_or_keep_observe_only"
        ),
        "action_time_boundary_not_reproduced": (
            "repair_non_executing_action_time_rehearsal_path"
        ),
        "action_time_preflight_ready": (
            "prepare_non_executing_finalgate_preflight_input"
        ),
        "market_wait_validated": "continue_watcher_observation_until_fresh_signal",
        "hard_safety_stop": "resolve_hard_safety_stop",
    }.get(first_blocker, str(candidate.get("next_engineering_action") or "reclassify_symbol_blocker"))


def _symbol_stop_condition(first_blocker: str) -> str:
    if first_blocker == "market_wait_validated":
        return "fresh signal expires or action-time lane is selected"
    if first_blocker == "action_time_preflight_ready":
        return "preflight input is prepared, stale facts appear, or lane is reclassified"
    if first_blocker == "scope_not_attached":
        return "scope proposal accepted, explicitly deferred, or symbol parked"
    return "blocker moves, repeats through stop review, or symbol exits candidate universe"


def _symbol_evidence_ref(
    *,
    strategy_group_id: str,
    symbol: str,
    first_blocker: str,
    parity_row: dict[str, Any],
    action_row: dict[str, Any],
    runtime_coverage_row: dict[str, Any] | None = None,
) -> str:
    if runtime_coverage_row and runtime_coverage_row.get("blocker_class") == first_blocker:
        return (
            "pg_watcher_runtime_coverage:candidate_universe_coverage:"
            f"{strategy_group_id}/{symbol} first_blocker={first_blocker}"
        )
    if first_blocker == "runtime_profile_scope_missing" and not runtime_coverage_row:
        return (
            "pg_watcher_runtime_coverage:candidate_universe_coverage:"
            f"{strategy_group_id}/{symbol} missing_active_watcher_scope"
        )
    if parity_row:
        evidence_source = str(parity_row.get("evidence_source") or "")
        if evidence_source:
            return (
                f"{evidence_source}:{strategy_group_id}/{symbol} "
                f"first_blocker={first_blocker}"
            )
        source_blocker = str(parity_row.get("blocker_class") or "")
        source_detail = (
            f" source_blocker_class={source_blocker}"
            if source_blocker != first_blocker
            else ""
        )
        return (
            "replay_live_parity_input:"
            f"{strategy_group_id}/{symbol} first_blocker={first_blocker}"
            f"{source_detail} watcher_tick_present={parity_row.get('watcher_tick_present')}"
        )
    if action_row and (
        action_row.get("strategy_group_id")
        or action_row.get("first_blocker")
        or action_row.get("action_time_path_ready") is not None
    ):
        return (
            "action_time_boundary_input:"
            f"{strategy_group_id}/{symbol} first_blocker={action_row.get('first_blocker')}"
        )
    return f"owner_pretrade_authorization_scope:{strategy_group_id}/{symbol}"


def _runtime_coverage(runtime_active_monitor: dict[str, Any]) -> dict[str, Any]:
    coverage = runtime_active_monitor.get("candidate_universe_coverage")
    if isinstance(coverage, dict):
        return coverage
    latest = runtime_active_monitor.get("latest_summary")
    if isinstance(latest, dict):
        coverage = latest.get("candidate_universe_coverage")
        if isinstance(coverage, dict):
            return coverage
    return {}


def _server_runtime_scope_ready(
    runtime_coverage_row: dict[str, Any],
    *,
    strategy_group_id: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
) -> bool:
    active_ids = runtime_coverage_row.get("active_runtime_instance_ids") or []
    selected_ids = runtime_coverage_row.get("selected_runtime_instance_ids") or []
    if str(runtime_coverage_row.get("state") or "") != "active_watcher_scope":
        return False
    if not active_ids or not selected_ids:
        return False
    if strategy_group_id is not None and (
        str(runtime_coverage_row.get("strategy_group_id") or "") != strategy_group_id
    ):
        return False
    if symbol is not None and str(runtime_coverage_row.get("symbol") or "") != symbol:
        return False
    coverage_side = str(
        runtime_coverage_row.get("side")
        or runtime_coverage_row.get("expected_side")
        or ""
    )
    if side is not None and coverage_side != side:
        return False
    return True


def _strategy_signal_fact_side_scope(
    strategy_group_id: str,
    owner_pretrade_authorization: dict[str, Any],
) -> tuple[str, ...]:
    if _owner_authorization_valid(owner_pretrade_authorization):
        return _candidate_side_scope(strategy_group_id, owner_pretrade_authorization)
    return ()


def _strategy_signal_fact_side_supported(
    strategy_group_id: str,
    side: str,
    owner_pretrade_authorization: dict[str, Any],
) -> bool:
    return str(side or "").lower() in set(
        _strategy_signal_fact_side_scope(
            strategy_group_id,
            owner_pretrade_authorization,
        )
    )


def _fresh_signal_timestamp(
    action_row: dict[str, Any],
    parity_row: dict[str, Any],
) -> str:
    if parity_row.get("fresh_signal_present") is True:
        for key in FRESH_SIGNAL_TIMESTAMP_KEYS:
            value = parity_row.get(key)
            if str(value or "").strip():
                return str(value)
    if action_row.get("fresh_signal_present") is True:
        for key in FRESH_SIGNAL_TIMESTAMP_KEYS:
            value = action_row.get(key)
            if str(value or "").strip():
                return str(value)
    return ""


def _fresh_signal_timestamp_source(
    action_row: dict[str, Any],
    parity_row: dict[str, Any],
) -> str:
    if parity_row.get("fresh_signal_present") is True:
        for key in FRESH_SIGNAL_TIMESTAMP_KEYS:
            if str(parity_row.get(key) or "").strip():
                return f"parity_row:{key}"
    if action_row.get("fresh_signal_present") is True:
        for key in FRESH_SIGNAL_TIMESTAMP_KEYS:
            if str(action_row.get(key) or "").strip():
                return f"action_time_boundary:{key}"
    return ""


def _lane_fingerprint(
    *,
    strategy_group_id: str,
    symbol: str,
    side: str,
    signal_state: str,
    fresh_signal_timestamp_utc: str,
) -> str:
    seed = "|".join(
        [
            strategy_group_id,
            symbol,
            side,
            signal_state,
            fresh_signal_timestamp_utc,
        ]
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _runtime_profile(row: dict[str, Any]) -> dict[str, Any]:
    coverage = _as_dict(row.get("server_runtime_coverage"))
    profile = _as_dict(coverage.get("runtime_profile"))
    max_notional = (
        profile.get("max_notional")
        or profile.get("max_notional_usdt")
        or profile.get("max_notional_per_action_usdt")
        or coverage.get("max_notional")
        or coverage.get("max_notional_usdt")
        or coverage.get("max_notional_per_action_usdt")
    )
    target_notional = (
        profile.get("target_notional_usdt")
        or profile.get("target_notional")
        or coverage.get("target_notional_usdt")
        or coverage.get("target_notional")
        or max_notional
    )
    leverage = (
        profile.get("leverage")
        or profile.get("max_leverage")
        or coverage.get("leverage")
        or coverage.get("max_leverage")
    )
    runtime_profile_id = (
        profile.get("runtime_profile_id")
        or profile.get("profile_id")
        or coverage.get("runtime_profile_id")
        or coverage.get("profile_id")
    )
    return {
        "runtime_profile_id": str(runtime_profile_id or ""),
        "target_notional_usdt": str(target_notional or ""),
        "max_notional": str(max_notional or ""),
        "leverage": str(leverage or ""),
        "profile_source": (
            "server_runtime_coverage"
            if any([runtime_profile_id, target_notional, max_notional, leverage])
            else "missing_runtime_profile_boundary"
        ),
        "authority_boundary": (
            "selected_runtime_profile_boundary_only; "
            "no_live_profile_or_sizing_change"
        ),
    }


def _runtime_profile_ready(runtime_coverage_row: dict[str, Any]) -> bool:
    profile = _runtime_profile({"server_runtime_coverage": runtime_coverage_row})
    return all(
        str(profile.get(key) or "").strip()
        for key in ("target_notional_usdt", "max_notional", "leverage")
    )


def _candidate_role(strategy_group_id: str, symbol: str) -> str:
    if symbol == PRIMARY_SYMBOLS.get(strategy_group_id):
        return "primary"
    if strategy_group_id == "BRF2-001":
        return "conditional"
    return "secondary"


def _symbol_role(strategy_group_id: str, symbol: str) -> int:
    return 0 if symbol == PRIMARY_SYMBOLS.get(strategy_group_id) else 1


def _action_time_lane_input(row: dict[str, Any]) -> dict[str, Any]:
    server_runtime_coverage = _as_dict(row.get("server_runtime_coverage"))
    runtime_profile = _runtime_profile(row)
    return {
        "strategy_group_id": row["strategy_group_id"],
        "symbol": row["symbol"],
        "side": row["side"],
        "fresh_signal_timestamp_utc": row.get("fresh_signal_timestamp_utc") or "",
        "fresh_signal_timestamp_source": row.get("fresh_signal_timestamp_source") or "",
        "lane_fingerprint": row.get("lane_fingerprint") or "",
        "active_runtime_instance_ids": list(
            server_runtime_coverage.get("active_runtime_instance_ids") or []
        ),
        "selected_runtime_instance_ids": list(
            server_runtime_coverage.get("selected_runtime_instance_ids") or []
        ),
        "server_runtime_coverage": server_runtime_coverage,
        "runtime_profile": runtime_profile,
        "scope_state": row["scope_state"],
        "owner_authorization": row["owner_authorization"],
        "first_blocker": row["first_blocker"],
        "next_action": row["next_action"],
        "signal_state": row["signal_state"],
        "public_facts_state": row["public_facts_state"],
        "strategy_signal_fact_side_scope": list(
            row.get("strategy_signal_fact_side_scope") or []
        ),
        "strategy_signal_fact_side_supported": row.get(
            "strategy_signal_fact_side_supported"
        )
        is True,
        "risk_state": row["risk_state"],
        "action_time": row["action_time"],
        "authority_boundary": (
            "action_time_lane_input_is_non_executing; "
            "no_finalgate_no_operation_layer_no_exchange_write"
        ),
    }


def _select_action_time_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return sorted(
        rows,
        key=lambda row: (
            _strategy_priority(str(row.get("strategy_group_id") or "")),
            str(row.get("symbol") or ""),
            str(row.get("side") or ""),
        ),
    )[0]


def _arbitration(
    *,
    promotion_candidates: list[dict[str, Any]],
    eligible_action_time_rows: list[dict[str, Any]],
    selected_action_time_row: dict[str, Any] | None,
) -> dict[str, Any]:
    selected = ""
    deferred: list[dict[str, str]] = []
    if selected_action_time_row:
        sorted_inputs = [selected_action_time_row]
        selected = (
            f"{sorted_inputs[0]['strategy_group_id']}:{sorted_inputs[0]['symbol']}:"
            f"{sorted_inputs[0]['side']}"
        )
    for row in eligible_action_time_rows:
        if row is selected_action_time_row:
            continue
        deferred.append(
            {
                "strategy_group_id": str(row.get("strategy_group_id") or ""),
                "symbol": str(row.get("symbol") or ""),
                "side": str(row.get("side") or ""),
                "reason": "deferred_by_single_action_time_candidate_rule",
            }
        )
    return {
        "promotion_candidate_count": len(promotion_candidates),
        "eligible_action_time_candidate_count": len(eligible_action_time_rows),
        "action_time_lane_input_count": 1 if selected_action_time_row else 0,
        "selected_action_time_candidate": selected or "none",
        "deferred_action_time_candidates": deferred,
        "single_real_submit_candidate": True,
        "rule": (
            "multiple promotion candidates may exist; real submit path may select "
            "at most one action-time candidate"
        ),
    }


def _strategy_priority(strategy_group_id: str) -> int:
    return {strategy_group_id: index for index, strategy_group_id in enumerate(WIP_LANES)}.get(
        strategy_group_id, 99
    )


def _no_trade_audit(
    *,
    symbol_readiness_rows: list[dict[str, Any]],
    action_time_lane_inputs: list[dict[str, Any]],
    arbitration: dict[str, Any],
) -> dict[str, Any]:
    blocker_counts: dict[str, int] = {}
    for row in symbol_readiness_rows:
        blocker = str(row.get("first_blocker") or "unknown")
        blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
    return {
        "status": (
            "action_time_candidate_present"
            if action_time_lane_inputs
            else "no_action_time_candidate"
        ),
        "reason": (
            "one_or_more_live_scope_candidates_can_enter_action_time"
            if action_time_lane_inputs
            else "candidate_pool_has_no_live_submit_allowed_fresh_satisfied_symbol"
        ),
        "blocker_counts": blocker_counts,
        "selected_action_time_candidate": arbitration["selected_action_time_candidate"],
    }


def _residual_deploy_blockers(candidate_rows: list[dict[str, Any]]) -> list[str]:
    residual: list[str] = []
    for row in candidate_rows:
        strategy_group_id = str(row.get("strategy_group_id") or "")
        first_blocker = str(row.get("first_blocker") or "")
        if first_blocker in RESIDUAL_DEPLOY_BLOCKERS:
            residual.append(f"{strategy_group_id}:{first_blocker}")
        readiness_status = str(
            _as_dict(row.get("action_time_readiness")).get("status") or ""
        )
        if readiness_status in ACTION_TIME_BLOCKED_STATUSES:
            residual.append(f"{strategy_group_id}:action_time:{readiness_status}")
    return residual


def _candidate_universe(
    symbol_readiness_rows: list[dict[str, Any]],
) -> dict[str, list[str]]:
    universe: dict[str, list[str]] = {}
    for row in symbol_readiness_rows:
        universe.setdefault(row["strategy_group_id"], []).append(row["symbol"])
    return {key: sorted(set(values)) for key, values in universe.items()}


def _candidate_lane_universe(
    symbol_readiness_rows: list[dict[str, Any]],
) -> dict[str, list[str]]:
    universe: dict[str, list[dict[str, str]]] = {}
    for row in symbol_readiness_rows:
        universe.setdefault(row["strategy_group_id"], []).append(
            {"symbol": row["symbol"], "side": row["side"]}
        )
    return {
        key: sorted(
            {f"{item['symbol']}:{item['side']}" for item in values},
            key=lambda item: tuple(item.split(":", 1)),
        )
        for key, values in universe.items()
    }


def _candidate_row(
    *,
    strategy_group_id: str,
    daily_row: dict[str, Any],
    tradeability_row: dict[str, Any],
    action_row: dict[str, Any],
) -> dict[str, Any]:
    first_blocker = str(daily_row.get("first_blocker") or "artifact_missing")
    selected_symbol = str(daily_row.get("symbol") or "strategy_scope")
    return {
        "strategy_group_id": strategy_group_id,
        "candidate_status": _candidate_status(strategy_group_id, first_blocker),
        "candidate_positioning": CANDIDATE_POSITIONING.get(
            strategy_group_id, "live candidate"
        ),
        "selected_symbol": selected_symbol,
        "side": str(daily_row.get("side") or "unknown"),
        "stage": str(daily_row.get("stage") or "unknown"),
        "daily_rank": int(daily_row.get("closest_to_live_rank") or 0),
        "first_blocker": first_blocker,
        "blocker_owner": str(
            tradeability_row.get("blocker_owner")
            or _blocker_owner(first_blocker)
        ),
        "evidence": str(daily_row.get("first_blocker_evidence") or ""),
        "next_engineering_action": str(
            daily_row.get("next_engineering_action") or ""
        ),
        "trigger_condition": _trigger_condition(strategy_group_id, selected_symbol),
        "market_condition": _market_condition(strategy_group_id, first_blocker),
        "action_time_readiness": _action_time_readiness(action_row),
        "stop_condition": str(daily_row.get("stop_condition") or ""),
        "exit_condition": _exit_condition(strategy_group_id, first_blocker),
        "owner_action_required": str(daily_row.get("owner_action_required") or "no"),
        "authority_boundary": DAILY_AUTHORITY_BOUNDARY,
    }


def _sync_candidate_rows_with_symbol_readiness(
    candidate_rows: list[dict[str, Any]],
    symbol_readiness_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_strategy: dict[str, list[dict[str, Any]]] = {}
    for row in symbol_readiness_rows:
        by_strategy.setdefault(str(row.get("strategy_group_id") or ""), []).append(row)

    synced: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        strategy_group_id = str(candidate.get("strategy_group_id") or "")
        summary = _strategy_summary_symbol_row(
            strategy_group_id,
            by_strategy.get(strategy_group_id, []),
        )
        if not summary or not _server_runtime_scope_ready(
            _as_dict(summary.get("server_runtime_coverage")),
            strategy_group_id=str(summary.get("strategy_group_id") or ""),
            symbol=str(summary.get("symbol") or ""),
            side=str(summary.get("side") or ""),
        ):
            synced.append(candidate)
            continue
        first_blocker = str(summary.get("first_blocker") or candidate["first_blocker"])
        selected_symbol = str(summary.get("symbol") or candidate["selected_symbol"])
        updated = dict(candidate)
        updated.update(
            {
                "candidate_status": _candidate_status(strategy_group_id, first_blocker),
                "selected_symbol": selected_symbol,
                "side": str(summary.get("side") or candidate["side"]),
                "first_blocker": first_blocker,
                "first_blocker_detail": str(
                    summary.get("first_blocker_detail")
                    or candidate.get("first_blocker_detail")
                    or ""
                ),
                "blocker_owner": _blocker_owner(first_blocker),
                "evidence": str(summary.get("evidence_ref") or candidate["evidence"]),
                "next_engineering_action": str(
                    summary.get("next_action")
                    or candidate["next_engineering_action"]
                ),
                "trigger_condition": _trigger_condition(
                    strategy_group_id,
                    selected_symbol,
                ),
                "market_condition": _market_condition(strategy_group_id, first_blocker),
                "action_time_readiness": summary.get("action_time")
                or candidate["action_time_readiness"],
                "stop_condition": str(
                    summary.get("stop_condition") or candidate["stop_condition"]
                ),
                "exit_condition": _exit_condition(strategy_group_id, first_blocker),
            }
        )
        synced.append(updated)
    return synced


def _strategy_summary_symbol_row(
    strategy_group_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not rows:
        return {}
    promotion_priority = {
        "action_time_lane": 0,
        "promotion_candidate": 1,
        "blocked": 2,
        "idle": 3,
    }
    return sorted(
        rows,
        key=lambda row: (
            promotion_priority.get(str(row.get("promotion_state") or ""), 9),
            _symbol_role(strategy_group_id, str(row.get("symbol") or "")),
            str(row.get("symbol") or ""),
            str(row.get("side") or ""),
        ),
    )[0]


def _candidate_status(strategy_group_id: str, first_blocker: str) -> str:
    if strategy_group_id == "BRF2-001" and first_blocker == "computed_not_satisfied":
        return "candidate_conditional_observation"
    return {
        "watcher_tick_missing": "candidate_runtime_input_blocked",
        "scope_not_attached": "candidate_scope_decision_pending",
        "computed_not_satisfied": "candidate_market_condition_wait",
        "market_wait_validated": "candidate_market_wait_validated",
        "action_time_preflight_ready": "candidate_action_time_preflight_ready",
        "policy_scope_missing": "candidate_owner_policy_pending",
        "hard_safety_stop": "candidate_safety_blocked",
    }.get(first_blocker, "candidate_engineering_blocked")


def _blocker_owner(first_blocker: str) -> str:
    if first_blocker in {"computed_not_satisfied", "market_wait_validated"}:
        return "market"
    if first_blocker == "action_time_preflight_ready":
        return "engineering"
    if first_blocker == "policy_scope_missing":
        return "owner"
    if first_blocker == "hard_safety_stop":
        return "safety"
    if first_blocker == "watcher_tick_missing":
        return "runtime"
    return "engineering"


def _trigger_condition(strategy_group_id: str, symbol: str) -> str:
    return {
        "MPG-001": f"{symbol} selective leader continuation signal with fresh public facts",
        "CPM-RO-001": f"{symbol} pullback reclaim signal with htf_trend_intact and reclaim_confirmed",
        "MI-001": f"{symbol} relative strength admission and scoped observation lane accepted",
        "SOR-001": f"{symbol} session opening range plus breakout and follow-through confirmation",
        "BRF2-001": "failed-rebound short setup after squeeze / strong-uptrend disable clears",
    }.get(strategy_group_id, "fresh eligible signal under selected StrategyGroup rules")


def _market_condition(strategy_group_id: str, first_blocker: str) -> str:
    if first_blocker == "watcher_tick_missing":
        return "public market facts must refresh before market condition can be trusted"
    if strategy_group_id == "BRF2-001":
        return "conditional short only when bullish/squeeze disable state clears"
    if first_blocker == "computed_not_satisfied":
        return "strategy fact matrix must clear on the next detector tick"
    if first_blocker == "scope_not_attached":
        return "market condition is secondary until scope/admission is attached"
    return "selected lane must satisfy its fresh eligible signal contract"


def _action_time_readiness(action_row: dict[str, Any]) -> dict[str, Any]:
    if not action_row:
        return {
            "status": "not_applicable_current_stage",
            "action_time_path_ready": False,
            "action_time_capability_certified": False,
            "action_time_capability_reason": "action_time_boundary_row_missing",
            "public_facts_ready": False,
            "private_action_time_facts_ready": False,
        }
    readiness = _as_dict(action_row.get("required_facts_readiness"))
    path_ready = action_row.get("action_time_path_ready") is True
    public_ready = readiness.get("public_facts_ready") is True
    private_ready = _action_time_private_facts_ready(action_row)
    if not public_ready:
        status = "blocked_public_facts"
    elif path_ready and private_ready:
        status = "ready_for_finalgate_preflight"
    elif path_ready:
        status = "ready_for_private_action_time_facts"
    else:
        status = "blocked_action_time_rehearsal"
    return {
        "status": status,
        "action_time_path_ready": path_ready,
        "action_time_capability_certified": (
            action_row.get("action_time_capability_certified") is True
        ),
        "action_time_capability_reason": str(
            action_row.get("action_time_capability_reason") or ""
        ),
        "action_time_capability_source_watermark": str(
            action_row.get("action_time_capability_source_watermark") or ""
        ),
        "action_time_capability_runtime_head": str(
            action_row.get("action_time_capability_runtime_head") or ""
        ),
        "public_facts_ready": public_ready,
        "private_action_time_facts_ready": private_ready,
        "first_blocker": str(action_row.get("first_blocker") or ""),
        "next_action": str(action_row.get("next_action") or ""),
    }


def _action_time_private_facts_ready(action_row: dict[str, Any]) -> bool:
    readiness = _as_dict(action_row.get("required_facts_readiness"))
    return (
        readiness.get("private_action_time_facts_ready") is True
        and readiness.get("active_position_or_open_order_clear") is True
        and readiness.get("action_time_available_balance") is True
    )


def _exit_condition(strategy_group_id: str, first_blocker: str) -> str:
    if strategy_group_id == "BRF2-001":
        return "exit mainline if bullish/squeeze disable remains active through the stop review window"
    if first_blocker == "scope_not_attached":
        return "exit or support-only if scoped admission is rejected"
    if first_blocker == "computed_not_satisfied":
        return "exit if repeated detector windows keep failing the same fact matrix"
    if first_blocker == "watcher_tick_missing":
        return "exit or downgrade if public facts cannot be refreshed through approved read-only paths"
    return "exit under WIP stop rule if blocker does not move"


def _p0_p1_review(
    candidate_rows: list[dict[str, Any]],
    source_validation: dict[str, Any],
) -> list[dict[str, Any]]:
    by_strategy = {row["strategy_group_id"]: row for row in candidate_rows}
    result: list[dict[str, Any]] = []
    for priority, item in P0_P1_ITEMS:
        status, evidence, next_action = _p0_p1_status(item, by_strategy, source_validation)
        result.append(
            {
                "priority": priority,
                "item": item,
                "status": status,
                "evidence": evidence,
                "next_action": next_action,
            }
        )
    return result


def _p0_p1_status(
    item: str,
    by_strategy: dict[str, dict[str, Any]],
    source_validation: dict[str, Any],
) -> tuple[str, str, str]:
    if item == "five_strategy_candidate_pool_control_surface":
        complete = len(by_strategy) == len(WIP_LANES) and all(
            _candidate_row_complete(row) for row in by_strategy.values()
        )
        return (
            "cleared" if complete else "open",
            "candidate_rows contain required fields for all active WIP lanes",
            "complete missing candidate fields",
        )
    if item == "mpg_watcher_closure":
        row = by_strategy.get("MPG-001", {})
        blocker = row.get("first_blocker")
        return (
            "open"
            if blocker in {"watcher_tick_missing", "scope_not_attached"}
            else "cleared",
            f"MPG-001 first_blocker={blocker}",
            row.get("next_engineering_action") or "refresh MPG public facts",
        )
    if item == "sor_watcher_closure":
        row = by_strategy.get("SOR-001", {})
        blocker = row.get("first_blocker")
        return (
            "open"
            if blocker in {"watcher_tick_missing", "scope_not_attached"}
            else "cleared",
            f"SOR-001 first_blocker={blocker}",
            row.get("next_engineering_action") or "refresh SOR public facts",
        )
    if item == "mi_scope_closure":
        row = by_strategy.get("MI-001", {})
        blocker = row.get("first_blocker")
        return (
            "open"
            if blocker in {"scope_not_attached", "policy_scope_missing"}
            else "cleared",
            f"MI-001 first_blocker={blocker}",
            row.get("next_engineering_action") or "close MI scope/admission",
        )
    if item == "cpm_computed_refresh":
        row = by_strategy.get("CPM-RO-001", {})
        blocker = row.get("first_blocker")
        return (
            "cleared"
            if blocker
            in {
                "computed_not_satisfied",
                "market_wait_validated",
                "action_time_boundary_not_reproduced",
            }
            else "open",
            f"CPM-RO-001 first_blocker={blocker}",
            row.get("next_engineering_action") or "refresh CPM detector facts",
        )
    if item == "brf2_conditionalization":
        row = by_strategy.get("BRF2-001", {})
        return (
            "cleared"
            if row.get("candidate_status") == "candidate_conditional_observation"
            else "open",
            f"BRF2-001 candidate_status={row.get('candidate_status')}",
            "keep BRF2 conditional or exit under stop review",
        )
    if item == "no_authority_leakage":
        return ("cleared", "candidate pool is non-executing", "preserve authority boundary")
    if item == "candidate_pool_validator":
        return ("cleared", "validator script is present and must pass", "run validator")
    if item == "output_whitelist_gate":
        return (
            "cleared",
            "deploy gate reruns validate_output_artifact_scope.py --git-status to reject routine output commits",
            "run validate_output_artifact_scope.py --git-status",
        )
    if item == "no_stale_facts":
        watcher_missing = [
            row["strategy_group_id"]
            for row in by_strategy.values()
            if row.get("first_blocker") == "watcher_tick_missing"
        ]
        blocked_public = [
            row["strategy_group_id"]
            for row in by_strategy.values()
            if _as_dict(row.get("action_time_readiness")).get("status")
            == "blocked_public_facts"
        ]
        if watcher_missing:
            return (
                "open",
                "watcher_tick_missing rows prove public facts are not current: "
                + ",".join(sorted(watcher_missing)),
                "refresh approved public facts path",
            )
        if blocked_public:
            return (
                "waived_with_reason",
                "non-executing deploy may proceed, but action-time public facts "
                "are not cleared for: "
                + ",".join(sorted(blocked_public)),
                "refresh action-time public facts before treating lane as market_wait_validated",
            )
        return (
            "cleared",
            "watcher and action-time public facts are current or not applicable",
            "refresh approved public facts path",
        )
    if item == "review_report":
        return (
            "cleared",
            "candidate pool includes machine-readable p0_p1_review rows",
            "rerun candidate pool after blocker refresh",
        )
    if item == "postdeploy_validation_script":
        deploy_gate = REPO_ROOT / "scripts/validate_strategy_live_candidate_pool_deploy_gate.py"
        return (
            "cleared" if deploy_gate.exists() else "open",
            "deploy gate validator checks candidate pool, Daily Table, Single Lane Packet, "
            "monitor sequence, output scope, and authority leakage",
            "run validate_strategy_live_candidate_pool_deploy_gate.py before deploy",
        )
    return ("open", "unknown review item", "classify review item")


def _candidate_row_complete(row: dict[str, Any]) -> bool:
    required = (
        "candidate_status",
        "selected_symbol",
        "side",
        "first_blocker",
        "blocker_owner",
        "evidence",
        "next_engineering_action",
        "trigger_condition",
        "market_condition",
        "action_time_readiness",
        "stop_condition",
        "exit_condition",
    )
    return all(str(row.get(key) or "") for key in required)


def _source_validation(
    *,
    daily_table: dict[str, Any],
    tradeability: dict[str, Any],
    replay_live_parity: dict[str, Any],
    action_time_boundary: dict[str, Any],
    single_lane_task_packet: dict[str, Any],
) -> dict[str, Any]:
    _ = single_lane_task_packet
    sources = {
        "daily_table": daily_table.get("status") == "daily_live_enablement_table_ready"
        and _as_dict(daily_table.get("source_validation")).get("valid") is True,
        "tradeability": tradeability.get("status") == "tradeability_decision_ready",
        "replay_live_parity": replay_live_parity.get("status")
        == "replay_live_parity_audit_ready",
        "action_time_boundary": action_time_boundary.get("status")
        == "strategy_fresh_signal_action_time_boundary_ready",
    }
    return {
        "valid": all(sources.values()),
        "sources": sources,
    }


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
