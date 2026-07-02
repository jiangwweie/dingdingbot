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
    AUTHORITY_BOUNDARY,
    SCHEMA,
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
    errors.extend(_validate_pretrade_runtime(artifact, symbol_rows))
    summary = _as_dict(artifact.get("summary"))
    if summary.get("candidate_count") != len(WIP_LANES):
        errors.append("summary.candidate_count must match active WIP lanes")
    if summary.get("symbol_readiness_count") != len(symbol_rows):
        errors.append("summary.symbol_readiness_count must match readiness rows")
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
    }:
        errors.append(f"{prefix}.scope_state is invalid")
    if row.get("promotion_state") not in {
        "idle",
        "promotion_candidate",
        "action_time_lane",
        "blocked",
    }:
        errors.append(f"{prefix}.promotion_state is invalid")
    if (
        row.get("promotion_state") == "action_time_lane"
        and row.get("scope_state") != "live_submit_allowed"
    ):
        errors.append(f"{prefix}.action_time_lane requires live_submit_allowed")
    if (
        row.get("promotion_state") == "action_time_lane"
        and not _server_runtime_scope_ready(
            _as_dict(row.get("server_runtime_coverage"))
        )
    ):
        errors.append(
            f"{prefix}.action_time_lane requires active server runtime coverage"
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
    runtime = _as_dict(artifact.get("pretrade_runtime"))
    if not runtime:
        errors.append("pretrade_runtime is required")
    counts = runtime.get("candidate_symbols_per_strategy_group")
    if not isinstance(counts, dict):
        errors.append("pretrade_runtime.candidate_symbols_per_strategy_group is required")
        counts = {}
    for strategy_group_id in WIP_LANES:
        count = int(counts.get(strategy_group_id) or 0)
        if count < 2:
            errors.append(
                f"pretrade_runtime requires at least two symbols for {strategy_group_id}"
            )
    promotion_candidates = _dict_rows(artifact.get("promotion_candidates"))
    action_time_inputs = _dict_rows(artifact.get("action_time_lane_inputs"))
    if len(action_time_inputs) > 1:
        errors.append("action_time_lane_inputs must contain at most one real-submit candidate")
    for index, row in enumerate(action_time_inputs):
        if row.get("scope_state") == "readonly_only":
            errors.append(
                f"action_time_lane_inputs[{index}] must not be readonly_only"
            )
        if "no_finalgate" not in str(row.get("authority_boundary") or ""):
            errors.append(f"action_time_lane_inputs[{index}].authority_boundary is invalid")
        if not _server_runtime_scope_ready(
            _as_dict(row.get("server_runtime_coverage"))
        ):
            errors.append(
                f"action_time_lane_inputs[{index}] requires active server runtime coverage"
            )
    arbitration = _as_dict(artifact.get("arbitration"))
    if arbitration.get("single_real_submit_candidate") is not True:
        errors.append("arbitration.single_real_submit_candidate must be true")
    if len(promotion_candidates) != sum(
        row.get("promotion_state") == "promotion_candidate" for row in symbol_rows
    ):
        errors.append("promotion_candidates must match symbol readiness rows")
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


def _server_runtime_scope_ready(runtime_coverage_row: dict[str, Any]) -> bool:
    active_ids = runtime_coverage_row.get("active_runtime_instance_ids") or []
    selected_ids = runtime_coverage_row.get("selected_runtime_instance_ids") or []
    return (
        str(runtime_coverage_row.get("state") or "") == "active_watcher_scope"
        and bool(active_ids)
        and bool(selected_ids)
    )


if __name__ == "__main__":
    raise SystemExit(main())
