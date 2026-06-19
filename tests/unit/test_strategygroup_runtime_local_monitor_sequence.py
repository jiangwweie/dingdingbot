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
        elif script == "runtime_live_cutover_readiness.py":
            _write_output(
                command,
                {
                    "status": "live_cutover_waiting_for_fresh_signal",
                    "interaction": {
                        "level": "L0_local_cutover_readiness",
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
        elif script == "runtime_first_bounded_live_order_completion_audit.py":
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
        elif script == "run_strategygroup_signal_coverage_diagnostic.py":
            _write_output(
                command,
                {
                    "status": "mainline_and_broader_no_signal",
                    "interaction": {
                        "level": "L0_local_signal_coverage",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        elif script == "build_strategygroup_signal_coverage_expansion_review.py":
            _write_output(
                command,
                {
                    "status": "no_expansion_review_needed",
                    "interaction": {
                        "level": "L0_local_signal_coverage_expansion_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        elif script == "build_strategygroup_l2_readiness_review.py":
            _write_output(
                command,
                {
                    "status": "l2_readiness_review_no_rows",
                    "interaction": {
                        "level": "L0_local_l2_readiness_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        elif script == "run_strategygroup_l2_intake_dry_run.py":
            _write_output(
                command,
                {
                    "status": "l2_intake_dry_run_no_candidates",
                    "interaction": {
                        "level": "L0_local_l2_intake_dry_run",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        else:
            assert script == "run_strategygroup_l2_tier_policy_review.py"
            _write_output(
                command,
                {
                    "status": "l2_tier_policy_review_no_candidates",
                    "interaction": {
                        "level": "L0_local_l2_tier_policy_review",
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
        live_cutover_json=tmp_path / "cutover.json",
        live_cutover_md=tmp_path / "cutover.md",
        goal_progress_json=tmp_path / "goal.json",
        goal_progress_md=tmp_path / "goal.md",
        completion_audit_json=tmp_path / "completion.json",
        completion_audit_md=tmp_path / "completion.md",
        signal_coverage_json=tmp_path / "signal-coverage.json",
        signal_coverage_md=tmp_path / "signal-coverage.md",
        signal_coverage_expansion_review_json=tmp_path / "signal-expansion.json",
        signal_coverage_expansion_review_md=tmp_path / "signal-expansion.md",
        l2_readiness_review_json=tmp_path / "l2-review.json",
        l2_readiness_review_md=tmp_path / "l2-review.md",
        l2_intake_dry_run_json=tmp_path / "l2-dry-run.json",
        l2_intake_dry_run_md=tmp_path / "l2-dry-run.md",
        l2_tier_policy_review_json=tmp_path / "l2-tier-review.json",
        l2_tier_policy_review_md=tmp_path / "l2-tier-review.md",
        command_runner=fake_runner,
    )

    assert calls == [
        "run_strategygroup_runtime_daily_check.py",
        "runtime_live_cutover_readiness.py",
        "run_strategygroup_runtime_goal_progress_audit.py",
        "runtime_first_bounded_live_order_completion_audit.py",
        "run_strategygroup_signal_coverage_diagnostic.py",
        "build_strategygroup_signal_coverage_expansion_review.py",
        "build_strategygroup_l2_readiness_review.py",
        "run_strategygroup_l2_intake_dry_run.py",
        "run_strategygroup_l2_tier_policy_review.py",
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
        if script == "runtime_live_cutover_readiness.py":
            _write_output(
                command,
                {"status": "live_cutover_waiting_for_fresh_signal", "interaction": {}},
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_runtime_goal_progress_audit.py":
            _write_output(command, {"status": "waiting_for_market", "interaction": {}})
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "runtime_first_bounded_live_order_completion_audit.py":
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

        if script == "run_strategygroup_signal_coverage_diagnostic.py":
            _write_output(
                command,
                {
                    "status": "mainline_and_broader_no_signal",
                    "interaction": {"level": "L0_local_signal_coverage"},
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_signal_coverage_expansion_review.py":
            _write_output(
                command,
                {
                    "status": "no_expansion_review_needed",
                    "interaction": {
                        "level": "L0_local_signal_coverage_expansion_review"
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_l2_readiness_review.py":
            _write_output(
                command,
                {
                    "status": "l2_readiness_review_no_rows",
                    "interaction": {
                        "level": "L0_local_l2_readiness_review"
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_l2_intake_dry_run.py":
            _write_output(
                command,
                {
                    "status": "l2_intake_dry_run_no_candidates",
                    "interaction": {
                        "level": "L0_local_l2_intake_dry_run"
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        assert script == "run_strategygroup_l2_tier_policy_review.py"
        _write_output(
            command,
            {
                "status": "l2_tier_policy_review_no_candidates",
                "interaction": {
                    "level": "L0_local_l2_tier_policy_review"
                },
            },
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    report = module.build_local_monitor_sequence_report(
        daily_check_json=tmp_path / "daily.json",
        daily_owner_progress=tmp_path / "daily.md",
        live_cutover_json=tmp_path / "cutover.json",
        live_cutover_md=tmp_path / "cutover.md",
        goal_progress_json=tmp_path / "goal.json",
        goal_progress_md=tmp_path / "goal.md",
        completion_audit_json=tmp_path / "completion.json",
        completion_audit_md=tmp_path / "completion.md",
        signal_coverage_json=tmp_path / "signal-coverage.json",
        signal_coverage_md=tmp_path / "signal-coverage.md",
        signal_coverage_expansion_review_json=tmp_path / "signal-expansion.json",
        signal_coverage_expansion_review_md=tmp_path / "signal-expansion.md",
        l2_readiness_review_json=tmp_path / "l2-review.json",
        l2_readiness_review_md=tmp_path / "l2-review.md",
        l2_intake_dry_run_json=tmp_path / "l2-dry-run.json",
        l2_intake_dry_run_md=tmp_path / "l2-dry-run.md",
        l2_tier_policy_review_json=tmp_path / "l2-tier-review.json",
        l2_tier_policy_review_md=tmp_path / "l2-tier-review.md",
        command_runner=fake_runner,
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["checks"]["blockers"] == ["completion_audit:non_market_gaps"]
    assert report["checks"]["non_market_gaps"][0]["missing_or_false"] == [
        "goal_progress:generated_before_daily_check"
    ]


def test_local_monitor_sequence_treats_stale_cache_as_refresh_not_blocker(
    tmp_path: Path,
) -> None:
    module = _load_module()

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        script = Path(command[1]).name
        if script == "run_strategygroup_runtime_daily_check.py":
            _write_output(
                command,
                {
                    "status": "needs_refresh",
                    "checks": {
                        "blockers": [],
                        "monitor_refresh_needed": True,
                        "monitor_refresh_reasons": ["runtime_progress_cache_stale"],
                    },
                    "interaction": {
                        "level": "L0_local_cache_gate",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 2, "", "")
        if script == "runtime_live_cutover_readiness.py":
            _write_output(
                command,
                {"status": "live_cutover_waiting_for_fresh_signal", "interaction": {}},
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_runtime_goal_progress_audit.py":
            _write_output(
                command,
                {
                    "status": "needs_refresh",
                    "checks": {
                        "blockers": [],
                        "product_gaps": [],
                        "monitor_refresh_needed": True,
                    },
                    "interaction": {
                        "level": "L0_local_goal_progress_audit",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 2, "", "")

        if script == "runtime_first_bounded_live_order_completion_audit.py":
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

        if script == "run_strategygroup_signal_coverage_diagnostic.py":
            _write_output(
                command,
                {
                    "status": "mainline_and_broader_no_signal",
                    "interaction": {
                        "level": "L0_local_signal_coverage",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_signal_coverage_expansion_review.py":
            _write_output(
                command,
                {
                    "status": "no_expansion_review_needed",
                    "interaction": {
                        "level": "L0_local_signal_coverage_expansion_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_l2_readiness_review.py":
            _write_output(
                command,
                {
                    "status": "l2_readiness_review_no_rows",
                    "interaction": {
                        "level": "L0_local_l2_readiness_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_l2_intake_dry_run.py":
            _write_output(
                command,
                {
                    "status": "l2_intake_dry_run_no_candidates",
                    "interaction": {
                        "level": "L0_local_l2_intake_dry_run",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        assert script == "run_strategygroup_l2_tier_policy_review.py"
        _write_output(
            command,
            {
                "status": "l2_tier_policy_review_no_candidates",
                "interaction": {
                    "level": "L0_local_l2_tier_policy_review",
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
        live_cutover_json=tmp_path / "cutover.json",
        live_cutover_md=tmp_path / "cutover.md",
        goal_progress_json=tmp_path / "goal.json",
        goal_progress_md=tmp_path / "goal.md",
        completion_audit_json=tmp_path / "completion.json",
        completion_audit_md=tmp_path / "completion.md",
        signal_coverage_json=tmp_path / "signal-coverage.json",
        signal_coverage_md=tmp_path / "signal-coverage.md",
        signal_coverage_expansion_review_json=tmp_path / "signal-expansion.json",
        signal_coverage_expansion_review_md=tmp_path / "signal-expansion.md",
        l2_readiness_review_json=tmp_path / "l2-review.json",
        l2_readiness_review_md=tmp_path / "l2-review.md",
        l2_intake_dry_run_json=tmp_path / "l2-dry-run.json",
        l2_intake_dry_run_md=tmp_path / "l2-dry-run.md",
        l2_tier_policy_review_json=tmp_path / "l2-tier-review.json",
        l2_tier_policy_review_md=tmp_path / "l2-tier-review.md",
        command_runner=fake_runner,
    )

    assert report["status"] == "needs_refresh"
    assert report["owner_summary"]["state"] == "监控状态需刷新"
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert report["checks"]["blockers"] == []
    assert report["checks"]["monitor_refresh_needed"] is True
    assert report["interaction"]["remote_interaction_count"] == 0
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["interaction"]["approaches_real_order"] is False


def test_local_monitor_sequence_surfaces_signal_coverage_gap(
    tmp_path: Path,
) -> None:
    module = _load_module()

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        script = Path(command[1]).name
        if script == "run_strategygroup_runtime_daily_check.py":
            _write_output(command, {"status": "waiting_for_market", "interaction": {}})
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "runtime_live_cutover_readiness.py":
            _write_output(
                command,
                {"status": "live_cutover_waiting_for_fresh_signal", "interaction": {}},
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_runtime_goal_progress_audit.py":
            _write_output(command, {"status": "waiting_for_market", "interaction": {}})
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "runtime_first_bounded_live_order_completion_audit.py":
            _write_output(
                command,
                {
                    "status": "not_complete_waiting_for_market",
                    "non_market_gaps": [],
                    "interaction": {},
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_signal_coverage_diagnostic.py":
            _write_output(
                command,
                {
                    "status": "mainline_no_signal_broader_would_enter",
                    "interaction": {
                        "level": "L0_local_signal_coverage",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_signal_coverage_expansion_review.py":
            _write_output(
                command,
                {
                    "status": "review_needed_broader_observe_only_would_enter",
                    "counts": {"review_row_count": 4},
                    "interaction": {
                        "level": "L0_local_signal_coverage_expansion_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_l2_readiness_review.py":
            _write_output(
                command,
                {
                    "status": "l2_readiness_review_has_conditional_candidate",
                    "decision": {
                        "default_next_step": "run_conditional_l2_dry_run_without_tier_change",
                        "handoff_intake_recommended_groups": ["BTPC-001"],
                    },
                    "interaction": {
                        "level": "L0_local_l2_readiness_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_l2_intake_dry_run.py":
            _write_output(
                command,
                {
                    "status": "l2_intake_dry_run_passed",
                    "decision": {
                        "groups_ready_for_l2_policy_review": ["BTPC-001"],
                    },
                    "interaction": {
                        "level": "L0_local_l2_intake_dry_run",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        assert script == "run_strategygroup_l2_tier_policy_review.py"
        _write_output(
            command,
            {
                "status": "l2_tier_policy_review_recommended",
                "decision": {
                    "groups_ready_to_apply_l2": ["BTPC-001"],
                },
                "interaction": {
                    "level": "L0_local_l2_tier_policy_review",
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
        live_cutover_json=tmp_path / "cutover.json",
        live_cutover_md=tmp_path / "cutover.md",
        goal_progress_json=tmp_path / "goal.json",
        goal_progress_md=tmp_path / "goal.md",
        completion_audit_json=tmp_path / "completion.json",
        completion_audit_md=tmp_path / "completion.md",
        signal_coverage_json=tmp_path / "signal-coverage.json",
        signal_coverage_md=tmp_path / "signal-coverage.md",
        signal_coverage_expansion_review_json=tmp_path / "signal-expansion.json",
        signal_coverage_expansion_review_md=tmp_path / "signal-expansion.md",
        l2_readiness_review_json=tmp_path / "l2-review.json",
        l2_readiness_review_md=tmp_path / "l2-review.md",
        l2_intake_dry_run_json=tmp_path / "l2-dry-run.json",
        l2_intake_dry_run_md=tmp_path / "l2-dry-run.md",
        l2_tier_policy_review_json=tmp_path / "l2-tier-review.json",
        l2_tier_policy_review_md=tmp_path / "l2-tier-review.md",
        command_runner=fake_runner,
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["checks"]["blockers"] == []
    assert report["checks"]["non_market_gaps"] == [
        {
            "source": "l2_tier_policy_review",
            "requirement": "conditional L2 tier policy review recommends a local policy update before the broader opportunity is considered covered",
            "missing_or_false": [
                "conditional_l2_tier_policy_update_needed",
                "groups:BTPC-001",
            ],
        }
    ]
    assert report["interaction"]["remote_interaction_count"] == 0
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["interaction"]["approaches_real_order"] is False


def test_local_monitor_sequence_clears_signal_gap_when_l2_already_enabled(
    tmp_path: Path,
) -> None:
    module = _load_module()

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        script = Path(command[1]).name
        if script == "run_strategygroup_runtime_daily_check.py":
            _write_output(command, {"status": "waiting_for_market", "interaction": {}})
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "runtime_live_cutover_readiness.py":
            _write_output(
                command,
                {"status": "live_cutover_waiting_for_fresh_signal", "interaction": {}},
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_runtime_goal_progress_audit.py":
            _write_output(command, {"status": "waiting_for_market", "interaction": {}})
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "runtime_first_bounded_live_order_completion_audit.py":
            _write_output(
                command,
                {
                    "status": "not_complete_waiting_for_market",
                    "non_market_gaps": [],
                    "interaction": {},
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_signal_coverage_diagnostic.py":
            _write_output(
                command,
                {
                    "status": "mainline_no_signal_broader_would_enter",
                    "interaction": {
                        "level": "L0_local_signal_coverage",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_signal_coverage_expansion_review.py":
            _write_output(
                command,
                {
                    "status": "review_needed_broader_observe_only_would_enter",
                    "interaction": {
                        "level": "L0_local_signal_coverage_expansion_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_l2_readiness_review.py":
            _write_output(
                command,
                {
                    "status": "l2_readiness_review_already_enabled",
                    "decision": {"enabled_l2_groups": ["BTPC-001"]},
                    "interaction": {
                        "level": "L0_local_l2_readiness_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_l2_intake_dry_run.py":
            _write_output(
                command,
                {
                    "status": "l2_intake_dry_run_no_candidates",
                    "interaction": {
                        "level": "L0_local_l2_intake_dry_run",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        assert script == "run_strategygroup_l2_tier_policy_review.py"
        _write_output(
            command,
            {
                "status": "l2_tier_policy_review_no_candidates",
                "interaction": {
                    "level": "L0_local_l2_tier_policy_review",
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
        live_cutover_json=tmp_path / "cutover.json",
        live_cutover_md=tmp_path / "cutover.md",
        goal_progress_json=tmp_path / "goal.json",
        goal_progress_md=tmp_path / "goal.md",
        completion_audit_json=tmp_path / "completion.json",
        completion_audit_md=tmp_path / "completion.md",
        signal_coverage_json=tmp_path / "signal-coverage.json",
        signal_coverage_md=tmp_path / "signal-coverage.md",
        signal_coverage_expansion_review_json=tmp_path / "signal-expansion.json",
        signal_coverage_expansion_review_md=tmp_path / "signal-expansion.md",
        l2_readiness_review_json=tmp_path / "l2-review.json",
        l2_readiness_review_md=tmp_path / "l2-review.md",
        l2_intake_dry_run_json=tmp_path / "l2-dry-run.json",
        l2_intake_dry_run_md=tmp_path / "l2-dry-run.md",
        l2_tier_policy_review_json=tmp_path / "l2-tier-review.json",
        l2_tier_policy_review_md=tmp_path / "l2-tier-review.md",
        command_runner=fake_runner,
    )

    assert report["status"] == "waiting_for_market"
    assert report["checks"]["blockers"] == []
    assert report["checks"]["non_market_gaps"] == []
    assert report["interaction"]["remote_interaction_count"] == 0
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["interaction"]["approaches_real_order"] is False
