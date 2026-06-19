from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "build_strategygroup_btpc_l2_keep_revise_fact_source_decision.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_btpc_l2_keep_revise_fact_source_decision",
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
        "decision": {
            "btpc_proxy_replay_quality_ready": True,
            "l4_promotion_recommended": False,
            "real_order_scope_change_recommended": False,
            "default_next_step": "feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_decision",
        },
        "interaction": {
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
        "strategy_quality_decisions": {
            "status": "ready",
            "rows": [
                {
                    "strategy_group_id": "BTPC-001",
                    "current_tier": "L2",
                    "tier_state": "l2_shadow_candidate_observation_enabled",
                    "strategy_quality_decision": "keep_l2_shadow_and_revise_fact_classifier_inputs",
                    "next_stage": "feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_decision",
                    "real_order_authority": False,
                    "candidate_or_finalgate_authority": False,
                    "not_l4_scope_change": True,
                    "btpc_proxy_replay_quality": {
                        "ready": True,
                        "status": "btpc_proxy_replay_quality_review_ready",
                        "case_count": 5,
                        "proxy_reviewable_would_enter_count": 2,
                        "revise_case_count": 3,
                        "live_required_facts_satisfied": False,
                        "real_order_authority": False,
                        "l4_scope_change_recommended": False,
                        "action_items": [
                            "attach_live_derivatives_fact_sources_before_btpc_live_eligibility",
                            "review_btpc_strong_uptrend_conflict_disable_rule",
                            "review_btpc_freshness_or_classifier_stale_signal_rule",
                            "continue_btpc_l2_shadow_observation_with_proxy_context",
                        ],
                    },
                }
            ],
        },
    }


def _proxy_quality() -> dict:
    return {
        "status": "btpc_proxy_replay_quality_review_ready",
        "decision": {
            "proxy_replay_quality_review_ready": True,
            "proxy_replay_satisfies_live_required_facts": False,
            "l4_scope_change_recommended": False,
            "real_order_scope_change_recommended": False,
        },
        "case_rows": [
            _case(
                "bear_pullback_would_enter",
                "keep_observing_l2_shadow_with_proxy_context",
            ),
            _case(
                "missing_derivatives_context",
                "revise_live_fact_collection_but_l2_proxy_reviewable",
            ),
            _case(
                "strong_uptrend_conflict",
                "revise_conflict_disable_before_l2_promotion",
            ),
            _case(
                "stale_signal",
                "revise_freshness_or_classifier_before_l2_promotion",
            ),
        ],
        "interaction": {
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
    }


def _case(fixture_case: str, decision: str) -> dict:
    return {
        "fixture_case": fixture_case,
        "proxy_replay_quality_decision": decision,
        "live_required_facts_satisfied": False,
        "l2_promotion_authority": False,
        "l4_scope_change_recommended": False,
        "real_order_authority": False,
        "candidate_or_finalgate_authority": False,
        "operation_layer_authority": False,
        "exchange_write_authority": False,
    }


def test_btpc_l2_decision_turns_proxy_quality_into_action_rows() -> None:
    module = _load_module()

    packet = module.build_btpc_l2_keep_revise_fact_source_decision(
        opportunity_decision_loop_packet=_opportunity_decision_loop(),
        btpc_proxy_replay_quality_packet=_proxy_quality(),
    )

    assert packet["status"] == "btpc_l2_keep_revise_fact_source_decision_ready"
    assert packet["counts"]["action_item_count"] == 4
    assert packet["counts"]["live_fact_source_action_count"] == 1
    assert packet["counts"]["classifier_rule_action_count"] == 2
    assert packet["counts"]["observation_action_count"] == 1
    assert packet["counts"]["proxy_replay_case_count"] == 5
    assert packet["counts"]["proxy_reviewable_would_enter_count"] == 2
    assert packet["counts"]["revise_case_count"] == 3
    assert packet["decision"]["keep_l2_shadow_observation"] is True
    assert packet["decision"]["attach_live_fact_sources_before_live_eligibility"] is True
    assert packet["decision"]["classifier_review_required_before_promotion"] is True
    assert packet["decision"]["proxy_decision_satisfies_live_required_facts"] is False
    assert packet["decision"]["l2_promotion_recommended_now"] is False
    assert packet["decision"]["l4_scope_change_recommended"] is False
    assert packet["decision"]["real_order_scope_change_recommended"] is False

    rows = {row["action"]: row for row in packet["action_rows"]}
    assert rows[
        "attach_live_derivatives_fact_sources_before_btpc_live_eligibility"
    ]["evidence_cases"] == ["missing_derivatives_context"]
    assert rows["review_btpc_strong_uptrend_conflict_disable_rule"][
        "evidence_cases"
    ] == ["strong_uptrend_conflict"]
    assert rows["review_btpc_freshness_or_classifier_stale_signal_rule"][
        "evidence_cases"
    ] == ["stale_signal"]
    assert rows["continue_btpc_l2_shadow_observation_with_proxy_context"][
        "evidence_cases"
    ] == ["bear_pullback_would_enter"]
    assert all(row["real_order_authority"] is False for row in packet["action_rows"])
    assert all(
        row["candidate_or_finalgate_authority"] is False
        for row in packet["action_rows"]
    )
    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["interaction"]["calls_operation_layer"] is False
    assert packet["interaction"]["calls_exchange_write"] is False
    assert packet["interaction"]["places_order"] is False
    assert packet["safety_invariants"]["does_not_lower_owner_selected_leverage"] is True
    assert (
        packet["safety_invariants"]["does_not_change_live_profile_or_sizing_defaults"]
        is True
    )


def test_btpc_l2_decision_blocks_live_authority_from_sources() -> None:
    module = _load_module()
    opportunity = _opportunity_decision_loop()
    opportunity["strategy_quality_decisions"]["rows"][0]["real_order_authority"] = True

    packet = module.build_btpc_l2_keep_revise_fact_source_decision(
        opportunity_decision_loop_packet=opportunity,
        btpc_proxy_replay_quality_packet=_proxy_quality(),
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert (
        "btpc_quality_row.real_order_authority"
        in packet["safety_invariants"]["source_forbidden_effects"]
    )
    assert packet["decision"]["default_next_step"] == (
        "stop_and_repair_btpc_l2_decision_source_forbidden_effects"
    )
    assert packet["operator_command_plan"]["places_order"] is False


def test_btpc_l2_decision_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    module = _load_module()
    opportunity_path = tmp_path / "opportunity.json"
    proxy_path = tmp_path / "proxy.json"
    output_path = tmp_path / "decision.json"
    owner_path = tmp_path / "decision.md"
    opportunity_path.write_text(json.dumps(_opportunity_decision_loop()), encoding="utf-8")
    proxy_path.write_text(json.dumps(_proxy_quality()), encoding="utf-8")

    exit_code = module.main(
        [
            "--opportunity-decision-loop-json",
            str(opportunity_path),
            "--btpc-proxy-replay-quality-json",
            str(proxy_path),
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
    assert file_payload["scope"] == "btpc_l2_keep_revise_fact_source_decision"
    assert file_payload["status"] == "btpc_l2_keep_revise_fact_source_decision_ready"
    owner_text = owner_path.read_text(encoding="utf-8")
    assert "BTPC L2 Keep / Revise / Fact Source Decision" in owner_text
