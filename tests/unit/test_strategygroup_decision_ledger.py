from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_decision_ledger.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_decision_ledger",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _opportunity_decision_loop(*, forbidden: bool = False) -> dict:
    return {
        "status": "decision_loop_ready",
        "strategy_quality_decisions": {
            "rows": [
                {
                    "strategy_group_id": "BTPC-001",
                    "current_tier": "L2",
                    "strategy_quality_decision": (
                        "keep_l2_shadow_and_revise_fact_classifier_inputs"
                    ),
                    "reason": (
                        "btpc_proxy_replay_quality_ready_with_review_only_revisions"
                    ),
                    "next_stage": (
                        "feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_decision"
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
                    "real_order_authority": False,
                    "candidate_or_finalgate_authority": False,
                },
                {
                    "strategy_group_id": "VCB-001",
                    "current_tier": "L1",
                    "strategy_quality_decision": "revise_before_l2",
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
                    "real_order_authority": False,
                    "candidate_or_finalgate_authority": False,
                },
                {
                    "strategy_group_id": "RBR-001",
                    "current_tier": "L1",
                    "strategy_quality_decision": "park_until_new_edge",
                    "reason": "parked_negative_or_low_quality_evidence",
                    "next_stage": "park_until_new_evidence",
                    "evidence": {
                        "replay_sample_count": 1,
                        "would_enter_sample_count": 0,
                        "revise_sample_count": 0,
                    },
                    "not_l4_scope_change": True,
                    "real_order_authority": False,
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
        "decision_recommendations": [
            {
                "strategy_group_id": "BRF-001",
                "decision": "promote_review",
                "reason": "official windows produced BRF would_enter",
                "next_checkpoint": "BRF-001_forward_outcome_and_requiredfacts_review",
            },
            {
                "strategy_group_id": "MI-001",
                "decision": "identity_review",
                "reason": "MI emits repeated would_enter events",
                "next_checkpoint": "MI-001_registry_identity_review",
            },
            {
                "strategy_group_id": "LSR-001",
                "decision": "revise",
                "reason": "side-specific rewrite remains the dominant blocker",
                "next_checkpoint": "LSR-001_classifier_fact_source_revision_review",
            },
            {
                "strategy_group_id": "MPG-001",
                "decision": "coverage_visibility_review",
                "reason": "mainline no_action should stay visible",
                "next_checkpoint": "MPG-001_no_action_visibility_and_routing_audit",
            },
        ],
        "priority_line_closure": {
            "phase2_priority_strategy_lines": [
                {
                    "strategy_group_id": "BRF-001",
                    "decision": "promote_review",
                    "would_enter_count": 1,
                    "high_priority_no_action_count": 168,
                    "would_enter_forward_positive_count": 0,
                    "missed_no_action_forward_positive_count": 136,
                },
                {
                    "strategy_group_id": "LSR-001",
                    "decision": "revise",
                    "would_enter_count": 2,
                    "high_priority_no_action_count": 167,
                    "would_enter_forward_positive_count": 2,
                    "missed_no_action_forward_positive_count": 0,
                }
            ],
            "phase3_registry_identity_review": [
                {
                    "strategy_group_id": "MI-001",
                    "decision": "identity_review",
                    "would_enter_count": 23,
                    "high_priority_no_action_count": 0,
                    "would_enter_forward_positive_count": 22,
                    "missed_no_action_forward_positive_count": 0,
                }
            ],
            "phase4_visibility_review": [
                {
                    "strategy_group_id": "MPG-001",
                    "decision": "coverage_visibility_review",
                    "would_enter_count": 0,
                    "high_priority_no_action_count": 0,
                    "would_enter_forward_positive_count": 0,
                    "missed_no_action_forward_positive_count": 0,
                }
            ],
        },
        "owner_visibility_state": {
            "p0_state": "waiting_for_market",
            "p0_5_observation_state": "review_needed",
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
        "decision_ledger_rows": [
            {
                "strategy_group_id": "BRF2-001",
                "tier": "unknown",
                "opportunity_type": "research_intake",
                "decision": "promote",
                "reason": (
                    "research_intake:paper_observation_admission_candidate; "
                    "main_control_absorbs_asset_not_execution_authority"
                ),
                "required_next_evidence": (
                    "paper_observation_packet_shape_requiredfacts_disable_facts_and_review_ledger_mapping"
                ),
                "authority_boundary": (
                    "main_control_research_intake_review_only; "
                    "real_order_authority=false"
                ),
                "next_checkpoint": "BRF2-001_paper_observation_admission_packet",
            },
            {
                "strategy_group_id": "RBR2-001",
                "tier": "unknown",
                "opportunity_type": "research_intake",
                "decision": "keep_observing",
                "reason": (
                    "research_intake:role_only_intake_candidate; "
                    "main_control_absorbs_asset_not_execution_authority"
                ),
                "required_next_evidence": (
                    "range_detector_facts_and_failed_upside_expansion_classifier_merge_review"
                ),
                "authority_boundary": (
                    "main_control_research_intake_review_only; "
                    "real_order_authority=false"
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
            "real_order_authority": False,
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_decision_ledger_outputs_one_minimal_row_per_strategygroup():
    module = _load_module()

    packet = module.build_strategygroup_decision_ledger(
        opportunity_decision_loop_packet=_opportunity_decision_loop(),
        signal_coverage_packet=_signal_coverage(),
        tier_policy=_tier_policy(),
    )

    assert packet["status"] == "decision_ledger_ready"
    assert packet["counts"]["current_row_count"] == 4
    assert packet["decision"]["one_current_row_per_strategy_group"] is True
    assert packet["decision"]["raw_replay_samples_duplicated"] is False
    assert packet["decision"]["no_action_attribution_is_field_input_only"] is True
    rows = {row["strategy_group_id"]: row for row in packet["ledger_rows"]}
    assert list(rows["BTPC-001"].keys()) == packet["required_row_fields"]
    assert rows["BTPC-001"]["decision"] == "revise"
    assert rows["BTPC-001"]["opportunity_type"] == "would_enter"
    assert "no_action:" in rows["BTPC-001"]["reason"]
    assert rows["VCB-001"]["decision"] == "revise"
    assert rows["RBR-001"]["decision"] == "park"
    assert rows["LSR-001"]["decision"] == "revise"
    assert rows["LSR-001"]["opportunity_type"] == "no_action"
    assert packet["tier_review"]["counts"] == {
        "park": 1,
        "revise_before_tier_change": 3,
    }
    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["interaction"]["places_order"] is False
    assert packet["safety_invariants"]["order_created"] is False


def test_decision_ledger_rolls_completed_revision_rows_to_observation() -> None:
    module = _load_module()
    opportunity = _opportunity_decision_loop()
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

    packet = module.build_strategygroup_decision_ledger(
        opportunity_decision_loop_packet=opportunity,
        signal_coverage_packet=signal,
        tier_policy=_tier_policy(),
        post_revision_replay_packet=_post_revision_replay_review(),
    )

    rows = {row["strategy_group_id"]: row for row in packet["ledger_rows"]}
    assert rows["VCB-001"]["decision"] == "keep_observing"
    assert rows["VCB-001"]["required_next_evidence"] == (
        "tier_review_after_post_revision_quality"
    )
    assert rows["VCB-001"]["next_checkpoint"] == (
        "run_post_revision_stage_review_before_any_l2_or_l4_scope_change"
    )
    assert rows["VCB-001"]["reason"].endswith("post_revision_replay_passed:1_cases")
    assert rows["LSR-001"]["decision"] == "keep_observing"
    assert rows["BRF-001"]["decision"] == "keep_observing"
    assert packet["decision"]["default_next_step"] == (
        "run_post_revision_stage_review_before_any_tier_policy_change"
    )
    assert packet["tier_review"]["counts"] == {
        "keep_current_tier": 3,
        "park": 1,
        "revise_before_tier_change": 1,
    }
    assert packet["interaction"]["places_order"] is False
    assert packet["safety_invariants"]["order_created"] is False


def test_decision_ledger_blocks_forbidden_source_effect():
    module = _load_module()

    packet = module.build_strategygroup_decision_ledger(
        opportunity_decision_loop_packet=_opportunity_decision_loop(forbidden=True),
        signal_coverage_packet=_signal_coverage(),
        tier_policy=_tier_policy(),
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert "packet_0.safety_invariants.order_created" in packet["safety_invariants"][
        "source_forbidden_effects"
    ]
    assert packet["interaction"]["places_order"] is False


def test_decision_ledger_integrates_capture_gap_audit_as_review_input_only():
    module = _load_module()

    packet = module.build_strategygroup_decision_ledger(
        opportunity_decision_loop_packet=_opportunity_decision_loop(),
        signal_coverage_packet=_signal_coverage(),
        tier_policy=_tier_policy(),
        post_revision_replay_packet=_post_revision_replay_review(),
        capture_gap_audit_packet=_capture_gap_audit(),
    )

    rows = {row["strategy_group_id"]: row for row in packet["ledger_rows"]}
    assert rows["BRF-001"]["decision"] == "promote"
    assert rows["BRF-001"]["required_next_evidence"].startswith(
        "promotion_evidence_review_only:"
    )
    assert rows["MI-001"]["decision"] == "revise"
    assert rows["MI-001"]["required_next_evidence"].startswith(
        "registry_identity_classification:"
    )
    assert rows["LSR-001"]["decision"] == "revise"
    assert rows["LSR-001"]["required_next_evidence"].startswith(
        "classifier_fact_source_revision_review:"
    )
    assert rows["MPG-001"]["decision"] == "keep_observing"
    assert (
        "source_recommendation:coverage_visibility_review"
        in rows["MPG-001"]["reason"]
    )
    assert packet["counts"]["capture_gap_audit_group_count"] == 4
    assert packet["capture_gap_audit"]["integrated"] is True
    assert packet["capture_gap_audit"]["owner_decision_required_now"] is False
    assert packet["capture_gap_audit"]["live_permission_change_recommended_now"] is False
    assert packet["decision"]["capture_gap_audit_is_decision_support_only"] is True
    assert packet["decision"]["real_order_scope_change_recommended"] is False
    assert packet["decision"]["l4_promotion_recommended"] is False
    assert packet["interaction"]["places_order"] is False
    assert packet["safety_invariants"]["order_created"] is False


def test_decision_ledger_integrates_research_intake_review_as_review_input_only():
    module = _load_module()

    packet = module.build_strategygroup_decision_ledger(
        opportunity_decision_loop_packet=_opportunity_decision_loop(),
        signal_coverage_packet=_signal_coverage(),
        tier_policy=_tier_policy(),
        research_intake_review_packet=_research_intake_review(),
    )

    rows = {row["strategy_group_id"]: row for row in packet["ledger_rows"]}
    assert rows["BRF2-001"]["decision"] == "promote"
    assert rows["BRF2-001"]["opportunity_type"] == "research_intake"
    assert rows["BRF2-001"]["required_next_evidence"] == (
        "paper_observation_packet_shape_requiredfacts_disable_facts_and_review_ledger_mapping"
    )
    assert "tiny_live_ready=false" in rows["BRF2-001"]["authority_boundary"]
    assert rows["RBR2-001"]["decision"] == "keep_observing"
    assert rows["RBR2-001"]["next_checkpoint"] == (
        "RBR2-001_role_only_range_detector_classifier_merge_note"
    )
    assert packet["counts"]["research_intake_group_count"] == 2
    assert packet["research_intake_review"]["integrated"] is True
    assert packet["research_intake_review"]["owner_decision_required_now"] is False
    assert (
        packet["research_intake_review"][
            "live_permission_change_recommended_now"
        ]
        is False
    )
    assert packet["decision"][
        "research_intake_review_is_decision_support_only"
    ] is True
    assert packet["decision"]["real_order_scope_change_recommended"] is False
    assert packet["decision"]["l4_promotion_recommended"] is False
    assert packet["interaction"]["calls_finalgate"] is False
    assert packet["interaction"]["calls_operation_layer"] is False
    assert packet["interaction"]["places_order"] is False
    assert packet["safety_invariants"]["order_created"] is False


def test_decision_ledger_cli_writes_outputs(tmp_path, capsys):
    module = _load_module()
    opportunity_path = tmp_path / "opportunity.json"
    signal_path = tmp_path / "signal.json"
    policy_path = tmp_path / "policy.json"
    out_path = tmp_path / "ledger.json"
    md_path = tmp_path / "ledger.md"
    _write_json(opportunity_path, _opportunity_decision_loop())
    _write_json(signal_path, _signal_coverage())
    _write_json(policy_path, _tier_policy())

    exit_code = module.main(
        [
            "--opportunity-decision-loop-json",
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
    assert file_payload["status"] == "decision_ledger_ready"
    assert "StrategyGroup Decision Ledger" in md_path.read_text(encoding="utf-8")
