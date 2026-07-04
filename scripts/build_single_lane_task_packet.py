#!/usr/bin/env python3
"""Build the single-lane task packet from Daily Live Enablement rank 1."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_daily_live_enablement_table import (  # noqa: E402
    AUTHORITY_BOUNDARY as DAILY_AUTHORITY_BOUNDARY,
    CONTRACT_BLOCKER_CLASSES,
    build_daily_live_enablement_table_from_control_state,
)
from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
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
MARKET_WAIT_BLOCKERS = {
    "computed_not_satisfied",
    "market_wait_validated",
}
READY_STATUS = "single_lane_task_packet_ready"
MARKET_WAIT_STATUS = "single_lane_task_packet_not_applicable_market_wait"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-table-json")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument(
        "--database-url",
        default=os.getenv("PG_DATABASE_URL", ""),
        help=(
            "PostgreSQL DSN for the DB-backed production current source. "
            "When omitted, the legacy daily-table JSON path is used only for "
            "local migration comparison."
        ),
    )
    parser.add_argument(
        "--require-database-url",
        action="store_true",
        help="Fail instead of falling back to legacy JSON inputs when PG_DATABASE_URL is absent.",
    )
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite/non-PG DSNs only in tests.",
    )
    parser.add_argument(
        "--allow-local-file-diagnostic",
        action="store_true",
        help=(
            "Allow explicit local Daily Table JSON input for migration diagnostics "
            "only. Production current Single Lane Packet must use PG."
        ),
    )
    args = parser.parse_args(argv)

    if args.require_database_url and not args.database_url:
        print(
            "ERROR: PG_DATABASE_URL is required for DB-backed Single Lane Packet",
            file=sys.stderr,
        )
        return 2

    if args.database_url:
        if not args.database_url.startswith(
            ("postgresql://", "postgresql+psycopg://")
        ) and not args.allow_non_postgres_for_test:
            print(
                "ERROR: DB-backed Single Lane Packet requires PostgreSQL DSN",
                file=sys.stderr,
            )
            return 2
        engine = sa.create_engine(args.database_url)
        try:
            with engine.connect() as conn:
                repository = PgBackedRuntimeControlStateRepository(conn)
                artifact = build_single_lane_task_packet_from_control_state(
                    repository.read_control_state(),
                )
        finally:
            engine.dispose()
    else:
        if not args.allow_local_file_diagnostic:
            print(
                "ERROR: PG_DATABASE_URL is required for DB-backed Single Lane Packet; "
                "use --allow-local-file-diagnostic only for explicit local diagnostics",
                file=sys.stderr,
            )
            return 2
        if not args.daily_table_json:
            print(
                "ERROR: explicit local diagnostic input required: --daily-table-json",
                file=sys.stderr,
            )
            return 2
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
    market_wait = first_blocker in MARKET_WAIT_BLOCKERS
    task_id = (
        _market_wait_packet_id(strategy_group_id, first_blocker)
        if market_wait
        else _task_id(strategy_group_id, first_blocker)
    )
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
        "status": MARKET_WAIT_STATUS if market_wait else READY_STATUS,
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
        "expected_state_change": (
            _market_wait_expected_state_change(
                strategy_group_id=strategy_group_id,
                symbol=symbol,
                first_blocker=first_blocker,
            )
            if market_wait
            else expected_change
        ),
        "next_action": next_action,
        "allowed_files": allowed_files,
        "forbidden_files": FORBIDDEN_FILES,
        "stop_condition": str(row.get("stop_condition") or ""),
        "tests": _tests_for(chain_position),
        "done_when": (
            _market_wait_done_when(
                strategy_group_id=strategy_group_id,
                symbol=symbol,
                first_blocker=first_blocker,
            )
            if market_wait
            else (
                f"{strategy_group_id}/{symbol} no longer has {first_blocker}, "
                "or the Daily Table reclassifies the same lane to a more precise first blocker."
            )
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


def build_single_lane_task_packet_from_control_state(
    control_state: dict[str, Any],
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    if control_state.get("source_mode") != "db_backed":
        raise ValueError("Single Lane Packet production path requires DB-backed state")
    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    daily_table = build_daily_live_enablement_table_from_control_state(
        control_state,
        generated_at_utc=generated,
    )
    artifact = build_single_lane_task_packet(
        daily_table=daily_table,
        source="pg_runtime_control_state:daily_live_enablement_table",
        generated_at_utc=generated,
    )
    artifact["source_mode"] = "db_backed"
    artifact["projection_target"] = "production_current"
    artifact["control_state_watermark"] = {
        "schema": str(control_state.get("schema") or ""),
        "table_counts": _as_dict(control_state.get("table_counts")),
    }
    return artifact


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
    if first_blocker == "action_time_preflight_ready":
        return f"P0-{strategy}-ACTION-TIME-PREFLIGHT-INPUT"
    return f"P0-{strategy}-{blocker}-CLOSURE"


def _market_wait_packet_id(strategy_group_id: str, first_blocker: str) -> str:
    strategy = re.sub(r"[^A-Z0-9]+", "-", strategy_group_id.upper()).strip("-")
    blocker = re.sub(r"[^A-Z0-9]+", "-", first_blocker.upper()).strip("-")
    if not strategy or not blocker:
        return "SINGLE-LANE-MARKET-WAIT-NOT-APPLICABLE"
    return f"OBSERVE-{strategy}-{blocker}"


def _expected_state_change(
    *,
    strategy_group_id: str,
    symbol: str,
    first_blocker: str,
) -> str:
    if first_blocker == "action_time_preflight_ready":
        return (
            f"{strategy_group_id}/{symbol} produces a non-executing FinalGate "
            "preflight input, or reclassifies to the next precise blocker before "
            "any live submit authority is granted."
        )
    return (
        f"{strategy_group_id}/{symbol} first_blocker changes from "
        f"{first_blocker} to the next precise blocker, market_wait_validated, "
        "or lane exit under the WIP stop rule."
    )


def _market_wait_expected_state_change(
    *,
    strategy_group_id: str,
    symbol: str,
    first_blocker: str,
) -> str:
    return (
        f"{strategy_group_id}/{symbol} remains under observation while "
        f"{first_blocker} is market-owned; no engineering closure task is created."
    )


def _market_wait_done_when(
    *,
    strategy_group_id: str,
    symbol: str,
    first_blocker: str,
) -> str:
    return (
        f"{strategy_group_id}/{symbol} exits market wait when detector facts change, "
        f"or Daily Table reclassifies {first_blocker} to a non-market first blocker."
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
        f"- Status: `{artifact.get('status')}`",
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
