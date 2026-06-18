from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_strategygroup_runtime_local_monitor_sequence.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_strategygroup_runtime_local_monitor_sequence",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_output(command: list[str], payload: dict) -> None:
    output_path = Path(command[command.index("--output-json") + 1])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload), encoding="utf-8")


def test_local_monitor_sequence_runs_cache_checks_in_order(tmp_path: Path) -> None:
    module = _load_module()
    calls: list[str] = []

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        script = Path(command[1]).name
        calls.append(script)
        if script == "run_strategygroup_runtime_daily_check.py":
            _write_output(
                command,
                {
                    "status": "waiting_for_market",
                    "interaction": {
                        "level": "L0_local_cache_read",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        elif script == "run_strategygroup_runtime_goal_progress_audit.py":
            _write_output(
                command,
                {
                    "status": "waiting_for_market",
                    "interaction": {
                        "level": "L0_local_goal_progress_audit",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        else:
            _write_output(
                command,
                {
                    "status": "not_complete_waiting_for_market",
                    "non_market_gaps": [],
                    "interaction": {
                        "level": "L0_local_completion_audit",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    report = module.build_local_monitor_sequence_report(
        daily_check_json=tmp_path / "daily.json",
        daily_owner_progress=tmp_path / "daily.md",
        goal_progress_json=tmp_path / "goal.json",
        goal_progress_md=tmp_path / "goal.md",
        completion_audit_json=tmp_path / "completion.json",
        completion_audit_md=tmp_path / "completion.md",
        command_runner=fake_runner,
    )

    assert calls == [
        "run_strategygroup_runtime_daily_check.py",
        "run_strategygroup_runtime_goal_progress_audit.py",
        "runtime_first_bounded_live_order_completion_audit.py",
    ]
    assert report["status"] == "waiting_for_market"
    assert report["checks"]["blockers"] == []
    assert report["interaction"]["level"] == "L0_local_monitor_sequence"
    assert report["interaction"]["remote_interaction_count"] == 0
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["interaction"]["approaches_real_order"] is False


def test_local_monitor_sequence_surfaces_completion_non_market_gap(
    tmp_path: Path,
) -> None:
    module = _load_module()

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        script = Path(command[1]).name
        if script == "run_strategygroup_runtime_daily_check.py":
            _write_output(command, {"status": "waiting_for_market", "interaction": {}})
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_runtime_goal_progress_audit.py":
            _write_output(command, {"status": "waiting_for_market", "interaction": {}})
            return subprocess.CompletedProcess(command, 0, "", "")

        _write_output(
            command,
            {
                "status": "needs_non_market_repair",
                "non_market_gaps": [
                    {
                        "requirement": "P0 completion audit input sources are traceable",
                        "missing_or_false": ["goal_progress:generated_before_daily_check"],
                    }
                ],
                "interaction": {
                    "level": "L0_local_completion_audit",
                    "remote_interaction_count": 0,
                },
            },
        )
        return subprocess.CompletedProcess(command, 2, "", "")

    report = module.build_local_monitor_sequence_report(
        daily_check_json=tmp_path / "daily.json",
        daily_owner_progress=tmp_path / "daily.md",
        goal_progress_json=tmp_path / "goal.json",
        goal_progress_md=tmp_path / "goal.md",
        completion_audit_json=tmp_path / "completion.json",
        completion_audit_md=tmp_path / "completion.md",
        command_runner=fake_runner,
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["checks"]["blockers"] == ["completion_audit:non_market_gaps"]
    assert report["checks"]["non_market_gaps"][0]["missing_or_false"] == [
        "goal_progress:generated_before_daily_check"
    ]
