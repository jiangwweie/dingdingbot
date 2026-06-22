from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from scripts import runtime_live_cutover_readiness as live_cutover_script


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


def _tier_policy(**overrides):
    base = {
        "schema": "brc.strategy_group_runtime_tier_policy.v1",
        "not_execution_authority": True,
        "not_finalgate_input": True,
        "not_operation_layer_input": True,
        "not_order_sizing_default": True,
        "current_strategy_groups": {
            "MPG-001": {"tier": "L4", "mode": "tiny_real_order_eligible"},
            "TEQ-001": {"tier": "L2", "mode": "shadow_candidate"},
            "FBS-001": {"tier": "L3", "mode": "armed_observation"},
            "SOR-001": {"tier": "L3", "mode": "conditional_armed_observation"},
            "PMR-001": {"tier": "L1", "mode": "observe_only"},
            "BTPC-001": {"tier": "L2", "mode": "shadow_candidate"},
        },
        "new_strategy_group_defaults": {
            "default_tier": "L1",
            "default_mode": "observe_only",
            "known_new_groups": {
                "BRF": "L1",
                "VCB": "L1",
                "LSR": "L1",
                "RBR": "L1",
            },
        },
        "safety_invariants": {
            "no_strategy_group_directly_defines_candidate_pipeline": True,
            "no_strategy_group_directly_defines_finalgate": True,
            "no_strategy_group_directly_defines_operation_layer": True,
            "no_strategy_group_directly_authorizes_real_submit": True,
            "l4_still_requires_official_runtime_chain": True,
        },
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
            "fresh_signal_notification_policy_checked": True,
            "allocated_subaccount_profile_boundary_checked": True,
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


def _live_cutover_readiness(**overrides):
    live_closure_required_evidence_keys = [
        "live_watcher_signal_packet_id",
        "required_facts_readiness_packet_id",
        "candidate_id",
        "runtime_grant_id",
        "fresh_submit_authorization_id",
        "action_time_finalgate_packet_id",
        "operation_layer_submit_authorization_id",
        "exchange_submit_execution_result_id",
        "exchange_native_hard_stop_order_id",
        "runtime_post_submit_finalize_packet_id",
        "post_submit_reconciliation_evidence_id",
        "post_submit_budget_settlement_id",
        "submit_outcome_review_id",
    ]
    base = {
        "scope": "runtime_live_cutover_readiness",
        "status": "live_cutover_waiting_for_fresh_signal",
        "owner_state": "等待机会",
        "next_fresh_signal_cutover_ready": True,
        "current_real_submit_allowed": False,
        "market_dependent_waiting_keys": [
            "fresh_signal",
            "candidate_authorization",
            "action_time_finalgate",
            "official_operation_layer",
            "real_exchange_acceptance",
            "post_submit_real_reconciliation",
        ],
        "non_market_blockers": [],
        "live_closure_cutover_contract": {
            "scope": "first_bounded_live_order_closure_cutover_contract",
            "status": "ready",
            "stage_count": 9,
            "required_evidence_keys": live_closure_required_evidence_keys,
            "checks": {
                "live_closure_contract_defined": True,
                "live_closure_contract_rejects_synthetic_signal": True,
                "live_closure_contract_rejects_disabled_smoke": True,
                "live_closure_contract_requires_live_signal_chain_binding": True,
                "live_closure_contract_requires_pre_submit_authorization_chain_binding": True,
                "live_closure_contract_requires_runtime_boundary_binding": True,
                "live_closure_contract_requires_exchange_acceptance": True,
                "live_closure_contract_requires_live_submit_truth": True,
                "live_closure_contract_requires_exchange_native_protection": True,
                "live_closure_contract_requires_exchange_native_protection_binding": True,
                "live_closure_contract_requires_post_submit_reconciliation": True,
                "live_closure_contract_requires_post_submit_result_binding": True,
                "live_closure_contract_has_no_owner_chat_confirmation_stage": True,
            },
        },
    }
    base.update(overrides)
    return base


def _live_closure_evidence_verification(**overrides):
    base = {
        "scope": "runtime_live_closure_evidence_verification",
        "status": "live_closure_complete",
        "owner_state": "完成",
        "completed_stage_count": 9,
        "stage_count": 9,
        "first_incomplete_stage": None,
        "missing_evidence_keys": [],
        "reject_reasons": [],
        "completion": {
            "first_bounded_real_order_complete": True,
            "real_order_closure_proven": True,
            "mock_signal_treated_as_real_signal": False,
            "disabled_smoke_treated_as_real_execution_proof": False,
        },
    }
    base.update(overrides)
    return base


def _runtime_boundary_proof() -> dict[str, object]:
    values = {
        "strategy_group_id": ["MPG-001"],
        "runtime_profile_id": ["owner-runtime-console-v1"],
        "subaccount_id": ["tokyo-runtime-subaccount"],
        "symbol": ["MSTR/USDT:USDT"],
        "side": ["long"],
        "notional": ["100"],
        "leverage": ["1"],
    }
    return {
        "source_packet_count": 4,
        "observed_fields": list(values),
        "missing_fields": [],
        "conflict_fields": [],
        "values": values,
    }


def _strategy_review_evidence_closure_wave(**overrides):
    base = {
        "status": "review_only_evidence_closure_wave_ready",
        "phase_status": {
            "phase_1_owner_perception_projection": "ready",
            "phase_2_evidence_closure_queue": "ready",
            "phase_3_next_owner_decision_package": "ready_for_owner_policy_decision",
        },
        "evidence_closure_packets": [
            {"strategy_group_id": "BRF-001"},
            {"strategy_group_id": "BTPC-001"},
            {"strategy_group_id": "LSR-001"},
            {"strategy_group_id": "MI-001"},
            {"strategy_group_id": "CPM-RO-001"},
            {"strategy_group_id": "MPG-001"},
        ],
        "next_owner_decision_package": {
            "status": "next_owner_decision_package_ready",
            "owner_policy_confirmation_required_now": True,
            "runtime_owner_intervention_required": False,
            "decision_count": 6,
        },
        "interaction": {
            "level": "L0_local_review_only_evidence_closure_wave",
            "remote_interaction_count": 0,
        },
        "safety_invariants": {
            "real_order_authority": False,
            "exchange_write_called": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "registry_authority_changed": False,
            "tier_policy_changed": False,
            "live_profile_changed": False,
            "mpg_member_live_scope_expanded": False,
        },
    }
    base.update(overrides)
    return base


def _strategy_review_deep_dive_wave(**overrides):
    base = {
        "status": "review_only_deep_dive_ready_for_owner_decision",
        "phase_status": {
            "phase_1_owner_perception_projection": "ready",
            "phase_2_six_line_deep_dive": "ready",
            "phase_3_owner_policy_decision_package": "ready_for_owner_policy_decision",
        },
        "deep_dive_packets": [
            {"strategy_group_id": "BRF-001"},
            {"strategy_group_id": "BTPC-001"},
            {"strategy_group_id": "LSR-001"},
            {"strategy_group_id": "MI-001"},
            {"strategy_group_id": "CPM-RO-001"},
            {"strategy_group_id": "MPG-001"},
        ],
        "owner_decision_package": {
            "status": "owner_policy_decision_package_ready",
            "owner_policy_confirmation_required_now": True,
            "runtime_owner_intervention_required": False,
            "decision_count": 6,
        },
        "interaction": {
            "level": "L0_local_review_only_deep_dive",
            "remote_interaction_count": 0,
        },
        "safety_invariants": {
            "real_order_authority": False,
            "exchange_write_called": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "registry_authority_changed": False,
            "tier_policy_changed": False,
            "live_profile_changed": False,
            "mpg_member_live_scope_expanded": False,
        },
    }
    base.update(overrides)
    return base


def test_goal_progress_waiting_for_market_with_p05_ready():
    module = _load_module()

    report = module.build_goal_progress_report(
        daily_check=_daily_check(),
        baseline=_baseline(),
        tier_policy=_tier_policy(),
    )

    assert report["schema"] == "brc.strategygroup_runtime_goal_progress_audit.v1"
    assert report["scope"] == "strategygroup_runtime_goal_progress_audit"
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
        "live_closure_evidence_status": "not_generated",
        "mock_signal_treated_as_real_signal": False,
        "real_order_closure_proven": False,
        "reason": "waiting_for_real_fresh_selected_strategygroup_signal",
        "status": "not_complete_waiting_for_market",
        "waiting_for_real_fresh_signal": True,
    }
    assert report["entry_fast_chain_boundary"] == {
        "candidate_authorization_to_finalgate_covered": True,
        "checks": {
            "all_selected_strategygroups_reach_finalgate_dispatch_checked": True,
            "fresh_signal_fast_auto_chain_checked": True,
            "operation_layer_authorization_chain_guard_checked": True,
            "operation_layer_blocker_review_policy_checked": True,
            "operation_layer_evidence_relay_checked": True,
            "operation_layer_standing_authorization_relay_checked": True,
            "required_facts_readiness_checked": True,
            "scoped_pipeline_operation_layer_handoff_checked": True,
            "selected_strategygroup_dispatch_guard_checked": True,
        },
        "finalgate_to_operation_layer_evidence_covered": True,
        "fresh_signal_to_candidate_authorization_covered": True,
        "operation_layer_authorization_guard_covered": True,
        "operation_layer_blocker_review_policy_covered": True,
        "real_action_time_finalgate_proven": False,
        "real_operation_layer_submit_proven": False,
        "real_order_dependent_remaining": True,
        "required_facts_gate_covered": True,
        "status": "ready",
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
        "reduce_only_recovery_standing_authorization_checked": True,
        "real_order_dependent_remaining": True,
        "real_post_submit_close_reconcile_settle_proven": False,
        "status": "ready",
    }
    assert report["strategygroup_tier_boundary"] == {
        "checks": {
            "all_selected_strategygroups_reach_finalgate_dispatch_checked": True,
            "allocated_subaccount_profile_boundary_checked": True,
            "new_strategygroups_default_observe_only_checked": True,
            "only_mpg_tiny_real_order_eligible_checked": True,
            "runtime_tier_policy_checked": True,
            "selected_strategygroup_dispatch_guard_checked": True,
            "strategygroup_adapter_boundary_checked": True,
            "tier_policy_source_readable": True,
        },
        "current_strategy_group_tiers": {
            "FBS-001": "L3",
            "MPG-001": "L4",
            "PMR-001": "L1",
            "SOR-001": "L3",
            "TEQ-001": "L2",
            "BTPC-001": "L2",
        },
        "first_live_lane_strategy_group": "MPG-001",
        "l4_strategy_groups": ["MPG-001"],
        "new_strategy_group_default_tiers": {
            "BRF": "L1",
            "LSR": "L1",
            "RBR": "L1",
            "VCB": "L1",
        },
        "new_strategy_groups_default_non_l4": True,
        "non_l4_strategy_groups": [
            "TEQ-001",
            "FBS-001",
            "SOR-001",
            "PMR-001",
            "BTPC-001",
        ],
        "status": "ready",
        "strategygroups_define_custom_execution_pipeline": False,
        "tier_policy_bypasses_finalgate": False,
        "tier_policy_bypasses_operation_layer": False,
        "tier_policy_is_execution_authority": False,
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


def test_goal_progress_projects_strategy_review_evidence_closure_without_runtime_intervention():
    module = _load_module()

    report = module.build_goal_progress_report(
        daily_check=_daily_check(),
        baseline=_baseline(),
        tier_policy=_tier_policy(),
        strategy_review_evidence_closure_wave=_strategy_review_evidence_closure_wave(),
    )

    assert report["status"] == "waiting_for_market"
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert report["checks"]["p05_ready"] is True
    assert report["checks"]["product_gaps"] == []
    boundary = report["strategy_review_evidence_closure_boundary"]
    assert boundary["status"] == "review_only_evidence_closure_wave_ready"
    assert boundary["phase_1_status"] == "ready"
    assert boundary["phase_2_status"] == "ready"
    assert boundary["phase_3_status"] == "ready_for_owner_policy_decision"
    assert boundary["evidence_packet_count"] == 6
    assert boundary["next_owner_decision_count"] == 6
    assert boundary["owner_policy_confirmation_required_now"] is True
    assert boundary["runtime_owner_intervention_required"] is False
    assert boundary["real_order_authority"] is False

    tracks = {track["id"]: track for track in report["tracks"]}
    assert tracks["p05_strategy_review_evidence_closure"]["status"] == "ready"
    assert tracks["p05_strategy_review_evidence_closure"]["owner_state"] == (
        "策略政策待确认"
    )
    text = module._owner_progress_text(report)
    assert "## Strategy Review Evidence Closure Boundary" in text
    assert "- Owner policy confirmation required now: 是" in text
    assert "- Runtime Owner intervention required: 否" in text
    assert "- Real order authority: 否" in text


def test_goal_progress_projects_strategy_review_deep_dive_without_runtime_intervention():
    module = _load_module()

    report = module.build_goal_progress_report(
        daily_check=_daily_check(),
        baseline=_baseline(),
        tier_policy=_tier_policy(),
        strategy_review_deep_dive_wave=_strategy_review_deep_dive_wave(),
    )

    assert report["status"] == "waiting_for_market"
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert report["checks"]["p05_ready"] is True
    assert report["checks"]["product_gaps"] == []
    boundary = report["strategy_review_deep_dive_boundary"]
    assert boundary["status"] == "review_only_deep_dive_ready_for_owner_decision"
    assert boundary["phase_1_status"] == "ready"
    assert boundary["phase_2_status"] == "ready"
    assert boundary["phase_3_status"] == "ready_for_owner_policy_decision"
    assert boundary["deep_dive_packet_count"] == 6
    assert boundary["next_owner_decision_count"] == 6
    assert boundary["owner_policy_confirmation_required_now"] is True
    assert boundary["runtime_owner_intervention_required"] is False
    assert boundary["real_order_authority"] is False

    tracks = {track["id"]: track for track in report["tracks"]}
    assert tracks["p05_strategy_review_deep_dive"]["status"] == "ready"
    assert tracks["p05_strategy_review_deep_dive"]["owner_state"] == (
        "六条线等待政策决策"
    )
    text = module._owner_progress_text(report)
    assert "## Strategy Review Deep Dive Boundary" in text
    assert "- Owner policy confirmation required now: 是" in text
    assert "- Runtime Owner intervention required: 否" in text
    assert "- Real order authority: 否" in text


def test_goal_progress_default_live_cutover_path_uses_runtime_monitor_latest():
    module = _load_module()

    assert (
        module.DEFAULT_LIVE_CUTOVER_READINESS_JSON.name
        == "latest-live-cutover-readiness.json"
    )
    assert "runtime-monitor" in str(module.DEFAULT_LIVE_CUTOVER_READINESS_JSON)
    assert "strategygroup-runtime-pilot/live-cutover-readiness" not in str(
        module.DEFAULT_LIVE_CUTOVER_READINESS_JSON
    )


def test_goal_progress_accepts_processing_owner_visibility_without_product_gap():
    module = _load_module()
    daily_check = _daily_check(status="processing")
    daily_check["checks"]["waiting_for_market"] = False
    daily_check["checks"]["runtime_live_closure_evidence_status"] = (
        "live_closure_in_progress"
    )
    daily_check["owner_summary"]["state"] = "处理中"
    daily_check["owner_summary"]["current_action"] = "等待系统完成收口"
    daily_check["owner_summary"]["visibility"] = {
        "category": "processing",
        "label": "处理中",
    }
    daily_check["notification"] = {
        "decision": "NOTIFY",
        "reason": "processing",
        "message": "系统正在处理真实订单闭环证据",
        "owner_intervention_required": False,
    }

    report = module.build_goal_progress_report(
        daily_check=daily_check,
        baseline=_baseline(),
        tier_policy=_tier_policy(),
        live_cutover_readiness=_live_cutover_readiness(),
    )

    assert report["status"] == "processing"
    assert report["owner_summary"]["state"] == "处理中"
    assert report["owner_summary"]["current_action"] == "等待系统完成收口"
    assert report["owner_summary"]["p0"] == "processing"
    assert report["owner_summary"]["p05"] == "ready"
    assert report["checks"]["product_gaps"] == []
    assert report["completion_boundary"]["status"] == (
        "not_complete_runtime_processing"
    )
    assert report["completion_boundary"]["reason"] == (
        "first_bounded_live_order_closure_in_progress"
    )
    assert report["live_closure_evidence_boundary"]["status"] == "in_progress"
    tracks = {track["id"]: track for track in report["tracks"]}
    assert tracks["p0_live_closure"]["status"] == "processing"
    assert tracks["p05_owner_visibility_loop"]["status"] == "ready"


def test_goal_progress_normalizes_no_signal_live_closure_residual_to_waiting(tmp_path):
    module = _load_module()
    daily_check = _daily_check(status="waiting_for_market")
    daily_check["checks"]["waiting_for_market"] = True
    daily_check["checks"]["runtime_live_closure_evidence_status"] = (
        "live_closure_in_progress"
    )
    daily_check["checks"]["real_order_readiness_summary"] = {
        "total": 2,
        "pass": 1,
        "waiting": 1,
        "blocked": 0,
        "submit_blocker_keys": [],
        "waiting_keys": ["fresh_signal"],
    }

    report = module.build_goal_progress_report(
        daily_check=daily_check,
        baseline=_baseline(),
        tier_policy=_tier_policy(),
        live_cutover_readiness=live_cutover_script.build_cutover_readiness_packet(
            output_dir=tmp_path / "cutover",
            generated_at_ms=1781753000000,
        ),
    )

    assert report["status"] == "waiting_for_market"
    assert report["owner_summary"]["state"] == "等待机会"
    assert report["owner_summary"]["current_action"] == "继续等待市场机会"
    assert report["checks"]["product_gaps"] == []
    assert report["completion_boundary"]["status"] == (
        "not_complete_waiting_for_market"
    )
    assert report["live_closure_evidence_boundary"]["status"] == "not_generated"
    assert report["live_closure_evidence_boundary"]["source_status"] == (
        "no_live_closure_evidence"
    )
    assert report["live_closure_evidence_boundary"]["raw_source_status"] == (
        "live_closure_in_progress"
    )
    assert report["live_closure_evidence_boundary"]["normalization_reason"] == (
        "waiting_for_market_no_fresh_signal"
    )
    assert report["live_closure_evidence_boundary"]["completed_stage_count"] == 0
    assert report["live_closure_evidence_boundary"]["stage_count"] == 9
    assert report["live_closure_evidence_boundary"]["expected_stage_count"] == 9
    assert report["live_closure_evidence_boundary"]["first_incomplete_stage"] == (
        "fresh_signal"
    )
    assert report["live_closure_evidence_boundary"]["market_dependent_waiting_keys"] == [
        "fresh_signal",
        "candidate_authorization",
        "action_time_finalgate",
        "official_operation_layer",
        "real_exchange_acceptance",
        "post_submit_real_reconciliation",
    ]
    assert report["p0_completion_audit_boundary"]["status"] == (
        "not_complete_waiting_for_market"
    )
    tracks = {track["id"]: track for track in report["tracks"]}
    assert tracks["p0_live_closure"]["status"] == "waiting_for_market"
    assert tracks["p05_owner_visibility_loop"]["status"] == "ready"


def test_goal_progress_marks_complete_from_live_closure_evidence_verification():
    module = _load_module()
    daily_check = _daily_check(status="ready")
    daily_check["checks"]["waiting_for_market"] = False
    daily_check["owner_summary"]["visibility"]["category"] = "running"
    live_cutover = _live_cutover_readiness()
    expected_evidence_keys = live_cutover["live_closure_cutover_contract"][
        "required_evidence_keys"
    ]

    report = module.build_goal_progress_report(
        daily_check=daily_check,
        baseline=_baseline(),
        tier_policy=_tier_policy(),
        live_cutover_readiness=live_cutover,
        live_closure_evidence_verification=_live_closure_evidence_verification(),
    )

    assert report["status"] == "ready"
    assert report["completion_boundary"]["goal_complete"] is True
    assert (
        report["completion_boundary"]["status"]
        == "complete"
    )
    assert report["completion_boundary"]["reason"] == "first_bounded_real_order_closed"
    assert report["live_closure_evidence_boundary"] == {
        "status": "complete",
        "source_status": "live_closure_complete",
        "raw_source_status": "live_closure_complete",
        "normalization_reason": None,
        "owner_state": "完成",
        "first_bounded_real_order_complete": True,
        "real_order_closure_proven": True,
        "completed_stage_count": 9,
        "stage_count": 9,
        "expected_stage_count": 9,
        "first_incomplete_stage": None,
        "expected_evidence_keys": expected_evidence_keys,
        "market_dependent_waiting_keys": [
            "fresh_signal",
            "candidate_authorization",
            "action_time_finalgate",
            "official_operation_layer",
            "real_exchange_acceptance",
            "post_submit_real_reconciliation",
        ],
        "missing_evidence_keys": [],
        "reject_reasons": [],
    }


def test_goal_progress_degrades_on_rejected_live_closure_evidence():
    module = _load_module()
    daily_check = _daily_check(status="ready")
    daily_check["checks"]["waiting_for_market"] = False
    daily_check["owner_summary"]["visibility"]["category"] = "running"

    report = module.build_goal_progress_report(
        daily_check=daily_check,
        baseline=_baseline(),
        tier_policy=_tier_policy(),
        live_cutover_readiness=_live_cutover_readiness(),
        live_closure_evidence_verification=_live_closure_evidence_verification(
            status="blocked_live_closure_rejected",
            owner_state="需要介入",
            completed_stage_count=0,
            first_incomplete_stage="live_fresh_signal",
            reject_reasons=["replay_signal"],
            completion={
                "first_bounded_real_order_complete": False,
                "real_order_closure_proven": False,
                "mock_signal_treated_as_real_signal": True,
                "disabled_smoke_treated_as_real_execution_proof": False,
            },
        ),
    )

    assert report["status"] == "degraded"
    assert report["live_closure_evidence_boundary"]["status"] == "rejected"
    assert "live_closure_evidence:replay_signal" in report["checks"]["product_gaps"]
    assert report["completion_boundary"]["goal_complete"] is False


def test_goal_progress_rejects_completion_flags_without_live_closure_evidence():
    module = _load_module()
    daily_check = _daily_check(status="ready")
    daily_check["checks"]["waiting_for_market"] = False
    daily_check["checks"]["first_bounded_real_order_complete"] = True
    daily_check["checks"]["real_order_closure_proven"] = True
    daily_check["owner_summary"]["visibility"]["category"] = "running"

    report = module.build_goal_progress_report(
        daily_check=daily_check,
        baseline=_baseline(),
        tier_policy=_tier_policy(),
        live_cutover_readiness=_live_cutover_readiness(),
    )

    assert report["status"] == "degraded"
    assert report["completion_boundary"]["goal_complete"] is False
    assert report["completion_boundary"]["first_bounded_real_order_complete"] is False
    assert report["completion_boundary"]["real_order_closure_proven"] is False
    assert (
        "live_closure_completion_claim_without_verified_evidence"
        in report["checks"]["product_gaps"]
    )


def test_goal_progress_owner_progress_text_has_track_table(tmp_path):
    module = _load_module()
    report = module.build_goal_progress_report(
        daily_check=_daily_check(),
        baseline=_baseline(),
        tier_policy=_tier_policy(),
        live_cutover_readiness=live_cutover_script.build_cutover_readiness_packet(
            output_dir=tmp_path / "cutover-owner-text",
            generated_at_ms=1781753000000,
        ),
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
    assert "- Market-dependent remaining: 5" in text
    assert (
        "- Market-dependent remaining items: "
        "fresh signal -> RequiredFacts -> candidate/auth fast chain, "
        "candidate/auth -> action-time FinalGate -> official Operation Layer "
        "evidence relay, real submit must happen only through official "
        "Operation Layer, entry accepted -> exchange-native hard "
        "stop/protection/recovery, post-submit finalize / reconciliation / "
        "budget settlement / review closure"
    ) in text
    assert "## Entry Fast Chain Boundary" in text
    assert "- Fresh signal to candidate/auth covered: 是" in text
    assert "- RequiredFacts gate covered: 是" in text
    assert "- Candidate/auth to FinalGate covered: 是" in text
    assert "- FinalGate to Operation Layer evidence covered: 是" in text
    assert "- Operation Layer authorization guard covered: 是" in text
    assert "- Real action-time FinalGate proven: 否" in text
    assert "- Real Operation Layer submit proven: 否" in text
    assert "## Exit Hardening Boundary" in text
    assert "- Post-submit exit outcome matrix checked: 是" in text
    assert "- Exchange-native hard stop required after entry: 是" in text
    assert "- Protection failure reduce-only recovery covered: 是" in text
    assert "- Real post-submit close/reconcile/settle proven: 否" in text
    assert "- Real order dependent remaining: 是" in text
    assert "## StrategyGroup Tier Boundary" in text
    assert "- First live lane StrategyGroup: MPG-001" in text
    assert "- L4 StrategyGroups: MPG-001" in text
    assert "- New StrategyGroups default non-L4: 是" in text
    assert "- Tier policy is execution authority: 否" in text
    assert "- Tier policy bypasses FinalGate: 否" in text
    assert "- Tier policy bypasses Operation Layer: 否" in text
    assert "## Live Cutover Readiness Boundary" in text
    assert "- Status: not_generated" in text
    assert "- Next fresh signal cutover ready: 是" in text
    assert "- Current real submit allowed: 否" in text
    assert "| P0.5 Runtime Interaction Optimization | ready | 已就绪 |" in text
    assert "## Evidence" in text
    assert "chain_ready_segments=3" in text
    assert "missing_chain_segments=0" in text
    assert "goal_chain_ready_segments=7" in text
    assert "missing_goal_chain_segments=0" in text
    assert "- P0.5 ready: 是" in text


def test_goal_progress_accepts_live_cutover_readiness_boundary(tmp_path):
    module = _load_module()
    report = module.build_goal_progress_report(
        daily_check=_daily_check(),
        baseline=_baseline(),
        tier_policy=_tier_policy(),
        live_cutover_readiness=live_cutover_script.build_cutover_readiness_packet(
            output_dir=tmp_path / "cutover",
            generated_at_ms=1781753000000,
        ),
    )

    assert report["status"] == "waiting_for_market"
    assert report["live_cutover_readiness_boundary"] == {
        "current_real_submit_allowed": False,
        "entry_fast_chain_ready": True,
        "exit_hardening_ready": True,
        "market_dependent_waiting_keys": [
            "fresh_signal",
            "candidate_authorization",
            "action_time_finalgate",
            "official_operation_layer",
            "real_exchange_acceptance",
            "post_submit_real_reconciliation",
        ],
        "next_fresh_signal_cutover_ready": True,
        "non_market_blockers": [],
        "owner_state": "等待机会",
        "source_status": "live_cutover_waiting_for_fresh_signal",
        "status": "ready",
        "strategygroup_tier_ready": True,
        "live_closure_cutover_contract_ready": True,
        "live_closure_required_stage_count": 9,
        "live_closure_required_evidence_keys": [
            "live_watcher_signal_packet_id",
            "required_facts_readiness_packet_id",
            "candidate_id",
            "runtime_grant_id",
            "fresh_submit_authorization_id",
            "action_time_finalgate_packet_id",
            "operation_layer_submit_authorization_id",
            "exchange_submit_execution_result_id",
            "exchange_native_hard_stop_order_id",
            "runtime_post_submit_finalize_packet_id",
            "post_submit_reconciliation_evidence_id",
            "post_submit_budget_settlement_id",
            "submit_outcome_review_id",
        ],
    }
    assert report["checks"]["product_gaps"] == []


def test_goal_progress_embeds_p0_completion_audit_boundary(tmp_path):
    module = _load_module()
    live_cutover = live_cutover_script.build_cutover_readiness_packet(
        output_dir=tmp_path / "cutover",
        generated_at_ms=1781753000000,
    )

    report = module.build_goal_progress_report(
        daily_check=_daily_check(),
        baseline=_baseline(),
        tier_policy=_tier_policy(),
        live_cutover_readiness=live_cutover,
    )

    assert report["status"] == "waiting_for_market"
    assert report["p0_completion_audit_boundary"] == {
        "goal_complete": False,
        "market_dependent_remaining": [
            "fresh signal -> RequiredFacts -> candidate/auth fast chain",
            (
                "candidate/auth -> action-time FinalGate -> official Operation "
                "Layer evidence relay"
            ),
            "real submit must happen only through official Operation Layer",
            "entry accepted -> exchange-native hard stop/protection/recovery",
            (
                "post-submit finalize / reconciliation / budget settlement / "
                "review closure"
            ),
        ],
        "market_dependent_remaining_count": 5,
        "non_market_gap_count": 0,
        "non_market_gap_keys": [],
        "source_status": "live_cutover_waiting_for_fresh_signal",
        "status": "not_complete_waiting_for_market",
    }
    assert report["checks"]["product_gaps"] == []


def test_goal_progress_degrades_on_missing_live_closure_contract():
    module = _load_module()
    readiness = _live_cutover_readiness()
    readiness.pop("live_closure_cutover_contract")

    report = module.build_goal_progress_report(
        daily_check=_daily_check(),
        baseline=_baseline(),
        tier_policy=_tier_policy(),
        live_cutover_readiness=readiness,
    )

    assert report["status"] == "degraded"
    assert report["live_cutover_readiness_boundary"]["status"] == "blocked"
    assert (
        "live_closure_cutover_contract:missing_or_not_ready"
        in report["live_cutover_readiness_boundary"]["non_market_blockers"]
    )
    assert (
        "live_cutover_readiness:live_closure_cutover_contract:"
        "missing_or_not_ready"
    ) in report["checks"]["product_gaps"]


def test_goal_progress_degrades_on_live_cutover_non_market_gap():
    module = _load_module()
    report = module.build_goal_progress_report(
        daily_check=_daily_check(),
        baseline=_baseline(),
        tier_policy=_tier_policy(),
        live_cutover_readiness=_live_cutover_readiness(
            status="blocked_non_market_cutover_gap",
            owner_state="需要介入",
            next_fresh_signal_cutover_ready=False,
            non_market_blockers=[
                "operation_layer_relay:operation_layer_evidence_relay_checked"
            ],
        ),
    )

    assert report["status"] == "degraded"
    assert report["live_cutover_readiness_boundary"]["status"] == "blocked"
    assert report["completion_boundary"]["status"] == "not_complete_product_gap"
    assert (
        "live_cutover_readiness:operation_layer_relay:"
        "operation_layer_evidence_relay_checked"
    ) in report["checks"]["product_gaps"]


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
        tier_policy=_tier_policy(),
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
    checks["allocated_subaccount_profile_boundary_checked"] = False
    checks["runtime_dry_run_required_checks_present"] = False
    checks["runtime_dry_run_missing_required_checks"] = [
        "post_submit_exit_outcome_matrix_checked"
    ]
    report = module.build_goal_progress_report(
        daily_check=_daily_check(checks=checks),
        baseline=_baseline(),
        tier_policy=_tier_policy(),
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


def test_goal_progress_marks_entry_fast_chain_boundary_needs_work_when_fast_chain_missing():
    module = _load_module()
    checks = dict(_daily_check()["checks"])
    checks["runtime_dry_run_required_checks_present"] = False
    checks["runtime_dry_run_missing_required_checks"] = [
        "fresh_signal_fast_auto_chain_checked"
    ]
    report = module.build_goal_progress_report(
        daily_check=_daily_check(checks=checks),
        baseline=_baseline(),
        tier_policy=_tier_policy(),
    )

    assert report["status"] == "degraded"
    assert report["entry_fast_chain_boundary"]["status"] == "needs_work"
    assert report["entry_fast_chain_boundary"]["checks"][
        "fresh_signal_fast_auto_chain_checked"
    ] is False
    assert report["entry_fast_chain_boundary"][
        "fresh_signal_to_candidate_authorization_covered"
    ] is False
    assert "entry_fast_chain_boundary_not_ready" in report["checks"]["product_gaps"]
    assert "missing_dry_run_check:fresh_signal_fast_auto_chain_checked" in report[
        "checks"
    ]["product_gaps"]


def test_goal_progress_marks_strategygroup_tier_boundary_needs_work_when_l4_guard_missing():
    module = _load_module()
    checks = dict(_daily_check()["checks"])
    checks["runtime_dry_run_required_checks_present"] = False
    checks["runtime_dry_run_missing_required_checks"] = [
        "only_mpg_tiny_real_order_eligible_checked"
    ]
    report = module.build_goal_progress_report(
        daily_check=_daily_check(checks=checks),
        baseline=_baseline(),
        tier_policy=_tier_policy(),
    )

    assert report["status"] == "degraded"
    assert report["strategygroup_tier_boundary"]["status"] == "needs_work"
    assert report["strategygroup_tier_boundary"]["l4_strategy_groups"] == []
    assert report["strategygroup_tier_boundary"][
        "first_live_lane_strategy_group"
    ] is None
    assert report["strategygroup_tier_boundary"]["checks"][
        "only_mpg_tiny_real_order_eligible_checked"
    ] is False
    assert "missing_dry_run_check:only_mpg_tiny_real_order_eligible_checked" in report[
        "checks"
    ]["product_gaps"]


def test_goal_progress_marks_tier_boundary_needs_work_when_allocated_subaccount_missing():
    module = _load_module()
    checks = dict(_daily_check()["checks"])
    checks["allocated_subaccount_profile_boundary_checked"] = False
    checks["runtime_dry_run_required_checks_present"] = False
    checks["runtime_dry_run_missing_required_checks"] = [
        "allocated_subaccount_profile_boundary_checked"
    ]
    report = module.build_goal_progress_report(
        daily_check=_daily_check(checks=checks),
        baseline=_baseline(),
        tier_policy=_tier_policy(),
    )

    assert report["status"] == "degraded"
    assert report["strategygroup_tier_boundary"]["status"] == "needs_work"
    assert report["strategygroup_tier_boundary"]["checks"][
        "allocated_subaccount_profile_boundary_checked"
    ] is False
    assert (
        "missing_dry_run_check:allocated_subaccount_profile_boundary_checked"
        in report["checks"]["product_gaps"]
    )
    assert "strategygroup_tier_boundary_not_ready" in report["checks"]["product_gaps"]


def test_goal_progress_marks_strategygroup_tier_boundary_needs_work_when_policy_missing():
    module = _load_module()
    report = module.build_goal_progress_report(
        daily_check=_daily_check(),
        baseline=_baseline(),
        tier_policy={},
    )

    assert report["status"] == "degraded"
    assert report["strategygroup_tier_boundary"]["status"] == "needs_work"
    assert report["strategygroup_tier_boundary"]["current_strategy_group_tiers"] == {}
    assert report["strategygroup_tier_boundary"]["checks"][
        "tier_policy_source_readable"
    ] is False
    assert report["completion_boundary"]["waiting_for_real_fresh_signal"] is False
    assert "strategygroup_tier_boundary_not_ready" in report["checks"]["product_gaps"]
    assert report["strategygroup_tier_boundary"][
        "tier_policy_is_execution_authority"
    ] is True


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
        tier_policy=_tier_policy(),
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
        tier_policy=_tier_policy(),
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
        tier_policy=_tier_policy(),
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
        tier_policy=_tier_policy(),
    )

    assert report["status"] == "degraded"
    assert "local_goal_progress_expected_zero_remote_interaction" in report["checks"][
        "product_gaps"
    ]


def test_goal_progress_keeps_stale_monitor_cache_out_of_trade_blockers():
    module = _load_module()
    daily_check = _daily_check(status="waiting_for_market_monitor_refresh_needed")
    daily_check["runtime_status"] = "waiting_for_market"
    daily_check["monitor_status"] = "needs_refresh"
    daily_check["owner_status"] = "waiting_for_opportunity"
    daily_check["owner_summary"]["state"] = "等待机会"
    daily_check["owner_summary"]["current_action"] = "刷新本地 runtime monitor 缓存"
    daily_check["owner_summary"]["visibility"] = {
        "category": "monitor_refresh",
        "label": "监控状态需刷新",
    }
    daily_check["notification"] = {
        "decision": "NOTIFY",
        "reason": "runtime_progress_cache_stale",
        "owner_intervention_required": False,
    }
    daily_check["checks"]["monitor_refresh_needed"] = True
    daily_check["checks"]["monitor_refresh_reasons"] = [
        "runtime_progress_cache_stale"
    ]

    report = module.build_goal_progress_report(
        daily_check=daily_check,
        baseline=_baseline(),
        tier_policy=_tier_policy(),
    )

    assert report["status"] == "waiting_for_market_monitor_refresh_needed"
    assert report["runtime_status"] == "waiting_for_market"
    assert report["monitor_status"] == "needs_refresh"
    assert report["owner_status"] == "waiting_for_opportunity"
    assert report["checks"]["blockers"] == []
    assert report["checks"]["product_gaps"] == []
    assert report["checks"]["monitor_refresh_needed"] is True
    assert report["checks"]["refresh_required"] is True
    assert report["checks"]["automation_notify"] is True
    assert report["checks"]["owner_notify"] is False
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert report["owner_summary"]["state"] == "等待机会"
    assert report["completion_boundary"]["status"] == "not_complete_waiting_for_market"
    assert report["completion_boundary"]["completion_blocker_class"] == "waiting_for_market"
    tracks = {track["id"]: track for track in report["tracks"]}
    assert tracks["p0_live_closure"]["status"] == "waiting_for_market"
    assert tracks["p05_runtime_interaction_optimization"]["status"] == "ready"


def test_goal_progress_keeps_deployment_issue_out_of_owner_decision():
    module = _load_module()
    daily_check = _daily_check(status="temporarily_unavailable_deployment_issue")
    daily_check["runtime_status"] = "temporarily_unavailable"
    daily_check["monitor_status"] = "deployment_issue"
    daily_check["owner_status"] = "temporarily_unavailable"
    daily_check["owner_summary"]["state"] = "暂不可用"
    daily_check["owner_summary"]["current_action"] = "处理部署基线不一致"
    daily_check["owner_summary"]["owner_intervention_required"] = False
    daily_check["owner_summary"]["visibility"] = {
        "category": "deployment_issue",
        "label": "暂不可用",
        "owner_intervention_required": False,
    }
    daily_check["notification"] = {
        "decision": "NOTIFY",
        "reason": "runtime_head_mismatch",
        "owner_intervention_required": False,
    }
    daily_check["checks"]["blockers"] = [
        "runtime_head_mismatch",
        "l1_snapshot_blocked",
    ]
    daily_check["checks"]["deployment_issue"] = True

    report = module.build_goal_progress_report(
        daily_check=daily_check,
        baseline=_baseline(),
        tier_policy=_tier_policy(),
    )

    assert report["status"] == "temporarily_unavailable_deployment_issue"
    assert report["runtime_status"] == "temporarily_unavailable"
    assert report["monitor_status"] == "deployment_issue"
    assert report["owner_status"] == "temporarily_unavailable"
    assert report["checks"]["blockers"] == []
    assert report["checks"]["owner_notify"] is False
    assert report["owner_summary"]["owner_intervention_required"] is False
    tracks = {track["id"]: track for track in report["tracks"]}
    assert tracks["p0_live_closure"]["status"] == "waiting_for_market"
    assert tracks["p0_live_closure"]["blockers"] == []


def test_goal_progress_cli_writes_json_and_owner_progress(tmp_path):
    module = _load_module()
    daily_check_path = tmp_path / "daily-check.json"
    baseline_path = tmp_path / "baseline.json"
    tier_policy_path = tmp_path / "tier-policy.json"
    live_cutover_path = tmp_path / "live-cutover.json"
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
    tier_policy_path.write_text(
        json.dumps(_tier_policy(), ensure_ascii=False),
        encoding="utf-8",
    )
    live_cutover_path.write_text(
        json.dumps(_live_cutover_readiness(), ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--daily-check-json",
            str(daily_check_path),
            "--baseline-json",
            str(baseline_path),
            "--tier-policy-json",
            str(tier_policy_path),
            "--live-cutover-readiness-json",
            str(live_cutover_path),
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
    assert payload["entry_fast_chain_boundary"]["status"] == "ready"
    assert payload["entry_fast_chain_boundary"][
        "real_action_time_finalgate_proven"
    ] is False
    assert payload["entry_fast_chain_boundary"][
        "real_operation_layer_submit_proven"
    ] is False
    assert payload["exit_hardening_boundary"]["status"] == "ready"
    assert payload["strategygroup_tier_boundary"]["status"] == "ready"
    assert payload["strategygroup_tier_boundary"]["l4_strategy_groups"] == [
        "MPG-001"
    ]
    assert payload["strategygroup_tier_boundary"][
        "new_strategy_groups_default_non_l4"
    ] is True
    assert payload["live_cutover_readiness_boundary"]["status"] == "ready"
    assert (
        payload["live_cutover_readiness_boundary"][
            "next_fresh_signal_cutover_ready"
        ]
        is True
    )
    assert (
        payload["exit_hardening_boundary"][
            "real_post_submit_close_reconcile_settle_proven"
        ]
        is False
    )
    progress = output_md.read_text(encoding="utf-8")
    assert "## StrategyGroup Runtime Goal Progress" in progress
    assert "## Completion Boundary" in progress
    assert "## Entry Fast Chain Boundary" in progress
    assert "## Exit Hardening Boundary" in progress
    assert "## StrategyGroup Tier Boundary" in progress
    assert "## Live Cutover Readiness Boundary" in progress
    assert "- Next fresh signal cutover ready: 是" in progress
    assert "- P0.5 ready: 是" in progress
    assert list(tmp_path.glob(".goal-progress.json.*.tmp")) == []
    assert list(tmp_path.glob(".goal-progress.md.*.tmp")) == []


def test_goal_progress_cli_auto_verifies_live_closure_evidence_packet(tmp_path):
    module = _load_module()
    daily_check_path = tmp_path / "daily-check.json"
    baseline_path = tmp_path / "baseline.json"
    tier_policy_path = tmp_path / "tier-policy.json"
    live_cutover_path = tmp_path / "live-cutover.json"
    live_closure_evidence_path = tmp_path / "live-closure-evidence.json"
    missing_verification_path = tmp_path / "missing-verification.json"
    output_json = tmp_path / "goal-progress.json"
    output_md = tmp_path / "goal-progress.md"
    daily_check = _daily_check(status="ready")
    daily_check["checks"]["waiting_for_market"] = False
    daily_check["owner_summary"]["visibility"]["category"] = "running"
    daily_check_path.write_text(
        json.dumps(daily_check, ensure_ascii=False),
        encoding="utf-8",
    )
    baseline_path.write_text(
        json.dumps(_baseline(), ensure_ascii=False),
        encoding="utf-8",
    )
    tier_policy_path.write_text(
        json.dumps(_tier_policy(), ensure_ascii=False),
        encoding="utf-8",
    )
    live_cutover = _live_cutover_readiness()
    live_cutover_path.write_text(
        json.dumps(live_cutover, ensure_ascii=False),
        encoding="utf-8",
    )
    evidence = {
        key: f"{key}-1"
        for key in live_cutover["live_closure_cutover_contract"][
            "required_evidence_keys"
        ]
    }
    live_closure_evidence_path.write_text(
        json.dumps(
            {
                "source_kind": "official_live_closure_evidence",
                "official_live_closure_evidence": True,
                "live_signal_chain_proof": {
                    "live_watcher_signal_packet_id": (
                        "live_watcher_signal_packet_id-1"
                    ),
                    "present_evidence_keys": [
                        "required_facts_readiness_packet_id",
                        "candidate_id",
                    ],
                    "matched_evidence_keys": [
                        "required_facts_readiness_packet_id",
                        "candidate_id",
                    ],
                    "missing_source_match_keys": [],
                },
                "pre_submit_authorization_chain_proof": {
                    "fresh_submit_authorization_id": (
                        "fresh_submit_authorization_id-1"
                    ),
                    "present_evidence_keys": [
                        "candidate_id",
                        "runtime_grant_id",
                        "action_time_finalgate_packet_id",
                        "operation_layer_submit_authorization_id",
                    ],
                    "matched_evidence_keys": [
                        "candidate_id",
                        "runtime_grant_id",
                        "action_time_finalgate_packet_id",
                        "operation_layer_submit_authorization_id",
                    ],
                    "missing_source_match_keys": [],
                },
                "live_submit_proof": {
                    "exchange_result_present": True,
                    "result_source_matched": True,
                    "result_source_count": 1,
                    "live_exchange_called": True,
                    "real_order_placed": True,
                    "exchange_accepted": True,
                    "exchange_order_id_present": True,
                    "exchange_submit_execution_result_id": (
                        "exchange_submit_execution_result_id-1"
                    ),
                },
                "exchange_native_protection_proof": {
                    "hard_stop_present": True,
                    "result_source_matched": True,
                    "result_source_count": 1,
                    "exchange_native": True,
                    "hard_stop_accepted": True,
                    "reduce_only": True,
                    "exchange_submit_execution_result_id": (
                        "exchange_submit_execution_result_id-1"
                    ),
                    "exchange_native_hard_stop_order_id": (
                        "exchange_native_hard_stop_order_id-1"
                    ),
                },
                "post_submit_close_loop_proof": {
                    "exchange_submit_execution_result_id": (
                        "exchange_submit_execution_result_id-1"
                    ),
                    "present_evidence_keys": [
                        "runtime_post_submit_finalize_packet_id",
                        "post_submit_reconciliation_evidence_id",
                        "post_submit_budget_settlement_id",
                        "submit_outcome_review_id",
                    ],
                    "matched_evidence_keys": [
                        "runtime_post_submit_finalize_packet_id",
                        "post_submit_reconciliation_evidence_id",
                        "post_submit_budget_settlement_id",
                        "submit_outcome_review_id",
                    ],
                    "missing_source_match_keys": [],
                    "finalize_complete": True,
                    "reconciliation_matched": True,
                    "budget_settled": True,
                    "review_recorded": True,
                },
                "runtime_boundary_proof": _runtime_boundary_proof(),
                "evidence": evidence,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--daily-check-json",
            str(daily_check_path),
            "--baseline-json",
            str(baseline_path),
            "--tier-policy-json",
            str(tier_policy_path),
            "--live-cutover-readiness-json",
            str(live_cutover_path),
            "--live-closure-evidence-verification-json",
            str(missing_verification_path),
            "--live-closure-evidence-json",
            str(live_closure_evidence_path),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["live_closure_evidence_boundary"]["status"] == "complete"
    assert payload["completion_boundary"]["goal_complete"] is True
    assert payload["completion_boundary"]["reason"] == "first_bounded_real_order_closed"
    assert not missing_verification_path.exists()


def test_goal_progress_cli_auto_generates_live_cutover_readiness_when_missing(
    tmp_path,
):
    module = _load_module()
    daily_check_path = tmp_path / "daily-check.json"
    baseline_path = tmp_path / "baseline.json"
    tier_policy_path = tmp_path / "tier-policy.json"
    live_cutover_path = tmp_path / "generated-live-cutover.json"
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
    tier_policy_path.write_text(
        json.dumps(_tier_policy(), ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--daily-check-json",
            str(daily_check_path),
            "--baseline-json",
            str(baseline_path),
            "--tier-policy-json",
            str(tier_policy_path),
            "--live-cutover-readiness-json",
            str(live_cutover_path),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    assert live_cutover_path.exists()
    generated_cutover = json.loads(live_cutover_path.read_text(encoding="utf-8"))
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert generated_cutover["status"] == "live_cutover_waiting_for_fresh_signal"
    assert payload["live_cutover_readiness_boundary"]["status"] == "ready"
    assert (
        payload["live_cutover_readiness_boundary"][
            "next_fresh_signal_cutover_ready"
        ]
        is True
    )
