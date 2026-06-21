from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "build_strategygroup_btpc_l2_shadow_fact_quality_review.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_btpc_l2_shadow_fact_quality_review",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _opportunity_decision_loop() -> dict:
    return {
        "status": "decision_loop_ready",
        "decision_rows": [
            {
                "strategy_group_id": "BTPC-001",
                "current_tier": "L2",
                "tier_state": "l2_shadow_candidate_observation_enabled",
                "decision_action": "continue_l2_shadow_quality_review",
                "replay_verification": {
                    "covered": True,
                    "sample_count": 5,
                    "would_enter_sample_count": 2,
                    "no_action_sample_count": 1,
                    "revise_sample_count": 3,
                    "non_executing_boundary_ok": True,
                    "fixture_cases": [
                        "bear_pullback_would_enter",
                        "missing_derivatives_context",
                        "no_signal_bear_trend_not_ready",
                        "stale_signal",
                        "strong_uptrend_conflict",
                    ],
                },
                "gap_work_items": [
                    _gap_item("historical_open_interest_window_missing"),
                    _gap_item("historical_global_long_short_ratio_window_missing"),
                    _gap_item("top_trader_position_ratio_window_missing"),
                    _gap_item("real_exchange_margin_liquidation_model_missing"),
                    _gap_item(
                        "short_squeeze_risk_not_runtime_blocking",
                        coverage_status="strategy_review_pending",
                        work_type="strategy_review_work",
                    ),
                ],
                "real_order_authority": False,
            }
        ],
        "safety_invariants": {
            "server_files_mutated": False,
            "tier_policy_changed": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "exchange_write_called": False,
        },
    }


def _gap_item(
    gap: str,
    *,
    coverage_status: str = "fact_source_pending",
    work_type: str = "required_fact_or_market_data_work",
) -> dict:
    return {
        "gap": gap,
        "coverage_status": coverage_status,
        "work_type": work_type,
        "owner_priority": "P0.5-high",
        "scheduled": True,
        "blocks_l2_progression": False,
        "next_stage_decision": "attach_fact_source_before_l2_review",
        "validation_command": "PYTHONDONTWRITEBYTECODE=1 python3 scripts/build_strategygroup_l2_readiness_review.py",
    }


def _l2_readiness() -> dict:
    return {
        "status": "l2_readiness_review_already_enabled",
        "readiness_rows": [
            {
                "strategy_group_id": "BTPC-001",
                "current_tier": "L2",
                "l2_readiness": "l2_shadow_candidate_observation_enabled",
            }
        ],
        "safety_invariants": {
            "server_files_mutated": False,
            "tier_policy_changed": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "exchange_write_called": False,
        },
    }


def _replay_lab() -> dict:
    return {
        "status": "passed",
        "l2_shadow_replay_samples": [
            {
                "strategy_group_id": "BTPC-001",
                "fixture_case": "bear_pullback_would_enter",
                "signal_status": "would_enter_observe_only",
                "review_recommendation": "keep_observing",
                "real_order_allowed": False,
                "exchange_write_allowed": False,
                "operation_layer_submit_allowed": False,
            },
            {
                "strategy_group_id": "BTPC-001",
                "fixture_case": "missing_derivatives_context",
                "signal_status": "would_enter_missing_required_facts",
                "review_recommendation": "revise",
                "real_order_allowed": False,
                "exchange_write_allowed": False,
                "operation_layer_submit_allowed": False,
            },
        ],
        "safety_invariants": {
            "server_files_mutated": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "exchange_write_called": False,
        },
    }


def _btpc_handoff() -> dict:
    return {
        "status": "l2_intake_contract_observe_only",
        "execution_boundary": {
            "final_gate_input": False,
            "operation_layer_input": False,
            "real_submit_authorized": False,
        },
        "risk_defaults": {
            "risk_tier": "not_live_order_eligible",
            "max_notional_per_action_usdt": "0",
            "max_active_positions": 0,
        },
    }


def test_btpc_l2_shadow_fact_quality_review_classifies_current_gaps() -> None:
    module = _load_module()

    packet = module.build_btpc_l2_shadow_fact_quality_review(
        opportunity_decision_loop_packet=_opportunity_decision_loop(),
        l2_readiness_packet=_l2_readiness(),
        replay_lab_packet=_replay_lab(),
        btpc_handoff=_btpc_handoff(),
    )

    assert packet["status"] == "btpc_l2_shadow_fact_quality_review_ready"
    assert packet["counts"]["fact_gap_count"] == 5
    assert packet["counts"]["classified_fact_gap_count"] == 5
    assert packet["counts"]["fact_source_pending_count"] == 4
    assert packet["counts"]["strategy_review_pending_count"] == 1
    assert packet["counts"]["promotion_blocker_count"] == 5
    assert packet["counts"]["real_order_eligibility_blocker_count"] == 1
    assert packet["counts"]["missing_derivatives_context_case_count"] == 1
    assert packet["counts"]["real_order_authorized_count"] == 0
    assert packet["counts"]["l4_scope_change_recommended_count"] == 0
    assert packet["btpc_state"]["l2_shadow_observation_enabled"] is True
    assert packet["btpc_state"]["replay_covered"] is True
    assert packet["btpc_state"]["handoff_boundary_ok"] is True

    rows = {row["gap"]: row for row in packet["fact_rows"]}
    assert rows["historical_open_interest_window_missing"]["required_fact"] == (
        "historical_open_interest_window"
    )
    assert rows["historical_open_interest_window_missing"]["boundary_effect"] == (
        "blocks_promotion_beyond_l2_review"
    )
    assert rows["real_exchange_margin_liquidation_model_missing"][
        "boundary_effect"
    ] == "blocks_any_btpc_real_order_eligibility"
    assert rows["short_squeeze_risk_not_runtime_blocking"]["boundary_effect"] == (
        "strategy_review_pending_not_runtime_blocking"
    )
    assert all(row["shadow_observation_can_continue"] is True for row in rows.values())
    assert all(row["real_order_authority"] is False for row in rows.values())
    assert all(row["l4_scope_change_recommended"] is False for row in rows.values())

    assert packet["decision"]["l2_shadow_observation_can_continue"] is True
    assert packet["decision"]["tier_policy_change_recommended_now"] is False
    assert packet["decision"]["l2_promotion_recommended_now"] is False
    assert packet["decision"]["l4_scope_change_recommended"] is False
    assert packet["decision"]["real_order_scope_change_recommended"] is False
    assert packet["decision"]["default_next_step"] == (
        "attach_btpc_derivatives_fact_sources_and_margin_model_for_l2_quality_review"
    )
    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["interaction"]["approaches_real_order"] is False
    assert packet["interaction"]["calls_finalgate"] is False
    assert packet["interaction"]["calls_operation_layer"] is False
    assert packet["interaction"]["calls_exchange_write"] is False
    assert packet["interaction"]["places_order"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_btpc_l2_shadow_fact_quality_review_blocks_forbidden_source_effects() -> None:
    module = _load_module()
    handoff = _btpc_handoff()
    handoff["execution_boundary"]["real_submit_authorized"] = True

    packet = module.build_btpc_l2_shadow_fact_quality_review(
        opportunity_decision_loop_packet=_opportunity_decision_loop(),
        l2_readiness_packet=_l2_readiness(),
        replay_lab_packet=_replay_lab(),
        btpc_handoff=handoff,
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert "btpc_handoff.execution_boundary.real_submit_authorized" in packet[
        "safety_invariants"
    ]["source_forbidden_effects"]
    assert packet["decision"]["default_next_step"] == (
        "stop_and_repair_btpc_fact_quality_source_forbidden_effects"
    )
    assert packet["operator_command_plan"]["places_order"] is False


def test_btpc_l2_shadow_fact_quality_review_cli_writes_outputs(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_module()
    decision_path = tmp_path / "decision.json"
    readiness_path = tmp_path / "readiness.json"
    replay_path = tmp_path / "replay.json"
    handoff_path = tmp_path / "handoff.json"
    output_path = tmp_path / "btpc-review.json"
    owner_path = tmp_path / "btpc-review.md"
    decision_path.write_text(json.dumps(_opportunity_decision_loop()), encoding="utf-8")
    readiness_path.write_text(json.dumps(_l2_readiness()), encoding="utf-8")
    replay_path.write_text(json.dumps(_replay_lab()), encoding="utf-8")
    handoff_path.write_text(json.dumps(_btpc_handoff()), encoding="utf-8")

    exit_code = module.main(
        [
            "--opportunity-decision-loop-json",
            str(decision_path),
            "--l2-readiness-json",
            str(readiness_path),
            "--replay-lab-json",
            str(replay_path),
            "--btpc-handoff-json",
            str(handoff_path),
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
    assert file_payload["scope"] == "btpc_l2_shadow_fact_quality_review"
    assert file_payload["status"] == "btpc_l2_shadow_fact_quality_review_ready"
    owner_text = owner_path.read_text(encoding="utf-8")
    assert "BTPC L2 Shadow Fact Quality Review" in owner_text
    assert "historical_open_interest_window_missing" in owner_text
    assert "blocks_any_btpc_real_order_eligibility" in owner_text
