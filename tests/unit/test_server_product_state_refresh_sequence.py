from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_server_product_state_refresh_sequence.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_server_product_state_refresh_sequence",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_server_product_state_refresh_sequence_records_optional_failure(tmp_path: Path):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(
            item.endswith("refresh_strategygroup_runtime_product_state_artifacts.py")
            for item in command
        ):
            return module.CommandResult(
                returncode=1,
                stdout="",
                stderr="optional refresh failed",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        report_dir=tmp_path / "reports",
        runtime_monitor_dir=tmp_path / "runtime-monitor",
        env_file=tmp_path / "live-readonly.env",
        output_json=tmp_path / "sequence.json",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_ready"
    assert report["summary"]["failed_optional_step_count"] == 1
    assert report["summary"]["failed_required_step_count"] == 0
    assert report["summary"]["final_goal_status_attempted"] is True
    assert calls[-1][1] == "scripts/build_strategygroup_runtime_goal_status.py"
    assert (tmp_path / "sequence.json").exists()


def test_server_product_state_refresh_sequence_fails_on_required_step_but_continues(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(item.endswith("validate_strategy_live_candidate_pool.py") for item in command):
            return module.CommandResult(
                returncode=1,
                stdout="",
                stderr="candidate pool invalid",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        report_dir=tmp_path / "reports",
        runtime_monitor_dir=tmp_path / "runtime-monitor",
        env_file=tmp_path / "live-readonly.env",
        output_json=tmp_path / "sequence.json",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["skipped_after_required_failure_count"] > 0
    assert report["summary"]["final_goal_status_attempted"] is False
    assert report["summary"]["final_goal_status_suppressed"] is True
    assert report["summary"]["blocked_by_required_step"] == "validate_candidate_pool"
    assert calls[-1][1] == "scripts/validate_strategy_live_candidate_pool.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "build_goal_status" in skipped_names
