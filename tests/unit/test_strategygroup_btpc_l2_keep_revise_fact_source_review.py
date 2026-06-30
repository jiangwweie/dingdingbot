from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "build_strategygroup_btpc_l2_keep_revise_fact_source_review.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_btpc_l2_keep_revise_fact_source_review",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _opportunity_review_work_loop() -> dict:
    return {
        "status": "review_work_loop_ready",
        "review_outcome_state": {
            "state_family": "Review Outcome State",
            "source_role": "signal_observation_work_queue_provenance",
            "tradeability_decision_source": False,
            "btpc_proxy_replay_quality_ready": True,
            "l4_promotion_recommended": False,
            "real_order_scope_change_recommended": False,
            "default_next_step": "feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_review",
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
        "strategy_asset_recommendations": {
            "status": "ready",
            "rows": [
                {
                    "strategy_group_id": "BTPC-001",
                    "current_tier": "L2",
                    "tier_state": "l2_shadow_candidate_observation_enabled",
                    "strategy_asset_recommendation": "keep_l2_shadow_and_revise_fact_classifier_inputs",
                    "next_stage": "feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_review",
                    "candidate_or_finalgate_authority": False,
                    "not_l4_scope_change": True,
                    "btpc_proxy_replay_quality": {
                        "ready": True,
                        "status": "btpc_proxy_replay_quality_review_ready",
                        "case_count": 5,
                        "proxy_reviewable_would_enter_count": 2,
                        "revise_case_count": 3,
                        "live_required_facts_satisfied": False,
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
        "review_outcome_state": {
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
        "proxy_replay_quality_review_outcome": decision,
        "live_required_facts_satisfied": False,
        "l2_promotion_authority": False,
        "l4_scope_change_recommended": False,
        "candidate_or_finalgate_authority": False,
        "operation_layer_authority": False,
        "exchange_write_authority": False,
    }


def test_btpc_l2_review_turns_proxy_quality_into_action_rows() -> None:
    module = _load_module()

    packet = module.build_btpc_l2_keep_revise_fact_source_review(
        opportunity_review_work_loop_artifact=_opportunity_review_work_loop(),
        btpc_proxy_replay_quality_artifact=_proxy_quality(),
    )

    assert packet["status"] == "btpc_l2_keep_revise_fact_source_review_ready"
    assert packet["counts"]["action_item_count"] == 4
    assert packet["counts"]["live_fact_source_action_count"] == 1
    assert packet["counts"]["classifier_rule_action_count"] == 2
    assert packet["counts"]["observation_action_count"] == 1
    assert packet["counts"]["proxy_replay_case_count"] == 5
    assert packet["counts"]["proxy_reviewable_would_enter_count"] == 2
    assert packet["counts"]["revise_case_count"] == 3
    assert "real_order_authorized_count" not in packet["counts"]
    assert "real_order_authority" not in packet["btpc_state"]
    assert "decision" not in packet
    review_outcome = packet["review_outcome_state"]
    assert review_outcome["state_family"] == "Review Outcome State"
    assert review_outcome["source_role"] == "btpc_l2_keep_revise_fact_source_provenance"
    assert review_outcome["tradeability_decision_source"] is False
    assert review_outcome["keep_l2_shadow_observation"] is True
    assert review_outcome["attach_live_fact_sources_before_live_eligibility"] is True
    assert review_outcome["classifier_review_required_before_promotion"] is True
    assert review_outcome["proxy_review_satisfies_live_required_facts"] is False
    assert review_outcome["l2_promotion_recommended_now"] is False
    assert review_outcome["l4_scope_change_recommended"] is False
    assert review_outcome["real_order_scope_change_recommended"] is False

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
    assert all("real_order_authority" not in row for row in packet["action_rows"])
    assert all(
        row["candidate_or_finalgate_authority"] is False
        for row in packet["action_rows"]
    )
    assert all(row["operation_layer_authority"] is False for row in packet["action_rows"])
    assert all(row["exchange_write_authority"] is False for row in packet["action_rows"])
    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["interaction"]["calls_operation_layer"] is False
    assert packet["interaction"]["calls_exchange_write"] is False
    assert packet["interaction"]["places_order"] is False
    assert packet["safety_invariants"]["local_btpc_l2_review_outcome_only"] is True
    assert packet["safety_invariants"]["proxy_review_is_not_live_required_fact"] is True
    assert packet["safety_invariants"]["does_not_lower_owner_selected_leverage"] is True
    assert (
        packet["safety_invariants"]["does_not_change_live_profile_or_sizing_defaults"]
        is True
    )
    assert "operator_command_plan" not in packet
    assert "execution_intent_created" not in packet["safety_invariants"]


def test_btpc_l2_review_blocks_live_authority_from_sources() -> None:
    module = _load_module()
    opportunity = _opportunity_review_work_loop()
    opportunity["strategy_asset_recommendations"]["rows"][0][
        "candidate_or_finalgate_authority"
    ] = True

    packet = module.build_btpc_l2_keep_revise_fact_source_review(
        opportunity_review_work_loop_artifact=opportunity,
        btpc_proxy_replay_quality_artifact=_proxy_quality(),
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert (
        "btpc_quality_row.candidate_or_finalgate_authority"
        in packet["safety_invariants"]["source_forbidden_effects"]
    )
    assert packet["review_outcome_state"]["default_next_step"] == (
        "stop_and_repair_btpc_l2_review_outcome_source_forbidden_effects"
    )
    assert packet["interaction"]["places_order"] is False
    assert packet["safety_invariants"]["order_created"] is False


def test_btpc_l2_review_blocks_scope_change_from_opportunity_review_outcome() -> None:
    module = _load_module()
    opportunity = _opportunity_review_work_loop()
    opportunity["review_outcome_state"]["real_order_scope_change_recommended"] = True

    packet = module.build_btpc_l2_keep_revise_fact_source_review(
        opportunity_review_work_loop_artifact=opportunity,
        btpc_proxy_replay_quality_artifact=_proxy_quality(),
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert (
        "opportunity_review_outcome.real_order_scope_change_recommended"
        in packet["safety_invariants"]["source_forbidden_effects"]
    )


def test_btpc_l2_review_rejects_source_legacy_authority_mirror_fields() -> None:
    module = _load_module()
    opportunity = _opportunity_review_work_loop()
    opportunity["safety_invariants"]["real_order_authority"] = False
    opportunity["strategy_asset_recommendations"]["rows"][0][
        "actionable_now"
    ] = False
    proxy = _proxy_quality()
    proxy["review_outcome_state"]["real_order_authority"] = False
    proxy["case_rows"][0]["actionable_now"] = False

    packet = module.build_btpc_l2_keep_revise_fact_source_review(
        opportunity_review_work_loop_artifact=opportunity,
        btpc_proxy_replay_quality_artifact=proxy,
    )

    assert packet["status"] == "blocked_forbidden_effect"
    effects = packet["safety_invariants"]["source_forbidden_effects"]
    assert (
        "opportunity_review_work_loop.safety_invariants."
        "legacy_authority_mirror_present:real_order_authority"
    ) in effects
    assert "btpc_quality_row.legacy_authority_mirror_present:actionable_now" in effects
    assert (
        "btpc_proxy_replay_quality.review_outcome_state."
        "legacy_authority_mirror_present:real_order_authority"
    ) in effects
    assert (
        "btpc_proxy_replay_quality.case_rows.bear_pullback_would_enter."
        "legacy_authority_mirror_present:actionable_now"
    ) in effects


def test_btpc_l2_review_rejects_legacy_packet_kwargs() -> None:
    module = _load_module()

    with pytest.raises(TypeError):
        module.build_btpc_l2_keep_revise_fact_source_review(
            opportunity_review_work_loop_packet=_opportunity_review_work_loop(),
            btpc_proxy_replay_quality_packet=_proxy_quality(),
        )


def test_btpc_l2_review_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    module = _load_module()
    opportunity_path = tmp_path / "opportunity.json"
    proxy_path = tmp_path / "proxy.json"
    output_path = tmp_path / "decision.json"
    owner_path = tmp_path / "decision.md"
    opportunity_path.write_text(json.dumps(_opportunity_review_work_loop()), encoding="utf-8")
    proxy_path.write_text(json.dumps(_proxy_quality()), encoding="utf-8")

    exit_code = module.main(
        [
            "--opportunity-review-work-loop-json",
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
    assert file_payload["scope"] == "btpc_l2_keep_revise_fact_source_review"
    assert file_payload["status"] == "btpc_l2_keep_revise_fact_source_review_ready"
    owner_text = owner_path.read_text(encoding="utf-8")
    assert "BTPC L2 Keep / Revise / Fact Source Review" in owner_text
    assert "Real order authority" not in owner_text
    assert "| Area | Action | Evidence | Exchange write |" in owner_text
    assert "| Area | Action | Evidence | Real order |" not in owner_text


def test_btpc_l2_review_cli_omitted_opportunity_does_not_read_default(
    tmp_path: Path,
):
    module = _load_module()
    proxy_path = tmp_path / "proxy.json"
    output_path = tmp_path / "decision.json"
    owner_path = tmp_path / "decision.md"
    proxy_path.write_text(json.dumps(_proxy_quality()), encoding="utf-8")

    exit_code = module.main(
        [
            "--btpc-proxy-replay-quality-json",
            str(proxy_path),
            "--output-json",
            str(output_path),
            "--output-owner-progress",
            str(owner_path),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_path.read_text(encoding="utf-8"))
    assert packet["status"] == "btpc_l2_review_waiting_for_proxy_quality_rollup"


def test_btpc_l2_review_cli_omitted_proxy_quality_does_not_read_default(
    tmp_path: Path,
):
    module = _load_module()
    opportunity_path = tmp_path / "opportunity.json"
    output_path = tmp_path / "decision.json"
    owner_path = tmp_path / "decision.md"
    opportunity_path.write_text(
        json.dumps(_opportunity_review_work_loop()), encoding="utf-8"
    )

    exit_code = module.main(
        [
            "--opportunity-review-work-loop-json",
            str(opportunity_path),
            "--output-json",
            str(output_path),
            "--output-owner-progress",
            str(owner_path),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_path.read_text(encoding="utf-8"))
    assert packet["status"] == "btpc_l2_keep_revise_fact_source_review_ready"
    assert packet["source_status"]["btpc_proxy_replay_quality_review"] is None
    assert all(row["evidence_cases"] == [] for row in packet["action_rows"])
