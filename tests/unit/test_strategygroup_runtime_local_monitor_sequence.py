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


def _write_waiting_brf2_candidate_packet(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "brf2_non_executing_candidate_packet_waiting_for_fresh_signal",
            "strategy_group_id": "BRF2-001",
            "candidate_packet_ready": False,
            "candidate_packet": {
                "candidate_packet_type": "brf2_non_executing_short_signal_candidate",
                "signal_state": "fact_input_missing",
            },
            "first_blocker": {
                "class": "brf2_watcher_fact_input_missing",
                "owner": "engineering",
                "next_action": "attach_brf2_watcher_fact_input_producer",
            },
            "next_runtime_step": "attach_brf2_watcher_fact_input_producer",
            "checks": {
                "actionable_now": False,
                "real_order_authority": False,
            },
            "interaction": {
                "level": "L0_local_brf2_non_executing_candidate_packet",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
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
                "role_review_is_decision_support_only": True,
                "no_action_attribution_queue_recorded": True,
                "real_order_scope_change_recommended": False,
                "l4_promotion_recommended": False,
            },
            "observation_layer": {
                "p0_state": "waiting_for_executable_fresh_signal",
                "p0_5_state": "observation_active",
                "mainline_ready_signal_count": 0,
                "broader_would_enter_count": 1,
                "broader_actionable_would_enter_count": 0,
                "high_priority_no_action_count": 4,
                "latest_observe_only_would_enter": {
                    "strategy_group_id": "RBR-001",
                    "symbol": "ADA/USDT:USDT",
                    "side": "short",
                    "confidence": "0.57",
                    "not_live_signal": True,
                },
                "actionable_now": False,
                "real_order_authority": False,
            },
            "role_review_rows": [
                {
                    "source_observation_strategy_group_id": "RBR-001",
                    "source_observation_symbol": "ADA/USDT:USDT",
                    "source_observation_side": "short",
                    "linked_intake_strategy_group_id": "RBR2-001",
                    "next_checkpoint": (
                        "RBR_RBR2_role_review_range_detector_classifier_merge_note"
                    ),
                }
            ],
            "no_action_attribution_queue": [
                {
                    "strategy_group_id": "BRF-001",
                    "attribution_class": "market_structure_or_path_risk",
                },
                {
                    "strategy_group_id": "BTPC-001",
                    "attribution_class": "fact_source_or_freshness",
                },
                {
                    "strategy_group_id": "LSR-001",
                    "attribution_class": "side_specific_rewrite",
                },
                {
                    "strategy_group_id": "VCB-001",
                    "attribution_class": "classifier_or_threshold",
                },
            ],
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


def _write_ready_tradeability_verdict(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.strategygroup_tradeability_verdict.v1",
            "scope": "strategygroup_tradeability_verdict_read_model",
            "status": "tradeability_verdict_ready",
            "generated_at_utc": "2026-06-23T00:00:00+00:00",
            "summary": {
                "row_count": 3,
                "tradable_now_count": 0,
                "actionable_now_count": 0,
                "real_order_authority_count": 0,
                "owner_first_blocker_count": 0,
                "engineering_first_blocker_count": 1,
                "market_first_blocker_count": 2,
                "runtime_first_blocker_count": 0,
                "strategy_review_first_blocker_count": 1,
                "top_strategy_group_id": "BRF2-001",
                "top_verdict": "not_tradable_facts",
                "top_first_blocker_class": "brf2_watcher_fact_input_missing",
                "top_next_action": "attach_brf2_watcher_fact_input_producer",
            },
            "verdict_rows": [
                {
                    "strategy_group_id": "BRF2-001",
                    "stage": "armed_observation",
                    "verdict": "not_tradable_facts",
                    "first_blocker_class": "brf2_watcher_fact_input_missing",
                    "blocker_owner": "engineering",
                    "next_action": "attach_brf2_watcher_fact_input_producer",
                    "after_next_state": "armed_observation",
                    "actionable_now": False,
                    "real_order_authority": False,
                },
                {
                    "strategy_group_id": "MPG-001",
                    "stage": "armed_observation",
                    "verdict": "not_tradable_market_wait",
                    "first_blocker_class": "fresh_executable_signal_absent",
                    "blocker_owner": "market",
                    "next_action": "continue_armed_observation_until_fresh_signal",
                    "after_next_state": "live_submit_ready",
                    "actionable_now": False,
                    "real_order_authority": False,
                },
                {
                    "strategy_group_id": "SOR-001",
                    "stage": "armed_observation",
                    "verdict": "not_tradable_market_wait",
                    "first_blocker_class": "fresh_session_range_signal_absent",
                    "blocker_owner": "market",
                    "next_action": "continue_session_range_armed_observation_until_fresh_signal",
                    "after_next_state": "live_submit_ready",
                    "actionable_now": False,
                    "real_order_authority": False,
                },
            ],
            "owner_summary": {
                "state": "交易资格已判定",
                "top_strategy_group_id": "BRF2-001",
                "top_verdict": "not_tradable_facts",
                "top_first_blocker": "brf2_watcher_fact_input_missing",
                "owner_policy_blocker_present": False,
                "owner_intervention_required": False,
                "real_order_authority": False,
                "actionable_now": False,
            },
            "checks": {
                "row_count": 3,
                "one_current_verdict_per_strategy_group": True,
                "owner_policy_blocker_present": False,
                "owner_decision_required": False,
                "row_count_matches_verdict_rows": True,
                "tradable_now_rows_have_authority": True,
                "authority_rows_are_tradable_now": True,
                "tradable_now_scoped_to_live_submit": True,
                "market_wait_only_after_admission": True,
                "actionable_now_count": 0,
                "real_order_authority_count": 0,
            },
            "interaction": {
                "level": "L0_local_tradeability_verdict",
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


def _write_ready_three_strategy_live_trial_portfolio(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.three_strategy_live_trial_portfolio.v1",
            "scope": "three_strategy_live_trial_portfolio_read_model",
            "status": "three_strategy_live_trial_portfolio_ready",
            "generated_at_utc": "2026-06-23T00:00:00+00:00",
            "portfolio_goal": "at_least_3_live_trial_strategygroups",
            "selected_strategy_groups": ["MPG-001", "BRF2-001", "SOR-001"],
            "seat_count": 3,
            "objective_met": True,
            "seat_readiness": {
                "MPG-001": {
                    "stage": "armed_observation",
                    "first_blocker": {
                        "verdict": "not_tradable_market_wait",
                        "first_blocker_class": "fresh_executable_signal_absent",
                        "blocker_owner": "market",
                        "next_action": "continue_armed_observation_until_fresh_signal",
                    },
                },
                "BRF2-001": {
                    "stage": "armed_observation",
                    "required_facts_mapping_ready": True,
                    "runtime_readiness": {
                        "armed_observation_ready": False,
                        "blocked_by": "brf2_watcher_fact_input_missing",
                        "tiny_live_ready": False,
                        "live_submit_ready": False,
                    },
                    "first_blocker": {
                        "verdict": "not_tradable_facts",
                        "first_blocker_class": "brf2_watcher_fact_input_missing",
                        "blocker_owner": "engineering",
                        "next_action": "attach_brf2_watcher_fact_input_producer",
                    },
                },
                "SOR-001": {
                    "stage": "armed_observation_ready",
                    "first_blocker": {
                        "verdict": "not_tradable_market_wait",
                        "first_blocker_class": "fresh_session_range_signal_absent",
                        "blocker_owner": "market",
                        "next_action": "continue_session_range_armed_observation_until_fresh_signal",
                    },
                },
            },
            "next_engineering_bottleneck": {
                "MPG-001": "fresh_signal_wait",
                "BRF2-001": "brf2_watcher_fact_input_missing",
                "SOR-001": "fresh_signal_wait",
            },
            "checks": {
                "seat_count": 3,
                "at_least_three_seats": True,
                "objective_met": True,
                "actionable_now": False,
                "real_order_authority": False,
            },
            "interaction": {
                "level": "L0_local_three_strategy_live_trial_portfolio",
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


def _write_ready_brf2_required_facts_mapping(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.brf2_required_facts_mapping.v1",
            "scope": "brf2_required_facts_mapping_for_armed_observation",
            "status": "brf2_required_facts_mapping_ready",
            "generated_at_utc": "2026-06-23T00:00:00+00:00",
            "strategy_group_id": "BRF2-001",
            "current_stage": "admitted_trial_asset",
            "after_next_state": "armed_observation",
            "required_facts_mapping_ready": True,
            "fresh_signal_rule": {
                "signal_id": "brf2_short_rally_failure_fresh_signal_v1",
                "side": "short",
            },
            "required_fact_keys": [
                "closed_1h_ohlcv",
                "closed_5m_ohlcv",
                "rally_context",
                "rally_failure_trigger_state",
                "short_squeeze_risk_state",
                "strong_reclaim_disable_state",
                "liquidity_downshift_state",
                "spread_liquidity_state",
            ],
            "disable_fact_keys": [
                "short_squeeze_risk_state",
                "strong_reclaim_disable_state",
                "rally_extension_invalidates_failure_state",
                "liquidity_downshift_state",
                "spread_liquidity_state",
            ],
            "first_blocker_after_mapping": "fresh_brf2_short_signal_absent",
            "next_action": "continue_brf2_armed_observation_until_fresh_signal",
            "checks": {
                "required_facts_mapping_ready": True,
                "required_fact_count": 8,
                "disable_fact_count": 5,
                "actionable_now": False,
                "real_order_authority": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "interaction": {
                "level": "L0_local_brf2_required_facts_mapping",
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


def _write_missing_brf2_runtime_signal_facts(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.brf2_runtime_signal_facts.v1",
            "scope": "brf2_runtime_signal_facts_read_model",
            "status": "brf2_runtime_signal_facts_missing_watcher_input",
            "generated_at_utc": "2026-06-23T00:00:00+00:00",
            "strategy_group_id": "BRF2-001",
            "fact_input_present": False,
            "watcher_tick_present": False,
            "source_status": "missing",
            "source_path": "output/runtime-monitor/latest-live-market-strategy-preview.json",
            "facts": {},
            "first_blocker": {
                "class": "brf2_watcher_fact_input_missing",
                "owner": "engineering",
                "next_action": "attach_brf2_watcher_fact_input_producer",
            },
            "next_action": "attach_brf2_watcher_fact_input_producer",
            "checks": {
                "fact_input_present": False,
                "watcher_tick_present": False,
                "missing_watcher_input": True,
                "actionable_now": False,
                "real_order_authority": False,
            },
            "interaction": {
                "level": "L0_local_brf2_runtime_signal_facts",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
        },
    )


def _expected_brf2_fact_input_gap() -> dict:
    return {
        "class": "missing_fact",
        "source": "brf2_runtime_signal_facts",
        "strategy_group_id": "BRF2-001",
        "gap": "brf2_watcher_fact_input_missing",
        "owner": "engineering",
        "next_action": "attach_brf2_watcher_fact_input_producer",
        "requirement": "BRF2 armed observation must have watcher fact input before it can be classified as market wait",
        "missing_or_false": [
            "brf2_runtime_signal_fact_input_present",
            "brf2_runtime_signal_watcher_tick_present",
        ],
    }


def _write_ready_brf2_runtime_signal_capture(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.brf2_runtime_signal_capture.v1",
            "scope": "brf2_runtime_signal_capture_read_model",
            "status": "brf2_runtime_signal_capture_ready",
            "generated_at_utc": "2026-06-23T00:00:00+00:00",
            "strategy_group_id": "BRF2-001",
            "fact_input_status": "brf2_runtime_signal_facts_missing_watcher_input",
            "fact_input_present": False,
            "watcher_tick_present": False,
            "watcher_scope": {
                "strategy_group_id": "BRF2-001",
                "signal_id": "brf2_short_rally_failure_fresh_signal_v1",
                "side_scope": ["short"],
                "timeframes": ["1h_closed", "5m_closed"],
            },
            "signal_detector_preview": {
                "detector_ready": True,
                "fact_input_present": False,
                "watcher_tick_present": False,
                "fact_input_status": "brf2_runtime_signal_facts_missing_watcher_input",
                "fresh_signal_present": False,
                "current_signal_state": "fact_input_missing",
                "first_blocker_class": "brf2_watcher_fact_input_missing",
                "first_blocker_owner": "engineering",
                "next_action": "attach_brf2_watcher_fact_input_producer",
                "missing_required_fact_keys": ["closed_1h_ohlcv"],
                "active_disable_fact_keys": [],
            },
            "no_action_attribution": {
                "attribution_ready": True,
                "strategy_group_id": "BRF2-001",
                "reason": "brf2_watcher_fact_input_missing",
                "blocked_fact_count": 1,
                "blocker_owner": "engineering",
            },
            "candidate_packet_shape": {
                "candidate_packet_ready": False,
                "candidate_packet_type": "brf2_non_executing_short_signal_candidate",
            },
            "checks": {
                "mapping_ready": True,
                "fact_input_present": False,
                "watcher_tick_present": False,
                "fact_input_status_ready": False,
                "watcher_scope_ready": True,
                "signal_detector_preview_ready": True,
                "no_action_attribution_ready": True,
                "candidate_packet_shape_ready": True,
                "fresh_signal_present": False,
                "missing_required_fact_count": 1,
                "active_disable_fact_count": 0,
                "actionable_now": False,
                "real_order_authority": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "interaction": {
                "level": "L0_local_brf2_runtime_signal_capture",
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


def _write_ready_trial_asset_admission_proposal(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.strategygroup_trial_asset_admission_proposal.v1",
            "scope": "strategygroup_trial_asset_admission_proposal",
            "status": "trial_asset_admission_proposal_ready",
            "generated_at_utc": "2026-06-23T00:00:00+00:00",
            "proposal": {
                "strategy_group_id": "BRF2-001",
                "current_stage": "tiny_live_intake_candidate",
                "proposed_stage": "admitted_trial_asset",
                "owner_policy_required": False,
                "owner_policy_recorded": True,
                "owner_policy_scope_missing": False,
                "next_action": (
                    "close_brf2_required_facts_mapping_for_armed_observation"
                ),
                "after_next_state": "armed_observation",
                "actionable_now": False,
                "real_order_authority": False,
            },
            "owner_policy_checkpoint": {
                "owner_policy_required": False,
                "owner_policy_recorded": True,
                "owner_policy_scope_missing": False,
                "owner_policy_fields": [
                    "capital_scope",
                    "max_notional",
                    "valid_until",
                    "slippage_limit",
                    "trial_identity",
                ],
                "owner_decision_required_now": False,
                "owner_intervention_required": False,
            },
            "checks": {
                "proposal_generated": True,
                "owner_policy_required": False,
                "owner_policy_recorded": True,
                "owner_policy_scope_missing": False,
                "owner_decision_required": False,
                "actionable_now": False,
                "real_order_authority": False,
            },
            "interaction": {
                "level": "L0_local_trial_asset_admission_proposal",
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


def _write_ready_brf2_owner_trial_policy_scope(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.brf2_owner_trial_policy_scope.v0",
            "scope": "final_owned_brf2_owner_trial_policy_scope_non_executing",
            "status": "brf2_owner_trial_policy_scope_recorded",
            "generated_at_utc": "2026-06-23T00:00:00+00:00",
            "brf2_policy_scope_recorded": True,
            "owner_policy_recorded": True,
            "owner_policy_scope_missing": False,
            "brf2_stage_after_policy": "admitted_trial_asset",
            "brf2_new_first_blocker": "required_facts_mapping_gap",
            "brf2_next_action": (
                "close_brf2_required_facts_mapping_for_armed_observation"
            ),
            "policy": {
                "strategy_group_id": "BRF2-001",
                "trial_identity": "BRF2_TINY_SHORT_TRIAL_30U_V0",
                "capital_scope": {
                    "type": "isolated_subaccount_full_allocation",
                    "amount": "30",
                    "currency": "USDT",
                    "loss_capable": True,
                },
                "side_scope": ["short"],
                "symbol_scope": "brf2_research_supported_symbols_only",
                "leverage_scenario": "5x_scenario_not_authority",
                "max_notional": {"amount": "150", "currency": "USDT"},
                "attempt_cap": 3,
                "loss_unit": {"amount": "10", "currency": "USDT"},
            },
            "interaction": {
                "level": "L0_local_brf2_owner_trial_policy_scope",
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


def _write_ready_strategygroup_portfolio_board(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "portfolio_board_ready",
            "portfolio_summary": {
                "portfolio_row_count": 10,
                "trial_candidate_count": 5,
                "engineering_continuation_count": 9,
                "owner_policy_decision_count": 4,
            },
            "trial_candidate_pool": {
                "candidate_count": 5,
                "eligible_now_count": 1,
                "actionable_now_count": 0,
                "live_permission_change_count": 0,
            },
            "owner_progress_projection": {
                "owner_intervention_required": False,
            },
            "interaction": {
                "level": "L0_local_strategygroup_portfolio_board",
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
                "registry_authority_changed": False,
                "tier_policy_changed": False,
                "live_profile_changed": False,
                "order_sizing_changed": False,
            },
        },
    )


def _write_ready_capital_trial_bridge(command: list[str]) -> None:
    assert "--research-intake-review-json" in command
    _write_output(
        command,
        {
            "status": "capital_trial_readiness_bridge_ready",
            "capital_trial_summary": {
                "eligibility_row_count": 7,
                "non_mpg_trial_candidate_count": 7,
                "selected_non_mpg_strategy_group_id": "BRF2-001",
                "selected_short_strategy_group_id": "BRF2-001",
                "short_candidate_trade_count": 1,
                "selected_candidate_status": (
                    "short_candidate_trade_packet_pending_owner_policy"
                ),
                "trial_packet_generated": True,
                "actionable_now_count": 0,
                "live_permission_change_count": 0,
                "real_order_authority_count": 0,
                "owner_policy_checkpoint_count": 1,
            },
            "trial_packet_v0": {
                "schema": "brc.strategygroup_capital_trial_packet.v0",
                "strategy_group_id": "BRF2-001",
                "decision": "promote",
                "reason": "promote_to_tiny_live_intake_candidate_not_live_ready",
                "promotion_scope": "intake_only",
                "promotion_target": "paper_observation_or_candidate_trade_packet",
                "tiny_live_ready": False,
                "next_checkpoint": "BRF2-001_tiny_live_intake_candidate_packet",
                "side_scope": ["short"],
                "actionable_now": False,
                "live_permission_change": False,
                "real_order_authority": False,
            },
            "selected_non_mpg_trial_candidate": {
                "strategy_group_id": "BRF2-001",
                "decision": "promote",
                "reason": "promote_to_tiny_live_intake_candidate_not_live_ready",
                "promotion_scope": "intake_only",
                "promotion_target": "paper_observation_or_candidate_trade_packet",
                "tiny_live_ready": False,
                "next_checkpoint": "BRF2-001_tiny_live_intake_candidate_packet",
                "side_scope": ["short"],
            },
            "owner_policy_checkpoint": {
                "runtime_owner_intervention_required": False,
            },
            "interaction": {
                "level": "L0_local_capital_trial_readiness_bridge",
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
                "registry_authority_changed": False,
                "tier_policy_changed": False,
                "live_profile_changed": False,
                "order_sizing_changed": False,
            },
        },
    )


def _write_ready_strategygroup_research_intake_review(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "research_intake_review_ready",
            "summary": {
                "candidate_count": 2,
                "paper_observation_admission_candidate_count": 1,
                "role_only_intake_candidate_count": 1,
                "tiny_live_ready_count": 0,
                "actionable_now_count": 0,
                "real_order_authority_count": 0,
            },
            "candidate_rows": [
                {
                    "strategy_group_id": "BRF2-001",
                    "main_control_intake_position": (
                        "paper_observation_admission_candidate"
                    ),
                    "actionable_now": False,
                    "real_order_authority": False,
                },
                {
                    "strategy_group_id": "RBR2-001",
                    "main_control_intake_position": "role_only_intake_candidate",
                    "actionable_now": False,
                    "real_order_authority": False,
                },
            ],
            "decision_ledger_rows": [
                {
                    "strategy_group_id": "BRF2-001",
                    "tier": "unknown",
                    "opportunity_type": "research_intake",
                    "decision": "promote",
                    "required_next_evidence": "paper_observation_packet_shape",
                    "authority_boundary": (
                        "research_intake_review_only; real_order_authority=false"
                    ),
                    "next_checkpoint": (
                        "BRF2-001_paper_observation_admission_packet"
                    ),
                },
                {
                    "strategy_group_id": "RBR2-001",
                    "tier": "unknown",
                    "opportunity_type": "research_intake",
                    "decision": "keep_observing",
                    "required_next_evidence": "range_detector_facts",
                    "authority_boundary": (
                        "research_intake_review_only; real_order_authority=false"
                    ),
                    "next_checkpoint": (
                        "RBR2-001_role_only_range_detector_classifier_merge_note"
                    ),
                },
            ],
            "interaction": {
                "level": "L0_local_research_intake_review",
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
                "tier_policy_changed": False,
                "live_profile_changed": False,
            },
        },
    )


def _write_passed_runtime_dry_run_audit_chain(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.runtime_dry_run_audit_chain.v1",
            "scope": "runtime_dry_run_audit_chain",
            "status": "passed",
            "scenario_count": 14,
            "checks": {
                "dangerous_effects_absent": True,
                "required_scenarios_present": True,
                "all_scenarios_passed": True,
            },
            "interaction": {
                "level": "L0_local_runtime_dry_run_audit_chain",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )


def _maybe_write_strategygroup_closure_step(
    script: str, command: list[str]
) -> subprocess.CompletedProcess[str] | None:
    if script == "runtime_dry_run_audit_chain.py":
        _write_passed_runtime_dry_run_audit_chain(command)
        return subprocess.CompletedProcess(command, 0, "", "")
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
    if script == "build_strategygroup_three_strategy_live_trial_portfolio.py":
        _write_ready_three_strategy_live_trial_portfolio(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_tradeability_verdict.py":
        _write_ready_tradeability_verdict(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_brf2_owner_trial_policy_scope.py":
        _write_ready_brf2_owner_trial_policy_scope(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_brf2_required_facts_mapping.py":
        _write_ready_brf2_required_facts_mapping(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_brf2_runtime_signal_facts.py":
        _write_missing_brf2_runtime_signal_facts(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_brf2_runtime_signal_capture.py":
        _write_ready_brf2_runtime_signal_capture(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_portfolio_board.py":
        _write_ready_strategygroup_portfolio_board(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_capital_trial_readiness_bridge.py":
        _write_ready_capital_trial_bridge(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_trial_asset_admission_proposal.py":
        _write_ready_trial_asset_admission_proposal(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_research_intake_review.py":
        _write_ready_strategygroup_research_intake_review(command)
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
        elif script == "build_brf2_non_executing_candidate_packet.py":
            _write_output(
                command,
                {
                    "status": (
                        "brf2_non_executing_candidate_packet_waiting_for_fresh_signal"
                    ),
                    "strategy_group_id": "BRF2-001",
                    "candidate_packet_ready": False,
                    "candidate_packet": {
                        "candidate_packet_type": (
                            "brf2_non_executing_short_signal_candidate"
                        ),
                        "signal_state": "fresh_signal_absent",
                    },
                    "first_blocker": {
                        "class": "fresh_brf2_short_signal_absent",
                        "owner": "market",
                        "next_action": (
                            "continue_brf2_armed_observation_until_fresh_signal"
                        ),
                    },
                    "next_runtime_step": (
                        "continue_brf2_armed_observation_until_fresh_signal"
                    ),
                    "checks": {
                        "actionable_now": False,
                        "real_order_authority": False,
                    },
                    "interaction": {
                        "level": "L0_local_brf2_non_executing_candidate_packet",
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
        strategygroup_portfolio_board_json=tmp_path / "portfolio-board.json",
        strategygroup_portfolio_board_md=tmp_path / "portfolio-board.md",
        strategygroup_trial_candidate_pool_md=tmp_path / "trial-pool.md",
        strategygroup_capital_trial_readiness_bridge_json=tmp_path
        / "capital-trial-bridge.json",
        strategygroup_capital_trial_readiness_bridge_md=tmp_path
        / "capital-trial-bridge.md",
        strategygroup_capital_trial_packet_json=tmp_path / "trial-packet.json",
        strategygroup_capital_trial_packet_md=tmp_path / "trial-packet.md",
        strategygroup_research_intake_review_json=tmp_path
        / "research-intake-review.json",
        strategygroup_research_intake_review_md=tmp_path
        / "research-intake-review.md",
        strategygroup_trial_asset_admission_proposal_json=tmp_path
        / "trial-admission-proposal.json",
        strategygroup_trial_asset_admission_proposal_md=tmp_path
        / "trial-admission-proposal.md",
        brf2_owner_trial_policy_scope_json=tmp_path / "brf2-policy.json",
        brf2_owner_trial_policy_scope_md=tmp_path / "brf2-policy.md",
        brf2_required_facts_mapping_json=tmp_path / "brf2-required-facts.json",
        brf2_required_facts_mapping_md=tmp_path / "brf2-required-facts.md",
        brf2_runtime_signal_facts_json=tmp_path / "brf2-signal-facts.json",
        brf2_runtime_signal_facts_md=tmp_path / "brf2-signal-facts.md",
        brf2_runtime_signal_capture_json=tmp_path / "brf2-signal-capture.json",
        brf2_runtime_signal_capture_md=tmp_path / "brf2-signal-capture.md",
        brf2_non_executing_candidate_packet_json=tmp_path / "brf2-candidate.json",
        brf2_non_executing_candidate_packet_md=tmp_path / "brf2-candidate.md",
        three_strategy_live_trial_portfolio_json=tmp_path
        / "three-strategy-portfolio.json",
        three_strategy_live_trial_portfolio_md=tmp_path
        / "three-strategy-portfolio.md",
        strategygroup_tradeability_verdict_json=tmp_path / "tradeability.json",
        strategygroup_tradeability_verdict_md=tmp_path / "tradeability.md",
        command_runner=fake_runner,
    )

    assert calls == [
        "run_strategygroup_runtime_daily_check.py",
        "runtime_dry_run_audit_chain.py",
        "runtime_live_cutover_readiness.py",
        "build_strategygroup_portfolio_board.py",
        "build_strategygroup_research_intake_review.py",
        "build_strategygroup_capital_trial_readiness_bridge.py",
        "build_brf2_owner_trial_policy_scope.py",
        "build_strategygroup_trial_asset_admission_proposal.py",
        "build_brf2_required_facts_mapping.py",
        "build_brf2_runtime_signal_facts.py",
        "build_brf2_runtime_signal_capture.py",
        "build_brf2_non_executing_candidate_packet.py",
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
        "build_strategygroup_three_strategy_live_trial_portfolio.py",
        "build_strategygroup_tradeability_verdict.py",
    ]
    assert len(decision_loop_commands) == 2
    assert "--btpc-proxy-replay-quality-json" not in decision_loop_commands[0]
    assert "--btpc-proxy-replay-quality-json" in decision_loop_commands[1]
    assert decision_loop_commands[1][
        decision_loop_commands[1].index("--btpc-proxy-replay-quality-json") + 1
    ] == str(tmp_path / "btpc-proxy-replay.json")
    assert report["status"] == "needs_non_market_repair"
    assert report["checks"]["blockers"] == []
    assert report["interaction"]["level"] == "L0_local_monitor_sequence"
    assert report["interaction"]["remote_interaction_count"] == 0
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["interaction"]["approaches_real_order"] is False
    assert report["strategy_research_intake"]["active"] is True
    assert report["strategy_research_intake"]["strategy_group_ids"] == [
        "BRF2-001",
        "RBR2-001",
    ]
    assert report["checks"]["research_intake_review_active"] is True
    assert report["checks"]["research_intake_candidates"] == [
        "BRF2-001",
        "RBR2-001",
    ]
    assert report["strategy_candidate_trade"]["selected_strategy_group_id"] == (
        "BRF2-001"
    )
    assert report["strategy_candidate_trade"]["selected_short_strategy_group_id"] == (
        "BRF2-001"
    )
    assert report["strategy_experiment_candidate"]["selected_strategy_group_id"] == (
        "BRF2-001"
    )
    assert report["strategy_experiment_candidate"]["decision"] == "promote"
    assert report["strategy_experiment_candidate"]["promotion_scope"] == "intake_only"
    assert report["strategy_experiment_candidate"]["tiny_live_ready"] is False
    assert report["strategy_observation_layer"]["p0_5_state"] == "observation_active"
    assert report["strategy_observation_layer"]["broader_would_enter_count"] == 1
    assert report["strategy_observation_layer"]["high_priority_no_action_count"] == 4
    assert report["strategy_observation_layer"]["latest_observe_only_would_enter"][
        "strategy_group_id"
    ] == "RBR-001"
    assert report["strategy_observation_layer"]["latest_observe_only_would_enter"][
        "symbol"
    ] == "ADA/USDT:USDT"
    assert report["strategy_observation_layer"]["selected_short_intake_candidate"] == (
        "BRF2-001"
    )
    assert report["strategy_observation_layer"]["no_action_attribution_count"] == 4
    assert report["strategy_observation_layer"]["role_review_count"] == 1
    assert report["checks"]["candidate_trade_selected_strategy_group_id"] == (
        "BRF2-001"
    )
    assert report["checks"]["p0_5_observation_state"] == "observation_active"
    assert report["checks"][
        "p0_5_latest_observe_only_would_enter_strategy_group_id"
    ] == "RBR-001"
    assert report["checks"]["p0_5_no_action_attribution_count"] == 4
    assert report["checks"]["p0_5_role_review_count"] == 1
    assert report["checks"]["short_experiment_candidate_promotion_scope"] == (
        "intake_only"
    )
    assert report["checks"]["short_experiment_candidate_tiny_live_ready"] is False
    assert report["checks"]["candidate_trade_real_order_authority"] is False
    assert report["strategy_tradeability_verdict"]["top_strategy_group_id"] == (
        "BRF2-001"
    )
    assert report["strategy_trial_asset_admission"]["status"] == (
        "trial_asset_admission_proposal_ready"
    )
    assert report["strategy_trial_asset_admission"]["strategy_group_id"] == (
        "BRF2-001"
    )
    assert report["strategy_trial_asset_admission"]["owner_policy_required"] is False
    assert report["brf2_owner_trial_policy"]["owner_policy_recorded"] is True
    assert report["brf2_owner_trial_policy"]["owner_policy_scope_missing"] is False
    assert report["brf2_required_facts_mapping"]["ready"] is True
    assert report["brf2_required_facts_mapping"]["fresh_signal_rule_id"] == (
        "brf2_short_rally_failure_fresh_signal_v1"
    )
    assert report["brf2_required_facts_mapping"]["after_next_state"] == (
        "armed_observation"
    )
    assert report["checks"]["brf2_owner_policy_recorded"] is True
    assert report["checks"]["brf2_owner_policy_scope_missing"] is False
    assert report["checks"]["brf2_stage_after_policy"] == "admitted_trial_asset"
    assert report["checks"]["brf2_new_first_blocker"] == "required_facts_mapping_gap"
    assert report["checks"]["brf2_required_facts_mapping_ready"] is True
    assert report["checks"]["brf2_after_required_facts_mapping_state"] == (
        "armed_observation"
    )
    assert report["checks"]["brf2_fresh_signal_rule_id"] == (
        "brf2_short_rally_failure_fresh_signal_v1"
    )
    assert report["checks"]["brf2_required_fact_count"] == 8
    assert report["checks"]["brf2_disable_fact_count"] == 5
    assert report["brf2_runtime_signal_facts"]["status"] == (
        "brf2_runtime_signal_facts_missing_watcher_input"
    )
    assert report["brf2_runtime_signal_facts"]["fact_input_present"] is False
    assert report["brf2_runtime_signal_facts"]["watcher_tick_present"] is False
    assert report["checks"]["brf2_runtime_signal_fact_input_present"] is False
    assert report["checks"]["brf2_runtime_signal_watcher_tick_present"] is False
    assert report["brf2_runtime_signal_capture"]["ready"] is True
    assert report["brf2_runtime_signal_capture"]["current_signal_state"] == (
        "fact_input_missing"
    )
    assert report["brf2_runtime_signal_capture"]["first_blocker_class"] == (
        "brf2_watcher_fact_input_missing"
    )
    assert report["brf2_runtime_signal_capture"]["candidate_packet_ready"] is False
    assert report["checks"]["brf2_runtime_signal_capture_ready"] is True
    assert report["checks"]["brf2_runtime_signal_state"] == "fact_input_missing"
    assert report["checks"]["brf2_runtime_signal_first_blocker_class"] == (
        "brf2_watcher_fact_input_missing"
    )
    assert report["checks"]["brf2_runtime_candidate_packet_ready"] is False
    assert report["checks"]["brf2_next_bottleneck"] == (
        "brf2_watcher_fact_input_missing"
    )
    assert report["three_strategy_live_trial_portfolio"]["ready"] is True
    assert report["three_strategy_live_trial_portfolio"]["seat_count"] == 3
    assert report["three_strategy_live_trial_portfolio"][
        "selected_strategy_groups"
    ] == ["MPG-001", "BRF2-001", "SOR-001"]
    assert report["checks"]["three_strategy_live_trial_portfolio_ready"] is True
    assert report["checks"]["live_trial_seat_count"] == 3
    assert report["checks"]["live_trial_strategy_groups"] == [
        "MPG-001",
        "BRF2-001",
        "SOR-001",
    ]
    assert report["checks"]["live_trial_market_wait_count"] == 2
    assert report["checks"]["live_trial_owner_policy_gap_count"] == 0
    assert report["checks"]["live_trial_engineering_gap_count"] == 1
    assert report["strategy_tradeability_verdict"]["top_verdict"] == (
        "not_tradable_facts"
    )
    assert report["strategy_tradeability_verdict"]["top_first_blocker_class"] == (
        "brf2_watcher_fact_input_missing"
    )
    assert report["strategy_tradeability_verdict"]["top_next_action"] == (
        "attach_brf2_watcher_fact_input_producer"
    )
    assert report["checks"]["tradeability_top_strategy_group_id"] == "BRF2-001"
    assert report["checks"]["tradeability_top_verdict"] == (
        "not_tradable_facts"
    )
    assert report["checks"]["tradeability_row_count"] == 3
    assert report["checks"]["tradeability_verdict_rows_count"] == 3
    assert report["checks"]["tradeability_row_count_matches_verdict_rows"] is True
    assert report["checks"]["tradeability_tradable_now_count"] == 0
    assert report["checks"]["tradeability_real_order_authority_count"] == 0
    assert report["checks"]["non_market_gaps"] == [_expected_brf2_fact_input_gap()]


def test_local_monitor_sequence_artifact_daily_check_uses_report_json_path(
    tmp_path: Path,
) -> None:
    module = _load_module()

    command = module._daily_check_command(
        mode="artifact",
        output_json=tmp_path / "daily.json",
        output_owner_progress=tmp_path / "daily.md",
    )

    assert "--report-json-path" in command
    assert command[command.index("--report-json-path") + 1] == str(
        tmp_path / "daily.json"
    )
    assert "--from-cache" not in command
    assert "--auto-cache" not in command


def test_local_monitor_sequence_auto_cache_uses_local_snapshot_inside_tokyo_release(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    monkeypatch.setattr(
        module,
        "REPO_ROOT",
        Path("/home/ubuntu/brc-deploy/releases/brc-runtime-governance-test"),
    )

    command = module._daily_check_command(
        mode="auto-cache",
        output_json=tmp_path / "daily.json",
        output_owner_progress=tmp_path / "daily.md",
    )

    assert "--auto-cache" in command
    assert command[command.index("--snapshot-host") + 1] == "local"


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

        if script == "build_brf2_non_executing_candidate_packet.py":
            _write_waiting_brf2_candidate_packet(command)
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
        strategygroup_portfolio_board_json=tmp_path / "portfolio-board.json",
        strategygroup_portfolio_board_md=tmp_path / "portfolio-board.md",
        strategygroup_trial_candidate_pool_md=tmp_path / "trial-pool.md",
        strategygroup_capital_trial_readiness_bridge_json=tmp_path
        / "capital-trial-bridge.json",
        strategygroup_capital_trial_readiness_bridge_md=tmp_path
        / "capital-trial-bridge.md",
        strategygroup_capital_trial_packet_json=tmp_path / "trial-packet.json",
        strategygroup_capital_trial_packet_md=tmp_path / "trial-packet.md",
        strategygroup_research_intake_review_json=tmp_path
        / "research-intake-review.json",
        strategygroup_research_intake_review_md=tmp_path
        / "research-intake-review.md",
        strategygroup_trial_asset_admission_proposal_json=tmp_path
        / "trial-admission-proposal.json",
        strategygroup_trial_asset_admission_proposal_md=tmp_path
        / "trial-admission-proposal.md",
        brf2_owner_trial_policy_scope_json=tmp_path / "brf2-policy.json",
        brf2_owner_trial_policy_scope_md=tmp_path / "brf2-policy.md",
        brf2_required_facts_mapping_json=tmp_path / "brf2-required-facts.json",
        brf2_required_facts_mapping_md=tmp_path / "brf2-required-facts.md",
        brf2_runtime_signal_facts_json=tmp_path / "brf2-signal-facts.json",
        brf2_runtime_signal_facts_md=tmp_path / "brf2-signal-facts.md",
        brf2_runtime_signal_capture_json=tmp_path / "brf2-signal-capture.json",
        brf2_runtime_signal_capture_md=tmp_path / "brf2-signal-capture.md",
        brf2_non_executing_candidate_packet_json=tmp_path / "brf2-candidate.json",
        brf2_non_executing_candidate_packet_md=tmp_path / "brf2-candidate.md",
        three_strategy_live_trial_portfolio_json=tmp_path
        / "three-strategy-portfolio.json",
        three_strategy_live_trial_portfolio_md=tmp_path
        / "three-strategy-portfolio.md",
        strategygroup_tradeability_verdict_json=tmp_path / "tradeability.json",
        strategygroup_tradeability_verdict_md=tmp_path / "tradeability.md",
        command_runner=fake_runner,
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert report["checks"]["blockers"] == []
    assert report["checks"]["execution_blockers"] == []
    assert report["checks"]["non_market_gaps"][0]["missing_or_false"] == [
        "goal_progress:generated_before_daily_check"
    ]
    assert report["checks"]["engineering_gaps"] == report["checks"]["non_market_gaps"]
    assert report["checks"]["owner_decision_required"] is False


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
                    "status": "waiting_for_market_monitor_refresh_needed",
                    "runtime_status": "waiting_for_market",
                    "monitor_status": "needs_refresh",
                    "owner_status": "waiting_for_opportunity",
                    "checks": {
                        "blockers": [],
                        "waiting_for_market": True,
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
                    "status": "waiting_for_market_monitor_refresh_needed",
                    "runtime_status": "waiting_for_market",
                    "monitor_status": "needs_refresh",
                    "owner_status": "waiting_for_opportunity",
                    "checks": {
                        "blockers": [],
                        "product_gaps": [],
                        "waiting_for_market": True,
                        "monitor_refresh_needed": True,
                        "monitor_refresh_reasons": ["runtime_progress_cache_stale"],
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

        if script == "build_brf2_non_executing_candidate_packet.py":
            _write_waiting_brf2_candidate_packet(command)
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
        strategygroup_portfolio_board_json=tmp_path / "portfolio-board.json",
        strategygroup_portfolio_board_md=tmp_path / "portfolio-board.md",
        strategygroup_trial_candidate_pool_md=tmp_path / "trial-pool.md",
        strategygroup_capital_trial_readiness_bridge_json=tmp_path
        / "capital-trial-bridge.json",
        strategygroup_capital_trial_readiness_bridge_md=tmp_path
        / "capital-trial-bridge.md",
        strategygroup_capital_trial_packet_json=tmp_path / "trial-packet.json",
        strategygroup_capital_trial_packet_md=tmp_path / "trial-packet.md",
        strategygroup_research_intake_review_json=tmp_path
        / "research-intake-review.json",
        strategygroup_research_intake_review_md=tmp_path
        / "research-intake-review.md",
        strategygroup_trial_asset_admission_proposal_json=tmp_path
        / "trial-admission-proposal.json",
        strategygroup_trial_asset_admission_proposal_md=tmp_path
        / "trial-admission-proposal.md",
        brf2_owner_trial_policy_scope_json=tmp_path / "brf2-policy.json",
        brf2_owner_trial_policy_scope_md=tmp_path / "brf2-policy.md",
        brf2_required_facts_mapping_json=tmp_path / "brf2-required-facts.json",
        brf2_required_facts_mapping_md=tmp_path / "brf2-required-facts.md",
        brf2_runtime_signal_facts_json=tmp_path / "brf2-signal-facts.json",
        brf2_runtime_signal_facts_md=tmp_path / "brf2-signal-facts.md",
        brf2_runtime_signal_capture_json=tmp_path / "brf2-signal-capture.json",
        brf2_runtime_signal_capture_md=tmp_path / "brf2-signal-capture.md",
        brf2_non_executing_candidate_packet_json=tmp_path / "brf2-candidate.json",
        brf2_non_executing_candidate_packet_md=tmp_path / "brf2-candidate.md",
        three_strategy_live_trial_portfolio_json=tmp_path
        / "three-strategy-portfolio.json",
        three_strategy_live_trial_portfolio_md=tmp_path
        / "three-strategy-portfolio.md",
        strategygroup_tradeability_verdict_json=tmp_path / "tradeability.json",
        strategygroup_tradeability_verdict_md=tmp_path / "tradeability.md",
        command_runner=fake_runner,
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["runtime_status"] == "waiting_for_market"
    assert report["monitor_status"] == "needs_refresh"
    assert report["owner_status"] == "waiting_for_opportunity"
    assert report["owner_summary"]["state"] == "需要修复"
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert report["checks"]["blockers"] == []
    assert report["checks"]["monitor_refresh_needed"] is True
    assert report["checks"]["monitor_refresh_reasons"] == [
        "runtime_progress_cache_stale"
    ]
    assert report["checks"]["refresh_required"] is True
    assert report["checks"]["automation_notify"] is True
    assert report["checks"]["owner_notify"] is False
    assert report["checks"]["non_market_gaps"] == [_expected_brf2_fact_input_gap()]
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

        if script == "build_brf2_non_executing_candidate_packet.py":
            _write_waiting_brf2_candidate_packet(command)
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
        strategygroup_portfolio_board_json=tmp_path / "portfolio-board.json",
        strategygroup_portfolio_board_md=tmp_path / "portfolio-board.md",
        strategygroup_trial_candidate_pool_md=tmp_path / "trial-pool.md",
        strategygroup_capital_trial_readiness_bridge_json=tmp_path
        / "capital-trial-bridge.json",
        strategygroup_capital_trial_readiness_bridge_md=tmp_path
        / "capital-trial-bridge.md",
        strategygroup_capital_trial_packet_json=tmp_path / "trial-packet.json",
        strategygroup_capital_trial_packet_md=tmp_path / "trial-packet.md",
        strategygroup_research_intake_review_json=tmp_path
        / "research-intake-review.json",
        strategygroup_research_intake_review_md=tmp_path
        / "research-intake-review.md",
        strategygroup_trial_asset_admission_proposal_json=tmp_path
        / "trial-admission-proposal.json",
        strategygroup_trial_asset_admission_proposal_md=tmp_path
        / "trial-admission-proposal.md",
        brf2_owner_trial_policy_scope_json=tmp_path / "brf2-policy.json",
        brf2_owner_trial_policy_scope_md=tmp_path / "brf2-policy.md",
        brf2_required_facts_mapping_json=tmp_path / "brf2-required-facts.json",
        brf2_required_facts_mapping_md=tmp_path / "brf2-required-facts.md",
        brf2_runtime_signal_facts_json=tmp_path / "brf2-signal-facts.json",
        brf2_runtime_signal_facts_md=tmp_path / "brf2-signal-facts.md",
        brf2_runtime_signal_capture_json=tmp_path / "brf2-signal-capture.json",
        brf2_runtime_signal_capture_md=tmp_path / "brf2-signal-capture.md",
        brf2_non_executing_candidate_packet_json=tmp_path / "brf2-candidate.json",
        brf2_non_executing_candidate_packet_md=tmp_path / "brf2-candidate.md",
        three_strategy_live_trial_portfolio_json=tmp_path
        / "three-strategy-portfolio.json",
        three_strategy_live_trial_portfolio_md=tmp_path
        / "three-strategy-portfolio.md",
        strategygroup_tradeability_verdict_json=tmp_path / "tradeability.json",
        strategygroup_tradeability_verdict_md=tmp_path / "tradeability.md",
        command_runner=fake_runner,
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert report["checks"]["blockers"] == []
    assert report["checks"]["non_market_gaps"] == [
        {
            "source": "l2_tier_policy_review",
            "requirement": "conditional L2 tier policy review recommends a local policy update before the broader opportunity is considered covered",
            "missing_or_false": [
                "conditional_l2_tier_policy_update_needed",
                "groups:BTPC-001",
            ],
        },
        _expected_brf2_fact_input_gap(),
    ]
    assert report["checks"]["engineering_gaps"] == report["checks"]["non_market_gaps"]
    assert report["checks"]["owner_decision_required"] is False
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

        if script == "build_brf2_non_executing_candidate_packet.py":
            _write_waiting_brf2_candidate_packet(command)
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
        strategygroup_portfolio_board_json=tmp_path / "portfolio-board.json",
        strategygroup_portfolio_board_md=tmp_path / "portfolio-board.md",
        strategygroup_trial_candidate_pool_md=tmp_path / "trial-pool.md",
        strategygroup_capital_trial_readiness_bridge_json=tmp_path
        / "capital-trial-bridge.json",
        strategygroup_capital_trial_readiness_bridge_md=tmp_path
        / "capital-trial-bridge.md",
        strategygroup_capital_trial_packet_json=tmp_path / "trial-packet.json",
        strategygroup_capital_trial_packet_md=tmp_path / "trial-packet.md",
        strategygroup_research_intake_review_json=tmp_path
        / "research-intake-review.json",
        strategygroup_research_intake_review_md=tmp_path
        / "research-intake-review.md",
        strategygroup_trial_asset_admission_proposal_json=tmp_path
        / "trial-admission-proposal.json",
        strategygroup_trial_asset_admission_proposal_md=tmp_path
        / "trial-admission-proposal.md",
        brf2_owner_trial_policy_scope_json=tmp_path / "brf2-policy.json",
        brf2_owner_trial_policy_scope_md=tmp_path / "brf2-policy.md",
        brf2_required_facts_mapping_json=tmp_path / "brf2-required-facts.json",
        brf2_required_facts_mapping_md=tmp_path / "brf2-required-facts.md",
        brf2_runtime_signal_facts_json=tmp_path / "brf2-signal-facts.json",
        brf2_runtime_signal_facts_md=tmp_path / "brf2-signal-facts.md",
        brf2_runtime_signal_capture_json=tmp_path / "brf2-signal-capture.json",
        brf2_runtime_signal_capture_md=tmp_path / "brf2-signal-capture.md",
        brf2_non_executing_candidate_packet_json=tmp_path / "brf2-candidate.json",
        brf2_non_executing_candidate_packet_md=tmp_path / "brf2-candidate.md",
        three_strategy_live_trial_portfolio_json=tmp_path
        / "three-strategy-portfolio.json",
        three_strategy_live_trial_portfolio_md=tmp_path
        / "three-strategy-portfolio.md",
        strategygroup_tradeability_verdict_json=tmp_path / "tradeability.json",
        strategygroup_tradeability_verdict_md=tmp_path / "tradeability.md",
        command_runner=fake_runner,
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["checks"]["blockers"] == []
    assert report["checks"]["non_market_gaps"] == [_expected_brf2_fact_input_gap()]
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


def test_local_monitor_sequence_success_allows_waiting_monitor_refresh() -> None:
    module = _load_module()

    assert module._sequence_report_is_success(
        {
            "status": "waiting_for_market_monitor_refresh_needed",
            "runtime_status": "waiting_for_market",
            "monitor_status": "needs_refresh",
            "checks": {
                "blockers": [],
                "execution_blockers": [],
                "non_market_gaps": [],
                "engineering_gaps": [],
                "owner_decision_required": False,
                "monitor_refresh_gaps": ["runtime_progress_cache_stale"],
            },
        }
    )


def test_local_monitor_sequence_fresh_signal_processing_beats_cache_refresh() -> None:
    module = _load_module()
    packets = {
        "daily_check": {
            "status": "processing",
            "runtime_status": "processing",
            "monitor_status": "needs_refresh",
            "checks": {
                "monitor_refresh_needed": True,
                "monitor_refresh_reasons": ["runtime_progress_cache_stale"],
            },
        },
        "goal_progress": {
            "status": "processing",
            "runtime_status": "processing",
            "monitor_status": "needs_refresh",
            "checks": {
                "monitor_refresh_needed": True,
                "monitor_refresh_reasons": ["runtime_progress_cache_stale"],
            },
        },
        "completion_audit": {"status": "not_complete_runtime_processing"},
        "signal_coverage": {"status": "mainline_runtime_signal_ready"},
    }

    status = module._sequence_status(steps=[], packets=packets)
    monitor_status = module._sequence_monitor_status(status=status, packets=packets)
    runtime_status = module._sequence_runtime_status(status=status, packets=packets)
    owner_status = module._sequence_owner_status(
        status=status,
        runtime_status=runtime_status,
        monitor_status=monitor_status,
        owner_decision_required=False,
    )

    assert status == "processing"
    assert runtime_status == "processing"
    assert monitor_status == "needs_refresh"
    assert owner_status == "processing"
    assert module._sequence_report_is_success(
        {
            "status": status,
            "runtime_status": runtime_status,
            "monitor_status": monitor_status,
            "checks": {
                "blockers": [],
                "execution_blockers": [],
                "non_market_gaps": [],
                "engineering_gaps": [],
                "owner_decision_required": False,
            },
        }
    )


def test_local_monitor_sequence_success_rejects_deployment_issue() -> None:
    module = _load_module()

    assert not module._sequence_report_is_success(
        {
            "status": "temporarily_unavailable_deployment_issue",
            "runtime_status": "temporarily_unavailable",
            "monitor_status": "deployment_issue",
            "checks": {
                "blockers": [],
                "execution_blockers": [],
                "non_market_gaps": [],
                "engineering_gaps": [],
                "owner_decision_required": False,
            },
        }
    )


def test_local_monitor_sequence_classifies_deployment_returncodes_without_owner_decision() -> None:
    module = _load_module()
    packets = {
        "daily_check": {
            "status": "temporarily_unavailable_deployment_issue",
            "runtime_status": "temporarily_unavailable",
            "monitor_status": "deployment_issue",
            "owner_summary": {"owner_intervention_required": False},
            "checks": {
                "blockers": ["runtime_head_mismatch", "l1_snapshot_blocked"],
                "deployment_issue": True,
                "owner_decision_required": False,
            },
        },
        "goal_progress": {
            "status": "temporarily_unavailable_deployment_issue",
            "runtime_status": "temporarily_unavailable",
            "monitor_status": "deployment_issue",
            "owner_summary": {"owner_intervention_required": False},
            "checks": {"blockers": [], "owner_decision_required": False},
        },
        "completion_audit": {"status": "not_complete_waiting_for_market"},
    }
    steps = [
        {"name": "daily_check", "returncode": 2},
        {"name": "goal_progress", "returncode": 2},
        {"name": "completion_audit", "returncode": 0},
    ]

    execution_blockers = [
        f"{step['name']}:returncode:{step['returncode']}"
        for step in steps
        if int(step.get("returncode") or 0) not in (0,)
        and not module._step_returncode_is_monitor_refresh(step, packets)
        and not module._step_returncode_is_deployment_issue(step, packets)
    ]

    assert module._sequence_status(steps=steps, packets=packets) == (
        "temporarily_unavailable_deployment_issue"
    )
    assert execution_blockers == []
    assert module._sequence_owner_decision_required(
        packets=packets,
        execution_blockers=execution_blockers,
        engineering_gaps=[],
    ) is False


def test_local_monitor_sequence_success_rejects_owner_decision() -> None:
    module = _load_module()

    assert not module._sequence_report_is_success(
        {
            "status": "waiting_for_market",
            "runtime_status": "waiting_for_market",
            "monitor_status": "fresh",
            "checks": {
                "blockers": [],
                "execution_blockers": [],
                "non_market_gaps": [],
                "engineering_gaps": [],
                "owner_decision_required": True,
            },
        }
    )
