#!/usr/bin/env python3
"""Validate the non-authority deploy gate for the live candidate pool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_daily_live_enablement_table import (  # noqa: E402
    validate_daily_live_enablement_table,
)
from scripts.validate_output_artifact_scope import (  # noqa: E402
    DEFAULT_MANIFEST,
    control_snapshot_paths,
    validate_changed_output_paths,
    validate_manifest,
)
from scripts.validate_single_lane_task_packet import (  # noqa: E402
    validate_single_lane_task_packet,
)
from scripts.validate_strategy_live_candidate_pool import (  # noqa: E402
    validate_strategy_live_candidate_pool,
)


DEFAULT_CANDIDATE_POOL_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-live-candidate-pool.json"
)
DEFAULT_DAILY_TABLE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-daily-live-enablement-table.json"
)
DEFAULT_SINGLE_LANE_TASK_PACKET_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-single-lane-task-packet.json"
)
DEFAULT_LOCAL_MONITOR_SEQUENCE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-local-monitor-sequence.json"
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
    parser.add_argument(
        "--candidate-pool-json", default=str(DEFAULT_CANDIDATE_POOL_JSON)
    )
    parser.add_argument("--daily-table-json", default=str(DEFAULT_DAILY_TABLE_JSON))
    parser.add_argument(
        "--single-lane-task-packet-json",
        default=str(DEFAULT_SINGLE_LANE_TASK_PACKET_JSON),
    )
    parser.add_argument(
        "--local-monitor-sequence-json",
        default=str(DEFAULT_LOCAL_MONITOR_SEQUENCE_JSON),
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument(
        "--skip-git-output-status",
        action="store_true",
        help="Skip git-status output scope check for fixture-only validation.",
    )
    args = parser.parse_args(argv)

    paths = {
        "candidate_pool": Path(args.candidate_pool_json),
        "daily_table": Path(args.daily_table_json),
        "single_lane_task_packet": Path(args.single_lane_task_packet_json),
        "local_monitor_sequence": Path(args.local_monitor_sequence_json),
    }
    artifacts = {name: _read_json(path) for name, path in paths.items()}
    manifest = _read_json(Path(args.manifest))
    errors = validate_strategy_live_candidate_pool(artifacts["candidate_pool"])
    errors.extend(validate_daily_live_enablement_table(artifacts["daily_table"]))
    errors.extend(validate_single_lane_task_packet(artifacts["single_lane_task_packet"]))
    errors.extend(_validate_local_monitor_sequence(artifacts["local_monitor_sequence"]))
    errors.extend(validate_manifest(manifest))
    errors.extend(_validate_manifest_contains_deploy_paths(manifest))
    if not args.skip_git_output_status:
        errors.extend(_validate_git_output_scope(manifest))
    errors.extend(_validate_deploy_readiness(artifacts["candidate_pool"]))
    errors.extend(_forbidden_true_paths(artifacts))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            json.dumps(
                {
                    "status": "strategy_live_candidate_pool_deploy_gate_blocked",
                    "deploy_ready": False,
                    "error_count": len(errors),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": "strategy_live_candidate_pool_deploy_gate_valid",
                "deploy_ready": True,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def validate_strategy_live_candidate_pool_deploy_gate(
    *,
    candidate_pool: dict[str, Any],
    daily_table: dict[str, Any],
    single_lane_task_packet: dict[str, Any],
    local_monitor_sequence: dict[str, Any],
    manifest: dict[str, Any],
    changed_output_paths: list[str] | None = None,
) -> list[str]:
    errors = validate_strategy_live_candidate_pool(candidate_pool)
    errors.extend(validate_daily_live_enablement_table(daily_table))
    errors.extend(validate_single_lane_task_packet(single_lane_task_packet))
    errors.extend(_validate_local_monitor_sequence(local_monitor_sequence))
    errors.extend(validate_manifest(manifest))
    errors.extend(_validate_manifest_contains_deploy_paths(manifest))
    if changed_output_paths is not None:
        errors.extend(validate_changed_output_paths(changed_output_paths, manifest))
    errors.extend(_validate_deploy_readiness(candidate_pool))
    errors.extend(_forbidden_true_paths(
        {
            "candidate_pool": candidate_pool,
            "daily_table": daily_table,
            "single_lane_task_packet": single_lane_task_packet,
            "local_monitor_sequence": local_monitor_sequence,
        }
    ))
    return errors


def _validate_local_monitor_sequence(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if artifact.get("status") not in {
        "local_monitor_sequence_complete",
        "temporarily_unavailable_monitor_refresh_needed",
    }:
        errors.append("local_monitor_sequence.status is not accepted for deploy gate validation")
    steps = {
        str(row.get("name") or ""): row
        for row in artifact.get("steps") or []
        if isinstance(row, dict)
    }
    for name in (
        "daily_live_enablement_table",
        "validate_daily_live_enablement_table",
        "single_lane_task_packet",
        "validate_single_lane_task_packet",
        "strategy_live_candidate_pool",
        "validate_strategy_live_candidate_pool",
    ):
        row = steps.get(name)
        if not row:
            errors.append(f"local_monitor_sequence.steps.{name} is required")
            continue
        if row.get("returncode") != 0:
            errors.append(f"local_monitor_sequence.steps.{name}.returncode must be 0")
    return errors


def _validate_manifest_contains_deploy_paths(manifest: dict[str, Any]) -> list[str]:
    allowed = control_snapshot_paths(manifest)
    required = {
        "output/runtime-monitor/latest-daily-live-enablement-table.json",
        "output/runtime-monitor/latest-daily-live-enablement-table.md",
        "output/runtime-monitor/latest-single-lane-task-packet.json",
        "output/runtime-monitor/latest-single-lane-task-packet.md",
        "output/runtime-monitor/latest-strategy-live-candidate-pool.json",
        "output/runtime-monitor/latest-strategy-live-candidate-pool.md",
    }
    missing = sorted(required - allowed)
    return [f"manifest missing deploy control snapshot {path}" for path in missing]


def _validate_git_output_scope(manifest: dict[str, Any]) -> list[str]:
    from scripts.validate_output_artifact_scope import _git_changed_output_paths

    return validate_changed_output_paths(_git_changed_output_paths(REPO_ROOT), manifest)


def _validate_deploy_readiness(candidate_pool: dict[str, Any]) -> list[str]:
    summary = candidate_pool.get("summary") if isinstance(candidate_pool, dict) else {}
    if not isinstance(summary, dict):
        return ["candidate_pool.summary is required"]
    errors: list[str] = []
    if summary.get("p0_cleared") is not True:
        errors.append("candidate_pool.summary.p0_cleared must be true before deploy")
    if summary.get("p1_cleared_or_waived") is not True:
        errors.append(
            "candidate_pool.summary.p1_cleared_or_waived must be true before deploy"
        )
    if summary.get("deploy_ready") is not True:
        errors.append("candidate_pool.summary.deploy_ready must be true before deploy")
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


if __name__ == "__main__":
    raise SystemExit(main())
