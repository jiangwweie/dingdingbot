from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_opportunity_decision_loop.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_opportunity_decision_loop",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _expansion_review() -> dict:
    return {
        "status": "review_needed_broader_observe_only_would_enter",
        "review_rows": [
            {
                "strategy_group_id": "BTPC-001",
                "symbol": "AVAX/USDT:USDT",
                "side": "short",
                "confidence": "0.62",
                "current_tier": "L2",
                "reason_codes": ["btpc_structure_loss_confirmed"],
                "execution_boundary": "shadow review only; no FinalGate/Operation Layer",
            },
            {
                "strategy_group_id": "VCB-001",
                "symbol": "LINK/USDT:USDT",
                "side": "long",
                "confidence": "0.60",
                "current_tier": "L1",
                "reason_codes": ["vcb_breakout_close_confirmed"],
                "execution_boundary": "observe-only; no candidate/order",
            },
            {
                "strategy_group_id": "RBR-001",
                "symbol": "ADA/USDT:USDT",
                "side": "short",
                "confidence": "0.57",
                "current_tier": "L1",
                "reason_codes": ["rbr_range_boundary_reject"],
                "execution_boundary": "observe-only; no candidate/order",
            },
        ],
        "safety_invariants": {
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "exchange_write_called": False,
        },
    }


def _l2_readiness() -> dict:
    return {
        "status": "l2_readiness_review_already_enabled",
        "readiness_rows": [
            {
                "strategy_group_id": "BTPC-001",
                "symbol": "AVAX/USDT:USDT",
                "side": "short",
                "current_tier": "L2",
                "l2_readiness": "l2_shadow_candidate_observation_enabled",
                "l2_shadow_candidate_observation_enabled": True,
                "positive_evidence": ["main-control L2 intake dry-run passed"],
                "blocking_gaps_before_l2": ["historical_open_interest_window_missing"],
            },
            {
                "strategy_group_id": "VCB-001",
                "symbol": "LINK/USDT:USDT",
                "side": "long",
                "current_tier": "L1",
                "l2_readiness": "blocked_classifier_redesign_required",
                "l2_shadow_candidate_observation_enabled": False,
                "positive_evidence": ["true-breakout classifier track exists"],
                "blocking_gaps_before_l2": [
                    "false_breakout_disable_state_missing_from_runtime",
                    "volume_compression_cost_m2m_full_sequence_negative",
                ],
                "classifier_repair_spec": {
                    "status": "local_repair_spec_ready",
                    "target_classifier": "true_breakout_pre_entry_classifier",
                    "blocking_gap_keys": [
                        "false_breakout_disable_state_missing_from_runtime"
                    ],
                    "required_entry_states": [
                        "breakout_close_confirmed",
                        "volume_expansion_confirmed",
                    ],
                    "required_disable_states": [
                        "false_breakout_reversal_detected"
                    ],
                    "replay_acceptance_cases": ["false_breakout_disable_needed"],
                    "acceptance_signal": "disable false breakout before L2",
                    "not_execution_authority": True,
                    "not_l2_promotion_authority": True,
                    "not_l4_scope_change": True,
                },
                "economic_replay_spec": {
                    "status": "local_economic_replay_spec_ready",
                    "blocking_gap_keys": [
                        "volume_compression_cost_m2m_full_sequence_negative"
                    ],
                    "required_cost_fields": [
                        "fee_estimate_usdt",
                        "slippage_estimate_usdt",
                        "funding_impact_usdt",
                        "min_qty_step_size_impact",
                        "fill_slot_assumption",
                        "leverage_survival_note",
                        "net_edge_note",
                        "does_not_lower_owner_selected_leverage",
                        "not_submit_authority",
                    ],
                    "replay_acceptance_cases": [
                        "compression_breakout_would_enter",
                        "false_breakout_disable_needed",
                    ],
                    "acceptance_signal": "VCB economic replay before L2",
                    "not_execution_authority": True,
                    "not_l2_promotion_authority": True,
                    "not_l4_scope_change": True,
                },
            },
            {
                "strategy_group_id": "RBR-001",
                "symbol": "ADA/USDT:USDT",
                "side": "short",
                "current_tier": "L1",
                "l2_readiness": "blocked_parked_negative_evidence",
                "l2_shadow_candidate_observation_enabled": False,
                "positive_evidence": ["range vocabulary exists"],
                "blocking_gaps_before_l2": ["calm_range_m2m_failed"],
            },
        ],
        "safety_invariants": {
            "tier_policy_changed": False,
            "shadow_candidate_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "exchange_write_called": False,
        },
    }


def _l2_intake() -> dict:
    return {
        "status": "l2_intake_dry_run_no_candidates",
        "source_readiness_rows": [
            {
                "strategy_group_id": "BTPC-001",
                "current_tier": "L2",
                "l2_readiness": "l2_shadow_candidate_observation_enabled",
                "l2_shadow_candidate_observation_enabled": True,
                "blocking_gaps_before_l2": ["historical_open_interest_window_missing"],
            },
            {
                "strategy_group_id": "VCB-001",
                "current_tier": "L1",
                "l2_readiness": "blocked_classifier_redesign_required",
                "l2_shadow_candidate_observation_enabled": False,
                "blocking_gaps_before_l2": [
                    "false_breakout_disable_state_missing_from_runtime"
                ],
            },
        ],
        "safety_invariants": {
            "tier_policy_changed": False,
            "shadow_candidate_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "exchange_write_called": False,
        },
    }


def _replay_lab(*, include_rbr: bool = False) -> dict:
    l1_rows = [
        {
            "strategy_group_id": "VCB-001",
            "fixture_case": "compression_breakout_would_enter",
            "signal_status": "would_enter_observe_only",
            "review_recommendation": "keep_observing",
            "blocker_class": "review_only_warning",
            "cost_review": _cost_review(),
            "real_order_allowed": False,
            "exchange_write_allowed": False,
            "operation_layer_submit_allowed": False,
        },
        {
            "strategy_group_id": "VCB-001",
            "fixture_case": "false_breakout_disable_needed",
            "signal_status": "would_enter_but_disable_classifier_missing",
            "review_recommendation": "revise",
            "blocker_class": "review_only_warning",
            "cost_review": _cost_review(),
            "real_order_allowed": False,
            "exchange_write_allowed": False,
            "operation_layer_submit_allowed": False,
        },
    ]
    if include_rbr:
        l1_rows.append(
            {
                "strategy_group_id": "RBR-001",
                "fixture_case": "range_boundary_would_enter",
                "signal_status": "would_enter_observe_only",
                "review_recommendation": "revise",
                "blocker_class": "review_only_warning",
                "real_order_allowed": False,
                "exchange_write_allowed": False,
                "operation_layer_submit_allowed": False,
            }
        )
    return {
        "status": "passed",
        "l2_shadow_replay_samples": [
            {
                "strategy_group_id": "BTPC-001",
                "fixture_case": "bear_pullback_would_enter",
                "signal_status": "would_enter_observe_only",
                "review_recommendation": "keep_observing",
                "blocker_class": "review_only_warning",
                "real_order_allowed": False,
                "exchange_write_allowed": False,
                "operation_layer_submit_allowed": False,
            }
        ],
        "l1_observe_replay_samples": l1_rows,
        "safety_invariants": {
            "shadow_candidate_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "exchange_write_called": False,
        },
    }


def _cost_review() -> dict:
    return {
        "fee_estimate_usdt": "0.012",
        "slippage_estimate_usdt": "0.038",
        "funding_impact_usdt": "0.001",
        "min_qty_step_size_impact": "review_only_exchange_rules_shape_present",
        "fill_slot_assumption": "single_slot_review_only_not_execution_authority",
        "leverage_survival_note": "review_only_no_owner_profile_or_leverage_change",
        "net_edge_note": "review-only economic shape",
        "does_not_lower_owner_selected_leverage": True,
        "not_submit_authority": True,
    }


def test_decision_loop_maps_observation_replay_gaps_and_tier_decisions():
    module = _load_module()

    packet = module.build_opportunity_decision_loop(
        expansion_review_packet=_expansion_review(),
        l2_readiness_packet=_l2_readiness(),
        l2_intake_packet=_l2_intake(),
        replay_lab_packet=_replay_lab(),
    )

    assert packet["status"] == "decision_loop_ready"
    assert packet["counts"]["observed_opportunity_count"] == 3
    assert packet["counts"]["replay_covered_count"] == 2
    assert packet["counts"]["work_queue_item_count"] == 4
    assert packet["counts"]["scheduled_work_queue_item_count"] == 3
    assert packet["counts"]["real_order_authorized_count"] == 0
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    assert rows["BTPC-001"]["decision_action"] == "continue_l2_shadow_quality_review"
    assert rows["BTPC-001"]["replay_verification"]["sample_count"] == 1
    assert rows["VCB-001"]["decision_action"] == (
        "repair_blocking_gaps_with_replay_or_facts"
    )
    assert rows["VCB-001"]["gap_work_items"][0]["work_type"] == (
        "classifier_or_rule_work"
    )
    assert rows["VCB-001"]["gap_work_items"][0]["owner_priority"] == "P0.5-high"
    assert rows["VCB-001"]["gap_work_items"][0]["blocks_l2_progression"] is True
    assert rows["VCB-001"]["gap_work_items"][0]["repair_spec"][
        "target_classifier"
    ] == "true_breakout_pre_entry_classifier"
    assert rows["VCB-001"]["gap_work_items"][0]["repair_spec"][
        "required_disable_states"
    ] == ["false_breakout_reversal_detected"]
    assert rows["VCB-001"]["gap_work_items"][0]["repair_spec"][
        "replay_case_coverage"
    ] == {
        "covered": True,
        "covered_cases": ["false_breakout_disable_needed"],
        "missing_cases": [],
        "required_case_count": 1,
    }
    assert rows["VCB-001"]["gap_work_items"][0]["completion_signal"] == (
        "disable false breakout before L2"
    )
    assert rows["RBR-001"]["decision_action"] == "park_or_vocabulary_only"
    work_items = packet["work_queue"]["items"]
    assert packet["work_queue"]["status"] == "ready"
    assert packet["work_queue"]["next_local_checkpoint"] == (
        "repair_classifier_or_disable_state_gaps_for_lsr_vcb"
    )
    assert packet["work_queue"]["counts"]["scheduled"] == 3
    assert packet["work_queue"]["by_work_type"]["classifier_or_rule_work"] == 1
    assert work_items[0]["strategy_group_id"] == "VCB-001"
    assert work_items[0]["work_type"] == "classifier_or_rule_work"
    assert work_items[0]["scheduled"] is True
    assert work_items[0]["repair_spec"]["replay_acceptance_cases"] == [
        "false_breakout_disable_needed"
    ]
    assert work_items[0]["repair_spec"]["replay_case_coverage"]["covered"] is True
    economic_item = next(
        item
        for item in work_items
        if item["strategy_group_id"] == "VCB-001"
        and item["work_type"] == "economic_replay_work"
    )
    assert economic_item["economic_spec"]["status"] == (
        "local_economic_replay_spec_ready"
    )
    assert economic_item["economic_spec"]["economic_case_coverage"]["covered"] is True
    assert economic_item["economic_spec"]["economic_case_coverage"][
        "missing_cases"
    ] == []
    assert economic_item["economic_spec"]["not_execution_authority"] is True
    assert economic_item["completion_signal"] == "VCB economic replay before L2"
    parked_items = [
        item for item in work_items if item["strategy_group_id"] == "RBR-001"
    ]
    assert parked_items
    assert all(item["scheduled"] is False for item in parked_items)
    for row in packet["decision_rows"]:
        assert row["real_order_authority"] is False
        assert row["l4_scope_change_recommended"] is False
    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["interaction"]["places_order"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["work_queue"]["safety_invariants"]["places_order"] is False
    assert packet["work_queue"]["safety_invariants"]["calls_operation_layer"] is False


def test_decision_loop_requires_replay_before_l2_when_missing():
    module = _load_module()
    packet = module.build_opportunity_decision_loop(
        expansion_review_packet={
            **_expansion_review(),
            "review_rows": [_expansion_review()["review_rows"][2]],
        },
        l2_readiness_packet={
            **_l2_readiness(),
            "readiness_rows": [
                {
                    **_l2_readiness()["readiness_rows"][2],
                    "l2_readiness": "blocked_classifier_redesign_required",
                }
            ],
        },
        l2_intake_packet={"status": "l2_intake_dry_run_no_candidates"},
        replay_lab_packet=_replay_lab(include_rbr=False),
    )

    row = packet["decision_rows"][0]
    assert row["strategy_group_id"] == "RBR-001"
    assert row["replay_verification"]["covered"] is False
    assert row["decision_action"] == "build_replay_corpus_before_l2"
    assert row["next_checkpoint"] == "add_group_replay_corpus_and_would_enter_case"
    assert packet["work_queue"]["counts"]["blocked_l2_progression"] == 1
    assert packet["work_queue"]["items"][0]["work_type"] == "replay_corpus_work"
    assert packet["work_queue"]["items"][0]["scheduled"] is True


def test_decision_loop_blocks_forbidden_source_effects():
    module = _load_module()
    readiness = _l2_readiness()
    readiness["safety_invariants"]["order_created"] = True

    packet = module.build_opportunity_decision_loop(
        expansion_review_packet=_expansion_review(),
        l2_readiness_packet=readiness,
        l2_intake_packet=_l2_intake(),
        replay_lab_packet=_replay_lab(),
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert "packet_1.safety.order_created" in packet["safety_invariants"][
        "source_forbidden_effects"
    ]
    assert packet["operator_command_plan"]["places_order"] is False


def test_decision_loop_cli_writes_json_and_owner_progress(tmp_path, capsys):
    module = _load_module()
    expansion_path = tmp_path / "expansion.json"
    readiness_path = tmp_path / "readiness.json"
    intake_path = tmp_path / "intake.json"
    replay_path = tmp_path / "replay.json"
    output_path = tmp_path / "decision-loop.json"
    owner_path = tmp_path / "decision-loop.md"
    expansion_path.write_text(json.dumps(_expansion_review()), encoding="utf-8")
    readiness_path.write_text(json.dumps(_l2_readiness()), encoding="utf-8")
    intake_path.write_text(json.dumps(_l2_intake()), encoding="utf-8")
    replay_path.write_text(json.dumps(_replay_lab()), encoding="utf-8")

    exit_code = module.main(
        [
            "--expansion-review-json",
            str(expansion_path),
            "--l2-readiness-json",
            str(readiness_path),
            "--l2-intake-json",
            str(intake_path),
            "--replay-lab-json",
            str(replay_path),
            "--output-json",
            str(output_path),
            "--output-owner-progress",
            str(owner_path),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["scope"] == "strategygroup_opportunity_decision_loop"
    assert file_payload["work_queue"]["status"] == "ready"
    owner_text = owner_path.read_text(encoding="utf-8")
    assert "StrategyGroup Opportunity Decision Loop" in owner_text
    assert "repair_blocking_gaps_with_replay_or_facts" in owner_text
    assert "Work Queue" in owner_text
    assert "classifier_or_rule_work" in owner_text
