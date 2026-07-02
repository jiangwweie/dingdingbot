from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO_ROOT / "scripts" / "build_single_lane_task_packet.py"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_single_lane_task_packet.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _builder():
    return _load_module(BUILDER_PATH, "build_single_lane_task_packet")


def _validator():
    return _load_module(VALIDATOR_PATH, "validate_single_lane_task_packet")


def _daily_table() -> dict:
    return {
        "schema": "brc.daily_live_enablement_table.v1",
        "status": "daily_live_enablement_table_ready",
        "rows": [
            {
                "strategy_group_id": "MPG-001",
                "symbol": "SOLUSDT",
                "side": "long",
                "stage": "armed",
                "chain_position": "replay_live_parity",
                "first_blocker": "watcher_tick_missing",
                "first_blocker_evidence": (
                    "output/runtime-monitor/latest-replay-live-parity-audit.json:"
                    "MPG-001/SOLUSDT blocker_class=watcher_tick_missing"
                ),
                "owner_action_required": "no",
                "next_engineering_action": (
                    "refresh_or_repair_watcher_public_fact_input"
                ),
                "stop_condition": (
                    "watcher/public facts tick is present for the selected lane"
                ),
                "closest_to_live_rank": 1,
                "authority_boundary": (
                    "daily_table_is_read_model; "
                    "no_finalgate_no_operation_layer_no_exchange_write"
                ),
            },
            {
                "strategy_group_id": "SOR-001",
                "symbol": "ETHUSDT",
                "side": "long",
                "stage": "armed",
                "chain_position": "action_time_boundary",
                "first_blocker": "action_time_boundary_not_reproduced",
                "first_blocker_evidence": "source",
                "owner_action_required": "no",
                "next_engineering_action": (
                    "repair_non_executing_action_time_rehearsal_path"
                ),
                "stop_condition": "candidate/auth boundary is reproduced",
                "closest_to_live_rank": 2,
                "authority_boundary": (
                    "daily_table_is_read_model; "
                    "no_finalgate_no_operation_layer_no_exchange_write"
                ),
            },
        ],
    }


def test_single_lane_packet_builds_from_rank_one_daily_row():
    packet = _builder().build_single_lane_task_packet(
        daily_table=_daily_table(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    assert packet["schema"] == "brc.single_lane_task_packet.v1"
    assert packet["status"] == "single_lane_task_packet_ready"
    assert packet["task_id"] == "P0-MPG-001-WATCHER-TICK-MISSING-CLOSURE"
    assert packet["active_lane"]["strategy_group_id"] == "MPG-001"
    assert packet["active_lane"]["symbol"] == "SOLUSDT"
    assert packet["first_blocker"] == "watcher_tick_missing"
    assert packet["source_rank"] == 1
    assert "output/runtime-monitor/latest-*.json" not in packet["allowed_files"]
    assert "scripts/build_replay_live_parity_audit.py" in packet["allowed_files"]
    assert _validator().validate_single_lane_task_packet(packet) == []


def test_single_lane_packet_validator_rejects_broad_output_glob():
    packet = _builder().build_single_lane_task_packet(
        daily_table=_daily_table(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )
    packet["allowed_files"].append("output/runtime-monitor/latest-*.json")

    errors = _validator().validate_single_lane_task_packet(packet)

    assert any("not glob" in error for error in errors)


def test_single_lane_packet_validator_rejects_exchange_authority():
    packet = _builder().build_single_lane_task_packet(
        daily_table=_daily_table(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )
    packet["safety_invariants"]["calls_exchange_write"] = True

    errors = _validator().validate_single_lane_task_packet(packet)

    assert any("calls_exchange_write" in error for error in errors)


def test_single_lane_packet_cli_and_validator_cli_round_trip(tmp_path: Path):
    daily_table = tmp_path / "daily.json"
    packet_json = tmp_path / "packet.json"
    packet_md = tmp_path / "packet.md"
    daily_table.write_text(json.dumps(_daily_table()), encoding="utf-8")

    build = subprocess.run(
        [
            sys.executable,
            str(BUILDER_PATH),
            "--daily-table-json",
            str(daily_table),
            "--output-json",
            str(packet_json),
            "--output-owner-progress",
            str(packet_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    assert packet_json.exists()
    assert packet_md.exists()

    validate = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(packet_json)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr


def test_single_lane_packet_cli_missing_rank_one_does_not_validate(tmp_path: Path):
    daily_table = tmp_path / "daily.json"
    packet_json = tmp_path / "packet.json"
    packet_md = tmp_path / "packet.md"
    table = _daily_table()
    table["rows"][0]["closest_to_live_rank"] = 2
    daily_table.write_text(json.dumps(table), encoding="utf-8")

    build = subprocess.run(
        [
            sys.executable,
            str(BUILDER_PATH),
            "--daily-table-json",
            str(daily_table),
            "--output-json",
            str(packet_json),
            "--output-owner-progress",
            str(packet_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr

    validate = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(packet_json)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert validate.returncode == 1
    assert "active_lane.strategy_group_id" in validate.stderr
