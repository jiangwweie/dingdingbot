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


def _write_passed_post_revision_review(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "passed",
            "interaction": {
                "level": "L0_local_post_revision_replay_review",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "server_files_mutated": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_opportunity_decision_loop(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "decision_loop_ready",
            "decision": {"default_next_step": "continue_btpc_l2_shadow_fact_quality_review"},
            "interaction": {
                "level": "L0_local_opportunity_decision_loop",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "server_files_mutated": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_btpc_fact_quality_review(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "btpc_l2_shadow_fact_quality_review_ready",
            "decision": {
                "default_next_step": "attach_btpc_derivatives_fact_sources_and_margin_model_for_l2_quality_review",
                "l2_shadow_observation_can_continue": True,
                "l4_scope_change_recommended": False,
                "real_order_scope_change_recommended": False,
            },
            "interaction": {
                "level": "L0_local_btpc_l2_shadow_fact_quality_review",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "server_files_mutated": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_btpc_local_fact_proxy_review(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "btpc_local_fact_proxy_review_ready",
            "decision": {
                "l2_shadow_quality_review_can_continue": True,
                "local_proxy_satisfies_live_required_facts": False,
                "l4_scope_change_recommended": False,
                "real_order_scope_change_recommended": False,
            },
            "interaction": {
                "level": "L0_local_btpc_fact_proxy_review",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "proxy_is_not_live_required_fact": True,
                "server_files_mutated": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_btpc_proxy_replay_quality_review(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "btpc_proxy_replay_quality_review_ready",
            "decision": {
                "proxy_replay_quality_review_ready": True,
                "proxy_replay_satisfies_live_required_facts": False,
                "l4_scope_change_recommended": False,
                "real_order_scope_change_recommended": False,
            },
            "interaction": {
                "level": "L0_local_btpc_proxy_replay_quality_review",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "proxy_replay_is_not_live_required_fact": True,
                "server_files_mutated": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_btpc_l2_keep_revise_fact_source_decision(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "btpc_l2_keep_revise_fact_source_decision_ready",
            "decision": {
                "keep_l2_shadow_observation": True,
                "revise_fact_classifier_inputs_before_promotion": True,
                "l2_promotion_recommended_now": False,
                "l4_scope_change_recommended": False,
                "real_order_scope_change_recommended": False,
            },
            "interaction": {
                "level": "L0_local_btpc_l2_keep_revise_fact_source_decision",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "server_files_mutated": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_btpc_live_derivatives_fact_source_mapping(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "btpc_live_derivatives_fact_source_mapping_ready_without_live_authority",
            "decision": {
                "live_derivatives_fact_source_mapping_ready": True,
                "mapping_satisfies_live_required_facts": False,
                "l2_promotion_recommended_now": False,
                "l4_scope_change_recommended": False,
                "real_order_scope_change_recommended": False,
            },
            "interaction": {
                "level": "L0_local_btpc_live_derivatives_fact_source_mapping",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "mapping_is_not_live_required_fact": True,
                "server_files_mutated": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_btpc_classifier_rule_review(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "btpc_classifier_rule_review_recorded_without_live_authority",
            "decision": {
                "classifier_rule_review_recorded": True,
                "classifier_review_satisfies_live_required_facts": False,
                "l2_promotion_recommended_now": False,
                "l4_scope_change_recommended": False,
                "real_order_scope_change_recommended": False,
            },
            "interaction": {
                "level": "L0_local_btpc_classifier_rule_review",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "classifier_review_is_not_live_required_fact": True,
                "server_files_mutated": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_strategygroup_decision_ledger(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "decision_ledger_ready",
            "decision": {
                "single_main_product": True,
                "one_current_row_per_strategy_group": True,
                "raw_replay_samples_duplicated": False,
                "real_order_scope_change_recommended": False,
                "l4_promotion_recommended": False,
            },
            "interaction": {
                "level": "L0_local_strategygroup_decision_ledger",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "local_decision_ledger_only": True,
                "server_files_mutated": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_strategygroup_quality_wave(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "quality_wave_ready",
            "rows": [
                {
                    "strategy_group_id": "BTPC-001",
                    "current_tier": "L2",
                    "current_decision": "revise",
                },
                {
                    "strategy_group_id": "VCB-001",
                    "current_tier": "L1",
                    "current_decision": "keep_observing",
                },
                {
                    "strategy_group_id": "LSR-001",
                    "current_tier": "L1",
                    "current_decision": "keep_observing",
                },
                {
                    "strategy_group_id": "BRF-001",
                    "current_tier": "L1",
                    "current_decision": "keep_observing",
                },
                {
                    "strategy_group_id": "RBR-001",
                    "current_tier": "L1",
                    "current_decision": "park",
                },
            ],
            "interaction": {
                "level": "L0_local_quality_wave",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
        },
    )


def _write_ready_handoff_boundary_closure(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "handoff_boundary_closure_ready",
            "interaction": {
                "level": "L0_local_handoff_boundary_closure",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
        },
    )


def _write_ready_btpc_fact_classifier_guard(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "btpc_fact_classifier_guard_ready",
            "interaction": {
                "level": "L0_local_btpc_fact_classifier_guard",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_lifecycle_rehearsal(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "lifecycle_rehearsal_ready",
            "interaction": {
                "level": "L0_local_lifecycle_rehearsal",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_pre_live_rehearsal_readiness(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "pre_live_rehearsal_ready",
            "decision": {
                "pre_live_rehearsal_ready": True,
                "live_submit_ready": False,
                "live_outcome_calibrated": False,
                "actionable_now": False,
                "real_order_authority": False,
            },
            "interaction": {
                "level": "L0_local_pre_live_rehearsal_readiness",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_live_submit_readiness_bridge(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "live_submit_standby_waiting_for_market",
            "runtime_consumption": {
                "standard_local_monitor_sequence_step": True,
                "tokyo_runtime_can_consume_after_deploy": True,
                "pre_live_rehearsal_ready_visible": True,
                "live_submit_ready_false_reason": "no_fresh_signal",
            },
            "owner_state": {
                "owner_status": "waiting_for_opportunity",
                "owner_label": "等待机会",
                "owner_intervention_required": False,
                "owner_manual_packet_read_required": False,
            },
            "checks": {
                "blockers": [],
                "pre_live_rehearsal_ready": True,
                "ready_for_finalgate_checkpoint": False,
                "live_submit_ready": False,
                "owner_intervention_required": False,
                "fresh_signal_state": "none",
            },
            "decision": {
                "pre_live_rehearsal_ready": True,
                "live_submit_standby_ready": True,
                "ready_for_finalgate_checkpoint": False,
                "live_submit_ready": False,
                "live_submit_ready_false_reason": "no_fresh_signal",
                "actionable_now": False,
                "real_order_authority": False,
            },
            "interaction": {
                "level": "L0_local_live_submit_readiness_bridge",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _maybe_write_strategygroup_closure_step(
    script: str, command: list[str]
) -> subprocess.CompletedProcess[str] | None:
    if script == "build_strategygroup_quality_wave.py":
        _write_ready_strategygroup_quality_wave(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_handoff_boundary_closure.py":
        _write_ready_handoff_boundary_closure(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_btpc_fact_classifier_guard.py":
        _write_ready_btpc_fact_classifier_guard(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_lifecycle_rehearsal.py":
        _write_ready_lifecycle_rehearsal(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_pre_live_rehearsal_readiness.py":
        _write_ready_pre_live_rehearsal_readiness(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_live_submit_readiness_bridge.py":
        _write_ready_live_submit_readiness_bridge(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    return None


def test_local_monitor_sequence_runs_cache_checks_in_order(tmp_path: Path) -> None:
    module = _load_module()
    calls: list[str] = []
    decision_loop_commands: list[list[str]] = []

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        script = Path(command[1]).name
        calls.append(script)
        closure_result = _maybe_write_strategygroup_closure_step(script, command)
        if closure_result is not None:
            return closure_result
        if script == "build_strategygroup_post_revision_replay_review.py":
            _write_passed_post_revision_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_opportunity_decision_loop.py":
            decision_loop_commands.append(command)
            _write_ready_opportunity_decision_loop(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_l2_shadow_fact_quality_review.py":
            _write_ready_btpc_fact_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_local_fact_proxy_review.py":
            _write_ready_btpc_local_fact_proxy_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_proxy_replay_quality_review.py":
            _write_ready_btpc_proxy_replay_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_l2_keep_revise_fact_source_decision.py"
        ):
            _write_ready_btpc_l2_keep_revise_fact_source_decision(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_live_derivatives_fact_source_mapping.py"
        ):
            _write_ready_btpc_live_derivatives_fact_source_mapping(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_classifier_rule_review.py":
            _write_ready_btpc_classifier_rule_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_decision_ledger.py":
            _write_ready_strategygroup_decision_ledger(command)
            return subprocess.CompletedProcess(command, 0, "", "")
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
        elif script == "run_strategygroup_runtime_replay_lab.py":
            _write_output(
                command,
                {
                    "status": "passed",
                    "checks": {"btpc001_l2_shadow_replay_cases_present": True},
                    "interaction": {
                        "level": "L0_local_replay_lab",
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
        replay_lab_json=tmp_path / "replay.json",
        replay_lab_md=tmp_path / "replay.md",
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
        post_revision_replay_review_json=tmp_path / "post-revision-review.json",
        post_revision_replay_review_md=tmp_path / "post-revision-review.md",
        opportunity_decision_loop_json=tmp_path / "opportunity-decision-loop.json",
        opportunity_decision_loop_md=tmp_path / "opportunity-decision-loop.md",
        btpc_l2_shadow_fact_quality_review_json=tmp_path / "btpc-fact-review.json",
        btpc_l2_shadow_fact_quality_review_md=tmp_path / "btpc-fact-review.md",
        btpc_local_fact_proxy_review_json=tmp_path / "btpc-proxy-review.json",
        btpc_local_fact_proxy_review_md=tmp_path / "btpc-proxy-review.md",
        btpc_proxy_replay_quality_review_json=tmp_path / "btpc-proxy-replay.json",
        btpc_proxy_replay_quality_review_md=tmp_path / "btpc-proxy-replay.md",
        btpc_l2_keep_revise_fact_source_decision_json=tmp_path
        / "btpc-l2-decision.json",
        btpc_l2_keep_revise_fact_source_decision_md=tmp_path
        / "btpc-l2-decision.md",
        btpc_live_derivatives_fact_source_mapping_json=tmp_path
        / "btpc-live-source-mapping.json",
        btpc_live_derivatives_fact_source_mapping_md=tmp_path
        / "btpc-live-source-mapping.md",
        btpc_classifier_rule_review_json=tmp_path / "btpc-classifier-rule.json",
        btpc_classifier_rule_review_md=tmp_path / "btpc-classifier-rule.md",
        strategygroup_decision_ledger_json=tmp_path / "decision-ledger.json",
        strategygroup_decision_ledger_md=tmp_path / "decision-ledger.md",
        strategygroup_quality_wave_json=tmp_path / "quality-wave.json",
        strategygroup_quality_wave_md=tmp_path / "quality-wave.md",
        strategygroup_handoff_boundary_closure_json=tmp_path
        / "handoff-boundary.json",
        strategygroup_handoff_boundary_closure_md=tmp_path
        / "handoff-boundary.md",
        strategygroup_btpc_fact_classifier_guard_json=tmp_path
        / "btpc-guard.json",
        strategygroup_btpc_fact_classifier_guard_md=tmp_path
        / "btpc-guard.md",
        strategygroup_lifecycle_rehearsal_json=tmp_path / "lifecycle.json",
        strategygroup_lifecycle_rehearsal_md=tmp_path / "lifecycle.md",
        strategygroup_pre_live_rehearsal_readiness_json=tmp_path
        / "pre-live-readiness.json",
        strategygroup_pre_live_rehearsal_readiness_md=tmp_path
        / "pre-live-readiness.md",
        strategygroup_live_submit_readiness_bridge_json=tmp_path
        / "live-submit-bridge.json",
        strategygroup_live_submit_readiness_bridge_md=tmp_path
        / "live-submit-bridge.md",
        command_runner=fake_runner,
    )

    assert calls == [
        "run_strategygroup_runtime_daily_check.py",
        "runtime_live_cutover_readiness.py",
        "run_strategygroup_runtime_goal_progress_audit.py",
        "runtime_first_bounded_live_order_completion_audit.py",
        "run_strategygroup_runtime_replay_lab.py",
        "run_strategygroup_signal_coverage_diagnostic.py",
        "build_strategygroup_signal_coverage_expansion_review.py",
        "build_strategygroup_l2_readiness_review.py",
        "run_strategygroup_l2_intake_dry_run.py",
        "run_strategygroup_l2_tier_policy_review.py",
        "build_strategygroup_post_revision_replay_review.py",
        "build_strategygroup_opportunity_decision_loop.py",
        "build_strategygroup_btpc_l2_shadow_fact_quality_review.py",
        "build_strategygroup_btpc_local_fact_proxy_review.py",
        "build_strategygroup_btpc_proxy_replay_quality_review.py",
        "build_strategygroup_opportunity_decision_loop.py",
        "build_strategygroup_btpc_l2_keep_revise_fact_source_decision.py",
        "build_strategygroup_btpc_live_derivatives_fact_source_mapping.py",
        "build_strategygroup_btpc_classifier_rule_review.py",
        "build_strategygroup_decision_ledger.py",
        "build_strategygroup_quality_wave.py",
        "build_strategygroup_handoff_boundary_closure.py",
        "build_strategygroup_btpc_fact_classifier_guard.py",
        "build_strategygroup_lifecycle_rehearsal.py",
        "build_strategygroup_pre_live_rehearsal_readiness.py",
        "build_strategygroup_live_submit_readiness_bridge.py",
    ]
    assert len(decision_loop_commands) == 2
    assert "--btpc-proxy-replay-quality-json" not in decision_loop_commands[0]
    assert "--btpc-proxy-replay-quality-json" in decision_loop_commands[1]
    assert decision_loop_commands[1][
        decision_loop_commands[1].index("--btpc-proxy-replay-quality-json") + 1
    ] == str(tmp_path / "btpc-proxy-replay.json")
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
        closure_result = _maybe_write_strategygroup_closure_step(script, command)
        if closure_result is not None:
            return closure_result
        if script == "build_strategygroup_post_revision_replay_review.py":
            _write_passed_post_revision_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_opportunity_decision_loop.py":
            _write_ready_opportunity_decision_loop(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_l2_shadow_fact_quality_review.py":
            _write_ready_btpc_fact_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_local_fact_proxy_review.py":
            _write_ready_btpc_local_fact_proxy_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_proxy_replay_quality_review.py":
            _write_ready_btpc_proxy_replay_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_l2_keep_revise_fact_source_decision.py"
        ):
            _write_ready_btpc_l2_keep_revise_fact_source_decision(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_live_derivatives_fact_source_mapping.py"
        ):
            _write_ready_btpc_live_derivatives_fact_source_mapping(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_classifier_rule_review.py":
            _write_ready_btpc_classifier_rule_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_decision_ledger.py":
            _write_ready_strategygroup_decision_ledger(command)
            return subprocess.CompletedProcess(command, 0, "", "")
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

        if script == "run_strategygroup_runtime_replay_lab.py":
            _write_output(
                command,
                {
                    "status": "passed",
                    "interaction": {
                        "level": "L0_local_replay_lab",
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
        replay_lab_json=tmp_path / "replay.json",
        replay_lab_md=tmp_path / "replay.md",
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
        post_revision_replay_review_json=tmp_path / "post-revision-review.json",
        post_revision_replay_review_md=tmp_path / "post-revision-review.md",
        opportunity_decision_loop_json=tmp_path / "opportunity-decision-loop.json",
        opportunity_decision_loop_md=tmp_path / "opportunity-decision-loop.md",
        btpc_l2_shadow_fact_quality_review_json=tmp_path / "btpc-fact-review.json",
        btpc_l2_shadow_fact_quality_review_md=tmp_path / "btpc-fact-review.md",
        btpc_local_fact_proxy_review_json=tmp_path / "btpc-proxy-review.json",
        btpc_local_fact_proxy_review_md=tmp_path / "btpc-proxy-review.md",
        btpc_proxy_replay_quality_review_json=tmp_path / "btpc-proxy-replay.json",
        btpc_proxy_replay_quality_review_md=tmp_path / "btpc-proxy-replay.md",
        btpc_l2_keep_revise_fact_source_decision_json=tmp_path
        / "btpc-l2-decision.json",
        btpc_l2_keep_revise_fact_source_decision_md=tmp_path
        / "btpc-l2-decision.md",
        btpc_live_derivatives_fact_source_mapping_json=tmp_path
        / "btpc-live-source-mapping.json",
        btpc_live_derivatives_fact_source_mapping_md=tmp_path
        / "btpc-live-source-mapping.md",
        btpc_classifier_rule_review_json=tmp_path / "btpc-classifier-rule.json",
        btpc_classifier_rule_review_md=tmp_path / "btpc-classifier-rule.md",
        strategygroup_decision_ledger_json=tmp_path / "decision-ledger.json",
        strategygroup_decision_ledger_md=tmp_path / "decision-ledger.md",
        strategygroup_quality_wave_json=tmp_path / "quality-wave.json",
        strategygroup_quality_wave_md=tmp_path / "quality-wave.md",
        strategygroup_handoff_boundary_closure_json=tmp_path
        / "handoff-boundary.json",
        strategygroup_handoff_boundary_closure_md=tmp_path
        / "handoff-boundary.md",
        strategygroup_btpc_fact_classifier_guard_json=tmp_path
        / "btpc-guard.json",
        strategygroup_btpc_fact_classifier_guard_md=tmp_path
        / "btpc-guard.md",
        strategygroup_lifecycle_rehearsal_json=tmp_path / "lifecycle.json",
        strategygroup_lifecycle_rehearsal_md=tmp_path / "lifecycle.md",
        strategygroup_pre_live_rehearsal_readiness_json=tmp_path
        / "pre-live-readiness.json",
        strategygroup_pre_live_rehearsal_readiness_md=tmp_path
        / "pre-live-readiness.md",
        strategygroup_live_submit_readiness_bridge_json=tmp_path
        / "live-submit-bridge.json",
        strategygroup_live_submit_readiness_bridge_md=tmp_path
        / "live-submit-bridge.md",
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
        closure_result = _maybe_write_strategygroup_closure_step(script, command)
        if closure_result is not None:
            return closure_result
        if script == "build_strategygroup_post_revision_replay_review.py":
            _write_passed_post_revision_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_opportunity_decision_loop.py":
            _write_ready_opportunity_decision_loop(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_l2_shadow_fact_quality_review.py":
            _write_ready_btpc_fact_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_local_fact_proxy_review.py":
            _write_ready_btpc_local_fact_proxy_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_proxy_replay_quality_review.py":
            _write_ready_btpc_proxy_replay_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_l2_keep_revise_fact_source_decision.py"
        ):
            _write_ready_btpc_l2_keep_revise_fact_source_decision(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_live_derivatives_fact_source_mapping.py"
        ):
            _write_ready_btpc_live_derivatives_fact_source_mapping(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_classifier_rule_review.py":
            _write_ready_btpc_classifier_rule_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_decision_ledger.py":
            _write_ready_strategygroup_decision_ledger(command)
            return subprocess.CompletedProcess(command, 0, "", "")
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

        if script == "run_strategygroup_runtime_replay_lab.py":
            _write_output(
                command,
                {
                    "status": "passed",
                    "interaction": {
                        "level": "L0_local_replay_lab",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_runtime_replay_lab.py":
            _write_output(
                command,
                {
                    "status": "passed",
                    "interaction": {
                        "level": "L0_local_replay_lab",
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
        replay_lab_json=tmp_path / "replay.json",
        replay_lab_md=tmp_path / "replay.md",
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
        post_revision_replay_review_json=tmp_path / "post-revision-review.json",
        post_revision_replay_review_md=tmp_path / "post-revision-review.md",
        opportunity_decision_loop_json=tmp_path / "opportunity-decision-loop.json",
        opportunity_decision_loop_md=tmp_path / "opportunity-decision-loop.md",
        btpc_l2_shadow_fact_quality_review_json=tmp_path / "btpc-fact-review.json",
        btpc_l2_shadow_fact_quality_review_md=tmp_path / "btpc-fact-review.md",
        btpc_local_fact_proxy_review_json=tmp_path / "btpc-proxy-review.json",
        btpc_local_fact_proxy_review_md=tmp_path / "btpc-proxy-review.md",
        btpc_proxy_replay_quality_review_json=tmp_path / "btpc-proxy-replay.json",
        btpc_proxy_replay_quality_review_md=tmp_path / "btpc-proxy-replay.md",
        btpc_l2_keep_revise_fact_source_decision_json=tmp_path
        / "btpc-l2-decision.json",
        btpc_l2_keep_revise_fact_source_decision_md=tmp_path
        / "btpc-l2-decision.md",
        btpc_live_derivatives_fact_source_mapping_json=tmp_path
        / "btpc-live-source-mapping.json",
        btpc_live_derivatives_fact_source_mapping_md=tmp_path
        / "btpc-live-source-mapping.md",
        btpc_classifier_rule_review_json=tmp_path / "btpc-classifier-rule.json",
        btpc_classifier_rule_review_md=tmp_path / "btpc-classifier-rule.md",
        strategygroup_decision_ledger_json=tmp_path / "decision-ledger.json",
        strategygroup_decision_ledger_md=tmp_path / "decision-ledger.md",
        strategygroup_quality_wave_json=tmp_path / "quality-wave.json",
        strategygroup_quality_wave_md=tmp_path / "quality-wave.md",
        strategygroup_handoff_boundary_closure_json=tmp_path
        / "handoff-boundary.json",
        strategygroup_handoff_boundary_closure_md=tmp_path
        / "handoff-boundary.md",
        strategygroup_btpc_fact_classifier_guard_json=tmp_path
        / "btpc-guard.json",
        strategygroup_btpc_fact_classifier_guard_md=tmp_path
        / "btpc-guard.md",
        strategygroup_lifecycle_rehearsal_json=tmp_path / "lifecycle.json",
        strategygroup_lifecycle_rehearsal_md=tmp_path / "lifecycle.md",
        strategygroup_pre_live_rehearsal_readiness_json=tmp_path
        / "pre-live-readiness.json",
        strategygroup_pre_live_rehearsal_readiness_md=tmp_path
        / "pre-live-readiness.md",
        strategygroup_live_submit_readiness_bridge_json=tmp_path
        / "live-submit-bridge.json",
        strategygroup_live_submit_readiness_bridge_md=tmp_path
        / "live-submit-bridge.md",
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
        closure_result = _maybe_write_strategygroup_closure_step(script, command)
        if closure_result is not None:
            return closure_result
        if script == "build_strategygroup_post_revision_replay_review.py":
            _write_passed_post_revision_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_opportunity_decision_loop.py":
            _write_ready_opportunity_decision_loop(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_l2_shadow_fact_quality_review.py":
            _write_ready_btpc_fact_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_local_fact_proxy_review.py":
            _write_ready_btpc_local_fact_proxy_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_proxy_replay_quality_review.py":
            _write_ready_btpc_proxy_replay_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_l2_keep_revise_fact_source_decision.py"
        ):
            _write_ready_btpc_l2_keep_revise_fact_source_decision(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_live_derivatives_fact_source_mapping.py"
        ):
            _write_ready_btpc_live_derivatives_fact_source_mapping(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_classifier_rule_review.py":
            _write_ready_btpc_classifier_rule_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_decision_ledger.py":
            _write_ready_strategygroup_decision_ledger(command)
            return subprocess.CompletedProcess(command, 0, "", "")
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

        if script == "run_strategygroup_runtime_replay_lab.py":
            _write_output(
                command,
                {
                    "status": "passed",
                    "interaction": {
                        "level": "L0_local_replay_lab",
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
        replay_lab_json=tmp_path / "replay.json",
        replay_lab_md=tmp_path / "replay.md",
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
        post_revision_replay_review_json=tmp_path / "post-revision-review.json",
        post_revision_replay_review_md=tmp_path / "post-revision-review.md",
        opportunity_decision_loop_json=tmp_path / "opportunity-decision-loop.json",
        opportunity_decision_loop_md=tmp_path / "opportunity-decision-loop.md",
        btpc_l2_shadow_fact_quality_review_json=tmp_path / "btpc-fact-review.json",
        btpc_l2_shadow_fact_quality_review_md=tmp_path / "btpc-fact-review.md",
        btpc_local_fact_proxy_review_json=tmp_path / "btpc-proxy-review.json",
        btpc_local_fact_proxy_review_md=tmp_path / "btpc-proxy-review.md",
        btpc_proxy_replay_quality_review_json=tmp_path / "btpc-proxy-replay.json",
        btpc_proxy_replay_quality_review_md=tmp_path / "btpc-proxy-replay.md",
        btpc_l2_keep_revise_fact_source_decision_json=tmp_path
        / "btpc-l2-decision.json",
        btpc_l2_keep_revise_fact_source_decision_md=tmp_path
        / "btpc-l2-decision.md",
        btpc_live_derivatives_fact_source_mapping_json=tmp_path
        / "btpc-live-source-mapping.json",
        btpc_live_derivatives_fact_source_mapping_md=tmp_path
        / "btpc-live-source-mapping.md",
        btpc_classifier_rule_review_json=tmp_path / "btpc-classifier-rule.json",
        btpc_classifier_rule_review_md=tmp_path / "btpc-classifier-rule.md",
        strategygroup_decision_ledger_json=tmp_path / "decision-ledger.json",
        strategygroup_decision_ledger_md=tmp_path / "decision-ledger.md",
        strategygroup_quality_wave_json=tmp_path / "quality-wave.json",
        strategygroup_quality_wave_md=tmp_path / "quality-wave.md",
        strategygroup_handoff_boundary_closure_json=tmp_path
        / "handoff-boundary.json",
        strategygroup_handoff_boundary_closure_md=tmp_path
        / "handoff-boundary.md",
        strategygroup_btpc_fact_classifier_guard_json=tmp_path
        / "btpc-guard.json",
        strategygroup_btpc_fact_classifier_guard_md=tmp_path
        / "btpc-guard.md",
        strategygroup_lifecycle_rehearsal_json=tmp_path / "lifecycle.json",
        strategygroup_lifecycle_rehearsal_md=tmp_path / "lifecycle.md",
        strategygroup_pre_live_rehearsal_readiness_json=tmp_path
        / "pre-live-readiness.json",
        strategygroup_pre_live_rehearsal_readiness_md=tmp_path
        / "pre-live-readiness.md",
        strategygroup_live_submit_readiness_bridge_json=tmp_path
        / "live-submit-bridge.json",
        strategygroup_live_submit_readiness_bridge_md=tmp_path
        / "live-submit-bridge.md",
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
        closure_result = _maybe_write_strategygroup_closure_step(script, command)
        if closure_result is not None:
            return closure_result
        if script == "build_strategygroup_post_revision_replay_review.py":
            _write_passed_post_revision_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_opportunity_decision_loop.py":
            _write_ready_opportunity_decision_loop(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_l2_shadow_fact_quality_review.py":
            _write_ready_btpc_fact_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_local_fact_proxy_review.py":
            _write_ready_btpc_local_fact_proxy_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_proxy_replay_quality_review.py":
            _write_ready_btpc_proxy_replay_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_l2_keep_revise_fact_source_decision.py"
        ):
            _write_ready_btpc_l2_keep_revise_fact_source_decision(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_live_derivatives_fact_source_mapping.py"
        ):
            _write_ready_btpc_live_derivatives_fact_source_mapping(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_classifier_rule_review.py":
            _write_ready_btpc_classifier_rule_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_decision_ledger.py":
            _write_ready_strategygroup_decision_ledger(command)
            return subprocess.CompletedProcess(command, 0, "", "")
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

        if script == "run_strategygroup_runtime_replay_lab.py":
            _write_output(
                command,
                {
                    "status": "passed",
                    "interaction": {
                        "level": "L0_local_replay_lab",
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
        replay_lab_json=tmp_path / "replay.json",
        replay_lab_md=tmp_path / "replay.md",
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
        post_revision_replay_review_json=tmp_path / "post-revision-review.json",
        post_revision_replay_review_md=tmp_path / "post-revision-review.md",
        opportunity_decision_loop_json=tmp_path / "opportunity-decision-loop.json",
        opportunity_decision_loop_md=tmp_path / "opportunity-decision-loop.md",
        btpc_l2_shadow_fact_quality_review_json=tmp_path / "btpc-fact-review.json",
        btpc_l2_shadow_fact_quality_review_md=tmp_path / "btpc-fact-review.md",
        btpc_local_fact_proxy_review_json=tmp_path / "btpc-proxy-review.json",
        btpc_local_fact_proxy_review_md=tmp_path / "btpc-proxy-review.md",
        btpc_proxy_replay_quality_review_json=tmp_path / "btpc-proxy-replay.json",
        btpc_proxy_replay_quality_review_md=tmp_path / "btpc-proxy-replay.md",
        btpc_l2_keep_revise_fact_source_decision_json=tmp_path
        / "btpc-l2-decision.json",
        btpc_l2_keep_revise_fact_source_decision_md=tmp_path
        / "btpc-l2-decision.md",
        btpc_live_derivatives_fact_source_mapping_json=tmp_path
        / "btpc-live-source-mapping.json",
        btpc_live_derivatives_fact_source_mapping_md=tmp_path
        / "btpc-live-source-mapping.md",
        btpc_classifier_rule_review_json=tmp_path / "btpc-classifier-rule.json",
        btpc_classifier_rule_review_md=tmp_path / "btpc-classifier-rule.md",
        strategygroup_decision_ledger_json=tmp_path / "decision-ledger.json",
        strategygroup_decision_ledger_md=tmp_path / "decision-ledger.md",
        strategygroup_quality_wave_json=tmp_path / "quality-wave.json",
        strategygroup_quality_wave_md=tmp_path / "quality-wave.md",
        strategygroup_handoff_boundary_closure_json=tmp_path
        / "handoff-boundary.json",
        strategygroup_handoff_boundary_closure_md=tmp_path
        / "handoff-boundary.md",
        strategygroup_btpc_fact_classifier_guard_json=tmp_path
        / "btpc-guard.json",
        strategygroup_btpc_fact_classifier_guard_md=tmp_path
        / "btpc-guard.md",
        strategygroup_lifecycle_rehearsal_json=tmp_path / "lifecycle.json",
        strategygroup_lifecycle_rehearsal_md=tmp_path / "lifecycle.md",
        strategygroup_pre_live_rehearsal_readiness_json=tmp_path
        / "pre-live-readiness.json",
        strategygroup_pre_live_rehearsal_readiness_md=tmp_path
        / "pre-live-readiness.md",
        strategygroup_live_submit_readiness_bridge_json=tmp_path
        / "live-submit-bridge.json",
        strategygroup_live_submit_readiness_bridge_md=tmp_path
        / "live-submit-bridge.md",
        command_runner=fake_runner,
    )

    assert report["status"] == "waiting_for_market"
    assert report["checks"]["blockers"] == []
    assert report["checks"]["non_market_gaps"] == []
    assert report["interaction"]["remote_interaction_count"] == 0
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["interaction"]["approaches_real_order"] is False


def test_local_monitor_sequence_clears_expansion_gap_when_decision_loop_ready() -> None:
    module = _load_module()

    gap = module._expansion_review_non_market_gap(
        {"status": "review_needed_broader_observe_only_would_enter"},
        {"status": "l2_readiness_review_all_blocked"},
        {"status": "l2_intake_dry_run_no_candidates"},
        {"status": "l2_tier_policy_review_no_candidates"},
        {"status": "decision_loop_ready"},
    )

    assert gap is None

    status = module._sequence_status(
        steps=[],
        packets={
            "daily_check": {"status": "waiting_for_market"},
            "goal_progress": {"status": "waiting_for_market"},
            "completion_audit": {"status": "not_complete_waiting_for_market"},
            "signal_coverage": {"status": "mainline_no_signal_broader_would_enter"},
            "signal_coverage_expansion_review": {
                "status": "review_needed_broader_observe_only_would_enter"
            },
            "l2_readiness_review": {"status": "l2_readiness_review_all_blocked"},
            "l2_intake_dry_run": {"status": "l2_intake_dry_run_no_candidates"},
            "l2_tier_policy_review": {"status": "l2_tier_policy_review_no_candidates"},
            "opportunity_decision_loop": {"status": "decision_loop_ready"},
        },
    )

    assert status == "waiting_for_market"


def test_local_monitor_sequence_treats_low_priority_would_enter_as_waiting() -> None:
    module = _load_module()

    status = module._sequence_status(
        steps=[],
        packets={
            "daily_check": {"status": "waiting_for_market"},
            "goal_progress": {"status": "waiting_for_market"},
            "completion_audit": {"status": "not_complete_waiting_for_market"},
            "signal_coverage": {
                "status": "mainline_no_signal_low_priority_broader_would_enter"
            },
            "signal_coverage_expansion_review": {
                "status": "low_priority_observe_only_would_enter_parked"
            },
            "l2_readiness_review": {"status": "l2_readiness_review_all_blocked"},
            "l2_intake_dry_run": {"status": "l2_intake_dry_run_no_candidates"},
            "l2_tier_policy_review": {"status": "l2_tier_policy_review_no_candidates"},
            "opportunity_decision_loop": {"status": "decision_loop_ready"},
        },
    )

    assert status == "waiting_for_market"
