#!/usr/bin/env python3
"""Build the single-lane task packet from Daily Live Enablement rank 1."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_daily_live_enablement_table import (  # noqa: E402
    AUTHORITY_BOUNDARY as DAILY_AUTHORITY_BOUNDARY,
    CONTRACT_BLOCKER_CLASSES,
)


SCHEMA = "brc.single_lane_task_packet.v1"
DEFAULT_DAILY_TABLE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-daily-live-enablement-table.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-single-lane-task-packet.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-single-lane-task-packet.md"
)

BASE_ALLOWED_FILES = [
    "scripts/build_single_lane_task_packet.py",
    "scripts/validate_single_lane_task_packet.py",
    "scripts/build_daily_live_enablement_table.py",
    "scripts/validate_daily_live_enablement_table.py",
    "tests/unit/test_single_lane_task_packet.py",
    "tests/unit/test_daily_live_enablement_table.py",
    "output/runtime-monitor/latest-single-lane-task-packet.json",
    "output/runtime-monitor/latest-single-lane-task-packet.md",
    "output/runtime-monitor/latest-daily-live-enablement-table.json",
    "output/runtime-monitor/latest-daily-live-enablement-table.md",
]
CHAIN_ALLOWED_FILES = {
    "replay_live_parity": [
        "scripts/build_replay_live_parity_audit.py",
        "tests/unit/test_replay_live_parity_audit.py",
        "output/runtime-monitor/latest-replay-live-parity-audit.json",
        "output/runtime-monitor/latest-replay-live-parity-audit.md",
    ],
    "symbol_scope_decision": [
        "scripts/build_strategygroup_tradeability_decision.py",
        "tests/unit/test_strategygroup_tradeability_decision.py",
        "output/runtime-monitor/latest-strategygroup-tradeability-decision.json",
        "output/runtime-monitor/latest-strategygroup-tradeability-decision.md",
    ],
    "action_time_boundary": [
        "scripts/build_strategy_fresh_signal_action_time_boundary.py",
        "tests/unit/test_strategy_fresh_signal_action_time_boundary.py",
        "output/runtime-monitor/latest-strategy-fresh-signal-action-time-boundary.json",
        "output/runtime-monitor/latest-strategy-fresh-signal-action-time-boundary.md",
    ],
    "daily_live_enablement_status": [
        "scripts/run_strategygroup_runtime_local_monitor_sequence.py",
        "tests/unit/test_strategygroup_runtime_local_monitor_sequence.py",
        "output/runtime-monitor/latest-local-monitor-sequence.json",
        "output/runtime-monitor/latest-local-monitor-sequence.md",
    ],
    "tradeability_first_blocker": [
        "scripts/build_strategygroup_tradeability_decision.py",
        "tests/unit/test_strategygroup_tradeability_decision.py",
        "output/runtime-monitor/latest-strategygroup-tradeability-decision.json",
        "output/runtime-monitor/latest-strategygroup-tradeability-decision.md",
    ],
}
FORBIDDEN_FILES = [
    "src/application/execution_orchestrator.py",
    "src/application/order_lifecycle_service.py",
    "src/application/position_projection_service.py",
    "src/application/capital_protection.py",
    "src/infrastructure/exchange_gateway.py",
    "src/application/reconciliation.py",
    "src/application/startup_reconciliation_service.py",
    "live profile files",
    "order sizing defaults",
    "credential or secret files",
    "FinalGate bypass paths",
    "Operation Layer bypass paths",
]
AUTHORITY_BOUNDARY = (
    "single_lane_task_packet_is_non_executing; "
    "no_finalgate_no_operation_layer_no_exchange_write_no_live_profile_or_sizing_change"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-table-json", default=str(DEFAULT_DAILY_TABLE_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_single_lane_task_packet(
        daily_table=_read_json(Path(args.daily_table_json)),
        source=str(_repo_relative(Path(args.daily_table_json))),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact) + "\n")
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "task_id": artifact["task_id"],
                "active_lane": (
                    f"{artifact['active_lane']['strategy_group_id']}:"
                    f"{artifact['active_lane']['symbol']}"
                ),
                "first_blocker": artifact["first_blocker"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def build_single_lane_task_packet(
    *,
    daily_table: dict[str, Any],
    source: str = "output/runtime-monitor/latest-daily-live-enablement-table.json",
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    row = _rank_1_row(daily_table)
    generated = (
        generated_at_utc
        or str(daily_table.get("generated_at_utc") or "")
        or datetime.now(timezone.utc).isoformat()
    )
    strategy_group_id = str(row.get("strategy_group_id") or "")
    symbol = str(row.get("symbol") or "")
    first_blocker = str(row.get("first_blocker") or "")
    chain_position = str(row.get("chain_position") or "")
    next_action = str(row.get("next_engineering_action") or "")
    task_id = _task_id(strategy_group_id, first_blocker)
    allowed_files = _unique(
        BASE_ALLOWED_FILES + CHAIN_ALLOWED_FILES.get(chain_position, [])
    )
    expected_change = _expected_state_change(
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        first_blocker=first_blocker,
    )
    return {
        "schema": SCHEMA,
        "status": "single_lane_task_packet_ready",
        "generated_at_utc": generated,
        "source": source,
        "source_rank": 1,
        "source_row_fingerprint": _row_fingerprint(row),
        "task_id": task_id,
        "active_lane": {
            "strategy_group_id": strategy_group_id,
            "symbol": symbol,
            "side": str(row.get("side") or ""),
            "stage": str(row.get("stage") or ""),
        },
        "chain_position": chain_position,
        "first_blocker": first_blocker,
        "evidence": str(row.get("first_blocker_evidence") or ""),
        "expected_state_change": expected_change,
        "next_action": next_action,
        "allowed_files": allowed_files,
        "forbidden_files": FORBIDDEN_FILES,
        "stop_condition": str(row.get("stop_condition") or ""),
        "tests": _tests_for(chain_position),
        "done_when": (
            f"{strategy_group_id}/{symbol} no longer has {first_blocker}, "
            "or the Daily Table reclassifies the same lane to a more precise first blocker."
        ),
        "authority_boundary": AUTHORITY_BOUNDARY,
        "source_authority_boundary": str(
            row.get("authority_boundary") or DAILY_AUTHORITY_BOUNDARY
        ),
        "owner_action_required": str(row.get("owner_action_required") or "no"),
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


def _rank_1_row(daily_table: dict[str, Any]) -> dict[str, Any]:
    rows = _dict_rows(daily_table.get("rows"))
    for row in rows:
        if row.get("closest_to_live_rank") == 1:
            return row
    return {}


def _task_id(strategy_group_id: str, first_blocker: str) -> str:
    strategy = re.sub(r"[^A-Z0-9]+", "-", strategy_group_id.upper()).strip("-")
    blocker = re.sub(r"[^A-Z0-9]+", "-", first_blocker.upper()).strip("-")
    if not strategy or not blocker:
        return "P0-SINGLE-LANE-TASK-PACKET-INVALID"
    return f"P0-{strategy}-{blocker}-CLOSURE"


def _expected_state_change(
    *,
    strategy_group_id: str,
    symbol: str,
    first_blocker: str,
) -> str:
    return (
        f"{strategy_group_id}/{symbol} first_blocker changes from "
        f"{first_blocker} to the next precise blocker, market_wait_validated, "
        "or lane exit under the WIP stop rule."
    )


def _tests_for(chain_position: str) -> list[str]:
    tests = [
        "python3 -m py_compile scripts/build_single_lane_task_packet.py scripts/validate_single_lane_task_packet.py",
        "pytest -q tests/unit/test_single_lane_task_packet.py",
        "python3 scripts/validate_single_lane_task_packet.py output/runtime-monitor/latest-single-lane-task-packet.json",
        "python3 scripts/validate_output_artifact_scope.py --git-status",
        "git diff --check",
    ]
    if chain_position == "replay_live_parity":
        tests.insert(
            0,
            "pytest -q tests/unit/test_replay_live_parity_audit.py tests/unit/test_daily_live_enablement_table.py",
        )
    elif chain_position == "action_time_boundary":
        tests.insert(
            0,
            "pytest -q tests/unit/test_strategy_fresh_signal_action_time_boundary.py tests/unit/test_daily_live_enablement_table.py",
        )
    elif chain_position == "symbol_scope_decision":
        tests.insert(
            0,
            "pytest -q tests/unit/test_strategygroup_tradeability_decision.py tests/unit/test_daily_live_enablement_table.py",
        )
    return tests


def _row_fingerprint(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_group_id": row.get("strategy_group_id"),
        "symbol": row.get("symbol"),
        "first_blocker": row.get("first_blocker"),
        "closest_to_live_rank": row.get("closest_to_live_rank"),
        "next_engineering_action": row.get("next_engineering_action"),
    }


def _markdown(artifact: dict[str, Any]) -> str:
    lane = _as_dict(artifact.get("active_lane"))
    lines = [
        "## Single Lane Task Packet",
        "",
        f"- Task ID: `{artifact.get('task_id')}`",
        (
            "- Active lane: "
            f"`{lane.get('strategy_group_id')} / {lane.get('symbol')} / {lane.get('side')}`"
        ),
        f"- Chain position: `{artifact.get('chain_position')}`",
        f"- First blocker: `{artifact.get('first_blocker')}`",
        f"- Evidence: `{artifact.get('evidence')}`",
        f"- Expected state change: `{artifact.get('expected_state_change')}`",
        f"- Next action: `{artifact.get('next_action')}`",
        f"- Stop condition: `{artifact.get('stop_condition')}`",
        f"- Authority boundary: `{artifact.get('authority_boundary')}`",
        "",
        "### Allowed Files",
        "",
    ]
    lines.extend(f"- `{item}`" for item in artifact.get("allowed_files") or [])
    lines.extend(["", "### Forbidden Files", ""])
    for item in artifact.get("forbidden_files") or []:
        if "/" in str(item):
            lines.append(f"- `{item}`")
        else:
            lines.append(f"- {item}")
    lines.extend(["", "### Done When", "", f"`{artifact.get('done_when')}`"])
    return "\n".join(lines)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo_relative(path: Path) -> Path:
    try:
        return path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return path


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
