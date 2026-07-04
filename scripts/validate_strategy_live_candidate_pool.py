#!/usr/bin/env python3
"""Validate the five StrategyGroup live-candidate pool artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_daily_live_enablement_table import (  # noqa: E402
    CONTRACT_BLOCKER_CLASSES,
    WIP_LANES,
)
from scripts.build_strategy_live_candidate_pool import (  # noqa: E402
    ACTION_TIME_INPUT_BLOCKERS,
    ACTION_TIME_SCOPE_STATES,
    AUTHORITY_BOUNDARY,
    OWNER_AUTHORIZATION_SCHEMA,
    PLACEHOLDER_SYMBOLS,
    SCHEMA,
    SCOPED_LIVE_SUBMIT_STRATEGIES,
    STRATEGY_SIGNAL_FACT_SIDE_SCOPE,
)


DEFAULT_INPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-live-candidate-pool.json"
)
FORBIDDEN_TRUE_KEYS = {
    "actionable_now",
    "real_order_authority",
    "calls_finalgate",
    "calls_operation_layer",
    "calls_exchange_write",
    "places_order",
    "order_created",
    "exchange_write_called",
    "finalgate_called",
    "operation_layer_called",
    "live_profile_changed",
    "order_sizing_changed",
}
SERVER_RUNTIME_COVERAGE_STATES = {
    "active_watcher_scope",
    "active_runtime_filtered_out",
    "runtime_profile_scope_missing",
    "watcher_tick_missing",
    "detector_not_attached",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_pool_json", nargs="?", default=str(DEFAULT_INPUT_JSON))
    args = parser.parse_args(argv)
    path = Path(args.candidate_pool_json)
    errors = validate_strategy_live_candidate_pool(_read_json(path))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "strategy_live_candidate_pool_valid",
                "path": str(path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def validate_strategy_live_candidate_pool(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if artifact.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    if artifact.get("status") != "strategy_live_candidate_pool_ready":
        errors.append("status must be strategy_live_candidate_pool_ready")
    source_validation = _as_dict(artifact.get("source_validation"))
    if source_validation.get("valid") is not True:
        errors.append("source_validation.valid must be true")
    rows = _dict_rows(artifact.get("candidate_rows"))
    symbol_rows = _dict_rows(artifact.get("symbol_readiness_rows"))
    if len(rows) != len(WIP_LANES):
        errors.append(f"candidate_rows must contain {len(WIP_LANES)} rows")
    strategy_ids = {str(row.get("strategy_group_id") or "") for row in rows}
    if strategy_ids != set(WIP_LANES):
        errors.append("candidate_rows must contain exactly active WIP lanes")
    for index, row in enumerate(rows):
        errors.extend(_validate_candidate_row(index, row))
    if not symbol_rows:
        errors.append("symbol_readiness_rows are required")
    for index, row in enumerate(symbol_rows):
        errors.extend(_validate_symbol_readiness_row(index, row))
    expected_symbols = _expected_candidate_symbols_by_strategy(artifact)
    expected_sides = _expected_side_scope_by_strategy(artifact)
    errors.extend(
        _validate_authorized_candidate_universe(
            symbol_rows,
            expected_symbols=expected_symbols,
            expected_sides=expected_sides,
        )
    )
    errors.extend(_validate_pretrade_runtime(artifact, symbol_rows))
    summary = _as_dict(artifact.get("summary"))
    if summary.get("candidate_count") != len(WIP_LANES):
        errors.append("summary.candidate_count must match active WIP lanes")
    if summary.get("symbol_readiness_count") != len(symbol_rows):
        errors.append("summary.symbol_readiness_count must match readiness rows")
    errors.extend(_validate_owner_authorization_summary(artifact))
    if artifact.get("authority_boundary") != AUTHORITY_BOUNDARY:
        errors.append("authority_boundary is invalid")
    errors.extend(_forbidden_true_paths(artifact))
    return errors


def _validate_candidate_row(index: int, row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    prefix = f"candidate_rows[{index}]"
    required = (
        "strategy_group_id",
        "candidate_status",
        "candidate_positioning",
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
    for key in required:
        if not row.get(key):
            errors.append(f"{prefix}.{key} is required")
    if row.get("first_blocker") not in CONTRACT_BLOCKER_CLASSES:
        errors.append(f"{prefix}.first_blocker must be a contract blocker")
    if row.get("blocker_owner") not in {
        "engineering",
        "runtime",
        "market",
        "owner",
        "safety",
        "engineering / owner",
        "engineering / strategy_review",
        "runtime / engineering",
        "runtime / safety",
        "strategy_review",
    }:
        errors.append(f"{prefix}.blocker_owner is invalid")
    readiness = _as_dict(row.get("action_time_readiness"))
    if not readiness.get("status"):
        errors.append(f"{prefix}.action_time_readiness.status is required")
    if readiness.get("status") == "ready_for_finalgate_preflight":
        if readiness.get("action_time_path_ready") is not True:
            errors.append(
                f"{prefix}.action_time_readiness.action_time_path_ready "
                "must be true for ready_for_finalgate_preflight"
            )
        if readiness.get("public_facts_ready") is not True:
            errors.append(
                f"{prefix}.action_time_readiness.public_facts_ready "
                "must be true for ready_for_finalgate_preflight"
            )
        if readiness.get("private_action_time_facts_ready") is not True:
            errors.append(
                f"{prefix}.action_time_readiness.private_action_time_facts_ready "
                "must be true for ready_for_finalgate_preflight"
            )
    if row.get("authority_boundary"):
        boundary = str(row.get("authority_boundary"))
        if "no_finalgate" not in boundary or "no_operation_layer" not in boundary:
            errors.append(f"{prefix}.authority_boundary is invalid")
    return errors


def _validate_symbol_readiness_row(index: int, row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    prefix = f"symbol_readiness_rows[{index}]"
    required = (
        "strategy_group_id",
        "symbol",
        "symbol_or_basket",
        "asset_class",
        "side",
        "candidate_role",
        "observation_scope",
        "detector_state",
        "watcher_state",
        "public_facts_state",
        "signal_state",
        "risk_state",
        "scope_state",
        "owner_authorization",
        "promotion_state",
        "first_blocker",
        "next_action",
        "stop_condition",
        "evidence_ref",
    )
    for key in required:
        value = row.get(key)
        if value is None or value == "":
            errors.append(f"{prefix}.{key} is required")
    if row.get("strategy_group_id") not in WIP_LANES:
        errors.append(f"{prefix}.strategy_group_id must be an active StrategyGroup")
    if row.get("first_blocker") not in CONTRACT_BLOCKER_CLASSES:
        errors.append(f"{prefix}.first_blocker must be a contract blocker")
    if row.get("observation_scope") not in {
        "none",
        "readonly",
        "active_observation",
    }:
        errors.append(f"{prefix}.observation_scope is invalid")
    if row.get("detector_state") not in {"missing", "ready", "running", "stale"}:
        errors.append(f"{prefix}.detector_state is invalid")
    if row.get("watcher_state") not in {"missing", "fresh", "stale"}:
        errors.append(f"{prefix}.watcher_state is invalid")
    public_facts = _as_dict(row.get("public_facts_state"))
    if public_facts.get("state") not in {
        "missing",
        "computed_not_satisfied",
        "satisfied",
    }:
        errors.append(f"{prefix}.public_facts_state.state is invalid")
    if row.get("signal_state") not in {"absent", "fresh", "stale", "invalidated"}:
        errors.append(f"{prefix}.signal_state is invalid")
    if row.get("risk_state") not in {"acceptable", "warning", "disable"}:
        errors.append(f"{prefix}.risk_state is invalid")
    if row.get("scope_state") not in {
        "readonly_only",
        "trial_scope_proposed",
        "live_submit_allowed",
        "conditional_action_time_rehearsal_allowed",
    }:
        errors.append(f"{prefix}.scope_state is invalid")
    errors.extend(_validate_row_owner_authorization(prefix, row))
    if row.get("promotion_state") not in {
        "idle",
        "promotion_candidate",
        "action_time_lane",
        "blocked",
    }:
        errors.append(f"{prefix}.promotion_state is invalid")
    if (
        row.get("promotion_state") == "action_time_lane"
        and row.get("scope_state") not in ACTION_TIME_SCOPE_STATES
    ):
        errors.append(f"{prefix}.action_time_lane requires action-time scope")
    if (
        row.get("promotion_state") == "action_time_lane"
        and row.get("first_blocker") in ACTION_TIME_INPUT_BLOCKERS
    ):
        errors.append(f"{prefix}.action_time_lane has unresolved blocker")
    if (
        row.get("promotion_state") == "action_time_lane"
        and row.get("strategy_signal_fact_side_supported") is not True
    ):
        errors.append(
            f"{prefix}.action_time_lane requires strategy signal fact side support"
        )
    if row.get("promotion_state") == "action_time_lane" and not str(
        row.get("fresh_signal_timestamp_utc") or ""
    ):
        errors.append(f"{prefix}.action_time_lane requires fresh signal timestamp")
    if row.get("promotion_state") == "action_time_lane" and not str(
        row.get("fresh_signal_timestamp_source") or ""
    ):
        errors.append(f"{prefix}.action_time_lane requires fresh signal timestamp source")
    if (
        row.get("fresh_signal_timestamp_source")
        == "action_time_boundary:_artifact_generated_at_utc"
    ):
        errors.append(
            f"{prefix}.fresh_signal_timestamp_source must not be artifact generated_at"
        )
    strategy_group_id = str(row.get("strategy_group_id") or "")
    side = str(row.get("side") or "")
    side_scope = set(STRATEGY_SIGNAL_FACT_SIDE_SCOPE.get(strategy_group_id, ()))
    if row.get("strategy_signal_fact_side_supported") is True and side not in side_scope:
        errors.append(
            f"{prefix}.strategy_signal_fact_side_supported contradicts side scope"
        )
    if (
        row.get("promotion_state") == "action_time_lane"
        and not _server_runtime_scope_ready(
            _as_dict(row.get("server_runtime_coverage")),
            strategy_group_id=str(row.get("strategy_group_id") or ""),
            symbol=str(row.get("symbol") or ""),
            side=str(row.get("side") or ""),
        )
    ):
        errors.append(
            f"{prefix}.action_time_lane requires active server runtime coverage"
        )
    coverage = _as_dict(row.get("server_runtime_coverage"))
    errors.extend(
        _validate_server_runtime_coverage_identity(
            prefix=f"{prefix}.server_runtime_coverage",
            coverage=coverage,
            strategy_group_id=str(row.get("strategy_group_id") or ""),
            symbol=str(row.get("symbol") or ""),
            side=str(row.get("side") or ""),
        )
    )
    if row.get("authority_boundary") and "no_finalgate" not in str(
        row.get("authority_boundary")
    ):
        errors.append(f"{prefix}.authority_boundary is invalid")
    return errors


def _validate_pretrade_runtime(
    artifact: dict[str, Any], symbol_rows: list[dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    expected_symbols = _expected_candidate_symbols_by_strategy(artifact)
    expected_sides = _expected_side_scope_by_strategy(artifact)
    runtime = _as_dict(artifact.get("pretrade_runtime"))
    if not runtime:
        errors.append("pretrade_runtime is required")
    counts = runtime.get("candidate_symbols_per_strategy_group")
    if not isinstance(counts, dict):
        errors.append("pretrade_runtime.candidate_symbols_per_strategy_group is required")
        counts = {}
    for strategy_group_id in WIP_LANES:
        count = int(counts.get(strategy_group_id) or 0)
        expected = len(expected_symbols.get(strategy_group_id, set()))
        if count != expected:
            errors.append(
                "pretrade_runtime candidate symbol count must match authorized "
                f"universe for {strategy_group_id}"
            )
    lane_counts = runtime.get("candidate_lanes_per_strategy_group")
    if not isinstance(lane_counts, dict):
        errors.append("pretrade_runtime.candidate_lanes_per_strategy_group is required")
        lane_counts = {}
    for strategy_group_id in WIP_LANES:
        count = int(lane_counts.get(strategy_group_id) or 0)
        expected = len(expected_symbols.get(strategy_group_id, set())) * len(
            expected_sides.get(strategy_group_id, set())
        )
        if count != expected:
            errors.append(
                "pretrade_runtime candidate lane count must match authorized "
                f"universe for {strategy_group_id}"
            )
    promotion_candidates = _dict_rows(artifact.get("promotion_candidates"))
    action_time_inputs = _dict_rows(artifact.get("action_time_lane_inputs"))
    readiness_by_lane = {
        (
            str(row.get("strategy_group_id") or ""),
            str(row.get("symbol") or ""),
            str(row.get("side") or ""),
        ): row
        for row in symbol_rows
    }
    if len(action_time_inputs) > 1:
        errors.append("action_time_lane_inputs must contain at most one real-submit candidate")
    for index, row in enumerate(action_time_inputs):
        strategy_group_id = str(row.get("strategy_group_id") or "")
        symbol = str(row.get("symbol") or "")
        side = str(row.get("side") or "")
        readiness_row = readiness_by_lane.get((strategy_group_id, symbol, side), {})
        if symbol in PLACEHOLDER_SYMBOLS:
            errors.append(
                f"action_time_lane_inputs[{index}].symbol must be a real authorized symbol"
            )
        if symbol not in expected_symbols.get(strategy_group_id, set()):
            errors.append(
                f"action_time_lane_inputs[{index}].symbol is outside authorized universe"
            )
        if row.get("scope_state") == "readonly_only":
            errors.append(
                f"action_time_lane_inputs[{index}] must not be readonly_only"
            )
        if row.get("first_blocker") in ACTION_TIME_INPUT_BLOCKERS:
            errors.append(
                f"action_time_lane_inputs[{index}] has unresolved blocker"
            )
        errors.extend(
            _validate_action_time_input_matches_readiness_row(
                index=index,
                action_time_input=row,
                readiness_row=readiness_row,
            )
        )
        errors.extend(_validate_row_owner_authorization(
            f"action_time_lane_inputs[{index}]",
            row,
        ))
        if "no_finalgate" not in str(row.get("authority_boundary") or ""):
            errors.append(f"action_time_lane_inputs[{index}].authority_boundary is invalid")
        if not _server_runtime_scope_ready(
            _as_dict(row.get("server_runtime_coverage")),
            strategy_group_id=strategy_group_id,
            symbol=symbol,
            side=str(row.get("side") or ""),
        ):
            errors.append(
                f"action_time_lane_inputs[{index}] requires active server runtime coverage"
            )
        errors.extend(
            _validate_server_runtime_coverage_identity(
                prefix=f"action_time_lane_inputs[{index}].server_runtime_coverage",
                coverage=_as_dict(row.get("server_runtime_coverage")),
                strategy_group_id=strategy_group_id,
                symbol=symbol,
                side=str(row.get("side") or ""),
            )
        )
    arbitration = _as_dict(artifact.get("arbitration"))
    if arbitration.get("single_real_submit_candidate") is not True:
        errors.append("arbitration.single_real_submit_candidate must be true")
    if len(promotion_candidates) != sum(
        row.get("promotion_state") == "promotion_candidate" for row in symbol_rows
    ):
        errors.append("promotion_candidates must match symbol readiness rows")
    return errors


def _validate_action_time_input_matches_readiness_row(
    *,
    index: int,
    action_time_input: dict[str, Any],
    readiness_row: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    prefix = f"action_time_lane_inputs[{index}]"
    if not readiness_row:
        return [f"{prefix} must match a symbol_readiness_rows action_time_lane row"]
    if action_time_input.get("signal_state") != "fresh":
        errors.append(f"{prefix} must report fresh signal_state")
    if not str(action_time_input.get("fresh_signal_timestamp_utc") or ""):
        errors.append(f"{prefix}.fresh_signal_timestamp_utc is required")
    if not str(action_time_input.get("fresh_signal_timestamp_source") or ""):
        errors.append(f"{prefix}.fresh_signal_timestamp_source is required")
    if (
        action_time_input.get("fresh_signal_timestamp_source")
        == "action_time_boundary:_artifact_generated_at_utc"
    ):
        errors.append(
            f"{prefix}.fresh_signal_timestamp_source must not be artifact generated_at"
        )
    if action_time_input.get("strategy_signal_fact_side_supported") is not True:
        errors.append(f"{prefix} requires strategy signal fact side support")
    if not str(action_time_input.get("lane_fingerprint") or ""):
        errors.append(f"{prefix}.lane_fingerprint is required")
    if readiness_row.get("promotion_state") != "action_time_lane":
        errors.append(f"{prefix} must come from a promoted action_time_lane row")
    if readiness_row.get("signal_state") != "fresh":
        errors.append(f"{prefix} must come from a fresh signal readiness row")
    for key in (
        "first_blocker",
        "signal_state",
        "scope_state",
        "side",
        "fresh_signal_timestamp_utc",
        "fresh_signal_timestamp_source",
        "lane_fingerprint",
        "strategy_signal_fact_side_supported",
    ):
        if action_time_input.get(key) != readiness_row.get(key):
            errors.append(f"{prefix}.{key} must match symbol_readiness_rows")
    runtime_profile = _as_dict(action_time_input.get("runtime_profile"))
    for key in ("target_notional_usdt", "max_notional", "leverage"):
        if not str(runtime_profile.get(key) or ""):
            errors.append(f"{prefix}.runtime_profile.{key} is required")
    if "no_live_profile_or_sizing_change" not in str(
        runtime_profile.get("authority_boundary") or ""
    ):
        errors.append(f"{prefix}.runtime_profile.authority_boundary is invalid")
    if _as_dict(action_time_input.get("public_facts_state")).get("state") != _as_dict(
        readiness_row.get("public_facts_state")
    ).get("state"):
        errors.append(
            f"{prefix}.public_facts_state.state must match symbol_readiness_rows"
        )
    if _as_dict(action_time_input.get("action_time")).get("status") != _as_dict(
        readiness_row.get("action_time")
    ).get("status"):
        errors.append(f"{prefix}.action_time.status must match symbol_readiness_rows")
    return errors


def _expected_candidate_symbols_by_strategy(
    artifact: dict[str, Any],
) -> dict[str, set[str]]:
    scopes = _owner_authorization_strategy_group_scopes(artifact)
    if scopes:
        return {
            strategy_group_id: {
                str(item)
                for item in _as_dict(scopes.get(strategy_group_id)).get(
                    "candidate_symbols"
                )
                or []
                if str(item or "")
            }
            for strategy_group_id in WIP_LANES
        }
    return {strategy_group_id: set() for strategy_group_id in WIP_LANES}


def _expected_side_scope_by_strategy(
    artifact: dict[str, Any],
) -> dict[str, set[str]]:
    scopes = _owner_authorization_strategy_group_scopes(artifact)
    if scopes:
        return {
            strategy_group_id: {
                str(item)
                for item in _as_dict(scopes.get(strategy_group_id)).get("side_scope")
                or []
                if str(item or "")
            }
            for strategy_group_id in WIP_LANES
        }
    return {strategy_group_id: set() for strategy_group_id in WIP_LANES}


def _owner_authorization_strategy_group_scopes(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    summary = _as_dict(_as_dict(artifact.get("pretrade_runtime")).get("owner_authorization"))
    scopes = summary.get("strategy_group_scopes")
    return scopes if isinstance(scopes, dict) else {}


def _validate_authorized_candidate_universe(
    symbol_rows: list[dict[str, Any]],
    *,
    expected_symbols: dict[str, set[str]],
    expected_sides: dict[str, set[str]],
) -> list[str]:
    errors: list[str] = []
    actual: dict[str, set[str]] = {}
    actual_lanes: dict[str, set[tuple[str, str]]] = {}
    for row in symbol_rows:
        strategy_group_id = str(row.get("strategy_group_id") or "")
        symbol = str(row.get("symbol") or "")
        side = str(row.get("side") or "")
        actual.setdefault(strategy_group_id, set()).add(symbol)
        actual_lanes.setdefault(strategy_group_id, set()).add((symbol, side))
        if symbol in PLACEHOLDER_SYMBOLS:
            errors.append(
                f"symbol_readiness_rows contains placeholder symbol {symbol}"
            )
    for strategy_group_id in WIP_LANES:
        expected_strategy_symbols = expected_symbols.get(strategy_group_id, set())
        actual_symbols = actual.get(strategy_group_id, set())
        if actual_symbols != expected_strategy_symbols:
            errors.append(
                "symbol_readiness_rows must match authorized universe for "
                f"{strategy_group_id}: expected={sorted(expected_strategy_symbols)} "
                f"actual={sorted(actual_symbols)}"
            )
        expected_lanes = {
            (symbol, side)
            for symbol in expected_strategy_symbols
            for side in expected_sides.get(strategy_group_id, set())
        }
        if actual_lanes.get(strategy_group_id, set()) != expected_lanes:
            errors.append(
                "symbol_readiness_rows must match authorized side universe for "
                f"{strategy_group_id}"
            )
    return errors


def _validate_owner_authorization_summary(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    summary = _as_dict(_as_dict(artifact.get("pretrade_runtime")).get("owner_authorization"))
    if not summary:
        return ["pretrade_runtime.owner_authorization is required"]
    if summary.get("schema") != OWNER_AUTHORIZATION_SCHEMA:
        errors.append("pretrade_runtime.owner_authorization.schema is invalid")
    if summary.get("status") != "owner_pretrade_runtime_authorization_recorded":
        errors.append("pretrade_runtime.owner_authorization.status is invalid")
    if summary.get("valid") is not True:
        errors.append("pretrade_runtime.owner_authorization.valid must be true")
    if summary.get("pretrade_candidate_allowed") is not True:
        errors.append(
            "pretrade_runtime.owner_authorization.pretrade_candidate_allowed must be true"
        )
    if summary.get("action_time_rehearsal_allowed") is not True:
        errors.append(
            "pretrade_runtime.owner_authorization.action_time_rehearsal_allowed must be true"
        )
    if summary.get("v0_single_action_time_lane") is not True:
        errors.append(
            "pretrade_runtime.owner_authorization.v0_single_action_time_lane must be true"
        )
    if summary.get("v0_single_real_submit_intent") is not True:
        errors.append(
            "pretrade_runtime.owner_authorization.v0_single_real_submit_intent must be true"
        )
    if set(summary.get("scoped_live_submit_strategy_groups") or []) != set(
        SCOPED_LIVE_SUBMIT_STRATEGIES
    ):
        errors.append(
            "pretrade_runtime.owner_authorization.scoped_live_submit_strategy_groups is invalid"
        )
    if set(summary.get("conditional_hard_gated_strategy_groups") or []) != {
        "BRF2-001"
    }:
        errors.append(
            "pretrade_runtime.owner_authorization.conditional_hard_gated_strategy_groups is invalid"
        )
    boundary = str(summary.get("authority_boundary") or "")
    if "no_exchange_write_bypass" not in boundary:
        errors.append("pretrade_runtime.owner_authorization.authority_boundary is invalid")
    return errors


def _validate_row_owner_authorization(
    prefix: str,
    row: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    authorization = _as_dict(row.get("owner_authorization"))
    strategy_group_id = str(row.get("strategy_group_id") or "")
    symbol = str(row.get("symbol") or "")
    if not authorization:
        return [f"{prefix}.owner_authorization is required"]
    if authorization.get("pretrade_candidate_allowed") is not True:
        errors.append(f"{prefix}.owner_authorization.pretrade_candidate_allowed must be true")
    if authorization.get("action_time_rehearsal_allowed") is not True:
        errors.append(
            f"{prefix}.owner_authorization.action_time_rehearsal_allowed must be true"
        )
    mode = str(authorization.get("live_submit_allowed") or "")
    side = str(row.get("side") or "")
    side_scope = {str(item) for item in authorization.get("side_scope") or []}
    if side not in side_scope:
        errors.append(f"{prefix}.owner_authorization.side_scope must include row side")
    gates = {
        str(item)
        for item in authorization.get("real_submit_required_gates") or []
    }
    common_gates = {
        "fresh_signal",
        "required_facts",
        "server_runtime_coverage",
        "action_time_facts",
        "finalgate",
        "operation_layer",
        "protection",
        "reconciliation",
    }
    if not common_gates.issubset(gates):
        errors.append(f"{prefix}.owner_authorization.real_submit_required_gates incomplete")
    if strategy_group_id == "BRF2-001":
        if mode != "conditional_hard_gated":
            errors.append(
                f"{prefix}.owner_authorization.live_submit_allowed must be conditional_hard_gated"
            )
        if row.get("scope_state") != "conditional_action_time_rehearsal_allowed":
            errors.append(
                f"{prefix}.scope_state must be conditional_action_time_rehearsal_allowed"
            )
        if not {"short_side_disable_clear", "squeeze_clear", "liquidity_clear"}.issubset(gates):
            errors.append(f"{prefix}.owner_authorization.brf2_hard_gates incomplete")
    else:
        if strategy_group_id in SCOPED_LIVE_SUBMIT_STRATEGIES and mode != "scoped":
            errors.append(
                f"{prefix}.owner_authorization.live_submit_allowed must be scoped"
            )
        if (
            strategy_group_id in SCOPED_LIVE_SUBMIT_STRATEGIES
            and row.get("scope_state") != "live_submit_allowed"
        ):
            errors.append(f"{prefix}.scope_state must be live_submit_allowed")
    candidate_symbols = {
        str(item)
        for item in authorization.get("candidate_symbols") or []
        if str(item or "")
    }
    if symbol not in candidate_symbols:
        errors.append(f"{prefix}.owner_authorization.symbol is outside authorized universe")
    boundary = str(authorization.get("authority_boundary") or "")
    if "no_exchange_write_bypass" not in boundary:
        errors.append(f"{prefix}.owner_authorization.authority_boundary is invalid")
    return errors


def _forbidden_true_paths(value: Any, path: str = "") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_TRUE_KEYS and child is True:
                errors.append(f"{child_path} must not be true")
            errors.extend(_forbidden_true_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_forbidden_true_paths(child, f"{path}[{index}]"))
    return errors


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _validate_server_runtime_coverage_identity(
    *,
    prefix: str,
    coverage: dict[str, Any],
    strategy_group_id: str,
    symbol: str,
    side: str,
) -> list[str]:
    if not coverage:
        return [f"{prefix} is required"]
    errors: list[str] = []
    if str(coverage.get("strategy_group_id") or "") != strategy_group_id:
        errors.append(f"{prefix}.strategy_group_id must match row strategy_group_id")
    if str(coverage.get("symbol") or "") != symbol:
        errors.append(f"{prefix}.symbol must match row symbol")
    coverage_side = str(coverage.get("side") or coverage.get("expected_side") or "")
    if coverage_side != side:
        errors.append(f"{prefix}.side must match row side")
    if str(coverage.get("state") or "") not in SERVER_RUNTIME_COVERAGE_STATES:
        errors.append(f"{prefix}.state is invalid")
    blocker = str(coverage.get("blocker_class") or "")
    if blocker not in {"none", *SERVER_RUNTIME_COVERAGE_STATES}:
        errors.append(f"{prefix}.blocker_class is invalid")
    if not str(coverage.get("next_action") or ""):
        errors.append(f"{prefix}.next_action is required")
    if "no_finalgate" not in str(coverage.get("authority_boundary") or ""):
        errors.append(f"{prefix}.authority_boundary is invalid")
    return errors


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


if __name__ == "__main__":
    raise SystemExit(main())
