from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = (
    REPO_ROOT / "scripts" / "validate_strategy_live_candidate_pool_deploy_gate.py"
)
CANDIDATE_POOL_TEST_PATH = REPO_ROOT / "tests/unit/test_strategy_live_candidate_pool.py"
DAILY_TABLE_TEST_PATH = REPO_ROOT / "tests/unit/test_daily_live_enablement_table.py"
SINGLE_LANE_BUILDER_PATH = REPO_ROOT / "scripts/build_single_lane_task_packet.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "validate_strategy_live_candidate_pool_deploy_gate",
        VALIDATOR_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_test_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidate_pool_test_module():
    return _load_test_module(CANDIDATE_POOL_TEST_PATH, "candidate_pool_test_fixtures")


def _daily_table() -> dict:
    module = _load_test_module(DAILY_TABLE_TEST_PATH, "daily_table_test_fixtures")
    return module._valid_table()


def _single_lane() -> dict:
    spec = importlib.util.spec_from_file_location(
        "build_single_lane_task_packet_for_deploy_gate_test",
        SINGLE_LANE_BUILDER_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.build_single_lane_task_packet(
        daily_table=_daily_table(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )


def _candidate_pool(deploy_ready: bool = False) -> dict:
    candidate_fixtures = _candidate_pool_test_module()
    artifact = candidate_fixtures._builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=candidate_fixtures._tradeability(),
        replay_live_parity=candidate_fixtures._parity(),
        action_time_boundary=candidate_fixtures._action_time(),
        single_lane_task_packet=_single_lane(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )
    artifact["summary"]["p0_cleared"] = deploy_ready
    artifact["summary"]["p1_cleared_or_waived"] = deploy_ready
    artifact["summary"]["deploy_ready"] = deploy_ready
    artifact["checks"]["p0_cleared"] = deploy_ready
    artifact["checks"]["p1_cleared_or_waived"] = deploy_ready
    artifact["checks"]["deploy_ready"] = deploy_ready
    return artifact


def _deploy_ready_candidate_pool() -> dict:
    artifact = _candidate_pool(deploy_ready=False)
    for row in artifact["candidate_rows"]:
        row["first_blocker"] = "computed_not_satisfied"
        row["blocker_owner"] = "market"
        row["owner_action_required"] = "no"
        row["candidate_status"] = "candidate_market_condition_wait"
        row["action_time_readiness"] = {
            "status": "not_applicable_current_stage",
            "action_time_path_ready": False,
            "public_facts_ready": True,
            "private_action_time_facts_ready": False,
        }
    for row in artifact["p0_p1_review"]:
        row["status"] = "cleared"
    artifact["summary"]["p0_cleared"] = True
    artifact["summary"]["p1_cleared_or_waived"] = True
    artifact["summary"]["deploy_ready"] = True
    artifact["checks"]["p0_cleared"] = True
    artifact["checks"]["p1_cleared_or_waived"] = True
    artifact["checks"]["deploy_ready"] = True
    return artifact


def _local_monitor_sequence() -> dict:
    return {
        "status": "temporarily_unavailable_monitor_refresh_needed",
        "steps": [
            {"name": "daily_live_enablement_table", "returncode": 0},
            {"name": "validate_daily_live_enablement_table", "returncode": 0},
            {"name": "single_lane_task_packet", "returncode": 0},
            {"name": "validate_single_lane_task_packet", "returncode": 0},
            {"name": "strategy_live_candidate_pool", "returncode": 0},
            {"name": "validate_strategy_live_candidate_pool", "returncode": 0},
        ],
    }


def _manifest() -> dict:
    return json.loads(
        (REPO_ROOT / "config" / "output_control_snapshots.json").read_text(
            encoding="utf-8"
        )
    )


def test_deploy_gate_blocks_when_candidate_pool_not_deploy_ready():
    module = _load_module()

    errors = module.validate_strategy_live_candidate_pool_deploy_gate(
        candidate_pool=_candidate_pool(deploy_ready=False),
        daily_table=_daily_table(),
        single_lane_task_packet=_single_lane(),
        local_monitor_sequence=_local_monitor_sequence(),
        manifest=_manifest(),
        changed_output_paths=[],
    )

    assert any("deploy_ready must be true" in error for error in errors)
    assert any("p0_cleared must be true" in error for error in errors)


def test_deploy_gate_accepts_valid_non_authority_artifacts_when_ready():
    module = _load_module()

    errors = module.validate_strategy_live_candidate_pool_deploy_gate(
        candidate_pool=_deploy_ready_candidate_pool(),
        daily_table=_daily_table(),
        single_lane_task_packet=_single_lane(),
        local_monitor_sequence=_local_monitor_sequence(),
        manifest=_manifest(),
        changed_output_paths=[],
    )

    assert errors == []


def test_deploy_gate_accepts_waiting_for_market_monitor_sequence():
    module = _load_module()
    monitor = _local_monitor_sequence()
    monitor["status"] = "waiting_for_market"

    errors = module.validate_strategy_live_candidate_pool_deploy_gate(
        candidate_pool=_deploy_ready_candidate_pool(),
        daily_table=_daily_table(),
        single_lane_task_packet=_single_lane(),
        local_monitor_sequence=monitor,
        manifest=_manifest(),
        changed_output_paths=[],
    )

    assert errors == []


def test_deploy_gate_recomputes_p0_p1_and_blocks_forged_summary():
    module = _load_module()

    errors = module.validate_strategy_live_candidate_pool_deploy_gate(
        candidate_pool=_candidate_pool(deploy_ready=True),
        daily_table=_daily_table(),
        single_lane_task_packet=_single_lane(),
        local_monitor_sequence=_local_monitor_sequence(),
        manifest=_manifest(),
        changed_output_paths=[],
    )

    assert any("does not match p0_p1_review" in error for error in errors)
    assert any("residual blocker" in error for error in errors)


def test_deploy_gate_blocks_owner_action_without_policy_waiver():
    module = _load_module()
    candidate_pool = _deploy_ready_candidate_pool()
    candidate_pool["candidate_rows"][0]["owner_action_required"] = "yes"

    errors = module.validate_strategy_live_candidate_pool_deploy_gate(
        candidate_pool=candidate_pool,
        daily_table=_daily_table(),
        single_lane_task_packet=_single_lane(),
        local_monitor_sequence=_local_monitor_sequence(),
        manifest=_manifest(),
        changed_output_paths=[],
    )

    assert any("owner_action_required=yes" in error for error in errors)


def test_deploy_gate_blocks_blocked_public_facts_without_waiver():
    module = _load_module()
    candidate_pool = _deploy_ready_candidate_pool()
    candidate_pool["candidate_rows"][0]["action_time_readiness"] = {
        "status": "blocked_public_facts",
        "public_facts_ready": False,
    }

    errors = module.validate_strategy_live_candidate_pool_deploy_gate(
        candidate_pool=candidate_pool,
        daily_table=_daily_table(),
        single_lane_task_packet=_single_lane(),
        local_monitor_sequence=_local_monitor_sequence(),
        manifest=_manifest(),
        changed_output_paths=[],
    )

    assert any("blocked_public_facts prevents deploy_ready" in error for error in errors)


def test_deploy_gate_cli_reports_blocked_for_current_not_ready_pool(tmp_path: Path):
    candidate_pool = tmp_path / "candidate_pool.json"
    daily_table = tmp_path / "daily_table.json"
    single_lane = tmp_path / "single_lane.json"
    monitor_sequence = tmp_path / "monitor_sequence.json"
    manifest = tmp_path / "manifest.json"
    candidate_pool.write_text(json.dumps(_candidate_pool(deploy_ready=False)), encoding="utf-8")
    daily_table.write_text(json.dumps(_daily_table()), encoding="utf-8")
    single_lane.write_text(json.dumps(_single_lane()), encoding="utf-8")
    monitor_sequence.write_text(json.dumps(_local_monitor_sequence()), encoding="utf-8")
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR_PATH),
            "--candidate-pool-json",
            str(candidate_pool),
            "--daily-table-json",
            str(daily_table),
            "--single-lane-task-packet-json",
            str(single_lane),
            "--local-monitor-sequence-json",
            str(monitor_sequence),
            "--manifest",
            str(manifest),
            "--skip-git-output-status",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "strategy_live_candidate_pool_deploy_gate_blocked" in result.stdout
