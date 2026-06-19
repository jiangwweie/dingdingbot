from __future__ import annotations

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


def test_expansion_review_recommends_observe_only_review_not_l4_promotion():
    module = _load_module()

    packet = module.build_signal_coverage_expansion_review(
        signal_coverage_packet=_signal_coverage(),
        tier_policy=_tier_policy(),
    )

    assert packet["status"] == "review_needed_broader_observe_only_would_enter"
    assert packet["counts"]["broader_would_enter_signal_count"] == 2
    assert packet["counts"]["new_strategy_group_review_count"] == 2
    assert packet["interaction"]["level"] == (
        "L0_local_signal_coverage_expansion_review"
    )
    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["interaction"]["mutates_remote_files"] is False
    assert packet["interaction"]["approaches_real_order"] is False
    assert packet["decision"]["observation_scope_review_recommended"] is True
    assert packet["decision"]["real_order_scope_change_recommended"] is False
    assert packet["decision"]["l4_promotion_recommended"] is False
    rows = {row["strategy_group_id"]: row for row in packet["review_rows"]}
    assert rows["BTPC-001"]["current_tier"] == "L1"
    assert rows["BTPC-001"]["suggested_next_tier"] == (
        "L2_after_handoff_review_and_dry_run"
    )
    assert rows["BTPC-001"]["may_place_real_order_after_this_review"] is False
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["operator_command_plan"]["changes_tier_policy"] is False
    assert packet["safety_invariants"]["does_not_expand_l4_real_order_scope"] is True


def test_expansion_review_reports_no_review_when_no_broader_signal():
    module = _load_module()

    packet = module.build_signal_coverage_expansion_review(
        signal_coverage_packet=_signal_coverage(would_enter=False),
        tier_policy=_tier_policy(),
    )

    assert packet["status"] == "no_expansion_review_needed"
    assert packet["owner_state"] == "waiting_for_opportunity"
    assert packet["review_rows"] == []
    assert packet["decision"]["observation_scope_review_recommended"] is False


def test_expansion_review_blocks_forbidden_source_effect():
    module = _load_module()

    packet = module.build_signal_coverage_expansion_review(
        signal_coverage_packet=_signal_coverage(forbidden=True),
        tier_policy=_tier_policy(),
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert "source.order" in packet["safety_invariants"]["source_forbidden_effects"]
    assert packet["operator_command_plan"]["places_order"] is False


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
