#!/usr/bin/env python3
"""Validate a single-lane task packet control artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_daily_live_enablement_table import CONTRACT_BLOCKER_CLASSES  # noqa: E402
from scripts.build_single_lane_task_packet import (  # noqa: E402
    AUTHORITY_BOUNDARY,
    MARKET_WAIT_BLOCKERS,
    MARKET_WAIT_STATUS,
    READY_STATUS,
    SCHEMA,
)


DEFAULT_INPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-single-lane-task-packet.json"
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
    parser.add_argument("packet_json", nargs="?", default=str(DEFAULT_INPUT_JSON))
    args = parser.parse_args(argv)
    path = Path(args.packet_json)
    errors = validate_single_lane_task_packet(_read_json(path))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "single_lane_task_packet_valid",
                "path": str(path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def validate_single_lane_task_packet(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if artifact.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    status = str(artifact.get("status") or "")
    if status not in {READY_STATUS, MARKET_WAIT_STATUS}:
        errors.append(
            f"status must be {READY_STATUS} or {MARKET_WAIT_STATUS}"
        )
    if artifact.get("source_rank") != 1:
        errors.append("source_rank must be 1")
    if not str(artifact.get("source") or ""):
        errors.append("source is required")
    lane = _as_dict(artifact.get("active_lane"))
    for key in ("strategy_group_id", "symbol", "side", "stage"):
        if not str(lane.get(key) or ""):
            errors.append(f"active_lane.{key} is required")
    required = (
        "task_id",
        "chain_position",
        "first_blocker",
        "evidence",
        "expected_state_change",
        "next_action",
        "stop_condition",
        "done_when",
        "authority_boundary",
        "owner_action_required",
    )
    for key in required:
        if not str(artifact.get(key) or ""):
            errors.append(f"{key} is required")
    blocker = str(artifact.get("first_blocker") or "")
    if blocker not in CONTRACT_BLOCKER_CLASSES:
        errors.append("first_blocker must be a contract blocker")
    task_id = str(artifact.get("task_id") or "")
    if blocker in MARKET_WAIT_BLOCKERS:
        if status != MARKET_WAIT_STATUS:
            errors.append("market blocker must use not_applicable_market_wait status")
        if task_id.startswith("P0-") or task_id.endswith("-CLOSURE"):
            errors.append("market blocker must not generate a P0 closure task")
    elif status != READY_STATUS:
        errors.append("non-market blocker must use single_lane_task_packet_ready")
    if artifact.get("authority_boundary") != AUTHORITY_BOUNDARY:
        errors.append("authority_boundary is invalid")
    if artifact.get("owner_action_required") not in {"yes", "no"}:
        errors.append("owner_action_required must be yes or no")
    errors.extend(_validate_allowed_files(artifact))
    errors.extend(_forbidden_true_paths(artifact))
    return errors


def _validate_allowed_files(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allowed_files = _string_list(artifact.get("allowed_files"))
    forbidden_files = _string_list(artifact.get("forbidden_files"))
    if not allowed_files:
        errors.append("allowed_files is required")
    if not forbidden_files:
        errors.append("forbidden_files is required")
    for item in allowed_files:
        if item in forbidden_files:
            errors.append(f"allowed_files must not include forbidden path {item}")
        if "*" in item:
            errors.append(f"allowed_files must use exact paths, not glob {item}")
        if item.startswith("output/") and item not in {
            "output/runtime-monitor/latest-single-lane-task-packet.json",
            "output/runtime-monitor/latest-single-lane-task-packet.md",
            "output/runtime-monitor/latest-daily-live-enablement-table.json",
            "output/runtime-monitor/latest-daily-live-enablement-table.md",
            "output/runtime-monitor/latest-strategygroup-tradeability-decision.json",
            "output/runtime-monitor/latest-strategygroup-tradeability-decision.md",
            "output/runtime-monitor/latest-replay-live-parity-audit.json",
            "output/runtime-monitor/latest-replay-live-parity-audit.md",
            "output/runtime-monitor/latest-strategy-fresh-signal-action-time-boundary.json",
            "output/runtime-monitor/latest-strategy-fresh-signal-action-time-boundary.md",
            "output/runtime-monitor/latest-local-monitor-sequence.json",
            "output/runtime-monitor/latest-local-monitor-sequence.md",
        }:
            errors.append(f"allowed output file is not a control snapshot: {item}")
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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


if __name__ == "__main__":
    raise SystemExit(main())
