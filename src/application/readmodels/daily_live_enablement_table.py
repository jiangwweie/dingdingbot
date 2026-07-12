#!/usr/bin/env python3
"""Build the Daily Live Enablement Table read model.

The table is the single daily control surface for active StrategyGroup live
enablement lanes. It is non-executing and must not create live authority.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
)
from src.application.readmodels.runtime_safety_truth import (  # noqa: E402
    current_runtime_safety_truths,
)

from src.infrastructure.sync_pg_dsn import (  # noqa: E402
    is_sync_postgres_dsn,
    normalize_sync_postgres_dsn,
)

SCHEMA = "brc.daily_live_enablement_table.v1"
WIP_LANES = ("CPM-RO-001", "MPG-001", "MI-001", "SOR-001", "BRF2-001")
WIP_PRIORITY_BONUS = {
    "CPM-RO-001": 20,
    "MPG-001": 20,
    "MI-001": 10,
    "SOR-001": 10,
    "BRF2-001": 0,
}
CONTRACT_BLOCKER_CLASSES = {
    "artifact_missing",
    "schema_invalid",
    "detector_not_attached",
    "watcher_tick_missing",
    "scope_not_attached",
    "computed_not_satisfied",
    "replay_live_rule_mismatch",
    "event_execution_capability_not_certified",
    "action_time_boundary_not_reproduced",
    "policy_scope_missing",
    "runtime_profile_scope_missing",
    "market_wait_validated",
    "action_time_preflight_ready",
    "active_position_resolution",
    "hard_safety_stop",
    "review_only_warning",
}
OWNER_BLOCKERS = {"policy_scope_missing"}
AUTHORITY_BOUNDARY = (
    "daily_table_is_read_model; no_finalgate_no_operation_layer_no_exchange_write"
)
SOURCE_EXPECTATIONS = {
    "tradeability": {
        "schema": "brc.strategygroup_tradeability_decision.v1",
        "statuses": {"tradeability_decision_ready"},
    },
    "replay_live_parity": {
        "schema": "brc.replay_live_parity_audit.v1",
        "statuses": {"replay_live_parity_audit_ready"},
    },
    "action_time_boundary": {
        "schema": "brc.strategy_fresh_signal_action_time_boundary.v1",
        "statuses": {"strategy_fresh_signal_action_time_boundary_ready"},
    },
    "mi_trial_admission": {
        "schema": "brc.mi_trial_admission_decision.v1",
        "statuses": {"mi_trial_admission_decision_ready"},
    },
    "runtime_safety": {
        "schema": "brc.strategygroup_runtime_safety_state.v1",
        "statuses": {
            "runtime_safety_state_ready",
            "live_submit_standby_waiting_for_market",
            "live_submit_ready",
        },
    },
}
BLOCKER_STAGE_TIER = {
    "action_time_preflight_ready": 1100,
    "market_wait_validated": 1000,
    "action_time_boundary_not_reproduced": 900,
    "event_execution_capability_not_certified": 895,
    "runtime_profile_scope_missing": 890,
    "active_position_resolution": 880,
    "watcher_tick_missing": 800,
    "detector_not_attached": 790,
    "replay_live_rule_mismatch": 780,
    "scope_not_attached": 700,
    "artifact_missing": 600,
    "schema_invalid": 590,
    "computed_not_satisfied": 500,
    "policy_scope_missing": 30,
    "hard_safety_stop": 0,
    "review_only_warning": 0,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("PG_DATABASE_URL", ""),
        help="PostgreSQL DSN for the DB-backed Daily Table current source.",
    )
    parser.add_argument(
        "--require-database-url",
        action="store_true",
        help="Accepted for deploy compatibility; Daily Table is always PG-only.",
    )
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite/non-PG DSNs only in tests.",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print(
            "ERROR: PG_DATABASE_URL is required for PG-only Daily Table",
            file=sys.stderr,
        )
        return 2

    database_url = normalize_sync_postgres_dsn(args.database_url)
    if not is_sync_postgres_dsn(database_url) and not args.allow_non_postgres_for_test:
        print(
            "ERROR: PG-only Daily Table requires PostgreSQL DSN",
            file=sys.stderr,
        )
        return 2
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            repository = PgBackedRuntimeControlStateRepository(conn)
            artifact = build_daily_live_enablement_table_from_control_state(
                repository.read_control_state(),
            )
    finally:
        engine.dispose()
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "row_count": artifact["summary"]["row_count"],
                "rank_1_lane": artifact["summary"]["rank_1_lane"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def build_daily_live_enablement_table(
    *,
    tradeability: dict[str, Any],
    replay_live_parity: dict[str, Any],
    action_time_boundary: dict[str, Any],
    mi_trial_admission: dict[str, Any],
    runtime_safety: dict[str, Any],
    candidate_pool: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    candidate_pool = candidate_pool or {}
    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    source_validation = _source_validation(
        tradeability=tradeability,
        replay_live_parity=replay_live_parity,
        action_time_boundary=action_time_boundary,
        mi_trial_admission=mi_trial_admission,
        runtime_safety=runtime_safety,
    )
    tradeability_rows = {
        str(row.get("strategy_group_id") or ""): row
        for row in _dict_rows(tradeability.get("decision_rows"))
    }
    ranked_rows = [
        _daily_row(
            strategy_group_id=strategy_group_id,
            tradeability_row=tradeability_rows.get(strategy_group_id, {}),
            replay_live_parity=replay_live_parity,
            action_time_boundary=action_time_boundary,
            mi_trial_admission=mi_trial_admission,
            runtime_safety=runtime_safety,
            candidate_pool_row=_candidate_pool_row(
                candidate_pool=candidate_pool,
                strategy_group_id=strategy_group_id,
            ),
        )
        for strategy_group_id in WIP_LANES
    ]
    ranked_rows = _rank_rows(ranked_rows)
    rank_1 = next(row for row in ranked_rows if row["closest_to_live_rank"] == 1)
    return {
        "schema": SCHEMA,
        "scope": "daily_live_enablement_table_non_authority",
        "status": (
            "daily_live_enablement_table_ready"
            if source_validation["valid"]
            else "daily_live_enablement_table_source_invalid"
        ),
        "generated_at_utc": generated,
        "source_validation": source_validation,
        "rows": ranked_rows,
        "summary": {
            "row_count": len(ranked_rows),
            "wip_lane_count": len(WIP_LANES),
            "rank_1_lane": (
                f"{rank_1['strategy_group_id']}:{rank_1['symbol']}"
            ),
            "rank_1_first_blocker": rank_1["first_blocker"],
            "rank_1_next_engineering_action": rank_1["next_engineering_action"],
            "owner_action_required_count": sum(
                row["owner_action_required"] == "yes" for row in ranked_rows
            ),
            "source_validation_valid": source_validation["valid"],
            "non_authority": True,
        },
        "checks": {
            "source_validation_passed": source_validation["valid"],
            "active_wip_lanes_only": {
                row["strategy_group_id"] for row in ranked_rows
            }
            == set(WIP_LANES),
            "single_rank_1": sum(
                row["closest_to_live_rank"] == 1 for row in ranked_rows
            )
            == 1,
            "all_rows_have_blocker_evidence_action_stop": all(
                row["first_blocker"]
                and row["first_blocker_evidence"]
                and row["next_engineering_action"]
                and row["stop_condition"]
                for row in ranked_rows
            ),
            "authority_boundary_preserved": all(
                row["authority_boundary"] == AUTHORITY_BOUNDARY
                for row in ranked_rows
            ),
            "finalgate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
        },
        "interaction": {
            "level": "L0_local_daily_live_enablement_table",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
        },
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


def build_daily_live_enablement_table_from_control_state(
    control_state: dict[str, Any],
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    if control_state.get("source_mode") != "db_backed":
        raise ValueError("Daily Table production path requires DB-backed state")
    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    from src.application.readmodels.strategy_live_candidate_pool import (  # noqa: PLC0415
        build_strategy_live_candidate_pool_from_control_state,
        build_strategy_live_candidate_pool_inputs_from_control_state,
    )

    candidate_pool_inputs = build_strategy_live_candidate_pool_inputs_from_control_state(
        control_state,
        generated_at_utc=generated,
    )
    candidate_pool = build_strategy_live_candidate_pool_from_control_state(
        control_state,
        generated_at_utc=generated,
    )
    artifact = build_daily_live_enablement_table(
        tradeability=candidate_pool_inputs["tradeability"],
        replay_live_parity=candidate_pool_inputs["replay_live_parity"],
        action_time_boundary=candidate_pool_inputs["action_time_boundary"],
        mi_trial_admission=_pg_mi_trial_admission_projection(control_state),
        runtime_safety=_pg_runtime_safety_projection(control_state),
        candidate_pool=candidate_pool,
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


def _pg_mi_trial_admission_projection(control_state: dict[str, Any]) -> dict[str, Any]:
    mi_rows = [
        row
        for row in _dict_rows(control_state.get("candidate_scope"))
        if row.get("strategy_group_id") == "MI-001" and row.get("status") == "active"
    ]
    return {
        "schema": "brc.mi_trial_admission_decision.v1",
        "status": "mi_trial_admission_decision_ready",
        "strategy_group_id": "MI-001",
        "trial_admission_decision": "pg_runtime_control_state_scope_recorded",
        "side": "long",
        "symbol_scope": {
            "reviewed_symbols": sorted(
                {str(row.get("symbol") or "") for row in mi_rows if row.get("symbol")}
            )
        },
        "source_mode": "db_backed",
    }


def _pg_runtime_safety_projection(control_state: dict[str, Any]) -> dict[str, Any]:
    truths = current_runtime_safety_truths(control_state)
    if truths:
        truth = truths[0]
        row = truth.snapshot
        submit_allowed = truth.submit_authorized
        return {
            "schema": "brc.strategygroup_runtime_safety_state.v1",
            "status": "live_submit_ready"
            if submit_allowed
            else "runtime_safety_state_ready",
            "runtime_safety_state": {
                "live_submit_ready": submit_allowed,
                "live_submit_ready_false_reason": str(
                    ""
                    if submit_allowed
                    else ",".join(truth.failure_reasons)
                    or row.get("safety_state")
                    or "submit_allowed_false"
                ),
                "snapshot_id": str(row.get("runtime_safety_snapshot_id") or ""),
                "lineage_verified": truth.lineage_verified,
            },
            "source_mode": "db_backed",
        }
    return {
        "schema": "brc.strategygroup_runtime_safety_state.v1",
        "status": "runtime_safety_state_ready",
        "runtime_safety_state": {
            "live_submit_ready": False,
            "live_submit_ready_false_reason": "no_current_runtime_safety_snapshot",
            "snapshot_id": "",
            "lineage_verified": False,
        },
        "source_mode": "db_backed",
    }


def _daily_row(
    *,
    strategy_group_id: str,
    tradeability_row: dict[str, Any],
    replay_live_parity: dict[str, Any],
    action_time_boundary: dict[str, Any],
    mi_trial_admission: dict[str, Any],
    runtime_safety: dict[str, Any],
    candidate_pool_row: dict[str, Any],
) -> dict[str, Any]:
    candidate_pool_first_blocker = str(candidate_pool_row.get("first_blocker") or "")
    raw_first_blocker = candidate_pool_first_blocker or str(
        tradeability_row.get("first_blocker_class") or "artifact_missing"
    )
    market_wait_validation = _market_wait_validation_for_row(
        tradeability_row=tradeability_row,
        candidate_pool_row=candidate_pool_row,
        first_blocker=raw_first_blocker,
    )
    first_blocker = _resolve_daily_first_blocker(
        raw_first_blocker=raw_first_blocker,
        market_wait_validation=market_wait_validation,
    )
    if raw_first_blocker != first_blocker:
        market_wait_validation = {
            **market_wait_validation,
            "reclassified_to": first_blocker,
        }
    canonical_lane = _as_dict(tradeability_row.get("canonical_lane"))
    parity_row = _best_parity_row(
        strategy_group_id=strategy_group_id,
        first_blocker=first_blocker,
        replay_live_parity=replay_live_parity,
        preferred_symbol=str(canonical_lane.get("symbol") or ""),
    )
    action_row = _action_time_row(
        strategy_group_id,
        action_time_boundary,
        preferred_symbol=str(parity_row.get("symbol") or ""),
    )
    symbol = str(candidate_pool_row.get("symbol") or "") or _lane_symbol(
        strategy_group_id=strategy_group_id,
        tradeability_row=tradeability_row,
        parity_row=parity_row,
        action_row=action_row,
        canonical_lane=canonical_lane,
        mi_trial_admission=mi_trial_admission,
    )
    side = str(candidate_pool_row.get("side") or "") or _lane_side(
        strategy_group_id=strategy_group_id,
        tradeability_row=tradeability_row,
        mi_trial_admission=mi_trial_admission,
    )
    stage = _daily_stage(str(tradeability_row.get("stage") or "research_candidate"))
    chain_position = _chain_position(first_blocker)
    if str(candidate_pool_row.get("promotion_state") or "") == "action_time_lane":
        stage = "action_time"
        chain_position = "action_time_boundary"
    evidence = (
        _candidate_pool_evidence(
            strategy_group_id=strategy_group_id,
            candidate_pool_row=candidate_pool_row,
            first_blocker=first_blocker,
        )
        if candidate_pool_row
        else _evidence(
            strategy_group_id=strategy_group_id,
            first_blocker=first_blocker,
            tradeability_row=tradeability_row,
            parity_row=parity_row,
            action_row=action_row,
            mi_trial_admission=mi_trial_admission,
        )
    )
    next_action = str(
        candidate_pool_row.get("next_action")
        or tradeability_row.get("next_action")
        or _next_action_for_blocker(first_blocker)
    )
    stop_condition = str(
        candidate_pool_row.get("stop_condition") or ""
    ) or _stop_condition(
        strategy_group_id=strategy_group_id,
        first_blocker=first_blocker,
        next_action=next_action,
    )
    return {
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "canonical_lane": canonical_lane,
        "side": side,
        "stage": stage,
        "chain_position": chain_position,
        "first_blocker": first_blocker,
        "first_blocker_evidence": evidence,
        "owner_action_required": (
            "yes" if first_blocker in OWNER_BLOCKERS else "no"
        ),
        "next_engineering_action": next_action,
        "stop_condition": stop_condition,
        "closest_to_live_rank": 0,
        "rank_reason": "",
        "authority_boundary": AUTHORITY_BOUNDARY,
        "replay_signal": _replay_signal(strategy_group_id, parity_row),
        "live_detector": _live_detector_state(first_blocker, parity_row),
        "market_wait_validation": market_wait_validation,
        "runtime_safety_reference": _runtime_safety_reference(
            strategy_group_id, runtime_safety
        ),
        "candidate_pool_reference": _candidate_pool_reference(candidate_pool_row),
    }


def _candidate_pool_row(
    *,
    candidate_pool: dict[str, Any],
    strategy_group_id: str,
) -> dict[str, Any]:
    if str(candidate_pool.get("status") or "") != "strategy_live_candidate_pool_ready":
        return {}
    rows = [
        row
        for row in _dict_rows(candidate_pool.get("symbol_readiness_rows"))
        if str(row.get("strategy_group_id") or "") == strategy_group_id
    ]
    if not rows:
        return {}
    return sorted(rows, key=_candidate_pool_row_sort_key)[0]


def _candidate_pool_row_sort_key(
    row: dict[str, Any]
) -> tuple[int, int, int, int, int, str]:
    symbol = str(row.get("symbol") or "")
    coverage = _as_dict(row.get("server_runtime_coverage"))
    coverage_ready = str(coverage.get("state") or "") == "active_watcher_scope"
    promotion_priority = {
        "action_time_lane": 400,
        "promotion_candidate": 300,
        "idle": 100,
        "blocked": 0,
    }.get(str(row.get("promotion_state") or ""), 0)
    role_priority = {
        "primary": 30,
        "lead": 20,
        "secondary": 10,
        "conditional": 5,
    }.get(str(row.get("candidate_role") or ""), 0)
    return (
        -promotion_priority,
        -BLOCKER_STAGE_TIER.get(str(row.get("first_blocker") or ""), 0),
        0 if coverage_ready else 1,
        -role_priority,
        -int(row.get("mismatch_count") or 0),
        symbol,
    )


def _candidate_pool_evidence(
    *,
    strategy_group_id: str,
    candidate_pool_row: dict[str, Any],
    first_blocker: str,
) -> str:
    coverage = _as_dict(candidate_pool_row.get("server_runtime_coverage"))
    coverage_state = str(coverage.get("state") or "unknown")
    detail = str(candidate_pool_row.get("first_blocker_detail") or "")
    return (
        "candidate_pool_input:"
        f"{strategy_group_id}/{candidate_pool_row.get('symbol') or 'strategy_scope'} "
        f"first_blocker={first_blocker} "
        f"first_blocker_detail={detail or first_blocker} "
        f"server_runtime_coverage={coverage_state}"
    )


def _candidate_pool_reference(candidate_pool_row: dict[str, Any]) -> dict[str, Any]:
    if not candidate_pool_row:
        return {}
    return {
        "source": "strategy_live_candidate_pool",
        "strategy_group_id": candidate_pool_row.get("strategy_group_id"),
        "symbol": candidate_pool_row.get("symbol"),
        "first_blocker": candidate_pool_row.get("first_blocker"),
        "promotion_state": candidate_pool_row.get("promotion_state"),
        "signal_state": candidate_pool_row.get("signal_state"),
        "scope_state": candidate_pool_row.get("scope_state"),
        "server_runtime_coverage": candidate_pool_row.get("server_runtime_coverage")
        or {},
    }


def _best_parity_row(
    *,
    strategy_group_id: str,
    first_blocker: str,
    replay_live_parity: dict[str, Any],
    preferred_symbol: str = "",
) -> dict[str, Any]:
    rows = [
        row
        for row in _dict_rows(replay_live_parity.get("per_symbol_mismatch_table"))
        if str(row.get("strategy_group_id") or "") == strategy_group_id
    ]
    if not rows:
        return {}
    matching = [
        row for row in rows if str(row.get("blocker_class") or "") == first_blocker
    ]
    candidates = matching or rows
    if preferred_symbol:
        exact = [
            row for row in candidates if str(row.get("symbol") or "") == preferred_symbol
        ]
        if exact:
            candidates = exact
    return sorted(
        candidates,
        key=lambda row: (
            -int(row.get("live_submit_scope_priority") or 0),
            -int(row.get("mismatch_count") or 0),
            str(row.get("symbol") or ""),
        ),
    )[0]


def _action_time_row(
    strategy_group_id: str,
    action_time_boundary: dict[str, Any],
    preferred_symbol: str = "",
) -> dict[str, Any]:
    fallback: dict[str, Any] = {}
    for row in _dict_rows(action_time_boundary.get("strategy_rows")):
        if str(row.get("strategy_group_id") or "") == strategy_group_id:
            if (
                preferred_symbol
                and str(row.get("symbol") or "") == preferred_symbol
            ):
                return row
            if not fallback:
                fallback = row
    return fallback


def _lane_symbol(
    *,
    strategy_group_id: str,
    tradeability_row: dict[str, Any],
    parity_row: dict[str, Any],
    action_row: dict[str, Any],
    canonical_lane: dict[str, Any],
    mi_trial_admission: dict[str, Any],
) -> str:
    if canonical_lane.get("symbol"):
        return str(canonical_lane["symbol"])
    if parity_row.get("symbol"):
        return str(parity_row["symbol"])
    if action_row.get("symbol"):
        return str(action_row["symbol"])
    if strategy_group_id == "MI-001":
        reviewed = _as_dict(mi_trial_admission.get("symbol_scope")).get(
            "reviewed_symbols"
        )
        if isinstance(reviewed, list) and reviewed:
            return str(reviewed[0])
    for path in _dict_rows(tradeability_row.get("trade_paths")):
        watcher = _as_dict(path.get("watcher_scope"))
        symbols = watcher.get("symbols")
        if isinstance(symbols, list) and symbols:
            return str(symbols[0])
        if isinstance(symbols, str) and symbols:
            return symbols
    policy = _as_dict(tradeability_row.get("policy_scope"))
    symbol_scope = policy.get("symbol_scope")
    if isinstance(symbol_scope, list) and symbol_scope:
        return str(symbol_scope[0])
    return "strategy_scope"


def _lane_side(
    *,
    strategy_group_id: str,
    tradeability_row: dict[str, Any],
    mi_trial_admission: dict[str, Any],
) -> str:
    if strategy_group_id == "MI-001" and mi_trial_admission.get("side"):
        return str(mi_trial_admission["side"])
    for path in _dict_rows(tradeability_row.get("trade_paths")):
        if path.get("side"):
            return str(path["side"])
    policy = _as_dict(tradeability_row.get("policy_scope"))
    side_scope = policy.get("side_scope")
    if isinstance(side_scope, list) and side_scope:
        return str(side_scope[0])
    return "unknown"


def _daily_stage(stage: str) -> str:
    return {
        "research_candidate": "research",
        "tiny_live_intake_candidate": "intake",
        "trial_asset_admission_candidate": "admission",
        "observe_only_would_enter": "readonly",
        "armed_observation": "armed",
        "tiny_live_ready": "action_time",
        "live_submit_ready": "live_submit_ready",
    }.get(stage, stage or "research")


def _chain_position(first_blocker: str) -> str:
    if first_blocker in {"scope_not_attached", "policy_scope_missing"}:
        return "symbol_scope_decision"
    if first_blocker in {
        "action_time_boundary_not_reproduced",
        "action_time_preflight_ready",
        "runtime_profile_scope_missing",
        "active_position_resolution",
    }:
        return "action_time_boundary"
    if first_blocker in {
        "detector_not_attached",
        "watcher_tick_missing",
        "computed_not_satisfied",
        "replay_live_rule_mismatch",
        "market_wait_validated",
    }:
        return "replay_live_parity"
    return "tradeability_first_blocker"


def _evidence(
    *,
    strategy_group_id: str,
    first_blocker: str,
    tradeability_row: dict[str, Any],
    parity_row: dict[str, Any],
    action_row: dict[str, Any],
    mi_trial_admission: dict[str, Any],
) -> str:
    if parity_row:
        source_blocker = str(parity_row.get("blocker_class") or "")
        source_detail = (
            f"source_blocker_class={source_blocker} "
            if source_blocker != first_blocker
            else ""
        )
        return (
            "replay_live_parity_input:"
            f"{strategy_group_id}/{parity_row.get('symbol') or 'strategy_scope'} "
            f"first_blocker={first_blocker} "
            f"{source_detail}"
            f"watcher_tick_present={parity_row.get('watcher_tick_present')}"
        )
    if action_row:
        return (
            "action_time_boundary_input:"
            f"{strategy_group_id} first_blocker={action_row.get('first_blocker')}"
        )
    if strategy_group_id == "MI-001" and mi_trial_admission:
        return (
            "mi_trial_admission_input:"
            f"trial_admission_decision={mi_trial_admission.get('trial_admission_decision')}"
        )
    detail = str(tradeability_row.get("first_blocker_detail") or first_blocker)
    return (
        "tradeability_decision_input:"
        f"{strategy_group_id} {detail}"
    )


def _stop_condition(
    *,
    strategy_group_id: str,
    first_blocker: str,
    next_action: str,
) -> str:
    if first_blocker == "market_wait_validated":
        return "fresh eligible signal appears or lane exits WIP under stop rule"
    if first_blocker == "computed_not_satisfied":
        return (
            "failed fact matrix clears or blocker reclassifies after next detector tick"
        )
    if first_blocker == "scope_not_attached":
        return (
            "scoped live observation proposal is attached or Owner scope decision is required"
        )
    if first_blocker == "policy_scope_missing":
        return "Owner scoped policy is recorded or lane exits mainline"
    if first_blocker == "detector_not_attached":
        return "live detector is attached to the selected lane"
    if first_blocker == "watcher_tick_missing":
        return "watcher/public facts tick is present for the selected lane"
    if first_blocker == "action_time_boundary_not_reproduced":
        return "non-executing action-time rehearsal reaches candidate/auth boundary"
    if first_blocker == "action_time_preflight_ready":
        return "non-executing FinalGate preflight input is prepared or lane reclassifies"
    if first_blocker == "artifact_missing":
        return "required current artifact is generated through monitor sequence"
    if first_blocker == "schema_invalid":
        return "artifact schema validates and generator regression test passes"
    return f"{next_action} changes first_blocker or lane exits WIP"


def _next_action_for_blocker(first_blocker: str) -> str:
    return {
        "artifact_missing": "generate_or_wire_current_artifact",
        "schema_invalid": "repair_artifact_schema_and_add_regression",
        "detector_not_attached": "attach_live_detector_to_selected_lane",
        "watcher_tick_missing": "refresh_or_repair_watcher_fact_source",
        "scope_not_attached": "produce_scoped_live_observation_or_scope_proposal",
        "computed_not_satisfied": "continue_observation_with_failed_fact_matrix",
        "replay_live_rule_mismatch": "normalize_replay_live_rules_or_record_revision",
        "action_time_boundary_not_reproduced": "repair_non_executing_action_time_rehearsal_path",
        "action_time_preflight_ready": "prepare_non_executing_finalgate_preflight_input",
        "policy_scope_missing": "record_scoped_owner_policy",
        "runtime_profile_scope_missing": "bind_runtime_profile_scope",
        "market_wait_validated": "continue_watcher_observation_until_fresh_signal",
        "active_position_resolution": "resolve_active_position_or_open_order",
        "hard_safety_stop": "remove_hard_safety_violation",
        "review_only_warning": "record_strategy_review_decision",
    }.get(first_blocker, "repair_daily_live_enablement_blocker_classification")


def _replay_signal(strategy_group_id: str, parity_row: dict[str, Any]) -> str:
    if parity_row:
        return "yes"
    if strategy_group_id == "MI-001":
        return "not_applicable"
    return "unknown_with_reason:no_replay_live_parity_row"


def _live_detector_state(first_blocker: str, parity_row: dict[str, Any]) -> str:
    if not parity_row:
        return "not_tested"
    if first_blocker in {"market_wait_validated", "action_time_preflight_ready"}:
        return "matched"
    if first_blocker in {
        "computed_not_satisfied",
        "scope_not_attached",
        "detector_not_attached",
        "watcher_tick_missing",
        "replay_live_rule_mismatch",
    }:
        return first_blocker
    return "not_matched"


def _market_wait_validation(tradeability_row: dict[str, Any]) -> dict[str, Any]:
    validation = _as_dict(tradeability_row.get("market_wait_validation"))
    if not validation:
        return {"valid": False, "not_applicable": True, "checks": {}}
    return validation


def _market_wait_validation_for_row(
    *,
    tradeability_row: dict[str, Any],
    candidate_pool_row: dict[str, Any],
    first_blocker: str,
) -> dict[str, Any]:
    if first_blocker != "market_wait_validated":
        return _market_wait_validation(tradeability_row)
    if not candidate_pool_row:
        return _market_wait_validation(tradeability_row)

    coverage = _as_dict(candidate_pool_row.get("server_runtime_coverage"))
    public_facts_state = _as_dict(candidate_pool_row.get("public_facts_state"))
    action_time = _as_dict(candidate_pool_row.get("action_time"))
    owner_authorization = _as_dict(candidate_pool_row.get("owner_authorization"))
    detector_state = str(candidate_pool_row.get("detector_state") or "")
    scope_state = str(candidate_pool_row.get("scope_state") or "")
    signal_state = str(candidate_pool_row.get("signal_state") or "")
    live_submit_allowed = str(owner_authorization.get("live_submit_allowed") or "")
    checks = {
        "asset_admission": True,
        "scope": scope_state
        in {"live_submit_allowed", "conditional_action_time_rehearsal_allowed"},
        "policy": (
            owner_authorization.get("pretrade_candidate_allowed") is True
            and owner_authorization.get("action_time_rehearsal_allowed") is True
            and live_submit_allowed in {"scoped", "conditional_hard_gated"}
        ),
        "detector": detector_state != "missing" and (
            bool(detector_state) or bool(public_facts_state)
        ),
        "watcher_input": (
            str(coverage.get("state") or "") == "active_watcher_scope"
            and bool(coverage.get("active_runtime_instance_ids") or [])
            and bool(coverage.get("selected_runtime_instance_ids") or [])
        ),
        "facts": str(public_facts_state.get("state") or "") == "satisfied",
        "classification": True,
        "action_time_path": _market_wait_action_time_path_ready(
            action_time=action_time,
            signal_state=signal_state,
        ),
        "fresh_signal_absent": signal_state == "absent",
    }
    return {
        "valid": all(checks.values()),
        "not_applicable": False,
        "mode": "candidate_pool_market_wait",
        "checks": checks,
    }


def _market_wait_action_time_path_ready(
    *,
    action_time: dict[str, Any],
    signal_state: str,
) -> bool:
    if "action_time_capability_certified" in action_time:
        return action_time.get("action_time_capability_certified") is True
    if action_time.get("action_time_path_ready") is True:
        return True
    first_blocker = str(action_time.get("first_blocker") or "")
    return (
        signal_state == "absent"
        and first_blocker.startswith("fresh_")
        and first_blocker.endswith("_absent")
    )


def _resolve_daily_first_blocker(
    *,
    raw_first_blocker: str,
    market_wait_validation: dict[str, Any],
) -> str:
    if raw_first_blocker != "market_wait_validated":
        return raw_first_blocker
    if market_wait_validation.get("valid") is True:
        return raw_first_blocker
    return _market_wait_failed_blocker(market_wait_validation)


def _market_wait_failed_blocker(validation: dict[str, Any]) -> str:
    checks = _as_dict(validation.get("checks"))
    for check_name, blocker in (
        ("asset_admission", "artifact_missing"),
        ("scope", "scope_not_attached"),
        ("policy", "policy_scope_missing"),
        ("detector", "detector_not_attached"),
        ("watcher_input", "watcher_tick_missing"),
        ("facts", "computed_not_satisfied"),
        ("classification", "schema_invalid"),
        ("action_time_path", "action_time_boundary_not_reproduced"),
        ("fresh_signal_absent", "action_time_boundary_not_reproduced"),
    ):
        if checks.get(check_name) is False:
            return blocker
    return "artifact_missing"


def _runtime_safety_reference(
    strategy_group_id: str,
    runtime_safety: dict[str, Any],
) -> dict[str, Any]:
    state = _as_dict(runtime_safety.get("runtime_safety_state"))
    return {
        "strategy_group_id": strategy_group_id,
        "live_submit_ready": state.get("live_submit_ready") is True,
        "live_submit_ready_false_reason": str(
            state.get("live_submit_ready_false_reason") or ""
        ),
        "state_source": "runtime_safety_state",
    }


def _source_validation(
    *,
    tradeability: dict[str, Any],
    replay_live_parity: dict[str, Any],
    action_time_boundary: dict[str, Any],
    mi_trial_admission: dict[str, Any],
    runtime_safety: dict[str, Any],
) -> dict[str, Any]:
    sources = {
        "tradeability": tradeability,
        "replay_live_parity": replay_live_parity,
        "action_time_boundary": action_time_boundary,
        "mi_trial_admission": mi_trial_admission,
        "runtime_safety": runtime_safety,
    }
    source_rows = {
        name: _validate_source(name, artifact)
        for name, artifact in sources.items()
    }
    return {
        "valid": all(row["valid"] for row in source_rows.values()),
        "sources": source_rows,
    }


def _validate_source(name: str, artifact: dict[str, Any]) -> dict[str, Any]:
    expectation = SOURCE_EXPECTATIONS[name]
    actual_schema = str(artifact.get("schema") or "")
    actual_status = str(artifact.get("status") or "")
    present = bool(artifact)
    schema_valid = actual_schema == expectation["schema"]
    status_valid = actual_status in expectation["statuses"]
    return {
        "present": present,
        "valid": present and schema_valid and status_valid,
        "schema_valid": schema_valid,
        "status_valid": status_valid,
        "expected_schema": expectation["schema"],
        "actual_schema": actual_schema,
        "expected_statuses": sorted(expectation["statuses"]),
        "actual_status": actual_status,
    }


def _rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            -_rank_stage_tier(row),
            -_rank_wip_priority(row),
            WIP_LANES.index(row["strategy_group_id"]),
        ),
    )
    ranked_by_id: dict[str, dict[str, Any]] = {}
    for rank, row in enumerate(ordered, start=1):
        ranked = dict(row)
        ranked["closest_to_live_rank"] = rank
        ranked["rank_reason"] = (
            f"{row['first_blocker']} tier {_rank_stage_tier(row)} "
            f"(WIP priority {_rank_wip_priority(row)} only breaks same-tier ties)"
        )
        ranked_by_id[row["strategy_group_id"]] = ranked
    return [ranked_by_id[strategy_group_id] for strategy_group_id in WIP_LANES]


def _rank_stage_tier(row: dict[str, Any]) -> int:
    return BLOCKER_STAGE_TIER.get(str(row.get("first_blocker") or ""), 0)


def _rank_wip_priority(row: dict[str, Any]) -> int:
    return WIP_PRIORITY_BONUS.get(str(row.get("strategy_group_id") or ""), 0)


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
