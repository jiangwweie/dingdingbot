from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_review_only_policy_confirmation.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_review_only_policy_confirmation",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _owner_decision_package() -> dict:
    card_specs = [
        (
            "BRF-001:owner_policy_decision",
            "BRF-001",
            "promote_review_direction",
            "approve_promote_review_without_live_scope_change",
            "build_brf_squeeze_requiredfacts_forward_outcome_review",
        ),
        (
            "BTPC-001:owner_policy_decision",
            "BTPC-001",
            "keep_l2_shadow_or_revise_gate",
            "keep_l2_shadow_and_revise_fact_classifier_inputs",
            "continue_btpc_fact_source_attachment_and_classifier_review",
        ),
        (
            "LSR-001:owner_policy_decision",
            "LSR-001",
            "formalize_short_revival_rewrite",
            "formalize_short_revival_rewrite_without_live_scope_change",
            "build_lsr_short_revival_range_context_requiredfacts_review",
        ),
        (
            "MI-001:owner_policy_decision",
            "MI-001",
            "registry_identity",
            "open_formal_candidate_review_and_overlap_check",
            "build_mi_identity_overlap_symbol_concentration_packet",
        ),
        (
            "CPM-RO-001:owner_policy_decision",
            "CPM-RO-001",
            "registry_identity",
            "keep_as_observation_asset_and_run_merge_review",
            "build_cpm_ro_semantic_source_merge_quality_packet",
        ),
        (
            "MPG-001:member_policy_decision",
            "MPG-001",
            "member_tiering_exit_decay_policy",
            "approve_member_role_split_without_live_scope_expansion",
            "build_mpg_member_exit_decay_policy_packet",
        ),
    ]
    return {
        "schema": "brc.strategygroup_owner_decision_package.v1",
        "status": "owner_decision_package_ready",
        "owner_decision_summary": {"decision_count": 6},
        "strategy_quality_snapshot": {
            "status": "ready",
            "p0_state": "waiting_for_market",
            "rows": [
                {
                    "strategy_group_id": "MPG-001",
                    "owner_state": "等待机会",
                    "system_found": "P0 selected lane has no executable fresh signal; member review is active.",
                },
                {
                    "strategy_group_id": "BRF-001",
                    "owner_state": "待复核",
                    "system_found": "observed 1 would_enter events",
                },
                {
                    "strategy_group_id": "BTPC-001",
                    "owner_state": "待调整",
                    "system_found": "observed 152 missed no_action forward positives",
                },
                {
                    "strategy_group_id": "LSR-001",
                    "owner_state": "待调整",
                    "system_found": "observed 2 would_enter events",
                },
                {
                    "strategy_group_id": "MI-001",
                    "owner_state": "身份待定",
                    "system_found": "observed 23 would_enter events",
                },
                {
                    "strategy_group_id": "CPM-RO-001",
                    "owner_state": "身份待定",
                    "system_found": "observed 18 would_enter events",
                },
            ],
        },
        "owner_decision_cards": [
            {
                "card_id": card_id,
                "strategy_group_id": strategy_group_id,
                "decision_type": decision_type,
                "decision_ready": True,
                "default_recommendation": default_recommendation,
                "next_system_action_if_approved": next_system_action,
                "next_checkpoint": f"{strategy_group_id}_next_checkpoint",
            }
            for (
                card_id,
                strategy_group_id,
                decision_type,
                default_recommendation,
                next_system_action,
            ) in card_specs
        ],
        "safety_invariants": {
            "registry_authority_changed": False,
            "tier_policy_changed": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "mpg_member_live_scope_expanded": False,
            "l4_real_order_scope_expanded": False,
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "exchange_write_called": False,
            "real_order_authority": False,
        },
    }


def test_review_only_policy_confirmation_builds_next_wave_queue():
    module = _load_module()
    packet = module.build_review_only_policy_confirmation(
        owner_decision_package=_owner_decision_package()
    )

    assert packet["status"] == "review_only_policy_confirmation_ready"
    assert packet["owner_confirmation"]["confirmed_default_recommendations"] is True
    assert packet["owner_confirmation"]["does_not_authorize_live_execution"] is True
    assert len(packet["confirmed_decisions"]) == 6
    assert len(packet["next_wave_queue"]) == 7

    decisions = {row["card_id"]: row for row in packet["confirmed_decisions"]}
    assert decisions["BRF-001:owner_policy_decision"]["selected_option_id"] == (
        "approve_promote_review"
    )
    assert decisions["BTPC-001:owner_policy_decision"]["review_only_policy_effect"] == (
        "keep_l2_shadow_and_continue_fact_classifier_revision"
    )
    assert decisions["MPG-001:member_policy_decision"][
        "does_not_expand_real_order_scope"
    ] is True

    queue = {row["queue_id"]: row for row in packet["next_wave_queue"]}
    assert "P05-PERCEPTION-001" in queue
    assert queue["P05-MI-001"]["actionable_task"] == (
        "build_mi_identity_overlap_symbol_concentration_packet"
    )
    assert queue["P05-CPM-RO-001"]["real_order_authority"] is False


def test_review_only_policy_confirmation_safety_invariants():
    module = _load_module()
    packet = module.build_review_only_policy_confirmation(
        owner_decision_package=_owner_decision_package()
    )

    assert packet["completion_boundary"]["owner_policy_confirmation_required_now"] is False
    assert packet["completion_boundary"]["runtime_owner_intervention_required"] is False
    assert "real_order_scope_expansion" in packet["completion_boundary"][
        "blocked_until_separate_owner_confirmation"
    ]
    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["interaction"]["calls_finalgate"] is False
    assert packet["interaction"]["calls_operation_layer"] is False
    assert packet["safety_invariants"]["real_order_authority"] is False
    assert packet["safety_invariants"]["registry_authority_changed"] is False

    snapshot = packet["owner_perception_snapshot"]
    assert snapshot["status"] == "owner_perception_snapshot_ready"
    assert snapshot["p0_state"] == "waiting_for_market"
    assert snapshot["p0_5_state"] == "review_only_policy_confirmed"
    assert snapshot["confirmed_decision_count"] == 6


def test_review_only_policy_confirmation_rejects_mismatched_defaults():
    module = _load_module()
    owner_package = _owner_decision_package()
    owner_package["owner_decision_cards"][0]["default_recommendation"] = (
        "unexpected_recommendation"
    )

    try:
        module.build_review_only_policy_confirmation(
            owner_decision_package=owner_package
        )
    except ValueError as exc:
        assert "default mismatch" in str(exc)
    else:
        raise AssertionError("expected mismatched default to fail")


def test_review_only_policy_confirmation_cli_writes_json_and_markdown(tmp_path, capsys):
    module = _load_module()
    owner_package = tmp_path / "owner-decision-package.json"
    output_json = tmp_path / "policy-confirmation.json"
    output_md = tmp_path / "policy-confirmation.md"
    owner_package.write_text(
        json.dumps(_owner_decision_package()),
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--owner-decision-package-json",
            str(owner_package),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    assert stdout_payload["status"] == "review_only_policy_confirmation_ready"
    assert packet["status"] == "review_only_policy_confirmation_ready"
    assert "Owner Perception Snapshot" in markdown
    assert "Next Wave Queue" in markdown
    assert "Real order authority: `false`" in markdown
