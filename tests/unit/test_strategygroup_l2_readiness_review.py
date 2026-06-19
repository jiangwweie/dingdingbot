from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_l2_readiness_review.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_l2_readiness_review",
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
                "current_tier": "L1",
            },
            {
                "strategy_group_id": "LSR-001",
                "symbol": "XRP/USDT:USDT",
                "side": "long",
                "current_tier": "L1",
            },
            {
                "strategy_group_id": "RBR-001",
                "symbol": "ADA/USDT:USDT",
                "side": "short",
                "current_tier": "L1",
            },
            {
                "strategy_group_id": "VCB-001",
                "symbol": "LINK/USDT:USDT",
                "side": "long",
                "current_tier": "L1",
            },
        ],
        "safety_invariants": {
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _policy() -> dict:
    return {
        "strategy_groups": {
            "BTPC-001": {
                "coverage_review_priority": "P0_5",
                "l2_readiness": "conditional_l2_review_candidate",
                "recommended_action": "prepare_main_control_handoff_intake_and_dry_run_before_any_l2_policy_change",
                "positive_evidence": ["largest current right-tail lead"],
                "blocking_gaps_before_l2": [
                    "main_control_handoff_not_imported",
                    "historical_open_interest_window_missing",
                ],
            },
            "LSR-001": {
                "coverage_review_priority": "P1",
                "l2_readiness": "blocked_rewrite_required",
                "recommended_action": "keep_l1_observe_only_until_side_specific_rewrite_handoff_exists",
                "blocking_gaps_before_l2": [
                    "side_specific_rewrite_missing",
                    "lsr_disable_classifier_state_missing_from_runtime",
                ],
                "classifier_repair_spec": {
                    "status": "local_repair_spec_ready",
                    "target_classifier": "side_specific_short_revival_classifier",
                    "blocking_gap_keys": [
                        "lsr_disable_classifier_state_missing_from_runtime"
                    ],
                    "required_entry_states": ["short_revival_confirmation_present"],
                    "required_disable_states": ["range_context_missing"],
                    "replay_acceptance_cases": ["short_revival_rewrite_needed"],
                    "acceptance_signal": "rewrite before L2",
                    "revision_execution": {
                        "status": "local_classifier_revision_executed",
                        "implementation_ref": "src/domain/reference_price_action_evaluators.py",
                        "logic_version": "lsr-001-price-action-v1",
                        "executed_entry_states": [
                            "short_revival_confirmation_present"
                        ],
                        "executed_disable_states": ["range_context_missing"],
                        "validation_cases": ["short_revival_short_would_enter"],
                        "not_execution_authority": True,
                        "not_l2_promotion_authority": True,
                        "not_l4_scope_change": True,
                    },
                    "not_execution_authority": True,
                    "not_l2_promotion_authority": True,
                    "not_l4_scope_change": True,
                },
                "economic_replay_spec": {
                    "status": "local_economic_replay_spec_ready",
                    "blocking_gap_keys": [
                        "cost_fill_slot_m2m_and_leverage_boundary_missing"
                    ],
                    "required_cost_fields": [
                        "fee_estimate_usdt",
                        "slippage_estimate_usdt",
                        "fill_slot_assumption",
                    ],
                    "replay_acceptance_cases": ["short_revival_rewrite_needed"],
                    "acceptance_signal": "economic replay before L2",
                    "replay_execution": {
                        "status": "local_economic_replay_executed",
                        "implementation_ref": "src/domain/strategygroup_runtime_replay.py",
                        "covered_cost_fields": [
                            "fee_estimate_usdt",
                            "slippage_estimate_usdt",
                            "fill_slot_assumption",
                        ],
                        "validation_cases": ["short_revival_rewrite_needed"],
                        "not_execution_authority": True,
                        "not_l2_promotion_authority": True,
                        "not_l4_scope_change": True,
                    },
                    "not_execution_authority": True,
                    "not_l2_promotion_authority": True,
                    "not_l4_scope_change": True,
                },
            },
            "RBR-001": {
                "coverage_review_priority": "P2",
                "l2_readiness": "blocked_parked_negative_evidence",
                "recommended_action": "keep_l1_or_park",
                "blocking_gaps_before_l2": ["calm_range_m2m_failed"],
            },
            "VCB-001": {
                "coverage_review_priority": "P1",
                "l2_readiness": "blocked_classifier_redesign_required",
                "recommended_action": "keep_l1_observe_only_until_false_breakout_disable",
                "blocking_gaps_before_l2": [
                    "cost_m2m_negative",
                    "false_breakout_disable_state_missing_from_runtime",
                ],
                "classifier_repair_spec": {
                    "status": "local_repair_spec_ready",
                    "target_classifier": "true_breakout_pre_entry_classifier",
                    "blocking_gap_keys": [
                        "false_breakout_disable_state_missing_from_runtime"
                    ],
                    "required_entry_states": ["breakout_close_confirmed"],
                    "required_disable_states": ["false_breakout_reversal_detected"],
                    "replay_acceptance_cases": ["false_breakout_disable_needed"],
                    "acceptance_signal": "disable false breakout before L2",
                    "revision_execution": {
                        "status": "local_classifier_revision_executed",
                        "implementation_ref": "src/domain/reference_price_action_evaluators.py",
                        "logic_version": "vcb-001-price-action-v1",
                        "executed_entry_states": ["breakout_close_confirmed"],
                        "executed_disable_states": [
                            "false_breakout_reversal_detected"
                        ],
                        "validation_cases": ["false_breakout_reversal_disabled"],
                        "not_execution_authority": True,
                        "not_l2_promotion_authority": True,
                        "not_l4_scope_change": True,
                    },
                    "not_execution_authority": True,
                    "not_l2_promotion_authority": True,
                    "not_l4_scope_change": True,
                },
                "economic_replay_spec": {
                    "status": "local_economic_replay_spec_ready",
                    "blocking_gap_keys": ["cost_m2m_negative"],
                    "required_cost_fields": [
                        "fee_estimate_usdt",
                        "slippage_estimate_usdt",
                        "fill_slot_assumption",
                    ],
                    "replay_acceptance_cases": ["false_breakout_disable_needed"],
                    "acceptance_signal": "cost replay before L2",
                    "replay_execution": {
                        "status": "local_economic_replay_executed",
                        "implementation_ref": "src/domain/strategygroup_runtime_replay.py",
                        "covered_cost_fields": [
                            "fee_estimate_usdt",
                            "slippage_estimate_usdt",
                            "fill_slot_assumption",
                        ],
                        "validation_cases": ["false_breakout_disable_needed"],
                        "not_execution_authority": True,
                        "not_l2_promotion_authority": True,
                        "not_l4_scope_change": True,
                    },
                    "not_execution_authority": True,
                    "not_l2_promotion_authority": True,
                    "not_l4_scope_change": True,
                },
            },
        },
        "safety_invariants": {"policy_is_review_only": True},
    }


def test_l2_readiness_review_selects_btpc_as_only_conditional_candidate():
    module = _load_module()

    packet = module.build_l2_readiness_review(
        expansion_review_packet=_expansion_review(),
        expansion_policy=_policy(),
    )

    assert packet["status"] == "l2_readiness_review_has_conditional_candidate"
    assert packet["counts"] == {
        "blocked_count": 3,
        "classifier_revision_executed_count": 2,
        "conditional_l2_candidate_count": 1,
        "economic_replay_executed_count": 2,
        "enabled_l2_count": 0,
        "classifier_repair_spec_ready_count": 2,
        "economic_replay_spec_ready_count": 2,
        "forbidden_effect_count": 0,
        "review_row_count": 4,
    }
    assert packet["decision"]["handoff_intake_recommended_groups"] == ["BTPC-001"]
    assert packet["decision"]["tier_policy_change_recommended"] is False
    assert packet["decision"]["l4_scope_change_recommended"] is False
    assert packet["decision"]["shadow_candidate_creation_recommended_now"] is False
    rows = {row["strategy_group_id"]: row for row in packet["readiness_rows"]}
    assert rows["BTPC-001"]["conditional_l2_review_candidate"] is True
    assert rows["BTPC-001"]["may_create_shadow_candidate_now"] is False
    assert rows["LSR-001"]["conditional_l2_review_candidate"] is False
    assert rows["LSR-001"]["classifier_repair_spec"]["status"] == (
        "local_repair_spec_ready"
    )
    assert rows["LSR-001"]["classifier_repair_spec"]["target_classifier"] == (
        "side_specific_short_revival_classifier"
    )
    assert rows["LSR-001"]["classifier_repair_spec"]["revision_execution"][
        "status"
    ] == "local_classifier_revision_executed"
    assert rows["LSR-001"]["classifier_repair_spec"]["revision_execution"][
        "logic_version"
    ] == "lsr-001-price-action-v1"
    assert rows["LSR-001"]["classifier_repair_spec"]["not_execution_authority"] is True
    assert rows["LSR-001"]["economic_replay_spec"]["status"] == (
        "local_economic_replay_spec_ready"
    )
    assert rows["LSR-001"]["economic_replay_spec"]["replay_execution"][
        "status"
    ] == "local_economic_replay_executed"
    assert rows["LSR-001"]["economic_replay_spec"]["not_execution_authority"] is True
    assert rows["RBR-001"]["conditional_l2_review_candidate"] is False
    assert rows["VCB-001"]["conditional_l2_review_candidate"] is False
    assert rows["VCB-001"]["classifier_repair_spec"]["required_disable_states"] == [
        "false_breakout_reversal_detected"
    ]
    assert rows["VCB-001"]["classifier_repair_spec"]["revision_execution"][
        "logic_version"
    ] == "vcb-001-price-action-v1"
    assert rows["VCB-001"]["economic_replay_spec"]["required_cost_fields"] == [
        "fee_estimate_usdt",
        "slippage_estimate_usdt",
        "fill_slot_assumption",
    ]
    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["safety_invariants"]["does_not_change_tier_policy"] is True
    assert packet["safety_invariants"]["does_not_expand_l4_real_order_scope"] is True


def test_l2_readiness_review_recognizes_enabled_l2_group():
    module = _load_module()
    policy = _policy()
    policy["strategy_groups"]["BTPC-001"]["l2_readiness"] = (
        "l2_shadow_candidate_observation_enabled"
    )
    policy["strategy_groups"]["BTPC-001"]["recommended_action"] = (
        "continue_l2_shadow_candidate_observation_without_l4_scope_change"
    )
    policy["strategy_groups"]["BTPC-001"]["blocking_gaps_before_l2"] = []

    packet = module.build_l2_readiness_review(
        expansion_review_packet=_expansion_review(),
        expansion_policy=policy,
    )

    assert packet["status"] == "l2_readiness_review_already_enabled"
    assert packet["counts"]["conditional_l2_candidate_count"] == 0
    assert packet["counts"]["enabled_l2_count"] == 1
    assert packet["decision"]["enabled_l2_groups"] == ["BTPC-001"]
    rows = {row["strategy_group_id"]: row for row in packet["readiness_rows"]}
    assert rows["BTPC-001"]["l2_shadow_candidate_observation_enabled"] is True
    assert rows["BTPC-001"]["may_place_real_order_now"] is False


def test_l2_readiness_review_reports_no_rows():
    module = _load_module()

    packet = module.build_l2_readiness_review(
        expansion_review_packet={"status": "no_expansion_review_needed", "review_rows": []},
        expansion_policy=_policy(),
    )

    assert packet["status"] == "l2_readiness_review_no_rows"
    assert packet["owner_state"] == "waiting_for_opportunity"
    assert packet["readiness_rows"] == []


def test_l2_readiness_review_blocks_forbidden_source_effect():
    module = _load_module()
    expansion = _expansion_review()
    expansion["safety_invariants"]["order_created"] = True

    packet = module.build_l2_readiness_review(
        expansion_review_packet=expansion,
        expansion_policy=_policy(),
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert "expansion_review.safety.order_created" in packet["safety_invariants"][
        "source_forbidden_effects"
    ]
    assert packet["operator_command_plan"]["places_order"] is False


def test_l2_readiness_review_cli_writes_json_and_owner_progress(tmp_path, capsys):
    module = _load_module()
    expansion_path = tmp_path / "expansion-review.json"
    policy_path = tmp_path / "policy.json"
    output_path = tmp_path / "l2-review.json"
    owner_path = tmp_path / "l2-review.md"
    expansion_path.write_text(json.dumps(_expansion_review()), encoding="utf-8")
    policy_path.write_text(json.dumps(_policy()), encoding="utf-8")

    exit_code = module.main(
        [
            "--expansion-review-json",
            str(expansion_path),
            "--expansion-policy-json",
            str(policy_path),
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
    assert file_payload["scope"] == "strategygroup_l2_readiness_review"
    owner_text = owner_path.read_text(encoding="utf-8")
    assert "L2 观察面准备度评审" in owner_text
    assert "BTPC-001" in owner_text
    assert (
        "| StrategyGroup | Symbol | Side | Tier | Priority | L2 Readiness | "
        "Action | Blocking gaps |"
    ) in owner_text
    assert "historical_open_interest_window_missing" in owner_text
