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
P1_ACCEPTED_STATUSES = {"cleared", "waived", "waived_with_reason"}
RESIDUAL_DEPLOY_BLOCKERS = {
    "artifact_missing",
    "schema_invalid",
    "detector_not_attached",
    "watcher_tick_missing",
    "scope_not_attached",
    "replay_live_rule_mismatch",
    "action_time_boundary_not_reproduced",
    "policy_scope_missing",
    "runtime_profile_scope_missing",
    "active_position_resolution",
    "hard_safety_stop",
}
ACTION_TIME_BLOCKED_STATUSES = {
    "blocked_public_facts",
    "blocked_action_time_rehearsal",
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
        "waiting_for_market",
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
    checks = candidate_pool.get("checks") if isinstance(candidate_pool, dict) else {}
    if not isinstance(checks, dict):
        checks = {}
    p0_p1_review = _dict_rows(candidate_pool.get("p0_p1_review"))
    candidate_rows = _dict_rows(candidate_pool.get("candidate_rows"))
    errors: list[str] = []

    recalculated_p0_cleared = _recalculate_p0_cleared(p0_p1_review)
    recalculated_p1_cleared_or_waived = _recalculate_p1_cleared_or_waived(
        p0_p1_review
    )
    residual_errors = _residual_candidate_readiness_errors(candidate_rows)
    recalculated_deploy_ready = (
        recalculated_p0_cleared
        and recalculated_p1_cleared_or_waived
        and not residual_errors
    )

    if summary.get("p0_cleared") is not True:
        errors.append("candidate_pool.summary.p0_cleared must be true before deploy")
    if summary.get("p1_cleared_or_waived") is not True:
        errors.append(
            "candidate_pool.summary.p1_cleared_or_waived must be true before deploy"
        )
    if summary.get("deploy_ready") is not True:
        errors.append("candidate_pool.summary.deploy_ready must be true before deploy")
    if summary.get("p0_cleared") != recalculated_p0_cleared:
        errors.append(
            "candidate_pool.summary.p0_cleared does not match p0_p1_review"
        )
    if checks.get("p0_cleared") != recalculated_p0_cleared:
        errors.append("candidate_pool.checks.p0_cleared does not match p0_p1_review")
    if summary.get("p1_cleared_or_waived") != recalculated_p1_cleared_or_waived:
        errors.append(
            "candidate_pool.summary.p1_cleared_or_waived does not match p0_p1_review"
        )
    if checks.get("p1_cleared_or_waived") != recalculated_p1_cleared_or_waived:
        errors.append(
            "candidate_pool.checks.p1_cleared_or_waived does not match p0_p1_review"
        )
    errors.extend(residual_errors)
    if summary.get("deploy_ready") != recalculated_deploy_ready:
        errors.append(
            "candidate_pool.summary.deploy_ready does not match recalculated deploy readiness"
        )
    if checks.get("deploy_ready") != recalculated_deploy_ready:
        errors.append(
            "candidate_pool.checks.deploy_ready does not match recalculated deploy readiness"
        )
    return errors


def _recalculate_p0_cleared(p0_p1_review: list[dict[str, Any]]) -> bool:
    p0_rows = [row for row in p0_p1_review if row.get("priority") == "P0"]
    return bool(p0_rows) and all(row.get("status") == "cleared" for row in p0_rows)


def _recalculate_p1_cleared_or_waived(p0_p1_review: list[dict[str, Any]]) -> bool:
    p1_rows = [row for row in p0_p1_review if row.get("priority") == "P1"]
    return bool(p1_rows) and all(
        row.get("status") in P1_ACCEPTED_STATUSES for row in p1_rows
    )


def _residual_candidate_readiness_errors(candidate_rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(candidate_rows):
        strategy_group_id = str(row.get("strategy_group_id") or f"row_{index}")
        blocker = str(row.get("first_blocker") or "")
        if blocker in RESIDUAL_DEPLOY_BLOCKERS:
            errors.append(
                "candidate_pool.candidate_rows"
                f"[{index}] {strategy_group_id} residual blocker {blocker} "
                "prevents deploy_ready"
            )
        if str(row.get("owner_action_required") or "no") == "yes":
            errors.append(
                "candidate_pool.candidate_rows"
                f"[{index}] {strategy_group_id} owner_action_required=yes "
                "prevents deploy_ready without explicit policy waiver"
            )
        readiness = _as_dict(row.get("action_time_readiness"))
        readiness_status = str(readiness.get("status") or "")
        if readiness_status in ACTION_TIME_BLOCKED_STATUSES:
            errors.append(
                "candidate_pool.candidate_rows"
                f"[{index}] {strategy_group_id} action_time_readiness.status="
                f"{readiness_status} prevents deploy_ready"
            )
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


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
