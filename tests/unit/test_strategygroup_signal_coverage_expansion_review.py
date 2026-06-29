from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_signal_coverage_expansion_review.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_signal_coverage_expansion_review",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _signal_coverage(*, forbidden: bool = False, would_enter: bool = True) -> dict:
    return {
        "status": "mainline_no_signal_broader_would_enter"
        if would_enter
        else "mainline_and_broader_no_signal",
        "checks": {"forbidden_effects": ["source.order"] if forbidden else []},
        "broader_observation": {
            "would_enter_signals": [
                {
                    "strategy_group_id": "BTPC-001",
                    "symbol": "AVAX/USDT:USDT",
                    "side": "short",
                    "confidence": "0.62",
                    "reason_codes": ["btpc_structure_loss_confirmed"],
                },
                {
                    "strategy_group_id": "VCB-001",
                    "symbol": "LINK/USDT:USDT",
                    "side": "long",
                    "confidence": "0.60",
                    "reason_codes": ["vcb_breakout_close_confirmed"],
                },
            ]
            if would_enter
            else []
        },
        "safety_invariants": {
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
            "source_forbidden_effects": [],
        },
    }


def _tier_policy() -> dict:
    return {
        "current_strategy_groups": {
            "MPG-001": {"tier": "L4", "mode": "tiny_real_order_eligible"},
            "TEQ-001": {"tier": "L2", "mode": "shadow_candidate"},
        },
        "new_strategy_group_defaults": {
            "known_new_groups": {
                "BTPC": "L1",
                "VCB": "L1",
            }
        },
    }


def _expansion_policy() -> dict:
    return {
        "strategy_groups": {
            "BTPC-001": {
                "coverage_review_priority": "P0_5",
                "l2_readiness": "l2_shadow_candidate_observation_enabled",
                "recommended_action": "continue_l2_shadow_candidate_observation_without_l4_scope_change",
            },
            "VCB-001": {
                "coverage_review_priority": "P1",
                "l2_readiness": "blocked_classifier_redesign_required",
                "recommended_action": "keep_l1_observe_only_until_false_breakout_disable",
            },
            "RBR-001": {
                "coverage_review_priority": "P2",
                "l2_readiness": "blocked_parked_negative_evidence",
                "recommended_action": "keep_l1_or_park_as_range_vocabulary_until_materially_new_classifier_exists",
            },
        }
    }


def test_expansion_review_recommends_observe_only_review_not_l4_promotion():
    module = _load_module()

    packet = module.build_signal_coverage_expansion_review(
        signal_coverage_artifact=_signal_coverage(),
        tier_policy=_tier_policy(),
        expansion_policy=_expansion_policy(),
    )

    assert packet["status"] == "review_needed_broader_observe_only_would_enter"
    assert packet["counts"]["broader_would_enter_signal_count"] == 2
    assert packet["counts"]["actionable_review_row_count"] == 2
    assert packet["counts"]["new_strategy_group_review_count"] == 2
    assert packet["interaction"]["level"] == (
        "L0_local_signal_coverage_expansion_review"
    )
    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["interaction"]["mutates_remote_files"] is False
    assert packet["interaction"]["approaches_real_order"] is False
    assert "decision" not in packet
    review_outcome = packet["review_outcome_state"]
    assert review_outcome["observation_scope_review_recommended"] is True
    assert review_outcome["real_order_scope_change_recommended"] is False
    assert review_outcome["l4_promotion_recommended"] is False
    assert review_outcome["tradeability_decision_source"] is False
    rows = {row["strategy_group_id"]: row for row in packet["review_rows"]}
    assert rows["BTPC-001"]["current_tier"] == "L1"
    assert rows["BTPC-001"]["coverage_review_priority"] == "P0_5"
    assert rows["BTPC-001"]["policy_l2_readiness"] == (
        "l2_shadow_candidate_observation_enabled"
    )
    assert rows["BTPC-001"]["suggested_next_tier"] == (
        "L2_after_handoff_review_and_dry_run"
    )
    assert rows["BTPC-001"]["execution_boundary"] == (
        "observe-only; no candidate/order"
    )
    assert rows["BTPC-001"]["may_place_real_order_after_this_review"] is False
    assert packet["interaction"]["places_order"] is False
    assert packet["safety_invariants"]["tier_policy_changed"] is False
    assert "operator_command_plan" not in packet
    assert packet["safety_invariants"]["does_not_expand_l4_real_order_scope"] is True
    assert "execution_intent_created" not in packet["safety_invariants"]


def test_expansion_review_records_p2_parked_signal_without_priority_review():
    module = _load_module()
    signal_coverage = _signal_coverage()
    signal_coverage["broader_observation"]["would_enter_signals"] = [
        {
            "strategy_group_id": "RBR-001",
            "symbol": "ADA/USDT:USDT",
            "side": "short",
            "confidence": "0.55",
            "reason_codes": ["rbr_range_boundary_reversion"],
        }
    ]
    tier_policy = _tier_policy()
    tier_policy["new_strategy_group_defaults"]["known_new_groups"]["RBR"] = "L1"

    packet = module.build_signal_coverage_expansion_review(
        signal_coverage_artifact=signal_coverage,
        tier_policy=tier_policy,
        expansion_policy=_expansion_policy(),
    )

    assert packet["status"] == "low_priority_observe_only_would_enter_parked"
    assert packet["owner_state"] == "waiting_for_opportunity"
    assert packet["counts"]["review_row_count"] == 1
    assert packet["counts"]["actionable_review_row_count"] == 0
    assert packet["counts"]["low_priority_or_parked_review_row_count"] == 1
    assert "decision" not in packet
    review_outcome = packet["review_outcome_state"]
    assert review_outcome["observation_scope_review_recommended"] is False
    assert review_outcome["low_priority_observation_recorded"] is True
    assert review_outcome["real_order_scope_change_recommended"] is False
    row = packet["review_rows"][0]
    assert row["strategy_group_id"] == "RBR-001"
    assert row["coverage_review_priority"] == "P2"
    assert row["policy_l2_readiness"] == "blocked_parked_negative_evidence"
    assert row["may_place_real_order_after_this_review"] is False
    assert packet["observation_layer"]["latest_observe_only_would_enter"] == {
        "strategy_group_id": "RBR-001",
        "symbol": "ADA/USDT:USDT",
        "side": "short",
        "confidence": "0.55",
        "source": "signal_coverage_broader_observation",
        "not_live_signal": True,
    }
    assert packet["counts"]["role_review_row_count"] == 1
    role = packet["role_review_rows"][0]
    assert role["source_observation_strategy_group_id"] == "RBR-001"
    assert role["linked_intake_strategy_group_id"] == "RBR2-001"
    assert "role_review_decision" not in role
    assert role["role_review_outcome"] == "review_range_detector_role_not_live_candidate"
    assert role["authority_boundary"] == (
        "role_review_only; no_finalgate_no_operation_layer; no_exchange_write"
    )


def test_expansion_review_records_high_priority_no_action_attribution_queue():
    module = _load_module()
    signal_coverage = _signal_coverage(would_enter=False)
    signal_coverage["broader_observation"]["high_priority_no_action_signals"] = [
        {
            "strategy_group_id": "BRF-001",
            "symbol": "BTC/USDT:USDT",
            "side": "none",
            "confidence": "0.25",
            "signal_type": "no_action",
            "reason_codes": ["brf_no_action_no_rally_extension"],
            "policy_l2_readiness": (
                "blocked_requiredfacts_and_squeeze_classifier_needed"
            ),
            "policy_recommended_action": (
                "keep_l1_observe_only_until_rally_failure_context_and_short_squeeze_classifier_are_attached"
            ),
        },
        {
            "strategy_group_id": "BTPC-001",
            "symbol": "AVAX/USDT:USDT",
            "side": "none",
            "confidence": "0.25",
            "signal_type": "no_action",
            "reason_codes": ["btpc_disable_stale_signal_before_l2_review"],
            "policy_l2_readiness": "l2_shadow_candidate_observation_enabled",
            "policy_recommended_action": (
                "continue_l2_shadow_candidate_observation_without_l4_scope_change"
            ),
        },
    ]

    packet = module.build_signal_coverage_expansion_review(
        signal_coverage_artifact=signal_coverage,
        tier_policy=_tier_policy(),
        expansion_policy=_expansion_policy(),
    )

    assert packet["counts"]["high_priority_no_action_attribution_count"] == 2
    queue = {row["strategy_group_id"]: row for row in packet["no_action_attribution_queue"]}
    assert queue["BRF-001"]["attribution_class"] == "market_structure_or_path_risk"
    assert queue["BTPC-001"]["attribution_class"] == "fact_source_or_freshness"
    assert queue["BRF-001"]["authority_boundary"] == (
        "no_action_attribution_only; no_finalgate_no_operation_layer; "
        "no_exchange_write"
    )
    assert packet["observation_layer"]["signal_observation_state"] == (
        "observation_active"
    )


def test_expansion_review_reports_no_review_when_no_broader_signal():
    module = _load_module()

    packet = module.build_signal_coverage_expansion_review(
        signal_coverage_artifact=_signal_coverage(would_enter=False),
        tier_policy=_tier_policy(),
    )

    assert packet["status"] == "no_expansion_review_needed"
    assert packet["owner_state"] == "waiting_for_opportunity"
    assert packet["review_rows"] == []
    assert "decision" not in packet
    assert (
        packet["review_outcome_state"]["observation_scope_review_recommended"]
        is False
    )


def test_expansion_review_blocks_forbidden_source_effect():
    module = _load_module()

    packet = module.build_signal_coverage_expansion_review(
        signal_coverage_artifact=_signal_coverage(forbidden=True),
        tier_policy=_tier_policy(),
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert "source.order" in packet["safety_invariants"]["source_forbidden_effects"]
    assert packet["interaction"]["places_order"] is False
    assert packet["safety_invariants"]["order_created"] is False


def test_expansion_review_rejects_source_authority_mirrors():
    module = _load_module()
    signal_coverage = deepcopy(_signal_coverage())
    signal_coverage["checks"]["actionable_now"] = False
    signal_coverage["broader_observation"]["real_order_authority"] = False
    signal_coverage["broader_observation"]["would_enter_signals"][0][
        "actionable_now"
    ] = False
    signal_coverage["safety_invariants"]["real_order_authority"] = False

    artifact = module.build_signal_coverage_expansion_review(
        signal_coverage_artifact=signal_coverage,
        tier_policy=_tier_policy(),
        expansion_policy=_expansion_policy(),
    )

    forbidden = artifact["safety_invariants"]["source_forbidden_effects"]
    assert artifact["status"] == "blocked_forbidden_effect"
    assert (
        "signal_coverage.checks.legacy_authority_mirror_present:actionable_now"
    ) in forbidden
    assert (
        "signal_coverage.broader_observation."
        "legacy_authority_mirror_present:real_order_authority"
    ) in forbidden
    assert (
        "signal_coverage.would_enter_signals.BTPC-001."
        "legacy_authority_mirror_present:actionable_now"
    ) in forbidden
    assert (
        "signal_coverage.safety_invariants."
        "legacy_authority_mirror_present:real_order_authority"
    ) in forbidden
    assert artifact["review_outcome_state"]["tradeability_decision_source"] is False
    assert artifact["interaction"]["calls_operation_layer"] is False
    assert artifact["safety_invariants"]["operation_layer_called"] is False


def test_expansion_review_cli_writes_json_and_owner_progress(tmp_path, capsys):
    module = _load_module()
    signal_path = tmp_path / "signal-coverage.json"
    policy_path = tmp_path / "tier-policy.json"
    output_path = tmp_path / "review.json"
    owner_path = tmp_path / "review.md"
    signal_path.write_text(json.dumps(_signal_coverage()), encoding="utf-8")
    policy_path.write_text(json.dumps(_tier_policy()), encoding="utf-8")

    exit_code = module.main(
        [
            "--signal-coverage-json",
            str(signal_path),
            "--tier-policy-json",
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
    assert file_payload["scope"] == "strategygroup_signal_coverage_expansion_review"
    owner_text = owner_path.read_text(encoding="utf-8")
    assert "策略观察面扩展评审" in owner_text
    assert "BTPC-001" in owner_text
    assert (
        "| StrategyGroup | Symbol | Side | Confidence | Tier | Next tier | "
        "Action | Boundary |"
    ) in owner_text
    assert "observe-only; no candidate/order" in owner_text
