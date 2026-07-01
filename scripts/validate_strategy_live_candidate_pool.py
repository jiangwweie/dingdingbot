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
    if len(rows) != len(WIP_LANES):
        errors.append(f"candidate_rows must contain {len(WIP_LANES)} rows")
    strategy_ids = {str(row.get("strategy_group_id") or "") for row in rows}
    if strategy_ids != set(WIP_LANES):
        errors.append("candidate_rows must contain exactly active WIP lanes")
    for index, row in enumerate(rows):
        errors.extend(_validate_candidate_row(index, row))
    summary = _as_dict(artifact.get("summary"))
    if summary.get("candidate_count") != len(WIP_LANES):
        errors.append("summary.candidate_count must match active WIP lanes")
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


if __name__ == "__main__":
    raise SystemExit(main())
