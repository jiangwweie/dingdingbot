from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_strategy_asset_state.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_strategy_asset_state",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _asset_rows(artifact: dict) -> list[dict]:
    return artifact["strategy_asset_state"]["asset_rows"]


def test_strategy_asset_state_normalize_does_not_fabricate_keep_observing() -> None:
    module = _load_module()

    invalid = module._normalize_asset_row(
        {
            "strategy_group_id": "BAD-001",
            "asset_decision": "unsupported_decision",
            "reason": "source emitted unsupported decision",
            "promotion_scope": "trial_admission",
            "promotion_target": "armed_observation",
        }
    )
    missing = module._normalize_asset_row(
        {
            "strategy_group_id": "MISS-001",
            "reason": "source omitted decision",
        }
    )

    assert invalid["asset_decision"] == "unknown"
    assert invalid["promotion_scope"] == "not_applicable"
    assert invalid["promotion_target"] == "not_applicable"
    assert "invalid_or_missing_decision:unsupported_decision" in invalid["reason"]
    assert missing["asset_decision"] == "unknown"
    assert "invalid_or_missing_decision:unknown" in missing["reason"]


def _opportunity_review_work_loop(*, forbidden: bool = False) -> dict:
    return {
        "status": "review_work_loop_ready",
        "strategy_asset_recommendations": {
            "rows": [
                {
                    "strategy_group_id": "BTPC-001",
                    "current_tier": "L2",
                    "strategy_asset_recommendation": (
                        "keep_l2_shadow_and_revise_fact_classifier_inputs"
                    ),
                    "reason": (
                        "btpc_proxy_replay_quality_ready_with_review_only_revisions"
                    ),
                    "next_stage": (
                        "feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_review"
                    ),
                    "evidence": {
                        "replay_sample_count": 5,
                        "would_enter_sample_count": 2,
                        "revise_sample_count": 3,
                        "fact_source_pending_item_count": 1,
                    },
                    "revision_completion": {
                        "status": "no_revision_required",
                        "completion_blockers": [],
                    },
                    "revision_execution": {
                        "status": "no_revision_execution_required",
                        "execution_blockers": [],
                    },
                    "not_l4_scope_change": True,
                    "candidate_or_finalgate_authority": False,
                },
                {
                    "strategy_group_id": "VCB-001",
                    "current_tier": "L1",
                    "strategy_asset_recommendation": "revise_before_l2",
                    "reason": "coverage_ready_but_revise_or_negative_evidence_present",
                    "next_stage": (
                        "record_revise_decision_and_keep_l1_until_review_passes"
                    ),
                    "evidence": {
                        "replay_sample_count": 5,
                        "would_enter_sample_count": 2,
                        "revise_sample_count": 1,
                    },
                    "revision_completion": {
                        "status": "local_revision_completion_ready",
                        "completion_blockers": [],
                    },
                    "revision_execution": {
                        "status": "local_revision_execution_complete",
                        "execution_blockers": [],
                    },
                    "not_l4_scope_change": True,
                    "candidate_or_finalgate_authority": False,
                },
                {
                    "strategy_group_id": "RBR-001",
                    "current_tier": "L1",
                    "strategy_asset_recommendation": "park_until_new_edge",
                    "reason": "parked_negative_or_low_quality_evidence",
                    "next_stage": "park_until_new_evidence",
                    "evidence": {
                        "replay_sample_count": 1,
                        "would_enter_sample_count": 0,
                        "revise_sample_count": 0,
                    },
                    "not_l4_scope_change": True,
                    "candidate_or_finalgate_authority": False,
                },
            ]
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
            "order_created": forbidden,
        },
    }


def _signal_coverage() -> dict:
    return {
        "status": "mainline_no_signal_broader_would_enter",
        "broader_observation": {
            "high_priority_no_action_signals": [
                {
                    "strategy_group_id": "BTPC-001",
                    "signal_type": "no_action",
                    "coverage_review_priority": "P0_5",
                    "human_summary": (
                        "BTPC v1 rejects stale shadow signals before any L2 promotion review."
                    ),
                    "reason_codes": ["btpc_disable_stale_signal_before_l2_review"],
                    "policy_l2_readiness": "l2_shadow_candidate_observation_enabled",
                    "policy_recommended_action": (
                        "continue_l2_shadow_candidate_observation_without_l4_scope_change"
                    ),
                },
                {
                    "strategy_group_id": "LSR-001",
                    "signal_type": "no_action",
                    "coverage_review_priority": "P1",
                    "human_summary": (
                        "LSR v1 disables the old long sweep preview until the short-revival rewrite passes review."
                    ),
                    "reason_codes": [
                        "lsr_disable_long_preview_conflicts_with_short_revival_lead"
                    ],
                    "policy_l2_readiness": "blocked_rewrite_required",
                    "policy_recommended_action": (
                        "keep_l1_observe_only_until_side_specific_rewrite_handoff_exists"
                    ),
                },
            ]
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
    }


def _tier_policy() -> dict:
    return {
        "current_strategy_groups": {
            "BTPC-001": {"tier": "L2"},
            "VCB-001": {"tier": "L1"},
            "RBR-001": {"tier": "L1"},
        },
        "new_strategy_group_defaults": {"known_new_groups": {"LSR": "L1"}},
    }


def _post_revision_replay_review() -> dict:
    return {
        "status": "passed",
        "review_rows": [
            {
                "strategy_group_id": "BRF-001",
                "fixture_case": "bear_rally_failure_short_would_enter",
                "passed": True,
            },
            {
                "strategy_group_id": "LSR-001",
                "fixture_case": "short_revival_short_would_enter",
                "passed": True,
            },
            {
                "strategy_group_id": "VCB-001",
                "fixture_case": "false_breakout_reversal_disabled",
                "passed": True,
            },
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
            "server_files_mutated": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
        },
    }


def _capture_gap_audit() -> dict:
    return {
        "schema": "brc.strategy_capture_gap_audit.v3",
        "status": "strategy_capture_gap_audit_ready",
        "system_observation_summary": {
            "would_enter_count": 44,
            "high_priority_no_action_count": 671,
        },
        "observation_recommendations": [
            {
                "strategy_group_id": "BRF-001",
                "observation_recommendation": "promote_review",
                "reason": "official windows produced BRF would_enter",
                "next_checkpoint": "BRF-001_forward_outcome_and_requiredfacts_review",
            },
            {
                "strategy_group_id": "MI-001",
                "observation_recommendation": "identity_review",
                "reason": "MI emits repeated would_enter events",
                "next_checkpoint": "MI-001_registry_identity_review",
            },
            {
                "strategy_group_id": "LSR-001",
                "observation_recommendation": "revise",
                "reason": "side-specific rewrite remains the dominant blocker",
                "next_checkpoint": "LSR-001_classifier_fact_source_revision_review",
            },
            {
                "strategy_group_id": "MPG-001",
                "observation_recommendation": "coverage_visibility_review",
                "reason": "mainline no_action should stay visible",
                "next_checkpoint": "MPG-001_no_action_visibility_and_routing_audit",
            },
        ],
        "priority_line_closure": {
            "phase2_priority_strategy_lines": [
                    {
                        "strategy_group_id": "BRF-001",
                        "observation_recommendation": "promote_review",
                        "would_enter_count": 1,
                    "high_priority_no_action_count": 168,
                    "would_enter_forward_positive_count": 0,
                    "missed_no_action_forward_positive_count": 136,
                },
                    {
                        "strategy_group_id": "LSR-001",
                        "observation_recommendation": "revise",
                    "would_enter_count": 2,
                    "high_priority_no_action_count": 167,
                    "would_enter_forward_positive_count": 2,
                    "missed_no_action_forward_positive_count": 0,
                }
            ],
            "phase3_registry_identity_review": [
                    {
                        "strategy_group_id": "MI-001",
                        "observation_recommendation": "identity_review",
                    "would_enter_count": 23,
                    "high_priority_no_action_count": 0,
                    "would_enter_forward_positive_count": 22,
                    "missed_no_action_forward_positive_count": 0,
                }
            ],
            "phase4_visibility_review": [
                    {
                        "strategy_group_id": "MPG-001",
                        "observation_recommendation": "coverage_visibility_review",
                    "would_enter_count": 0,
                    "high_priority_no_action_count": 0,
                    "would_enter_forward_positive_count": 0,
                    "missed_no_action_forward_positive_count": 0,
                }
            ],
        },
        "owner_visibility_state": {
            "p0_state": "waiting_for_market",
            "signal_observation_state": "review_needed",
            "no_live_permission": True,
            "owner_intervention_required": False,
        },
        "safety_invariants": {
            "server_files_mutated": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
    }


def _research_intake_review() -> dict:
    return {
        "schema": "brc.strategygroup_research_intake_review.v1",
        "status": "research_intake_review_ready",
        "summary": {
            "candidate_count": 2,
            "paper_observation_admission_candidate_count": 1,
            "role_only_intake_candidate_count": 1,
            "actionable_now_count": 0,
            "real_order_authority_count": 0,
        },
        "strategy_decision_provenance_rows": [
            {
                "strategy_group_id": "BRF2-001",
                "tier": "unknown",
                "opportunity_type": "research_intake",
                "current_decision": "promote",
                "promotion_scope": "intake_only",
                "promotion_target": "paper_observation_or_experiment_evidence",
                "reason": (
                    "research_intake:paper_observation_admission_candidate; "
                    "main_control_absorbs_asset_not_execution_authority"
                ),
                "required_next_evidence": (
                    "paper_observation_evidence_shape_requiredfacts_disable_facts_and_review_ledger_mapping"
                ),
                "authority_boundary": (
                    "main_control_research_intake_review_only; "
                    "promotion_scope=intake_only; no_official_live_order_authority"
                ),
                "next_checkpoint": "BRF2-001_paper_observation_admission_evidence",
            },
            {
                "strategy_group_id": "RBR2-001",
                "tier": "unknown",
                "opportunity_type": "research_intake",
                "current_decision": "keep_observing",
                "promotion_scope": "not_applicable",
                "promotion_target": "not_applicable",
                "reason": (
                    "research_intake:role_only_intake_candidate; "
                    "main_control_absorbs_asset_not_execution_authority"
                ),
                "required_next_evidence": (
                    "range_detector_facts_and_failed_upside_expansion_classifier_merge_review"
                ),
                "authority_boundary": (
                    "main_control_research_intake_review_only; "
                    "no_official_live_order_authority"
                ),
                "next_checkpoint": (
                    "RBR2-001_role_only_range_detector_classifier_merge_note"
                ),
            },
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
            "server_files_mutated": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
            "tier_policy_changed": False,
            "live_profile_changed": False,
            "actionable_now": False,
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_strategy_asset_state_outputs_one_minimal_row_per_strategygroup():
    module = _load_module()

    artifact = module.build_strategygroup_strategy_asset_state(
        opportunity_review_work_loop_artifact=_opportunity_review_work_loop(),
        signal_coverage_artifact=_signal_coverage(),
        tier_policy=_tier_policy(),
    )

    assert artifact["schema"] == "brc.strategygroup_strategy_asset_state.v1"
    assert artifact["scope"] == "strategygroup_strategy_asset_state"
    assert artifact["status"] == "strategy_asset_state_ready"
    assert artifact["counts"]["current_row_count"] == 4
    assert "decision" not in artifact
    assert "source_row_fields" not in artifact
    rows = {row["strategy_group_id"]: row for row in _asset_rows(artifact)}
    assert list(rows["BTPC-001"].keys()) == artifact["required_asset_row_fields"]
    assert rows["BTPC-001"]["current_decision"] == "revise"
    assert rows["BTPC-001"]["opportunity_type"] == "would_enter"
    assert "no_action:" in rows["BTPC-001"]["reason"]
    assert rows["VCB-001"]["current_decision"] == "revise"
    assert rows["RBR-001"]["current_decision"] == "park"
    assert rows["LSR-001"]["current_decision"] == "revise"
    assert rows["LSR-001"]["opportunity_type"] == "no_action"
    assert "tier_review" not in artifact
    asset_state = artifact["strategy_asset_state"]
    assert asset_state["state_family"] == "Strategy Asset State"
    assert asset_state["primary_judgment_source"] is True
    assert asset_state["tradeability_decision_source"] is False
    assert asset_state["one_current_row_per_strategy_group"] is True
    assert asset_state["raw_replay_samples_duplicated"] is False
    assert asset_state["no_action_attribution_is_field_input_only"] is True
    assert "replay_decision_bridge_is_field_input_only" not in asset_state
    assert asset_state["asset_count"] == len(_asset_rows(artifact))
    assert "compatibility_sections" not in asset_state
    asset_rows = {
        row["strategy_group_id"]: row
        for row in asset_state["asset_rows"]
    }
    assert asset_rows["BTPC-001"]["stage"] == "revision_required"
    assert asset_rows["BTPC-001"]["current_decision"] == "revise"
    assert "actionable_now" not in asset_rows["BTPC-001"]
    assert "real_order_authority" not in asset_rows["BTPC-001"]
    assert "no_l4_scope_change" in asset_rows["BTPC-001"]["authority_boundary"]
    assert artifact["interaction"]["remote_interaction_count"] == 0
    assert artifact["interaction"]["places_order"] is False
    assert artifact["interaction"]["level"] == "L0_local_strategy_asset_state"
    assert artifact["safety_invariants"]["local_strategy_asset_state_only"] is True
    assert artifact["safety_invariants"]["order_created"] is False
    assert "execution_intent_created" not in artifact["safety_invariants"]


def test_strategy_asset_state_rolls_completed_revision_rows_to_observation() -> None:
    module = _load_module()
    opportunity = _opportunity_review_work_loop()
    signal = _signal_coverage()
    signal["broader_observation"]["high_priority_no_action_signals"].extend(
        [
            {
                "strategy_group_id": "BRF-001",
                "signal_type": "no_action",
                "coverage_review_priority": "P0_5",
                "human_summary": "BRF waits for rally-failure and squeeze-risk review.",
                "reason_codes": ["brf_no_action_no_rally_extension"],
                "policy_l2_readiness": "blocked_requiredfacts_and_squeeze_classifier_needed",
                "policy_recommended_action": (
                    "keep_l1_observe_only_until_rally_failure_context_and_short_squeeze_classifier_are_attached"
                ),
            },
        ]
    )

    artifact = module.build_strategygroup_strategy_asset_state(
        opportunity_review_work_loop_artifact=opportunity,
        signal_coverage_artifact=signal,
        tier_policy=_tier_policy(),
        post_revision_replay_artifact=_post_revision_replay_review(),
    )

    rows = {row["strategy_group_id"]: row for row in _asset_rows(artifact)}
    assert rows["VCB-001"]["current_decision"] == "keep_observing"
    assert rows["VCB-001"]["required_next_evidence"] == (
        "tier_review_after_post_revision_quality"
    )
    assert rows["VCB-001"]["next_checkpoint"] == (
        "run_post_revision_stage_review_before_any_l2_or_l4_scope_change"
    )
    assert rows["VCB-001"]["reason"].endswith("post_revision_replay_passed:1_cases")
    assert rows["LSR-001"]["current_decision"] == "keep_observing"
    assert rows["BRF-001"]["current_decision"] == "keep_observing"
    assert artifact["strategy_asset_state"]["default_next_step"] == (
        "run_post_revision_stage_review_before_any_tier_policy_change"
    )
    assert "tier_review" not in artifact
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_strategy_asset_state_blocks_forbidden_source_effect():
    module = _load_module()

    artifact = module.build_strategygroup_strategy_asset_state(
        opportunity_review_work_loop_artifact=_opportunity_review_work_loop(forbidden=True),
        signal_coverage_artifact=_signal_coverage(),
        tier_policy=_tier_policy(),
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    assert "opportunity_review_work_loop_artifact.safety_invariants.order_created" in artifact[
        "safety_invariants"
    ]["source_forbidden_effects"]
    assert artifact["interaction"]["places_order"] is False


def test_strategy_asset_state_rejects_legacy_packet_source_kwargs():
    module = _load_module()

    with pytest.raises(TypeError):
        module.build_strategygroup_strategy_asset_state(
            opportunity_review_work_loop_packet=_opportunity_review_work_loop(),
            signal_coverage_artifact=_signal_coverage(),
            tier_policy=_tier_policy(),
        )


def test_strategy_asset_state_integrates_capture_gap_audit_as_review_input_only():
    module = _load_module()

    artifact = module.build_strategygroup_strategy_asset_state(
        opportunity_review_work_loop_artifact=_opportunity_review_work_loop(),
        signal_coverage_artifact=_signal_coverage(),
        tier_policy=_tier_policy(),
        post_revision_replay_artifact=_post_revision_replay_review(),
        capture_gap_audit_artifact=_capture_gap_audit(),
    )

    rows = {row["strategy_group_id"]: row for row in _asset_rows(artifact)}
    assert rows["BRF-001"]["current_decision"] == "promote"
    assert rows["BRF-001"]["promotion_scope"] == "trial_admission"
    assert rows["BRF-001"]["promotion_target"] == (
        "promotion_evidence_review_only"
    )
    assert rows["BRF-001"]["required_next_evidence"].startswith(
        "promotion_evidence_review_only:"
    )
    assert rows["MI-001"]["current_decision"] == "revise"
    assert rows["MI-001"]["required_next_evidence"].startswith(
        "registry_identity_classification:"
    )
    assert rows["LSR-001"]["current_decision"] == "revise"
    assert rows["LSR-001"]["required_next_evidence"].startswith(
        "classifier_fact_source_revision_review:"
    )
    assert rows["MPG-001"]["current_decision"] == "keep_observing"
    assert (
        "source_recommendation:coverage_visibility_review"
        in rows["MPG-001"]["reason"]
    )
    assert artifact["counts"]["capture_gap_audit_group_count"] == 4
    assert artifact["capture_gap_audit"]["integrated"] is True
    assert artifact["capture_gap_audit"]["owner_policy_confirmation_required_now"] is False
    assert artifact["capture_gap_audit"]["live_permission_change_recommended_now"] is False
    assert (
        artifact["strategy_asset_state"]["capture_gap_audit_is_decision_support_only"]
        is True
    )
    assert artifact["strategy_asset_state"]["real_order_scope_change_recommended"] is False
    assert artifact["strategy_asset_state"]["l4_promotion_recommended"] is False
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_strategy_asset_state_does_not_default_missing_capture_gap_recommendation_to_keep_observing():
    module = _load_module()
    capture_gap = json.loads(json.dumps(_capture_gap_audit()))
    capture_gap["observation_recommendations"].append(
        {
            "strategy_group_id": "MISS-CG-001",
            "reason": "source omitted observation recommendation",
            "next_checkpoint": "MISS-CG-001_capture_gap_review",
        }
    )
    capture_gap["priority_line_closure"]["phase4_visibility_review"].append(
        {
            "strategy_group_id": "MISS-CG-001",
            "would_enter_count": 0,
            "high_priority_no_action_count": 1,
            "would_enter_forward_positive_count": 0,
            "missed_no_action_forward_positive_count": 0,
        }
    )

    artifact = module.build_strategygroup_strategy_asset_state(
        opportunity_review_work_loop_artifact=_opportunity_review_work_loop(),
        signal_coverage_artifact=_signal_coverage(),
        tier_policy=_tier_policy(),
        capture_gap_audit_artifact=capture_gap,
    )

    rows = {row["strategy_group_id"]: row for row in _asset_rows(artifact)}
    assert rows["MPG-001"]["current_decision"] == "keep_observing"
    assert rows["MISS-CG-001"]["current_decision"] == "unknown"
    assert rows["MISS-CG-001"]["current_decision"] != "keep_observing"
    assert "source_recommendation:missing_observation_recommendation" in rows[
        "MISS-CG-001"
    ]["reason"]


def test_strategy_asset_state_does_not_default_unknown_quality_decision_to_keep_observing():
    module = _load_module()
    opportunity = json.loads(json.dumps(_opportunity_review_work_loop()))
    opportunity["strategy_asset_recommendations"]["rows"].append(
        {
            "strategy_group_id": "MISS-QD-001",
            "current_tier": "L1",
            "strategy_asset_recommendation": "unsupported_quality_route",
            "reason": "source emitted unsupported quality decision",
            "next_stage": "manual_quality_route_classification",
            "evidence": {
                "replay_sample_count": 1,
                "would_enter_sample_count": 0,
                "revise_sample_count": 0,
            },
            "not_l4_scope_change": True,
            "candidate_or_finalgate_authority": False,
        }
    )

    artifact = module.build_strategygroup_strategy_asset_state(
        opportunity_review_work_loop_artifact=opportunity,
        signal_coverage_artifact=_signal_coverage(),
        tier_policy=_tier_policy(),
    )

    rows = {row["strategy_group_id"]: row for row in _asset_rows(artifact)}
    assert rows["MISS-QD-001"]["current_decision"] == "unknown"
    assert rows["MISS-QD-001"]["current_decision"] != "keep_observing"
    assert (
        "source_strategy_asset_recommendation:unsupported:unsupported_quality_route"
        in rows["MISS-QD-001"]["reason"]
    )
    assert rows["BTPC-001"]["current_decision"] == "revise"


def test_strategy_asset_state_does_not_default_empty_no_action_policy_to_keep_observing():
    module = _load_module()
    signal = json.loads(json.dumps(_signal_coverage()))
    signal["broader_observation"]["high_priority_no_action_signals"].append(
        {
            "strategy_group_id": "MISS-NA-001",
            "signal_type": "no_action",
            "coverage_review_priority": "P0_5",
        }
    )

    artifact = module.build_strategygroup_strategy_asset_state(
        opportunity_review_work_loop_artifact={"strategy_asset_recommendations": {"rows": []}},
        signal_coverage_artifact=signal,
        tier_policy=_tier_policy(),
    )

    rows = {row["strategy_group_id"]: row for row in _asset_rows(artifact)}
    assert rows["MISS-NA-001"]["current_decision"] == "unknown"
    assert rows["MISS-NA-001"]["current_decision"] != "keep_observing"
    assert (
        "source_no_action_policy:missing_policy_recommended_action_readiness_and_reason_codes"
        in rows["MISS-NA-001"]["reason"]
    )
    assert rows["BTPC-001"]["current_decision"] == "keep_observing"


def test_strategy_asset_state_integrates_research_intake_review_as_review_input_only():
    module = _load_module()

    artifact = module.build_strategygroup_strategy_asset_state(
        opportunity_review_work_loop_artifact=_opportunity_review_work_loop(),
        signal_coverage_artifact=_signal_coverage(),
        tier_policy=_tier_policy(),
        research_intake_review_artifact=_research_intake_review(),
    )

    rows = {row["strategy_group_id"]: row for row in _asset_rows(artifact)}
    assert rows["BRF2-001"]["current_decision"] == "promote"
    assert all(
        "decision" not in row
        for row in _research_intake_review()["strategy_decision_provenance_rows"]
    )
    assert rows["BRF2-001"]["promotion_scope"] == "intake_only"
    assert rows["BRF2-001"]["promotion_target"] == (
        "paper_observation_or_experiment_evidence"
    )
    assert rows["BRF2-001"]["opportunity_type"] == "research_intake"
    assert rows["BRF2-001"]["required_next_evidence"] == (
        "paper_observation_evidence_shape_requiredfacts_disable_facts_and_review_ledger_mapping"
    )
    assert (
        "non_executing_trial_readiness=false"
        in rows["BRF2-001"]["authority_boundary"]
    )
    assert "promotion_scope=intake_only" in rows["BRF2-001"][
        "authority_boundary"
    ]
    assert rows["RBR2-001"]["current_decision"] == "keep_observing"
    assert rows["RBR2-001"]["promotion_scope"] == "not_applicable"
    assert rows["RBR2-001"]["next_checkpoint"] == (
        "RBR2-001_role_only_range_detector_classifier_merge_note"
    )
    assert artifact["counts"]["research_intake_group_count"] == 2
    assert artifact["research_intake_review"]["integrated"] is True
    assert artifact["research_intake_review"]["owner_policy_confirmation_required_now"] is False
    assert (
        artifact["research_intake_review"][
            "live_permission_change_recommended_now"
        ]
        is False
    )
    assert artifact["strategy_asset_state"][
        "research_intake_review_is_decision_support_only"
    ] is True
    assert artifact["strategy_asset_state"]["real_order_scope_change_recommended"] is False
    assert artifact["strategy_asset_state"]["l4_promotion_recommended"] is False
    assert artifact["interaction"]["calls_finalgate"] is False
    assert artifact["interaction"]["calls_operation_layer"] is False
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_strategy_asset_state_blocks_unscoped_promote_from_research_intake():
    module = _load_module()
    research = _research_intake_review()
    research["strategy_decision_provenance_rows"][0].pop("promotion_scope")
    research["strategy_decision_provenance_rows"][0].pop("promotion_target")

    artifact = module.build_strategygroup_strategy_asset_state(
        opportunity_review_work_loop_artifact=_opportunity_review_work_loop(),
        signal_coverage_artifact=_signal_coverage(),
        tier_policy=_tier_policy(),
        research_intake_review_artifact=research,
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    assert "strategy_asset_state.BRF2-001.unscoped_promote:not_applicable" in artifact[
        "safety_invariants"
    ]["source_forbidden_effects"]
    rows = {row["strategy_group_id"]: row for row in _asset_rows(artifact)}
    assert rows["BRF2-001"]["current_decision"] == "promote"
    assert rows["BRF2-001"]["promotion_scope"] == "not_applicable"
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_strategy_asset_state_records_observation_layer_role_review_and_no_action_queue():
    module = _load_module()
    signal = _signal_coverage()
    signal["checks"] = {
        "mainline_ready_signal_count": 0,
        "broader_actionable_would_enter_signal_count": 0,
    }
    signal["broader_observation"]["would_enter_signals"] = [
        {
            "strategy_group_id": "RBR-001",
            "symbol": "ADA/USDT:USDT",
            "side": "short",
            "confidence": "0.57",
            "signal_type": "would_enter",
            "reason_codes": [
                "rbr_range_context",
                "rbr_boundary_rejection_confirmed",
            ],
        }
    ]
    signal["broader_observation"]["high_priority_no_action_signals"].extend(
        [
            {
                "strategy_group_id": "BRF-001",
                "signal_type": "no_action",
                "coverage_review_priority": "P0_5",
                "symbol": "BTC/USDT:USDT",
                "side": "none",
                "confidence": "0.25",
                "reason_codes": ["brf_no_action_no_rally_extension"],
                "policy_l2_readiness": (
                    "blocked_requiredfacts_and_squeeze_classifier_needed"
                ),
                "policy_recommended_action": (
                    "keep_l1_observe_only_until_rally_failure_context_and_short_squeeze_classifier_are_attached"
                ),
            },
            {
                "strategy_group_id": "VCB-001",
                "signal_type": "no_action",
                "coverage_review_priority": "P1",
                "symbol": "LINK/USDT:USDT",
                "side": "none",
                "confidence": "0.25",
                "reason_codes": ["vcb_no_action_volume_expansion_missing"],
                "policy_l2_readiness": "blocked_classifier_redesign_required",
                "policy_recommended_action": (
                    "keep_l1_observe_only_until_false_breakout_disable_and_pre_entry_classifier_are_redesigned"
                ),
            },
        ]
    )

    artifact = module.build_strategygroup_strategy_asset_state(
        opportunity_review_work_loop_artifact=_opportunity_review_work_loop(),
        signal_coverage_artifact=signal,
        tier_policy=_tier_policy(),
        research_intake_review_artifact=_research_intake_review(),
    )

    assert artifact["observation_layer"]["p0_state"] == (
        "waiting_for_executable_fresh_signal"
    )
    assert artifact["observation_layer"]["latest_observe_only_would_enter"] == {
        "strategy_group_id": "RBR-001",
        "symbol": "ADA/USDT:USDT",
        "side": "short",
        "confidence": "0.57",
        "not_live_signal": True,
    }
    assert artifact["counts"]["role_review_row_count"] == 1
    assert artifact["role_review_rows"][0]["linked_intake_strategy_group_id"] == (
        "RBR2-001"
    )
    assert "role_review_decision" not in artifact["role_review_rows"][0]
    assert artifact["role_review_rows"][0]["role_review_outcome"] == (
        "review_range_detector_role_not_live_candidate"
    )
    assert artifact["counts"]["high_priority_no_action_attribution_count"] == 4
    queue = {row["strategy_group_id"]: row for row in artifact["no_action_attribution_queue"]}
    assert queue["BRF-001"]["attribution_class"] == "market_structure_or_path_risk"
    assert queue["BTPC-001"]["attribution_class"] == "fact_source_or_freshness"
    assert queue["LSR-001"]["attribution_class"] == "side_specific_rewrite"
    assert queue["VCB-001"]["attribution_class"] == "classifier_or_threshold"
    assert artifact["strategy_asset_state"]["role_review_is_decision_support_only"] is True
    assert artifact["strategy_asset_state"]["no_action_attribution_queue_recorded"] is True
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_strategy_asset_state_cli_writes_outputs(tmp_path, capsys):
    module = _load_module()
    opportunity_path = tmp_path / "opportunity.json"
    signal_path = tmp_path / "signal.json"
    policy_path = tmp_path / "policy.json"
    out_path = tmp_path / "strategy-asset-state.json"
    md_path = tmp_path / "strategy-asset-state.md"
    _write_json(opportunity_path, _opportunity_review_work_loop())
    _write_json(signal_path, _signal_coverage())
    _write_json(policy_path, _tier_policy())

    exit_code = module.main(
        [
            "--opportunity-review-work-loop-json",
            str(opportunity_path),
            "--signal-coverage-json",
            str(signal_path),
            "--tier-policy-json",
            str(policy_path),
            "--capture-gap-audit-json",
            str(tmp_path / "missing-capture-gap.json"),
            "--research-intake-review-json",
            str(tmp_path / "missing-research-intake-review.json"),
            "--output-json",
            str(out_path),
            "--output-owner-progress",
            str(md_path),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["status"] == "strategy_asset_state_ready"
    assert "Strategy Asset State" in md_path.read_text(encoding="utf-8")


def test_strategy_asset_state_cli_omitted_optional_generated_inputs_stay_missing(
    tmp_path, capsys
):
    module = _load_module()
    opportunity_path = tmp_path / "opportunity.json"
    signal_path = tmp_path / "signal.json"
    policy_path = tmp_path / "policy.json"
    out_path = tmp_path / "strategy-asset-state.json"
    md_path = tmp_path / "strategy-asset-state.md"
    _write_json(opportunity_path, _opportunity_review_work_loop())
    _write_json(signal_path, _signal_coverage())
    _write_json(policy_path, _tier_policy())

    exit_code = module.main(
        [
            "--opportunity-review-work-loop-json",
            str(opportunity_path),
            "--signal-coverage-json",
            str(signal_path),
            "--tier-policy-json",
            str(policy_path),
            "--output-json",
            str(out_path),
            "--output-owner-progress",
            str(md_path),
        ]
    )

    assert exit_code == 0
    capsys.readouterr()
    file_payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert file_payload["source_status"]["capture_gap_audit"] is None
    assert file_payload["source_status"]["research_intake_review"] is None


def test_strategy_asset_state_cli_requires_generated_inputs(tmp_path):
    module = _load_module()
    out_path = tmp_path / "strategy-asset-state.json"
    md_path = tmp_path / "strategy-asset-state.md"

    try:
        module.main(
            [
                "--output-json",
                str(out_path),
                "--output-owner-progress",
                str(md_path),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected missing generated inputs to fail argparse")
