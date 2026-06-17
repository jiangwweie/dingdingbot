from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_strategygroup_runtime_goal_progress_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_strategygroup_runtime_goal_progress_audit",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _baseline(**overrides):
    base = {
        "default_check": "python3 scripts/run_strategygroup_runtime_daily_check.py --auto-cache --json",
        "heartbeat_check": "python3 scripts/run_strategygroup_runtime_daily_check.py --auto-cache --heartbeat",
        "routine_status_check": "python3 scripts/run_strategygroup_runtime_daily_check.py --auto-cache --owner-progress",
        "strict_no_server_check": "python3 scripts/run_strategygroup_runtime_daily_check.py --from-cache --require-fresh-cache --owner-progress",
        "deploy_session_owner_progress_check": "python3 scripts/run_tokyo_runtime_deploy_session.py --run-daily-check --daily-check-mode cache --owner-progress",
    }
    base.update(overrides)
    return base


def _daily_check(**overrides):
    base = {
        "status": "waiting_for_market",
        "current_read_interaction": {
            "level": "L0_local_cache_read",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "owner_summary": {
            "state": "等待机会",
            "current_action": "继续等待市场机会",
            "owner_intervention_required": False,
            "visibility": {
                "category": "waiting_for_market",
                "label": "等待机会",
            },
            "progress": {
                "dry_run_audit": "审计演练正常",
            },
        },
        "checks": {
            "blockers": [],
            "warnings": [],
            "product_gaps": [],
            "waiting_for_market": True,
            "runtime_ready": True,
            "watcher_ready": True,
            "source_readiness_ready": True,
            "runtime_dry_run_audit_passed": True,
            "runtime_dry_run_required_checks_present": True,
            "runtime_dry_run_missing_required_checks": [],
            "runtime_dry_run_scenario_count": 14,
            "runtime_execution_chain_ready_segment_count": 3,
            "runtime_execution_chain_missing_or_failed_segments": [],
            "runtime_execution_goal_chain_ready_segment_count": 7,
            "runtime_execution_goal_chain_missing_or_failed_segments": [],
        },
        "notification": {
            "decision": "DONT_NOTIFY",
            "reason": "healthy_waiting_for_market",
        },
        "safety_invariants": {
            "remote_files_modified": False,
            "env_files_read": False,
            "secrets_read": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }
    base.update(overrides)
    return base


def test_goal_progress_waiting_for_market_with_p05_ready():
    module = _load_module()

    report = module.build_goal_progress_report(
        daily_check=_daily_check(),
        baseline=_baseline(),
    )

    assert report["status"] == "waiting_for_market"
    assert report["interaction"]["level"] == "L0_local_goal_progress_audit"
    assert report["interaction"]["remote_interaction_count"] == 0
    assert report["owner_summary"]["state"] == "等待机会"
    assert report["owner_summary"]["current_action"] == "继续等待市场机会"
    assert report["owner_summary"]["p0"] == "waiting_for_market"
    assert report["owner_summary"]["p05"] == "ready"
    assert report["checks"]["p05_ready"] is True
    assert report["checks"]["blockers"] == []
    assert report["completion_boundary"] == {
        "completion_blocker_class": "waiting_for_market",
        "disabled_smoke_treated_as_real_execution_proof": False,
        "dry_run_readiness_proven": True,
        "first_bounded_real_order_complete": False,
        "goal_complete": False,
        "mock_signal_treated_as_real_signal": False,
        "real_order_closure_proven": False,
        "reason": "waiting_for_real_fresh_selected_strategygroup_signal",
        "status": "not_complete_waiting_for_market",
        "waiting_for_real_fresh_signal": True,
    }
    assert report["exit_hardening_boundary"] == {
        "active_position_remains_open_policy_covered": True,
        "entry_filled_protection_failed_reduce_only_recovery_covered": True,
        "entry_filled_protection_ok_covered": True,
        "exchange_native_hard_stop_required_after_entry": True,
        "exchange_submit_failed_before_acceptance_policy_covered": True,
        "partial_fill_policy_covered": True,
        "position_closed_by_sl_tp_or_reduce_only_recovery_covered": True,
        "post_submit_exit_outcome_matrix_checked": True,
        "real_order_dependent_remaining": True,
        "real_post_submit_close_reconcile_settle_proven": False,
        "status": "ready",
    }
    tracks = {track["id"]: track for track in report["tracks"]}
    assert tracks["p0_live_closure"]["status"] == "waiting_for_market"
    assert tracks["p05_runtime_interaction_optimization"]["status"] == "ready"
    assert tracks["p05_engineering_rehearsal_loop"]["status"] == "ready"
    assert "chain_ready_segments=3" in tracks["p05_engineering_rehearsal_loop"][
        "evidence"
    ]
    assert "missing_chain_segments=0" in tracks["p05_engineering_rehearsal_loop"][
        "evidence"
    ]
    assert "goal_chain_ready_segments=7" in tracks[
        "p05_engineering_rehearsal_loop"
    ]["evidence"]
    assert "missing_goal_chain_segments=0" in tracks[
        "p05_engineering_rehearsal_loop"
    ]["evidence"]
    assert tracks["p05_owner_visibility_loop"]["status"] == "ready"
    assert tracks["p05_safety_invariants"]["status"] == "ready"


def test_goal_progress_owner_progress_text_has_track_table():
    module = _load_module()
    report = module.build_goal_progress_report(
        daily_check=_daily_check(),
        baseline=_baseline(),
    )

    text = module._owner_progress_text(report)

    assert "## StrategyGroup Runtime Goal Progress" in text
    assert "- 当前阶段: 等待机会" in text
    assert "- 交互等级: L0_local_goal_progress_audit" in text
    assert "- 远端交互次数: 0" in text
    assert "## Completion Boundary" in text
    assert "- Goal complete: 否" in text
    assert "- Status: not_complete_waiting_for_market" in text
    assert "- Completion blocker class: waiting_for_market" in text
    assert "- First bounded real order complete: 否" in text
    assert "- Real order closure proven: 否" in text
    assert "- Waiting for real fresh signal: 是" in text
    assert "- Dry-run readiness proven: 是" in text
    assert "## Exit Hardening Boundary" in text
    assert "- Post-submit exit outcome matrix checked: 是" in text
    assert "- Exchange-native hard stop required after entry: 是" in text
    assert "- Protection failure reduce-only recovery covered: 是" in text
    assert "- Real post-submit close/reconcile/settle proven: 否" in text
    assert "- Real order dependent remaining: 是" in text
    assert "| P0.5 Runtime Interaction Optimization | ready | 已就绪 |" in text
    assert "## Evidence" in text
    assert "chain_ready_segments=3" in text
    assert "missing_chain_segments=0" in text
    assert "goal_chain_ready_segments=7" in text
    assert "missing_goal_chain_segments=0" in text
    assert "- P0.5 ready: 是" in text


def test_goal_progress_marks_non_market_gap_as_degraded():
    module = _load_module()
    report = module.build_goal_progress_report(
        daily_check=_daily_check(
            checks={
                **_daily_check()["checks"],
                "runtime_dry_run_audit_passed": False,
            }
        ),
        baseline=_baseline(),
    )

    assert report["status"] == "degraded"
    assert report["owner_summary"]["p05"] == "needs_work"
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert report["completion_boundary"]["goal_complete"] is False
    assert report["completion_boundary"]["status"] == "not_complete_product_gap"
    assert report["completion_boundary"]["completion_blocker_class"] == "missing_fact"
    assert report["completion_boundary"]["waiting_for_real_fresh_signal"] is False
    assert report["completion_boundary"]["dry_run_readiness_proven"] is False
    assert "runtime_dry_run_audit_not_passed" in report["checks"]["product_gaps"]
    tracks = {track["id"]: track for track in report["tracks"]}
    assert tracks["p05_engineering_rehearsal_loop"]["status"] == "blocked"


def test_goal_progress_marks_exit_hardening_boundary_needs_work_when_matrix_missing():
    module = _load_module()
    checks = dict(_daily_check()["checks"])
    checks["runtime_dry_run_required_checks_present"] = False
    checks["runtime_dry_run_missing_required_checks"] = [
        "post_submit_exit_outcome_matrix_checked"
    ]
    report = module.build_goal_progress_report(
        daily_check=_daily_check(checks=checks),
        baseline=_baseline(),
    )

    assert report["status"] == "degraded"
    assert report["exit_hardening_boundary"]["status"] == "needs_work"
    assert (
        report["exit_hardening_boundary"][
            "post_submit_exit_outcome_matrix_checked"
        ]
        is False
    )
    assert (
        report["exit_hardening_boundary"][
            "entry_filled_protection_failed_reduce_only_recovery_covered"
        ]
        is False
    )
    assert "missing_dry_run_check:post_submit_exit_outcome_matrix_checked" in report[
        "checks"
    ]["product_gaps"]


def test_goal_progress_marks_missing_chain_segment_as_degraded():
    module = _load_module()
    checks = dict(_daily_check()["checks"])
    checks["runtime_execution_chain_ready_segment_count"] = 1
    checks["runtime_execution_chain_missing_or_failed_segments"] = [
        "operation_layer_evidence_relay_checked"
    ]
    report = module.build_goal_progress_report(
        daily_check=_daily_check(checks=checks),
        baseline=_baseline(),
    )

    assert report["status"] == "degraded"
    assert "missing_chain_segment:operation_layer_evidence_relay_checked" in report[
        "checks"
    ]["product_gaps"]
    tracks = {track["id"]: track for track in report["tracks"]}
    rehearsal = tracks["p05_engineering_rehearsal_loop"]
    assert rehearsal["status"] == "blocked"
    assert "chain_ready_segments=1" in rehearsal["evidence"]
    assert "missing_chain_segments=1" in rehearsal["evidence"]


def test_goal_progress_marks_missing_goal_chain_segment_as_degraded():
    module = _load_module()
    checks = dict(_daily_check()["checks"])
    checks["runtime_execution_goal_chain_ready_segment_count"] = 5
    checks["runtime_execution_goal_chain_missing_or_failed_segments"] = [
        "official_operation_layer_evidence_handoff"
    ]
    report = module.build_goal_progress_report(
        daily_check=_daily_check(checks=checks),
        baseline=_baseline(),
    )

    assert report["status"] == "degraded"
    assert (
        "missing_goal_chain_segment:official_operation_layer_evidence_handoff"
        in report["checks"]["product_gaps"]
    )
    tracks = {track["id"]: track for track in report["tracks"]}
    rehearsal = tracks["p05_engineering_rehearsal_loop"]
    assert rehearsal["status"] == "blocked"
    assert "goal_chain_ready_segments=5" in rehearsal["evidence"]
    assert "missing_goal_chain_segments=1" in rehearsal["evidence"]


def test_goal_progress_keeps_chain_segment_count_unknown_when_daily_check_lacks_it():
    module = _load_module()
    checks = dict(_daily_check()["checks"])
    checks.pop("runtime_execution_chain_ready_segment_count")
    checks.pop("runtime_execution_chain_missing_or_failed_segments")
    checks.pop("runtime_execution_goal_chain_ready_segment_count")
    checks.pop("runtime_execution_goal_chain_missing_or_failed_segments")
    report = module.build_goal_progress_report(
        daily_check=_daily_check(checks=checks),
        baseline=_baseline(),
    )

    tracks = {track["id"]: track for track in report["tracks"]}
    rehearsal = tracks["p05_engineering_rehearsal_loop"]
    assert rehearsal["status"] == "ready"
    assert "chain_ready_segments=unknown" in rehearsal["evidence"]
    assert "missing_chain_segments=0" in rehearsal["evidence"]
    assert "goal_chain_ready_segments=unknown" in rehearsal["evidence"]
    assert "missing_goal_chain_segments=0" in rehearsal["evidence"]


def test_goal_progress_rejects_remote_interaction_in_local_audit():
    module = _load_module()
    report = module.build_goal_progress_report(
        daily_check=_daily_check(
            current_read_interaction={
                "level": "L1_daily_check_from_snapshot",
                "remote_interaction_count": 1,
                "mutates_remote_files": False,
                "approaches_real_order": False,
            }
        ),
        baseline=_baseline(),
    )

    assert report["status"] == "degraded"
    assert "local_goal_progress_expected_zero_remote_interaction" in report["checks"][
        "product_gaps"
    ]


def test_goal_progress_cli_writes_json_and_owner_progress(tmp_path):
    module = _load_module()
    daily_check_path = tmp_path / "daily-check.json"
    baseline_path = tmp_path / "baseline.json"
    output_json = tmp_path / "goal-progress.json"
    output_md = tmp_path / "goal-progress.md"
    daily_check_path.write_text(
        json.dumps(_daily_check(), ensure_ascii=False),
        encoding="utf-8",
    )
    baseline_path.write_text(
        json.dumps(_baseline(), ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--daily-check-json",
            str(daily_check_path),
            "--baseline-json",
            str(baseline_path),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
            "--owner-progress",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["status"] == "waiting_for_market"
    assert payload["interaction"]["remote_interaction_count"] == 0
    assert payload["completion_boundary"]["goal_complete"] is False
    assert (
        payload["completion_boundary"]["status"]
        == "not_complete_waiting_for_market"
    )
    assert payload["completion_boundary"]["dry_run_readiness_proven"] is True
    assert payload["exit_hardening_boundary"]["status"] == "ready"
    assert (
        payload["exit_hardening_boundary"][
            "real_post_submit_close_reconcile_settle_proven"
        ]
        is False
    )
    progress = output_md.read_text(encoding="utf-8")
    assert "## StrategyGroup Runtime Goal Progress" in progress
    assert "## Completion Boundary" in progress
    assert "## Exit Hardening Boundary" in progress
    assert "- P0.5 ready: 是" in progress
    assert list(tmp_path.glob(".goal-progress.json.*.tmp")) == []
    assert list(tmp_path.glob(".goal-progress.md.*.tmp")) == []
