#!/usr/bin/env python3
"""Validate the Daily Live Enablement Table control surface."""

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
    AUTHORITY_BOUNDARY,
    CONTRACT_BLOCKER_CLASSES,
    OWNER_BLOCKERS,
    SCHEMA,
    SOURCE_EXPECTATIONS,
    WIP_LANES,
)


DEFAULT_INPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-daily-live-enablement-table.json"
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
    parser.add_argument("table_json", nargs="?", default=str(DEFAULT_INPUT_JSON))
    args = parser.parse_args(argv)
    path = Path(args.table_json)
    errors = validate_daily_live_enablement_table(_read_json(path))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "daily_live_enablement_table_valid",
                "path": str(path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def validate_daily_live_enablement_table(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if artifact.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    if artifact.get("status") != "daily_live_enablement_table_ready":
        errors.append("status must be daily_live_enablement_table_ready")
    errors.extend(_validate_source_validation(artifact))
    rows = _dict_rows(artifact.get("rows"))
    if len(rows) != len(WIP_LANES):
        errors.append(f"row count must be {len(WIP_LANES)}")
    strategy_ids = [str(row.get("strategy_group_id") or "") for row in rows]
    if set(strategy_ids) != set(WIP_LANES):
        errors.append("rows must contain exactly the active WIP lanes")
    if len(strategy_ids) != len(set(strategy_ids)):
        errors.append("strategy_group_id rows must be unique")
    rank_1_count = sum(row.get("closest_to_live_rank") == 1 for row in rows)
    if rank_1_count != 1:
        errors.append("closest_to_live_rank=1 must appear exactly once")
    ranks = sorted(int(row.get("closest_to_live_rank") or 0) for row in rows)
    if ranks != list(range(1, len(rows) + 1)):
        errors.append("closest_to_live_rank values must be contiguous")
    for index, row in enumerate(rows):
        errors.extend(_validate_row(row, index))
    errors.extend(_forbidden_true_paths(artifact))
    return errors


def _validate_source_validation(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    source_validation = _as_dict(artifact.get("source_validation"))
    if source_validation.get("valid") is not True:
        errors.append("source_validation.valid must be true")
    sources = _as_dict(source_validation.get("sources"))
    for name in SOURCE_EXPECTATIONS:
        row = _as_dict(sources.get(name))
        if not row:
            errors.append(f"source_validation.sources.{name} is required")
            continue
        if row.get("valid") is not True:
            errors.append(f"source_validation.sources.{name}.valid must be true")
        if row.get("present") is not True:
            errors.append(f"source_validation.sources.{name}.present must be true")
        if row.get("schema_valid") is not True:
            errors.append(
                f"source_validation.sources.{name}.schema_valid must be true"
            )
        if row.get("status_valid") is not True:
            errors.append(
                f"source_validation.sources.{name}.status_valid must be true"
            )
    return errors


def _validate_row(row: dict[str, Any], index: int) -> list[str]:
    prefix = f"rows[{index}]"
    errors: list[str] = []
    required = (
        "strategy_group_id",
        "symbol",
        "side",
        "stage",
        "chain_position",
        "first_blocker",
        "first_blocker_evidence",
        "owner_action_required",
        "next_engineering_action",
        "stop_condition",
        "closest_to_live_rank",
        "rank_reason",
        "authority_boundary",
    )
    for key in required:
        if row.get(key) in {None, ""}:
            errors.append(f"{prefix}.{key} is required")
    strategy_group_id = str(row.get("strategy_group_id") or "")
    if strategy_group_id not in WIP_LANES:
        errors.append(f"{prefix}.strategy_group_id is not an active WIP lane")
    blocker = str(row.get("first_blocker") or "")
    if blocker not in CONTRACT_BLOCKER_CLASSES:
        errors.append(f"{prefix}.first_blocker is not a contract blocker")
    if blocker.startswith("fresh_") or blocker in {
        "waiting_for_market",
        "fresh_signal_absent",
        "missing_fact",
        "live_detector_artifact_missing",
    }:
        errors.append(f"{prefix}.first_blocker is a legacy blocker")
    action = str(row.get("next_engineering_action") or "")
    if not action:
        errors.append(f"{prefix}.next_engineering_action is required")
    if any(separator in action for separator in (" and ", " then ", ";", "\n")):
        errors.append(f"{prefix}.next_engineering_action must be one action")
    if not str(row.get("first_blocker_evidence") or ""):
        errors.append(f"{prefix}.first_blocker_evidence is required")
    if not str(row.get("stop_condition") or ""):
        errors.append(f"{prefix}.stop_condition is required")
    owner_required = str(row.get("owner_action_required") or "")
    if owner_required not in {"yes", "no"}:
        errors.append(f"{prefix}.owner_action_required must be yes or no")
    if owner_required == "yes" and blocker not in OWNER_BLOCKERS:
        errors.append(f"{prefix}.owner_action_required is invalid for {blocker}")
    if owner_required == "no" and blocker in OWNER_BLOCKERS:
        errors.append(f"{prefix}.owner_action_required must be yes for {blocker}")
    if row.get("authority_boundary") != AUTHORITY_BOUNDARY:
        errors.append(f"{prefix}.authority_boundary is invalid")
    if blocker == "market_wait_validated":
        validation = _as_dict(row.get("market_wait_validation"))
        if validation.get("valid") is not True:
            errors.append(
                f"{prefix}.market_wait_validated requires complete checklist"
            )
    if row.get("lane_status") == "advanced" and blocker in {
        "artifact_missing",
        "schema_invalid",
    }:
        errors.append(f"{prefix}.artifact-only progress cannot be advanced")
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
