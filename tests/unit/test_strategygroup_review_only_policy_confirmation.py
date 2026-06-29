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


def _owner_policy_package() -> dict:
    policy_item_specs = [
        (
            "BRF-001:owner_policy_choice",
            "BRF-001",
            "promote_review_direction",
            "approve_promote_review_without_live_scope_change",
            "build_brf_squeeze_requiredfacts_forward_outcome_review",
        ),
        (
            "BTPC-001:owner_policy_choice",
            "BTPC-001",
            "keep_l2_shadow_or_revise_gate",
            "keep_l2_shadow_and_revise_fact_classifier_inputs",
            "continue_btpc_fact_source_attachment_and_classifier_review",
        ),
        (
            "LSR-001:owner_policy_choice",
            "LSR-001",
            "formalize_short_revival_rewrite",
            "formalize_short_revival_rewrite_without_live_scope_change",
            "build_lsr_short_revival_range_context_requiredfacts_review",
        ),
        (
            "MI-001:owner_policy_choice",
            "MI-001",
            "registry_identity",
            "open_formal_candidate_review_and_overlap_check",
            "open_mi_identity_overlap_symbol_concentration_review",
        ),
        (
            "CPM-RO-001:owner_policy_choice",
            "CPM-RO-001",
            "registry_identity",
            "keep_as_observation_asset_and_run_merge_review",
            "open_cpm_ro_semantic_source_merge_quality_review",
        ),
        (
            "MPG-001:member_policy_decision",
            "MPG-001",
            "member_tiering_exit_decay_policy",
            "approve_member_role_split_without_live_scope_expansion",
            "open_mpg_member_exit_decay_policy_review",
        ),
    ]
    return {
        "schema": "brc.strategygroup_owner_policy_package.v1",
        "status": "owner_policy_package_ready",
        "owner_policy_summary": {"owner_policy_item_count": 6},
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
        "owner_policy_items": [
            {
                "policy_item_id": policy_item_id,
                "strategy_group_id": strategy_group_id,
                "owner_policy_type": decision_type,
                "owner_policy_ready": True,
                "default_recommendation": default_recommendation,
                "strategy_review_checkpoint_if_approved": strategy_review_checkpoint,
                "next_checkpoint": f"{strategy_group_id}_next_checkpoint",
            }
            for (
                policy_item_id,
                strategy_group_id,
                decision_type,
                default_recommendation,
                strategy_review_checkpoint,
            ) in policy_item_specs
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
        },
    }


def test_review_only_policy_confirmation_builds_next_wave_queue():
    module = _load_module()
    confirmation = module.build_review_only_policy_confirmation(
        owner_policy_package=_owner_policy_package()
    )

    assert confirmation["status"] == "review_only_policy_confirmation_ready"
    assert confirmation["owner_confirmation"]["confirmed_default_recommendations"] is True
    assert confirmation["owner_confirmation"]["does_not_authorize_live_execution"] is True
    assert confirmation["source_package"] == {
        "source_role": "owner_policy_projection_source",
        "source_status": "owner_policy_source_ready",
        "owner_policy_item_count": 6,
    }
    assert "confirmed_decisions" not in confirmation
    assert len(confirmation["confirmed_policy_items"]) == 6
    assert len(confirmation["next_wave_queue"]) == 7

    policy_items = {
        row["policy_item_id"]: row for row in confirmation["confirmed_policy_items"]
    }
    assert policy_items["BRF-001:owner_policy_choice"]["selected_option_id"] == (
        "approve_promote_review"
    )
    assert policy_items["BTPC-001:owner_policy_choice"]["review_only_policy_effect"] == (
        "keep_l2_shadow_and_continue_fact_classifier_revision"
    )
    assert policy_items["MPG-001:member_policy_decision"][
        "does_not_expand_real_order_scope"
    ] is True
    assert all("decision_type" not in item for item in policy_items.values())
    assert policy_items["BRF-001:owner_policy_choice"]["owner_policy_type"] == (
        "promote_review_direction"
    )
    for item in policy_items.values():
        assert "forbidden_effects" not in item

    queue = {row["queue_id"]: row for row in confirmation["next_wave_queue"]}
    assert "signal-observation-perception-001" in queue
    assert queue["signal-observation-mi-001"]["actionable_task"] == (
        "open_mi_identity_overlap_symbol_concentration_review"
    )
    assert all("real_order_authority" not in row for row in queue.values())


def test_review_only_policy_confirmation_safety_invariants():
    module = _load_module()
    confirmation = module.build_review_only_policy_confirmation(
        owner_policy_package=_owner_policy_package()
    )

    assert (
        confirmation["completion_boundary"]["owner_policy_confirmation_required_now"]
        is False
    )
    assert (
        confirmation["completion_boundary"]["runtime_owner_intervention_required"]
        is False
    )
    assert "real_order_scope_expansion" in confirmation["completion_boundary"][
        "blocked_until_separate_owner_confirmation"
    ]
    assert confirmation["interaction"]["remote_interaction_count"] == 0
    assert confirmation["interaction"]["calls_finalgate"] is False
    assert confirmation["interaction"]["calls_operation_layer"] is False
    assert "real_order_authority" not in confirmation["safety_invariants"]
    assert "execution_intent_created" not in confirmation["safety_invariants"]
    assert confirmation["safety_invariants"]["registry_authority_changed"] is False

    snapshot = confirmation["owner_perception_snapshot"]
    assert snapshot["status"] == "owner_perception_snapshot_ready"
    assert snapshot["p0_state"] == "waiting_for_market"
    assert snapshot["signal_observation_review_state"] == (
        "review_only_policy_confirmed"
    )
    assert "confirmed_decision_count" not in snapshot
    assert snapshot["confirmed_policy_count"] == 6


def test_review_only_policy_confirmation_rejects_actionable_now_authority_mirror():
    module = _load_module()
    owner_package = _owner_policy_package()
    owner_package["safety_invariants"]["actionable_now"] = True

    try:
        module.build_review_only_policy_confirmation(
            owner_policy_package=owner_package
        )
    except ValueError as exc:
        assert "legacy authority mirrors" in str(exc)
        assert "actionable_now" in str(exc)
    else:
        raise AssertionError("expected legacy authority mirror to fail")


def test_review_only_policy_confirmation_rejects_mismatched_defaults():
    module = _load_module()
    owner_package = _owner_policy_package()
    owner_package["owner_policy_items"][0]["default_recommendation"] = (
        "unexpected_recommendation"
    )

    try:
        module.build_review_only_policy_confirmation(
            owner_policy_package=owner_package
        )
    except ValueError as exc:
        assert "default mismatch" in str(exc)
    else:
        raise AssertionError("expected mismatched default to fail")


def test_review_only_policy_confirmation_cli_writes_json_and_markdown(tmp_path, capsys):
    module = _load_module()
    owner_package = tmp_path / "owner-policy-package.json"
    output_json = tmp_path / "policy-confirmation.json"
    output_md = tmp_path / "policy-confirmation.md"
    owner_package.write_text(
        json.dumps(_owner_policy_package()),
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--owner-policy-package-json",
            str(owner_package),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    confirmation = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    assert stdout_payload["status"] == "review_only_policy_confirmation_ready"
    assert confirmation["status"] == "review_only_policy_confirmation_ready"
    assert "Owner Perception Snapshot" in markdown
    assert "Next Wave Queue" in markdown
    assert "Real order authority: `false`" not in markdown
    assert "| `real_order_authority` | `false` |" not in markdown


def test_review_only_policy_confirmation_cli_omitted_input_does_not_read_default(
    tmp_path,
):
    module = _load_module()

    try:
        module.main(
            [
                "--output-json",
                str(tmp_path / "policy-confirmation.json"),
                "--output-md",
                str(tmp_path / "policy-confirmation.md"),
            ]
        )
    except ValueError as exc:
        assert "owner policy package is not ready" in str(exc)
    else:
        raise AssertionError("expected omitted owner policy package to fail")
